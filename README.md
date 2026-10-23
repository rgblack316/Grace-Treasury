# Grace Treasury — Church Accounting & Treasurer's Report App

A clean, self-hosted web application for church treasurers to track income, expenses, and
transfers across multiple bank accounts, reconcile against bank statements, attach receipts,
and produce a professional, printable monthly Treasurer's Report for business meetings.

Built to run privately on your own server (e.g. a home server) inside Docker. Every church that
installs it starts with a clean, empty database and creates its own administrator account on first run.

---

## ✨ Features

- **First-run setup wizard** — no default/shared credentials. Using the one-time setup code from
  installation, the first person to open the app creates the administrator (treasurer) account with a strong password (12+ characters, upper &
  lower case, a number, and a symbol).
- **Multiple bank accounts** — add, rename, set opening balances, and deactivate accounts. Account
  numbers are shown masked (e.g. `*1234`).
- **Funds** — track money by purpose (General, Building, Missions, …) independent of which account holds it.
  Each fund can have an **opening balance** (so you can start from what you already hold), and funds can be
  **nested** inside one another — a parent fund's total rolls up its own balance plus its children's, while
  each child is still tracked on its own.
- **Fund Activity** — move money between funds or adjust a single fund directly (for corrections or
  designations) from the dedicated **Funds** page, without touching any bank-account balance. Every entry is
  dated, can carry a memo, and appears in a clear history.
- **Split across funds** — when recording income or an expense you can divide the amount among several funds
  (e.g. a $1,000 offering: $600 General, $400 Building), with a helper showing the remaining unallocated amount.
  A single fund stays the quick default; splitting is optional.
- **Income / Expense / Transfer** — record expenses with Payment Method (Check, Debit Card, ACH, etc.), Check # for checks, Payee, Memo/Reason; record income
  and transfers between accounts. Filter the ledger by account, type, fund, category, **cleared status**,
  or date range, and search by memo or check number. Same-day checks are listed highest-number-first.
- **Dashboard** — current balance per account and per fund (with roll-ups for nested funds), plus recent activity.
- **Monthly Treasurer's Report** — pick any custom date range (or a preset), choose which accounts
  to include, and view/print it or download a letter-size PDF. Shows Balance Forward, itemized
  Expenses and Income, totals, and New Balance, with optional category-summary and fund-balance sections.
- **Bank reconciliation** — tick off each transaction that has cleared the bank; a running cleared
  balance per account helps you match your statement. Filter the ledger by **status (cleared /
  uncleared)** to quickly see what has not posted yet.
- **Void stale entries** — mark a transaction as **void** (e.g. a check that was never presented to the
  bank) so it no longer counts toward any account balance, reconciliation total, fund balance, or report —
  while staying in the ledger with a clear "Void" badge for your audit trail. Restore it anytime if it
  eventually posts.
- **Receipt attachments** — attach photos (JPG/PNG/HEIC/WEBP) or PDFs to any transaction. Files are
  stored **inside MongoDB (GridFS)**, so everything stays on your server — no cloud, no API keys.
- **Spreadsheet import** — bulk-import past months from a CSV template; new payees, categories, and
  funds are auto-created.
- **Branded browser title** — the browser tab shows your church's name with the app, e.g.
  *"Providence Baptist Church - Grace Treasury"*, pulled live from **Settings → Church Info**.
- **Users & roles** — the treasurer can add additional logins and create custom roles that limit what
  each person can do (view only, record transactions, manage settings, manage users, manage backups).
- **Backup & restore** — export the whole database to a JSON file (and restore it) from the Settings
  page, **plus automatic nightly backups** written to a folder/volume you choose, with configurable
  time and retention.

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

### Easiest: one-line scripts (Ubuntu / Debian)

On a fresh Ubuntu 22.04+/Debian 12+ server, the helper scripts install Docker, clone the repo,
generate a secure `.env`, and start everything for you. Run as your normal user (not root):

```bash
# Fresh install
curl -fsSL https://raw.githubusercontent.com/rgblack316/Grace-Treasury/main/install.sh -o install.sh
bash install.sh
```

Later, to update to the newest version (this makes a safety database backup first, then
fast-forwards the code and rebuilds — your data volume is never touched):

```bash
cd ~/grace-treasury
./upgrade.sh
```

> The scripts default to cloning `https://github.com/rgblack316/Grace-Treasury.git`. Override with
> `REPO_URL=... bash install.sh` if your repository lives elsewhere, and `APP_DIR=... ./upgrade.sh`
> if you installed somewhere other than `~/grace-treasury`.

#### One-time manual upgrade (existing VMs on an older script)

If a server is running an older copy of `upgrade.sh` that cancels because of files in `backups/`
(or because the script itself was hand-edited), the script cannot update itself. Do this **once**
per server to get onto the fixed version — afterwards `./upgrade.sh` works normally:

```bash
cd ~/grace-treasury            # or your install path

# 1. (Optional but recommended) take a manual database backup first
docker compose exec -T mongo mongodump --db church_treasury --archive --gzip \
  > backups/manual-$(date +%F_%H-%M-%S).archive.gz

# 2. Discard any local edits to tracked files (this does NOT delete your backups/ or .env —
#    untracked files and ignored files are left untouched)
git checkout -- .

# 3. Pull the latest code. Files in backups/ are untracked, so they do not block this.
git pull --ff-only origin main

# 4. Rebuild and restart (your MongoDB data volume is never touched)
docker compose up -d --build
```

From then on, the updated `upgrade.sh` ignores the `backups/` folder, so routine upgrades are just
`./upgrade.sh`.

Prefer to do it by hand? Follow the manual steps below.

### 1. Install prerequisites
- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/)

### 2. Get the code
```bash
git clone https://github.com/rgblack316/Grace-Treasury.git grace-treasury
cd grace-treasury
```

### 3. Create your environment file
```bash
cp env.example .env
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
creating your administrator account. You'll need the **setup code**: `install.sh` shows it at the end
and saves it as `SETUP_CODE` in `.env` (for a manual install, set your own there, or find the generated
one with `docker compose logs backend`). Then add your bank accounts and funds under **Settings**.

To stop:
```bash
docker compose down
```
Your data lives in the `mongo_data` Docker volume, so it survives restarts.

---

## ⚙️ Environment variables

Set these in your `.env` file (see `env.example`):

| Variable | Required | Description |
|----------|----------|-------------|
| `JWT_SECRET` | ✅ | Long random string used to sign login tokens. **Change this.** |
| `DB_NAME` | ✅ | Database name (default `church_treasury`). |
| `CORS_ORIGINS` | ✅ | Allowed origin(s) for the frontend, e.g. `http://localhost:8080`. |
| `TRUSTED_PROXY` | optional | IP or CIDR range that **cloudflared** (or another reverse proxy) connects from. Only requests from here may report the visitor's real IP via `CF-Connecting-IP`. Default `172.16.0.0/12` fits cloudflared running in the same VM as the app. |
| `SESSION_IDLE_HOURS` | optional | Sign-in lasts this long without activity (default `12`). Active users are renewed automatically. |
| `SESSION_MAX_DAYS` | optional | Everyone re-enters their password at least this often, even if active (default `7`). |
| `BACKUP_DIR` | optional | Folder (inside the backend container) where nightly backups are written. The Compose file mounts `./backups` on your host to `/data/backups`. |

> **Fully offline:** Everything — including receipt images (stored in MongoDB GridFS) — lives in your
> local database and files on your server. No external services or API keys are required.

---

## 🖥️ Running without Docker (manual / development)

**Backend**
```bash
cd backend
pip install -r requirements.txt        # or requirements-dev.txt to also run the tests
# set MONGO_URL, DB_NAME, JWT_SECRET, CORS_ORIGINS in backend/.env
uvicorn server:app --host 0.0.0.0 --port 8001
```

**Frontend**
```bash
cd frontend
yarn install
yarn start      # development
# or: yarn build  -> serve the build/ folder with any static server
```

> The app calls the backend at the **same origin** under `/api` (in Docker, the Nginx container proxies
> `/api` to the backend). For local `yarn start` development, run the frontend behind a proxy that forwards
> `/api` to `http://localhost:8001`, or serve the built frontend from the same origin as the API.

You'll also need MongoDB running locally (`mongodb://localhost:27017`).

---

## 🔐 First-run & security notes

- There are **no default credentials**. The first visit forces you to create an admin account, which
  requires the one-time **setup code** (`SETUP_CODE` in `.env`), so a stranger who reaches a fresh install
  can't claim it. Wrong codes are rate-limited, and only one first admin can ever be created.
- Passwords must be at least **12 characters** and include **uppercase, lowercase, a number, and a symbol**.
- Only Administrators can add/remove users and roles.
- Keep your `JWT_SECRET` private and back it up — changing it logs everyone out.
- **Sign-in protection:** 5 wrong passwords for an email from the same IP locks that email from that IP
  for 15 minutes; 20 failures from one IP locks the IP. Nginx also limits login requests to about 10 per
  minute per IP. Administrators can review failed sign-ins and unlock people under **Settings → Security**.
- **Temporary passwords:** passwords set by a user manager (new users and resets) must be changed at the
  next sign-in, so only the user knows their final password. Everyone can change their own password from
  the account menu.
- **Session length:** you stay signed in while you're using the app; after 12 hours without activity you're
  signed out, and everyone re-enters their password at least every 7 days (see `SESSION_IDLE_HOURS` /
  `SESSION_MAX_DAYS`).
- **Sessions:** changing or resetting a password, or changing someone's role, signs that user out of every
  device immediately. Admins can also sign a user out from **Settings → Users**, and anyone can use
  **Sign out other devices** from the account menu.
- **User management is Administrator-only.** Custom roles can't include *Manage users and roles*; to give
  someone that ability, make them an Administrator. (Upgrading removes it from any existing custom roles.)
  All user and role changes are recorded in **Settings → Security → Activity Log**.
- **Account emails:** if SMTP is set up (Backup & Restore → Email), users are emailed when their account is
  created, their password is reset or changed, or their role changes. Passwords are never included.
- **Browser protections:** nginx sends a strict Content Security Policy (only the app's own scripts, styles,
  fonts and API), refuses to be shown inside other sites, and sends `nosniff`, `Referrer-Policy: no-referrer`
  and a `Permissions-Policy` that turns off camera, microphone and location. Fonts are bundled with the app,
  so it makes no requests to outside services.
- **HTTPS (HSTS):** turn this on in **Cloudflare** (SSL/TLS → Edge Certificates → HTTP Strict Transport
  Security), not in the app, so local `http://` access on your network keeps working. Suggested: max-age
  1 month to start, *Include subdomains* off unless every subdomain uses HTTPS, *Preload* off, *No-Sniff* on.
  Also enable **Always Use HTTPS**.
- **Cloudflare Tunnel:** the app reads each visitor's real IP from Cloudflare so lockouts work per visitor.
  If cloudflared runs on the **same machine/VM** as Grace Treasury, no setup is needed. If it runs on a
  different machine, set `TRUSTED_PROXY` in `.env` to that machine's IP. (This is an app setting, not a
  Cloudflare one.) To check: after one wrong password from your phone, **Settings → Security** should show
  your phone's public IP, not a `172.x.x.x` address.

---

## 💾 Backups

From **Settings → Backup & Restore** you can:
- **Export** a full JSON backup of all data at any time, and **Restore** from a backup file (this
  replaces all current data and signs you out).
- Configure **automatic nightly backups**: enable/disable, set the time of day, and choose how many
  recent backups to keep. Nightly backups are written to the `BACKUP_DIR` folder (mapped to `./backups`
  on your host by the Compose file) and can be downloaded, restored, or deleted from the same page.

Backup & Restore is **Administrator-only**.

**Encrypt your backups.** Set a **backup passphrase** under **Backup Encryption** and every backup —
nightly, downloaded, and emailed — is encrypted (AES-256-GCM, key derived from the passphrase with
scrypt). Restoring an encrypted backup asks for its passphrase. **If the passphrase is lost, encrypted
backups cannot be opened** — write it down and keep it somewhere safe away from the server. Changing the
passphrase doesn't re-encrypt older backups; they still open with the passphrase in use when they were made.

Backups never include the email (SMTP) password; after restoring onto a new server, re-enter it under
Email Backups. Backup files are readable only by the app's user (`./backups` is mode 700, files 600).
Receipt images live in MongoDB and are preserved by the `mongo_data` volume.

The SMTP password and the backup key are stored encrypted in the database using a key derived from
`JWT_SECRET`. If you ever change `JWT_SECRET`, re-enter the SMTP password and set the backup passphrase again.

`upgrade.sh` also saves a full database dump and a copy of `.env` in `backups/pre-upgrade-*` (owner-only
permissions). These are **not** encrypted — delete old ones once an upgrade is confirmed working.

### Email backups (off-site copy)
Under **Settings → Backup & Restore → Email Backups** you can have each nightly backup emailed to the
treasurer automatically, using your own email account (SMTP — e.g. Gmail with an app password, or your
church's mail server). Enter the SMTP host/port/username/password, a from and recipient address, pick
STARTTLS (port 587) or SSL (port 465), and use **Send Test Email** to confirm it works. Nothing leaves
your server except the email you send through your own provider. Only **encrypted** backups are emailed, so set a backup
passphrase first.

---

## 🔄 Keeping dependencies current

- `backend/requirements.txt` lists only what the app imports, with exact versions; test tools are in
  `backend/requirements-dev.txt`.
- `frontend/yarn.lock` pins every JavaScript package; the Docker build installs exactly those versions.
- **Dependabot** (`.github/dependabot.yml`) opens weekly pull requests for Python and JavaScript updates
  and monthly ones for the Docker base images. In GitHub, also turn on **Settings → Code security →
  Dependabot alerts** and **Dependabot security updates**.

---

## 📄 License

This project is licensed under the **GNU General Public License v3.0 (GPL-3.0)**.

You are free to use, modify, and distribute this software, provided that any
distributed derivative works are also released under the GPL-3.0. The software
is provided "as is", without warranty of any kind. See the full text in the
[`LICENSE`](./LICENSE) file.
