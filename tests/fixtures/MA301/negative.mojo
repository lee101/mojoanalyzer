def kept(n: Int) -> List[List[Int]]:
    var out = List[List[Int]]()
    for i in range(n):
        var row = List[Int]()
        row.append(i)
        out.append(row^)
    return out^


def sized(xs: List[Int]) -> Int:
    var t = 0
    for i in range(len(xs)):
        var row = List[Int](capacity=xs[i])
        row.append(i)
        t += len(row)
    return t


def unused(n: Int) -> Int:
    var t = 0
    for i in range(n):
        var row = List[Int]()
        t += len(row) + i
    return t


def literal_loop() -> Int:
    var t = 0
    for i in range(3):
        var row = List[Int]()
        row.append(i)
        t += len(row)
    return t


def returned(n: Int) -> List[Int]:
    for i in range(n):
        var row = List[Int]()
        row.append(i)
        if i == 2:
            return row^
    return List[Int]()


def main():
    var xs: List[Int] = [1, 2]
    print(len(kept(2)), sized(xs), unused(2), literal_loop(), len(returned(4)))
