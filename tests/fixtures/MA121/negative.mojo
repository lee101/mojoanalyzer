from std.sys.info import size_of


struct Sorted:
    var px: Float64
    var qty: Float64
    var buy: Bool
    var ok: Bool

    def __init__(out self):
        self.px = 1.0
        self.qty = 2.0
        self.buy = True
        self.ok = False


struct Named:
    var buy: Bool
    var sym: String
    var ok: Bool

    def __init__(out self):
        self.buy = True
        self.sym = "A"
        self.ok = False


def main():
    print(size_of[Sorted](), Named().sym)
