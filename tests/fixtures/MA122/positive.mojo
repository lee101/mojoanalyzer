def f(xs: List[Int]) -> Int:
    var s = 0
    for i in range(len(xs)):
        s += xs[i] // 8 + xs[i] % 16
    return s


def halve(n0: Int) -> Int:
    var n = n0
    var c = 0
    while n > 0:
        n //= 2
        c += 1
    return c


def main():
    var xs: List[Int] = [1, 2, 3, -7]
    print(f(xs), halve(1000))
