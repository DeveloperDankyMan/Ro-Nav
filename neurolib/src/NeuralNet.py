from .Neuron import Neuron
from .InputNeuron import InputNeuron
from .Edge import Edge
import math

class NeuralNet:
    def __init__(self, num_inputs, num_outputs, num_hidden_layers, neurons_per_hidden):
        self.input_neurons = []
        self.hidden_neurons = []
        self.output_neurons = []
        self.all_edges = []
        self.fitness = 0

        for i in range(1, num_inputs + 1):
            self.input_neurons.append(InputNeuron(i, self))

        for _ in range(num_hidden_layers):
            for _ in range(neurons_per_hidden):
                self.hidden_neurons.append(Neuron(self))

        for _ in range(num_outputs):
            self.output_neurons.append(Neuron(self))

        # Connect input → first hidden layer
        for inp in self.input_neurons:
            for i in range(neurons_per_hidden):
                Edge(inp, self.hidden_neurons[i], self)

        # Connect hidden layers
        for layer in range(num_hidden_layers - 1):
            for n in range(neurons_per_hidden):
                src = self.hidden_neurons[layer * neurons_per_hidden + n]
                dst = self.hidden_neurons[(layer + 1) * neurons_per_hidden + n]
                Edge(src, dst, self)

        # Connect last hidden → output
        start = (num_hidden_layers - 1) * neurons_per_hidden
        for h in range(start, start + neurons_per_hidden):
            for out in self.output_neurons:
                Edge(self.hidden_neurons[h], out, self)

    def evaluate(self, inputs):
        if len(inputs) != len(self.input_neurons):
            raise ValueError(f"Expected {len(self.input_neurons)} inputs, got {len(inputs)}")

        outputs = []
        for neuron in self.output_neurons:
            neuron.clear_evaluate_cache()
            outputs.append(neuron.evaluate(inputs))

        return outputs

    def increase_fitness(self, delta=1):
        self.fitness += delta

    def reset_fitness(self):
        self.fitness = 0

    def get_weights(self):
        return [edge.weight for edge in self.all_edges]

    def get_number_of_weights(self):
        return len(self.all_edges)

    def put_weights(self, weights):
        for edge in self.all_edges:
            edge.weight = weights.pop(0)

    def propagate_error(self, examples):
        for i, neuron in enumerate(self.output_neurons):
            neuron.get_error(examples[i])

    def update_weights(self, learning_rate):
        for neuron in self.output_neurons:
            neuron.update_weights(learning_rate)
