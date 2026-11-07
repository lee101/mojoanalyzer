comptime V = SIMD[DType.float64, 4]


def cold(v: V) -> Float64:
    var s = 0.0
    for l in range(4):
        s += v[l]
    return s


def big_trip(xs: List[V]) -> Float64:
    var s = 0.0
    for i in range(len(xs)):
        for l in range(64):
            s += Float64(l)
    return s


def early_exit(xs: List[V]) -> Float64:
    var s = 0.0
    for i in range(len(xs)):
        var v = xs[i]
        for l in range(4):
            if v[l] < 0:
                break
            s += v[l]
    return s


def runtime_trip(xs: List[V], k: Int) -> Float64:
    var s = 0.0
    for i in range(len(xs)):
        var v = xs[i]
        for l in range(k):
            s += v[l]
    return s


def already(xs: List[V]) -> Float64:
    var s = 0.0
    for i in range(len(xs)):
        var v = xs[i]
        comptime for l in range(4):
            s += v[l]
    return s


def main():
    var xs = List[V](length=2, fill=V(1, 2, 3, 4))
    print(cold(xs[0]), big_trip(xs), early_exit(xs), runtime_trip(xs, 2), already(xs))
