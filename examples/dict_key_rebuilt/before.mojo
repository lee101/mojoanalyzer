from std.time import perf_counter_ns
from std.sys import argv

def main() raises:
    var n = 200000 + len(argv()) - 1
    var syms: List[String] = ["AAPL", "MSFT", "NVDA", "AMD", "TSLA"]
    var d = Dict[String, Int]()
    var t0 = perf_counter_ns()
    for i in range(n):
        var s = syms[i % 5]
        if s + ":" + String(i % 3) in d:
            d[s + ":" + String(i % 3)] += 1
        else:
            d[s + ":" + String(i % 3)] = 1
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, len(d))
