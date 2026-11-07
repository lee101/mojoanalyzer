def rets(px: List[Float64]) -> List[Float64]:
    var r = List[Float64](length=len(px), fill=0.0)
    for i in range(1, len(px)):
        r[i] = px[i] / px[i - 1] - 1.0
    return r^


def guarded(px: List[Float64]) -> Float64:
    var s = 0.0
    for i in range(len(px)):
        if i == 0:
            continue
        s += px[i] - px[i - 1]
    return s


def fwd(px: List[Float64]) -> Float64:
    var s = 0.0
    for i in range(len(px) - 1):
        s += px[i + 1] - px[i]
    return s


def main():
    var px: List[Float64] = [1.0, 2.0, 3.0]
    print(rets(px)[1], guarded(px), fwd(px))
