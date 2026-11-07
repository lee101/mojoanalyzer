def to_shares(target: Float64, held: Float64, px: Float64) -> Int:
    return Int((target - held) / px + 0.5)


def held_qty(raw: String) raises -> Int:
    return Int(atof(raw + "") if raw != "qty" else 0.0)


def short_qty(notional: Float64, px: Float64) -> Int:
    return Int(-notional / px)


def main() raises:
    print(to_shares(100.0, 250.0, 10.0), held_qty("1.5"), short_qty(100.0, 3.0))
