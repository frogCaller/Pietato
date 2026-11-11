"""Apps > LED backlight, on the screen: a picture of the LEDs behind your TV, lit as they are now (its own colour, a
game's, music's), beside how it's set: the 8x8 grid, or a TV with the strip round it. Its buttons, its options and the
LEDs themselves are media mode's (screens/glow.py, glow.py): this just draws them, and only as often as they change."""
import time

from .fine import detail, made_fine
from .glow import TV_H, TV_W
from .sims import Sim

BOARD = (12, 14, 17)                     # the grid's board (and the TV's screen)
BOARD_EDGE = (44, 50, 58)
UNLIT = (40, 44, 51)                     # an LED that's off
CORE = 0.31                              # an LED's size, of the space for each (its radius)
HALO = 0.78                              # ...and its light's
STEADY, LIVELY, OFF = 1.0, 0.2, 2.0      # seconds to its next picture: the LEDs as they are; changing; off


class Backlight(Sim):
    key = "glow"
    blurb = "The LEDs behind your TV, lit by your games and music, or in a colour you pick."
    poke_label = None
    options = ()
    paced = True                         # drawn again as the LEDs change (frame_in), not frame by frame
    backdrop = (14, 16, 20)

    def __init__(self, w, h, rng=None, values=None):
        super().__init__(w, h, rng, values)
        self.plain = False               # no LEDs of this Pietato's own: no picture of them (its note says the rest)
        self.grid = None                 # the LEDs, while they're on (glow.Grid): media mode's
        self.points = None               # a strip's LEDs, where each is round the TV (0 to 1 across and down), or None
        self.shade = 1.0                 # its picture drawn this bright, for how bright the LEDs are
        self.facts = []                  # (label, value) beside it
        self.says = None                 # (title, words) at the foot of its picture, or None
        self.own_hints = []              # its buttons
        self.sprites = {}                # (sizes, detail) -> an LED's light and its middle (masks)
        self.drawn = None                # the colours last drawn

    def update(self, dt):
        return None

    def colours(self):
        """The LEDs' colours now, as they're seen (the grid's rows x cols x 3, or a strip's n x 3), or None: off, or
        not lit yet (or a strip that's not the one drawn: about to be)."""
        g = self.grid
        if g is None:
            return None
        if self.points is None:
            return g.picture() if g.lit() is None else None
        got = g.lit()
        return got[1] if got is not None and len(got[1]) == len(self.points) else None

    def frame_in(self, wall):
        g = self.grid
        if g is None:
            return OFF
        now = self.colours()
        if now is not None and (self.drawn is None or self.drawn.shape != now.shape
                                or abs(now - self.drawn).max() >= 2):
            return LIVELY                 # (changed since it was drawn)
        return LIVELY if g.lively(time.monotonic()) else STEADY

    def stats(self):
        return self.facts

    def note(self):
        return self.says

    def hints(self):
        return self.own_hints

    def light(self, core_d, halo_d, s):
        """An LED's light round it and its middle (this wide across), as masks: made once for each size."""
        key = (round(core_d, 2), round(halo_d, 2), s)
        got = self.sprites.get(key)
        if got is None:
            from PIL import Image, ImageDraw, ImageFilter
            n = max(4, round(halo_d * s))
            halo = Image.new("L", (n, n), 0)
            r = n * 0.26
            ImageDraw.Draw(halo).ellipse((n / 2 - r, n / 2 - r, n / 2 + r, n / 2 + r), fill=150)
            halo = halo.filter(ImageFilter.GaussianBlur(n * 0.13))
            k = 4                         # (drawn 4 times as big, then made smaller: round edges)
            m = max(2, round(core_d * s))
            core = Image.new("L", (m * k, m * k), 0)
            ImageDraw.Draw(core).ellipse((0, 0, m * k - 1, m * k - 1), fill=255)
            core = core.resize((m, m), Image.LANCZOS)
            got = self.sprites[key] = (made_fine(halo, s), made_fine(core, s), n / s, m / s)
            if len(self.sprites) > 8:
                self.sprites = {key: got}
        return got

    def board(self):
        """Where the grid goes in the box: (left, top, the space for each LED), as big as fits."""
        side = max(80, min(self.w - 48, self.h - 32))
        return (self.w - side) / 2, (self.h - side) / 2, side / 8

    def tv(self):
        """Where the TV goes in the box, with room round it for the strip: (left, top, width, height)."""
        tw = max(80, min(self.w - 96, (self.h - 96) * TV_W / TV_H))
        th = tw * TV_H / TV_W
        return (self.w - tw) / 2, (self.h - th) / 2, tw, th

    def draw(self, img, x0, y0):
        from .fine import ImageDraw
        pic = self.colours()
        self.drawn = pic
        if self.plain:
            return
        s = detail(img)
        d = ImageDraw.Draw(img)
        lit = pic is not None and pic.max() >= 4
        shown = (pic * self.shade).clip(0, 255).round().astype(int).tolist() if lit else None
        spots = []                        # (its middle, its colour or None: off)
        if self.points is None:
            bx, by, pitch = self.board()
            d.rounded_rectangle((x0 + bx - pitch * 0.25, y0 + by - pitch * 0.25, x0 + bx + pitch * 8.25,
                                 y0 + by + pitch * 8.25), radius=pitch * 0.35, fill=BOARD, outline=BOARD_EDGE)
            core_d, halo_d = 2 * CORE * pitch, 2 * HALO * pitch
            for r in range(8):
                for c in range(8):
                    spots.append(((x0 + bx + (c + 0.5) * pitch, y0 + by + (r + 0.5) * pitch),
                                  tuple(shown[r][c]) if lit else None))
        else:
            tx, ty, tw, th = self.tv()
            tx, ty = x0 + tx, y0 + ty
            d.rounded_rectangle((tx, ty, tx + tw, ty + th), radius=6, fill=BOARD, outline=BOARD_EDGE, width=2)
            n = len(self.points)
            pitch = (2 * tw + 2 * th) / max(1, n)
            core_d, halo_d = max(3.0, min(14.0, pitch * 0.66)), max(10.0, min(34.0, pitch * 2.4))
            gap = 6 + core_d / 2              # (the strip, just round the TV's edge)
            for i, (fx, fy) in enumerate(self.points.tolist()):
                if fy < 1e-3:
                    at = (tx + fx * tw, ty - gap)
                elif fy > 1 - 1e-3:
                    at = (tx + fx * tw, ty + th + gap)
                elif fx < 1e-3:
                    at = (tx - gap, ty + fy * th)
                else:
                    at = (tx + tw + gap, ty + fy * th)
                spots.append((at, tuple(shown[i]) if lit else None))
        halo, core, hn, cn = self.light(core_d, halo_d, s)

        def put(mask, at, size, col):     # (on the picture's own pixels)
            x, y = round((at[0] - size / 2) * s) / s, round((at[1] - size / 2) * s) / s
            img.paste(col, (x, y) if s > 1 else (int(x), int(y)), mask)
        for at, col in spots:             # their light first, under all of them
            if col is not None and max(col) >= 12:
                put(halo, at, hn, col)
        for at, col in spots:
            if col is None or max(col) < 40:   # (dark, or nearly: an LED that's off, as it looks)
                col = UNLIT if col is None else tuple(max(v, u) for v, u in zip(col, UNLIT))
            put(core, at, cn, col)
