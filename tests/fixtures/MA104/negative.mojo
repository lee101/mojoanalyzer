from std.algorithm import vectorize
from std.sys import simd_width_of


def scale(mut a: List[Float32], k: Float32):
    var p = a.unsafe_ptr()
    comptime w0 = simd_width_of[DType.float32]()

    def body[w: Int](i: Int) {mut p, k}:
        p.unsafe_store[width=w](i, p.unsafe_load[width=w](i) * k)

    vectorize[w0](len(a), body)


def quad(a: List[Float32]) -> Float32:
    var p = a.unsafe_ptr()
    return p.unsafe_load[width=4](0).reduce_add()


def main():
    var a = List[Float32](length=37, fill=1.0)
    scale(a, 2.0)
    print(quad(a))
