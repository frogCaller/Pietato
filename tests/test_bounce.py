"""The Soundboard's Bounce (pitato/bounce.py, screens/bounce.py, soundplay.py). The shape and its balls on their own:
each shape, turning slowly or as fast as it goes either way, eight balls going as fast as they go, for a minute: every
ball inside it all the while, every wall hit, and no wall heard twice at once from one ball; how straight on each hit
was, and where; its walls' notes, a scale's from its key up; a sound's own note found (and none in a drum's). Its
picture: the walls one outline, as thick all the way round, pointed at its corners (no dot there), a wall that's hit
brighter and no bigger. Its
player, against a pretend sound card: its own sounds, at middle C; a note heard when it's told, exactly; only a few
at a time, each no longer than it should be; from the left or the right; its echo, at its distance, from side to
side, and none with it off; its space, dying away; its tone; its drone; the Soundboard's own sounds in a space too;
all of it stopped at once; and next to no work with nothing playing. Then in media mode: L from the Soundboard's
buttons, its page (no row for it on START's card now); its balls moving and their notes played as they hit, each
wall's its own, BOUNCE_LATE after, louder straight on, from the side they hit; its effects told its player; A and B;
its sliders (▲▼ pick one, ◀▶ move it); X its next sound, Y its next scale, SELECT its next key, each said (and the
balls not shaken); START, its card (paused: nothing moves, nothing's drawn); its shape, sound, key, scale and snapping
there (snapped: each note on an eighth of the Soundboard's tempo), and no row to leave it by; drawn frame by frame
while it plays, and the page as it is, all in
the accent colour; R on to the Soundboard's buttons, L back; HOME: out to Apps at once, and its page again when the
Soundboard's opened."""
import json, math, os, random, shutil, subprocess, sys, threading, time, wave
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
sys.path.insert(0, ROOT)
import numpy as np

S = SP + "/t_bounce"
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


# a pretend aplay: reads the sound a period at a time and puts it in a buffer as long as --buffer-time says once
# there's room for it, as aplay and ALSA do (the period it's read waits with it), and plays it at the sound card's
# rate; logs each period as it goes in (when, where in the stream, how loud, where its first sound is; and how loud
# on the left and on the right) and when it starts playing (each frame's heard at that start, and a frame's time after
# for each frame)
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
    log.write(f"# lr {written} {int(np.abs(x[:, 0]).max())} {int(np.abs(x[:, 1]).max())}\\n")
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


def lr_heard(since=0):
    """How loud each period was on the left and on the right, after that line of the log: [(when it's heard, left,
    right)]."""
    start = offset = None
    out = []
    for k, ln in enumerate(open(ALOG).read().splitlines()):
        if ln.startswith("# start"):
            start, offset = float(ln.split()[2]), int(ln.split()[4])
        elif ln.startswith("# lr ") and start is not None and k >= since:
            _, _, at, left, right = ln.split()
            out.append((start + (int(at) - offset) / RATE, int(left), int(right)))
    return out


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


def spread(xs):
    return max(xs) - min(xs) if xs else 0.0


# ---- the shape and its balls, on their own --------------------------------------------------------------------------
if not ONLY or "world" in ONLY:
    import pitato.bounce as BN
    rows, doubles, strengths, wide = [], 0, [], []
    for name, sides in BN.SHAPES:
        for spin in (-BN.SPIN_MOST, 0.3, BN.SPIN_MOST):
            w = BN.World(sides, spin, BN.SPEEDS[1], random.Random(7))
            while w.add():
                pass
            hits, out = [], 0
            for _ in range(1200):
                hits += w.step(0.05)
                out += not w.inside()
            per = [sum(1 for h in hits if h[0] == k) for k in range(sides)]
            last = {}
            for k, t, ball, hard, x in hits:
                if (ball, k) in last and t - last[(ball, k)] < BN.AGAIN - 1e-9:
                    doubles += 1
                last[(ball, k)] = t
                strengths.append(hard)
                wide.append(x)
            rows.append((name, spin, len(w.balls), out, min(per)))
    check(f"each shape, turning slowly or as fast as it goes either way, eight balls as fast as they go, for a minute: "
          f"every ball inside it all the while, every wall hit, no wall heard twice at once from one ball "
          f"(shape, spin, balls, frames with one outside, fewest hits on a wall: {rows}; twice at once: {doubles})",
          all(r[2] == BN.BALLS_MOST and r[3] == 0 and r[4] > 20 for r in rows) and doubles == 0)
    check(f"...each hit, how straight on (0 to 1: {min(strengths):.2f} to {max(strengths):.2f}, half of them "
          f"{sorted(strengths)[len(strengths) // 2]:.2f} or more) and where across ({min(wide):+.2f} to "
          f"{max(wide):+.2f})",
          0.0 <= min(strengths) < 0.3 and max(strengths) == 1.0 and 0.3 < sorted(strengths)[len(strengths) // 2] < 0.95
          and -1.0 <= min(wide) < -0.8 and 0.8 < max(wide) <= 1.0)
    notes = ([BN.wall_note(k, "C", "Pentatonic") for k in range(6)], [BN.wall_note(k, "A", "Minor") for k in range(7)],
             [BN.wall_note(k, "E", "Blues") for k in range(6)])
    check(f"its walls' notes: the scale's, from its key up, round the shape ({notes})",
          notes == ([60, 62, 64, 67, 69, 72], [57, 59, 60, 62, 64, 65, 67], [64, 67, 69, 70, 71, 74]))
    semis = (BN.note_semis(60, 60, "C"), BN.note_semis(57, 60, "A"), BN.note_semis(60, 57.2, "C"),
             BN.note_semis(60, 69.0, "C"), BN.note_semis(66, None, "D"))
    check(f"...from a sound's own note to a wall's: its own sounds (middle C) to the key; one of yours (A, a little "
          f"sharp; A above middle C) to the key's notes nearest it; a drum, the scale from wherever it is ({semis})",
          [round(x, 3) for x in semis] == [0.0, -3.0, 2.8, 3.0, 4.0])
    sys.path.insert(0, ROOT + "/pitato")
    import soundplay as SPL
    t = np.arange(int(0.8 * RATE)) / RATE
    harm = ((np.sin(2 * np.pi * 220 * t) + 0.4 * np.sin(4 * np.pi * 220 * t)) * np.exp(-t / 0.4) * 15000
            ).astype(np.int16)
    found = ([SPL.pitch_of(SPL.make_tone(sid)) for sid in SPL.TONES], SPL.pitch_of(harm),
             SPL.pitch_of((np.random.default_rng(3).standard_normal(20000) * 9000).astype(np.int16)))
    check(f"a sound's own note: its own sounds' (middle C, 60), an A below it (57), and none in a noise ({found})",
          all(abs(x - 60) < 0.3 for x in found[0]) and abs(found[1] - 57) < 0.1 and found[2] is None)

    # its picture: the walls one outline, nothing at the corners, a wall that's hit brighter and no bigger
    from PIL import Image, ImageDraw
    from pitato.theme import BG, co_mix
    INK, SIDE = (86, 156, 214), 400
    R = SIDE / 2 - 12                                  # (its corners, from its middle: as bounce.draw has them)
    THICK = getattr(BN, "WALL", (5, 8))[0]             # (px: its walls, on a screen this size)

    def picture(sides, turned, lit, now=100.0):
        """(its pixels; which are its walls'; each pixel's place from its middle, x and y up; its walls' ways out)."""
        w = BN.World(sides)
        w.angle = turned
        im = Image.new("RGB", (SIDE, SIDE), BG)
        BN.draw(ImageDraw.Draw(im), (0, 0, SIDE, SIDE), {"corners": w.corners(), "lit": lit, "colour": INK,
                                                         "balls": [(0.0, 0.0)], "paused": False}, {}, now)
        a = np.asarray(im).astype(int)
        yy, xx = np.mgrid[0:SIDE, 0:SIDE]
        x, y = xx - SIDE / 2, SIDE / 2 - yy
        walls = (np.abs(a - np.array(BG)).max(axis=2) > 0) & (np.hypot(x, y) > 60)   # (not the ball in its middle)
        return a, walls, x, y, w

    bands, tips, areas = [], [], []
    for name, sides in BN.SHAPES:
        a, walls, x, y, w = picture(sides, 0.35, [0.0] * sides)
        across = np.max([x * ux + y * uy for ux, uy in w.walls()], axis=0)   # (how far out, across the nearest wall)
        bands.append(float(np.abs(across[walls] - R * math.cos(math.pi / sides)).max()))
        tip = R + THICK / 2 / math.cos(math.pi / sides)    # (where two walls' outer edges meet: its corner's point)
        tips.append(max(abs(float((x * cx + y * cy)[walls].max()) - tip) for cx, cy in w.corners()))
        areas.append(int(walls.sum()) / (sides * 2 * R * math.sin(math.pi / sides) * THICK))
    check(f"its picture, each shape: its walls one outline, as thick all the way round ({THICK} px: no pixel more than "
          f"{max(bands):.1f} px from a wall's middle line; {min(areas):.2f} to {max(areas):.2f} of the pixels that "
          f"makes), and pointed at each corner (the outline ends within {max(tips):.1f} px of where two walls' outer "
          f"edges meet: no dot there, and no notch)", max(bands) <= THICK / 2 + 2.0 and max(tips) <= 1.8
          and all(0.9 <= v <= 1.15 for v in areas))   # (a pixel or two either way: how a slanting edge is drawn)
    a0, plain, x, y, w = picture(6, 0.2, [0.0] * 6)
    a1, hit, _, _, _ = picture(6, 0.2, [0.0, 100.0, 0.0, 0.0, 0.0, 0.0])
    dim = np.array(co_mix(BG, INK, BN.DIM))
    outs = np.array([x * ux + y * uy for ux, uy in w.walls()])
    nearest = outs.argmax(axis=0)
    clear = np.sort(outs, axis=0)[-1] - np.sort(outs, axis=0)[-2] > 2.0     # (not on the line between two walls)
    bright = (np.abs(a1 - np.array(INK)).max(axis=2) == 0) & hit
    check(f"...a wall that's hit: brighter from corner to corner (the accent itself, {int(bright.sum())} px, all of "
          f"them that wall's), the others as they were, and nothing bigger: the very same pixels are drawn "
          f"({int((plain != hit).sum())} differ), so nothing shows at its two ends",
          bool((plain == hit).all()) and 0.85 <= int(bright.sum()) / (2 * R * math.sin(math.pi / 6) * THICK) <= 1.15
          and bool((nearest[bright & clear] == 1).all()) and bool((bright | ~clear)[hit & (nearest == 1)].all())
          and bool((np.abs(a1 - dim).max(axis=2) == 0)[hit & clear & (nearest != 1)].all())
          and bool((np.abs(a0 - dim).max(axis=2) == 0)[plain].all()))
    half = picture(6, 0.2, [0.0, 100.0, 0.0, 0.0, 0.0, 0.0], now=100.0 + BN.LIT / 2)[0]
    over = picture(6, 0.2, [0.0, 100.0, 0.0, 0.0, 0.0, 0.0], now=100.0 + BN.LIT + 0.01)[0]
    spot = hit & clear & (nearest == 1)
    fade = half[spot].mean(axis=0)
    check(f"...dying away: half-way, between the two ({[round(float(v)) for v in fade]}); after {BN.LIT} s, as dim as "
          f"the rest", all(min(d, i) < v < max(d, i) for v, d, i in zip(fade, dim, INK) if d != i)
          and bool((np.abs(over - dim).max(axis=2) == 0)[plain].all()))


# ---- its player --------------------------------------------------------------------------------------------------
if not ONLY or "player" in ONLY:
    sys.path.insert(0, ROOT + "/pitato")
    import soundplay as SPL
    KICK = burst(S + "/files/kick.wav")
    t = np.arange(int(1.0 * RATE)) / RATE
    TONE = wav(S + "/files/tone.wav", np.sin(2 * np.pi * 440 * t) * 6000 * np.minimum(1.0, (1.0 - t) * 50))
    LOW, HIGH = burst(S + "/files/low.wav", 0.3, 9000, 200.0), burst(S + "/files/high.wav", 0.3, 9000, 6000.0)
    p = Player()
    p.tell(do="load", sounds=[["kick", KICK], ["tone", TONE], ["low", LOW], ["high", HIGH]])
    p.tell(do="volume", v=100)
    p.tell(do="warm")
    until(lambda: all(p.got("ready", id=s) for s in ("kick", "tone", "low", "high")) and p.got("sound", ok=True), 5)
    time.sleep(0.6)
    for sid in list(SPL.TONES) + ["tone", "kick"]:
        p.tell(do="pitch", id=sid)
    until(lambda: len(p.got("pitch")) >= len(SPL.TONES) + 2, 5)
    said = {m["id"]: m["midi"] for m in p.got("pitch")}
    check(f"asked a sound's own note: its own sounds at middle C, the A above it, none in a drum ({said})",
          all(abs(said.get(s, 0) - 60) < 0.3 for s in SPL.TONES) and abs(said.get("tone", 0) - 69) < 0.1
          and said.get("kick", 1) is None)
    time.sleep(SPL.LEAD_SECS + 0.5)                    # (working those out kept it busy, and the sound card waited:
                                                       #  when it hears what it's sent, worked out again since)
    mark = log_at()
    t0 = time.monotonic() + 0.3
    for k in range(5):
        p.tell(do="note", id="kick", semis=0, gain=1.0, at=t0 + 0.25 * k)
    time.sleep(1.8)
    hits, _ = heard(mark)
    off = [(h[0] - (t0 + 0.25 * k)) * 1000 for k, h in enumerate(hits)]
    check(f"a note heard when it's told: each at its very moment ({[round(o, 1) for o in off]} ms)",
          len(hits) == 5 and all(abs(o) <= 4.0 for o in off) and spread(off) <= 1.5)
    mark = log_at()
    p.tell(do="note", id="kick", semis=0, gain=1.0, at=time.monotonic() - 1.0)
    time.sleep(0.5)
    late = heard(mark)[0]
    check(f"...one whose moment's gone by: at once ({len(late)})", len(late) == 1)

    def peak_of(n, sid="tone", gain=0.12, semis=0.0):
        mark = log_at()
        at = time.monotonic() + 0.3
        for _ in range(n):
            p.tell(do="note", id=sid, semis=semis, gain=gain, at=at)
        time.sleep(1.4)
        return max((pk for _, pk, _ in heard(mark)[1]), default=0)

    one, ten = peak_of(1), peak_of(10)
    check(f"only a few at a time: ten told at once, as loud as {SPL.BOUNCE_MOST} ({ten} against one's {one})",
          abs(ten / max(1, one) - SPL.BOUNCE_MOST) < 0.6)
    mark = log_at()
    p.tell(do="note", id="tone", semis=-24.0, gain=1.0, at=time.monotonic() + 0.3)
    time.sleep(3.4)
    loud = [w for w, pk, _ in heard(mark)[1] if pk > 300]
    span = loud[-1] - loud[0] if loud else 0
    check(f"...each no longer than it should be: a sound two octaves down (4 s of it) cut at {SPL.BOUNCE_SECS} s "
          f"({span:.2f} s)", abs(span - SPL.BOUNCE_SECS) < 0.08)

    def lr(pan=None):
        """A kick from that side: how loud it was on the left and on the right."""
        mark = log_at()
        p.tell(**dict(do="note", id="kick", semis=0, gain=1.0, at=time.monotonic() + 0.2,
                      **({} if pan is None else {"pan": pan})))
        time.sleep(0.6)
        got = lr_heard(mark)
        return max((x[1] for x in got), default=0), max((x[2] for x in got), default=0)

    middle, left, right = lr(), lr(-0.8), lr(0.8)
    check(f"a note from the left, from the right, from the middle: louder that side, as loud as ever there (left, "
          f"right: {left}, {right}, {middle})", middle[0] == middle[1] > 15000 and left[0] == middle[0]
          and right[1] == middle[1] and left[1] < 0.3 * left[0] and right[0] < 0.3 * right[1])
    p.tell(do="fx", space=0, echo=0.6, tone=0.5, secs=0.3)
    mark = log_at()
    t1 = time.monotonic() + 0.3
    p.tell(do="note", id="kick", semis=0, gain=1.0, at=t1)
    time.sleep(1.6)
    hits, periods = heard(mark)
    when = [round((h[0] - t1) * 1000) for h in hits]
    loudest = [max((pk for w, pk, _ in periods if h[0] - 0.01 <= w <= h[0] + 0.045), default=0) for h in hits]
    lr_at = [max(((l_, r_) for w, l_, r_ in lr_heard(mark) if h[0] - 0.01 <= w <= h[0] + 0.03),
                 key=lambda x: x[0] + x[1], default=(0, 0)) for h in hits]
    check(f"its echo: the note, then again every 0.3 s, each quieter than the one before ({when} ms, as loud as "
          f"{loudest}), from one side, then the other ({lr_at[1:4]})", len(hits) >= 4 and abs(when[0]) <= 3
          and all(abs(w - 300 * k) <= 3 for k, w in enumerate(when[:4]))
          and all(b < a for a, b in zip(loudest[:4], loudest[1:4]))
          and lr_at[1][0] > 2 * lr_at[1][1] and lr_at[2][1] > 2 * lr_at[2][0] and lr_at[3][0] > 2 * lr_at[3][1])
    p.tell(do="fx", space=0, echo=0, tone=0.5)
    time.sleep(3.5)
    mark = log_at()
    p.tell(do="note", id="kick", semis=0, gain=1.0, at=time.monotonic() + 0.3)
    time.sleep(1.0)
    check(f"...and none with it off ({len(heard(mark)[0])})", len(heard(mark)[0]) == 1)

    def after(sid="kick", play=False, secs=2.5, **c):
        """A sound, then this long: how loud each period was, from when it was heard."""
        mark = log_at()
        t = time.monotonic() + (0.0 if play else 0.2)
        p.tell(**(dict(do="play", id=sid) if play else dict(do="note", id=sid, semis=0, gain=1.0, at=t, **c)))
        time.sleep(secs)
        return [(w - t, pk) for w, pk, _ in heard(mark)[1] if w >= t - 0.05]

    p.tell(do="fx", space=0.3, echo=0, tone=0.5)
    got = after(secs=3.5)
    tail = [round(w, 1) for w, pk in got if pk > 60]
    check(f"its space: the note goes on round it after it's gone (heard till {max(tail, default=0)} s), dying away, "
          f"then nothing at all ({got[-3:]})", 0.4 < max(tail, default=0) < 2.0 and all(pk == 0 for _, pk in got[-5:]))
    loud = {}
    for tone in (0.1, 0.9, 0.5):
        p.tell(do="fx", space=0, echo=0, tone=tone)
        loud[tone] = (max(pk for _, pk in after("low", secs=0.6)), max(pk for _, pk in after("high", secs=0.6)))
    check(f"its tone: as the sound is at the middle ({loud[0.5]}); turned down, a high sound much softer "
          f"({loud[0.1][1]}) and a low one much the same ({loud[0.1][0]}); turned up, the high one much louder "
          f"({loud[0.9][1]})", all(abs(v - 9000) <= 180 for v in loud[0.5]) and loud[0.1][1] < 0.3 * 9000
          and loud[0.1][0] > 0.8 * 9000
          and loud[0.9][1] > 1.6 * 9000 and loud[0.9][0] < 1.3 * 9000)
    mark = log_at()
    p.tell(do="drone", level=0.8, note=60)
    time.sleep(2.0)
    on = [pk for _, pk, _ in heard(mark)[1]][-40:]
    p.tell(do="drone", level=0, note=60)
    time.sleep(1.8)
    off = [pk for _, pk, _ in heard(mark)[1]][-20:]
    check(f"its drone: a quiet note held, with nothing played ({min(on, default=0)} to {max(on, default=0)}), and gone "
          f"when it's turned down ({max(off, default=0)})", on and min(on) > 1000 and max(on) < 16000 and off
          and max(off) == 0)
    p.tell(do="space", v=0.5)
    got = after(play=True, secs=2.0)
    p.tell(do="space", v=0)
    time.sleep(2.5)
    plain = after(play=True, secs=1.0)
    check(f"the Soundboard's own sounds in a space too, when START's card says so (heard till "
          f"{max((round(w, 1) for w, pk in got if pk > 60), default=0)} s), and not when it doesn't (till "
          f"{max((round(w, 2) for w, pk in plain if pk > 60), default=0)} s)",
          max((w for w, pk in got if pk > 60), default=0) > 0.4
          and max((w for w, pk in plain if pk > 60), default=1) < 0.1)
    p.tell(do="fx", space=0.9, echo=0.5, tone=0.5, secs=0.25)
    mark = log_at()
    p.tell(do="note", id="kick", semis=0, gain=1.0)
    time.sleep(0.5)
    p.tell(do="stop")
    time.sleep(0.5)
    stopped = [pk for _, pk, _ in heard(mark)[1]][-10:]
    check(f"everything stopped: its echo and its space with it ({stopped})", stopped and max(stopped) == 0)
    pid = p.p.pid

    def cpu(secs):
        def ticks():
            return sum(int(x) for x in open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[11:13])
        a = ticks()
        time.sleep(secs)
        return (ticks() - a) / os.sysconf("SC_CLK_TCK") / secs

    time.sleep(1.0)
    idle = cpu(2.0)
    check(f"...and then, with its effects still set and nothing playing: next to no work ({idle * 100:.1f}% of a "
          f"core)", idle < 0.05)
    p.quit()


# ---- in media mode ---------------------------------------------------------------------------------------------------
if not ONLY or "app" in ONLY:
    import pietato_all as g
    import pitato.beatlink as BL
    import pitato.listen as L
    import pitato.bounce as BN
    import pitato.screens.bounce as SBN
    HOME = S + "/home/u"
    os.makedirs(HOME, exist_ok=True)
    if os.path.exists(ALOG):
        os.remove(ALOG)
    g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/mcache"; g.PADS_FILE = S + "/pads.json"
    g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
    g.STATIC = S + "/static"
    os.makedirs(g.STATIC, exist_ok=True)
    json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
    g.home_dir = lambda: HOME
    AS = S + "/asound"
    os.makedirs(AS + "/card0/pcm0p")
    open(AS + "/cards", "w").write(" 0 [vc4hdmi0       ]: vc4-hdmi - vc4-hdmi-0\n                      vc4-hdmi-0\n")
    os.makedirs(S + "/v4l")
    L.ASOUND, L.V4L = AS, S + "/v4l"
    BL.BEAT_HOST, BL.BEAT_PORT = "127.0.0.3", 25470
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

    def tap(name, repeat=False):
        m.press(name, repeat=repeat)
        m.release(name)
        spin(0.02)

    def notes(since=0.0):
        return [(at, c) for at, c in told if c.get("do") == "note" and at >= since]

    apps = next(t_ for t_ in g.LIBRARY if t_["name"] == "Apps")
    ai = g.LIBRARY.index(apps)
    m.open_app(ai)
    m.sels[ai] = next(k for k, it in enumerate(m.tab_items()) if it["title"] == "Soundboard")
    m.press("a")
    spin(4, lambda: m.board is not None and len(m.board.ready) == 32 and m.board.sound_ok)
    b = m.board
    tap("start")
    rows = m.board_rows()
    tap("start")
    hints = m.sim_hints(m.sim_game())
    tap("l")
    s = m.sim_game()
    check(f"L from the Soundboard's buttons ({hints[0]}; START's card has no row for it now: {[r[0] for r in rows]}): "
          f"the shape, {BN.BALLS_FIRST} balls in it ({s.bounce and (s.bounce['shape'], s.bounce['count'])}); its "
          f"buttons along the bottom ({m.sim_hints(s)})", not any(r[0] in ("seq", "bounce") for r in rows)
          and hints[0] == ("L R", "Sequencer, Bounce") and m.board_mode() == "bounce"
          and b.bounce is not None and len(b.bounce.balls) == BN.BALLS_FIRST and b.card is None and m.sim_opts is None
          and s.bounce["shape"] == "Hexagon" and m.sim_hints(s)[:2] == [("A B", "Balls"), ("SELECT", "Key")]
          and m.sim_hints(s)[-2:] == [("START", "Pause"), ("HOME", "Back")])
    from PIL import ImageDraw as PILDraw
    texts = []
    real_text = PILDraw.ImageDraw.text
    PILDraw.ImageDraw.text = lambda self, xy, text, *a, **k: (texts.append((str(text), round(xy[0]))),
                                                             real_text(self, xy, text, *a, **k))[1]
    flush()
    PILDraw.ImageDraw.text = real_text
    line = {t: x for t, x in texts if t == "Bounce" or t.startswith("Hexagon") or t.endswith(" pentatonic")}
    check(f"...its line: its name over the shape, between ◀ and ▶ (L and R go on from it), its key and scale at the "
          f"left, its shape's name and how many balls at the right ({line})", 150 < line.get("Bounce", 0) < 280
          and line.get("C pentatonic", 0) == 14 and line.get(f"Hexagon, {BN.BALLS_FIRST} balls", 0) > 300
          and "Hexagon" not in line)
    from PIL import Image as PILImage
    beside = []
    PILDraw.ImageDraw.text = lambda self, xy, text, *a, **k: (beside.append(str(text)),
                                                             real_text(self, xy, text, *a, **k))[1]
    BN.draw_panel(PILDraw.Draw(PILImage.new("RGB", (196, 340))), (0, 0, 196, 340), s.bounce, s.bounce_fonts())
    PILDraw.ImageDraw.text = real_text
    at_x, at_y = beside.index("X"), beside.index("Y")
    check(f"...beside it, over its sliders: X and its sound, Y and its scale ({beside[at_x:at_y + 2]}), and nothing "
          f"about shaking the balls", beside[at_x:at_y + 2] == ["X", "Bell", "Y", "Pentatonic"]
          and not any("hake" in t for t in beside))
    lights = []
    was_light = m.bounce_light
    m.bounce_light = lambda k, when: (lights.append((k, when)), was_light(k, when))[1]
    t0 = time.monotonic()
    spin(4.0)
    got = notes(t0)
    walls = {round(c["semis"], 3) for _, c in got}
    ahead = [c["at"] - SBN.BOUNCE_LATE - at for at, c in got]       # (how long before its ball hit, it was told)
    hit = [min((abs(c["at"] - SBN.BOUNCE_LATE - when) for k, when in lights
                if round(c["semis"], 3) == round(BN.note_semis(BN.wall_note(k, "C", "Pentatonic"), 60, "C"), 3)),
               default=9) for _, c in got if c["at"] - SBN.BOUNCE_LATE < lights[-1][1] - 0.05] if lights else [9]
    gains, pans = [c["gain"] for _, c in got], [c["pan"] for _, c in got]
    check(f"its balls go, and each that hits a wall plays its note, the wall's own (C pentatonic round the hexagon: "
          f"{sorted(walls)}), on its own Bell, told before the ball gets there ({min(ahead, default=0):.3f} to "
          f"{max(ahead, default=0):.3f} s before) and heard BOUNCE_LATE after it does (each within "
          f"{max(hit) * 1000:.1f} ms of its wall's hit)", len(got) >= 4 and len(lights) >= len(hit) >= 4
          and walls <= {0.0, 2.0, 4.0, 7.0, 9.0, 12.0} and all(c["id"] == "Tones/Bell" for _, c in got)
          and all(-0.001 <= x <= SBN.BOUNCE_AHEAD + 0.001 for x in ahead) and max(hit) <= 0.012)
    later = time.monotonic() + 30.0                   # (two more told, of hits as they could be: heard much later)
    m.bounce_note(0, later, None, 0.0, -1.0)
    m.bounce_note(1, later, None, 1.0, 1.0)
    graze, straight = notes(later - 31.0)[-2:]
    check(f"...louder the straighter a ball hits, heard from the side it hits on: as they went ({min(gains):.2f} to "
          f"{max(gains):.2f}, {min(pans):+.2f} to {max(pans):+.2f}), a ball grazing the left ({graze[1]['gain']}, "
          f"{graze[1]['pan']:+}) and one straight into the right ({straight[1]['gain']}, {straight[1]['pan']:+})",
          all(SBN.BOUNCE_GAIN * SBN.BOUNCE_SOFT - 1e-3 <= g <= SBN.BOUNCE_GAIN + 1e-3 for g in gains)
          and all(abs(p) <= SBN.BOUNCE_PAN + 1e-3 for p in pans)
          and graze[1]["gain"] == round(SBN.BOUNCE_GAIN * SBN.BOUNCE_SOFT, 3) and graze[1]["pan"] == -SBN.BOUNCE_PAN
          and straight[1]["gain"] == SBN.BOUNCE_GAIN and straight[1]["pan"] == SBN.BOUNCE_PAN)
    fx = [c for _, c in told if c.get("do") in ("fx", "drone")]
    check(f"...its player told its effects as its sliders have them (reverb 4, echo 3 a dotted eighth apart, tone 5: "
          f"as the sound is) and no drone ({fx[:2]})", {"do": "fx", "space": 0.4, "echo": 0.3, "tone": 0.5,
                                                         "secs": round(SBN.ECHO_BEATS * 60.0 / b.clock.bpm, 4)} in fx
          and {"do": "drone", "level": 0.0, "note": 60} in fx)
    lit = m.sim_game().bounce["lit"]
    check(f"...the walls hit, lit as they were ({sum(1 for x in lit if x)} of {len(lit)})",
          any(x and time.monotonic() - x < 4.5 for x in lit))
    for _ in range(7):
        tap("a")
    most = len(b.bounce.balls)
    tap("b")
    check(f"A: a ball more, up to {BN.BALLS_MOST} (and said: {toasts[-1:]}); B: one fewer ({most}, "
          f"{len(b.bounce.balls)})",
          most == BN.BALLS_MOST and len(b.bounce.balls) == BN.BALLS_MOST - 1 and toasts[-1:] == [
              f"That's as many balls as there can be ({BN.BALLS_MOST})"])
    spin0, speed0 = b.bounce.spin, b.bounce.speed
    sl = m.sim_game().bounce["sliders"]
    check(f"its sliders, at the right of its page: {[(k, v) for k, _, v, _, _ in sl]}, Spin picked",
          [k for k, *_ in sl] == ["spin", "speed", "space", "echo", "tone", "drone"] and b.bounce_sel == 0
          and [v for _, _, v, _, _ in sl] == [2, 4, 4, 3, 5, 0] and [x[1] for x in sl][2] == "Reverb")
    tap("left")
    tap("left", repeat=True)
    tap("left", repeat=True)
    turned = b.bounce.spin
    for _ in range(40):
        tap("right", repeat=True)
    tap("down")
    tap("right")
    tap("right")
    check(f"◀ moves Spin's slider down (held, on and on: {spin0} to {turned}, the other way round), ▶ up, as fast as "
          f"it turns at most ({b.bounce.spin}); ▼ picks Speed, ▶ the balls faster ({speed0} to {b.bounce.speed})",
          abs(turned - (spin0 - 3 * BN.SPIN_STEP)) < 1e-6 and b.bounce.spin == BN.SPIN_MOST and b.bounce_sel == 1
          and abs(b.bounce.speed - (speed0 + 2 * BN.SPEED_STEP)) < 1e-6)
    tap("down")
    tap("left")
    tap("down")
    tap("down")
    tap("down")
    tap("right")
    fx = [c for _, c in told if c.get("do") in ("fx", "drone")]
    says = BN.SAYS["drone"]
    check(f"...Reverb, ◀: less, Drone (▼▼▼), ▶: on, each told its player at once ({fx[-2:]}), kept as it's left, not "
          f"each step ({m.setting('bounce_space')}); what the one picked does, said under them ({says!r})",
          b.bounce_levels == {"space": 3, "echo": 3, "tone": 5, "drone": 1} and fx[-2]["space"] == 0.3
          and fx[-1] == {"do": "drone", "level": 0.1, "note": 60} and m.setting("bounce_space") == "4"
          and BN.SLIDERS[b.bounce_sel][0] == "drone")
    tap("down")
    check("...▼ past the last: the first again", b.bounce_sel == 0)
    tap("x")
    said_x = toasts[-1:]
    ways = [(round(bl[3], 6), round(bl[4], 6)) for bl in b.bounce.balls]
    where = [(round(bl[1], 3), round(bl[2], 3)) for bl in b.bounce.balls]
    m.press("y")
    now_ways = [(round(bl[3], 6), round(bl[4], 6)) for bl in b.bounce.balls]
    now_where = [(round(bl[1], 3), round(bl[2], 3)) for bl in b.bounce.balls]
    m.release("y")
    one = (m.setting("bounce_scale"), toasts[-1:], m.sim_game().bounce["scale"])
    tap("y", repeat=True)
    tap("y")
    two = (m.setting("bounce_scale"), toasts[-1:])
    check(f"X: its next sound, said ({said_x}); Y: its next scale, said, and on its page ({one}), round and round "
          f"({two}; held: once is once); the balls go on as they were (not shaken), the key and the shape as they "
          f"were ({m.setting('bounce_key')}, {b.bounce.sides} sides)", m.setting("bounce_sound") == "Tones/Marimba"
          and said_x == ["Marimba"] and one == ("Blues", ["Blues"], "Blues") and two == ("Major", ["Major"])
          and m.setting("bounce_key") == "C" and now_where == where and now_ways == ways and b.bounce.sides == 6)
    world = b.bounce
    t1 = time.monotonic()
    tap("select")
    one = (m.setting("bounce_key"), toasts[-1:], m.sim_game().bounce["key"])
    drone = [c for at, c in told if at >= t1 and c.get("do") == "drone"]
    tap("select", repeat=True)
    tap("select")
    two = (m.setting("bounce_key"), toasts[-1:])
    check(f"SELECT: its next key, said, and on its page ({one}), its drone's told its note ({drone[-1:]}), and on "
          f"({two}; held: once is once); its shape's left alone (it's on its card: {b.bounce.sides} sides), and its "
          f"scale ({m.setting('bounce_scale')})", one == ("C#", ["Key: C#"], "C#") and two == ("D", ["Key: D"])
          and bool(drone) and drone[-1].get("note") == 61 and b.bounce is world and b.bounce.sides == 6
          and m.setting("bounce_shape") in (None, "", "Hexagon") and m.setting("bounce_scale") == "Major")
    # START: its card, paused
    tap("start")
    t_was, frames = b.bounce.t, FB.frames
    mark = time.monotonic()
    spin(0.8)
    end = time.monotonic() + 0.8
    n0 = FB.frames
    while time.monotonic() < end:
        m.tick()
        if m.dirty:
            m.flush()
        time.sleep(0.005)
    check(f"START: its card ({[r[0] for r in m.board_rows()]}), and it's paused: nothing moves, no notes, nothing "
          f"drawn ({FB.frames - n0} frames)", b.card == "bounce" and m.sim_opts == 0 and b.bounce.t == t_was
          and not notes(mark) and FB.frames - n0 <= 3
          and [r[0] for r in m.board_rows()] == ["shape", "sound", "key", "scale", "snap"])
    from PIL import Image as PILImage, ImageDraw as PILDraw
    probe = PILDraw.Draw(PILImage.new("RGB", (1, 1)))
    how = m.wrap(probe, SBN.BOUNCE_HOW, m.fonts["small"], 404 - 44, lines=3)
    check(f"...and how its buttons go now, all of it in the card's three lines ({how})", len(how) <= 3
          and not how[-1].endswith("…") and "Y: the scale. SELECT: the key." in " ".join(how)
          and " ".join(how).endswith("L and R: the Soundboard, the Sequencer."))
    tap("right")                                       # (shape: Triangle, the first again after the last)
    one = (b.bounce.sides, m.setting("bounce_shape"))
    tap("left")
    tap("left")                                        # (...and back: Hexagon, Pentagon)
    two = (b.bounce.sides, m.setting("bounce_shape"))
    tap("down")
    tap("right")                                       # (sound: Kalimba)
    tap("down")
    tap("left")                                        # (key: C#)
    tap("down")
    tap("left")                                        # (scale: Blues, the last before the first)
    tap("down")
    tap("right")                                       # (snap: On)
    rows = {k: v for k, _, v in m.board_rows()}
    check(f"...its shape there, ◀▶: round and round ({one}, {two}), the balls still inside it; its sound, key, scale "
          f"and snapping, changed there too ({rows})", one == (3, "Triangle") and two == (5, "Pentagon")
          and rows["shape"] == "Pentagon" and b.bounce is world and b.bounce.inside() and rows["sound"] == "Kalimba"
          and rows["key"] == "C#" and rows["scale"] == "Blues" == m.setting("bounce_scale") and rows["snap"] == "On")
    tap("start")
    m.board_tempo(120)
    c = b.clock
    t0 = time.monotonic()
    spin(3.0)
    got = notes(t0)
    beats = [c.beat(x["at"]) / SBN.BOUNCE_GRID for _, x in got]
    check(f"START again: on it goes; snapped, each note on an eighth of the Soundboard's tempo ({len(got)} notes, "
          f"{[round(x % 1, 3) for x in beats][:6]}...), on its Kalimba, C# blues round the pentagon",
          b.card is None and len(got) >= 3 and all(abs(x - round(x)) < 1e-3 for x in beats)
          and all(x["id"] == "Tones/Kalimba" for _, x in got)
          and {round(x["semis"], 3) for _, x in got} <= {1.0, 4.0, 6.0, 7.0, 8.0})
    end = time.monotonic() + 2.0
    n0 = FB.frames
    while time.monotonic() < end:
        m.tick()
        if m.dirty:
            m.flush()
        time.sleep(0.005)
    drawn = FB.frames - n0
    check(f"...drawn frame by frame as it plays ({drawn} in 2 s: {drawn / 2:.0f} a second)", 30 <= drawn <= 48)
    page = flush()
    s = m.sim_game()
    accent = tuple(SBN.ACCENT)
    shape = page[118:430, :420]
    dim_px = int((np.abs(shape - np.array(g.co_mix(g.BG, accent, BN.DIM))).max(axis=2) <= 12).sum())
    lit_px = int((np.abs(shape - np.array(accent)).max(axis=2) <= 12).sum())
    others = int(((np.abs(shape - np.array(g.BG)).max(axis=2) > 40)
                  & (np.abs(shape - np.array(accent)).max(axis=2) > 60)
                  & (np.abs(shape - np.array(g.co_mix(g.BG, accent, BN.DIM))).max(axis=2) > 60)).sum())
    check(f"the page: the shape and its balls in one colour, the accent ({accent}: its walls {dim_px} px, dim till "
          f"they're hit; the balls and the walls just hit {lit_px} px), and nothing in any other ({others} px)",
          s.bounce["colour"] == accent and dim_px + lit_px > 1800 and dim_px > 300 and lit_px > 300 and others < 400)
    tap("start")
    labels = [r[1] for r in m.board_rows()]
    hints = m.board_card_hints()
    tap("start")
    tap("r", repeat=True)
    held = m.board_mode()
    tap("r")
    s = m.sim_game()
    check(f"R from Bounce (its card has no row to leave it by: {labels}; {hints}): the Soundboard's buttons again, "
          f"its effects and drone off ({[c for _, c in told[-2:]]}), its sliders kept ({m.sim_hints(s)}); held: "
          f"once is once", labels == ["Shape", "Sound", "Key", "Scale", "Snap to the tempo"]
          and hints == [("▲▼", "Choose"), ("◀▶", "Change"), ("START", "Play on")] and held == "bounce"
          and m.board_mode() == "pads" and b.bounce is None and b.card is None and s.bounce is None
          and [c for _, c in told[-2:]] == [{"do": "fx", "space": 0, "echo": 0, "tone": 0.5},
                                            {"do": "drone", "level": 0}]
          and m.sim_hints(s)[-2] == ("START", "More")
          and m.setting("bounce_spin") == f"{BN.SPIN_MOST:.2f}" and m.setting("bounce_space") == "3"
          and m.setting("bounce_drone") == "1")
    tap("up")
    check("...and its buttons play their sounds as ever", spin(1.0, lambda: b.bank()["pads"]["up"] in b.playing))
    tap("l")
    was = b.bounce is not None and m.board_mode() == "bounce"
    proc, balls = b.proc, len(b.bounce.balls)
    home = m.sim_home()
    out = (m.tab == ai and m.view == "list" and not m.board_shown()
           and m.tab_items()[m.sels[ai]]["title"] == "Soundboard")
    spin(0.5)
    check(f"HOME in Bounce: back to Apps at once, the Soundboard picked (not its buttons' page first: {out}); its "
          f"player gone; HOME again there isn't its", was and home is True and out and m.sim_opts is None
          and b.proc is None and until(lambda: proc.poll() is not None, 5) and m.sim_home() is False)
    t1 = time.monotonic()
    m.press("a")
    spin(4, lambda: m.board.proc is not None and m.board.sound_ok)
    spin(0.3)
    s = m.sim_game()
    fx = [c for at, c in told if at >= t1 and c.get("do") == "fx"]
    check(f"...the Soundboard opened again: Bounce's page, as it was left ({balls} balls), its effects told its new "
          f"player ({fx[:1]})", m.board_shown() and m.board_mode() == "bounce" and b.proc is not None
          and b.proc is not proc and s.bounce is not None and s.bounce["count"] == balls and bool(fx)
          and m.sim_hints(s)[-2:] == [("START", "Pause"), ("HOME", "Back")])
    check("...and HOME from there: Apps again", m.sim_home() is True and m.tab == ai and m.view == "list"
          and m.tab_items()[m.sels[ai]]["title"] == "Soundboard")
    m.press("b")
    spin(0.2)
    m.leave()

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
