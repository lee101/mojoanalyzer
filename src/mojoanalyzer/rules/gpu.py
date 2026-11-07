from __future__ import annotations

import itertools
from collections.abc import Iterable

from ..core import FileCtx, Finding, Rule
from ..expr import Attr, Call, Sub, unparse
from ..parser import Stmt


def _ctx_call(s: Stmt) -> tuple[str, str] | None:
    e = s.expr if s.kind == "expr" else None
    if not isinstance(e, Call):
        return None
    f = e.func.obj if isinstance(e.func, Sub) else e.func
    if isinstance(f, Attr):
        return unparse(f.obj), f.attr
    return None


class RedundantSync(Rule):
    """`ctx.synchronize()` immediately followed by another `ctx.enqueue_*` on the same context: the stream is
    in-order and the host does nothing in between, so the sync only adds a host round-trip."""

    id = "MA117"
    name = "redundant-gpu-sync"
    severity = "low"
    bad = "ctx.enqueue_copy(dev, host)\nctx.synchronize()\nctx.enqueue_function[k](dev, grid_dim=g, block_dim=b)"
    good = "ctx.enqueue_copy(dev, host)\nctx.enqueue_function[k](dev, grid_dim=g, block_dim=b)"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for blk in [ctx.mod.body, *(s.body for s in ctx.mod.walk() if s.body)]:
            for a, b in itertools.pairwise(blk):
                ca, cb = _ctx_call(a), _ctx_call(b)
                if ca is None or cb is None or ca[1] != "synchronize" or ca[0] != cb[0]:
                    continue
                if not cb[1].startswith("enqueue_"):
                    continue
                yield self.finding(
                    ctx, a, f"`{ca[0]}.synchronize()` directly before `{ca[0]}.{cb[1]}` on the same stream",
                    "drop it; sync once before the host reads results",
                )  # fmt: skip
