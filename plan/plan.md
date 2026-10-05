# Church Treasury & Accounting App

A self-hosted web app for a church treasurer to record income, expenses, and transfers across multiple bank accounts, and to produce a clean monthly treasurer's report for business meetings. Built on proper double-entry accounting underneath so the books always balance.

## Who it's for
- The church treasurer (primary user) who records transactions and runs reports.
- A small number of additional trusted people (e.g., pastor or assistant) who each get their own login.
- Runs on a local server in your home inside a Docker container; only people you give logins to can use it.

## The monthly report (informed by your current spreadsheet)
Your uploaded "Monthly Report.xlsx" is a per-account treasurer's statement titled "Providence Baptist Church – Treasurers Report for [Month] [Year]". The app uses it as the reference for what to include, but redesigns the layout for better readability and a cleaner printed appearance. For each selected account the report shows:

- **Account header** with the account (e.g., *3217) and "Balance Forward as of: [date] [amount]".
- **Expenses** table with Date, Check #, Payee, Amount, and Memo/Reason, followed by **Total Expenses**.
- **Income** lines such as Deposit and Interest Paid, followed by **Total Income**.
- **Summary** block: Balance Forward, Total Income, Less Expenses, and **New Balance as of: [date] [amount]**.

The report lets you **select which accounts to include** (your two reported accounts, or all of them) and choose **any custom date range** — a start and end date — so each report can cover the exact meeting-to-meeting period (e.g., 10/1/2026–10/28/2026) rather than a fixed calendar month. Quick presets (last month, this month, since last meeting) are offered for convenience, but the dates are always adjustable. "Balance Forward" reflects the balance as of the start date and "New Balance" reflects the end date. View it on a clean printable page or download it as a PDF formatted for letter-size paper. The church name and account labels are configurable.

In addition to this statement, the following supplementary summaries are available (and can be included or left off a given report):
- Income vs. expense summary by category.
- Fund balances.

## Core features and experience

**Accounts & funds**
- Track multiple bank accounts (starting with your two reported accounts plus a third) with masked labels like *3217; add, rename, or deactivate accounts at any time.
- Set each account's opening balance and date so "Balance Forward" and "New Balance" compute correctly.
- Track funds (e.g., General Fund, Building Fund, Missions Fund) so you can see how much money belongs to each purpose, independent of which account holds it.

**Chart of accounts (double-entry)**
- A chart of accounts organized into the standard groups: Assets (bank accounts), Liabilities, Equity/Fund balances, Income, and Expenses.
- Comes pre-loaded with a sensible starter chart (seeded from the income and expense types seen in your spreadsheet) that you can rename, add to, or remove items from.
- Every transaction is recorded with double-entry so totals always reconcile.

**Categories & payees (for fast, consistent entry)**
- **Categories** are optional on each transaction and fully manageable — add or remove them at any time — so income and expenses can be grouped for the summary reports.
- A managed list of **Payees/Vendors** (e.g., Frontier Communications, Hope Gas, Walmart) that you select from a dropdown when recording a transaction, with the ability to add or remove entries — just like categories — to make inputting transactions quick and consistent.

**Recording money movement**
- Record **income** (e.g., Deposit, Interest Paid) with date, account, amount, optional category, fund, and memo.
- Record **expenses** with date, account, **Check #**, **Payee** (from the dropdown), amount, optional category, fund, and **Memo/Reason**.
- Record **transfers** between bank accounts.
- Browse, search, edit, and delete transactions; filter by account, fund, category, payee, or date range.

**Dashboard**
- Current balance per bank account and per fund, plus recent activity.

**Login**
- Each person logs in with their own email and password; the treasurer can add or remove the other logins.

## User flow
1. Log in.
2. Land on a dashboard showing balances per bank account and per fund, plus recent activity.
3. Add a transaction — income, expense (with Check #, Payee, Memo/Reason), or transfer.
4. Review and manage transactions in a searchable, filterable list.
5. Go to Reports, choose the date range (or a preset) and the accounts to include, and generate the treasurer's report.
6. View it on screen, print it, or download the PDF for the business meeting.
7. Manage accounts, funds, categories, payees, and the chart of accounts from a settings area as needs change.

## UI/UX feel
- Clean, calm, and trustworthy — appropriate for financial record-keeping, not flashy.
- Clear numbers and tables that are easy to read and easy to print; the printed report closely mirrors the familiar spreadsheet.
- Straightforward navigation: Dashboard, Transactions, Reports, Settings.
- Works well on a desktop/laptop browser; usable on a tablet.

## Implementation phases

**Phase 1 — MVP (built now)**
- Logins for a few users, with the treasurer able to add/remove users.
- Manage bank accounts (add/rename/deactivate, opening balances), funds, categories, and a Payees/Vendors list (all add/remove), plus the chart of accounts (starter chart pre-loaded).
- Record income, expenses (Date, Check #, Payee, Amount, optional Category, Memo/Reason), and transfers using double-entry.
- Transaction list with search, filter, edit, and delete.
- Dashboard with account and fund balances.
- Monthly treasurer's report redesigned for readability, with a **selectable custom date range** (plus presets) and selectable accounts, viewable/printable on screen and downloadable as PDF; optional category-summary and fund-balance sections.

**Phase 2 — later**
- Budgets per category/fund and budget-vs-actual reporting.
- Bank reconciliation (mark transactions cleared, reconcile to a statement balance).
- Import transactions from a spreadsheet or bank CSV.
- Attach receipts/images to transactions.

**Phase 3 — later**
- Year-end and giving-statement reports.
- Recurring transactions (e.g., regular monthly bills).
- Audit log of who changed what.
- Data export/backup tools suited to self-hosting.

## Assumptions
- Logins use email + password (standard custom authentication), since this runs on your private home server for a few trusted people.
- The first account created is the treasurer/administrator who can manage other users; others are regular users who can record transactions and run reports (no separate permission tiers in the MVP — everyone with a login can do everything except manage users).
- Currency is US Dollars with standard two-decimal formatting.
- The printed monthly report is informed by your spreadsheet's content but redesigned for readability and a cleaner printed appearance; the church name defaults to "Providence Baptist Church" and is editable.
- The starter chart of accounts, income types (Deposit, Interest Paid), a starter expense category set, and a starter Payees/Vendors list are seeded from your spreadsheet and are fully editable (add/remove).
- Categories are optional on each transaction; the summary-by-category report simply reflects whatever categories are assigned.
- "Deposit" income is recorded as a single line as in your current report; finer income breakdowns (tithes, offerings, designated) are optional categories you can add if desired.
- Reports use a selectable custom date range (any start/end date) to match variable meeting-to-meeting periods, with quick presets available; the PDF is formatted for standard letter-size paper.
- Three bank accounts to start (your two reported accounts plus one more), with add/remove supported from day one; account numbers are shown masked (e.g., *3217).
- All data is stored locally within your self-hosted setup; no external/cloud services are required for the MVP.
