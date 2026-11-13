"""Apps > The Cookie, on the screen: the cookie at the top (or the plate it's gone from), a line on where it is or
what's just happened, and a row for each of your Pietatos: its name, its Bot's last few throws (so you can learn its
habit), and the cookie beside the one that has it. Nothing on it moves: it's drawn again when something changes, and
once a second while a countdown runs. (cookie.py: the rules. screens/cookie.py: its buttons, and what media mode does
for it. cookie_mark here: the small cookie on the status bar and the home screen of the one that has it.)"""
from .cookie import COOKIE_KEPT
from .fine import detail, made_fine
from .sims import rps_span, rps_sprite, Sim
from .theme import BG, BODY, co_mix, FONT_UI, FONT_UI_BOLD, LINE, MUTED, ROW, TEXT

COOKIE_DOUGH = (214, 166, 100)
COOKIE_EDGE = (176, 126, 68)
COOKIE_CHIP = (88, 56, 40)
COOKIE_SPOTS = ((-0.36, -0.36, 0.15), (0.24, -0.46, 0.12), (0.48, 0.08, 0.15), (-0.06, 0.02, 0.13),
                (-0.52, 0.22, 0.11), (0.12, 0.50, 0.14))   # its chips: across, down and how big, of its own size
COOKIE_PIECE = {"r": 0, "s": 1, "p": 2}  # a throw's picture: Rock Paper Scissors' own (sims.py: rock, scissors, paper)
COOKIE_STILL = 10.0           # seconds between its pictures when nothing changes (your others' throws, how long ago)
COOKIE_SIDE = 14              # px round the page
COOKIE_TOP = 78               # ...for the cookie and its lines
COOKIE_ROW = (52, 8)          # ...a Pietato's row at most, and between two
COOKIE_ROWS = 6               # rows at most (more of them than that: the last says how many more)
COOKIE_SLOT = 28              # px for each throw (its picture: 10 px from its middle)


def cookie_mark(d, cx, cy, r):
    """A small cookie drawn straight on (the status bar's, the home screen's): its dough and three chips."""
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=COOKIE_DOUGH, outline=COOKIE_EDGE)
    c = max(1.0, r * 0.2)
    for px, py in ((-0.36, -0.3), (0.34, -0.08), (-0.04, 0.44)):
        x, y = cx + px * r, cy + py * r
        d.ellipse((x - c, y - c, x + c, y + c), fill=COOKIE_CHIP)


def cookie_picture(r, s=1, plate=None):
    """A cookie this big (its half, px), for a picture drawn s times as finely: drawn four times bigger and made
    smaller, for round edges. plate: the plate it's gone from instead, a ring in that colour with a few crumbs."""
    from PIL import Image, ImageDraw
    K = 4
    half = (r + 2) * s
    n = 2 * half * K
    big = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    c, R = n / 2, r * s * K

    def disc(px, py, rad, fill):
        d.ellipse((c + px * R - rad * R, c + py * R - rad * R, c + px * R + rad * R, c + py * R + rad * R), fill=fill)
    if plate is not None:
        d.ellipse((c - R, c - R, c + R, c + R), outline=plate + (255,), width=max(1, round(R * 0.07)))
        for px, py, rad in COOKIE_SPOTS[1::2]:         # (crumbs, where it was)
            disc(px * 0.55, py * 0.55, rad * 0.32, plate + (255,))
    else:
        disc(0, 0, 1.0, COOKIE_EDGE + (255,))
        disc(-0.03, -0.04, 0.93, COOKIE_DOUGH + (255,))
        for px, py, rad in COOKIE_SPOTS:
            disc(px, py, rad, COOKIE_CHIP + (255,))
            disc(px - rad * 0.3, py - rad * 0.3, rad * 0.3, co_mix(COOKIE_CHIP, COOKIE_DOUGH, 0.35) + (255,))
    return made_fine(big.reduce(K), s)


class CookiePage(Sim):
    key = "cookie"
    blurb = "One cookie between your Pietatos. Beat the one that has it at rock paper scissors and it's yours."
    poke_label = None
    options = ()
    bare = True                         # on the page itself: no box, and nothing beside it
    paced = True                        # drawn again when something changes, not frame by frame

    def __init__(self, w, h, rng=None, values=None):
        super().__init__(w, h, rng, values)
        self.head = ("", "")            # its top: a line, and a smaller one under it
        self.here = False               # the cookie's here (drawn at the top; else the plate it's gone from)
        self.moves = 0                  # how many times it's changed hands
        self.rows = []                  # your Pietatos: (name, a word on it, its colour or None, its Bot's last
                                        #  throws, it has the cookie, it's on)
        self.until = None               # seconds till its top next changes by itself (a countdown): asked each frame
        self.own_hints = []             # its buttons
        self.fonts = {}
        self.pics = {}

    @property
    def backdrop(self):
        return BG                       # (the page's own colour, as it is now)

    def update(self, dt):
        return None

    def refit(self, w, h):
        self.w, self.h = w, h

    def hints(self):
        return self.own_hints

    def frame_in(self, wall):
        return self.until() if self.until is not None else COOKIE_STILL

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

    @staticmethod
    def fit(text, font, width):
        """text, cut short (…) if it's wider than width."""
        if font.getlength(text) <= width:
            return text
        while len(text) > 1 and font.getlength(text + "…") > width:
            text = text[:-1]
        return text.rstrip() + "…"

    def picture(self, what, r, s, colour=None):
        """A picture kept: the cookie ("cookie"), its plate ("plate", in colour), or a throw ("r", "p", "s")."""
        key = (what, r, s, colour)
        pic = self.pics.get(key)
        if pic is None:
            if what in COOKIE_PIECE:
                pic = made_fine(rps_sprite(COOKIE_PIECE[what], r * s, 0, 0, rps_span(r) * s), s)
            else:
                pic = cookie_picture(r, s, colour if what == "plate" else None)
            if len(self.pics) > 40:
                self.pics.clear()
            self.pics[key] = pic
        return pic

    @staticmethod
    def put(img, pic, cx, cy):
        """pic on img, its middle at (cx, cy)."""
        x, y = cx - pic.width / 2, cy - pic.height / 2
        img.paste(pic, (x, y) if detail(img) > 1 else (int(round(x)), int(round(y))), pic)

    def draw(self, img, x0, y0):
        from .fine import ImageDraw
        d = ImageDraw.Draw(img)
        s = detail(img)
        W, E = self.w, COOKIE_SIDE
        # the top: the cookie, a line on it and a smaller one, how many times it's changed hands
        r = 27
        cx, cy = x0 + E + r + 4, y0 + COOKIE_TOP // 2 + 2
        self.put(img, self.picture("cookie", r, s) if self.here else self.picture("plate", r, s, LINE), cx, cy)
        tx, right = cx + r + 16, x0 + W - E
        head, sub = self.head
        f_head, f_sub, f_small = self.font(20, True), self.font(14), self.font(13)
        moved = "" if self.moves < 1 else "Changed hands once" if self.moves == 1 else \
            f"Changed hands {self.moves} times"
        if moved and f_head.getlength(head) > right - tx - f_small.getlength(moved) - 18:
            moved = ""                                 # (no room for it beside a long line)
        d.text((tx, cy - 12), self.fit(head, f_head, right - tx), font=f_head, fill=TEXT, anchor="lm")
        d.text((tx, cy + 13), self.fit(sub, f_sub, right - tx), font=f_sub, fill=BODY, anchor="lm")
        if moved:
            d.text((right, cy - 12), moved, font=f_small, fill=MUTED, anchor="rm")
        # your Pietatos, a row each
        rows = list(self.rows)
        more = len(rows) - COOKIE_ROWS + 1 if len(rows) > COOKIE_ROWS else 0
        if more:
            rows = rows[:COOKIE_ROWS - 1]
        n = len(rows) + (1 if more else 0)
        if not n:
            return
        most, gap = COOKIE_ROW
        top = y0 + COOKIE_TOP + 22
        rh = int(max(26, min(most, (self.h - COOKIE_TOP - 22 - 6 - (n - 1) * gap) / n)))
        x, w = x0 + E, W - 2 * E
        ends = x + w - 50                              # (its throws end here: the cookie's place is after them)
        if any(row[3] for row in rows):
            d.text((ends, top - 11), "Last throws", font=self.font(12), fill=MUTED, anchor="rm")
        f_name, f_word = self.font(16, True), self.font(13)
        for k, (name, word, colour, throws, has, on) in enumerate(rows):
            y = top + k * (rh + gap)
            mid = y + rh / 2
            d.rounded_rectangle((x, y, x + w - 1, y + rh - 1), radius=10, fill=ROW,
                                outline=COOKIE_DOUGH if has else LINE, width=2 if has else 1)
            dot = colour or MUTED
            d.ellipse((x + 14, mid - 5, x + 24, mid + 5), fill=dot if on else co_mix(ROW, dot, 0.35))
            throws = throws[-COOKIE_KEPT:]
            room = ends - len(throws) * COOKIE_SLOT - 14 - (x + 36)
            ink = TEXT if on else MUTED
            if word and rh >= 44:                      # (its word under its name)
                d.text((x + 36, mid - 9), self.fit(name, f_name, room), font=f_name, fill=ink, anchor="lm")
                d.text((x + 36, mid + 11), self.fit(word, f_word, room), font=f_word, fill=MUTED, anchor="lm")
            else:                                      # (...or after it, in a shorter row)
                name = self.fit(name, f_name, room - (f_word.getlength(word) + 12 if word else 0))
                d.text((x + 36, mid), name, font=f_name, fill=ink, anchor="lm")
                if word:
                    d.text((x + 36 + f_name.getlength(name) + 12, mid + 1), word, font=f_word, fill=MUTED,
                           anchor="lm")
            for i, t in enumerate(throws):             # (the last, last)
                self.put(img, self.picture(t, 10, s), ends - (len(throws) - i - 0.5) * COOKIE_SLOT, mid)
            if has:
                self.put(img, self.picture("cookie", 11, s), x + w - 26, mid)
        if more:
            y = top + (n - 1) * (rh + gap)
            d.text((x + 36, y + rh / 2), f"And {more} more", font=f_word, fill=MUTED, anchor="lm")
