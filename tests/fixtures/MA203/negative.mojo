def is_zero(x: Float64) -> Bool:
    return x == 0.0 or x == -1.0


def tie(a: List[Float64], i: Int, j: Int) -> Bool:
    return a[i] == a[j]


def changed(old: Float64, new: Float64) -> Bool:
    return old != new


def same_cfg(a: Float64, b: Float64) -> Bool:
    return abs(a * 2.0 - b) <= 1e-12


def main():
    var xs: List[Float64] = [1.0, 1.0]
    print(is_zero(0.0), tie(xs, 0, 1), changed(1.0, 2.0), same_cfg(1.0, 2.0))
