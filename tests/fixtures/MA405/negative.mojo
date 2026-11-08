from std.sys.info import size_of


def str(x: Int) -> String:
    return String(x)


@fieldwise_init
struct P(Copyable, Movable):
    var x: Int


def main():
    print(str(size_of[Int]()), P(1).x)
