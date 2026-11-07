from __future__ import annotations

from mojoanalyzer.engine import analyze_sources


def hits(src: str, rule: str, conf: str = "low") -> list[tuple[int, str]]:
    return [(f.line, f.confidence) for f in analyze_sources([("a.mojo", src)], [rule], conf)]


def test_division_guards() -> None:
    base = (
        "def f(ys: List[Float64], s: Float64) -> Float64:\n    var xs = List[Float64]()\n    for y in ys:\n"
        "        if y > 0.0:\n            xs.append(y)\n    var n = len(xs)\n{g}    return s / Float64(n)\n"
    )
    assert hits(base.format(g=""), "MA201") == [(7, "high")]
    for g in (
        "    if n == 0:\n        return 0.0\n",
        "    if not xs:\n        return 0.0\n",
        "    if len(xs) < 2:\n        return 0.0\n",
        "    debug_assert(n > 0)\n",
    ):
        assert hits(base.format(g=g), "MA201") == [], g


def test_division_validator_call_guard() -> None:
    src = (
        "def f(a: Float64, raw: String) raises -> Float64:\n    var px = atof(raw)\n    if not ok(px):\n"
        "        return 0.0\n    return a / px\n\ndef ok(x: Float64) -> Bool:\n    return x > 0\n"
    )
    assert hits(src, "MA201") == []
    assert hits(src.replace("    if not ok(px):\n        return 0.0\n", ""), "MA201") == [(3, "medium")]


def test_division_index_decode_and_same_predicate() -> None:
    src = (
        "def f(a: List[Int], b: List[Int]) -> Int:\n    var na = len(a)\n    var nb = len(b)\n    var t = 0\n"
        "    for k in range(na * nb):\n        t += k // nb + k % nb\n    return t\n"
    )
    assert hits(src, "MA201") == []
    src2 = (
        "def f(xs: List[Float64]) -> Float64:\n    var n = 0\n    for x in xs:\n        if x > 0.0:\n"
        "            n += 1\n    var s = 0.0\n    for x in xs:\n        if x > 0.0:\n            s += x / Float64(n)\n"
        "    return s\n"
    )
    assert hits(src2, "MA201") == []


def test_int_true_division_only_int_operands() -> None:
    assert hits("def f(a: Int, b: Int) -> Float64:\n    return Float64(a / b)\n", "MA206") == [(2, "high")]
    assert hits("def f(a: Float64, b: Int) -> Float64:\n    return Float64(a / Float64(b))\n", "MA206") == []
    assert hits("def f(a: Int, b: Int) -> Int:\n    return a / b\n", "MA206") == [(2, "low")]


def test_ambiguous_redeclared_type_is_unknown() -> None:
    src = (
        "def f(c: Bool, j: Float64) -> Bool:\n    if c:\n        var x = 0\n        return x > 1\n"
        "    var x = j * 2.0\n    return x == x\n"
    )
    assert [c for _, c in hits(src, "MA204")] == ["low"]


def test_edge_index_requires_unguarded_start() -> None:
    src = (
        "def f(px: List[Float64]) -> Float64:\n    var s = 0.0\n    for i in range(len(px)):\n"
        "        s += px[max(i - 1, 0)]\n    return s\n"
    )
    assert hits(src, "MA213") == []
