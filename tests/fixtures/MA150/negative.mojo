struct Sim(Movable):
    var grps: Dict[String, List[Int16]]
    var n: Int

    def lab_take(mut self, name: String) -> List[Int16]:
        return self.grps.pop(name)

    def lab_put(mut self, name: String, var g: List[Int16]):
        self.grps[name] = g^

    def count(self) -> Int:
        return self.n

    def fresh(self, name: String) -> List[Int16]:
        var g = List[Int16](length=self.n, fill=0)
        return g.copy()


def snapshot(xs: List[Int]) -> List[Int]:
    return xs.copy()
