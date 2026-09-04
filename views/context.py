"""
The bundle of state every tab renders against.

Each tab used to read module-level globals (`df`, `MY_TEAM`,
`AI_GM_EXTRA`, `EFFECTIVE_TRADE_ROSTERS`) that `app.py` happened to have
defined further up the file. Passing them explicitly makes each tab's
inputs obvious from its signature and lets one be rendered on its own.
"""

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class AppContext:
    """Everything a tab needs, assembled once per rerun by `app.py`."""

    #: Game log after the sidebar's result/playbook/window filters.
    df: pd.DataFrame

    #: The franchise being managed, from the sidebar team selector.
    my_team: str

    #: Players added this session through the AI GM Assistant. Session
    #: scoped on purpose — never merged into the module-level rosters —
    #: so one visitor's additions stay out of everyone else's view.
    extra_players: "list[dict]" = field(default_factory=list)

    #: Base trade rosters: the roster CSV plus the CPU demo teams.
    trade_rosters: pd.DataFrame = field(default_factory=pd.DataFrame)

    #: `trade_rosters` with this session's AI GM additions appended.
    effective_trade_rosters: pd.DataFrame = field(default_factory=pd.DataFrame)
