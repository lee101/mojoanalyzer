struct Holder(Movable):
    var xs: List[Int]

    def __init__(out self, var xs: List[Int]):
        self.xs = xs^


def sorted_copy(var xs: List[Int]) -> List[Int]:
    sort(xs)
    return xs^


def appended(var xs: List[Int]) -> Int:
    xs.append(1)
    return len(xs)


def count(var n: Int) -> Int:
    return n + 1


def main():
    var h = Holder([1, 2])
    print(len(h.xs), len(sorted_copy([3, 1])), appended([1]), count(2))
