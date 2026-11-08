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


HOT = """def f(xs: List[Float64], k: Int) -> Float64:
    var s = 0.0
    for i in range(len(xs)):
        var w = List[Float64]()
        for j in range(k):
            w.append(xs[j])
        s += w[0]
    return s


def g(n: Int) -> List[Int]:
    var ys = List[Int]()
    for i in range(n):
        ys.append(i)
    return ys^
"""


def test_llm_format_dedupe_and_top(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / "h.mojo"
    p.write_text(SRC.replace("def f(", "def f2(") + "\n\n" + SRC + "\n\n" + HOT)
    main([str(p), "--format", "llm", "--fail-on", "never", "--min-confidence", "low"])
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("mojoanalyzer ") and "MA106:" in out[0]
    assert any(ln.startswith(" L") and " MA301 " in ln and " -> " in ln for ln in out)
    main([str(p), "--format", "llm", "--top", "1", "--fail-on", "never", "--min-confidence", "low"])
    top = capsys.readouterr().out.splitlines()
    assert "top 1" in top[0] and len([ln for ln in top if ln.startswith(" L")]) == 1


def test_llm_merges_lines_in_one_function() -> None:
    from mojoanalyzer.core import Finding
    from mojoanalyzer.report import llm

    fs = [Finding("a.mojo", ln, 0, "MA122", "low", "high", "none", "m", "s", scope="f") for ln in (3, 9)]
    assert " L3,L9 MA122 m -> s" in llm(fs, 1)


def test_hot_only_and_sarif(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / "h.mojo"
    p.write_text(HOT)
    main([str(p), "--format", "json", "--fail-on", "never", "--min-confidence", "low"])
    allf = json.loads(capsys.readouterr().out)
    assert {d["rule"] for d in allf} >= {"MA301", "MA106"}
    assert all("hot" in d for d in allf)
    main([str(p), "--format", "json", "--hot-only", "--fail-on", "never", "--min-confidence", "low"])
    hot = json.loads(capsys.readouterr().out)
    assert hot and all(d["hot"] > 0 for d in hot) and len(hot) < len(allf)
    main([str(p), "--format", "sarif", "--fail-on", "never"])
    doc = json.loads(capsys.readouterr().out)
    assert doc["version"] == "2.1.0" and doc["runs"][0]["results"][0]["ruleId"].startswith("MA")


def test_hot_weighting_called_from_loop() -> None:
    src = """def leaf(xs: List[Int]) -> Int:
    var t = 0
    for i in range(len(xs)):
        t += xs[i] // 4
    return t


def driver(xs: List[Int]) -> Int:
    var s = 0
    for r in range(10):
        s += leaf(xs)
    return s
"""
    fs = [f for f in analyze_sources([("a.mojo", src)]) if f.rule == "MA122"]
    assert fs and fs[0].hot == 2 and fs[0].scope == "leaf"
