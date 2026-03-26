import math
from .Edge import Edge
from .BiasNeuron import BiasNeuron

def sigmoid(x):
    return 1 / (1 + math.exp(-x))

class Neuron:
    def __init__(self, net):
        self.incoming_edges = []
        self.outgoing_edges = []
        self.type = "normal/output"

        self.incoming_edges.append(Edge(BiasNeuron(), self, net))

        self.last_output = None
        self.last_input = None
        self.error = None

    def evaluate(self, inputs):
        if self.last_output is not None:
            return self.last_output

        weighted_sum = 0
        self.last_input = []

        for edge in self.incoming_edges:
            inp = edge.source.evaluate(inputs)
            self.last_input.append(inp)
            weighted_sum += edge.weight * inp

        self.last_output = sigmoid(weighted_sum)
        return self.last_output

    def get_error(self, example):
        if self.last_output is None:
            raise RuntimeError("Neuron tried to get error with no last output!")

        if len(self.outgoing_edges) == 0:
            self.error = example - self.last_output
        else:
            self.error = 0
            for edge in self.outgoing_edges:
                self.error += edge.weight * edge.target.get_error(example)

        return self.error

    def update_weights(self, learning_rate):
        if self.error is not None and self.last_output is not None:
            for i, edge in enumerate(self.incoming_edges):
                delta = learning_rate * self.last_output * (1 - self.last_output) * self.error * self.last_input[i]
                edge.weight += delta

            for edge in self.outgoing_edges:
                edge.target.update_weights(learning_rate)

            self.error = None
            self.last_output = None
            self.last_input = None

    def clear_evaluate_cache(self):
        if self.last_output is not None:
            self.last_output = None
            for edge in self.incoming_edges:
                edge.source.clear_evaluate_cache()
