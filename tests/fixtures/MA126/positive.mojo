def total(d: Dict[String, Int]) raises -> Int:
    var s = 0
    for k in d:
        s += d[k]
    return s


def main() raises:
    var d = Dict[String, Int]()
    d["a"] = 1
    print(total(d))
