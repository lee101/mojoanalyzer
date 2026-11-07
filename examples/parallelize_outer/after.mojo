from std.time import perf_counter_ns
from std.sys import argv
from std.math import sqrt
from max.algorithm import parallelize


def heavy(seed: Int, m: Int) -> Float64:
    var s = 0.0
    for j in range(m):
        s += sqrt(Float64(seed * 31 + j))
    return s


def main() raises:
    var n = 512 + len(argv()) - 1
    var out = List[Float64](length=n, fill=0.0)
    var op = out.unsafe_ptr()
    var t0 = perf_counter_ns()

    def job(i: Int) {mut op}:
        op[i] = heavy(i, 200000)

    parallelize(job, n)
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, out[7])
