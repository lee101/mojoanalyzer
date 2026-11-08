def main():
    var xs: List[Float64] = [3.0, 1.0, 2.0]
    var acc = 0.0
    for r in range(3):
        xs.append(Float64(r))
        sort(xs)
        acc += xs[r]
    for r in range(2):
        var ys: List[Float64] = [Float64(r), 0.0]
        sort(ys)
        acc += ys[0]
    print(acc)
