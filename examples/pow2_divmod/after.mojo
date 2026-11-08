from std.time import perf_counter_ns
from std.sys import argv

def f(xs: List[Int], k: Int) -> Int:
    var s = 0
    for i in range(len(xs)):
        var j = xs[i] + k
        s += (j >> 3) + (j & 15)
    return s


def main() raises:
    var n = 1000000 + len(argv()) - 1
    var xs = List[Int](capacity=n)
    for i in range(n):
        xs.append(i * 7)
    var t0 = perf_counter_ns()
    var acc = 0
    for r in range(200):
        acc += f(xs, r)
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, acc)
