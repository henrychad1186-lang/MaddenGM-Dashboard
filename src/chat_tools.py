"""
Tools the GM Chat can call mid-answer.

The chat's system prompt carries a text snapshot of the roster, cap and
game log, which is enough to discuss the team but not to price a trade:
"what would it take to get Justin Jefferson?" needs the trade engine's
actual numbers, and a model reasoning from the snapshot will estimate
them. These tools let it ask the same functions the Trade Machine tab
calls instead.

Every tool is read-only. Each returns a JSON-serialisable dict; a tool
that can't answer returns {"error": ...} rather than raising, so a bad
name or a stale roster becomes something the model can say back to the
user instead of a crashed chat.
"""

from dataclasses import dataclass, field

import pandas as pd

from src import roster as roster_mod
from src import roster_analyzer
from src import trade_engine

MAX_RESULTS = 12


@dataclass
class ToolContext:
    """What the tools read. Built by the caller from the same state the
    other tabs use, so session additions from the AI GM tab count too."""
    team: str
    rosters: pd.DataFrame          # all teams, trade-engine shape
    extra_players: "list[dict]" = field(default_factory=list)


TOOL_DEFINITIONS = [
    {
        "name": "lookup_player",
        "description": (
            "Look up a player on any team in the trade data by name (partial, "
            "case-insensitive). Returns ratings, age, dev trait, team, trade "
            "value, and - for the user's own players - the cut/keep/trade "
            "verdict with its reason and the cap savings and dead-cap penalty "
            "if released or traded."),
        "eager_input_streaming": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Player name or part of it, e.g. 'Jefferson' or 'J. Love'."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "list_trade_targets",
        "description": (
            "List players on other teams (the ones the trade engine models) at "
            "a position, highest trade value first, optionally filtered by "
            "minimum OVR and maximum age."),
        "eager_input_streaming": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "position": {"type": "string", "description": "Madden position, e.g. EDGE, WR, CB, QB, MLB."},
                "min_ovr": {"type": "integer", "description": "Only players at or above this OVR."},
                "max_age": {"type": "integer", "description": "Only players at or below this age."},
            },
            "required": ["position"],
        },
    },
    {
        "name": "evaluate_trade",
        "description": (
            "Run a proposed trade through the trade engine. 'offer' is the "
            "user's players going out, 'request' is the players coming back. "
            "Returns the verdict (accepted / lean accept / declined), each "
            "side's total trade value, and a draft-pick sweetener suggestion "
            "when the offer falls short."),
        "eager_input_streaming": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "offer": {"type": "array", "items": {"type": "string"}, "description": "Names of the user's players offered."},
                "request": {"type": "array", "items": {"type": "string"}, "description": "Names of the players requested."},
            },
            "required": ["offer", "request"],
        },
    },
    {
        "name": "find_trade_partners",
        "description": (
            "For one of the user's players, rank the other teams by interest "
            "in acquiring him, with the reason. 'best_offer' is that team's "
            "highest-trade-value non-QB player, not what they would give for "
            "him - price any actual swap with evaluate_trade."),
        "eager_input_streaming": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the user's player to shop."},
            },
            "required": ["name"],
        },
    },
]


def _jsonable(v):
    # NaN first: it is a float, and json.dumps would emit a bare NaN,
    # which isn't JSON. CPU players have no SPD/ACC/... so it's common.
    if isinstance(v, float) and v != v:
        return None
    if isinstance(v, (int, float, str, bool)) or v is None:
        return v
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "item"):
        return v.item()
    return str(v)


def _record(row) -> dict:
    return {k: _jsonable(v) for k, v in dict(row).items()}


def _all_players(ctx: ToolContext) -> pd.DataFrame:
    if ctx.extra_players:
        return pd.concat([ctx.rosters, pd.DataFrame(ctx.extra_players)],
                         ignore_index=True)
    return ctx.rosters


def _match(ctx: ToolContext, name: str) -> "tuple[pd.DataFrame, str | None]":
    """Rows whose name matches, exact (case-insensitive) first, else substring.
    Returns (rows, error)."""
    df = _all_players(ctx)
    q = name.strip().lower()
    if not q:
        return df.iloc[0:0], "Empty player name."
    names = df["Name"].astype(str).str.lower()
    exact = df[names == q]
    if len(exact):
        return exact, None
    part = df[names.str.contains(q, regex=False)]
    if part.empty:
        # "Justin Jefferson" vs stored "J. Jefferson": try the last name.
        last = q.split()[-1]
        part = df[names.str.contains(last, regex=False)] if len(last) > 2 else part
    if part.empty:
        return part, f"No player matching '{name}' in the trade data."
    return part, None


def _one(ctx: ToolContext, name: str) -> "tuple[dict | None, str | None]":
    rows, err = _match(ctx, name)
    if err:
        return None, err
    if len(rows) > 1:
        options = ", ".join(f"{r['Name']} ({r['Team']} {r['Pos']})"
                            for _, r in rows.head(MAX_RESULTS).iterrows())
        return None, f"'{name}' matches several players: {options}. Use a fuller name."
    return _record(rows.iloc[0]), None


def lookup_player(ctx: ToolContext, name: str) -> dict:
    rows, err = _match(ctx, name)
    if err:
        return {"error": err}
    verdicts = {}
    if (rows["Team"] == ctx.team).any():
        verdicts = {v["Name"]: v for v in
                    roster_analyzer.analyze_roster(ctx.team, ctx.extra_players)}
    out = []
    for _, row in rows.head(MAX_RESULTS).iterrows():
        p = _record(row)
        p.pop("_id", None)
        p["trade_value"] = round(trade_engine.get_trade_value(p), 1)
        v = verdicts.get(p["Name"]) if p.get("Team") == ctx.team else None
        if v:
            p["verdict"] = v["Verdict"]
            p["verdict_reason"] = v["Reason"]
            p["cap_savings_if_moved_M"] = v["Savings"]
            p["dead_cap_if_moved_M"] = v["Penalty"]
        out.append(p)
    return {"players": out, "matches": len(rows)}


def list_trade_targets(ctx: ToolContext, position: str,
                       min_ovr: "int | None" = None,
                       max_age: "int | None" = None) -> dict:
    df = _all_players(ctx)
    pos = roster_mod.normalize_position(position.strip().upper())
    others = df[df["Team"] != ctx.team]
    cands = others[others["Pos"].astype(str).apply(roster_mod.normalize_position) == pos]
    if min_ovr is not None:
        cands = cands[pd.to_numeric(cands["OVR"], errors="coerce") >= min_ovr]
    if max_age is not None:
        cands = cands[pd.to_numeric(cands["Age"], errors="coerce") <= max_age]
    teams = sorted(others["Team"].dropna().unique().tolist())
    if cands.empty:
        return {"targets": [], "teams_modeled": teams,
                "note": f"No {pos} on {', '.join(teams)} matches those filters."}
    recs = [_record(r) for _, r in cands.iterrows()]
    for p in recs:
        p["trade_value"] = round(trade_engine.get_trade_value(p), 1)
    recs.sort(key=lambda p: p["trade_value"], reverse=True)
    keep = ("Name", "Team", "Pos", "OVR", "Age", "Dev", "trade_value")
    return {"targets": [{k: p.get(k) for k in keep} for p in recs[:MAX_RESULTS]],
            "teams_modeled": teams}


def evaluate_trade(ctx: ToolContext, offer: "list[str]", request: "list[str]") -> dict:
    offered, requested, errors = [], [], []
    for names, side, want_own in ((offer, offered, True), (request, requested, False)):
        for n in names:
            p, err = _one(ctx, n)
            if err:
                errors.append(err)
            elif want_own and p.get("Team") != ctx.team:
                errors.append(f"{p['Name']} plays for {p.get('Team')}, not {ctx.team}; "
                              "only your own players can be offered.")
            elif not want_own and p.get("Team") == ctx.team:
                errors.append(f"{p['Name']} is already on {ctx.team}.")
            else:
                side.append(p)
    if errors:
        return {"error": " ".join(errors)}
    if not offered or not requested:
        return {"error": "A trade needs at least one player on each side."}
    res = trade_engine.evaluate_trade(offered, requested)
    res.pop("verdict_color", None)
    res["offered"] = [f"{p['Name']} ({p['Pos']}, {p['OVR']} OVR)" for p in offered]
    res["requested"] = [f"{p['Name']} ({p['Team']} {p['Pos']}, {p['OVR']} OVR)" for p in requested]
    return res


def find_trade_partners(ctx: ToolContext, name: str) -> dict:
    p, err = _one(ctx, name)
    if err:
        return {"error": err}
    if p.get("Team") != ctx.team:
        return {"error": f"{p['Name']} plays for {p.get('Team')}; pick one of your own players."}
    partners = trade_engine.find_trade_partners(p, user_team=ctx.team)
    return {"player": f"{p['Name']} ({p['Pos']}, {p['OVR']} OVR)",
            "partners": [{k: _jsonable(v) for k, v in d.items()} for d in partners]}


_TOOLS = {
    "lookup_player": (lookup_player, {"name": str}, set()),
    "list_trade_targets": (list_trade_targets,
                           {"position": str, "min_ovr": int, "max_age": int},
                           {"min_ovr", "max_age"}),
    "evaluate_trade": (evaluate_trade, {"offer": list, "request": list}, set()),
    "find_trade_partners": (find_trade_partners, {"name": str}, set()),
}


def validate(name: str, args) -> "str | None":
    """Check a tool call's input before running it. Inputs stream eagerly,
    so the API doesn't validate them for us: a truncated or malformed
    call can arrive as a partial dict. Returns an error string or None."""
    if name not in _TOOLS:
        return f"Unknown tool '{name}'."
    if not isinstance(args, dict):
        return "Tool input must be a JSON object."
    _, types, optional = _TOOLS[name]
    for key in args:
        if key not in types:
            return f"Unexpected argument '{key}'."
    for key, typ in types.items():
        if key not in args or args[key] is None:
            if key in optional:
                continue
            return f"Missing required argument '{key}'."
        val = args[key]
        if typ is int:
            if isinstance(val, bool) or not isinstance(val, int):
                return f"'{key}' must be an integer."
        elif typ is list:
            if not isinstance(val, list) or not all(isinstance(x, str) and x.strip() for x in val):
                return f"'{key}' must be a list of player names."
        elif not isinstance(val, typ) or not val.strip():
            return f"'{key}' must be a non-empty string."
    return None


def run(ctx: ToolContext, name: str, args) -> dict:
    """Validate and execute one tool call. Never raises."""
    err = validate(name, args)
    if err:
        return {"error": err}
    fn = _TOOLS[name][0]
    try:
        return fn(ctx, **{k: v for k, v in args.items() if v is not None})
    except Exception as exc:  # noqa: BLE001 - surfaced to the model, not the user's screen
        return {"error": f"{name} failed: {exc}"}


def describe(name: str, args) -> str:
    """One-line human label for a tool call, shown in the chat."""
    a = args if isinstance(args, dict) else {}
    if name == "lookup_player":
        return f"looked up {a.get('name', '?')}"
    if name == "list_trade_targets":
        return f"listed {a.get('position', '?')} trade targets"
    if name == "evaluate_trade":
        return (f"ran the trade engine: {', '.join(a.get('offer') or [])} for "
                f"{', '.join(a.get('request') or [])}")
    if name == "find_trade_partners":
        return f"found trade partners for {a.get('name', '?')}"
    return name
