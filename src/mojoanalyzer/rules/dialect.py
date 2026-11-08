from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import ClassVar

from ..core import FileCtx, Finding, Rule, stmt_nodes
from ..expr import Attr, BinOp, Call, Name, Sub, path_of, walk
from ..parser import Stmt
from ..tokenizer import K, Token

STD_MODULES = {
    "sys", "math", "memory", "algorithm", "collections", "time", "gpu", "os", "builtin", "python", "utils",
    "testing", "random", "pathlib", "bit", "benchmark", "hashlib", "io", "subprocess", "tempfile", "complex",
    "itertools", "logger", "runtime", "compile", "reflection", "ffi",
}  # fmt: skip
RENAMED = {
    "simdwidthof": "simd_width_of", "sizeof": "size_of", "alignof": "align_of", "bitwidthof": "bit_width_of",
    "str": "String(x)", "DTypePointer": "Pointer[Scalar[dtype]]", "Reference": "a `ref` binding or Pointer(to=x)",
    "StringRef": "StringSlice", "Stringable": "Writable (+ write_to)", "InlinedFixedVector": "InlineArray / List",
    "isinstance": "compile-time dispatch (traits / comptime if)", "MutableAnyOrigin": "MutAnyOrigin",
    "MutableStaticOrigin": "StaticConstantOrigin / MutAnyOrigin", "StaticMutableOrigin": "MutAnyOrigin",
    "memset_zero": "unsafe_memset_zero",
}  # fmt: skip
DECORATORS = {
    "value": "@fieldwise_init + (Copyable, Movable) conformance",
    "register_passable": "conform to TrivialRegisterPassable",
}


def all_stmts(ctx: FileCtx) -> Iterator[Stmt]:
    for s in ctx.mod.walk():
        yield from s.decorators
        yield s


def defined_names(ctx: FileCtx) -> set[str]:
    out: set[str] = set()
    for s in ctx.mod.walk():
        if s.kind == "def" and s.fn:
            out.add(s.fn.name)
            out.update(p.name for p in s.fn.params)
            out.update(p.name for p in s.fn.cparams)
        elif s.kind in ("struct", "trait") and len(s.toks) > 1:
            out.add(s.toks[1].value)
        elif s.kind in ("var", "comptime") and s.decl:
            out.update(s.decl[0])
        elif s.kind == "for" and s.loop:
            out.update(s.loop[0])
        elif s.kind in ("import", "from"):
            vals = [t.value for t in s.toks]
            if "as" in vals:
                out.update(vals[i + 1] for i, v in enumerate(vals) if v == "as" and i + 1 < len(vals))
            if s.kind == "from" and len(vals) > 1 and vals[1] != "std" and "import" in vals:
                out.update(t.value for t in s.toks[vals.index("import") + 1 :] if t.kind is K.NAME)
    return out


def _prev_is_dot(toks: list[Token], i: int) -> bool:
    return i > 0 and toks[i - 1].is_op(".")


class RemovedKeyword(Rule):
    """`fn`, `let` and `alias` were removed (Mojo 1.0): the file does not parse. `fn` is still reserved, so it
    cannot be used as a variable or argument name either."""

    id = "MA401"
    name = "removed-keyword"
    severity = "high"
    bad = "fn f(x: Int) -> Int:\n    let y = x\nalias N = 4"
    good = "def f(x: Int) -> Int:\n    var y = x\ncomptime N = 4"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            t0 = s.toks[0] if s.toks else None
            if t0 is None:
                continue
            if s.kind == "def" and t0.value == "fn":
                yield self.finding(ctx, t0, "`fn` was removed", "use `def`")
            elif s.kind == "comptime" and t0.value == "alias":
                yield self.finding(ctx, t0, "`alias` was removed", "use `comptime NAME = ...`")
            elif t0.value == "let" and len(s.toks) > 2 and s.toks[1].kind is K.NAME and s.kind == "assign":
                yield self.finding(ctx, t0, "`let` was removed", "use `var`")
            for i, t in enumerate(s.toks):
                if t.value != "fn" or i == 0 or t.kind is not K.NAME:
                    continue
                nxt = s.toks[i + 1] if i + 1 < len(s.toks) else None
                if s.toks[i - 1].is_name("var") or (nxt is not None and nxt.is_op(":") and s.kind == "def"):
                    yield self.finding(ctx, t, "`fn` is a reserved word", "rename the binding")


class RemovedConvention(Rule):
    """Argument conventions `owned`/`inout`/`borrowed` and the `read` capture convention were removed; `out` is
    reserved and cannot name an argument. The signature does not parse."""

    id = "MA402"
    name = "removed-convention"
    severity = "high"
    bad = "def f(owned a: List[Int], inout b: Int, out: Int): ...\ndef g() {read x}: ..."
    good = "def f(var a: List[Int], mut b: Int, res: Int): ...\ndef g() {imm x}: ..."
    NEW: ClassVar[dict[str, str]] = {"owned": "var", "inout": "mut", "borrowed": "drop it (read is the default)"}

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.defs():
            if s.fn is None:
                continue
            for p in [*s.fn.params, *s.fn.cparams]:
                if p.convention in self.NEW:
                    yield self.finding(
                        ctx, p.tok, f"`{p.convention}` convention was removed", f"use {self.NEW[p.convention]}"
                    )
                if p.name == "out" and p.convention == "read":
                    yield self.finding(ctx, p.tok, "`out` is reserved as an argument name", "rename the argument")
            depth = 0
            for t in s.toks:
                if t.is_op("{"):
                    depth += 1
                elif t.is_op("}"):
                    depth -= 1
                elif depth > 0 and t.is_name("read"):
                    yield self.finding(ctx, t, "`read` capture convention was removed", "use `imm`")


class ParameterDecorator(Rule):
    """`@parameter for` / `@parameter if` no longer parse ("statement does not support decorators"): use
    `comptime for` / `comptime if`. `@parameter` on a nested `def` still compiles but is deprecated."""

    id = "MA403"
    name = "parameter-decorator"
    severity = "high"
    bad = "@parameter\nfor i in range(4):\n    ..."
    good = "comptime for i in range(4):\n    ..."

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            for d in s.decorators:
                if len(d.toks) != 2 or d.toks[1].value != "parameter":
                    continue
                if s.kind in ("for", "if"):
                    yield self.finding(ctx, d, f"`@parameter {s.kind}` does not parse", f"`comptime {s.kind}`")
                elif s.kind == "def":
                    yield self.finding(
                        ctx, d, "`@parameter` on a closure is deprecated",
                        "declare captures (`def k(i: Int) {mut p}:`) or use `@__parameter`", severity="low",
                    )  # fmt: skip


class BareStdImport(Rule):
    """The standard library is namespaced under `std.`: `from math import sqrt` fails with "unable to locate
    module 'math'" unless a local module of that name exists."""

    id = "MA404"
    name = "bare-std-import"
    severity = "high"
    bad = "from math import sqrt"
    good = "from std.math import sqrt"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        here = ctx.path.parent if ctx.path.name else Path(".")
        for s in ctx.mod.body:
            if s.kind not in ("import", "from") or len(s.toks) < 2:
                continue
            mod = s.toks[1]
            if mod.kind is not K.NAME or mod.value not in STD_MODULES:
                continue
            if (here / f"{mod.value}.mojo").exists() or (here / mod.value).is_dir():
                continue
            if any(p.endswith(f"/{mod.value}.mojo") or p == f"{mod.value}.mojo" for p in self._paths(ctx)):
                continue
            yield self.finding(ctx, mod, f"`{mod.value}` is a std module", f"`{s.toks[0].value} std.{mod.value} ...`")

    def _paths(self, ctx: FileCtx) -> set[str]:
        return {e.path for es in ctx.index.funcs.values() for e in es}


class RemovedName(Rule):
    """Builtins, types and decorators that were renamed or removed by Mojo 1.x (`sizeof`, `str()`,
    `DTypePointer`, `StringRef`, `Stringable`, `@value`, `@register_passable`, `memset_zero`, ...): "use of
    unknown declaration". Names the file defines itself are skipped."""

    id = "MA405"
    name = "removed-name"
    severity = "high"
    bad = "@value\nstruct P:\n    var x: Int\ndef f(x: Int) -> String:\n    return str(sizeof[Int]())"
    good = (
        "@fieldwise_init\nstruct P(Copyable, Movable):\n    var x: Int\n"
        "def f(x: Int) -> String:\n    return String(size_of[Int]())"
    )

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        own = defined_names(ctx)
        for s in all_stmts(ctx):
            if s.kind == "decorator":
                if len(s.toks) > 1 and s.toks[1].value in DECORATORS and s.toks[1].value not in own:
                    nm = s.toks[1].value
                    yield self.finding(ctx, s.toks[1], f"`@{nm}` was removed", DECORATORS[nm])
                continue
            for i, t in enumerate(s.toks):
                if t.kind is not K.NAME or t.value not in RENAMED or t.value in own or _prev_is_dot(s.toks, i):
                    continue
                if t.value == "str":
                    nxt = s.toks[i + 1] if i + 1 < len(s.toks) else None
                    if nxt is None or not nxt.is_op("("):
                        continue
                yield self.finding(ctx, t, f"`{t.value}` no longer exists", f"use {RENAMED[t.value]}")


SIMD_T = ("SIMD[", "Scalar[", "Float64", "Float32", "Float16", "BFloat16")


class RemovedMethod(Rule):
    """Methods that changed shape: `UnsafePointer[T].alloc(n)` (now `alloc[T](n)`), `List.capacity` (now a
    method, `capacity()`), SIMD/scalar `.min()`/`.max()` (free `min`/`max`). `String.reserve` is deprecated in
    favour of `reserve_bytes`."""

    id = "MA406"
    name = "removed-method"
    severity = "high"
    bad = "var p = UnsafePointer[Int].alloc(n)\nvar c = xs.capacity\nvar m = a.max(b)"
    good = "var p = alloc[Int](n)\nvar c = xs.capacity()\nvar m = max(a, b)"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            env = ctx.env(s.func())
            for n in stmt_nodes(s):
                pm: dict[int, object] = {}
                for x in walk(n):
                    for c in x.children():
                        pm[id(c)] = x
                for x in walk(n):
                    if not isinstance(x, Attr):
                        continue
                    p = pm.get(id(x))
                    called = isinstance(p, Call) and p.func is x
                    if x.attr == "alloc" and isinstance(x.obj, Sub) and isinstance(x.obj.obj, Name):
                        if x.obj.obj.id in ("UnsafePointer", "Pointer") and called:
                            yield self.finding(ctx, x, f"`{x.obj.obj.id}[T].alloc` no longer exists",
                                               "`from std.memory import alloc`; `alloc[T](n)`")  # fmt: skip
                        continue
                    t = ctx.type_of(x.obj, env) or ""
                    t = t.replace(" ", "")
                    if x.attr == "capacity" and not called and t.startswith(("List[", "String")):
                        yield self.finding(ctx, x, "`capacity` is a method", f"`{path_of(x.obj) or '...'}.capacity()`")
                    elif x.attr in ("min", "max") and called and t.startswith(SIMD_T):
                        yield self.finding(ctx, x, f"SIMD/scalar has no `.{x.attr}()`", f"free `{x.attr}(a, b)`")
                    elif x.attr == "reserve" and called and t == "String":
                        yield self.finding(
                            ctx, x, "`String.reserve` is deprecated", "`reserve_bytes(n)`", severity="low"
                        )


class StringIndexLen(Rule):
    """`len(s)` and positional `s[i]` on a `String` are compile errors (UTF-8 makes "length" ambiguous): use
    `s.byte_length()` and `s[byte=i]` (or `codepoints()` / `s[codepoint=i]`)."""

    id = "MA407"
    name = "string-len-index"
    severity = "high"
    bad = 'var s = String("abc")\nvar n = len(s)\nvar c = s[0]'
    good = 'var s = String("abc")\nvar n = s.byte_length()\nvar c = s[byte=0]'

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            env = ctx.env(s.func())
            for n in stmt_nodes(s):
                for x in walk(n):
                    if isinstance(x, Call) and isinstance(x.func, Name) and x.func.id == "len" and len(x.args) == 1:
                        if self._is_str(ctx, x.args[0], env):
                            yield self.finding(ctx, x, "`len()` of a String does not compile",
                                               f"`{path_of(x.args[0]) or 's'}.byte_length()`")  # fmt: skip
                    elif isinstance(x, Sub) and len(x.index) == 1 and not x.kw and self._is_str(ctx, x.obj, env):
                        yield self.finding(ctx, x, "positional String index does not compile", "`s[byte=i]`")

    def _is_str(self, ctx: FileCtx, n: object, env: dict[str, str]) -> bool:
        if not isinstance(n, (Name, Attr)):
            return False
        t = ctx.type_of(n, env)
        return t in ("String", "StringSlice", "StaticString")


class TupleReturn(Rule):
    """`-> (A, B)` is a tuple value, not a type: "expected a type, found a tuple value". Write `-> Tuple[A, B]`."""

    id = "MA408"
    name = "tuple-return-type"
    severity = "high"
    bad = "def f() -> (Int, Int):\n    return (1, 2)"
    good = "def f() -> Tuple[Int, Int]:\n    return (1, 2)"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.defs():
            if s.fn and s.fn.ret.startswith("(") and "," in s.fn.ret:
                yield self.finding(ctx, s, f"tuple return type `{s.fn.ret}`", f"`-> Tuple[{s.fn.ret[1:-1]}]`")


class FString(Rule):
    """f-strings do not exist in Mojo: `f"x={x}"` is a parse error. Use `String("x=", x)` or `s.write(...)`."""

    id = "MA409"
    name = "f-string"
    severity = "high"
    bad = 'print(f"x={x}")'
    good = 'print("x=", x)'

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in all_stmts(ctx):
            for t in s.toks:
                if t.kind is K.STRING and t.value[:1] in "fF" and t.value[1:2] in ("'", '"'):
                    yield self.finding(ctx, t, "f-string literal", 'String("x=", x) / s.write("x=", x)')


class SimdEqScalar(Rule):
    """`a == b` on SIMD vectors of width > 1 returns one `Bool` (all lanes equal), not a lane mask. Binding it to
    a variable usually means a mask was intended: use `a.eq(b)` (and `.ne/.lt/.le/.gt/.ge`)."""

    id = "MA410"
    name = "simd-eq-scalar"
    severity = "medium"
    confidence = "medium"
    bad = "var m = a == b  # a, b: SIMD[DType.float32, 4]"
    good = "var m = a.eq(b)"
    why = "SIMD(1,2,1,3) == SIMD(1) is False, not [True, False, True, False]"

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.mod.walk():
            v = s.decl[2] if s.kind == "var" and s.decl else s.assign[1] if s.kind == "assign" and s.assign else None
            if not (isinstance(v, BinOp) and v.op in ("==", "!=")):
                continue
            env = ctx.env(s.func())
            if self._vec(ctx, v.left, env, s) and self._vec(ctx, v.right, env, s):
                m = "eq" if v.op == "==" else "ne"
                yield self.finding(
                    ctx, v, f"`{v.op}` on SIMD vectors reduces to one Bool", f"`a.{m}(b)` for a lane mask"
                )

    def _vec(self, ctx: FileCtx, n: object, env: dict[str, str], s: Stmt) -> bool:
        t = None
        if isinstance(n, (Name, Attr, Sub)):
            t = ctx.type_of(n, env)
        elif isinstance(n, Call) and isinstance(n.func, Sub) and isinstance(n.func.obj, Name):
            if n.func.obj.id == "SIMD":
                t = "SIMD[" + ",".join(str(getattr(i, "text", getattr(i, "id", "?"))) for i in n.func.index) + "]"
        if not t or not t.replace(" ", "").startswith("SIMD["):
            return False
        w = t.replace(" ", "")[5:-1].split(",")[-1]
        if w.isdigit():
            return int(w) > 1
        k = ctx.comptime_int(Name(Token(K.NAME, w, 0, 0), w), s.func()) if w.isidentifier() else None
        return k is not None and k > 1


class DeprecatedPointerApi(Rule):
    """Deprecated in 1.2 (warnings today, errors later): `UnsafePointer` -> `Pointer`, `p.load`/`p.store` ->
    `unsafe_load`/`unsafe_store`, `p.free()` -> `p.unsafe_free()`, positional `p[i]` -> `p[unsafe_offset=i]`."""

    id = "MA411"
    name = "deprecated-pointer-api"
    severity = "low"
    bad = "var p: UnsafePointer[Int, MutAnyOrigin] = q\nvar v = p.load[width=4](0)\np.free()"
    good = "var p: Pointer[Int, MutAnyOrigin] = q\nvar v = p.unsafe_load[width=4](0)\np.unsafe_free()"
    NEW: ClassVar[dict[str, str]] = {"load": "unsafe_load", "store": "unsafe_store", "free": "unsafe_free"}

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        own = defined_names(ctx)
        for s in ctx.mod.walk():
            if s.kind in ("import", "from"):
                continue
            for i, t in enumerate(s.toks):
                if t.is_name("UnsafePointer") and "UnsafePointer" not in own and not _prev_is_dot(s.toks, i):
                    yield self.finding(ctx, t, "`UnsafePointer` is deprecated", "`Pointer`")
            env = ctx.env(s.func())
            for n in stmt_nodes(s):
                for x in walk(n):
                    f = x.func.obj if isinstance(x, Call) and isinstance(x.func, Sub) else (
                        x.func if isinstance(x, Call) else None
                    )  # fmt: skip
                    if isinstance(f, Attr) and f.attr in self.NEW and self._ptr(ctx, f.obj, env):
                        yield self.finding(ctx, f, f"`.{f.attr}` on a pointer is deprecated", f"`.{self.NEW[f.attr]}`")
                    elif isinstance(x, Sub) and len(x.index) == 1 and not x.kw and self._ptr(ctx, x.obj, env):
                        if s.kind == "comptime":
                            continue
                        yield self.finding(ctx, x, "positional pointer index is deprecated", "`p[unsafe_offset=i]`")

    def _ptr(self, ctx: FileCtx, n: object, env: dict[str, str]) -> bool:
        if not isinstance(n, (Name, Attr)):
            return False
        t = ctx.type_of(n, env)
        return bool(t) and str(t).replace(" ", "").startswith(("Pointer[", "UnsafePointer["))


class ExportAbi(Rule):
    """`@export` without an explicit `abi("C")` effect is deprecated ("@export requires an explicit 'abi()'
    effect"); the effect goes before the arrow."""

    id = "MA412"
    name = "export-abi"
    severity = "low"
    bad = "@export\ndef f(x: Int) -> Int: ..."
    good = '@export\ndef f(x: Int) abi("C") -> Int: ...'

    def check(self, ctx: FileCtx) -> Iterable[Finding]:
        for s in ctx.defs():
            if not s.has_decorator("export"):
                continue
            if any(t.is_name("abi") for t in s.toks):
                continue
            d = next(d for d in s.decorators if len(d.toks) > 1 and d.toks[1].value == "export")
            yield self.finding(ctx, d, "@export without `abi(...)`", 'def f(...) abi("C") -> T:')
