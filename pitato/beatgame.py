"""Game beat, for Now playing (SELECT there, after the lofi art): a dancer in the middle of a dance floor at night,
moving to the beat. On its strong beats zombies (balls, each a soft colour, glowing brighter on the beat) drift in from
the edges; on the others the dancer throws notes at the nearest, each its own colour and glowing: they arc through the
air, flaring on the next beat, and land on the one after, clearing them. Nothing to do but watch: the dancer never
falls (a zombie that gets to it is cleared too). Its beats are the ones the ear finds in a song of yours (ear.py), or
a station's bass rising (hear: its bars); the ring round the dancer is Now playing's bars. Drawn at a whole part of
the screen's size (fewer than twice GAME_LINES up its shorter side) and enlarged, so a Pi 4 or 5 keeps up (not a Pi
Zero 2 W or a Pi 3: screens/music.py's bars_here)."""
import collections
import math
import random

GAME_FPS = 15                    # its frames a second
GAME_LINES = 360                 # drawn a whole part of the screen's size, fewer than twice this up its shorter
                                 # side (then enlarged)
GAME_UNIT = 480                  # ...its sizes as on a screen this many pixels up its shorter side
GAME_MOST = 50                   # zombies on the floor at once, at most
LATE = 0.2                       # a beat heard this long ago or more (a pause, a slow frame): a move, nothing else
IDLE = 2.0                       # no beat this long: the dancer keeps moving at the tempo it had, all the same
STATION_LONG = 180.0             # a station's waves grow over this long (a song's over its length)
TAU = math.pi * 2

INK = (236, 233, 226)            # the dancer
NOTE_HUES = ((255, 92, 170), (255, 166, 62), (255, 228, 86), (108, 236, 134), (80, 206, 255), (172, 132, 255))
NOTE_BEATS = 2                   # a note's in the air this many beats (glowing brighter on each), landing on the last
NOTE_TIME = (0.5, 1.2)           # ...but no shorter or longer than this (seconds)
NOTE_SIZE = 1.3                  # its notes, this much bigger than the web page's
GLOWS = 5                        # how bright a note's glow can be, in steps (each step's picture made once)
FLOOR = ((19, 19, 17), (15, 15, 14))   # its tiles, in turn
BACK = (11, 11, 10)
KINDS = {"walk": (13, 1, 46), "run": (10, 1, 70), "brute": (21, 3, 34)}   # a zombie: its size, hits, speed
PASTELS = ((255, 182, 193), (255, 214, 170), (250, 240, 170), (182, 240, 196), (178, 220, 255), (212, 192, 255),
           (255, 196, 238))              # ...its colour, one of these
POSES = (((-4, 6, -9, 14, -7, 21), (4, 6, 9, 14, 7, 21), (-7, -6, -14, -14, -12, -24), (7, -6, 14, -14, 12, -24)),
         ((-4, 6, -6, 14, -10, 21), (4, 6, 10, 12, 12, 19), (-7, -6, -16, -2, -20, 4), (7, -6, 15, -14, 20, -22)),
         ((-4, 6, -2, 13, -5, 21), (4, 6, 6, 14, 4, 21), (-7, -6, -15, -12, -22, -12), (7, -6, 15, -12, 22, -12)),
         ((-4, 6, -12, 12, -12, 19), (4, 6, 6, 14, 10, 21), (-7, -6, -15, -14, -20, -22), (7, -6, 16, -2, 20, 4)))
LEAN = (0.0, -0.09, 0.0, 0.09)   # each pose's lean, and its head's sway
HEAD_X = (0, -2, 0, 2)


def game_size(W, H):
    """The picture it's drawn at for a W x H screen, and how many times bigger the screen is: (w, h, k)."""
    k = max(1, min(W, H) // GAME_LINES)
    return -(-W // k), -(-H // k), k


class BeatGame:
    """The dance floor for one song (or station): song, the one it's for. beat(t, hard): a beat heard at t
    (seconds, the clock frame's is), how hard (0 to 1); hear(levels, t): a station's bars, its beats found in them;
    frame(W, H, t, levels, paused, accent, progress): the floor at t, W x H (an RGB picture), moved on to then
    unless paused."""

    def __init__(self, song=None, seed=None):
        self.song = song
        self.rnd = random.Random(seed if seed is not None else sum(map(ord, str(song or ""))))
        self.zombies, self.notes, self.bits, self.rings = [], [], [], []
        self.kills = 0
        self.beat_at, self.beats, self.pose, self.face = -9.0, 0, 0, 1
        self.spb, self.glow, self.spin, self.bass = 0.5, 0.0, 0.0, 0.0
        self.prev_spawn, self.last = False, "fire"
        self.hards = collections.deque(maxlen=16)      # the last beats' strengths: a strong one's over their middle
        self.t = None                                  # (when it was last moved on to)
        self.size, self.u, self.back = None, 1.0, (None, None)
        self.low, self.low_at, self.low_was = 0.0, -9.0, 0.0   # (a station's bass, as it's been lately)
        self.progress, self.born = 0.0, None
        self.hue, self.glows = 0, {}                   # (the next note's colour; their glows' pictures, made once)

    # -- the beat ---------------------------------------------------------------------------------------------
    def beat(self, t, hard=0.7, now=None):
        """A beat heard at t: the dancer's next move; a wave of zombies on a strong one (never two in a row), its notes
        at them on the others. One heard a while ago (LATE): the move, nothing else."""
        gap = t - self.beat_at
        if 0.2 < gap < 1.5:
            self.spb += (gap - self.spb) * 0.5
        self.beats += 1
        self.pose = (self.pose + 1) % 4
        self.beat_at = t
        if now is not None and now - t >= LATE or self.size is None:
            return
        self.hards.append(hard)
        middle = sorted(self.hards)[int(len(self.hards) * 0.45)]
        spawn = hard >= middle and hard > 0.05 and not self.prev_spawn
        self.prev_spawn, self.last = spawn, "spawn" if spawn else "fire"
        self.rings.append([30 * self.u, 0.5 if spawn else 0.25, spawn, None, None])
        if self.beats % 16 == 0:
            self.spin = 1.0
        if spawn:
            self.wave(hard, t)
        else:
            self.fire(t, now if now is not None else t)

    def hear(self, levels, t):
        """A station's bars (0 to 1, low notes first) at t: a beat where its bass rises over what it's been lately."""
        low = sum(levels[:4]) / 4 if levels else 0.0
        rise = low - self.low
        if rise > 0.08 and low > self.low_was and t - self.low_at > 0.25:
            self.low_at = t
            self.beat(t, min(1.0, 0.3 + rise * 4), t)
        self.low += (low - self.low) * 0.15
        self.low_was = low

    def wave(self, hard, t):
        w, h = self.size
        u, rnd = self.u, self.rnd.random
        n = round(2 + hard * 3 + self.progress * 4)
        reach = math.hypot(w, h) / 2 + 30 * u
        side = rnd() * TAU
        for i in range(n):
            if len(self.zombies) >= GAME_MOST:
                break
            a = side + (i / n - 0.5) * 1.8 + (rnd() - 0.5) * 0.3
            r = rnd()
            kind = "walk"
            if self.progress > 0.2 and r < 0.3:
                kind = "run"
            if self.progress > 0.4 and r > 0.88:
                kind = "brute"
            size, hits, speed = KINDS[kind]
            self.zombies.append({"x": w / 2 + math.cos(a) * reach, "y": h / 2 + math.sin(a) * reach, "r": size * u,
                                 "hp": hits, "k": kind, "hit": 0.0, "a": 0.0, "ph": rnd() * TAU, "born": t,
                                 "sp": speed * u * (0.85 + rnd() * 0.3), "marked": 0,
                                 "hue": int(rnd() * len(PASTELS)) % len(PASTELS)})

    def fire(self, t, now):
        """Notes thrown at the zombies nearest the dancer (the beat was at t, heard now): each its own colour, out to
        one side and up through the air, to land on its zombie NOTE_BEATS beats after the one it was thrown on."""
        if not self.zombies:
            self.glow = 1.0
            return
        w, h = self.size
        cx, cy, u, rnd = w / 2, h / 2, self.u, self.rnd.random
        reach = max(130 * u, min(w, h) * 0.26)
        near = sorted(((z["x"] - cx) ** 2 + (z["y"] - cy) ** 2, i) for i, z in enumerate(self.zombies)
                      if (not z["marked"] or z["hp"] > z["marked"])
                      and (z["x"] - cx) ** 2 + (z["y"] - cy) ** 2 < reach ** 2)
        shots = min(16, max(2, math.ceil(len(near) / 1.3)))
        flight = max(NOTE_TIME[0], min(NOTE_TIME[1], NOTE_BEATS * self.spb - max(0.0, now - t)))
        for n, (_, i) in enumerate(near[:shots]):
            z = self.zombies[i]
            z["marked"] += 1
            self.notes.append({"x0": cx, "y0": cy - 8 * u, "x": cx, "y": cy - 8 * u, "s": 0.0, "time": flight,
                               "at": now, "tgt": z, "tx": z["x"], "ty": z["y"],
                               "bend": (0.2 + rnd() * 0.25) * (1 if n % 2 else -1),
                               "lift": (20 + rnd() * 28) * u, "hue": self.hue % len(NOTE_HUES), "vx": 0.0,
                               "vy": 0.0, "tr": collections.deque(maxlen=7)})
            self.hue += 1
        if near:
            self.face = -1 if self.zombies[near[0][1]]["x"] < cx else 1
        self.glow = 1.0

    def burst(self, z):
        self.kills += 1
        rnd = self.rnd.random
        for k in range(16):
            a, s = rnd() * TAU, (40 + rnd() * 140) * self.u
            colour = INK if k % 3 == 0 else PASTELS[z["hue"]]
            self.bits.append([z["x"], z["y"], math.cos(a) * s, math.sin(a) * s - 30 * self.u, 0.9 + rnd() * 0.6, 1.5,
                              colour, (2 + rnd() * 2.5) * self.u])
        self.rings.append([z["r"], 0.6, False, (z["x"], z["y"]), PASTELS[z["hue"]]])

    # -- moving on --------------------------------------------------------------------------------------------
    def pulse(self, t):
        return math.exp(-max(0.0, t - self.beat_at) * 6)

    def step(self, t, levels=()):
        dt = 0.0 if self.t is None else max(0.0, min(0.1, t - self.t))   # (a frame's time: a fifteenth, as a rule)
        self.t = t
        if levels:
            self.bass += (sum(levels[:4]) / 4 - self.bass) * 0.3
        else:
            self.bass *= 0.95
        if t - self.beat_at > max(IDLE, self.spb * 3):   # (quiet a while: it dances on all the same)
            self.beat_at, self.pose, self.last = t, (self.pose + 1) % 4, "fire"
        w, h = self.size
        cx, cy, u = w / 2, h / 2, self.u
        pu = self.pulse(t)
        for z in list(self.zombies):
            dx, dy = cx - z["x"], cy - z["y"]
            d = math.hypot(dx, dy) or 1.0
            s = z["sp"] * (0.25 + 1.9 * pu)
            z["x"] += dx / d * s * dt
            z["y"] += dy / d * s * dt
            z["a"] = math.atan2(dy, dx)
            z["hit"] = max(0.0, z["hit"] - dt)
            if d < z["r"] + 20 * u:                    # (at the dancer: cleared all the same)
                self.burst(z)
                self.zombies.remove(z)
        for b in list(self.notes):
            self.fly(b, dt, t)
        for p in list(self.bits):
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[2] *= 0.95
            p[3] = p[3] * 0.95 - 12 * u * dt
            p[4] -= dt
            if p[4] <= 0:
                self.bits.remove(p)
        for r in list(self.rings):
            r[0] += dt * (120 if r[3] is not None else 520) * u
            r[1] -= dt * (1.4 if r[3] is not None else 0.7)
            if r[1] <= 0:
                self.rings.remove(r)
        self.glow = max(0.0, self.glow - dt * 4)
        self.spin = max(0.0, self.spin - dt * 1.6)

    def fly(self, b, dt, t):
        """A note on through the air to t: along a curve from the dancer's hands to its zombie (wherever it's got
        to), slow at first and quicker as it goes (from when it was thrown); there, it hits it (or one beside where
        it was, if it's gone)."""
        u = self.u
        z = b["tgt"]
        if z is not None and z in self.zombies:
            b["tx"], b["ty"] = z["x"], z["y"]
        b["tr"].append((b["x"], b["y"]))
        b["s"] = s = min(1.0, b["s"] + min(dt, max(0.0, t - b["at"])) / b["time"])
        x0, y0, tx, ty = b["x0"], b["y0"], b["tx"], b["ty"]
        dx, dy = tx - x0, ty - y0
        mx = x0 + dx * 0.35 - dy * b["bend"]           # (its curve's pull: out to one side, and up)
        my = y0 + dy * 0.35 + dx * b["bend"] - b["lift"]
        e = 0.35 * s + 0.65 * s * s
        x = (1 - e) ** 2 * x0 + 2 * (1 - e) * e * mx + e * e * tx
        y = (1 - e) ** 2 * y0 + 2 * (1 - e) * e * my + e * e * ty
        if dt > 0:
            b["vx"], b["vy"] = (x - b["x"]) / dt, (y - b["y"]) / dt
        b["x"], b["y"] = x, y
        if s < 1.0 - 1e-6:
            return
        self.notes.remove(b)
        if z is not None:
            z["marked"] = max(0, z["marked"] - 1)
        if z not in self.zombies:                      # (its zombie's gone: another there, or a fizzle)
            z = next((o for o in self.zombies if (o["x"] - x) ** 2 + (o["y"] - y) ** 2 < (o["r"] + 10 * u) ** 2), None)
        colour = NOTE_HUES[b["hue"]]
        rnd = self.rnd.random
        for _ in range(5):
            self.bits.append([x, y, (rnd() - 0.5) * 150 * u, (rnd() - 0.5) * 150 * u, 0.35, 0.35, colour, 2 * u])
        if z is None:
            return
        self.rings.append([6 * u, 0.55, False, (x, y), colour])
        sp = math.hypot(b["vx"], b["vy"]) or 1.0
        z["hp"] -= 1
        z["hit"] = 0.12
        z["x"] += b["vx"] / sp * 8 * u
        z["y"] += b["vy"] / sp * 8 * u
        if z["hp"] <= 0:
            self.burst(z)
            self.zombies.remove(z)

    # -- drawing ----------------------------------------------------------------------------------------------
    def fit(self, w, h):
        """Its floor at this size: the same zombies and all as before, moved with the floor's middle."""
        if self.size == (w, h):
            return
        if self.size is not None:
            dx, dy = (w - self.size[0]) / 2, (h - self.size[1]) / 2
            for z in self.zombies:
                z["x"] += dx
                z["y"] += dy
                z["marked"] = 0
            self.notes.clear()
            self.bits.clear()
        self.size, self.u = (w, h), min(w, h) / GAME_UNIT
        self.glows = {}

    def background(self, accent, depth=8):
        """The floor with nothing on it: its tiles, darker towards the edges, a little of the accent in the middle
        (spread over a 16-bit screen's few steps: depth, as home.py's stepped has it). Made once for its size and
        colour."""
        key = (self.size, tuple(accent), depth)
        if self.back[0] == key:
            return self.back[1]
        import numpy as np
        from PIL import Image
        w, h = self.size
        T = 56 * self.u
        cx, cy = w / 2, h / 2
        img = np.zeros((h, w, 3), np.float32)
        img[:] = BACK
        ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
        i = np.floor((xs - (cx % T - T / 2)) / T).astype(int)
        j = np.floor((ys - (cy % T - T / 2)) / T).astype(int)
        inside = (((xs - (cx % T - T / 2)) % T) >= 1) & (((xs - (cx % T - T / 2)) % T) < T - 1) \
            & (((ys - (cy % T - T / 2)) % T) >= 1) & (((ys - (cy % T - T / 2)) % T) < T - 1)
        odd = ((i + j) & 1).astype(bool)
        img[inside & odd] = FLOOR[0]
        img[inside & ~odd] = FLOOR[1]
        d = np.hypot(xs - cx, ys - cy) / (max(w, h) * 0.75)
        warm = np.clip(1 - d / 0.35, 0, 1)[..., None] * 0.08          # (the accent in the middle, fading by a third)
        dark = np.clip((d - 0.35) / 0.65, 0, 1)[..., None] * 0.75       # (and darker out to the edges)
        img = img * (1 - warm) + np.array(accent, np.float32) * warm
        img = img * (1 - dark)
        pic = Image.fromarray(np.clip(img + 0.5, 0, 255).astype(np.uint8), "RGB")
        if depth != 8:
            from .home import stepped
            pic = stepped(pic, depth)
        self.back = (key, pic)
        return pic

    def frame(self, W, H, t, levels=(), paused=False, accent=(229, 51, 42), progress=0.0, depth=8):
        """The floor at t, W x H (an RGB picture): moved on to then, unless paused (depth: the bits a colour has on
        the screen, its floor's shades spread over them)."""
        from PIL import Image, ImageDraw
        w, h, k = game_size(W, H)
        self.fit(w, h)
        self.progress = max(0.0, min(1.0, progress))
        if not paused:
            self.step(t, levels)
        else:
            self.t = t
        img = self.background(accent, depth).copy()
        d = ImageDraw.Draw(img, "RGBA")
        u, cx, cy = self.u, w / 2, h / 2
        pu = self.pulse(t)
        self.draw_floor(d, pu, accent)
        for r, a, lit, at, hue in self.rings:
            a = max(0.0, a)
            colour = (tuple(accent) + (int(255 * a),) if lit else hue + (int(255 * a * 0.8),) if hue
                      else INK + (int(255 * a * 0.6),))
            if at is None:
                d.ellipse((cx - r, cy + 14 * u - r * 0.42, cx + r, cy + 14 * u + r * 0.42), outline=colour,
                          width=max(1, round(1.5 * u)))
            else:
                d.ellipse((at[0] - r, at[1] - r, at[0] + r, at[1] + r), outline=colour, width=max(1, round(2 * u)))
        self.draw_ring(d, cx, cy, levels, accent)
        for x, y, _, _, life, most, colour, s in self.bits:
            a = max(0.0, min(1.0, life / most * 1.4))
            c = tuple(accent if colour is None else colour) + (int(255 * a),)
            d.ellipse((x - s, y - s, x + s, y + s), fill=c)
        lit = min(GLOWS - 1, int((0.25 + 0.75 * pu) * GLOWS))   # (glowing: brightest on the beat)
        for z in self.zombies:                         # (all their glows, then the balls over them)
            self.zombie_glow(img, z, t, lit)
        for z in self.zombies:
            self.draw_zombie(d, z, t, pu)
        self.draw_dancer(d, cx, cy, pu, t, accent)
        for b in self.notes:
            self.draw_note(img, d, b, lit, pu)
        if k > 1:
            img = img.resize((w * k, h * k), Image.BILINEAR)
        return img if img.size == (W, H) else img.crop((0, 0, W, H))

    def draw_floor(self, d, pu, accent):
        """The beat's ripple across the floor: the tiles round a ring going out from the middle, lit a little (the
        accent on a beat that brought zombies)."""
        if pu < 0.02:
            return
        w, h = self.size
        T = 56 * self.u
        cx, cy = w / 2, h / 2
        ring = (1 - pu) * max(w, h) * 0.45
        colour, most = (tuple(accent), 0.08) if self.last == "spawn" else (INK, 0.05)
        ox, oy = cx % T - T / 2, cy % T - T / 2
        x = ox - T
        while x < w + T:
            y = oy - T
            while y < h + T:
                a = max(0.0, 1 - abs(math.hypot(x + T / 2 - cx, y + T / 2 - cy) - ring) / (80 * self.u)) * pu
                if a > 0.02:
                    d.rectangle((x + 1, y + 1, x + T - 2, y + T - 2), fill=colour + (int(255 * a * most),))
                y += T
            x += T

    def draw_ring(self, d, cx, cy, levels, accent):
        """Now playing's bars, round the dancer's feet: low notes at the top and bottom, in the accent."""
        u = self.u
        n = 64
        r0 = (58 + self.bass * 10) * u
        oy = cy + 14 * u
        d.ellipse((cx - r0, oy - r0 * 0.42, cx + r0, oy + r0 * 0.42), outline=INK + (20,), width=1)
        width = max(1, round(3 * u))
        for i in range(n):
            j = i if i < n // 2 else n - 1 - i
            v = float(levels[j]) if j < len(levels) else 0.0
            a = i / n * TAU - math.pi / 2
            ln = (4 + v * v * 70) * u
            ca, sa = math.cos(a), math.sin(a) * 0.42
            if j < 4:
                colour = tuple(accent) + (int(255 * (0.35 + v * 0.6)),)
            else:
                colour = INK + (int(255 * (0.12 + v * 0.5)),)
            d.line((cx + ca * r0, oy + sa * r0, cx + ca * (r0 + ln), oy + sa * (r0 + ln)), fill=colour, width=width)

    def zombie_glow(self, img, z, t, lit):
        if t - z["born"] < 0.4:                        # (just come: its glow when it's there)
            return
        pic = self.halo(PASTELS[z["hue"]], round(z["r"] * (1.9 + 0.2 * lit)), 0.22 + 0.09 * lit, 0.0)
        r = pic.width // 2
        img.paste(pic, (round(z["x"]) - r, round(z["y"]) - r), pic)

    def draw_zombie(self, d, z, t, pu):
        """A zombie: a ball in its colour, a little lighter on the beat (white for a moment when it's hit)."""
        r, x, y = z["r"], z["x"], z["y"]
        fade = max(0.0, min(1.0, (t - z["born"]) * 1.5))
        colour = PASTELS[z["hue"]]
        ink = INK if z["hit"] > 0 else tuple(int(c + (255 - c) * 0.35 * pu) for c in colour)
        d.ellipse((x - r, y - r, x + r, y + r), fill=ink + (int(255 * fade),))

    def draw_dancer(self, d, x, y, pu, t, accent):
        """The dancer: holding its pose, leaning a little towards the next one late in the beat, then swinging into
        it on the beat (overshooting a touch), hopping, turning to face what it fires at, and spinning round every
        sixteenth beat."""
        u = self.u
        tb = max(0.0, t - self.beat_at)
        spb = max(0.2, self.spb)
        ph = min(1.0, tb / spb)
        hit = min(0.12, spb * 0.28)
        pose = self.pose
        if tb < hit:
            frm, to = (pose + 3) % 4, pose
            q = tb / hit - 1
            k = 0.2 + 0.8 * (1 + 2.2 * q * q * q + 1.2 * q * q)
        else:
            frm, to = pose, (pose + 1) % 4
            a = (ph - 0.66) / 0.34 if ph > 0.66 else 0.0
            k = 0.2 * a * a

        def mix(a, b):
            return a + (b - a) * k
        limbs = [[mix(v, POSES[to][i][j]) for j, v in enumerate(s)] for i, s in enumerate(POSES[frm])]
        lean, hx = mix(LEAN[frm], LEAN[to]), mix(HEAD_X[frm], HEAD_X[to])
        hop = (pu * 9 if pose == 0 else pu * 4) + math.sin(ph * math.pi) * 2
        sq = pu * 0.1
        sx = (1 + sq) * self.face * (math.cos(self.spin * TAU * 2) if self.spin > 0 else 1) or 0.001
        sy = 1 - sq
        cl, sl = math.cos(lean), math.sin(lean)

        def at(px, py):                                # (the dancer's own place to the floor's: its lean, its
            qx, qy = px, py - 22 - hop                 # squash on the beat, which way it faces, its hop)
            qx, qy = qx * cl - qy * sl, qx * sl + qy * cl
            return x + qx * sx * u, y + (qy * sy + 22) * u
        sh = (17 - pu * 3) * u
        d.ellipse((x - sh, y + 17 * u, x + sh, y + 27 * u), fill=(0, 0, 0, 140))
        if self.glow > 0:
            gx, gy = at(0, -6)
            g = (30 + self.glow * 10) * u
            d.ellipse((gx - g, gy - g, gx + g, gy + g), fill=INK + (int(255 * self.glow * 0.18),))
        width = max(2, round(5 * u))
        for s in limbs:
            pts = [at(s[0], s[1]), at(s[2], s[3]), at(s[4], s[5])]
            d.line(pts, fill=INK, width=width, joint="curve")
            for px, py in pts[1:]:
                e = width / 2
                d.ellipse((px - e, py - e, px + e, py + e), fill=INK)
        bx, by = at(0, -0.5)
        half = 9 * u * max(0.15, abs(sx))
        d.rounded_rectangle((bx - half, by - 9.5 * u, bx + half, by + 9.5 * u), radius=max(1, round(6 * u)), fill=INK)
        hxp, hyp = at(hx, -19)
        e = 9 * u
        d.ellipse((hxp - e, hyp - e, hxp + e, hyp + e), fill=(216, 212, 202))
        if abs(sx) > 0.3:                              # (its eyes, but not side on)
            for ex in (3.25, -1.75):
                px, py = at(hx + ex, -19.5)
                d.rectangle((px - 1.25 * u, py - 1.5 * u, px + 1.25 * u, py + 1.5 * u), fill=BACK)
        e = 11 * u
        d.arc((hxp - e, hyp - e, hxp + e, hyp + e), 198, 342, fill=tuple(accent), width=max(1, round(3 * u)))
        for ex in (-10.5, 10.5):
            px, py = at(hx + ex, -18)
            d.rounded_rectangle((px - 2.5 * u, py - 4 * u, px + 2.5 * u, py + 4 * u), radius=max(1, round(2 * u)),
                                fill=tuple(accent))

    def halo(self, colour, r, most, core):
        """A glow r pixels out: its colour fading out from the middle (whiter there, by core: 0 to 1), most (0 to
        1) of it there. An RGBA picture, made once for each (at this size)."""
        r = max(3, r)
        key = (colour, r, round(most, 3), core)
        pic = self.glows.get(key)
        if pic is None:
            import numpy as np
            from PIL import Image
            ys, xs = np.mgrid[-r:r + 1, -r:r + 1].astype(np.float32)
            d = np.hypot(xs, ys) / r
            a = np.clip(1 - d, 0, 1) ** 2 * most
            white = np.clip(1 - d / 0.3, 0, 1)[..., None] * core
            rgb = np.array(colour, np.float32) * (1 - white) + 255 * white
            pic = Image.fromarray(np.dstack([rgb, a[..., None] * 255]).clip(0, 255).astype(np.uint8), "RGBA")
            self.glows[key] = pic
        return pic

    def draw_note(self, img, d, b, lit, pu):
        """A note in the air: its trail, its glow (brighter on the beat), and the note, in its colour."""
        u, s = self.u, NOTE_SIZE
        colour = NOTE_HUES[b["hue"]]
        x, y = b["x"], b["y"]
        pts = list(b["tr"]) + [(x, y)]
        width = max(1, round(2 * u))
        for i in range(1, len(pts)):
            d.line((pts[i - 1], pts[i]), fill=colour + (int(150 * i / len(pts)),), width=width)
        if b["s"] > 0.15:                              # (its glow once it's away from the dancer's hands)
            pic = self.halo(colour, round((9 + 4 * lit) * NOTE_SIZE * u), 0.4 + 0.12 * lit, 0.5)
            r = pic.width // 2
            img.paste(pic, (round(x) - r, round(y) - r), pic)
        ink = tuple(int(c + (255 - c) * (0.25 + 0.5 * pu)) for c in colour)
        d.ellipse((x - 4.5 * s * u, y + (3 - 3.4) * s * u, x + 4.5 * s * u, y + (3 + 3.4) * s * u), fill=ink)
        d.rectangle((x + 3 * s * u, y - 9 * s * u, x + 4.8 * s * u, y + 3 * s * u), fill=ink)
        d.rectangle((x + 3 * s * u, y - 9 * s * u, x + 9 * s * u, y - 6.8 * s * u), fill=ink)
