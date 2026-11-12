struct Sim(Movable):
    var grps: Dict[String, List[Int16]]
    var names: List[String]

    def lab(mut self, name: String) -> List[Int16]:
        return self.grps[name].copy()

    def all_names(self) -> List[String]:
        return self.names.copy()


def walk(mut sm: Sim, n: Int) -> Int:
    var t = 0
    for i in range(n):
        var g = sm.lab("sic2")
        t += Int(g[i])
    return t
