"""Rules from the pm-simfast pass (2026-11-12): costs that only show when one function is called for every cell of a sweep.

Each one was found with a profile and missed by the rules that existed: a 20 MB copy per call hidden in a getter, 0.7 M scattered
reads per call that a one-off gather removes, a heap temporary built to read one scalar, small `List`s returned by helpers that run
once per row, and an SIMD dot-product row that left half of both FMA ports idle.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..core import FileCtx, Finding, Rule, hot_depth, loop_called, stmt_nodes
from ..expr import Attr, BinOp, Call, Name, Node, Seq, Str, Sub, Transfer, path_of, root_name, unparse, walk
from ..parser import Stmt

HEAP_HEADS = ("List[", "Dict[", "Set[", "String")


def _ret(s: Stmt) -> Node | None:
    if s.kind != "return":
        return None
    ns = stmt_nodes(s)
    return ns[0] if ns else None


def _own_stmts(fn: Stmt) -> list[Stmt]:
    return [s for s in fn.walk() if s.func() is fn]


def _heap(t: str | None) -> bool:
    return t is not None and t.replace(" ", "").startswith(HEAP_HEADS)


class CopyGetter(Rule):
    """A function whose result is `<field>.copy()` (or `<field>[key].copy()`) hands every caller a deep copy of a container
    it owns. Callers that only read pay an allocation and a memcpy of the whole container per call, and nothing at the call
    site says so. Return a borrow (take the value as a `ref` / pointer view), or offer a take / put pair for callers that
    need ownership for the length of one call."""

    id = "MA150"
    name = "copy-getter"
    severity = "low"
    confidence = "medium"
    risk = "api"
    bad = "def lab(mut self, name: String) -> List[Int16]:\n    return self.grps[name].copy()"
    good = (
        "def lab_take(mut self, name: String) -> List[Int16]:\n    return self.grps.pop(name)\n\n"
        "def lab_put(mut self, name: String, var g: List[Int16]):\n    self.grps[name] = g^"
    )
    why = "pm-simfast: a 20 MB label array copied per simulated cell, 4.9 ms of 42.9 ms (11.5%); gone with take / put"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        hot = loop_called(ctx)
        for fn in ctx.defs():
            if fn.fn is None or fn.parent is None or fn.parent.kind != "struct":
                continue
            rets = [s for s in _own_stmts(fn) if s.kind == "return"]
            if not rets:
                continue
            env = ctx.env(fn)
            for s in rets:
                v = _ret(s)
                if not (isinstance(v, Call) and isinstance(v.func, Attr) and v.func.attr == "copy" and not v.args):
                    continue
                src = v.func.obj
                if root_name(src) != "self" or any(isinstance(y, Call) for y in walk(src)):
                    continue
                t = ctx.type_of(src, env)
                if t is not None and not _heap(t):
                    continue
                if t is None and not isinstance(src, Sub):
                    continue
                called = fn.fn.name in hot
                yield self.finding(
                    ctx, s, f"`{fn.fn.name}` returns a deep copy of `{unparse(src)}` on every call",
                    "return a borrow, or add a take / put pair for callers that hold it for one call",
                    severity="medium" if called else None,
                )  # fmt: skip


def _indirect_vars(loop: Stmt) -> dict[str, str]:
    """names bound in the loop body to an element of an index array: `var j = Int(idx[q])` -> {j: idx}."""
    out: dict[str, str] = {}
    for s in loop.walk():
        if s.kind in ("def", "struct"):
            continue
        val: Node | None = None
        nm: str | None = None
        if s.kind == "var" and s.decl and len(s.decl[0]) == 1:
            nm, val = s.decl[0][0], s.decl[2]
        elif s.kind == "assign" and s.assign and len(s.assign[0]) == 1 and isinstance(s.assign[0][0], Name):
            nm, val = s.assign[0][0].id, s.assign[1]
        if nm is None or val is None:
            continue
        if isinstance(val, Call) and isinstance(val.func, Name) and val.func.id in ("Int", "Int32", "Int64") and len(val.args) == 1:
            val = val.args[0]
        if isinstance(val, Sub) and len(val.index) == 1 and path_of(val.obj) is not None:
            out[nm] = path_of(val.obj) or ""
    return out


class ScatteredGather(Rule):
    """Inside a loop, several arrays are read at `row * width + j` where `j` itself comes out of an index list: every read
    lands on a different cache line of a different array. When the index lists and the arrays do not change between calls
    (a sweep over other knobs), gather the columns once into one contiguous struct-of-arrays table in walk order; each call
    then streams it. Confidence is low without a profile: it pays when the arrays are far larger than L2."""

    id = "MA151"
    name = "scattered-gather"
    severity = "low"
    confidence = "low"
    risk = "none"
    bad = (
        "for q in range(b0[k], b0[k + 1]):\n    var j = Int(bkj[q])\n"
        "    acc += w[q] * (C[t * S + j] / O[t * S + j] - 1.0) - cost * adv[t * S + j]"
    )
    good = (
        "# once: tab.cmo[q] = C[t * S + j] / O[t * S + j] - 1.0; tab.adv[q] = adv[t * S + j]\n"
        "for q in range(b0[k], b0[k + 1]):\n    acc += w[q] * tab.cmo[q] - cost * tab.adv[q]"
    )
    why = "pm-simfast: 9 scattered reads x 45 candidates x 1,702 nights per cell = 22.9 ms; 1.0 ms from a table built once"
    options = {"min_arrays": 3}

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        need = int(self.options.get("min_arrays", 3))  # type: ignore[arg-type]
        for loop in ctx.mod.walk():
            if loop.kind != "for" or loop.comptime:
                continue
            ind = _indirect_vars(loop)
            if not ind:
                continue
            arrays: dict[str, set[str]] = {}
            for s in loop.walk():
                if s.kind in ("def", "struct"):
                    continue
                for n in stmt_nodes(s):
                    for x in walk(n):
                        if not (isinstance(x, Sub) and len(x.index) == 1 and not x.kw):
                            continue
                        p = path_of(x.obj)
                        ix = x.index[0]
                        if p is None or not isinstance(ix, BinOp) or ix.op != "+":
                            continue
                        used = {y.id for y in walk(ix) if isinstance(y, Name)} & set(ind)
                        if not used or not any(isinstance(y, BinOp) and y.op == "*" for y in walk(ix)):
                            continue
                        for u in used:
                            arrays.setdefault(u, set()).add(p)
            for j, ps in sorted(arrays.items()):
                ps.discard(ind[j])
                if len(ps) < need:
                    continue
                if any(a is not loop and a.kind == "for" and _indirect_vars(a).get(j) for a in loop.ancestors()):
                    continue
                names = ", ".join(sorted(ps)[:6])
                yield self.finding(
                    ctx, loop, f"{len(ps)} arrays ({names}) are read at rows picked through `{ind[j]}`: one cache miss per read",
                    f"if `{ind[j]}` and the arrays are fixed across calls, gather these columns once into a contiguous table in `{ind[j]}` order",
                    severity="medium" if len(ps) >= 4 and hot_depth(loop) >= 1 else None,
                )  # fmt: skip


def _heap_ctor_return(ctx: FileCtx, name: str) -> str | None:
    """`def name(...): return Ctor(..., "text", ...)`: the constructor name when a heap argument is built per call."""
    e = ctx.index.free_func(name, ctx.display)
    if e is None:
        return None
    body = [s for s in e.stmt.body if s.kind != "docstring"]
    if len(body) != 1:
        return None
    v = _ret(body[0])
    if not (isinstance(v, Call) and isinstance(v.func, Name) and v.func.id[:1].isupper()):
        return None
    if any(isinstance(a, (Str, Seq)) for a in v.args) or any(isinstance(a, (Str, Seq)) for _, a in v.kw):
        return v.func.id
    return None


class TempStructField(Rule):
    """`make().field` inside a loop where `make()` builds a struct with a `String` or list argument: the whole struct is
    constructed (allocation included) and destroyed every iteration to read one scalar. Read the field once above the loop."""

    id = "MA152"
    name = "temp-struct-field-in-loop"
    severity = "low"
    confidence = "high"
    bad = 'def s6() -> Cfg:\n    return Cfg("s6", "sic2", 6, 0.5)\n\nfor k in range(n):\n    gb[k] = book_g(W[k], s6().g)'
    good = "var gfix = s6().g\nfor k in range(n):\n    gb[k] = book_g(W[k], gfix)"
    why = "pm-simfast: two String allocations per night x 1,702 nights per cell for one Float64"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            if s.kind in ("def", "struct", "comptime") or not s.enclosing_loops():
                continue
            for n in stmt_nodes(s):
                for x in walk(n):
                    if not (isinstance(x, Attr) and isinstance(x.obj, Call) and isinstance(x.obj.func, Name)):
                        continue
                    c = x.obj
                    if c.args or c.kw:
                        continue
                    ctor = _heap_ctor_return(ctx, c.func.id)
                    if ctor is None:
                        continue
                    yield self.finding(
                        ctx, x, f"`{unparse(x)}` builds a `{ctor}` (heap fields) every iteration to read `.{x.attr}`",
                        f"var {x.attr}0 = {unparse(x)} above the loop",
                        severity="medium" if hot_depth(s) >= 2 else None,
                    )  # fmt: skip


def _fresh_list_return(ctx: FileCtx, name: str) -> bool:
    """free function that declares a `List[...]` local with a constructor and returns it (`return w^`)."""
    e = ctx.index.free_func(name, ctx.display)
    if e is None or e.info is None:
        return False
    made: set[str] = set()
    for s in _own_stmts(e.stmt):
        if s.kind == "var" and s.decl and len(s.decl[0]) == 1:
            v = s.decl[2]
            if isinstance(v, Call) and isinstance(v.func, Sub) and root_name(v.func) == "List":
                made.add(s.decl[0][0])
    if not made:
        return False
    rets = [_ret(s) for s in _own_stmts(e.stmt) if s.kind == "return"]
    return bool(rets) and all(isinstance(r, Transfer) and isinstance(r.operand, Name) and r.operand.id in made for r in rets if r is not None)


class FreshListPerCall(Rule):
    """A helper that allocates a `List`, fills it and returns it (`return w^`) is called inside a loop: one allocation and
    one free per iteration that MA301 cannot see, because the constructor is in the callee. Give the helper a caller-owned
    output (a `mut` list it clears, or a pointer into a scratch buffer) and keep the returning wrapper for cold callers."""

    id = "MA153"
    name = "fresh-list-per-call"
    severity = "low"
    confidence = "medium"
    risk = "api"
    bad = (
        "def tilt(x: List[Float64]) -> List[Float64]:\n    var w = List[Float64](length=len(x), fill=1.0)\n    return w^\n\n"
        "for k in range(nights):\n    var w = tilt(xs[k])\n    acc += w[0]"
    )
    good = (
        "def tilt_into(x: List[Float64], mut w: List[Float64]):\n    w.resize(len(x), 1.0)\n\n"
        "var w = List[Float64]()\nfor k in range(nights):\n    tilt_into(xs[k], w)\n    acc += w[0]"
    )
    why = "pm-simfast: 53 k allocations per simulated cell (96% <= 256 B) from per-row / per-night helper results"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        seen: set[tuple[int, str]] = set()
        for s in ctx.mod.walk():
            if s.kind in ("def", "struct", "comptime"):
                continue
            loops = s.enclosing_loops()
            if not loops:
                continue
            for n in stmt_nodes(s):
                for x in walk(n):
                    if not (isinstance(x, Call) and isinstance(x.func, Name)):
                        continue
                    f = x.func.id
                    if (id(loops[0]), f) in seen or not _fresh_list_return(ctx, f):
                        continue
                    seen.add((id(loops[0]), f))
                    yield self.finding(
                        ctx, x, f"`{f}()` allocates and returns a new List on every iteration of the loop at L{loops[0].line}",
                        f"add `{f}_into(..., mut out)` (or a pointer kernel) and reuse one buffer across iterations",
                        severity="medium" if hot_depth(s) >= 2 else None,
                    )  # fmt: skip


def _fma_acc(s: Stmt) -> str | None:
    """`acc = x.fma(y, acc)` -> acc."""
    if s.kind != "assign" or not s.assign or len(s.assign[0]) != 1:
        return None
    tgt, val = s.assign[0][0], s.assign[1]
    if not (isinstance(tgt, Name) and isinstance(val, Call) and isinstance(val.func, Attr) and val.func.attr == "fma"):
        return None
    if len(val.args) != 2 or not (isinstance(val.args[1], Name) and val.args[1].id == tgt.id):
        return None
    return tgt.id


class FmaChainWidth(Rule):
    """An innermost loop whose body advances three to seven SIMD accumulators with `acc = x.fma(w, acc)`. Each
    accumulator is a dependency chain (4 cycles per FMA on Zen, 5 on Haswell / Broadwell, 4 on Skylake+) and the core has two
    FMA ports, so four chains can use at most 0.8-1.0 of the 2 FMA slots per cycle unless the out-of-order window overlaps
    neighbouring blocks. Widen the block to eight or more accumulators (16 ymm registers allow it). When every accumulator is
    its own output (a row of a product) the result is bit-identical; splitting one reduction into more accumulators is not."""

    id = "MA154"
    name = "fma-chain-width"
    severity = "low"
    confidence = "low"
    risk = "none"
    bad = (
        "for k in range(F):\n    var xk = V(xr[k])\n    z0 = xk.fma(w.unsafe_load[width=8](k * H), z0)\n"
        "    z1 = xk.fma(w.unsafe_load[width=8](k * H + 8), z1)"
    )
    good = (
        "for k in range(F):\n    var xk = V(xr[k])\n    z0 = xk.fma(w.unsafe_load[width=8](k * H), z0)\n"
        "    # ... z1 .. z6 ...\n    z7 = xk.fma(w.unsafe_load[width=8](k * H + 56), z7)"
    )
    why = "pm-simfast headfast z row: 4 -> 8 accumulators, same bits; see tests/simfast/RESULTS.md for the measured gain"
    options = {"min_chains": 8}

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        need = int(self.options.get("min_chains", 8))  # type: ignore[arg-type]
        for loop in ctx.mod.walk():
            if loop.kind != "for" or loop.comptime or any(b.kind in ("for", "while") for b in loop.walk()):
                continue
            accs = [a for a in (_fma_acc(b) for b in loop.body) if a is not None]
            if len(accs) < 3 or len(set(accs)) != len(accs) or len(accs) >= need:
                continue
            if any(b.kind not in ("assign", "var") for b in loop.body):
                continue
            yield self.finding(
                ctx, loop, f"{len(accs)} FMA accumulators ({', '.join(accs)}) per pass: the chains leave FMA ports idle",
                f"widen the block to {need} accumulators (bit-identical when each is its own output)",
            )  # fmt: skip
