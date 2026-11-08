def main():
    var a = SIMD[DType.float32, 4](1.0)
    var b = SIMD[DType.float32, 4](2.0)
    print(a.max(b))
