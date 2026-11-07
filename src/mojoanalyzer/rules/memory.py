from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import TypeGuard

from ..core import (
    FileCtx,
    Finding,
    Rule,
    all_nodes,
    body_stmts,
    has_kind,
    is_list_type,
    may_mutate,
    range_args,
    range_unit_step,
    stmt_nodes,
    trip_text,
)
from ..expr import Attr, BinOp, Call, Name, Node, Num, Seq, Str, Sub, names, path_of, root_name, unparse, walk
from ..parser import Param, Stmt
from ._util import readonly_uses

HEAVY = ("List[", "Dict[", "String", "Set[", "Deque[", "InlineArray[")
SCALARS = {
    "Int", "Int8", "Int16", "Int32", "Int64", "UInt", "UInt8", "UInt16", "UInt32", "UInt64", "Float16", "Float32",
    "Float64", "BFloat16", "Bool",
}  # fmt: skip


def blocks(mod: Stmt) -> Iterator[list[Stmt]]:
    yield mod.body
    for s in mod.walk():
        if s.body:
            yield s.body


def _empty_list_ctor(n: Node | None) -> str | None:
    if isinstance(n, Call) and not n.args and not n.kw and isinstance(n.func, Sub):
        if isinstance(n.func.obj, Name) and n.func.obj.id == "List":
            return unparse(n.func)
    return None


class ListReserve(Rule):
    """Empty `List` filled by an unconditional `append` in the loop that immediately follows: the count is known,
    so allocate once (`List[T](capacity=n)`, or `length=n, fill=v` for a constant)."""

    id = "MA106"
    name = "list-reserve"
    severity = "medium"
    bad = "var xs = List[Int]()\nfor i in range(n):\n    xs.append(f(i))"
    good = "var xs = List[Int](capacity=n)\nfor i in range(n):\n    xs.append(f(i))"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for blk in blocks(ctx.mod):
            for k, st in enumerate(blk):
                got = self._decl(st)
                if got is None:
                    continue
                name, typ = got
                loop = None
                for nxt in blk[k + 1 :]:
                    mentions = any(name in names(n) for n in stmt_nodes(nxt)) or any(
                        name in names(n) for b in nxt.walk() for n in stmt_nodes(b)
                    )
                    if not mentions:
                        if nxt.body or nxt.kind in ("return", "break", "continue", "raise"):
                            break
                        continue
                    loop = nxt
                    break
                if loop is None or loop.kind != "for" or loop.comptime or not loop.loop:
                    continue
                count = self._count(ctx, loop)
                if count is None:
                    continue
                app = self._single_append(loop, name)
                if app is None:
                    continue
                arg = app.args[0]
                ivars = set(loop.loop[0])
                if isinstance(arg, (Num, Str)) or (
                    isinstance(arg, Name) and arg.id not in ivars and not _assigned_in(loop.body, arg.id)
                ):
                    tip = f"{typ}(length={count}, fill={unparse(arg)}) and drop the loop"
                else:
                    tip = f"{typ}(capacity={count})"
                lit = count.isdigit() and int(count) <= 64
                sev = "low" if lit or not (st.enclosing_loops() or loop.enclosing_loops()) else "medium"
                yield self.finding(
                    ctx, st, f"`{name}` grows by append in a loop of known trip count {count}", tip, severity=sev
                )

    def _decl(self, st: Stmt) -> tuple[str, str] | None:
        if st.kind == "var" and st.decl and len(st.decl[0]) == 1 and st.toks[0].value == "var":
            nm, typ, val = st.decl
            ctor = _empty_list_ctor(val)
            if ctor:
                return nm[0], ctor
            if typ and typ.startswith("List[") and isinstance(val, Seq) and val.kind == "list" and not val.items:
                return nm[0], typ
        if st.kind == "assign" and st.assign and len(st.assign[0]) == 1 and isinstance(st.assign[0][0], Name):
            ctor = _empty_list_ctor(st.assign[1])
            if ctor:
                return st.assign[0][0].id, ctor
        return None

    def _count(self, ctx: FileCtx, loop: Stmt) -> str | None:
        assert loop.loop is not None
        _tgt, it = loop.loop
        ra = range_args(it)
        if ra is not None:
            return trip_text(ra) if range_unit_step(it) else None
        p = path_of(it) if it is not None else None
        if p is None:
            return None
        env = ctx.env(loop.func())
        t = ctx.resolve(env.get(p), env)
        if t and t.replace(" ", "").startswith(("List[", "Span[", "InlineArray[", "Set[")):
            return f"len({p})"
        return None

    def _single_append(self, loop: Stmt, name: str) -> Call | None:
        if has_kind(loop.body, "break", "continue", "return", "raise", "yield", "def"):
            return None
        app: Call | None = None
        for b in loop.body:
            e = b.expr if b.kind == "expr" else None
            if (
                isinstance(e, Call)
                and isinstance(e.func, Attr)
                and isinstance(e.func.obj, Name)
                and e.func.obj.id == name
                and e.func.attr == "append"
                and len(e.args) == 1
                and not e.kw
            ):
                if app is not None:
                    return None
                app = e
                if name in names(e.args[0]):
                    return None
                continue
        if app is None:
            return None
        hits = sum(1 for _, x in all_nodes(loop.body) if isinstance(x, Name) and x.id == name)
        return app if hits == 1 else None


def _assigned_in(stmts: list[Stmt], name: str) -> bool:
    from ..core import assigned_names

    return name in assigned_names(stmts)


class StringConcatLoop(Rule):
    """String built with `+`/`String(x)` temporaries inside a loop: each iteration allocates temporaries.
    Append in place with `s.write(a, b, ...)`."""

    id = "MA107"
    name = "string-concat-loop"
    severity = "low"
    bad = 'for i in range(n):\n    s += String(i) + ","'
    good = 'for i in range(n):\n    s.write(i, ",")'

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            if not s.enclosing_loops():
                continue
            tgt = rhs = None
            if s.kind == "augassign" and s.aug and s.aug[1] == "+=":
                tgt, _, rhs = s.aug
            elif s.kind == "assign" and s.assign and len(s.assign[0]) == 1:
                t, v = s.assign[0][0], s.assign[1]
                if isinstance(v, BinOp) and v.op == "+" and t is not None:
                    parts = _flatten(v)
                    if unparse(parts[0]) == unparse(t):
                        tgt, rhs = t, _rebuild(parts[1:])
            if tgt is None or rhs is None:
                continue
            p = path_of(tgt)
            if p is None:
                continue
            env = ctx.env(s.func())
            if ctx.type_of(tgt, env) != "String":
                continue
            parts = _flatten(rhs)
            convs = [x for x in parts if _string_call(x) is not None]
            if len(parts) < 2 and not convs:
                continue
            if all(isinstance(x, Str) for x in parts):
                continue
            args = ", ".join(unparse(_string_call(x) or x) for x in parts)
            yield self.finding(
                ctx, s, f"string `{p}` extended with temporary concatenation in a loop", f"{p}.write({args})"
            )


def _string_call(n: Node) -> Node | None:
    if isinstance(n, Call) and isinstance(n.func, Name) and n.func.id == "String" and len(n.args) == 1 and not n.kw:
        return n.args[0]
    return None


def _flatten(n: Node) -> list[Node]:
    if isinstance(n, BinOp) and n.op == "+":
        return _flatten(n.left) + _flatten(n.right)
    return [n]


def _rebuild(parts: list[Node]) -> Node | None:
    if not parts:
        return None
    out = parts[0]
    for p in parts[1:]:
        out = BinOp(p.tok, "+", out, p)
    return out


class DictDoubleLookup(Rule):
    """`if k in d:` followed by `d[k]`: two hash lookups (and `d[k]` raises). Use one `d.find(k)`."""

    id = "MA108"
    name = "dict-double-lookup"
    severity = "low"
    bad = "if k in d:\n    s += d[k]"
    good = "var v = d.find(k)\nif v:\n    s += v.value()"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            if s.kind not in ("if", "elif") or s.comptime:
                continue
            c = s.cond
            if not (isinstance(c, BinOp) and c.op == "in"):
                continue
            d, k = path_of(c.right), c.left
            if d is None or not isinstance(k, (Name, Attr, Num, Str)):
                continue
            env = ctx.env(s.func())
            t = ctx.resolve(env.get(d), env)
            if not t or not t.replace(" ", "").startswith("Dict["):
                continue
            inner = t.replace(" ", "")[5:-1]
            depth = 0
            val = ""
            for i, ch in enumerate(inner):
                if ch in "[(":
                    depth += 1
                elif ch in "])":
                    depth -= 1
                elif ch == "," and depth == 0:
                    val = inner[i + 1 :]
                    break
            if val not in SCALARS:
                continue
            hit = self._first_read(s.body, d, k)
            if hit is None:
                continue
            ks = unparse(k)
            yield self.finding(
                ctx, s, f"`{ks} in {d}` then `{d}[{ks}]`: two lookups",
                f"var v = {d}.find({ks}); if v: ... v.value()",
            )  # fmt: skip

    def _first_read(self, body: list[Stmt], d: str, k: Node) -> Sub | None:
        kn = names(k)
        for b in body_stmts(body):
            if b.kind == "def":
                return None
            if b.kind == "assign" and b.assign:
                for t in b.assign[0]:
                    if t is not None and (path_of(t) == d or (root_name(t) in kn) or _is_dk(t, d, k)):
                        return None
            if b.kind == "augassign" and b.aug and b.aug[0] is not None:
                t = b.aug[0]
                if _is_dk(t, d, k) or root_name(t) in kn or path_of(t) == d:
                    return None
            if b.kind == "var" and b.decl and set(b.decl[0]) & kn:
                return None
            for n in stmt_nodes(b):
                for x in walk(n):
                    if isinstance(x, Call) and isinstance(x.func, Attr) and path_of(x.func.obj) == d:
                        if x.func.attr not in ("find", "get", "__contains__", "keys", "values", "items"):
                            return None
                    if _is_dk(x, d, k):
                        return x
        return None


def _is_dk(x: Node, d: str, k: Node) -> TypeGuard[Sub]:
    return isinstance(x, Sub) and path_of(x.obj) == d and len(x.index) == 1 and unparse(x.index[0]) == unparse(k)


class CopyInLoop(Rule):
    """`var x = expr.copy()` inside a loop where `x` is only read: bind a reference instead (`ref x = expr`),
    avoiding a deep copy (allocation) per iteration."""

    id = "MA109"
    name = "copy-in-loop"
    severity = "medium"
    bad = "for i in range(n):\n    var row = rows[i].copy()\n    s += row[0]"
    good = "for i in range(n):\n    ref row = rows[i]\n    s += row[0]"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            if s.kind != "var" or s.toks[0].value != "var" or not s.decl or len(s.decl[0]) != 1:
                continue
            if not s.enclosing_loops() or s.parent is None:
                continue
            name, typ, val = s.decl
            x = name[0]
            if not (isinstance(val, Call) and isinstance(val.func, Attr) and val.func.attr == "copy"):
                continue
            if val.args or val.kw:
                continue
            src = val.func.obj
            if any(isinstance(y, Call) for y in walk(src)) or (path_of(src) is None and not isinstance(src, Sub)):
                continue
            env = ctx.env(s.func())
            t = typ or ctx.type_of(src, env)
            if t in SCALARS or (t and t.startswith(("SIMD[", "Scalar["))):
                continue
            sib = s.parent.body
            rest = sib[sib.index(s) + 1 :]
            r = root_name(src)
            if r is None or not readonly_uses(rest, x, ctx.index) or may_mutate(rest, r, ctx.index):
                continue
            if not any(isinstance(y, Name) and y.id == x for _, y in all_nodes(rest)):
                continue
            yield self.finding(
                ctx,
                s,
                f"`{x}` deep-copies `{unparse(src)}` every iteration but is only read",
                f"ref {x} = {unparse(src)}",
            )


class VarArgReadOnly(Rule):
    """`var` (owned) argument of a heap type that the body only reads: callers must copy or move into it.
    Use the default read convention; existing `f(x^)` call sites still compile."""

    id = "MA110"
    name = "owned-arg-read-only"
    severity = "low"
    risk = "api"
    bad = "def total(var xs: List[Float64]) -> Float64:\n    return xs[0]"
    good = "def total(xs: List[Float64]) -> Float64:\n    return xs[0]"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        trait_methods = {
            e.info.name
            for es in ctx.index.funcs.values()
            for e in es
            if e.stmt.parent and e.stmt.parent.kind == "trait"
        }
        for s in ctx.defs():
            info = s.fn
            if info is None or info.name.startswith("__") or info.name in trait_methods:
                continue
            if s.parent is None or s.parent.kind == "trait" or s.func() is not None:
                continue
            if not s.body or (len(s.body) == 1 and s.body[0].kind in ("pass", "expr") and s.body[0].text() == "..."):
                continue
            for p in info.params:
                if p.convention not in ("var", "owned") or not p.type.startswith(HEAVY):
                    continue
                if not readonly_uses(s.body, p.name, ctx.index):
                    continue
                yield self.finding(
                    ctx, p.tok, f"owned `var {p.name}: {p.type}` is only read in {info.name}()",
                    "drop `var` (read convention) so callers need not copy",
                )  # fmt: skip


class QuadraticListOps(Rule):
    """`List.insert(0, x)` / `List.pop(0)` in a loop are O(n) each (O(n^2) total): use `Deque`
    (`appendleft`/`popleft`)."""

    id = "MA115"
    name = "list-front-ops"
    severity = "high"
    bad = "for i in range(n):\n    xs.insert(0, i)"
    good = "var xs = Deque[Int]()\nfor i in range(n):\n    xs.appendleft(i)"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            if not s.enclosing_loops() or s.kind in ("for", "while"):
                continue
            env = ctx.env(s.func())
            for n in stmt_nodes(s):
                for x in walk(n):
                    if not (isinstance(x, Call) and isinstance(x.func, Attr)):
                        continue
                    m = x.func.attr
                    front = x.args and isinstance(x.args[0], Num) and x.args[0].text == "0"
                    if not front or (m, len(x.args)) not in (("insert", 2), ("pop", 1)):
                        continue
                    p = path_of(x.func.obj)
                    if p is None or not is_list_type(ctx.resolve(env.get(p), env)):
                        continue
                    alt = "appendleft" if m == "insert" else "popleft"
                    call = f"{p}.insert(0, ...)" if m == "insert" else f"{p}.pop(0)"
                    yield self.finding(ctx, x, f"`{call}` in a loop shifts every element", f"Deque + {alt}()")


class ListMembership(Rule):
    """`x in xs` on a `List` inside a loop is a linear scan: keep a `Set` (or `Dict`) for membership."""

    id = "MA116"
    name = "list-membership"
    severity = "medium"
    confidence = "medium"
    bad = "for i in range(n):\n    if i in seen:  # seen: List[Int]\n        hits += 1"
    good = "var seen = Set[Int]()  # ...\nfor i in range(n):\n    if i in seen:\n        hits += 1"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            if not s.enclosing_loops() or s.kind == "for":
                continue
            fn = s.func()
            env = ctx.env(fn)
            for n in stmt_nodes(s):
                for x in walk(n):
                    if not (isinstance(x, BinOp) and x.op in ("in", "not in")):
                        continue
                    p = path_of(x.right)
                    if p is None or not is_list_type(ctx.resolve(env.get(p), env)):
                        continue
                    if fn is not None and self._small_literal(fn, p):
                        continue
                    yield self.finding(
                        ctx, x, f"linear `{x.op}` scan of List `{p}` inside a loop", f"maintain a Set for `{p}` lookups"
                    )

    def _small_literal(self, fn: Stmt, p: str) -> bool:
        for s in fn.walk():
            if s.kind == "var" and s.decl and s.decl[0] == [p]:
                v = s.decl[2]
                if isinstance(v, Seq) and len(v.items) <= 16:
                    return True
        return False


class CopyIntoReadArg(Rule):
    """`f(x.copy())` where `f` takes that argument by the default read convention: the copy is discarded
    unread. Pass `x` directly."""

    id = "MA119"
    name = "copy-into-read-arg"
    severity = "low"
    bad = "def f(xs: List[Int]) -> Int: ...\nf(ys.copy())"
    good = "f(ys)"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            for n in stmt_nodes(s):
                for c in walk(n):
                    if not isinstance(c, Call):
                        continue
                    fname = c.func.id if isinstance(c.func, Name) else c.func.attr if isinstance(c.func, Attr) else None
                    if fname is None:
                        continue
                    es = ctx.index.lookup(fname, ctx.display)
                    if not es:
                        continue
                    method = isinstance(c.func, Attr)
                    for i, a in enumerate(c.args):
                        if not (isinstance(a, Call) and isinstance(a.func, Attr) and a.func.attr == "copy"):
                            continue
                        if a.args or a.kw:
                            continue
                        r = root_name(a.func.obj)
                        if r is None or any(r in names(o) for o in c.args if o is not a):
                            continue
                        if not all(self._read_at(e.info.params, i, method) for e in es):
                            continue
                        yield self.finding(
                            ctx, a, f"copy passed to read-only parameter of {fname}()",
                            f"pass `{unparse(a.func.obj)}` without .copy()",
                        )  # fmt: skip

    def _read_at(self, params: list[Param], i: int, method: bool) -> bool:
        ps = list(params)
        if ps and ps[0].name == "self":
            if not method:
                return False
            ps = ps[1:]
        elif method:
            return False
        if i >= len(ps):
            return False
        p = ps[i]
        return p.convention in ("read", "borrowed") and bool(p.type) and not p.type.startswith(("Pointer", "Unsafe"))


__all__ = [
    "CopyInLoop",
    "CopyIntoReadArg",
    "DictDoubleLookup",
    "ListMembership",
    "ListReserve",
    "QuadraticListOps",
    "StringConcatLoop",
    "VarArgReadOnly",
]
