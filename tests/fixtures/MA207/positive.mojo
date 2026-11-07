def converged(px: Float64, target: Float64) -> Bool:
    return px - target < 1e-9


def close_enough(a: Float64, b: Float64, tol: Float64) -> Bool:
    return a - b <= tol


def main():
    print(converged(1.0, 2.0), close_enough(1.0, 5.0, 0.1))
