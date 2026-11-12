def tilt_into(x: List[Float64], a: Float64, mut w: List[Float64]):
    w.clear()
    for k in range(len(x)):
        w.append(1.0 + a * x[k])


def tilt(x: List[Float64], a: Float64) -> List[Float64]:
    var w = List[Float64](length=len(x), fill=1.0)
    for k in range(len(x)):
        w[k] = 1.0 + a * x[k]
    return w^


def fill_cache(mut cache: List[List[Float64]], x: List[Float64]):
    if len(x) == 0:
        return
    var w = List[Float64](length=len(x), fill=1.0)
    cache.append(w^)


def warm(mut cache: List[List[Float64]], xs: List[List[Float64]]):
    for k in range(len(xs)):
        fill_cache(cache, xs[k])


def nights(xs: List[List[Float64]], a: Float64) -> Float64:
    var acc = 0.0
    var w = List[Float64]()
    for k in range(len(xs)):
        tilt_into(xs[k], a, w)
        acc += w[0]
    var once = tilt(xs[0], a)
    return acc + once[0]
