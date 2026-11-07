from std.time import perf_counter_ns
from std.sys import argv


def render(n: Int) -> String:
    var s = String()
    for i in range(n):
        s.write(i, ",")
    return s


def main() raises:
    var n = 200000 + len(argv()) - 1
    var t0 = perf_counter_ns()
    var tot = 0
    for _ in range(20):
        tot += render(n).byte_length()
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, tot)
