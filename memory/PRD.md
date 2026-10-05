# Church Treasury & Accounting App — PRD

## Original Problem Statement
Self-hosted accounting app for a church treasurer (Providence Baptist Church) to track income and expenses across multiple bank accounts and print monthly treasurer's reports for business meetings. Three bank accounts to start, with add/remove support. Runs locally in Docker.

## Architecture
- **Backend**: FastAPI (`/app/backend/server.py`), MongoDB (motor). All routes under `/api`.
- **Frontend**: React 19 + CRACO, Tailwind, shadcn/ui, Spectral/IBM Plex Sans/JetBrains Mono fonts.
- **Auth**: JWT Bearer tokens (localStorage key `ct_token`), bcrypt password hashing. First user = admin/treasurer.
- **PDF**: reportlab server-side (`/api/reports/treasurer/pdf`), letter size.

## User Personas
- **Treasurer (admin)**: records transactions, runs reports, manages users and all settings.
- **Additional users**: record transactions and run reports; cannot manage users.

## Core Requirements (static)
- Multi bank-account tracking (masked labels), add/rename/deactivate, opening balances.
- Funds, categories, payees, chart of accounts — all CRUD manageable.
- Record income / expense (Check #, Payee, Memo) / transfer.
- Transaction list: search, filter (account/type/fund/category/date), edit, delete.
- Dashboard: per-account + per-fund balances, recent activity.
- Monthly treasurer's report: custom date range + presets, selectable accounts, printable + PDF, optional category/fund sections. Balance Forward / Total Income / Less Expenses / New Balance reconcile.

## Implemented (2026-06 / MVP complete)
- JWT auth, admin seeding (rgblack@gmail.com), user management (admin-only).
- Accounts/Funds/Categories/Payees/COA CRUD + Church Info settings.
- Income/Expense/Transfer recording via dialog; transactions list with filters/search/edit/delete.
- Dashboard with balances + recent activity.
- Treasurer's report (on-screen, print CSS, server-side PDF) with reconciliation verified.
- Seeded 3 accounts, 3 funds, categories, payees, COA, and sample June 2026 transactions (from uploaded spreadsheet).
- Header derives church name from settings.
- Verified: 24/24 backend tests pass; all critical frontend flows pass.

## Backlog
### P1
- Budgets per category/fund + budget-vs-actual.
- Bank reconciliation (mark cleared, reconcile to statement balance).
- CSV/spreadsheet import.
- Attach receipts/images to transactions (object storage).

### P2
- Year-end & giving-statement reports.
- Recurring transactions.
- Audit log (who changed what).
- Data export/backup tools for self-hosting.
- Deeper double-entry posting via chart of accounts.

## Notes
- CORS currently `*`; tighten origins before production (low risk — Bearer auth, not cookies).
- Sample June 2026 transactions on *3217 are demo data and deletable.
