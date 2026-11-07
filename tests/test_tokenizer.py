from __future__ import annotations

from mojoanalyzer.tokenizer import K, tokenize


def kinds(src: str) -> list[tuple[str, str]]:
    return [(t.kind.value, t.value) for t in tokenize(src) if t.kind not in (K.NL,)]


def test_nested_quotes_and_prefixes() -> None:
    toks = [t for t in tokenize('x = "a \'b\' \\"c\\"" + r"\\d" + b\'e\'\n') if t.kind is K.STRING]
    assert [t.value for t in toks] == ['"a \'b\' \\"c\\""', 'r"\\d"', "b'e'"]


def test_triple_quoted_docstring_spans_lines() -> None:
    src = 'def f():\n    """doc\n    with # not a comment\n    and "quotes" """\n    return 1\n'
    toks = tokenize(src)
    s = [t for t in toks if t.kind is K.STRING]
    assert len(s) == 1 and s[0].line == 2 and "# not a comment" in s[0].value
    assert not [t for t in toks if t.kind is K.COMMENT]
    assert [t.line for t in toks if t.is_name("return")] == [5]


def test_indent_dedent_balance() -> None:
    src = "def f():\n    if x:\n        y = 1\n\n    # c\n    z = 2\nw = 3\n"
    toks = tokenize(src)
    assert sum(t.kind is K.INDENT for t in toks) == sum(t.kind is K.DEDENT for t in toks) == 2


def test_bracket_continuation_no_newline() -> None:
    src = "x = f(a,\n      b,  # c\n      c)\ny = 1\n"
    toks = tokenize(src)
    assert sum(t.kind is K.NEWLINE for t in toks) == 2
    assert not [t for t in toks if t.kind is K.INDENT]


def test_backslash_continuation() -> None:
    src = "x = 1 + \\\n    2\ny = 3\n"
    assert sum(t.kind is K.NEWLINE for t in tokenize(src)) == 2


def test_numbers_and_ops() -> None:
    vals = [v for k, v in kinds("a = 1_000 + 0x1F + 1e-6 + 2.5 + .5 ** 2 // 3\n") if k in ("NUMBER", "OP")]
    assert vals == ["=", "1_000", "+", "0x1F", "+", "1e-6", "+", "2.5", "+", ".5", "**", "2", "//", "3"]


def test_transfer_and_arrow() -> None:
    vals = [v for k, v in kinds("def f(var x: T) -> T:\n    return x^\n") if k == "OP"]
    assert "->" in vals and "^" in vals


def test_unterminated_string_is_tolerated() -> None:
    toks = tokenize('x = "abc\ny = 2\n')
    assert any(t.is_name("y") for t in toks)


def test_backtick_identifier() -> None:
    toks = tokenize("var x = __mlir_type.`!kgen.pointer<none>`\n")
    assert any(t.kind is K.NAME and t.value.startswith("`") for t in toks)
