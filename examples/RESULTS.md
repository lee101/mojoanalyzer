# Benchmark results

Each directory holds a `before.mojo` (pattern the rule flags) and `after.mojo` (the suggested rewrite).
`./run.sh` builds both with `mojo build -g` (default opt level) and reports the best of `RUNS` runs (default 3);
with `MOJOMEM=/path/to/mojomem` it adds the number of Mojo heap allocations (LD_PRELOAD over
`KGEN_CompilerRT_AlignedAlloc`, the allocator behind List/String/Dict/`alloc[T]`).

Mojo 1.2.0.dev2026100805, AMD Ryzen 9 5950X (16C/32T, AVX2), Linux 6.8. Times in ms.

## MA1xx (original set)

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

## MA12x and MA3xx

Best of 7. The host was shared with other jobs (load average 50-70 on 32 threads), so run-to-run variance was up to
2x; where an earlier quieter run differed a lot it is noted. Allocation counts are exact and load-independent.
Every after-version prints the same result as its before-version (and `small_writes` writes a byte-identical file).

| example | rule | before | after | speedup | allocs before -> after |
|---|---|---:|---:|---:|---:|
| sort_in_loop | MA127 `sort(xs)` every iteration -> once | 11.45 | 0.071 | 162x | 2,001 -> 2 |
| invariant_alloc | MA302 `hdr.split(",")` in loop -> hoisted | 10.44 | 0.18 | 57x | 200,000 -> 1 |
| small_writes | MA307 `f.write()` per row -> String buffer, one write | 144.7 | 5.39 | 27x | 3 -> 19 (100k write calls -> 1) |
| dict_iter_lookup | MA126 `for k in d: d[k]` -> `d.items()` | 41.2 | 6.2 | 6.6x | 80 -> 80 |
| alloc_in_loop | MA301 `List` per iteration -> hoist + `clear()` | 511.2 | 94.6 | 5.4x | 19,998,401 -> 101 |
| alloc_in_loop_dict | MA301 `Dict` per iteration -> hoist + `clear()` | 12.0 | 4.17 | 2.9x | 200,000 -> 10 |
| alloc_in_loop_string | MA301 `String` per iteration -> hoist + `resize(0)` | 32.4 | 29.3 | 1.1x | 190,000 -> 1 |
| dict_capacity | MA308 `Dict()` + n inserts -> `Dict(capacity=n)` | 49.3 | 20.6 | 2.4x | 1,010 -> 30 |
| aos_soa | MA120 `bars[i].close` (64 B struct) -> `close[i]` | 469.6 | 201.3 | 2.3x (7.5x quiet run) | 1 -> 1 |
| repeated_call | MA125 `norm(xs) / (1 + norm(xs))` -> bind once | 387.0 | 192.2 | 2.0x | 1 -> 1 |
| pow2_divmod | MA122 `j // 8 + j % 16` -> `(j >> 3) + (j & 15)` | 366.7 | 207.9 | 1.8x (4.4x quiet run) | 1 -> 1 |
| dict_key_rebuilt | MA305 key built 3x per iteration -> once | 15.45 | 8.45 | 1.8x | 11 -> 11 (keys <= 23 B are inline) |
| nested_list_rows | MA306 `List[List[Float64]]` rows -> flat `[i*k + j]` | 14.87 | 9.17 | 1.6x | 200,010 -> 10 |
| missed_move | MA303 `rows.append(row.copy())` -> `row^` | 17.55 | 16.86 | 1.04x | 40,001 -> 20,001 (39.5 MB less copied) |

No benchmark (no speed claim in the rule text): MA121 (layout is deterministic: `size_of` 32 B -> 24 B verified),
MA123 (Python), MA124, MA128, MA129 (the host's NVIDIA driver 575 is below the 580 this nightly requires), MA130,
MA304, MA309.

## Negative results (measured, rule deliberately not implemented)

| pattern | before | after | note |
|---|---:|---:|---|
| `x ** 2` -> `x * x` | 79.6 | 76.4 | within noise; the compiler already folds it |
| `while i < len(xs)` -> hoisted `n = len(xs)` | 103.9 | 103.5 | no difference; `len` is a field load that LLVM hoists |
| `var w = xs[a:b]` -> `Span(xs)[a:b]` | 8.4 | 10.5 | 1 allocation both ways: List slicing already returns a Span view |
| `s.write(String(i), ...)` -> `s.write(i, ...)` | 91 | 73 | 19 -> 19 allocations (short strings are inline); time within load noise |
| `if flag:` on a Bool param in a hot loop -> `def f[flag: Bool]` + `comptime if` | 155 | 156 | LLVM unswitches the loop itself (pinned, 7 runs) |
| `raises` callee that cannot raise, in an inner loop | 177 | 174 | within noise |
| tail recursion -> `while` loop | 0.0074 | 0.0076 | LLVM eliminates the recursion (and folds the sum) |
| tiny leaf function -> `@always_inline` | 183 | 170 | within noise; already inlined |
| `var TS = 4` loop bound -> `comptime TS = 4` | 237 | 288 | no gain |

Notes
- MA101 is reported at low confidence unless the index feeds SIMD lane access or a GPU kernel tile loop: LLVM
  already fully unrolls most small constant loops, so the gain is small.
- The MA105 gain scales with cores. Treat it as an upper bound for embarrassingly parallel work.
- MA103/MA112 change results in the last bits. Do not apply them to code that must stay bit-exact
  (for example Go parity built with `--fp-mode contract=off`).
- MA122 is exact for every signed value because Mojo `//` floors and `%` takes the divisor's sign:
  `-7 // 2 == -7 >> 1 == -4`, `-7 % 16 == -7 & 15 == 9` (checked on Int, Int32 and UInt).
