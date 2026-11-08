def dump(path: String, n: Int) raises:
    with open(path, "w") as f:
        for i in range(n):
            f.write(i, ",", i * 2, "\n")


def main() raises:
    dump("/tmp/mojoanalyzer_ma307.csv", 3)
