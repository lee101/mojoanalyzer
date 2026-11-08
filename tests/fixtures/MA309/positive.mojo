def main():
    var seen = List[Bool](length=256, fill=False)
    seen[3] = True
    print(seen[3])
