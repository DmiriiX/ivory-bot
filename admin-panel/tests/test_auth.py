import hashlib
import hmac
import importlib.util
import json
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

path = Path(__file__).resolve().parents[1] / "app.py"
spec = importlib.util.spec_from_file_location("ivory_admin", path)
admin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admin)


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.patch = patch.multiple(admin,
            TG_TOKEN="test-telegram-token",
            GITHUB_TOKEN="test-github-token",
            BASE="https://admin.example.com",
            BOT_SECRET="test_webhook_secret",
            ADMIN_IDS={12345},
        )
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def signed(self, user=12345, timestamp=None):
        data = {"auth_date": str(timestamp if timestamp is not None else int(time.time())), "user": json.dumps({"id": user}, separators=(",", ":"))}
        check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
        secret = hmac.new(b"WebAppData", admin.TG_TOKEN.encode(), hashlib.sha256).digest()
        data["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        return urlencode(data)

    def test_valid_admin_signature(self):
        self.assertEqual(admin.authenticate(self.signed())["id"], 12345)

    def test_non_admin_denied(self):
        with self.assertRaises(Exception) as caught:
            admin.authenticate(self.signed(user=999))
        self.assertEqual(caught.exception.status_code, 403)

    def test_expired_token_denied(self):
        with self.assertRaises(Exception) as caught:
            admin.authenticate(self.signed(timestamp=int(time.time())-90000))
        self.assertEqual(caught.exception.status_code, 401)

    def test_tampered_signature_denied(self):
        data = self.signed().replace("12345", "99999")
        with self.assertRaises(Exception) as caught:
            admin.authenticate(data)
        self.assertEqual(caught.exception.status_code, 401)

if __name__ == "__main__":
    unittest.main()
