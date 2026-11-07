def normalize(mut y: List[Float64], x: List[Float64], d: Float64):
    var yp = y.unsafe_ptr()
    var xp = x.unsafe_ptr()
    for i in range(len(y)):
        yp[i] = xp[i] / d


def per_year(mut r: List[Float64]):
    var rp = r.unsafe_ptr()
    for i in range(len(r)):
        rp[i] = (rp[i] + 0.01) / 252.0


def row_normalize(mut a: List[Float64], n: Int):
    for c in range(n):
        var d = a[c * n + c]
        for q in range(n):
            a[c * n + q] /= d


def main():
    var x = List[Float64](length=8, fill=3.0)
    var y = List[Float64](length=8, fill=0.0)
    normalize(y, x, 3.0)
    per_year(y)
    var sq = List[Float64](length=4, fill=2.0)
    row_normalize(sq, 2)
    print(y[1])
