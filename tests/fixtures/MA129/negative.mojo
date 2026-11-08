from max.gpu.host import DeviceContext
from max.gpu import thread_idx, block_idx, block_dim

comptime FP = Pointer[Float32, MutAnyOrigin]


def k_inc(p: FP, n: Int32):
    var i = Int32(block_idx.x) * Int32(block_dim.x) + Int32(thread_idx.x)
    if i < n:
        p[unsafe_offset=Int(i)] = p[unsafe_offset=Int(i)] + 1.0


def main() raises:
    var ctx = DeviceContext()
    var n = 1024
    var dev = ctx.enqueue_create_buffer[DType.float32](n)
    var host = ctx.enqueue_create_host_buffer[DType.float32](n)
    var p = dev.unsafe_ptr().unsafe_mut_cast[True]().unsafe_origin_cast[MutAnyOrigin]()
    var acc: Float32 = 0
    for step in range(10):
        ctx.enqueue_function[k_inc](p, Int32(n), grid_dim=(n + 255) // 256, block_dim=256)
        ctx.enqueue_copy(host, dev)
        ctx.synchronize()
        acc += host[0]
    for step in range(10):
        ctx.enqueue_function[k_inc](p, Int32(n), grid_dim=(n + 255) // 256, block_dim=256)
    ctx.synchronize()
    print(acc)
