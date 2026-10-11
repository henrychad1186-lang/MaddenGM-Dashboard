"""The Posit Connect Cloud publish config must ship what app.py needs.

Posit Publisher generated a file list of app.py and requirements.txt
alone, and the deployment record shows that is what went up: the app
then stops at its first `from src... import`. Regenerating the config
from the Publisher UI can drop these again, so the list is pinned here.
"""

import glob
import pathlib

import pytest

tomllib = pytest.importorskip("tomllib", reason="tomllib is Python 3.11+")

_CONFIGS = [p for p in glob.glob(".posit/publish/*.toml")
            if tomllib.loads(pathlib.Path(p).read_text()).get("type")
            == "python-streamlit"]

# Read at startup and shipped in the repo; everything else in data/ is
# created at runtime.
_NEEDED = ["/app.py", "/requirements.txt", "/src",
           "/data/game_logs.csv", "/data/packers_roster.csv"]


@pytest.mark.parametrize("path", _CONFIGS)
def test_streamlit_publish_ships_the_app_package_and_data(path):
    files = tomllib.loads(pathlib.Path(path).read_text())["files"]
    missing = [f for f in _NEEDED if f not in files]
    assert not missing, f"{path} would deploy without {missing}"


def test_there_is_a_streamlit_publish_config():
    assert _CONFIGS, "no python-streamlit config under .posit/publish"
