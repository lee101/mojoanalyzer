comptime V = SIMD[DType.float32, 8]


def zrow(P: Pointer[Float32, MutUntrackedOrigin], c: Pointer[Float32, MutUntrackedOrigin], xr: Pointer[Float32, MutUntrackedOrigin], zb: Pointer[Float32, MutUntrackedOrigin], F: Int, Hp: Int):
    for j in range(0, Hp, 32):
        var z0 = c.unsafe_load[width=8](j)
        var z1 = c.unsafe_load[width=8](j + 8)
        var z2 = c.unsafe_load[width=8](j + 16)
        var z3 = c.unsafe_load[width=8](j + 24)
        for k in range(F):
            var xk = V(xr[unsafe_offset=k])
            z0 = xk.fma(P.unsafe_load[width=8](k * Hp + j), z0)
            z1 = xk.fma(P.unsafe_load[width=8](k * Hp + j + 8), z1)
            z2 = xk.fma(P.unsafe_load[width=8](k * Hp + j + 16), z2)
            z3 = xk.fma(P.unsafe_load[width=8](k * Hp + j + 24), z3)
        zb.unsafe_store[width=8](j, z0)
        zb.unsafe_store[width=8](j + 8, z1)
        zb.unsafe_store[width=8](j + 16, z2)
        zb.unsafe_store[width=8](j + 24, z3)
