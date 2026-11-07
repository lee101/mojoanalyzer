from __future__ import annotations

from collections.abc import Iterable

from ..core import FileCtx, Finding, Rule, body_stmts, range_args
from ..expr import Name, Num, Unary
from ..parser import Stmt


class LiteralArgParam(Rule):
    """Function argument that every call site in the analyzed files passes as an integer/bool literal and that
    drives control flow (`range`, `if`, `while`): make it a compile-time parameter so the branch/trip count folds.
    One instantiation per distinct value."""

    id = "MA118"
    name = "literal-arg-to-param"
    severity = "info"
    confidence = "low"
    risk = "api"
    bad = "def f(x: List[Float64], k: Int): for i in range(k): ...\nf(a, 4); f(b, 8)"
    good = "def f[k: Int](x: List[Float64]): comptime for i in range(k): ...\nf[4](a); f[8](b)"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.defs():
            info = s.fn
            if info is None or s.parent is None or s.parent.kind != "module" or info.name == "main":
                continue
            e = ctx.index.free_func(info.name)
            if e is None or e.stmt is not s or info.name in ctx.index.bare_refs:
                continue
            calls = ctx.index.calls.get(info.name, [])
            if len(calls) < 2:
                continue
            for i, p in enumerate(info.params):
                if p.convention != "read" or p.type not in ("Int", "Bool") or p.default is not None:
                    continue
                vals: set[str] = set()
                ok = True
                for c, _ in calls:
                    if c.kw or i >= len(c.args):
                        ok = False
                        break
                    a = c.args[i]
                    if isinstance(a, Num) and not a.is_float:
                        vals.add(a.text)
                    elif isinstance(a, Name) and a.id in ("True", "False"):
                        vals.add(a.id)
                    else:
                        ok = False
                        break
                if not ok or not vals:
                    continue
                if not self._drives_control(s, p.name, p.type):
                    continue
                yield self.finding(
                    ctx, p.tok,
                    f"`{p.name}` of {info.name}() is a literal at all {len(calls)} call sites "
                    f"({', '.join(sorted(vals))}) and drives a loop bound / hot branch",
                    f"def {info.name}[{p.name}: {p.type}](...) and call {info.name}[{sorted(vals)[0]}](...)",
                )  # fmt: skip

    def _drives_control(self, s: Stmt, name: str, typ: str) -> bool:
        for st in body_stmts(s.body):
            if typ == "Bool" and st.kind in ("if", "elif") and st.enclosing_loops():
                c = st.cond
                if isinstance(c, Unary) and c.op == "not":
                    c = c.operand
                if isinstance(c, Name) and c.id == name:
                    return True
            if typ == "Int" and st.kind == "for" and st.loop:
                ra = range_args(st.loop[1])
                if ra and any(isinstance(a, Name) and a.id == name for a in ra):
                    return True
        return False
