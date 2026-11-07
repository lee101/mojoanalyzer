from std.time import perf_counter_ns
from std.sys import argv, simd_width_of


def dot(a: List[Float64], b: List[Float64]) -> Float64:
    comptime w = simd_width_of[DType.float64]() * 4
    var ap = a.unsafe_ptr()
    var bp = b.unsafe_ptr()
    var n = len(a)
    var acc = SIMD[DType.float64, w](0)
    var i = 0
    while i + w <= n:
        acc += ap.unsafe_load[width=w](i) * bp.unsafe_load[width=w](i)
        i += w
    var s = acc.reduce_add()
    while i < n:
        s += ap[i] * bp[i]
        i += 1
    return s


def main() raises:
    var n = 1 << 20 + len(argv()) - 1
    var a = List[Float64](length=n, fill=1.5)
    var b = List[Float64](length=n, fill=0.25)
    var t0 = perf_counter_ns()
    var acc = 0.0
    for _ in range(200):
        acc += dot(a, b)
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, acc)
