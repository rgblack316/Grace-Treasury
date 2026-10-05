"""Backend tests for the 3 new features: CSV Import, Reconciliation, Attachments."""
import io
import os
import struct
import zlib
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
API = f"{BASE_URL}/api"
ADMIN_EMAIL = "rgblack@gmail.com"
ADMIN_PASSWORD = "Treasury2026!"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


def _tiny_png_bytes():
    # Minimal valid 1x1 PNG
    sig = b"\x89PNG\r\n\x1a\n"
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw = b"\x00\xff\xff\xff"
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


# ----------------------------- CSV Import -----------------------------
class TestImport:
    def test_template_download(self, auth):
        r = requests.get(f"{API}/import/template", headers=auth)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        body = r.text
        for col in ["Date", "Type", "Account", "To Account", "Amount", "Check#", "Payee", "Category", "Fund", "Memo"]:
            assert col in body

    def test_import_valid_and_errors_and_autocreate(self, auth):
        # Build CSV with 2 valid rows (auto-creating payee/category/fund) + 3 bad rows
        csv_text = (
            "Date,Type,Account,To Account,Amount,Check#,Payee,Category,Fund,Memo\n"
            "2026-07-01,income,*1234,,123.45,,TEST_IMP_Payee,TEST_IMP_Cat_Inc,TEST_IMP_Fund,TEST_IMP_INCOME\n"
            "2026-07-02,expense,*1234,,50.00,5001,TEST_IMP_Payee,TEST_IMP_Cat_Exp,TEST_IMP_Fund,TEST_IMP_EXP\n"
            "not-a-date,expense,*1234,,10,,,,General Fund,bad date\n"
            "2026-07-03,bogus,*1234,,10,,,,General Fund,bad type\n"
            "2026-07-04,expense,*9999,,10,,,,General Fund,bad account\n"
        )
        files = {"file": ("import.csv", csv_text.encode("utf-8"), "text/csv")}
        r = requests.post(f"{API}/import/transactions", headers=auth, files=files)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["created"] == 2, data
        reasons = " | ".join(e["reason"] for e in data["errors"])
        assert len(data["errors"]) == 3, data["errors"]
        assert "Date" in reasons
        assert "Type" in reasons
        assert "Account" in reasons
        assert data["created_payees"] >= 1
        assert data["created_categories"] >= 2  # income + expense cat (different types)
        assert data["created_funds"] >= 1

        # Verify imported transactions appear in list
        lr = requests.get(f"{API}/transactions", headers=auth, params={"search": "TEST_IMP"})
        assert lr.status_code == 200
        rows = lr.json()
        assert any(t.get("memo") == "TEST_IMP_INCOME" for t in rows)
        assert any(t.get("memo") == "TEST_IMP_EXP" for t in rows)

        # Cleanup created txns, payee, categories, fund
        for t in rows:
            if (t.get("memo") or "").startswith("TEST_IMP"):
                requests.delete(f"{API}/transactions/{t['id']}", headers=auth)
        for p in requests.get(f"{API}/payees", headers=auth).json():
            if p["name"].startswith("TEST_IMP"):
                requests.delete(f"{API}/payees/{p['id']}", headers=auth)
        for c in requests.get(f"{API}/categories", headers=auth).json():
            if c["name"].startswith("TEST_IMP"):
                requests.delete(f"{API}/categories/{c['id']}", headers=auth)
        for f in requests.get(f"{API}/funds", headers=auth).json():
            if f["name"].startswith("TEST_IMP"):
                requests.delete(f"{API}/funds/{f['id']}", headers=auth)

    def test_import_transfer_requires_destination(self, auth):
        csv_text = (
            "Date,Type,Account,To Account,Amount,Check#,Payee,Category,Fund,Memo\n"
            "2026-07-05,transfer,*1234,,100,,,,,missing dest\n"
        )
        files = {"file": ("t.csv", csv_text.encode("utf-8"), "text/csv")}
        r = requests.post(f"{API}/import/transactions", headers=auth, files=files)
        assert r.status_code == 200
        d = r.json()
        assert d["created"] == 0
        assert any("Transfer" in e["reason"] or "To Account" in e["reason"] for e in d["errors"])


# ----------------------------- Reconciliation -----------------------------
class TestReconcile:
    def test_cleared_toggle_and_reconcile_math(self, auth):
        accts = requests.get(f"{API}/accounts", headers=auth).json()
        acc = next(a for a in accts if a["mask"] == "*1234")
        # Create a fresh expense
        cats = requests.get(f"{API}/categories", headers=auth).json()
        exp_cat = next(c for c in cats if c["type"] == "expense")
        payload = {"type": "expense", "date": "2026-07-20", "account_id": acc["id"],
                   "amount": 42.00, "category_id": exp_cat["id"], "memo": "TEST_RECON"}
        tr = requests.post(f"{API}/transactions", headers={**auth, "Content-Type": "application/json"}, json=payload)
        assert tr.status_code == 200
        tid = tr.json()["id"]
        try:
            rec0 = requests.get(f"{API}/accounts/{acc['id']}/reconcile", headers=auth).json()
            cb0 = rec0["cleared_balance"]
            un0 = rec0["uncleared_count"]

            # Mark cleared
            pr = requests.patch(f"{API}/transactions/{tid}/cleared",
                                headers={**auth, "Content-Type": "application/json"},
                                json={"cleared": True})
            assert pr.status_code == 200 and pr.json()["cleared"] is True

            rec1 = requests.get(f"{API}/accounts/{acc['id']}/reconcile", headers=auth).json()
            assert round(rec1["cleared_balance"] - cb0, 2) == -42.00, (rec0, rec1)
            assert rec1["uncleared_count"] == un0 - 1

            # Untick
            pr2 = requests.patch(f"{API}/transactions/{tid}/cleared",
                                 headers={**auth, "Content-Type": "application/json"},
                                 json={"cleared": False})
            assert pr2.status_code == 200
            rec2 = requests.get(f"{API}/accounts/{acc['id']}/reconcile", headers=auth).json()
            assert round(rec2["cleared_balance"], 2) == round(cb0, 2)
            assert rec2["uncleared_count"] == un0
        finally:
            requests.delete(f"{API}/transactions/{tid}", headers=auth)

    def test_reconcile_fields_present(self, auth):
        accts = requests.get(f"{API}/accounts", headers=auth).json()
        r = requests.get(f"{API}/accounts/{accts[0]['id']}/reconcile", headers=auth)
        assert r.status_code == 200
        d = r.json()
        for k in ("current_balance", "cleared_balance", "uncleared_count", "uncleared_total"):
            assert k in d


# ----------------------------- Attachments -----------------------------
class TestAttachments:
    def _mk_txn(self, auth, ttype="expense"):
        accts = requests.get(f"{API}/accounts", headers=auth).json()
        acc = accts[0]
        payload = {"type": ttype, "date": "2026-07-25", "account_id": acc["id"], "amount": 7.77, "memo": f"TEST_ATT_{ttype}"}
        if ttype == "transfer":
            payload["to_account_id"] = accts[1]["id"]
        else:
            cats = requests.get(f"{API}/categories", headers=auth).json()
            c = next(c for c in cats if c["type"] == ttype)
            payload["category_id"] = c["id"]
        r = requests.post(f"{API}/transactions", headers={**auth, "Content-Type": "application/json"}, json=payload)
        assert r.status_code == 200
        return r.json()["id"]

    def test_upload_list_download_delete(self, auth, token):
        tid = self._mk_txn(auth, "expense")
        try:
            png = _tiny_png_bytes()
            files = {"file": ("receipt.png", png, "image/png")}
            r = requests.post(f"{API}/transactions/{tid}/attachments", headers=auth, files=files)
            assert r.status_code == 200, r.text
            fid = r.json()["id"]

            # List
            lr = requests.get(f"{API}/transactions/{tid}/attachments", headers=auth)
            assert lr.status_code == 200
            attached = lr.json()
            assert any(f["id"] == fid for f in attached)

            # Transaction list exposes attachment_count > 0
            tx_list = requests.get(f"{API}/transactions", headers=auth, params={"search": "TEST_ATT"}).json()
            match = next(t for t in tx_list if t["id"] == tid)
            assert match.get("attachment_count", 0) >= 1

            # Download via Bearer header
            dr = requests.get(f"{API}/attachments/{fid}/download", headers=auth)
            assert dr.status_code == 200
            assert dr.content[:8] == b"\x89PNG\r\n\x1a\n"

            # Download via ?auth= query (used by image preview in UI)
            dr2 = requests.get(f"{API}/attachments/{fid}/download", params={"auth": token})
            assert dr2.status_code == 200

            # Download unauthenticated
            dr3 = requests.get(f"{API}/attachments/{fid}/download")
            assert dr3.status_code == 401

            # Delete attachment
            delr = requests.delete(f"{API}/attachments/{fid}", headers=auth)
            assert delr.status_code == 200
            lr2 = requests.get(f"{API}/transactions/{tid}/attachments", headers=auth)
            assert not any(f["id"] == fid for f in lr2.json())
        finally:
            requests.delete(f"{API}/transactions/{tid}", headers=auth)

    def test_attachment_on_income(self, auth):
        tid = self._mk_txn(auth, "income")
        try:
            files = {"file": ("r.png", _tiny_png_bytes(), "image/png")}
            r = requests.post(f"{API}/transactions/{tid}/attachments", headers=auth, files=files)
            assert r.status_code == 200
        finally:
            requests.delete(f"{API}/transactions/{tid}", headers=auth)

    def test_disallowed_file_type(self, auth):
        tid = self._mk_txn(auth, "expense")
        try:
            files = {"file": ("note.txt", b"hello world", "text/plain")}
            r = requests.post(f"{API}/transactions/{tid}/attachments", headers=auth, files=files)
            assert r.status_code == 400
        finally:
            requests.delete(f"{API}/transactions/{tid}", headers=auth)

    def test_attachment_on_missing_txn(self, auth):
        files = {"file": ("r.png", _tiny_png_bytes(), "image/png")}
        r = requests.post(f"{API}/transactions/nonexistent-id/attachments", headers=auth, files=files)
        assert r.status_code == 404

    def test_delete_txn_soft_deletes_attachments(self, auth):
        tid = self._mk_txn(auth, "expense")
        files = {"file": ("r.png", _tiny_png_bytes(), "image/png")}
        r = requests.post(f"{API}/transactions/{tid}/attachments", headers=auth, files=files)
        assert r.status_code == 200
        # Delete the transaction
        dr = requests.delete(f"{API}/transactions/{tid}", headers=auth)
        assert dr.status_code == 200
        # Attachments list for that txn should be empty (soft deleted) OR still callable without error
        lr = requests.get(f"{API}/transactions/{tid}/attachments", headers=auth)
        assert lr.status_code == 200
        assert lr.json() == []
