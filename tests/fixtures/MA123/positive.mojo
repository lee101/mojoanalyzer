from std.python import Python


def main() raises:
    for i in range(3):
        var m = Python.import_module("math")
        print(m.sqrt(Float64(i)))
