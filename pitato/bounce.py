"""The Soundboard's Bounce (Apps > Soundboard, START's card > Bounce): a shape turning slowly in the middle of the page,
balls bouncing about inside it, and each of its walls a note. A ball that hits a wall plays that wall's note, and the
wall lights up a moment (the shape and its balls in the accent you picked). The notes are a scale's, from its key up,
wall after wall round the shape, so whatever's hit
sounds right with the rest: a ball that hits a wall straight on louder than one that grazes it, and heard from where
it hits, left or right. Beside it, its sliders. (screens/bounce.py: its buttons, its notes to the player, the web
page's say. soundplay.py and soundfx.py: the notes played, a few at a time, and its space, echo, tone and drone.
soundboard.py: its page, drawn with this.)

The shape's corners are 1 from its middle, and everything's measured that way: the page draws it as big as it fits.
A ball goes in a straight line at the speed it's set to, and comes off a wall as off a mirror; off one that's turning
into it, a little sooner, but never faster than it's set to (the shape turning doesn't speed the balls up)."""
import itertools
import math
import random

SHAPES = (("Triangle", 3), ("Square", 4), ("Pentagon", 5), ("Hexagon", 6))
SCALES = {"Major": (0, 2, 4, 5, 7, 9, 11), "Minor": (0, 2, 3, 5, 7, 8, 10), "Pentatonic": (0, 2, 4, 7, 9),
          "Blues": (0, 3, 5, 6, 7, 10)}
KEYS = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
TONES = ("Bell", "Marimba", "Kalimba", "Glass", "Pluck", "Pad")   # its own sounds (the player makes them):
                                                                   # Tones/Bell and so on
TONE_ROOT = 60                         # ...each made at this note (MIDI: middle C)
BALLS_MOST = 8
BALLS_FIRST = 3                        # balls in it the first time
RADIUS = 0.05                          # a ball's (of the shape's corners' distance from its middle)
SPIN_STEP, SPIN_MOST = 0.15, 1.5       # radians a second: a step of its Spin slider, and at most either way round
SPEED_STEP, SPEEDS = 0.2, (0.2, 2.4)   # (its corners' distance from its middle) a second: a step of Speed's
STEP = 1 / 120                         # seconds of each step of the balls
AGAIN = 0.06                           # seconds before a ball's heard on the same wall again (a corner: one note)
LIT = 0.3                              # seconds a wall stays lit after a ball hits it
DIM = 0.55                             # a wall's colour, not lit: this much of it (the rest the page's)
SLIDERS = (("spin", "Spin", -10, 10, 2), ("speed", "Speed", 1, 12, 4), ("space", "Reverb", 0, 10, 4),
           ("echo", "Echo", 0, 10, 3), ("tone", "Tone", 0, 10, 5), ("drone", "Drone", 0, 10, 0))
SAYS = {"spin": "Which way it turns, how fast", "speed": "How fast the balls go", "space": "A small room to a big hall",
        "echo": "Each note again, side to side", "tone": "◀ darker, ▶ brighter", "drone": "A soft note held under it"}
SLIDER = {key: (low, high, usual) for key, _, low, high, usual in SLIDERS}   # its sliders: each from, to, and as it
LEVELS = ("space", "echo", "tone", "drone")   # starts. Spin and Speed: steps of how fast; these: of its sound
ECHO_WAS = {"On": 3, "Off": 0}         # its echo, before it had a slider: on or off
QUIET = ("space", "echo", "drone")     # sliders that are off at 0
PANEL = (196, 340)                     # px wide, its sliders: on the GPi Case's screen, and a bigger one


def shape_sides(name):
    return dict(SHAPES).get(name, 6)


def root_of(key):
    """The key's own note (MIDI): from G below middle C up to F# above it, so the notes sit near the middle."""
    k = KEYS.index(key) if key in KEYS else 0
    return 60 + k if k <= 6 else 48 + k


def wall_note(k, key, scale):
    """Wall k's note (MIDI): the scale's k-th, from the key up (past the scale's top: the next octave's)."""
    steps = SCALES.get(scale, SCALES["Major"])
    octave, i = divmod(k, len(steps))
    return root_of(key) + 12 * octave + steps[i]


def note_semis(note, own, key):
    """Semitones from a sound's own note (own: MIDI, as near as the player could tell; None: it hasn't one, a drum
    say) to a wall's note, the key's notes moved to the octave nearest the sound, so it's played near its own pitch.
    With no note of its own: the scale from wherever it is."""
    root = root_of(key)
    if own is None:
        return float(note - root)
    return float(note + 12 * round((own - root) / 12) - own)


def note_name(note):
    return KEYS[note % 12]


class World:
    """The shape and the balls in it. step moves them on, and says which walls were hit, when."""

    def __init__(self, sides=6, spin=0.3, speed=0.8, rng=None):
        self.sides, self.spin, self.speed = sides, spin, speed
        self.angle = 0.0
        self.t = 0.0                    # seconds it's run
        self.balls = []                 # [its number, x, y, which way (a unit's x, y)]
        self.last = {}                  # (a ball's number, a wall) -> when it was last heard there
        self.rng = rng or random.Random()
        self.numbers = itertools.count()

    def add(self):
        """A ball, near the middle, going any way. False: there are as many as there can be."""
        if len(self.balls) >= BALLS_MOST:
            return False
        a, r = self.rng.uniform(0, 2 * math.pi), 0.2 * self.rng.random()
        self.balls.append([next(self.numbers), r * math.cos(a + 2.0), r * math.sin(a + 2.0), math.cos(a), math.sin(a)])
        return True

    def drop(self):
        """The newest ball gone. False: there's none."""
        if not self.balls:
            return False
        gone = self.balls.pop()[0]
        self.last = {k: t for k, t in self.last.items() if k[0] != gone}
        return True

    def shake(self):
        """Every ball off another way, as fast as ever (Y): a flurry of new notes."""
        for b in self.balls:
            a = self.rng.uniform(0, 2 * math.pi)
            b[3], b[4] = math.cos(a), math.sin(a)

    def reshape(self, sides):
        """Another shape: the balls stay where they are, pushed inside it if they're out."""
        self.sides = sides
        self.last = {}
        self.step(0.0)

    def clone(self):
        """A copy to look ahead with: where the balls will be, if nothing's pressed meanwhile."""
        c = World.__new__(World)
        c.sides, c.spin, c.speed, c.angle, c.t = self.sides, self.spin, self.speed, self.angle, self.t
        c.balls = [list(b) for b in self.balls]
        c.last, c.rng, c.numbers = dict(self.last), self.rng, self.numbers
        return c

    def walls(self):
        """Each wall's outward way (unit x, y), wall k between corners k and k + 1."""
        n, a = self.sides, self.angle
        return [(math.cos(a + math.pi * (2 * k + 1) / n), math.sin(a + math.pi * (2 * k + 1) / n)) for k in range(n)]

    def corners(self):
        n, a = self.sides, self.angle
        return [(math.cos(a + 2 * math.pi * k / n), math.sin(a + 2 * math.pi * k / n)) for k in range(n)]

    def step(self, dt):
        """dt seconds on (a step at a time): [(the wall, when it was hit, the ball, how hard, where across)]: a ball
        that's come off it, how straight on (1: head on, as fast as it goes; less, a glancing blow), and how far left
        or right it was (-1 to 1, as the shape's drawn)."""
        hits = []
        n = max(1, math.ceil(dt / STEP - 1e-9))
        h = dt / n
        far = math.cos(math.pi / self.sides) - RADIUS     # how far a ball's middle can be from the shape's, along a
        clear = far * far                                 # wall's way out (nearer than that every way: no wall near)
        for _ in range(n):
            self.t += h
            self.angle = (self.angle + self.spin * h) % (2 * math.pi)
            ways = None
            for b in self.balls:
                num, x, y, dx, dy = b
                x += dx * self.speed * h
                y += dy * self.speed * h
                if x * x + y * y > clear:                 # (near a wall: which, if any)
                    ways = ways or self.walls()
                    for _ in range(3):                    # (in a corner, pushed in off one wall and out of the other:
                        moved = False                     #  the walls again)
                        for k, (ux, uy) in enumerate(ways):
                            out = x * ux + y * uy - far
                            if out <= 0:
                                continue
                            moved = True
                            wn = -self.spin * (y * ux - x * uy)    # (the wall's own speed, outward, where the ball is)
                            vx, vy = dx * self.speed, dy * self.speed
                            vn = vx * ux + vy * uy
                            if vn > wn:                   # (going out faster than the wall: off it, as off a mirror)
                                vx -= 2 * (vn - wn) * ux
                                vy -= 2 * (vn - wn) * uy
                                sp = math.hypot(vx, vy)
                                if sp > 1e-9:
                                    dx, dy = vx / sp, vy / sp
                                key = (num, k)
                                if self.t - self.last.get(key, -1.0) >= AGAIN:
                                    hard = min(1.0, (vn - wn) / self.speed) if self.speed > 0 else 1.0
                                    hits.append((k, self.t, num, round(hard, 3), round(x - out * ux, 3)))
                                self.last[key] = self.t
                            x -= out * ux                 # (inside again)
                            y -= out * uy
                        if not moved:
                            break
                    else:                                 # (still out, deep in a sharp corner: towards the middle
                        most = max(x * ux + y * uy for ux, uy in ways) / far   # till it's in)
                        if most > 1.0:
                            x, y = x / most, y / most
                b[1:] = x, y, dx, dy
        return hits

    def inside(self, slack=1e-6):
        """Every ball inside every wall (the tests')."""
        far = math.cos(math.pi / self.sides) - RADIUS
        return all(x * ux + y * uy <= far + slack for _, x, y, _, _ in self.balls for ux, uy in self.walls())


def slider_words(key, v):
    """A slider's value, as its page says it: Spin either way (+ anticlockwise), Off for the sound's at 0."""
    if key == "spin":
        return f"{v:+d}" if v else "0"
    return "Off" if key in QUIET and v == 0 else str(v)


def draw_panel(d, box, view, fonts):
    """Its sliders, at the right of the page: X and Y at the top (its sound; Y shakes the balls), then each slider,
    the one ▲▼ picked lit, its value at its right (◀▶ move it), and under them a few words on what it does."""
    from .theme import ACCENT, ACCENTS, BG, BODY, co_mix, MUTED, ROW, TEXT
    x0, y0, x1, y1 = box
    hues = dict(ACCENTS)
    ih = fonts["info_h"]
    r = ih * 0.32
    rows = view["sliders"]
    says = SAYS.get(rows[view["sel"] % len(rows)][0], "") if rows else ""
    f = fonts["caption"]
    while len(says) > 3 and f.getlength(says) > x1 - x0 - 12:
        says = says[:-2].rstrip() + "…"
    d.text((x0 + 12, y1 - ih * 0.4), says, font=f, fill=MUTED, anchor="lm")
    y1 -= ih * 0.8
    for (letter, colour), words in ((("X", hues["Pink"]), view["sound"]), (("Y", hues["Gold"]), "Shake the balls")):
        mid = y0 + ih / 2
        d.ellipse((x0 + 6, mid - r, x0 + 6 + 2 * r, mid + r), fill=colour)
        d.text((x0 + 6 + r, mid), letter, font=fonts["badge"], fill=co_mix(colour, (16, 19, 23), 0.85), anchor="mm")
        f = fonts["info"]
        room = x1 - x0 - 2 * r - 22
        while len(words) > 3 and f.getlength(words) > room:
            words = words[:-2].rstrip() + "…"
        d.text((x0 + 2 * r + 16, mid), words, font=f, fill=TEXT, anchor="lm")
        y0 += ih
    y0 += 6
    rh = (y1 - y0) / max(1, len(rows))
    knob, thick = fonts["knob"], fonts["track"]
    for i, (key, label, v, low, high) in enumerate(rows):
        on = i == view["sel"]
        top = y0 + i * rh
        if on:
            d.rounded_rectangle((x0, top + 1, x1, top + rh - 2), radius=10, fill=ROW)
        ly, ty = top + rh * 0.36, top + rh * 0.72
        tx0, tx1 = x0 + 12 + knob, x1 - 12 - knob
        d.text((x0 + 12, ly), label, font=fonts["label_b" if on else "label"], fill=TEXT if on else BODY, anchor="lm")
        words = slider_words(key, v)
        f = fonts["label_b" if on else "label"]
        vx = x1 - 12
        if on:                                         # (◀ and ▶ either side of it: they move it)
            a = knob * 0.7
            d.polygon([(vx, ly), (vx - a, ly - a), (vx - a, ly + a)], fill=ACCENT)
            vx -= a + 8
            d.text((vx, ly), words, font=f, fill=TEXT, anchor="rm")
            lx = vx - f.getlength(words) - 8
            d.polygon([(lx - a, ly), (lx, ly - a), (lx, ly + a)], fill=ACCENT)
        else:
            d.text((vx, ly), words, font=f, fill=MUTED, anchor="rm")
        at = (v - low) / (high - low) if high > low else 0.0
        kx = tx0 + (tx1 - tx0) * at
        zero = tx0 + (tx1 - tx0) * ((0 - low) / (high - low) if low < 0 else 0.0)   # (Spin: from the middle)
        d.rounded_rectangle((tx0, ty - thick / 2, tx1, ty + thick / 2), radius=thick / 2,
                            fill=co_mix(BG, TEXT, 0.14))
        a, b = sorted((zero, kx))
        if b - a >= 1:
            d.rounded_rectangle((a, ty - thick / 2, b, ty + thick / 2), radius=thick / 2,
                                fill=ACCENT if on else co_mix(BG, TEXT, 0.38))
        k = knob if on else knob * 0.8
        d.ellipse((kx - k, ty - k, kx + k, ty + k), fill=TEXT if on else co_mix(BG, TEXT, 0.6))


def draw(d, box, view, fonts, now):
    """The shape and its balls, in one colour (the accent: its walls dim, lit a moment when hit), as big as fits in box
    (the page under its top line). view: what screens/soundboard.py says of it (soundboard.py's Soundboard.bounce)."""
    from .theme import BG, co_mix, TEXT
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    r = min(x1 - x0, y1 - y0) / 2 - 12
    big = r > 220                                         # (a bigger screen: thicker walls)
    thin, thick = (7, 12) if big else (5, 8)
    pts = [(cx + r * x, cy - r * y) for x, y in view["corners"]]   # (the page's y goes down)
    n = len(pts)
    lit = view["lit"]
    order = sorted(range(n), key=lambda k: lit[k])        # (the lit ones drawn last, over their corners)
    colour = view["colour"]
    for k in order:
        glow = max(0.0, 1.0 - (now - lit[k]) / LIT) if lit[k] else 0.0
        width = round(thin + (thick - thin) * glow)
        fill = co_mix(co_mix(BG, colour, DIM), colour, glow)
        a, b = pts[k], pts[(k + 1) % n]
        d.line((a, b), fill=fill, width=width)
        for px, py in (a, b):                             # (round corners: no notch where two walls meet)
            d.ellipse((px - width / 2, py - width / 2, px + width / 2, py + width / 2), fill=fill)
    br = max(4, r * RADIUS)
    for x, y in view["balls"]:
        bx, by = cx + r * x, cy - r * y
        d.ellipse((bx - br, by - br, bx + br, by + br), fill=colour)
    if view["paused"]:
        d.text((cx, cy), "Paused", font=fonts["bold"], fill=TEXT, anchor="mm")
    elif not view["balls"]:
        d.text((cx, cy), "A adds a ball", font=fonts["small"], fill=co_mix(BG, TEXT, 0.6), anchor="mm")
