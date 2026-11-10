"""Apps' Fish Tank, and your Pietatos' tanks joined up into one (pitato/fishtank.py, screens/fishtank.py, fishlook.py):
the grid (where each tank goes, the same on each of them; what's next to what; the way from one to another; the space
between screens), a fish swimming in its own tank and through the others', food sinking to the bottom and eaten (in
another's tank too), two Pietatos telling each other where their fish are (each drawn smoothly by the other), the
grid arranged on one and kept by both, and what's checked of what another says. Then media mode: its page and
buttons, its options, how it's drawn (each fish's pictures once, a few at a time; quick; a fish in the space between
screens on neither), telling your others (straight to each, on the beacons' port) and hearing them, one gone quiet,
sharing off; the web page's Fish Tank (the whole grid, a fish's picture, food dropped in, the tanks arranged); and the
page itself in a real browser: drawn, a tap feeds a tank, a tank dragged somewhere new, and the space between screens
set."""
import asyncio, io, json, math, os, random, shutil, socket, sys, threading, time, types
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS); sys.path.insert(0, ROOT)
import pietato_all as g

S = SP + "/t_fishtank"
shutil.rmtree(S, ignore_errors=True)
H = S + "/home"
for d in ("Music", "Videos", "Pictures", "Documents"):
    os.makedirs(f"{H}/{d}")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"; g.GROUP_LOG = S + "/group.json"
json.dump({"settings": {"name": "Den", "accent": "Teal"}}, open(g.STATE_FILE, "w"))
g.home_dir = lambda: H
import gk_static; gk_static.use_home(g, H)
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
g.list_devices = lambda: []
F = sys.modules["pitato.fishtank"]
SF = sys.modules["pitato.screens.fishtank"]
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


def until(cond, sec=5):
    t = time.monotonic()
    while not cond() and time.monotonic() - t < sec:
        time.sleep(0.05)
    return cond()


class Peer(SF.FishScreen):
    """Another Pietato's part of the big tank: its own Aquarium, hearing the rest as media mode does (fish_take)."""

    def __init__(self, name, oid, kind, accent, seed):
        self.aquarium = aq = F.Aquarium(random.Random(seed))
        aq.me, aq.kind, aq.accent = name, kind, accent
        self.oid, self.kept, self.fish_clocks = oid, {}, {}

    def set_setting(self, key, value):
        self.kept[key] = value

    def msg(self, watched=False):
        aq = self.aquarium
        return json.loads(json.dumps(dict(aq.wire(), fishtank=1, id=self.oid, name=aq.me, accent=aq.accent,
                                          w=watched)))


def inside(grid, x, y):
    """(x, y) is in one of the grid's tanks, where a fish can be."""
    c, r = grid.cell_of(x, y)
    if not grid.has(c, r):
        return False
    x0, x1, y0, y1 = grid.box(c, r)
    return x0 - 1e-6 <= x <= x1 + 1e-6 and y0 - 1e-6 <= y <= y1 + 1e-6


# ---- the grid --------------------------------------------------------------------------------------------------
check(f"three tanks, none arranged: along the top, by name, the same however they're heard "
      f"({F.place(['Kitchen', 'Den', 'bedroom'], {})})",
      F.place(["Kitchen", "Den", "bedroom"], {}) == {"bedroom": (0, 0), "Den": (1, 0), "Kitchen": (2, 0)}
      == F.place(["bedroom", "Kitchen", "Den", "Den"], None))
check("...arranged: each where it was put, one new along the top after them",
      F.place(["Den", "Kitchen", "Bedroom"], {"Den": [0, 0], "Kitchen": [0, 1]})
      == {"Den": (0, 0), "Kitchen": (0, 1), "Bedroom": (1, 0)})
check("...from (0, 0), however it was put", F.place(["Den", "Kitchen"], {"Den": [-1, 2], "Kitchen": [0, 2]})
      == {"Den": (0, 0), "Kitchen": (1, 0)})
check("...two in one place: the second along the top instead",
      F.place(["Den", "Kitchen"], {"Den": [0, 0], "Kitchen": [0, 0]}) == {"Den": (0, 0), "Kitchen": (1, 0)})
junk = {"Den": [0.5, 0], "Kitchen": [True, 0], "Bedroom": [0, 0, 0], "Attic": "x", "Garage": [99, 0]}
check(f"...where it isn't a place: as if not arranged ({F.place(list(junk), junk)})",
      F.place(list(junk), junk) == F.place(list(junk), {}))
G = F.Grid({"Den": (0, 0), "Bedroom": (1, 0), "Kitchen": (0, 1)})
check(f"an L of three: {G.cols} x {G.rows}; a tank's sides open where another is beyond them ({G.box(0, 0)})",
      (G.cols, G.rows) == (2, 2) and G.box(0, 0) == (F.EDGE_X, 1, F.TOP, 1)
      and G.box(1, 0) == (1, 2 - F.EDGE_X, F.TOP, F.BOTTOM) and G.box(0, 1) == (F.EDGE_X, 1 - F.EDGE_X, 1, 1 + F.BOTTOM))
check("...the water's surface over the bottom one is the top one's; the bottom under the top one, the bottom one's",
      G.top_of(0, 1) == 0 and G.bottom_of(0, 0) == 1 and G.top_of(1, 0) == 0 and G.bottom_of(1, 0) == 0)
check(f"...the way from the right one to the bottom one: through the corner ({G.path((1, 0), (0, 1))})",
      G.path((1, 0), (0, 1)) == [(1, 0), (0, 0), (0, 1)] and G.path((0, 0), (0, 0)) == [(0, 0)])
check("...two with a gap between: no way", F.Grid({"A": (0, 0), "B": (2, 0)}).path((0, 0), (2, 0)) == [])
x, y = G.move(0.5, 0.5, 1.0, 0)
check(f"...a fish swims across into the next tank ({x:.2f}, {y:.2f})", 1 < x < 2 and y == 0.5)
x, y = G.move(0.5, 1.5, 1.0, 0)
check(f"...but not through the glass where there's none beyond ({x:.2f})", abs(x - (1 - F.EDGE_X)) < 1e-5)
x, y = G.move(1.5, 0.5, 0, 1.0)
check(f"...nor down through the bottom ({y:.2f})", abs(y - F.BOTTOM) < 1e-5)
x, y = G.move(0.5, 0.5, 0, 1.0)
check(f"...down into the one below ({y:.2f})", 1 < y < 1 + F.BOTTOM)
GG = F.Grid({"Den": (0, 0), "Kitchen": (1, 0), "Attic": (0, 1)}, (0.1, 0.2))
check(f"the space between screens (a tenth of one across, a fifth down): each tank further on by it "
      f"({GG.origin(1, 0)}, {GG.origin(0, 1)})", GG.origin(1, 0) == (1.1, 0) and GG.origin(0, 1) == (0, 1.2))
check("...a place in it: in the nearer tank", GG.cell_of(1.04, 0.5) == (0, 0) and GG.cell_of(1.06, 0.5) == (1, 0)
      and GG.cell_of(0.5, 1.09) == (0, 0) and GG.cell_of(0.5, 1.11) == (0, 1))
check(f"...a fish can swim half into it, where there's a tank beyond ({GG.box(0, 0)})",
      GG.box(0, 0) == (F.EDGE_X, 1.05, F.TOP, 1.1) and GG.box(1, 0)[:2] == (1.05, 2.1 - F.EDGE_X))
x, y = GG.move(0.9, 0.5, 0.3, 0)
check(f"...and swims through it into the next tank ({x:.2f})", abs(x - 1.2) < 1e-9 and GG.cell_of(x, y) == (1, 0))
x, y = GG.move(1.5, 0.5, 0, 1.0)
check(f"...but not down where there's no tank below ({y:.2f})", abs(y - F.BOTTOM) < 1e-5)
x, y = GG.move(0.5, 0.8, 0, 0.5)
check(f"...down through it into the one below ({y:.2f})", abs(y - 1.3) < 1e-9 and GG.cell_of(x, y) == (0, 1))

# ---- a fish on its own -------------------------------------------------------------------------------------------
den = Peer("Den", "den000000000", "Neon tetra", "Teal", 1)
aq = den.aquarium
spots, faces, turns = [], [], 0
for i in range(1200):                                  # (two minutes)
    aq.tick(0.1)
    f = aq.fish
    spots.append((f["x"], f["y"]))
    if faces and f["face"] != faces[-1]:
        turns += 1
    faces.append(f["face"])
check(f"a fish on its own: in its tank all the time ({sum(inside(aq.grid, *p) for p in spots)} of {len(spots)})",
      all(inside(aq.grid, *p) for p in spots) and aq.grid.cells == {"Den": (0, 0)})
xs, ys = [p[0] for p in spots], [p[1] for p in spots]
check(f"...swimming all over it ({min(xs):.2f}-{max(xs):.2f} across, {min(ys):.2f}-{max(ys):.2f} down)",
      max(xs) - min(xs) > 0.5 and max(ys) - min(ys) > 0.25)
check(f"...turning round now and then, not back and forth ({turns} turns in two minutes)", 2 <= turns <= 120 / F.TURN_AGAIN)
check(f"...its tail going ({aq.fish['wag']:.0f})", aq.fish["wag"] > 100)
check("food for a tank that isn't there: none", aq.feed("Attic") is False and not aq.food)
check("X: a pinch of food at the top of its tank", aq.feed() is True and len(aq.food) == F.FOOD_FLAKES
      and all(0 < fl["x"] < 1 and 0.04 <= fl["y"] <= 0.09 for fl in aq.food))
fed = aq.fed
for i in range(900):
    aq.tick(0.1)
    if not aq.food:
        break
check(f"...eaten, every flake ({aq.fed - fed} in {i / 10:.0f} s)", not aq.food and aq.fed - fed == F.FOOD_FLAKES)
aq.feed()
fish, aq.fish = aq.fish, None
for _ in range(400):                                   # (no fish to eat it: just the food)
    aq.sink(0.1)
    aq.clock += 0.1
floor = F.FLOOR
check(f"...with no fish to eat it: down to the bottom, and lying there ({sorted({round(fl['y'], 3) for fl in aq.food})})",
      len(aq.food) == F.FOOD_FLAKES and all(abs(fl["y"] - floor) < 1e-9 and fl["down"] is not None for fl in aq.food))
for _ in range(int(F.FOOD_STAYS * 10) + 5):
    aq.sink(0.1)
    aq.clock += 0.1
check("...then gone", not aq.food)
aq.fish = fish
aq.feed()
for _ in range(200):                                   # (on the bottom by now, with the fish kept out of it)
    aq.sink(0.1)
    aq.clock += 0.1
low, fed = 0.0, aq.fed
for i in range(300):
    aq.tick(0.1)
    low = max(low, aq.fish["y"])
    if not aq.food:
        break
check(f"...food on the bottom: a hungry fish goes down to it, and eats it all ({aq.fed - fed} in {i / 10:.0f} s, "
      f"down to {low:.2f})", not aq.food and aq.fed - fed == F.FOOD_FLAKES and F.BOTTOM < low <= F.NIBBLE)
ys = []
for _ in range(100):
    aq.tick(0.1)
    ys.append(aq.fish["y"])
check(f"...and swims up from it again, not all at once (at most {max(abs(a - b) for a, b in zip(ys, ys[1:])):.3f} "
      f"in a tenth of a second)", max(abs(a - b) for a, b in zip(ys, ys[1:])) < 0.05 and min(ys) < F.BOTTOM)
aq.call()
cx, cy = (F.EDGE_X + 1 - F.EDGE_X) / 2, (F.TOP + F.BOTTOM) / 2
check(f"A: it's called to the middle of its tank ({aq.fish['goal']})", aq.fish["goal"] == (cx, cy))
near = 9.0
for _ in range(150):
    aq.tick(0.1)
    near = min(near, math.hypot(aq.fish["x"] - cx, aq.fish["y"] - cy))
check(f"...and comes ({near:.2f} from it, nearest)", near < 0.06)

check(f"its look, as the others draw it: its light ({aq.decor()})", aq.decor() == {"light": "Day"})

# ---- two of them: the Den's and the Kitchen's ---------------------------------------------------------------------
kit = Peer("Kitchen", "kitchen00000", "Clownfish", "Gold", 2)
clock = [0.0]
T0 = time.time()                                       # (their clocks: this test's, as it goes on)
F.time = SF.time = types.SimpleNamespace(time=lambda: T0 + clock[0], monotonic=lambda: clock[0], sleep=time.sleep)


def run(peers, secs, dt=0.1, say=0.25, each=None):
    """peers on for secs: each fish moved on every dt; each tells the others where it is every say."""
    t, next_say = 0.0, 0.0
    while t < secs - 1e-9:
        for p in peers:
            p.aquarium.tick(dt)
        t += dt
        clock[0] += dt
        if t >= next_say:
            next_say += say
            said = [(p, p.msg()) for p in peers]
            for p in peers:
                for q, msg in said:
                    if q is not p:
                        p.fish_take(msg, clock[0])
            for p in peers:
                p.aquarium.follow(clock[0])
        if each is not None:
            each()


run([den, kit], 1)
check(f"two of them, each told where the other's fish is: one grid, the same on both ({den.aquarium.grid.cells})",
      den.aquarium.grid.cells == kit.aquarium.grid.cells == {"Den": (0, 0), "Kitchen": (1, 0)})
been = set()
pos = []


def where():
    f = den.aquarium.fish
    been.add(den.aquarium.grid.cell_of(f["x"], f["y"]))
    pos.append((f["x"], f["y"]))


run([den, kit], 240, each=where)
check(f"...the Den's fish swims into the Kitchen's tank, and back (in {sorted(been)})", been == {(0, 0), (1, 0)})
steps = []


def follow_each():
    kit.aquarium.follow(clock[0])
    s = kit.aquarium.shown.get("den000000000")
    if s is not None:
        steps.append((s[0], s[1]))


run([den, kit], 30, dt=0.05, say=0.25, each=follow_each)
jumps = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(steps, steps[1:])]
check(f"...the Kitchen draws the Den's fish swimming on between what it's told: smoothly, no jumps (at most "
      f"{max(jumps):.4f} a frame, a twentieth of a second)", len(steps) > 500 and max(jumps) < 0.025)
check("...and never through the glass", all(inside(den.aquarium.grid, *p) for p in pos))
seen = {who: (x, y) for x, y, _, _, _, _, who, _, _, _ in kit.aquarium.everyone()}
said = den.msg()["fish"]
check(f"...the Kitchen sees the Den's fish where the Den says it is ({seen.get('Den')}, "
      f"{said['tank']} {said['u']:.2f} {said['v']:.2f})",
      seen.get("Den") is not None and abs(seen["Den"][0] - (said["u"] + (1 if said["tank"] == "Kitchen" else 0))) < 0.15
      and abs(seen["Den"][1] - said["v"]) < 0.15)
check("...as the kind of fish it is", {q[6]: q[5] for q in kit.aquarium.everyone()}.get("Den") == "Neon tetra")
den.aquarium.food.clear(); kit.aquarium.food.clear()
fed = den.aquarium.fed + kit.aquarium.fed
check("the Den drops food in the Kitchen's tank", den.aquarium.feed("Kitchen")
      and all(1 < fl["x"] < 2 for fl in den.aquarium.food))
run([den, kit], 0.5)
theirs = [p for p in kit.aquarium.flakes() if p[2] == "Den"]
check(f"...the Kitchen has it in its water too ({len(theirs)} flakes)", len(theirs) == F.FOOD_FLAKES)
for _ in range(120):
    run([den, kit], 1)
    if not den.aquarium.food:
        break
run([den, kit], 0.5)
eaten = den.aquarium.fed + kit.aquarium.fed - fed
check(f"...all of it eaten, by the fish in either tank ({eaten} bites: the Den's fish "
      f"{den.aquarium.fed}, the Kitchen's {kit.aquarium.fed})", not den.aquarium.food and F.FOOD_FLAKES <= eaten <= 12
      and not [p for p in kit.aquarium.flakes() if p[2] == "Den"])
den.aquarium.feed("Den")
fid = den.aquarium.food[0]["id"]
msg = kit.msg()
msg["ate"] = [["Den", fid]]
den.fish_take(msg, clock[0])
den.aquarium.sink(0.1)
check("...a flake the other's fish ate: gone from the one that dropped it", fid not in [fl["id"] for fl in den.aquarium.food])
den.aquarium.food.clear()

# the grid, arranged on one: kept by the other
now = time.time()
kit.aquarium.arrange({"Den": (0, 0), "Kitchen": (0, 1)}, now, (0.0, 0.25))
run([den, kit], 0.5)
check(f"arranged on the Kitchen's, one above the other: the Den's has it too ({den.aquarium.grid.cells}, "
      f"kept: {den.kept.get('fish_grid')})", den.aquarium.grid.cells == kit.aquarium.grid.cells
      == {"Den": (0, 0), "Kitchen": (0, 1)} and den.kept.get("fish_grid", {}).get("cells") == {"Den": [0, 0],
                                                                                                "Kitchen": [0, 1]})
check(f"...and the space between them, a quarter of a screen ({den.aquarium.gap}, {den.kept['fish_grid'].get('gap')})",
      den.aquarium.gap == (0.0, 0.25) and den.aquarium.grid.gy == 0.25 and den.kept["fish_grid"]["gap"] == [0.0, 0.25])
check("...an older arrangement doesn't undo it", not den.aquarium.arrange({"Den": (0, 0), "Kitchen": (1, 0)}, now - 5))
been.clear(); pos.clear()
run([den, kit], 240, each=where)
check(f"...the Den's fish swims down into the Kitchen's tank, and up again, through the space between them (in "
      f"{sorted(been)}; {sum(1 < y < 1.25 for _, y in pos)} times in it)", been == {(0, 0), (0, 1)}
      and all(inside(den.aquarium.grid, *p) for p in pos) and any(1 < y < 1.25 for _, y in pos))

# what's checked of what another says
cut = dict(kit.msg(), id="kitchen00000")
bad = [("no id", dict(cut, id=None)), ("this one's own name", dict(cut, id="other0000000", name="Den")),
       ("another's name", dict(cut, id="other0000000"))]
for what, msg in bad:
    before = dict(den.aquarium.others)
    den.fish_take(msg, clock[0])
    check(f"another's says, with {what}: not taken", den.aquarium.others.keys() == before.keys())
odd = dict(cut, fish={"tank": "Kitchen", "u": float("nan"), "v": 0.5, "vx": 0, "vy": 0, "face": 1, "kind": "Shark"},
           decor={"plants": [[2, 0.3, 0.02, 1, "#zzzzzz", True], [0.5, 0.3, 0.02, 1, "#336633", 1]],
                  "rocks": "lots", "stone": 7, "light": "Disco"},
           food=[[1, "Den", 0.5, 0.5], ["x", "Den", 0.5, 0.5], [2, "Den", float("inf"), 0.5]] + [[3, "Den", 0.5, 0.5]] * 40,
           grid={"t": time.time() + 3600, "cells": {"Den": [0, 0], "Kitchen": [1, 0]}})
den.fish_take(json.loads(json.dumps(odd)), clock[0])
o = den.aquarium.others["kitchen00000"]
check(f"...a fish somewhere that isn't a place: no fish ({o['fish']})", o["fish"] is None)
check(f"...its look kept to what's expected ({o['decor']})", o["decor"] == {"light": "Day"})
old = dict(cut, decor={"plants": [[0.5, 0.3, 0.02, 1.0, "#336633", True]], "rocks": [[0.4, 0.05, 0.5]], "stone": 0.4,
                       "light": "Night"})
den.fish_take(json.loads(json.dumps(old)), clock[0])
check(f"...one not updated yet, with plants, rocks and bubbles: just its light "
      f"({den.aquarium.others['kitchen00000']['decor']})", den.aquarium.others["kitchen00000"]["decor"] == {"light": "Night"})
den.fish_take(json.loads(json.dumps(odd)), clock[0])
check(f"...food: the flakes that are flakes, of no more than {F.FOOD_MOST} ({len(o['food'])})",
      len(o["food"]) == F.FOOD_MOST - 2 and o["food"][0] == (1, "Den", 0.5, 0.5)
      and all(fl[0] == 3 for fl in o["food"][1:]))
check("...a grid arranged an hour from now: not taken", den.aquarium.grid.cells == {"Den": (0, 0), "Kitchen": (0, 1)}
      and den.aquarium.stored == {"Den": [0, 0], "Kitchen": [0, 1]})


F.time = SF.time = time                                # (the real clock again)


# ---- media mode ----------------------------------------------------------------------------------------------------
class FB:
    w, h = 640, 480; real_w, real_h = 640, 480; last = None
    def show(self, img): FB.last = img.copy()
    def show_part(self, img, box): FB.last = img.copy()
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
fake = [time.monotonic()]
SF.time = types.SimpleNamespace(monotonic=lambda: fake[0], time=time.time, sleep=time.sleep)   # (the fish's clock)


def tick(secs, step=0.1):
    """Media mode's main loop, for secs: the fish moved on, what's heard put in, your others told."""
    end = fake[0] + secs
    while fake[0] < end - 1e-9:
        fake[0] += step
        m.fish_tick(fake[0])


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
check(f"media mode: a fish of its own, by its name ({m.aquarium.kind}, {F.fish_default('Den')})",
      m.aquarium.me == "Den" and m.aquarium.kind == F.fish_default("Den") == "Neon tetra")
m.web_tab("Fish Tank")
s = m.sim_game()
check(f"Apps > Fish Tank: its page, the fish that lives on all the time ({type(s).__name__})",
      s.key == "fish" and s.aq is m.aquarium and m.on_fish_page())
check(f"...its buttons: {m.sim_hints(s)}", m.sim_hints(s) == [("A", "Call your fish"), ("X", "Feed"),
                                                               ("START", "Options")])
tick(3)
first = (m.aquarium.fish["x"], m.aquarium.fish["y"])
tick(3)
check(f"...it swims ({first} to {m.aquarium.fish['x']:.2f}, {m.aquarium.fish['y']:.2f})",
      (m.aquarium.fish["x"], m.aquarium.fish["y"]) != first)
m.press("x")
check("X: food in", len(m.aquarium.food) == F.FOOD_FLAKES)
m.press("a")
check(f"A: called ({m.msg})", m.msg == "Here, fish!" and m.aquarium.fish["goal"] is not None)
seed, look = m.aquarium.seed, m.aquarium.decor()
m.press("y")
check("Y: nothing (it's all water: nothing to move)", m.aquarium.seed == seed and m.aquarium.decor() == look
      and m.setting("fish_seed") is None)
m.dirty = True; m.flush()
shot = FB.last.convert("RGB")
shot.save(S + "/fish_page.png")
box = shot.crop((g.SIM_BOX[0] + 4, g.SIM_BOX[1] + 4, g.SIM_BOX[2] - 4, g.SIM_BOX[1] + 60))
blue = sum(1 for r, gg, b in box.getdata() if b > r + 40 and b > 120)
check(f"...drawn: water in its box ({blue} of {box.width * box.height} pixels blue)", blue > 0.8 * box.width * box.height)

# how it's drawn: the water once, and each fish's pictures once (a few new ones a frame, at most), so a frame's quick
import pitato.fishlook as FL
from PIL import Image
made, real_picture = [], FL.fish_picture


def counted(kind, length, wag):
    made.append((kind, length, round(wag, 4)))
    return real_picture(kind, length, wag)


FL.fish_picture = counted
tank = F.FishTank(640, 480, random.Random(4))
a1 = tank.aq
a1.me, a1.kind = "Den", "Goldfish"
for i, kind in enumerate(F.FISH_KINDS[1:]):
    a1.others[f"p{i}"] = {"name": f"P{i}", "accent": "", "decor": {"light": "Day"}, "food": [], "ate": [],
                          "at": 0, "age": 0, "fish": {"tank": "Den", "u": 0.2 + 0.18 * i, "v": 0.25 + 0.15 * i,
                                                      "vx": 0.12, "vy": 0.0, "face": 1, "kind": kind}}
a1.tick(0.1)
pic, each, took = Image.new("RGB", (640, 480)), [], []
for i in range(60):
    before = len(made)
    a1.follow(1000 + i * 0.05)
    t0 = time.perf_counter()
    tank.draw(pic, 0, 0)
    took.append(time.perf_counter() - t0)
    each.append(len(made) - before)
    a1.tick(0.05)
FL.fish_picture = real_picture
pic.save(S + "/fish_drawn.png")
kinds = {k for k, _, _ in made}
check(f"each fish's pictures: a few new ones a frame at most ({each[:12]}...)", each[0] <= len(F.FISH_KINDS)
      and max(each[1:]) <= F.FISH_MAKE and kinds == set(F.FISH_KINDS))
tails = len({F.tail_frame(k) for k in range(F.FISH_WAGS)})   # (its tail swings across and back: the same pictures)
check(f"...each drawn once, and kept: by now, each of every kind's ({len(made)} for {len(kinds)} kinds, {tails} each)",
      len(made) == len(set(made)) == len(kinds) * tails)
took = sorted(took[-20:])
check(f"...so a frame's quick, once they're made ({took[10] * 1000:.2f} ms)", took[10] < 0.015)


def view(me, x):
    """me's tank drawn, with the Den and the Kitchen side by side, a third of a screen between them: a fish at x (or
    none)."""
    t = F.FishTank(640, 480, random.Random(5))
    q = t.aq
    q.me, q.kind = me, "Goldfish"
    q.arrange({"Den": (0, 0), "Kitchen": (1, 0)}, 1.0, (0.3, 0.0))
    q.others["o"] = {"name": "Kitchen" if me == "Den" else "Den", "accent": "", "decor": {"light": "Day"},
                     "food": [], "ate": [], "at": 0, "age": 0, "fish": None}
    q.regrid()
    q.fish = None if x is None else {"x": x, "y": 0.5, "vx": 0.0, "vy": 0.0, "face": 1, "turn": 0.0, "wag": 0.0,
                                     "goal": None, "via": None, "rest": 9.0}
    out = Image.new("RGB", (640, 480))
    t.draw(out, 0, 0)
    return out.tobytes()


den_bare, kit_bare = view("Den", None), view("Kitchen", None)
check("a fish in the space between screens: on neither", view("Den", 1.15) == den_bare and view("Kitchen", 1.15) == kit_bare)
check("...just into it: still partly on the screen it's leaving",
      view("Den", 1.02) != den_bare and view("Kitchen", 1.02) == kit_bare)
check("...nearly through: partly on the next", view("Den", 1.28) == den_bare and view("Kitchen", 1.28) != kit_bare)
m.press("start")
rows = [k for k, _, _, _ in m.sim_rows(type(s))]
check(f"START: its options ({rows})", rows == ["kind", "light", "full"])
m.press("right")
tick(0.1)
check(f"...another fish, kept ({m.aquarium.kind}, {m.setting('sim_fish_kind')})",
      m.aquarium.kind == F.FISH_KINDS[0] == m.setting("sim_fish_kind"))
m.press("down"); m.press("right")
tick(0.1)
check(f"...the light: Night ({m.aquarium.light})", m.aquarium.light == "Night" and m.aquarium.decor()["light"] == "Night")
m.press("left")
m.press("b")
tick(0.1)

# telling your others, and hearing them
ear = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
ear.bind(("127.0.0.1", 0)); ear.settimeout(0.5)
SF.CAM_BEACON = ear.getsockname()[1]                   # (the beacons' port: one of this test's own)


def heard_all(wait=0.5):
    """What this one's told your others since last asked (straight to each: here, on the beacons' port)."""
    out = []
    ear.settimeout(wait)
    try:
        while True:
            out.append(json.loads(ear.recv(8192).decode()))
            ear.settimeout(0.05)
    except (socket.timeout, OSError):
        pass
    return out


m.fish_said = 0.0
tick(0.1)
check("none of yours on: nobody told", heard_all() == [])
port = 9
m.pie.hear("127.0.0.1", {"pietato": 1, "id": "kitchen00000", "port": port, "host": "Kitchen", "accent": "Gold"})
m.fish_said = 0.0
tick(0.1)
got = heard_all()
told = got[-1] if got else {}
check(f"the Kitchen's Pietato on: told, straight to it ({len(json.dumps(told))} bytes: "
      f"{sorted(told)})", len(got) == 1 and told.get("fishtank") == 1 and told.get("id") == m.share_id
      and told.get("name") == "Den" and told["fish"]["tank"] == "Den" and told["fish"]["kind"] == m.aquarium.kind
      and told["w"] is True and told["decor"] == {"light": "Day"}
      and len(json.dumps(told)) < 4000)
tick(1, 0.04)                                    # (25 turns a second: told every third, a tenth of a second or more
n = len(heard_all())                             #  since the last. A turn every tenth exactly was told every one or
check(f"...while its Fish Tank is on the screen: several times a second ({n} in a second)", 7 <= n <= 9)   # every other,
                                                 #  by how the clock's figures rounded: by how long the machine was up)
m.go_home()
m.fish_web_at = -1e9
tick(4)
n = len(heard_all())
check(f"...when nobody's watching: now and then ({n} in four seconds)", 1 <= n <= 3)
kit = Peer("Kitchen", "kitchen00000", "Clownfish", "Gold", 2)
kit.aquarium.tick(0.1)
m.camera.heard("10.0.0.99", json.dumps(kit.msg()).encode())
tick(0.1)
check("another's fish from somewhere that isn't one of yours: not heard", not m.aquarium.others)
m.camera.heard("127.0.0.1", json.dumps(kit.msg(watched=True)).encode())
tick(0.1)
check(f"...from the Kitchen's: heard, and its tank joins this one ({m.aquarium.grid.cells})",
      m.aquarium.grid.cells == {"Den": (0, 0), "Kitchen": (1, 0)})
check("...the Kitchen's being watched: so is this one now", m.fish_watched(fake[0]))
m.aquarium.fish.update(x=1.5, y=0.5, goal=None, via=None)      # (in the Kitchen's tank, for now)
tick(4.9)
check(f"the Kitchen not heard for a while: its tank's gone ({m.aquarium.grid.cells})",
      m.aquarium.grid.cells == {"Den": (0, 0)} and not m.aquarium.others)
check(f"...and the Den's fish, in it then, is home ({m.aquarium.fish['x']:.2f}, {m.aquarium.fish['y']:.2f})",
      inside(m.aquarium.grid, m.aquarium.fish["x"], m.aquarium.fish["y"]))
heard_all()
m.set_setting("share", "Off")
m.camera.heard("127.0.0.1", json.dumps(kit.msg()).encode())
m.fish_said = 0.0
tick(0.1)
check("sharing off: nothing heard, nobody told", not m.aquarium.others and heard_all() == [])
m.set_setting("share", "On")

# the web page's (the control server's thread asks; what the main loop made)
m.camera.heard("127.0.0.1", json.dumps(kit.msg()).encode())
tick(0.1)
web = m.web_fish()
check(f"the web page's Fish Tank: every tank, with its colour ({[(t['name'], t['c'], t['r'], t['colour']) for t in web['tanks']]})",
      [(t["name"], t["c"], t["r"], t["me"]) for t in web["tanks"]] == [("Den", 0, 0, True), ("Kitchen", 1, 0, False)]
      and web["tanks"][0]["colour"] == SF.hex_colour(dict(SF.ACCENTS)["Teal"])
      and web["tanks"][1]["colour"] == SF.hex_colour(dict(SF.ACCENTS)["Gold"]))
check(f"...every fish ({[(f['name'], f['kind']) for f in web['fish']]})",
      sorted((f["name"], f["kind"]) for f in web["fish"]) == [("Den", m.aquarium.kind), ("Kitchen", "Clownfish")]
      and web["cols"] == 2 and web["rows"] == 1 and web["sharing"] is True)
check("...and someone's watching now: the others told so", m.fish_watched(fake[0]))
pic = m.web_fish_pic("Clownfish", "3", "96")
im = Image.open(io.BytesIO(pic)) if pic else None
check(f"...a fish's picture: a PNG, facing right ({im and im.size})", im is not None and im.mode == "RGBA"
      and im.width >= 96 and m.web_fish_pic("Clownfish", "3", "96") is pic)
check("...not one of the fish: none", m.web_fish_pic("Shark", "0", "96") is None and m.web_fish_pic("Betta", "x", "96") is None)
r = m.web_command({"cmd": "fishfeed", "tank": "Kitchen"})
check(f"...food dropped in the Kitchen's tank ({r})", r == {"ok": True} and len(m.aquarium.food) >= F.FOOD_FLAKES
      and all(1 < fl["x"] < 2 for fl in m.aquarium.food[-F.FOOD_FLAKES:]))
r = m.web_command({"cmd": "fishfeed", "tank": "Attic"})
check(f"...in one that isn't there: said ({r})", "isn't there" in r.get("error", ""))
r = m.web_command({"cmd": "fishgrid", "cells": {"Den": [1, 0], "Kitchen": [0, 0]}})
check(f"...the tanks arranged: side by side, the Kitchen first ({r}, {m.aquarium.grid.cells})",
      r == {"ok": True} and m.aquarium.grid.cells == {"Den": (1, 0), "Kitchen": (0, 0)}
      and m.setting("fish_grid")["cells"] == {"Den": [1, 0], "Kitchen": [0, 0]})
tick(0.1)
told = heard_all()
check("...and the Kitchen's told at once", told and told[-1]["grid"]["cells"] == {"Den": [1, 0], "Kitchen": [0, 0]})
for bad in ({"Den": [0, 0.5]}, {"Den": [True, 0]}, ["Den"], {"Den": [0, 99]}):
    r = m.web_command({"cmd": "fishgrid", "cells": bad})
    if "isn't a grid" not in r.get("error", ""):
        check(f"...{bad}: not a grid ({r})", False)
check("...what isn't a grid: said, the grid as it was", m.aquarium.grid.cells == {"Den": (1, 0), "Kitchen": (0, 0)})
m2 = g.Media()
check(f"...kept for next time ({m2.aquarium.stored})", m2.aquarium.stored == {"Den": [1, 0], "Kitchen": [0, 0]}
      and m2.aquarium.seed == m.aquarium.seed)


SF.time = time                                         # (the real clock again, for the real main loop)


# ---- the web page, in a real browser ------------------------------------------------------------------------------
class UI:
    def write(self, *a): pass
    def syn(self): pass


m3 = g.Media(); m3.enter()
control = g.Control()
server = g.serve_control(m3, control, port=0, key="k" * 32)
done = threading.Event()
errors = []


def loop():
    try:
        g.run(UI(), m3, control, stop=done.is_set)
    except Exception as ex:
        import traceback; traceback.print_exc(); errors.append(ex)


threading.Thread(target=loop, daemon=True).start()
time.sleep(0.4)
m3.pie.hear("127.0.0.1", {"pietato": 1, "id": "kitchen00000", "port": port, "host": "Kitchen", "accent": "Gold"})
m3.pie.hear("127.0.0.1", {"pietato": 1, "id": "bedroom00000", "port": port + 1, "host": "Bedroom", "accent": "Pink"})
others = [Peer("Kitchen", "kitchen00000", "Clownfish", "Gold", 3), Peer("Bedroom", "bedroom00000", "Betta", "Pink", 5)]


def peers():
    """The Kitchen's and the Bedroom's Pietatos: their fish, told to this one (by its beacons' listener) and each
    other, and this one's heard (on the beacons' port, as its main loop tells it)."""
    while not done.is_set():
        now = time.monotonic()
        for o in others:
            o.aquarium.tick(0.1)
        for msg in heard_all(0.02):
            for o in others:
                o.fish_take(msg, now)
        for o in others:
            for p in others:
                if p is not o:
                    o.fish_take(p.msg(), now)
            m3.camera.heard("127.0.0.1", json.dumps(o.msg(watched=True)).encode())
        time.sleep(0.1)


threading.Thread(target=peers, daemon=True).start()
check("this one and two more: one grid of three", until(lambda: len(m3.aquarium.grid.cells) == 3))
import logging; logging.getLogger("werkzeug").setLevel(logging.ERROR)
sys.path.append(ROOT + "/pitato")
import webui
webui.HOME = H; webui.STATIC = S + "/static"; os.makedirs(webui.STATIC + "/fonts")
for f in os.listdir(ROOT + "/static/fonts"):
    shutil.copy(ROOT + "/static/fonts/" + f, webui.STATIC + "/fonts/")
webui.FONTS_DIR = webui.STATIC + "/fonts"
open(S + "/control-key", "w").write("k" * 32)
webui.STATE_FILE = g.STATE_FILE; webui.NET_ROOT = g.NET_ROOT
webui.CONTROL = ("127.0.0.1", server.server_address[1]); webui.CONTROL_KEY = S + "/control-key"
client = webui.app.test_client()
r = client.get("/api/pi/fish")
check(f"the page's Fish Tank: only the page asks for it ({r.status_code})", r.status_code == 403)
r = client.get("/api/pi/fish", headers={"X-Pitato-Page": "1"})
check(f"...the page: the grid ({r.status_code}, {[t['name'] for t in (r.get_json() or {}).get('tanks', [])]})",
      r.status_code == 200 and len(r.get_json()["tanks"]) == 3)
r = client.get("/api/pi/fishpic?name=Betta&id=2&size=96")
check(f"...a fish's picture loads without asking that way, and is kept ({r.status_code}, {r.mimetype}, "
      f"{r.headers.get('Cache-Control')})", r.status_code == 200 and r.mimetype == "image/png"
      and "max-age" in r.headers.get("Cache-Control", ""))
r = client.post("/api/pi/fishgrid", json={"cells": {"Den": [0, 0], "Bedroom": [1, 0], "Kitchen": [0, 1]}},
                headers={"X-Pitato-Page": "1"})
check(f"...arranged from the page: an L ({r.get_json()})", r.status_code == 200
      and until(lambda: m3.aquarium.grid.cells == {"Den": (0, 0), "Bedroom": (1, 0), "Kitchen": (0, 1)}))
check("...the others have it too", until(lambda: all(o.aquarium.grid.cells == m3.aquarium.grid.cells for o in others)))
PORT = 5469
threading.Thread(target=lambda: webui.app.run(host="127.0.0.1", port=PORT, threaded=True), daemon=True).start()
time.sleep(1)
from playwright.async_api import async_playwright


async def page():
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        pg = await b.new_page(viewport={"width": 1280, "height": 860})
        oops = []
        pg.on("pageerror", lambda e: oops.append(str(e)))
        await pg.goto(f"http://127.0.0.1:{PORT}/#library")
        await pg.wait_for_selector(".ltab", timeout=10000)
        await pg.click(".ltab:has-text('Fish Tank')")
        await pg.wait_for_selector(".ft-stage canvas", timeout=5000)
        await pg.wait_for_function("FT.data && FT.data.tanks.length === 3", timeout=5000)
        await asyncio.sleep(1.5)
        await pg.screenshot(path=S + "/fish_web.png")
        info = await pg.evaluate("""(() => {
          const c = FT.cv, x = c.getContext("2d"), w = c.width, h = c.height;
          const water = (c0, r0) => {     // (of 25 points in a cell, above its sand: how many are water)
            let n = 0;
            for (let i = 0; i < 5; i++) for (let j = 0; j < 5; j++) {
              const p = x.getImageData(Math.floor((c0 + 0.1 + 0.2 * i) * w / 2), Math.floor((r0 + 0.15 + 0.15 * j) * h / 2), 1, 1).data;
              if (p[3] === 255 && p[2] > p[0] + 30) n++;
            }
            return n;
          };
          const none = x.getImageData(Math.floor(0.75 * w), Math.floor(0.75 * h), 1, 1).data[3];
          return {w, h, hint: FT.hint.textContent, sub: FT.sub.textContent, den: water(0, 0), bed: water(1, 0),
                  kit: water(0, 1), none, pics: Object.values(FT.pics).filter((i) => i.complete && i.naturalWidth).length};
        })()""")
        check(f"the page: the grid drawn, {info['w']} x {info['h']} ({info['sub']}; {info['hint']})",
              info["sub"] == "3 tanks, joined up" and info["hint"] == "Tap a tank to feed it."
              and abs(info["w"] / info["h"] - 4 / 3) < 0.02)
        check(f"...water in each tank ({info['den']}, {info['bed']}, {info['kit']} of 25 points), nothing where there's "
              f"none ({info['none']})", min(info["den"], info["bed"], info["kit"]) >= 20 and info["none"] == 0)
        check(f"...the fish, from the Pi's pictures of them ({info['pics']})", info["pics"] >= 2)
        food = len(m3.aquarium.food)
        cv = await pg.eval_on_selector(".ft-stage canvas", "c => { const b = c.getBoundingClientRect(); "
                                                           "return [b.left, b.top, b.width, b.height]; }")
        await pg.mouse.click(cv[0] + cv[2] * 0.75, cv[1] + cv[3] * 0.2)
        fed = await asyncio.to_thread(until, lambda: len(m3.aquarium.food) >= food + F.FOOD_FLAKES)
        await asyncio.sleep(0.3)
        check(f"...a tap on the Bedroom's tank: food in it ({await pg.text_content('#toast')})", fed
              and await pg.text_content("#toast") == "Food in Bedroom's tank")
        await pg.click(".ft-bar button")
        await asyncio.sleep(0.3)
        lay = await pg.evaluate("ftLayout()")
        check(f"Arrange: the tanks as tiles, a place free all round ({lay}; {await pg.text_content('.ft-hint')})",
              await pg.text_content(".ft-bar button") == "Done" and (lay["cols"], lay["rows"], lay["off"]) == (4, 4, 1))
        await pg.screenshot(path=S + "/fish_web_arrange.png")

        async def spot(c, r):
            """The middle of place (c, r) of Arrange's, on the page."""
            box = await pg.eval_on_selector(".ft-stage canvas", "c => { const b = c.getBoundingClientRect(); "
                                                                "return [b.left, b.top, b.width, b.height]; }")
            lay = await pg.evaluate("ftLayout()")
            return box[0] + box[2] / lay["cols"] * (c + 0.5), box[1] + box[3] / lay["rows"] * (r + 0.5)

        sx, sy = await spot(2, 1)                                # (the Bedroom: (1, 0), one place in)
        tx, ty = await spot(1, 3)                                # (under the Kitchen)
        await pg.mouse.move(sx, sy)
        await pg.mouse.down()
        for k in range(1, 11):
            await pg.mouse.move(sx + (tx - sx) * k / 10, sy + (ty - sy) * k / 10)
            await asyncio.sleep(0.02)
        await pg.mouse.up()
        col = {"Den": (0, 0), "Kitchen": (0, 1), "Bedroom": (0, 2)}
        check(f"...the Bedroom's dragged under the Kitchen's: one column ({m3.aquarium.grid.cells})",
              await asyncio.to_thread(until, lambda: m3.aquarium.grid.cells == col))
        check("...kept, and the others have it too", m3.setting("fish_grid")["cells"] == {k: list(v) for k, v in col.items()}
              and await asyncio.to_thread(until, lambda: all(o.aquarium.grid.cells == col for o in others)))
        await asyncio.sleep(0.3)
        sx, sy = await spot(1, 1)                                # (the Den onto the Kitchen: they swap)
        tx, ty = await spot(1, 2)
        await pg.mouse.move(sx, sy)
        await pg.mouse.down()
        await pg.mouse.move(tx, ty, steps=8)
        await pg.mouse.up()
        swap = {"Kitchen": (0, 0), "Den": (0, 1), "Bedroom": (0, 2)}
        check(f"...one dropped on another: they swap ({m3.aquarium.grid.cells})",
              await asyncio.to_thread(until, lambda: m3.aquarium.grid.cells == swap))
        await pg.click(".ft-bar button")
        await pg.wait_for_function("FT.data && FT.data.rows === 3 && FT.data.cols === 1", timeout=5000)
        await asyncio.sleep(1.0)
        await pg.screenshot(path=S + "/fish_web_column.png")
        tall = await pg.evaluate("[FT.cv.width, FT.cv.height]")
        check(f"Done: the column drawn ({tall})", abs(tall[1] / tall[0] - 3 * 3 / 4) < 0.05)
        await pg.click(".ft-bar button")
        await asyncio.sleep(0.3)
        shown = await pg.evaluate("!FT.gaps.hidden")
        await pg.evaluate("""(v) => { const r = document.querySelector(".ft-gap input[data-i='1']");
                                      r.value = v; r.dispatchEvent(new Event("input")); }""", "20")
        got = await asyncio.to_thread(until, lambda: m3.aquarium.gap == (0.0, 0.2))
        check(f"Arrange's Space between screens: down, a fifth of a screen ({shown}; {m3.aquarium.gap})", shown
              and got and m3.setting("fish_grid")["gap"] == [0.0, 0.2])
        check("...the others have it too", await asyncio.to_thread(
            until, lambda: all(o.aquarium.gap == (0.0, 0.2) for o in others)))
        await asyncio.sleep(0.4)
        await pg.screenshot(path=S + "/fish_web_gaps_arrange.png")
        await pg.click(".ft-bar button")
        await pg.wait_for_function("FT.data && FT.data.gap && FT.data.gap[1] === 0.2", timeout=5000)
        await asyncio.sleep(1.0)
        await pg.screenshot(path=S + "/fish_web_gaps.png")
        tall = await pg.evaluate("[FT.cv.width, FT.cv.height]")
        empty = await pg.evaluate("""(() => { const c = FT.cv, x = c.getContext("2d");
          return x.getImageData(Math.floor(c.width / 2), Math.floor(c.height * 1.1 / 3.4), 1, 1).data[3]; })()""")
        check(f"...drawn with it between them, nothing there ({tall}, {empty})",
              abs(tall[1] / tall[0] - 3.4 * 3 / 4) < 0.05 and empty == 0)
        ph = await b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True,
                              has_touch=True)
        await ph.goto(f"http://127.0.0.1:{PORT}/#library")
        await ph.wait_for_selector(".ltab", timeout=10000)
        await ph.click(".ltab:has-text('Fish Tank')")
        await ph.wait_for_function("FT.data && FT.data.tanks.length === 3", timeout=5000)
        await asyncio.sleep(1.0)
        await ph.screenshot(path=S + "/fish_web_phone.png")
        check("...a phone: no sideways scrolling", await ph.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        check(f"...nothing went wrong on the page ({oops})", not oops)
        await b.close()


asyncio.run(page())
done.set()
check("the loop ran without trouble", not errors)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
