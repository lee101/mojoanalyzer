from std.memory import alloc


struct Pool:
    var capacity: Int

    def __init__(out self):
        self.capacity = 4


def main():
    var xs = List[Int](capacity=4)
    var a = SIMD[DType.float32, 4](1.0)
    var b = SIMD[DType.float32, 4](2.0)
    var p = alloc[Int](4)
    p.unsafe_free()
    print(xs.capacity(), max(a, b), Pool().capacity)
