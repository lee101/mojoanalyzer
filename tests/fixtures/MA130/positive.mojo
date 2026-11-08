from max.gpu.host import DeviceContext
from max.gpu import thread_idx, block_idx, block_dim

comptime FP = Pointer[Float32, MutAnyOrigin]


def k_rowsum(X: FP, out_: FP, n: Int32, k: Int32):
    var i = Int32(block_idx.x) * Int32(block_dim.x) + Int32(thread_idx.x)
    if i < n:
        var s: Float32 = 0
        for c in range(Int(k)):
            s += X[unsafe_offset=Int(i) * Int(k) + c]
        out_[unsafe_offset=Int(i)] = s


def main() raises:
    var ctx = DeviceContext()
    var n = 256
    var k = 16
    var xd = ctx.enqueue_create_buffer[DType.float32](n * k)
    var od = ctx.enqueue_create_buffer[DType.float32](n)
    var xp = xd.unsafe_ptr().unsafe_mut_cast[True]().unsafe_origin_cast[MutAnyOrigin]()
    var op = od.unsafe_ptr().unsafe_mut_cast[True]().unsafe_origin_cast[MutAnyOrigin]()
    ctx.enqueue_function[k_rowsum](xp, op, Int32(n), Int32(k), grid_dim=1, block_dim=256)
    ctx.synchronize()
    print(n)
