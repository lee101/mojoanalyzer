def total(p: Pointer[Float32, MutAnyOrigin], n: Int) -> Float32:
    var v = p.unsafe_load[width=4](0)
    p.unsafe_store(0, v)
    return p[unsafe_offset=1] + v[0]


def main():
    var xs = List[Float32](length=8, fill=1.0)
    var q = xs.unsafe_ptr().unsafe_mut_cast[True]().unsafe_origin_cast[MutAnyOrigin]()
    print(total(q, 8), xs[0])
