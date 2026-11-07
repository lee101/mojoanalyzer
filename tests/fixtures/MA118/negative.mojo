def le_var(b: List[UInt8], off: Int, n: Int) -> Int:
    var v = 0
    for i in range(n):
        v |= Int(b[off + i]) << (8 * i)
    return v


def pad(s: String, w: Int) -> String:
    var out = s
    if out.byte_length() < w:
        out = " " + out
    return out


def main():
    var b = List[UInt8](length=16, fill=1)
    var k = len(b) // 4
    print(le_var(b, 0, 4), le_var(b, 4, k), pad("a", 3), pad("b", 4))
