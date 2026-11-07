from std.collections import Set


def count_set(seen: Set[Int], n: Int) -> Int:
    var hits = 0
    for i in range(n):
        if i in seen:
            hits += 1
    return hits


def small_literal(n: Int) -> Int:
    var keep: List[Int] = [2, 3]
    var hits = 0
    for i in range(n):
        if i in keep:
            hits += 1
    return hits


def once(seen: List[Int]) -> Bool:
    return 3 in seen


def main():
    var s = Set[Int]()
    s.add(1)
    var l: List[Int] = [3]
    print(count_set(s, 3), small_literal(4), once(l))
