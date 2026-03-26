from .Neuron import Neuron

class NeuronLayer:
    def __init__(self, num_neurons, num_inputs_per_neuron):
        self.num_neurons = num_neurons
        self.num_inputs_per_neuron = num_inputs_per_neuron
        self.neurons = [Neuron(num_inputs_per_neuron) for _ in range(num_neurons)]
