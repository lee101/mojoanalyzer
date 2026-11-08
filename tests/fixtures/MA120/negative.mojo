@fieldwise_init
struct Bar(Copyable, Movable):
    var open: Float64
    var high: Float64
    var low: Float64
    var close: Float64
    var volume: Float64


@fieldwise_init
struct Pt(Copyable, Movable):
    var x: Float64
    var y: Float64


def ohl(bars: List[Bar]) -> Float64:
    var s = 0.0
    for i in range(len(bars)):
        s += bars[i].open + bars[i].high + bars[i].low
    return s


def whole(bars: List[Bar]) -> Float64:
    var s = 0.0
    var last = bars[0].copy()
    for i in range(len(bars)):
        s += bars[i].close
        last = bars[i].copy()
    return s + last.open


def small(ps: List[Pt]) -> Float64:
    var s = 0.0
    for i in range(len(ps)):
        s += ps[i].x
    return s


def main():
    var bars = List[Bar]()
    bars.append(Bar(1.0, 2.0, 0.5, 1.5, 10.0))
    var ps = List[Pt]()
    ps.append(Pt(1.0, 2.0))
    print(ohl(bars), whole(bars), small(ps))
