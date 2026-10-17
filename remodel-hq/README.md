# Remodel HQ

Single-file, offline web app for running a remodeling business. Open `index.html` in any browser — no install, no server.

- **Dashboard** — open quote value, booked YTD, win rate, avg margin on won jobs, active projects, receivables, tasks due this week.
- **Quotes** — client info, scope, line items from the price book or trade hourly rates, markup, tax on materials, discount, deposit. Shows internal cost and margin. Prints a client proposal (line prices with markup built in, category totals only, or lump sum) with exclusions, terms and signature lines. Convert an accepted quote to a project.
- **Projects** — kanban board (drag between Lead → Scheduled → In Progress → Punch List → Complete / On Hold) or table. Tasks with due dates, change orders, job costs by category, payments, budget vs. actual, amount owed, projected profit.
- **Templates** — reusable quote templates (seeded: bath, kitchen, basement, deck, paint). Price-book lines pick up current prices when a quote is created.
- **Price List** — trade labor rates and a unit price book (material + labor per unit), editable inline, CSV import/export.
- **Settings** — company info, default markup/tax/deposit/terms, JSON backup/restore, quotes/projects CSV export.

Shortcuts: `1`–`6` tabs · `N` new · `/` search · `Ctrl+S` save · `Esc` close.

**Limits:** data lives in this browser's localStorage (~5 MB). It does not sync across devices or users — download a backup regularly. Seeded prices are generic placeholders, not sourced; replace them with your own bids and rates.
