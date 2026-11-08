@export
def f(x: Int) abi("C") -> Int:
    return x + 1


def main():
    print(f(1))
