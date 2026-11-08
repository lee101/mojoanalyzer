def count(syms: List[String], n: Int) raises -> Int:
    var d = Dict[String, Int]()
    for i in range(n):
        var key = syms[i % len(syms)] + ":" + String(i % 3)
        if key in d:
            d[key] += 1
        else:
            d[key] = 1
    return len(d)


def changes(syms: List[String]) raises -> Int:
    var d = Dict[String, Int]()
    var s = syms[0]
    d[s + "x"] = 1
    s = syms[1]
    d[s + "x"] = 2
    return len(d)


def main() raises:
    var syms: List[String] = ["A", "B"]
    print(count(syms, 10), changes(syms))
