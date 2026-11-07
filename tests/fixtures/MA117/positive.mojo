from max.gpu.host import DeviceContext, DeviceBuffer
from max.gpu import thread_idx, block_idx, block_dim

comptime FP = Pointer[Float32, MutAnyOrigin]


def k_scale(p: FP, n: Int32, a: Float32):
    var i = Int32(block_idx.x) * Int32(block_dim.x) + Int32(thread_idx.x)
    if i < n:
        p[Int(i)] = p[Int(i)] * a


def run(ctx: DeviceContext, n: Int) raises -> Float32:
    var host = ctx.enqueue_create_host_buffer[DType.float32](n)
    var dev = ctx.enqueue_create_buffer[DType.float32](n)
    ctx.synchronize()
    for i in range(n):
        host[i] = Float32(i)
    var p = dev.unsafe_ptr().unsafe_mut_cast[True]().unsafe_origin_cast[MutAnyOrigin]()
    ctx.enqueue_copy(dev, host)
    ctx.synchronize()
    ctx.enqueue_function[k_scale](p, Int32(n), Float32(2), grid_dim=(n + 255) // 256, block_dim=256)
    ctx.enqueue_copy(host, dev)
    ctx.synchronize()
    return host[1]


def main() raises:
    var ctx = DeviceContext()
    print(run(ctx, 1024))
