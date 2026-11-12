"""Apps' Band, the music itself: your Pietatos play together, each its own instrument (drums, bass, guitar, keys), and
you play along on the buttons. This is what they play, worked out the same on every one of them, so nothing has to be
sent from one to another but the song, its tempo and when it started (screens/band.py; the sound is bandplay.py's).

A song is a tempo, a feel and its chords, a bar each (SONGS). Each instrument has a part for it at three levels (light,
the groove, busy), written a bar at a time on sixteen steps (PARTS), and played on whatever chord the bar has: so it's
always in key. The song has a shape of its own, four bars at a time (FORM: who comes in when, who's busy, whose solo
it is), and each player says what it does with its next four bars (CHOICES): the song's own part as it is, busier,
simpler, sitting out, a fill, a solo. Dice pick that (dice), or a decision model on your bot's computer does (ask has
what it's told): four bars ahead, and never waited for.

Nothing here but Python's own: no sound, no clock."""
import random

SEATS = ("drums", "bass", "guitar", "keys")
SEAT_NAME = {"drums": "Drums", "bass": "Bass", "guitar": "Guitar", "keys": "Keys"}
BEATS, STEPS, SECTION = 4, 16, 4     # beats in a bar, steps a part's written on, bars a player decides for at a time
BPM = (60, 160)                      # as slow and as fast as a song's played
PADS = ("up", "left", "right", "down", "x", "y", "a", "b")

NOTES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
CHORDS = {"": (0, 4, 7), "m": (0, 3, 7), "7": (0, 4, 7, 10), "m7": (0, 3, 7, 10), "maj7": (0, 4, 7, 11)}
SCALES = {"minor": (0, 3, 5, 7, 10), "major": (0, 2, 4, 7, 9)}   # five notes each: none of them clashes with a chord

# The songs: each a loop of chords, a bar each. feel: which parts (PARTS). swing: how late the notes between the beats
# come (0: evenly; 1: a shuffle's).
SONGS = (
    {"key": "rock", "name": "Rock", "bpm": 116, "feel": "rock", "swing": 0.0, "home": ("A", "minor"),
     "chart": ("Am", "F", "C", "G")},
    {"key": "blues", "name": "Blues", "bpm": 92, "feel": "blues", "swing": 1.0, "home": ("E", "minor"),
     "chart": ("E7", "E7", "E7", "E7", "A7", "A7", "E7", "E7", "B7", "A7", "E7", "B7")},
    {"key": "funk", "name": "Funk", "bpm": 102, "feel": "funk", "swing": 0.0, "home": ("E", "minor"),
     "chart": ("Em7", "Em7", "A7", "A7")},
    {"key": "chill", "name": "Chill", "bpm": 80, "feel": "chill", "swing": 0.35, "home": ("C", "major"),
     "chart": ("Dm7", "G7", "Cmaj7", "Am7")},
)

# The parts, a bar on sixteen steps (four to a beat). Each instrument: light, the groove, busy.
#   drums: three lines (kick, snare, hats): x a hit, X a hard one, o a soft one, O an open hat
#   bass: R the chord's root, 3 its third, 5 fifth, 6 sixth, 7 seventh, 8 the root an octave up, a the note that leads
#         into the next bar's chord; - holds the note before, . is silence
#   guitar: S the chord, strummed and left to ring; s a short one; m muted, low; 1 to 5 its strings, one at a time
#   keys: P the chord, held; c a short one; 1 to 4 its notes, one at a time
PARTS = {
    "rock": {
        "drums": (("x.......x.......", "....x.......x...", "x...x...x...x..."),
                  ("x.....x.x.......", "....x.......x...", "x.x.x.x.x.x.x.x."),
                  ("x.....x.x.x...x.", "....X.......X...", "x.x.x.x.x.x.x.O.")),
        "bass": ("R-------R-------", "R-R-R-R-R-R-R-R-", "R-R-R-R-8-R-5-a-"),
        "guitar": ("S...............", "m.m.m.m.m.m.m.m.", "S.m.m.S.m.m.S.m."),
        "keys": ("P...............", "P.......c...c...", "c.c.c.c.c.c.c.c."),
    },
    "blues": {
        "drums": (("x.......x.......", "....x.......x...", "x...x...x...x..."),
                  ("x.......x.x.....", "....x.......x...", "x.x.x.x.x.x.x.x."),
                  ("x.....x.x.....x.", "....X.......X...", "X.x.X.x.X.x.X.x.")),
        "bass": ("R-------5-------", "R---3---5---6---", "R-R-3-3-5-5-6-5-"),
        "guitar": ("....s.......s...", "m.m.m.m.m.m.m.m.", "S.s.s.s.S.s.s.s."),
        "keys": ("P...............", "..c...c...c...c.", "c.c...c.c.c...c."),
    },
    "funk": {
        "drums": (("x.........x.....", "....x.......x...", "x.x.x.x.x.x.x.x."),
                  ("x..x......x.....", "....x.......x...", "xoxoxoxoxoxoxoxo"),
                  ("x..x..x...x..x..", "....X..o.o..X...", "xoxoxoxoxoxoxoOo")),
        "bass": ("R.........R.....", "R..R......R.8...", "R..R..8...R.8.a."),
        "guitar": ("....s.......s...", "s..s..s...s.s...", "s.ss.s.s.ss.s.s."),
        "keys": ("P...............", "..c.....c..c....", "c..c..c.c..c..c."),
    },
    "chill": {
        "drums": (("x.........x.....", "....o.......o...", "x.x.x.x.x.x.x.x."),
                  ("x......x..x.....", "....x.......x...", "x.x.x.x.x.x.x.x."),
                  ("x..x...x..x.....", "....x.......x...", "x.x.x.x.x.x.x.O.")),
        "bass": ("R---------------", "R---------R-5---", "R-----5---R---a-"),
        "guitar": ("S...............", "1.2.3.4.3.2.3.2.", "1.3.2.4.3.5.4.3."),
        "keys": ("P...............", "P.......3...4...", "1.2.3.4.3.2.3.2."),
    },
}
# The drums' fills: the bar's last two beats (kick, snare, tom), the song going on after with a crash. A feel that
# swings has its own (nothing on the steps between a beat's two halves)
FILLS = {"even": (("x.......", "x.x.xxxx", "........"), ("x.......", "..x...x.", "x.xx.x.x"), ("........", "....x.xx", "........")),
         "swung": (("x.......", "x.x.x.x.", "........"), ("x.......", "....x...", "x.x...x."), ("........", "....x.x.", "........"))}
# A solo's rhythms: a bar each (x a note)
RIFFS = ("x.x.x...x.x.x...", "x...x.x.x...x.x.", "..x.x.x.x.....x.", "x.x...x.x.x.....", "x.....x.x.x.x...",
         "x.x.x.x...x...x.")
RIFFS_SWUNG = ("x.x.x...x.x.x...", "x...x.x.x...x.x.", "..x.x.x.x.....x.", "x.x...x.x.x.....", "x.....x.x...x...")

# The song's shape: what each does (drums, bass, guitar, keys), four bars at a time. 0: sits out; 1 to 3: light, the
# groove, busy; "solo". It starts small, and from the third on goes round (FORM_ROUND).
FORM = ((1, 0, 0, 1), (1, 1, 0, 1), (2, 2, 1, 1), (2, 2, 2, 1), (3, 2, 2, 2), (3, 3, 2, 2), (2, 2, 1, "solo"),
        (2, 2, 1, "solo"), (0, 1, 1, 2), (1, 2, 0, 2), (2, 2, 2, 1), (3, 3, 3, 2), (3, 3, "solo", 1), (3, 3, "solo", 2),
        (2, 2, 2, 2), (1, 1, 1, 1))
FORM_ROUND = 2
FORM_SAYS = {0: "sits out", 1: "plays lightly", 2: "plays the groove", 3: "plays hard", "solo": "takes a solo"}

# What a player can do with its next four bars
CHOICES = {
    "follow": "Play your part as the song has it for these bars",
    "lift": "Play busier than that: more notes, more push",
    "ease": "Play simpler than that: fewer notes, more room for the others",
    "rest": "Sit these four bars out",
    "fill": "Play your part, and a fill at the end of it, into the next four bars",
    "solo": "Take a solo for these four bars",
}
SEAT_CHOICES = {"drums": ("follow", "lift", "ease", "rest", "fill"), "bass": ("follow", "lift", "ease", "rest"),
                "guitar": ("follow", "lift", "ease", "rest", "solo"), "keys": ("follow", "lift", "ease", "rest", "solo")}
DO_SAYS = {"follow": "", "lift": "busier", "ease": "simpler", "rest": "sitting out", "fill": "a fill", "solo": "solo"}
ASKS = ("You play the {seat} in a band of four: drums, bass, guitar and keys. Pick what you do for the next four "
        "bars so that the band sounds good together. Go with the song when it builds or settles. Leave room when "
        "another player takes a solo, or when a person is playing along. Don't do the same thing for too long, and "
        "don't all sit out at once.")

# How loud each is, of all it can be (one Pietato plays them all through one speaker, when it's the only one)
GAIN = {"kick": 0.85, "snare": 0.75, "hat": 0.3, "open": 0.36, "crash": 0.5, "tom": 0.7, "clap": 0.6, "cow": 0.4,
        "bass": 0.75, "strum": 0.72, "stab": 0.75, "mute": 0.85, "string": 0.62, "pad": 0.62, "comp": 0.68, "key": 0.58,
        "lead": 0.72, "you": 0.9, "count": 0.5}
DRUM_FILES = {"kick": "Kick.wav", "snare": "Snare.wav", "hat": "Hi-hat.wav", "open": "Open hat.wav",
              "crash": "Crash.wav", "tom": "Tom.wav", "clap": "Clap.wav", "cow": "Cowbell.wav"}
DRUM_PADS = {"a": ("Kick", "kick"), "b": ("Snare", "snare"), "x": ("Hi-hat", "hat"), "y": ("Open hat", "open"),
             "left": ("Tom", "tom"), "right": ("Clap", "clap"), "up": ("Crash", "crash"), "down": ("Cowbell", "cow")}
RING = {"bass": 1.4, "guitar": 2.0, "keys": 3.6}     # seconds a note of each is made to last
SHORT = 0.22                                          # ...and a short chord


# ---- songs, chords, notes -------------------------------------------------------------------------------------------
def song(key):
    """A song by its key (the first, for one there isn't)."""
    return next((s for s in SONGS if s["key"] == key), SONGS[0])


def chord(name):
    """A chord by its name ("Am7"): (its root, 0 to 11 from C; its kind; its notes, 0 to 11)."""
    root = name[:2] if name[1:2] == "#" else name[:1]
    kind = name[len(root):]
    r = NOTES.index(root)
    return r, kind, tuple((r + i) % 12 for i in CHORDS[kind])


def note_name(midi):
    return f"{NOTES[midi % 12]}{midi // 12 - 1}"


def in_range(pc, low):
    """The note of that name (0 to 11) at or just above low."""
    return low + (pc - low) % 12


def bass_notes(name, then=None):
    """A chord's notes for the bass: {R, 3, 5, 6, 7, 8, a}. a leads into the chord after (then): a step below its
    root; the same chord again: this one's fifth, from below."""
    r, kind, _ = chord(name)
    root = in_range(r, 28)                             # E1 to D#2
    iv = CHORDS[kind]
    out = {"R": root, "3": root + iv[1], "5": root + 7 if root + 7 <= 43 else root - 5, "6": root + 9,
           "7": root + (iv[3] if len(iv) > 3 else 10), "8": root + 12}
    nxt = in_range(chord(then)[0], 28) if then else root
    out["a"] = nxt - 1 if nxt != root else out["5"]
    return out


def guitar_notes(name):
    """A chord on the guitar, low to high: its root, fifth, the root again (or its seventh), its third above that,
    its fifth above that."""
    r, kind, _ = chord(name)
    root = in_range(r, 40)                             # E2 to D#3
    iv = CHORDS[kind]
    return (root, root + 7, root + (iv[3] if len(iv) > 3 else 12), root + 12 + iv[1], root + 19)


def keys_notes(name):
    """A chord on the keys: its notes, close together round the middle of the keyboard."""
    return tuple(sorted(in_range(pc, 57) for pc in chord(name)[2]))


def scale_notes(a_song, low, high):
    """The notes a solo's made of: the song's five, from low to high."""
    root, kind = a_song["home"]
    pcs = {(NOTES.index(root) + i) % 12 for i in SCALES[kind]}
    return [m for m in range(low, high + 1) if m % 12 in pcs]


LEAD = {"guitar": (57, 76), "keys": (69, 86), "bass": (28, 43)}


# ---- its sounds: what each is called, and what it's made of (bandplay.py makes them) --------------------------------
def note_id(seat, midi):
    return f"{seat[0]}{midi}"


def spec(voice, notes, secs, how=""):
    return f"synth:{voice}:{'+'.join(str(n) for n in notes)}:{secs:g}" + (f":{how}" if how else "")


def chord_sounds(seat, name):
    """A chord's own sounds on the guitar or the keys: {what it's for: (its name, what it's made of)}."""
    if seat == "guitar":
        notes = guitar_notes(name)
        return {"strum": (f"g{name}", spec("guitar", notes, RING["guitar"], "strum")),
                "stab": (f"g{name}.", spec("guitar", notes[1:], SHORT, "stab")),
                "mute": (f"g{name}_", spec("guitar", notes[:2], 0.16, "mute"))}
    notes = keys_notes(name)
    return {"pad": (f"k{name}", spec("keys", notes, RING["keys"])),
            "comp": (f"k{name}.", spec("keys", notes, 0.3, "stab"))}


def note_sound(seat, midi):
    return note_id(seat, midi), spec(seat, (midi,), RING[seat])


def sounds(a_song, seats, mine=None, folder=""):
    """Every sound those instruments may play in a song, the ones wanted soonest first: [(its name, a file's path or
    what it's made of)]. mine: the instrument you play on the buttons (its sounds too). folder: where the drums'
    files are."""
    out, seen = [], set()

    def add(name, what):
        if name not in seen:
            seen.add(name)
            out.append((name, what))
    want = [s for s in SEATS if s in seats or s == mine]
    chart = list(dict.fromkeys(a_song["chart"]))
    if "drums" in want:
        for key, fn in DRUM_FILES.items():
            add(key, f"{folder}/{fn}")
    for seat in want:
        if seat == "bass":
            for name in chart:
                add(*note_sound("bass", bass_notes(name)["R"]))
            for name in a_song["chart"]:
                for then in a_song["chart"]:
                    for midi in bass_notes(name, then).values():
                        add(*note_sound("bass", midi))
        elif seat in ("guitar", "keys"):
            for name in chart:
                for name_, what in chord_sounds(seat, name).values():
                    add(name_, what)
            for name in chart:
                for midi in (guitar_notes(name) if seat == "guitar" else keys_notes(name) + (keys_notes(name)[0] + 12,)):
                    add(*note_sound(seat, midi))
            for midi in scale_notes(a_song, *LEAD[seat]):
                add(*note_sound(seat, midi))
    if mine == "bass":
        for midi in scale_notes(a_song, *LEAD["bass"]):
            add(*note_sound("bass", midi))
    return out


# ---- when a step is ----------------------------------------------------------------------------------------------------
def step_at(step, swing=0.0):
    """Where in its bar a step is, in beats: evenly, or with the notes between the beats late (a shuffle: swing 1)."""
    beat, sub = divmod(step, 4)
    half = 0.5 + swing / 6.0
    return beat + (0.0, half / 2, half, (half + 1) / 2)[sub]


def held(line, k):
    """How many steps the note at step k lasts: till the next note or silence."""
    n = 1
    while k + n < len(line) and line[k + n] == "-":
        n += 1
    return n


# ---- the parts -------------------------------------------------------------------------------------------------------
def bar(a_song, seat, n, level, solo=False, fill=False, crash=False, seed=0):
    """Bar n of a song as one instrument plays it: [(when in the bar, in beats; the sound; how loud, 0 to 1; its
    lane: a sound in a lane ends the one before it there; how long it lasts, in beats: 0, all of it)], in order.
    level: 0 (nothing) to 3. solo: a solo instead (guitar, keys). fill: the drums' fill at its end. crash: a crash
    on its first beat."""
    chart, sw = a_song["chart"], a_song["swing"]
    name, then = chart[n % len(chart)], chart[(n + 1) % len(chart)]
    out = []
    if seat == "drums":
        if crash and level:
            out.append((0.0, "crash", GAIN["crash"], "", 0))
        if level:
            kick, snare, hats = PARTS[a_song["feel"]]["drums"][level - 1]
            if fill:
                k, s, t = FILLS["swung" if sw > 0.2 else "even"][(seed + n) % 3]
                kick, snare, hats = kick[:8] + k, snare[:8] + s, hats[:8] + "." * 8
                out += [(step_at(8 + i, sw), "tom", GAIN["tom"], "", 0) for i, c in enumerate(t) if c == "x"]
            for line, what in ((kick, "kick"), (snare, "snare")):
                for i, c in enumerate(line):
                    if c != ".":
                        out.append((step_at(i, sw), what, GAIN[what] * {"X": 1.15, "o": 0.4}.get(c, 1.0), "", 0))
            for i, c in enumerate(hats):
                if c != ".":
                    what = "open" if c == "O" else "hat"
                    out.append((step_at(i, sw), what, GAIN[what] * {"X": 1.3, "o": 0.5}.get(c, 1.0), "hat", 0))
    elif solo and seat in ("guitar", "keys"):
        out = solo_bar(a_song, seat, n, seed)
    elif level and seat == "bass":
        line, notes = PARTS[a_song["feel"]]["bass"][level - 1], bass_notes(name, then)
        for i, c in enumerate(line):
            if c in notes:
                long = step_at(i + held(line, i), sw) - step_at(i, sw)
                out.append((step_at(i, sw), note_id("bass", notes[c]), GAIN["bass"], "bass", round(long * 0.92, 4)))
    elif level and seat == "guitar":
        line, own, strings = PARTS[a_song["feel"]]["guitar"][level - 1], chord_sounds("guitar", name), guitar_notes(name)
        for i, c in enumerate(line):
            at = step_at(i, sw)
            if c == "S":
                out.append((at, own["strum"][0], GAIN["strum"], "guitar", 0))
            elif c == "s":
                out.append((at, own["stab"][0], GAIN["stab"], "guitar", 0))
            elif c == "m":
                out.append((at, own["mute"][0], GAIN["mute"], "guitar", 0))
            elif c.isdigit():
                out.append((at, note_id("guitar", strings[int(c) - 1]), GAIN["string"], "", 0))
    elif level and seat == "keys":
        line, own, notes = PARTS[a_song["feel"]]["keys"][level - 1], chord_sounds("keys", name), keys_notes(name)
        notes = notes + (notes[0] + 12,)
        for i, c in enumerate(line):
            at = step_at(i, sw)
            if c == "P":
                out.append((at, own["pad"][0], GAIN["pad"], "keys", 0))
            elif c == "c":
                out.append((at, own["comp"][0], GAIN["comp"], "keys", 0))
            elif c.isdigit():
                out.append((at, note_id("keys", notes[min(int(c), len(notes)) - 1]), GAIN["key"], "", 0))
    return sorted(out)


def solo_bar(a_song, seat, n, seed=0):
    """A bar of a solo: four bars are made at a time, from the song's five notes. Each bar has a rhythm of its own
    (the third the first's again); the tune steps up and down them, lands on a note of the bar's chord on its first
    and third beats, and ends on one, held."""
    first = n - n % SECTION
    r = random.Random(f"solo:{seed}:{seat}:{first}")
    notes = scale_notes(a_song, *LEAD[seat])
    sw = a_song["swing"]
    riffs = RIFFS_SWUNG if sw > 0.2 else RIFFS
    picks = [r.choice(riffs) for _ in range(SECTION)]
    picks[2] = picks[0]
    at = r.randrange(len(notes) // 3, 2 * len(notes) // 3)
    bars = []
    for k in range(SECTION):
        tones = set(chord(a_song["chart"][(first + k) % len(a_song["chart"])])[2])
        line, out = picks[k], []
        steps = [i for i, c in enumerate(line) if c == "x"]
        for j, i in enumerate(steps):
            at = max(0, min(len(notes) - 1, at + r.choice((-2, -1, -1, 1, 1, 2, 0))))
            last = k == SECTION - 1 and j == len(steps) - 1
            if i % 8 == 0 or last:                     # (a strong beat, or its last note: one of the chord's)
                near = sorted(range(len(notes)), key=lambda x: (notes[x] % 12 not in tones, abs(x - at)))
                at = near[0]
            long = (steps[j + 1] - i if j + 1 < len(steps) else STEPS - i)
            out.append((step_at(i, sw), note_id(seat, notes[at]), GAIN["lead"], seat + ".l",
                        round(min(long, 6) * 0.25 * 0.95, 4)))
        bars.append(out)
    return bars[n % SECTION]


def count_in(a_song):
    """The bar before the first: four taps, so everyone starts together."""
    return [(float(b), "hat", GAIN["count"] * (1.4 if b == 0 else 1.0), "hat", 0) for b in range(BEATS)]


# ---- the song's shape, and what each does with it ---------------------------------------------------------------------
def form(seed, section):
    """What the song has each do in a section (four bars): {instrument: 0 to 3, or "solo"}. Which of the guitar and
    the keys solos first goes by the seed."""
    k = section if section < len(FORM) else FORM_ROUND + (section - len(FORM)) % (len(FORM) - FORM_ROUND)
    row = dict(zip(SEATS, FORM[k]))
    if seed % 2:
        row["guitar"], row["keys"] = row["keys"], row["guitar"]
    return row


def played(base, do):
    """A player's part for a section: what the song has (0 to 3, or "solo") and what the player does with it:
    (its level, 0 to 3; a solo; a fill at its end)."""
    solo = base == "solo"
    level = 2 if solo else int(base)
    if do == "rest":
        return 0, False, False
    if do == "lift":
        level = min(3, level + 1)
    elif do == "ease":
        level, solo = (max(1, level - 1) if level else 0), False
    elif do == "solo":
        level, solo = max(level, 2), True
    return level, solo, do == "fill" and level > 0


def dice(seed, seat, section, others=None, person=None):
    """What a player does with a section when nobody's asked: the song's own part, mostly; now and then busier or
    simpler; the drums a fill, often; and the guitar and the keys simpler while another solos or a person plays
    along on one of them. others: {instrument: what it's doing}; person: the instrument a person's playing."""
    r = random.Random(f"dice:{seed}:{seat}:{section}").random()
    lead = any(do == "solo" for s, do in (others or {}).items() if s != seat) or (person in ("guitar", "keys")
                                                                                     and person != seat)
    if seat in ("guitar", "keys") and lead:
        return "ease"
    if seat == "drums":
        return "fill" if r < 0.45 else "follow" if r < 0.85 else "lift" if r < 0.93 else "ease"
    return "follow" if r < 0.72 else "lift" if r < 0.86 else "ease"


def ask(a_song, bpm, seat, section, seed, doing=None, others=None, person=None):
    """What a decision model's asked for a player's next four bars: (what it's told of the band, the question, its
    choices). doing: (what this player's been doing, for how many sections); others: {instrument: what it's doing};
    person: (the instrument a person's playing along on, how busily: 1 to 3)."""
    now, nxt = form(seed, section - 1) if section else {}, form(seed, section)
    state = {"song": a_song["name"], "tempo": bpm, "four_bars_number": section + 1,
             "the_song_has_you": FORM_SAYS[nxt[seat]],
             "the_song_has_the_others": {SEAT_NAME[s]: FORM_SAYS[nxt[s]] for s in SEATS if s != seat},
             "before_that_you": FORM_SAYS[now[seat]] if now else "hadn't started"}
    if doing:
        state["you_have_been"] = {"doing": CHOICES[doing[0]], "for_this_many_times_running": doing[1]}
    if others:
        state["the_others_now"] = {SEAT_NAME[s]: CHOICES[do] for s, do in others.items() if s != seat and do in CHOICES}
    if person and person[0] in SEAT_NAME:
        state["a_person_is_playing"] = {"instrument": SEAT_NAME[person[0]], "how_busily_1_to_3": person[1]}
    return state, ASKS.format(seat=SEAT_NAME[seat].lower()), {k: CHOICES[k] for k in SEAT_CHOICES[seat]}


# ---- the buttons: your instrument ---------------------------------------------------------------------------------------
def pads(a_song, seat, name):
    """What each button plays on an instrument while the bar's chord is name: {button: (what its tile says, the
    sound, how loud, its lane, how long in beats: 0, all of it)}. The drums: one each. The others: A, B, X and Y go
    with the chord (so they always fit); the d-pad's four are notes of the song's own, low to high (down, left,
    right, up)."""
    you = GAIN["you"]
    if seat == "drums":
        return {pad: (label, key, min(1.0, GAIN[key] * 1.25), "hat" if key in ("hat", "open") else "", 0)
                for pad, (label, key) in DRUM_PADS.items()}
    low, high = LEAD[seat]
    tune = scale_notes(a_song, low, high)
    home = NOTES.index(a_song["home"][0])
    first = min(next(i for i, m in enumerate(tune) if m % 12 == home), max(0, len(tune) - 4))
    out = {pad: (note_name(m), note_id(seat, m), you * 0.8, "" if seat == "keys" else seat + ".l", 0)
           for pad, m in zip(("down", "left", "right", "up"), tune[first:first + 4])}
    if seat == "bass":
        notes = bass_notes(name)
        for pad, c in (("a", "R"), ("b", "5"), ("x", "3"), ("y", "8")):
            out[pad] = (note_name(notes[c]), note_id("bass", notes[c]), you, "bass", 0)
        return out
    own = chord_sounds(seat, name)
    if seat == "guitar":
        strings = guitar_notes(name)
        out["a"] = (name, own["strum"][0], you * 0.75, "guitar", 0)
        out["b"] = (name + " short", own["stab"][0], you * 0.75, "guitar", 0)
        out["x"] = (note_name(strings[3]), note_id("guitar", strings[3]), you * 0.8, "guitar.l", 0)
        out["y"] = (note_name(strings[2]), note_id("guitar", strings[2]), you * 0.8, "guitar.l", 0)
        return out
    notes = keys_notes(name)
    out["a"] = (name, own["pad"][0], you * 0.7, "keys", 0)
    out["b"] = (name + " short", own["comp"][0], you * 0.75, "keys", 0)
    out["x"] = (note_name(notes[-1]), note_id("keys", notes[-1]), you * 0.8, "", 0)
    out["y"] = (note_name(notes[0] + 12), note_id("keys", notes[0] + 12), you * 0.8, "", 0)
    return out
