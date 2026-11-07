from std.math import exp


def mean(xs: List[Float64]) -> Float64:
    var n = len(xs)
    if n == 0:
        return 0.0
    var s = 0.0
    for x in xs:
        s += x
    return s / Float64(n)


def ranks(xs: List[Float64]) -> List[Float64]:
    var n = len(xs)
    var out = List[Float64](length=n, fill=0.0)
    for i in range(n):
        out[i] = (Float64(i) + 0.5) / Float64(n)
    return out^


def stoch(c: Float64, h: Float64, l: Float64) -> Float64:
    return (c - l) / (h - l) if h > l else 0.5


def safe(a: Float64, sd: Float64) -> Float64:
    var d = max(sd, 1e-12)
    var e = sd + 1e-9
    return a / d + a / e


def softmax_norm(xs: List[Float64]) -> Float64:
    var tot = 0.0
    for x in xs:
        tot += exp(x)
    return 1.0 / tot


def appended(x: Float64) -> Float64:
    var ys = List[Float64]()
    ys.append(x)
    return x / Float64(len(ys))


def main():
    var xs: List[Float64] = [1.0, 2.0]
    print(mean(xs), ranks(xs)[0], stoch(1.0, 2.0, 0.5), safe(1.0, 0.0), softmax_norm(xs), appended(2.0))
