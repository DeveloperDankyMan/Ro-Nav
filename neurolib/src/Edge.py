import random

class Edge:
    def __init__(self, source, target, net):
        self.weight = random.random() - random.random()
        self.source = source
        self.target = target

        net.all_edges.append(self)
        source.outgoing_edges.append(self)
        target.incoming_edges.append(self)
