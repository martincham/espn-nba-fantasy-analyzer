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
from gui.board import DraftBoard  # noqa: E402
from gui.server import serve  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    parser = argparse.ArgumentParser(prog="python3 -m gui", description="Draft Room: fantasy NBA auction draft board.")
    parser.add_argument("--port", type=int, default=8000, help="default 8000")
    parser.add_argument("--settings", default=os.path.join(ROOT, "settings.txt"), help="path to settings.txt")
    parser.add_argument("--refresh", action="store_true", help="re-download the player pool from ESPN")
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    args = parser.parse_args()

    board = DraftBoard(
        settings_path=args.settings,
        pool_path=os.path.join(ROOT, "draftPool.json"),
        state_path=os.path.join(ROOT, "draftState.json"),
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
        server = serve(board, port=args.port)
    except OSError as ex:
        print(f"Couldn't start on port {args.port}: {ex.strerror}. Try --port {args.port + 1}.", file=sys.stderr)
        return 1
    url = f"http://127.0.0.1:{args.port}"
    print(f"{board.league.name} · {len(board.players)} players · Draft Room running at {url}  (Ctrl+C to stop)", flush=True)
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
