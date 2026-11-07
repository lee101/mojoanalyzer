from std.time import perf_counter_ns
from std.sys import argv


def build(n: Int) -> List[Int]:
    var xs = List[Int]()
    for i in range(n):
        xs.append(i * 3)
    return xs^


def main() raises:
    var n = 1 << 22 + len(argv()) - 1
    var t0 = perf_counter_ns()
    var tot = 0
    for _ in range(20):
        var xs = build(n)
        tot += xs[n - 1]
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, tot)
