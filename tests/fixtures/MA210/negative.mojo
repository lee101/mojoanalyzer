def side_name(side: Int) -> String:
    if side == 1:
        return "buy"
    elif side == -1:
        return "sell"
    if side == 1:
        return "again"
    return "flat"


def main():
    print(side_name(1))
