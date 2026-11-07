from __future__ import annotations

from ..core import (
    MATH_FUNCS,
    PURE_BUILTINS,
    READONLY_METHODS,
    FileCtx,
    Index,
    body_stmts,
    callee,
    elem_type,
    is_float_type,
    may_mutate,
    stmt_nodes,
)
from ..expr import Attr, BinOp, Call, Name, Node, Num, Str, Sub, Unary, path_of, walk
from ..parser import Stmt

FLOAT_CASTS = {"Float64", "Float32", "Float16", "BFloat16"}


def parent_map(n: Node) -> dict[int, Node]:
    out: dict[int, Node] = {}
    for x in walk(n):
        for c in x.children():
            out[id(c)] = x
    return out


def readonly_uses(stmts: list[Stmt], name: str, index: Index | None) -> bool:
    if may_mutate(stmts, name, index):
        return False
    for s in body_stmts(stmts):
        if s.kind in ("def", "struct"):
            return False
        nodes = stmt_nodes(s)
        for n in nodes:
            pm = parent_map(n)
            for x in walk(n):
                if not (isinstance(x, Name) and x.id == name):
                    continue
                p = pm.get(id(x))
                if isinstance(p, Sub) and p.obj is x:
                    continue
                if isinstance(p, Attr) and p.obj is x:
                    gp = pm.get(id(p))
                    if isinstance(gp, Call) and gp.func is p and p.attr not in READONLY_METHODS:
                        return False
                    continue
                if isinstance(p, Call) and p.func is not x and callee(p) in PURE_BUILTINS | {"print"}:
                    continue
                if isinstance(p, BinOp) and p.op in ("in", "not in", "==", "!="):
                    continue
                if p is None and s.kind == "for" and s.loop and s.loop[1] is x:
                    continue
                return False
    return True


def float_dtype(t: str | None) -> str:
    m = {"Float64": "float64", "Float32": "float32", "Float16": "float16", "BFloat16": "bfloat16"}
    return f"DType.{m.get(t or '', 'float64')}"


class Elementwise:
    """Checks that an expression only combines lane values (`a[i]`, body temps) with loop-invariant scalars."""

    def __init__(self, ctx: FileCtx, env: dict[str, str], ivar: str, variant: set[str], temps: set[str]) -> None:
        self.ctx = ctx
        self.env = env
        self.ivar = ivar
        self.variant = variant
        self.temps = temps
        self.arrays: dict[str, str | None] = {}

    def lane_sub(self, n: Node) -> str | None:
        if isinstance(n, Sub) and len(n.index) == 1 and not n.kw:
            ix = n.index[0]
            p = path_of(n.obj)
            if isinstance(ix, Name) and ix.id == self.ivar and p is not None:
                return p
        return None

    def ok(self, n: Node | None) -> bool:
        if n is None:
            return False
        match n:
            case Num():
                return True
            case Name(id=i):
                if i == self.ivar:
                    return False
                return i in self.temps or i not in self.variant
            case Attr():
                p = path_of(n)
                return p is not None and p.split(".")[0] not in self.variant and p.split(".")[0] != self.ivar
            case Sub():
                p = self.lane_sub(n)
                if p is None:
                    return False
                t = self.ctx.type_of(n.obj, self.env)
                self.arrays[p] = elem_type(t) if t else None
                return True
            case BinOp(op=op, left=lft, right=r):
                return op in ("+", "-", "*", "/") and self.ok(lft) and self.ok(r)
            case Unary(op="-", operand=o):
                return self.ok(o)
            case Call(func=Name(id=f), args=args, kw=[]):
                return (f in MATH_FUNCS or f in FLOAT_CASTS) and bool(args) and all(self.ok(a) for a in args)
        return False

    def floats_only(self) -> bool:
        return bool(self.arrays) and all(is_float_type(t) for t in self.arrays.values())


NUMERIC_METHODS = {
    "unsafe_load", "unsafe_store", "load", "store", "cast", "reduce_add", "reduce_max", "reduce_min", "reduce_mul",
    "fma", "select", "eq", "ne", "lt", "le", "gt", "ge", "unsafe_bitcast", "unsafe_offset",
}  # fmt: skip
NUMERIC_ELEMS = {
    "Int", "Int8", "Int16", "Int32", "Int64", "UInt", "UInt8", "UInt16", "UInt32", "UInt64", "Float16", "Float32",
    "Float64", "BFloat16", "Bool",
}  # fmt: skip


def numeric_body(stmts: list[Stmt]) -> bool:
    """Loop body that only does arithmetic: calls limited to math builtins/casts and SIMD/pointer methods."""
    for s in body_stmts(stmts):
        if s.kind in ("def", "struct", "try", "with", "raise", "return", "yield"):
            return False
        for n in stmt_nodes(s):
            for x in walk(n):
                if isinstance(x, Str):
                    return False
                if isinstance(x, Call):
                    c = callee(x)
                    if isinstance(x.func, Attr) or (isinstance(x.func, Sub) and isinstance(x.func.obj, Attr)):
                        if c not in NUMERIC_METHODS:
                            return False
                    elif c not in (PURE_BUILTINS - {"String"}):
                        return False
    return True


def is_numeric_elem(t: str | None) -> bool:
    if not t:
        return False
    t = t.replace(" ", "")
    return t in NUMERIC_ELEMS or t.startswith(("SIMD[", "Scalar["))


def is_builtin_call(n: Node) -> bool:
    return isinstance(n, Call) and callee(n) in PURE_BUILTINS
