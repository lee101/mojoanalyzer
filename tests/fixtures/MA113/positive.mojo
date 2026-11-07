def matvec(w: List[Float64], x: List[Float64], n: Int, m: Int) -> List[Float64]:
    var out = List[Float64](length=n, fill=0.0)
    for i in range(n):
        var s = 0.0
        for j in range(m):
            if x[j] == x[j]:
                s += w[i * m + j] * x[j]
        out[i] = s
    return out^


def main():
    var w = List[Float64](length=6, fill=1.0)
    var x = List[Float64](length=3, fill=2.0)
    print(matvec(w, x, 2, 3)[1])
