def fill_px(side: Int, bid: Float64, ask: Float64) -> Float64:
    var px = 0.0
    if side > 0:
        px = ask
    else:
        px = bid
    if side == 0:
        px = bid
    return px


def main():
    print(fill_px(1, 1.0, 2.0))
