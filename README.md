# mojoanalyzer

A conservative static analyzer for Mojo performance/idiom issues (MA1xx), correctness/math-safety issues in
numeric and trading code (MA2xx), heap-allocation churn (MA3xx) and Mojo 1.2 dialect breakage (MA4xx), in the
spirit of ruff. It is tuned for
precision over recall: a rule fires only when the parser can prove the preconditions for its rewrite, and each
finding states its risk.

Target dialect: Mojo 1.2 nightly (`def`, `comptime`, `comptime for`, `std.` imports, `Pointer`,
`unsafe_load`/`unsafe_store`, capture lists `def f(i: Int) {mut p}:`, `max.algorithm.parallelize`,
`DeviceContext`).

## Usage

```
uv run mojoanalyzer PATH... [--format text|json|llm|sarif] [--top N] [--hot-only]
                            [--select MA11,MA102] [--ignore MA101]
                            [--min-confidence low|medium|high] [--min-severity info|low|medium|high]
                            [--no-risk fp] [--fail-on low|...|never] [--statistics]
uv run mojoanalyzer --list-rules
uv run mojoanalyzer --explain MA114          # describe a rule
uv run mojoanalyzer PATH --explain           # add a `why:` line (concrete failure) under each finding
uv run mojoanalyzer PATH --rule-option MA203.strict=1
```

Output: `path:line:col RULE severity confidence message -> suggestion [risk: ...]`, one line per finding.
`--format json` emits the same fields plus `why` and `risk_note`.

Correctness-only, high-confidence run: `uv run mojoanalyzer src --select MA2 --min-confidence high`.

For LLM agents: `uv run mojoanalyzer src --format llm --top 40 --hot-only`. Output is grouped by file, one line per
finding, `L<line> RULE msg -> fix [risk]`; identical findings in one function merge into `L12,L40,L77`; the header
has per-rule counts. `--top N` ranks by severity x confidence x (1 + hot), where hot = loop depth at the finding
(closures dispatched by `parallelize`/`vectorize` and GPU kernels count as a level) + 1 if the enclosing function is
called from a loop elsewhere in the same file (transitively). `--hot-only` keeps findings with hot > 0 (MA4xx
dialect errors are always kept). JSON and SARIF carry `hot` and `scope` (enclosing function).

- `--min-confidence` defaults to `medium`. Low-confidence findings (heuristic gain only) are opt-in.
- Exit code 1 if any reported finding is at or above `--fail-on` (default `low`).
- Suppress a finding inline with `# mojoanalyzer: ignore[MA106]`, or with a bare `# mojoanalyzer: ignore` for all
  rules. For a whole file, use `# mojoanalyzer: ignore-file[MA107]`.
- Use `--no-risk fp` to drop FP-reassociating suggestions, for example in code that must match Go or NumPy bit
  for bit.

## Rules

| id | name | sev | risk | flags | suggests |
|---|---|---|---|---|---|
| MA101 | comptime-unroll | low | codesize | constant trip count 2..16 in a hot loop | `comptime for` (high confidence only for SIMD lane index or GPU tile loop) |
| MA102 | vectorize-elementwise | medium | none | float elementwise loop, no carried dependency | `vectorize[simd_width_of[DType]()]` with `unsafe_load`/`unsafe_store`; bit-identical |
| MA103 | simd-reduction | medium | **fp** | scalar float sum/min/max reduction | SIMD accumulators + `reduce_add`/`reduce_max` (sum is reassociated) |
| MA104 | literal-simd-width | low | none | `vectorize[8]`, `unsafe_load[width=8]` striding a manual loop | `simd_width_of[DType]()` |
| MA105 | parallelize-candidate | medium | threads | outer loop writing only `out[i]`/locals, read-only callees, nested loop | `parallelize` closure |
| MA106 | list-reserve | low/medium | none | empty `List` + unconditional `append` in the following loop of known count | `List[T](capacity=n)` or `length=n, fill=v` |
| MA107 | string-concat-loop | low | none | `s += a + String(b)` / `s = s + ...` in a loop | `s.write(a, b)` |
| MA108 | dict-double-lookup | low | none | `if k in d:` then `d[k]` (scalar values) | `d.find(k)` |
| MA109 | copy-in-loop | medium | none | `var x = e.copy()` in a loop, `x` and `e` never mutated afterwards | `ref x = e` |
| MA110 | owned-arg-read-only | low | api | `var xs: List[...]` parameter that is only read | default read convention (`f(x^)` call sites still compile) |
| MA111 | iterate-directly | low | none | `for i in range(len(xs))` where `i` is used only as `xs[i]` | `for x in xs` |
| MA112 | reciprocal-multiply | low | **fp** | float `/` or `/=` by a loop-invariant value in a numeric loop (powers of 2 excluded) | hoist `1/d`, multiply |
| MA113 | unsafe-ptr-inner-loop | medium | **unsafe** | bounds-checked numeric `List` indexing in an inner numeric loop | `unsafe_ptr()` before the loop |
| MA114 | loop-interchange | high | none | perfectly nested loops traversing row-major data column-wise; only when the swap is legal and bit-exact | swap the loops |
| MA115 | list-front-ops | high | none | `List.insert(0, x)` / `List.pop(0)` in a loop | `Deque` |
| MA116 | list-membership | medium | none | `x in xs` on a `List` inside a loop (literal lists of 16 or fewer items skipped) | `Set` |
| MA117 | redundant-gpu-sync | low | none | `ctx.synchronize()` immediately followed by `ctx.enqueue_*` | drop the sync |
| MA118 | literal-arg-to-param | info | api | an Int/Bool arg passed as a literal at every call site and driving a loop bound or hot branch | compile-time parameter (low confidence) |
| MA119 | copy-into-read-arg | low | none | `f(x.copy())` where `f`'s parameter uses the read convention | pass `x` |

More performance rules (MA12x-MA13x), each kept only after a measured win or with no speed claim:

| id | name | sev | risk | flags | suggests |
|---|---|---|---|---|---|
| MA120 | aos-field-loop | low | api | numeric loop reading <= 1/4 of the bytes of each element of a `List[Struct]` (>= 4 fields, scalar hot fields) | SoA: hot field in its own List |
| MA121 | struct-padding | info/low | api | struct of fixed-size scalars whose declaration order adds padding (Mojo keeps order: verified 32 B -> 24 B) | largest-first order (low if the struct is stored in a List) |
| MA122 | pow2-divmod | low | none | Int `x // 2^k`, `x % 2^k` in a numeric loop (comptime-only operands skipped) | `x >> k`, `x & (2^k-1)`: exact for negatives under Mojo floor semantics |
| MA123 | python-in-loop | medium | none | `Python.import_module`/`evaluate` with literal args in a loop | hoist (no benchmark) |
| MA124 | print-in-hot-loop | info | none | unconditional `print` in an inner loop whose other statements are numeric | buffer, print once |
| MA125 | repeated-pure-call | low | none | same call to a provably pure project function containing a loop, twice in one expression | bind once |
| MA126 | dict-iter-lookup | medium | none | `for k in d:` + `d[k]`, `d` not mutated | `for e in d.items()` |
| MA127 | sort-in-loop | high | none | `sort(xs)` in a loop that does not otherwise change `xs` | sort once |
| MA128 | huge-always-inline | info | codesize | `@always_inline` with >= 60 statements and >= 2 call sites | drop it |
| MA129 | gpu-sync-in-loop | medium | none | loop containing only kernel launches, scalar bookkeeping and `synchronize()` | sync after the loop (no benchmark: host driver too old) |
| MA130 | gpu-uncoalesced | low | api | kernel loop indexing `buf[tid * S + k]` (thread index on the slow axis) | transposed layout `buf[k * N + tid]` |

Measured and dropped (no win on this toolchain): loop-invariant Bool branch -> comptime parameter/unswitching,
`raises` on a callee in an inner loop, tail recursion -> loop (LLVM already does both), `@always_inline` on tiny leaf
functions (already inlined), `var` constant -> `comptime` for loop bounds.

### Allocation rules (MA3xx)

Allocation claims were verified with the real Mojo allocator (`mojomem`, an LD_PRELOAD over
`KGEN_CompilerRT_AlignedAlloc`); counts are in [examples/RESULTS.md](examples/RESULTS.md).

| id | name | sev | risk | flags | suggests |
|---|---|---|---|---|---|
| MA301 | alloc-in-loop | low/medium | none | `List`/`Dict`/`Set`/`String` declared in a loop, grown there, never escaping (no `^`, return, store, owned-arg pass); `alloc[T](n)` freed in the same iteration. Medium when nested or in a loop-called function | hoist above the outermost loop where the ctor is invariant; `clear()` / `resize(0)` in place |
| MA302 | invariant-alloc-in-loop | medium | none | `.split()`, `String(x)`, `.copy()`, `.upper()`, `.join()`... with loop-invariant operands whose result is only read | compute once before the loop |
| MA303 | missed-move | medium | none | `x.copy()` that is the last use of local/owned `x` (no loop between decl and use, no closure capture) | `x^` |
| MA304 | copy-read-only | low | none | `var y = e.copy()` outside loops, `y` only read, `e` unchanged while `y` lives | `ref y = e` |
| MA305 | dict-key-rebuilt | low | none | same String key expression built for >= 2 lookups of one Dict in a block | build the key once |
| MA306 | nested-list-rows | low | api | `List[List[T]]` of fixed-length numeric rows (append in a loop, or `length=n, fill=List(length=k)`) | flat `List[T](length=n*k)`, `[i*k + j]` |
| MA307 | small-writes-in-loop | medium | none | `f.write()` on a FileHandle inside a loop nested in the `with open()`/`var f = open()` scope | buffer in a String, write once |
| MA308 | dict-capacity | low | none | empty `Dict` + one unconditional insert per iteration of the next loop (count > 64) | `Dict[K, V](capacity=n)` |
| MA309 | list-bool-bitset | info | api | `List[Bool](length=K, fill=False)`, comptime K >= 64 | `BitSet[K]` |

Measured and dropped: `var w = xs[a:b]` -> `Span` (List slicing already returns a Span view in 1.2, 1 allocation
either way), `s.write(String(x))` -> `s.write(x)` (short strings are inline/SSO: no heap allocation, no reliable
time difference). `List` growth without capacity remains MA106; `String` has no capacity constructor and its
`reserve` is deprecated, so no String rule.

### Dialect rules (MA4xx)

Ported from `mojolint` and re-verified on Mojo 1.2.0.dev2026100805: every error-level rule has
`positive_cerr_*.mojo` fixtures that the test suite asserts **fail** to build; negatives must build.

| id | name | sev | flags | fix |
|---|---|---|---|---|
| MA401 | removed-keyword | high | `fn`, `let`, `alias`; `fn` as a name | `def`, `var`, `comptime` |
| MA402 | removed-convention | high | `owned`/`inout`/`borrowed` args, `{read x}` capture, `out` as arg name | `var`/`mut`/default, `{imm x}` |
| MA403 | parameter-decorator | high/low | `@parameter for`/`if` (error); `@parameter def` (deprecated) | `comptime for`/`if`; capture list |
| MA404 | bare-std-import | high | `from math import ...` with no local module of that name | `from std.math import ...` |
| MA405 | removed-name | high | `sizeof`/`simdwidthof`/`alignof`/`bitwidthof`, `str()`, `DTypePointer`, `Reference`, `StringRef`, `Stringable`, `InlinedFixedVector`, `isinstance`, `MutableAnyOrigin`, `memset_zero`, `@value`, `@register_passable` (names the file defines or imports from project modules are skipped) | new name |
| MA406 | removed-method | high/low | `UnsafePointer[T].alloc(n)`, `List.capacity` attribute, SIMD/Float `.min()`/`.max()`; `String.reserve` (deprecated) | `alloc[T](n)`, `.capacity()`, free `min`/`max`, `reserve_bytes` |
| MA407 | string-len-index | high | `len(s)`, positional `s[i]` on a String | `s.byte_length()`, `s[byte=i]` |
| MA408 | tuple-return-type | high | `-> (A, B)` | `-> Tuple[A, B]` |
| MA409 | f-string | high | `f"..."` | `String("x=", x)` |
| MA410 | simd-eq-scalar | medium | `var m = a == b` on SIMD width > 1 (returns one Bool) | `a.eq(b)` |
| MA411 | deprecated-pointer-api | low | `UnsafePointer`, pointer `.load`/`.store`/`.free`, positional `p[i]` | `Pointer`, `unsafe_load`/`unsafe_store`/`unsafe_free`, `p[unsafe_offset=i]` |
| MA412 | export-abi | low | `@export` without `abi(...)` | `def f(...) abi("C") -> T:` |

Not ported (no longer true on 1.2): `vectorize` rejecting capturing closures (compiles), `simd-eq` as a compile
error (it compiles; MA410 covers the semantic trap), `alloc` in loops as a dialect issue (now MA301 with escape
analysis), and the regex perf rules (superseded by MA1xx/MA3xx).

### Correctness rules (MA2xx)

Confidence here means "likely a real defect", not "the pattern matched". Each message says what is wrong, `->` the
rewrite, and `--explain` adds why it fails (the concrete bad value).

| id | name | sev | conf | flags | suggests |
|---|---|---|---|---|---|
| MA201 | unguarded-division | medium | high/med/low | divisor never compared/clamped/validated in the function: `len(xs)`, a 0-initialised counter (high); `n - 1`, `h - l`, a parsed API field (medium); price-like names (low). Skips loop-protected (`for i in range(n): x / n`), same-predicate counters, index decoding (`idx // ns`), lists proven non-empty (append/`xs[0]` earlier), validator calls `if not ok(px)` | `if n == 0: return ...` / `max(d, eps)` |
| MA202 | int-truncation | medium | med/low | `Int(float)` on a qty/notional (medium if parsed from a string field or visibly signed), `Int(x + 0.5)` on a maybe-negative value | `Int(round(q))`, `Int(floor(x + 1e-9))`, `Int(floor(x + 0.5))` |
| MA203 | float-equality | low | medium | `==`/`!=` where a side is computed arithmetic; literal compares only for non-dyadic literals (0.1); ties within one array and inf/NaN/MAX sentinels skipped. `MA203.strict=1` flags all literals | `abs(a - b) <= tol` |
| MA204 | nan-compare | high/info | high/low | compare with `nan()` (always False, high); `n != n` on Int (high); `x != x` / `x - x == 0` idioms (info, low) | `isnan`, `isfinite` |
| MA205 | math-domain | medium | high/med/low | `sqrt(E[x^2] - E[x]^2)` / `log(a - b)` without clamp (high); `log(a / b)` with unchecked operands (medium if parsed, else low) | `sqrt(max(v, 0.0))` |
| MA206 | int-true-division | high | high | `Float64(a / b)` with Int operands (Mojo Int `/` floors: 7/2 == 3); bare Int `/` at low | `Float64(a) / Float64(b)` |
| MA207 | one-sided-tolerance | medium | medium | `a - b < eps` without `abs` | `abs(a - b) < eps` |
| MA208 | swapped-clamp | high | high/med | `min(max(x, A), B)` with A > B, `clamp(x, hi, lo)`, hi/lo-named swaps | swap bounds |
| MA209 | suspicious-identity | high | high/med | `x = x`, `a - a` (Int), `x < x`, `t if c else t` | intended operand |
| MA210 | duplicate-condition | high | high | repeated condition in an if/elif chain | fix the copy |
| MA211 | identical-branches | medium | medium | every branch of an if/else has the same body | drop the condition |
| MA212 | unreachable-code | medium | high | statement after return/raise/break/continue | move or delete |
| MA213 | edge-index | high | high/med | `xs[i - k]` in `range(0, ..)` or `xs[i + k]` in `range(len(xs))` with no test on `i`; `range(len(xs) + 1)`; `xs[len(xs)]` | shift the range |
| MA214 | discarded-status | medium | med/low | `_ = f()` dropping a Bool status of an action call or a write/send byte count | check / retry |
| MA215 | unit-scale | medium | low | `1 + x_bps` / `1 + x_pct` with no 1e-4 / 0.01 in the statement or at the field's assignment | `1 + x_bps * 1e-4` |

Ported from: ruff/pylint (float equality, unreachable code), clippy (float_cmp, cast_possible_truncation,
if_same_then_else, manual clamp), go vet/staticcheck (self-assignment, SA4000 identical operands, x == NaN).
Not ported: mutable defaults and unused variables/results (Mojo has value semantics and already warns on unused
values); ddof and sqrt(252)/sqrt(365) consistency (no reliable signal on real code).

Risk levels:
- `none`: same semantics and the same bits.
- `fp`: the last bits of FP results change.
- `unsafe`: bounds checks are removed.
- `threads`: callee thread safety must hold.
- `api`: the signature changes.
- `codesize`: compile time and code size grow.

`examples/` holds before/after pairs for 27 rules, compiled and timed with the real toolchain. See
[examples/RESULTS.md](examples/RESULTS.md): speedups range from 1.06x (MA101) and 1.2x (MA108) up to 9.9x
(MA114), 11x (MA109) and over 500x (MA115/MA116). Two candidate rules were dropped after measurement:
`x**2` -> `x*x` and `len()` hoisting gave no gain.

## Design

- `tokenizer.py`: an indentation-aware tokenizer that emits INDENT/DEDENT/NEWLINE and handles string prefixes,
  triple-quoted strings across lines, escapes, bracket and backslash continuation, backtick identifiers, Mojo
  operators (`->`, postfix `^`) and unterminated-string recovery.
- `parser.py`: builds a statement tree (decorators, `def`/`struct`/`trait`, `for`/`while`/`if`/`comptime
  for`, inline bodies, `;`). It parses `def` signatures, including argument conventions (`mut`/`var`/`ref`/
  `out`/`deinit`), compile-time parameters, captures, `raises` and the return type.
- `expr.py`: a Pratt expression parser with Mojo specifics: `x^` transfer vs xor, `f[params](args)`, keyword
  subscripts `s[byte=0:3]`, slices, and `ref`/`var` in argument lists. It also has an unparser for
  suggestion text.
- `core.py`: per-function type environments built from parameters, declarations, constructor calls,
  `comptime` aliases, struct fields and `unsafe_ptr()`. It also provides conservative mutation analysis (an
  unknown callee counts as a mutator), a project-wide function/call index, and hot-code detection (loop depth,
  GPU kernels, closures passed to `parallelize`/`vectorize`).
- `rules/alloc.py` (MA3xx): escape analysis for locals (method/index/read-param uses only), loop invariance (no
  assignment, `except`/`with` binding or possible mutation in the loop), last-use liveness for `^` moves.
- `rules/dialect.py` (MA4xx): token- and signature-level checks; skips names the file defines or imports.
- `report.py`: `llm` and `sarif` output; `core.annotate` attaches `hot`/`scope` to every finding.
- `rules/correctness.py`: per-function facts shared by MA2xx (guard keys from every comparison, truthiness test,
  validator call and assert; definitions; range-loop vars; a numeric type lattice Int/Float that follows
  declarations, casts, math calls and project function return types; ambiguous re-declarations become unknown).
- `rules/`: one class per rule, each with an id, docstring and bad/good examples. When information is
  missing, rules bail out: unknown element type, unknown callee, any loop exit, aliasing, and so on.

The whole predictionmojo tree (218 files, about 105k lines) parses with zero expression-parse failures; all 66 rules
take about 25 s.

## Development

```
uv run pytest                  # 547 tests: units, golden fixtures, CLI, mojo build of every fixture/example
uv run pytest -m 'not compile' # skip the toolchain tests
UPDATE_GOLDEN=1 uv run pytest tests/test_fixtures.py
uvx ruff check && uvx ruff format --check && uvx ty check
examples/run.sh                # re-run benchmarks (MOJO=/path/to/mojo)
```

Every rule has `tests/fixtures/<RULE>/positive*.mojo` (must fire) and `negative*.mojo` (near misses, must not
fire), each with a golden `.expected` file covering all rules. All fixtures and examples build with
`mojo build`, except `positive_cerr_*.mojo` dialect fixtures, which must fail to build.
The compile tests use `$MOJO` or `/home/lee/code/pm-wt-algo7/.venv/bin/mojo` and are skipped when
neither exists.
