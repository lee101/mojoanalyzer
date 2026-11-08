def f(var x: List[Int], mut y: Int) -> Int:
    y += 1
    return len(x)


def main():
    var x = 1
    var y = 0

    def g() {imm x} -> Int:
        return x

    print(f(List[Int](), y), g(), y)
