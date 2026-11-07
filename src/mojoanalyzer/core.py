from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from .expr import Attr, BinOp, Call, Name, Node, Num, Seq, Str, Sub, Transfer, path_of, root_name, unparse, walk
from .parser import FuncInfo, Stmt, parse, tuple_items
from .tokenizer import Token

SEVERITIES = ("info", "low", "medium", "high")
CONFIDENCES = ("low", "medium", "high")
RISKS = {
    "none": "no semantic change",
    "fp": "changes FP rounding (not bit-exact)",
    "unsafe": "bounds checks removed",
    "threads": "concurrency: verify callees are thread-safe",
    "api": "signature change",
    "codesize": "larger code / compile time",
}
FLOAT_TYPES = {"Float16", "Float32", "Float64", "BFloat16", "Float8_e4m3fn", "Float8_e5m2"}
FLOAT_DTYPES = {"DType.float16", "DType.float32", "DType.float64", "DType.bfloat16"}
PURE_BUILTINS = {
    "len", "min", "max", "abs", "sqrt", "exp", "log", "log2", "log10", "exp2", "tanh", "sin", "cos", "tan", "floor",
    "ceil", "round", "fma", "Float64", "Float32", "Float16", "Int", "Int32", "Int64", "UInt8", "UInt32", "UInt64",
    "Bool", "range", "isnan", "isinf", "isfinite", "clamp", "pow", "erf", "atan", "atan2", "copysign", "trunc",
    "SIMD", "Scalar", "UInt", "Int8", "Int16", "UInt16", "rsqrt", "log1p", "expm1", "cbrt", "hypot", "String",
}  # fmt: skip
MATH_FUNCS = {
    "sqrt", "exp", "log", "log2", "log10", "exp2", "tanh", "sin", "cos", "tan", "floor", "ceil", "fma", "abs", "min",
    "max", "rsqrt", "log1p", "expm1", "cbrt", "trunc", "copysign", "erf", "atan",
}  # fmt: skip
READONLY_METHODS = {
    "copy", "byte_length", "find", "rfind", "startswith", "endswith", "split", "strip", "lstrip", "rstrip", "get",
    "keys", "values", "items", "count", "index", "as_bytes", "lower", "upper", "isdigit", "__len__", "__contains__",
    "codepoints", "reduce_add", "reduce_max", "reduce_min", "reduce_mul", "cast", "value", "tag", "is_some", "is_none",
    "or_else", "join", "format", "eq", "ne", "lt", "le", "gt", "ge", "select", "contains", "unsafe_get",
}  # fmt: skip
ITEM_TYPES = ("List", "InlineArray", "Span", "Pointer", "UnsafePointer", "LegacyUnsafePointer", "OwnedPointer")


@dataclass(slots=True)
class Finding:
    path: str
    line: int
    col: int
    rule: str
    severity: str
    confidence: str
    risk: str
    message: str
    suggestion: str

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "line": self.line,
            "col": self.col,
            "rule": self.rule,
            "severity": self.severity,
            "confidence": self.confidence,
            "risk": self.risk,
            "risk_note": RISKS[self.risk],
            "message": self.message,
            "suggestion": self.suggestion,
        }

    def format(self) -> str:
        risk = "" if self.risk == "none" else f" [risk: {RISKS[self.risk]}]"
        return (
            f"{self.path}:{self.line}:{self.col + 1} {self.rule} {self.severity} {self.confidence} "
            f"{self.message} -> {self.suggestion}{risk}"
        )


class Rule:
    id: ClassVar[str]
    name: ClassVar[str]
    severity: ClassVar[str]
    confidence: ClassVar[str] = "high"
    risk: ClassVar[str] = "none"
    bad: ClassVar[str] = ""
    good: ClassVar[str] = ""

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        raise NotImplementedError

    def finding(
        self,
        ctx: FileCtx,
        at: Stmt | Node | Token,
        message: str,
        suggestion: str,
        *,
        severity: str | None = None,
        confidence: str | None = None,
        risk: str | None = None,
    ) -> Finding:
        return Finding(
            ctx.display,
            at.line,
            at.col,
            self.id,
            severity or self.severity,
            confidence or self.confidence,
            risk or self.risk,
            message,
            suggestion,
        )


@dataclass
class FuncEntry:
    info: FuncInfo
    stmt: Stmt
    path: str
    owner: str | None


@dataclass
class Index:
    funcs: dict[str, list[FuncEntry]] = field(default_factory=dict)
    calls: dict[str, list[tuple[Call, str]]] = field(default_factory=dict)
    bare_refs: set[str] = field(default_factory=set)

    def add(self, path: str, mod: Stmt) -> None:
        for s in mod.walk():
            if s.kind == "def" and s.fn is not None:
                owner = s.parent.toks[1].value if s.parent and s.parent.kind in ("struct", "trait") else None
                self.funcs.setdefault(s.fn.name, []).append(FuncEntry(s.fn, s, path, owner))
            for n in stmt_nodes(s):
                for x in walk(n):
                    if isinstance(x, Call):
                        if isinstance(x.func, Name):
                            self.calls.setdefault(x.func.id, []).append((x, path))
                        self.bare_refs.update(a.id for a in [*x.args, *(v for _, v in x.kw)] if isinstance(a, Name))
                    elif isinstance(x, Sub):
                        self.bare_refs.update(a.id for a in x.index if isinstance(a, Name))
                    elif isinstance(x, Name) and x is n:
                        self.bare_refs.add(x.id)

    def lookup(self, name: str, path: str | None = None) -> list[FuncEntry]:
        es = self.funcs.get(name, [])
        local = [e for e in es if e.path == path]
        return local or es

    def free_func(self, name: str, path: str | None = None) -> FuncEntry | None:
        allf = self.funcs.get(name, [])
        es = [e for e in allf if e.owner is None and e.stmt.parent is not None and e.stmt.parent.kind == "module"]
        local = [e for e in es if e.path == path]
        if path is not None and local:
            return local[0] if len(local) == 1 and len([e for e in allf if e.path == path]) == 1 else None
        return es[0] if len(es) == 1 and len(allf) == 1 else None


def stmt_nodes(s: Stmt) -> list[Node]:
    out: list[Node | None] = []
    if s.kind == "expr":
        out.append(s.expr)
    elif s.kind == "assign" and s.assign:
        out.extend(s.assign[0])
        out.append(s.assign[1])
    elif s.kind == "augassign" and s.aug:
        out.extend([s.aug[0], s.aug[2]])
    elif s.kind in ("var", "comptime") and s.decl:
        out.append(s.decl[2])
    elif s.kind in ("if", "elif", "while"):
        out.append(s.cond)
    elif s.kind == "for" and s.loop:
        out.append(s.loop[1])
    elif s.kind in ("return", "raise", "yield", "assert"):
        from .expr import parse_expr

        out.append(parse_expr(s.toks[1:]))
    return [n for n in out if n is not None]


class FileCtx:
    def __init__(self, path: Path, src: str, index: Index | None = None, display: str | None = None) -> None:
        self.path = path
        self.display = display or str(path)
        self.src = src
        self.lines = src.splitlines()
        self.mod = parse(src)
        self.index = index or Index()
        self.aliases: dict[str, str] = {}
        self.module_comptime: dict[str, Node] = {}
        self.structs: dict[str, dict[str, str]] = {}
        for s in self.mod.body:
            if s.kind == "comptime" and s.decl and len(s.decl[0]) == 1 and s.decl[2] is not None:
                self.aliases[s.decl[0][0]] = unparse(s.decl[2])
                self.module_comptime[s.decl[0][0]] = s.decl[2]
        for s in self.mod.walk():
            if s.kind == "struct" and len(s.toks) > 1:
                fields: dict[str, str] = {}
                for b in s.body:
                    if b.kind == "var" and b.decl and b.decl[1]:
                        for nm in b.decl[0]:
                            fields[nm] = b.decl[1]
                    elif b.kind == "comptime" and b.decl and b.decl[2] is not None and len(b.decl[0]) == 1:
                        fields.setdefault("@" + b.decl[0][0], unparse(b.decl[2]))
                self.structs[s.toks[1].value] = fields
        self._envs: dict[int, dict[str, str]] = {}

    def defs(self) -> Iterator[Stmt]:
        for s in self.mod.walk():
            if s.kind == "def":
                yield s

    def env(self, fn: Stmt | None) -> dict[str, str]:
        if fn is None:
            return {}
        key = id(fn)
        if key in self._envs:
            return self._envs[key]
        outer = fn.func()
        env = dict(self.env(outer)) if outer is not None else {}
        st = fn.parent
        if st is not None and st.kind == "struct" and len(st.toks) > 1:
            for k, v in self.structs.get(st.toks[1].value, {}).items():
                env["self." + k] = v
        info = fn.fn
        if info:
            for p in info.params:
                if p.type:
                    env[p.name] = p.type
            for p in info.cparams:
                if p.type:
                    env[p.name] = p.type
        for s in fn.walk():
            if s.func() is not fn:
                continue
            if s.kind == "var" and s.decl:
                ns, typ, val = s.decl
                if len(ns) == 1:
                    t = typ or self.infer(val, env)
                    if t and ns[0] not in env:
                        env[ns[0]] = t
            elif s.kind == "comptime" and s.decl and len(s.decl[0]) == 1 and s.decl[2] is not None:
                env.setdefault("@" + s.decl[0][0], unparse(s.decl[2]))
        self._envs[key] = env
        return env

    def resolve(self, t: str | None, env: dict[str, str] | None = None) -> str | None:
        if t is None:
            return None
        for _ in range(4):
            m = re.match(r"^([A-Za-z_]\w*)(.*)$", t)
            if not m:
                return t
            head, rest = m.groups()
            if env is not None and "@" + head in env:
                t = env["@" + head] + rest
            elif head in self.aliases:
                t = self.aliases[head] + rest
            else:
                return t
        return t

    def infer(self, val: Node | None, env: dict[str, str]) -> str | None:
        match val:
            case Num():
                return "Float64" if val.is_float else "Int"
            case Str():
                return "String"
            case Call(func=f) if isinstance(f, (Name, Sub)):
                head = f.id if isinstance(f, Name) else root_name(f)
                if head and head[:1].isupper():
                    if head in self.aliases or head in env or "@" + head in env:
                        return self.resolve(unparse(f), env)
                    return unparse(f)
            case Call(func=Attr(obj=o, attr="copy")):
                return self.type_of(o, env)
            case Call(func=Attr(obj=o, attr="unsafe_ptr"), args=[]):
                t = self.type_of(o, env)
                e = elem_type(t) if t else None
                return f"Pointer[{e}]" if e else None
            case Sub() | Name() | Attr():
                return self.type_of(val, env)
            case Seq(kind="list", items=items) if items and all(isinstance(i, Num) and i.is_float for i in items):
                return "List[Float64]"
        return None

    def type_of(self, n: Node | None, env: dict[str, str]) -> str | None:
        if n is None:
            return None
        p = path_of(n)
        if p is not None and p in env:
            return self.resolve(env[p], env)
        if isinstance(n, Sub) and len(n.index) == 1:
            t = self.type_of(n.obj, env)
            if t:
                return elem_type(t)
        if isinstance(n, Num):
            return "Float64" if n.is_float else "Int"
        if isinstance(n, Call) and isinstance(n.func, Name) and n.func.id in FLOAT_TYPES | {"Int", "String"}:
            return n.func.id
        return None

    def comptime_int(self, n: Node | None, fn: Stmt | None) -> int | None:
        if isinstance(n, Num) and not n.is_float:
            return n.int_value()
        if isinstance(n, Name):
            v = None
            if fn is not None:
                for s in fn.walk():
                    if s.kind == "comptime" and s.decl and s.decl[0] == [n.id]:
                        v = s.decl[2]
            if v is None:
                v = self.module_comptime.get(n.id)
            if isinstance(v, Num) and not v.is_float:
                return v.int_value()
        return None


def elem_type(t: str) -> str | None:
    m = re.match(r"^(\w+)\[(.*)\]$", t.replace(" ", ""))
    if not m:
        return None
    head, inner = m.groups()
    if head not in ITEM_TYPES:
        return None
    depth = 0
    for i, c in enumerate(inner):
        if c in "[(":
            depth += 1
        elif c in "])":
            depth -= 1
        elif c == "," and depth == 0:
            return inner[:i]
    return inner


def is_float_type(t: str | None) -> bool:
    if not t:
        return False
    t = t.replace(" ", "")
    if t in FLOAT_TYPES:
        return True
    m = re.match(r"^(Scalar|SIMD)\[(DType\.\w+)", t)
    return bool(m and m.group(2) in FLOAT_DTYPES)


def is_list_type(t: str | None) -> bool:
    return bool(t) and t.replace(" ", "").startswith("List[")  # type: ignore[union-attr]


def is_float_buffer(t: str | None) -> bool:
    if not t:
        return False
    e = elem_type(t)
    return is_float_type(e)


def body_stmts(stmts: list[Stmt]) -> Iterator[Stmt]:
    for s in stmts:
        yield s
        yield from s.walk()


def assigned_names(stmts: list[Stmt]) -> set[str]:
    out: set[str] = set()
    for s in body_stmts(stmts):
        if s.kind == "var" and s.decl:
            out.update(s.decl[0])
        elif s.kind == "assign" and s.assign:
            for t in s.assign[0]:
                for x in tuple_items(t):
                    r = root_name(x)
                    if r:
                        out.add(r)
        elif s.kind == "augassign" and s.aug and s.aug[0] is not None:
            r = root_name(s.aug[0])
            if r:
                out.add(r)
        elif s.kind == "for" and s.loop:
            out.update(s.loop[0])
        elif s.kind == "def" and s.fn:
            out.add(s.fn.name)
    return out


def declared_names(stmts: list[Stmt]) -> set[str]:
    out: set[str] = set()
    for s in body_stmts(stmts):
        if s.kind == "var" and s.decl:
            out.update(s.decl[0])
        elif s.kind == "for" and s.loop:
            out.update(s.loop[0])
    return out


def all_nodes(stmts: list[Stmt]) -> Iterator[tuple[Stmt, Node]]:
    for s in body_stmts(stmts):
        for n in stmt_nodes(s):
            for x in walk(n):
                yield s, x


def may_mutate(stmts: list[Stmt], name: str, index: Index | None = None, allow_calls: bool = False) -> bool:
    for s in body_stmts(stmts):
        if s.kind == "assign" and s.assign:
            for t in s.assign[0]:
                if any(root_name(x) == name for x in tuple_items(t)):
                    return True
        elif s.kind == "augassign" and s.aug and s.aug[0] is not None:
            if root_name(s.aug[0]) == name:
                return True
        elif (
            (s.kind == "for" and s.loop and name in s.loop[0])
            or (s.kind == "var" and s.decl and name in s.decl[0])
            or s.kind == "def"
        ):
            return True
        if s.kind == "for" and s.toks and any(t.value == "ref" for t in s.toks[:3]):
            if s.loop and s.loop[1] is not None and name in {root_name(s.loop[1])}:
                return True
        for n in stmt_nodes(s):
            for x in walk(n):
                if isinstance(x, Transfer) and root_name(x.operand) == name:
                    return True
                if isinstance(x, Call):
                    f = x.func
                    if isinstance(f, Attr) and root_name(f.obj) == name and f.attr not in READONLY_METHODS:
                        return True
                    if not allow_calls:
                        callee = f.id if isinstance(f, Name) else None
                        for i, a in enumerate(x.args):
                            if root_name(a) == name and not _read_arg(callee, i, index) and not isinstance(a, Call):
                                return True
                        for k, v in x.kw:
                            if root_name(v) == name and not isinstance(v, Call) and not _read_kw(callee, k, index):
                                return True
    return False


def _read_arg(callee: str | None, i: int, index: Index | None) -> bool:
    if callee is None:
        return False
    if callee in PURE_BUILTINS or callee == "print":
        return True
    if index is None:
        return False
    es = index.funcs.get(callee)
    if not es:
        return False
    for e in es:
        ps = [p for p in e.info.params if p.name != "self"]
        if i >= len(ps) or ps[i].convention not in ("read", "borrowed"):
            return False
    return True


def _read_kw(callee: str | None, k: str, index: Index | None) -> bool:
    if callee == "print" or callee in PURE_BUILTINS:
        return True
    if callee is None or index is None:
        return False
    es = index.funcs.get(callee)
    if not es:
        return False
    for e in es:
        p = next((p for p in e.info.params if p.name == k), None)
        if p is None or p.convention not in ("read", "borrowed"):
            return False
    return True


def uses(stmts: list[Stmt], name: str) -> list[Node]:
    return [x for _, x in all_nodes(stmts) if isinstance(x, Name) and x.id == name]


def has_kind(stmts: list[Stmt], *kinds: str) -> bool:
    return any(s.kind in kinds for s in body_stmts(stmts))


def is_gpu_kernel(fn: Stmt | None) -> bool:
    if fn is None:
        return False
    if "gpu" not in fn._cache:
        fn._cache["gpu"] = _gpu_kernel(fn)
    return bool(fn._cache["gpu"])


def _gpu_kernel(fn: Stmt) -> bool:
    for s in fn.walk():
        for n in stmt_nodes(s):
            for x in walk(n):
                if isinstance(x, Name) and x.id in ("thread_idx", "block_idx", "global_idx", "barrier"):
                    return True
    return False


def range_args(n: Node | None) -> list[Node] | None:
    if isinstance(n, Call) and isinstance(n.func, Name) and n.func.id == "range" and 1 <= len(n.args) <= 3 and not n.kw:
        return n.args
    return None


def range_unit_step(n: Node | None) -> bool:
    a = range_args(n)
    return a is not None and (len(a) < 3 or (isinstance(a[2], Num) and a[2].text == "1"))


def trip_text(args: list[Node]) -> str:
    if len(args) == 1:
        return unparse(args[0])
    a, b = args[0], args[1]
    if isinstance(a, Num) and a.text == "0":
        return unparse(b)
    if isinstance(a, BinOp) and a.op == "-" and unparse(a.left) == unparse(b):
        return unparse(a.right)
    if isinstance(b, BinOp) and b.op == "+" and unparse(b.left) == unparse(a):
        return unparse(b.right)
    return f"{_paren(b)} - {_paren(a)}"


def _paren(n: Node) -> str:
    s = unparse(n)
    return f"({s})" if isinstance(n, BinOp) else s


def hot_depth(s: Stmt) -> int:
    d = 0
    cur: Stmt | None = s
    while cur is not None:
        fn = cur.func()
        d += sum(1 for a in cur.enclosing_loops())
        if fn is None:
            break
        if is_gpu_kernel(fn) and fn.parent is not None and fn.parent.kind == "module":
            d += 1
        if fn.parent is not None and fn.parent.kind not in {"module", "struct"}:
            if fn.fn and _closure_dispatched(fn):
                d += 1
            cur = fn
            continue
        break
    return d


def _closure_dispatched(fn: Stmt) -> bool:
    if "dispatched" not in fn._cache:
        fn._cache["dispatched"] = _dispatched(fn)
    return bool(fn._cache["dispatched"])


def _dispatched(fn: Stmt) -> bool:
    name = fn.fn.name if fn.fn else None
    outer = fn.func()
    if outer is None or name is None:
        return False
    for s in outer.walk():
        for n in stmt_nodes(s):
            for x in walk(n):
                if isinstance(x, Call) and _callee(x) in (
                    "parallelize",
                    "vectorize",
                    "sync_parallelize",
                    "elementwise",
                ):
                    if any(isinstance(a, Name) and a.id == name for a in x.args):
                        return True
                    if isinstance(x.func, Sub) and any(isinstance(a, Name) and a.id == name for a in x.func.index):
                        return True
    return False


def _callee(c: Call) -> str | None:
    f = c.func
    if isinstance(f, Sub):
        f = f.obj
    if isinstance(f, Name):
        return f.id
    if isinstance(f, Attr):
        return f.attr
    return None


callee = _callee
