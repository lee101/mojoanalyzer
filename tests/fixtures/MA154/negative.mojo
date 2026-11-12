comptime V = SIMD[DType.float32, 8]


def zrow8(P: Pointer[Float32, MutUntrackedOrigin], c: Pointer[Float32, MutUntrackedOrigin], xr: Pointer[Float32, MutUntrackedOrigin], zb: Pointer[Float32, MutUntrackedOrigin], F: Int, Hp: Int):
    for j in range(0, Hp, 64):
        var z0 = c.unsafe_load[width=8](j)
        var z1 = c.unsafe_load[width=8](j + 8)
        var z2 = c.unsafe_load[width=8](j + 16)
        var z3 = c.unsafe_load[width=8](j + 24)
        var z4 = c.unsafe_load[width=8](j + 32)
        var z5 = c.unsafe_load[width=8](j + 40)
        var z6 = c.unsafe_load[width=8](j + 48)
        var z7 = c.unsafe_load[width=8](j + 56)
        for k in range(F):
            var xk = V(xr[unsafe_offset=k])
            z0 = xk.fma(P.unsafe_load[width=8](k * Hp + j), z0)
            z1 = xk.fma(P.unsafe_load[width=8](k * Hp + j + 8), z1)
            z2 = xk.fma(P.unsafe_load[width=8](k * Hp + j + 16), z2)
            z3 = xk.fma(P.unsafe_load[width=8](k * Hp + j + 24), z3)
            z4 = xk.fma(P.unsafe_load[width=8](k * Hp + j + 32), z4)
            z5 = xk.fma(P.unsafe_load[width=8](k * Hp + j + 40), z5)
            z6 = xk.fma(P.unsafe_load[width=8](k * Hp + j + 48), z6)
            z7 = xk.fma(P.unsafe_load[width=8](k * Hp + j + 56), z7)
        zb.unsafe_store[width=8](j, z0)
        zb.unsafe_store[width=8](j + 8, z1)


def single(a: Pointer[Float32, MutUntrackedOrigin], b: Pointer[Float32, MutUntrackedOrigin], n: Int) -> Float32:
    var acc = V(0)
    for i in range(0, n, 8):
        acc = a.unsafe_load[width=8](i).fma(b.unsafe_load[width=8](i), acc)
    return acc.reduce_add()
