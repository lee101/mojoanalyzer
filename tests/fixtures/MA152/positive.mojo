@fieldwise_init
struct Cfg(Copyable, Movable):
    var name: String
    var grp: String
    var m: Int
    var g: Float64


def s6() -> Cfg:
    return Cfg("s6", "sic2", 6, 0.5)


def gross(W: List[Float64]) -> Float64:
    var t = 0.0
    for k in range(len(W)):
        t += W[k] * s6().g
    return t
