from __future__ import annotations

import os
from pathlib import Path

import pytest

from mojoanalyzer.engine import analyze_sources
from mojoanalyzer.rules import BY_ID

from .conftest import fixture_files

FILES = fixture_files()
UPDATE = os.environ.get("UPDATE_GOLDEN") == "1"


def run(path: Path) -> list[str]:
    found = analyze_sources([(path.name, path.read_text())], min_confidence="low")
    return [f"{f.line}:{f.col + 1} {f.rule} {f.severity} {f.confidence}" for f in found]


@pytest.mark.parametrize("path", FILES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_golden(path: Path) -> None:
    got = run(path)
    golden = path.with_suffix(".expected")
    if UPDATE or not golden.exists():
        golden.write_text("".join(f"{g}\n" for g in got))
    assert got == golden.read_text().splitlines()


@pytest.mark.parametrize("path", FILES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_polarity(path: Path) -> None:
    rule = path.parent.name
    hits = [g for g in run(path) if g.split()[1] == rule]
    if path.name.startswith("positive"):
        assert hits, f"{rule} positive fixture produced no {rule} finding"
    else:
        assert not hits, f"{rule} false positive(s): {hits}"


def test_every_rule_has_fixtures() -> None:
    for rid in BY_ID:
        d = FILES[0].parent.parent / rid
        assert list(d.glob("positive*.mojo")), rid
        assert list(d.glob("negative*.mojo")), rid


def test_rule_metadata() -> None:
    from mojoanalyzer.core import CONFIDENCES, RISKS, SEVERITIES

    for rid, r in BY_ID.items():
        assert r.id == rid and r.name and r.__doc__ and r.bad and r.good
        assert r.severity in SEVERITIES and r.confidence in CONFIDENCES and r.risk in RISKS
