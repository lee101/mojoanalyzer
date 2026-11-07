from __future__ import annotations

import itertools
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import ClassVar

from ..core import (
    PURE_BUILTINS,
    READONLY_METHODS,
    FileCtx,
    Finding,
    Rule,
    callee,
    elem_type,
    is_float_type,
    range_args,
    stmt_nodes,
)
from ..expr import Attr, BinOp, Call, IfExp, Name, Node, Num, Seq, Str, Sub, Unary, path_of, root_name, unparse, walk
from ..parser import Stmt, tuple_items
from ._util import FLOAT_CASTS, parent_map

INT_TYPES = {"Int", "Int8", "Int16", "Int32", "Int64", "UInt", "UInt8", "UInt16", "UInt32", "UInt64"}
CASTS = FLOAT_CASTS | INT_TYPES
ORDER = {"<", ">", "<=", ">=", "==", "!="}
FLOAT_FUNCS = {
    "sqrt", "exp", "log", "log2", "log10", "exp2", "tanh", "sin", "cos", "tan", "rsqrt", "log1p", "expm1", "cbrt",
    "erf", "atan", "atan2", "hypot", "pow", "atof",
}  # fmt: skip
SAME_FUNCS = {"abs", "min", "max", "floor", "ceil", "round", "trunc", "clamp", "copysign"}
PRICE = {
    "px", "price", "prices", "close", "closes", "open", "opens", "high", "highs", "low", "lows", "mid", "bid", "ask",
    "vwap", "basis", "entry", "prev", "last", "ref", "equity", "eq", "nav", "cash", "notional", "capital", "bp",
    "std", "sd", "sigma", "vol", "vols", "volatility", "var", "variance", "denom", "den", "norm", "total", "tot",
    "sum", "count", "cnt", "nobs", "qty", "shares", "volume", "adv", "dv", "spread", "range", "rng", "atr", "p0",
    "c0", "o0", "cp", "hpx", "spx", "pc", "po", "lp",
}  # fmt: skip
MONEY = {
    "qty", "shares", "share", "sh", "notional", "position", "pos", "size", "lot", "lots", "equity", "cash", "dollars",
    "usd", "budget", "alloc", "amount", "amt", "units", "contracts", "filled", "bp", "buying", "nav", "capital",
    "dollar",
}  # fmt: skip
ROUND_FUNCS = {"floor", "ceil", "round", "trunc"}
WRITE_FUNCS = {"c_write", "write", "write_fd", "send", "fwrite", "sendall", "send_all", "write_all"}
PARSE_CALL = re.compile(r"^(?!.*(sum|bits|mean|dot))(.*(atof|float|ofloat|json|jnum|read_f64)|num)$", re.I)
ACTION_WORDS = re.compile(r"(submit|cancel|place|send|write|close|flush|replace|order|post|put|save|store|commit)")


def tokens(path: str) -> list[str]:
    last = path.rsplit(".", maxsplit=1)[-1].lstrip("_").lower()
    return [t for t in re.split(r"_+", last) if t]


def is_const_name(n: str) -> bool:
    return n.isupper() and len(n) > 1


def strip_casts(n: Node) -> Node:
    while isinstance(n, Call) and isinstance(n.func, Name) and n.func.id in CASTS and len(n.args) == 1 and not n.kw:
        n = n.args[0]
    while (
        isinstance(n, Call) and isinstance(n.func, Sub) and root_name(n.func) in ("Scalar", "SIMD") and len(n.args) == 1
    ):
        n = n.args[0]
    return n


def is_len(n: Node) -> Node | None:
    if isinstance(n, Call) and isinstance(n.func, Name) and n.func.id == "len" and len(n.args) == 1:
        return n.args[0]
    if isinstance(n, Call) and isinstance(n.func, Attr) and n.func.attr in ("__len__", "byte_length") and not n.args:
        return n.func.obj
    return None


def num_value(n: Node | None) -> float | None:
    if isinstance(n, Num):
        try:
            return float(n.text.replace("_", "")) if n.is_float else float(int(n.text.replace("_", ""), 0))
        except ValueError:
            return None
    if isinstance(n, Unary) and n.op == "-":
        v = num_value(n.operand)
        return None if v is None else -v
    if isinstance(n, Call) and isinstance(n.func, Name) and n.func.id in CASTS and len(n.args) == 1:
        return num_value(n.args[0])
    return None


def pure(n: Node) -> bool:
    for x in walk(n):
        if isinstance(x, Call):
            c = callee(x)
            if isinstance(x.func, Attr):
                if c not in READONLY_METHODS and c not in ("unsafe_get", "__getitem__", "load"):
                    return False
            elif c not in PURE_BUILTINS:
                return False
    return True


@dataclass
class Fn:
    """Per-function facts shared by the correctness rules (guards, definitions, numeric types)."""

    stmt: Stmt | None
    stmts: list[Stmt]
    env: dict[str, str]
    guards: set[str] = field(default_factory=set)
    defs: dict[str, list[tuple[Stmt, str, Node | None]]] = field(default_factory=dict)
    rvars: dict[str, Stmt] = field(default_factory=dict)
    params: set[str] = field(default_factory=set)


def guard_keys(n: Node) -> set[str]:
    out: set[str] = set()
    c = strip_casts(n)
    while isinstance(c, Call) and callee(c) == "abs" and len(c.args) == 1:
        c = strip_casts(c.args[0])
    out.add(unparse(c))
    if isinstance(c, Sub):
        p = path_of(c.obj)
        if p:
            out.add(p + "[]")
    if (x := is_len(c)) is not None:
        out.add(unparse(x))
    if isinstance(c, BinOp) and c.op in ("-", "+") and num_value(c.right) is not None:
        out |= guard_keys(c.left)
    return out


class Facts:
    def __init__(self, ctx: FileCtx) -> None:
        self.ctx = ctx
        self._fn: dict[int, Fn] = {}
        self._mod: Fn | None = None
        self.flat: list[tuple[Stmt, Node]] | None = None
        self._by_fn: dict[int, list[Stmt]] | None = None

    def stmts_of(self, fn: Stmt | None) -> list[Stmt]:
        if self._by_fn is None:
            by: dict[int, list[Stmt]] = {}
            stack: list[tuple[Stmt, Stmt | None]] = [(c, None) for c in reversed(self.ctx.mod.body)]
            while stack:
                st, owner = stack.pop()
                by.setdefault(id(owner), []).append(st)
                inner = st if st.kind == "def" else owner
                stack.extend((c, inner) for c in reversed(st.body))
            self._by_fn = by
        return self._by_fn.get(id(fn), [])

    def of(self, s: Stmt) -> Fn:
        fn = s.func()
        if fn is None:
            if self._mod is None:
                self._mod = self._build(None)
            return self._mod
        if id(fn) not in self._fn:
            self._fn[id(fn)] = self._build(fn)
        return self._fn[id(fn)]

    def _build(self, fn: Stmt | None) -> Fn:
        ctx = self.ctx
        f = Fn(fn, self.stmts_of(fn), ctx.env(fn))
        outer = fn.func() if fn is not None else None
        if outer is not None:
            o = self._fn.get(id(outer)) or self._build(outer)
            self._fn[id(outer)] = o
            f.guards |= o.guards
            for k, v in o.defs.items():
                f.defs.setdefault(k, []).extend(v)
            f.rvars.update(o.rvars)
            f.params |= o.params
        if fn is not None and fn.fn:
            f.params |= {p.name for p in fn.fn.params}
        scope = list(fn.walk()) if fn is not None else f.stmts
        for s in scope:
            if s.kind in ("if", "elif", "while") and s.cond is not None:
                self._truthy(s.cond, f.guards)
            for n in stmt_nodes(s):
                for x in nodes(n):
                    if isinstance(x, BinOp) and x.op in ORDER:
                        f.guards |= guard_keys(x.left) | guard_keys(x.right)
                        f.guards.add("pair:" + "|".join(sorted((unparse(x.left), unparse(x.right)))))
                    elif isinstance(x, IfExp):
                        self._truthy(x.cond, f.guards)
                    elif isinstance(x, Unary) and x.op == "not":
                        f.guards |= guard_keys(x.operand)
                    elif isinstance(x, BinOp) and x.op in ("and", "or"):
                        self._truthy(x.left, f.guards)
                        self._truthy(x.right, f.guards)
                    elif isinstance(x, Call) and callee(x) in ("debug_assert", "assert_true", "require"):
                        for a in x.args:
                            self._truthy(a, f.guards)
        for s in f.stmts:
            if s.kind == "var" and s.decl and len(s.decl[0]) == 1:
                f.defs.setdefault(s.decl[0][0], []).append((s, "=", s.decl[2]))
            elif s.kind == "assign" and s.assign:
                tg, val = s.assign
                for t in tg:
                    if t is not None and not isinstance(t, Seq):
                        f.defs.setdefault(unparse(t), []).append((s, "=", val))
                    elif isinstance(t, Seq):
                        for it in tuple_items(t):
                            f.defs.setdefault(unparse(it), []).append((s, "=", None))
            elif s.kind == "augassign" and s.aug and s.aug[0] is not None:
                f.defs.setdefault(unparse(s.aug[0]), []).append((s, s.aug[1], s.aug[2]))
            elif s.kind == "for" and s.loop:
                ra = range_args(s.loop[1])
                for nm in s.loop[0]:
                    if ra is not None and len(s.loop[0]) == 1:
                        f.rvars[nm] = s
                    f.defs.setdefault(nm, []).append((s, "for", s.loop[1]))
        decl_t: dict[str, set[str | None]] = {}
        for st in f.stmts:
            if st.kind == "var" and st.decl and len(st.decl[0]) == 1:
                decl_t.setdefault(st.decl[0][0], set()).add(st.decl[1] or ctx.infer(st.decl[2], f.env))
        f.env = dict(f.env)
        for k, ts in decl_t.items():
            if len(ts) > 1 or None in ts:
                f.env.pop(k, None)
        for k in f.rvars:
            if k not in decl_t:
                f.env.setdefault(k, "Int")
        return f

    def _truthy(self, c: Node, out: set[str]) -> None:
        if isinstance(c, Unary) and c.op == "not":
            c = c.operand
        if isinstance(c, (Name, Attr, Sub)) or is_len(c) is not None:
            out |= guard_keys(c)
        elif isinstance(c, Call):
            for a in [*c.args, *(v for _, v in c.kw)]:
                out |= guard_keys(a)
        elif isinstance(c, BinOp) and c.op in ("and", "or"):
            self._truthy(c.left, out)
            self._truthy(c.right, out)

    def ntype(self, n: Node | None, f: Fn, depth: int = 0) -> str | None:
        if n is None or depth > 4:
            return None
        if isinstance(n, Name) and n.id not in f.env and n.id not in f.params:
            ts = {self.ntype(v, f, depth + 1) for _, op, v in f.defs.get(n.id, []) if op == "="}
            if len(ts) == 1:
                return ts.pop()
        ctx = self.ctx
        match n:
            case Num():
                return "f" if n.is_float else "i"
            case Name() | Attr() | Sub():
                p = path_of(n)
                t = None
                if p is not None and p in f.env:
                    t = ctx.resolve(f.env[p], f.env)
                elif isinstance(n, Sub):
                    t = ctx.type_of(n, f.env)
                elif isinstance(n, Name) and is_const_name(n.id) and n.id in ctx.module_comptime:
                    return self.ntype(ctx.module_comptime[n.id], f, depth + 1)
                return tmap(t)
            case Call(func=Name(id=c), args=args):
                if c in FLOAT_CASTS or c in FLOAT_FUNCS:
                    return "f"
                if c in INT_TYPES or c == "len":
                    return "i"
                if c in SAME_FUNCS and args:
                    ts = {self.ntype(a, f, depth + 1) for a in args}
                    return ts.pop() if len(ts) == 1 else ("f" if "f" in ts else None)
                es = ctx.index.lookup(c, ctx.display)
                rets = {e.info.ret for e in es if e.owner is None}
                if len(rets) == 1:
                    return tmap(rets.pop())
                return None
            case Call(func=Attr(attr=a)) if a in ("__len__", "byte_length"):
                return "i"
            case BinOp(op=op, left=lft, right=r) if op in ("+", "-", "*", "/", "//", "%", "**"):
                a, b = self.ntype(lft, f, depth + 1), self.ntype(r, f, depth + 1)
                if "f" in (a, b):
                    return "f"
                return "i" if a == b == "i" else None
            case Unary(op=op, operand=o) if op in ("-", "+"):
                return self.ntype(o, f, depth + 1)
            case IfExp(then=t, other=o):
                a, b = self.ntype(t, f, depth + 1), self.ntype(o, f, depth + 1)
                return a if a == b else None
        return None


def tmap(t: str | None) -> str | None:
    if not t:
        return None
    t = t.replace(" ", "")
    if is_float_type(t):
        return "f"
    if t in INT_TYPES or re.match(r"^(Scalar|SIMD)\[DType\.u?int\d*", t):
        return "i"
    return None


def in_func(s: Stmt) -> Iterator[Stmt]:
    for a in s.ancestors():
        if a.kind == "def":
            return
        yield a


def stmt_walk(ctx: FileCtx) -> list[tuple[Stmt, Node]]:
    fx = facts(ctx)
    if fx.flat is None:
        fx.flat = [(s, n) for s in [ctx.mod, *ctx.mod.walk()] for n in stmt_nodes(s)]
    return fx.flat


_WALK: dict[int, list[Node]] = {}


def nodes(root: Node) -> list[Node]:
    got = _WALK.get(id(root))
    if got is None or (got and got[0] is not root):
        got = _WALK[id(root)] = list(walk(root))
    return got


_FACTS: dict[int, Facts] = {}


def facts(ctx: FileCtx) -> Facts:
    fx = _FACTS.get(id(ctx))
    if fx is None or fx.ctx is not ctx:
        if len(_FACTS) > 4:
            _FACTS.clear()
        _WALK.clear()
        fx = _FACTS[id(ctx)] = Facts(ctx)
    return fx


class UnguardedDivision(Rule):
    """Division by a runtime value that the function never compares, clamps or tests: an empty list, a zero sum,
    a flat bar (`h == l`) or a missing price (0.0) divides by zero. Float division silently yields inf/NaN that
    flows into weights and order sizes; Mojo `Int` division by zero returns 0 without trapping."""

    id = "MA201"
    name = "unguarded-division"
    severity = "medium"
    confidence = "medium"
    bad = "var n = len(rets)\nreturn s / Float64(n)"
    good = "var n = len(rets)\nif n == 0:\n    return 0.0\nreturn s / Float64(n)"
    why = "a zero divisor turns into inf/NaN (Float) or 0 (Int) and propagates into sizing silently"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        fx = facts(ctx)
        for s, root in stmt_walk(ctx):
            for x in nodes(root):
                if isinstance(x, BinOp) and x.op in ("/", "//", "%"):
                    d = x.right
                elif s.kind == "augassign" and s.aug and s.aug[1] in ("/=", "//=") and x is s.aug[2]:
                    d = x
                else:
                    continue
                f = fx.of(s)
                if isinstance(x, BinOp) and x.op in ("//", "%") and self._index_decode(x.left, s, f):
                    continue
                got = self._classify(fx, f, d, s)
                if got is None:
                    continue
                conf, what, why = got
                if conf != "low" and any(isinstance(y, Str) for y in nodes(root)):
                    conf = "low"
                txt = unparse(d)
                kind = fx.ntype(d, f)
                if isinstance(x, BinOp) and x.op == "%" and kind != "i":
                    continue
                fail = "Int: returns 0 silently" if kind == "i" else "Float: inf/NaN propagates"
                if kind is None:
                    fail = "inf/NaN (Float) or 0 (Int)"
                yield self.finding(
                    ctx, d,
                    f"divisor `{txt}` ({what}) is never checked in this function",
                    f"guard: `if {self._guard_expr(d)} == 0: return <fallback>` or divide by `max({txt}, eps)`",
                    confidence=conf,
                    why=f"{why}; zero divisor -> {fail}",
                )  # fmt: skip

    @staticmethod
    def _index_decode(n: Node, s: Stmt, f: Fn) -> bool:
        """`idx // ns`, `idx % ns` with idx a closure parameter or range loop index: mixed-radix decoding of a flat
        cell index, which only runs when the product of the radices is positive."""
        r = root_name(strip_casts(n)) if isinstance(strip_casts(n), (Name, BinOp)) else None
        if isinstance(strip_casts(n), BinOp):
            r = next((x.id for x in walk(n) if isinstance(x, Name)), None)
        if r is None:
            return False
        fn = s.func()
        if fn is not None and fn.func() is not None and fn.fn and r in {p.name for p in fn.fn.params}:
            return True
        if r in f.rvars and any(lp.loop and r in lp.loop[0] for lp in s.enclosing_loops()):
            return True
        ds = [v for st, op, v in f.defs.get(r, []) if op == "=" and st.func() is fn]
        if len(ds) == 1 and isinstance(ds[0], BinOp) and ds[0].op in ("%", "//") and ds[0].left is not n:
            return UnguardedDivision._index_decode(ds[0].left, s, f)
        return False

    @staticmethod
    def _guard_expr(d: Node) -> str:
        c = strip_casts(d)
        return unparse(c)

    def _classify(self, fx: Facts, f: Fn, d: Node, s: Stmt) -> tuple[str, str, str] | None:
        c = strip_casts(d)
        if num_value(c) is not None:
            return None
        keys = guard_keys(c)
        lx0 = self._len_source(f, c)
        if lx0 is not None:
            keys |= guard_keys(lx0)
        if keys & f.guards or self._loop_protected(s, keys, lx0, f) or (lx0 is not None and self._appended(f, lx0, s)):
            return None
        sf = s.func()
        nested = sf is not None and sf.func() is not None
        if lx0 is not None:
            lr = root_name(lx0)
            if lr is not None and (is_const_name(lr) or lr in fx.ctx.module_comptime):
                return None
            conf = "medium" if nested else "high"
            if lr in f.params and len(f.stmts) <= 6 and not any(st.kind in ("if", "elif") for st in f.stmts):
                conf = "low"
            return conf, f"len({unparse(lx0)})", f"`{unparse(lx0)}` can be empty"
        if isinstance(c, BinOp) and c.op == "-":
            k = num_value(c.right)
            base = strip_casts(c.left)
            if num_value(base) is not None or (isinstance(base, Name) and is_const_name(base.id)):
                return None
            if k is not None and k > 0:
                bk = guard_keys(base)
                lx = self._len_source(f, base)
                if lx is not None:
                    bk |= guard_keys(lx)
                if bk & f.guards or self._loop_protected(s, bk, lx, f):
                    return None
                if isinstance(base, Name) and self._safe_name(fx, f, base.id, s):
                    return None
                return (
                    "medium",
                    f"`{unparse(base)} - {unparse(c.right)}`",
                    (f"zero when {unparse(base)} == {unparse(c.right)} (e.g. sample variance with one observation)"),
                )
            if k is None and pure(c):
                return self._diff_ok(f, c)
            return None
        if isinstance(c, Name):
            n = c.id
            if is_const_name(n) or n in fx.ctx.module_comptime or self._safe_name(fx, f, n, s):
                return None
            defs = [d for d in f.defs.get(n, []) if d[0] is not s]
            acc = self._accumulator(defs, f.defs)
            if acc in ("count", "sum") and self._same_predicate(defs, s):
                return None
            if acc == "count":
                return (
                    "high",
                    "a counter starting at 0",
                    "stays 0 when no element passes the filter or the loop is empty",
                )
            if acc == "sum":
                return (
                    "medium",
                    "an accumulator starting at 0",
                    "stays 0 when the loop runs zero times or all terms are 0",
                )
            if acc == "pos":
                return None
            for _, op, v in defs:
                if op == "=" and isinstance(v, BinOp) and v.op == "-" and num_value(v.right) is None and pure(v):
                    if num_value(v.left) is not None or guard_keys(v) & f.guards:
                        return None
                    got = self._diff_ok(f, v)
                    return None if got is None else (got[0], f"difference `{unparse(v)}`", got[2])
            if any(op == "=" and v is not None and self._parsed(v) for _, op, v in defs):
                return "medium", "parsed from external data", "an API/file field can be 0 or missing (parsed as 0.0)"
            if set(tokens(n)) & PRICE:
                return "low", "price/denominator-like", "data-derived values can be 0 (missing bar, halted name)"
            return "low", "unchecked value", "may be zero"
        if isinstance(c, (Sub, Attr)):
            p = path_of(c.obj) if isinstance(c, Sub) else path_of(c)
            if p is None:
                return None
            last = p.split(".")[-1]
            if is_const_name(last) or (isinstance(c, Attr) and self._safe_name(fx, f, p, s)):
                return None
            if set(tokens(p)) & PRICE:
                return "low", "price/denominator-like", "data-derived values can be 0 (missing bar, halted name)"
            return "low", "unchecked value", "may be zero"
        return None

    @staticmethod
    def _diff_ok(f: Fn, c: BinOp) -> tuple[str, str, str] | None:
        if num_value(c.left) is not None or num_value(c.right) is not None:
            return None
        pk = "pair:" + "|".join(sorted((unparse(c.left), unparse(c.right))))
        if pk in f.guards or (guard_keys(c.left) & f.guards and guard_keys(c.right) & f.guards):
            return None
        if guard_keys(c) & f.guards:
            return None
        return "medium", "a difference", "zero when both sides are equal (flat bar h == l, unchanged price)"

    @staticmethod
    def _same_predicate(defs: list[tuple[Stmt, str, Node | None]], s: Stmt) -> bool:
        def conds(st: Stmt) -> set[str]:
            return {unparse(a.cond) for a in in_func(st) if a.kind in ("if", "elif", "while") and a.cond is not None}

        inc = [conds(st) for st, op, _ in defs if op == "+="]
        here = conds(s)
        return bool(inc) and all(c and c <= here for c in inc)

    @staticmethod
    def _parsed(v: Node) -> bool:
        for x in walk(v):
            if isinstance(x, Call) and (c := callee(x)) is not None and PARSE_CALL.search(c) and c not in FLOAT_CASTS:
                return True
        return False

    @staticmethod
    def _loop_protected(s: Stmt, keys: set[str], lx: Node | None, f: Fn | None = None) -> bool:
        for lp in s.enclosing_loops():
            if lp.kind != "for" or not lp.loop:
                continue
            it = lp.loop[1]
            if it is None:
                continue
            ra = range_args(it)
            if ra is not None:
                end = ra[0] if len(ra) == 1 else ra[1]
                seen, todo = [end], [end]
                while todo:
                    e = strip_casts(todo.pop())
                    nxt: list[Node] = []
                    if isinstance(e, BinOp) and e.op == "*":
                        nxt = [e.left, e.right]
                    elif isinstance(e, Name) and f is not None:
                        ds = [v for _, op, v in f.defs.get(e.id, []) if op == "="]
                        if len(ds) == 1 and ds[0] is not None and len(seen) < 12:
                            nxt = [ds[0]]
                    seen += nxt
                    todo += nxt
                if any(guard_keys(e) & keys for e in seen):
                    return True
            elif lx is not None and unparse(it) == unparse(lx):
                return True
        return False

    @staticmethod
    def _appended(f: Fn, lx: Node, s: Stmt) -> bool:
        tgt = unparse(lx)
        chain = {id(a) for a in s.ancestors()}
        for st in f.stmts:
            if st.line >= s.line or st.kind != "expr" or st.parent is None or id(st.parent) not in chain:
                continue
            e = st.expr
            if isinstance(e, Call) and isinstance(e.func, Attr) and e.func.attr == "append":
                if unparse(e.func.obj) == tgt:
                    return True
        for st in f.stmts:
            if st.line > s.line or st.parent is None or (id(st.parent) not in chain and st is not s):
                continue
            for n in stmt_nodes(st):
                for x in nodes(n):
                    if isinstance(x, Sub) and len(x.index) == 1 and unparse(x.obj) == tgt:
                        ix = x.index[0]
                        lit = num_value(ix)
                        if (lit is not None and lit in (0, -1)) or (
                            isinstance(ix, BinOp)
                            and ix.op == "-"
                            and is_len(ix.left) is not None
                            and unparse(is_len(ix.left)) == tgt
                        ):
                            return True
        return False

    def _len_source(self, f: Fn, n: Node) -> Node | None:
        if (lx := is_len(n)) is not None:
            return lx
        if not isinstance(n, Name):
            return None
        defs = f.defs.get(n.id, [])
        if len(defs) == 1 and defs[0][1] == "=" and defs[0][2] is not None:
            return is_len(strip_casts(defs[0][2]))
        return None

    @staticmethod
    def _is_exp(v: Node | None, defs_all: dict[str, list[tuple[Stmt, str, Node | None]]]) -> bool:
        if isinstance(v, Call) and callee(v) in ("exp", "exp2"):
            return True
        if isinstance(v, Name):
            ds = [d for _, op, d in defs_all.get(v.id, []) if op == "="]
            return len(ds) == 1 and isinstance(ds[0], Call) and callee(ds[0]) in ("exp", "exp2")
        return False

    @staticmethod
    def _accumulator(
        defs: list[tuple[Stmt, str, Node | None]], defs_all: dict[str, list[tuple[Stmt, str, Node | None]]]
    ) -> str | None:
        init = [d for d in defs if d[1] == "="]
        aug = [d for d in defs if d[1] in ("+=",)]
        if not (
            len(init) == 1
            and num_value(init[0][2]) == 0
            and bool(aug)
            and all(d[1] in ("=", "+=") for d in defs)
            and any(d[0].enclosing_loops() for d in aug)
        ):
            return None
        if all(UnguardedDivision._is_exp(v, defs_all) for _, _, v in aug):
            return "pos"
        if all(num_value(v) == 1 for _, _, v in aug):
            conditional = any(a.kind in ("if", "elif", "else") for st, _, _ in aug for a in in_func(st))
            return "count" if conditional else "sum"
        return "sum"

    def _safe_name(self, fx: Facts, f: Fn, n: str, s: Stmt) -> bool:
        defs = f.defs.get(n, [])
        if n in f.rvars and not [d for d in defs if d[1] != "for"]:
            lp = f.rvars[n].loop
            ra = range_args(lp[1]) if lp else None
            if ra and len(ra) >= 2 and (v := num_value(ra[0])) is not None and v >= 1:
                return True
            return bool(ra and len(ra) >= 2 and ra[0] is not None and guard_keys(ra[0]) & f.guards)
        vals = [v for _, op, v in defs if op == "="]
        if not vals or any(op not in ("=", "*=") for _, op, _ in defs):
            return False
        return all(self._safe_value(fx, f, v) for v in vals)

    def _safe_value(self, fx: Facts, f: Fn, v: Node | None) -> bool:
        if v is None:
            return False
        v = strip_casts(v)
        nv = num_value(v)
        if nv is not None:
            return nv != 0
        if isinstance(v, Call) and callee(v) in ("max", "clamp") and isinstance(v.func, Name):
            return any((num_value(a) or 0) > 0 or (isinstance(a, Name) and "eps" in a.id.lower()) for a in v.args)
        if isinstance(v, Call) and callee(v) in ("exp", "exp2", "sqrt") and isinstance(v.func, Name):
            return callee(v) != "sqrt"
        if isinstance(v, BinOp) and v.op == "+":
            for a, b in ((v.left, v.right), (v.right, v.left)):
                if 0 < (num_value(a) or 0) <= 1e-3 or ((num_value(a) or 0) > 0 and self._nonneg(b)):
                    return True
                if isinstance(a, Name) and re.search(r"eps|tiny", a.id.lower()) and self._nonneg(b):
                    return True
        if isinstance(v, BinOp) and v.op == "*":
            return self._safe_value(fx, f, v.left) and self._safe_value(fx, f, v.right)
        if isinstance(v, IfExp):
            return self._safe_value(fx, f, v.then) and self._safe_value(fx, f, v.other)
        return False

    @staticmethod
    def _nonneg(n: Node) -> bool:
        n = strip_casts(n)
        if isinstance(n, Call) and callee(n) in ("abs", "sqrt", "exp", "len"):
            return True
        if isinstance(n, BinOp) and n.op == "*" and unparse(n.left) == unparse(n.right):
            return True
        if isinstance(n, BinOp) and n.op == "**" and num_value(n.right) == 2:
            return True
        return (num_value(n) or -1) >= 0 or is_len(n) is not None


class IntTruncation(Rule):
    """`Int(float)` on a share count, notional or round-half-up idiom: `Int()` truncates toward zero, so
    `Int(x + 0.5)` rounds -2.7 to -2 and `Int(qty)` turns 2.9999999 (division noise) into 2 and -0.6 (fractional
    short) into 0."""

    id = "MA202"
    name = "int-truncation"
    severity = "medium"
    confidence = "medium"
    bad = "var q = Int(target_usd / px)\nvar r = Int(x + 0.5)"
    good = "var q = Int(floor(target_usd / px + 1e-9))\nvar r = Int(floor(x + 0.5))"
    why = "Int(Float64) truncates toward zero; sizes and signed deltas round the wrong way"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        fx = facts(ctx)
        for s, root in stmt_walk(ctx):
            for x in nodes(root):
                if not (isinstance(x, Call) and isinstance(x.func, Name) and x.func.id in ("Int", "Int64", "Int32")):
                    continue
                if len(x.args) != 1 or x.kw:
                    continue
                a = x.args[0]
                if isinstance(a, Call) and callee(a) in ROUND_FUNCS:
                    continue
                f = fx.of(s)
                if isinstance(a, BinOp) and a.op == "+" and 0 < (num_value(a.right) or 0) <= 1e-6:
                    continue
                if isinstance(a, BinOp) and a.op == "+" and 0.5 in (num_value(a.right), num_value(a.left)):
                    e = a.left if num_value(a.right) == 0.5 else a.right
                    if self._nonneg(e):
                        continue
                    yield self.finding(
                        ctx, x,
                        f"`Int({unparse(a)})` round-half-up idiom truncates toward zero",
                        f"Int(floor({unparse(a)})) (same result for x >= 0)",
                        confidence="medium" if self._signed(e) else "low",
                        why="for negative x, Int(x + 0.5) rounds -2.7 -> -2 and -0.7 -> 0 (should be -3, -1); "
                        "a short/sell delta comes out one share small",
                    )  # fmt: skip
                    continue
                if fx.ntype(a, f) != "f" or self._nonneg(a):
                    continue
                toks = {t for x2 in walk(a) if (p := path_of(x2)) is not None for t in tokens(p)}
                strs = {t for x2 in walk(a) if isinstance(x2, Str) for t in re.split(r"[_\W]+", x2.text.lower()) if t}
                hit = (toks | strs) & MONEY
                if not hit:
                    continue
                parsed = bool(strs & MONEY)
                signed = self._signed(a)
                yield self.finding(
                    ctx, x,
                    f"`Int()` truncates a float {'/'.join(sorted(hit))} toward zero",
                    f"Int(round({unparse(a)})) for a parsed quantity"
                    if parsed else f"Int(floor({unparse(a)} + 1e-9)) (explicit floor, absorbs division noise)",
                    confidence="medium" if parsed or signed else "low",
                    why="fractional or short positions truncate toward flat (0.6 -> 0, -1.5 -> -1), so a held "
                    "position reads as 0 or one share small" if parsed else
                    "2.9999999 (division noise) -> 2 drops a share; negative values round toward zero, not down",
                )  # fmt: skip

    @staticmethod
    def _nonneg(e: Node) -> bool:
        e = strip_casts(e)
        if isinstance(e, Call) and callee(e) in ("abs", "len", "sqrt", "exp") and isinstance(e.func, Name):
            return True
        if isinstance(e, BinOp) and e.op in ("*", "/"):
            lft = strip_casts(e.left)
            return (UnguardedDivision._nonneg(e.left) and UnguardedDivision._nonneg(e.right)) or (
                isinstance(lft, Call) and callee(lft) == "abs" and (num_value(e.right) or -1) > 0
            )
        return False

    @staticmethod
    def _signed(e: Node) -> bool:
        for x in walk(e):
            if isinstance(x, BinOp) and x.op == "-":
                return True
            if isinstance(x, Unary) and x.op == "-":
                return True
            if (p := path_of(x)) is not None and set(tokens(p)) & {"delta", "diff", "d", "chg", "ret", "pnl", "dq"}:
                return True
        return False


DYADIC_DEN = 1 << 10


def exact_literal(v: float) -> bool:
    return abs(v) < 1e15 and (v * DYADIC_DEN).is_integer()


class FloatEquality(Rule):
    """`==`/`!=` between two computed floats, or against a literal that is not exactly representable (0.1, 1e-4):
    after any arithmetic the values differ in the last bits, so the branch flips on rounding noise. Exact sentinel
    literals (0.0, 1.0, -1.0, 0.5) are allowed; set `MA203.strict` to flag them too."""

    id = "MA203"
    name = "float-equality"
    severity = "low"
    confidence = "medium"
    bad = "if w == target_w: skip()\nif frac == 0.1: ..."
    good = "if abs(w - target_w) <= 1e-12 * max(abs(w), abs(target_w)): skip()"
    why = "computed floats rarely compare equal; 0.1 + 0.2 != 0.3"
    options: ClassVar[dict[str, object]] = {"strict": False}

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        fx = facts(ctx)
        strict = bool(self.options.get("strict"))
        for s, root in stmt_walk(ctx):
            fn = s.func()
            if fn is not None and fn.fn and (fn.fn.name.startswith("__") or "eq" in fn.fn.name.lower()):
                continue
            for x in nodes(root):
                if not (isinstance(x, BinOp) and x.op in ("==", "!=")):
                    continue
                if unparse(x.left) == unparse(x.right):
                    continue
                f = fx.of(s)
                lv, rv = num_value(x.left), num_value(x.right)
                lit = lv if lv is not None else rv
                other = x.right if lv is not None else x.left
                if lv is not None and rv is not None:
                    continue
                if lit is not None:
                    if fx.ntype(other, f) != "f" or (exact_literal(lit) and not strict):
                        continue
                    comp = self._computed(other, f)
                    yield self.finding(
                        ctx, x,
                        f"float `{unparse(x)}` against literal {lit:g}",
                        f"abs({unparse(other)} - {lit:g}) <= 1e-9",
                        confidence="medium" if comp and not exact_literal(lit) else "low",
                        why=f"{lit:g} is not exactly representable; a computed value lands one ulp away"
                        if not exact_literal(lit)
                        else "exact sentinel compare; fine only if the value is assigned, never computed",
                    )  # fmt: skip
                    continue
                if fx.ntype(x.left, f) != "f" or fx.ntype(x.right, f) != "f":
                    continue
                if any(self._special(n) for n in (x.left, x.right)):
                    continue
                pl, pr = self._arr(x.left), self._arr(x.right)
                if pl is not None and pl == pr:
                    continue
                cl, cr = self._computed(x.left, f), self._computed(x.right, f)
                if not (cl or cr):
                    continue
                a, b = unparse(x.left), unparse(x.right)
                yield self.finding(
                    ctx, x,
                    f"exact compare of computed float `{unparse(x)}`",
                    f"abs({a} - {b}) <= tol (or `# mojoanalyzer: ignore[MA203]` if bit-exact equality is intended)",
                    confidence="medium",
                    why="arithmetic results differ in the last bits; tie/dedupe/branch flips on rounding noise",
                )  # fmt: skip

    @staticmethod
    def _special(n: Node) -> bool:
        if isinstance(n, Unary):
            n = n.operand
        if isinstance(n, Name) and is_const_name(n.id):
            return True
        if isinstance(n, Attr) and n.attr in ("MAX", "MIN", "MAX_FINITE", "MIN_FINITE"):
            return True
        return any(isinstance(y, Call) and re.search(r"inf|nan|max_finite", (callee(y) or "").lower()) for y in walk(n))

    @staticmethod
    def _arr(n: Node) -> str | None:
        return path_of(n.obj) if isinstance(n, Sub) else None

    def _computed(self, n: Node, f: Fn, depth: int = 0) -> bool:
        n = strip_casts(n)
        if isinstance(n, BinOp) and n.op in ("+", "-", "*", "/", "**"):
            return True
        if isinstance(n, Call) and isinstance(n.func, Name) and n.func.id in FLOAT_FUNCS - {"atof"}:
            return True
        if isinstance(n, Name) and depth < 3:
            defs = f.defs.get(n.id, [])
            return any(
                op in ("+=", "-=", "*=", "/=") or (v is not None and self._computed(v, f, depth + 1))
                for _, op, v in defs
                if op != "for"
            )
        return False


class NanCompare(Rule):
    """Self-comparison `x != x` / `x == x` (the NaN idiom; always False/True for non-floats and removed by
    fast-math), and comparisons against a NaN value, which are always False."""

    id = "MA204"
    name = "nan-compare"
    severity = "low"
    confidence = "high"
    bad = "if x != x: continue\nif y == nan[DType.float64](): ..."
    good = "if isnan(x): continue\nif isnan(y): ..."
    why = "NaN compares unequal to everything, including itself"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        fx = facts(ctx)
        for s, root in stmt_walk(ctx):
            for x in nodes(root):
                if not (isinstance(x, BinOp) and x.op in ORDER):
                    continue
                f = fx.of(s)
                for side, other in ((x.left, x.right), (x.right, x.left)):
                    if self._is_nan(side):
                        yield self.finding(
                            ctx, x,
                            f"comparison with NaN `{unparse(x)}` is always {'True' if x.op == '!=' else 'False'}",
                            f"{'not ' if x.op == '!=' else ''}isnan({unparse(other)})",
                            severity="high",
                            why="IEEE NaN is unordered: every ==, <, > against NaN is False",
                        )  # fmt: skip
                        break
                else:
                    if x.op not in ("==", "!=") or unparse(x.left) != unparse(x.right) or not pure(x.left):
                        continue
                    t = fx.ntype(x.left, f)
                    if t == "i":
                        yield self.finding(
                            ctx, x,
                            f"`{unparse(x)}` on an Int is always {'False' if x.op == '!=' else 'True'}",
                            "remove, or test the intended variable",
                            severity="high",
                            why="self-comparison of a non-float is constant; likely a typo for another variable",
                        )  # fmt: skip
                        continue
                    yield self.finding(
                        ctx, x,
                        f"NaN test via self-compare `{unparse(x)}`",
                        f"{'' if x.op == '!=' else 'not '}isnan({unparse(x.left)})  (from std.math import isnan)",
                        severity="info",
                        confidence="low",
                        why="opaque, and fast-math (-ffast-math/nnan) folds it to constant False, silently letting "
                        "NaN through",
                    )  # fmt: skip
            for x in nodes(root):
                if not (isinstance(x, BinOp) and x.op in ("==", "!=") and num_value(x.right) == 0):
                    continue
                d = x.left
                if isinstance(d, BinOp) and d.op == "-" and unparse(d.left) == unparse(d.right) and pure(d.left):
                    yield self.finding(
                        ctx, x,
                        f"finiteness test via `{unparse(x)}`",
                        f"{'' if x.op == '==' else 'not '}isfinite({unparse(d.left)})",
                        severity="info",
                        confidence="low",
                        why="x - x == 0 is False only for inf/NaN; fast-math folds it to True",
                    )  # fmt: skip

    @staticmethod
    def _is_nan(n: Node) -> bool:
        if isinstance(n, Call) and isinstance(n.func, Sub) and root_name(n.func) == "nan":
            return True
        if isinstance(n, Call) and isinstance(n.func, Name) and n.func.id == "nan":
            return True
        if isinstance(n, Attr) and n.attr in ("nan", "NaN", "NAN"):
            return True
        if isinstance(n, Call) and isinstance(n.func, Name) and n.func.id in FLOAT_CASTS and n.args:
            a = n.args[0]
            return isinstance(a, Seq) is False and unparse(a).strip("\"'").lower() == "nan"
        return False


class MathDomain(Rule):
    """`sqrt`/`log` of an expression that can leave the domain: `sqrt(s2/n - mu*mu)` goes slightly negative from
    cancellation, `log(a - b)` hits 0, `log(p1 / p0)` with an unchecked data price returns -inf/NaN."""

    id = "MA205"
    name = "math-domain"
    severity = "medium"
    confidence = "high"
    bad = "var sd = sqrt(s2 / n - mu * mu)\nr = log(px / prev)"
    good = "var sd = sqrt(max(s2 / n - mu * mu, 0.0))\nr = log(px / prev) if px > 0 and prev > 0 else 0.0"
    why = "NaN from a negative sqrt/log poisons every downstream sum, z-score and weight"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        fx = facts(ctx)
        for s, root in stmt_walk(ctx):
            for x in nodes(root):
                if not (isinstance(x, Call) and isinstance(x.func, Name) and len(x.args) == 1):
                    continue
                fname = x.func.id
                if fname not in ("sqrt", "log", "log2", "log10", "rsqrt"):
                    continue
                f = fx.of(s)
                a = x.args[0]
                got = self._diff(fx, f, a, s)
                if got is not None:
                    yield self.finding(
                        ctx, x,
                        f"`{fname}` of a difference `{unparse(got)}` with no clamp",
                        f"{fname}(max({unparse(a)}, {'0.0' if fname == 'sqrt' else 'eps'}))",
                        confidence="high" if fname in ("sqrt", "rsqrt") else "medium",
                        why="E[x^2] - E[x]^2 and similar differences go below 0 by rounding when variance ~ 0 "
                        f"(constant series) -> {fname} returns NaN" if fname in ("sqrt", "rsqrt") else
                        "a difference reaches 0 or below -> log returns -inf/NaN",
                    )  # fmt: skip
                    continue
                if fname.startswith("log") and isinstance(a, BinOp) and a.op == "/":
                    bad = [o for o in (a.left, a.right) if self._unchecked(fx, f, o)]
                    if len(bad) == 2 or (
                        bad and isinstance(strip_casts(a.right), (Sub, Attr, Name)) and bad[-1] is a.right
                    ):
                        names = ", ".join(unparse(b) for b in bad)
                        yield self.finding(
                            ctx, x,
                            f"`{fname}({unparse(a)})` with unchecked {names}",
                            f"{fname}(a / b) if a > 0 and b > 0 else <fallback>",
                            confidence="medium" if self._parsed_side(f, a) else "low",
                            why="a 0 or missing (0.0/negative sentinel) price gives log(0) = -inf or log(<0) = NaN, "
                            "which survives sums and sorts",
                        )  # fmt: skip

    def _diff(self, fx: Facts, f: Fn, a: Node, s: Stmt) -> Node | None:
        a = strip_casts(a)
        if isinstance(a, BinOp) and a.op in ("/", "*") and num_value(a.right) is not None:
            a = a.left
        if isinstance(a, BinOp) and a.op in ("/", "*") and isinstance(strip_casts(a.right), (Name, Call)):
            if is_len(strip_casts(a.right)) is not None or isinstance(strip_casts(a.right), Name):
                a = a.left
        while (
            isinstance(a, BinOp) and a.op == "+" and num_value(a.right) is not None and (num_value(a.right) or 0) <= 0
        ):
            a = a.left
        if isinstance(a, BinOp) and a.op == "+" and (num_value(a.right) or 0) > 0:
            return None
        if isinstance(a, BinOp) and a.op == "-" and num_value(a.left) is None and self._squarish(a.right):
            if guard_keys(a) & f.guards:
                return None
            return a
        if isinstance(a, Name):
            defs = f.defs.get(a.id, [])
            if guard_keys(a) & f.guards or not defs:
                return None
            vals = [v for _, op, v in defs if op == "="]
            if len(vals) == 1 and len(defs) == 1 and vals[0] is not None:
                inner = self._diff(fx, f, vals[0], s)
                return inner
        return None

    @staticmethod
    def _squarish(n: Node) -> bool:
        n = strip_casts(n)
        for x in walk(n):
            if isinstance(x, BinOp) and x.op == "*" and unparse(x.left) == unparse(x.right):
                return True
            if isinstance(x, BinOp) and x.op == "**":
                return True
            if isinstance(x, BinOp) and x.op == "*":
                ln, rn = {path_of(y) for y in walk(x.left)}, {path_of(y) for y in walk(x.right)}
                if ln & rn - {None}:
                    return True
        return False

    def _unchecked(self, fx: Facts, f: Fn, o: Node) -> bool:
        c = strip_casts(o)
        if num_value(c) is not None:
            return False
        if guard_keys(c) & f.guards:
            return False
        if isinstance(c, Name):
            if is_const_name(c.id):
                return False
            defs = f.defs.get(c.id, [])
            ud = UnguardedDivision()
            if ud._safe_name(fx, f, c.id, f.stmt or fx.ctx.mod):
                return False
            for _, op, v in defs:
                if op == "=" and isinstance(v, Call) and callee(v) in ("max", "exp", "abs"):
                    return False
            return True
        return isinstance(c, (Sub, Attr))

    @staticmethod
    def _parsed_side(f: Fn, a: Node) -> bool:
        for x in walk(a):
            if isinstance(x, Name):
                if any(
                    op == "=" and v is not None and UnguardedDivision._parsed(v) for _, op, v in f.defs.get(x.id, [])
                ):
                    return True
            elif isinstance(x, Call) and UnguardedDivision._parsed(x):
                return True
        return False


class IntTrueDivision(Rule):
    """`Int / Int` converted to a float: in Mojo `Int.__truediv__` is floor division returning `Int` (7 / 2 == 3),
    so `Float64(a / b)` silently drops the fraction."""

    id = "MA206"
    name = "int-true-division"
    severity = "high"
    confidence = "high"
    bad = "var frac = Float64(hits / total)"
    good = "var frac = Float64(hits) / Float64(total)"
    why = "Mojo Int / Int floors (7/2 == 3, -7/2 == -4); the float conversion happens after the fraction is gone"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        fx = facts(ctx)
        for s, root in stmt_walk(ctx):
            pm: dict[int, Node] | None = None
            for x in nodes(root):
                if not (isinstance(x, BinOp) and x.op == "/"):
                    continue
                if isinstance(x.left, Num) and isinstance(x.right, Num):
                    continue
                f = fx.of(s)
                if fx.ntype(x.left, f) != "i" or fx.ntype(x.right, f) != "i":
                    continue
                if pm is None:
                    pm = parent_map(root)
                cur: Node = x
                p = pm.get(id(cur))
                while isinstance(p, (BinOp, Unary)) and (not isinstance(p, BinOp) or p.op in ("+", "-", "*", "/")):
                    cur, p = p, pm.get(id(p))
                fctx = isinstance(p, Call) and isinstance(p.func, Name) and p.func.id in FLOAT_CASTS
                if fctx:
                    yield self.finding(
                        ctx, x,
                        f"`{unparse(x)}` is Int floor division inside `{p.func.id}()`",  # type: ignore[union-attr]
                        f"Float64({unparse(x.left)}) / "
                        + (f"{unparse(x.right)}.0" if isinstance(x.right, Num) else f"Float64({unparse(x.right)})"),
                    )  # fmt: skip
                else:
                    yield self.finding(
                        ctx, x,
                        f"`{unparse(x)}` on Int is floor division",
                        f"{unparse(x.left)} // {unparse(x.right)} (explicit) or Float64({unparse(x.left)}) / "
                        f"Float64({unparse(x.right)})",
                        severity="info",
                        confidence="low",
                        why="Python readers expect true division; `//` states the intent",
                    )  # fmt: skip


class OneSidedTolerance(Rule):
    """`a - b < eps` without `abs()`: true for every `a` far below `b`, so a "close enough" test passes for wildly
    different values."""

    id = "MA207"
    name = "one-sided-tolerance"
    severity = "medium"
    confidence = "medium"
    bad = "if px - target < 1e-9: done = True"
    good = "if abs(px - target) < 1e-9: done = True"
    why = "a - b < eps holds for any a < b, not just a ~= b"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for _, root in stmt_walk(ctx):
            for x in nodes(root):
                if not (isinstance(x, BinOp) and x.op in ("<", "<=", ">", ">=")):
                    continue
                if x.op in ("<", "<="):
                    diff, tol = x.left, x.right
                else:
                    diff, tol = x.right, x.left
                if not (isinstance(diff, BinOp) and diff.op == "-" and num_value(diff.right) is None):
                    continue
                if not self._tol(tol):
                    continue
                txt = unparse(root)
                mirror = unparse(BinOp(diff.tok, "-", diff.right, diff.left))
                if mirror in txt:
                    continue
                yield self.finding(
                    ctx, x,
                    f"one-sided tolerance `{unparse(x)}`",
                    f"abs({unparse(diff)}) {x.op if x.op in ('<', '<=') else {'>': '<', '>=': '<='}[x.op]} "
                    f"{unparse(tol)}",
                )  # fmt: skip

    @staticmethod
    def _tol(n: Node) -> bool:
        v = num_value(n)
        if v is not None:
            return 0 < v <= 1e-6
        p = path_of(n)
        return p is not None and bool(set(tokens(p)) & {"eps", "epsilon", "tol", "atol", "rtol", "tolerance"})


class SwappedClamp(Rule):
    """`min(max(x, A), B)` with A > B (or `max(min(x, A), B)` with A < B, `clamp(x, hi, lo)`): the result is the
    constant B regardless of x."""

    id = "MA208"
    name = "swapped-clamp"
    severity = "high"
    confidence = "high"
    bad = "var w = min(max(x, 1.0), -1.0)"
    good = "var w = min(max(x, -1.0), 1.0)"
    why = "with crossed bounds the clamp ignores its input and always returns one bound"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for _, root in stmt_walk(ctx):
            for x in nodes(root):
                if not (isinstance(x, Call) and isinstance(x.func, Name) and len(x.args) == 2 and not x.kw):
                    continue
                o = x.func.id
                if o == "clamp" and len(x.args) == 3:
                    continue
                if o not in ("min", "max"):
                    continue
                inner_op = "max" if o == "min" else "min"
                for i, a in enumerate(x.args):
                    if isinstance(a, Call) and isinstance(a.func, Name) and a.func.id == inner_op and len(a.args) == 2:
                        outer_b = x.args[1 - i]
                        for inner_b in a.args:
                            bad = self._crossed(o, inner_b, outer_b)
                            if bad:
                                yield self.finding(
                                    ctx, x,
                                    f"clamp bounds crossed in `{unparse(x)}`: always {unparse(outer_b)}",
                                    f"{o}({inner_op}(x, {unparse(outer_b)}), {unparse(inner_b)}) -> "
                                    f"swap the bounds",
                                    confidence=bad,
                                )  # fmt: skip
        for _, root in stmt_walk(ctx):
            for x in nodes(root):
                if isinstance(x, Call) and isinstance(x.func, Name) and x.func.id == "clamp" and len(x.args) == 3:
                    lo, hi = num_value(x.args[1]), num_value(x.args[2])
                    if lo is not None and hi is not None and lo > hi:
                        yield self.finding(
                            ctx, x,
                            f"`{unparse(x)}` has lower bound > upper bound",
                            f"clamp({unparse(x.args[0])}, {unparse(x.args[2])}, {unparse(x.args[1])})",
                        )  # fmt: skip

    @staticmethod
    def _crossed(outer: str, inner_b: Node, outer_b: Node) -> str | None:
        a, b = num_value(inner_b), num_value(outer_b)
        if a is not None and b is not None:
            if (outer == "min" and a > b) or (outer == "max" and a < b):
                return "high"
            return None
        pa, pb = path_of(inner_b), path_of(outer_b)
        if pa is None or pb is None:
            return None
        ta, tb = set(tokens(pa)), set(tokens(pb))
        hi, lo = {"hi", "high", "max", "upper", "ub", "cap", "ceil"}, {"lo", "low", "min", "lower", "lb", "floor"}
        if outer == "min" and ta & hi and tb & lo:
            return "medium"
        if outer == "max" and ta & lo and tb & hi:
            return "medium"
        return None


class SuspiciousIdentity(Rule):
    """Self-assignment `x = x`, identical operands (`a - a`, `a / a`, `x < x`, `c and c`), and `t if c else t`:
    almost always a typo for a different variable (go vet / staticcheck SA4000)."""

    id = "MA209"
    name = "suspicious-identity"
    severity = "high"
    confidence = "high"
    bad = "self.qty = self.qty\nvar spread = ask - ask"
    good = "self.qty = qty\nvar spread = ask - bid"
    why = "the expression is constant; the intended second operand is missing"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        fx = facts(ctx)
        for s, root in stmt_walk(ctx):
            if s.kind == "assign" and s.assign and len(s.assign[0]) == 1:
                t, v = s.assign[0][0], s.assign[1]
                if t is not None and v is not None and unparse(t) == unparse(v) and pure(v):
                    yield self.finding(
                        ctx,
                        s,
                        f"self-assignment `{unparse(t)} = {unparse(v)}`",
                        "assign the intended source (parameter or other field)",
                    )
                    continue
            for x in nodes(root):
                if isinstance(x, BinOp) and x.op in (
                    "-",
                    "/",
                    "//",
                    "%",
                    "<",
                    ">",
                    "<=",
                    ">=",
                    "and",
                    "or",
                    "^",
                    "&",
                    "|",
                ):
                    if unparse(x.left) == unparse(x.right) and pure(x.left) and num_value(x.left) is None:
                        if x.op in ("-", "/", "//", "<=", ">=") and fx.ntype(x.left, fx.of(s)) != "i":
                            continue
                        yield self.finding(
                            ctx, x, f"identical operands `{unparse(x)}`", "replace one side with the intended variable"
                        )
                elif isinstance(x, IfExp) and unparse(x.then) == unparse(x.other):
                    yield self.finding(
                        ctx,
                        x,
                        f"both arms equal in `{unparse(x)}`",
                        f"{unparse(x.then)} (or fix the arm that should differ)",
                        confidence="medium",
                    )


def chains(ctx: FileCtx) -> Iterator[list[Stmt]]:
    for blk in [ctx.mod.body, *(s.body for s in ctx.mod.walk() if s.body)]:
        cur: list[Stmt] = []
        for st in blk:
            if st.kind == "if":
                if cur:
                    yield cur
                cur = [st]
            elif st.kind in ("elif", "else") and cur and st.comptime == cur[0].comptime:
                cur.append(st)
            else:
                if cur:
                    yield cur
                cur = []
        if cur:
            yield cur


class DuplicateCondition(Rule):
    """The same condition twice in one `if`/`elif` chain: the later branch can never run."""

    id = "MA210"
    name = "duplicate-condition"
    severity = "high"
    confidence = "high"
    bad = "if side == 1:\n    buy()\nelif side == 1:\n    sell()"
    good = "if side == 1:\n    buy()\nelif side == -1:\n    sell()"
    why = "the first matching branch wins, so the duplicate branch is dead code"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for ch in chains(ctx):
            seen: dict[str, Stmt] = {}
            for st in ch:
                if st.kind == "else" or st.cond is None:
                    continue
                for c in self._atoms(st.cond):
                    k = unparse(c)
                    if k in seen and seen[k] is not st:
                        yield self.finding(
                            ctx, st,
                            f"condition `{k}` already tested at line {seen[k].line}; this branch is dead",
                            "fix the condition (likely a copy-paste of the earlier branch)",
                            confidence="high" if pure(c) else "medium",
                        )  # fmt: skip
                        break
                k0 = unparse(st.cond)
                seen.setdefault(k0, st)

    @staticmethod
    def _atoms(c: Node) -> list[Node]:
        out: list[Node] = [c]
        if isinstance(c, BinOp) and c.op == "or":
            out = []
            stack: list[Node] = [c]
            while stack:
                y = stack.pop()
                if isinstance(y, BinOp) and y.op == "or":
                    stack += [y.left, y.right]
                else:
                    out.append(y)
        return out


def body_text(st: Stmt) -> str:
    return "\n".join(" ".join(t.value for t in b.toks) + f"@{len(list(b.ancestors()))}" for b in st.walk())


class IdenticalBranches(Rule):
    """`if`/`else` (or a whole `if`/`elif`/`else` chain) whose branches have identical bodies: the condition has no
    effect, usually because one branch was copied and not edited (clippy if_same_then_else)."""

    id = "MA211"
    name = "identical-branches"
    severity = "medium"
    confidence = "medium"
    bad = "if side > 0:\n    px = bid\nelse:\n    px = bid"
    good = "if side > 0:\n    px = ask\nelse:\n    px = bid"
    why = "both paths do the same thing; the branch that should differ was not edited"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for ch in chains(ctx):
            if len(ch) < 2 or ch[-1].kind != "else":
                continue
            texts = [body_text(st) for st in ch]
            if texts[0] and all(t == texts[0] for t in texts[1:]):
                yield self.finding(
                    ctx, ch[0],
                    f"all {len(ch)} branches of this if/else have identical bodies",
                    "drop the condition or edit the branch that should differ",
                )  # fmt: skip


TERMINATORS = {"return", "raise", "break", "continue"}


class UnreachableCode(Rule):
    """Statements after `return`/`raise`/`break`/`continue` in the same block never execute."""

    id = "MA212"
    name = "unreachable-code"
    severity = "medium"
    confidence = "high"
    bad = "return pnl\nlog_fill(pnl)"
    good = "log_fill(pnl)\nreturn pnl"
    why = "code after an unconditional exit is dead; often a misplaced log/flush/state update"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for blk in [ctx.mod.body, *(s.body for s in ctx.mod.walk() if s.body)]:
            for a, b in itertools.pairwise(blk):
                if a.kind in TERMINATORS and b.kind not in ("elif", "else", "except", "finally", "docstring", "pass"):
                    if b.comptime or a.comptime:
                        continue
                    yield self.finding(
                        ctx, b, f"unreachable after `{a.kind}` on line {a.line}", "move it before the exit or delete it"
                    )


class EdgeIndex(Rule):
    """Index `xs[i - k]` in a loop starting at 0 (or `xs[i + k]` in a loop to `len(xs)`) with no test on `i`, and
    `range(len(xs) + 1)` / `xs[len(xs)]`: out of bounds on the first or last iteration. Mojo's `List` asserts on
    a negative index (crash), and with assertions off reads outside the buffer."""

    id = "MA213"
    name = "edge-index"
    severity = "high"
    confidence = "high"
    bad = "for i in range(len(px)):\n    r[i] = px[i] / px[i - 1] - 1.0"
    good = "for i in range(1, len(px)):\n    r[i] = px[i] / px[i - 1] - 1.0"
    why = "first/last iteration indexes outside the list"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        fx = facts(ctx)
        for st in ctx.mod.walk():
            if st.kind != "for" or not st.loop or len(st.loop[0]) != 1:
                continue
            ra = range_args(st.loop[1])
            if ra is None or (len(ra) == 3 and num_value(ra[2]) != 1):
                continue
            i = st.loop[0][0]
            start = num_value(ra[0]) if len(ra) >= 2 else 0.0
            end = ra[-1] if len(ra) == 1 else ra[1]
            hit = False
            for b in st.walk():
                for n in stmt_nodes(b):
                    for x in nodes(n):
                        if isinstance(x, Sub) and len(x.index) == 1 and isinstance(x.index[0], (Name, BinOp)):
                            ix0 = x.index[0]
                            if (isinstance(ix0, Name) and ix0.id == i) or (
                                isinstance(ix0, BinOp) and isinstance(ix0.left, Name) and ix0.left.id == i
                            ):
                                hit = True
            if not hit:
                continue
            skip: set[int] = set()
            for b in st.walk():
                if b.kind == "def" or (b.kind == "for" and b.loop and i in b.loop[0]):
                    skip.add(id(b))
                    skip.update(id(c) for c in b.walk())
            body = [b for b in st.walk() if id(b) not in skip]
            guarded = self._guarded(st, body, i)
            reported: set[str] = set()
            for b in body:
                for n in stmt_nodes(b):
                    for x in nodes(n):
                        if not (isinstance(x, Sub) and len(x.index) == 1 and not x.kw):
                            continue
                        ix = x.index[0]
                        obj = path_of(x.obj)
                        if obj is None or obj in reported:
                            continue
                        f = fx.of(b)
                        t = ctx.type_of(x.obj, f.env)
                        if t is not None and t.replace(" ", "").startswith(("Dict[", "String", "StringSlice")):
                            continue
                        if t is None and obj in f.env:
                            continue
                        known = t is not None and elem_type(t) is not None
                        if (
                            start == 0
                            and isinstance(ix, BinOp)
                            and ix.op == "-"
                            and isinstance(ix.left, Name)
                            and ix.left.id == i
                            and (num_value(ix.right) or 0) > 0
                            and not guarded
                        ):
                            reported.add(obj)
                            yield self.finding(
                                ctx, x,
                                f"`{unparse(x)}` at {i}=0 indexes {unparse(x.obj)}[-{unparse(ix.right)}]",
                                f"start the loop at {unparse(ix.right)}: range({unparse(ix.right)}, {unparse(end)})"
                                f" or guard `if {i} >= {unparse(ix.right)}`",
                                confidence="high" if known else "medium",
                                why="negative index on the first iteration: List asserts (crash) or reads garbage "
                                "with assertions off; a stale/last value would leak into the first row",
                            )  # fmt: skip
                        elif (
                            isinstance(ix, BinOp)
                            and ix.op == "+"
                            and isinstance(ix.left, Name)
                            and ix.left.id == i
                            and (num_value(ix.right) or 0) > 0
                            and is_len(end) is not None
                            and unparse(is_len(end)) == obj
                            and not guarded
                        ):
                            reported.add(obj)
                            yield self.finding(
                                ctx, x,
                                f"`{unparse(x)}` reaches {obj}[len({obj})] on the last iteration",
                                f"range(len({obj}) - {unparse(ix.right)})",
                                confidence="high" if known else "medium",
                                why="index one past the end on the final iteration: assert crash or OOB read",
                            )  # fmt: skip
                        elif (
                            isinstance(ix, Name)
                            and ix.id == i
                            and isinstance(end, BinOp)
                            and end.op == "+"
                            and (num_value(end.right) or 0) > 0
                            and is_len(end.left) is not None
                            and unparse(is_len(end.left)) == obj
                            and not guarded
                        ):
                            reported.add(obj)
                            yield self.finding(
                                ctx, x,
                                f"loop to `{unparse(end)}` indexes `{unparse(x)}` past the end",
                                f"range(len({obj}))",
                                why="the last iteration reads index len(xs)",
                            )  # fmt: skip
        for _, root in stmt_walk(ctx):
            for x in nodes(root):
                if isinstance(x, Sub) and len(x.index) == 1 and (lx := is_len(x.index[0])) is not None:
                    if unparse(lx) == unparse(x.obj):
                        yield self.finding(
                            ctx, x, f"`{unparse(x)}` is one past the end",
                            f"{unparse(x.obj)}[len({unparse(x.obj)}) - 1]",
                            why="valid indices are 0..len-1",
                        )  # fmt: skip

    @staticmethod
    def _guarded(loop: Stmt, body: list[Stmt], i: str) -> bool:
        for b in body:
            for n in stmt_nodes(b):
                for x in walk(n):
                    if isinstance(x, BinOp) and x.op in ORDER and i in {y.id for y in walk(x) if isinstance(y, Name)}:
                        return True
                    if (
                        isinstance(x, Call)
                        and callee(x) in ("max", "min")
                        and i in {y.id for y in walk(x) if isinstance(y, Name)}
                    ):
                        return True
        for a in loop.ancestors():
            if a.kind == "def":
                break
        return False


class DiscardedStatus(Rule):
    """`_ = f(...)` discarding a `Bool` success flag of an action (submit/cancel/send/write...) or the byte count of
    a raw write: a failed order/cancel or a partial write goes unnoticed."""

    id = "MA214"
    name = "discarded-status"
    severity = "medium"
    confidence = "medium"
    bad = "_ = cancel_order(http, oid)\n_ = c_write(fd, buf, n)"
    good = "if not cancel_order(http, oid):\n    log_err(oid)\nwrite_all(fd, buf, n)"
    why = "the call reports failure through its return value, which is thrown away"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            if s.kind != "assign" or not s.assign or len(s.assign[0]) != 1:
                continue
            t, v = s.assign
            if not (isinstance(t[0], Name) and t[0].id == "_" and isinstance(v, Call)):
                continue
            c = callee(v)
            if c is None:
                continue
            es = ctx.index.lookup(c, ctx.display) if isinstance(v.func, Name) else []
            rets = {e.info.ret for e in es}
            wr = isinstance(v.func, Name) and c in WRITE_FUNCS and (not rets or rets <= {"Int", "Int64", "Int32"})
            if wr or (
                isinstance(v.func, Sub)
                and root_name(v.func) == "external_call"
                and any("write" in unparse(a) or "send" in unparse(a) for a in v.func.index)
            ):
                yield self.finding(
                    ctx, s, f"byte count of `{c}(...)` discarded",
                    "check the return: loop until all bytes are written, treat < 0 as an error",
                    why="write/send may write fewer bytes than asked or fail (-1); the payload is silently truncated",
                )  # fmt: skip
                continue
            if rets == {"Bool"} and ACTION_WORDS.search(c.lower()):
                yield self.finding(
                    ctx, s, f"Bool status of `{c}(...)` discarded",
                    f"if not {c}(...): <log/retry/abort>",
                )  # fmt: skip
            elif rets == {"Bool"}:
                yield self.finding(
                    ctx, s, f"Bool result of `{c}(...)` discarded",
                    f"if not {c}(...): <handle>", confidence="low",
                )  # fmt: skip


class UnitScale(Rule):
    """A `*bps*` value used in arithmetic with no 1e4 / 1e-4 scaling in the statement, or `1 + pct` with no
    1/100 scaling: off by 10000x / 100x (heuristic)."""

    id = "MA215"
    name = "unit-scale"
    severity = "medium"
    confidence = "low"
    bad = "var fill = px * (1.0 + slip_bps)"
    good = "var fill = px * (1.0 + slip_bps * 1e-4)"
    why = "basis points are 1/10000; mixing them with fractions misprices by 10000x"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        scaled: set[str] = set()
        for s, root in stmt_walk(ctx):
            tgt = None
            if s.kind == "assign" and s.assign and s.assign[0] and s.assign[0][0] is not None:
                tgt = path_of(s.assign[0][0])
            elif s.kind == "var" and s.decl and len(s.decl[0]) == 1:
                tgt = s.decl[0][0]
            if tgt and any((v := num_value(x)) is not None and v in (1e4, 1e-4, 1e2, 1e-2) for x in nodes(root)):
                scaled.add(tgt.split(".")[-1])
        for s, root in stmt_walk(ctx):
            if s.kind in ("if", "elif", "while", "assert"):
                continue
            vals = [num_value(x) for x in nodes(root)]
            consts = [x.id for x in nodes(root) if isinstance(x, Name) and is_const_name(x.id)]
            for x in nodes(root):
                if not (isinstance(x, BinOp) and x.op in ("+", "-")):
                    continue
                for a, b in ((x.left, x.right), (x.right, x.left)):
                    p = path_of(a)
                    if p is None or num_value(b) != 1 or p.split(".")[-1] in scaled:
                        continue
                    tk = set(tokens(p))
                    unit = (
                        "bps"
                        if "bps" in tk or ("bp" in tk and "bps" in p.lower())
                        else ("pct" if tk & {"pct", "percent"} else None)
                    )
                    if unit is None:
                        continue
                    want = (1e4, 1e-4) if unit == "bps" else (1e2, 1e-2)
                    if any(v is not None and any(abs(v - w) < 1e-12 * max(1, w) for w in want) for v in vals):
                        continue
                    if any(unit.upper() in c or "SCALE" in c for c in consts):
                        continue
                    yield self.finding(
                        ctx, x,
                        f"`{unparse(x)}` adds a {unit} value to 1 without scaling",
                        f"1.0 {x.op} {p} * {'1e-4' if unit == 'bps' else '0.01'}",
                    )  # fmt: skip
                    break
