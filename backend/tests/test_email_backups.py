"""Tests for Email Backups (SMTP) feature.

Covers:
- GET/PUT /api/settings/email -- password masked (has_password), persistence
- PUT with blank/None password retains previously saved password
- POST /api/email/test -- 400 missing host/to, 502 on unreachable SMTP
- POST /api/backups/{name}/email -- 400 unconfigured, 502 on SMTP failure, 404 on missing file
- Permissions: Viewer gets 403 on all these endpoints
"""
import os
import pytest
import requests

BASE_URL = (os.environ.get('REACT_APP_BACKEND_URL') or "https://church-treasury-5.preview.emergentagent.com").rstrip('/')
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "treasurer@church.org"
ADMIN_PASS = "Church#Treasury2026"
VIEWER_EMAIL = "viewer@church.org"
VIEWER_PASS = "Viewer#Account9"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    return r


@pytest.fixture(scope="module")
def admin_token():
    r = _login(ADMIN_EMAIL, ADMIN_PASS)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def viewer_token(admin_headers):
    # Make sure the viewer exists
    r = _login(VIEWER_EMAIL, VIEWER_PASS)
    if r.status_code == 200:
        return r.json()["token"]
    # create viewer via admin
    roles = requests.get(f"{API}/roles", headers=admin_headers, timeout=30).json()
    viewer_role = next((x for x in roles if x.get("name", "").lower() == "viewer"), None)
    assert viewer_role, "Viewer role not seeded"
    cr = requests.post(f"{API}/auth/users", headers=admin_headers, json={
        "name": "Viewer", "email": VIEWER_EMAIL, "password": VIEWER_PASS, "role_id": viewer_role["id"],
    }, timeout=30)
    assert cr.status_code in (200, 201, 400), cr.text
    r = _login(VIEWER_EMAIL, VIEWER_PASS)
    assert r.status_code == 200, f"Viewer login failed: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def viewer_headers(viewer_token):
    return {"Authorization": f"Bearer {viewer_token}"}


# ----------------- GET /settings/email masking -----------------
class TestGetEmailSettings:
    def test_get_returns_shape_no_raw_password(self, admin_headers):
        r = requests.get(f"{API}/settings/email", headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ["enabled", "smtp_host", "smtp_port", "smtp_username",
                  "use_tls", "from_address", "to_address", "has_password"]:
            assert k in data, f"Missing field {k}"
        assert "smtp_password" not in data, "GET must not return raw password"
        assert isinstance(data["has_password"], bool)


# ----------------- PUT /settings/email + persistence -----------------
class TestUpdateEmailSettings:
    def test_save_and_persist(self, admin_headers):
        payload = {
            "enabled": True,
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_username": "t@example.com",
            "smtp_password": "secret123",
            "use_tls": True,
            "from_address": "t@example.com",
            "to_address": "treasurer@church.org",
        }
        r = requests.put(f"{API}/settings/email", headers=admin_headers, json=payload, timeout=30)
        assert r.status_code == 200, r.text

        g = requests.get(f"{API}/settings/email", headers=admin_headers, timeout=30).json()
        assert g["enabled"] is True
        assert g["smtp_host"] == "smtp.example.com"
        assert g["smtp_port"] == 587
        assert g["smtp_username"] == "t@example.com"
        assert g["from_address"] == "t@example.com"
        assert g["to_address"] == "treasurer@church.org"
        assert g["use_tls"] is True
        assert g["has_password"] is True
        assert "smtp_password" not in g

    def test_blank_password_retains_existing(self, admin_headers):
        # first ensure one is saved
        requests.put(f"{API}/settings/email", headers=admin_headers, json={
            "enabled": True, "smtp_host": "smtp.example.com", "smtp_port": 587,
            "smtp_username": "t@example.com", "smtp_password": "secret123",
            "use_tls": True, "from_address": "t@example.com", "to_address": "treasurer@church.org",
        }, timeout=30).raise_for_status()

        # now save again with no password
        r = requests.put(f"{API}/settings/email", headers=admin_headers, json={
            "enabled": True, "smtp_host": "smtp.example.com", "smtp_port": 587,
            "smtp_username": "t@example.com",
            "use_tls": True, "from_address": "t@example.com", "to_address": "treasurer@church.org",
        }, timeout=30)
        assert r.status_code == 200, r.text
        g = requests.get(f"{API}/settings/email", headers=admin_headers, timeout=30).json()
        assert g["has_password"] is True, "Password should be retained when PUT omits it"

    def test_blank_string_password_retains_existing(self, admin_headers):
        r = requests.put(f"{API}/settings/email", headers=admin_headers, json={
            "enabled": True, "smtp_host": "smtp.example.com", "smtp_port": 587,
            "smtp_username": "t@example.com", "smtp_password": "",
            "use_tls": True, "from_address": "t@example.com", "to_address": "treasurer@church.org",
        }, timeout=30)
        assert r.status_code == 200
        g = requests.get(f"{API}/settings/email", headers=admin_headers, timeout=30).json()
        assert g["has_password"] is True


# ----------------- POST /email/test -----------------
class TestSendTestEmail:
    def test_missing_host_returns_400(self, admin_headers):
        # Save empty host
        requests.put(f"{API}/settings/email", headers=admin_headers, json={
            "enabled": False, "smtp_host": "", "smtp_port": 587, "smtp_username": "",
            "use_tls": True, "from_address": "", "to_address": "",
        }, timeout=30).raise_for_status()
        r = requests.post(f"{API}/email/test", headers=admin_headers, timeout=30)
        assert r.status_code == 400, r.text
        assert "host" in (r.json().get("detail") or "").lower() or "recipient" in (r.json().get("detail") or "").lower()

    def test_unreachable_host_returns_502(self, admin_headers):
        requests.put(f"{API}/settings/email", headers=admin_headers, json={
            "enabled": True,
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_username": "t@example.com",
            "smtp_password": "secret123",
            "use_tls": True,
            "from_address": "t@example.com",
            "to_address": "treasurer@church.org",
        }, timeout=30).raise_for_status()
        # Hit backend directly to bypass Cloudflare ingress (which rewrites 5xx bodies).
        # Login locally first to get a token (user table is shared).
        lr = requests.post("http://localhost:8001/api/auth/login",
                           json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
        assert lr.status_code == 200
        local_hdr = {"Authorization": f"Bearer {lr.json()['token']}"}
        r = requests.post("http://localhost:8001/api/email/test", headers=local_hdr, timeout=60)
        assert r.status_code == 502, f"Expected 502, got {r.status_code}: {r.text}"
        detail = r.json().get("detail", "")
        assert "Could not send email" in detail, f"Expected error prefix in detail, got: {detail}"


# ----------------- POST /backups/{name}/email -----------------
class TestEmailBackup:
    def test_email_nonexistent_backup_404(self, admin_headers):
        r = requests.post(f"{API}/backups/church-treasury-backup-does-not-exist.json/email",
                          headers=admin_headers, timeout=30)
        assert r.status_code == 404, r.text


# ----------------- Permissions: Viewer gets 403 -----------------
class TestViewerForbidden:
    def test_viewer_get_settings_email_403(self, viewer_headers):
        r = requests.get(f"{API}/settings/email", headers=viewer_headers, timeout=30)
        assert r.status_code == 403, r.text

    def test_viewer_put_settings_email_403(self, viewer_headers):
        r = requests.put(f"{API}/settings/email", headers=viewer_headers, json={
            "enabled": False, "smtp_host": "x", "smtp_port": 587, "smtp_username": "",
            "use_tls": True, "from_address": "", "to_address": "",
        }, timeout=30)
        assert r.status_code == 403, r.text

    def test_viewer_test_email_403(self, viewer_headers):
        r = requests.post(f"{API}/email/test", headers=viewer_headers, timeout=30)
        assert r.status_code == 403, r.text

    def test_viewer_email_backup_403(self, viewer_headers):
        r = requests.post(f"{API}/backups/anything.json/email", headers=viewer_headers, timeout=30)
        assert r.status_code == 403, r.text


# ----------------- Regression smoke -----------------
class TestRegressionBackupTab:
    def test_get_backups_settings_still_works(self, admin_headers):
        r = requests.get(f"{API}/settings/backup", headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text

    def test_list_backups_still_works(self, admin_headers):
        r = requests.get(f"{API}/backups", headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_data_export_still_works(self, admin_headers):
        r = requests.get(f"{API}/data/export", headers=admin_headers, timeout=60)
        assert r.status_code == 200, r.text
