def cols(hdr: String, n: Int) raises -> Int:
    var t = 0
    for i in range(n):
        var parts = hdr.split(",")
        t += parts[i % 2].byte_length()
    return t


def matches(sym: String, xs: List[String]) -> Int:
    var t = 0
    for i in range(len(xs)):
        if xs[i] == String(sym).upper():
            t += 1
    return t


def main() raises:
    var xs: List[String] = ["A", "b"]
    print(cols("a,b", 3), matches("a", xs))
