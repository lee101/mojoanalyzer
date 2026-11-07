from __future__ import annotations

from ..core import Rule
from .api import LiteralArgParam
from .gpu import RedundantSync
from .loops import (
    BoundsCheckedIndex,
    ComptimeUnroll,
    LiteralSimdWidth,
    LoopInterchange,
    ParallelizeCandidate,
    RangeLenIndex,
    ReciprocalDivide,
    SimdReduction,
    VectorizeElementwise,
)
from .memory import (
    CopyInLoop,
    CopyIntoReadArg,
    DictDoubleLookup,
    ListMembership,
    ListReserve,
    QuadraticListOps,
    StringConcatLoop,
    VarArgReadOnly,
)

ALL: list[type[Rule]] = sorted(
    [
        ComptimeUnroll,
        VectorizeElementwise,
        SimdReduction,
        LiteralSimdWidth,
        ParallelizeCandidate,
        ListReserve,
        StringConcatLoop,
        DictDoubleLookup,
        CopyInLoop,
        VarArgReadOnly,
        RangeLenIndex,
        ReciprocalDivide,
        BoundsCheckedIndex,
        LoopInterchange,
        QuadraticListOps,
        ListMembership,
        RedundantSync,
        LiteralArgParam,
        CopyIntoReadArg,
    ],
    key=lambda r: r.id,
)
BY_ID = {r.id: r for r in ALL}
