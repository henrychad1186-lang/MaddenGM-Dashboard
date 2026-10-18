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

## Hosted version (`hosted.html`)

`hosted.html` is the copy published as a private claude.ai artifact so it opens on a phone. It is generated from `index.html` by `build_hosted.py`; edit `index.html`, then rebuild:

```
python3 remodel-hq/build_hosted.py remodel-hq/index.html remodel-hq/hosted.html
```

Differences from `index.html`:
- Data lives in the artifact's database (collection `biz`: `settings`, `pricebook`, `trades`, and one doc per quote `q_*`, project `p_*`, template `t_*`), so it syncs across devices. Only the owner and Editors can read or write it. localStorage is just a fast-start cache.
- Print becomes **Proposal**: an in-page preview plus a downloadable standalone `.html` proposal to print or send.
- Confirmations and prompts are in-page dialogs; CSV and backup exports go through the viewer's download prompt.
- It is a page fragment (no `<html>`/`<head>`): the artifact host adds that wrapper. Use `index.html` for opening locally.
