def grid(n: Int, k: Int) -> Float64:
    var m = List[List[Float64]](capacity=n)
    for i in range(n):
        m.append(List[Float64](length=k, fill=0.0))
    var t = List[List[Float64]](length=n, fill=List[Float64](length=k, fill=1.0))
    return m[0][0] + t[0][0]


def main():
    print(grid(3, 4))
