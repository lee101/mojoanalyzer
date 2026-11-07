from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from .conftest import EXAMPLES, fixture_files, mojo_bin

MOJO = mojo_bin()
FILES = fixture_files() + sorted(EXAMPLES.glob("*/*.mojo"))
pytestmark = [pytest.mark.compile, pytest.mark.skipif(MOJO is None, reason="mojo toolchain not found")]


@pytest.fixture(scope="module")
def compiled(tmp_path_factory: pytest.TempPathFactory) -> dict[Path, tuple[int, str]]:
    out = tmp_path_factory.mktemp("bin")
    mojo = MOJO or "mojo"

    def build(p: Path) -> tuple[Path, tuple[int, str]]:
        r = subprocess.run(
            [mojo, "build", "-o", str(out / f"{p.parent.name}_{p.stem}"), str(p)],
            capture_output=True,
            check=False,
            text=True,
            timeout=600,
        )
        errs = "\n".join(ln for ln in (r.stdout + r.stderr).splitlines() if "error" in ln)
        return p, (r.returncode, errs)

    with ThreadPoolExecutor(max_workers=8) as ex:
        return dict(ex.map(build, FILES))


@pytest.mark.parametrize("path", FILES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_compiles(path: Path, compiled: dict[Path, tuple[int, str]]) -> None:
    rc, errs = compiled[path]
    assert rc == 0, errs
