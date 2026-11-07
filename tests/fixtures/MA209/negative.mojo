def finite(x: Float64) -> Bool:
    return x - x == 0.0


def nan_() -> Float64:
    var z = 0.0
    return z / z


def spread(ask: Int, bid: Int) -> Int:
    return ask - bid


def main():
    print(finite(1.0), nan_(), spread(2, 1))
