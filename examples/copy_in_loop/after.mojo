from std.time import perf_counter_ns
from std.sys import argv


def total(rows: List[List[Float64]]) -> Float64:
    var s = 0.0
    for i in range(len(rows)):
        ref row = rows[i]
        s += row[0] + row[len(row) - 1]
    return s


def main() raises:
    var n = 20000 + len(argv()) - 1
    var rows = List[List[Float64]](length=n, fill=List[Float64](length=64, fill=1.0))
    var t0 = perf_counter_ns()
    var acc = 0.0
    for _ in range(100):
        acc += total(rows)
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, acc)
