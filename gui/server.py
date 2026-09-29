"""Local HTTP server for the draft GUI (standard library only).

GET  /                 the app
GET  /static/<file>    CSS / JS
GET  /api/board        full snapshot
GET  /api/version      board revision (open pages re-fetch when it changes) and
                       restart/static-file fingerprint (auto-reload)
POST /api/<action>     apply an edit, then return {"board": snapshot, "error": msg|null}
                       (POST /api/plan starts the recommended-team search; the snapshot's
                       "plan" shows it building, then ready; plan-switch, plan-use, plan-restore and
                       plan-save edit it or add its players to my team)

With a password (hosted use), every request needs it through HTTP Basic auth (the
username is ignored) or the session cookie handed out with the page, which lasts
SESSION_DAYS so browsers that forget Basic credentials on quit don't ask again.
Changing the password signs everyone out. Without one, only requests addressed to 127.0.0.1 or localhost
are served, so another site can't reach the app by pointing its own name at this
computer (DNS rebinding). POSTs from another site's page are refused either way.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import mimetypes
import os
import socketserver
import time
import traceback
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

from library import draft
from gui.board import DraftBoard

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
STATIC_ROOT = os.path.realpath(STATIC_DIR)
MAX_BODY = 1_000_000
BOOT_ID = f"{os.getpid()}-{time.time():.0f}"  # changes on every (re)start
LOCAL_NAMES = ("127.0.0.1", "localhost")
SESSION_COOKIE = "draftroom"
SESSION_DAYS = 90


def session_token(password: str) -> str:
    """Cookie value for a password: a slow hash, so a leaked cookie doesn't give the password away cheaply."""
    return hashlib.pbkdf2_hmac("sha256", password.encode(), b"draftroom-session", 200_000).hex()


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
        "settings": lambda b: board.update_settings(**{k: b[k] for k in ("marketScale", "rated", "ignorePlayers", "replacement", "fillRate", "core", "fadeStart", "fadeEnd", "punt", "fitModel", "projLine", "catWeights", "pricing", "planObjective", "planFocus") if k in b}),
        "state": lambda b: board.replace_state(b["state"], b.get("rev")),
        "refresh": lambda b: board.load(refresh=True),
        "plan": lambda b: board.build_plan(),
        "avoid": lambda b: board.set_avoid(pid(b), bool(b.get("avoid", True))),
        "plan-switch": lambda b: board.switch_plan(int(b["out"]), int(b["in"])),
        "plan-restore": lambda b: board.restore_plan(),
        "plan-use": lambda b: board.use_plan(list(b["ids"])),
        "plan-save": lambda b: board.save_plan(),
    }


def make_handler(board: DraftBoard, reload: bool = False, password: Optional[str] = None):
    actions = _actions(board)
    expected = password.encode() if password else None
    token = session_token(password) if password else None

    class Handler(BaseHTTPRequestHandler):
        server_version = "DraftRoom/1"

        def log_message(self, fmt, *args):  # quiet: only log errors
            pass

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            if self.renew_session:
                self.send_header("Set-Cookie", f"{SESSION_COOKIE}={token}; Max-Age={SESSION_DAYS * 86400}; Path=/; Secure; HttpOnly; SameSite=Lax")
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: Any) -> None:
            self._send(status, json.dumps(payload, separators=(",", ":")).encode(), "application/json")

        def _has_session(self) -> bool:
            cookies = SimpleCookie()
            try:
                cookies.load(self.headers.get("Cookie") or "")
            except CookieError:
                return False
            given = cookies.get(SESSION_COOKIE)
            return given is not None and hmac.compare_digest(given.value.encode(), token.encode())

        def _authorized(self) -> bool:
            """True without a password, or when the request carries it (Basic auth, any username) or the session cookie.

            A Basic login, or opening the page, (re)issues the cookie for another SESSION_DAYS."""
            self.renew_session = False  # the handler serves every request on a kept-alive connection
            if expected is None:
                return True
            page = urlparse(self.path).path in ("/", "/index.html")
            if self._has_session():
                self.renew_session = page
                return True
            scheme, _, encoded = (self.headers.get("Authorization") or "").partition(" ")
            if scheme.lower() == "basic":
                try:
                    given = base64.b64decode(encoded, validate=True).partition(b":")[2]
                except (binascii.Error, ValueError):
                    given = b""
                if hmac.compare_digest(given, expected):
                    self.renew_session = True
                    return True
            body = b"Password required."
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Draft Room", charset="UTF-8"')
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return False

        def _local_host(self) -> bool:
            """Without a password, refuse requests addressed to any other name (DNS rebinding)."""
            host = self.headers.get("Host")
            if expected is not None or host is None or urlparse(f"//{host}").hostname in LOCAL_NAMES:
                return True
            self._send(403, f"Open the Draft Room at http://127.0.0.1:{self.server.server_port} instead.".encode(), "text/plain")
            return False

        def _same_origin(self) -> bool:
            """Refuse POSTs sent by another site's page (browsers add Origin to those)."""
            origin = self.headers.get("Origin")
            return origin is None or urlparse(origin).netloc == self.headers.get("Host")

        def do_GET(self):
            if not self._authorized() or not self._local_host():
                return
            path = urlparse(self.path).path
            if path == "/api/board":
                return self._json(200, board.snapshot())
            if path == "/api/version":
                return self._json(200, {"reload": reload, "boot": BOOT_ID, "static": static_fingerprint() if reload else 0, "rev": board.rev})
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
            if not self._authorized() or not self._local_host():
                return
            if not self._same_origin():
                return self._json(403, {"error": "Requests from other sites aren't allowed."})
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
        # can stall for tens of seconds on some Macs, and we don't need the name.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def serve(board: DraftBoard, host: str = "127.0.0.1", port: int = 8000, reload: bool = False, password: Optional[str] = None) -> DraftServer:
    return DraftServer((host, port), make_handler(board, reload, password))
