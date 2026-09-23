"""Development auto-reload for `python3 -m gui --reload` (standard library only).

A small supervisor runs the real server as a child process and restarts it
whenever a .py file under gui/ or library/ changes. The page notices the
restart (and any edit to gui/static) through /api/version and reloads itself.
"""

from __future__ import annotations

import glob
import os
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from typing import Dict, List, Optional

CHILD_ENV = "DRAFTROOM_RELOAD_CHILD"
POLL_SECONDS = 0.5


def _interrupt(*_) -> None:
    raise KeyboardInterrupt


def is_child() -> bool:
    return os.environ.get(CHILD_ENV) == "1"


def _python_files(root: str) -> Dict[str, int]:
    files = {}
    for folder in ("gui", "library"):
        for path in glob.glob(os.path.join(root, folder, "**", "*.py"), recursive=True):
            try:
                files[path] = os.stat(path).st_mtime_ns
            except OSError:
                pass  # deleted mid-scan
    return files


def _changed(before: Dict[str, int], after: Dict[str, int]) -> List[str]:
    return sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))


def supervise(root: str, child_args: List[str], url: str, open_browser: bool) -> int:
    """Run `python -m gui <child_args>` and restart it when Python files change."""
    env = dict(os.environ, **{CHILD_ENV: "1"})
    # Treat a terminate signal like Ctrl+C so the child server is always stopped too.
    signal.signal(signal.SIGTERM, _interrupt)
    command = [sys.executable, "-m", "gui", *child_args]
    child: Optional[subprocess.Popen] = None
    print("Auto-reload is on: watching gui/ and library/ for changes.", flush=True)
    if open_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    try:
        while True:
            files = _python_files(root)
            child = subprocess.Popen(command, cwd=root, env=env)
            while True:
                time.sleep(POLL_SECONDS)
                now = _python_files(root)
                changed = _changed(files, now)
                if changed:
                    names = ", ".join(os.path.relpath(p, root) for p in changed[:3])
                    print(f"\nChanged: {names}. Restarting…", flush=True)
                    break
                if child.poll() is not None and child.returncode != 0:
                    print("The server stopped with an error. Fix it and save; it will restart.", flush=True)
                    while not _changed(files, _python_files(root)):
                        time.sleep(POLL_SECONDS)
                    print("Change detected. Restarting…", flush=True)
                    break
                if child.poll() is not None:  # clean exit
                    return 0
            _stop(child)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    finally:
        if child is not None:
            _stop(child)


def _stop(child: subprocess.Popen) -> None:
    if child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()
