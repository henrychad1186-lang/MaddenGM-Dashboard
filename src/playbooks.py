"""
Madden 27 playbooks and schemes, and the franchise's chosen setup.

The built-in lists are a **seed, not a closed catalog.** The 32 team
books are safe — they are the league, and it does not change between
patches. The alternate books and the scheme names are drawn from
community playbook databases (Huddle.gg, Civil.gg, Madden School) and
are known to be incomplete: Huddle.gg counts 17 alternate offensive
books and only 12 could be named from those sources, the defensive
alternates were never enumerated anywhere, and the sources disagree on
spelling ("Run N Gun" / "Run n Gun" / "Run 'N' Gun").

So the list is deliberately open. Anything the user types is kept and
offered back alongside the built-ins, which means an EA patch or a
name this module got wrong is a thing the user fixes in ten seconds
rather than a wrong answer baked into the app. `CATALOGUE_NOTE` is
rendered next to the pickers so the provenance is on screen rather
than buried here.
"""

import json
import os

# The league. Playbook names in Madden are the full team name.
TEAM_PLAYBOOKS = [
    "Arizona Cardinals", "Atlanta Falcons", "Baltimore Ravens",
    "Buffalo Bills", "Carolina Panthers", "Chicago Bears",
    "Cincinnati Bengals", "Cleveland Browns", "Dallas Cowboys",
    "Denver Broncos", "Detroit Lions", "Green Bay Packers",
    "Houston Texans", "Indianapolis Colts", "Jacksonville Jaguars",
    "Kansas City Chiefs", "Las Vegas Raiders", "Los Angeles Chargers",
    "Los Angeles Rams", "Miami Dolphins", "Minnesota Vikings",
    "New England Patriots", "New Orleans Saints", "New York Giants",
    "New York Jets", "Philadelphia Eagles", "Pittsburgh Steelers",
    "San Francisco 49ers", "Seattle Seahawks", "Tampa Bay Buccaneers",
    "Tennessee Titans", "Washington Commanders",
]

# Named in community databases for Madden 27. Huddle.gg counts 17
# alternate offensive books; these are the ones the sources actually
# spelled out, so five or so are missing.
ALTERNATE_OFFENSE = [
    "Air Raid", "Air Raid Classic", "Balanced", "Pistol",
    "Run and Shoot", "Run 'N' Gun", "Shotgun", "Shotgun Classic",
    "Singleback", "Spread", "Spread Classic", "West Coast",
]

# Thinner still. No source enumerated the defensive alternates; these
# are the three that were named outright.
ALTERNATE_DEFENSE = ["3-4", "4-3", "Multiple D"]

# Franchise schemes are a separate concept from playbooks and no source
# listed them in full — one article's title implies ten. These are the
# names that appeared; expect to add to them.
OFFENSIVE_SCHEMES = [
    "Air Raid", "Pistol", "Run and Shoot", "Spread", "Vertical",
    "West Coast",
]
DEFENSIVE_SCHEMES = ["3-4", "4-3", "46", "Multiple D"]

CATALOGUE_NOTE = (
    "Team books are the 32 NFL teams. The alternate books and scheme "
    "names come from community playbook databases and are **known to "
    "be incomplete** — Huddle.gg counts 17 alternate offensive books "
    "and 12 are listed here. Anything you type is saved and offered "
    "next time, so add what's missing."
)

OTHER = "Other — type it below"

SETUP_JSON = os.path.join("data", "franchise_setup.json")

_FIELDS = ("off_playbook", "off_scheme", "def_playbook", "def_scheme")


def blank_setup() -> dict:
    """An unset franchise setup: every field empty, nothing invented."""
    return {field: "" for field in _FIELDS}


def load_setup(path: str = SETUP_JSON) -> dict:
    """The saved setup, or a blank one.

    A missing or unreadable file reads as "nothing chosen yet" rather
    than raising — the form exists to get the user out of that state,
    so it must open.
    """
    try:
        with open(path) as handle:
            saved = json.load(handle)
    except (OSError, ValueError):
        return blank_setup()
    if not isinstance(saved, dict):
        return blank_setup()
    out = blank_setup()
    for field in _FIELDS:
        value = saved.get(field)
        if isinstance(value, str):
            out[field] = value.strip()
    return out


def save_setup(setup: dict, path: str = SETUP_JSON) -> "tuple[bool, str]":
    """Write the setup atomically. Returns (ok, message).

    Atomic for the same reason `dynasty.save_history` is: a crash
    partway leaves truncated JSON, which `load_setup` reads as nothing
    chosen — silently discarding what the user picked.
    """
    cleaned = blank_setup()
    for field in _FIELDS:
        value = setup.get(field, "")
        cleaned[field] = value.strip() if isinstance(value, str) else ""

    directory = os.path.dirname(os.path.abspath(path)) or "."
    tmp = f"{path}.tmp"
    try:
        os.makedirs(directory, exist_ok=True)
        with open(tmp, "w") as handle:
            json.dump(cleaned, handle, indent=2)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False, ("Could not save the franchise setup — the "
                       "filesystem is read-only.")
    return True, "Saved."


def options(builtin: "list[str]", *extras) -> "list[str]":
    """The built-in names plus anything the user has already used.

    Sorted, de-duplicated and case-insensitive on the duplicate check,
    so a book typed as "west coast" does not sit next to "West Coast"
    as though they were different books. The built-in spelling wins,
    because the sources disagree and one of them has to.
    """
    seen = {name.casefold(): name for name in reversed(builtin)}
    for extra in extras:
        for name in extra or ():
            if not isinstance(name, str):
                continue
            name = name.strip()
            if name and name.casefold() not in seen:
                seen[name.casefold()] = name
    return sorted(seen.values(), key=str.casefold)
