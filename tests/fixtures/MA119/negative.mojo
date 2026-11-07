def consume(var xs: List[Float64]) -> Float64:
    xs.append(1.0)
    return xs[0]


def bump(mut xs: List[Float64]):
    xs[0] += 1.0


def both(a: List[Float64], mut b: List[Float64]):
    b[0] = a[0]


def main():
    var a = List[Float64](length=3, fill=1.0)
    var c = a.copy()
    bump(c)
    both(a.copy(), a)
    print(consume(a.copy()), c[0], a[0])
