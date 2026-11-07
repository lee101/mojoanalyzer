def taps(x: List[Float64], n: Int) -> Float64:
    var k = 3
    var acc = 0.0
    for i in range(k, n):
        for j in range(k):
            acc += x[i - j] * 0.25
    return acc


def main():
    var x = List[Float64](length=16, fill=1.0)
    print(taps(x, 16))
