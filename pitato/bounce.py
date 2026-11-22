"""The Soundboard's Bounce (Apps > Soundboard, START's card > Bounce): a shape turning slowly in the middle of the page,
balls bouncing about inside it, and each of its walls a note. A ball that hits a wall plays that wall's note, and the
wall lights up a moment. The notes are a scale's, from its key up, wall after wall round the shape, so whatever's hit
sounds right with the rest. (screens/soundboard.py: its buttons, its notes to the player, the web page's say.
soundplay.py: the notes played, a few at a time, and their echo. soundboard.py: its page, drawn with this.)

The shape's corners are 1 from its middle, and everything's measured that way: the page draws it as big as it fits.
A ball goes in a straight line at the speed it's set to, and comes off a wall as off a mirror; off one that's turning
into it, a little sooner, but never faster than it's set to (the shape turning doesn't speed the balls up)."""
import colorsys
import itertools
import math
import random

SHAPES = (("Triangle", 3), ("Square", 4), ("Pentagon", 5), ("Hexagon", 6))
SCALES = {"Major": (0, 2, 4, 5, 7, 9, 11), "Minor": (0, 2, 3, 5, 7, 8, 10), "Pentatonic": (0, 2, 4, 7, 9),
          "Blues": (0, 3, 5, 6, 7, 10)}
KEYS = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
TONES = ("Bell", "Pluck", "Pad")       # its own sounds (the player makes them): Tones/Bell and so on
TONE_ROOT = 60                         # ...each made at this note (MIDI: middle C)
BALLS_MOST = 8
BALLS_FIRST = 3                        # balls in it the first time
RADIUS = 0.05                          # a ball's (of the shape's corners' distance from its middle)
SPIN_STEP, SPIN_MOST = 0.1, 1.5        # radians a second: each press of ◀ or ▶, and at most either way round
SPEED_STEP, SPEEDS = 0.2, (0.2, 2.4)   # (its corners' distance from its middle) a second: each press of ▲ or ▼
STEP = 1 / 120                         # seconds of each step of the balls
AGAIN = 0.06                           # seconds before a ball's heard on the same wall again (a corner: one note)
LIT = 0.3                              # seconds a wall stays lit after a ball hits it


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


def wall_colour(note):
    """A note's colour: round the colour wheel by fifths, so the walls next to each other are well apart."""
    r, g, b = colorsys.hsv_to_rgb((note * 7 % 12) / 12.0, 0.55, 1.0)
    return int(r * 255), int(g * 255), int(b * 255)


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
        """dt seconds on (a step at a time): [(the wall, when it was hit, the ball)]: a ball that's come off it."""
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
                                    hits.append((k, self.t, num))
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


def draw(d, box, view, fonts, now):
    """The shape, its walls in their notes' colours (lit a moment when hit), and the balls, as big as fits in box (the
    page under its top line). view: what screens/soundboard.py says of it (soundboard.py's Soundboard.bounce)."""
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
    for k in order:
        colour = view["colours"][k]
        glow = max(0.0, 1.0 - (now - lit[k]) / LIT) if lit[k] else 0.0
        width = round(thin + (thick - thin) * glow)
        fill = co_mix(co_mix(BG, colour, 0.45), colour, glow)
        a, b = pts[k], pts[(k + 1) % n]
        d.line((a, b), fill=fill, width=width)
        for px, py in (a, b):                             # (round corners: no notch where two walls meet)
            d.ellipse((px - width / 2, py - width / 2, px + width / 2, py + width / 2), fill=fill)
    br = max(4, r * RADIUS)
    for x, y in view["balls"]:
        bx, by = cx + r * x, cy - r * y
        d.ellipse((bx - br, by - br, bx + br, by + br), fill=TEXT)
    if view["paused"]:
        d.text((cx, cy), "Paused", font=fonts["bold"], fill=TEXT, anchor="mm")
    elif not view["balls"]:
        d.text((cx, cy), "A adds a ball", font=fonts["small"], fill=co_mix(BG, TEXT, 0.6), anchor="mm")
