def appends(xs: List[String]) -> String:
    var s = String()
    for x in xs:
        s += x
    return s


def written(n: Int) -> String:
    var s = String()
    for i in range(n):
        s.write(i, ",")
    return s


def once(a: String, b: String) -> String:
    var s = String()
    s += a + b
    return s


def numbers(n: Int) -> Int:
    var t = 0
    for i in range(n):
        t += i + 1
    return t


def main():
    var xs: List[String] = ["a", "b"]
    print(appends(xs), written(3), once("x", "y"), numbers(3))
