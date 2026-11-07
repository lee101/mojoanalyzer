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


DIV = """def mean(xs: List[Float64]) -> Float64:
    var s = 0.0
    var k = 0
    for x in xs:
        if x > 0.0:
            s += x
            k += 1
    return s / Float64(k)
"""


def test_explain_verbose_and_json_why(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / "a.mojo"
    p.write_text(DIV)
    main([str(p), "--select", "MA201", "--fail-on", "never"])
    out = capsys.readouterr().out
    assert out.count("\n") == 1 and "MA201 medium high" in out and "why:" not in out
    main([str(p), "--select", "MA201", "--fail-on", "never", "--explain"])
    assert "\n    why: " in capsys.readouterr().out
    main(["--explain", str(p), "--select", "MA201", "--fail-on", "never"])
    assert "\n    why: " in capsys.readouterr().out
    main([str(p), "--select", "MA201", "--format", "json"])
    d = json.loads(capsys.readouterr().out)[0]
    assert d["rule"] == "MA201" and "0 silently" not in d["why"] and "NaN" in d["why"]


def test_rule_option_strict_float_eq(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from mojoanalyzer.rules import BY_ID

    p = tmp_path / "a.mojo"
    p.write_text("def f(a: Float64, b: Float64) -> Bool:\n    var w = a * b\n    return w == 1.0\n")
    main([str(p), "--select", "MA203", "--min-confidence", "low", "--format", "json"])
    assert json.loads(capsys.readouterr().out) == []
    old = BY_ID["MA203"].options
    try:
        main(
            [
                str(p),
                "--select",
                "MA203",
                "--min-confidence",
                "low",
                "--format",
                "json",
                "--rule-option",
                "MA203.strict=1",
            ]
        )
        assert [d["rule"] for d in json.loads(capsys.readouterr().out)] == ["MA203"]
    finally:
        BY_ID["MA203"].options = old
    assert main(["--explain", "MA201"]) == 0
    assert "why:" in capsys.readouterr().out
