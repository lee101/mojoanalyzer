def cancel_order(oid: Int) -> Bool:
    return oid > 0


def flatten(oids: List[Int]):
    for o in oids:
        _ = cancel_order(o)


def main():
    flatten([1, 2])
