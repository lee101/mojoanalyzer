def total(var xs: List[Float64]) -> Float64:
    var s = 0.0
    for x in xs:
        s += x
    return s + Float64(len(xs))


def main():
    var a = List[Float64](length=3, fill=1.0)
    print(total(a^))
