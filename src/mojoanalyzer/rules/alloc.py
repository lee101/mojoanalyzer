from __future__ import annotations

from collections.abc import Iterable, Iterator

from ..core import (
    PURE_BUILTINS,
    READONLY_METHODS,
    FileCtx,
    Finding,
    Rule,
    all_nodes,
    assigned_names,
    body_stmts,
    callee,
    elem_type,
    hot_depth,
    loop_called,
    may_mutate,
    range_args,
    stmt_nodes,
)
from ..expr import Attr, BinOp, Call, Name, Node, Seq, Str, Sub, Transfer, names, path_of, root_name, unparse, walk
from ..parser import Stmt
from ._util import is_numeric_elem, parent_map, readonly_uses

CONTAINERS = ("List", "Dict", "Set", "String")
GROW = {"List": {"append", "extend", "insert", "resize"}, "Set": {"add"}, "Dict": {"setdefault"}, "String": {"write"}}
RESET = {"List": "{x}.clear()", "Dict": "{x}.clear()", "Set": "{x}.clear()", "String": "{x}.resize(0)"}
LOCAL_METHODS = READONLY_METHODS | {
    "append", "extend", "insert", "clear", "pop", "resize", "add", "remove", "discard", "setdefault", "write",
    "reverse", "unsafe_ptr", "__setitem__", "__getitem__", "update", "swap_elements",
}  # fmt: skip
SCALAR_T = {
    "Int", "Int8", "Int16", "Int32", "Int64", "UInt", "UInt8", "UInt16", "UInt32", "UInt64", "Float16", "Float32",
    "Float64", "BFloat16", "Bool",
}  # fmt: skip


def _head(n: Node | None) -> str | None:
    f = n.func if isinstance(n, Call) else None
    if isinstance(f, Sub) and isinstance(f.obj, Name):
        return f.obj.id
    if isinstance(f, Name):
        return f.id
    return None


def _rest(s: Stmt) -> list[Stmt]:
    if s.parent is None:
        return []
    sib = s.parent.body
    return sib[sib.index(s) + 1 :]


def _after(s: Stmt, stop: Stmt | None) -> Iterator[Stmt]:
    """Statements that run after `s` up to the end of `stop`'s body (an ancestor), in source order."""
    cur: Stmt = s
    while cur.parent is not None and cur is not stop:
        yield from _rest(cur)
        if cur.parent is stop:
            break
        cur = cur.parent


def _loop_variant(loop: Stmt) -> set[str]:
    v = assigned_names(loop.body)
    if loop.kind == "for" and loop.loop:
        v |= set(loop.loop[0])
    for b in body_stmts(loop.body):
        if b.kind in ("except", "with"):
            toks = [t.value for t in b.toks]
            for kw in ("as", "except"):
                if kw in toks and toks.index(kw) + 1 < len(toks):
                    v.add(toks[toks.index(kw) + 1])
    return v


def _invariant(n: Node, loop: Stmt, ctx: FileCtx, allow_calls: frozenset[str] = frozenset()) -> bool:
    var = _loop_variant(loop)
    for x in walk(n):
        if isinstance(x, Name) and x.id in var:
            return False
        if isinstance(x, Call) and x is not n:
            c = callee(x)
            if isinstance(x.func, Attr) and c not in READONLY_METHODS:
                return False
            if not isinstance(x.func, Attr) and c not in PURE_BUILTINS and c not in allow_calls:
                return False
    return all(not may_mutate(loop.body, r, ctx.index) for r in names(n))


def _local_only(stmts: list[Stmt], x: str, ctx: FileCtx) -> bool:
    """Every use of `x` keeps the value inside this scope: method calls, indexing, reads by builtins/read params."""
    for s in body_stmts(stmts):
        if s.kind in ("def", "struct", "return", "yield", "raise"):
            if any(x in names(n) for n in stmt_nodes(s)) or s.kind in ("def", "struct"):
                if s.kind in ("def", "struct") and not any(
                    isinstance(n, Name) and n.id == x for b in s.walk() for n in _all(b)
                ):
                    continue
                return False
        if s.kind == "var" and s.decl and x in s.decl[0]:
            return False
        if s.kind == "assign" and s.assign:
            for t in s.assign[0]:
                if isinstance(t, Name) and t.id == x:
                    return False
            if isinstance(s.assign[1], Name) and s.assign[1].id == x:
                return False
        if s.kind == "var" and s.decl and isinstance(s.decl[2], Name) and s.decl[2].id == x:
            return False
        for n in stmt_nodes(s):
            pm = parent_map(n)
            for y in walk(n):
                if not (isinstance(y, Name) and y.id == x):
                    continue
                p = pm.get(id(y))
                if p is None:
                    if s.kind == "for" or (s.kind in ("if", "elif", "while", "expr")):
                        continue
                    if s.kind == "augassign" and s.aug and s.aug[0] is y:
                        continue
                    return False
                if isinstance(p, Transfer):
                    return False
                if isinstance(p, Sub) and p.obj is y:
                    continue
                if isinstance(p, Attr) and p.obj is y:
                    gp = pm.get(id(p))
                    if isinstance(gp, Call) and gp.func is p and p.attr not in LOCAL_METHODS:
                        return False
                    continue
                if isinstance(p, BinOp):
                    continue
                if isinstance(p, Call) and p.func is not y:
                    c = callee(p)
                    if c in PURE_BUILTINS | {"print"}:
                        continue
                    if isinstance(p.func, Attr) and p.func.attr == "write":
                        continue
                    if c and _param_conv_ok(ctx, c, p, y):
                        continue
                return False
    return True


def _all(s: Stmt) -> Iterator[Node]:
    for n in stmt_nodes(s):
        yield from walk(n)


def _param_conv_ok(ctx: FileCtx, c: str, call: Call, arg: Node) -> bool:
    es = ctx.index.lookup(c, ctx.display)
    if not es or isinstance(call.func, Attr):
        return False
    if arg not in call.args:
        return False
    i = next(k for k, a in enumerate(call.args) if a is arg)
    for e in es:
        ps = [p for p in e.info.params if p.name != "self"]
        if i >= len(ps) or ps[i].convention not in ("read", "mut", "borrowed", "inout"):
            return False
    return True


def _grows(stmts: list[Stmt], x: str, kind: str) -> bool:
    for s in body_stmts(stmts):
        if kind == "String" and s.kind == "augassign" and s.aug and isinstance(s.aug[0], Name) and s.aug[0].id == x:
            return True
        if kind == "Dict" and s.kind == "assign" and s.assign:
            if any(isinstance(t, Sub) and isinstance(t.obj, Name) and t.obj.id == x for t in s.assign[0]):
                return True
        for n in stmt_nodes(s):
            for y in walk(n):
                if isinstance(y, Call) and isinstance(y.func, Attr) and isinstance(y.func.obj, Name):
                    if y.func.obj.id == x and y.func.attr in GROW[kind]:
                        return True
    return False


def _decl_count(fn: Stmt | None, x: str) -> int:
    if fn is None:
        return 99
    k = 0
    for s in fn.walk():
        if (s.kind == "var" and s.decl and x in s.decl[0]) or (s.kind == "for" and s.loop and x in s.loop[0]):
            k += 1
    if fn.fn and any(p.name == x for p in fn.fn.params):
        k += 1
    return k


def _hoist_target(s: Stmt, ctor: Node, ctx: FileCtx) -> Stmt | None:
    best = None
    for loop in s.enclosing_loops():
        if loop.comptime or not _invariant(ctor, loop, ctx):
            break
        best = loop
    return None if best is None or _tiny_loop(best, ctx) else best


def _tiny_loop(loop: Stmt, ctx: FileCtx) -> bool:
    if loop.kind != "for" or not loop.loop:
        return False
    it = loop.loop[1]
    if isinstance(it, Seq) and len(it.items) <= 4:
        return True
    ra = range_args(it)
    if ra is not None and len(ra) == 1:
        k = ctx.comptime_int(ra[0], loop.func())
        return k is not None and k <= 4
    return False


def _hot_sev(ctx: FileCtx, s: Stmt) -> str:
    fn = s.func()
    called = fn is not None and fn.fn is not None and fn.fn.name in loop_called(ctx)
    return "medium" if hot_depth(s) >= 2 or called else "low"


class AllocInLoop(Rule):
    """A `List`/`Dict`/`Set`/`String` declared inside a loop and grown there allocates (and frees) its buffer
    every iteration. Hoist the declaration above the loop and reset it in place (`clear()`, `resize(0)` for
    String): capacity is kept, so after the first iteration no allocation happens. Also `alloc[T](n)` freed in
    the same iteration. Risk: the buffer's peak capacity stays live until the loop ends."""

    id = "MA301"
    name = "alloc-in-loop"
    severity = "medium"
    bad = "for i in range(n):\n    var row = List[Float64]()\n    for j in range(k):\n        row.append(x[i + j])"
    good = (
        "var row = List[Float64]()\nfor i in range(n):\n    row.clear()\n"
        "    for j in range(k):\n        row.append(x[i + j])"
    )
    why = "each iteration pays malloc + free (+ regrowth copies); measured 20.0M -> 101 allocations, 5.4x"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            if s.kind != "var" or s.toks[0].value != "var" or not s.decl or len(s.decl[0]) != 1:
                continue
            loops = s.enclosing_loops()
            if not loops or s.parent is None:
                continue
            x, _typ, val = s.decl
            nm = x[0]
            if isinstance(val, Call) and _head(val) == "alloc":
                yield from self._alloc(ctx, s, nm, val)
                continue
            kind = _head(val)
            if kind not in CONTAINERS or not isinstance(val, Call):
                continue
            if kind == "String":
                if val.kw or len(val.args) > 1 or (val.args and not (isinstance(val.args[0], Str))):
                    continue
                if val.args and isinstance(val.args[0], Str) and val.args[0].text not in ('""', "''"):
                    continue
            elif val.args or any(k != "capacity" for k, _ in val.kw):
                continue
            rest = _rest(s)
            if not _grows(rest, nm, kind) or not _local_only(rest, nm, ctx):
                continue
            if _decl_count(s.func(), nm) != 1:
                continue
            tgt = _hoist_target(s, val, ctx)
            if tgt is None:
                continue
            ctor = unparse(val)
            reset = RESET[kind].format(x=nm)
            yield self.finding(
                ctx, s, f"`{nm}` = {ctor} is allocated and freed every iteration of the loop at L{tgt.line}",
                f"hoist `var {nm} = {ctor}` above L{tgt.line}; `{reset}` here (keeps capacity)",
                severity=_hot_sev(ctx, s),
            )  # fmt: skip

    def _alloc(self, ctx: FileCtx, s: Stmt, nm: str, val: Call) -> Iterable[Finding]:
        rest = _rest(s)
        frees = [
            b
            for b in rest
            if b.kind == "expr"
            and isinstance(b.expr, Call)
            and isinstance(b.expr.func, Attr)
            and isinstance(b.expr.func.obj, Name)
            and b.expr.func.obj.id == nm
            and b.expr.func.attr in ("free", "unsafe_free")
        ]
        if len(frees) != 1 or any(b.kind in ("break", "continue", "return", "raise") for b in body_stmts(rest)):
            return
        others = [b for b in rest if b is not frees[0]]
        for b in body_stmts(others):
            if b.kind in ("def", "struct"):
                return
            if b.kind == "assign" and b.assign and any(root_name(t) == nm for t in b.assign[0] if t is not None):
                if not all(isinstance(t, Sub) for t in b.assign[0]):
                    return
            for n in stmt_nodes(b):
                pm = parent_map(n)
                for y in walk(n):
                    if isinstance(y, Name) and y.id == nm:
                        p = pm.get(id(y))
                        if not (isinstance(p, Sub) and p.obj is y) and not (isinstance(p, Attr) and p.obj is y):
                            return
        if _decl_count(s.func(), nm) != 1:
            return
        tgt = _hoist_target(s, val, ctx)
        if tgt is None:
            return
        yield self.finding(
            ctx, s, f"`{unparse(val)}` allocated and freed every iteration of the loop at L{tgt.line}",
            f"allocate `{nm}` once above L{tgt.line}, free after the loop",
        )  # fmt: skip


ALLOC_METHODS = {"split", "upper", "lower", "replace", "join", "copy", "format"}


def _alloc_call(n: Node, ctx: FileCtx, env: dict[str, str]) -> bool:
    if not isinstance(n, Call):
        return False
    f = n.func
    if isinstance(f, Name) and f.id == "String" and n.args and not n.kw:
        return not all(isinstance(a, Str) for a in n.args)
    if isinstance(f, Attr) and f.attr in ALLOC_METHODS:
        if f.attr == "copy":
            t = ctx.type_of(f.obj, env)
            return not n.args and t is not None and t.replace(" ", "").startswith(("List[", "Dict[", "String", "Set["))
        if f.attr == "join":
            return isinstance(f.obj, Str) or ctx.type_of(f.obj, env) == "String"
        t = ctx.type_of(f.obj, env)
        return t in ("String", "StringSlice") or (f.attr == "split" and isinstance(f.obj, Str))
    return False


class InvariantAlloc(Rule):
    """An allocating call (`.split()`, `String(x)`, `.copy()`, `.upper()`, `.join()`, ...) whose operands do not
    change inside the loop, and whose result is only read: it builds the same heap value every iteration.
    Compute it once before the loop."""

    id = "MA302"
    name = "invariant-alloc-in-loop"
    severity = "medium"
    bad = 'for i in range(n):\n    var cols = header.split(",")\n    t += len(cols[i % 8])'
    good = 'var cols = header.split(",")\nfor i in range(n):\n    t += len(cols[i % 8])'
    why = "the same heap object is rebuilt per iteration; measured 200k -> 1 allocation, 57x"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            loops = s.enclosing_loops()
            if not loops or s.kind in ("for", "while", "def", "struct"):
                continue
            fn = s.func()
            env = ctx.env(fn)
            if s.kind == "var" and s.decl and len(s.decl[0]) == 1 and s.toks[0].value == "var":
                val = s.decl[2]
                if val is not None and _alloc_call(val, ctx, env):
                    x = s.decl[0][0]
                    tgt = self._target(val, loops, ctx)
                    if tgt is None or _decl_count(fn, x) != 1:
                        continue
                    rest = _rest(s)
                    if not readonly_uses(rest, x, ctx.index) or not _no_escape(rest, x):
                        continue
                    yield self.finding(
                        ctx, s, f"`{unparse(val)}` is loop-invariant but rebuilt every iteration (loop L{tgt.line})",
                        f"move `var {x} = {unparse(val)}` above L{tgt.line}",
                    )  # fmt: skip
                    continue
            for n in stmt_nodes(s):
                top = s.kind == "var" and s.decl and n is s.decl[2] and isinstance(n, Call)
                roots = list(n.args) if top and isinstance(n, Call) else [n]
                for r in roots:
                    pm = parent_map(r)
                    hit: set[int] = set()
                    for y in walk(r):
                        if not _alloc_call(y, ctx, env):
                            continue
                        p = pm.get(id(y))
                        if not _read_consumer(p, y):
                            continue
                        tgt = self._target(y, loops, ctx)
                        if tgt is None:
                            continue
                        hit.add(id(y))
                        a = pm.get(id(y))
                        while a is not None and id(a) not in hit:
                            a = pm.get(id(a))
                        if a is not None:
                            continue
                        yield self.finding(
                            ctx, y, f"`{unparse(y)}` is loop-invariant but rebuilt every iteration (loop L{tgt.line})",
                            f"bind it once above L{tgt.line}",
                        )  # fmt: skip

    def _target(self, val: Node, loops: list[Stmt], ctx: FileCtx) -> Stmt | None:
        best = None
        for loop in loops:
            if loop.comptime or not _invariant(val, loop, ctx):
                break
            best = loop
        return None if best is None or _tiny_loop(best, ctx) else best


def _read_consumer(p: Node | None, y: Node) -> bool:
    if isinstance(p, Sub) and p.obj is y:
        return True
    if isinstance(p, BinOp) and p.op in ("==", "!=", "in", "not in", "<", ">", "<=", ">="):
        return True
    if isinstance(p, Attr) and p.obj is y:
        return p.attr in READONLY_METHODS - {"copy"}
    return False


def _no_escape(stmts: list[Stmt], x: str) -> bool:
    for _, n in all_nodes(stmts):
        if isinstance(n, Transfer) and root_name(n.operand) == x:
            return False
    for s in body_stmts(stmts):
        if s.kind in ("return", "yield"):
            for n in stmt_nodes(s):
                if isinstance(n, Name) and n.id == x:
                    return False
                if isinstance(n, Call) and any(isinstance(a, Name) and a.id == x for a in n.args):
                    return False
    return True


def _var_locals(fn: Stmt) -> dict[str, Stmt]:
    out: dict[str, Stmt] = {}
    bad: set[str] = set()
    for s in fn.walk():
        if s.func() is not fn:
            if s.kind == "def":
                bad |= {n.id for b in s.walk() for n in _all(b) if isinstance(n, Name)}
                if s.fn and s.fn.captures:
                    bad |= set(s.fn.captures)
            continue
        if s.kind == "var" and s.decl and len(s.decl[0]) == 1:
            nm = s.decl[0][0]
            if s.toks[0].value != "var" or nm in out:
                bad.add(nm)
            out[nm] = s
        elif s.kind == "for" and s.loop:
            bad |= set(s.loop[0])
    if fn.fn:
        for p in fn.fn.params:
            if p.convention in ("var", "owned"):
                out[p.name] = fn
            else:
                bad.add(p.name)
    return {k: v for k, v in out.items() if k not in bad}


class MissedMove(Rule):
    """`x.copy()` where this is the last use of the local `x`: the deep copy (allocation + memcpy) is thrown
    away immediately after. Transfer ownership with `x^` instead."""

    id = "MA303"
    name = "missed-move"
    severity = "medium"
    bad = "var row = make_row(i)\nrows.append(row.copy())"
    good = "var row = make_row(i)\nrows.append(row^)"
    why = "the source dies right after, so the copy is pure overhead; measured 40001 -> 20001 allocations"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for fn in ctx.defs():
            locs = _var_locals(fn)
            if not locs:
                continue
            env = ctx.env(fn)
            for s in fn.walk():
                if s.func() is not fn or s.kind in ("for", "while", "if", "elif", "def", "struct", "with", "try"):
                    continue
                for n in stmt_nodes(s):
                    for c in walk(n):
                        if not (isinstance(c, Call) and isinstance(c.func, Attr) and c.func.attr == "copy"):
                            continue
                        o = c.func.obj
                        if c.args or c.kw or not isinstance(o, Name) or o.id not in locs:
                            continue
                        x = o.id
                        if self._into_read_param(ctx, c, n):
                            continue
                        t = ctx.type_of(o, env)
                        if t and (t in SCALAR_T or t.startswith(("SIMD[", "Scalar["))):
                            continue
                        if sum(1 for _, y in [(s, z) for z in _all(s)] if isinstance(y, Name) and y.id == x) != 1:
                            continue
                        decl = locs[x]
                        if not self._dead_after(s, decl, fn, x):
                            continue
                        yield self.finding(
                            ctx, c, f"`{x}.copy()` is the last use of `{x}`: the copy is discarded",
                            f"transfer with `{x}^`",
                        )  # fmt: skip

    def _into_read_param(self, ctx: FileCtx, c: Call, root: Node) -> bool:
        from .memory import CopyIntoReadArg

        for p in walk(root):
            if isinstance(p, Call) and any(a is c for a in p.args):
                fname = p.func.id if isinstance(p.func, Name) else p.func.attr if isinstance(p.func, Attr) else None
                es = ctx.index.lookup(fname, ctx.display) if fname else []
                i = next(k for k, a in enumerate(p.args) if a is c)
                chk = CopyIntoReadArg()
                return bool(es) and all(chk._read_at(e.info.params, i, isinstance(p.func, Attr)) for e in es)
        return False

    def _dead_after(self, s: Stmt, decl: Stmt, fn: Stmt, x: str) -> bool:
        stop = fn if decl is fn else decl.parent
        if stop is None:
            return False
        cur: Stmt | None = s
        while cur is not None and cur is not stop:
            if cur.kind in ("for", "while") and cur is not s:
                return False
            cur = cur.parent
        if cur is None:
            return False
        for b in _after(s, stop):
            for bb in [b, *b.walk()]:
                if any(isinstance(y, Name) and y.id == x for y in _all(bb)):
                    return False
                if bb.kind == "def" and bb.fn and bb.fn.captures and x in bb.fn.captures:
                    return False
        return True


class CopyReadOnly(Rule):
    """`var y = e.copy()` (outside a loop; MA109 covers loops) where `y` is only read and `e` is not mutated
    while `y` is alive: bind a reference (`ref y = e`) and skip the deep copy."""

    id = "MA304"
    name = "copy-read-only"
    severity = "low"
    bad = "var cfg = self.cfg.copy()\nreturn cfg.n * 2"
    good = "ref cfg = self.cfg\nreturn cfg.n * 2"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            if s.kind != "var" or s.toks[0].value != "var" or not s.decl or len(s.decl[0]) != 1:
                continue
            if s.enclosing_loops() or s.parent is None or s.func() is None:
                continue
            (y,), typ, val = s.decl
            if not (isinstance(val, Call) and isinstance(val.func, Attr) and val.func.attr == "copy"):
                continue
            if val.args or val.kw:
                continue
            src = val.func.obj
            if any(isinstance(z, Call) for z in walk(src)) or (path_of(src) is None and not isinstance(src, Sub)):
                continue
            env = ctx.env(s.func())
            t = typ or ctx.type_of(src, env)
            if t is None or t in SCALAR_T or t.startswith(("SIMD[", "Scalar[")):
                continue
            rest = _rest(s)
            r = root_name(src)
            if r is None or not readonly_uses(rest, y, ctx.index) or may_mutate(rest, r, ctx.index):
                continue
            if not _no_escape(rest, y) or not any(isinstance(z, Name) and z.id == y for _, z in all_nodes(rest)):
                continue
            fn = s.func()
            locs = _var_locals(fn) if fn is not None else {}
            if isinstance(src, Name) and fn is not None and src.id in locs:
                if MissedMove()._dead_after(s, locs[src.id], fn, src.id):
                    continue
            yield self.finding(
                ctx, s, f"`{y}` deep-copies `{unparse(src)}` but is only read",
                f"ref {y} = {unparse(src)}",
            )  # fmt: skip


def _key_exprs(n: Node, dicts: set[str]) -> Iterator[Node]:
    for y in walk(n):
        if isinstance(y, Sub) and len(y.index) == 1 and path_of(y.obj) in dicts:
            yield y.index[0]
        elif isinstance(y, BinOp) and y.op in ("in", "not in") and path_of(y.right) in dicts:
            yield y.left
        elif isinstance(y, Call) and isinstance(y.func, Attr) and y.func.attr in ("find", "get", "pop"):
            if path_of(y.func.obj) in dicts and y.args:
                yield y.args[0]


def _built_key(k: Node) -> bool:
    if isinstance(k, BinOp) and k.op == "+":
        return True
    return isinstance(k, Call) and callee(k) == "String" and bool(k.args)


class DictKeyRebuilt(Rule):
    """The same String key is built (concatenation / `String(...)`) for several lookups of one `Dict` in the
    same block: each build allocates and each lookup rehashes. Build the key once."""

    id = "MA305"
    name = "dict-key-rebuilt"
    severity = "low"
    bad = 'if s + ":" + t in d:\n    d[s + ":" + t] += 1\nelse:\n    d[s + ":" + t] = 1'
    good = 'var key = s + ":" + t\nif key in d:\n    d[key] += 1\nelse:\n    d[key] = 1'

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for fn in ctx.defs():
            env = ctx.env(fn)
            dicts = {k for k, v in env.items() if ctx.resolve(v, env) and str(ctx.resolve(v, env)).startswith("Dict[")}
            if not dicts:
                continue
            for blk in [fn.body, *(b.body for b in fn.walk() if b.body and b.kind in ("for", "while"))]:
                seen: dict[str, list[tuple[Stmt, Node]]] = {}
                region = list(blk)
                for st in region:
                    if st.kind in ("for", "while", "def"):
                        continue
                    for b in [st, *(x for x in st.walk() if x.kind not in ("for", "while", "def"))]:
                        if any(a.kind in ("for", "while", "def") for a in b.ancestors() if a in set(st.walk())):
                            continue
                        for n in stmt_nodes(b):
                            for k in _key_exprs(n, dicts):
                                if _built_key(k):
                                    seen.setdefault(unparse(k), []).append((b, k))
                assigned = assigned_names(region)
                for key, occ in seen.items():
                    if len(occ) < 2:
                        continue
                    first = occ[0][0].line
                    nm = names(occ[0][1])
                    if any(self._assigned_after(region, v, first) for v in nm & assigned):
                        continue
                    lines = sorted({b.line for b, _ in occ})
                    if len(lines) < 2 and len(occ) < 2:
                        continue
                    yield self.finding(
                        ctx, occ[1][1], f"key `{key}` built {len(occ)}x for lookups (L{', L'.join(map(str, lines))})",
                        f"var key = {key} once, reuse it",
                    )  # fmt: skip

    def _assigned_after(self, region: list[Stmt], v: str, line: int) -> bool:
        for b in body_stmts(region):
            if b.line < line:
                continue
            if b.kind == "var" and b.decl and v in b.decl[0]:
                return True
            if b.kind == "assign" and b.assign and any(root_name(t) == v for t in b.assign[0] if t is not None):
                return True
            if b.kind == "augassign" and b.aug and b.aug[0] is not None and root_name(b.aug[0]) == v:
                return True
            if b.kind == "for" and b.loop and v in b.loop[0]:
                return True
        return False


class NestedListRows(Rule):
    """`List[List[T]]` of fixed-length numeric rows: one heap block per row (n+1 allocations, rows scattered in
    memory, two dependent loads per element). Use one flat `List[T](length=n*k)` indexed `i*k + j`."""

    id = "MA306"
    name = "nested-list-rows"
    severity = "low"
    confidence = "medium"
    risk = "api"
    bad = "var m = List[List[Float64]]()\nfor i in range(n):\n    m.append(List[Float64](length=k, fill=0.0))"
    good = "var m = List[Float64](length=n * k, fill=0.0)  # m[i * k + j]"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            if s.kind == "var" and s.decl and len(s.decl[0]) == 1 and isinstance(s.decl[2], Call):
                v = s.decl[2]
                t = _ctor_type(v)
                if t and t.startswith("List[List[") and v.kw and {k for k, _ in v.kw} == {"length", "fill"}:
                    kw = dict(v.kw)
                    row = kw["fill"]
                    rt = _ctor_type(row) if isinstance(row, Call) else None
                    if rt and isinstance(row, Call) and {k for k, _ in row.kw} == {"length", "fill"} and not row.args:
                        et = elem_type(rt)
                        nlit = ctx.comptime_int(kw["length"], s.func())
                        if is_numeric_elem(et) and (nlit is None or nlit > 64):
                            rk = dict(row.kw)
                            n, k = unparse(kw["length"]), unparse(rk["length"])
                            yield self.finding(
                                ctx, s, f"`{s.decl[0][0]}` is {n} separate {rt} rows of {k}: {n}+1 allocations",
                                f"List[{et}](length={_par(n)} * {_par(k)}, fill={unparse(rk['fill'])}), "
                                f"index [i * {_par(k)} + j]",
                            )  # fmt: skip
                continue
            if s.kind != "expr" or not s.enclosing_loops():
                continue
            e = s.expr
            if not (isinstance(e, Call) and isinstance(e.func, Attr) and e.func.attr == "append" and len(e.args) == 1):
                continue
            row = e.args[0]
            rt = _ctor_type(row)
            if not (isinstance(row, Call) and rt and rt.startswith("List[") and not row.args):
                continue
            if {k for k, _ in row.kw} != {"length", "fill"}:
                continue
            et = elem_type(rt)
            if not is_numeric_elem(et):
                continue
            loop = s.enclosing_loops()[0]
            rk = dict(row.kw)
            if not _invariant(rk["length"], loop, ctx) or s.parent is not loop or _tiny_loop(loop, ctx):
                continue
            p = path_of(e.func.obj)
            if p is None:
                continue
            env = ctx.env(s.func())
            mt = ctx.resolve(env.get(p), env)
            if not (mt and mt.replace(" ", "").startswith("List[List[")):
                continue
            k = unparse(rk["length"])
            yield self.finding(
                ctx, s, f"`{p}` gets one {rt} heap row of fixed length {k} per iteration",
                f"flat List[{et}] of n * {_par(k)}, index [i * {_par(k)} + j]",
            )  # fmt: skip


def _par(s: str) -> str:
    return s if s.replace("_", "").isalnum() or s.replace(".", "").isalnum() else f"({s})"


def _ctor_type(n: Node | None) -> str | None:
    if isinstance(n, Call) and isinstance(n.func, Sub) and isinstance(n.func.obj, Name):
        return unparse(n.func).replace(" ", "")
    return None


def _file_handles(fn: Stmt) -> dict[str, Stmt]:
    """Handle name -> the statement whose following/inner code may use it (the `with`, or the `var f = open()`)."""
    out: dict[str, Stmt] = {}
    for s in fn.walk():
        if s.kind == "with":
            toks = [t.value for t in s.toks]
            if "open" in toks and "as" in toks:
                i = toks.index("as")
                if i + 1 < len(toks):
                    out[toks[i + 1]] = s
        if s.kind == "var" and s.decl and len(s.decl[0]) == 1 and isinstance(s.decl[2], Call):
            if callee(s.decl[2]) == "open":
                out[s.decl[0][0]] = s
    return out


def _loop_inside(s: Stmt, owner: Stmt) -> bool:
    for loop in s.enclosing_loops():
        if owner.kind == "with":
            if any(a is owner for a in loop.ancestors()):
                return True
        elif any(a.parent is owner.parent and a.line > owner.line for a in [loop, *loop.ancestors()]):
            return True
    return False


class SmallWritesInLoop(Rule):
    """`f.write(...)` on a `FileHandle` inside a loop: every call is a separate `write(2)` syscall. Build the
    output in a `String` with `buf.write(...)` and write it once (or in large chunks)."""

    id = "MA307"
    name = "small-writes-in-loop"
    severity = "medium"
    bad = 'with open(p, "w") as f:\n    for i in range(n):\n        f.write(i, "\\n")'
    good = 'var buf = String()\nfor i in range(n):\n    buf.write(i, "\\n")\nwith open(p, "w") as f:\n    f.write(buf)'

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for fn in ctx.defs():
            fh = _file_handles(fn)
            if not fh:
                continue
            for s in fn.walk():
                if s.func() is not fn or s.kind != "expr" or not s.enclosing_loops():
                    continue
                e = s.expr
                if isinstance(e, Call) and isinstance(e.func, Attr) and e.func.attr == "write":
                    if isinstance(e.func.obj, Name) and e.func.obj.id in fh and _loop_inside(s, fh[e.func.obj.id]):
                        h = e.func.obj.id
                        yield self.finding(
                            ctx, s, f"`{h}.write()` per loop iteration: one syscall each",
                            "accumulate into a String buffer, write once after the loop",
                        )  # fmt: skip


class DictNoCapacity(Rule):
    """Empty `Dict` filled by one unconditional insert per iteration of the loop right after it, with a known
    trip count: pass `capacity=` so the table is sized once instead of rehashing as it grows."""

    id = "MA308"
    name = "dict-capacity"
    severity = "low"
    bad = "var d = Dict[Int, Int]()\nfor i in range(n):\n    d[i] = f(i)"
    good = "var d = Dict[Int, Int](capacity=n)\nfor i in range(n):\n    d[i] = f(i)"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        from .memory import ListReserve, blocks

        lr = ListReserve()
        for blk in blocks(ctx.mod):
            for k, st in enumerate(blk):
                if st.kind != "var" or not st.decl or len(st.decl[0]) != 1 or st.toks[0].value != "var":
                    continue
                v = st.decl[2]
                if not (isinstance(v, Call) and _head(v) == "Dict" and not v.args and not v.kw):
                    continue
                nm = st.decl[0][0]
                nxt = blk[k + 1] if k + 1 < len(blk) else None
                if nxt is None or nxt.kind != "for" or nxt.comptime or not nxt.loop:
                    continue
                count = lr._count(ctx, nxt)
                if count is None or (count.isdigit() and int(count) <= 64):
                    continue
                if any(b.kind in ("break", "continue", "return", "raise", "if", "elif", "else", "def", "for", "while")
                       for b in body_stmts(nxt.body)):  # fmt: skip
                    continue
                ins = [
                    b
                    for b in nxt.body
                    if b.kind == "assign"
                    and b.assign
                    and len(b.assign[0]) == 1
                    and isinstance(b.assign[0][0], Sub)
                    and isinstance(b.assign[0][0].obj, Name)
                    and b.assign[0][0].obj.id == nm
                ]
                uses = sum(1 for _, x in all_nodes(nxt.body) if isinstance(x, Name) and x.id == nm)
                if len(ins) != 1 or uses != 1:
                    continue
                yield self.finding(
                    ctx, st, f"`{nm}` gets {count} inserts in the next loop but starts at default capacity",
                    f"{unparse(v.func)}(capacity={count})",
                )  # fmt: skip


class ListBoolBitset(Rule):
    """`List[Bool]` of a compile-time-known size: one byte per flag on the heap. `BitSet[N]` stores 8 flags per
    byte inline (no allocation). Info only: bit access costs a shift/mask."""

    id = "MA309"
    name = "list-bool-bitset"
    severity = "info"
    confidence = "low"
    risk = "api"
    bad = "var seen = List[Bool](length=256, fill=False)"
    good = "var seen = BitSet[256]()"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            if s.kind != "var" or not s.decl or len(s.decl[0]) != 1:
                continue
            v = s.decl[2]
            if _ctor_type(v) != "List[Bool]" or not isinstance(v, Call):
                continue
            kw = dict(v.kw)
            if set(kw) != {"length", "fill"} or not (isinstance(kw["fill"], Name) and kw["fill"].id == "False"):
                continue
            n = ctx.comptime_int(kw["length"], s.func())
            if n is None or n < 64:
                continue
            yield self.finding(
                ctx,
                s,
                f"List[Bool] of comptime size {n} ({n} B heap)",
                f"BitSet[{n}]() ({(n + 63) // 64 * 8} B inline)",
            )
