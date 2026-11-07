def dot(a: List[Float64], b: List[Float64]) -> Float64:
    var ap = a.unsafe_ptr()
    var bp = b.unsafe_ptr()
    var s = 0.0
    for i in range(len(a)):
        s += ap[i] * bp[i]
    return s


def peak(a: List[Float32]) -> Float32:
    var m: Float32 = -1e30
    for i in range(len(a)):
        m = max(m, a[i])
    return m


def main():
    var a = List[Float64](length=64, fill=1.0)
    var f = List[Float32](length=64, fill=3.0)
    print(dot(a, a), peak(f))
