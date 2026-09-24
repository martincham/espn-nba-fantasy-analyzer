"""Local HTTP server for the draft GUI (standard library only).

GET  /                 the app
GET  /static/<file>    CSS / JS
GET  /api/board        full snapshot
GET  /api/version      restart/static-file fingerprint (auto-reload)
POST /api/<action>     apply an edit, then return {"board": snapshot, "error": msg|null}
"""

from __future__ import annotations

import json
import mimetypes
import os
import socketserver
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

from library import draft
from gui.board import DraftBoard

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
STATIC_ROOT = os.path.realpath(STATIC_DIR)
MAX_BODY = 1_000_000
BOOT_ID = f"{os.getpid()}-{time.time():.0f}"  # changes on every (re)start


def static_fingerprint() -> int:
    """Newest modification time in gui/static, so edits there trigger a page reload."""
    newest = 0
    for folder, _, files in os.walk(STATIC_ROOT):
        for name in files:
            try:
                newest = max(newest, os.stat(os.path.join(folder, name)).st_mtime_ns)
            except OSError:
                pass
    return newest


def _actions(board: DraftBoard) -> Dict[str, Callable[[Dict[str, Any]], Optional[str]]]:
    def pid(body):
        return int(body["id"])

    def opt(body, key):
        return None if body.get(key) is None else float(body[key])

    return {
        "adjust": lambda b: board.adjust(pid(b), **{k: b[k] for k in ("delta", "gpDelta", "expMin", "cost", "note") if k in b}),
        "reset-adjustments": lambda b: board.reset_adjustments(),
        "pick": lambda b: board.pick(pid(b), b.get("status"), opt(b, "price")),
        "price": lambda b: board.set_price(pid(b), float(b["price"])),
        "move": lambda b: board.move(pid(b), int(b["slot"]), opt(b, "price")),
        "clear-roster": lambda b: board.clear_roster(),
        "reset-draft": lambda b: board.reset_draft(),
        "settings": lambda b: board.update_settings(**{k: b[k] for k in ("marketScale", "rated", "ignorePlayers", "replacement", "core", "fadeStart", "fadeEnd", "punt", "fitModel") if k in b}),
        "state": lambda b: board.replace_state(b["state"]),
        "refresh": lambda b: board.load(refresh=True),
    }


def make_handler(board: DraftBoard, reload: bool = False):
    actions = _actions(board)

    class Handler(BaseHTTPRequestHandler):
        server_version = "DraftRoom/1"

        def log_message(self, fmt, *args):  # quiet: only log errors
            pass

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: Any) -> None:
            self._send(status, json.dumps(payload, separators=(",", ":")).encode(), "application/json")

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/board":
                return self._json(200, board.snapshot())
            if path == "/api/version":
                return self._json(200, {"reload": reload, "boot": BOOT_ID, "static": static_fingerprint() if reload else 0})
            if path in ("/", "/index.html"):
                path = "/static/index.html"
            if path.startswith("/static/"):
                # Resolve and confine to STATIC_DIR: rejects "..", absolute paths and symlinks out.
                full = os.path.realpath(os.path.join(STATIC_DIR, path[len("/static/"):].lstrip("/")))
                if os.path.commonpath([full, STATIC_ROOT]) != STATIC_ROOT or not os.path.isfile(full):
                    return self._send(404, b"Not found", "text/plain")
                with open(full, "rb") as f:
                    body = f.read()
                ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
                if ctype.startswith("text/") or ctype.endswith("javascript"):
                    ctype += "; charset=utf-8"
                return self._send(200, body, ctype)
            self._send(404, b"Not found", "text/plain")

        def do_POST(self):
            path = urlparse(self.path).path
            action = actions.get(path[len("/api/"):]) if path.startswith("/api/") else None
            if action is None:
                return self._json(404, {"error": "Unknown action."})
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                return self._json(413, {"error": "Request too large."})
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                error = action(body)
            except draft.EspnError as ex:
                error = str(ex)
            except (KeyError, ValueError, TypeError) as ex:
                return self._json(400, {"error": f"Bad request: {ex}"})
            except Exception:  # keep the server alive; show the error in the UI
                traceback.print_exc()
                error = "Something went wrong on the server. See the terminal for details."
            self._json(200, {"board": board.snapshot(), "error": error})

    return Handler


class DraftServer(ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self):
        # HTTPServer.server_bind does a reverse-DNS lookup (socket.getfqdn) that
        # can stall for tens of seconds on some Macs. We only serve localhost.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def serve(board: DraftBoard, host: str = "127.0.0.1", port: int = 8000, reload: bool = False) -> DraftServer:
    return DraftServer((host, port), make_handler(board, reload))
