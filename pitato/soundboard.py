"""Apps' Soundboard: a sound on every button. The d-pad's four and A, B, X and Y each play the sound that's on them,
as many at once as you like (pressed again while it plays, a sound starts again); SELECT stops them all; L and R go
through the banks of eight. START has the rest: the bank, the volume, a new sound recorded with a USB microphone and
put on a button, and B there goes back (here, B is a button like the others).

The sounds: a starter pack that comes with Pietato (pitato/sounds, public domain), and your own, wav, mp3 or ogg files
in the Soundboard folder of your home folder. A new file there is on a button a moment later (My sounds' first free
one). The web page's Soundboard adds, records, renames and deletes them, and puts them on the buttons.

This draws the page: the bank's name, and the buttons laid out as they are on a controller, each with its sound's
name, lit while it plays. (soundbank.py: the sounds and banks. soundplay.py: the player, a process of its own.
screens/soundboard.py: its buttons, and what media mode does for it.)"""
from .sims import Sim
from .theme import ACCENTS, BG, BODY, co_mix, FONT_UI, FONT_UI_BOLD, LINE, MUTED, ROW, TEXT, WARN

_HUES = dict(ACCENTS)
PAD_COLOUR = {"up": _HUES["Blue"], "left": _HUES["Teal"], "right": _HUES["Green"], "down": _HUES["Purple"],
              "x": _HUES["Pink"], "y": _HUES["Gold"], "a": _HUES["Red"], "b": _HUES["White"]}   # each button's own
PAD_NAME = {"up": "▲", "left": "◀", "right": "▶", "down": "▼", "x": "X", "y": "Y", "a": "A", "b": "B"}
PAD_PLACE = {"up": (0, 0.5, 0), "left": (0, 0, 1), "right": (0, 1, 1), "down": (0, 0.5, 2),     # (which side, how far
             "x": (1, 0.5, 0), "y": (1, 0, 1), "a": (1, 1, 1), "b": (1, 0.5, 2)}                # across it, which row)
TOP = 40                         # px for the bank's line
EDGE, GAP, MIDDLE = 12, 8, 24    # px round the buttons, between them, between the d-pad's and the letters'
STILL = 30.0                     # seconds between its frames when nothing changes (it's drawn again when something does)
REC_CARD = (344, 118)


class Soundboard(Sim):
    key = "sound"
    blurb = "A sound on every button. Your own go in your Soundboard folder, or on from the web page."
    poke_label = None
    options = ()
    bare = True                         # on the page itself: no box, and nothing beside it
    paced = True                        # drawn again when something changes, not frame by frame
    top_px = TOP                        # px above its buttons (the Band's page, made from this one, has more there)

    def __init__(self, w, h, rng=None, values=None):
        super().__init__(w, h, rng, values)
        self.bank = (0, 1, "")          # which bank, of how many, its name
        self.pads = {}                  # button -> (its sound's name, "ready", "loading" or "bad"); none: nothing on it
        self.lit = frozenset()          # the buttons whose sounds are playing
        self.trouble = ""               # a few words at the top left when the sound can't be heard
        self.placing = None             # a sound being put on a button: (its name, the button it's on in this bank)
        self.rec = None                 # recording: (seconds so far, how loud just now, 0 to 1)
        self.own_hints = []             # its buttons
        self.taps = []                  # where its buttons are on the screen: (box, the button)
        self.fonts = {}
        self.tiles = {}

    @property
    def backdrop(self):
        return BG                       # (the page's own colour, as it is now)

    def relook(self):
        self.tiles.clear()

    def update(self, dt):
        return None

    def frame_in(self, wall):
        return STILL

    def hints(self):
        return self.own_hints

    def refit(self, w, h):
        self.w, self.h = w, h

    def font(self, size, bold=False):
        key = (size, bold)
        if key not in self.fonts:
            from PIL import ImageFont
            try:
                basic = ImageFont.Layout.BASIC if hasattr(ImageFont, "Layout") else ImageFont.LAYOUT_BASIC
                self.fonts[key] = ImageFont.truetype(FONT_UI_BOLD if bold else FONT_UI, size, layout_engine=basic)
            except OSError:
                self.fonts[key] = ImageFont.load_default()
        return self.fonts[key]

    def boxes(self):
        """Where each button's tile is on the page (x, y, w, h): the d-pad's four on the left as they are on a
        controller (up, left and right, down), the letters' on the right (X, Y and A, B)."""
        tw = (self.w - 2 * EDGE - MIDDLE - 2 * GAP) // 4
        th = max(40, (self.h - self.top_px - 2 * GAP - EDGE // 2) // 3)
        out = {}
        for pad, (side, across, row) in PAD_PLACE.items():
            x = EDGE + side * (2 * tw + GAP + MIDDLE) + round(across * (tw + GAP))
            out[pad] = (x, self.top_px + row * (th + GAP), tw, th)
        return out

    @staticmethod
    def fitted(text, font, width, lines=2):
        """A sound's name on its tile: broken at spaces over two lines at most, what's left over cut short (…)."""
        def cut(s):
            if font.getlength(s) <= width:
                return s
            while len(s) > 1 and font.getlength(s + "…") > width:
                s = s[:-1]
            return s.rstrip() + "…"
        words, out, line = text.split(), [], ""
        for k, word in enumerate(words):
            trial = (line + " " + word).strip()
            if font.getlength(trial) <= width or not line:
                line = trial
                continue
            if len(out) == lines - 1:                  # (the last line: all the rest on it, cut to fit)
                line = line + " " + " ".join(words[k:])
                break
            out.append(line)
            line = word
        out.append(line)
        return [cut(s) for s in out[:lines]]

    @staticmethod
    def arrow(d, pad, cx, cy, r, fill):
        """The d-pad's arrows, drawn (a font may not have them)."""
        pts = {"up": [(cx, cy - r), (cx + r, cy + r * 0.8), (cx - r, cy + r * 0.8)],
               "down": [(cx, cy + r), (cx + r, cy - r * 0.8), (cx - r, cy - r * 0.8)],
               "left": [(cx - r, cy), (cx + r * 0.8, cy - r), (cx + r * 0.8, cy + r)],
               "right": [(cx + r, cy), (cx - r * 0.8, cy - r), (cx - r * 0.8, cy + r)]}[pad]
        d.polygon(pts, fill=fill)

    def tile(self, pad, w, h):
        """A button's tile: its key, and its sound's name. Lit in its own colour while its sound plays. Kept."""
        from .fine import Image, ImageDraw, scale
        got = self.pads.get(pad)
        lit = pad in self.lit and got is not None
        here = self.placing is not None and self.placing[1] == pad
        key = (pad, got, lit, here, w, h, scale())
        tile = self.tiles.get(key)
        if tile is not None:
            return tile
        colour = PAD_COLOUR[pad]
        tile = Image.new("RGB", (w, h), BG)
        d = ImageDraw.Draw(tile)
        big = h >= 104                                 # (a bigger screen than the GPi Case's: bigger words to match)
        f, small = self.font(19 if big else 16, bold=True), self.font(15 if big else 13)
        r, step = (14, 24) if big else (12, 20)
        if got is None:                                # nothing on it
            d.rounded_rectangle((0, 0, w - 1, h - 1), radius=12, fill=co_mix(BG, ROW, 0.45), outline=LINE)
            cap, ink, words = co_mix(ROW, colour, 0.3), co_mix(BG, ROW, 0.45), [("Empty", MUTED)]
        else:
            name, state = got
            if lit:
                d.rounded_rectangle((0, 0, w - 1, h - 1), radius=12, fill=colour)
                cap, ink, text = co_mix(colour, BG, 0.82), colour, co_mix(colour, BG, 0.9)
            else:
                d.rounded_rectangle((0, 0, w - 1, h - 1), radius=12, fill=ROW,
                                    outline=TEXT if here else LINE, width=2 if here else 1)
                cap, ink = colour, co_mix(colour, BG, 0.85)
                text = TEXT if state == "ready" else MUTED
            words = [(line, text) for line in self.fitted(name, f, w - 26)]
            if state == "bad" and not lit:
                words = words[:1] + [("Can't play it", co_mix(WARN, ROW, 0.25))]
        d.ellipse((11, 10, 11 + 2 * r, 10 + 2 * r), fill=cap)
        if pad in ("up", "down", "left", "right"):
            self.arrow(d, pad, 11 + r, 10 + r, r * 0.46, ink)
        else:
            d.text((11 + r, 10 + r), PAD_NAME[pad], font=self.font(14 if not big else 16, bold=True), fill=ink,
                   anchor="mm")
        y = max(20 + 2 * r, h - 14 - step * len(words)) + step // 2 - 1
        for k, (line, fill) in enumerate(words):
            plain = got is None or (k and got[1] == "bad" and not lit)
            d.text((13, y), line, font=small if plain else f, fill=fill, anchor="lm")
            y += step
        if len(self.tiles) > 300:
            self.tiles.clear()
        self.tiles[key] = tile
        return tile

    def top(self, d, x0, y0):
        """The bank's line: its name between ◀ and ▶ (L and R), which it is of how many; putting a sound on a
        button, what to do instead of the count. A few words at the left if the sound can't be heard."""
        i, n, name = self.bank
        W, mid = self.w, y0 + TOP // 2 - 2
        f, small = self.font(18, bold=True), self.font(13)
        name = name or "Soundboard"
        while len(name) > 4 and f.getlength(name) > W * 0.42:
            name = name[:-2].rstrip() + "…"
        nw = f.getlength(name)
        cx = x0 + W / 2
        d.text((cx, mid), name, font=f, fill=TEXT, anchor="mm")
        if n > 1:
            self.arrow(d, "left", cx - nw / 2 - 20, mid, 5, MUTED)
            self.arrow(d, "right", cx + nw / 2 + 20, mid, 5, MUTED)
        if self.placing is not None:
            words = f"Press a button for {self.placing[0]}"
            room = W / 2 - nw / 2 - 44 - EDGE
            while len(words) > 8 and small.getlength(words) > room:
                words = words[:-2].rstrip() + "…"
            d.text((x0 + EDGE + 2, mid), words, font=small, fill=TEXT, anchor="lm")
        elif self.trouble:
            d.text((x0 + EDGE + 2, mid), self.trouble, font=small, fill=WARN, anchor="lm")
        if n > 1:
            d.text((x0 + W - EDGE - 2, mid), f"{i + 1} of {n}", font=small, fill=MUTED, anchor="rm")
        self.taps.append(((x0, y0, x0 + W // 2, y0 + TOP - 4), "l"))
        self.taps.append(((x0 + W // 2, y0, x0 + W, y0 + TOP - 4), "r"))

    def rec_card(self, img, x0, y0):
        """Recording: how long so far, and how loud it is just now."""
        from .fine import Image, ImageDraw
        secs, level = self.rec
        w, h = REC_CARD
        card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(card)
        red = _HUES["Red"]
        d.rounded_rectangle((0, 0, w - 1, h - 1), radius=12, fill=ROW + (255,), outline=LINE + (255,))
        d.ellipse((22, 24, 34, 36), fill=red + (255,))
        d.text((44, 30), "Recording", font=self.font(18, bold=True), fill=TEXT + (255,), anchor="lm")
        d.text((w - 22, 30), f"{int(secs) // 60}:{int(secs) % 60:02d}", font=self.font(18, bold=True),
               fill=TEXT + (255,), anchor="rm")
        d.rounded_rectangle((22, 56, w - 23, 68), radius=6, fill=BG + (255,))
        loud = max(0.0, min(1.0, level)) ** 0.5        # (quiet sounds show too)
        if loud > 0.02:
            d.rounded_rectangle((22, 56, 22 + max(12, round((w - 45) * loud)), 68), radius=6,
                                fill=(red if level > 0.94 else _HUES["Green"]) + (255,))
        d.text((22, 92), "Make your sound. The silence round it is trimmed.", font=self.font(13), fill=BODY + (255,),
               anchor="lm")
        img.paste(card, (x0 + (self.w - w) // 2, y0 + (self.h - h) // 2), card)

    def draw(self, img, x0, y0):
        from .fine import ImageDraw
        self.taps = []
        self.top(ImageDraw.Draw(img), x0, y0)
        for pad, (x, y, w, h) in self.boxes().items():
            img.paste(self.tile(pad, w, h), (x0 + x, y0 + y))
            self.taps.append(((x0 + x, y0 + y, x0 + x + w, y0 + y + h), pad))
        if self.rec is not None:
            self.taps = []                             # (recording: its buttons are A and B, along the bottom)
            self.rec_card(img, x0, y0)
