def total(d: Dict[String, Int]) -> Int:
    var s = 0
    for e in d.items():
        s += e.value
    return s


def bump(mut d: Dict[String, Int]) raises:
    for k in d.keys():
        d[k] = d[k] + 1


def other(d: Dict[String, Int], e: Dict[String, Int]) raises -> Int:
    var s = 0
    for k in d:
        s += e[k]
    return s


def main() raises:
    var d = Dict[String, Int]()
    d["a"] = 1
    bump(d)
    print(total(d), other(d, d))
