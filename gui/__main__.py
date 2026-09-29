"""Run the draft GUI:  python3 -m gui  (from the repo root)."""

from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser

try:
    import espn_api  # noqa: F401
except ModuleNotFoundError:
    sys.exit(
        f"espn-api isn't installed for this Python ({sys.executable}).\n"
        "Install it with:  python3 -m pip install espn-api\n"
        "or run the GUI with the same Python you use for main.py."
    )

from library import draft  # noqa: E402
from gui import reloader  # noqa: E402
from gui.board import DraftBoard  # noqa: E402
from gui.server import serve  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_HOSTS = ("127.0.0.1", "localhost")
PASSWORD_ENV = "DRAFTROOM_PASSWORD"


def _url(host: str, port: int) -> str:
    """Where to open the app: 0.0.0.0 listens everywhere, including this computer."""
    return f"http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}"


def main() -> int:
    parser = argparse.ArgumentParser(prog="python3 -m gui", description="Draft Room: fantasy NBA auction draft board.")
    parser.add_argument("--host", default="127.0.0.1", help="default 127.0.0.1 (this computer only); 0.0.0.0 for every network")
    parser.add_argument("--port", type=int, default=8000, help="default 8000")
    parser.add_argument("--data-dir", default=os.environ.get("DRAFTROOM_DATA", ROOT), help="folder for draftPool.json and draftState.json (default: the repo folder)")
    parser.add_argument("--settings", help="path to settings.txt (default: in the data folder)")
    parser.add_argument("--refresh", action="store_true", help="re-download the player pool from ESPN")
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    parser.add_argument("--reload", action="store_true", help="restart when Python files change and refresh the page (for development)")
    args = parser.parse_args()
    if not args.host:
        parser.error("--host can't be empty")
    settings = args.settings or os.path.join(args.data_dir, "settings.txt")
    password = os.environ.get(PASSWORD_ENV) or None
    if args.host not in LOCAL_HOSTS and not password:
        print(f"Set {PASSWORD_ENV} before listening on {args.host}: anyone who can reach the app can change or reset your draft.", file=sys.stderr)
        return 1

    if args.reload and not reloader.is_child():
        child_args = ["--host", args.host, "--port", str(args.port), "--data-dir", args.data_dir, "--settings", settings, "--no-browser", "--reload"]
        if args.refresh:
            child_args.append("--refresh")
        return reloader.supervise(ROOT, child_args, _url(args.host, args.port), not args.no_browser)

    board = DraftBoard(
        settings_path=settings,
        pool_path=os.path.join(args.data_dir, "draftPool.json"),
        state_path=os.path.join(args.data_dir, "draftState.json"),
    )
    print("Loading player pool...", flush=True)
    try:
        board.load(refresh=args.refresh)
    except draft.EspnError as ex:
        print(f"Couldn't load the player pool: {ex}", file=sys.stderr)
        return 1
    for warning in board.warnings:
        print(f"Note: {warning}", flush=True)

    try:
        server = serve(board, host=args.host, port=args.port, reload=args.reload, password=password)
    except OSError as ex:
        print(f"Couldn't start on port {args.port}: {ex.strerror}. Try --port {args.port + 1}.", file=sys.stderr)
        return 1
    url = _url(args.host, args.port)
    lock = " · password on" if password else ""
    print(f"{board.league.name} · {len(board.players)} players · Draft Room running at {url}{lock}  (Ctrl+C to stop)", flush=True)
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
