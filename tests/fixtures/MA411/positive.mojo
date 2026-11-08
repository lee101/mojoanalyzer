def total(p: UnsafePointer[Float32, MutAnyOrigin], n: Int) -> Float32:
    var v = p.load[width=4](0)
    p.store(0, v)
    return p[1] + v[0]


def main():
    var xs = List[Float32](length=8, fill=1.0)
    var q = xs.unsafe_ptr().unsafe_mut_cast[True]().unsafe_origin_cast[MutAnyOrigin]()
    print(total(q, 8))
