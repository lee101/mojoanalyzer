from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from .tokenizer import K, Token


@dataclass(slots=True)
class Node:
    tok: Token

    @property
    def line(self) -> int:
        return self.tok.line

    @property
    def col(self) -> int:
        return self.tok.col

    def children(self) -> list[Node]:
        return []


@dataclass(slots=True)
class Name(Node):
    id: str


@dataclass(slots=True)
class Num(Node):
    text: str

    @property
    def is_float(self) -> bool:
        t = self.text.lower()
        return not t.startswith(("0x", "0b", "0o")) and ("." in t or "e" in t)

    def int_value(self) -> int | None:
        try:
            return int(self.text.replace("_", ""), 0)
        except ValueError:
            return None


@dataclass(slots=True)
class Str(Node):
    text: str


@dataclass(slots=True)
class Attr(Node):
    obj: Node
    attr: str

    def children(self) -> list[Node]:
        return [self.obj]


@dataclass(slots=True)
class Sub(Node):
    obj: Node
    index: list[Node]
    kw: list[tuple[str, Node]] = field(default_factory=list)

    def children(self) -> list[Node]:
        return [self.obj, *self.index, *(v for _, v in self.kw)]


@dataclass(slots=True)
class Call(Node):
    func: Node
    args: list[Node]
    kw: list[tuple[str, Node]] = field(default_factory=list)

    def children(self) -> list[Node]:
        return [self.func, *self.args, *(v for _, v in self.kw)]


@dataclass(slots=True)
class BinOp(Node):
    op: str
    left: Node
    right: Node

    def children(self) -> list[Node]:
        return [self.left, self.right]


@dataclass(slots=True)
class Unary(Node):
    op: str
    operand: Node

    def children(self) -> list[Node]:
        return [self.operand]


@dataclass(slots=True)
class Transfer(Node):
    operand: Node

    def children(self) -> list[Node]:
        return [self.operand]


@dataclass(slots=True)
class IfExp(Node):
    cond: Node
    then: Node
    other: Node

    def children(self) -> list[Node]:
        return [self.cond, self.then, self.other]


@dataclass(slots=True)
class Seq(Node):
    kind: str
    items: list[Node]

    def children(self) -> list[Node]:
        return list(self.items)


@dataclass(slots=True)
class Other(Node):
    items: list[Node] = field(default_factory=list)
    src: str = ""

    def children(self) -> list[Node]:
        return list(self.items)


def walk(n: Node | None) -> Iterator[Node]:
    if n is None:
        return
    stack = [n]
    while stack:
        x = stack.pop()
        yield x
        stack.extend(reversed(x.children()))


CMP = {"<", ">", "<=", ">=", "==", "!=", "in", "is", "not in", "is not"}
BIN_PREC = [
    ({"or"}, 1),
    ({"and"}, 2),
    (CMP, 4),
    ({"|"}, 5),
    ({"^"}, 6),
    ({"&"}, 7),
    ({"<<", ">>"}, 8),
    ({"+", "-"}, 9),
    ({"*", "/", "//", "%", "@"}, 10),
]
PREC = {op: p for ops, p in BIN_PREC for op in ops}
STOP_AFTER_CARET = {")", "]", "}", ",", ":", "=", ";", "."}


class ParseError(Exception):
    pass


class ExprParser:
    def __init__(self, toks: list[Token]) -> None:
        self.t = [x for x in toks if x.kind not in (K.COMMENT, K.NL, K.NEWLINE, K.INDENT, K.DEDENT, K.END)]
        self.i = 0

    def peek(self, k: int = 0) -> Token | None:
        j = self.i + k
        return self.t[j] if j < len(self.t) else None

    def next(self) -> Token:
        if self.i >= len(self.t):
            raise ParseError("eof")
        tok = self.t[self.i]
        self.i += 1
        return tok

    def expect(self, v: str) -> Token:
        tok = self.next()
        if tok.value != v:
            raise ParseError(f"expected {v} got {tok.value}")
        return tok

    def at_op(self, *vals: str) -> bool:
        p = self.peek()
        return p is not None and p.kind is K.OP and p.value in vals

    def at_name(self, v: str) -> bool:
        p = self.peek()
        return p is not None and p.is_name(v)

    def at_end(self) -> bool:
        return self.i >= len(self.t)

    def parse_tuple(self) -> Node:
        first = self.parse_expr()
        if not self.at_op(","):
            return first
        items = [first]
        while self.at_op(","):
            self.next()
            if self.at_end() or self.at_op(")", "]", "}", "=", ":"):
                break
            items.append(self.parse_expr())
        return Seq(first.tok, "tuple", items)

    def parse_expr(self) -> Node:
        n = self.parse_bin(1)
        p = self.peek()
        if p is not None and p.is_name("if"):
            save = self.i
            self.next()
            try:
                cond = self.parse_bin(1)
                if self.at_name("else"):
                    self.next()
                    other = self.parse_expr()
                    return IfExp(n.tok, cond, n, other)
            except ParseError:
                pass
            self.i = save
        return n

    def _binop_here(self) -> tuple[str, int] | None:
        p = self.peek()
        if p is None:
            return None
        if p.kind is K.NAME:
            if p.value in ("and", "or", "in", "is"):
                if p.value == "is" and (q := self.peek(1)) is not None and q.is_name("not"):
                    return "is not", 2
                return p.value, 1
            if p.value == "not" and (q := self.peek(1)) is not None and q.is_name("in"):
                return "not in", 2
            return None
        if p.kind is K.OP and p.value in PREC:
            if p.value == "^":
                q = self.peek(1)
                if q is None or (q.kind is K.OP and q.value in STOP_AFTER_CARET):
                    return None
            return p.value, 1
        return None

    def parse_bin(self, min_prec: int) -> Node:
        if min_prec <= 3 and (p := self.peek()) is not None and p.is_name("not"):
            tok = self.next()
            left: Node = Unary(tok, "not", self.parse_bin(3))
        else:
            left = self.parse_unary()
        while True:
            hit = self._binop_here()
            if hit is None:
                return left
            op, width = hit
            prec = PREC.get(op, 4)
            if prec < min_prec:
                return left
            tok = self.peek()
            assert tok is not None
            self.i += width
            right = self.parse_bin(prec + 1)
            left = BinOp(tok, op, left, right)

    def parse_unary(self) -> Node:
        p = self.peek()
        if p is not None and p.kind is K.OP and p.value in ("-", "+", "~"):
            tok = self.next()
            return Unary(tok, p.value, self.parse_unary())
        return self.parse_power()

    def parse_power(self) -> Node:
        base = self.parse_postfix()
        if self.at_op("**"):
            tok = self.next()
            return BinOp(tok, "**", base, self.parse_unary())
        return base

    def parse_postfix(self) -> Node:
        n = self.parse_atom()
        while True:
            p = self.peek()
            if p is None or p.kind is not K.OP:
                return n
            if p.value == ".":
                self.next()
                a = self.next()
                n = Attr(a, n, a.value)
            elif p.value == "(":
                tok = self.next()
                args, kw = self.parse_args(")")
                n = Call(tok, n, args, kw)
            elif p.value == "[":
                tok = self.next()
                args, kw = self.parse_args("]")
                n = Sub(tok, n, args, kw)
            elif p.value == "^":
                q = self.peek(1)
                if q is None or (q.kind is K.OP and q.value in STOP_AFTER_CARET):
                    tok = self.next()
                    n = Transfer(tok, n)
                else:
                    return n
            elif p.value == "!":
                self.next()
            else:
                return n

    def parse_args(self, close: str) -> tuple[list[Node], list[tuple[str, Node]]]:
        args: list[Node] = []
        kw: list[tuple[str, Node]] = []
        while not self.at_op(close):
            p = self.peek()
            if p is None:
                raise ParseError("eof in args")
            q = self.peek(1)
            if p.kind is K.NAME and q is not None and q.is_op("="):
                self.i += 2
                i0 = self.i
                v = self.parse_expr()
                if close == "]" and self.at_op(":"):
                    self._slice_rest()
                    v = Other(v.tok, [v], self._text(i0))
                kw.append((p.value, v))
            elif p.is_op("*", "**"):
                self.next()
                args.append(self.parse_expr())
            elif p.is_op(":") and close == "]":
                i0 = self.i
                self._slice_rest()
                args.append(Other(p, [], self._text(i0)))
            else:
                i0 = self.i
                e = self.parse_expr()
                if close == "]" and self.at_op(":"):
                    self._slice_rest()
                    e = Other(e.tok, [e], self._text(i0))
                elif p.is_name() and self.at_op(":") and close != "]":
                    pass
                args.append(e)
            if self.at_op(","):
                self.next()
            elif not self.at_op(close):
                raise ParseError(f"bad arg sep {self.peek()}")
        self.next()
        return args, kw

    def parse_atom(self) -> Node:
        tok = self.next()
        if tok.kind is K.NAME:
            if tok.value in ("ref", "var", "deinit", "owned") and ((q := self.peek()) is not None and q.kind is K.NAME):
                return self.parse_atom()
            if tok.value == "origin_of" or tok.value.startswith("__mlir"):
                pass
            return Name(tok, tok.value)
        if tok.kind is K.NUMBER:
            return Num(tok, tok.value)
        if tok.kind is K.STRING:
            text = tok.value
            while (p := self.peek()) is not None and p.kind is K.STRING:
                text += self.next().value
            return Str(tok, text)
        if tok.kind is K.OP:
            if tok.value == "(":
                if self.at_op(")"):
                    self.next()
                    return Seq(tok, "tuple", [])
                inner = self.parse_tuple()
                if not isinstance(inner, Seq):
                    if self.at_name("for"):
                        self._skip_to(")")
                        return Other(tok, [inner])
                    self.expect(")")
                    return inner
                self.expect(")")
                return inner
            if tok.value == "[":
                items, _ = self.parse_list_like("]")
                return Seq(tok, "list", items)
            if tok.value == "{":
                items, _ = self.parse_list_like("}")
                return Seq(tok, "set", items)
            if tok.value == "...":
                return Other(tok)
        raise ParseError(f"unexpected {tok}")

    def _slice_rest(self) -> None:
        while self.at_op(":"):
            self.next()
            if not self.at_op(",", "]", ":"):
                self.parse_expr()

    def _text(self, i0: int) -> str:
        out = ""
        prev: Token | None = None
        for t in self.t[i0 : self.i]:
            if prev is not None and prev.kind in (K.NAME, K.NUMBER) and t.kind in (K.NAME, K.NUMBER):
                out += " "
            out += t.value
            prev = t
        return out

    def parse_list_like(self, close: str) -> tuple[list[Node], bool]:
        items: list[Node] = []
        while not self.at_op(close):
            if self.at_end():
                raise ParseError("eof")
            p = self.peek()
            if p is not None and p.is_name("for"):
                self._skip_to(close)
                return items, True
            if p is not None and p.is_op("*", "**"):
                self.next()
            items.append(self.parse_expr())
            if self.at_op(":"):
                self.next()
                items.append(self.parse_expr())
            if self.at_op(","):
                self.next()
        self.next()
        return items, False

    def _skip_to(self, close: str) -> None:
        depth = 0
        while not self.at_end():
            t = self.next()
            if t.kind is K.OP and t.value in "([{":
                depth += 1
            elif t.kind is K.OP and t.value in ")]}":
                if depth == 0 and t.value == close:
                    return
                depth -= 1
        raise ParseError("eof skip")


def parse_expr(toks: list[Token]) -> Node | None:
    if not toks:
        return None
    p = ExprParser(toks)
    try:
        n = p.parse_tuple()
    except (ParseError, AssertionError):
        return None
    if not p.at_end():
        return None
    return n


def unparse(n: Node | None) -> str:
    if n is None:
        return "?"
    match n:
        case Name(id=i):
            return i
        case Num(text=t):
            return t
        case Str(text=t):
            return t
        case Attr(obj=o, attr=a):
            return f"{unparse(o)}.{a}"
        case Sub(obj=o, index=ix, kw=kw):
            return f"{unparse(o)}[{_args(ix, kw)}]"
        case Call(func=f, args=a, kw=kw):
            return f"{unparse(f)}({_args(a, kw)})"
        case BinOp(op=op, left=lft, right=r):
            return f"{_wrap(lft, op)} {op} {_wrap(r, op, right=True)}"
        case Unary(op=op, operand=o):
            sep = " " if op == "not" else ""
            return f"{op}{sep}{_wrap(o, 'u')}"
        case Transfer(operand=o):
            return f"{unparse(o)}^"
        case IfExp(cond=c, then=t, other=o):
            return f"{unparse(t)} if {unparse(c)} else {unparse(o)}"
        case Seq(kind="tuple", items=it):
            return "(" + ", ".join(unparse(x) for x in it) + ("," if len(it) == 1 else "") + ")"
        case Seq(kind="list", items=it):
            return "[" + ", ".join(unparse(x) for x in it) + "]"
        case Seq(items=it):
            return "{" + ", ".join(unparse(x) for x in it) + "}"
        case Other(src=src) if src:
            return src
        case Other(items=[x]):
            return unparse(x)
    return "?"


def _args(a: list[Node], kw: list[tuple[str, Node]]) -> str:
    return ", ".join([unparse(x) for x in a] + [f"{k}={unparse(v)}" for k, v in kw])


def _wrap(n: Node, op: str, right: bool = False) -> str:
    s = unparse(n)
    if isinstance(n, (BinOp, IfExp)):
        po = PREC.get(op, 11 if op in ("**", "u") else 4)
        pn = PREC.get(n.op, 11) if isinstance(n, BinOp) else 0
        if pn < po or (right and pn == po):
            return f"({s})"
    return s


def root_name(n: Node) -> str | None:
    while True:
        match n:
            case Name(id=i):
                return i
            case Attr(obj=o) | Sub(obj=o) | Transfer(operand=o):
                n = o
            case Call(func=Attr(obj=o)):
                n = o
            case _:
                return None


def path_of(n: Node) -> str | None:
    match n:
        case Name(id=i):
            return i
        case Attr(obj=o, attr=a):
            p = path_of(o)
            return None if p is None else f"{p}.{a}"
    return None


def names(n: Node | None) -> set[str]:
    return {x.id for x in walk(n) if isinstance(x, Name)}


def same(a: Node | None, b: Node | None) -> bool:
    return a is not None and b is not None and unparse(a) == unparse(b)
