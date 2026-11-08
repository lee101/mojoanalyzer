from std.time import perf_counter_ns
from std.sys import argv

def main() raises:
    var n = 200000 + len(argv()) - 1
    var hdr = String("ts,open,high,low,close,volume,vwap,n")
    var t0 = perf_counter_ns()
    var acc = 0
    for i in range(n):
        var cols = hdr.split(",")
        acc += cols[i % 8].byte_length()
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, acc)
