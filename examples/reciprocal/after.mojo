from std.time import perf_counter_ns
from std.sys import argv


def norm(mut y: List[Float64], x: List[Float64], d: Float64):
    var yp = y.unsafe_ptr()
    var xp = x.unsafe_ptr()
    var inv = 1.0 / d
    for i in range(len(y)):
        yp[i] = xp[i] * inv


def main() raises:
    var n = 1 << 16 + len(argv()) - 1
    var x = List[Float64](length=n, fill=1.5)
    var y = List[Float64](length=n, fill=0.0)
    var t0 = perf_counter_ns()
    for r in range(5000):
        norm(y, x, 3.0 + Float64(r))
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, y[7])
