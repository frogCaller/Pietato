"""Apps > LED backlight, on the screen: a picture of the LEDs behind your TV, lit as they are now (its own colour, a
game's, music's), beside how it's set: the 8x8 grid, or a TV with the strip round it. Its buttons, its options and the
LEDs themselves are media mode's (screens/glow.py, glow.py): this just draws them, and only as often as they change.
On a Pietato with no LEDs of its own, the picture is of your ESP32 boards instead: an LED for each, in its own colour
(dark, if it takes what's playing), with its name."""
import math
import time

from .fine import detail, made_fine
from .glow import TV_H, TV_W
from .sims import Sim
from .theme import BODY, FONT_UI, FONT_UI_BOLD, MUTED

BOARD = (12, 14, 17)                     # the grid's board (and the TV's screen)
BOARD_EDGE = (44, 50, 58)
UNLIT = (40, 44, 51)                     # an LED that's off
CORE = 0.31                              # an LED's size, of the space for each (its radius)
HALO = 0.78                              # ...and its light's
STEADY, LIVELY, OFF = 1.0, 0.2, 2.0      # seconds to its next picture: the LEDs as they are; changing; off
FOOT = 100                               # your ESP32 boards' picture: the room kept at the foot of the box (its card)
BOARD_W, BOARD_H = 104, 96               # ...the least room for a board with its name under it (fewer fit: no names)


class Backlight(Sim):
    key = "glow"
    blurb = "The LEDs behind your TV, lit by your games and music, or in a colour you pick."
    poke_label = None
    options = ()
    paced = True                         # drawn again as the LEDs change (frame_in), not frame by frame
    backdrop = (14, 16, 20)

    def __init__(self, w, h, rng=None, values=None):
        super().__init__(w, h, rng, values)
        self.plain = False               # no LEDs of this Pietato's own: your ESP32 boards' picture instead
        self.lamps = []                  # ...those boards: (name, how many LEDs, its own colour or None)
        self.tags = {}                   # (words, size, bold, detail) -> their mask, and its size
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

    def tag(self, text, size, bold, s):
        """A few words as a mask in the screen's own pixels (a board's name, how many LEDs it has), and how wide and
        tall they are: made once."""
        key = (text, size, bold, s)
        got = self.tags.get(key)
        if got is None:
            from PIL import Image, ImageDraw, ImageFont
            try:
                font = ImageFont.truetype(FONT_UI_BOLD if bold else FONT_UI, round(size * s))
            except OSError:
                font = ImageFont.load_default()
            l, t, r, b = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), text, font=font)
            w, h = -(-(r - l + 2) // s) * s, -(-(b - t + 2) // s) * s     # (whole pixels of the picture's own)
            pic = Image.new("L", (max(s, w), max(s, h)), 0)
            ImageDraw.Draw(pic).text((1 - l, 1 - t), text, font=font, fill=255)
            if len(self.tags) > 200:
                self.tags = {}
            got = self.tags[key] = (made_fine(pic, s), pic.width / s, pic.height / s)
        return got

    def draw_boards(self, img, x0, y0):
        """Your ESP32 boards, an LED each: lit in its own colour, or dark (it takes what's playing); its name under
        it, and how many LEDs it has if that's more than one. More of them than there's room to name: just the LEDs."""
        n = len(self.lamps)
        if not n:
            return
        s = detail(img)
        room = max(BOARD_H, self.h - FOOT)             # (above the card at the foot of the box)
        across, down = max(1, int(self.w // BOARD_W)), max(1, int(room // BOARD_H))
        named = n <= across * down
        if named:
            cols = min(n, across)
            rows = math.ceil(n / cols)
            cw, ch = self.w / cols, min(room / rows, BOARD_H + 16)
            core_d = 24.0
        else:
            cols = max(1, math.ceil(math.sqrt(n * self.w / room)))
            rows = math.ceil(n / cols)
            cw = ch = min(self.w / cols, room / rows)
            core_d = max(4.0, min(24.0, cw * 0.45))
        halo_d = core_d * HALO / CORE
        halo, core, hn, cn = self.light(core_d, halo_d, s)
        top = (room - rows * ch) / 2

        def put(mask, x, y, col):         # (on the picture's own pixels)
            x, y = round(x * s) / s, round(y * s) / s
            img.paste(col, (x, y) if s > 1 else (int(x), int(y)), mask)

        def words(text, cx, y, size, bold, col):
            mask, w, h = self.tag(text, size, bold, s)
            if w > cw - 4 and text.startswith("ESP32 "):   # (no room for all of its name: the part that's its own)
                mask, w, h = self.tag(text[6:], size, bold, s)
            while w > cw - 4 and len(text) > 2:
                text = text[:-2].rstrip() + "…"
                mask, w, h = self.tag(text, size, bold, s)
            put(mask, cx - w / 2, y, col)
        for k, (name, count, colour) in enumerate(self.lamps):
            row, i = divmod(k, cols)
            here = min(cols, n - row * cols)           # (the last row: in the middle)
            cx = x0 + (self.w - here * cw) / 2 + (i + 0.5) * cw
            cy = y0 + top + (row + 0.5) * ch - (16 if named else 0)
            if colour is not None and max(colour) >= 12:
                put(halo, cx - hn / 2, cy - hn / 2, tuple(colour))
            put(core, cx - cn / 2, cy - cn / 2, UNLIT if colour is None else
                tuple(max(v, u) for v, u in zip(colour, UNLIT)) if max(colour) < 40 else tuple(colour))
            if named:
                words(name, cx, cy + core_d / 2 + 9, 12, True, BODY)
                if count > 1:
                    words(f"{count} LEDs", cx, cy + core_d / 2 + 26, 11, False, MUTED)

    def draw(self, img, x0, y0):
        from .fine import ImageDraw
        pic = self.colours()
        self.drawn = pic
        if self.plain:
            self.draw_boards(img, x0, y0)
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
