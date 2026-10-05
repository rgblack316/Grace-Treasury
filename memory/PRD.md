# Grace Treasury — Church Accounting App — PRD

## Summary
Self-hostable, generic church treasury app. Track income/expenses/transfers across bank accounts,
reconcile, attach receipts, import CSV, produce printable/PDF monthly Treasurer's Reports. Distributed
via GitHub + Docker Compose; each church starts with an empty DB and runs a first-run setup wizard.
Fully offline — no cloud services or API keys required.

## Architecture
- Backend: FastAPI (`/app/backend/server.py`), MongoDB (motor). Routes under `/api`.
- Frontend: React 19 + CRACO, Tailwind, shadcn/ui.
- Auth: JWT Bearer (localStorage `ct_token`), bcrypt. First user = Administrator via setup wizard.
- Receipts: MongoDB GridFS (`fs_bucket`) — local, persists in mongo_data volume.
- Scheduled backups: APScheduler nightly job -> JSON files in BACKUP_DIR (configurable).
- PDF: reportlab, letter size.
- Distribution: docker-compose.yml (mongo + backend + frontend/nginx), Dockerfiles, README.md, .env.example.

## Permissions / Roles
- Permissions: transactions.view, transactions.manage, reports.view, settings.manage, users.manage, data.manage.
- Built-in roles: Administrator (all, is_system), Bookkeeper, Viewer. Admin can create custom roles.
- Enforced backend (require_permission deps) + gated frontend (can()).

## Implemented
- MVP: accounts/funds/categories/payees/COA CRUD, income/expense/transfer, dashboard, transactions list, Treasurer's Report (print + PDF).
- Iteration 2: CSV import, bank reconciliation (cleared + running cleared balance), receipt attachments.
- Iteration 3: first-run setup wizard, no default creds, strong-password rule; no seeded accounts/transactions (generic categories/fund/COA only); roles & permissions; DB export/import; Docker/README distribution.
- Iteration 4: receipts in MongoDB GridFS (fully offline); automatic nightly backups (APScheduler) with enable/time/retention + run/list/download/delete/restore server backups; path-traversal guarded; data.manage gated.
- Verified across iterations by testing agent; latest backend 23/23, no open defects.

### Iteration 5 (email backups)
- SMTP email backups: configurable host/port/username/password/from/to + STARTTLS/SSL; password masked on read, retained when blank.
- Endpoints (data.manage): GET/PUT /api/settings/email, POST /api/email/test, POST /api/backups/{name}/email. Nightly job emails the backup when enabled (maybe_email_backup).
- Settings → Backup & Restore → Email Backups card with Save + Send Test Email.
- Email/SMTP failures return 400 (not 502) so the real error reaches the UI through the ingress.
- Verified: backend 14/14; UI persistence/masking/permissions pass.

## Backlog
- P1: Budgets per fund/category + budget-vs-actual; year-end giving statements.
- P2: Recurring transactions; audit log; split server.py and Settings.js into modules.

## Notes
- DB intentionally empty on delivery -> setup wizard at /setup.
- BACKUP_DIR defaults to backend/backups; docker-compose mounts ./backups volume.
- No cloud keys needed; receipts live in MongoDB.
