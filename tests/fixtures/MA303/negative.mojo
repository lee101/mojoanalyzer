def reused(n: Int) -> List[List[Float64]]:
    var rows = List[List[Float64]](capacity=n)
    var row = List[Float64](length=4, fill=0.0)
    for i in range(n):
        row[0] = Float64(i)
        rows.append(row.copy())
    return rows^


def after(n: Int) -> Int:
    var a = List[Int](length=n, fill=1)
    var b = a.copy()
    b.append(2)
    return len(a) + len(b)


def param(xs: List[Int]) -> List[Int]:
    return xs.copy()


def main():
    print(len(reused(2)), after(3), len(param(List[Int]())))
