def rebalance(w: Float64, cash: Float64, eq: Float64) -> Bool:
    var target = cash / eq
    if w == target:
        return False
    var frac = w * 0.5
    return frac != 0.1


def main():
    print(rebalance(0.3, 1.0, 3.0))
