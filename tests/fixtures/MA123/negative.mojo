from std.python import Python


def main() raises:
    var m = Python.import_module("math")
    for i in range(3):
        print(m.sqrt(Float64(i)))
