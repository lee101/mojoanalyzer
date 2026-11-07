def frac(hits: Int, total: Int) -> Float64:
    return Float64(hits / total)


def half(n: Int) -> Float64:
    return Float64(n / 2) * 0.5


def main():
    print(frac(1, 3), half(7))
