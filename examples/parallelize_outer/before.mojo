from std.time import perf_counter_ns
from std.sys import argv
from std.math import sqrt


def heavy(seed: Int, m: Int) -> Float64:
    var s = 0.0
    for j in range(m):
        s += sqrt(Float64(seed * 31 + j))
    return s


def main() raises:
    var n = 512 + len(argv()) - 1
    var out = List[Float64](length=n, fill=0.0)
    var t0 = perf_counter_ns()
    for i in range(n):
        out[i] = heavy(i, 200000)
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, out[7])
