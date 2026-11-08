def norm(xs: List[Float64]) -> Float64:
    var s = 0.0
    for i in range(len(xs)):
        s += xs[i] * xs[i]
    return s


def main():
    var xs: List[Float64] = [1.0, 2.0]
    var acc = 0.0
    for _ in range(3):
        acc += norm(xs) / (1.0 + norm(xs))
    print(acc)
