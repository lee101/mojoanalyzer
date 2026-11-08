from std.time import perf_counter_ns
from std.sys import argv

def main() raises:
    var n = 20000 + len(argv()) - 1
    var k = 16
    var t0 = perf_counter_ns()
    var acc = 0.0
    for r in range(10):
        var m = List[List[Float64]](capacity=n)
        for i in range(n):
            m.append(List[Float64](length=k, fill=0.0))
        for i in range(n):
            for j in range(k):
                m[i][j] = Float64(i + j)
        for i in range(n):
            for j in range(k):
                acc += m[i][j]
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, acc)
