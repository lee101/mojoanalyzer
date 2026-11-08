def main():
    var a = SIMD[DType.float32, 4](1.0, 2.0, 1.0, 3.0)
    var b = SIMD[DType.float32, 4](1.0)
    var m = a.eq(b)
    var x: Float64 = 1.0
    var y: Float64 = 1.0
    var same = x == y
    if a == b:
        print("all")
    print(m, same)
