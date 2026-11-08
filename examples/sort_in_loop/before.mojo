from std.time import perf_counter_ns
from std.sys import argv

def main() raises:
    var n = 2000 + len(argv()) - 1
    var xs = List[Float64](capacity=n)
    for i in range(n):
        xs.append(Float64((i * 7919) % n))
    var t0 = perf_counter_ns()
    var acc = 0.0
    for r in range(2000):
        sort(xs)
        acc += xs[r % n]
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, acc)
