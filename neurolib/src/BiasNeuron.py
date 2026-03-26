class BiasNeuron:
    def __init__(self):
        self.incoming_edges = []
        self.outgoing_edges = []
        self.type = "Bias"

    def clear_evaluate_cache(self):
        pass

    def evaluate(self, *_):
        return 1
