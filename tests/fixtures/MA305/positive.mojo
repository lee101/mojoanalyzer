def count(syms: List[String], n: Int) raises -> Int:
    var d = Dict[String, Int]()
    for i in range(n):
        var s = syms[i % len(syms)]
        if s + ":" + String(i % 3) in d:
            d[s + ":" + String(i % 3)] += 1
        else:
            d[s + ":" + String(i % 3)] = 1
    return len(d)


def main() raises:
    var syms: List[String] = ["A", "B"]
    print(count(syms, 10))
