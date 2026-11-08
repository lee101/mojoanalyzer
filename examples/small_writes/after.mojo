from std.time import perf_counter_ns
from std.sys import argv

def main() raises:
    var n = 100000 + len(argv()) - 1
    var t0 = perf_counter_ns()
    var buf = String()
    for i in range(n):
        buf.write(i, ",", i * 2, "\n")
    with open("/tmp/mojoanalyzer_fw_after.csv", "w") as f:
        f.write(buf)
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, n)
