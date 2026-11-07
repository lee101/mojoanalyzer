def int_sum(a: List[Int]) -> Int:
    var s = 0
    for i in range(len(a)):
        s += a[i]
    return s


def recurrence(a: List[Float64]) -> Float64:
    var s = 0.0
    for i in range(len(a)):
        s = s * 0.5 + a[i]
    return s


def conditional(a: List[Float64]) -> Float64:
    var s = 0.0
    for i in range(len(a)):
        if a[i] > 0:
            s += a[i]
    return s


def mixed(mut y: List[Float64], a: List[Float64]) -> Float64:
    var s = 0.0
    for i in range(len(a)):
        s += a[i]
        y[i] = a[i]
    return s


def main():
    var a = List[Float64](length=64, fill=1.0)
    var y = List[Float64](length=64, fill=0.0)
    var ai = List[Int](length=64, fill=1)
    print(int_sum(ai), recurrence(a), conditional(a), mixed(y, a))
