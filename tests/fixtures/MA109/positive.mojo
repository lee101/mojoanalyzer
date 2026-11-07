def total(rows: List[List[Float64]]) -> Float64:
    var s = 0.0
    for i in range(len(rows)):
        var row = rows[i].copy()
        s += row[0] + Float64(len(row))
    return s


def main():
    var rows = List[List[Float64]](length=3, fill=List[Float64](length=4, fill=1.0))
    print(total(rows))
