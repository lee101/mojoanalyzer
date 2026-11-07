def filtered(n: Int) -> List[Int]:
    var xs = List[Int]()
    for i in range(n):
        if i % 2 == 0:
            xs.append(i)
    return xs^


def early(n: Int) -> List[Int]:
    var xs = List[Int]()
    for i in range(n):
        if i > 10:
            break
        xs.append(i)
    return xs^


def reserved(n: Int) -> List[Int]:
    var xs = List[Int](capacity=n)
    for i in range(n):
        xs.append(i)
    return xs^


def twice(n: Int) -> List[Int]:
    var xs = List[Int]()
    for i in range(n):
        xs.append(i)
        xs.append(-i)
    return xs^


def from_split(s: String) raises -> List[Int]:
    var xs = List[Int]()
    for p in s.split(","):
        xs.append(atol(p))
    return xs^


def main() raises:
    print(len(filtered(5)), len(early(20)), len(reserved(3)), len(twice(2)), len(from_split("1,2")))
