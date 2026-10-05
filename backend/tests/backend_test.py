"""Backend API tests for Church Treasury app."""
import os
import pytest
import requests
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://church-treasury-5.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "rgblack@gmail.com"
ADMIN_PASSWORD = "Treasury2026!"


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def client(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


# ----------------------------- Auth -----------------------------
class TestAuth:
    def test_login_success(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        d = r.json()
        assert "token" in d and d["user"]["email"] == ADMIN_EMAIL
        assert d["user"]["role"] == "admin"

    def test_login_invalid(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
        assert r.status_code == 401

    def test_me(self, client):
        r = client.get(f"{API}/auth/me")
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL

    def test_me_unauth(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401


# ----------------------------- Dashboard -----------------------------
class TestDashboard:
    def test_dashboard(self, client):
        r = client.get(f"{API}/dashboard")
        assert r.status_code == 200
        d = r.json()
        assert "total_balance" in d
        assert len(d["accounts"]) == 3
        assert len(d["funds"]) >= 3
        assert isinstance(d["recent"], list)


# ----------------------------- Lookups -----------------------------
class TestLookups:
    def test_accounts(self, client):
        r = client.get(f"{API}/accounts")
        assert r.status_code == 200
        accts = r.json()
        masks = {a["mask"] for a in accts}
        assert {"*1234", "*5678", "*9012"}.issubset(masks)

    def test_funds(self, client):
        r = client.get(f"{API}/funds")
        assert r.status_code == 200 and len(r.json()) >= 3

    def test_categories(self, client):
        r = client.get(f"{API}/categories")
        assert r.status_code == 200 and len(r.json()) > 0

    def test_payees(self, client):
        assert client.get(f"{API}/payees").status_code == 200

    def test_coa(self, client):
        assert client.get(f"{API}/coa").status_code == 200


# ----------------------------- Report -----------------------------
class TestReport:
    def test_june_2026_report(self, client):
        accts = client.get(f"{API}/accounts").json()
        acc_main = next(a for a in accts if a["mask"] == "*1234")
        r = client.get(f"{API}/reports/treasurer",
                       params={"start": "2026-06-01", "end": "2026-06-30", "account_ids": acc_main["id"]})
        assert r.status_code == 200
        rpt = r.json()
        a = rpt["accounts"][0]
        assert a["balance_forward"] == 76880.68
        assert a["total_income"] == 3955.74
        assert a["total_expenses"] == 762.93
        assert a["new_balance"] == 80073.49
        # reconciliation
        assert round(a["balance_forward"] + a["total_income"] - a["total_expenses"], 2) == a["new_balance"]
        # expense rows have check# / payee / memo
        for e in a["expenses"]:
            assert "check_number" in e and "payee" in e and "memo" in e

    def test_report_pdf(self, client):
        accts = client.get(f"{API}/accounts").json()
        acc_main = next(a for a in accts if a["mask"] == "*1234")
        r = client.get(f"{API}/reports/treasurer/pdf",
                       params={"start": "2026-06-01", "end": "2026-06-30",
                               "account_ids": acc_main["id"],
                               "include_category": "true", "include_funds": "true"})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/pdf")
        assert r.content[:4] == b"%PDF"


# ----------------------------- Transactions CRUD -----------------------------
class TestTransactions:
    def test_crud_income(self, client):
        accts = client.get(f"{API}/accounts").json()
        acc = next(a for a in accts if a["mask"] == "*5678")
        funds = client.get(f"{API}/funds").json()
        cats = client.get(f"{API}/categories").json()
        inc_cat = next(c for c in cats if c["type"] == "income")

        payload = {"type": "income", "date": "2026-07-05", "account_id": acc["id"],
                   "amount": 500.0, "category_id": inc_cat["id"],
                   "fund_id": funds[0]["id"], "memo": "TEST_INCOME"}
        r = client.post(f"{API}/transactions", json=payload)
        assert r.status_code == 200
        txn = r.json()
        tid = txn["id"]
        assert txn["amount"] == 500.0

        # Verify in list with filters
        lr = client.get(f"{API}/transactions", params={"account_id": acc["id"], "type": "income"})
        assert any(t["id"] == tid for t in lr.json())

        # Verify balance increased
        d = client.get(f"{API}/dashboard").json()
        a_bal = next(x["balance"] for x in d["accounts"] if x["id"] == acc["id"])
        assert a_bal >= 500.0

        # Update
        payload["amount"] = 600.0
        payload["memo"] = "TEST_INCOME_UPDATED"
        r2 = client.put(f"{API}/transactions/{tid}", json=payload)
        assert r2.status_code == 200 and r2.json()["amount"] == 600.0

        # Delete
        r3 = client.delete(f"{API}/transactions/{tid}")
        assert r3.status_code == 200
        # confirm gone
        lr2 = client.get(f"{API}/transactions", params={"search": "TEST_INCOME_UPDATED"})
        assert not any(t["id"] == tid for t in lr2.json())

    def test_expense_with_check_payee(self, client):
        accts = client.get(f"{API}/accounts").json()
        acc = next(a for a in accts if a["mask"] == "*1234")
        payees = client.get(f"{API}/payees").json()
        cats = client.get(f"{API}/categories").json()
        exp_cat = next(c for c in cats if c["type"] == "expense")
        payload = {"type": "expense", "date": "2026-07-10", "account_id": acc["id"],
                   "amount": 50.0, "payee_id": payees[0]["id"], "check_number": "9999",
                   "category_id": exp_cat["id"], "memo": "TEST_EXPENSE"}
        r = client.post(f"{API}/transactions", json=payload)
        assert r.status_code == 200
        tid = r.json()["id"]
        assert r.json()["check_number"] == "9999"
        client.delete(f"{API}/transactions/{tid}")

    def test_transfer_adjusts_balances(self, client):
        accts = client.get(f"{API}/accounts").json()
        src = next(a for a in accts if a["mask"] == "*5678")
        dst = next(a for a in accts if a["mask"] == "*9012")

        d0 = client.get(f"{API}/dashboard").json()
        src_bal0 = next(x["balance"] for x in d0["accounts"] if x["id"] == src["id"])
        dst_bal0 = next(x["balance"] for x in d0["accounts"] if x["id"] == dst["id"])

        payload = {"type": "transfer", "date": "2026-07-12", "account_id": src["id"],
                   "to_account_id": dst["id"], "amount": 200.0, "memo": "TEST_TRANSFER"}
        r = client.post(f"{API}/transactions", json=payload)
        assert r.status_code == 200
        tid = r.json()["id"]

        d1 = client.get(f"{API}/dashboard").json()
        src_bal1 = next(x["balance"] for x in d1["accounts"] if x["id"] == src["id"])
        dst_bal1 = next(x["balance"] for x in d1["accounts"] if x["id"] == dst["id"])
        assert round(src_bal1 - src_bal0, 2) == -200.0
        assert round(dst_bal1 - dst_bal0, 2) == 200.0

        client.delete(f"{API}/transactions/{tid}")

    def test_transfer_without_destination_fails(self, client):
        accts = client.get(f"{API}/accounts").json()
        payload = {"type": "transfer", "date": "2026-07-12",
                   "account_id": accts[0]["id"], "amount": 10.0}
        r = client.post(f"{API}/transactions", json=payload)
        assert r.status_code == 400

    def test_filters(self, client):
        accts = client.get(f"{API}/accounts").json()
        acc = next(a for a in accts if a["mask"] == "*1234")
        r = client.get(f"{API}/transactions", params={
            "account_id": acc["id"], "type": "expense",
            "start": "2026-06-01", "end": "2026-06-30"})
        assert r.status_code == 200
        for t in r.json():
            assert t["type"] == "expense"
            assert "2026-06-01" <= t["date"] <= "2026-06-30"


# ----------------------------- Settings CRUD -----------------------------
class TestSettings:
    def test_fund_crud(self, client):
        r = client.post(f"{API}/funds", json={"name": "TEST_Fund", "description": "x", "active": True})
        assert r.status_code == 200
        fid = r.json()["id"]
        r2 = client.put(f"{API}/funds/{fid}", json={"name": "TEST_Fund2", "description": "y", "active": True})
        assert r2.status_code == 200 and r2.json()["name"] == "TEST_Fund2"
        assert client.delete(f"{API}/funds/{fid}").status_code == 200

    def test_account_crud(self, client):
        r = client.post(f"{API}/accounts", json={"name": "TEST_Acct", "mask": "*0001", "opening_balance": 100.0})
        aid = r.json()["id"]
        assert client.put(f"{API}/accounts/{aid}", json={"name": "TEST_Acct2", "mask": "*0002", "opening_balance": 50.0}).status_code == 200
        assert client.delete(f"{API}/accounts/{aid}").status_code == 200

    def test_payee_category_coa_crud(self, client):
        for path, payload in [
            ("payees", {"name": "TEST_P"}),
            ("categories", {"name": "TEST_C", "type": "expense"}),
            ("coa", {"code": "9999", "name": "TEST_COA", "group": "Expense"}),
        ]:
            r = client.post(f"{API}/{path}", json=payload)
            assert r.status_code == 200, path
            iid = r.json()["id"]
            assert client.delete(f"{API}/{path}/{iid}").status_code == 200

    def test_church_info_update(self, client):
        r0 = client.get(f"{API}/settings/church")
        assert r0.status_code == 200
        original = r0.json()
        new = {"church_name": "Providence Baptist Church", "treasurer_name": "R.G. Black", "meeting_day": "Sunday"}
        r = client.put(f"{API}/settings/church", json=new)
        assert r.status_code == 200
        r2 = client.get(f"{API}/settings/church")
        assert r2.json()["treasurer_name"] == "R.G. Black"
        # restore
        client.put(f"{API}/settings/church", json={
            "church_name": original.get("church_name", "Providence Baptist Church"),
            "treasurer_name": original.get("treasurer_name", ""),
            "meeting_day": original.get("meeting_day", ""),
        })


# ----------------------------- Users (admin) -----------------------------
class TestUsers:
    def test_list_users_admin(self, client):
        r = client.get(f"{API}/auth/users")
        assert r.status_code == 200

    def test_create_delete_user(self, client):
        email = f"TEST_user_{datetime.now().strftime('%H%M%S')}@test.com"
        r = client.post(f"{API}/auth/users", json={
            "email": email, "password": "Pass1234!", "name": "Test User", "role": "user"})
        assert r.status_code == 200
        uid = r.json()["id"]
        lr = client.get(f"{API}/auth/users").json()
        assert any(u["id"] == uid for u in lr)
        assert client.delete(f"{API}/auth/users/{uid}").status_code == 200

    def test_non_admin_cannot_manage_users(self, client):
        # create a non-admin user, login as them, try listing users
        email = f"TEST_nonadmin_{datetime.now().strftime('%H%M%S')}@test.com"
        password = "Pass1234!"
        r = client.post(f"{API}/auth/users", json={
            "email": email, "password": password, "name": "NonAdmin", "role": "user"})
        assert r.status_code == 200
        uid = r.json()["id"]
        try:
            lr = requests.post(f"{API}/auth/login", json={"email": email, "password": password})
            assert lr.status_code == 200
            tok = lr.json()["token"]
            r2 = requests.get(f"{API}/auth/users", headers={"Authorization": f"Bearer {tok}"})
            assert r2.status_code == 403
            # also POST should be forbidden
            r3 = requests.post(f"{API}/auth/users",
                               json={"email": "x@x.com", "password": "x", "name": "x"},
                               headers={"Authorization": f"Bearer {tok}"})
            assert r3.status_code == 403
        finally:
            client.delete(f"{API}/auth/users/{uid}")
