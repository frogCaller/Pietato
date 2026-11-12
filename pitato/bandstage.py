"""Apps' Band: your Pietatos play together, each its own instrument (drums, bass, guitar, keys), and you play along on
the buttons. Any Pietato can start one (SELECT): the others that are on join it, each taking an instrument, and play
it through their own speaker, in step; the one that started it plays whatever nobody's taken. On its own, it's the
whole band. L and R pick the instrument your buttons play; while you play it, the Pietato leaves it to you. START has
the song, the tempo, the volume, and who decides what each player does with its next four bars (dice, or a decision
model on your bot's computer); B there goes back.

This draws the page: who's on what, and how busy; the bar's chord and the next one's, and the beat; and your
instrument's buttons, laid out as they are on a controller, each with the note it plays now. (band.py: the music.
bandplay.py: its player, a process of its own. screens/band.py: its buttons, the others, and what media mode does for
it.)"""
from .soundboard import EDGE, GAP, Soundboard, STILL
from .theme import ACCENTS, BG, co_mix, LINE, MUTED, ROW, TEXT, WARN

_HUES = dict(ACCENTS)
SEAT_COLOUR = {"drums": _HUES["Gold"], "bass": _HUES["Purple"], "guitar": _HUES["Teal"], "keys": _HUES["Blue"]}
SEATS_H = 58                     # px its players' cards are tall


class BandStage(Soundboard):
    key = "band"
    blurb = "Your Pietatos play together, each its own instrument. Play along on the buttons."
    top_px = 112

    def __init__(self, w, h, rng=None, values=None):
        super().__init__(w, h, rng, values)
        self.seats = []                 # each player: (instrument, its name, who has it, a word on what it's doing,
                                        #  how busy: 0 to 3, it's the one your buttons play)
        self.now = ("", "", None)       # the bar's chord, the next bar's, the beat (0 to 3; None: it isn't playing)
        self.song = ("", 0, "")         # the song, its tempo, a few words when it isn't playing ("SELECT starts it")
        self.until = None               # seconds till its picture next changes (asked each frame), when it's playing

    def frame_in(self, wall):
        return self.until() if self.until is not None else STILL

    def seat_card(self, d, x, y, w, seat):
        key, name, who, doing, level, mine = seat
        colour = SEAT_COLOUR.get(key, TEXT)
        d.rounded_rectangle((x, y, x + w - 1, y + SEATS_H - 1), radius=10, fill=ROW,
                            outline=colour if mine else LINE, width=2 if mine else 1)
        d.text((x + 12, y + 18), name, font=self.font(16, bold=True), fill=TEXT, anchor="lm")
        for k in range(3):                             # how busy it is: three bars, as many lit
            bx = x + w - 17 - (2 - k) * 10
            top = y + 26 - 6 * (k + 1)
            d.rounded_rectangle((bx, top, bx + 6, y + 26), radius=2,
                                fill=colour if k < level else co_mix(ROW, MUTED, 0.22))
        small = self.font(13)
        words = who if not doing else f"{who}: {doing}" if who else doing
        while len(words) > 4 and small.getlength(words) > w - 22:
            words = words[:-2].rstrip() + "…"
        d.text((x + 12, y + 41), words, font=small, fill=co_mix(colour, TEXT, 0.35) if mine else MUTED, anchor="lm")

    def top(self, d, x0, y0):
        """Its players, then a line: the chord now and the one after, the beat, and the song."""
        W = self.w
        n = max(1, len(self.seats))
        cw = (W - 2 * EDGE - (n - 1) * GAP) // n
        for k, seat in enumerate(self.seats):
            self.seat_card(d, x0 + EDGE + k * (cw + GAP), y0 + 4, cw, seat)
        mid = y0 + SEATS_H + 4 + (self.top_px - SEATS_H - 8) // 2
        chord, then, beat = self.now
        name, bpm, words = self.song
        small = self.font(13)
        x = x0 + EDGE + 2
        if self.trouble:
            d.text((x, mid), self.trouble, font=small, fill=WARN, anchor="lm")
        elif beat is None:
            d.text((x, mid), words, font=self.font(15), fill=MUTED, anchor="lm")
        else:
            big = self.font(24, bold=True)
            d.text((x, mid), chord, font=big, fill=TEXT, anchor="lm")
            if then and then != chord:
                d.text((x + big.getlength(chord) + 12, mid + 2), f"then {then}", font=small, fill=MUTED, anchor="lm")
            for k in range(4):                         # the beat: four dots, the one it's on lit
                cx = x0 + W // 2 - 30 + k * 20
                r = 5 if k == beat else 4
                d.ellipse((cx - r, mid - r, cx + r, mid + r), fill=TEXT if k == beat else co_mix(BG, LINE, 0.9))
        if name:
            d.text((x0 + W - EDGE - 2, mid), f"{name}  {bpm}" if bpm else name, font=small, fill=MUTED, anchor="rm")
        self.taps.append(((x0, y0, x0 + W // 2, y0 + SEATS_H + 4), "l"))
        self.taps.append(((x0 + W // 2, y0, x0 + W, y0 + SEATS_H + 4), "r"))
