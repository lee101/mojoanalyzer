def converged(px: Float64, target: Float64) -> Bool:
    return abs(px - target) < 1e-9


def both(a: Float64, b: Float64, eps: Float64) -> Bool:
    return a - b < eps and b - a < eps


def margin(a: Float64, b: Float64) -> Bool:
    return a - b < 0.5


def main():
    print(converged(1.0, 2.0), both(1.0, 1.0, 0.1), margin(1.0, 2.0))
