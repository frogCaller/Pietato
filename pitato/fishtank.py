"""Apps' Fish Tank: a tank with your Pietato's own fish in it, and food to drop in (pitato/fishlook.py has how it all
looks).

Your Pietatos' tanks (each one on your network, with Settings > Share with other Pietatos on) join up into one big
tank, a grid of them: side by side, and above and below each other, as the web page's Fish Tank arranges them (in a
row by name, till then). The water's surface is along the top of the grid, its bottom along the grid's bottom, and each
Pietato's fish swims through all of it: off one's screen and onto the next. Each Pietato moves its own fish (always,
whether its tank's on its screen or not), and tells the others where it is a few times a second (screens/fishtank.py);
each draws whichever fish are in its own tank, and the web page draws them all.

The grid's cells are 1 x 1 (across and down, whatever a screen's shape), with a gap between each and the next (a TV's
frame, and the wall between two: as much of a tank's width across, and of its height down, as the web page's Fish Tank
sets it): places are in those units, (0, 0) the grid's top left. A fish swims through a gap as through the water,
unseen, so it comes out on the next screen as it would through a real one. A fish is as long as a share of its cell's
height, so it's as big on each screen, for its size."""
import math
import random
import time

from .sims import Sim

FISH_KINDS = ("Goldfish", "Clownfish", "Betta", "Angelfish", "Neon tetra")
FISH_LENGTH = 0.17           # a fish: as long as this much of a cell's height
FISH_CRUISE = 0.17           # ...swimming along at this many cells a second
FISH_HUNGRY = 0.34           # ...and to food at this
FISH_EASE = 1.6              # how quickly it comes round to where it's going
FISH_AWAY = 0.45             # a new place to swim to: in another of the tanks, this often
FISH_TURN = 0.45             # seconds a fish takes to turn round
FISH_WAGS = 8                # its pictures, its tail in each place in turn (each drawn once, and kept)
FISH_MAKE = 3                # ...new ones drawn each frame, at most (the rest the next: never a hitch)
FISH_TILTS = (-20, -10, 0, 10, 20)   # degrees it leans, swimming up or down
EDGE_X = 0.08                # a fish keeps this far from a cell's side with no tank beyond it
TOP, BOTTOM = 0.13, 0.86     # ...and between these, in a cell with no tank above it (the surface) or below (the bottom)
FLOOR = 0.94                 # food that sinks to the bottom lies this far down
NIBBLE = FLOOR - 0.04        # ...and a hungry fish swims down to this, for it
FOOD_FLAKES = 6              # a feed: this many flakes
FOOD_SINK = 0.05             # cells a second
FOOD_STAYS = 25.0            # seconds a flake on the bottom stays before it's gone
FOOD_REACH = 0.05            # a fish's mouth this near a flake eats it
MOUTH = 0.055                # ...its mouth: this far in front of its middle (in cells)
TURN_AGAIN = 1.2             # seconds before it turns round again, at least
FOOD_MOST = 18               # flakes one Pietato has in the water, at most
REMOTE_SETTLE = 0.15         # seconds another's fish, drawn where it is now (from where it said it was, as fast as it
                             # was swimming), takes to be put right as each new word comes
REMOTE_AHEAD = 0.6           # ...guessed on from what it said, this long at most
GRID_MOST = 6                # cells across or down, at most
GAP_MOST = 0.5               # the gap between tanks: as much as half a tank, at most


def fish_default(name):
    """A fish of its own for each Pietato, by its name (START's Fish changes it)."""
    return FISH_KINDS[sum(map(ord, name or "")) % len(FISH_KINDS)]


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
    """The tanks joined up: who's where, what's next to what, and the gaps between them (gap: a share of a tank's width
    across, and of its height down; a fish swims through one, unseen)."""

    def __init__(self, cells, gap=(0.0, 0.0)):
        self.cells = dict(cells)                      # name -> (c, r)
        self.at = {v: n for n, v in self.cells.items()}
        self.cols = max((c for c, _ in self.cells.values()), default=0) + 1
        self.rows = max((r for _, r in self.cells.values()), default=0) + 1
        self.gx, self.gy = (max(0.0, min(GAP_MOST, float(g))) for g in gap)
        self.px, self.py = 1 + self.gx, 1 + self.gy  # (a tank and the gap after it)

    def has(self, c, r):
        return (c, r) in self.at

    def origin(self, c, r):
        """A tank's top left, in the grid."""
        return c * self.px, r * self.py

    def cell_of(self, x, y):
        """The tank a place is in (in a gap: the nearer of the two)."""
        return int(math.floor((x + self.gx / 2) / self.px)), int(math.floor((y + self.gy / 2) / self.py))

    def local(self, x, y):
        """((c, r), across, down) for a place: its tank, and where in it (0 to 1 each way, or a little past, in a gap)."""
        c, r = self.cell_of(x, y)
        ox, oy = self.origin(c, r)
        return (c, r), x - ox, y - oy

    def box(self, c, r, low=False):
        """Where a fish can be in a cell: (x0, x1, y0, y1), kept from its sides with no tank beyond them, and half into
        the gaps that have (low: a hungry one, down to the food on the bottom)."""
        ox, oy = self.origin(c, r)
        return (ox + (-self.gx / 2 if self.has(c - 1, r) else EDGE_X),
                ox + 1 + (self.gx / 2 if self.has(c + 1, r) else -EDGE_X),
                oy + (-self.gy / 2 if self.has(c, r - 1) else TOP),
                oy + (1 + self.gy / 2 if self.has(c, r + 1) else (NIBBLE if low else BOTTOM)))

    def inside(self, c, r, edge=0.05):
        """Where in a tank there's something to see a fish (not in a gap): its box, as far as the screen goes."""
        ox, oy = self.origin(c, r)
        x0, x1, y0, y1 = self.box(c, r)
        return (max(x0, ox) + edge, min(x1, ox + 1) - edge, max(y0, oy) + edge * 0.8, min(y1, oy + 1) - edge * 0.8)

    def top_of(self, c, r):
        """The water's surface over a cell: the top of the topmost tank in an unbroken run above it."""
        while self.has(c, r - 1):
            r -= 1
        return r

    def bottom_of(self, c, r):
        while self.has(c, r + 1):
            r += 1
        return r

    def surface(self, c, r):
        """How far down the grid the water's surface over a cell is."""
        return self.top_of(c, r) * self.py

    def floor(self, c, r):
        """...and the top of the tank at the bottom under it."""
        return self.bottom_of(c, r) * self.py

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
        hungry fish, down to the bottom; one that's there already comes up from it as it swims, not at once)."""
        c, r = self.cell_of(x, y)
        if not self.has(c, r):                        # (somewhere that's gone: as it is, for it to be put back)
            return x + dx, y + dy
        nx = x + dx
        nc = self.cell_of(nx, y)[0]
        if nc != c and not self.has(nc, r):
            nc = c
        x0, x1, _, _ = self.box(nc, r)
        nx = min(max(nx, x0), x1 - 1e-6)
        ny = y + dy
        nr = self.cell_of(nx, ny)[1]
        if nr != r and not self.has(nc, nr):
            nr = r
        _, _, y0, y1 = self.box(nc, nr, low)
        if not low and nr == r:
            y1 = max(y1, min(y + 1e-6, self.box(nc, nr, True)[3]))   # (no further down, though)
        return nx, min(max(ny, y0), y1 - 1e-6)


def wag_rate(speed):
    """A fish's pictures a second, swimming this fast (cells a second): its tail quicker the faster it goes."""
    return FISH_WAGS * (0.5 + 2.5 * speed)


def tail_frame(frame):
    """Its picture for frame (of FISH_WAGS, its tail swinging one way and back): the first frame with its tail in the
    same place (on its way across and on its way back, it's the same picture)."""
    frame %= FISH_WAGS
    return min(frame, (FISH_WAGS // 2 - frame) % FISH_WAGS)


def tail_wag(frame):
    """Where its tail is at frame: -1 to 1."""
    return math.sin(frame / FISH_WAGS * 2 * math.pi)


# ---- your Pietatos' fish, together ----------------------------------------------------------------------------
class Aquarium:
    """The big tank as this Pietato knows it, and its own fish, food and decorations. me: its name. Others' tanks:
    heard() as they tell it (screens/fishtank.py); tick() moves its own fish on (media mode's main loop, always)."""

    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.me = ""
        self.kind = FISH_KINDS[0]
        self.light = "Day"
        self.seed = self.rng.randrange(1 << 30)
        self.stored = {}             # the grid you arranged: {name: [c, r]}, and when ("t")
        self.stored_t = 0.0
        self.gap = (0.0, 0.0)        # ...and the gaps between its tanks (a share of one's width, and of its height)
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
        new = Grid(place(self.tanks(), self.stored), self.gap)
        if new.cells == old.cells and (new.gx, new.gy) == (old.gx, old.gy):
            return
        self.grid = new
        for thing in [self.fish] + self.food:
            if thing is None:
                continue
            (c, r), u, v = old.local(thing["x"], thing["y"])
            name = old.at.get((c, r))
            if name in new.cells:
                ox, oy = new.origin(*new.cells[name])
                thing["x"], thing["y"] = ox + u, oy + v
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
        x0, x1, y0, y1 = self.grid.inside(c, r)
        x = (x0 + x1) / 2 if not side else (x1 if side > 0 else x0)
        self.fish = {"x": x, "y": self.grid.origin(c, r)[1] + 0.45, "vx": 0.0, "vy": 0.0, "face": -1 if side > 0 else 1,
                     "turn": 0.0, "wag": 0.0, "goal": None, "via": None, "rest": 1.0}

    def call(self):
        """A: your fish swims back to this tank."""
        if self.fish is None:
            self.come_home()
        c, r = self.mine()
        x0, x1, y0, y1 = self.grid.inside(c, r)
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
        """The food sinks, a little this way and that, to the bottom under it, and lies there a while."""
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
                floor = g.floor(c, r) + FLOOR
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
                    ox, oy = self.grid.origin(*self.grid.cells[name])
                    out.append((ox + u, oy + v, o["name"], fid))
        return out

    def feed(self, name=None, n=FOOD_FLAKES):
        """A pinch of food, sprinkled in at the top of a tank (yours, or another's by its name). False: no such tank."""
        name = name or self.me
        if name not in self.grid.cells:
            return False
        ox, oy = self.grid.origin(*self.grid.cells[name])
        for _ in range(n):
            self.food.append({"id": self.rng.randrange(1 << 20), "x": ox + self.rng.uniform(0.1, 0.9),
                              "y": oy + self.rng.uniform(0.04, 0.09), "down": None})
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
        x0, x1, y0, y1 = g.inside(*there)
        f["goal"] = (rng.uniform(x0, max(x0 + 0.01, x1)), rng.uniform(y0, max(y0 + 0.01, y1)))
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
        ox, oy = g.origin(nc, nr)
        if nc != c:                                   # (across: in at the side, at a height both have)
            _, _, a0, a1 = g.box(c, r)
            y = min(max(f["y"], max(y0, a0) + 0.02), min(y1, a1) - 0.02)
            return (ox + 0.12 if nc > c else ox + 0.88, y)
        bx0, bx1, _, _ = g.box(c, r)
        x = min(max(f["x"], max(x0, bx0) + 0.04), min(x1, bx1) - 0.04)
        return (x, oy + 0.15 if nr > r else oy + 0.85)

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
        f["wag"] += dt * wag_rate(math.hypot(f["vx"], f["vy"]))

    # -- what it tells the others, and hears from them -----------------------------------------------------------------
    def decor(self):
        """This tank's look, as the others draw it: its light."""
        return {"light": self.light}

    def local(self, x, y):
        """(a tank's name, where in it) for a place in the grid: what the others understand, whatever their grid."""
        (c, r), u, v = self.grid.local(x, y)
        return self.grid.at.get((c, r)), u, v

    def wire(self):
        """What this one tells the others: its fish (in which tank, where), its food, what its fish ate of theirs,
        its decorations, the grid as you last arranged it."""
        f = self.fish
        out = {"decor": self.decor(), "grid": {"t": self.stored_t, "cells": self.stored, "gap": list(self.gap)},
               "food": [], "ate": [[whose, fid] for whose, fid in self.eaten]}
        if f is not None:
            name, u, v = self.local(f["x"], f["y"])
            out["fish"] = {"tank": name, "u": round(u, 4), "v": round(v, 4), "vx": round(f["vx"], 4),
                           "vy": round(f["vy"], 4), "face": f["face"], "kind": self.kind,
                           "ts": round(time.time(), 3)}   # (when: so the others draw it where it is by then)
        for fl in self.food[:FOOD_MOST]:
            name, u, v = self.local(fl["x"], fl["y"])
            if name:
                out["food"].append([fl["id"], name, round(u, 3), round(v, 3)])
        return out

    def arrange(self, cells, t, gap=None):
        """The grid as you arranged it (here, or on another, at t), and the gaps between its tanks: the latest kept."""
        if t <= self.stored_t:
            return False
        self.stored = {n: [int(c), int(r)] for n, (c, r) in cells.items()}
        self.stored_t = t
        self.gap = tuple(max(0.0, min(GAP_MOST, float(g))) for g in gap) if gap else (0.0, 0.0)
        return True

    # -- where things are drawn ---------------------------------------------------------------------------------------
    def follow(self, now):
        """The others' fish, drawn where they are now: from where each said it was and how fast it was swimming, as
        long ago as it said it (o["sent"]: when, by this one's clock), and put right a little at a time as each new
        word comes. now: time.monotonic() (asked by the screen and the web page both: moved on once for the time
        gone by)."""
        dt = min(0.5, now - self.followed) if self.followed else 0.0
        self.followed = now
        if dt <= 0:
            return
        k = 1 - math.exp(-dt / REMOTE_SETTLE)
        seen = set()
        for oid, o in self.others.items():
            g = o.get("fish")
            if not g or g.get("tank") not in self.grid.cells:
                continue
            ox, oy = self.grid.origin(*self.grid.cells[g["tank"]])
            ahead = min(REMOTE_AHEAD, max(0.0, now - o.get("sent", o.get("at", now))))
            tx, ty = ox + g["u"] + g["vx"] * ahead, oy + g["v"] + g["vy"] * ahead
            s = self.shown.get(oid)
            if s is None or abs(s[0] - tx) + abs(s[1] - ty) > 0.8:   # (new, or it jumped: there at once)
                s = self.shown[oid] = [tx, ty, g["face"], 0.0, 0.0]
            else:
                s[0] += g["vx"] * dt                   # (swimming on as it was...)
                s[1] += g["vy"] * dt
                s[0] += (tx - s[0]) * k                # (...and put right, a little at a time)
                s[1] += (ty - s[1]) * k
            if g["face"] != s[2] and s[4] <= 0:
                s[4] = FISH_TURN
            if s[4] > 0:
                was = s[4]
                s[4] -= dt
                if s[4] <= FISH_TURN / 2 < was:
                    s[2] = g["face"]
            s[3] += dt * wag_rate(math.hypot(g["vx"], g["vy"]))
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
                ox, oy = self.grid.origin(*self.grid.cells[g["tank"]])
                s = (ox + g["u"], oy + g["v"], g["face"], 0.0, 0.0)
            out.append((s[0], s[1], s[2], s[3], max(0.0, s[4]) / FISH_TURN, g.get("kind"), o.get("name") or "", oid,
                        g.get("vx", 0.0), g.get("vy", 0.0)))
        return out

    def snapshot(self, now):
        """Everything, for the web page's Fish Tank: the grid, each tank's look, every fish, the food."""
        tanks = []
        for name, (c, r) in sorted(self.grid.cells.items()):
            o = next((o for o in self.others.values() if o["name"] == name), None)
            tanks.append({"name": name, "c": c, "r": r, "me": name == self.me,
                          "accent": (o or {}).get("accent", "") if name != self.me else self.accent,
                          "decor": self.decor() if name == self.me else (o or {}).get("decor") or {}})
        fish = [{"name": who, "kind": kind if kind in FISH_KINDS else FISH_KINDS[0], "x": round(x, 4), "y": round(y, 4),
                 "vx": round(vx, 4), "vy": round(vy, 4), "face": face}
                for x, y, face, _, _, kind, who, _, vx, vy in self.everyone()]
        return {"t": now, "me": self.me, "cols": self.grid.cols, "rows": self.grid.rows, "tanks": tanks,
                "gap": [self.grid.gx, self.grid.gy], "wags": FISH_WAGS,
                "fish": fish, "food": [[round(x, 3), round(y, 3)] for x, y, _, _ in self.flakes()],
                "arranged": self.stored_t}

    accent = ""


# ---- this Pietato's tank, on its screen --------------------------------------------------------------------------
class FishTank(Sim):
    """This Pietato's tank in the big one: what's in its cell of the grid (and a fish crossing over into it, or out),
    drawn from the Aquarium (aq: media mode's, moving on all the time). Its water's drawn once, and each fish's
    pictures (pitato/fishlook.py) once each: a frame is only them pasted where they are now."""
    key = "fish"
    blurb = ("Your Pietato's own fish. Your other Pietatos' tanks join this one, so the fish swim from one to the "
             "next. The web page arranges them.")
    poke_label = "Feed"
    options = (("kind", "Fish", FISH_KINDS, FISH_KINDS[0]),
               ("light", "Light", ("Day", "Night"), "Day"))
    backdrop = (8, 38, 70)

    def __init__(self, w, h, rng=None, values=None):
        super().__init__(w, h, rng, values)
        self.aq = Aquarium(self.rng)                   # (media mode gives it its own: sim_game)
        self.pictures = {}
        self.made = 0                                  # (fish pictures drawn so far this frame)

    def refit(self, w, h):
        self.w, self.h = w, h
        self.pictures.clear()

    def poke(self):
        self.aq.feed()

    def update(self, dt):
        if dt > 0:
            self.clock += dt
            self.aq.follow(time.monotonic())
        return None

    def cell(self):
        return self.aq.mine()

    def back(self, fs):
        """The water: darker the deeper it is in the grid, light from the surface, the glass where there's no tank
        beyond. Drawn once (and again when the grid, the screen's size or the light changes)."""
        from .fishlook import back
        aq, g = self.aq, self.aq.grid
        c, r = self.cell()
        sides = "".join(k for k, (dc, dr) in zip("lrtb", ((-1, 0), (1, 0), (0, -1), (0, 1)))
                        if not g.has(c + dc, r + dr))
        deep = max(1.0, g.rows * g.py - g.gy)          # (the grid's height, its gaps too)
        oy = g.origin(c, r)[1]
        key = (self.w, self.h, fs, aq.seed, c, aq.light, sides, round(oy, 4), round(deep, 4))
        got = self.pictures.get("back")
        if got is None or got[0] != key:
            got = self.pictures["back"] = (key, back(self.w * fs, self.h * fs, aq.seed + c, aq.light, oy / deep,
                                                     (oy + 1) / deep, "t" in sides, sides))
        return got[1]

    def fish_frame(self, kind, length, frame):
        """(the frame it is, a fish's picture) with its tail at frame (of FISH_WAGS): each drawn once and kept, a few
        new ones each frame at most (the nearest one there is, till then: never a hitch)."""
        frame = tail_frame(frame)
        frames = self.pictures.setdefault(("frames", kind, length), {})
        got = frames.get(frame)
        if got is None:
            if frames and self.made >= FISH_MAKE:
                near = min(frames, key=lambda f: min((f - frame) % FISH_WAGS, (frame - f) % FISH_WAGS))
                return near, frames[near]
            from .fishlook import fish_picture
            got = frames[frame] = fish_picture(kind, length, tail_wag(frame))
            self.made += 1
        return frame, got

    def sprite(self, kind, length, wag, face, tilt, squash):
        """A fish's picture as it's drawn now: facing its way, leaning, narrower as it turns round (kept)."""
        frame, base = self.fish_frame(kind, length, int(wag) % FISH_WAGS)
        key = ("fish", kind, length, frame, face, tilt, squash)
        got = self.pictures.get(key)
        if got is None:
            from PIL import Image
            pic = base if face > 0 else base.transpose(Image.FLIP_LEFT_RIGHT)
            if tilt:
                pic = pic.rotate(-tilt if face > 0 else tilt, resample=Image.BICUBIC, expand=True)
            if squash < 1:
                pic = pic.resize((max(1, int(pic.width * squash)), pic.height), Image.BILINEAR)
            if len(self.pictures) > 700:               # (a lot kept: those made from the others go, for now)
                for k in [k for k in self.pictures if isinstance(k, tuple) and k[0] == "fish"]:
                    del self.pictures[k]
            got = self.pictures[key] = pic
        return got

    def flake(self, size, seed):
        """A flake of food's picture (kept)."""
        key = ("flake", size, seed)
        got = self.pictures.get(key)
        if got is None:
            from .fishlook import flake_picture
            got = self.pictures[key] = flake_picture(size, seed * 1.3, seed)
        return got

    def tag(self, text, colour, fs):
        """A small label (whose a fish is; the tank next door), in the screen's own pixels: kept."""
        key = ("tag", text, tuple(colour), fs)
        got = self.pictures.get(key)
        if got is None:
            from PIL import Image, ImageDraw, ImageFont
            from .theme import FONT_UI_BOLD
            size = max(9, int(self.h * 0.035)) * fs
            try:
                font = ImageFont.truetype(FONT_UI_BOLD, size)
            except OSError:
                font = ImageFont.load_default()
            probe = ImageDraw.Draw(Image.new("L", (1, 1)))
            w, h = int(probe.textlength(text, font=font)) + 10 * fs, int(size * 1.5)
            pic = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            dd = ImageDraw.Draw(pic)
            dd.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=(8, 22, 40, 150))
            dd.text((w / 2, h / 2), text, font=font, fill=tuple(colour) + (255,), anchor="mm")
            got = self.pictures[key] = pic
        return got

    def draw(self, img, x0, y0):
        from .fine import detail, made_fine
        fs = detail(img)
        aq, g = self.aq, self.aq.grid
        c, r = self.cell()
        W, H = self.w * fs, self.h * fs
        ox, oy = g.origin(c, r)
        tank = self.back(fs).copy()
        self.made = 0
        size = max(1.5, round(H * 0.007 * 2) / 2)
        for fx, fy, _, fid in aq.flakes():             # (the food in this tank)
            u, v = fx - ox, fy - oy
            if -0.02 <= u <= 1.02 and -0.02 <= v <= 1.02:
                pic = self.flake(size, fid % 5)
                tank.paste(pic, (int(u * W - pic.width / 2), int(v * H - pic.height / 2)), pic)
        self.draw_fish(tank, fs, c, r)
        self.draw_sides(tank, fs, c, r)
        img.paste(made_fine(tank, fs), (x0, y0))

    def draw_fish(self, tank, fs, c, r):
        """Each fish in this tank (and the part of one crossing into it, or out of it, through its side), with whose
        it is when there are others."""
        from .fishlook import fish_size
        from .theme import ACCENTS
        aq, g = self.aq, self.aq.grid
        W, H = self.w * fs, self.h * fs
        ox, oy = g.origin(c, r)
        length = max(16, int(H * FISH_LENGTH))
        joined = len(g.cells) > 1
        accents = {o["name"]: o.get("accent", "") for o in aq.others.values()}
        accents[aq.me] = aq.accent
        for x, y, face, wag, turn, kind, who, _, vx, vy in sorted(aq.everyone(), key=lambda q: q[1]):
            kind = kind if kind in FISH_KINDS else FISH_KINDS[0]
            across, down = fish_size(kind)
            u, v = x - ox, y - oy
            ru, rv = length * across / 2 / W, length * down / 2 / H
            if not (-ru < u < 1 + ru and -rv < v < 1 + rv + (0.08 if joined else 0)):
                continue
            tilt = 0
            if abs(vx) + abs(vy) > 0.02:
                a = math.degrees(math.atan2(vy * self.h, abs(vx) * self.w + 1e-6))
                tilt = min(FISH_TILTS, key=lambda t: abs(t - a * 0.8))
            squash = max(0.25, round(abs(math.cos(turn * math.pi)) * 4) / 4) if turn else 1.0
            pic = self.sprite(kind, length, wag, 1 if face > 0 else -1, tilt, squash)
            px, py = u * W, v * H
            tank.paste(pic, (int(px - pic.width / 2), int(py - pic.height / 2)), pic)
            if joined and 0 <= u <= 1 and 0 <= v <= 1:   # (whose it is: while it's in this tank, not between)
                colour = dict(ACCENTS).get(accents.get(who), (228, 232, 238))
                t = self.tag(who or "?", colour, fs)
                tank.paste(t, (int(px - t.width / 2), int(py + length * 0.34)), t)

    def draw_sides(self, tank, fs, c, r):
        """The tanks next door: their names at the edges they're through."""
        g = self.aq.grid
        W, H, m = self.w * fs, self.h * fs, 6 * fs
        for dc, dr, word in ((-1, 0, "← {}"), (1, 0, "{} →"), (0, -1, "↑ {}"), (0, 1, "↓ {}")):
            name = g.at.get((c + dc, r + dr))
            if not name:
                continue
            t = self.tag(word.format(name), (200, 222, 236), fs)
            x = m if dc < 0 else W - t.width - m if dc > 0 else (W - t.width) // 2
            y = m if dr < 0 else H - t.height - m if dr > 0 else int(H * 0.42)
            tank.paste(t, (int(x), int(y)), t)

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
        return [("A", "Call your fish"), ("X", "Feed"), ("START", "Options")]

    def chart(self):
        return None
