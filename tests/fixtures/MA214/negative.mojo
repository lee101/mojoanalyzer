def cancel_order(oid: Int) -> Bool:
    return oid > 0


def describe(oid: Int) -> String:
    return String(oid)


def flatten(oids: List[Int]):
    for o in oids:
        if not cancel_order(o):
            print("cancel failed", o)
        _ = describe(o)


def main():
    flatten([1, 2])
