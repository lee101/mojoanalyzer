def head(a: List[Int]) -> Int:
    var b = a.copy()
    return b[0] + len(b)


def main():
    var xs: List[Int] = [1, 2]
    print(head(xs))
