"""Client-facing scope text in the Remodel HQ template seed.

A template's `scope` is the one field here that prints on the proposal
the client signs (`index.html`, the "Scope of work" section). Its
`description` and the price-book `note` do not — they are internal.
That asymmetry is what makes this worth a test: an internal note left
in a scope leaks to the client, and a promise added to a scope is a
promise only the client ever reads.

There is no JS test runner in this repo, so these parse the HTML.
"""

import pathlib
import re

import pytest

_HQ = pathlib.Path(__file__).resolve().parent.parent / "remodel-hq"
_SOURCES = ("index.html", "hosted.html")

# Phrases that belong to the estimator's own sheets, not to a client.
_INTERNAL = ("painting sheet", "quick price list", "master guide",
             "baseline says", "range $", "min $", "oct 17")


def _text(name):
    path = _HQ / name
    if not path.exists():
        pytest.skip(f"{name} not present")
    return path.read_text(encoding="utf-8")


def _scopes(src):
    """{template name: scope} for every entry in seed()."""
    found = re.findall(
        r'\{ id: uid\(\), name: "([^"]+)".*?scope: "((?:[^"\\]|\\.)*)"',
        src, re.S)
    assert found, "no templates parsed — the seed() shape changed"
    return dict(found)


@pytest.mark.parametrize("name", _SOURCES)
def test_no_scope_leaks_an_internal_source_note(name):
    """#82 found three. This keeps the fourth from shipping."""
    leaks = [(t, p) for t, s in _scopes(_text(name)).items()
             for p in _INTERNAL if p in s.lower()]
    assert not leaks, f"internal notes in client-facing scope: {leaks}"


@pytest.mark.parametrize("name", _SOURCES)
def test_the_trip_minimum_does_not_promise_labour_it_does_not_include(name):
    """The scope must not out-promise the two internal sources.

    The price book sells `Service Call / Trip Minimum` as a flat $165
    "Minimum service call" with no labour attached, and the template's
    own description calls it "Trip minimum (includes travel and
    setup)". A scope reading "...and up to 1 hour of labor" contradicts
    both, and it is the only one of the three the client ever sees — on
    a quote that also bills 2 hours of carpentry on top, so it reads as
    3 hours of attendance for a 2-hour charge.

    Nothing in the repo sources that hour, so the scope is held to what
    the description and the price book actually say.
    """
    scopes = _scopes(_text(name))
    trip = [s for t, s in scopes.items() if "Service Call / Trip Minimum:" in s]
    assert trip, "the Service Call template vanished"
    for scope in trip:
        line = next(ln for ln in scope.split("\\n")
                    if "Service Call / Trip Minimum:" in ln)
        assert "hour" not in line.lower(), (
            f"scope promises labour the price book does not include: {line!r}")


def test_the_in_place_rewrite_matches_the_seed():
    """`SCOPE_FIXES` rewrites templates already saved in a user's browser.

    It is a second copy of the same strings, so it drifts from the seed
    the moment one is edited alone — and a correction applied only to
    the seed would never reach anybody who already has the old data.
    """
    src = _text("index.html")
    block = re.search(r"const SCOPE_FIXES = \[(.*?)\n\];", src, re.S)
    assert block, "SCOPE_FIXES block not found"
    pairs = re.findall(r'\["((?:[^"\\]|\\.)*)", "((?:[^"\\]|\\.)*)"\]',
                       block.group(1))
    assert pairs, "no replacement pairs parsed"
    joined = " ".join(_scopes(src).values())
    missing = [to for _, to in pairs if to not in joined]
    assert not missing, (
        "SCOPE_FIXES rewrites saved data to text the seed no longer uses, "
        f"so the two have drifted: {missing}")


# Every scope wording that has ever been shipped to a browser, oldest
# first. `SCOPE_FIXES` has to carry each of them forward, because
# `index.html:419` is `localStorage.getItem(KEY) || seed()` — saved data
# wins and the seed only runs for a browser that has never loaded the
# app. A user who opened an intermediate version has that version's
# text saved, and only a migration can reach it.
_SHIPPED_TRIP_SCOPES = (
    # Original, with the internal note.
    "- Service Call / Trip Minimum: Minimum service call (Quick Price "
    "List, Oct 17). Master guide baseline says $150.\n"
    "- Handyman / General Carpentry: Punch-list, framing, fixture swaps",
    # What #82 shipped and republished to the live artifact.
    "- Service Call / Trip Minimum: Travel to site, setup, and up to 1 "
    "hour of labor\n"
    "- Handyman / General Carpentry: Punch-list, framing, fixture swaps",
)


def _scope_fixes(src):
    block = re.search(r"const SCOPE_FIXES = \[(.*?)\n\];", src, re.S)
    assert block, "SCOPE_FIXES block not found"
    pairs = re.findall(r'\["((?:[^"\\]|\\.)*)", "((?:[^"\\]|\\.)*)"\]',
                       block.group(1))
    assert pairs, "no replacement pairs parsed"
    # The HTML holds \n as a two-character escape; the saved string has
    # a real newline, which is what the replacement runs against.
    return [(f.replace("\\n", "\n"), t.replace("\\n", "\n"))
            for f, t in pairs]


def _migrate(pairs, scope):
    """`SCOPE_FIXES.reduce((a,[f,t]) => a.split(f).join(t), scope)`."""
    for frm, to in pairs:
        scope = scope.replace(frm, to)
    return scope


@pytest.mark.parametrize("name", _SOURCES)
@pytest.mark.parametrize("saved", _SHIPPED_TRIP_SCOPES)
def test_every_shipped_scope_migrates_off_the_one_hour_promise(name, saved):
    """A correction only the seed carries reaches nobody who already ran it.

    Replacing the one-hour sentence in the seed is not enough: anyone
    who loaded the version that introduced it has it in localStorage,
    and startup prefers that over the seed. `quoteFromTemplate` then
    copies the saved scope onto every new proposal, so the promise
    keeps printing.
    """
    migrated = _migrate(_scope_fixes(_text(name)), saved)
    assert "hour of labor" not in migrated, (
        f"a saved scope still promises an hour after migration: {migrated!r}")
    assert "Painting sheet" not in migrated


def test_the_hosted_build_migrates_templates_it_loads_from_the_cloud():
    """The local pass cannot reach data that arrives after it.

    `hosted.html` runs the rewrite once at startup and then calls
    `connect()`. On the first snapshot `onStore` does `DB = blankDB()`
    and repopulates from the store, so every template it ingests has
    never been through `SCOPE_FIXES` — on the one build that is
    actually deployed and shared. The correction has to run again
    after that ingest.
    """
    src = _text("hosted.html")
    assert "function fixScopes()" in src, "fixScopes() is not defined"
    first_load = re.search(
        r"const ui = DB\.ui; DB = blankDB\(\);(.*?)setSync\(\"Saved\"\); render\(\);",
        src, re.S)
    assert first_load, "onStore's first-snapshot branch not found"
    assert "fixScopes();" in first_load.group(1), (
        "cloud templates are ingested without the scope migration")


def test_the_local_build_has_no_cloud_path_to_miss():
    """index.html keeps the single startup pass: it has no store."""
    src = _text("index.html")
    assert "function fixScopes()" in src and "fixScopes();" in src
    # The word also appears in a comment pointing at the hosted build,
    # so this looks for a definition, not a mention.
    assert "function onStore" not in src, (
        "index.html gained a sync path; it needs the same post-ingest call")


def test_a_later_snapshot_cannot_undo_the_migration():
    """Snapshots arrive cache-first, then server.

    The first-load guard is `fromCache && snap.empty`, so a cached
    *non-empty* snapshot passes it, sets `ready`, and is migrated. The
    server copy then lands in the incremental branch, where
    `putRemote()` swaps the template back to the stored version — which
    still carries the promise. The flush does not catch it either,
    because `lastSent` already matches the server document.

    Driven through the real handler with two synthetic snapshots rather
    than asserted on the source text; removing the incremental
    `fixScopes()` makes this fail with the promise restored.
    """
    sync_api = pytest.importorskip("playwright.sync_api")
    chrome = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    if not pathlib.Path(chrome).exists():
        pytest.skip("bundled Chromium not present")
    page_url = "file://" + str((_HQ / "hosted.html").resolve())
    js = """
    () => {
      const BAD = "- Service Call / Trip Minimum: Travel to site, setup, "
                + "and up to 1 hour of labor";
      const doc = (scope, desc) => ({
        id: "t_x1", metadata: {hasPendingWrites: false},
        data: () => ({id: "x1", name: "Probe", description: desc,
                      scope: scope})});
      const snap = (docs, fromCache) => ({
        empty: docs.length === 0, metadata: {fromCache}, docs,
        forEach: f => docs.forEach(f)});
      onStore(snap([doc(BAD, "v1")], true));      // cached, non-empty
      onStore(snap([doc(BAD, "v2")], false));     // server, edited elsewhere
      return (DB.templates.find(t => t.id === "x1") || {}).scope;
    }
    """
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome,
                                    args=["--no-sandbox"])
        try:
            page = browser.new_page()
            page.goto(page_url)
            page.wait_for_timeout(1500)
            scope = page.evaluate(js)
        finally:
            browser.close()
    assert "hour of labor" not in scope, (
        f"a later snapshot restored the promise: {scope!r}")
    assert "Travel to site and on-site setup" in scope, scope


def _in_page(js):
    """Evaluate js against a loaded hosted.html, or skip."""
    sync_api = pytest.importorskip("playwright.sync_api")
    chrome = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    if not pathlib.Path(chrome).exists():
        pytest.skip("bundled Chromium not present")
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome,
                                    args=["--no-sandbox"])
        try:
            page = browser.new_page()
            page.goto("file://" + str((_HQ / "hosted.html").resolve()))
            page.wait_for_timeout(1500)
            return page.evaluate(js)
        finally:
            browser.close()


def test_a_template_open_in_an_editor_is_migrated_when_it_closes():
    """The one template the incremental branch deliberately skips.

    While a record is open, `onStore` parks the remote copy in
    `heldRemote` rather than swapping it out underneath the editor, and
    `releaseDoc()` applies it on close. So the migration in the
    incremental branch never sees it — the open template is exactly the
    one that slips past. Covered at `putRemote()` instead, which is the
    single point every remote write passes through.
    """
    scope = _in_page("""
    () => {
      const BAD = "- Service Call / Trip Minimum: Travel to site, setup, "
                + "and up to 1 hour of labor";
      const doc = (scope, desc) => ({
        id: "t_e1", metadata: {hasPendingWrites: false},
        data: () => ({id: "e1", name: "Probe", description: desc, scope})});
      const snap = (docs) => ({empty: false, metadata: {fromCache: false},
        docs, forEach: f => docs.forEach(f)});
      onStore(snap([doc("clean placeholder", "v1")]));
      openDocKey = "t_e1";                 // the editor is open
      onStore(snap([doc(BAD, "v2")]));     // held back, not applied
      releaseDoc();                        // applied on close
      return (DB.templates.find(t => t.id === "e1") || {}).scope;
    }
    """)
    assert "hour of labor" not in scope, (
        f"releaseDoc() restored the promise: {scope!r}")


def test_a_restored_backup_is_migrated():
    """`DB = d` replaces everything and bypasses `putRemote` entirely.

    A backup taken while the one-hour wording was live carries it, and
    restoring one is exactly the moment old data re-enters.
    """
    src = _text("index.html")
    restore = re.search(r"DB = d; DB\.ui = DB\.ui \|\|[^;]*;([^\n]*)", src)
    assert restore, "the backup restore path moved"
    assert "fixScopes();" in restore.group(1), (
        "a restored backup is not migrated: " + restore.group(1).strip())


def test_migrating_does_not_count_as_a_local_edit():
    """The cost of correcting data in place, and its over-correction guard.

    `releaseDoc()` applies the other device's version only when nothing
    was edited here, comparing `canon(local)` with `lastSent`. Once
    `putRemote()` rewrites a scope on the way in, the local copy
    differs from the stored document by the correction alone — so a
    genuine remote change to any template that needed migrating was
    being read as a local edit and silently dropped.

    Both directions are checked, because the fix is to ignore the
    migration in that comparison and the risk is ignoring a real edit
    with it: a remote change must survive, and a local change must
    still win.
    """
    out = _in_page("""
    () => {
      const BAD = "- Service Call / Trip Minimum: Travel to site, setup, "
                + "and up to 1 hour of labor";
      const doc = (id, scope, desc) => ({
        id: "t_" + id, metadata: {hasPendingWrites: false},
        data: () => ({id, name: "Probe", description: desc, scope})});
      const snap = d => ({empty: false, metadata: {fromCache: false},
        docs: d, forEach: f => d.forEach(f)});
      const t = id => DB.templates.find(x => x.id === id) || {};
      const out = {};
      onStore(snap([doc("m1", BAD, "v1")]));
      openDocKey = "t_m1";
      onStore(snap([doc("m1", BAD, "v2-remote-edit")]));
      releaseDoc();
      out.remoteDesc = t("m1").description;
      out.remoteScope = t("m1").scope;
      onStore(snap([doc("m2", BAD, "base")]));
      openDocKey = "t_m2";
      t("m2").description = "edited-here";
      onStore(snap([doc("m2", BAD, "remote-v3")]));
      releaseDoc();
      out.localDesc = t("m2").description;
      return out;
    }
    """)
    assert out["remoteDesc"] == "v2-remote-edit", (
        "a remote edit was dropped because the migration looked like a "
        f"local edit: {out['remoteDesc']!r}")
    assert "hour of labor" not in out["remoteScope"], out["remoteScope"]
    assert out["localDesc"] == "edited-here", (
        "a real local edit was overwritten by the held remote copy: "
        f"{out['localDesc']!r}")


def test_a_migrated_template_is_written_back_to_the_store():
    """Correcting DB is not enough; the cloud has to converge.

    `putRemote()` rewrites the scope, but `lastSent` still holds the
    stored document and neither `onStore()` nor `releaseDoc()`
    schedules a write. The startup `fixScopes()` pass cannot cover it
    either: `putRemote` has already corrected the template, so that
    pass sees nothing changed and never calls `save()`. The local copy
    then looks right while every other device keeps the old promise.

    The guard on the other side matters as much: a template that is
    already correct must not schedule a write, or every load churns the
    store. `save()` is observed through its 400ms debounce timer.
    """
    out = _in_page("""
    () => {
      const BAD = "- Service Call / Trip Minimum: Travel to site, setup, "
                + "and up to 1 hour of labor";
      const OK = "- Service Call / Trip Minimum: Travel to site and "
               + "on-site setup";
      const doc = (id, scope) => ({
        id: "t_" + id, metadata: {hasPendingWrites: false},
        data: () => ({id, name: "P", description: "d", scope})});
      const snap = d => ({empty: false, metadata: {fromCache: false},
        docs: d, forEach: f => d.forEach(f)});
      const out = {};
      let n = 0; const realST = window.setTimeout;
      window.setTimeout = function (f, ms) { if (ms === 400) n++;
                                             return realST(f, ms); };
      onStore(snap([doc("s1", BAD)]));
      out.fixedScope = (DB.templates.find(t => t.id === "s1") || {}).scope;
      out.fixedSaves = n;
      n = 0;
      onStore(snap([doc("s2", OK)]));
      out.cleanScope = (DB.templates.find(t => t.id === "s2") || {}).scope;
      out.cleanSaves = n;
      window.setTimeout = realST;
      return out;
    }
    """)
    assert "hour of labor" not in out["fixedScope"], out["fixedScope"]
    assert out["fixedSaves"] > 0, (
        "the scope was corrected locally but no write was scheduled, so "
        "the store keeps the old promise")
    assert "on-site setup" in out["cleanScope"], out["cleanScope"]
    assert out["cleanSaves"] == 0, (
        "an already-correct template scheduled a write; every load would "
        "churn the store")
