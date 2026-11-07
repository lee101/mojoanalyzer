def halves(mut y: List[Float64]):
    var yp = y.unsafe_ptr()
    for i in range(len(y)):
        yp[i] = yp[i] / 2.0


def variant(mut y: List[Float64], x: List[Float64]):
    var yp = y.unsafe_ptr()
    var xp = x.unsafe_ptr()
    var d = 1.0
    for i in range(len(y)):
        d += 1.0
        yp[i] = xp[i] / d


def ints(xs: List[Int], k: Int) -> Int:
    var s = 0
    for i in range(len(xs)):
        s += xs[i] // k
    return s


def invariant_whole(mut y: List[Float64], a: Float64, d: Float64):
    var yp = y.unsafe_ptr()
    for i in range(len(y)):
        yp[i] = a / d


def main():
    var x = List[Float64](length=8, fill=3.0)
    var y = List[Float64](length=8, fill=0.0)
    var xi = List[Int](length=8, fill=3)
    halves(y)
    variant(y, x)
    invariant_whole(y, 1.0, 3.0)
    print(y[1], ints(xi, 2))
