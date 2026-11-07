from std.time import perf_counter_ns
from std.sys import argv


def tally(d: Dict[Int, Int], n: Int) raises -> Int:
    var s = 0
    for i in range(n):
        var k = i % 2048
        if k in d:
            s += d[k]
    return s


def main() raises:
    var d = Dict[Int, Int]()
    for i in range(1024):
        d[i * 2] = i
    var n = 1 << 22 + len(argv()) - 1
    var t0 = perf_counter_ns()
    var s = tally(d, n)
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, s)
