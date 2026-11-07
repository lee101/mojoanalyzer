from __future__ import annotations

from ..core import Rule
from .api import LiteralArgParam
from .correctness import (
    DiscardedStatus,
    DuplicateCondition,
    EdgeIndex,
    FloatEquality,
    IdenticalBranches,
    IntTrueDivision,
    IntTruncation,
    MathDomain,
    NanCompare,
    OneSidedTolerance,
    SuspiciousIdentity,
    SwappedClamp,
    UnguardedDivision,
    UnitScale,
    UnreachableCode,
)
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
        UnguardedDivision,
        IntTruncation,
        FloatEquality,
        NanCompare,
        MathDomain,
        IntTrueDivision,
        OneSidedTolerance,
        SwappedClamp,
        SuspiciousIdentity,
        DuplicateCondition,
        IdenticalBranches,
        UnreachableCode,
        EdgeIndex,
        DiscardedStatus,
        UnitScale,
    ],
    key=lambda r: r.id,
)
BY_ID = {r.id: r for r in ALL}
