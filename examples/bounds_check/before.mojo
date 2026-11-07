from std.time import perf_counter_ns
from std.sys import argv


def axpy(mut y: List[Float64], x: List[Float64], a: Float64):
    for i in range(len(y)):
        y[i] = y[i] + a * x[i]


def main() raises:
    var n = 1 << 20 + len(argv()) - 1
    var x = List[Float64](length=n, fill=1.5)
    var y = List[Float64](length=n, fill=0.25)
    var t0 = perf_counter_ns()
    for _ in range(200):
        axpy(y, x, 1e-6)
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, y[7])
