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
