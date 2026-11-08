from __future__ import annotations

from collections.abc import Iterable

from ..core import (
    PURE_BUILTINS,
    READONLY_METHODS,
    FileCtx,
    Finding,
    Index,
    Rule,
    all_nodes,
    assigned_names,
    body_stmts,
    callee,
    elem_type,
    hot_depth,
    is_gpu_kernel,
    may_mutate,
    stmt_nodes,
)
from ..expr import Attr, BinOp, Call, Name, Node, Num, Str, Sub, path_of, unparse, walk
from ..parser import Stmt
from ._util import numeric_body, parent_map
from .correctness import facts

SIZES = {
    "Bool": 1, "Int8": 1, "UInt8": 1, "Int16": 2, "UInt16": 2, "Float16": 2, "BFloat16": 2, "Int32": 4,
    "UInt32": 4, "Float32": 4, "Int": 8, "UInt": 8, "Int64": 8, "UInt64": 8, "Float64": 8,
}  # fmt: skip
HEAP_SIZES = {"String": 24, "List": 24, "Dict": 48, "Set": 48, "Pointer": 8, "UnsafePointer": 8, "Optional": 16}


def _fsize(t: str) -> int | None:
    t = t.replace(" ", "")
    if t in SIZES:
        return SIZES[t]
    if t.startswith(("Pointer[", "UnsafePointer[")):
        return 8
    return None


def _approx(t: str) -> int:
    s = _fsize(t)
    if s is not None:
        return s
    head = t.split("[", maxsplit=1)[0]
    return HEAP_SIZES.get(head, 8)


def _fields(ctx: FileCtx, sname: str) -> dict[str, str] | None:
    f = ctx.index.structs.get(sname) or ctx.structs.get(sname)
    if f is None:
        return None
    return {k: v for k, v in f.items() if not k.startswith("@")}


class AosFieldLoop(Rule):
    """Hot loop reading one or two fields of every element of a `List[Struct]` with many fields: each element's
    whole cache footprint is streamed to use a few bytes of it. Keep the hot fields in their own `List` (SoA)."""

    id = "MA120"
    name = "aos-field-loop"
    severity = "low"
    confidence = "medium"
    risk = "api"
    bad = "for i in range(len(bars)):\n    s += bars[i].close  # Bar has 8 fields"
    good = "for i in range(len(close)):\n    s += close[i]  # close: List[Float64]"
    why = "an 8-field Bar is 64 B per element; summing .close reads 8 B of it (measured 2.3-7.5x)"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            if s.kind != "for" or s.comptime or not s.loop or any(b.kind in ("for", "while") for b in s.walk()):
                continue
            if is_gpu_kernel(s.func()) or not numeric_body(s.body):
                continue
            env = ctx.env(s.func())
            tgt, it = s.loop
            whole: dict[str, str] = {}
            if len(tgt) == 1 and it is not None and path_of(it) is not None:
                whole[tgt[0]] = str(path_of(it))
            used: dict[str, set[str]] = {}
            bad: set[str] = set()
            for st in body_stmts(s.body):
                for n in stmt_nodes(st):
                    pm = parent_map(n)
                    for x in walk(n):
                        lst = None
                        if isinstance(x, Sub) and len(x.index) == 1 and path_of(x.obj) is not None:
                            lst = path_of(x.obj)
                        elif isinstance(x, Name) and x.id in whole:
                            lst = whole[x.id]
                        if lst is None:
                            continue
                        p = pm.get(id(x))
                        if isinstance(p, Attr) and p.obj is x:
                            gp = pm.get(id(p))
                            if isinstance(gp, Call) and gp.func is p:
                                bad.add(lst)
                            else:
                                used.setdefault(lst, set()).add(p.attr)
                        elif isinstance(x, (Sub, Name)):
                            bad.add(lst)
            for lst, flds in used.items():
                if lst in bad:
                    continue
                t = ctx.resolve(env.get(lst), env)
                et = elem_type(t) if t and t.replace(" ", "").startswith("List[") else None
                fs = _fields(ctx, et) if et else None
                if not fs or len(fs) < 4 or not flds <= set(fs) or any(_fsize(fs[f]) is None for f in flds):
                    continue
                total = sum(_approx(v) for v in fs.values())
                touched = sum(_approx(fs[f]) for f in flds)
                if total < 32 or touched * 4 > total:
                    continue
                yield self.finding(
                    ctx, s, f"loop reads {', '.join(sorted(flds))} ({touched} of ~{total} B) from each {et} in `{lst}`",
                    "keep hot field(s) in separate List(s) (SoA) for this loop",
                )  # fmt: skip


class StructPadding(Rule):
    """Struct fields in an order that forces alignment padding (Mojo keeps declaration order): sorting fields by
    size (largest first) shrinks every element, which matters for large `List[Struct]` buffers."""

    id = "MA121"
    name = "struct-padding"
    severity = "info"
    risk = "api"
    bad = "struct A:\n    var a: Bool\n    var b: Float64\n    var c: Bool\n    var d: Float64  # size_of 32"
    good = "struct A:\n    var b: Float64\n    var d: Float64\n    var a: Bool\n    var c: Bool  # size_of 24"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        listed = {
            elem_type(t.replace(" ", ""))
            for fs in ctx.index.structs.values()
            for t in fs.values()
            if t.replace(" ", "").startswith("List[")
        }
        for s in ctx.mod.walk():
            if s.kind != "struct" or len(s.toks) < 2:
                continue
            name = s.toks[1].value
            flds = [(nm, b.decl[1]) for b in s.body if b.kind == "var" and b.decl and b.decl[1] for nm in b.decl[0]]
            if len(flds) < 3:
                continue
            sz = [_fsize(t) for _, t in flds]
            if any(x is None for x in sz):
                continue
            sizes = [x for x in sz if x is not None]
            cur, best = _layout(sizes), _layout(sorted(sizes, reverse=True))
            if best >= cur:
                continue
            order = [nm for (nm, _), _x in sorted(zip(flds, sizes, strict=True), key=lambda p: -p[1])]
            sev = "low" if name in listed or self._in_list(ctx, name) else "info"
            tip = (
                f"order fields: {', '.join(order)}"
                if len(order) <= 8
                else "declare fields largest-first (8 B, 4 B, 2 B, 1 B)"
            )
            yield self.finding(
                ctx,
                s,
                f"struct {name} is {cur} B with padding; {best} B with fields ordered by size",
                tip,
                severity=sev,
            )

    def _in_list(self, ctx: FileCtx, name: str) -> bool:
        return f"List[{name}]" in ctx.src


def _layout(sizes: list[int]) -> int:
    off = 0
    for s in sizes:
        off = (off + s - 1) // s * s + s
    m = max(sizes)
    return (off + m - 1) // m * m


class Pow2DivMod(Rule):
    """Integer `x // 2**k` / `x % 2**k` in a loop: Mojo's floor semantics make these exactly `x >> k` and
    `x & (2**k - 1)` for every signed or unsigned value, but the compiler emits the sign fix-up sequence."""

    id = "MA122"
    name = "pow2-divmod"
    severity = "low"
    bad = "for i in range(n):\n    s += xs[i] // 8 + xs[i] % 16"
    good = "for i in range(n):\n    s += (xs[i] >> 3) + (xs[i] & 15)"
    why = "floor // and Python-style % by 2^k equal arithmetic shift / mask for negatives too (-7 // 2 == -7 >> 1)"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        fx = facts(ctx)
        for s in ctx.mod.walk():
            if s.kind in ("comptime", "def", "struct") or hot_depth(s) < 1:
                continue
            loops = s.enclosing_loops()
            if loops and not numeric_body(loops[0].body):
                continue
            f = None
            if s.kind == "augassign" and s.aug and s.aug[1] in ("//=", "%=") and s.aug[0] is not None:
                k = _log2(s.aug[2])
                if k is not None:
                    f = f or fx.of(s)
                    if fx.ntype(s.aug[0], f) == "i":
                        lhs = unparse(s.aug[0])
                        new = f"{lhs} >>= {k}" if s.aug[1] == "//=" else f"{lhs} &= {(1 << k) - 1}"
                        yield self.finding(ctx, s, f"`{s.aug[1]} {1 << k}` on an integer", new)
            for n in stmt_nodes(s):
                for x in walk(n):
                    if not (isinstance(x, BinOp) and x.op in ("//", "%")):
                        continue
                    k = _log2(x.right)
                    if k is None or isinstance(x.left, Num) or _comptime_only(ctx, x.left, s):
                        continue
                    f = f or fx.of(s)
                    if fx.ntype(x.left, f) != "i":
                        continue
                    a = unparse(x.left)
                    a = f"({a})" if isinstance(x.left, BinOp) else a
                    new = f"({a} >> {k})" if x.op == "//" else f"({a} & {(1 << k) - 1})"
                    yield self.finding(ctx, x, f"integer `{unparse(x)}` by a power of two in a loop", new)


def _comptime_only(ctx: FileCtx, n: Node, s: Stmt) -> bool:
    env = ctx.env(s.func())
    ns = [y.id for y in walk(n) if isinstance(y, Name)]
    return bool(ns) and all(v in ctx.module_comptime or "@" + v in env for v in ns)


def _log2(n: Node | None) -> int | None:
    if not isinstance(n, Num) or n.is_float:
        return None
    v = n.int_value()
    if v is None or v < 2 or v & (v - 1):
        return None
    return v.bit_length() - 1


class PythonInLoop(Rule):
    """`Python.import_module()` / `Python.evaluate()` inside a loop: a CPython call (module dict lookup, object
    creation, refcounting) per iteration for a loop-invariant result. Do it once before the loop."""

    id = "MA123"
    name = "python-in-loop"
    severity = "medium"
    bad = 'for i in range(n):\n    var np = Python.import_module("numpy")'
    good = 'var np = Python.import_module("numpy")\nfor i in range(n):\n    ...'

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            if not s.enclosing_loops() or s.kind in ("for", "while"):
                continue
            for n in stmt_nodes(s):
                for x in walk(n):
                    if not (isinstance(x, Call) and isinstance(x.func, Attr)):
                        continue
                    if path_of(x.func.obj) != "Python" or x.func.attr not in ("import_module", "evaluate"):
                        continue
                    if not x.args or not all(isinstance(a, (Str, Num)) for a in x.args):
                        continue
                    yield self.finding(
                        ctx, x, f"`Python.{x.func.attr}(...)` with constant args inside a loop", "hoist above the loop"
                    )


class PrintInHotLoop(Rule):
    """Unconditional `print` in the body of a nested loop: formatting plus a locked, flushed stdout write per
    inner iteration usually dominates the loop. Collect into a String and print once, or gate it."""

    id = "MA124"
    name = "print-in-hot-loop"
    severity = "info"
    confidence = "medium"
    bad = "for i in range(n):\n    for j in range(m):\n        print(i, j, x[i * m + j])"
    good = (
        "var out = String()\nfor i in range(n):\n    for j in range(m):\n"
        "        out.write(i, ' ', j, ' ', x[i * m + j], '\\n')\nprint(out)"
    )

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            if s.kind != "expr" or not isinstance(s.expr, Call) or callee(s.expr) != "print":
                continue
            if not isinstance(s.expr.func, Name):
                continue
            loops = s.enclosing_loops()
            if len(loops) < 2 or s.parent is not loops[0]:
                continue
            inner = loops[0]
            if any(b.kind in ("if", "elif", "else", "break", "return", "raise", "continue") for b in inner.body):
                continue
            rest = [b for b in inner.body if b is not s]
            if inner.kind != "for" or not rest or not numeric_body(rest):
                continue
            yield self.finding(
                ctx, s, "unconditional print() in an inner loop", "buffer into a String, print once after the loop"
            )


def pure_func(index: Index, name: str, path: str | None, depth: int = 0) -> bool:
    e = index.free_func(name, path)
    if e is None or depth > 3:
        return False
    if any(p.convention not in ("read", "borrowed") or "Pointer" in p.type or "Span" in p.type for p in e.info.params):
        return False
    if e.info.captures is not None:
        return False
    fn = e.stmt
    local = {p.name for p in e.info.params}
    decl = set()
    for s in fn.walk():
        if s.kind in ("def", "struct", "with", "try", "raise", "yield"):
            return False
        if s.kind == "var" and s.decl:
            decl.update(s.decl[0])
        if s.kind == "for" and s.loop:
            decl.update(s.loop[0])
    for s in fn.walk():
        if s.kind in ("assign", "augassign"):
            tg = s.assign[0] if s.assign else [s.aug[0]] if s.aug else []
            for t in tg:
                r = None if t is None else (t.id if isinstance(t, Name) else None)
                root = None
                y = t
                while isinstance(y, (Sub, Attr)):
                    y = y.obj
                if isinstance(y, Name):
                    root = y.id
                if root is None or root not in decl:
                    return False
                _ = r
        for n in stmt_nodes(s):
            for x in walk(n):
                if not isinstance(x, Call):
                    continue
                f = x.func.obj if isinstance(x.func, Sub) else x.func
                if isinstance(f, Name):
                    if f.id in PURE_BUILTINS - {"String"} or f.id in ("Float64", "Int"):
                        continue
                    if f.id[:1].isupper() and f.id in ("List", "SIMD", "InlineArray"):
                        continue
                    if not pure_func(index, f.id, e.path, depth + 1):
                        return False
                elif isinstance(f, Attr):
                    r = f.obj
                    while isinstance(r, (Sub, Attr)):
                        r = r.obj
                    if not isinstance(r, Name):
                        return False
                    if r.id in decl and r.id not in local:
                        continue
                    if r.id in local and f.attr in READONLY_METHODS:
                        continue
                    return False
                else:
                    return False
    return True


class RepeatedPureCall(Rule):
    """The same call to a side-effect-free project function, with identical arguments, appears more than once in
    one expression: it is computed again (the compiler cannot prove purity across a non-inlined call)."""

    id = "MA125"
    name = "repeated-pure-call"
    severity = "low"
    bad = "acc += norm(xs) / (1.0 + norm(xs))"
    good = "var nv = norm(xs)\nacc += nv / (1.0 + nv)"
    why = "norm() walks the list twice; measured 2.0x on a 10k-element norm"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            if s.kind in ("def", "struct", "comptime"):
                continue
            for n in stmt_nodes(s):
                seen: dict[str, Call] = {}
                for x in walk(n):
                    if not (isinstance(x, Call) and isinstance(x.func, Name) and x.args and not x.kw):
                        continue
                    if x.func.id in PURE_BUILTINS or not all(_simple(a) for a in x.args):
                        continue
                    key = unparse(x)
                    if key in seen:
                        if not pure_func(ctx.index, x.func.id, ctx.display) or not self._heavy(ctx, x.func.id):
                            continue
                        yield self.finding(ctx, x, f"`{key}` is evaluated more than once in this expression",
                                           f"var v = {key} once, reuse it")  # fmt: skip
                        break
                    seen[key] = x

    def _heavy(self, ctx: FileCtx, name: str) -> bool:
        e = ctx.index.free_func(name, ctx.display)
        return e is not None and any(b.kind in ("for", "while") for b in e.stmt.walk())


def _simple(a: Node) -> bool:
    return all(isinstance(y, (Name, Attr, Num, Sub)) or (isinstance(y, BinOp) and y.op in "+-*") for y in walk(a))


class DictIterLookup(Rule):
    """`for k in d:` followed by `d[k]` in the body: every iteration re-hashes a key it already holds (and
    `d[k]` can raise). Iterate `d.items()` and use `e.key` / `e.value`."""

    id = "MA126"
    name = "dict-iter-lookup"
    severity = "medium"
    bad = "for k in d:\n    s += d[k]"
    good = "for e in d.items():\n    s += e.value"
    why = "one hash + probe per element saved; measured 6.6x on 20k String keys"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            if s.kind != "for" or s.comptime or not s.loop or len(s.loop[0]) != 1 or s.loop[1] is None:
                continue
            k = s.loop[0][0]
            it = s.loop[1]
            if isinstance(it, Call) and isinstance(it.func, Attr) and it.func.attr == "keys" and not it.args:
                it = it.func.obj
            d = path_of(it)
            if d is None:
                continue
            env = ctx.env(s.func())
            t = ctx.resolve(env.get(d), env)
            if not t or not t.replace(" ", "").startswith("Dict["):
                continue
            hits = [
                x
                for _, x in all_nodes(s.body)
                if isinstance(x, Sub) and path_of(x.obj) == d and len(x.index) == 1 and unparse(x.index[0]) == k
            ]
            if not hits or may_mutate(s.body, d.split(".")[0], ctx.index) or k in assigned_names(s.body):
                continue
            yield self.finding(
                ctx, s, f"iterates keys of `{d}` then looks up `{d}[{k}]` ({len(hits)}x)",
                f"for e in {d}.items(): use e.key / e.value",
            )  # fmt: skip


class SortInLoop(Rule):
    """`sort(xs)` inside a loop that never changes `xs` otherwise: after the first iteration it re-sorts sorted
    data, O(n log n) (or O(n)) per iteration for nothing. Sort once before the loop."""

    id = "MA127"
    name = "sort-in-loop"
    severity = "high"
    bad = "for r in range(k):\n    sort(xs)\n    acc += xs[r]"
    good = "sort(xs)\nfor r in range(k):\n    acc += xs[r]"
    why = "measured 162x for 2000 floats sorted 2000 times"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            if s.kind != "expr" or not isinstance(s.expr, Call) or callee(s.expr) != "sort" or len(s.expr.args) != 1:
                continue
            e = s.expr
            if isinstance(e.func, Attr):
                continue
            loops = s.enclosing_loops()
            if not loops:
                continue
            p = path_of(e.args[0])
            if p is None:
                continue
            r = p.split(".")[0]
            loop = loops[0]
            others = [b for b in loop.body if b is not s]
            if r in assigned_names(loop.body) or may_mutate(others, r, ctx.index):
                continue
            if loop.kind == "for" and loop.loop and r in loop.loop[0]:
                continue
            yield self.finding(ctx, s, f"`sort({p})` repeats every iteration but `{p}` is not modified in the loop",
                               f"sort once above L{loop.line}")  # fmt: skip


class HugeAlwaysInline(Rule):
    """`@always_inline` on a large function: every call site gets a full copy, inflating code size and compile
    time, and often hurting i-cache. Keep `@always_inline` for small leaves."""

    id = "MA128"
    name = "huge-always-inline"
    severity = "info"
    confidence = "medium"
    risk = "codesize"
    bad = "@always_inline\ndef step(...):  # 120 statements, called from 6 sites"
    good = "def step(...):  # let the inliner decide"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.defs():
            if not s.has_decorator("always_inline") or s.fn is None:
                continue
            if any(len(d.toks) > 2 for d in s.decorators if len(d.toks) > 1 and d.toks[1].value == "always_inline"):
                continue
            n = sum(1 for b in s.walk() if b.kind not in ("docstring", "pass"))
            calls = len(ctx.index.calls.get(s.fn.name, []))
            if n < 60 or calls < 2:
                continue
            yield self.finding(ctx, s, f"@always_inline {s.fn.name}() has {n} statements and {calls} call sites",
                               "drop @always_inline (or split out the cold part)")  # fmt: skip


LAUNCH = ("enqueue_function", "enqueue_function_checked", "enqueue_function_experimental")


class GpuSyncInLoop(Rule):
    """A loop that only enqueues kernels and calls `ctx.synchronize()` each iteration: the host never reads
    results in between, so each sync is a full host/device round trip that serialises launches. Sync once
    after the loop (the stream is in-order)."""

    id = "MA129"
    name = "gpu-sync-in-loop"
    severity = "medium"
    bad = "for s in range(steps):\n    ctx.enqueue_function[k](buf, grid_dim=g, block_dim=b)\n    ctx.synchronize()"
    good = "for s in range(steps):\n    ctx.enqueue_function[k](buf, grid_dim=g, block_dim=b)\nctx.synchronize()"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            if s.kind not in ("for", "while") or not s.body:
                continue
            syncs: list[Stmt] = []
            launches = 0
            ok = True
            for b in s.body:
                e = b.expr if b.kind == "expr" else None
                c = callee(e) if isinstance(e, Call) else None
                if isinstance(e, Call) and isinstance(e.func, (Attr, Sub)) and c == "synchronize":
                    syncs.append(b)
                elif isinstance(e, Call) and c in LAUNCH:
                    launches += 1
                elif b.kind in ("var", "assign", "augassign") and not any(
                    isinstance(x, (Sub, Call)) and not (isinstance(x, Call) and callee(x) in PURE_BUILTINS)
                    for x in _nodes(b)
                ):
                    continue
                else:
                    ok = False
                    break
            if not ok or not syncs or not launches:
                continue
            yield self.finding(ctx, syncs[0], "synchronize() every iteration of a launch-only loop",
                               f"move the sync after the loop at L{s.line}")  # fmt: skip


def _nodes(b: Stmt) -> list[Node]:
    return [x for n in stmt_nodes(b) for x in walk(n)]


TID = {"thread_idx", "global_idx"}


def _strip(n: Node) -> Node:
    while isinstance(n, Call) and isinstance(n.func, Name) and n.func.id in ("Int", "Int32", "UInt", "UInt32", "Int64"):
        if len(n.args) != 1:
            break
        n = n.args[0]
    return n


def _is_tid_expr(n: Node, tids: set[str]) -> bool:
    for x in walk(n):
        if isinstance(x, Attr) and isinstance(x.obj, Name) and x.obj.id in TID and x.attr == "x":
            return True
        if isinstance(x, Name) and x.id in tids:
            return True
    return False


class GpuUncoalesced(Rule):
    """In a GPU kernel loop, `buf[tid * S + k]` with the thread index on the slow axis: neighbouring threads
    touch addresses `S` elements apart on every step, so each warp load splits into many transactions. Store
    the data transposed (`buf[k * N + tid]`) so a warp reads one contiguous segment."""

    id = "MA130"
    name = "gpu-uncoalesced"
    severity = "low"
    confidence = "medium"
    risk = "api"
    bad = "var i = block_idx.x * block_dim.x + thread_idx.x\nfor k in range(K):\n    s += X[i * K + k]"
    good = "for k in range(K):\n    s += X[k * N + i]  # X stored transposed"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for fn in ctx.defs():
            if not is_gpu_kernel(fn) or fn.parent is None or fn.parent.kind != "module":
                continue
            tids: set[str] = set()
            for s in fn.walk():
                if s.kind == "var" and s.decl and len(s.decl[0]) == 1 and s.decl[2] is not None:
                    v = _strip(s.decl[2])
                    if _is_tid_expr(v, set()) and not any(isinstance(y, Sub) for y in walk(v)):
                        tids.add(s.decl[0][0])
            if not tids:
                continue
            done: set[int] = set()
            for s in fn.walk():
                if s.kind != "for" or not s.loop or len(s.loop[0]) != 1:
                    continue
                k = s.loop[0][0]
                for st in body_stmts(s.body):
                    for n in stmt_nodes(st):
                        for x in walk(n):
                            if not isinstance(x, Sub) or id(x) in done:
                                continue
                            ix = x.index[0] if len(x.index) == 1 else dict(x.kw).get("unsafe_offset")
                            if ix is None:
                                continue
                            stride = self._slow_tid(_strip(ix), tids, k)
                            if stride is None:
                                continue
                            done.add(id(x))
                            yield self.finding(
                                ctx, x, f"`{unparse(x)}`: thread index on slow axis (stride {stride}), loop over {k}",
                                f"transpose the layout to [{k} * N + tid] for coalesced warp loads",
                            )  # fmt: skip

    def _slow_tid(self, ix: Node, tids: set[str], k: str) -> str | None:
        if not (isinstance(ix, BinOp) and ix.op == "+"):
            return None
        for a, b in ((ix.left, ix.right), (ix.right, ix.left)):
            b2 = _strip(b)
            if not (isinstance(b2, Name) and b2.id == k):
                continue
            a2 = _strip(a)
            if isinstance(a2, BinOp) and a2.op == "*":
                for t, st in ((a2.left, a2.right), (a2.right, a2.left)):
                    t2 = _strip(t)
                    if isinstance(t2, Name) and t2.id in tids and not _is_tid_expr(st, tids):
                        if isinstance(st, Num) and st.text == "1":
                            return None
                        return unparse(st)
        return None
