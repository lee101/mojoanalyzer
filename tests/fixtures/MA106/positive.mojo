def squares(n: Int) -> List[Int]:
    var xs = List[Int]()
    for i in range(n):
        xs.append(i * i)
    return xs^


def doubled(src: List[Float64]) -> List[Float64]:
    var out = List[Float64]()
    for x in src:
        out.append(x * 2.0)
    return out^


def zeros(n: Int) -> List[Float64]:
    var z = List[Float64]()
    for _ in range(n):
        z.append(0.0)
    return z^


def main():
    print(len(squares(5)), len(doubled(zeros(3))))
