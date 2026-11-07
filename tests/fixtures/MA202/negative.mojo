from std.math import floor


def lots(cash: Float64, px: Float64) -> Int:
    return Int(floor(cash / px))


def cap(bp: Float64, px: Float64) -> Int:
    return Int(bp / px + 1e-9)


def bucket(u: Float64, n: Int) -> Int:
    return Int(u * Float64(n))


def rnd(x: Float64) -> Int:
    return Int(abs(x) * 100.0 + 0.5)


def main():
    print(lots(100.0, 3.0), cap(10.0, 3.0), bucket(0.5, 10), rnd(-1.234))
