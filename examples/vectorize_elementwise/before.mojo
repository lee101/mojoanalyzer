from std.time import perf_counter_ns
from std.sys import argv
from std.math import sqrt


def kern(mut y: List[Float32], x: List[Float32], a: Float32, b: Float32):
    for i in range(len(y)):
        y[i] = sqrt(x[i]) * a + b


def main() raises:
    var n = 1 << 16 + len(argv()) - 1
    var x = List[Float32](length=n, fill=2.0)
    var y = List[Float32](length=n, fill=0.0)
    var t0 = perf_counter_ns()
    for r in range(5000):
        kern(y, x, 1.0 + Float32(r), 0.5)
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, y[7])
