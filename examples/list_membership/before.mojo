from std.time import perf_counter_ns
from std.sys import argv


def main() raises:
    var seen = List[Int]()
    for i in range(2000):
        seen.append(i * 7)
    var n = 200000 + len(argv()) - 1
    var t0 = perf_counter_ns()
    var hits = 0
    for i in range(n):
        if i in seen:
            hits += 1
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, hits)
