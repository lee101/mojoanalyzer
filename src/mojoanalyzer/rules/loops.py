from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

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
    declared_names,
    elem_type,
    has_kind,
    hot_depth,
    is_float_type,
    is_gpu_kernel,
    is_list_type,
    may_mutate,
    range_args,
    range_unit_step,
    stmt_nodes,
    trip_text,
)
from ..expr import Attr, BinOp, Call, Name, Node, Num, Sub, Transfer, names, path_of, root_name, unparse, walk
from ..parser import Stmt, tuple_items
from ._util import Elementwise, float_dtype, is_numeric_elem, numeric_body, parent_map

LOOP_EXIT = ("break", "continue", "return", "raise", "yield")


def simple_for(s: Stmt) -> tuple[str, list[Node]] | None:
    if s.kind != "for" or s.comptime or not s.loop:
        return None
    tgt, it = s.loop
    ra = range_args(it)
    if len(tgt) != 1 or ra is None or not range_unit_step(it):
        return None
    return tgt[0], ra


def innermost(s: Stmt) -> bool:
    return not any(x.kind in ("for", "while", "def") for x in s.walk())


@dataclass
class SimpleLoop:
    kind: str
    ivar: str
    ew: Elementwise
    writes: list[str]
    accs: list[tuple[str, str]]


def analyze_simple(ctx: FileCtx, s: Stmt) -> SimpleLoop | None:
    if "simple" not in s._cache:
        s._cache["simple"] = _analyze_simple(ctx, s)
    r = s._cache["simple"]
    return r if isinstance(r, SimpleLoop) else None


def _analyze_simple(ctx: FileCtx, s: Stmt) -> SimpleLoop | None:
    sf = simple_for(s)
    if sf is None or not s.body or any(b.body for b in s.body):
        return None
    ivar, ra = sf
    fn = s.func()
    if is_gpu_kernel(fn):
        return None
    n = ctx.comptime_int(ra[-1] if len(ra) == 1 else ra[1], fn)
    if n is not None and n < 32:
        return None
    env = ctx.env(fn)
    temps = declared_names(s.body)
    variant = assigned_names(s.body) | {ivar}
    ew = Elementwise(ctx, env, ivar, variant, temps)
    writes: list[str] = []
    accs: list[tuple[str, str]] = []
    for b in s.body:
        if b.kind == "var" and b.decl and len(b.decl[0]) == 1 and b.decl[2] is not None:
            if b.toks[0].value != "var" or not ew.ok(b.decl[2]):
                return None
        elif b.kind == "assign" and b.assign and len(b.assign[0]) == 1:
            tgt, val = b.assign[0][0], b.assign[1]
            p = ew.lane_sub(tgt) if tgt is not None else None
            if p is not None:
                if not ew.ok(val):
                    return None
                t = ctx.type_of(tgt.obj, env) if isinstance(tgt, Sub) else None
                ew.arrays[p] = elem_type(t) if t else None
                writes.append(p)
                continue
            if isinstance(tgt, Name) and tgt.id not in temps and isinstance(val, Call):
                f = callee(val)
                if f in ("max", "min") and len(val.args) == 2 and not val.kw:
                    a, c = val.args
                    other = (
                        c
                        if isinstance(a, Name) and a.id == tgt.id
                        else a
                        if isinstance(c, Name) and c.id == tgt.id
                        else None
                    )
                    if other is not None and tgt.id not in names(other) and ew.ok(other):
                        accs.append((tgt.id, f))
                        continue
            return None
        elif b.kind == "augassign" and b.aug and b.aug[0] is not None:
            tgt, op, val = b.aug
            assert tgt is not None
            p = ew.lane_sub(tgt)
            if p is not None and op in ("+=", "-=", "*=", "/="):
                if not ew.ok(val):
                    return None
                t = ctx.type_of(tgt.obj, env) if isinstance(tgt, Sub) else None
                ew.arrays[p] = elem_type(t) if t else None
                writes.append(p)
                continue
            if isinstance(tgt, Name) and tgt.id not in temps and op in ("+=", "-="):
                if tgt.id in names(val) or not ew.ok(val):
                    return None
                accs.append((tgt.id, "sum"))
                continue
            return None
        else:
            return None
    acc_names = {a for a, _ in accs}
    for b in s.body:
        for nd in stmt_nodes(b):
            used = names(nd)
            if b.kind == "augassign" and b.aug and isinstance(b.aug[0], Name) and b.aug[0].id in acc_names:
                used = names(b.aug[2])
            elif (
                b.kind == "assign" and b.assign and isinstance(b.assign[0][0], Name) and b.assign[0][0].id in acc_names
            ):
                continue
            if used & acc_names:
                return None
    if len({a for a, _ in accs}) != len(accs):
        return None
    if writes and not accs:
        if not ew.floats_only():
            return None
        return SimpleLoop("elementwise", ivar, ew, writes, [])
    if accs and not writes:
        if not all(is_float_type(ctx.type_of(Name(s.toks[0], a), env)) for a, _ in accs):
            return None
        if not ew.arrays or any(t is None for t in ew.arrays.values()):
            return None
        return SimpleLoop("reduction", ivar, ew, [], accs)
    return None


def _has_list(ctx: FileCtx, s: Stmt, paths: Iterable[str]) -> bool:
    env = ctx.env(s.func())
    return any(is_list_type(ctx.resolve(env.get(p), env)) for p in paths)


class ComptimeUnroll(Rule):
    """Small constant trip-count loop in hot code: `comptime for` guarantees unrolling and makes the index a
    compile-time value (cheap SIMD lane access, usable as a parameter)."""

    id = "MA101"
    name = "comptime-unroll"
    severity = "low"
    confidence = "medium"
    risk = "codesize"
    bad = "for l in range(4):\n    s += v[l]"
    good = "comptime for l in range(4):\n    s += v[l]"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            sf = simple_for(s)
            if sf is None:
                continue
            ivar, ra = sf
            if len(ra) == 2 and not (isinstance(ra[0], Num) and ra[0].text == "0"):
                continue
            fn = s.func()
            k = ctx.comptime_int(ra[-1], fn)
            local_var = None
            if k is None and isinstance(ra[-1], Name) and fn is not None:
                local_var = _const_local(fn, ra[-1].id, ctx)
                k = local_var
            if k is None or not 2 <= k <= 16:
                continue
            if hot_depth(s) < 1:
                continue
            body = list(body_stmts(s.body))
            if len(body) > 12 or has_kind(s.body, *LOOP_EXIT, "for", "while", "def", "try", "with"):
                continue
            if ivar in assigned_names(s.body):
                continue
            env = ctx.env(fn)
            lane = False
            for _, x in all_nodes(s.body):
                if isinstance(x, Sub) and any(isinstance(i, Name) and i.id == ivar for i in x.index):
                    t = ctx.type_of(x.obj, env)
                    if t and t.replace(" ", "").startswith(("SIMD[", "Scalar[")):
                        lane = True
            kern = is_gpu_kernel(fn)
            conf = "high" if lane else "medium" if kern else "low"
            why = "SIMD lane index becomes compile-time" if lane else "guaranteed unroll"
            tip = f"comptime for {ivar} in range({unparse(ra[-1])}):"
            if local_var is not None:
                tip = f"declare `comptime {unparse(ra[-1])} = {k}` then {tip}"
            yield self.finding(ctx, s, f"constant trip count {k} in hot loop ({why})", tip, confidence=conf)


def _const_local(fn: Stmt, name: str, ctx: FileCtx) -> int | None:
    val = None
    for s in fn.walk():
        if s.func() is not fn:
            continue
        if s.kind == "var" and s.decl and s.decl[0] == [name]:
            if val is not None:
                return None
            val = s.decl[2]
    if not (isinstance(val, Num) and not val.is_float):
        return None
    if _mutated_beyond_decl(fn, name, ctx):
        return None
    return val.int_value()


def _mutated_beyond_decl(fn: Stmt, name: str, ctx: FileCtx) -> bool:
    rest = [s for s in fn.walk() if not (s.kind == "var" and s.decl and s.decl[0] == [name])]
    flat = [Stmt(s.kind, s.toks, s.line, s.col) for s in rest]
    for f, s in zip(flat, rest, strict=True):
        f._cache = s._cache
    return may_mutate(flat, name, ctx.index)


class VectorizeElementwise(Rule):
    """Elementwise loop over float buffers with no loop-carried dependency: use `vectorize` with
    `simd_width_of`. Results are bit-identical (no reassociation)."""

    id = "MA102"
    name = "vectorize-elementwise"
    severity = "medium"
    bad = "for i in range(n):\n    y[i] = a * x[i] + y[i]"
    good = "vectorize[simd_width_of[DType.float64]()](n, body)  # body: unsafe_load/unsafe_store[width=w]"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            sl = analyze_simple(ctx, s)
            if sl is None or sl.kind != "elementwise":
                continue
            ra = simple_for(s)
            assert ra is not None
            dt = float_dtype(next(iter(sl.ew.arrays.values())))
            lists = _has_list(ctx, s, sl.ew.arrays)
            arrs = ", ".join(sorted(sl.ew.arrays))
            msg = f"elementwise float loop over {arrs}, no loop-carried dependency"
            tip = (
                f"vectorize[simd_width_of[{dt}]()]({trip_text(ra[1])}, body) with unsafe_ptr() + "
                f"unsafe_load/unsafe_store[width=w]; bit-identical"
            )
            if lists:
                yield self.finding(ctx, s, msg + " (List bounds checks block auto-vectorization)", tip)
            else:
                yield self.finding(
                    ctx, s, msg + " (LLVM may already auto-vectorize)", tip, severity="low", confidence="low"
                )


class SimdReduction(Rule):
    """Scalar float reduction (`s += f(x[i])`, `m = max(m, x[i])`): use SIMD accumulators + `reduce_add`/
    `reduce_max`. Sums are reassociated, so results change in the last bits; min/max are exact."""

    id = "MA103"
    name = "simd-reduction"
    severity = "medium"
    risk = "fp"
    bad = "for i in range(n):\n    s += a[i] * b[i]"
    good = "acc += pa.unsafe_load[width=w](i) * pb.unsafe_load[width=w](i)  # then acc.reduce_add()"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            sl = analyze_simple(ctx, s)
            if sl is None or sl.kind != "reduction":
                continue
            env = ctx.env(s.func())
            dt = float_dtype(ctx.type_of(Name(s.toks[0], sl.accs[0][0]), env))
            kinds = {k for _, k in sl.accs}
            accs = ", ".join(a for a, _ in sl.accs)
            exact = kinds <= {"max", "min"}
            red = "/".join(sorted({"reduce_add" if k == "sum" else f"reduce_{k}" for k in kinds}))
            tip = f"SIMD[{dt}, simd_width_of[{dt}]()] accumulator(s) + {red} (or vectorize)"
            if exact:
                yield self.finding(
                    ctx, s, f"scalar min/max reduction into {accs}", tip + "; exact (NaN propagation may differ)",
                    risk="none",
                )  # fmt: skip
            else:
                yield self.finding(ctx, s, f"scalar float sum reduction into {accs}", tip)


class LiteralSimdWidth(Rule):
    """Hardcoded SIMD width passed to `vectorize`/`width=`: use `simd_width_of[DType]()` so the width follows
    the target (AVX2/AVX-512/NEON) and stays autotune-friendly."""

    id = "MA104"
    name = "literal-simd-width"
    severity = "low"
    bad = "vectorize[8](n, body)"
    good = "vectorize[simd_width_of[DType.float32]()](n, body)"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        seen: set[tuple[int, int]] = set()
        loops_done: set[int] = set()
        for s in ctx.mod.walk():
            fn = s.func()
            for n in stmt_nodes(s):
                for x in walk(n):
                    width: Node | None = None
                    what = ""
                    if isinstance(x, Sub) and path_of(x.obj) in ("vectorize", "algorithm.vectorize") and x.index:
                        width, what = x.index[0], "vectorize width"
                    elif isinstance(x, Sub) and isinstance(x.obj, Attr) and x.obj.attr in (
                        "unsafe_load", "unsafe_store", "load", "store"
                    ):  # fmt: skip
                        width = next((v for k, v in x.kw if k == "width"), None)
                        what = f"{x.obj.attr} width"
                    if width is None:
                        continue
                    k = ctx.comptime_int(width, fn)
                    if k is None or k < 2:
                        continue
                    loop = None
                    if what != "vectorize width":
                        loop = _width_strides_loop(s, width, k)
                        if loop is None or id(loop) in loops_done:
                            continue
                        loops_done.add(id(loop))
                    key = (width.line, width.col)
                    if key in seen:
                        continue
                    seen.add(key)
                    src = f"`{unparse(width)}` = {k}" if isinstance(width, Name) else str(k)
                    yield self.finding(
                        ctx,
                        width,
                        f"hardcoded {what} {src}",
                        "simd_width_of[DType.<type>]() (comptime), keep tail loop",
                    )


def _width_strides_loop(s: Stmt, width: Node, k: int) -> Stmt | None:
    for a in s.ancestors():
        if a.kind == "while":
            for b in body_stmts(a.body):
                if b.kind == "augassign" and b.aug and b.aug[1] == "+=" and b.aug[2] is not None:
                    if unparse(b.aug[2]) == unparse(width) or (isinstance(b.aug[2], Num) and b.aug[2].int_value() == k):
                        return a
            return None
        if a.kind == "def":
            return None
    return None


class ParallelizeCandidate(Rule):
    """Outer loop whose iterations are independent (each writes only `out[i]` and locals, calls only pure
    builtins / read-only project functions) and do heavy work (nested loop): candidate for `parallelize`."""

    id = "MA105"
    name = "parallelize-candidate"
    severity = "medium"
    confidence = "medium"
    risk = "threads"
    bad = "for i in range(n):\n    out[i] = heavy(i)"
    good = "def job(i: Int) {mut op}:\n    op[i] = heavy(i)\nparallelize(job, n)"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            sf = simple_for(s)
            if sf is None or s.enclosing_loops():
                continue
            ivar, ra = sf
            fn = s.func()
            if fn is None or is_gpu_kernel(fn) or hot_depth(s) > 0:
                continue
            k = ctx.comptime_int(ra[-1] if len(ra) == 1 else ra[1], fn)
            if k is not None and k <= 16:
                continue
            res = self._independent(ctx, s, ivar)
            if res is None:
                continue
            outs, heavy = res
            if not heavy or not outs:
                continue
            ptrs = ", ".join(f"mut {o.replace('.', '_')}_p" for o in outs)
            tip = (
                f"def job({ivar}: Int) {{{ptrs}, ...}}: <body writing via unsafe_ptr()>; "
                f"parallelize(job, {trip_text(ra)}) (std max.algorithm)"
            )
            yield self.finding(
                ctx, s, f"independent iterations writing only {', '.join(outs)}[{ivar}] with {heavy}", tip,
                confidence="medium" if heavy == "nested loop" else "low",
            )  # fmt: skip

    def _independent(self, ctx: FileCtx, s: Stmt, ivar: str) -> tuple[list[str], str] | None:
        if has_kind(s.body, "break", "return", "raise", "yield", "def", "struct", "with"):
            return None
        local = declared_names(s.body) | {ivar}
        outs: list[str] = []
        heavy = "nested loop" if has_kind(s.body, "for", "while") else ""

        def write_ok(t: Node | None) -> bool:
            r = None if t is None else root_name(t)
            if t is None or r is None:
                return False
            if r in local:
                return True
            if isinstance(t, Sub) and len(t.index) == 1 and isinstance(t.index[0], Name) and t.index[0].id == ivar:
                p = path_of(t.obj)
                if p is not None:
                    if p not in outs:
                        outs.append(p)
                    return True
            return False

        for b in body_stmts(s.body):
            if b.kind == "assign" and b.assign:
                for t in b.assign[0]:
                    if not all(write_ok(x) for x in tuple_items(t)):
                        return None
            elif b.kind == "augassign" and b.aug and not write_ok(b.aug[0]):
                return None
            for n in stmt_nodes(b):
                for x in walk(n):
                    if isinstance(x, Transfer) and root_name(x.operand) not in local:
                        return None
                    if not isinstance(x, Call):
                        continue
                    f = x.func
                    if isinstance(f, Sub):
                        f = f.obj
                    if isinstance(f, Attr):
                        r = root_name(f.obj)
                        if r not in local and f.attr not in READONLY_METHODS:
                            return None
                        continue
                    if not isinstance(f, Name):
                        return None
                    if f.id in PURE_BUILTINS and f.id != "String":
                        continue
                    if f.id[:1].isupper() and f.id in ctx.structs:
                        continue
                    e = ctx.index.free_func(f.id, ctx.display)
                    if e is None or e.info.raises:
                        return None
                    if any(p.convention not in ("read", "borrowed", "var", "owned") for p in e.info.params):
                        return None
                    if _impure(e.stmt):
                        return None
                    if not heavy and has_kind(e.stmt.body, "for", "while"):
                        heavy = f"loop in {f.id}()"
        for o in outs:
            for _, x in all_nodes(s.body):
                if isinstance(x, Sub) and path_of(x.obj) == o:
                    if not (len(x.index) == 1 and isinstance(x.index[0], Name) and x.index[0].id == ivar):
                        return None
        return outs, heavy


def _impure(fn: Stmt) -> bool:
    for _, x in all_nodes(fn.body):
        if isinstance(x, Call) and callee(x) in ("print", "external_call", "open", "random_float64", "seed", "now"):
            return True
        if isinstance(x, Name) and x.id in ("stdout", "stderr"):
            return True
    return False


class RangeLenIndex(Rule):
    """`for i in range(len(xs))` where `i` is only used as `xs[i]` (reads): iterate the list directly; no
    bounds checks, no semantic change."""

    id = "MA111"
    name = "iterate-directly"
    severity = "low"
    bad = "for i in range(len(xs)):\n    s += xs[i]"
    good = "for x in xs:\n    s += x"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            p = range_len_target(ctx, s)
            if p is None:
                continue
            ivar, xs = p
            fn = s.func()
            used = {x.id for _, x in all_nodes(fn.body if fn else s.body) if isinstance(x, Name)}
            used |= {pp.name for pp in (fn.fn.params if fn and fn.fn else [])}
            el = next(c for c in ("x", "v", "e", "item", "elem", "el_") if c not in used)
            yield self.finding(
                ctx, s, f"index `{ivar}` only used as `{xs}[{ivar}]` (bounds-checked)",
                f"for {el} in {xs}: (use {el} for {xs}[{ivar}])",
            )  # fmt: skip


def range_len_target(ctx: FileCtx, s: Stmt) -> tuple[str, str] | None:
    sf = simple_for(s)
    if sf is None or analyze_simple(ctx, s) is not None:
        return None
    ivar, ra = sf
    if len(ra) != 1:
        return None
    c = ra[0]
    if not (isinstance(c, Call) and isinstance(c.func, Name) and c.func.id == "len" and len(c.args) == 1):
        return None
    xs = path_of(c.args[0])
    if xs is None:
        return None
    env = ctx.env(s.func())
    t = ctx.resolve(env.get(xs), env)
    if not t or not t.replace(" ", "").startswith(("List[", "Span[", "InlineArray[")):
        return None
    if ivar in assigned_names(s.body) or has_kind(s.body, "def"):
        return None
    root = xs.split(".")[0]
    if may_mutate(s.body, root, ctx.index):
        return None
    found = False
    for b in body_stmts(s.body):
        for n in stmt_nodes(b):
            pm = parent_map(n)
            for x in walk(n):
                if not (isinstance(x, Name) and x.id == ivar):
                    continue
                sub = pm.get(id(x))
                if not (isinstance(sub, Sub) and len(sub.index) == 1 and sub.index[0] is x and path_of(sub.obj) == xs):
                    return None
                gp = pm.get(id(sub))
                if isinstance(gp, Attr):
                    ggp = pm.get(id(gp))
                    if isinstance(ggp, Call) and ggp.func is gp and gp.attr not in READONLY_METHODS:
                        return None
                if isinstance(gp, Call) and gp.func is not sub and callee(gp) not in PURE_BUILTINS | {"print"}:
                    return None
                if isinstance(gp, Transfer) or (gp is None and b.kind in ("var", "return")):
                    return None
                found = True
    return (ivar, xs) if found else None


class ReciprocalDivide(Rule):
    """Float division by a loop-invariant value inside a loop: hoist `inv = 1.0 / d` and multiply
    (div is ~4-20x the latency/throughput of mul). Not bit-exact."""

    id = "MA112"
    name = "reciprocal-multiply"
    severity = "low"
    confidence = "medium"
    risk = "fp"
    bad = "for i in range(n):\n    y[i] = x[i] / d"
    good = "var inv = 1.0 / d\nfor i in range(n):\n    y[i] = x[i] * inv"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        done: set[tuple[int, str]] = set()
        for s in ctx.mod.walk():
            loops = s.enclosing_loops()
            if not loops or s.kind in ("for", "while", "def", "struct"):
                continue
            loop = loops[0]
            if not innermost(loop) or not numeric_body(loop.body):
                continue
            env = ctx.env(s.func())
            variant = assigned_names(loop.body)
            if loop.kind == "for" and loop.loop:
                variant |= set(loop.loop[0])
            if loop.kind == "while":
                variant |= assigned_names([loop])
            cands: list[tuple[Node, Node, Node | None]] = []
            if s.kind == "augassign" and s.aug and s.aug[1] == "/=" and s.aug[0] is not None and s.aug[2] is not None:
                cands.append((s.aug[0], s.aug[2], s.aug[0]))
            for n in stmt_nodes(s):
                cands.extend((x, x.right, x.left) for x in walk(n) if isinstance(x, BinOp) and x.op == "/")
            for x, d, left in cands:
                if left is None or not self._invariant_divisor(ctx, d, variant, env):
                    continue
                if not (names(left) & variant) and not any(isinstance(y, Sub) for y in walk(left)):
                    continue
                key = (id(loop), unparse(d))
                if key in done:
                    continue
                done.add(key)
                yield self.finding(
                    ctx, x, f"division by loop-invariant `{unparse(d)}` in loop (line {loop.line})",
                    f"hoist `var inv = 1.0 / {unparse(d)}` before the loop and multiply",
                )  # fmt: skip

    def _invariant_divisor(self, ctx: FileCtx, d: Node, variant: set[str], env: dict[str, str]) -> bool:
        if isinstance(d, Num):
            if not d.is_float:
                return False
            try:
                v = float(d.text.replace("_", ""))
            except ValueError:
                return False
            m = abs(v)
            return not (
                m == 0 or (m.is_integer() and int(m) & int(m) - 1 == 0) or ((1 / m).is_integer() and _pow2(1 / m))
            )
        p = path_of(d)
        if p is None or p.split(".")[0] in variant:
            return False
        return is_float_type(ctx.type_of(d, env))


def _pow2(x: float) -> bool:
    i = int(x)
    return i > 0 and i & (i - 1) == 0


class BoundsCheckedIndex(Rule):
    """Bounds-checked `List` indexing in an inner loop (List `__getitem__` asserts by default, which also blocks
    auto-vectorization): take `unsafe_ptr()` once before the loop."""

    id = "MA113"
    name = "unsafe-ptr-inner-loop"
    severity = "medium"
    risk = "unsafe"
    bad = "for j in range(m):\n    s += w[j] * x[j]"
    good = "var wp = w.unsafe_ptr()\nfor j in range(m):\n    s += wp[j] * x[j]"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            sf = simple_for(s)
            if sf is None or not innermost(s) or hot_depth(s) < 1:
                continue
            if analyze_simple(ctx, s) is not None or range_len_target(ctx, s) is not None:
                continue
            ivar, _ = sf
            fn = s.func()
            if is_gpu_kernel(fn) or not numeric_body(s.body):
                continue
            env = ctx.env(fn)
            lists: list[str] = []
            for _, x in all_nodes(s.body):
                if isinstance(x, Sub) and len(x.index) == 1 and ivar in names(x.index[0]):
                    p = path_of(x.obj)
                    if p is None or p in lists:
                        continue
                    t = ctx.resolve(env.get(p), env)
                    if is_list_type(t) and is_numeric_elem(elem_type(t or "")) and not _structural(s.body, p, ctx):
                        lists.append(p)
            if lists:
                ptrs = "; ".join(f"var {p.replace('.', '_')}_p = {p}.unsafe_ptr()" for p in lists)
                yield self.finding(
                    ctx, s, f"bounds-checked List indexing of {', '.join(lists)} in inner loop",
                    f"{ptrs} before the loop, index the pointer",
                )  # fmt: skip


def _structural(stmts: list[Stmt], p: str, ctx: FileCtx) -> bool:
    for b in body_stmts(stmts):
        if b.kind == "def":
            return True
        if b.kind == "assign" and b.assign:
            for t in b.assign[0]:
                for x in tuple_items(t):
                    if path_of(x) == p or (isinstance(x, Name) and p.startswith(x.id + ".")):
                        return True
        if b.kind == "var" and b.decl and p.split(".", maxsplit=1)[0] in b.decl[0]:
            return True
        for n in stmt_nodes(b):
            pm = parent_map(n)
            for x in walk(n):
                if path_of(x) != p:
                    continue
                par = pm.get(id(x))
                if isinstance(par, Attr) and par.attr not in READONLY_METHODS:
                    gp = pm.get(id(par))
                    if isinstance(gp, Call) and gp.func is par:
                        return True
                if isinstance(par, Transfer):
                    return True
                if isinstance(par, Call) and par.func is not x and callee(par) not in PURE_BUILTINS | {"print"}:
                    return True
    return False


def linear(e: Node, vs: set[str]) -> dict[str, str] | None:
    match e:
        case Name(id=i) if i in vs:
            return {i: "1"}
        case BinOp(op="+" | "-", left=lft, right=r):
            a, b = linear(lft, vs), linear(r, vs)
            if a is None or b is None or set(a) & set(b):
                return None
            if e.op == "-" and b:
                return None
            return {**a, **b}
        case BinOp(op="*", left=lft, right=r):
            for v, c in ((lft, r), (r, lft)):
                if not (names(c) & vs):
                    lv = linear(v, vs)
                    if lv is None:
                        return None
                    if not lv:
                        return {}
                    if any(x != "1" for x in lv.values()):
                        return None
                    if isinstance(c, Num) and c.text == "1":
                        return lv
                    return dict.fromkeys(lv, unparse(c))
            return None
        case Call(func=Name(id="Int"), args=[a]):
            return linear(a, vs)
    return None if names(e) & vs else {}


class LoopInterchange(Rule):
    """Perfectly nested loops traversing a row-major buffer column-wise (inner index has a non-unit stride,
    outer index is unit-stride): swap the loops. Only flagged when the swap is legal and bit-exact (writes are
    per-element, accumulation order per element is preserved)."""

    id = "MA114"
    name = "loop-interchange"
    severity = "high"
    bad = "for j in range(m):\n    for i in range(n):\n        s[j] += a[i * m + j]"
    good = "for i in range(n):\n    for j in range(m):\n        s[j] += a[i * m + j]"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            so = simple_for(s)
            if so is None or len(s.body) != 1:
                continue
            inner = s.body[0]
            si = simple_for(inner)
            if si is None or not inner.body or any(b.body for b in inner.body):
                continue
            a, rao = so
            b, rai = si
            if a == b or any(a in names(x) for x in rai) or any(b in names(x) for x in rao):
                continue
            fn = s.func()
            if is_gpu_kernel(fn):
                continue
            res = self._analyze(ctx, inner, a, b)
            if res is None:
                continue
            col, arrays = res
            if not col:
                continue
            yield self.finding(
                ctx, s, f"column-wise traversal of {', '.join(arrays)}: inner `{b}` strided, outer `{a}` unit-stride",
                f"interchange: `for {b} ...:` outer, `for {a} ...:` inner (bit-exact here)",
            )  # fmt: skip

    def _analyze(self, ctx: FileCtx, inner: Stmt, a: str, b: str) -> tuple[bool, list[str]] | None:
        temps = declared_names(inner.body)
        vs = {a, b}
        col_arrays: list[str] = []
        row = False
        writes: dict[str, str] = {}
        for st in inner.body:
            if st.kind == "var":
                if not st.decl or st.decl[2] is None or st.toks[0].value != "var":
                    return None
                continue
            if st.kind == "assign" and st.assign and len(st.assign[0]) == 1:
                t = st.assign[0][0]
            elif st.kind == "augassign" and st.aug:
                t = st.aug[0]
            else:
                return None
            if not isinstance(t, Sub):
                return None
            p = _access_path(t)
            if p is None or p.split(".")[0] in temps:
                return None
            key = unparse(t)
            if p in writes and writes[p] != key:
                return None
            writes[p] = key
        for _, x in all_nodes(inner.body):
            if isinstance(x, Call) and callee(x) not in PURE_BUILTINS:
                return None
            if isinstance(x, Transfer):
                return None
        nested = {id(x.obj) for _, x in all_nodes(inner.body) if isinstance(x, Sub) and isinstance(x.obj, Sub)}
        for _, x in all_nodes(inner.body):
            if not isinstance(x, Sub):
                continue
            p = _access_path(x)
            if p is None:
                continue
            if p in writes and unparse(x) != writes[p] and not writes[p].startswith(unparse(x) + "["):
                return None
            if id(x) in nested:
                continue
            kind = self._stride(x, a, b, vs)
            if kind is None and b in {n.id for i in x.index for n in walk(i) if isinstance(n, Name)}:
                return None
            if kind == "col":
                if p not in col_arrays:
                    col_arrays.append(p)
            elif kind == "row":
                row = True
        if row:
            return False, []
        return bool(col_arrays), col_arrays

    def _stride(self, x: Sub, a: str, b: str, vs: set[str]) -> str | None:
        if isinstance(x.obj, Sub) and len(x.obj.index) == 1 and len(x.index) == 1:
            i1, i2 = x.obj.index[0], x.index[0]
            if isinstance(i1, Name) and isinstance(i2, Name):
                if i1.id == b and i2.id == a:
                    return "col"
                if i1.id == a and i2.id == b:
                    return "row"
            return None
        if len(x.index) != 1:
            return None
        lin = linear(x.index[0], vs)
        if not lin:
            return None
        cb, ca = lin.get(b), lin.get(a)
        if cb == "1":
            return "row"
        if cb is not None and ca == "1":
            return "col"
        return None


def _access_path(x: Sub) -> str | None:
    o: Node = x
    while isinstance(o, Sub):
        o = o.obj
    return path_of(o)


__all__ = [
    "BoundsCheckedIndex",
    "ComptimeUnroll",
    "LiteralSimdWidth",
    "LoopInterchange",
    "ParallelizeCandidate",
    "RangeLenIndex",
    "ReciprocalDivide",
    "SimdReduction",
    "VectorizeElementwise",
    "analyze_simple",
]
