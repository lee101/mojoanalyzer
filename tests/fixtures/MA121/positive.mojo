from std.sys.info import size_of


struct Fill:
    var buy: Bool
    var px: Float64
    var ok: Bool
    var qty: Float64

    def __init__(out self):
        self.buy = True
        self.px = 1.0
        self.ok = False
        self.qty = 2.0


def main():
    var fills = List[Fill]()
    fills.append(Fill())
    print(size_of[Fill](), len(fills))
