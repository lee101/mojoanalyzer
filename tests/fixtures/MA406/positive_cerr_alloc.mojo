def main():
    var p = UnsafePointer[Int].alloc(4)
    p.free()
