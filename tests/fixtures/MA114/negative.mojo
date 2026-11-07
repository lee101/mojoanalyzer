def rowwise(a: List[Float64], mut s: List[Float64], n: Int, m: Int):
    var ap = a.unsafe_ptr()
    var sp = s.unsafe_ptr()
    for i in range(n):
        for j in range(m):
            sp[j] += ap[i * m + j]


def scalar_acc(a: List[Float64], n: Int, m: Int) -> Float64:
    var ap = a.unsafe_ptr()
    var t = 0.0
    for j in range(m):
        for i in range(n):
            t += ap[i * m + j]
    return t


def mixed(a: List[Float64], mut b: List[Float64], n: Int, m: Int):
    var ap = a.unsafe_ptr()
    var bp = b.unsafe_ptr()
    for j in range(m):
        for i in range(n):
            bp[j * n + i] = ap[i * m + j]


def triangular(mut a: List[Float64], n: Int):
    var ap = a.unsafe_ptr()
    for j in range(n):
        for i in range(j):
            ap[i * n + j] = 0.0


def main():
    var a = List[Float64](length=12, fill=1.0)
    var s = List[Float64](length=4, fill=0.0)
    var b = List[Float64](length=12, fill=0.0)
    var sq = List[Float64](length=9, fill=1.0)
    rowwise(a, s, 3, 4)
    mixed(a, b, 3, 4)
    triangular(sq, 3)
    print(s[1], scalar_acc(a, 3, 4), b[1], sq[1])
