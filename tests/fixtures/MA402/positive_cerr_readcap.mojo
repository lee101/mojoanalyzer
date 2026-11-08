def main():
    var x = 1

    def g() {read x} -> Int:
        return x

    print(g())
