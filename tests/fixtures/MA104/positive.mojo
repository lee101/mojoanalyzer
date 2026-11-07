from std.algorithm import vectorize


def scale(mut a: List[Float32], k: Float32):
    var p = a.unsafe_ptr()

    def body[w: Int](i: Int) {mut p, k}:
        p.unsafe_store[width=w](i, p.unsafe_load[width=w](i) * k)

    vectorize[8](len(a), body)


def add(mut a: List[Float32], b: List[Float32]):
    comptime W = 8
    var pa = a.unsafe_ptr()
    var pb = b.unsafe_ptr()
    var n = len(a)
    var i = 0
    while i + W <= n:
        pa.unsafe_store[width=W](i, pa.unsafe_load[width=W](i) + pb.unsafe_load[width=W](i))
        i += W
    while i < n:
        pa[i] = pa[i] + pb[i]
        i += 1


def main():
    var a = List[Float32](length=37, fill=1.0)
    var b = List[Float32](length=37, fill=2.0)
    scale(a, 2.0)
    add(a, b)
    print(a[36])
