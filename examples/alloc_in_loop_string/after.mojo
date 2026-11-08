from std.time import perf_counter_ns
from std.sys import argv

def main() raises:
    var n = 200000 + len(argv()) - 1
    var t0 = perf_counter_ns()
    var acc = 0
    var line = String()
    for i in range(n):
        line.resize(0)
        line.write(i, ",", i * 2, ",", i * 3, ",", Float64(i) * 0.5)
        acc += line.byte_length()
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, acc)
