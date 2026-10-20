"""The Windows desktop proxy is available to long-running Workers."""

import os
import unittest
from unittest.mock import patch

import db


class WindowsProxyFallbackTests(unittest.TestCase):
    def test_uses_system_proxy_when_launcher_has_no_proxy_environment(self):
        with patch.object(db.os, "name", "nt"), patch.object(
            db, "getproxies", return_value={"http": "http://127.0.0.1:17890", "https": "http://127.0.0.1:17890"}
        ), patch.dict(os.environ, {}, clear=True):
            db._use_windows_system_proxy()
            self.assertEqual(os.environ["HTTP_PROXY"], "http://127.0.0.1:17890")
            self.assertEqual(os.environ["HTTPS_PROXY"], "http://127.0.0.1:17890")

    def test_keeps_explicit_proxy_configuration(self):
        with patch.object(db.os, "name", "nt"), patch.object(
            db, "getproxies", return_value={"https": "http://127.0.0.1:17890"}
        ), patch.dict(os.environ, {"HTTPS_PROXY": "http://explicit:8080"}, clear=True):
            db._use_windows_system_proxy()
            self.assertEqual(os.environ["HTTPS_PROXY"], "http://explicit:8080")


if __name__ == "__main__":
    unittest.main()
