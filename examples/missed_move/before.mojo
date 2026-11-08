from std.time import perf_counter_ns
from std.sys import argv

def main() raises:
    var n = 20000 + len(argv()) - 1
    var t0 = perf_counter_ns()
    var rows = List[List[Float64]](capacity=n)
    for i in range(n):
        var row = List[Float64](length=256, fill=Float64(i))
        rows.append(row.copy())
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, len(rows), rows[n - 1][3])
