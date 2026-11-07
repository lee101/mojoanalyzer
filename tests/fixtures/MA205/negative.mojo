from std.math import sqrt, log


def vol(s2: Float64, s1: Float64, n: Int) -> Float64:
    var mu = s1 / Float64(n)
    return sqrt(max(s2 / Float64(n) - mu * mu, 0.0))


def adam(b2: Float64, t: Int) -> Float64:
    return sqrt(1.0 - b2 ** Float64(t))


def ret(px: Float64, prev: Float64) -> Float64:
    return log(px / prev) if px > 0 and prev > 0 else 0.0


def main():
    print(vol(10.0, 3.0, 4), adam(0.999, 3), ret(2.0, 1.0))
