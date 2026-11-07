def fill_px(px: Float64, slip_bps: Float64) -> Float64:
    return px * (1.0 + slip_bps)


def main():
    print(fill_px(100.0, 5.0))
