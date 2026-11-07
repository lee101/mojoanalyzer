from __future__ import annotations

import json
from pathlib import Path

import pytest

from mojoanalyzer.cli import main
from mojoanalyzer.engine import analyze_sources

SRC = """def f(n: Int) -> List[Int]:
    var xs = List[Int]()
    for i in range(n):
        xs.append(i * i)
    return xs^
"""


def test_text_and_exit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / "a.mojo"
    p.write_text(SRC)
    assert main([str(p), "--fail-on", "low"]) == 1
    out = capsys.readouterr().out
    assert f"{p}:2:5 MA106 low high" in out and "-> List[Int](capacity=n)" in out
    assert main([str(p), "--fail-on", "high"]) == 0


def test_json_select_ignore(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / "a.mojo"
    p.write_text(SRC)
    main([str(tmp_path), "--format", "json", "--select", "MA106"])
    data = json.loads(capsys.readouterr().out)
    assert [d["rule"] for d in data] == ["MA106"] and data[0]["risk"] == "none"
    main([str(tmp_path), "--format", "json", "--ignore", "MA1"])
    assert json.loads(capsys.readouterr().out) == []


def test_inline_suppression() -> None:
    src = SRC.replace("List[Int]()", "List[Int]()  # mojoanalyzer: ignore[MA106]")
    assert analyze_sources([("a.mojo", src)]) == []
    src2 = SRC.replace("List[Int]()", "List[Int]()  # mojoanalyzer: ignore[MA101]")
    assert len(analyze_sources([("a.mojo", src2)])) == 1
    src3 = SRC.replace("List[Int]()", "List[Int]()  # mojoanalyzer: ignore")
    assert analyze_sources([("a.mojo", src3)]) == []
    assert analyze_sources([("a.mojo", "# mojoanalyzer: ignore-file[MA106]\n" + SRC)]) == []


def test_min_confidence_filters() -> None:
    src = "\n".join(
        [
            "def f(xs: List[Int]) -> Int:",
            "    var s = 0",
            "    for i in range(len(xs)):",
            "        for l in range(3):",
            "            s += l",
            "    return s",
            "",
        ]
    )
    assert not [f for f in analyze_sources([("a.mojo", src)], min_confidence="medium") if f.rule == "MA101"]
    assert [f for f in analyze_sources([("a.mojo", src)], min_confidence="low") if f.rule == "MA101"]


def test_list_and_explain(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--list-rules"]) == 0
    assert "MA114" in capsys.readouterr().out
    assert main(["--explain", "MA112"]) == 0
    assert "FP rounding" in capsys.readouterr().out
