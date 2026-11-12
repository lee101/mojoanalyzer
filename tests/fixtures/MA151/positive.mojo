def book(bk0: List[Int], bkj: List[Int32], C: List[Float64], O: List[Float64], adv: List[Float64], px: List[Float32], t: Int, S: Int, k: Int) -> Float64:
    var acc = 0.0
    for q in range(bk0[k], bk0[k + 1]):
        var j = Int(bkj[q])
        var c1 = C[(t - 1) * S + j]
        var o = O[t * S + j]
        acc += (C[t * S + j] / o - 1.0) * Float64(px[t * S + j]) / c1 - adv[t * S + j]
    return acc
