from std.time import perf_counter_ns
from std.sys import argv

def main() raises:
    var n = 20000 + len(argv()) - 1
    var k = 16
    var t0 = perf_counter_ns()
    var acc = 0.0
    for r in range(10):
        var m = List[Float64](length=n * k, fill=0.0)
        for i in range(n):
            for j in range(k):
                m[i * k + j] = Float64(i + j)
        for i in range(n):
            for j in range(k):
                acc += m[i * k + j]
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, acc)
