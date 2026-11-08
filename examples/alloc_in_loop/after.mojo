from std.time import perf_counter_ns
from std.sys import argv

def f(xs: List[Float64], k: Int) -> Float64:
    var s = 0.0
    var win = List[Float64]()
    for i in range(len(xs) - k):
        win.clear()
        for j in range(k):
            win.append(xs[i + j] * 2.0)
        s += win[0] + win[k - 1]
    return s


def main() raises:
    var n = 200000 + len(argv()) - 1
    var xs = List[Float64](length=n, fill=0.5)
    var t0 = perf_counter_ns()
    var acc = 0.0
    for r in range(20):
        acc += f(xs, 16)
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, acc)
