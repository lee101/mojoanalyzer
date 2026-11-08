@register_passable("trivial")
struct P:
    var x: Int

    def __init__(out self, x: Int):
        self.x = x


def main():
    print(P(1).x)
