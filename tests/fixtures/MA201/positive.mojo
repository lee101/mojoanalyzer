def mean(rets: List[Float64], extra: Float64) -> Float64:
    var s = extra
    for r in rets:
        s += r
    var n = len(rets)
    return s / Float64(n)


def hit_rate(xs: List[Float64]) -> Float64:
    var hits = 0
    var s = 0.0
    for x in xs:
        if x > 0.0:
            hits += 1
            s += x
    return s / Float64(hits)


def stoch(c: Float64, h: Float64, l: Float64) -> Float64:
    return (c - l) / (h - l)


def sample_var(ss: Float64, n: Int) -> Float64:
    return ss / Float64(n - 1)


def main():
    var xs: List[Float64] = [1.0, -2.0, 3.0]
    print(mean(xs, 0.0), hit_rate(xs), stoch(1.0, 2.0, 0.5), sample_var(2.0, 3))
