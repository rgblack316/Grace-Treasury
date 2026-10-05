"""Backend tests: GridFS receipts (local only) + Scheduled backups + viewer 403s + validation."""
import io
import os
import struct
import time
import zlib
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://church-treasury-5.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "treasurer@church.org", "password": "Church#Treasury2026"}
VIEWER = {"email": "viewer@church.org", "password": "Viewer#Account9"}


def _h(t): return {"Authorization": f"Bearer {t}"}


def _png():
    sig = b"\x89PNG\r\n\x1a\n"
    def c(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (sig + c(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + c(b"IDAT", zlib.compress(b"\x00\xff\xff\xff")) + c(b"IEND", b""))


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json=ADMIN)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def viewer_token():
    r = requests.post(f"{API}/auth/login", json=VIEWER)
    if r.status_code != 200:
        pytest.skip("Viewer user not available")
    return r.json()["token"]


# ----- GridFS receipt roundtrip (no cloud key) -----
class TestGridFSReceipts:
    def test_upload_download_delete(self, admin_token):
        accts = requests.get(f"{API}/accounts", headers=_h(admin_token)).json()
        assert accts
        acc = accts[0]
        cats = requests.get(f"{API}/categories", headers=_h(admin_token)).json()
        c = next(c for c in cats if c["type"] == "expense")
        tx = requests.post(f"{API}/transactions", headers=_h(admin_token),
                           json={"type": "expense", "date": "2026-01-15",
                                 "account_id": acc["id"], "amount": 1.23,
                                 "category_id": c["id"], "memo": "TEST_GRIDFS"}).json()
        tid = tx["id"]
        try:
            r = requests.post(f"{API}/transactions/{tid}/attachments",
                              headers=_h(admin_token),
                              files={"file": ("r.png", _png(), "image/png")})
            assert r.status_code == 200, r.text
            fid = r.json()["id"]

            # Bearer download
            dr = requests.get(f"{API}/attachments/{fid}/download", headers=_h(admin_token))
            assert dr.status_code == 200
            assert dr.headers.get("content-type", "").startswith("image/")
            assert dr.content[:8] == b"\x89PNG\r\n\x1a\n"

            # ?auth= query
            dr2 = requests.get(f"{API}/attachments/{fid}/download", params={"auth": admin_token})
            assert dr2.status_code == 200
            assert dr2.content[:8] == b"\x89PNG\r\n\x1a\n"

            # attachment_count on txn list
            lst = requests.get(f"{API}/transactions", headers=_h(admin_token),
                               params={"search": "TEST_GRIDFS"}).json()
            items = lst.get("items", lst) if isinstance(lst, dict) else lst
            m = next(t for t in items if t["id"] == tid)
            assert m.get("attachment_count", 0) >= 1

            # Delete
            dd = requests.delete(f"{API}/attachments/{fid}", headers=_h(admin_token))
            assert dd.status_code == 200
            l2 = requests.get(f"{API}/transactions/{tid}/attachments", headers=_h(admin_token)).json()
            assert not any(f["id"] == fid for f in l2)
        finally:
            requests.delete(f"{API}/transactions/{tid}", headers=_h(admin_token))


# ----- Scheduled backup config -----
class TestBackupConfig:
    def test_get_config(self, admin_token):
        r = requests.get(f"{API}/settings/backup", headers=_h(admin_token))
        assert r.status_code == 200
        d = r.json()
        for k in ("enabled", "time", "retention"):
            assert k in d

    def test_put_config_persists(self, admin_token):
        r = requests.put(f"{API}/settings/backup", headers=_h(admin_token),
                         json={"enabled": True, "time": "03:30", "retention": 7})
        assert r.status_code == 200
        d = requests.get(f"{API}/settings/backup", headers=_h(admin_token)).json()
        assert d["time"] == "03:30"
        assert d["retention"] == 7
        assert d["enabled"] is True

    def test_invalid_time_rejected(self, admin_token):
        r = requests.put(f"{API}/settings/backup", headers=_h(admin_token),
                         json={"enabled": True, "time": "99:99", "retention": 7})
        assert r.status_code == 400

    def test_viewer_cannot_read_backup_cfg(self, viewer_token):
        r = requests.get(f"{API}/settings/backup", headers=_h(viewer_token))
        assert r.status_code == 403

    def test_viewer_cannot_update_backup_cfg(self, viewer_token):
        r = requests.put(f"{API}/settings/backup", headers=_h(viewer_token),
                         json={"enabled": True, "time": "02:00", "retention": 5})
        assert r.status_code == 403


# ----- Backup actions + retention -----
class TestBackupActions:
    def test_run_now_and_list(self, admin_token):
        r = requests.post(f"{API}/backups/run", headers=_h(admin_token))
        assert r.status_code == 200
        name = r.json().get("name")
        assert name and name.endswith(".json")
        time.sleep(0.5)
        lst = requests.get(f"{API}/backups", headers=_h(admin_token)).json()
        names = [b.get("name") for b in lst]
        assert name in names

    def test_download_backup(self, admin_token):
        lst = requests.get(f"{API}/backups", headers=_h(admin_token)).json()
        assert lst
        name = lst[0]["name"]
        r = requests.get(f"{API}/backups/{name}/download", headers=_h(admin_token))
        assert r.status_code == 200
        assert len(r.content) > 10

    def test_download_backup_query_auth(self, admin_token):
        lst = requests.get(f"{API}/backups", headers=_h(admin_token)).json()
        name = lst[0]["name"]
        r = requests.get(f"{API}/backups/{name}/download", params={"auth": admin_token})
        assert r.status_code == 200

    def test_retention_enforced(self, admin_token):
        # Set retention=2 then create 4 backups, final count <=2
        requests.put(f"{API}/settings/backup", headers=_h(admin_token),
                     json={"enabled": True, "time": "02:00", "retention": 2})
        for _ in range(4):
            requests.post(f"{API}/backups/run", headers=_h(admin_token))
            time.sleep(1.1)  # filenames encode seconds
        lst = requests.get(f"{API}/backups", headers=_h(admin_token)).json()
        assert len(lst) <= 2, [b["name"] for b in lst]

    def test_delete_backup(self, admin_token):
        # Make sure we have at least one, delete it
        requests.post(f"{API}/backups/run", headers=_h(admin_token))
        time.sleep(0.3)
        lst = requests.get(f"{API}/backups", headers=_h(admin_token)).json()
        assert lst
        name = lst[-1]["name"]
        r = requests.delete(f"{API}/backups/{name}", headers=_h(admin_token))
        assert r.status_code in (200, 204)
        lst2 = requests.get(f"{API}/backups", headers=_h(admin_token)).json()
        assert name not in [b["name"] for b in lst2]

    def test_viewer_cannot_run_backup(self, viewer_token):
        r = requests.post(f"{API}/backups/run", headers=_h(viewer_token))
        assert r.status_code == 403

    def test_viewer_cannot_list_backups(self, viewer_token):
        r = requests.get(f"{API}/backups", headers=_h(viewer_token))
        assert r.status_code == 403


# ----- Path traversal protection -----
class TestPathTraversal:
    @pytest.mark.parametrize("bad", [
        "../etc/passwd",
        "..%2Fetc%2Fpasswd",
        "foo/bar.json",
        "no-prefix.json",
        "church-treasury-backup-../x.json",
    ])
    def test_download_bad_name(self, admin_token, bad):
        r = requests.get(f"{API}/backups/{bad}/download", headers=_h(admin_token))
        assert r.status_code in (400, 404), (bad, r.status_code)

    @pytest.mark.parametrize("bad", ["../etc/passwd", "foo.json"])
    def test_delete_bad_name(self, admin_token, bad):
        r = requests.delete(f"{API}/backups/{bad}", headers=_h(admin_token))
        assert r.status_code in (400, 404)

    @pytest.mark.parametrize("bad", ["../etc/passwd", "foo.json"])
    def test_restore_bad_name(self, admin_token, bad):
        r = requests.post(f"{API}/backups/{bad}/restore", headers=_h(admin_token))
        assert r.status_code in (400, 404)


# ----- Restore from server backup (destructive-ish — admin should still log back in) -----
class TestServerRestore:
    def test_restore_roundtrip(self, admin_token):
        # make a known-good backup then restore it
        r = requests.post(f"{API}/backups/run", headers=_h(admin_token))
        assert r.status_code == 200
        name = r.json()["name"]
        time.sleep(0.4)
        rr = requests.post(f"{API}/backups/{name}/restore", headers=_h(admin_token))
        assert rr.status_code == 200, rr.text
        time.sleep(1)
        lr = requests.post(f"{API}/auth/login", json=ADMIN)
        assert lr.status_code == 200
