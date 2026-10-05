# Grace Treasury — Church Accounting App — PRD

## Summary
Self-hostable, generic church treasury app. Track income/expenses/transfers across bank accounts,
reconcile, attach receipts, import CSV, produce printable/PDF monthly Treasurer's Reports. Distributed
via GitHub + Docker Compose; each church starts with an empty DB and runs a first-run setup wizard.

## Architecture
- Backend: FastAPI (`/app/backend/server.py`), MongoDB (motor). Routes under `/api`.
- Frontend: React 19 + CRACO, Tailwind, shadcn/ui, Spectral/IBM Plex Sans/JetBrains Mono.
- Auth: JWT Bearer (localStorage `ct_token`), bcrypt. First user = Administrator via setup wizard.
- Receipts: Emergent object storage (requires EMERGENT_LLM_KEY); all other data in local MongoDB.
- PDF: reportlab, letter size.
- Distribution: docker-compose.yml (mongo + backend + frontend/nginx), Dockerfiles, README.md, .env.example.

## Permissions / Roles
- Permissions: transactions.view, transactions.manage, reports.view, settings.manage, users.manage, data.manage.
- Built-in roles seeded on setup: Administrator (all, is_system), Bookkeeper, Viewer. Admin can create custom roles.
- Enforced backend (require_permission deps) and gated in frontend (can() + visible nav/buttons).

## Implemented
### MVP (2026-06)
- Accounts/funds/categories/payees/COA CRUD, income/expense/transfer, dashboard, transactions list, Treasurer's Report (print + PDF).
### Iteration 2
- CSV import, bank reconciliation (cleared + running cleared balance), receipt attachments.
### Iteration 3 (generic / self-host)
- First-run setup wizard; NO default credentials; strong-password rule (12+, upper/lower/number/symbol).
- No seeded accounts/transactions/payees; generic categories + General Fund + generic COA seeded on setup; church name blank.
- Roles & permissions system (built-in + custom), per-user role assignment, strong password on user create/update.
- Database backup (export JSON) and restore (import JSON, replaces all data) in Settings.
- README.md, .env.example, docker-compose.yml, backend/frontend Dockerfiles, nginx.conf.
- Verified: backend 26/26 (+ prior suites), all targeted frontend flows pass; DB wiped for clean first-run handoff.

## Backlog
- P1: Budgets per fund/category + budget-vs-actual; year-end giving statements.
- P2: Recurring transactions; audit log; split server.py into modules; optional local-disk receipt storage to remove cloud dependency.

## Notes
- DB is intentionally empty on delivery → app shows the setup wizard at /setup.
- CORS `*` in dev; docker-compose sets CORS_ORIGINS to the frontend origin.
- Receipts need EMERGENT_LLM_KEY; documented as optional in README.
