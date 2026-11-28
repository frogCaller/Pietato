"""The Soundboard's Sequencer: a grid of sounds and steps. Each row's a sound (a kick, a snare, a hat, and a lead: a
tune's notes), and across it go the sixteen steps of a bar, a sixteenth note each. A cell that's on plays its row's
sound as the bar comes round to it, over and over, at the Soundboard's tempo: a beat you make by turning cells on and
off. The lead's cells each have a note of their own, one of the key's (Bounce's key and scale: a tune here and
Bounce's notes sound right together).
The first tune a Pietato has is made from its name (born: the same name, the same tune), so each of yours starts
with its own; Y changes a little of it (mutated: a few cells, a few notes), as often as you like: each cell changed
is as likely to be on as it is in a tune made afresh, so however often, it's still a tune.
This is the tune itself, and how its page is drawn: on its line, four buttons (its tempo, its key, its scale and the
lead's sound: A on one, its next), the grid under it in one colour (the accent: a cell that's on, lit; the column the
bar's on, outlined; the cell ◀▶▲▼ have moved to, ringed), and under that the sound as bars, low notes at the left.
screens/sequencer.py has its buttons, and what it tells the Soundboard's player (its cells as part of the loop, so
they're heard at their very moments)."""
import math
import random
import zlib

from . import bounce as BN

ROWS, STEPS = 4, 16
LEAD_ROW = ROWS - 1              # the row whose cells are notes
STEP = 0.25                      # beats to a step (a sixteenth)
BAR = STEPS * STEP               # ...and to the whole of it (a bar)
DRUMS = ("Starter/Kick.wav", "Starter/Snare.wav", "Starter/Hi-hat.wav")   # the three rows above the lead, to begin
LEAD = "Tones/Pluck"             # ...and the lead's sound (one of the player's own: Bounce's Tones)
ROW_HUES = ("Red", "Gold", "Teal", "Purple")   # each row's own colour on the page (theme.py's): its mark, its cells
HEAD_BAND = 0.07                 # the column the bar's on: this much lighter than the page, from its number down
KNOBS = ("Tempo", "Key", "Scale", "Lead")   # its buttons, on its line at the top: A on one, its next
TEMPOS = (60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160)   # ...the Tempo one's, round and round (START's card:
                                 # any tempo)
BARS_MOST = 0.6                  # the bars under the grid: no taller than this much of it (a taller page has the rest
                                 # above and below it all)
GAINS = (0.6, 0.5, 0.4, 0.85)    # how loud each row's played, of its sound as it is: a mix (the starter kick and
#                                  snare are as loud as a sound can be: three sounds at once that loud are too much)
NOTES = 8                        # the lead's notes: the scale's first so many, from the key up (0: the key's own)
BARS = 32                        # the sound's bars under the grid
BARS_FALL = 0.72                 # what a bar keeps each frame as it falls (at 20 frames a second)
BARS_KEPT = 0.4                  # seconds its player's bars are shown after it said them (it says no more: silence)
# how likely each step of a row is to be on, in a tune made from a number: a kick on the bar's first beat, mostly on
# its third; a snare on its second and fourth; and here and there between
KICK = {0: 1.0, 8: 0.85, 4: 0.3, 12: 0.3, 10: 0.35, 3: 0.2, 6: 0.2, 11: 0.2, 14: 0.25, 7: 0.1}
SNARE = {4: 1.0, 12: 1.0, 7: 0.12, 9: 0.12, 15: 0.2, 10: 0.08}
HATS = ((0, 2, 4, 6, 8, 10, 12, 14), tuple(range(STEPS)), (2, 6, 10, 14), (0, 2, 3, 4, 6, 8, 10, 11, 12, 14))
WALK = (-2, -1, -1, 0, 1, 1, 2, 3)   # the lead's next note: how far from the one before (up a little more than down)
RARE = 0.04                      # how likely a cell is to come on, changing a tune, where a tune made afresh has none


def seed_of(name):
    """A Pietato's own number, from its name: what its first tune's made from."""
    return zlib.crc32(("pietato:" + (name or "")).encode("utf-8"))


def born(seed):
    """A tune made from a number: (its grid: ROWS rows of STEPS, True where a cell's on; the lead's note for each
    step). The same number, the same tune."""
    rng = random.Random(seed)
    kick = [rng.random() < KICK.get(k, 0.0) for k in range(STEPS)]
    snare = [rng.random() < SNARE.get(k, 0.0) for k in range(STEPS)]
    kind = rng.choice(HATS)
    hat = [k in kind and rng.random() < 0.9 for k in range(STEPS)]
    lead = [rng.random() < (0.75 if k % 4 == 0 else 0.5 if k % 2 == 0 else 0.3) for k in range(STEPS)]
    lead[0] = True
    notes, at = [], 0
    for k in range(STEPS):
        at = 0 if k == 0 else max(0, min(NOTES - 1, at + rng.choice(WALK)))
        notes.append(at)
    return [kick, snare, hat, lead], notes


def chance(row, k):
    """How likely a cell is to be on, in a tune being changed (mutated): as in one made from a number (born), or
    nearly (any of its hats' ways: the eighths mostly, the sixteenths between now and then); and a little, where
    one made from a number never has one."""
    if row == 0:
        return max(KICK.get(k, 0.0), RARE)
    if row == 1:
        return max(SNARE.get(k, 0.0), RARE)
    if row == 2:
        return 0.8 if k % 2 == 0 else 0.25
    return 0.75 if k % 4 == 0 else 0.5 if k % 2 == 0 else 0.3


def mutated(grid, notes, rng):
    """A tune changed a little (Y): two to four of its cells the other way (each picked anywhere, and made afresh:
    on as likely as chance says, till that many have changed), and up to three of the lead's notes moved to a step
    or so from the note before (ones that are heard, if any are). (grid, notes): new ones."""
    grid = [list(row) for row in grid]
    notes = list(notes)
    want, changed = rng.choice((2, 3, 3, 4)), set()
    for _ in range(400):
        if len(changed) >= want:
            break
        row, k = rng.randrange(ROWS), rng.randrange(STEPS)
        on = rng.random() < chance(row, k)
        if on != grid[row][k]:
            grid[row][k] = on
            changed ^= {(row, k)}                      # (one changed back again: not changed)
    heard = [k for k in range(1, STEPS) if grid[LEAD_ROW][k]] or list(range(1, STEPS))
    for _ in range(rng.choice((1, 2, 3))):
        k = rng.choice(heard)
        notes[k] = max(0, min(NOTES - 1, notes[k - 1] + rng.choice(WALK)))
    return grid, notes


def dumps(grid, notes):
    """A tune as a line of text (kept with the settings): each row's cells (x: on), then the lead's notes."""
    return "/".join("".join("x" if on else "." for on in row) for row in grid) + ":" + "".join(str(n) for n in notes)


def loads(text):
    """A tune from its line of text: (grid, notes), or None (it isn't one)."""
    try:
        cells, _, tune = str(text).partition(":")
        rows = cells.split("/")
        if len(rows) != ROWS or any(len(r) != STEPS or set(r) - set("x.") for r in rows) or len(tune) != STEPS:
            return None
        notes = [int(c) for c in tune]
    except (TypeError, ValueError):
        return None
    if any(not 0 <= n < NOTES for n in notes):
        return None
    return [[c == "x" for c in r] for r in rows], notes


def note_of(step, key, scale):
    """The lead's note for a step of the scale (MIDI): as Bounce's walls have them, from the key up."""
    return BN.wall_note(step, key, scale)


def hits(grid, notes, sounds, key, scale):
    """The tune as the loop takes it: [(beat of its bar, sound, semitones, how loud)], each cell that's on. sounds:
    each row's (the lead's: one of the player's own, played so many semitones from middle C; the others: as they
    are)."""
    out = []
    for r, row in enumerate(grid):
        sid = sounds[r] if r < len(sounds) else None
        if not sid:
            continue
        for k, on in enumerate(row):
            if on:
                semis = note_of(notes[k], key, scale) - BN.TONE_ROOT if r == LEAD_ROW else 0
                out.append((k * STEP, sid, semis, GAINS[r]))
    return out


def step_at(clock, now):
    """The step the bar's on at a moment (clock: the tempo, beat b0, heard at t0)."""
    bpm, b0, t0 = clock
    return int(math.floor((b0 + (now - t0) * bpm / 60.0) / STEP)) % STEPS


def next_step_in(clock, now):
    """Seconds till the bar's on its next step."""
    bpm, b0, t0 = clock
    at = (b0 + (now - t0) * bpm / 60.0) / STEP
    return (math.floor(at) + 1 - at) * STEP * 60.0 / bpm


# ---- its page ------------------------------------------------------------------------------------------------------
def layout(box, big):
    """Where its parts go in box (the page under its top line): the steps' numbers' row, the grid's cells' corners
    and size, the rows' names' left and right edges, and the bars' box: no taller than so much of the grid, a taller
    page's room left above and below it all. (Its buttons are on its line: soundboard.py's seq_knobs.)"""
    x0, y0, x1, y1 = box
    edge = 12
    label = 124 if big else 74
    gap, beat_gap = (8, 14) if big else (4, 8)
    cw = int((x1 - x0 - 2 * edge - label - 12 * gap - 3 * beat_gap) // STEPS)
    ch = cw                                            # (square, and as far apart down as across: as a beat's are)
    pitch = ch + gap
    num = 14 if big else 10                            # (the steps' numbers this far down, the grid as far again)
    under = 16 if big else 8                           # (between the grid and the bars)
    grid_h = ROWS * pitch - gap
    bars_h = y1 - 8 - (y0 + 2 * num + grid_h + under)   # (the bars' room)
    spare = max(0, bars_h - round(grid_h * BARS_MOST))
    y0 += spare // 2
    nums = y0 + num
    gx, gy = x0 + edge + label, nums + num
    xs, x = [], gx
    for c in range(STEPS):
        xs.append(x)
        x += cw + (beat_gap if c % 4 == 3 else gap)
    ys = [gy + r * pitch for r in range(ROWS)]
    top = ys[-1] + ch + under
    bars = (x0 + edge, top, x1 - edge, top + bars_h - spare)
    return {"xs": xs, "ys": ys, "cw": cw, "ch": ch, "left": x0 + edge, "label": gx - (16 if big else 12),
            "bars": bars, "nums": nums}


def lit_tile(cw, ch, colour, head, back):
    """A cell that's on: (its picture, its shape): the colour, lighter at its top (whiter while the bar's on it)."""
    from .fine import Image, ImageDraw
    from .theme import co_mix
    white = (255, 255, 255)
    top = co_mix(colour, white, 0.62 if head else 0.3)
    low = co_mix(colour, white, 0.4) if head else co_mix(colour, back, 0.08)
    tile = Image.new("RGB", (cw, ch), back)
    td = ImageDraw.Draw(tile)
    for y in range(ch):
        td.line((0, y, cw, y), fill=co_mix(top, low, y / max(1, ch - 1)))
    mask = Image.new("L", (cw * 4, ch * 4), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, cw * 4 - 1, ch * 4 - 1), radius=cw * 4 // 5, fill=255)
    return tile, mask.resize((cw, ch), Image.LANCZOS)


def draw_note(d, x, y, cw, ch, name, high, font):
    """A lead cell's note on it: its name, and a dot over it if it's in the octave above the key's."""
    ink = (16, 19, 23)
    cx, cy = x + cw / 2, y + ch / 2
    d.text((cx, cy), name, font=font, fill=ink, anchor="mm")
    if high:
        r = 1.5 if ch < 44 else 2
        top = cy - getattr(font, "size", 11) * 0.5 - 3 - r
        d.ellipse((cx - r, top - r, cx + r, top + r), fill=ink)


def draw_steps(d, lay, fonts, lit=None):
    """The steps' numbers over the grid, 1 to 16: each beat's first brighter, and the one the bar's on (lit)."""
    from .theme import BODY, MUTED, TEXT
    for c, x in enumerate(lay["xs"]):
        beat = c % 4 == 0
        d.text((x + lay["cw"] / 2, lay["nums"]), str(c + 1), font=fonts["step_b" if beat or c == lit else "step"],
               fill=TEXT if c == lit else BODY if beat else MUTED, anchor="mm")


def draw_grid(img, d, lay, view, fonts, tiles):
    """The grid as it is with the bar nowhere on it: the steps' numbers, each row's mark (its colour) and name, its
    cells (on: lit in the row's colour, a lead's with its note's name), and a ring round the one ◀▶▲▼ have moved
    to."""
    from .theme import ACCENTS, BG, BODY, co_mix, ROW, TEXT
    hues = dict(ACCENTS)
    cw, ch = lay["cw"], lay["ch"]
    dark, dark2 = co_mix(BG, ROW, 0.9), co_mix(BG, ROW, 0.6)
    radius = cw // 5
    draw_steps(d, lay, fonts)
    m = 4 if ch < 44 else 5                             # (half its mark's side)
    for r, y in enumerate(lay["ys"]):
        mine = view["cursor"][0] == r
        name = view["rows"][r]
        f = fonts["row_b" if mine else "row"]
        left = lay["left"] + 2 * m + 9
        while len(name) > 3 and f.getlength(name) > lay["label"] - left:
            name = name[:-2].rstrip() + "…"
        d.rounded_rectangle((lay["left"] + 2, y + ch / 2 - m, lay["left"] + 2 + 2 * m, y + ch / 2 + m), radius=2,
                            fill=hues[ROW_HUES[r]])
        d.text((left, y + ch / 2), name, font=f, fill=TEXT if mine else BODY, anchor="lm")
        for c, x in enumerate(lay["xs"]):
            if view["grid"][r][c]:
                tile, mask = tiles[r][False]
                img.paste(tile, (x, y), mask)
                if r == LEAD_ROW:
                    draw_note(d, x, y, cw, ch, view["names"][c], view["high"][c], fonts["note"])
            else:
                d.rounded_rectangle((x, y, x + cw - 1, y + ch - 1), radius=radius,
                                    fill=dark if c // 4 % 2 == 0 else dark2)
            if view["cursor"] == (r, c):
                d.rounded_rectangle((x - 4, y - 4, x + cw + 3, y + ch + 3), radius=radius + 3, outline=TEXT, width=2)


def knob_values(view):
    """What its buttons say they're set to: the tempo, the key, the scale, the lead's sound."""
    return f"{view['bpm']} BPM", view["key"], view["scale"], view["rows"][LEAD_ROW]


def draw_knobs(d, boxes, view, fonts, named, gap):
    """Its buttons on its line (boxes: soundboard.py's seq_knobs): each its name (named: there's room for them all)
    and what it's set to, in the middle of it, gap apart; a ring round the one ◀▶▲▼ have moved to."""
    from .theme import BG, BODY, co_mix, MUTED, ROW, TEXT
    here = view["cursor"][1] // 4 if view["cursor"][0] == ROWS else None
    for k, ((x0, y0, x1, y1), name, value) in enumerate(zip(boxes, KNOBS, knob_values(view))):
        h = y1 - y0
        d.rounded_rectangle((x0, y0, x1 - 1, y1 - 1), radius=h // 2, fill=co_mix(BG, ROW, 0.9),
                            outline=co_mix(ROW, MUTED, 0.35))
        wide = fonts["knob_b"].getlength(value) + (fonts["knob"].getlength(name) + gap if named else 0)
        x, mid = (x0 + x1 - wide) / 2, (y0 + y1) / 2
        if named:
            d.text((x, mid), name, font=fonts["knob"], fill=BODY if k == here else MUTED, anchor="lm")
            x += fonts["knob"].getlength(name) + gap
        d.text((x, mid), value, font=fonts["knob_b"], fill=TEXT, anchor="lm")
        if k == here:
            d.rounded_rectangle((x0 - 3, y0 - 3, x1 + 2, y1 + 2), radius=h // 2 + 3, outline=TEXT, width=2)


def draw_head(img, d, lay, view, fonts, tiles, step):
    """The column the bar's on: lighter behind it from its number down, its number lit, its cells that are on
    whiter."""
    from .theme import BG, co_mix, ROW, TEXT
    cw, ch = lay["cw"], lay["ch"]
    x = lay["xs"][step]
    radius = cw // 5
    band = co_mix(BG, TEXT, HEAD_BAND)
    top = lay["nums"] - 9
    d.rounded_rectangle((x - 3, top, x + cw + 2, lay["ys"][-1] + ch + 3), radius=radius + 2, fill=band)
    d.text((x + cw / 2, lay["nums"]), str(step + 1), font=fonts["step_b"], fill=TEXT, anchor="mm")
    for r, y in enumerate(lay["ys"]):
        if view["grid"][r][step]:
            tile, mask = tiles[r][True]
            img.paste(tile, (x, y), mask)
            if r == LEAD_ROW:
                draw_note(d, x, y, cw, ch, view["names"][step], view["high"][step], fonts["note"])
        else:
            d.rounded_rectangle((x, y, x + cw - 1, y + ch - 1), radius=radius,
                                fill=co_mix(co_mix(BG, ROW, 0.9), TEXT, 0.14))
        if view["cursor"] == (r, step):
            d.rounded_rectangle((x - 4, y - 4, x + cw + 3, y + ch + 3), radius=radius + 3, outline=TEXT, width=2)


def draw_bars(d, box, levels, colour):
    """The sound as bars (levels: each 0 to 1, low notes at the left), in a box of their own."""
    from .theme import BG, co_mix, LINE, ROW
    x0, y0, x1, y1 = box
    d.rounded_rectangle(box, radius=8, fill=co_mix(BG, ROW, 0.3), outline=LINE)
    n = len(levels)
    pad = 10
    bw = (x1 - x0 - 2 * pad) / max(1, n)
    base = y1 - 9
    room = base - y0 - 10
    dim, bright = co_mix(colour, BG, 0.25), co_mix(colour, (255, 255, 255), 0.2)
    for k, v in enumerate(levels):
        v = max(0.0, min(1.0, v))
        h = max(2, round(v * room))
        bx = x0 + pad + k * bw
        d.rectangle((bx, base - h, bx + max(1, bw - (4 if bw > 8 else 2)), base), fill=co_mix(dim, bright, v))
    d.line((x0 + pad, base + 1, x1 - pad, base + 1), fill=co_mix(colour, BG, 0.45))
