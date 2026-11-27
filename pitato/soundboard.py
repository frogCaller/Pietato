"""Apps' Soundboard: a sound on every button. The d-pad's four and A, B, X and Y each play the sound that's on them,
as many at once as you like (pressed again while it plays, a sound starts again); SELECT goes through the banks of
eight; L and R go round its three pages (these buttons, the Sequencer, Bounce). START has the rest: a loop recorded,
the bank, the volume, a new sound recorded with a USB microphone and put on a button. HOME goes back (B is a button
like the others here).

The sounds: a starter pack that comes with Pietato (pitato/sounds, public domain), and your own, wav, mp3 or ogg files
in the Soundboard folder of your home folder. A new file there is on a button a moment later (My sounds' first free
one). The web page's Soundboard adds, records, renames and deletes them, and puts them on the buttons.

This draws the page: its name between ◀ and ▶ (L and R: its other pages), the bank's name (and a dot for each bank),
and the buttons laid out as they are on a controller (each one's button and its sound's name in its tile's middle),
each with its sound's name, lit from behind in its button's colour, brightly while it plays; the loop, recording or
playing, with the beat it's on, how far round it is and the tempo; and a note played with A, B, X or Y held, on that
button's tile. Bounce instead, while it's up: its shape and balls, and its sliders beside them (bounce.py). Or the
Sequencer: its grid of sounds and steps, and the sound as bars under it (sequencer.py).
(soundbank.py: the sounds and banks. soundplay.py: the player, a process of its own. screens/soundboard.py: its
buttons, and what media mode does for it.)"""
import math
import time

from . import bounce as BN
from . import sequencer as SQ
from .sims import Sim
from .theme import ACCENTS, BG, BODY, co_mix, FONT_UI, FONT_UI_BOLD, LINE, MUTED, ROW, TEXT, WARN

_HUES = dict(ACCENTS)
PAD_COLOUR = {"up": _HUES["Blue"], "left": _HUES["Teal"], "right": _HUES["Green"], "down": _HUES["Purple"],
              "x": _HUES["Pink"], "y": _HUES["Gold"], "a": _HUES["Red"], "b": _HUES["White"]}   # each button's own
PAD_NAME = {"up": "▲", "left": "◀", "right": "▶", "down": "▼", "x": "X", "y": "Y", "a": "A", "b": "B"}
PAD_PLACE = {"up": (0, 0.5, 0), "left": (0, 0, 1), "right": (0, 1, 1), "down": (0, 0.5, 2),     # (which side, how far
             "x": (1, 0.5, 0), "y": (1, 0, 1), "a": (1, 1, 1), "b": (1, 0.5, 2)}                # across it, which row)
TOP = 40                         # px for its line (the page's name, the bank, the loop)
PAGE_NAME = "Soundboard"         # its buttons' page, as its line names it (the others: Sequencer, Bounce)
EDGE, GAP, MIDDLE = 12, 8, 24    # px round the page's own things and between them (the Band's page: its buttons')
SPACE = (0.15, 1.15, 0.2, 0.05)  # its buttons are square, with room to breathe. Of a button's side: between two of
                                 # them, between the d-pad's and the letters' (about as far as a cross's left button
                                 # is from its right: two crosses, apart), at the page's sides at least, and above and
                                 # under them at least
TILE_MOST = 170                  # ...and no bigger than this, px (a big screen): as big as what's on it needs, no more
STILL = 30.0                     # seconds between its frames when nothing changes (it's drawn again when something does)
REC_CARD = (344, 118)
INK = (16, 19, 23)               # the words on a lit tile: dark, whatever the page is
SHADE = (0.07, 0.05)             # a tile, lit a little from above: this much more of its colour at its top, less at
LIT_SHADE = (0.12, 0.10)         # its bottom; one whose sound's playing: this much lighter at its top, darker below
BANK_DOTS = 8                    # banks shown as a dot each, at most (more: which, of how many)


class Soundboard(Sim):
    key = "sound"
    blurb = "A sound on every button. Your own go in your Soundboard folder, or on from the web page."
    poke_label = None
    options = ()
    bare = True                         # on the page itself: no box, and nothing beside it
    paced = True                        # drawn again when something changes, not frame by frame
    top_px = TOP                        # px above its buttons (the Band's page, made from this one, has more there)
    spaced = True                       # its buttons square and apart, in the page's middle (boxes)

    def __init__(self, w, h, rng=None, values=None):
        super().__init__(w, h, rng, values)
        self.bank = (0, 1, "")          # which bank, of how many, its name
        self.pads = {}                  # button -> (its sound's name, "ready", "loading" or "bad"); none: nothing on it
        self.lit = frozenset()          # the buttons whose sounds are playing
        self.trouble = ""               # a few words at the top left when the sound can't be heard
        self.placing = None             # a sound being put on a button: (its name, the button it's on in this bank)
        self.rec = None                 # recording: (seconds so far, how loud just now, 0 to 1)
        self.own_hints = []             # its buttons
        self.loop = None                # the loop: {"rec": recording a layer, "layers", "bar", "beat", "bpm"}, or None
        self.clock = None               # ...its beat: (tempo, beat b0, heard at t0): drawn again on each beat
        self.held_note = None           # a note being played: (the button held, the note's name)
        self.bounce = None              # Bounce, while it's up (screens/bounce.py's bounce_page): drawn instead
        self.seq = None                 # the Sequencer, while it's up (screens/sequencer.py's seq_page): drawn instead
        self.seq_bars = [0.0] * SQ.BARS   # ...its bars as they're drawn (each falls back slowly), and when they were
        self.seq_bars_at = 0.0
        self.fps = 20                   # ...frames a second, while its balls move
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
        if self.bounce is not None:                    # (Bounce: frame by frame while it plays, else when it changes)
            return STILL if self.bounce["paused"] else 1.0 / max(1, self.fps)
        if self.seq is not None:                       # (the Sequencer: frame by frame while there's sound to show)
            return 1.0 / max(1, self.fps) if self.seq_moving(time.monotonic()) else STILL
        if self.clock is None:
            return STILL
        bpm, b0, t0 = self.clock                       # (the loop: drawn again as each beat's heard)
        now = time.monotonic()
        beat = b0 + (now - t0) * bpm / 60.0
        return max(0.02, t0 + (math.floor(beat) + 1 - b0) * 60.0 / bpm - now + 0.005)

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
        controller (up, left and right, down), the letters' on the right (X, Y and A, B). They're square, and each
        four a cross: left and right a button apart, up and down between them, so it's as wide as it's tall. They
        don't fill the page: as big as its height or its width lets three rows of them and six across be, with room
        between them and round them (SPACE), all of them together in its middle. (Wider than tall, close together,
        left and right side by side, filling it: the Band's page, which has less room for them.)"""
        room = self.h - self.top_px - EDGE // 2
        if self.spaced:
            between, apart, sides, above = SPACE
            side = max(40, int(min(TILE_MOST, room / (3 + 2 * between + 2 * above),
                                   self.w / (6 + 4 * between + apart + 2 * sides))))
            tw = th = side
            gap, middle = round(side * between), round(side * apart)
            wide, along = 3 * tw + 2 * gap, 2 * (tw + gap)     # (a cross's width; from its left button to its right)
            left = (self.w - (2 * wide + middle)) // 2
            top = self.top_px + max(0, (room - (3 * th + 2 * gap)) // 2)
        else:
            gap, middle, left, top = GAP, MIDDLE, EDGE, self.top_px
            tw = (self.w - 2 * EDGE - MIDDLE - 2 * GAP) // 4
            th = max(40, (room - 2 * GAP) // 3)
            wide, along = 2 * tw + gap, tw + gap
        out = {}
        for pad, (side, across, row) in PAD_PLACE.items():
            x = left + side * (wide + middle) + round(across * along)
            out[pad] = (x, top + row * (th + gap), tw, th)
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

    @staticmethod
    def shaded(w, h, top, bottom, radius):
        """A tile with round corners, its colour going evenly from `top` to `bottom` (a pad lit a little from
        above), on the page's own."""
        from .fine import Image, ImageDraw
        body = Image.new("RGB", (w, h), bottom)
        bd = ImageDraw.Draw(body)
        for y in range(h - 1):
            bd.rectangle((0, y, w - 1, y), fill=co_mix(top, bottom, y / (h - 1)))
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
        tile = Image.new("RGB", (w, h), BG)
        tile.paste(body, (0, 0), mask)
        return tile

    def tile(self, pad, w, h):
        """A button's tile, a pad lit from behind in its button's colour: dimly, and brightly while its sound plays;
        its button and its sound's name, one over the other in its middle. Nothing on it: an outline. Kept."""
        from .fine import Image, ImageDraw, scale
        got = self.pads.get(pad)
        lit = pad in self.lit and got is not None
        here = self.placing is not None and self.placing[1] == pad
        held = self.held_note
        note = held[1] if held is not None and held[0] == pad and got is not None else None
        key = (pad, got, lit, here, note, w, h, scale(), BG)
        tile = self.tiles.get(key)
        if tile is not None:
            return tile
        colour = PAD_COLOUR[pad]
        size = max(16, min(28, round(h * 0.17)))       # (a bigger screen than the GPi Case's: bigger words to match)
        size = max(13, min(size, round(w * 0.165)))    # (...a narrow tile, a square one on a small screen: smaller,
        f, small = self.font(size, bold=True), self.font(max(11, size - 3))   # so a word like Explosion's all there)
        r, step = max(13, min(24, round(h * 0.15))), round(size * 1.22)
        edge = 14 if h >= 104 else 12
        room = w - 2 * max(7, round(w * 0.09))         # (px its name has, across)
        if got is None:                                # nothing on it
            tile = Image.new("RGB", (w, h), BG)
            d = ImageDraw.Draw(tile)
            d.rounded_rectangle((0, 0, w - 1, h - 1), radius=edge, fill=BG, outline=co_mix(BG, LINE, 1.0), width=2)
            cap, ink, words = co_mix(BG, colour, 0.22), BG, [("Empty", MUTED)]
        else:
            name, state = got
            if lit:                                    # (dark words on it, on a light page too)
                tile = self.shaded(w, h, co_mix(colour, (255, 255, 255), LIT_SHADE[0]),
                                   co_mix(colour, INK, LIT_SHADE[1]), edge)
                d = ImageDraw.Draw(tile)
                cap, ink, text = co_mix(colour, INK, 0.82), colour, co_mix(colour, INK, 0.9)
            else:
                glow = 0.18 if state == "ready" else 0.05
                tile = self.shaded(w, h, co_mix(ROW, colour, glow + SHADE[0]),
                                   co_mix(ROW, colour, max(0.0, glow - SHADE[1])), edge)
                d = ImageDraw.Draw(tile)
                d.rounded_rectangle((0, 0, w - 1, h - 1), radius=edge, width=2 if here else 1,
                                    outline=TEXT if here else co_mix(ROW, colour, glow + 0.14))
                cap = colour if state == "ready" else co_mix(ROW, colour, 0.45)
                ink = co_mix(colour, BG, 0.85)
                text = TEXT if state == "ready" else MUTED
            words = [(line, text) for line in self.fitted(name, f, room)]
            if state == "bad" and not lit:
                words = words[:1] + [("Can't play it", co_mix(WARN, ROW, 0.25))]
        gap = round(h * 0.07)                          # (its button, a gap, its name: together, in its middle)
        top = max(edge - 4, (h - (2 * r + gap + step * len(words))) // 2)
        cx = w // 2
        d.ellipse((cx - r, top, cx + r, top + 2 * r), fill=cap)
        if pad in ("up", "down", "left", "right"):
            self.arrow(d, pad, cx, top + r, r * 0.46, ink)
        else:
            d.text((cx, top + r), PAD_NAME[pad], font=self.font(max(14, r + 2), bold=True), fill=ink, anchor="mm")
        if note is not None:                           # (a note being played on it: which, at its top right; small,
            wide = w >= 110                            #  in the corner, on a narrow tile: clear of its button)
            d.text((w - edge, edge + 6) if wide else (w - 7, 12), note,
                   font=self.font(size + 1 if wide else size - 1, bold=True),
                   fill=co_mix(colour, BG, 0.85) if lit else colour, anchor="rm")
        y = top + 2 * r + gap + step // 2
        for k, (line, fill) in enumerate(words):
            plain = got is None or (k and got[1] == "bad" and not lit)
            d.text((cx, y), line, font=small if plain else f, fill=fill, anchor="mm")
            y += step
        if len(self.tiles) > 300:
            self.tiles.clear()
        self.tiles[key] = tile
        return tile

    def top(self, d, x0, y0):
        """Its line: this page's name between ◀ and ▶ (L and R: the Sequencer, and Bounce); at the right the bank's
        name (SELECT: the next) and a dot for each bank, this one's lit (a lot of them: which it is, of how many). A
        few words at the left if the sound can't be heard. The loop: at the left, its tempo before the bank's name,
        and how far round it is under them. Putting a sound on a button: the bank's name between ◀ and ▶ instead
        (L and R go through the banks, then), and what to do at the left."""
        i, n, name = self.bank
        W, mid = self.w, y0 + TOP // 2 - 2
        big = W >= 960                                 # (a bigger screen than the GPi Case's)
        f, small = self.font(22 if big else 18, bold=True), self.font(15 if big else 13)
        placing = self.placing is not None
        title = (name or PAGE_NAME) if placing else PAGE_NAME
        while len(title) > 4 and f.getlength(title) > W * 0.42:
            title = title[:-2].rstrip() + "…"
        nw = f.getlength(title)
        cx = x0 + W / 2
        d.text((cx, mid), title, font=f, fill=TEXT, anchor="mm")
        if n > 1 or not placing:
            self.arrow(d, "left", cx - nw / 2 - 20, mid, 6 if big else 5, MUTED)
            self.arrow(d, "right", cx + nw / 2 + 20, mid, 6 if big else 5, MUTED)
        if placing:
            words = f"Press a button for {self.placing[0]}"
            room = W / 2 - nw / 2 - 44 - EDGE
            while len(words) > 8 and small.getlength(words) > room:
                words = words[:-2].rstrip() + "…"
            d.text((x0 + EDGE + 2, mid), words, font=small, fill=TEXT, anchor="lm")
        elif self.trouble:
            d.text((x0 + EDGE + 2, mid), self.trouble, font=small, fill=WARN, anchor="lm")
        elif self.loop is not None:
            self.loop_line(d, x0 + EDGE + 2, mid, big)
        x = x0 + W - EDGE - 2
        if 1 < n <= BANK_DOTS:                         # (the banks: a dot each)
            r, step = (4, 14) if big else (3, 11)
            for k in reversed(range(n)):
                d.ellipse((x - 2 * r, mid - r, x, mid + r), fill=TEXT if k == i else co_mix(BG, MUTED, 0.55))
                x -= step
            x -= 8
        elif n > 1:
            x -= small.getlength(f"{i + 1} of {n}") + 14
            d.text((x + 14, mid), f"{i + 1} of {n}", font=small, fill=MUTED, anchor="lm")
        tempo = f"{self.loop['bpm']} BPM" if self.loop is not None else ""
        if name and not placing:                       # (the bank that's up: before its dots)
            bold = self.font(15 if big else 13, bold=True)
            room = x - (cx + nw / 2 + 44) - (small.getlength(tempo) + 14 if tempo else 0)
            while len(name) > 3 and bold.getlength(name) > room:
                name = name[:-2].rstrip() + "…"
            d.text((x, mid), name, font=bold, fill=TEXT, anchor="rm")
            x -= bold.getlength(name) + 14
        if tempo:
            d.text((x, mid), tempo, font=small, fill=MUTED, anchor="rm")
            self.loop_track(d, x0 + EDGE, x0 + W - EDGE, y0 + TOP - 7)
        self.taps.append(((x0, y0, x0 + W // 2, y0 + TOP - 4), "l"))
        self.taps.append(((x0 + W // 2, y0, x0 + W, y0 + TOP - 4), "r"))

    def loop_line(self, d, x, mid, big=False):
        """The loop, at the top left: recording (red) or playing, a mark for each beat of the bar (the one heard now,
        lit), and which bar of the loop it's in."""
        lp = self.loop
        f = self.font(15 if big else 13, bold=True)
        red, lit = _HUES["Red"], TEXT
        r, b = (6, 5) if big else (5, 4)
        d.ellipse((x, mid - r, x + 2 * r, mid + r), fill=red if lp["rec"] else _HUES["Green"])
        words = "Recording" if lp["rec"] else ("Loop" if lp["layers"] == 1 else f"Loop, {lp['layers']} layers")
        if lp.get("seq") and not lp["rec"] and not lp["layers"]:
            words = "Sequencer"                        # (its tune alone, playing under these buttons)
        d.text((x + 2 * r + 7, mid), words, font=f, fill=TEXT, anchor="lm")
        x += 2 * r + 7 + f.getlength(words) + 10
        for k in range(1, 5):
            on = k == lp["beat"]
            d.rounded_rectangle((x, mid - b, x + 2 * b, mid + b), radius=2,
                                fill=(red if lp["rec"] else lit) if on else co_mix(BG, ROW, 0.9))
            x += 2 * b + 4
        d.text((x + 4, mid), f"bar {lp['bar']}", font=self.font(15 if big else 13), fill=MUTED, anchor="lm")

    def loop_track(self, d, x0, x1, y):
        """A line under the bank's: how far round the loop it is (to the beat), recording (red) or playing."""
        lp = self.loop
        beats = 4 * max(1, lp.get("bars", 1))
        done = ((lp["bar"] - 1) * 4 + lp["beat"]) / beats
        d.rounded_rectangle((x0, y, x1, y + 2), radius=1, fill=co_mix(BG, ROW, 0.9))
        d.rounded_rectangle((x0, y, x0 + max(4, round((x1 - x0) * done)), y + 2), radius=1,
                            fill=_HUES["Red"] if lp["rec"] else _HUES["Green"])

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

    def bounce_top(self, d, x0, y0, w):
        """Bounce's line, over its shape (w wide): its name between ◀ and ▶ (L and R: the Soundboard's other pages),
        its key and scale at the left (SELECT: the next key; Y: the next scale), its shape and how many balls at the
        right."""
        v = self.bounce
        mid = y0 + TOP // 2 - 2
        big = self.w >= 960
        f, small = self.font(22 if big else 18, bold=True), self.font(15 if big else 13)
        cx = x0 + w / 2
        d.text((cx, mid), "Bounce", font=f, fill=TEXT, anchor="mm")
        nw = f.getlength("Bounce")
        self.arrow(d, "left", cx - nw / 2 - 20, mid, 6 if big else 5, MUTED)
        self.arrow(d, "right", cx + nw / 2 + 20, mid, 6 if big else 5, MUTED)
        n = v["count"]
        d.text((x0 + EDGE + 2, mid), f"{v['key']} {v['scale'].lower()}", font=small, fill=TEXT, anchor="lm")
        d.text((x0 + w - EDGE - 2, mid), f"{v['shape']}, {n} ball" + ("" if n == 1 else "s"), font=small, fill=MUTED,
               anchor="rm")
        self.taps.append(((x0, y0, x0 + w // 2, y0 + TOP - 4), "l"))
        self.taps.append(((x0 + w // 2, y0, x0 + w, y0 + TOP - 4), "r"))

    def bounce_panel(self, w, h, fonts):
        """Bounce's sliders, a picture kept till one of them (or what X and Y change) does: the balls are drawn
        frame by frame, and words are slow to draw on a Pi Zero."""
        from .fine import Image, ImageDraw, scale
        from .theme import ACCENT
        v = self.bounce
        key = ("panel", tuple(v["sliders"]), v["sel"], v["sound"], v["key"], v["scale"], w, h, scale(), BG, ACCENT)
        tile = self.tiles.get(key)
        if tile is None:
            tile = Image.new("RGB", (w, h), BG)
            BN.draw_panel(ImageDraw.Draw(tile), (0, 0, w, h), v, fonts)
            for k in [k for k in self.tiles if k[0] == "panel"]:
                del self.tiles[k]                      # (the one before: not wanted again soon)
            self.tiles[key] = tile
        return tile

    def bounce_fonts(self):
        """Bounce's words: its shape's, and its sliders' (bigger on a bigger screen)."""
        big = self.w >= 960
        return {"bold": self.font(26 if big else 20, bold=True), "small": self.font(18 if big else 14),
                "label": self.font(19 if big else 14), "label_b": self.font(19 if big else 14, bold=True),
                "info": self.font(19 if big else 14, bold=True), "badge": self.font(15 if big else 11, bold=True),
                "caption": self.font(17 if big else 12),
                "info_h": 44 if big else 28, "knob": 9 if big else 6, "track": 6 if big else 4}

    # -- the Sequencer -------------------------------------------------------------------------------------------------
    def seq_moving(self, now):
        """Its page changes by itself just now: it's playing (the bar goes along it), or there's sound (its bars up,
        or still falling)."""
        v = self.seq
        if v["paused"]:
            return False
        heard = v["bars"] is not None and now - v["bars"][0] < SQ.BARS_KEPT and any(v["bars"][1])
        return v["playing"] or heard or max(self.seq_bars) > 0.01

    def seq_fonts(self):
        big = self.w >= 960
        return {"bold": self.font(22 if big else 18, bold=True), "small": self.font(15 if big else 13),
                "row": self.font(19 if big else 14), "row_b": self.font(19 if big else 14, bold=True),
                "note": self.font(15 if big else 11, bold=True), "arrow": 6 if big else 5}

    def seq_cells(self, cw, ch, colour):
        """A cell that's on, as it's drawn (and as it is while the bar's on it): pictures kept."""
        from .fine import scale
        key = ("seqcell", cw, ch, colour, BG, scale())
        tiles = self.tiles.get(key)
        if tiles is None:
            tiles = self.tiles[key] = {head: SQ.lit_tile(cw, ch, colour, head, BG) for head in (False, True)}
        return tiles

    def seq_still(self, lay, fonts, tiles):
        """Its page with the bar nowhere on it and no bars: a picture kept till something on it changes (the bar and
        the bars are drawn frame by frame, and words are slow to draw on a Pi Zero)."""
        from .fine import Image, ImageDraw, scale
        v = self.seq
        key = ("seq", v["grid"], v["names"], v["high"], tuple(v["rows"]), v["cursor"], v["key"], v["scale"],
               v["bpm"], v["playing"], v["colour"], self.w, self.h, scale(), BG)
        tile = self.tiles.get(key)
        if tile is None:
            tile = Image.new("RGB", (self.w, self.h), BG)
            d = ImageDraw.Draw(tile)
            SQ.draw_top(d, 0, 0, self.w, v, fonts, TOP)
            SQ.draw_grid(tile, d, lay, v, fonts, tiles)
            for k in [k for k in self.tiles if k[0] == "seq"]:
                del self.tiles[k]                      # (the one before: not wanted again soon)
            self.tiles[key] = tile
        return tile

    def seq_levels(self, now):
        """Its bars as they're drawn now: up at once to what its player last said, falling back slowly."""
        v = self.seq
        said = v["bars"]
        fresh = said[1] if said is not None and now - said[0] < SQ.BARS_KEPT else ()
        fall = SQ.BARS_FALL ** (max(0.0, min(1.0, now - self.seq_bars_at)) * 20.0)
        self.seq_bars_at = now
        self.seq_bars = [max(fresh[k] if k < len(fresh) else 0.0, self.seq_bars[k] * fall) for k in range(SQ.BARS)]
        return self.seq_bars

    def draw_seq(self, img, x0, y0):
        """The Sequencer's page: its line and grid (a picture kept), the column the bar's on, and the sound's bars."""
        from .fine import ImageDraw
        v = self.seq
        fonts = self.seq_fonts()
        lay = SQ.layout((0, TOP, self.w, self.h), self.w >= 960)
        tiles = self.seq_cells(lay["cw"], lay["ch"], v["colour"])
        frame = self.seq_still(lay, fonts, tiles).copy()
        d = ImageDraw.Draw(frame)
        now = time.monotonic()
        if v["playing"] and not v["paused"]:
            SQ.draw_head(frame, d, lay, v, fonts, tiles, SQ.step_at(v["clock"], now))
        SQ.draw_bars(d, lay["bars"], self.seq_levels(now), v["colour"])
        img.paste(frame, (x0, y0))
        self.taps.append(((x0, y0, x0 + self.w // 2, y0 + TOP - 4), "l"))
        self.taps.append(((x0 + self.w // 2, y0, x0 + self.w, y0 + TOP - 4), "r"))
        cw, ch = lay["cw"], lay["ch"]
        for r, y in enumerate(lay["ys"]):              # (a tap on a cell: on or off, as A there)
            for c, x in enumerate(lay["xs"]):
                self.taps.append(((x0 + x, y0 + y, x0 + x + cw, y0 + y + ch), ("seq", r, c)))

    def draw(self, img, x0, y0):
        from .fine import ImageDraw
        self.taps = []
        if self.seq is not None and self.bounce is None:   # (the Sequencer: its grid, and the sound's bars)
            self.draw_seq(img, x0, y0)
            return
        if self.bounce is not None:                    # (Bounce: its shape and balls, and its sliders at the right,
            d = ImageDraw.Draw(img)                    #  bounce.py)
            pw = BN.PANEL[self.w >= 960]
            shape_w = self.w - pw - 2 * EDGE
            fonts = self.bounce_fonts()
            self.bounce_top(d, x0, y0, shape_w)
            BN.draw(d, (x0, y0 + TOP, x0 + shape_w, y0 + self.h), self.bounce, fonts, time.monotonic())
            px, py = x0 + shape_w + EDGE, y0 + 6
            img.paste(self.bounce_panel(self.w - shape_w - 2 * EDGE, self.h - 12, fonts), (px, py))
            return
        self.top(ImageDraw.Draw(img), x0, y0)
        for pad, (x, y, w, h) in self.boxes().items():
            img.paste(self.tile(pad, w, h), (x0 + x, y0 + y))
            self.taps.append(((x0 + x, y0 + y, x0 + x + w, y0 + y + h), pad))
        if self.rec is not None:
            self.taps = []                             # (recording: its buttons are A and B, along the bottom)
            self.rec_card(img, x0, y0)
