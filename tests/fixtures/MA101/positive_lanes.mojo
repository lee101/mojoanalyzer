comptime V = SIMD[DType.float64, 4]


def weighted(xs: List[V]) -> Float64:
    var p = xs.unsafe_ptr()
    var s = 0.0
    for i in range(len(xs)):
        var v = p[i]
        for l in range(4):
            s += v[l] * Float64(l + 1)
    return s


def main():
    var xs = List[V](length=8, fill=V(1, 2, 3, 4))
    print(weighted(xs))
