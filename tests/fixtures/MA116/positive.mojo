def count_seen(seen: List[Int], n: Int) -> Int:
    var hits = 0
    for i in range(n):
        if i in seen:
            hits += 1
    return hits


def main():
    var seen: List[Int] = [1, 2, 3]
    print(count_seen(seen, 5))
