from std.math import sqrt
from std.time import perf_counter_ns


def main():
    print(sqrt(2.0), perf_counter_ns() > 0)
