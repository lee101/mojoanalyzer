def pnl(q: Int, px: Float64) -> Float64:
    var v = Float64(q) * px
    return v
    print("fill", v)


def main():
    for i in range(3):
        if i == 1:
            continue
            print("never")
    print(pnl(2, 3.0))
