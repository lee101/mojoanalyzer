from std.time import perf_counter_ns
from std.sys import argv

def main() raises:
    var n = 200000 + len(argv()) - 1
    var t0 = perf_counter_ns()
    var acc = 0
    for r in range(10):
        var d = Dict[Int, Int](capacity=n)
        for i in range(n):
            d[i * 31] = i
        acc += len(d)
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, acc)
