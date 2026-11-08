from std.time import perf_counter_ns
from std.sys import argv

def f(d: Dict[String, Int]) raises -> Int:
    var s = 0
    for e in d.items():
        s += e.value
    return s


def main() raises:
    var n = 20000 + len(argv()) - 1
    var d = Dict[String, Int]()
    for i in range(n):
        d[String("key", i)] = i
    var t0 = perf_counter_ns()
    var acc = 0
    for r in range(200):
        acc += f(d)
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, acc)
