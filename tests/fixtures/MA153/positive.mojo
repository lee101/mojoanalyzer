def tilt(x: List[Float64], a: Float64) -> List[Float64]:
    var w = List[Float64](length=len(x), fill=1.0)
    for k in range(len(x)):
        w[k] = 1.0 + a * x[k]
    return w^


def nights(xs: List[List[Float64]], a: Float64) -> Float64:
    var acc = 0.0
    for k in range(len(xs)):
        var w = tilt(xs[k], a)
        acc += w[0]
    return acc
