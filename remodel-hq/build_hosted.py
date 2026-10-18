# Builds hosted.html (the claude.ai artifact version) from index.html.
# Usage: python3 remodel-hq/build_hosted.py remodel-hq/index.html remodel-hq/hosted.html
import sys, re
src, dst = sys.argv[1], sys.argv[2]
s = open(src).read()
def R(old, new, count=1):
    global s
    n = s.count(old)
    assert n == count, (n, old[:80])
    s = s.replace(old, new)

# ---- skeleton
R('''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Remodel HQ</title>''', '''<title>Remodel HQ</title>
<meta name="claude:viewport-fit-sides" content="cover">''')
R('</style>\n</head>\n<body>', '</style>')
R('</script>\n</body>\n</html>', '</script>')

# ---- theme tokens: guarded dark + explicit data-theme
DARK = '''--bg:#121417;--panel:#1b1e23;--panel2:#22262c;--text:#e6e8eb;--muted:#9aa3ad;--line:#2f343b;
    --accent:#f97316;--accent-ink:#1b1e23;--good:#4ade80;--warn:#fbbf24;--bad:#f87171;--info:#60a5fa;
    --shadow:0 1px 2px rgba(0,0,0,.4);'''
R('''@media (prefers-color-scheme: dark){
  :root{''' + DARK + '''}
}''', '''@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){''' + DARK + '''color-scheme:dark}
}
:root[data-theme="dark"]{''' + DARK + '''color-scheme:dark}''')

# ---- layout: safe-area gutters, sticky header
GUT = 'padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))'
R('html,body{margin:0;background:var(--bg);', 'body{margin:0;background:var(--bg);')
R('header{position:sticky;top:0;z-index:20;', 'body::before{content:"";position:fixed;inset:0 0 auto;height:env(safe-area-inset-top,0px);z-index:30;background:var(--panel)}\nheader{position:sticky;top:env(safe-area-inset-top,0px);z-index:20;')
R('padding:10px 16px;flex-wrap:wrap}', 'padding-block:10px;' + GUT + ';flex-wrap:wrap}')
R('main{max-width:1280px;margin:0 auto;padding:16px}', 'main{max-width:1280px;margin:0 auto;padding-block:16px;' + GUT + '}')
R('main{padding:12px}', 'nav button kbd{display:none}')
R('.toast{position:fixed;bottom:16px;right:16px;', '.toast{position:fixed;bottom:calc(16px + env(safe-area-inset-bottom,0px));right:max(16px,env(safe-area-inset-right,0px));')
R('#printArea{display:none}\n', '''.sync{font-size:11px;font-weight:700;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:2px 8px;white-space:nowrap}
.sync.err{color:var(--warn);border-color:var(--warn)}
button.danger{background:var(--bad);border-color:var(--bad);color:var(--bg)}
#ask{width:min(440px,92vw)}
#ask p{margin:0 0 12px;font-size:15px}
.paper{background:#fff;color:#1b1f24;border-radius:8px;padding:20px;overflow-x:auto;box-shadow:var(--shadow)}
.paper th{background:#f1f2f4;color:#444}.paper th,.paper td{border-color:#ddd}
.paper .totals{max-width:300px}
''')
s = re.sub(r'@media print\{.*?\n\}\n', '', s, flags=re.S)

# ---- markup
R('<h1>Remodel <span>HQ</span></h1>', '<h1>Remodel <span>HQ</span></h1>\n  <span id="sync" class="sync">Connecting…</span>')
R('<h3 style="margin-top:0">Company (prints on quotes)</h3>', '<h3 style="margin-top:0">Company (shown on proposals)</h3>')
R('<p class="help">Everything is stored in this browser (localStorage, ~5 MB limit). It does not sync between devices or users. Back up regularly.</p>',
  '<p class="help" id="storeHelp">Your data is saved to this page\'s private database, so it is the same on your phone and computer. Only you, and anyone you add as an Editor, can see it. Download a backup now and then anyway.</p>')
R('<div id="printArea"></div>\n', '''<dialog id="ask"><div class="db"><p id="askMsg"></p><input id="askInput" hidden style="margin-bottom:12px">
  <div class="bar" style="margin:0"><span class="grow"></span><button type="button" id="askNo">Cancel</button><button type="button" class="pri" id="askYes">OK</button></div></div></dialog>
''')
R('data-act="print">Print</button>', 'data-act="print">Proposal</button>')
R('<button data-a="print">Print / PDF</button>', '<button data-a="print">Proposal</button>')
R('<label>Printed price detail</label>', '<label>Proposal price detail</label>')
R('(not printed)', '(not on proposal)')

# ---- storage + sync
R('''let DB;
try { DB = JSON.parse(localStorage.getItem(KEY)) || seed(); } catch { DB = seed(); }
DB.ui = DB.ui || { tab: "dash", pView: "board" };
let saveTimer;
function save() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    try { localStorage.setItem(KEY, JSON.stringify(DB)); }
    catch (e) { toast("Save failed: storage full? Download a backup."); }
  }, 150);
}''', '''/* State lives in the artifact database (collection "biz", one doc per record) when the
   viewer provides one; localStorage is a fast-start cache and the offline fallback. */
const blankDB = () => ({ settings: seed().settings, pricebook: [], trades: [], templates: [], quotes: [], projects: [], ui: { tab: "dash", pView: "board" } });
let DB;
try { DB = JSON.parse(localStorage.getItem(KEY)); } catch { DB = null; }
DB = DB || blankDB();
DB.ui = DB.ui || { tab: "dash", pView: "board" };
let saveTimer, store = null, ready = false, syncing = false, resync = false, openDocKey = null;
const lastSent = {}, heldRemote = {};
// Stable stringify so key order never makes identical docs look different.
const canon = v => Array.isArray(v) ? "[" + v.map(canon).join(",") + "]"
  : v && typeof v === "object" ? "{" + Object.keys(v).sort().map(k => JSON.stringify(k) + ":" + canon(v[k])).join(",") + "}" : JSON.stringify(v ?? null);
function setSync(text, err = false) { const el = $("#sync"); el.textContent = text; el.classList.toggle("err", err); }
function docsOf() {
  const m = { settings: DB.settings, pricebook: { items: DB.pricebook }, trades: { items: DB.trades } };
  DB.quotes.forEach(q => m["q_" + q.id] = q); DB.projects.forEach(p => m["p_" + p.id] = p); DB.templates.forEach(t => m["t_" + t.id] = t);
  return m;
}
function save() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    try { localStorage.setItem(KEY, JSON.stringify(DB)); } catch {}
    if (store && ready) flush();
  }, 400);
}
async function flush() {
  if (syncing) { resync = true; return; }
  syncing = true; setSync("Saving…");
  try {
    const docs = docsOf(), col = store.collection("biz");
    for (const [k, v] of Object.entries(docs)) {
      const j = canon(v);
      if (lastSent[k] !== j) { await col.doc(k).set(JSON.parse(j)); lastSent[k] = j; }
    }
    for (const k of Object.keys(lastSent)) if (!(k in docs)) { await col.doc(k).delete(); delete lastSent[k]; }
    setSync("Saved");
  } catch (e) {
    setSync("Not saved", true);
    toast(e && e.code === "quota_exceeded" ? "The database is full. Delete old quotes or projects, then try again."
      : "Couldn't save to the cloud. Your changes are kept on this device and will retry on your next edit.");
  }
  syncing = false;
  if (resync) { resync = false; flush(); }
}
function putRemote(key, body) {
  if (key === "settings") DB.settings = { ...seed().settings, ...body };
  else if (key === "pricebook") DB.pricebook = body.items || [];
  else if (key === "trades") DB.trades = body.items || [];
  else {
    const coll = { q: "quotes", p: "projects", t: "templates" }[key[0]]; if (!coll) return;
    const arr = DB[coll], o = arr.find(x => x.id === body.id);
    if (o) { Object.keys(o).forEach(k => delete o[k]); Object.assign(o, body); } else arr.push(body);
  }
}
function dropRemote(key) {
  const coll = { q: "quotes", p: "projects", t: "templates" }[key[0]], id = key.slice(2);
  if (coll && key[1] === "_") DB[coll] = DB[coll].filter(x => x.id !== id);
}
function onStore(snap) {
  if (!ready) {
    if (snap.metadata.fromCache && snap.empty) return;
    ready = true;
    const hadLocal = DB.quotes.length + DB.projects.length + DB.templates.length + DB.pricebook.length > 0;
    if (snap.empty) { setSync("Saved"); if (hadLocal) flush(); render(); return; }
    const ui = DB.ui; DB = blankDB(); DB.ui = ui;
    for (const d of snap.docs) { const body = d.data(); lastSent[d.id] = canon(body); putRemote(d.id, JSON.parse(lastSent[d.id])); }
    try { localStorage.setItem(KEY, JSON.stringify(DB)); } catch {}
    setSync("Saved"); render(); return;
  }
  let changed = false;
  const seen = new Set();
  for (const d of snap.docs) {
    seen.add(d.id);
    if (d.metadata.hasPendingWrites) continue;
    const j = canon(d.data());
    if (lastSent[d.id] === j) continue;
    if (d.id === openDocKey) { heldRemote[d.id] = j; continue; } // don't swap the record out from under an open editor
    lastSent[d.id] = j; putRemote(d.id, JSON.parse(j)); changed = true;
  }
  if (!snap.metadata.fromCache) for (const k of Object.keys(lastSent)) {
    if (seen.has(k) || k === openDocKey) continue;
    delete lastSent[k]; dropRemote(k); changed = true;
  }
  if (changed) { try { localStorage.setItem(KEY, JSON.stringify(DB)); } catch {} render(); }
}
function releaseDoc() {
  const k = openDocKey; openDocKey = null;
  if (!k || !(k in heldRemote)) return;
  const j = heldRemote[k]; delete heldRemote[k];
  // Apply the other device's version only if nothing was edited here; otherwise this edit wins on the next save.
  const local = docsOf()[k];
  if (local && canon(local) === lastSent[k]) { lastSent[k] = j; putRemote(k, JSON.parse(j)); }
}
let dl = null;
async function connect() {
  const use = window.claude && window.claude.use;
  [store, dl] = use ? await Promise.all([window.claude.use("db"), window.claude.use("downloads")]) : [null, null];
  if (!store) {
    if (!DB.pricebook.length && !DB.quotes.length && !DB.templates.length) { const ui = DB.ui; DB = seed(); DB.ui = ui; save(); render(); }
    setSync("This device only", true);
    $("#storeHelp").textContent = "Cloud sync isn't available here, so data is kept in this browser only (about 5 MB). Download backups regularly.";
    return;
  }
  store.collection("biz").onSnapshot(onStore, () => { setSync("Sync stopped", true); toast("Lost the connection to your data. Reload the page to reconnect."); });
}

/* In-page confirm / prompt (the hosted viewer blocks the browser's own dialogs). */
function ask(msg, { input = null, ok = "OK", danger = false } = {}) {
  return new Promise(res => {
    const d = $("#ask"), inp = $("#askInput"), yes = $("#askYes");
    $("#askMsg").textContent = msg; inp.hidden = input === null; inp.value = input ?? "";
    yes.textContent = ok; yes.className = danger ? "danger" : "pri";
    const done = v => { d.close(); res(v); };
    yes.onclick = () => done(input === null ? true : (inp.value.trim() || null));
    $("#askNo").onclick = () => done(input === null ? false : null);
    d.oncancel = e => { e.preventDefault(); done(input === null ? false : null); };
    inp.onkeydown = e => { if (e.key === "Enter") yes.click(); };
    d.showModal(); (input === null ? yes : inp).focus();
  });
}''')

R('''function download(name, text, type = "text/plain") {
  const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}''', '''async function download(name, text, type = "text/plain") {
  if (!(window.claude && window.claude.use)) { // opened as a plain local file
    const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name; a.click();
    return setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }
  if (!dl) return toast("File downloads aren't available in this view.");
  try { await dl.save({ filename: name, data: text }); toast("Saved " + name); }
  catch (e) { if (!e || e.code !== "declined") toast("Couldn't save " + name + ". Try again in a moment."); }
}''')

# ---- dialogs track the open record
R('dlg.addEventListener("close", () => { dlgSave = null; render(); });', 'dlg.addEventListener("close", () => { dlgSave = null; releaseDoc(); render(); });')
R('''  const q = DB.quotes.find(x => x.id === id); if (!q) return;
  const draw''', '''  const q = DB.quotes.find(x => x.id === id); if (!q) return;
  openDocKey = "q_" + q.id;
  const draw''')
R('''  const p = DB.projects.find(x => x.id === id); if (!p) return;
''', '''  const p = DB.projects.find(x => x.id === id); if (!p) return;
  openDocKey = "p_" + p.id;
''')
R('''  const t = DB.templates.find(x => x.id === id);
  const draw''', '''  const t = DB.templates.find(x => x.id === id); if (!t) return;
  openDocKey = "t_" + t.id;
  const draw''')

# ---- confirm/prompt call sites
R('''    $("#dlgActions").onclick = e => {
      const a = e.target.dataset.a;
      if (a === "print") printQuote(q);
      if (a === "tpl") { const name = prompt("Template name", q.projectName || "New template"); if (!name) return;''',
'''    $("#dlgActions").onclick = async e => {
      const a = e.target.dataset.a;
      if (a === "print") showProposal(q);
      if (a === "tpl") { const name = await ask("Name this template", { input: q.projectName || "New template", ok: "Save template" }); if (!name) return;''')
R('if (a === "del" && confirm(`Delete quote #${q.number}?`))', 'if (a === "del" && await ask(`Delete quote #${q.number}? This can\'t be undone.`, { ok: "Delete quote", danger: true }))')
R('''    $("#dlgActions").onclick = e => {
      const a = e.target.dataset.a;
      if (a === "q")''', '''    $("#dlgActions").onclick = async e => {
      const a = e.target.dataset.a;
      if (a === "q")''')
R('if (a === "del" && confirm(`Delete project "${p.name}"?`))', 'if (a === "del" && await ask(`Delete project "${p.name}"? Its costs, payments and tasks go with it.`, { ok: "Delete project", danger: true }))')
R('$("#tList").onclick = e => {', '$("#tList").onclick = async e => {')
R('if (confirm(`Delete template "${t.name}"?`))', 'if (await ask(`Delete template "${t.name}"?`, { ok: "Delete template", danger: true }))')
R('''  $(tableSel).addEventListener("click", e => {
    if (!e.target.hasAttribute("data-rm")) return;''', '''  $(tableSel).addEventListener("click", async e => {
    if (!e.target.hasAttribute("data-rm")) return;''')
R('if (confirm(`Delete "${r.name || r.trade}"?`))', 'if (await ask(`Delete "${r.name || r.trade || "this row"}"?`, { ok: "Delete", danger: true }))')
R('if (!confirm("Replace ALL current data with this backup?")) return;', 'if (!await ask("Replace all current data with this backup? Everything now in Remodel HQ will be overwritten.", { ok: "Replace data", danger: true })) return;')
R('$("#reset").onclick = () => { if (confirm("Erase all quotes, projects, templates and pricing and restore the starter data?") && confirm("Really? This cannot be undone without a backup.")) {',
  '$("#reset").onclick = async () => { if (await ask("Erase all quotes, projects, templates and pricing and restore the starter data? This can\'t be undone without a backup.", { ok: "Erase everything", danger: true })) {')
R('else if (act === "print") printQuote(q);', 'else if (act === "print") showProposal(q);')
R('window.addEventListener("afterprint", () => $("#printArea").innerHTML = "");\n', '')

# ---- proposal: in-page preview + downloadable standalone HTML
i = s.index('/* ---------- print ---------- */'); j = s.index('/* ---------- projects ---------- */')
body = s[i:j]
body = body.replace('/* ---------- print ---------- */\nfunction printQuote(q) {', '/* ---------- proposal ---------- */\nfunction proposalHTML(q) {')
body = body.replace('  $("#printArea").innerHTML = `<div class="pq">', '  return `<div class="pq">')
body = body.replace('''    <div class="sig"><div>Client signature / date</div><div>${esc(s.company)} / date</div></div></div>`;
  window.print();
}''', '''    <div class="sig"><div>Client signature / date</div><div>${esc(s.company)} / date</div></div></div>`;
}
const PQ_CSS = `body{font:13px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:#1b1f24;background:#fff;margin:0;padding:24px;max-width:860px;margin:auto}
table{border-collapse:collapse;width:100%}th,td{padding:6px 8px;border-bottom:1px solid #ddd;text-align:left}th{background:#f1f2f4;font-size:11px;text-transform:uppercase}
.n{text-align:right;font-variant-numeric:tabular-nums}.totals{margin-left:auto;max-width:300px}.totals div{display:flex;justify-content:space-between;padding:3px 0}
.totals .big{font-size:18px;font-weight:700;border-top:1px solid #ddd;padding-top:6px}
.pq h1{font-size:22px;margin:0}.pq .hdr{display:flex;justify-content:space-between;gap:20px;border-bottom:3px solid #c2410c;padding-bottom:10px;margin-bottom:14px}
.pq .meta{display:flex;justify-content:space-between;gap:20px;margin-bottom:14px}.pq .sec{margin:12px 0}.pq .sec h3{font-size:13px;margin:0 0 4px;text-transform:uppercase;color:#c2410c}
.pq .sig{display:flex;gap:40px;margin-top:40px}.pq .sig div{flex:1;border-top:1px solid #000;padding-top:4px}@page{margin:14mm}`;
function showProposal(q) {
  const html = proposalHTML(q);
  openDlg(`Proposal #${q.number}`, `<p class="help" style="margin-top:0">Download the proposal as a file, then open it to print, save as PDF, or send it to ${esc(q.client.name || "the client")}.</p><div class="paper">${html}</div>`,
    `<button class="pri" data-a="dl">Download proposal</button> <button data-a="back">Back to quote</button>`);
  $("#dlgActions").onclick = e => {
    const a = e.target.dataset.a;
    if (a === "back") editQuote(q.id);
    if (a === "dl") {
      const name = `Proposal-${q.number}-${(q.client.name || "client").replace(/[^A-Za-z0-9]+/g, "-")}.html`;
      download(name, `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Proposal #${q.number}</title><style>${PQ_CSS}</style></head><body>${html}</body></html>`, "text/html");
    }
  };
}''')
s = s[:i] + body + s[j:]
R('show(DB.ui.tab || "dash");', 'show(DB.ui.tab || "dash");\nconnect();')
assert 'confirm(' not in s and 'prompt(' not in s and 'print()' not in s and 'printArea' not in s, "leftover blocked API"
open(dst, 'w').write(s)
print("ok", len(s))
