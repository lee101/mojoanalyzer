def main():
    comptime for i in range(3):
        print(i)
    comptime if True:
        print(1)
    var x = 1

    def g() {imm x} -> Int:
        return x

    print(g())
