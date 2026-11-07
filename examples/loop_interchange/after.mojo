from std.time import perf_counter_ns
from std.sys import argv


def colsum(a: List[Float64], mut s: List[Float64], n: Int, m: Int):
    var ap = a.unsafe_ptr()
    var sp = s.unsafe_ptr()
    for i in range(n):
        for j in range(m):
            sp[j] += ap[i * m + j]


def main() raises:
    var n = 4096 + len(argv()) - 1
    var m = 4096
    var a = List[Float64](length=n * m, fill=0.5)
    var s = List[Float64](length=m, fill=0.0)
    var t0 = perf_counter_ns()
    for _ in range(5):
        colsum(a, s, n, m)
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, s[3])
