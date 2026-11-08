def mutated(a: List[Int]) -> Int:
    var b = a.copy()
    b.append(3)
    return len(b)


def source_changes(mut a: List[Int]) -> Int:
    var b = a.copy()
    a.append(1)
    return len(b) + len(a)


def in_loop(rows: List[List[Int]]) -> Int:
    var t = 0
    for i in range(len(rows)):
        var r = rows[i].copy()
        t += r[0]
    return t


def main():
    var xs: List[Int] = [1, 2]
    var rows = List[List[Int]]()
    rows.append(xs.copy())
    print(mutated(xs), source_changes(xs), in_loop(rows))
