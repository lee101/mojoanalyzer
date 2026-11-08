def main():
    var x = 1

    @parameter
    def g() -> Int:
        return x

    print(g())
