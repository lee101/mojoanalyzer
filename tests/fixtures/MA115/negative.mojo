from std.collections import Deque


def tail_ops(n: Int) -> Int:
    var xs = List[Int]()
    for i in range(n):
        xs.append(i)
    var s = 0
    while len(xs) > 0:
        s += xs.pop()
    return s


def once(mut xs: List[Int]):
    xs.insert(0, 7)


def deque(n: Int) raises -> Int:
    var d = Deque[Int]()
    for i in range(n):
        d.appendleft(i)
    return d.popleft()


def main() raises:
    var xs: List[Int] = [1]
    once(xs)
    print(tail_ops(3), deque(3), xs[0])
