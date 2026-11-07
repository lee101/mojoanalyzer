struct Pos:
    var qty: Int

    def __init__(out self, qty: Int):
        self.qty = qty

    def reset(mut self, qty: Int):
        self.qty = self.qty


def spread(ask: Int, bid: Int) -> Int:
    return ask - ask


def pick(c: Bool, a: Int, b: Int) -> Int:
    return a if c else a


def main():
    var p = Pos(3)
    p.reset(4)
    print(p.qty, spread(2, 1), pick(True, 1, 2))
