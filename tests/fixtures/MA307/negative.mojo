def dump(path: String, n: Int) raises:
    var buf = String()
    for i in range(n):
        buf.write(i, ",", i * 2, "\n")
    with open(path, "w") as f:
        f.write(buf)


def many(paths: List[String]) raises:
    for p in paths:
        with open(p, "w") as f:
            f.write("x\n")


def main() raises:
    dump("/tmp/mojoanalyzer_ma307n.csv", 3)
    var ps: List[String] = ["/tmp/mojoanalyzer_ma307m.csv"]
    many(ps)
