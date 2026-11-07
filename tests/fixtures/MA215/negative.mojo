struct Cfg:
    var loc_bps: Float64

    def __init__(out self, raw: Float64):
        self.loc_bps = raw * 1e-4


def fill_px(px: Float64, slip_bps: Float64, c: Cfg) -> Float64:
    return px * (1.0 + slip_bps / 1e4) * (1.0 + c.loc_bps)


def main():
    print(fill_px(100.0, 5.0, Cfg(3.0)))
