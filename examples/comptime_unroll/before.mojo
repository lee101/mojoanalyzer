from std.time import perf_counter_ns
from std.sys import argv

comptime V = SIMD[DType.float64, 4]


def hsum(x: List[V]) -> Float64:
    var p = x.unsafe_ptr()
    var s = 0.0
    for i in range(len(x)):
        var v = p[i]
        for l in range(4):
            s += v[l] * Float64(l + 1)
    return s


def main() raises:
    var n = 1 << 18 + len(argv()) - 1
    var x = List[V](length=n, fill=V(1, 2, 3, 4))
    var t0 = perf_counter_ns()
    var acc = 0.0
    for _ in range(200):
        acc += hsum(x)
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, acc)
