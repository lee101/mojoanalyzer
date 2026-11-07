from std.time import perf_counter_ns
from std.sys import argv
from std.collections import Deque


def main() raises:
    var n = 100000 + len(argv()) - 1
    var t0 = perf_counter_ns()
    var xs = Deque[Int]()
    for i in range(n):
        xs.appendleft(i)
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, xs[0])
