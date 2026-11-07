def pnl(q: Int, px: Float64) -> Float64:
    var v = Float64(q) * px
    if v > 0:
        return v
    else:
        print("neg")
    return -v


def main():
    print(pnl(2, 3.0))
