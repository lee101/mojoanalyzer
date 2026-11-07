def outer_only(x: List[Float64]) -> Float64:
    var s = 0.0
    for j in range(len(x)):
        if x[j] > 0:
            s += x[j]
    return s


def pointers(w: List[Float64], x: List[Float64], n: Int, m: Int) -> Float64:
    var wp = w.unsafe_ptr()
    var xp = x.unsafe_ptr()
    var s = 0.0
    for i in range(n):
        for j in range(m):
            if xp[j] > 0:
                s += wp[i * m + j] * xp[j]
    return s


def grows(mut xs: List[Float64], n: Int):
    for i in range(n):
        for j in range(2):
            if j > 0:
                xs.append(xs[j])


def strings(xs: List[String], n: Int) -> Int:
    var t = 0
    for i in range(n):
        for j in range(len(xs)):
            if xs[j] == "a":
                t += 1
    return t


def main():
    var w = List[Float64](length=6, fill=1.0)
    var x = List[Float64](length=3, fill=2.0)
    var ss: List[String] = ["a"]
    grows(x, 1)
    print(outer_only(x), pointers(w, x, 2, 3), strings(ss, 2))
