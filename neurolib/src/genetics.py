import random

class Genetics:
    settings = {
        "cross_over_rate": 0.7,
        "mutation_rate": 0.3,
        "mutation_mutex_max": 0.1
    }

    @staticmethod
    def crossover(mum, dad):
        if random.random() >= Genetics.settings["cross_over_rate"] or mum == dad:
            return mum[:], dad[:]

        if len(mum) != len(dad):
            raise ValueError("Chromosome length mismatch")

        point = random.randint(1, len(mum) - 2)

        def mix(a, b):
            return a[:point] + b[point:]

        return mix(mum, dad), mix(dad, mum)

    @staticmethod
    def mutate(chromosome):
        new = []
        for w in chromosome:
            if random.random() < Genetics.settings["mutation_rate"]:
                w += Genetics.settings["mutation_mutex_max"] * (1 - 2 * random.random())
            new.append(w)
        return new

    @staticmethod
    def meiosis(mum, dad):
        mum, dad = Genetics.crossover(mum, dad)
        return Genetics.mutate(mum), Genetics.mutate(dad)
