def present(names: List[String], name: String) -> Bool:
    for i in range(len(names)):
        if names[i] == name:
            return True
    return False


def total(xs: List[Float64]) -> Float64:
    var s = 0.0
    for i in range(len(xs)):
        s += xs[i] * 2.0
    return s


def main():
    var names: List[String] = ["a", "b"]
    var xs = List[Float64](length=3, fill=1.0)
    print(present(names, "b"), total(xs))
