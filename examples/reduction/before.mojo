from std.time import perf_counter_ns
from std.sys import argv


def dot(a: List[Float64], b: List[Float64]) -> Float64:
    var ap = a.unsafe_ptr()
    var bp = b.unsafe_ptr()
    var s = 0.0
    for i in range(len(a)):
        s += ap[i] * bp[i]
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
