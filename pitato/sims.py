"""Apps' little worlds: what they share, and Rock Paper Scissors (the Fish Tank: fishtank.py)."""
import math
import random

from .theme import co_mix
from .fine import detail, made_fine


# ---- Apps' little worlds to watch ---------------------------------------------------------------------
# Each sim runs in a box beside its numbers, or on the whole screen (SELECT, or START's Full screen). A
# pauses, X gives it a poke, Y starts it again, START has its options, B goes back to the list.
# Rock Paper Scissors: pieces bounce around, and one hit by its counter switches sides until one team is
# left (pick a winner before the first capture). fishtank.py has the Fish Tank.
SIM_FLOOR = (21, 27, 33)                      # the box
SIM_BOX = (12, 78, 452, 424)                  # ...on the GPi Case's screen (a wider one: the box is wider)
SIM_IN = 2                                    # pieces keep this far in from its wall
SIM_PANEL = (468, 78, 628, 424)               # the numbers, beside it
SIM_DIRTY = (SIM_BOX[0], SIM_BOX[1], SIM_PANEL[2], SIM_PANEL[3])   # what changes from one frame to the next
SIM_FPS, SIM_FPS_BIG = 20, 10                 # frames a second (a Pi Zero on a TV: fewer, each one scaled up)
SIM_SMOOTH = ((20, 0.5), (30, 0.5), (60, 0.25))   # a world that moves smoothly (Rock Paper Scissors): this many
                                              # instead, the most of them that a frame takes this machine no more
                                              # than this share of the time between (media mode times its frames)
SIM_SETTLE = 2.0                              # ...seconds at one rate before it's changed for another
SIM_KEEN = (0.85, 1.15)                       # ...up to a rate with this much of its share to spare; down from it
                                              # once it's this much over
SIM_SAMPLE = 0.2                              # seconds between a chart's points
SIM_FULL = ("full", "Full screen", ("Off", "On"), "Off")   # (the last row of every sim's START card)


def sim_clock(secs):
    """1:05"""
    return f"{int(secs) // 60}:{int(secs) % 60:02d}"


def sim_hue(h, s=0.45, v=1.0):
    import colorsys
    return tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h % 1.0, s, v))


class Sim:
    """A little world in a box, w x h px. update moves it on, draw puts it on the screen (the box's
    top-left at x0, y0), poke is X, restart is Y. Its options - (key, label, choices, default) - are
    START's card; values holds what you picked."""
    key = ""
    blurb = ""
    poke_label = None               # X: what it does, or None
    options = ()
    restart_for = ()                # options it starts again for
    pale_defaults = {}              # options it starts with on a light page (Settings > App pages) instead, till
                                    # you pick any of them: {key: choice}
    smooth = False                  # it moves smoothly: drawn more often where the machine has the time (SIM_SMOOTH)
    bare = False                    # drawn on the page itself, in the middle: no box, no numbers beside it
    paced = False                   # its picture changes now and then (frame_in says when), not frame by frame
    look_now = False                # what look() says is drawn the moment it changes (the numbers: 4 times a second)
    backdrop = SIM_FLOOR            # what's behind it on the whole screen

    def __init__(self, w, h, rng=None, values=None):
        self.w, self.h = w, h
        self.rng = rng or random.Random()
        self.values = {k: d for k, _, _, d in self.options}
        self.values.update(values or {})
        self.paused = False
        self.clock = self.sampled = 0.0
        self.history = []               # (seconds, counts...), for a chart
        self.started = {}               # the options it last started with (those it starts again for)

    def configure(self, values):
        """Your choices, put to use: True if it has to start again for them."""
        changed = {k for k, v in values.items() if self.values.get(k) != v}
        self.values.update(values)
        self.apply()
        return bool(changed & set(self.restart_for))

    def apply(self):
        pass

    def needs_restart(self):
        """An option it starts again for has changed since it last started."""
        return any(self.values.get(k) != self.started.get(k) for k in self.restart_for)

    def restart(self):
        self.clock = self.sampled = 0.0
        self.history = []
        self.started = {k: self.values.get(k) for k in self.restart_for}

    def refit(self, w, h):
        """The box changes size (full screen, and back)."""
        self.w, self.h = w, h
        self.restart()

    def relook(self):
        """The pages' look has changed (Settings > App pages): pictures it kept in the page's colours, thrown away."""

    def update(self, dt):
        return None

    def frame_in(self, wall):
        """A paced sim: seconds until its picture next changes (wall: time.time())."""
        return None

    def poke(self):
        pass

    def draw(self, img, x0, y0):
        pass

    def stats(self):
        """(label, value) rows for beside the box."""
        return []

    def chart(self):
        """(history, colours, top) for a chart beside the box, or None."""
        return None

    def note(self):
        """(title, words) for a card at the foot of the box, or None."""
        return None

    def note_top(self):
        """The card goes at the top of the box instead (out of the way of something at the foot)."""
        return False

    def hints(self):
        """Its buttons along the bottom, if it has its own: [(button, what it does)], or None."""
        return None

    def look(self):
        """Something that changes what's beside the box besides its numbers (drawn again when it does), or
        None."""
        return None

    def sample(self, counts):
        self.history.append((self.clock, tuple(counts)))
        if len(self.history) > 400:              # a long run: every other point
            self.history = self.history[:-1:2] + self.history[-1:]


# ---- Rock Paper Scissors ---------------------------------------------------------------------------------
RPS_TEAMS = ("Rock", "Scissors", "Paper")      # each one beats the next, and Paper beats Rock
RPS_COLOUR = ((154, 148, 139), (226, 123, 140), (127, 166, 222))      # ...their colours
RPS_ROCK_EDGE = (94, 89, 82)
RPS_SHEET, RPS_SHEET_EDGE = (230, 236, 241), (127, 142, 156)
RPS_BLADE, RPS_BLADE_EDGE = (201, 210, 217), (134, 146, 156)
RPS_COUNTS = (5, 10, 15, 20, 25, 30)                            # pieces per team
RPS_SIZES = (("Small", 10), ("Medium", 13), ("Large", 16))       # how big a piece is (its radius, px)
RPS_SPEEDS = (("Slow", 40), ("Normal", 70), ("Fast", 120), ("Very fast", 200))   # px a second
RPS_READY = 3               # seconds to pick a winner before a round starts
RPS_NEXT = 10               # seconds the winner shows, then the next round starts by itself
RPS_TURNS = 48              # the angles a piece is drawn at (each one drawn once, then kept)
RPS_EASE = 1.5              # how quickly a piece gets back to the speed (after a bump or a shake)
RPS_QUICK = [True]          # its pieces put on the picture PIL's inner way (draw): False once that hasn't worked
RPS_LOOKS = random.Random(5)
RPS_ROCKS = [[0.78 + RPS_LOOKS.random() * 0.22 for _ in range(10)] for _ in range(6)]   # six rocks' shapes


def rps_span(r):
    """How wide a piece's picture is (square): room for it at any angle."""
    return 2 * int(math.ceil(r * 1.1)) + 4


def rps_sprite(team, r, turn, look=0, span=None):
    """A piece of a team (0 rock, 1 scissors, 2 paper), turned to one of RPS_TURNS angles: drawn four
    times bigger and shrunk, for smooth edges. RGBA, the piece's middle in its middle (span wide: rps_span's)."""
    from .fine import ImageDraw
    from PIL import Image
    K = 4
    S = span or rps_span(r)
    big = Image.new("RGBA", (S * K, S * K), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    c = S * K / 2
    a = turn * 2 * math.pi / RPS_TURNS
    ca, sa = math.cos(a), math.sin(a)

    def P(px, py):
        return (c + (px * ca - py * sa) * K, c + (px * sa + py * ca) * K)

    def dot(px, py, rad, fill):
        x, y = P(px, py)
        d.ellipse((x - rad * K, y - rad * K, x + rad * K, y + rad * K), fill=fill)

    def seg(p, q, w, fill):                    # a line with round ends
        for x, y in (P(*p), P(*q)):
            d.ellipse((x - w * K / 2, y - w * K / 2, x + w * K / 2, y + w * K / 2), fill=fill)
        d.line((P(*p), P(*q)), fill=fill, width=max(1, round(w * K)))

    def edge(pts, w, fill):                    # an outline, its corners rounded (round once more)
        d.line(pts + pts[:2], fill=fill, width=max(1, round(w * K)), joint="curve")

    if team == 0:                              # a lumpy stone
        shape = RPS_ROCKS[look % len(RPS_ROCKS)]
        n = len(shape)
        pts = [P(math.cos(i / n * 2 * math.pi) * r * s, math.sin(i / n * 2 * math.pi) * r * s)
               for i, s in enumerate(shape)]
        d.polygon(pts, fill=RPS_COLOUR[0])
        edge(pts, max(1, r * 0.09), RPS_ROCK_EDGE)
        dot(-r * 0.25, -r * 0.25, r * 0.28, co_mix(RPS_COLOUR[0], (255, 255, 255), 0.18))
        dot(r * 0.3, r * 0.15, r * 0.08, RPS_ROCK_EDGE)
        dot(-r * 0.05, r * 0.42, r * 0.06, RPS_ROCK_EDGE)
    elif team == 2:                            # a sheet with a folded corner, written on
        w, hh, f = r * 0.62, r * 0.8, r * 0.3
        pts = [P(-w, -hh), P(w - f, -hh), P(w, -hh + f), P(w, hh), P(-w, hh)]
        d.polygon(pts, fill=RPS_SHEET)
        lw = max(1, r * 0.07)
        edge(pts, lw, RPS_SHEET_EDGE)
        d.line((P(w - f, -hh), P(w - f, -hh + f), P(w, -hh + f)), fill=RPS_SHEET_EDGE,
               width=max(1, round(lw * K)), joint="curve")
        for y in (-0.22, 0.08, 0.38):
            seg((-w * 0.62, y * r), (w * (0.3 if y < 0 else 0.62), y * r), max(1.2, r * 0.1), RPS_COLOUR[2])
    else:                                      # two blades and two rings
        for sgn in (1, -1):
            seg((-r * 0.3, sgn * r * 0.2), (r * 0.92, -sgn * r * 0.34), r * 0.22, RPS_BLADE_EDGE)
            seg((-r * 0.3, sgn * r * 0.2), (r * 0.9, -sgn * r * 0.33), r * 0.12, RPS_BLADE)
        o = (0.26 + 0.08) * r * K
        for sgn in (1, -1):
            x, y = P(-r * 0.56, sgn * r * 0.36)
            d.ellipse((x - o, y - o, x + o, y + o), outline=RPS_COLOUR[1], width=max(1, round(r * 0.16 * K)))
        dot(r * 0.12, 0, r * 0.08, RPS_BLADE_EDGE)
    return big.reduce(K)


class RockPaperScissors(Sim):
    """Rock, paper and scissors bounce around the box; a piece hit by its counter switches sides, until
    one team is left. A round: a moment to pick a winner (ready), the round (on), the winner (over), then
    the next round by itself. Positions are px inside the box."""
    key = "rps"
    blurb = "Paper covers rock, rock crushes scissors, scissors cut paper. A piece hit by its counter switches sides."
    poke_label = "Shake"
    smooth = True
    options = (("count", "Pieces per team", RPS_COUNTS, 20),
               ("size", "Size", tuple(n for n, _ in RPS_SIZES), "Medium"),
               ("speed", "Speed", tuple(n for n, _ in RPS_SPEEDS), "Normal"))
    restart_for = ("count",)

    def __init__(self, w, h, rng=None, values=None):
        super().__init__(w, h, rng, values)
        self.count, self.r, self.speed = 20, 13, 70   # pieces per team, their radius, px a second
        self.x, self.y, self.vx, self.vy = [], [], [], []
        self.t = []                     # each piece's team
        self.ang, self.spin, self.look = [], [], []
        self.round = 0
        self.phase = "ready"            # ready (a moment to pick a winner), on, over (a team has won)
        self.wait = 0.0                 # ready: seconds until it starts; over: until the next round
        self.captures = 0
        self.pick = None                # the team you think will win (kept for the next rounds)
        self.winner = None
        self.calls = [0, 0]             # winners you picked, rounds you picked one in
        self.sprites = {}               # (team, look, turn) -> a piece's picture, at the size it is now
        self.apply()
        self.new_round()

    def apply(self):
        self.count = self.values["count"]
        self.resize(dict(RPS_SIZES)[self.values["size"]])
        self.speed = dict(RPS_SPEEDS)[self.values["speed"]]

    def restart(self):
        self.new_round()

    # -- a round ------------------------------------------------------------------------------
    def new_round(self):
        """Each team in a bunch of its own, round the middle, set off in all directions."""
        rnd, W, H = self.rng, self.w, self.h
        base = rnd.random() * math.pi * 2
        homes = [(W / 2 + math.cos(base + t * math.pi * 2 / 3) * W * 0.3,
                  H / 2 + math.sin(base + t * math.pi * 2 / 3) * H * 0.3) for t in range(3)]
        xs, ys, ts = [], [], []
        for t in range(3):
            for _ in range(self.count):
                x, y = self.free_spot(xs, ys, homes, t)
                xs.append(x)
                ys.append(y)
                ts.append(t)
        order = list(range(len(xs)))
        rnd.shuffle(order)                      # (no team always drawn on top)
        self.x, self.y, self.t = [xs[i] for i in order], [ys[i] for i in order], [ts[i] for i in order]
        self.vx, self.vy = [], []
        for _ in order:
            a = rnd.random() * math.pi * 2
            self.vx.append(math.cos(a) * self.speed)
            self.vy.append(math.sin(a) * self.speed)
        self.ang = [rnd.random() * math.pi * 2 for _ in order]
        self.spin = [(rnd.random() - 0.5) * 1.2 for _ in order]
        self.look = [rnd.randrange(len(RPS_ROCKS)) for _ in order]
        self.round += 1
        self.phase, self.wait, self.paused = "ready", float(RPS_READY), False
        self.clock = self.sampled = 0.0
        self.captures = 0
        self.winner = None
        self.history = []
        self.started = {k: self.values.get(k) for k in self.restart_for}
        self.sample(self.counts())

    def free_spot(self, xs, ys, homes, t):
        """A place no piece is on yet, near team t's home and nearer it than the others' (a small box
        fills up: the bunch spreads out on its own side), or anywhere on its side."""
        rnd, r, W, H = self.rng, self.r, self.w, self.h
        far = (2 * r) ** 2
        cx, cy = homes[t]
        spread = min(W, H) * 0.2
        best = None
        for k in range(150):
            a, d = rnd.random() * math.pi * 2, math.sqrt(rnd.random()) * spread * (1 + k / 25)
            x = min(max(cx + math.cos(a) * d, r), W - r)
            y = min(max(cy + math.sin(a) * d, r), H - r)
            mine = (x - cx) ** 2 + (y - cy) ** 2
            if any((x - hx) ** 2 + (y - hy) ** 2 < mine for hx, hy in homes):
                continue                                   # (another team's side)
            if all((ox - x) ** 2 + (oy - y) ** 2 >= far for ox, oy in zip(xs, ys)):
                return x, y
            if best is None:
                best = (x, y)
        return best or (min(max(cx, r), W - r), min(max(cy, r), H - r))

    def is_open(self):
        """Picks are open until the first capture."""
        return self.phase == "ready" or (self.phase == "on" and not self.captures)

    def choose(self, d):
        """Left and right: no pick, Rock, Scissors, Paper."""
        ways = [None, 0, 1, 2]
        self.pick = ways[(ways.index(self.pick) + d) % len(ways)]

    def start(self):
        if self.phase == "ready":
            self.phase, self.wait = "on", 0.0

    def shake(self):
        for i in range(len(self.x)):
            a = self.rng.random() * math.pi * 2
            self.vx[i], self.vy[i] = math.cos(a) * self.speed * 1.8, math.sin(a) * self.speed * 1.8

    def poke(self):
        if self.phase != "ready":
            self.shake()

    def resize(self, r):
        self.r = r
        for i in range(len(self.x)):
            self.x[i] = min(max(self.x[i], r), max(r, self.w - r))
            self.y[i] = min(max(self.y[i], r), max(r, self.h - r))

    def refit(self, w, h):
        """The box changes size (full screen, and back): everything spreads out or closes up with it."""
        sx, sy = w / self.w, h / self.h
        self.w, self.h = w, h
        r = self.r
        for i in range(len(self.x)):
            self.x[i] = min(max(self.x[i] * sx, r), max(r, w - r))
            self.y[i] = min(max(self.y[i] * sy, r), max(r, h - r))

    def counts(self):
        c = [0, 0, 0]
        for t in self.t:
            c[t] += 1
        return c

    def update(self, dt):
        """Time goes on: "won" when a team has just won, "next" when the next round has begun."""
        if self.paused or dt <= 0:
            return None
        if self.phase == "ready":
            for i in range(len(self.ang)):
                self.ang[i] += self.spin[i] * dt
            self.wait -= dt
            if self.wait <= 0:
                self.start()
            return None
        self.move(dt)
        if self.phase == "over":
            self.wait -= dt
            if self.wait <= 0:
                self.new_round()
                return "next"
            return None
        self.clock += dt
        self.sampled += dt
        if self.sampled >= SIM_SAMPLE:
            self.sampled = 0.0
            self.sample(self.counts())
        left = set(self.t)
        if len(left) == 1:
            self.winner = left.pop()
            self.phase, self.wait = "over", float(RPS_NEXT)
            self.sample(self.counts())
            if self.pick is not None:
                self.calls = [self.calls[0] + (self.pick == self.winner), self.calls[1] + 1]
            return "won"
        return None

    def move(self, dt):
        """Everything moves on: off the walls, off each other, and a piece hit by its counter
        changes sides. (Small steps, with only nearby pieces checked: quick enough for a Pi Zero.)"""
        n = len(self.x)
        if not n:
            return
        X, Y, VX, VY, T = self.x, self.y, self.vx, self.vy, self.t
        r, W, H = self.r, self.w, self.h
        rr = 2 * r
        rr2 = rr * rr
        lo, hi_x, hi_y = r, W - r, H - r
        top = max(max(map(abs, VX)), max(map(abs, VY)))
        least = 2 if dt >= 0.04 else 1             # (drawn more often than twenty times a second: a step's short
        steps = max(least, min(8, int(math.ceil(top * 1.42 * dt / (0.5 * r)))))   # enough by itself)
        h = dt / steps
        cols = int(W // rr) + 1
        sqrt = math.sqrt
        caps = 0
        for _ in range(steps):
            for i in range(n):
                x = X[i] + VX[i] * h
                y = Y[i] + VY[i] * h
                if x < lo:
                    x = lo
                    if VX[i] < 0:
                        VX[i] = -VX[i]
                elif x > hi_x:
                    x = hi_x
                    if VX[i] > 0:
                        VX[i] = -VX[i]
                if y < lo:
                    y = lo
                    if VY[i] < 0:
                        VY[i] = -VY[i]
                elif y > hi_y:
                    y = hi_y
                    if VY[i] > 0:
                        VY[i] = -VY[i]
                X[i] = x
                Y[i] = y
            grid = {}
            for i in range(n):
                k = int(Y[i] // rr) * cols + int(X[i] // rr)
                cell = grid.get(k)
                if cell is None:
                    grid[k] = [i]
                else:
                    cell.append(i)
            for k, cell in grid.items():
                for nb in (k, k + 1, k + cols - 1, k + cols, k + cols + 1):   # (the other half
                    other = cell if nb == k else grid.get(nb)            # checks this one)
                    if other is None:
                        continue
                    for a in range(len(cell)):
                        i = cell[a]
                        for j in (other[a + 1:] if nb == k else other):
                            dx = X[j] - X[i]
                            dy = Y[j] - Y[i]
                            d2 = dx * dx + dy * dy
                            if d2 >= rr2:
                                continue
                            d = sqrt(d2) or 0.0001
                            nx, ny = dx / d, dy / d
                            corr = (rr - d) / 2
                            X[i] -= nx * corr
                            Y[i] -= ny * corr
                            X[j] += nx * corr
                            Y[j] += ny * corr
                            vn = (VX[j] - VX[i]) * nx + (VY[j] - VY[i]) * ny
                            if vn < 0:                   # coming together: they bounce
                                VX[i] += vn * nx
                                VY[i] += vn * ny
                                VX[j] -= vn * nx
                                VY[j] -= vn * ny
                                if T[i] != T[j]:
                                    if T[j] == (T[i] + 1) % 3:
                                        T[j] = T[i]
                                    else:
                                        T[i] = T[j]
                                    caps += 1
        self.captures += caps
        k = min(1.0, dt * RPS_EASE)               # back toward the speed, gently
        sp, ang, spin = self.speed, self.ang, self.spin
        for i in range(n):
            x, y = X[i], Y[i]                        # (a crowd can push one into the wall: not through it)
            if x < lo:
                x = lo
            if y < lo:
                y = lo
            X[i] = hi_x if x > hi_x else x
            Y[i] = hi_y if y > hi_y else y
            ang[i] += spin[i] * dt
            s = sqrt(VX[i] * VX[i] + VY[i] * VY[i])
            if s < 1:
                a = self.rng.random() * math.pi * 2
                VX[i], VY[i] = math.cos(a) * sp, math.sin(a) * sp
                continue
            f = 1 + (sp / s - 1) * k
            VX[i] *= f
            VY[i] *= f

    def draw(self, img, x0, y0):
        """Every piece, where it is: its picture at the nearest of RPS_TURNS angles."""
        sprites = self.sprites
        if sprites.get("r") != self.r:                 # (another size: drawn again, as needed)
            sprites.clear()
            sprites["r"] = self.r
        span = rps_span(self.r)
        half = span // 2
        ox, oy = x0 - half, y0 - half
        k = RPS_TURNS / (2 * math.pi)
        fs = detail(img)                               # (a screen drawn finely: the pieces drawn as finely, and put
        core = None                                    # in place between its pixels)
        if RPS_QUICK[0]:                               # (PIL's own picture underneath: sixty pieces put straight on
            try:                                       # it cost half what sixty pastes do, each with its checks: a
                under = img if fs == 1 else img.pic    # frame a tenth cheaper on a Pi Zero. A fine picture's: its
                under.load()                           # own pixels, each piece where paste would put it)
                core = under.im
            except Exception:
                core = None
        for x, y, t, a, look in zip(self.x, self.y, self.t, self.ang, self.look):
            turn = int(a * k + 0.5) % RPS_TURNS
            key = (t, look if t == 0 else 0, turn, fs)
            s = sprites.get(key)
            if s is None:
                s = sprites[key] = (rps_sprite(t, self.r, turn, look) if fs == 1 else
                                    made_fine(rps_sprite(t, self.r * fs, turn, look, rps_span(self.r) * fs), fs))
            if core is not None:
                try:
                    if fs == 1:
                        px, py, bit = ox + int(x + 0.5), oy + int(y + 0.5), s.im
                    else:
                        px, py, bit = round((ox + x) * fs), round((oy + y) * fs), s.pic.im
                    core.paste(bit, (px, py, px + span * fs, py + span * fs), bit)
                    continue
                except Exception:                      # (a PIL that has it another way: its paste, from now on)
                    RPS_QUICK[0], core = False, None
            img.paste(s, (ox + int(x + 0.5), oy + int(y + 0.5)) if fs == 1 else (ox + x, oy + y), s)
