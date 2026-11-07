from __future__ import annotations

import os
import shutil
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLES = Path(__file__).parent.parent / "examples"
DEFAULT_MOJO = "/home/lee/code/pm-wt-algo7/.venv/bin/mojo"


def mojo_bin() -> str | None:
    cand = os.environ.get("MOJO") or (DEFAULT_MOJO if Path(DEFAULT_MOJO).exists() else shutil.which("mojo"))
    return cand if cand and Path(cand).exists() else None


def fixture_files() -> list[Path]:
    return sorted(FIXTURES.glob("MA*/*.mojo"))
