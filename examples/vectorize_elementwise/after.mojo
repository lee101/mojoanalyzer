from std.time import perf_counter_ns
from std.sys import argv, simd_width_of
from std.math import sqrt
from std.algorithm import vectorize


def kern(mut y: List[Float32], x: List[Float32], a: Float32, b: Float32):
    var yp = y.unsafe_ptr()
    var xp = x.unsafe_ptr()

    def body[w: Int](i: Int) {mut yp, xp, a, b}:
        yp.unsafe_store[width=w](i, sqrt(xp.unsafe_load[width=w](i)) * a + b)

    vectorize[simd_width_of[DType.float32]()](len(y), body)


def main() raises:
    var n = 1 << 16 + len(argv()) - 1
    var x = List[Float32](length=n, fill=2.0)
    var y = List[Float32](length=n, fill=0.0)
    var t0 = perf_counter_ns()
    for r in range(5000):
        kern(y, x, 1.0 + Float32(r), 0.5)
    print("ms", Float64(perf_counter_ns() - t0) / 1e6, y[7])
