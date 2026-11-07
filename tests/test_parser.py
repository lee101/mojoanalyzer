from __future__ import annotations

from mojoanalyzer.expr import BinOp, Call, Sub, Transfer, parse_expr, unparse
from mojoanalyzer.parser import parse
from mojoanalyzer.tokenizer import tokenize

SRC = '''"""module doc"""
from std.algorithm import vectorize

comptime N = 16
comptime V = SIMD[DType.float32, 4]


@fieldwise_init
struct P(Copyable, Movable):
    var x: Float64
    var ys: List[Int]

    def norm(self) -> Float64:
        return self.x


@always_inline
def f[w: Int](mut a: List[Float32], var b: List[Float32], out c: Int, ref d: P) raises -> Int:
    """doc"""
    comptime for i in range(4):
        a[i] = 0
    @parameter
    def g(k: Int) {mut a}:
        pass
    for ref x in a:
        x += 1
    if True: return 1
    var s = a[0:2]; var t = 3
    return len(b) + w


def main():
    pass
'''


def kinds(mod):
    return [(s.kind, s.line) for s in mod.walk()]


def test_structure() -> None:
    mod = parse(SRC)
    top = [(s.kind, s.line) for s in mod.body]
    assert top == [
        ("docstring", 1),
        ("from", 2),
        ("comptime", 4),
        ("comptime", 5),
        ("struct", 9),
        ("def", 18),
        ("def", 32),
    ]
    st = mod.body[4]
    assert st.decorators[0].text() == "@ fieldwise_init"
    assert [s.kind for s in st.body] == ["var", "var", "def"]
    assert st.body[2].body[0].kind == "return"


def test_def_signature() -> None:
    f = parse(SRC).body[5]
    assert f.has_decorator("always_inline")
    info = f.fn
    assert info is not None and info.name == "f" and info.raises and info.ret == "Int"
    assert [(p.name, p.convention, p.type) for p in info.params] == [
        ("a", "mut", "List[Float32]"),
        ("b", "var", "List[Float32]"),
        ("c", "out", "Int"),
        ("d", "ref", "P"),
    ]
    assert [(p.name, p.type) for p in info.cparams] == [("w", "Int")]


def test_body_kinds() -> None:
    f = parse(SRC).body[5]
    ks = [s.kind for s in f.body]
    assert ks == ["docstring", "for", "def", "for", "if", "var", "var", "return"]
    assert f.body[1].comptime and f.body[1].loop is not None and f.body[1].loop[0] == ["i"]
    assert f.body[2].has_decorator("parameter") and f.body[2].fn is not None and f.body[2].fn.captures == ["a"]
    assert f.body[3].loop is not None and f.body[3].loop[0] == ["x"]
    assert f.body[4].body[0].kind == "return"
    assert f.body[5].decl is not None and f.body[5].decl[0] == ["s"]


def test_decl_named_out() -> None:
    s = parse("def f():\n    var out = List[Int]()\n").body[0].body[0]
    assert s.decl is not None and s.decl[0] == ["out"]


def test_continuation_statement() -> None:
    mod = parse("def f():\n    var x = g(1,\n          2)\n    y = x\n")
    assert [(s.kind, s.line) for s in mod.body[0].body] == [("var", 2), ("assign", 4)]


def test_expr_roundtrip() -> None:
    for src in [
        "a[i * m + j] + b.c(d, k=2)",
        "x if c else -y",
        "not a in b and c is not d",
        "p.unsafe_load[width=w](i) * k",
        "s[byte=0:3]",
        "(a + b) * c",
        "a ** -2",
    ]:
        n = parse_expr(tokenize(src + "\n"))
        assert n is not None, src
        assert unparse(parse_expr(tokenize(unparse(n) + "\n"))) == unparse(n)


def test_transfer_vs_xor() -> None:
    a = parse_expr(tokenize("f(x^, y)\n"))
    assert isinstance(a, Call) and isinstance(a.args[0], Transfer)
    b = parse_expr(tokenize("x ^ y\n"))
    assert isinstance(b, BinOp) and b.op == "^"


def test_subscript_kw() -> None:
    n = parse_expr(tokenize("p.unsafe_load[width=8](i)\n"))
    assert isinstance(n, Call) and isinstance(n.func, Sub) and n.func.kw[0][0] == "width"


def test_parses_whole_predictionmojo_shape() -> None:
    src = "\n".join(
        [
            "struct S:",
            "    def m(self):",
            "        while True:",
            "            try:",
            "                pass",
            "            except e:",
            "                break",
            "",
        ]
    )
    assert [s.kind for s in parse(src).walk()] == ["struct", "def", "while", "try", "pass", "except", "break"]
