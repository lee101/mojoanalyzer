from std.time import perf_counter_ns
from std.sys import argv


def main() raises:
    var n = 100000 + len(argv()) - 1
    var t0 = perf_counter_ns()
    var xs = List[Int]()
    for i in range(n):
        xs.insert(0, i)
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, xs[0])
