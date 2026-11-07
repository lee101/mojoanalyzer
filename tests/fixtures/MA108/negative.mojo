def heavy_values(d: Dict[Int, List[Int]], k: Int) raises -> Int:
    if k in d:
        return len(d[k])
    return 0


def mutated(mut d: Dict[Int, Int], k: Int) raises -> Int:
    if k in d:
        d[k] = d[k] + 1
    return d[k] if k in d else 0


def rebound(d: Dict[Int, Int], k0: Int) raises -> Int:
    var k = k0
    if k in d:
        k = k + 1
        return d[k] if k in d else 0
    return 0


def found(d: Dict[Int, Int], k: Int) -> Int:
    var v = d.find(k)
    if v:
        return v.value()
    return 0


def main() raises:
    var d = Dict[Int, List[Int]]()
    d[1] = [1, 2]
    var e = Dict[Int, Int]()
    e[1] = 2
    print(heavy_values(d, 1), mutated(e, 1), rebound(e, 0), found(e, 1))
