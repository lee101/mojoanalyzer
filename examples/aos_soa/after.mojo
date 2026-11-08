from std.time import perf_counter_ns
from std.sys import argv

def f(close: List[Float64]) -> Float64:
    var s = 0.0
    for i in range(len(close)):
        s += close[i]
    return s


def main() raises:
    var n = 1000000 + len(argv()) - 1
    var close = List[Float64](capacity=n)
    for i in range(n):
        close.append(Float64(i % 7))
    var t0 = perf_counter_ns()
    var acc = 0.0
    for r in range(200):
        acc += f(close)
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, acc)
