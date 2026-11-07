def reversed_ids(n: Int) -> List[Int]:
    var xs = List[Int]()
    for i in range(n):
        xs.insert(0, i)
    return xs^


def drain(mut q: List[Int]) -> Int:
    var s = 0
    while len(q) > 0:
        s += q.pop(0)
    return s


def main():
    var q = reversed_ids(4)
    print(drain(q))
