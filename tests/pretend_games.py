"""Pretend games for the AI player's tests (tests/test_instincts.py, tests/test_start_screens.py,
tests/test_learned.py), and a way to play them in the game's own time. Race: a pseudo-3D racing game. Level: a side-scrolling platformer. Room: a top-down room
(an RPG's: nothing moves till you walk). Flow: any of them from its start, the way real games start: logos, a title
screen, menus, pages of text, a name to put in, a coin, a moment with nothing to press; then the game, where Start
pauses it. flows(): a few such starts, by name. Pretend decision models: one that isn't answering, one that knows
what to press (after a while each time), one that always says the same, one that picks anything. SimIO: what the
player (pitato/anygame.py) needs of pitato/gameai.py's GameIO, on a pretend game, with a clock of its own: the game
moves on only as the player looks and waits, so a minute and a half of play takes a second or two, and comes out the
same each time. play(): one try, and how it went."""
import math
import random
import sys
import threading

import numpy as np
from PIL import Image

from paths import ROOT

sys.path.insert(0, ROOT)
from pitato import anygame as AG, gameai as A, instincts as I   # noqa: E402

W, H = 256, 224


# ---- a racing game ---------------------------------------------------------------------------------------------------
class Race:
    """A pseudo-3D racing game: the road's middle bends by its curvature, the camera behind the car; the car's
    across the road (px, metres from the middle), its speed, how far it's gone. Off the road it's slow; the wall
    stops it."""
    W, H, HORIZON, CAM, F = 256, 224, 90, 1.5, 160.0
    R, WALL = 4.0, 6.5                               # the road's half-width, and the wall from the middle
    VMAX = 50.0

    def __init__(self, split=False, dirt=False, curves=None):
        self.split, self.dirt = split, dirt
        self.curves = curves or [(300, 0.0), (400, 0.004), (200, 0.0), (400, -0.005), (200, 0.0), (300, 0.006),
                                 (300, -0.006), (250, 0.0), (350, 0.005), (300, -0.004)]
        self.z, self.px, self.v = 0.0, 0.0, 0.0
        self.held, self.sticks = set(), {}
        self.gas, self.brake = "b", "y"
        self.on_road = self.frames = self.crashes = 0
        self.title = False
        self.view_h = 112 if split else self.H

    def k(self, z):
        z %= sum(n for n, _ in self.curves)
        for n, k in self.curves:
            if z < n:
                return k
            z -= n
        return 0.0

    def steer(self):
        if "lx" in self.sticks:
            return self.sticks["lx"] / 127.0
        return ("right" in self.held) - ("left" in self.held)

    def step(self, dt=1 / 60):
        self.frames += 1
        if self.title:
            self.title = "start" not in self.held
            return
        gas, brake = self.gas in self.held, self.brake in self.held
        v = self.v + (12.0 if gas else -3.0) * dt - (20.0 if brake else 0.0) * dt
        off = abs(self.px) > self.R
        if off and v > 18.0:
            v -= 25.0 * dt
        self.v = max(-5.0, min(self.VMAX, v))
        self.px += (self.steer() * (3.0 + 0.25 * abs(self.v)) - self.k(self.z) * self.v * self.v * 0.6) * dt
        if abs(self.px) > self.WALL:
            self.px = math.copysign(self.WALL, self.px)
            if abs(self.v) > 5:
                self.crashes += 1
            self.v = 0.0
        self.z += self.v * dt
        self.on_road += not off

    def frame(self):
        W, H = self.W, self.view_h
        img = np.zeros((self.H, W, 3), np.uint8)
        if self.title:
            img[:] = (20, 20, 80)
            img[60:90, 60:196] = (220, 200, 40)
            if (self.frames // 30) % 2:
                img[150:160, 90:166] = (255, 255, 255)
            return Image.fromarray(img)
        horizon = self.HORIZON * H // self.H
        img[:horizon] = (100, 150, 255)
        xs = np.arange(W)
        cum, step_d = [], 1.0                                 # the road's middle, ahead: where it's bent to
        off, slope, d = 0.0, 0.0, 0.0
        for i in range(400):
            cum.append(off)
            slope += self.k(self.z + d) * step_d
            off += slope * step_d
            d += step_d
        for y in range(horizon + 1, H):
            D = self.CAM * self.F / (y - horizon) * (H / self.H)
            if D > 399:
                D = 399
            cx = W / 2 + (cum[int(D)] - self.px) * self.F / D
            half = self.R * self.F / D
            rum = 0.4 * self.F / D
            band = int((self.z + D) / 8) % 2
            if self.dirt:
                grass, road = ((70, 150, 50) if band else (60, 135, 45)), ((150, 110, 60) if band else (140, 102, 55))
            else:
                grass, road = ((40, 160, 40) if band else (30, 140, 30)), ((110, 110, 110) if band else (100, 100, 100))
            row = np.empty((W, 3), np.uint8)
            row[:] = grass
            dist = np.abs(xs - cx)
            row[dist < half] = road
            if not self.dirt:
                row[(dist >= half) & (dist < half + rum)] = (200, 30, 30) if band else (230, 230, 230)
                if band and D < 60:
                    row[dist < 0.12 * self.F / D] = (240, 240, 240)
            img[y] = row
        cy = H - 46 * H // self.H                              # the car, at the bottom in the middle
        img[cy:cy + 22, 112:144] = (200, 20, 20)
        img[cy + 14:cy + 22, 108:116] = img[cy + 14:cy + 22, 140:148] = (10, 10, 10)
        img[cy + 2:cy + 8, 118:138] = (60, 60, 90)
        if self.split:                                         # a black bar, then a map of the track below
            img[H:H + 4] = (0, 0, 0)
            img[H + 4:] = (30, 90, 30)
            for t in range(0, 360, 3):
                x = int(128 + 90 * math.cos(math.radians(t)))
                yy = int(H + 4 + 50 + 40 * math.sin(math.radians(t)))
                if H + 4 <= yy < self.H:
                    img[yy, max(0, x - 2):x + 2] = (160, 160, 160)
            a = (self.z / 1000.0) % 1 * 2 * math.pi
            img[int(H + 54 + 40 * math.sin(a)) - 2:int(H + 54 + 40 * math.sin(a)) + 2,
                int(128 + 90 * math.cos(a)) - 2:int(128 + 90 * math.cos(a)) + 2] = (255, 0, 0)
        return Image.fromarray(img)


# ---- a platformer ---------------------------------------------------------------------------------------------------
class Level:
    """A side-scrolling platformer: 16-pixel tiles, the floor two tiles deep, pipes to jump over, pits, enemies
    walking at you (jump on them, or they get you); the camera follows. Falling in a pit, or into an enemy: back to
    the last checkpoint."""
    W, H, T = 256, 224, 16

    def __init__(self, length=200):
        self.length = length
        self.pipes = {20: 2, 42: 3, 68: 2, 72: 3, 96: 4, 120: 2, 150: 3, 175: 4}
        self.pits = [(30, 3), (58, 2), (85, 4), (108, 3), (135, 3), (162, 4)]
        self.enemies = [[50 * 16.0, 1], [115 * 16.0, 1], [140 * 16.0, 1], [185 * 16.0, 1]]
        self.x, self.y, self.vx, self.vy = 3 * 16.0, 12 * 16.0 - 24, 0.0, 0.0
        self.ground = True
        self.held = set()
        self.deaths, self.best, self.frames = 0, 0.0, 0
        self.jumped = False
        self.frozen = 0

    def solid(self, tx, ty):
        if tx < 0:
            return True
        if ty >= 12:
            return not any(s <= tx < s + w for s, w in self.pits)
        h = self.pipes.get(tx) or self.pipes.get(tx - 1)
        return bool(h) and ty >= 12 - h

    def die(self):
        self.deaths += 1
        cp = max(3, (int(self.x // 16) // 25) * 25 + 3)
        while not self.solid(cp, 12) or self.solid(cp, 11):
            cp += 1
        self.x, self.y, self.vx, self.vy = cp * 16.0, 12 * 16.0 - 24, 0.0, 0.0
        self.frozen = 40

    def step(self):
        self.frames += 1
        if self.frozen:
            self.frozen -= 1
            return
        run, jump = "y" in self.held, "b" in self.held
        want = ("right" in self.held) - ("left" in self.held)
        self.vx = want * (2.5 if run else 1.5)
        if jump and self.ground and not self.jumped:
            self.vy, self.ground, self.jumped = -6.0, False, True
        if not jump:
            self.jumped = False
        self.vy += 0.22 if (jump and self.vy < 0) else 0.6
        self.vy = min(self.vy, 8.0)
        nx = self.x + self.vx                                   # across: pipes stop it
        top, bottom = int(self.y // 16), int((self.y + 23) // 16)
        lead = int((nx + 13) // 16) if self.vx > 0 else int(nx // 16)
        if not any(self.solid(lead, ty) for ty in range(top, bottom + 1)):
            self.x = nx
        ny = self.y + self.vy                                   # up and down: floors and pipe tops
        self.ground = False
        if self.vy > 0:
            feet = int((ny + 24) // 16)
            if any(self.solid(tx, feet) for tx in (int(self.x // 16), int((self.x + 13) // 16))):
                ny, self.vy, self.ground = feet * 16 - 24.0, 0.0, True
        self.y = ny
        if self.y > self.H + 40:
            return self.die()
        for e in self.enemies:                                  # enemies: walk at you; jumped on, they're gone
            if e[1]:
                e[0] -= 0.6
                if abs(e[0] - self.x) < 14 and 12 * 16 - 14 - 24 <= self.y <= 12 * 16 - 14 + 4:
                    if self.vy > 0 and self.y < 12 * 16 - 14 - 12:
                        e[1], self.vy = 0, -4.0
                    else:
                        return self.die()
        self.best = max(self.best, self.x)

    def frame(self):
        W, H = self.W, self.H
        cam = max(0.0, self.x - 112)
        img = np.zeros((H, W, 3), np.uint8)
        img[:] = (100, 150, 255)
        img[8:16, 8:80] = (255, 255, 255)                       # (a score along the top)
        for sx in range(W):
            tx = int((sx + cam) // 16)
            if self.solid(tx, 12):
                img[192:, sx] = (180, 100, 40) if (tx % 2) else (160, 88, 36)
            h = self.pipes.get(tx) or self.pipes.get(tx - 1)
            if h:
                img[192 - 16 * h:192, sx] = (40, 180, 60)
        for e in self.enemies:
            if e[1]:
                ex = int(e[0] - cam)
                if -16 < ex < W:
                    img[178:192, max(0, ex):max(0, ex + 14)] = (120, 30, 20)
        px, py = int(self.x - cam), int(self.y)
        if py < H:
            img[max(0, py):max(0, py + 12), px:px + 14] = (220, 40, 40)
            img[max(0, py + 12):max(0, min(H, py + 24)), px:px + 14] = (40, 40, 200)
        return Image.fromarray(img)


class FairLevel(Level):
    """The level, but its enemies walk on while you're put back at a checkpoint (else one can stand on the checkpoint
    and get you over and over, with nothing on the screen moving)."""

    def step(self):
        if self.frozen:
            for e in self.enemies:
                if e[1]:
                    e[0] -= 0.6
        super().step()


# ---- a top-down room ------------------------------------------------------------------------------------------------
class Room:
    """A top-down room (an RPG's): nothing moves till you walk; the view scrolls as you do. A wall all round."""

    def __init__(self):
        self.x, self.y, self.held, self.sticks, self.frames, self.walked = 400.0, 300.0, set(), {}, 0, 0.0
        self.map = np.random.default_rng(3).integers(0, 4, size=(60, 80))

    def step(self):
        self.frames += 1
        dx = ("right" in self.held) - ("left" in self.held)
        dy = ("down" in self.held) - ("up" in self.held)
        nx, ny = min(1200.0, max(80.0, self.x + 1.5 * dx)), min(880.0, max(80.0, self.y + 1.5 * dy))
        self.walked += abs(nx - self.x) + abs(ny - self.y)
        self.x, self.y = nx, ny

    def frame(self):
        img = np.zeros((H, W, 3), np.uint8)
        cx, cy = int(self.x) - W // 2, int(self.y) - H // 2
        ys, xs = np.mgrid[0:H, 0:W]
        tile = self.map[((ys + cy) // 16) % 60, ((xs + cx) // 16) % 80]
        img[..., 0] = 60 + tile * 30
        img[..., 1] = 120 + tile * 20
        img[..., 2] = 60
        img[H // 2 - 8:H // 2 + 8, W // 2 - 6:W // 2 + 6] = (220, 40, 40)
        return Image.fromarray(img)


# ---- a game from its start ------------------------------------------------------------------------------------------
class Flow:
    """A game from its start: stages got through one after another, then the game itself (inner). A stage is a dict:
    kind logo (frames it lasts; skip: buttons that skip it), title or coin (go: buttons that start it; blink: PRESS
    START blinks; moving: its background scrolls; demo: frames till its own demo plays, the game going by), menu (n
    things to pick, right: the one that goes on, dull: ones that do nothing, go: buttons that pick; any other leads
    somewhere B or a pick gets back from), text (pages, go; print: frames a page takes to appear), name (go types a
    letter, done jumps to OK), wait (frames: nothing to press). In the game, Start pauses it (pause), with nothing to
    show for it; a level done shows its tally (still) till a button (tally: which ones; any that plays, or Start, if
    not said), then the next level. system: the console (its jump and run buttons work the pretend level's, its gas
    and brake the race's)."""

    def __init__(self, inner, stages, pause=True, system="snes", tally=None):
        self.inner, self.stages, self.pause, self.tally = inner, list(stages) + [{"kind": "play"}], pause, tally
        self.system = system
        lib = dict(AG.BUTTONS.get(system, AG.NINTENDO))
        roles = I.roles_for(system, [label for label, _ in AG.BUTTONS.get(system, AG.NINTENDO)], "")
        self.remap = {}                          # this console's jump and run buttons: the pretend level's
        if isinstance(inner, Level):
            if lib.get(roles.get("jump")):
                self.remap[lib[roles["jump"]]] = "b"
            if lib.get(roles.get("run")):
                self.remap[lib[roles["run"]]] = "y"
        elif isinstance(inner, Race):
            inner.gas, inner.brake = lib.get(roles.get("gas")) or "b", lib.get(roles.get("brake")) or "y"
        self.at, self.t, self.frames = 0, 0, 0
        self.held, self.sticks, self.was = set(), {}, set()
        self.paused, self.pauses = False, 0
        self.paused_frames = self.paused_run = self.paused_longest = 0
        self.sub = {}
        self.presses = []                        # [(frame, button)]: every button as it went down
        self.reached = {}                        # stage: the frame it was reached at
        self.cleared, self.levels, self.done = 0, 0, 0.0   # (a level done: its tally up; how many, how far in all)
        self.wrong = 0                           # times it went somewhere it shouldn't (a menu's wrong pick)

    @property
    def stage(self):
        return self.stages[self.at]

    @property
    def playing(self):
        return self.stage["kind"] == "play"

    def go(self):
        self.at += 1
        self.t, self.sub = 0, {}
        self.reached[self.at] = self.frames

    def step(self):
        self.frames += 1
        new = self.held - self.was
        self.was = set(self.held)
        self.presses += [(self.frames, b) for b in sorted(new)]
        st, k = self.stage, self.stage["kind"]
        self.t += 1
        if k == "play":
            self.play_step(new)
        elif k == "logo":
            if self.t >= st["frames"] or (new & set(st.get("skip", ())) and self.t > 20):
                self.go()
        elif k == "wait":
            if self.t >= st["frames"]:
                self.go()
        elif k in ("title", "coin"):
            demo = st.get("demo")
            if demo and self.t > demo:               # (its own demo: any button, back to the title)
                if new or self.t > demo + 600:
                    self.t = 0
            elif new & set(st["go"]) and self.t > 10:
                self.go()
        elif k == "menu":
            cur = self.sub.setdefault("cur", st.get("first", 0))
            if self.sub.get("dead"):                 # (somewhere it shouldn't be: B or a pick gets back)
                if new & ({"b"} | set(st["go"])):
                    self.sub["dead"] = False
            elif "down" in new:
                self.sub["cur"] = (cur + 1) % st["n"]
            elif "up" in new:
                self.sub["cur"] = (cur - 1) % st["n"]
            elif new & set(st["go"]) and self.t > 8:
                if cur == st.get("right", 0):
                    self.go()
                elif cur not in st.get("dull", ()):  # (a dull one does nothing: CONTINUE, with nothing saved)
                    self.sub["dead"] = True
                    self.wrong += 1
        elif k == "text":
            page, shown, full = self.sub.setdefault("page", 0), self.sub.setdefault("shown", 0), st.get("print", 40)
            self.sub["shown"] = min(full, shown + 1)
            if new & set(st["go"]):
                if self.sub["shown"] < full:         # (still appearing: all of it at once)
                    self.sub["shown"] = full
                elif page + 1 >= st["pages"]:
                    self.go()
                else:
                    self.sub["page"], self.sub["shown"] = page + 1, 0
        elif k == "name":
            n, ok = self.sub.setdefault("n", 0), self.sub.setdefault("ok", False)
            if new & set(st.get("done", ("start",))):
                self.sub["ok"] = True
            elif new & set(st["go"]):
                if ok or n >= st.get("most", 7):
                    if n > 0:
                        self.go()
                else:
                    self.sub["n"] = n + 1

    def play_step(self, new):
        if self.cleared:                             # (the level's done: its tally, still, till a button; then the
            past = set(self.tally) if self.tally else {"start", "a"} | set(self.remap)           # next level)
            if new & past and self.t - self.cleared > 30:
                self.cleared, self.levels = 0, self.levels + 1
                self.done += self.inner.best
                self.inner = FairLevel()
                self.inner.pipes = {k + 3 * self.levels: v for k, v in self.inner.pipes.items()}
            return
        if isinstance(self.inner, Level) and self.inner.x >= (self.inner.length - 12) * 16:
            self.cleared = self.t
            return
        if self.pause and "start" in new:
            self.paused = not self.paused
            self.pauses += 1
        if self.paused:
            self.paused_frames += 1
            self.paused_run += 1
            self.paused_longest = max(self.paused_longest, self.paused_run)
            return
        self.paused_run = 0
        held = set(self.held)
        if self.remap:
            held = {b for b in self.held if b in ("left", "right", "up", "down")} | \
                   {self.remap[b] for b in self.held if b in self.remap}
        self.inner.held, self.inner.sticks = held, dict(self.sticks)
        self.inner.step()

    def frame(self):
        st, k = self.stage, self.stage["kind"]
        if k == "play":
            if self.cleared:
                img = np.zeros((H, W, 3), np.uint8)
                img[:] = (20, 20, 20)
                img[60:80, 70:186] = (255, 255, 255)
                img[110:122, 90:166] = (255, 220, 0)
                return Image.fromarray(img)
            img = self.inner.frame()
            if self.levels % 2:                      # (the next level: other colours)
                img = Image.fromarray(np.asarray(img)[..., ::-1].copy())
            return img
        img = np.zeros((H, W, 3), np.uint8)
        if k == "logo":
            fade = min(1.0, self.t / 30.0)
            img[:] = (int(240 * fade),) * 3
            img[90:130, 70:186] = (int(30 * fade), int(60 * fade), int(200 * fade))
        elif k == "wait":
            img[100:116, 90:170] = (255, 255, 255)
            n = 3 - min(2, self.t * 3 // max(1, st["frames"]))
            img[130:150, 120:120 + 8 * n] = (255, 220, 0)
        elif k in ("title", "coin"):
            demo = st.get("demo")
            if demo and self.t > demo:               # (its own demo: the game going by, its name over it)
                x = getattr(self.inner, "x", None)
                if x is not None:
                    self.inner.x = x + ((self.t - demo) % 600) * 2.0
                img = np.asarray(self.inner.frame()).copy()
                if x is not None:
                    self.inner.x = x
                img[20:36, 60:196] = (200, 60, 30)
                return Image.fromarray(img)
            img[:] = st.get("colour", (20, 20, 90))
            if st.get("moving"):                      # (its background scrolls by, on and on)
                xs = (np.arange(W) + self.t * 2) % 64
                img[110:, :, 1] = np.where(xs < 32, 70, 110)[None, :]
                ys = (np.arange(H - 110) * 3 + self.t) % 48
                img[110:, :, 2] = np.where(ys < 24, 60, 140)[:, None]
            img[40:90, 48:208] = (220, 190, 40) if k == "title" else (60, 200, 220)
            if not st.get("blink", True) or (self.t // 30) % 2:
                img[150:160, 80:176] = (255, 255, 255)
        elif k == "menu":
            img[:] = st.get("colour", (30, 60, 40))
            if self.sub.get("dead"):
                img[:] = (70, 30, 30)
                img[30:50, 40:216] = (220, 220, 220)
                for j in range(5):
                    img[70 + j * 24:82 + j * 24, 60:200] = (150, 150, 150)
                return Image.fromarray(img)
            img[24:44, 60:196] = (230, 230, 230)
            cur = self.sub.get("cur", st.get("first", 0))
            for j in range(st["n"]):
                y = 70 + j * 28
                img[y:y + 14, 90:190] = (120, 120, 120) if j in st.get("dull", ()) else (220, 220, 220)
                if j == cur:
                    img[y + 2:y + 12, 70:82] = (255, 60, 60)
            if st.get("moving"):
                xs = (np.arange(W) + self.t * 3) % 80
                img[190:, :, 0] = np.where(xs < 40, 40, 160)[None, :]
        elif k == "text":
            img[:] = st.get("colour", (40, 40, 40))
            img[20:120, 80:176] = (200, 150, 100)       # (someone talking)
            img[150:214, 10:246] = (245, 245, 245)
            page, shown, full = self.sub.get("page", 0), self.sub.get("shown", 0), st.get("print", 40)
            rng = np.random.default_rng(100 + self.at * 31 + page)
            for j in range(3):
                n = int(rng.integers(120, 220) * min(1.0, max(0.0, (shown - j * full / 3) / (full / 3))))
                for x in range(18, 18 + n, 8):
                    if rng.random() < 0.8:
                        img[158 + j * 18:168 + j * 18, x:x + 6] = (30, 30, 30)
            if shown >= full and (self.t // 20) % 2:
                img[204:210, 230:238] = (200, 0, 0)
        elif k == "name":
            img[:] = (20, 40, 80)
            img[20:40, 60:60 + 14 * 8] = (10, 10, 10)
            for j in range(self.sub.get("n", 0)):
                img[24:36, 64 + j * 14:74 + j * 14] = (255, 255, 255)
            for r in range(4):
                for c in range(10):
                    img[70 + r * 26:86 + r * 26, 24 + c * 21:40 + c * 21] = (190, 190, 210)
            img[180:200, 190:240] = (255, 220, 0) if self.sub.get("ok") else (120, 120, 60)
        return Image.fromarray(img)

    def hint(self):
        """What a good player presses now (for a pretend model that knows): a button, or "play"."""
        st, k = self.stage, self.stage["kind"]
        if k == "play":
            return "start" if self.paused or self.cleared else "play"
        if k in ("logo", "wait"):
            return (list(st.get("skip", ())) or ["wait"])[0]
        if k in ("title", "coin", "text"):
            return list(st["go"])[0]
        if k == "menu":
            if self.sub.get("dead"):
                return "b"
            return list(st["go"])[0] if self.sub.get("cur", st.get("first", 0)) == st.get("right", 0) else "down"
        if self.sub.get("n", 0) < 3:                 # (a name: a few letters, then OK)
            return list(st["go"])[0]
        return list(st["go"])[0] if self.sub.get("ok") else list(st.get("done", ("start",)))[0]

    def far(self):
        """How far it's got in the game itself: pixels of levels, metres of road, steps walked."""
        inner = self.inner
        return self.done + float(next(getattr(inner, n) for n in ("best", "z", "walked") if hasattr(inner, n)))


def flows():
    """{name: a function giving (the game's name, its console, a new Flow)}: the starts real games have."""
    logo = {"kind": "logo", "frames": 150, "skip": ["a", "start"]}
    return {
        "a title screen, then the level": lambda: ("Super Mario Bros. (World)", "nes", Flow(FairLevel(), [
            {"kind": "title", "go": ["start"], "demo": 480}, {"kind": "wait", "frames": 40}], system="nes")),
        "a logo, then a title screen that's all movement": lambda: ("Sonic The Hedgehog (USA)", "genesis", Flow(
            FairLevel(), [{"kind": "logo", "frames": 200}, {"kind": "title", "go": ["start"], "moving": True}],
            system="genesis")),
        "logos, a title screen, a file to pick, text": lambda: ("Kirby's Adventure (USA)", "nes", Flow(FairLevel(), [
            logo, logo, {"kind": "title", "go": ["start", "a"]}, {"kind": "menu", "n": 3, "go": ["a"]},
            {"kind": "text", "pages": 3, "go": ["a"]}], system="nes")),
        "a racing game's menus": lambda: ("Super Mario Kart (USA)", "snes", Flow(Race(), [
            {"kind": "title", "go": ["start"]}, {"kind": "menu", "n": 2, "go": ["b", "start"]},
            {"kind": "menu", "n": 3, "go": ["b"], "colour": (60, 30, 60)},
            {"kind": "menu", "n": 4, "go": ["b"], "colour": (30, 30, 80), "moving": True},
            {"kind": "wait", "frames": 180}], system="snes")),
        "an RPG's long start": lambda: ("Pokemon - Ruby Version (USA)", "gba", Flow(Room(), [
            dict(logo, frames=240), {"kind": "title", "go": ["start", "a"]}, {"kind": "menu", "n": 2, "go": ["a"]},
            {"kind": "text", "pages": 12, "go": ["a"], "print": 60}, {"kind": "name", "go": ["a"], "done": ["start"]},
            {"kind": "text", "pages": 4, "go": ["a"], "print": 60}], system="gba")),
        "an arcade game: a coin first": lambda: ("Mario Bros. Arcade", "neogeo", Flow(FairLevel(), [
            {"kind": "coin", "go": ["select"]}, {"kind": "title", "go": ["start"]},
            {"kind": "menu", "n": 4, "go": ["b"], "moving": True}], system="neogeo")),
        "a title screen only A starts": lambda: ("Mega Man 2 (USA)", "nes", Flow(FairLevel(), [
            {"kind": "title", "go": ["a"]}, {"kind": "menu", "n": 2, "go": ["a", "start"]}], system="nes")),
        "CONTINUE first, with nothing saved": lambda: ("Metroid Fusion (USA)", "gba", Flow(FairLevel(), [
            {"kind": "title", "go": ["start", "a"]}, {"kind": "menu", "n": 3, "go": ["a"], "right": 1, "dull": [0]}],
            system="gba")),
        "a game it doesn't know, text first": lambda: ("Zorblax Quest (USA)", "gba", Flow(Room(), [
            dict(logo, frames=180), {"kind": "title", "go": ["start"]}, {"kind": "menu", "n": 3, "go": ["a"]},
            {"kind": "text", "pages": 5, "go": ["a"]}], system="gba")),
    }


# ---- pretend decision models: (the game, its choices, the fallback) -> (pick, "model" or "own", seconds it took) ----
def silent(game, choices, fallback):
    """Its computer isn't answering."""
    return fallback, "own", 0.05


def knows(latency=1.2, wake=0.0):
    """One that sees what's on the screen and picks what a good player would, after a while each time (the first
    time, wake seconds more)."""
    first = [True]

    def model(game, choices, fallback):
        took = latency + (wake if first[0] else 0.0)
        first[0] = False
        want = game.hint()
        if want == "play":
            want = next((k for k in ("drive", "go_right", "fight_right", "shoot", "right_held") if k in choices),
                        fallback)
        keys = {b: AG.button_key(label) for label, b in AG.BUTTONS.get(game.system, AG.NINTENDO)}
        want = keys.get(want, want)                  # (the emulator's name for a button: this console's own for it)
        return (want if want in choices else fallback), "model", took
    return model


def always(pick, latency=0.8):
    """One that always picks the same (the first of pick that's among its choices)."""
    def model(game, choices, fallback):
        return next((k for k in ([pick] if isinstance(pick, str) else pick) if k in choices), fallback), "model", \
            latency
    return model


def muddled(latency=1.0, seed=1):
    """One that picks anything at all."""
    rnd = random.Random(seed)

    def model(game, choices, fallback):
        return rnd.choice(sorted(choices)), "model", latency
    return model


PLAYS = ("go_right", "drive", "fight_right", "shoot", "right_held")     # (what "it's being played" is, in each kind)


# ---- playing one, in the game's own time ---------------------------------------------------------------------------
class Owner:
    def __init__(self):
        self.stopping, self.model, self.server, self.offline = threading.Event(), "clef", "", False


class SimDecider:
    """The decision model, asked while the game goes on: its pick comes when its time's up (the game's time)."""

    def __init__(self, io):
        self.io, self.job, self.out = io, None, None

    def settle(self):
        if self.job is not None and self.io.t >= self.job[0]:
            self.out, self.job = self.job[1:], None

    def idle(self):
        self.settle()
        return self.job is None

    def ask(self, says, state, choices, fallback, picture, kind="live", quiet=True):
        pick, by, took = self.io.model(self.io.g, choices, fallback)
        self.io.asked.append({"kind": kind, "state": state, "choices": dict(choices), "says": says, "at": self.io.t,
                              "pick": pick, "by": by, "picture": picture})
        self.job = (self.io.t + took, pick, by)

    def take(self):
        self.settle()
        got, self.out = self.out, None
        return got

    def forget(self):
        self.job = self.out = None


class SimIO:
    """What the player needs of gameai's GameIO, on a pretend game, in the game's own time: now() is its clock, and
    the game steps 60 times for each second the player looks or waits. most: seconds to play, then Stop."""
    LOOK = 0.004                                     # seconds a look takes

    def __init__(self, game, model, most=90.0, resumed=False):
        self.g, self.model, self.most = game, model, most
        self.t, self.acc = 0.0, 0.0
        self.ai = Owner()
        self.held, self.pushed, self.sticks = set(), set(), {}
        self.blind, self.last_by = False, "model"
        self.asked, self.logged, self.statuses, self.taps = [], [], [], []
        self.pressed, self.was = [], set()               # [(when, button)]: every button as it went down
        self.run = type("Run", (), {"resumed": resumed})()
        self.looks = 0

    def now(self):
        return self.t

    def live(self):
        if self.ai.stopping.is_set() or self.t > self.most:
            raise A.emerald.Stop()

    def advance(self, secs):
        self.t += secs
        self.acc += secs * 60.0
        while self.acc >= 1.0:
            self.acc -= 1.0
            self.pressed += [(round(self.t, 2), b) for b in sorted(self.held - self.was)]
            self.was = set(self.held)
            self.g.held, self.g.sticks = set(self.held), dict(self.sticks)
            self.g.step()

    def look(self):
        self.live()
        self.looks += 1
        self.advance(self.LOOK)
        return A.Look(self.g.frame())

    def wait(self, secs):
        self.live()
        self.advance(secs)

    def hold_only(self, buttons, sticks=None):
        self.held, self.sticks = set(buttons), dict(sticks or {})

    def hold(self, b):
        self.held.add(b)

    def release(self, b):
        self.held.discard(b)

    def stick(self, axis, v):
        self.sticks[axis] = v

    def let_go(self):
        self.held, self.sticks = set(), {}

    def tap(self, b):
        self.live()
        self.taps.append((round(self.t, 2), b))
        self.held.add(b)
        self.advance(0.05)
        self.held.discard(b)
        self.advance(0.06)

    def decider(self):
        return SimDecider(self)

    def status(self, w):
        if not self.statuses or self.statuses[-1][1] != w:
            self.statuses.append((round(self.t, 1), w))

    def log(self, **e):
        self.logged.append(dict(e, t=round(self.t, 1)))

    def said(self, words):
        """Whether its log has an event with these words in it."""
        return any(words in str(e.get("event")) for e in self.logged)


def play_on(game, title, system, model, secs, resumed=False, coach=None, seed=7):
    """Any pretend game played for so many seconds of its own time: (its SimIO, the player)."""
    random.seed(seed)
    io = SimIO(game, model, secs, resumed)
    p = AG.AnyGame({"title": title, "system": system}, io, coach)
    try:
        p.play()
    except A.emerald.Stop:
        pass
    return io, p


def play(make, model, secs=90.0, resumed=False, coach=None, seed=7):
    """One try at a game from flows() (make), with a pretend model, for so many seconds of the game's time: how it
    went: {"io", "game", "player", "secs" (till the game itself was reached; None: never), "far", "levels",
    "paused" (seconds in all), "paused_longest", "pauses", "presses", "wrong"}."""
    title, system, game = make()
    start = game.far()
    io, p = play_on(game, title, system, model, secs, resumed, coach, seed)
    last = len(game.stages) - 1
    at = game.reached.get(last)
    return {"io": io, "game": game, "player": p, "secs": None if at is None else at / 60.0,
            "far": game.far() - start, "levels": game.levels, "paused": game.paused_frames / 60.0,
            "paused_longest": game.paused_longest / 60.0, "pauses": game.pauses,
            "presses": [(round(f / 60.0, 1), b) for f, b in game.presses], "wrong": game.wrong}
