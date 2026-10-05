# Grace Treasury — Church Accounting & Treasurer's Report App

A clean, self-hosted web application for church treasurers to track income, expenses, and
transfers across multiple bank accounts, reconcile against bank statements, attach receipts,
and produce a professional, printable monthly Treasurer's Report for business meetings.

Built to run privately on your own server (e.g. a home server) inside Docker. Every church that
installs it starts with a clean, empty database and creates its own administrator account on first run.

---

## ✨ Features

- **First-run setup wizard** — no default/shared credentials. The first person to open the app
  creates the administrator (treasurer) account with a strong password (12+ characters, upper &
  lower case, a number, and a symbol).
- **Multiple bank accounts** — add, rename, set opening balances, and deactivate accounts. Account
  numbers are shown masked (e.g. `*3217`).
- **Funds** — track money by purpose (General, Building, Missions, …) independent of which account holds it.
- **Income / Expense / Transfer** — record expenses with Check #, Payee, Memo/Reason; record income
  and transfers between accounts. Everything is searchable and filterable.
- **Dashboard** — current balance per account and per fund, plus recent activity.
- **Monthly Treasurer's Report** — pick any custom date range (or a preset), choose which accounts
  to include, and view/print it or download a letter-size PDF. Shows Balance Forward, itemized
  Expenses and Income, totals, and New Balance, with optional category-summary and fund-balance sections.
- **Bank reconciliation** — tick off each transaction that has cleared the bank; a running cleared
  balance per account helps you match your statement.
- **Receipt attachments** — attach photos (JPG/PNG/HEIC/WEBP) or PDFs to any transaction.
- **Spreadsheet import** — bulk-import past months from a CSV template; new payees, categories, and
  funds are auto-created.
- **Users & roles** — the treasurer can add additional logins and create custom roles that limit what
  each person can do (view only, record transactions, manage settings, manage users, manage backups).
- **Backup & restore** — export the entire database to a JSON file and restore it later, from the Settings page.

### Built-in roles
| Role | Can do |
|------|--------|
| **Administrator** | Everything (assigned to the first account; cannot be deleted) |
| **Bookkeeper** | View & record transactions, reconcile, view reports |
| **Viewer** | View transactions and reports only |

You can create your own roles with any combination of these permissions:
`transactions.view`, `transactions.manage`, `reports.view`, `settings.manage`, `users.manage`, `data.manage`.

---

## 🧱 Tech stack

- **Frontend:** React (served as a static build via Nginx in Docker)
- **Backend:** FastAPI (Python)
- **Database:** MongoDB
- **Auth:** JWT (email + password, bcrypt-hashed)

---

## 🚀 Quick start with Docker Compose (recommended)

This runs the whole stack (frontend + backend + MongoDB) on your own machine.

### 1. Install prerequisites
- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/)

### 2. Get the code
```bash
git clone https://github.com/<your-username>/grace-treasury.git
cd grace-treasury
```

### 3. Create your environment file
```bash
cp .env.example .env
```
Open `.env` and set a strong, random `JWT_SECRET`:
```bash
openssl rand -hex 32
```

### 4. Start it
```bash
docker compose up -d --build
```

### 5. Open the app
Visit **http://localhost:8080** (or your server's IP). On first launch you'll be guided through
creating your administrator account. Then add your bank accounts and funds under **Settings**.

To stop:
```bash
docker compose down
```
Your data lives in the `mongo_data` Docker volume, so it survives restarts.

---

## ⚙️ Environment variables

Set these in your `.env` file (see `.env.example`):

| Variable | Required | Description |
|----------|----------|-------------|
| `JWT_SECRET` | ✅ | Long random string used to sign login tokens. **Change this.** |
| `DB_NAME` | ✅ | Database name (default `church_treasury`). |
| `CORS_ORIGINS` | ✅ | Allowed origin(s) for the frontend, e.g. `http://localhost:8080`. |
| `EMERGENT_LLM_KEY` | optional | Only needed for **receipt attachments** (cloud file storage). Leave blank to run fully offline without the receipts feature. |

> **Note on receipts:** Receipt file storage uses a managed object-storage service and requires
> `EMERGENT_LLM_KEY`. All other data (accounts, transactions, users, reports) is stored entirely in
> your local MongoDB and never leaves your server. If you don't set this key, the app works normally —
> only the receipt-attachment feature is disabled.

---

## 🖥️ Running without Docker (manual / development)

**Backend**
```bash
cd backend
pip install -r requirements.txt
# set MONGO_URL, DB_NAME, JWT_SECRET, CORS_ORIGINS in backend/.env
uvicorn server:app --host 0.0.0.0 --port 8001
```

**Frontend**
```bash
cd frontend
yarn install
# set REACT_APP_BACKEND_URL in frontend/.env (e.g. http://localhost:8001)
yarn start      # development
# or: yarn build  -> serve the build/ folder with any static server
```

You'll also need MongoDB running locally (`mongodb://localhost:27017`).

---

## 🔐 First-run & security notes

- There are **no default credentials**. The first visit forces you to create an admin account.
- Passwords must be at least **12 characters** and include **uppercase, lowercase, a number, and a symbol**.
- Only users with the `users.manage` permission (the Administrator) can add/remove users and roles.
- Keep your `JWT_SECRET` private and back it up — changing it logs everyone out.

---

## 💾 Backups

From **Settings → Backup & Restore** you can:
- **Export** a full JSON backup of all data at any time.
- **Restore** a backup (this replaces all current data and signs you out).

Store exported backups somewhere safe (they contain your records and hashed logins).

---

## 📄 License

Provided as-is for church and non-profit use. See `LICENSE` if included.
