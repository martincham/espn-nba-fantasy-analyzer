import base64
import http.client
import json
import os
import tempfile
import threading
import unittest
from unittest import mock

from gui.board import load_settings
from gui.server import serve


def basic(password, user="friend"):
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


class ServerCase(unittest.TestCase):
    password = None

    @classmethod
    def setUpClass(cls):
        board = mock.MagicMock()
        board.snapshot.return_value = {"ok": True}
        board.reset_draft.return_value = None  # no error
        cls.board = board
        cls.httpd = serve(board, port=0, password=cls.password)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def request(self, method, path, headers=None, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            response.read()
            return response
        finally:
            conn.close()


class PasswordTest(ServerCase):
    """With a password, every request needs it."""

    password = "correct horse"

    def test_asks_for_the_password(self):
        for method, path in [("GET", "/"), ("GET", "/static/app.js"), ("GET", "/api/board"), ("POST", "/api/reset-draft")]:
            response = self.request(method, path)
            self.assertEqual(response.status, 401, path)
            self.assertIn("Basic", response.getheader("WWW-Authenticate"))
        self.board.reset_draft.assert_not_called()

    def test_wrong_password(self):
        for header in [basic("wrong"), basic(""), "Basic not-base64!", "Bearer correct horse"]:
            self.assertEqual(self.request("GET", "/api/board", {"Authorization": header}).status, 401, header)

    def test_right_password_any_username(self):
        for user in ["friend", ""]:
            self.assertEqual(self.request("GET", "/api/board", {"Authorization": basic(self.password, user)}).status, 200)
        self.assertEqual(self.request("GET", "/", {"Authorization": basic(self.password)}).status, 200)

    def test_login_hands_out_a_lasting_session_cookie(self):
        cookie = self.request("GET", "/", {"Authorization": basic(self.password)}).getheader("Set-Cookie")
        for flag in ["Max-Age=7776000", "Secure", "HttpOnly", "SameSite=Lax"]:
            self.assertIn(flag, cookie)
        session = cookie.partition(";")[0]
        self.assertEqual(self.request("GET", "/api/board", {"Cookie": session}).status, 200)
        self.assertEqual(self.request("POST", "/api/reset-draft", {"Cookie": f"other=1; {session}"}, body=b"{}").status, 200)
        # Opening the page extends the session; API calls don't resend it.
        self.assertIsNotNone(self.request("GET", "/", {"Cookie": session}).getheader("Set-Cookie"))
        self.assertIsNone(self.request("GET", "/static/app.js", {"Cookie": session}).getheader("Set-Cookie"))

    def test_wrong_session_cookie(self):
        for cookie in ["draftroom=", "draftroom=abc", 'draftroom="', "other=1"]:
            response = self.request("GET", "/api/board", {"Cookie": cookie})
            self.assertEqual(response.status, 401, cookie)
            self.assertIsNone(response.getheader("Set-Cookie"))

    def test_new_password_ends_old_sessions(self):
        from gui.server import session_token
        self.assertNotEqual(session_token(self.password), session_token(self.password + "!"))
        self.assertEqual(self.request("GET", "/api/board", {"Cookie": f"draftroom={session_token('old one')}"}).status, 401)


class OriginTest(ServerCase):
    """POSTs from another site's page are refused, with or without a password."""

    def post(self, headers):
        return self.request("POST", "/api/reset-draft", headers, body=b"{}").status

    def test_refuses_other_sites(self):
        self.board.reset_draft.reset_mock()
        host = f"127.0.0.1:{self.httpd.server_address[1]}"
        self.assertEqual(self.post({"Host": host, "Origin": "https://evil.example"}), 403)
        self.board.reset_draft.assert_not_called()

    def test_allows_the_app_itself(self):
        host = f"127.0.0.1:{self.httpd.server_address[1]}"
        self.assertEqual(self.post({"Host": host, "Origin": f"http://{host}"}), 200)
        self.assertEqual(self.post({"Host": host}), 200)  # scripts and old browsers send no Origin


class RebindingTest(ServerCase):
    """Without a password, only requests addressed to this computer are served."""

    def test_refuses_other_names(self):
        self.board.reset_draft.reset_mock()
        port = self.httpd.server_address[1]
        host = f"evil.example:{port}"
        self.assertEqual(self.request("GET", "/api/board", {"Host": host}).status, 403)
        self.assertEqual(self.request("POST", "/api/reset-draft", {"Host": host, "Origin": f"http://{host}"}, b"{}").status, 403)
        self.board.reset_draft.assert_not_called()

    def test_allows_local_names(self):
        port = self.httpd.server_address[1]
        for host in [f"127.0.0.1:{port}", f"localhost:{port}", "localhost"]:
            self.assertEqual(self.request("GET", "/api/board", {"Host": host}).status, 200, host)


class HostedNamesTest(ServerCase):
    """With a password, any name works: the password is the protection."""

    password = "pw"

    def test_any_name_with_the_password(self):
        headers = {"Host": "oaks-draft.fly.dev", "Authorization": basic(self.password)}
        self.assertEqual(self.request("GET", "/api/board", headers).status, 200)


class CommandLineTest(unittest.TestCase):
    def test_ignores_generic_host_and_port(self):
        from gui import __main__ as cli

        server = mock.MagicMock()
        server.serve_forever.side_effect = KeyboardInterrupt
        env = {"HOST": "somebody.local", "PORT": "3000"}
        with mock.patch.dict(os.environ, env), mock.patch.object(cli, "DraftBoard"), mock.patch.object(
            cli, "serve", return_value=server
        ) as serve, mock.patch("sys.argv", ["gui", "--no-browser"]), mock.patch("builtins.print"):
            self.assertEqual(cli.main(), 0)
        self.assertEqual((serve.call_args.kwargs["host"], serve.call_args.kwargs["port"]), ("127.0.0.1", 8000))


class SettingsEnvTest(unittest.TestCase):
    def test_environment_overrides_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "settings.txt")
            with open(path, "w") as f:
                json.dump({"leagueId": 1, "espn_s2": "file", "SWID": "{file}", "ignorePlayers": 2}, f)
            with mock.patch.dict(os.environ, {"ESPN_S2": "env", "ESPN_SWID": "{env}", "ESPN_LEAGUE_ID": ""}):
                settings = load_settings(path)
        self.assertEqual((settings["espn_s2"], settings["SWID"]), ("env", "{env}"))
        self.assertEqual((settings["leagueId"], settings["ignorePlayers"]), (1, 2))  # empty variables don't override

    def test_environment_without_file(self):
        with mock.patch.dict(os.environ, {"ESPN_LEAGUE_ID": "123"}):
            self.assertEqual(load_settings("/nonexistent/settings.txt")["leagueId"], "123")


if __name__ == "__main__":
    unittest.main()
