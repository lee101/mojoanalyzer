def ragged(n: Int) -> Int:
    var m = List[List[Int]]()
    for i in range(n):
        m.append(List[Int](length=i + 1, fill=0))
    return len(m)


def names(n: Int) -> Int:
    var m = List[List[String]]()
    for i in range(n):
        m.append(List[String](length=2, fill="a"))
    return len(m)


def tiny() -> Float64:
    var t = List[List[Float64]](length=3, fill=List[Float64](length=4, fill=1.0))
    return t[0][0]


def main():
    print(ragged(3), names(2), tiny())
