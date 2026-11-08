@fieldwise_init
struct Bar(Copyable, Movable):
    var open: Float64
    var high: Float64
    var low: Float64
    var close: Float64
    var volume: Float64


def total(bars: List[Bar]) -> Float64:
    var s = 0.0
    for i in range(len(bars)):
        s += bars[i].close
    return s


def total_iter(bars: List[Bar]) -> Float64:
    var s = 0.0
    for b in bars:
        s += b.volume
    return s


def main():
    var bars = List[Bar]()
    bars.append(Bar(1.0, 2.0, 0.5, 1.5, 10.0))
    print(total(bars), total_iter(bars))
