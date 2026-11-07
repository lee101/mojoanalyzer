from std.math import sqrt


def axpy(mut y: List[Float64], x: List[Float64], a: Float64):
    for i in range(len(y)):
        y[i] = y[i] + a * x[i]


def scale_shift(mut y: List[Float32], x: List[Float32], a: Float32, b: Float32):
    for i in range(len(y)):
        var t = sqrt(x[i])
        y[i] = t * a + b


def main():
    var x = List[Float64](length=64, fill=1.0)
    var y = List[Float64](length=64, fill=2.0)
    axpy(y, x, 0.5)
    var xf = List[Float32](length=64, fill=4.0)
    var yf = List[Float32](length=64, fill=0.0)
    scale_shift(yf, xf, 2.0, 1.0)
    print(y[3], yf[3])
