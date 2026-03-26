from .src.Neuron import Neuron
from .src.NeuralNet import NeuralNet
from .src.genetics import Genetics
from .src.population import Population


class NeuroLibrary:
    def __init__(self):
        self.classes = {
            "neuron": Neuron,
            "network": NeuralNet,
            "population": Population,
        }

        # Optional: if you later add NetworkLayer
        # "networklayer": NetworkLayer

        self.genetics = Genetics

    def new(self, class_name, *args, **kwargs):
        if not isinstance(class_name, str):
            raise TypeError("ClassName must be a string")

        key = class_name.lower()
        if key not in self.classes:
            raise ValueError(f"Could not create object type: {class_name} from neuro.")

        cls = self.classes[key]
        return cls(*args, **kwargs)


# Export a ready-to-use instance, similar to returning the table in Lua
neuro = NeuroLibrary()
