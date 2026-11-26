"""The Soundboard's Sequencer (pitato/sequencer.py, screens/sequencer.py, soundplay.py). The tune on its own: made from
a number (the same number, the same tune; a Pietato's name, its number), changed a little, kept as a line of text
and read back, its cells as the loop takes them (the lead's notes, the key's), which step the bar's on, and where
its page's parts go. Its player: one of its own sounds in a loop, at its note, at its very frame, as loud as the loop
says; a row's sound starting again as its next cell comes, so never more sounds at once than rows; the sound as bars
(low notes at the left, the same at any volume, said twenty times a second, silence said once), through the real
player too, and nothing said of them till they're asked for. Then in media mode: START's card, Sequencer; its page,
still till it plays; A turns a cell on and off (heard at once, stopped), X a lead cell's note or a drum's sound; a
tap on a cell; B plays it: the loop told its cells, heard on their beats; the bar going along the grid, the sound's
bars under it; Y, and taking that back; a new tune, clearing it; L and R, SELECT, its card; HOME, and the
Soundboard's buttons over it; START held there; Bounce with it; the Soundboard left and opened again; the tune kept;
a bigger screen, and drawn finely."""
import json, os, random, shutil, subprocess, sys, threading, time, wave
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
sys.path.insert(0, ROOT)
import numpy as np

S = SP + "/t_sequencer"
shutil.rmtree(S, ignore_errors=True)
for d in (S + "/bin", S + "/cache", S + "/files"):
    os.makedirs(d)
ok_all = []
RATE = 48000
PLAYER = ROOT + "/pitato/soundplay.py"
ONLY = sys.argv[1:]


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def until(cond, secs=5.0, step=0.01):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(step)
    return bool(cond())


# a pretend aplay (test_bounce.py's): it plays what it's sent at the sound card's rate, through a buffer as long as it's
# told, and logs each period as it goes in (when, where in the stream, how loud, where its first sound is) and when it
# starts playing: so when each sound's heard
open(S + "/bin/aplay", "w").write('''#!/usr/bin/env python3
import os, sys, time
import numpy as np
args = sys.argv[1:]
rate = int(args[args.index("-r") + 1]) if "-r" in args else 48000
buf = next((int(a.split("=")[1]) for a in args if a.startswith("--buffer-time=")), 100000)
per = next((int(a.split("=")[1]) for a in args if a.startswith("--period-time=")), 20000)
log = open(os.environ["FAKE_APLAY_LOG"], "a", buffering=1)
time.sleep(0.03)
pf, bf = per * rate // 1000000, buf * rate // 1000000
log.write(f"# open {time.monotonic():.6f} buffer {buf} period {per}\\n")
start, offset, written = None, 0, 0
def whole(n):
    out = b""
    while len(out) < n:
        d = os.read(0, n - len(out))
        if not d:
            return None
        out += d
    return out
while True:
    data = whole(pf * 4)
    if data is None:
        break
    while True:
        now = time.monotonic()
        played = offset if start is None else offset + int((now - start) * rate)
        if start is not None and played >= written:
            sys.stderr.write("underrun!!! (at least 1.000 ms long)\\n"); sys.stderr.flush()
            log.write(f"# underrun {now:.6f}\\n")
            start, offset, played = None, written, written
        if written - played + pf <= bf:
            break
        time.sleep(0.0004)
    x = np.frombuffer(data, dtype="<i2").reshape(-1, 2).astype(np.int64)
    loud = np.nonzero(np.abs(x).max(axis=1) > 200)[0]
    log.write(f"{time.monotonic():.6f} {written} {int(np.abs(x).max())} {int(loud[0]) if len(loud) else -1}\\n")
    written += pf
    if start is None and written - offset + pf > bf:
        start = time.monotonic()
        log.write(f"# start {start:.6f} at {offset}\\n")
''')
os.chmod(S + "/bin/aplay", 0o755)
os.environ["PATH"] = S + "/bin:" + os.environ["PATH"]
ALOG = S + "/aplay.log"
os.environ["FAKE_APLAY_LOG"] = ALOG


def heard(since=0):
    """Each sound heard after that line of the log, as the sound card plays it: [(when its first loud sample's heard,
    the period's peak)], one for each start after silence; and the periods' (when heard, peak, loud or not)."""
    start = offset = None
    out, periods, quiet = [], [], True
    lines = open(ALOG).read().splitlines()
    for k, ln in enumerate(lines):
        if ln.startswith("# start"):
            start, offset = float(ln.split()[2]), int(ln.split()[4])
            continue
        if ln.startswith("#") or len(ln.split()) != 4 or start is None:
            continue
        t, at, peak, first = ln.split()
        at, peak, first = int(at), int(peak), int(first)
        when = start + (at - offset) / RATE
        if k >= since:
            periods.append((when, peak, first >= 0))
            if first >= 0 and quiet:
                out.append((start + (at + first - offset) / RATE, peak))
        quiet = first < 0
    return out, periods


def log_at():
    try:
        return len(open(ALOG).read().splitlines())
    except OSError:
        return 0


def wav(path, x):
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(np.asarray(x, dtype="<i2").tobytes())
    return path


def burst(path, secs=0.03, amp=20000, f=1000.0):
    """A short, loud sound that starts at once."""
    t = np.arange(int(secs * RATE)) / RATE
    return wav(path, np.sin(2 * np.pi * f * t) * amp * np.minimum(1.0, (secs - t) * 400))


class Player:
    def __init__(self, cache=S + "/cache", **env):
        self.said = []
        self.p = subprocess.Popen([sys.executable, "-I", PLAYER, cache], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  env=dict(os.environ, **env), text=True, bufsize=1)
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        for line in self.p.stdout:
            self.said.append((time.monotonic(), json.loads(line)))

    def tell(self, **c):
        self.p.stdin.write(json.dumps(c) + "\n")
        self.p.stdin.flush()

    def got(self, what, **more):
        return [m for _, m in self.said if m.get("is") == what and all(m.get(k) == v for k, v in more.items())]

    def quit(self):
        try:
            self.tell(do="quit")
        except (OSError, ValueError):
            pass
        try:
            return self.p.wait(5)
        except subprocess.TimeoutExpired:
            self.p.kill()
            return None


DEN = "x..x..x.x......./....x.......x..x/x.x.x.x...x.x.x./x.x.x.....x...x.:0000220342357677"   # (the name Den's tune)

# ---- the tune, on its own ------------------------------------------------------------------------------------------
if not ONLY or "tune" in ONLY:
    import pitato.bounce as BN
    import pitato.sequencer as SQ
    den, again = SQ.born(SQ.seed_of("Den")), SQ.born(SQ.seed_of("Den"))
    names = ["Den", "Kitchen", "Sam", ""] + [f"pietato-{k}" for k in range(60)]
    tunes = {SQ.dumps(*SQ.born(SQ.seed_of(n))) for n in names}
    check(f"a tune made from a Pietato's name: the same name, the same tune, whenever it's made ({SQ.dumps(*den)}); "
          f"another name, another ({len(tunes)} tunes from {len(names)} names)",
          den == again and SQ.dumps(*den) == DEN and len(tunes) >= len(names) - 2)
    made = [SQ.born(k) for k in range(200)]
    shapes = all(len(g_) == SQ.ROWS == 4 and all(len(r) == SQ.STEPS == 16 and all(type(c) is bool for c in r)
                                                 for r in g_) and len(n) == 16 for g_, n in made)
    ranges = all(all(type(x) is int and 0 <= x < SQ.NOTES for x in n) and n[0] == 0
                 and all(abs(a - b_) <= 3 for a, b_ in zip(n, n[1:])) for _, n in made)
    anchors = all(g_[0][0] and g_[1][4] and g_[1][12] and g_[3][0] for g_, _ in made)
    counts = [sum(sum(r) for r in g_) for g_, _ in made]
    check(f"...each a grid of four rows of sixteen steps and a note for each of the lead's; a kick on the bar's first "
          f"beat, a snare on its second and fourth, the lead's first note the key's own, each next one a step or "
          f"three from the last; a tune's worth of cells on ({min(counts)} to {max(counts)} of 64)",
          shapes and ranges and anchors and 8 <= min(counts) and max(counts) <= 46)
    cells, moved, same, kept = [], [], 0, True
    for k in range(100):
        grid, notes = SQ.born(1000 + k)
        was = SQ.dumps(grid, notes)
        g2, n2 = SQ.mutated(grid, notes, random.Random(k))
        kept = kept and SQ.dumps(grid, notes) == was and g2 is not grid and all(a is not b_ for a, b_ in zip(g2, grid))
        cells.append(sum(a != b_ for r1, r2 in zip(grid, g2) for a, b_ in zip(r1, r2)))
        moved.append(sum(a != b_ for a, b_ in zip(notes, n2)))
        same += SQ.dumps(g2, n2) == was
        kept = kept and all(type(x) is int and 0 <= x < SQ.NOTES for x in n2) and len(g2) == 4 and all(
            len(r) == 16 and all(type(c_) is bool for c_ in r) for r in g2)
    check(f"changed a little: a few cells on or off ({min(cells)} to {max(cells)}), up to three of the lead's notes "
          f"moved ({max(moved)} at most), a new tune each time ({same} of 100 the same), the one it was made from as "
          f"it was", kept and 2 <= min(cells) and max(cells) <= 4 and max(moved) <= 3 and same == 0)
    rng = random.Random(42)
    grid, notes = [[True] * 16 for _ in range(4)], [7] * 16
    counts, anchors = [], []
    for k in range(400):                               # (every cell on to start with: not a tune at all)
        grid, notes = SQ.mutated(grid, notes, rng)
        if k >= 200:
            counts.append(sum(sum(r) for r in grid))
            anchors.append(grid[0][0] and grid[1][4] and grid[1][12])
    born_counts = [sum(sum(r) for r in g_) for g_, _ in made]
    check(f"changed again and again (400 times, from every cell on): still a tune, as many cells on as one made "
          f"afresh has ({min(counts)} to {max(counts)}, theirs {min(born_counts)} to {max(born_counts)}), its kick on "
          f"the bar's first beat and its snare on the second and fourth ({sum(anchors)} of {len(anchors)} times)",
          10 <= min(counts) and max(counts) <= 46 and sum(anchors) >= 0.9 * len(anchors))
    back = all(SQ.loads(SQ.dumps(*t)) == t for t in made[:50])
    half = DEN.split(":")[0]
    bad = [SQ.loads(x) for x in ("", None, 7, "x" * 16, half, half + ":00002203423576", half + ":0000220342357678",
                                 half + ":000022034235767x", DEN.replace("/", "", 1), DEN.replace("x", "o", 1),
                                 half[:-1] + ":" + "0" * 16, half + "/" + "." * 16 + ":" + "0" * 16)]
    check(f"kept as a line of text and read back: the same tune; a line that isn't one (nothing, half of one, a note "
          f"there isn't, a row too short, a row too many...): none ({bad})", back and bad == [None] * len(bad)
          and SQ.loads(DEN) == den and SQ.dumps(*SQ.loads(DEN)) == DEN)
    grid = [[False] * 16 for _ in range(4)]
    grid[0][0] = grid[0][6] = grid[1][4] = grid[2][2] = grid[3][3] = grid[3][8] = True
    notes = [0] * 16
    notes[3] = 5
    hits = SQ.hits(grid, notes, ["K", "S", "H", "Tones/Pluck"], "C", "Pentatonic")
    minor = SQ.hits(grid, notes, ["K", "", None, "Tones/Bell"], "A", "Minor")
    every = [SQ.note_of(n, key, scale) - BN.TONE_ROOT for key in BN.KEYS for scale in BN.SCALES
             for n in range(SQ.NOTES)]
    check(f"its cells as the loop takes them: each one that's on, at its step's beat, its row's sound, as loud as its "
          f"row is ({hits}); the lead's at their notes, the key's (C pentatonic: its sixth note the C above; A minor: "
          f"{minor[-2:]}), whole semitones from middle C, never far ({min(every)} to {max(every)}); a row with no "
          f"sound, not at all", hits == [(0.0, "K", 0, SQ.GAINS[0]), (1.5, "K", 0, SQ.GAINS[0]),
                                         (1.0, "S", 0, SQ.GAINS[1]), (0.5, "H", 0, SQ.GAINS[2]),
                                         (0.75, "Tones/Pluck", 12, SQ.GAINS[3]), (2.0, "Tones/Pluck", 0, SQ.GAINS[3])]
          and minor == [(0.0, "K", 0, SQ.GAINS[0]), (1.5, "K", 0, SQ.GAINS[0]),
                        (0.75, "Tones/Bell", 5, SQ.GAINS[3]), (2.0, "Tones/Bell", -3, SQ.GAINS[3])]
          and all(type(x) is int for x in every) and -6 <= min(every) and max(every) <= 24
          and SQ.BAR == 4.0 and all(0 < x <= 1 for x in SQ.GAINS))
    c120 = (120.0, 0.0, 100.0)
    steps = [SQ.step_at(c120, t) for t in (100.0, 100.124, 100.126, 101.999, 102.001)]
    check(f"the step the bar's on: a sixteenth of a beat each, round and round ({steps}; from beat 2.5: "
          f"{SQ.step_at((120.0, 2.5, 100.0), 100.0)}), and how long till its next "
          f"({SQ.next_step_in(c120, 100.1):.3f} s)", steps == [0, 0, 1, 15, 0]
          and SQ.step_at((120.0, 2.5, 100.0), 100.0) == 10 and abs(SQ.next_step_in(c120, 100.1) - 0.025) < 1e-6)
    fits = []
    for box, big in (((0, 40, 640, 346), False), ((0, 40, 960, 406), True), ((0, 40, 1920, 946), True)):
        lay = SQ.layout(box, big)
        xs, ys, cw, ch = lay["xs"], lay["ys"], lay["cw"], lay["ch"]
        gaps = [b_ - a - cw for a, b_ in zip(xs, xs[1:])]
        bx0, by0, bx1, by1 = lay["bars"]
        fits.append(len(xs) == 16 and len(ys) == 4 and cw >= 28 and ch >= cw
                    and all(g_ > 0 for g_ in gaps) and all(gaps[k] > gaps[0] for k in (3, 7, 11))
                    and len({g_ for k, g_ in enumerate(gaps) if k % 4 != 3}) == 1
                    and box[0] < lay["left"] < lay["label"] < xs[0] and xs[-1] + cw <= box[2] - 12
                    and ys[0] > box[1] and all(b_ - a > ch for a, b_ in zip(ys, ys[1:]))
                    and by0 > ys[-1] + ch and box[0] < bx0 < bx1 < box[2] and by1 <= box[3] and by1 - by0 >= 80)
    check(f"where its page's parts go, on the GPi Case's screen and on bigger ones: sixteen cells across in four "
          f"beats of four, four rows, the rows' names at their left, the bars' box under them, all of it on the page "
          f"({fits})", all(fits))

# ---- its player ----------------------------------------------------------------------------------------------------
if not ONLY or "player" in ONLY:
    import pitato.sequencer as SQ
    sys.path.insert(0, ROOT + "/pitato")
    import soundplay as SPL
    said = []
    real_say = SPL.say
    SPL.say = lambda **w: said.append(w)
    pl = SPL.Player(S + "/cache")
    pl.told({"do": "tone", "id": "Tones/Pluck"}, 0.0)
    until(lambda: all(("tone", "Tones/Pluck", r) in pl.made for r in SPL.TONE_ROOTS), 20)
    t = np.arange(int(0.05 * RATE)) / RATE
    pl.sounds["tick"] = (None, (np.sin(2 * np.pi * 1000 * t) * 20000 * np.minimum(1.0, (0.05 - t) * 400)
                                ).astype(np.int16))

    def mixed(hits, secs, bpm=120.0, beats=4, look=None):
        """What its player mixes of a loop, with no sound card (its clock: the frames it's mixed): left and right."""
        pl.loop = SPL.loop_from({"hits": hits, "beats": beats, "bpm": bpm, "b0": 0.0, "t0": 0.0, "click": False})
        pl.base, pl.fed, pl.voices = 0.0, 0, []
        out = []
        for _ in range(int(secs * RATE / SPL.CHUNK)):
            out.append(np.frombuffer(pl.mix(), dtype="<i2").reshape(-1, 2).astype(np.int32))
            if look is not None:
                look()
            pl.fed += SPL.CHUNK
        return np.concatenate(out)

    found, starts = {}, {}
    for semis in (0, 7, 12, 16, -5):
        x = mixed([[1.5, "Tones/Pluck", semis, -1e9]], 1.6)
        loud = np.nonzero(np.abs(x[:, 0]) > 60)[0]
        starts[semis] = int(loud[0]) - int(0.75 * RATE) if len(loud) else None
        found[semis] = SPL.pitch_of(x[int(0.75 * RATE):, 0].astype(np.int16))
    check(f"one of its player's own sounds in a loop (the lead's): heard, at its note (so many semitones from middle "
          f"C: {found}), from its beat's very frame ({starts} frames after it)",
          all(v is not None and abs(v - (60 + k)) < 0.3 for k, v in found.items())
          and all(v is not None and 0 <= v <= 48 for v in starts.values()))
    full = mixed([[0, "Tones/Pluck", 0, -1e9]], 0.5)
    half = mixed([[0, "Tones/Pluck", 0, -1e9, 4, 0.5]], 0.5)
    tick = mixed([[0, "tick", 0, -1e9, 4, 0.25]], 0.3)
    ratio = np.abs(half).max() / max(1, np.abs(full).max())
    odd = [SPL.loop_from({"hits": [[0, "tick", 0, 0, 4, gain]], "beats": 4, "bpm": 120, "b0": 0, "t0": 0})
           for gain in (-0.5, 9, "loud", float("nan"), None)]
    plain = SPL.loop_from({"hits": [[0, "tick", 0, 0], [1, "tick", 0, 0, 2]], "beats": 4, "bpm": 120, "b0": 0, "t0": 0})
    check(f"...as loud as the loop says: half ({ratio:.3f} of it), one of the Soundboard's a quarter "
          f"({np.abs(tick).max()} of {int(20000 * 0.25 * pl.gain / 256)}); as it is, when it doesn't say "
          f"({plain and [g_[1] for g_ in plain['groups']]}); a loudness that isn't one: not in the loop ({odd})",
          abs(ratio - 0.5) < 0.02 and abs(int(np.abs(tick).max()) - int(20000 * 0.25 * pl.gain / 256)) <= 40
          and plain is not None and [g_[1] for g_ in plain["groups"]] == [[(1.0, "tick", 0, 0.0, 1.0)],
                                                                         [(0.0, "tick", 0, 0.0, 1.0)]]
          and odd == [None] * len(odd))
    live, total = [], []
    grid = [[True] * 16 for _ in range(4)]
    busy = [[b_, sid, semis, -1e9, 4, gain] for b_, sid, semis, gain in
            SQ.hits(grid, [k % 8 for k in range(16)], ["tick", "tick", "tick", "Tones/Pluck"], "C", "Major")]
    for k, h in enumerate(busy):                       # (three rows, three sounds: the tick under three names)
        if h[1] == "tick":
            h[1] = ("tick", "tock", "tuck")[k // 16]
    pl.sounds["tock"] = pl.sounds["tuck"] = pl.sounds["tick"]
    x = mixed(busy, 2.0, bpm=240.0, look=lambda: (live.append(sum(1 for v in pl.voices if v.fade is None)),
                                                  total.append(len(pl.voices))))
    check(f"every cell of the grid on, as fast as it goes: each row's sound starts again as its next cell comes, so "
          f"never more sounds at once than rows ({max(live)} going, {max(total)} with the ones fading out), and "
          f"it's heard ({np.abs(x).max()})", max(live) == 4 and max(total) <= 8 and np.abs(x).max() > 8000)

    # the sound as bars
    def bars_of(x, gain=256, then=0.0):
        """What it says of a sound (left and right the same, as loud as x) played at that volume, then silence."""
        pl.gain = gain
        pl.bars_set(False)
        pl.bars_set(True)
        del said[:]
        n = 0
        for k in range(len(x) // SPL.CHUNK):
            chunk = (x[k * SPL.CHUNK:(k + 1) * SPL.CHUNK] * gain // 256).astype("<i2")
            pl.bars_take(np.repeat(chunk[:, None], 2, axis=1).tobytes(), n * SPL.CHUNK / RATE)
            n += 1
        for _ in range(int(then * RATE / SPL.CHUNK)):
            pl.bars_take(SPL.SILENCE, n * SPL.CHUNK / RATE)
            n += 1
        return [w["v"] for w in said if w.get("is") == "bars"]

    t = np.arange(int(0.5 * RATE)) / RATE
    low, high = [(np.sin(2 * np.pi * f * t) * 6000).astype(np.int64) for f in (60.0, 8000.0)]
    lo, hi = bars_of(low), bars_of(high)
    check(f"the sound as bars: said every twentieth of a second ({len(lo)} in half a second), thirty-two of them, "
          f"each 0 to 99; a low sound, the ones at the left ({lo[-1][:5]}... nothing from the tenth on: "
          f"{max(lo[-1][10:])}); a high one, the ones at the right ({hi[-1][26:]}, nothing in the first twenty: "
          f"{max(hi[-1][:20])})", 9 <= len(lo) <= 11 and all(len(v) == SPL.BARS == SQ.BARS == 32 for v in lo + hi)
          and all(type(n_) is int and 0 <= n_ <= 99 for v in lo + hi for n_ in v)
          and int(np.argmax(lo[-1])) <= 2 and max(lo[-1][:3]) >= 60 and max(lo[-1][10:]) == 0
          and int(np.argmax(hi[-1])) in (28, 29, 30) and max(hi[-1]) >= 60 and max(hi[-1][:20]) == 0)
    quiet, loud = bars_of(low, gain=77)[-1], bars_of(low, gain=256)[-1]
    top = bars_of((np.sin(2 * np.pi * 1000.0 * t) * 32767).astype(np.int64))[-1]
    faint = bars_of((np.sin(2 * np.pi * 1000.0 * t) * 30).astype(np.int64))
    check(f"...the same at any volume (at 30: {quiet[:4]}, at 100: {loud[:4]}); a sound as loud as can be, to the top "
          f"({max(top)}); one too faint to hear, nothing ({len(faint)} said)",
          max(abs(a - b_) for a, b_ in zip(quiet, loud)) <= 2 and max(top) == 99 and faint == [])
    after = bars_of(low, then=0.6)
    check(f"...silence after it: nothing, said once, and then no more (the tallest bar, each time it was said: "
          f"{[max(v) for v in after[-4:]]}; {len(after)} times in all, for 1.1 s)", after[-1] == [0] * 32
          and max(after[-2]) > 0 and after.count([0] * 32) == 1 and len(after) <= 13)
    SPL.say = real_say

    # the real player, and a pretend sound card
    p = Player()
    p.tell(do="load", sounds=[["hat", burst(S + "/files/hat.wav", secs=0.06, amp=16000, f=7000.0)]])
    p.tell(do="volume", v=100)
    p.tell(do="warm")
    until(lambda: p.got("ready", id="hat") and p.got("sound", ok=True), 5)
    p.tell(do="tone", id="Tones/Marimba")
    time.sleep(SPL.LEAD_SECS + 1.0)                    # (its sound card open a while, its sound made)
    p.tell(do="play", id="hat")
    time.sleep(0.5)
    unasked = len(p.got("bars"))
    p.tell(do="bars", on=True)
    mark = log_at()
    t0 = time.monotonic() + 0.4
    p.tell(do="loop", hits=[[0, "Tones/Marimba", 0, -1e9, 4, 0.8]], beats=4, bpm=120, b0=0.0, t0=t0, click=False)
    time.sleep(4.9)
    starts, periods = heard(mark)
    off = []
    for k in range(3):                                 # (each time round: where it starts, and that it's loud then)
        near = [h[0] for h in starts if abs(h[0] - (t0 + 2.0 * k)) < 0.05]
        loud = max((pk for w, pk, _ in periods if 0 <= w - (t0 + 2.0 * k) < 0.1), default=0)
        off.append(round((near[0] - (t0 + 2.0 * k)) * 1000, 1) if near and loud > 2000 else None)
    check(f"the real player, told a loop with one of its own sounds in it: heard each time round, on its beat "
          f"({off} ms from it)", all(o is not None and -1.0 <= o <= 5.0 for o in off))
    bars = [(at, m_["v"]) for at, m_ in p.said if m_.get("is") == "bars"]
    gaps = sorted(b_[0] - a[0] for a, b_ in zip(bars, bars[1:]))
    sums = np.sum([v for _, v in bars], axis=0) if bars else np.zeros(32)
    check(f"...nothing said of the sound's bars till they're asked for ({unasked}); asked: said as it plays, about "
          f"twenty times a second ({len(bars)} in 4.9 s, half of them {gaps[len(gaps) // 2] * 1000:.0f} ms apart or "
          f"less), the note's own bar the tallest (bar {int(np.argmax(sums))}: middle C)", unasked == 0
          and 40 <= len(bars) <= 100 and 0.035 <= gaps[len(gaps) // 2] <= 0.07 and 8 <= int(np.argmax(sums)) <= 11
          and all(len(v) == 32 for _, v in bars))
    p.tell(do="loop")
    time.sleep(2.2)
    n0 = len(p.got("bars"))
    last = p.got("bars")[-1]["v"]
    p.tell(do="play", id="hat")
    time.sleep(0.5)
    n1 = len(p.got("bars"))
    hat_bars = [m_["v"] for m_ in p.got("bars")[n0:n1]]
    p.tell(do="bars", on=False)
    time.sleep(0.2)
    n2 = len(p.got("bars"))
    p.tell(do="play", id="hat")
    time.sleep(0.5)
    check(f"...the loop gone and its sound over: nothing, said once ({last[:4]}...); a sound played then: its bars "
          f"({len(hat_bars)} said, the tallest bar {int(np.argmax(np.max(hat_bars, axis=0))) if hat_bars else None}: "
          f"a hat's, at the right), then nothing again; told to stop: no more of them, whatever plays "
          f"({len(p.got('bars')) - n2})", last == [0] * 32 and 2 <= len(hat_bars) <= 8
          and int(np.argmax(np.max(hat_bars, axis=0))) >= 26 and hat_bars[-1] == [0] * 32
          and len(p.got("bars")) == n2)
    peaks = []
    for c_ in ({"id": "hat"}, {"id": "hat", "gain": 0.5}, {"id": "hat", "gain": 7}, {"id": "hat", "gain": "x"},
               {"id": "Tones/Marimba", "gain": 0.8}, {"id": "Tones/Marimba", "gain": 0.4},
               {"id": "Tones/Marimba", "semis": 12, "gain": 0.4}):
        mark = log_at()
        p.tell(do="play", **c_)
        time.sleep(0.5)
        peaks.append(max((pk for _, pk, _ in heard(mark)[1]), default=0))
        p.tell(do="stop")
        time.sleep(0.3)
    check(f"a sound played as loud as it's told: as it is, and half; a loudness that isn't one: not played; one of "
          f"the player's own, half as loud again, and an octave up ({peaks} of 32767)",
          abs(peaks[1] / max(1, peaks[0]) - 0.5) < 0.03 and peaks[2:4] == [0, 0] and 9000 < peaks[4] < 12000
          and abs(peaks[5] / max(1, peaks[4]) - 0.5) < 0.05 and peaks[6] > 2000)
    p.tell(do="loop", hits=[[0, "Tones/Glass", 3, -1e9, 4, 0.8], [1, "nothing", 0, -1e9, 4, 0.8]], beats=4, bpm=120,
           b0=0.0, t0=time.monotonic(), click=False)
    time.sleep(0.6)
    check("...a loop with a sound of its own that isn't made yet, and one there isn't: it plays on (the first is "
          "made, and heard from then)", p.p.poll() is None)
    check("...and it goes when it's told to", p.quit() == 0)


# ---- in media mode ---------------------------------------------------------------------------------------------------
if not ONLY or "app" in ONLY:
    import pietato_all as g
    import pitato.beatlink as BL
    import pitato.fine as FINE
    import pitato.listen as L
    import pitato.bounce as BN
    import pitato.sequencer as SQ
    import pitato.soundboard as SB
    import pitato.screens.sequencer as SSQ
    HOME = S + "/home/u"
    os.makedirs(HOME, exist_ok=True)
    if os.path.exists(ALOG):
        os.remove(ALOG)
    g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/mcache"; g.PADS_FILE = S + "/pads.json"
    g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
    g.STATIC = S + "/static"
    os.makedirs(g.STATIC, exist_ok=True)
    json.dump({"settings": {"name": "Den"}}, open(g.STATE_FILE, "w"))
    g.home_dir = lambda: HOME
    AS = S + "/asound"
    os.makedirs(AS + "/card0/pcm0p")
    open(AS + "/cards", "w").write(" 0 [vc4hdmi0       ]: vc4-hdmi - vc4-hdmi-0\n                      vc4-hdmi-0\n")
    os.makedirs(S + "/v4l")
    L.ASOUND, L.V4L = AS, S + "/v4l"
    BL.BEAT_HOST, BL.BEAT_PORT = "127.0.0.3", 25472
    real_run = subprocess.run
    subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                           if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0]))
                                           in {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli",
                                               "vcgencmd"} else real_run(cmd, *a, **k))

    class FB:
        w, h = 640, 480
        real_w, real_h = 640, 480
        s = 1
        last = None
        frames = 0
        def show(self, img): FB.last = img.copy(); FB.frames += 1
        def show_part(self, img, box): self.show(img)
        def blank_outside(self, box): pass
        def invalidate(self): pass
        def close(self): pass

    g.Framebuffer = FB
    m = g.Media()
    m.enter()
    m.saves_peers = lambda addr=None: []
    toasts = []
    was_toast = m.toast
    m.toast = lambda text, secs=4: (toasts.append(text), was_toast(text, secs))[1]
    told = []
    was_tell = m.board_tell
    m.board_tell = lambda **c: (told.append((time.monotonic(), c)), was_tell(**c))[1]

    def flush():
        m.dirty = True
        m.flush()
        return np.asarray(FB.last.convert("RGB")).astype(int)

    def spin(secs=0.3, cond=None):
        end = time.monotonic() + secs
        while time.monotonic() < end:
            m.tick()
            if cond is not None and cond():
                return True
            time.sleep(0.005)
        return bool(cond()) if cond is not None else None

    def drawn(secs):
        """How many times the screen's drawn in so long, left to itself."""
        end, n0 = time.monotonic() + secs, FB.frames
        while time.monotonic() < end:
            m.tick()
            if m.dirty:
                m.flush()
            time.sleep(0.005)
        return FB.frames - n0

    def tap(name, repeat=False):
        m.press(name, repeat=repeat)
        m.release(name)
        spin(0.02)

    def said(do, since=0.0):
        return [c for at, c in told if c.get("do") == do and at >= since]

    def loops():
        return said("loop")

    def card(key):
        """START's card, that row picked."""
        if m.sim_opts is None:
            tap("start")
        m.sim_opts = [r[0] for r in m.board_rows()].index(key)

    def go(r, c):
        """The d-pad, to that cell."""
        while m.board.seq_at[0] != r:
            tap("down")
        while m.board.seq_at[1] != c:
            tap("right")

    apps = next(t_ for t_ in g.LIBRARY if t_["name"] == "Apps")
    ai = g.LIBRARY.index(apps)
    m.open_app(ai)
    m.sels[ai] = next(k for k, it in enumerate(m.tab_items()) if it["title"] == "Soundboard")
    m.press("a")
    spin(4, lambda: m.board is not None and len(m.board.ready) == 24 and m.board.sound_ok)
    b = m.board
    KICK, SNARE, HAT = SQ.DRUMS
    tap("start")
    rows = m.board_rows()
    m.sim_opts = [r[0] for r in rows].index("seq")
    hints = m.board_card_hints()
    t_open = time.monotonic()
    tap("a")
    spin(0.3)
    s = m.sim_game()
    where = []
    real_draw = s.draw
    s.draw = lambda img, x0, y0: (where.append((x0, y0)), real_draw(img, x0, y0))[1]
    want = SQ.born(SQ.seed_of("Den"))
    check(f"START's card has Sequencer, before Bounce ({[r[0] for r in rows[-2:]]}; its buttons: {hints}); A there: "
          f"its page, the card gone: a grid of four sounds ({s.seq and s.seq['rows']}) and sixteen steps, the tune "
          f"this Pietato's name gives it, not playing yet; its buttons along the bottom ({m.sim_hints(s)})",
          [r[:2] for r in rows[-2:]] == [("seq", "Sequencer"), ("bounce", "Bounce")] and ("A", "Open") in hints
          and b.seq_up and not b.seq_on and b.card is None and m.sim_opts is None and s.seq is not None
          and s.seq["grid"] == tuple(tuple(r) for r in want[0]) and b.seq == [want[0], want[1]]
          and SQ.dumps(*b.seq) == DEN and s.seq["rows"] == ["Kick", "Snare", "Hi-hat", "Pluck"]
          and s.seq["cursor"] == (0, 0) and not s.seq["playing"] and s.seq["colour"] == tuple(SSQ.ACCENT)
          and m.sim_hints(s) == [("A", "On/off"), ("B", "Play"), ("X", "Sound"), ("Y", "Mutate"), ("START", "More"),
                                 ("HOME", "Back")])
    check(f"...its player told to make the lead's sound ready and to say the sound as bars "
          f"({[c for c in said('tone', t_open) + said('bars', t_open)]}); no loop yet ({loops()[-1:]})",
          {"do": "tone", "id": "Tones/Pluck"} in said("tone", t_open) and said("bars", t_open) == [
              {"do": "bars", "on": True}] and loops()[-1] == {"do": "loop"} and all(d in b.ready for d in SQ.DRUMS))

    def look():
        """The page as it's drawn now: (the picture, which cells are lit, which columns are outlined, the bar's)."""
        page = flush()
        x0, y0 = where[-1]
        lay = SQ.layout((0, SB.TOP, s.w, s.h), s.w >= 960)
        cw = lay["cw"]
        lit = [[int(page[y0 + y + 4, x0 + x + cw // 2].sum()) > 300 for x in lay["xs"]] for y in lay["ys"]]
        heads = [c for c, x in enumerate(lay["xs"])
                 if all(page[y0 + y, x0 + x + cw // 2][0] > 215 for y in lay["ys"])]
        return page, lit, heads, lay

    page, lit, heads, lay = look()
    x0, y0 = where[-1]
    ring = page[y0 + lay["ys"][0] - 4, x0 + lay["xs"][0] + lay["cw"] // 2]
    other = page[y0 + lay["ys"][1] - 4, x0 + lay["xs"][5] + lay["cw"] // 2]
    bx0, by0, bx1, by1 = lay["bars"]
    box = page[y0 + by0 + 4:y0 + by1 - 12, x0 + bx0 + 4:x0 + bx1 - 4]
    still = drawn(0.8)
    check(f"its page, stopped: the cells that are on lit, the others dark, as the tune has them; no column outlined "
          f"({heads}); a ring round the cell ◀▶▲▼ are on ({ring.tolist()}, and none round another: {other.tolist()}); "
          f"no bars ({int((box.sum(axis=2) > 300).sum())} px lit in their box); and still: not drawn again, left to "
          f"itself ({still} times in 0.8 s)", lit == [list(r) for r in want[0]] and heads == []
          and int(ring.sum()) > 300 and int(other.sum()) < 150 and int((box.sum(axis=2) > 300).sum()) == 0
          and still <= 2)

    # A, X and the d-pad, stopped
    t1 = time.monotonic()
    tap("right")
    tap("a")
    on1, play1 = b.seq[0][0][1], said("play", t1)
    tap("a")
    check(f"▶, then A: the kick's second cell on, and heard at once as it is in the tune, stopped as it is "
          f"({play1}); A again: off, and nothing heard ({said('play', t1)})", on1
          and play1 == [{"do": "play", "id": KICK, "gain": SQ.GAINS[0]}]
          and not b.seq[0][0][1] and said("play", t1) == play1 and b.seq_at == (0, 1))
    tap("down"); tap("down"); tap("down")
    t1 = time.monotonic()
    tap("a")
    first = said("play", t1)
    tap("x")
    second = said("play", t1)[1:]
    names = m.sim_game().seq["names"]
    hint_x = m.sim_hints(m.sim_game())[2]
    for _ in range(SQ.NOTES - 1):
        tap("x")
    check(f"▼ to the lead's row, A: its cell on, heard at its note (the key's own: {first}); X: the next note of "
          f"the key up ({second}, {names[1]} on its cell; its button says so: {hint_x}); X as many times as there "
          f"are notes: round to where it began ({b.seq[1][1]})",
          b.seq_at == (3, 1) and b.seq[0][3][1]
          and first == [{"do": "play", "id": "Tones/Pluck", "gain": SQ.GAINS[3]}]
          and second == [{"do": "play", "id": "Tones/Pluck", "semis": 2, "gain": SQ.GAINS[3]}]
          and names[1] == "D" and names[0] == "C" and hint_x == ("X", "Note") and b.seq[1][1] == 0)
    tap("right"); tap("right"); tap("right")
    t1 = time.monotonic()
    was_note = b.seq[1][4]
    b.seq[0][3][4] = False
    tap("x")
    check(f"X on a lead cell that's off: on, at the note it had ({said('play', t1)})", b.seq_at == (3, 4)
          and b.seq[0][3][4] and b.seq[1][4] == was_note == 2
          and said("play", t1) == [{"do": "play", "id": "Tones/Pluck", "gain": SQ.GAINS[3], "semis": 4}])
    go(3, 0)
    tap("left")
    edge = b.seq_at
    tap("down")
    wrap = b.seq_at
    for _ in range(5):
        tap("right", repeat=True)
    check(f"◀ from the first step: the last; ▼ from the last row: the first ({edge}, {wrap}); held, on and on "
          f"({b.seq_at})", edge == (3, 15) and wrap == (0, 15) and b.seq_at == (0, 4))

    # its card: Clear it; a tap on a cell; B, and the tune heard on its beats
    card("clear")
    ask = m.board_card_hints()
    tap("a")
    cleared = not any(any(r) for r in b.seq[0])
    tap("start")
    check(f"START, its card; Clear it ({ask}): every cell off ({toasts[-1:]}), the lead's notes as they were, the "
          f"card still up till START", cleared and toasts[-1:] == ["Cleared"] and b.card is None
          and m.sim_opts is None and ("A", "Do it") in ask and len(b.seq[1]) == 16)
    flush()
    places = {w[1:]: box_ for box_, w in m.taps_now() if w[0] == "seq"}
    x0, y0 = where[-1]
    fit = all(places.get((r, c)) == (x0 + x, y0 + y, x0 + x + lay["cw"], y0 + y + lay["ch"])
              for r, y in enumerate(lay["ys"]) for c, x in enumerate(lay["xs"]))
    t1 = time.monotonic()
    pressed = []
    for c in (0, 4, 8, 12):
        keys = m.tap_do(("seq", 2, c))
        pressed.append(keys)
        for k in keys:
            tap(k)
    check(f"a tap on a cell (the web page's picture of this screen: {len(places)} places, each cell's own): moved to, "
          f"and A pressed ({pressed}): the hat on each beat, heard as each went on ({len(said('play', t1))} times)",
          len(places) == 64 and fit and pressed == [["a"]] * 4 and b.seq_at == (2, 12)
          and [k for k, on in enumerate(b.seq[0][2]) if on] == [0, 4, 8, 12]
          and said("play", t1) == [{"do": "play", "id": HAT, "gain": SQ.GAINS[2]}] * 4
          and m.tap_do(("seq", 9, 0)) == [] and m.tap_do(("seq", 0, 16)) == [] and m.tap_do(("seq", "x", 0)) == [])
    m.board_tempo(120)
    spin(1.0)
    t_play = time.monotonic()
    tap("b")
    spin(0.3)
    lp = loops()[-1]
    mark = log_at()
    spin(2.7)
    c = b.clock
    on = [t_ for t_, _ in heard(mark)[0]]
    beats = [c.beat(t_) for t_ in on]
    out = [round((t_ - c.at(round(c.beat(t_)))) * 1000, 1) for t_ in on]
    check(f"B: it plays. Its player told the loop: each cell that's on, at its beat of the bar, its row's sound, as "
          f"loud as its row is, from any beat ({lp.get('hits')}), at the Soundboard's tempo ({lp.get('bpm')})",
          b.seq_on and lp.get("hits") == [[float(k), HAT, 0, SSQ.SEQ_ALWAYS, 4.0, SQ.GAINS[2]] for k in range(4)]
          and lp.get("bpm") == 120 and lp.get("click") is False and len(said("loop", t_play)) == 1)
    check(f"...and heard: the hat on each beat, half a second apart ({out} ms from its beat)", len(on) >= 4
          and all(abs(x) <= 4 for x in out) and [round(b_) for b_ in beats] == list(
              range(round(beats[0]), round(beats[0]) + len(beats))))

    # its page, playing
    n = drawn(2.0)
    for _ in range(20):                                # (a picture with the bar well inside a step, to be sure which)
        if 0.02 < SQ.next_step_in((c.bpm, c.b0, c.t0), time.monotonic()) < 0.09:
            break
        spin(0.01)
    step = SQ.step_at((c.bpm, c.b0, c.t0), time.monotonic())
    page, lit, heads, lay = look()
    s = m.sim_game()
    check(f"its page as it plays: drawn frame by frame ({n} in 2 s: {n / 2:.0f} a second); the column the bar's on "
          f"outlined, and only that one ({heads}: step {step}); the cells lit as before; its button says Stop "
          f"({m.sim_hints(s)[1]}), its line that it's playing", 30 <= n <= 48 and heads == [step]
          and lit == [list(r) for r in b.seq[0]] and m.sim_hints(s)[1] == ("B", "Stop") and s.seq["playing"]
          and s.seq["bpm"] == 120 and s.seq["clock"] == (c.bpm, c.b0, c.t0))
    end, got = time.monotonic() + 2.0, False
    while time.monotonic() < end and not got:          # (till a hat's just been heard: its bars up)
        m.tick()
        if m.dirty:
            m.flush()
            got = max(s.seq_bars) > 0.3
        time.sleep(0.005)
    page = np.asarray(FB.last.convert("RGB")).astype(int)
    x0, y0 = where[-1]
    bx0, by0, bx1, by1 = lay["bars"]
    box = page[y0 + by0 + 4:y0 + by1 - 12, x0 + bx0 + 4:x0 + bx1 - 4]
    bright = box.sum(axis=2) > 300
    left, right = int(bright[:, :bright.shape[1] // 2].sum()), int(bright[:, bright.shape[1] // 2:].sum())
    fresh = b.bars is not None and time.monotonic() - b.bars[0] < 0.5
    check(f"...and the sound as bars under the grid, as its player says them ({len(b.bars[1]) if b.bars else 0} of "
          f"them): a hat's, at the right ({right} px lit there, {left} at the left)", got and fresh
          and len(b.bars[1]) == 32 and all(0.0 <= v <= 1.0 for v in b.bars[1]) and right > 300 and right > 4 * left)
    tap("b")
    falling = drawn(1.5)
    stopped = loops()[-1]
    idle = drawn(1.0)
    page, lit, heads, lay = look()
    box = page[y0 + by0 + 4:y0 + by1 - 12, x0 + bx0 + 4:x0 + bx1 - 4]
    check(f"B again: stopped. Nothing in the loop any more ({stopped}); the bars fall away "
          f"({falling} frames; then {max(m.sim_game().seq_bars):.3f}, {int((box.sum(axis=2) > 300).sum())} px), no "
          f"column's outlined ({heads}), and its page is still again ({idle} frames in a second); the tune kept",
          not b.seq_on and stopped == {"do": "loop"} and max(m.sim_game().seq_bars) < 0.02
          and int((box.sum(axis=2) > 300).sum()) == 0 and heads == [] and idle <= 2
          and m.setting("seq_tune") == SQ.dumps(*b.seq) and m.sim_hints(m.sim_game())[1] == ("B", "Play"))

    # the bars, as its player says them
    b.bars = None
    slow = m.seq_heard(b.proc, {"is": "bars", "v": [50] * 32})
    m.dirty, m.sim_next = False, time.monotonic() + 30
    m.board_said(b.proc, {"is": "bars", "v": [99] * 32 + [7]})
    woke = (m.dirty, m.sim_next, b.bars and b.bars[1])
    m.dirty = False
    quick = m.seq_heard(b.proc, {"is": "bars", "v": [33, 200, -4, "x", True] + [0] * 27})
    levels = b.bars[1]
    odd = (m.seq_heard(b.proc, {"is": "bars", "v": "loud"}), m.seq_heard(object(), {"is": "bars", "v": [9] * 32}))
    check(f"its player's bars, with its page still: media mode hears of the first (it's drawn from then: "
          f"{woke[0]}, {woke[1]}), thirty-two of them, each 0 to 1; the ones after are only kept for the next frame "
          f"({quick}, {m.dirty}; a level that isn't one: 0 to 1 even so, {levels[:5]}); nonsense, or another "
          f"player's: not kept ({odd}, {b.bars[1][:2]})", slow is False and woke[0] is True and woke[1] == 0.0
          and woke[2] == [1.0] * 32 and quick is True and m.dirty is False
          and levels == [33 / 99.0, 1.0, 0.0, 0.0, 0.0] + [0.0] * 27 and odd == (False, True)
          and b.bars[1] == levels)
    drawn(1.5)

    # X on a drum's row: its sound; one that's on no button
    go(2, 12)
    choices = m.seq_choices()
    t1 = time.monotonic()
    tap("x")
    new = m.seq_sounds()[2]
    name = m.sim_game().seq["rows"][2]
    check(f"X on a drum's row: its next sound, of the Soundboard's ({len(choices)} to go through: the three it "
          f"starts with, then every button's), said ({toasts[-1:]}), on its row ({name}) and heard",
          choices[:3] == list(SQ.DRUMS) and len(choices) >= 20 and new == choices[3] and toasts[-1:] == [name]
          and name == SSQ.B.title(new) and said("play", t1) == [{"do": "play", "id": new, "gain": SQ.GAINS[2]}]
          and m.setting("seq_sounds").split("|")[2] == new and m.sim_hints(m.sim_game())[2] == ("X", "Sound"))
    m.seq_set_sound(2, HAT)
    pads_was = [dict(bank["pads"]) for bank in b.banks]
    for bank in b.banks:
        for pad, sid in list(bank["pads"].items()):
            if sid == HAT:
                del bank["pads"][pad]
    t1 = time.monotonic()
    m.board_load()
    load = said("load", t1)[-1]["sounds"] if said("load", t1) else []
    for bank, was in zip(b.banks, pads_was):
        bank["pads"] = was
    m.board_load()
    check(f"a row's sound that's on no button: its player's told to have it all the same, first "
          f"({[x[0] for x in load[:2]]})", bool(load) and load[0][0] == HAT and os.path.isfile(load[0][1])
          and m.seq_extra() == list(SQ.DRUMS))
    mine = os.path.join(HOME, SSQ.B.FOLDER, "Clap.wav")
    burst(mine, secs=0.05, amp=15000, f=2500.0)
    seen = spin(4.0, lambda: "Clap.wav" in b.ready)
    m.seq_set_sound(1, "Clap.wav")
    tap("b")
    spin(0.2)
    b.seq[0][1][4] = True
    m.seq_changed()
    with_it = (m.seq_sounds()[1], m.sim_game().seq["rows"][1], [h[1] for h in loops()[-1]["hits"] if h[0] == 1.0])
    os.remove(mine)
    gone = spin(4.0, lambda: m.seq_sounds()[1] == SNARE)
    after_it = (m.sim_game().seq["rows"][1], [h[1] for h in loops()[-1]["hits"] if h[0] == 1.0])
    tap("b")
    b.seq[0][1][4] = False
    m.seq_changed()
    check(f"one of your own sounds as a row's ({with_it}); its file taken away: the row's back to the sound it "
          f"starts with, in the loop too ({after_it})", seen and with_it == ("Clap.wav", "Clap", ["Clap.wav", HAT])
          and gone and after_it == ("Snare", [SNARE, HAT]))

    # Y, a new tune, and taking them back
    card("new")
    m.seq_rng = random.Random(11)
    tap("a")
    made = SQ.born(random.Random(11).getrandbits(32))
    new_ok = b.seq == [made[0], made[1]] and toasts[-1:] == ["A new tune"]
    tap("start")
    before = SQ.dumps(*b.seq)
    m.seq_rng = random.Random(3)
    tap("y")
    after = SQ.dumps(*b.seq)
    diff = sum(a != b_ for a, b_ in zip(before, after))
    card("back")
    tap("a")
    took = (SQ.dumps(*b.seq), toasts[-1])
    tap("a")
    check(f"its card's A new tune: one made afresh; Y: a little of it changed ({diff} of its cells and notes); its "
          f"card's Take back the last change: as it was before Y ({took[1]}); again: nothing to take back "
          f"({toasts[-1]})", new_ok and 1 <= diff <= 12 and after == SQ.dumps(*SQ.mutated(*made, random.Random(3)))
          and took == (before, "Back as it was") and toasts[-1] == "Nothing to take back"
          and SQ.dumps(*b.seq) == before)
    tap("start")

    # L and R, SELECT, its card, while it plays
    tap("b")
    spin(0.3)
    t1 = time.monotonic()
    tap("r")
    up = (m.setting("board_bpm"), round(b.clock.bpm), loops()[-1].get("bpm"))
    for _ in range(3):
        tap("l", repeat=True)
    down = (m.setting("board_bpm"), round(b.clock.bpm), loops()[-1].get("bpm"))
    check(f"L and R, as it plays: the Soundboard's tempo, two beats a minute at a time, the loop told from the beat "
          f"it's at ({up}, then held: {down})", up == ("122", 122, 122) and down == ("116", 116, 116)
          and len(said("loop", t1)) == 4)
    lead_at = 5                                        # (a lead cell at the scale's third note, to hear it change)
    b.seq[0][3][lead_at], b.seq[1][lead_at] = True, 2
    m.seq_changed()

    def lead_semis():
        return next(h[2] for h in loops()[-1]["hits"] if h[1].startswith("Tones/") and h[0] == lead_at * 0.25)

    was_semis = lead_semis()
    tap("select")
    scale = m.setting("bounce_scale")
    check(f"SELECT: the next scale, Bounce's too ({scale}): the lead's notes are that scale's from the next time "
          f"round ({was_semis} semitones, now {lead_semis()}), its cells say which "
          f"({m.sim_game().seq['names'][lead_at]})", scale == "Blues" and was_semis == 4 and lead_semis() == 5
          and m.sim_game().seq["names"][lead_at] == "F" and m.sim_game().seq["scale"] == "Blues")
    tap("start")
    rows = m.board_rows()
    hints = m.sim_hints(m.sim_game())
    quiet = drawn(0.8)
    check(f"START: its card ({[r[0] for r in rows]}; its buttons: {hints}), the tune playing on behind it (its page "
          f"not drawn frame by frame meanwhile: {quiet} frames)", b.card == "seq" and m.sim_opts == 0 and b.seq_on
          and [r[0] for r in rows] == ["tempo", "volume", "key", "scale", "lead", "new", "clear", "back", "leave"]
          and hints == [("▲▼", "Choose"), ("◀▶", "Change"), ("START", "Play on")] and quiet <= 3
          and loops()[-1].get("hits") and rows[0][2] == "116 BPM" and rows[3][2] == "Blues")
    vol = m.volume
    tap("right")
    tap("down")
    tap("left")
    tap("down")
    tap("right")
    tap("down")
    tap("left")
    tap("down")
    t1 = time.monotonic()
    tap("right")
    rows = {k: v for k, _, v in m.board_rows()}
    lead_id = next(h[1] for h in loops()[-1]["hits"] if h[1].startswith("Tones/"))
    check(f"...◀▶ there: the tempo a beat at a time, the volume, the key, the scale, the lead's sound ({rows}): told "
          f"its player ({said('tone', t1)}), and the loop's lead is that one now ({lead_id}, in C# from "
          f"{lead_semis()} semitones)", rows["tempo"] == "117 BPM" and rows["volume"] == str(vol - 5)
          and m.volume == vol - 5 and rows["key"] == "C#" and rows["scale"] == "Pentatonic" and rows["lead"] == "Pad"
          and said("tone", t1) == [{"do": "tone", "id": "Tones/Pad"}] and lead_id == "Tones/Pad"
          and lead_semis() == 5 and m.setting("bounce_key") == "C#" and m.sim_game().seq["rows"][3] == "Pad"
          and loops()[-1]["bpm"] == 117)
    m.sim_opts = [r[0] for r in m.board_rows()].index("leave")
    leave_hints = m.board_card_hints()
    tap("start")
    going = drawn(1.0)
    check(f"...START again: on with it, drawn frame by frame again ({going} in a second); its last row's button: "
          f"{leave_hints[1]}", b.card is None and m.sim_opts is None and b.seq_up and going >= 14
          and leave_hints[1] == ("A", "Leave"))

    # HOME: the Soundboard's buttons, over it
    t1 = time.monotonic()
    tune = SQ.dumps(*b.seq)
    home = m.sim_home()
    spin(0.3)
    s = m.sim_game()
    lp = dict(s.loop or {})
    for _ in range(len(b.banks)):                      # (the Starter bank: a sound on every button)
        if b.bank()["name"] != "Starter":
            tap("r")
    tap("up")
    over = spin(1.0, lambda: b.bank()["pads"].get("up") in b.playing)
    check(f"HOME: the Soundboard's buttons again, the tune still playing under them (its loop still told: "
          f"{len(loops()[-1].get('hits') or [])} cells; no more bars asked for: {said('bars', t1)}); its line says "
          f"so ({lp}); a button's sound over it; the tune kept",
          home is True and not b.seq_up and b.seq_on and s.seq is None and m.board_shown()
          and said("bars", t1) == [{"do": "bars", "on": False}] and bool(loops()[-1].get("hits"))
          and lp.get("seq") is True and lp.get("layers") == 0 and lp.get("bars") == 1 and lp.get("rec") is False
          and m.sim_hints(s)[-3:] == [("SELECT", "Record a loop"), ("START", "More"), ("HOME", "Back")] and over
          and m.setting("seq_tune") == tune)
    tap("select")
    c = b.clock
    spin(0.2)
    tap("up")
    spin(0.3)
    tap("select")
    both = loops()[-1]
    check(f"...a loop recorded over it: its layer and the tune's cells, one loop ({len(both.get('hits') or [])} "
          f"sounds in it)", len(b.layers) == 1 and len(both["hits"]) == 1 + sum(sum(r) for r in b.seq[0])
          and sorted({h[4] for h in both["hits"]}) == [4.0, 8])
    m.press("start")
    spin(0.8)
    m.release("start")
    spin(0.1)
    check(f"START held there: the loop cleared and the tune stopped ({toasts[-1:]}, {loops()[-1]}), its cells as "
          f"they were", toasts[-1:] == ["Loop cleared"] and not b.seq_on and not b.layers and loops()[-1] == {
              "do": "loop"} and SQ.dumps(*b.seq) == tune and m.sim_game().loop is None)

    # Bounce with it
    card("seq")
    tap("a")
    tap("b")
    spin(0.2)
    up_again = b.seq_up and b.seq_on and m.sim_game().seq is not None
    why = m.bounce_web({"on": True})
    spin(0.3)
    s = m.sim_game()
    check(f"the Sequencer opened again and played (B); Bounce started from the web page meanwhile: Bounce's page, "
          f"the tune playing on with it ({why})", up_again and why is None and b.bounce is not None and not b.seq_up
          and b.seq_on and s.bounce is not None and s.seq is None and bool(loops()[-1].get("hits")))
    home = m.sim_home()
    card("seq")
    tap("a")
    check("...HOME leaves Bounce; START's card, Sequencer: its page again, still playing", home is True
          and b.bounce is None and b.seq_up and b.seq_on and m.sim_game().seq is not None
          and m.sim_game().seq["playing"])

    # the Soundboard left with it up, and opened again
    proc = b.proc
    m.go_home()
    spin(0.5)
    gone = b.proc is None and until(lambda: proc.poll() is not None, 5)
    kept = m.setting("seq_tune")
    t1 = time.monotonic()
    m.open_app(ai)
    m.sels[ai] = next(k for k, it in enumerate(m.tab_items()) if it["title"] == "Soundboard")
    m.press("a")
    spin(4, lambda: m.board.proc is not None and len(m.board.ready) >= 24 and m.board.sound_ok)
    spin(0.3)
    check(f"the Soundboard left with it up and playing: its player gone, the tune kept ({kept == tune}); opened "
          f"again: its page as it was, playing: its new player told the lead's sound, the bars and the loop "
          f"({[c['do'] for c in said('tone', t1) + said('bars', t1)]}, {len(loops()[-1].get('hits') or [])} cells)",
          gone and kept == tune and b.proc is not None and b.proc is not proc and b.seq_up and b.seq_on
          and m.sim_game().seq is not None and {"do": "tone", "id": "Tones/Pad"} in said("tone", t1)
          and {"do": "bars", "on": True} in said("bars", t1) and bool(loops()[-1].get("hits")))
    tap("b")

    # the tune, kept
    b.seq = b.seq_was = None
    back = SQ.dumps(*m.seq_tune())
    m.set_setting("seq_tune", "nonsense")
    b.seq = None
    born = SQ.dumps(*m.seq_tune())
    m.set_setting("seq_sounds", "Nope/Gone.wav|" + SNARE + "|Tones/Bell|" + KICK)
    odd = m.seq_sounds()
    m.set_setting("seq_sounds", KICK + "|" + SNARE + "|" + HAT + "|Tones/Glass")
    check(f"the next time (its tune read from the settings): the one that was kept; a line there that isn't a tune: "
          f"the one this Pietato's name gives it; a row's sound that's gone, or isn't one of its kind: the one it "
          f"starts with ({odd}); the lead's, kept ({m.seq_sounds()[3]})", back == tune and born == DEN
          and odd == [KICK, SNARE, HAT, "Tones/Pluck"] and m.seq_sounds() == [KICK, SNARE, HAT, "Tones/Glass"])

    # a bigger screen, and drawn finely
    for _ in range(40):                                # (its last sound gone, its bars down: a page that's still)
        if drawn(0.25) == 0 and max(m.sim_game().seq_bars) < 0.02:
            break
    FB.w, FB.h, FB.real_w, FB.real_h = 960, 540, 960, 540
    m.fb = FB()
    m.forget_drawn()
    page, lit, heads, lay = look()
    x0, y0 = where[-1]
    s = m.sim_game()
    check(f"a bigger screen: its cells bigger ({lay['cw']} by {lay['ch']}), lit as the tune has them, all of it "
          f"between the bars ({page.shape[1]} by {page.shape[0]})", page.shape[:2] == (540, 960) and lay["cw"] >= 40
          and lit == [list(r) for r in b.seq[0]] and x0 + lay["xs"][-1] + lay["cw"] <= 960
          and y0 + lay["bars"][3] <= 540 - 40)
    FB.w, FB.h, FB.real_w, FB.real_h = 640, 480, 640, 480
    m.fb = FB()
    m.forget_drawn()
    plain, _, _, lay = look()
    FB.s = 2                                           # (a screen with pixels for it: drawn twice as finely)
    m.fine_scale()
    fine = flush()
    pic = FB.last
    x0, y0 = where[-1]
    cells = (slice(y0 + lay["ys"][0], y0 + lay["ys"][-1] + lay["ch"]), slice(x0 + lay["xs"][0], x0 + lay["xs"][-1]))
    tap("b")
    playing = flush()
    tap("b")
    check(f"drawn finely (twice the pixels each way: {getattr(getattr(pic, 'pic', pic), 'size', None)}): the same "
          f"page (its usual-size copy {np.abs(fine - plain).mean():.2f} levels from the plain one, on average; its "
          f"cells {np.abs(fine[cells] - plain[cells]).mean():.2f}), playing too", FINE.detail(pic) == 2
          and pic.pic.size == (1280, 960) and np.abs(fine - plain).mean() < 3.0
          and np.abs(fine[cells] - plain[cells]).mean() < 3.0 and playing.shape == plain.shape)
    FB.s = 1
    m.fine_scale()
    flush()
    home = m.sim_home()
    check("HOME, and HOME again: back to Apps, the Soundboard picked", home is True and m.sim_home() is True
          and m.tab == ai and m.view == "list" and m.tab_items()[m.sels[ai]]["title"] == "Soundboard")
    m.press("b")
    spin(0.2)
    m.leave()

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
