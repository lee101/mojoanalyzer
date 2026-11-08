comptime N = 4


def f(x: Int) -> Int:
    var fnx = x
    return fnx


def main():
    var out = f(N)
    print(out)
