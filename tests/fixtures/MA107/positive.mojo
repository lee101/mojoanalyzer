def csv(xs: List[Float64]) -> String:
    var s = String()
    for i in range(len(xs)):
        s += String(xs[i]) + ","
    return s


def labels(n: Int) -> String:
    var out = String("")
    for i in range(n):
        out = out + "k" + String(i)
    return out


def main():
    var xs = List[Float64](length=3, fill=1.5)
    print(csv(xs), labels(3))
