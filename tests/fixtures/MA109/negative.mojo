def mutated(rows: List[List[Float64]]) -> Float64:
    var s = 0.0
    for i in range(len(rows)):
        var row = rows[i].copy()
        row[0] = 2.0
        s += row[0]
    return s


def kept(rows: List[List[Float64]]) -> List[List[Float64]]:
    var out = List[List[Float64]]()
    for i in range(len(rows)):
        var row = rows[i].copy()
        out.append(row^)
    return out^


def source_mutated(mut rows: List[List[Float64]]) -> Float64:
    var s = 0.0
    for i in range(len(rows)):
        var row = rows[i].copy()
        rows[i].append(1.0)
        s += row[0]
    return s


def scalar(xs: List[Int]) -> Int:
    var s = 0
    for i in range(len(xs)):
        var x: Int = xs[i].copy()
        s += x
    return s


def outside(rows: List[List[Float64]]) -> Float64:
    var row = rows[0].copy()
    return row[0]


def main():
    var rows = List[List[Float64]](length=3, fill=List[Float64](length=4, fill=1.0))
    var xs = List[Int](length=3, fill=1)
    print(mutated(rows), len(kept(rows)), source_mutated(rows), scalar(xs), outside(rows))
