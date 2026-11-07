def frac(hits: Int, total: Int) -> Float64:
    return Float64(hits) / Float64(total)


def mid(n: Int) -> Int:
    return n // 2


def scale(x: Float64, n: Int) -> Float64:
    return x / Float64(n)


def main():
    print(frac(1, 3), mid(7), scale(1.0, 4))
