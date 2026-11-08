from std.time import perf_counter_ns
from std.sys import argv

@fieldwise_init
struct Bar(Copyable, Movable):
    var open: Float64
    var high: Float64
    var low: Float64
    var close: Float64
    var volume: Float64
    var vwap: Float64
    var ts: Int
    var n: Int


def f(bars: List[Bar]) -> Float64:
    var s = 0.0
    for i in range(len(bars)):
        s += bars[i].close
    return s


def main() raises:
    var n = 1000000 + len(argv()) - 1
    var bars = List[Bar](capacity=n)
    for i in range(n):
        bars.append(Bar(1.0, 2.0, 0.5, Float64(i % 7), 100.0, 1.1, i, 3))
    var t0 = perf_counter_ns()
    var acc = 0.0
    for r in range(200):
        acc += f(bars)
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, acc)
