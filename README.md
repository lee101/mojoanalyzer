# mojoanalyzer

A conservative static analyzer for Mojo performance and idiom issues, in the spirit of ruff. It is tuned for
precision over recall: a rule fires only when the parser can prove the preconditions for its rewrite, and each
finding states its risk.

Target dialect: Mojo 1.2 nightly (`def`, `comptime`, `comptime for`, `std.` imports, `Pointer`,
`unsafe_load`/`unsafe_store`, capture lists `def f(i: Int) {mut p}:`, `max.algorithm.parallelize`,
`DeviceContext`).

## Usage

```
uv run mojoanalyzer PATH... [--format text|json] [--select MA11,MA102] [--ignore MA101]
                            [--min-confidence low|medium|high] [--min-severity info|low|medium|high]
                            [--no-risk fp] [--fail-on low|...|never] [--statistics]
uv run mojoanalyzer --list-rules
uv run mojoanalyzer --explain MA114
```

Output: `path:line:col RULE severity confidence message -> suggestion [risk: ...]`

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

Risk levels:
- `none`: same semantics and the same bits.
- `fp`: the last bits of FP results change.
- `unsafe`: bounds checks are removed.
- `threads`: callee thread safety must hold.
- `api`: the signature changes.
- `codesize`: compile time and code size grow.

`examples/` holds before/after pairs for 13 rules, compiled and timed with the real toolchain. See
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
- `rules/`: one class per rule, each with an id, docstring and bad/good examples. When information is
  missing, rules bail out: unknown element type, unknown callee, any loop exit, aliasing, and so on.

The whole predictionmojo tree (215 files, 105k lines) parses with zero expression-parse failures and analyzes in
about 10 s.

## Development

```
uv run pytest                  # 168 tests: tokenizer/parser units, golden fixtures, CLI, mojo build of every fixture/example
uv run pytest -m 'not compile' # skip the toolchain tests
UPDATE_GOLDEN=1 uv run pytest tests/test_fixtures.py
uvx ruff check && uvx ruff format --check && uvx ty check
examples/run.sh                # re-run benchmarks (MOJO=/path/to/mojo)
```

Every rule has `tests/fixtures/<RULE>/positive*.mojo` (must fire) and `negative*.mojo` (near misses, must not
fire), each with a golden `.expected` file covering all rules. All fixtures and examples build with
`mojo build`. The compile tests use `$MOJO` or `/home/lee/code/pm-wt-algo7/.venv/bin/mojo` and are skipped when
neither exists.
