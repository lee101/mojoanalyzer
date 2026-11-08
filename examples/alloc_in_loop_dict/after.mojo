from std.time import perf_counter_ns
from std.sys import argv

def main() raises:
    var n = 20000 + len(argv()) - 1
    var t0 = perf_counter_ns()
    var acc = 0
    var cnt = Dict[Int, Int]()
    for i in range(n):
        cnt.clear()
        for j in range(32):
            cnt[(i + j) % 17] = j
        acc += len(cnt)
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, acc)
