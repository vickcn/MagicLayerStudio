import time
import unittest
from fastapi.testclient import TestClient
from web.backend.app import app, _google_sessions, _google_sessions_lock, GOOGLE_SESSION_COOKIE

class TestGoogleAuth(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_session_endpoint_unconfigured(self):
        response = self.client.get("/api/auth/session")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("configured", data)
        self.assertIn("authenticated", data)
        self.assertFalse(data["authenticated"])

    def test_auth_start_unconfigured(self):
        response = self.client.get("/auth/google/start", follow_redirects=False)
        self.assertEqual(response.status_code, 503)
        self.assertIn("尚未設定", response.json()["detail"])

    def test_valid_session_and_auto_refresh_check(self):
        # 模擬已登入 Session（過期時間充裕）
        session_id = "test_session_123"
        session_data = {
            "sub": "google-12345",
            "name": "Test User",
            "email": "test@example.com",
            "picture": "https://example.com/avatar.jpg",
            "access_token": "valid_token",
            "refresh_token": "valid_refresh_token",
            "expires_at": time.time() + 3600,
        }
        with _google_sessions_lock:
            _google_sessions[session_id] = session_data

        self.client.cookies.set(GOOGLE_SESSION_COOKIE, session_id)
        response = self.client.get("/api/auth/session")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["authenticated"])
        self.assertEqual(data["email"], "test@example.com")
        self.assertEqual(data["sub"], "google-12345")

if __name__ == "__main__":
    unittest.main()
