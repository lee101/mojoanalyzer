def index(n: Int) -> Int:
    var d = Dict[Int, Int]()
    for i in range(n):
        d[i * 31] = i
    return len(d)


def main():
    print(index(100))
