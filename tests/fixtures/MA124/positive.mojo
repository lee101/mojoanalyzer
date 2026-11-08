def main():
    var s = 0.0
    for i in range(3):
        for j in range(4):
            s += Float64(i * j)
            print(i, j, s)
