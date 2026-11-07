from max.gpu.host import DeviceContext


def run(ctx: DeviceContext, n: Int) raises -> Float32:
    var host = ctx.enqueue_create_host_buffer[DType.float32](n)
    var dev = ctx.enqueue_create_buffer[DType.float32](n)
    ctx.synchronize()
    for i in range(n):
        host[i] = Float32(i)
    ctx.enqueue_copy(dev, host)
    ctx.enqueue_copy(host, dev)
    ctx.synchronize()
    return host[1]


def main() raises:
    var ctx = DeviceContext()
    print(run(ctx, 1024))
