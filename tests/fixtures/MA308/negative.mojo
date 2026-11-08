def odd(n: Int) -> Int:
    var d = Dict[Int, Int]()
    for i in range(n):
        if i % 2 == 1:
            d[i] = i
    return len(d)


def small() -> Int:
    var d = Dict[Int, Int]()
    for i in range(8):
        d[i] = i
    return len(d)


def sized(n: Int) -> Int:
    var d = Dict[Int, Int](capacity=n)
    for i in range(n):
        d[i] = i
    return len(d)


def main():
    print(odd(10), small(), sized(10))
