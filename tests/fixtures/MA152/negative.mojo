@fieldwise_init
struct Cfg(Copyable, Movable):
    var name: String
    var grp: String
    var m: Int
    var g: Float64


@fieldwise_init
struct P(Copyable, Movable):
    var a: Float64
    var b: Float64


def s6() -> Cfg:
    return Cfg("s6", "sic2", 6, 0.5)


def plain() -> P:
    return P(1.0, 2.0)


def gross(W: List[Float64]) -> Float64:
    var gfix = s6().g
    var t = 0.0
    for k in range(len(W)):
        t += W[k] * gfix + plain().a
    return t
