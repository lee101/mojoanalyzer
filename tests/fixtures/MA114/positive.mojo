def colsum(a: List[Float64], mut s: List[Float64], n: Int, m: Int):
    var ap = a.unsafe_ptr()
    var sp = s.unsafe_ptr()
    for j in range(m):
        for i in range(n):
            sp[j] += ap[i * m + j]


def transpose_scale(a: List[List[Float64]], mut b: List[List[Float64]], n: Int, m: Int):
    for j in range(m):
        for i in range(n):
            b[i][j] = a[i][j] * 2.0


def main():
    var a = List[Float64](length=12, fill=1.0)
    var s = List[Float64](length=4, fill=0.0)
    colsum(a, s, 3, 4)
    var aa = List[List[Float64]](length=3, fill=List[Float64](length=4, fill=1.0))
    var bb = List[List[Float64]](length=3, fill=List[Float64](length=4, fill=0.0))
    transpose_scale(aa, bb, 3, 4)
    print(s[1], bb[2][3])
