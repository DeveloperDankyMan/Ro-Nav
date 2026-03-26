# test_url.py
from http_module import req
import json
import random
from collections import deque
import requests
from neurolib import neuro
import time
import os
import math

# ---------------------------------------------------------
# Maze Generator
# ---------------------------------------------------------
def generate_maze(w, h):
    maze = [[1 for _ in range(w)] for _ in range(h)]

    def carve(x, y):
        maze[y][x] = 0
        dirs = [(2,0), (-2,0), (0,2), (0,-2)]
        random.shuffle(dirs)
        for dx, dy in dirs:
            nx, ny = x + dx, y + dy
            if 1 <= nx < w-1 and 1 <= ny < h-1 and maze[ny][nx] == 1:
                maze[y + dy//2][x + dx//2] = 0
                carve(nx, ny)

    carve(1, 1)
    return maze

# ---------------------------------------------------------
# Maze Solver
# ---------------------------------------------------------
def solve_maze(maze, start=(1,1), goal=None):
    h = len(maze)
    w = len(maze[0])
    if goal is None:
        goal = (w-2, h-2)

    q = deque([start])
    visited = {start: None}

    while q:
        x, y = q.popleft()
        if (x, y) == goal:
            break
        for dx, dy in [(1,0),(-1,0),(0,1),(0,-1)]:
            nx, ny = x+dx, y+dy
            if 0 <= nx < w and 0 <= ny < h and maze[ny][nx] == 0:
                if (nx, ny) not in visited:
                    visited[(nx, ny)] = (x, y)
                    q.append((nx, ny))

    path = []
    cur = goal
    while cur:
        path.append(cur)
        cur = visited.get(cur)
    path.reverse()
    return path

# ---------------------------------------------------------
# Visualization helpers
# ---------------------------------------------------------
def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def print_maze(maze, npc_pos, start, goal):
    xN, yN = npc_pos
    xS, yS = start
    xG, yG = goal

    for y in range(len(maze)):
        row = ""
        for x in range(len(maze[0])):
            if (x, y) == (xN, yN):
                row += "N"
            elif (x, y) == (xS, yS):
                row += "S"
            elif (x, y) == (xG, yG):
                row += "G"
            else:
                row += "#" if maze[y][x] == 1 else "."
        print(row)
    print()

def print_frame(maze, npc_pos, start, goal):
    clear_screen()
    print_maze(maze, npc_pos, start, goal)

# ---------------------------------------------------------
# NPC sensory inputs
# ---------------------------------------------------------
def npc_inputs(maze, pos):
    x, y = pos

    def wall(dx, dy):
        nx, ny = x+dx, y+dy
        if 0 <= nx < len(maze[0]) and 0 <= ny < len(maze):
            return 1.0 if maze[ny][nx] == 1 else 0.0
        return 1.0

    return [
        wall(0, -1),
        wall(0, 1),
        wall(-1, 0),
        wall(1, 0)
    ]

# ---------------------------------------------------------
# Interpret NN output into movement
# ---------------------------------------------------------
def decode_move(output):
    o = output[0]
    if o < 0.25: return (0, -1)
    if o < 0.50: return (0, 1)
    if o < 0.75: return (-1, 0)
    return (1, 0)

# ---------------------------------------------------------
# Fitness function with smooth animation
# ---------------------------------------------------------
def run_npc(net, maze, visualize=False, max_steps=500): #=200):
    start = (1, 1)
    goal = (len(maze[0]) - 2, len(maze) - 2)
    x, y = start

    path = solve_maze(maze, start, goal)
    best_dist = len(path)

    fitness = 0

    if visualize:
        print_frame(maze, (x, y), start, goal)
        time.sleep(0.3)

    for step in range(max_steps):
        inputs = npc_inputs(maze, (x, y))
        out = net.evaluate(inputs)
        dx, dy = decode_move(out)

        nx, ny = x + dx, y + dy

        # -------------------------------
        # WALL COLLISION → RESET TO START
        # -------------------------------
        if maze[ny][nx] == 1:
            fitness -= 50
            x, y = start  # reset NPC
            if visualize:
                print_frame(maze, (x, y), start, goal)
                print("NPC hit a wall → resetting to start...")
                time.sleep(0.3)
            continue

        # -------------------------------
        # VALID MOVE
        # -------------------------------
        x, y = nx, ny
        dist = abs(goal[0] - x) + abs(goal[1] - y)

        if dist < best_dist:
            fitness += 5
            best_dist = dist

        fitness -= 1

        if visualize:
            print_frame(maze, (x, y), start, goal)
            time.sleep(0.1)

        # -------------------------------
        # GOAL REACHED
        # -------------------------------
        if (x, y) == goal:
            fitness += 1000
            if visualize:
                print("NPC reached the goal!")
            break

    return fitness

# ---------------------------------------------------------
# Train NN using genetic algorithm
# ---------------------------------------------------------
def train_maze_escape():
    maze = generate_maze(15, 15) # generate_maze(21, 21)

    pop = neuro.new("population")

    for _ in range(20):
        net = neuro.new("network", 4, 1, 1, 4)
        pop.add_brain(net)

    for gen in range(30):
        for brain in pop.brains:
            brain.fitness = run_npc(brain, maze)

        pop.evolve()

        best = pop.get_best().fitness
        print(f"Generation {gen+1} best fitness: {best}")

    return pop.get_best(), maze

# ---------------------------------------------------------
# Run best network with visualization
# ---------------------------------------------------------
def run_best():
    best, maze = train_maze_escape()
    print("\nRunning best network with visualization:\n")
    run_npc(best, maze, visualize=True)

run_best()
