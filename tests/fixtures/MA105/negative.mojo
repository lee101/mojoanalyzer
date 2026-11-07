def carried(a: List[Float64], n: Int, m: Int) -> Float64:
    var tot = 0.0
    for i in range(n):
        for j in range(m):
            tot += a[i * m + j]
    return tot


def appends(n: Int, m: Int) -> List[Float64]:
    var out = List[Float64]()
    for i in range(n):
        var s = 0.0
        for j in range(m):
            s += Float64(j)
        out.append(s)
    return out^


def neighbour(mut out: List[Float64], n: Int, m: Int):
    for i in range(1, n):
        var s = 0.0
        for j in range(m):
            s += Float64(j)
        out[i] = out[i - 1] + s


def prints(n: Int, m: Int):
    for i in range(n):
        var s = 0.0
        for j in range(m):
            s += Float64(j)
        print(s)


def light(mut out: List[Float64], n: Int):
    for i in range(n):
        out[i] = Float64(i) * 2.0


def main():
    var a = List[Float64](length=12, fill=1.0)
    var o = List[Float64](length=4, fill=0.0)
    neighbour(o, 4, 3)
    prints(2, 2)
    light(o, 4)
    print(carried(a, 3, 4), appends(2, 2)[0], o[3])
