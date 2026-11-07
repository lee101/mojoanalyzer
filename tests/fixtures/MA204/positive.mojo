from std.math import nan


def bad(x: Float64) -> Bool:
    return x == nan[DType.float64]()


def idiom(x: Float64) -> Bool:
    return x != x


def typo(n: Int) -> Bool:
    return n != n


def main():
    print(bad(1.0), idiom(1.0), typo(2))
