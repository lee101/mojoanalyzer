def le_int(b: List[UInt8], off: Int, n: Int) -> Int:
    var v = 0
    for i in range(n):
        v |= Int(b[off + i]) << (8 * i)
    return v


def main():
    var b = List[UInt8](length=16, fill=1)
    print(le_int(b, 0, 4), le_int(b, 4, 8))
