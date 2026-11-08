from std.memory import alloc


def windows(xs: List[Float64], k: Int) -> Float64:
    var s = 0.0
    for i in range(len(xs) - k):
        var win = List[Float64]()
        for j in range(k):
            win.append(xs[i + j])
        s += win[0] + win[len(win) - 1]
    return s


def counts(xs: List[Int]) -> Int:
    var t = 0
    for i in range(len(xs)):
        var c = Dict[Int, Int]()
        for j in range(4):
            c[(xs[i] + j) % 3] = j
        t += len(c)
    return t


def lines(n: Int) -> Int:
    var t = 0
    for i in range(n):
        var line = String()
        line.write(i, ",", i * 2)
        t += line.byte_length()
    return t


def scratch(n: Int, k: Int) -> Int:
    var t = 0
    for i in range(n):
        var p = alloc[Int](k)
        p[unsafe_offset=0] = i
        t += p[unsafe_offset=0]
        p.free()
    return t


def main():
    var xs: List[Float64] = [1.0, 2.0, 3.0, 4.0]
    var ys: List[Int] = [1, 2, 3]
    print(windows(xs, 2), counts(ys), lines(3), scratch(3, 4))
