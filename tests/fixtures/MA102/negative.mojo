def prefix(mut y: List[Float64]):
    for i in range(1, len(y)):
        y[i] = y[i] + y[i - 1]


def ints(mut y: List[Int], x: List[Int]):
    for i in range(len(y)):
        y[i] = x[i] * 2


def branchy(mut y: List[Float64], x: List[Float64]):
    for i in range(len(y)):
        if x[i] > 0:
            y[i] = x[i]


def uses_index(mut y: List[Float64]):
    for i in range(len(y)):
        y[i] = Float64(i) * 0.5


def gather(mut y: List[Float64], x: List[Float64], idx: List[Int]):
    for i in range(len(y)):
        y[i] = x[idx[i]]


def tiny(mut y: List[Float64]):
    for i in range(8):
        y[i] = y[i] * 2.0


def main():
    var y = List[Float64](length=16, fill=1.0)
    var x = List[Float64](length=16, fill=1.0)
    var yi = List[Int](length=16, fill=1)
    var idx = List[Int](length=16, fill=0)
    prefix(y)
    ints(yi, yi.copy())
    branchy(y, x)
    uses_index(y)
    gather(y, x, idx)
    tiny(y)
    print(y[3], yi[3])
