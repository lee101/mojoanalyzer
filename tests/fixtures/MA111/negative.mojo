def uses_index(xs: List[Float64]) -> Float64:
    var s = 0.0
    for i in range(len(xs)):
        s += xs[i] * Float64(i)
    return s


def writes(mut xs: List[Float64]):
    for i in range(len(xs)):
        xs[i] = xs[i] * 2.0


def two_lists(xs: List[Float64], ys: List[Float64]) -> Float64:
    var s = 0.0
    for i in range(len(xs)):
        s += xs[i] * ys[i]
    return s


def grow_rows(mut rows: List[List[Int]]):
    for i in range(len(rows)):
        rows[i].append(0)


def main():
    var xs = List[Float64](length=3, fill=1.0)
    writes(xs)
    var rows = List[List[Int]](length=2, fill=List[Int]())
    grow_rows(rows)
    print(uses_index(xs), two_lists(xs, xs), len(rows[0]))
