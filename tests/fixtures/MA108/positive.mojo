def tally(d: Dict[Int, Int], n: Int) raises -> Int:
    var s = 0
    for i in range(n):
        var k = i % 7
        if k in d:
            s += d[k]
    return s


def lookup(d: Dict[String, Float64], key: String) raises -> Float64:
    if key in d:
        return d[key] * 2.0
    return 0.0


def main() raises:
    var d = Dict[Int, Int]()
    d[3] = 4
    var e = Dict[String, Float64]()
    e["a"] = 1.5
    print(tally(d, 10), lookup(e, "a"))
