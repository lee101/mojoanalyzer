def main():
    var xs: List[Float64] = [3.0, 1.0, 2.0]
    var acc = 0.0
    for r in range(3):
        sort(xs)
        acc += xs[r]
    print(acc)
