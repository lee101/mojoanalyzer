from std.time import perf_counter_ns
from std.sys import argv

def norm(xs: List[Float64]) -> Float64:
    var s = 0.0
    for i in range(len(xs)):
        s += xs[i] * xs[i]
    return s


def main() raises:
    var n = 10000 + len(argv()) - 1
    var xs = List[Float64](length=n, fill=0.5)
    var t0 = perf_counter_ns()
    var acc = 0.0
    for r in range(20000):
        acc += norm(xs) / (1.0 + norm(xs))
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, acc)
