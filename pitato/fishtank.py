"""Apps' Fish Tank: a tank with your Pietato's own fish in it, plants swaying, bubbles rising, food to drop in.

Your Pietatos' tanks (each one on your network, with Settings > Share with other Pietatos on) join up into one big
tank, a grid of them: side by side, and above and below each other, as the web page's Fish Tank arranges them (in a
row by name, till then). The water's surface is along the top of the grid, the sand along its bottom, and each
Pietato's fish swims through all of it: off one's screen and onto the next. Each Pietato moves its own fish (always,
whether its tank's on its screen or not), and tells the others where it is a few times a second (screens/fishtank.py);
each draws whichever fish are in its own tank, and the web page draws them all.

The grid's cells are 1 x 1 (across and down, whatever a screen's shape): places are in cells, (0, 0) the grid's top
left. A fish is as long as a share of its cell's height, so it's as big on each screen, for its size."""
import math
import random

from .sims import Sim

FISH_KINDS = ("Goldfish", "Clownfish", "Betta", "Angelfish", "Neon tetra")
FISH_LENGTH = 0.17           # a fish: as long as this much of a cell's height
FISH_CRUISE = 0.17           # ...swimming along at this many cells a second
FISH_HUNGRY = 0.34           # ...and to food at this
FISH_EASE = 1.6              # how quickly it comes round to where it's going
FISH_AWAY = 0.45             # a new place to swim to: in another of the tanks, this often
FISH_TURN = 0.45             # seconds a fish takes to turn round
FISH_WAGS = 6                # its tail's pictures, one after another
FISH_TILTS = (-20, -10, 0, 10, 20)   # degrees it leans, swimming up or down
EDGE_X = 0.08                # a fish keeps this far from a cell's side with no tank beyond it
TOP, BOTTOM = 0.13, 0.8      # ...and between these, in a cell with no tank above it (the surface) or below (the sand)
SAND = 0.86                  # a bottom cell's sand starts this far down
FLOOR = SAND + 0.02          # ...food that sinks to it lies this far down
NIBBLE = SAND - 0.02         # ...and a hungry fish swims down to this, for it
FOOD_FLAKES = 6              # a feed: this many flakes
FOOD_SINK = 0.05             # cells a second
FOOD_STAYS = 25.0            # seconds a flake on the sand stays before it's gone
FOOD_REACH = 0.05            # a fish's mouth this near a flake eats it
MOUTH = 0.055                # ...its mouth: this far in front of its middle (in cells)
TURN_AGAIN = 1.2             # seconds before it turns round again, at least
FOOD_MOST = 18               # flakes one Pietato has in the water, at most
BUBBLE_EVERY = 0.35          # seconds between an air stone's bubbles (a little more or less)
BUBBLE_RISE = 0.22           # cells a second
REMOTE_EASE = 8.0            # another's fish, drawn easing to where it says it is
REMOTE_AHEAD = 0.5           # ...and guessed on from what it said, this long at most
GRID_MOST = 6                # cells across or down, at most

# each kind: (body, belly, fins (with their see-through), its height for its length, what's special)
LOOKS = {
    "Goldfish": ((246, 138, 38), (255, 196, 96), (255, 162, 64, 190), 0.44, "fan"),
    "Clownfish": ((246, 112, 30), (255, 160, 70), (246, 112, 30, 235), 0.42, "bands"),
    "Betta": ((64, 92, 222), (110, 140, 240), (132, 72, 214, 175), 0.36, "veil"),
    "Angelfish": ((214, 220, 226), (240, 242, 244), (200, 208, 216, 210), 0.86, "angel"),
    "Neon tetra": ((150, 166, 180), (196, 204, 212), (176, 190, 204, 150), 0.3, "neon"),
}
WATER = {"Day": ((58, 156, 200), (10, 52, 96)), "Night": ((22, 56, 92), (4, 14, 30))}   # (top, bottom)
SAND_COLOURS = {"Day": ((214, 192, 146), (168, 140, 96)), "Night": ((84, 82, 78), (52, 50, 48))}


def fish_default(name):
    """A fish of its own for each Pietato, by its name (START's Fish changes it)."""
    return FISH_KINDS[sum(map(ord, name or "")) % len(FISH_KINDS)]


def mix(a, b, t):
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def hash32(k, s):
    """A number in [0, 1) from two whole numbers, the same every time (and in the web page's own drawing)."""
    x = ((k & 0xFFFFFFFF) * 2654435761 ^ (s & 0xFFFFFFFF) * 2246822519) & 0xFFFFFFFF
    x ^= x >> 15
    x = (x * 2246822507) & 0xFFFFFFFF
    x ^= x >> 13
    x = (x * 3266489909) & 0xFFFFFFFF
    x ^= x >> 16
    return x / 4294967296


def name_seed(name):
    h = 0
    for ch in name or "":
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h


# ---- the grid --------------------------------------------------------------------------------------------------
def place(names, stored):
    """Where each tank is: {its name: (column, row)}, from the grid you arranged (stored: {name: [c, r]}), the rest
    after them along the top row, in order of name; the whole of it from (0, 0). The same on each of them."""
    names = sorted(set(n for n in names if n), key=lambda n: (n.lower(), n))
    cells, taken = {}, set()
    for n in names:
        at = (stored or {}).get(n)
        if (isinstance(at, (list, tuple)) and len(at) == 2 and all(isinstance(v, int) and not isinstance(v, bool)
                                                                   for v in at)):
            at = (at[0], at[1])
            if at not in taken and all(-GRID_MOST < v < 2 * GRID_MOST for v in at):
                cells[n] = at
                taken.add(at)
    c = 0
    for n in names:
        if n in cells:
            continue
        while (c, 0) in taken:
            c += 1
        cells[n] = (c, 0)
        taken.add((c, 0))
    if cells:
        c0 = min(c for c, _ in cells.values())
        r0 = min(r for _, r in cells.values())
        cells = {n: (c - c0, r - r0) for n, (c, r) in cells.items()}
    return cells


class Grid:
    """The tanks joined up: who's where, and what's next to what."""

    def __init__(self, cells):
        self.cells = dict(cells)                      # name -> (c, r)
        self.at = {v: n for n, v in self.cells.items()}
        self.cols = max((c for c, _ in self.cells.values()), default=0) + 1
        self.rows = max((r for _, r in self.cells.values()), default=0) + 1

    def has(self, c, r):
        return (c, r) in self.at

    def cell_of(self, x, y):
        return int(math.floor(x)), int(math.floor(y))

    def box(self, c, r, low=False):
        """Where a fish can be in a cell: (x0, x1, y0, y1), kept from its sides with no tank beyond them (low: a
        hungry one, down to the food on the sand)."""
        return (c + (0 if self.has(c - 1, r) else EDGE_X), c + 1 - (0 if self.has(c + 1, r) else EDGE_X),
                r + (0 if self.has(c, r - 1) else TOP),
                r + 1 - (0 if self.has(c, r + 1) else 1 - (NIBBLE if low else BOTTOM)))

    def top_of(self, c, r):
        """The water's surface over a cell: the top of the topmost tank in an unbroken run above it."""
        while self.has(c, r - 1):
            r -= 1
        return r

    def bottom_of(self, c, r):
        while self.has(c, r + 1):
            r += 1
        return r

    def path(self, a, b):
        """The cells from a to b, a step at a time (each next to the last): [a, ..., b], or [] when there's no way."""
        if a == b:
            return [a]
        seen, todo = {a: None}, [a]
        while todo:
            cur = todo.pop(0)
            for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nb = (cur[0] + dc, cur[1] + dr)
                if nb in seen or not self.has(*nb):
                    continue
                seen[nb] = cur
                if nb == b:
                    out = [b]
                    while out[-1] != a:
                        out.append(seen[out[-1]])
                    return out[::-1]
                todo.append(nb)
        return []

    def move(self, x, y, dx, dy, low=False):
        """(x, y) moved by (dx, dy), but not through a side with no tank beyond it: across first, then down (low: a
        hungry fish, down to the sand; one that's there already comes up from it as it swims, not at once)."""
        c, r = self.cell_of(x, y)
        if not self.has(c, r):                        # (somewhere that's gone: as it is, for it to be put back)
            return x + dx, y + dy
        nx = x + dx
        nc = int(math.floor(nx))
        if nc != c and not self.has(nc, r):
            nc = c
        x0, x1, _, _ = self.box(nc, r)
        nx = min(max(nx, x0), x1 - 1e-6)
        ny = y + dy
        nr = int(math.floor(ny))
        if nr != r and not self.has(nc, nr):
            nr = r
        _, _, y0, y1 = self.box(nc, nr, low)
        if not low and nr == r:
            y1 = max(y1, min(y + 1e-6, self.box(nc, nr, True)[3]))   # (no further down, though)
        return nx, min(max(ny, y0), y1 - 1e-6)


def stone_bubbles(sx, sy, seed, top, t):
    """An air stone's bubbles now (t: by the clock), from one at (sx, sy), up to the surface at top: [(x, y, r)]. The
    web page works them out the same way, so they're where they are on the screen too, more or less."""
    out = []
    most = (sy - top) / BUBBLE_RISE
    k = int(t // BUBBLE_EVERY)
    for i in range(k - int(most / BUBBLE_EVERY) - 2, k + 1):
        born = i * BUBBLE_EVERY + hash32(i, seed) * BUBBLE_EVERY * 0.6
        age = t - born
        if not 0 <= age <= most:
            continue
        y = sy - BUBBLE_RISE * age
        if y <= top + 0.03:
            continue
        x = sx + 0.012 * math.sin(age * 3.1 + i)
        out.append((x, y, (0.007 + 0.009 * hash32(i, seed + 7)) * (1 + 0.6 * age / max(most, 0.1))))
    return out


# ---- your Pietatos' fish, together ----------------------------------------------------------------------------
class Aquarium:
    """The big tank as this Pietato knows it, and its own fish, food and decorations. me: its name. Others' tanks:
    heard() as they tell it (screens/fishtank.py); tick() moves its own fish on (media mode's main loop, always)."""

    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.me = ""
        self.kind = FISH_KINDS[0]
        self.light = "Day"
        self.bubbles_on = True
        self.seed = self.rng.randrange(1 << 30)
        self.stored = {}             # the grid you arranged: {name: [c, r]}, and when ("t")
        self.stored_t = 0.0
        self.others = {}             # another's id -> {"name", "accent", "fish", "food", "ate", "decor", "at"}
        self.grid = Grid({})
        self.fish = None             # yours: {"x", "y", "vx", "vy", "face", "turn", "wag", "goal", "via", "rest"}
        self.food = []               # flakes you dropped: {"id", "x", "y", "down"}
        self.eaten = {}              # (whose flake, its id) -> when your fish ate it
        self.fed = 0
        self.clock = 0.0
        self.shown = {}              # another's fish, as it's drawn here: id -> [x, y, face, wag, turn]
        self.followed = 0.0          # ...when they were last moved on (monotonic)
        self.home_now = False        # (A: called home)
        self.ate_new = False         # (its fish ate another's food just now: to be told at once)

    # -- who's there ---------------------------------------------------------------------------------------------
    def tanks(self):
        """{name: its id or None for this one} of the tanks joined up."""
        out = {self.me: None}
        for oid, o in self.others.items():
            if o["name"] and o["name"] not in out:
                out[o["name"]] = oid
        return out

    def regrid(self):
        """The grid again (one come or gone, the arrangement changed); your fish and food kept where they are in
        their own cells, or brought back into yours."""
        old = self.grid
        new = Grid(place(self.tanks(), self.stored))
        if new.cells == old.cells:
            return
        self.grid = new
        for thing in [self.fish] + self.food:
            if thing is None:
                continue
            c, r = old.cell_of(thing["x"], thing["y"])
            name = old.at.get((c, r))
            if name in new.cells:
                nc, nr = new.cells[name]
                thing["x"] += nc - c
                thing["y"] += nr - r
            elif thing is self.fish:
                self.fish = None                     # (its tank's gone: home it comes)
            else:
                thing["gone"] = True
        self.food = [f for f in self.food if not f.get("gone")]
        if self.fish is not None:
            self.fish["goal"], self.fish["via"] = None, None
        self.shown.clear()

    def mine(self):
        return self.grid.cells.get(self.me, (0, 0))

    def come_home(self, side=0):
        c, r = self.mine()
        x0, x1, y0, y1 = self.grid.box(c, r)
        x = (x0 + x1) / 2 if not side else (x1 - 0.05 if side > 0 else x0 + 0.05)
        self.fish = {"x": x, "y": r + 0.45, "vx": 0.0, "vy": 0.0, "face": -1 if side > 0 else 1, "turn": 0.0,
                     "wag": 0.0, "goal": None, "via": None, "rest": 1.0}

    def call(self):
        """A: your fish swims back to this tank."""
        if self.fish is None:
            self.come_home()
        c, r = self.mine()
        x0, x1, y0, y1 = self.grid.box(c, r)
        self.fish["goal"] = ((x0 + x1) / 2, (y0 + y1) / 2)
        self.fish["via"], self.fish["rest"] = None, 0.0

    # -- time goes on ---------------------------------------------------------------------------------------------
    def tick(self, dt):
        if dt <= 0:
            return
        self.clock += dt
        self.regrid()
        if self.fish is None:
            self.come_home()
        self.sink(dt)
        self.swim(dt)

    def sink(self, dt):
        """The food sinks, a little this way and that, to the sand under it, and lies there a while."""
        g = self.grid
        eaten = set()
        for o in self.others.values():
            eaten |= {fid for whose, fid in o.get("ate") or () if whose == self.me}
        keep = []
        for fl in self.food:
            if fl["id"] in eaten:
                continue
            if fl["down"] is None:
                c, r = g.cell_of(fl["x"], fl["y"])
                floor = g.bottom_of(c, r) + FLOOR
                fl["y"] = min(fl["y"] + FOOD_SINK * dt, floor)
                fl["x"] += math.sin(self.clock * 1.7 + fl["id"]) * 0.02 * dt
                if fl["y"] >= floor:
                    fl["down"] = self.clock
            if fl["down"] is None or self.clock - fl["down"] < FOOD_STAYS:
                keep.append(fl)
        self.food = keep
        for k, at in list(self.eaten.items()):
            if self.clock - at > 6:
                del self.eaten[k]

    def flakes(self):
        """Every flake in the water: [(x, y, whose: None for yours, its id)]."""
        out = [(fl["x"], fl["y"], None, fl["id"]) for fl in self.food]
        for oid, o in self.others.items():
            for fid, name, u, v in o.get("food") or ():
                if name in self.grid.cells and (o["name"], fid) not in self.eaten:
                    c, r = self.grid.cells[name]
                    out.append((c + u, r + v, o["name"], fid))
        return out

    def feed(self, name=None, n=FOOD_FLAKES):
        """A pinch of food, sprinkled in at the top of a tank (yours, or another's by its name). False: no such tank."""
        name = name or self.me
        if name not in self.grid.cells:
            return False
        c, r = self.grid.cells[name]
        x0, x1, y0, _ = self.grid.box(c, r)
        for _ in range(n):
            self.food.append({"id": self.rng.randrange(1 << 20), "x": self.rng.uniform(x0 + 0.08, x1 - 0.08),
                              "y": r + self.rng.uniform(0.04, 0.09), "down": None})
        self.food = self.food[-FOOD_MOST:]
        if self.fish is not None:
            self.fish["rest"] = 0.0
        return True

    def goal_new(self):
        """Somewhere new to swim to: in the tank it's in mostly, now and then another it can get to."""
        f, g, rng = self.fish, self.grid, self.rng
        here = g.cell_of(f["x"], f["y"])
        there = here
        if len(g.cells) > 1 and rng.random() < FISH_AWAY:
            there = rng.choice([v for v in g.cells.values() if v != here])
        x0, x1, y0, y1 = g.box(*there)
        f["goal"] = (rng.uniform(x0 + 0.05, max(x0 + 0.06, x1 - 0.05)), rng.uniform(y0 + 0.04, max(y0 + 0.05, y1 - 0.04)))
        f["via"] = None

    def waypoint(self, goal):
        """Where to head for next on the way to goal: into the next cell on the way (around any gap in the grid)."""
        f, g = self.fish, self.grid
        here = g.cell_of(f["x"], f["y"])
        there = g.cell_of(*goal)
        if here == there:
            return goal
        way = g.path(here, there)
        if len(way) < 2:
            return None
        (c, r), (nc, nr) = way[0], way[1]
        x0, x1, y0, y1 = g.box(nc, nr)
        if nc != c:                                   # (across: in at the side, at a height both have)
            _, _, a0, a1 = g.box(c, r)
            y = min(max(f["y"] - r + nr, max(y0, a0 + nr - r) + 0.02), min(y1, a1 + nr - r) - 0.02)
            return (nc + 0.12 if nc > c else nc + 0.88, y)
        bx0, bx1, _, _ = g.box(c, r)
        x = min(max(f["x"], max(x0, bx0) + 0.04), min(x1, bx1) - 0.04)
        return (x, nr + 0.15 if nr > r else nr + 0.85)

    def swim(self, dt):
        """Your fish: to where it's going (food first), easing round, its tail going as fast as it swims."""
        f, g = self.fish, self.grid
        food = self.flakes()
        target, hungry = None, False
        if food:
            mx = f["x"] + f["face"] * MOUTH           # (its mouth, in front of it)
            fx, fy, whose, fid = min(food, key=lambda p: (p[0] - mx) ** 2 + (p[1] - f["y"]) ** 2)
            if (fx - mx) ** 2 + (fy - f["y"]) ** 2 < 2.2 ** 2 and g.path(g.cell_of(f["x"], f["y"]),
                                                                          g.cell_of(fx, fy)):
                hungry = True
                if (fx - mx) ** 2 + (fy - f["y"]) ** 2 < FOOD_REACH ** 2:
                    self.fed += 1
                    if whose is None:
                        self.food = [fl for fl in self.food if fl["id"] != fid]
                    else:
                        self.eaten[(whose, fid)] = self.clock
                        self.ate_new = True           # (the one that dropped it told at once)
                else:                                 # (its mouth to it: from the side it's on, facing it)
                    side = 1 if fx >= f["x"] else -1
                    target = self.waypoint((fx - side * MOUTH, fy))
                    if (f["face"] != side and f["turn"] <= 0
                            and self.clock - f.get("turned", -TURN_AGAIN) >= TURN_AGAIN):
                        f["turn"], f["turned"] = FISH_TURN, self.clock
        if not hungry:
            if f["goal"] is None:
                self.goal_new()
            target = self.waypoint(f["goal"])
            if target is None:
                f["goal"] = None
        want_x = want_y = 0.0
        if f["rest"] > 0 and not hungry:
            f["rest"] -= dt
            want_y = math.sin(self.clock * 1.3) * 0.02
        elif target is not None:
            dx, dy = target[0] - f["x"], target[1] - f["y"]
            dist = math.hypot(dx, dy)
            if dist < 0.05 and not hungry and target == f["goal"]:
                f["rest"] = self.rng.uniform(0.6, 3.0)
                f["goal"] = None
            elif dist > 1e-6:
                speed = (FISH_HUNGRY if hungry else FISH_CRUISE) * min(1.0, dist / 0.25 + 0.3)
                want_x, want_y = dx / dist * speed, dy / dist * speed * 0.75
        k = min(1.0, dt * FISH_EASE)
        f["vx"] += (want_x - f["vx"]) * k
        f["vy"] += (want_y - f["vy"]) * k
        f["x"], f["y"] = g.move(f["x"], f["y"], f["vx"] * dt, f["vy"] * dt, hungry)
        if (not hungry and abs(f["vx"]) > 0.05 and (f["vx"] > 0) != (f["face"] > 0) and f["turn"] <= 0
                and self.clock - f.get("turned", -TURN_AGAIN) >= TURN_AGAIN):
            f["turn"], f["turned"] = FISH_TURN, self.clock   # (round it turns: not back and forth)
        if f["turn"] > 0:
            was = f["turn"]
            f["turn"] -= dt
            if f["turn"] <= FISH_TURN / 2 < was:
                f["face"] = -f["face"]
        f["wag"] += dt * (2.5 + 9 * math.hypot(f["vx"], f["vy"]))

    # -- what it tells the others, and hears from them -----------------------------------------------------------------
    def decor(self):
        """This tank's plants, rocks and air stone (where, how big), from its seed: drawn the same everywhere."""
        key = (self.seed, self.bubbles_on, self.light)
        if getattr(self, "decor_was", (None,))[0] == key:
            return self.decor_was[1]
        rnd = random.Random(self.seed)
        plants = [[round(rnd.uniform(0.05, 0.95), 3), round(rnd.uniform(0.25, 0.48), 3), round(rnd.uniform(0.014, 0.025), 4),
                   round(rnd.uniform(0, 6.3), 2), "#%02x%02x%02x" % mix((52, 150, 76), (96, 176, 72), rnd.random()),
                   rnd.random() < 0.35] for _ in range(rnd.randint(4, 6))]
        rocks = [[round(rnd.uniform(0.08, 0.92), 3), round(rnd.uniform(0.04, 0.085), 3), round(rnd.uniform(0.6, 1.0), 2)]
                 for _ in range(rnd.randint(2, 3))]
        stone = round(rnd.uniform(0.15, 0.85), 3) if self.bubbles_on else None
        self.decor_was = (key, {"plants": plants, "rocks": rocks, "stone": stone, "light": self.light})
        return self.decor_was[1]

    def local(self, x, y):
        """(a tank's name, where in it) for a place in the grid: what the others understand, whatever their grid."""
        c, r = self.grid.cell_of(x, y)
        return self.grid.at.get((c, r)), x - c, y - r

    def wire(self):
        """What this one tells the others: its fish (in which tank, where), its food, what its fish ate of theirs,
        its decorations, the grid as you last arranged it."""
        f = self.fish
        out = {"decor": self.decor(), "grid": {"t": self.stored_t, "cells": self.stored},
               "food": [], "ate": [[whose, fid] for whose, fid in self.eaten]}
        if f is not None:
            name, u, v = self.local(f["x"], f["y"])
            out["fish"] = {"tank": name, "u": round(u, 4), "v": round(v, 4), "vx": round(f["vx"], 4),
                           "vy": round(f["vy"], 4), "face": f["face"], "kind": self.kind}
        for fl in self.food[:FOOD_MOST]:
            name, u, v = self.local(fl["x"], fl["y"])
            if name:
                out["food"].append([fl["id"], name, round(u, 3), round(v, 3)])
        return out

    def arrange(self, cells, t):
        """The grid as you arranged it (here, or on another, at t): the latest kept."""
        if t <= self.stored_t:
            return False
        self.stored = {n: [int(c), int(r)] for n, (c, r) in cells.items()}
        self.stored_t = t
        return True

    # -- where things are drawn ---------------------------------------------------------------------------------------
    def follow(self, now):
        """The others' fish: drawn easing to where they say they are (and on from there a moment, as they swim).
        now: time.monotonic() (asked by the screen and the web page both: moved on once for the time gone by)."""
        dt = min(0.5, now - self.followed) if self.followed else 0.0
        self.followed = now
        if dt <= 0:
            return
        k = min(1.0, dt * REMOTE_EASE)
        seen = set()
        for oid, o in self.others.items():
            g = o.get("fish")
            if not g or g.get("tank") not in self.grid.cells:
                continue
            c, r = self.grid.cells[g["tank"]]
            ahead = min(REMOTE_AHEAD, max(0.0, o.get("age", 0.0)))
            tx, ty = c + g["u"] + g["vx"] * ahead, r + g["v"] + g["vy"] * ahead
            s = self.shown.get(oid)
            if s is None or abs(s[0] - tx) + abs(s[1] - ty) > 0.8:   # (new, or it jumped: there at once)
                s = self.shown[oid] = [tx, ty, g["face"], 0.0, 0.0]
            s[0] += (tx - s[0]) * k
            s[1] += (ty - s[1]) * k
            if g["face"] != s[2] and s[4] <= 0:
                s[4] = FISH_TURN
            if s[4] > 0:
                was = s[4]
                s[4] -= dt
                if s[4] <= FISH_TURN / 2 < was:
                    s[2] = g["face"]
            s[3] += dt * (2.5 + 9 * math.hypot(g["vx"], g["vy"]))
            seen.add(oid)
        for oid in list(self.shown):
            if oid not in seen:
                del self.shown[oid]

    def everyone(self):
        """Each fish as it's drawn: [(x, y, facing, tail, turning (0 to 1), kind, whose name, its id, vx, vy)]."""
        out = []
        f = self.fish
        if f is not None:
            out.append((f["x"], f["y"], f["face"], f["wag"], max(0.0, f["turn"]) / FISH_TURN, self.kind, self.me,
                        None, f["vx"], f["vy"]))
        for oid, o in self.others.items():
            g, s = o.get("fish") or {}, self.shown.get(oid)
            if s is None:                             # (not followed yet: where it says it is)
                if g.get("tank") not in self.grid.cells:
                    continue
                c, r = self.grid.cells[g["tank"]]
                s = (c + g["u"], r + g["v"], g["face"], 0.0, 0.0)
            out.append((s[0], s[1], s[2], s[3], max(0.0, s[4]) / FISH_TURN, g.get("kind"), o.get("name") or "", oid,
                        g.get("vx", 0.0), g.get("vy", 0.0)))
        return out

    def stones(self):
        """Each air stone in the grid: (x, y, its seed, the surface over it)."""
        out = []
        for name, (c, r) in self.grid.cells.items():
            if self.grid.has(c, r + 1):
                continue
            d = self.decor() if name == self.me else next((o.get("decor") for o in self.others.values()
                                                           if o["name"] == name), None) or {}
            if d.get("stone") is not None:
                out.append((c + d["stone"], r + SAND - 0.01, name_seed(name), self.grid.top_of(c, r)))
        return out

    def snapshot(self, now):
        """Everything, for the web page's Fish Tank: the grid, each tank's look, every fish, the food."""
        tanks = []
        for name, (c, r) in sorted(self.grid.cells.items()):
            o = next((o for o in self.others.values() if o["name"] == name), None)
            tanks.append({"name": name, "c": c, "r": r, "me": name == self.me,
                          "accent": (o or {}).get("accent", "") if name != self.me else self.accent,
                          "decor": self.decor() if name == self.me else (o or {}).get("decor") or {}})
        fish = [{"name": who, "kind": kind if kind in LOOKS else FISH_KINDS[0], "x": round(x, 4), "y": round(y, 4),
                 "vx": round(vx, 4), "vy": round(vy, 4), "face": face}
                for x, y, face, _, _, kind, who, _, vx, vy in self.everyone()]
        return {"t": now, "me": self.me, "cols": self.grid.cols, "rows": self.grid.rows, "tanks": tanks,
                "fish": fish, "food": [[round(x, 3), round(y, 3)] for x, y, _, _ in self.flakes()],
                "arranged": self.stored_t}

    accent = ""


# ---- a fish's picture ----------------------------------------------------------------------------------------------
def fish_picture(kind, length, wag):
    """A fish facing right, length px long (its middle in the picture's middle), its tail at wag (-1 to 1): drawn
    four times bigger and shrunk, for smooth edges. RGBA."""
    from PIL import Image, ImageChops, ImageDraw, ImageFilter
    body, belly, fins, tall, style = LOOKS.get(kind, LOOKS["Goldfish"])
    K = 4
    L = length * K
    W, H = int(length * 1.5) * K, int(length * max(1.0, tall * (2.05 if style == "angel" else 1.7))) * K
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fin_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d, f = ImageDraw.Draw(img), ImageDraw.Draw(fin_layer)
    cx, cy = W / 2, H / 2

    def P(x, y):
        return cx + x * L, cy + y * L

    hh = tall / 2                                     # half the body's height
    nose, rear = 0.42, -0.26                          # where the body ends, front and back
    tail_root = rear - 0.06
    swing = wag * 0.12
    if style in ("fan", "veil"):                      # the tail, swinging
        long = 0.42 if style == "veil" else 0.3
        spread = 0.36 if style == "veil" else 0.26
        tip_x = tail_root - long
        f.polygon([P(tail_root + 0.04, -0.05), P(tip_x + 0.05, -spread + swing), P(tip_x, -spread * 0.4 + swing),
                   P(tip_x + 0.08, swing), P(tip_x, spread * 0.4 + swing), P(tip_x + 0.05, spread + swing),
                   P(tail_root + 0.04, 0.05)], fill=fins)
        for k in (-0.6, -0.2, 0.2, 0.6):              # (its rays)
            f.line((P(tail_root, 0), P(tip_x + 0.06, k * spread + swing)), fill=mix(fins[:3], (90, 40, 10), 0.25)
                   + (110,), width=max(1, int(L * 0.008)))
    elif style == "angel":
        tip_x = tail_root - 0.2
        f.polygon([P(tail_root + 0.03, -0.04), P(tip_x, -0.2 + swing), P(tip_x + 0.05, swing),
                   P(tip_x, 0.2 + swing), P(tail_root + 0.03, 0.04)], fill=fins)
    else:                                             # (a forked little tail)
        tip_x = tail_root - 0.2
        f.polygon([P(tail_root + 0.03, -0.03), P(tip_x, -0.16 + swing), P(tip_x + 0.07, swing),
                   P(tip_x, 0.16 + swing), P(tail_root + 0.03, 0.03)],
                  fill=(230, 46, 64, 220) if style == "neon" else fins)
    if style == "angel":                              # its fins: on its back, under it
        f.polygon([P(0.05, -hh * 0.8), P(-0.12, -hh * 1.9), P(-0.2, -hh * 1.85), P(-0.22, -hh * 0.4)], fill=fins)
        f.polygon([P(0.05, hh * 0.8), P(-0.12, hh * 1.9), P(-0.2, hh * 1.85), P(-0.22, hh * 0.4)], fill=fins)
    elif style == "veil":
        f.polygon([P(0.1, -hh * 0.85), P(-0.2, -hh * 2.0 - swing * 0.3), P(-0.34, -hh * 1.2), P(-0.2, -hh * 0.6)],
                  fill=fins)
        f.polygon([P(0.12, hh * 0.85), P(-0.18, hh * 2.1 + swing * 0.3), P(-0.32, hh * 1.2), P(-0.18, hh * 0.6)],
                  fill=fins)
    else:
        f.polygon([P(0.12, -hh * 0.9), P(-0.02, -hh * 1.55), P(-0.16, -hh * 1.4), P(-0.18, -hh * 0.7)], fill=fins)
        f.polygon([P(-0.04, hh * 0.85), P(-0.12, hh * 1.3), P(-0.2, hh * 1.15), P(-0.2, hh * 0.6)], fill=fins)
    img.alpha_composite(fin_layer)
    n = 40                                            # its body: round at the front, narrowing to its tail
    top, bottom = [], []
    for i in range(n + 1):
        t = i / n
        x = rear + (nose - rear) * t
        shape = math.sin(math.pi * min(1.0, t * 1.08)) ** (0.75 if t > 0.5 else 0.95)
        thin = 0.38 + 0.62 * min(1.0, t * 2.2)        # (narrow where it meets the tail)
        top.append(P(x, -hh * shape * thin))
        bottom.append(P(x, hh * shape * thin))
    outline = [P(tail_root, -hh * 0.2)] + top + bottom[::-1] + [P(tail_root, hh * 0.2)]
    d.polygon(outline, fill=body)
    d.polygon([P(rear + 0.06, hh * 0.05)] + bottom[6:-3] + [P(nose - 0.12, hh * 0.05)], fill=belly)   # (paler under)
    mask = Image.new("L", (W, H), 0)                  # (its body's shape: its markings stay on it)
    ImageDraw.Draw(mask).polygon(outline, fill=255)
    if style == "bands":                              # (a clownfish's white bands, edged in black)
        for bx, bw in ((0.24, 0.035), (0.03, 0.045), (-0.19, 0.03)):
            band = Image.new("L", (W, H), 0)
            ImageDraw.Draw(band).rectangle((P(bx - bw, -1)[0], 0, P(bx + bw, 1)[0], H), fill=255)
            m = ImageChops.multiply(band, mask)
            edge = ImageChops.multiply(m.filter(ImageFilter.MaxFilter(max(3, int(L * 0.025) | 1))), mask)
            img.paste((24, 20, 20, 255), (0, 0), edge)
            img.paste((250, 250, 244, 255), (0, 0), m)
    elif style == "angel":                            # (its dark stripes)
        for bx in (0.18, -0.02, -0.18):
            stripe = Image.new("L", (W, H), 0)
            ImageDraw.Draw(stripe).rectangle((P(bx - 0.025, 0)[0], 0, P(bx + 0.025, 0)[0], H), fill=200)
            img.paste((40, 44, 52, 255), (0, 0), ImageChops.multiply(stripe, mask))
    elif style == "neon":                             # (its glowing blue line, and red behind it)
        red = Image.new("L", (W, H), 0)
        ImageDraw.Draw(red).rectangle((0, cy, P(0.06, 0)[0], H), fill=255)
        img.paste((226, 44, 62, 255), (0, 0), ImageChops.multiply(red, mask))
        line = Image.new("L", (W, H), 0)
        ImageDraw.Draw(line).line((P(rear + 0.02, -hh * 0.12), P(nose - 0.1, -hh * 0.3)), fill=255,
                                  width=max(2, int(L * 0.06)))
        img.paste((64, 210, 255, 255), (0, 0), ImageChops.multiply(line, mask))
    d.polygon([P(nose - 0.16, -hh * 0.55), P(0.0, -hh * 0.72), P(-0.12, -hh * 0.5), P(0.02, -hh * 0.42)],
              fill=mix(body, (255, 255, 255), 0.35) + (255,))    # (a shine)
    gill = (P(0.18, -hh * 0.55), P(0.3, hh * 0.55))
    d.arc((gill[0][0], gill[0][1], gill[1][0], gill[1][1]), start=110, end=250,
          fill=mix(body, (0, 0, 0), 0.3) + (255,), width=max(1, int(L * 0.012)))
    d.polygon([P(0.12, hh * 0.15), P(0.0, hh * 0.45 + swing * 0.2), P(-0.03, hh * 0.3)], fill=fins[:3] + (230,))
    ex, ey, er = nose - 0.11, -hh * 0.18, max(0.035, tall * 0.075)
    d.ellipse((P(ex - er, ey - er), P(ex + er, ey + er)), fill=(250, 250, 250, 255))
    d.ellipse((P(ex - er * 0.25, ey - er * 0.6), P(ex + er * 0.85, ey + er * 0.6)), fill=(18, 18, 24, 255))
    d.ellipse((P(ex + er * 0.15, ey - er * 0.5), P(ex + er * 0.45, ey - er * 0.2)), fill=(255, 255, 255, 255))
    return img.reduce(K)


# ---- this Pietato's tank, on its screen --------------------------------------------------------------------------
class FishTank(Sim):
    """This Pietato's tank in the big one: what's in its cell of the grid (and a fish crossing over into it), drawn
    from the Aquarium (aq: media mode's, moving on all the time)."""
    key = "fish"
    blurb = ("Your Pietato's own fish. Your other Pietatos' tanks join this one, so the fish swim from one to the "
             "next. The web page arranges them.")
    poke_label = "Feed"
    options = (("kind", "Fish", FISH_KINDS, FISH_KINDS[0]),
               ("bubbles", "Bubbles", ("On", "Off"), "On"),
               ("light", "Light", ("Day", "Night"), "Day"))
    backdrop = (8, 38, 70)

    def __init__(self, w, h, rng=None, values=None):
        super().__init__(w, h, rng, values)
        self.aq = Aquarium(self.rng)                   # (media mode gives it its own: sim_game)
        self.pictures = {}
        self.wall = None                               # the clock, for the bubbles: time.time() (media mode's)

    def refit(self, w, h):
        self.w, self.h = w, h
        self.pictures.clear()

    def restart(self):
        """Y: the tank's plants and rocks somewhere new (media mode keeps its seed)."""
        super().restart()
        self.aq.seed = self.rng.randrange(1 << 30)
        self.pictures.pop("back", None)

    def poke(self):
        self.aq.feed()

    def update(self, dt):
        import time
        if dt > 0:
            self.clock += dt
            self.aq.follow(time.monotonic())
        return None

    def cell(self):
        return self.aq.mine()

    def back(self, fs):
        """Water (darker the deeper it is in the grid), light from above, and in a bottom cell the sand and its
        rocks: drawn once (and again when the grid, its size or the light changes)."""
        aq, g = self.aq, self.aq.grid
        c, r = self.cell()
        top, low = not g.has(c, r - 1), not g.has(c, r + 1)
        dec = aq.decor()
        key = (self.w, self.h, fs, aq.seed, aq.light, aq.bubbles_on, g.rows, r, top, low)
        got = self.pictures.get("back")
        if got is not None and got[0] == key:
            return got[1]
        import numpy as np
        from PIL import Image, ImageDraw, ImageFilter
        from .fine import made_fine
        W, H = self.w * fs, self.h * fs
        night = aq.light == "Night"
        hi, deep = WATER[aq.light]
        t = (r + np.linspace(0, 1, H, dtype=np.float32)) / max(1, g.rows)
        water = np.array(hi, np.float32) + (np.array(deep, np.float32) - np.array(hi, np.float32)) * t[:, None, None] ** 0.8
        pic = Image.fromarray(np.repeat(water, W, axis=1).astype(np.uint8), "RGB")
        rays = Image.new("L", (W, H), 0)               # (light from above, in soft beams, fading as it goes down)
        rd = ImageDraw.Draw(rays)
        rnd = random.Random(aq.seed + 1 + c)
        for _ in range(4):
            x = rnd.uniform(-0.2 * W, W)
            spread, lean = rnd.uniform(0.04, 0.09) * W, rnd.uniform(0.15, 0.4) * H
            rd.polygon([(x, 0), (x + spread, 0), (x + spread + lean, H), (x + lean, H)],
                       fill=int((26 if night else 46) * max(0.0, 1 - r * 0.45)))
        rays = rays.filter(ImageFilter.GaussianBlur(max(2, W // 40)))
        fade = Image.linear_gradient("L").resize((W, H)).point(lambda v: 255 - int(v * 0.6))
        from PIL import ImageChops
        pic.paste((210, 236, 255) if not night else (90, 120, 170), (0, 0), ImageChops.multiply(rays, fade))
        d = ImageDraw.Draw(pic)
        if top:                                        # (the surface)
            d.rectangle((0, 0, W, max(2, H // 90)), fill=(150, 210, 236) if not night else (60, 90, 130))
        if low:                                        # (the sand, its rocks, the air stone)
            sand_y, margin = int(SAND * H), int(H * 0.02) + 2
            sand_top, sand_low = SAND_COLOURS[aq.light]
            edge = [(x, sand_y + math.sin(x / W * 9 + aq.seed % 7) * H * 0.012) for x in range(0, W + 8, 8)]
            d.polygon([(0, H)] + edge + [(W, H)], fill=sand_top)
            band = np.array(pic)
            rows = band[sand_y - margin:H]
            grain = np.random.default_rng(aq.seed).random(rows.shape[:2]) < 0.08
            shade = np.linspace(0, 1, rows.shape[0], dtype=np.float32)[:, None, None]
            is_sand = np.all(rows == np.array(sand_top, np.uint8), axis=2, keepdims=True)
            tone = np.array(sand_top, np.float32) + (np.array(sand_low, np.float32)
                                                     - np.array(sand_top, np.float32)) * shade
            tone = np.where(grain[:, :, None], tone * 0.86, tone)
            band[sand_y - margin:H] = np.where(is_sand, tone, rows).astype(np.uint8)
            pic = Image.fromarray(band, "RGB")
            d = ImageDraw.Draw(pic)
            for rx, size, light in dec["rocks"]:       # (round grey stones, half in the sand)
                rr = size * H
                cx, cy = rx * W, sand_y + rr * 0.35
                colour = mix((96, 104, 116), (140, 146, 156), light)
                if night:
                    colour = mix(colour, (20, 24, 32), 0.55)
                d.ellipse((cx - rr * 1.3, cy - rr, cx + rr * 1.3, cy + rr), fill=colour)
                d.ellipse((cx - rr * 0.8, cy - rr * 0.8, cx + rr * 0.2, cy - rr * 0.2),
                          fill=mix(colour, (255, 255, 255), 0.18))
            if dec["stone"] is not None:
                sx = dec["stone"] * W
                d.rounded_rectangle((sx - H * 0.03, sand_y - H * 0.012, sx + H * 0.03, sand_y + H * 0.014),
                                    radius=max(1, H // 120), fill=(70, 74, 84) if not night else (40, 42, 48))
        got = self.pictures["back"] = (key, made_fine(pic, fs))
        return got[1]

    def sprite(self, kind, size, wag, face, tilt, squash, fs):
        """A fish's picture, as it's drawn now (kept: a few of each)."""
        frame = int(wag) % FISH_WAGS
        key = ("fish", kind, size, frame, face, tilt, round(squash, 1), fs)
        got = self.pictures.get(key)
        if got is None:
            from PIL import Image
            from .fine import made_fine
            base_key = ("fishbase", kind, size, frame, fs)
            base = self.pictures.get(base_key)
            if base is None:
                base = self.pictures[base_key] = fish_picture(kind, size * fs, math.sin(frame / FISH_WAGS * 2 * math.pi))
            pic = base if face > 0 else base.transpose(Image.FLIP_LEFT_RIGHT)
            if tilt:
                pic = pic.rotate(-tilt if face > 0 else tilt, resample=Image.BICUBIC, expand=True)
            if squash < 0.99:
                pic = pic.resize((max(1, int(pic.width * squash)), pic.height), Image.BILINEAR)
            if len(self.pictures) > 400:
                keep = {k: v for k, v in self.pictures.items() if not (isinstance(k, tuple) and k[0] == "fish")}
                self.pictures.clear()
                self.pictures.update(keep)
            got = self.pictures[key] = made_fine(pic, fs) if fs > 1 else pic
        return got

    def tag(self, text, colour, fs):
        """A small label (whose a fish is; the tank next door): kept."""
        key = ("tag", text, tuple(colour), fs)
        got = self.pictures.get(key)
        if got is None:
            from PIL import Image, ImageDraw, ImageFont
            from .theme import FONT_UI_BOLD
            from .fine import made_fine
            size = max(9, int(self.h * 0.035)) * fs
            try:
                font = ImageFont.truetype(FONT_UI_BOLD, size)
            except OSError:
                font = ImageFont.load_default()
            probe = ImageDraw.Draw(Image.new("L", (1, 1)))
            w, h = int(probe.textlength(text, font=font)) + 10 * fs, int(size * 1.5)
            w, h = w + (fs - w % fs) % fs, h + (fs - h % fs) % fs
            pic = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            dd = ImageDraw.Draw(pic)
            dd.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=(8, 22, 40, 150))
            dd.text((w / 2, h / 2), text, font=font, fill=tuple(colour) + (255,), anchor="mm")
            got = self.pictures[key] = made_fine(pic, fs) if fs > 1 else pic
        return got

    def draw(self, img, x0, y0):
        import time
        from .fine import ImageDraw, detail
        fs = detail(img)
        aq, g = self.aq, self.aq.grid
        c, r = self.cell()
        W, H = self.w, self.h
        tank = self.back(fs).copy()
        d = ImageDraw.Draw(tank)
        night = aq.light == "Night"
        dec = aq.decor()
        wall = self.wall or time.time()
        if not g.has(c, r + 1):                        # (plants, swaying, in a bottom cell)
            for px, ph, pw, phase, green, leafy in dec["plants"]:
                colour = tuple(int(green[i:i + 2], 16) for i in (1, 3, 5))
                if night:
                    colour = mix(colour, (12, 40, 40), 0.55)
                pts = []
                for i in range(10):
                    t = i / 9
                    sway = math.sin(wall * 1.4 + phase + t * 2.4) * 0.05 * H * t ** 1.4
                    pts.append((px * W + sway, (SAND + 0.02 - t * ph) * H))
                for i in range(9):
                    d.line((pts[i], pts[i + 1]), fill=mix(colour, (230, 255, 200), 0.12 * i / 9),
                           width=max(1, round(pw * H * (1 - 0.65 * i / 9))))
                if leafy:
                    for i in range(2, 9, 2):
                        x, y = pts[i]
                        s, leaf = (-1 if i % 4 else 1), H * 0.05 * (1 - i / 18)
                        d.polygon([(x, y), (x + s * leaf, y - leaf * 0.5), (x + s * leaf * 1.6, y - leaf * 0.2),
                                   (x + s * leaf * 0.7, y + leaf * 0.15)], fill=mix(colour, (180, 230, 120), 0.2))
        for fx, fy, _, _ in aq.flakes():               # (the food in this tank)
            if c <= fx < c + 1 and r <= fy < r + 1.05:
                x, y, rad = (fx - c) * W, (fy - r) * H, max(1.2, H * 0.006)
                d.rectangle((x - rad, y - rad, x + rad, y + rad), fill=(206, 120, 52))
        for sx, sy, seed, top in aq.stones():          # (bubbles: from the stone below, if this is above it)
            if not c <= sx < c + 1:
                continue
            for bx, by, br in stone_bubbles(sx, sy, seed, top, wall):
                if r - 0.05 <= by < r + 1.05:
                    x, y, rad = (bx - c) * W, (by - r) * H, max(1.5, br * H)
                    d.ellipse((x - rad, y - rad, x + rad, y + rad), outline=(214, 240, 255), width=1)
                    d.ellipse((x - rad * 0.45, y - rad * 0.55, x - rad * 0.05, y - rad * 0.15), fill=(240, 252, 255))
        self.draw_fish(tank, fs, c, r)
        self.draw_sides(tank, fs, c, r)
        img.paste(tank, (x0, y0))

    def draw_fish(self, tank, fs, c, r):
        """Each fish in this tank (and half of one crossing over into it), with whose it is when there are others."""
        aq = self.aq
        size = max(16, int(self.h * FISH_LENGTH))
        joined = len(aq.grid.cells) > 1
        reach_x, reach_y = size / self.w, size / self.h
        from .theme import ACCENTS
        accents = {o["name"]: o.get("accent", "") for o in aq.others.values()}
        accents[aq.me] = aq.accent
        for x, y, face, wag, turn, kind, who, _, vx, vy in sorted(aq.everyone(), key=lambda q: q[1]):
            if not (c - reach_x < x < c + 1 + reach_x and r - reach_y < y < r + 1 + reach_y):
                continue
            tilt = 0
            if abs(vx) + abs(vy) > 0.02:
                a = math.degrees(math.atan2(vy * self.h, abs(vx) * self.w + 1e-6))
                tilt = min(FISH_TILTS, key=lambda t: abs(t - a * 0.8))
            squash = abs(math.cos(turn * math.pi)) if turn else 1.0
            pic = self.sprite(kind if kind in LOOKS else FISH_KINDS[0], size, wag, 1 if face > 0 else -1, tilt,
                              max(0.2, squash), fs)
            px, py = (x - c) * self.w, (y - r) * self.h
            tank.paste(pic, (px - pic.width / 2, py - pic.height / 2) if fs > 1 else
                       (int(px - pic.width / 2), int(py - pic.height / 2)), pic)
            if joined:
                colour = dict(ACCENTS).get(accents.get(who), (228, 232, 238))
                t = self.tag(who or "?", colour, fs)
                tank.paste(t, (px - t.width / 2, py + size * 0.42) if fs > 1 else
                           (int(px - t.width / 2), int(py + size * 0.42)), t)

    def draw_sides(self, tank, fs, c, r):
        """The tanks next door: their names at the edges they're through."""
        g = self.aq.grid
        for dc, dr, word in ((-1, 0, "← {}"), (1, 0, "{} →"), (0, -1, "↑ {}"), (0, 1, "↓ {}")):
            name = g.at.get((c + dc, r + dr))
            if not name:
                continue
            t = self.tag(word.format(name), (200, 222, 236), fs)
            x = 6 if dc < 0 else self.w - t.width - 6 if dc > 0 else (self.w - t.width) / 2
            y = 6 if dr < 0 else self.h - t.height - 6 if dr > 0 else self.h * 0.42
            tank.paste(t, (x, y) if fs > 1 else (int(x), int(y)), t)

    def stats(self):
        aq = self.aq
        c, r = self.cell()
        here = sum(1 for x, y, *_ in aq.everyone() if aq.grid.cell_of(x, y) == (c, r))
        f = aq.fish
        where = "Here" if f is None or aq.grid.cell_of(f["x"], f["y"]) == (c, r) else \
            (aq.grid.at.get(aq.grid.cell_of(f["x"], f["y"])) or "Away")[:12]
        return [("Fish here", str(here)), ("Tanks", str(len(aq.grid.cells))), ("Your fish", where),
                ("Fed", str(aq.fed))]

    def hints(self):
        return [("A", "Call your fish"), ("X", "Feed"), ("Y", "New look"), ("START", "Options")]

    def chart(self):
        return None
