def dense(C: List[Float64], O: List[Float64], adv: List[Float64], t: Int, S: Int) -> Float64:
    var acc = 0.0
    for j in range(S):
        acc += C[t * S + j] / O[t * S + j] - adv[t * S + j]
    return acc


def one_array(bkj: List[Int32], C: List[Float64], t: Int, S: Int, n: Int) -> Float64:
    var acc = 0.0
    for q in range(n):
        var j = Int(bkj[q])
        acc += C[t * S + j] + C[(t - 1) * S + j]
    return acc


def flat(idx: List[Int], a: List[Float64], b: List[Float64], c: List[Float64], n: Int) -> Float64:
    var acc = 0.0
    for q in range(n):
        var j = idx[q]
        acc += a[j] + b[j] + c[j]
    return acc
