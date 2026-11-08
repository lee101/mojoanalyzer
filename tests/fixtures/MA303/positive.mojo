def build(n: Int) -> List[List[Float64]]:
    var rows = List[List[Float64]](capacity=n)
    for i in range(n):
        var row = List[Float64](length=4, fill=Float64(i))
        rows.append(row.copy())
    return rows^


def last(var xs: List[Int]) -> List[Int]:
    xs.append(1)
    return xs.copy()


def main():
    print(len(build(3)), len(last(List[Int]())))
