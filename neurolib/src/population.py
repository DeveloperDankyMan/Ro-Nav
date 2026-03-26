import math
import random
from Neuro.genetics import Genetics
from Neuro.NeuralNet import NeuralNet


class Population:
    settings = {
        "kill_rate": 0.8
    }

    def __init__(self):
        self.population = 0
        self.generation = 1
        self.brains = []
        self.best_brain = None

    def add_brain(self, neural_net: NeuralNet):
        self.population += 1
        self.brains.append(neural_net)

    # ------------------------------
    # Evolution
    # ------------------------------
    def evolve(self):
        best = self.get_best()

        # Pairwise evolution
        for i in range(0, len(self.brains), 2):
            mum = self.get_chromosome()
            dad = self.get_chromosome()

            chrom1 = mum.get_weights()
            chrom2 = dad.get_weights()

            new1, new2 = Genetics.meiosis(chrom1, chrom2)

            baby1 = self.brains[i]
            baby1.put_weights(new1)

            if i + 1 < len(self.brains):
                baby2 = self.brains[i + 1]
                baby2.put_weights(new2)

        # Keep best brain intact
        self.brains[0].put_weights(best.get_weights())

        self.generation += 1

    # ------------------------------
    # Fitness helpers
    # ------------------------------
    def get_best(self):
        best = -math.inf
        best_brain = None

        for brain in self.brains:
            if brain.fitness > best:
                best = brain.fitness
                best_brain = brain

        return best_brain

    def get_worst(self):
        worst = math.inf
        worst_brain = None

        for brain in self.brains:
            if brain.fitness < worst:
                worst = brain.fitness
                worst_brain = brain

        return worst_brain

    def get_total_fitness(self):
        return sum(brain.fitness for brain in self.brains)

    def reset_fitness(self):
        for brain in self.brains:
            brain.fitness = 0

    # ------------------------------
    # Roulette‑wheel selection
    # ------------------------------
    def get_chromosome(self):
        total_fitness = self.get_total_fitness()
        pick = random.random() * total_fitness
        current = 0

        for brain in self.brains:
            current += brain.fitness
            if current >= pick:
                return brain

        return self.brains[-1]  # fallback
