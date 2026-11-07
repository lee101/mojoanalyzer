from std.math import sqrt


def heavy(seed: Int, m: Int) -> Float64:
    var s = 0.0
    for j in range(m):
        s += sqrt(Float64(seed * 31 + j))
    return s


def run(n: Int) -> List[Float64]:
    var out = List[Float64](length=n, fill=0.0)
    for i in range(n):
        out[i] = heavy(i, 1000)
    return out^


def rowsums(a: List[Float64], n: Int, m: Int) -> List[Float64]:
    var out = List[Float64](length=n, fill=0.0)
    for i in range(n):
        var s = 0.0
        for j in range(m):
            s += a[i * m + j]
        out[i] = s
    return out^


def main():
    var a = List[Float64](length=12, fill=1.0)
    print(run(4)[1], rowsums(a, 3, 4)[2])
