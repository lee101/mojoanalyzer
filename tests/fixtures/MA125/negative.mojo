def norm(xs: List[Float64]) -> Float64:
    var s = 0.0
    for i in range(len(xs)):
        s += xs[i] * xs[i]
    return s


def sq(x: Float64) -> Float64:
    return x * x


def bump(mut c: List[Float64]) -> Float64:
    c[0] += 1.0
    var s = 0.0
    for v in c:
        s += v
    return s


def noisy(xs: List[Float64]) -> Float64:
    var s = 0.0
    for v in xs:
        print(v)
        s += v
    return s


def main():
    var xs: List[Float64] = [1.0, 2.0]
    var ys: List[Float64] = [3.0]
    var a = norm(xs) + norm(ys)
    var b = sq(a) + sq(a)
    var c = bump(xs) + bump(xs)
    var d = noisy(xs) + noisy(xs)
    print(a, b, c, d)
