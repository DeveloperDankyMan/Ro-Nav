from .Edge import Edge
from .BiasNeuron import BiasNeuron

class InputNeuron:
    def __init__(self, index, net):
        self.index = index
        self.incoming_edges = []
        self.outgoing_edges = []
        self.type = "Input"

        # Add bias edge
        self.incoming_edges.append(Edge(BiasNeuron(), self, net))

        self.last_output = None

    def evaluate(self, inputs):
        self.last_output = inputs[self.index - 1]
        return self.last_output

    def get_error(self, example):
        for edge in self.outgoing_edges:
            edge.target.get_error(example)

    def update_weights(self, learning_rate):
        for edge in self.outgoing_edges:
            edge.target.update_weights(learning_rate)

    def clear_evaluate_cache(self):
        self.last_output = None
