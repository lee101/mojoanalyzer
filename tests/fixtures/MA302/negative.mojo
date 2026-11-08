def cols(var hdr: String, n: Int) raises -> Int:
    var t = 0
    for i in range(n):
        var parts = hdr.split(",")
        t += parts[0].byte_length()
        hdr += ",x"
    return t


def fresh(base: List[Int], n: Int) -> Int:
    var t = 0
    for i in range(n):
        var row = base.copy()
        row.append(i)
        t += len(row)
    return t


def per_row(rows: List[String]) raises -> Int:
    var t = 0
    for r in rows:
        var parts = r.split(",")
        t += len(parts)
    return t


def main() raises:
    var b: List[Int] = [1]
    var rows: List[String] = ["a,b"]
    print(cols("a,b", 2), fresh(b, 2), per_row(rows))
