from std.math import isnan, isfinite


def ok(x: Float64, y: Float64) -> Bool:
    return isnan(x) or not isfinite(y) or x != y


def main():
    print(ok(1.0, 2.0))
