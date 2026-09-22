import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from entrust import browser


class FakeContext:
    def __init__(self, cookies=None):
        self._cookies = cookies or []
        self.added_cookies = []

    def cookies(self):
        return self._cookies

    def add_cookies(self, cookies):
        self.added_cookies.extend(cookies)


class SessionCookiesTest(unittest.TestCase):
    def test_saves_and_restores_session_cookies(self):
        cookies = [{"name": "session", "value": "opaque", "domain": ".example.com", "path": "/"}]
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory)
            state_file = profile / "session_cookies.json"
            with patch.object(browser, "USER_DATA_DIR", profile), patch.object(
                browser, "SESSION_COOKIES_FILE", state_file
            ):
                self.assertEqual(browser.save_session_cookies(FakeContext(cookies)), 1)
                self.assertEqual(json.loads(state_file.read_text(encoding="utf-8")), cookies)
                self.assertEqual(state_file.stat().st_mode & 0o777, 0o600)

                restored = FakeContext()
                self.assertEqual(browser.restore_session_cookies(restored), 1)
                self.assertEqual(restored.added_cookies, cookies)


if __name__ == "__main__":
    unittest.main()
