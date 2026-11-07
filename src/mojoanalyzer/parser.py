from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from .expr import Name, Node, Seq, parse_expr
from .tokenizer import K, Token, tokenize

COMPOUND = {
    "def",
    "fn",
    "struct",
    "trait",
    "class",
    "for",
    "while",
    "if",
    "elif",
    "else",
    "try",
    "except",
    "finally",
    "with",
}
AUG = {"+=", "-=", "*=", "/=", "//=", "%=", "**=", "&=", "|=", "^=", "<<=", ">>=", "@="}
CONVENTIONS = {"read", "mut", "var", "ref", "out", "deinit", "owned", "inout", "borrowed"}


@dataclass(slots=True)
class Param:
    name: str
    convention: str
    type: str
    default: str | None
    tok: Token


@dataclass(slots=True)
class FuncInfo:
    name: str
    params: list[Param]
    cparams: list[Param]
    ret: str
    raises: bool
    captures: list[str] | None


@dataclass(eq=False)
class Stmt:
    kind: str
    toks: list[Token]
    line: int
    col: int
    body: list[Stmt] = field(default_factory=list)
    decorators: list[Stmt] = field(default_factory=list)
    parent: Stmt | None = None
    comptime: bool = False
    _cache: dict[str, object] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"Stmt({self.kind}@{self.line}:{self.col} {' '.join(t.value for t in self.toks[:8])})"

    @property
    def header(self) -> list[Token]:
        return self.toks

    def text(self) -> str:
        return " ".join(t.value for t in self.toks)

    def walk(self) -> Iterator[Stmt]:
        stack = list(reversed(self.body))
        while stack:
            s = stack.pop()
            yield s
            stack.extend(reversed(s.body))

    def ancestors(self) -> Iterator[Stmt]:
        p = self.parent
        while p is not None:
            yield p
            p = p.parent

    def func(self) -> Stmt | None:
        for a in self.ancestors():
            if a.kind == "def":
                return a
        return None

    def enclosing_loops(self) -> list[Stmt]:
        out = []
        for a in self.ancestors():
            if a.kind == "def":
                break
            if a.kind in ("for", "while"):
                out.append(a)
        return out

    def has_decorator(self, name: str) -> bool:
        return any(len(d.toks) > 1 and d.toks[1].value == name for d in self.decorators)

    def _memo(self, key: str, fn):
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    @property
    def expr(self) -> Node | None:
        return self._memo("expr", lambda: parse_expr(self.toks) if self.kind == "expr" else None)

    @property
    def assign(self) -> tuple[list[Node | None], Node | None] | None:
        def f() -> tuple[list[Node | None], Node | None] | None:
            if self.kind != "assign":
                return None
            parts = split_top(self.toks, "=")
            return [parse_expr(p) for p in parts[:-1]], parse_expr(parts[-1])

        return self._memo("assign", f)

    @property
    def aug(self) -> tuple[Node | None, str, Node | None] | None:
        def f() -> tuple[Node | None, str, Node | None] | None:
            if self.kind != "augassign":
                return None
            for i, t in enumerate(self.toks):
                if t.kind is K.OP and t.value in AUG and _depth_at(self.toks, i) == 0:
                    return parse_expr(self.toks[:i]), t.value, parse_expr(self.toks[i + 1 :])
            return None

        return self._memo("aug", f)

    @property
    def decl(self) -> tuple[list[str], str | None, Node | None] | None:
        def f() -> tuple[list[str], str | None, Node | None] | None:
            if self.kind not in ("var", "comptime"):
                return None
            toks = self.toks[1:]
            if self.kind == "comptime" and toks and toks[0].value in ("comptime",):
                toks = toks[1:]
            parts = split_top(toks, "=")
            lhs = parts[0]
            val = parse_expr(parts[1]) if len(parts) > 1 else None
            colon = next((i for i, t in enumerate(lhs) if t.is_op(":") and _depth_at(lhs, i) == 0), None)
            names_toks = lhs if colon is None else lhs[:colon]
            typ = None if colon is None else "".join(_tok_text(lhs[colon + 1 :]))
            ns = [t.value for t in names_toks if t.kind is K.NAME]
            return ns, typ, val

        return self._memo("decl", f)

    @property
    def cond(self) -> Node | None:
        def f() -> Node | None:
            if self.kind not in ("if", "elif", "while"):
                return None
            toks = self.toks[1:]
            if toks and toks[0].value == "if" and self.comptime:
                toks = toks[1:]
            return parse_expr(toks[:-1] if toks and toks[-1].is_op(":") else toks)

        return self._memo("cond", f)

    @property
    def loop(self) -> tuple[list[str], Node | None] | None:
        def f() -> tuple[list[str], Node | None] | None:
            if self.kind != "for":
                return None
            toks = self.toks
            i = next((j for j, t in enumerate(toks) if t.is_name("for")), 0) + 1
            j = next((k for k in range(i, len(toks)) if toks[k].is_name("in") and _depth_at(toks, k) == 0), None)
            if j is None:
                return None
            tt = toks[i:j]
            if len(tt) > 1 and tt[0].value in ("ref", "var", "mut") and tt[1].kind is K.NAME:
                tt = tt[1:]
            tgt = [t.value for t in tt if t.kind is K.NAME]
            end = len(toks) - 1 if toks[-1].is_op(":") else len(toks)
            return tgt, parse_expr(toks[j + 1 : end])

        return self._memo("loop", f)

    @property
    def fn(self) -> FuncInfo | None:
        return self._memo("fn", lambda: parse_def(self.toks) if self.kind == "def" else None)


def _tok_text(toks: list[Token]) -> list[str]:
    return [t.value for t in toks]


def _depth_at(toks: list[Token], idx: int) -> int:
    d = 0
    for t in toks[:idx]:
        if t.kind is K.OP:
            if t.value in "([{":
                d += 1
            elif t.value in ")]}":
                d -= 1
    return d


def split_top(toks: list[Token], sep: str) -> list[list[Token]]:
    out: list[list[Token]] = [[]]
    d = 0
    for t in toks:
        if t.kind is K.OP:
            if t.value in "([{":
                d += 1
            elif t.value in ")]}":
                d -= 1
            elif t.value == sep and d == 0:
                out.append([])
                continue
        out[-1].append(t)
    return out


def first_top(toks: list[Token], val: str) -> int | None:
    d = 0
    for i, t in enumerate(toks):
        if t.kind is K.OP:
            if t.value in "([{":
                d += 1
            elif t.value in ")]}":
                d -= 1
            elif t.value == val and d == 0:
                return i
    return None


def classify(toks: list[Token]) -> tuple[str, bool]:
    if not toks:
        return "empty", False
    t0 = toks[0]
    if t0.is_op("@"):
        return "decorator", False
    if t0.kind is K.STRING and len(toks) == 1:
        return "docstring", False
    if t0.kind is K.NAME:
        v = t0.value
        if (
            v == "comptime"
            and len(toks) > 1
            and toks[1].kind is K.NAME
            and toks[1].value in ("for", "if", "elif", "else")
        ):
            return toks[1].value, True
        if v == "comptime" and len(toks) > 1 and toks[1].is_op(":"):
            return "else", True
        if v in ("comptime", "alias"):
            return "comptime", False
        if v in ("async",) and len(toks) > 1 and toks[1].value in ("def", "fn", "for", "with"):
            return ("def" if toks[1].value in ("def", "fn") else toks[1].value), False
        if v == "fn":
            return "def", False
        if v in COMPOUND:
            return v, False
        if v in ("var", "ref"):
            return "var", False
        if v in ("return", "pass", "break", "continue", "raise", "import", "from", "assert", "del", "yield"):
            return v, False
    d = 0
    for t in toks:
        if t.kind is K.OP:
            if t.value in "([{":
                d += 1
            elif t.value in ")]}":
                d -= 1
            elif d == 0 and t.value in AUG:
                return "augassign", False
            elif d == 0 and t.value == "=":
                return "assign", False
    return "expr", False


class _P:
    def __init__(self, toks: list[Token]) -> None:
        self.t = toks
        self.i = 0

    def logical_line(self) -> tuple[list[Token], list[Token]]:
        sig: list[Token] = []
        com: list[Token] = []
        while self.i < len(self.t):
            tok = self.t[self.i]
            if tok.kind is K.NEWLINE:
                self.i += 1
                break
            if tok.kind in (K.INDENT, K.DEDENT, K.END) and not sig:
                break
            if tok.kind in (K.INDENT, K.DEDENT, K.END):
                break
            self.i += 1
            if tok.kind is K.COMMENT:
                com.append(tok)
            elif tok.kind is not K.NL:
                sig.append(tok)
        return sig, com

    def skip_blank(self) -> None:
        while self.i < len(self.t) and self.t[self.i].kind in (K.NL, K.COMMENT, K.NEWLINE):
            self.i += 1

    def block(self, parent: Stmt) -> list[Stmt]:
        out: list[Stmt] = []
        decos: list[Stmt] = []
        while True:
            self.skip_blank()
            if self.i >= len(self.t):
                break
            tok = self.t[self.i]
            if tok.kind is K.END:
                break
            if tok.kind is K.DEDENT:
                if parent.kind == "module":
                    self.i += 1
                    continue
                self.i += 1
                break
            if tok.kind is K.INDENT:
                self.i += 1
                stray = Stmt("block", [], tok.line, tok.col, parent=parent)
                stray.body = self.block(stray)
                out.extend(stray.body)
                for s in stray.body:
                    s.parent = parent
                continue
            sig, _ = self.logical_line()
            if not sig:
                continue
            for part in split_top(sig, ";"):
                if not part:
                    continue
                s = self.make(part, parent)
                if s.kind == "decorator":
                    decos.append(s)
                    continue
                s.decorators = decos
                decos = []
                out.append(s)
        return out

    def make(self, toks: list[Token], parent: Stmt) -> Stmt:
        kind, ct = classify(toks)
        s = Stmt(kind, toks, toks[0].line, toks[0].col, parent=parent, comptime=ct)
        if kind in COMPOUND:
            c = first_top(toks, ":")
            if c is None:
                return s
            if c == len(toks) - 1:
                self.skip_blank()
                if self.i < len(self.t) and self.t[self.i].kind is K.INDENT:
                    self.i += 1
                    s.body = self.block(s)
            else:
                s.toks = toks[: c + 1]
                for part in split_top(toks[c + 1 :], ";"):
                    if part:
                        s.body.append(self.make(part, s))
        return s


def parse(src: str) -> Stmt:
    toks = tokenize(src)
    mod = Stmt("module", [], 1, 0)
    p = _P(toks)
    mod.body = p.block(mod)
    return mod


def parse_def(toks: list[Token]) -> FuncInfo | None:
    i = 0
    while i < len(toks) and toks[i].value in ("async", "def", "fn"):
        i += 1
    if i >= len(toks) or toks[i].kind is not K.NAME:
        return None
    name = toks[i].value
    i += 1
    cparams: list[Param] = []
    if i < len(toks) and toks[i].is_op("["):
        j = _match(toks, i)
        cparams = _params(toks[i + 1 : j])
        i = j + 1
    params: list[Param] = []
    if i < len(toks) and toks[i].is_op("("):
        j = _match(toks, i)
        params = _params(toks[i + 1 : j])
        i = j + 1
    rest = toks[i:]
    raises = any(t.is_name("raises") for t in rest)
    captures = None
    for k, t in enumerate(rest):
        if t.is_op("{"):
            j = _match(rest, k)
            captures = [x.value for x in rest[k + 1 : j] if x.kind is K.NAME and x.value not in CONVENTIONS]
            break
    ret = ""
    for k, t in enumerate(rest):
        if t.is_op("->"):
            end = len(rest) - 1 if rest[-1].is_op(":") else len(rest)
            ret = "".join(x.value for x in rest[k + 1 : end] if not x.is_name("raises"))
            break
    return FuncInfo(name, params, cparams, ret, raises, captures)


def _match(toks: list[Token], i: int) -> int:
    d = 0
    for j in range(i, len(toks)):
        t = toks[j]
        if t.kind is K.OP and t.value in "([{":
            d += 1
        elif t.kind is K.OP and t.value in ")]}":
            d -= 1
            if d == 0:
                return j
    return len(toks) - 1


def _params(toks: list[Token]) -> list[Param]:
    out: list[Param] = []
    for part in split_top(toks, ","):
        if not part or (part[0].is_op("*", "/", "**") and len(part) == 1):
            continue
        p = list(part)
        conv = "read"
        while p and p[0].kind is K.NAME and p[0].value in CONVENTIONS and len(p) > 1 and p[1].kind is K.NAME:
            conv = p[0].value
            p = p[1:]
        if p and p[0].kind is K.NAME and p[0].value.startswith("ref") and len(p) > 1 and p[1].is_op("["):
            j = _match(p, 1)
            conv = "ref"
            p = p[j + 1 :]
        while p and p[0].is_op("*", "**"):
            p = p[1:]
        if not p or p[0].kind is not K.NAME:
            continue
        name = p[0].value
        eq = first_top(p, "=")
        body = p[1:eq] if eq is not None else p[1:]
        typ = "".join(t.value for t in body[1:]) if body and body[0].is_op(":") else ""
        default = " ".join(t.value for t in p[eq + 1 :]) if eq is not None else None
        out.append(Param(name, conv, typ, default, p[0]))
    return out


def is_name_node(n: Node | None, name: str) -> bool:
    return isinstance(n, Name) and n.id == name


def tuple_items(n: Node | None) -> list[Node]:
    if isinstance(n, Seq) and n.kind == "tuple":
        return n.items
    return [] if n is None else [n]
