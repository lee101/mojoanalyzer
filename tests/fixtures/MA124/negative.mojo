def main():
    var line = String()
    for i in range(3):
        print(i)
        for j in range(4):
            if j == 3:
                print(i, j)
        for j in range(2):
            line += String(j)
            print(line)
