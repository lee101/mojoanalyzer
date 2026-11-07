def clip(x: Float64) -> Float64:
    return min(max(x, 1.0), -1.0)


def clip2(x: Float64, lo: Float64, hi: Float64) -> Float64:
    return min(max(x, hi), lo)


def main():
    print(clip(0.3), clip2(0.3, -1.0, 1.0))
