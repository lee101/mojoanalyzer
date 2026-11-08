def f(xs: List[Int], ys: List[Float64]) -> Float64:
    var s = 0.0
    for i in range(len(xs)):
        s += Float64(xs[i] // 6 + xs[i] % 10)
        s += ys[i] // 4.0
        s += ys[i] // 2
    return s


def once(n: Int) -> Int:
    return n // 8 + n % 4


def main():
    var xs: List[Int] = [1, 2]
    var ys: List[Float64] = [1.0, 2.0]
    print(f(xs, ys), once(17))
