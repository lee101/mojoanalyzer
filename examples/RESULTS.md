# Benchmark results

Each directory holds a `before.mojo` (pattern the rule flags) and `after.mojo` (the suggested rewrite).
`./run.sh` builds both with `mojo build` (default opt level) and reports the best of 3 runs.

Mojo 1.2.0.dev2026100805, AMD Ryzen 9 5950X (16C/32T, AVX2), Linux 6.8. Times in ms.

| example | rule | before | after | speedup | bit-identical |
|---|---|---:|---:|---:|---|
| insert_front | MA115 `List.insert(0)` -> `Deque.appendleft` | 517.5 | 0.83 | 624x | yes |
| list_membership | MA116 `x in List` -> `Set` | 312.2 | 0.61 | 509x | yes |
| copy_in_loop | MA109 `var r = rows[i].copy()` -> `ref r = rows[i]` | 53.0 | 4.8 | 11.0x | yes |
| parallelize_outer | MA105 independent outer loop -> `parallelize` | 191.1 | 18.6 | 10.3x | yes |
| loop_interchange | MA114 column-wise -> row-wise traversal | 473.5 | 47.6 | 9.9x | yes |
| vectorize_elementwise | MA102 List elementwise loop -> `vectorize` | 395.3 | 46.2 | 8.6x | yes |
| reduction | MA103 scalar sum -> SIMD accumulators | 186.0 | 27.9 | 6.7x | no (reassociation) |
| list_reserve | MA106 append loop -> `List(capacity=n)` | 360.2 | 54.3 | 6.6x | yes |
| reciprocal | MA112 `x / d` -> `x * (1/d)` | 326.8 | 75.1 | 4.3x | no (rounding) |
| bounds_check | MA113 List index -> `unsafe_ptr()` | 258.8 | 77.7 | 3.3x | yes |
| string_concat | MA107 `s += String(i) + ","` -> `s.write(i, ",")` | 102.7 | 67.3 | 1.5x | yes |
| dict_lookup | MA108 `if k in d: d[k]` -> `d.find(k)` | 15.0 | 12.8 | 1.18x | yes |
| comptime_unroll | MA101 `for l in range(4)` over SIMD lanes -> `comptime for` | 187.8 | 177.5 | 1.06x | yes |

Negative results (measured, rule deliberately not implemented):

| pattern | before | after | note |
|---|---:|---:|---|
| `x ** 2` -> `x * x` | 79.6 | 76.4 | within noise; the compiler already folds it |
| `while i < len(xs)` -> hoisted `n = len(xs)` | 103.9 | 103.5 | no difference; `len` is a field load that LLVM hoists |

Notes
- MA101 is reported at low confidence unless the index feeds SIMD lane access or a GPU kernel tile loop: LLVM
  already fully unrolls most small constant loops, so the gain is small.
- The MA105 gain scales with cores. Treat it as an upper bound for embarrassingly parallel work.
- MA103/MA112 change results in the last bits. Do not apply them to code that must stay bit-exact
  (for example Go parity built with `--fp-mode contract=off`).
