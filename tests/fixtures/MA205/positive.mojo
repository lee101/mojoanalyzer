from std.math import sqrt, log


def vol(s2: Float64, s1: Float64, n: Int) -> Float64:
    var mu = s1 / Float64(n)
    return sqrt(s2 / Float64(n) - mu * mu)


def vol2(s2: Float64, mu: Float64) -> Float64:
    var v = s2 - mu * mu
    return sqrt(v)


def gap(px: Float64, prev: Float64) -> Float64:
    return log(px - prev)


def main():
    print(vol(10.0, 3.0, 4), vol2(1.0, 0.5), gap(2.0, 1.0))
