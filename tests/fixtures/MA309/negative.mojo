def flags(n: Int) -> Bool:
    var seen = List[Bool](length=n, fill=False)
    var few = List[Bool](length=16, fill=False)
    return len(seen) > 0 and not few[0]


def main():
    print(flags(300))
