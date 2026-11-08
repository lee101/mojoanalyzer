# Design

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

A 218-file, 105k-line Mojo trading codebase parses with zero expression-parse failures; all 66 rules
take about 25 s.
