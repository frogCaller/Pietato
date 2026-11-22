"""The Soundboard's Bounce (pitato/bounce.py, screens/bounce.py, soundplay.py). The shape and its balls on their own:
each shape, turning slowly or as fast as it goes either way, eight balls going as fast as they go, for a minute: every
ball inside it all the while, every wall hit, and no wall heard twice at once from one ball; its walls' notes, a
scale's from its key up; a sound's own note found (and none in a drum's). Its player, against a pretend sound card:
its own sounds, at middle C; a note heard when it's told, exactly; only a few at a time, each no longer than it should
be; a light echo, at its distance, and none with it off. Then in media mode: START's card, Bounce; its balls moving and
their notes played as they hit, each wall's its own, BOUNCE_LATE after; A and B, ◀▶ ▲▼, L and R, SELECT; START, its
card (paused: nothing moves, nothing's drawn); its sound, key, echo and snapping there (snapped: each note on an
eighth of the Soundboard's tempo); Leave Bounce; drawn frame by frame while it plays, and the page as it is."""
import json, os, random, shutil, subprocess, sys, threading, time, wave
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
# rate; logs each period as it goes in (when, where in the stream, how loud, where its first sound is) and when it
# starts playing (each frame's heard at that start, and a frame's time after for each frame)
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


def spread(xs):
    return max(xs) - min(xs) if xs else 0.0


# ---- the shape and its balls, on their own --------------------------------------------------------------------------
if not ONLY or "world" in ONLY:
    import pitato.bounce as BN
    rows, doubles = [], 0
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
            for k, t, ball in hits:
                if (ball, k) in last and t - last[(ball, k)] < BN.AGAIN - 1e-9:
                    doubles += 1
                last[(ball, k)] = t
            rows.append((name, spin, len(w.balls), out, min(per)))
    check(f"each shape, turning slowly or as fast as it goes either way, eight balls as fast as they go, for a minute: "
          f"every ball inside it all the while, every wall hit, no wall heard twice at once from one ball "
          f"(shape, spin, balls, frames with one outside, fewest hits on a wall: {rows}; twice at once: {doubles})",
          all(r[2] == BN.BALLS_MOST and r[3] == 0 and r[4] > 20 for r in rows) and doubles == 0)
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


# ---- its player --------------------------------------------------------------------------------------------------
if not ONLY or "player" in ONLY:
    sys.path.insert(0, ROOT + "/pitato")
    import soundplay as SPL
    KICK = burst(S + "/files/kick.wav")
    t = np.arange(int(1.0 * RATE)) / RATE
    TONE = wav(S + "/files/tone.wav", np.sin(2 * np.pi * 440 * t) * 6000 * np.minimum(1.0, (1.0 - t) * 50))
    p = Player()
    p.tell(do="load", sounds=[["kick", KICK], ["tone", TONE]])
    p.tell(do="volume", v=100)
    p.tell(do="warm")
    until(lambda: p.got("ready", id="kick") and p.got("ready", id="tone") and p.got("sound", ok=True), 5)
    time.sleep(0.6)
    for sid in ("Tones/Bell", "Tones/Pluck", "Tones/Pad", "tone", "kick"):
        p.tell(do="pitch", id=sid)
    until(lambda: len(p.got("pitch")) >= 5, 5)
    said = {m["id"]: m["midi"] for m in p.got("pitch")}
    check(f"asked a sound's own note: its own sounds at middle C, the A above it, none in a drum ({said})",
          all(abs(said.get(s, 0) - 60) < 0.3 for s in SPL.TONES) and abs(said.get("tone", 0) - 69) < 0.1
          and said.get("kick", 1) is None)
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
    p.tell(do="note", id="Tones/Pad", semis=-12.0, gain=1.0, at=time.monotonic() + 0.3)
    time.sleep(3.2)
    loud = [w for w, pk, _ in heard(mark)[1] if pk > 300]
    span = loud[-1] - loud[0] if loud else 0
    check(f"...each no longer than it should be: its pad an octave down (4.8 s of it) cut at {SPL.BOUNCE_SECS} s "
          f"({span:.2f} s)", abs(span - SPL.BOUNCE_SECS) < 0.08)
    p.tell(do="echo", on=True, secs=0.3)
    mark = log_at()
    t1 = time.monotonic() + 0.3
    p.tell(do="note", id="kick", semis=0, gain=1.0, at=t1)
    time.sleep(1.6)
    hits, periods = heard(mark)
    when = [round((h[0] - t1) * 1000) for h in hits]
    loudest = [max((pk for w, pk, _ in periods if h[0] - 0.01 <= w <= h[0] + 0.045), default=0) for h in hits]
    ratio = loudest[1] / loudest[0] if len(hits) > 1 and loudest[0] else 0
    check(f"a light echo: the note, then again every 0.3 s, each a little of the one before ({when} ms; the first "
          f"{ratio:.2f} as loud)", len(hits) >= 3 and abs(when[0]) <= 3 and abs(when[1] - 300) <= 3
          and abs(when[2] - 600) <= 3 and abs(ratio - SPL.ECHO_FEED / 256) < 0.04)
    p.tell(do="echo", on=False)
    mark = log_at()
    p.tell(do="note", id="kick", semis=0, gain=1.0, at=time.monotonic() + 0.3)
    time.sleep(1.0)
    check(f"...and none with it off ({len(heard(mark)[0])})", len(heard(mark)[0]) == 1)
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
    spin(4, lambda: m.board is not None and len(m.board.ready) == 24 and m.board.sound_ok)
    b = m.board
    tap("start")
    rows = m.board_rows()
    m.sim_opts = [r[0] for r in rows].index("bounce")
    hints = m.board_card_hints()
    tap("a")
    s = m.sim_game()
    check(f"START's card has Bounce, last (its buttons: {hints}); A there: the shape, {BN.BALLS_FIRST} balls in it, "
          f"the card gone ({s.bounce and (s.bounce['shape'], s.bounce['count'])}); its buttons along the bottom "
          f"({m.sim_hints(s)})", rows[-1][:2] == ("bounce", "Bounce") and ("A", "Open") in hints
          and b.bounce is not None and len(b.bounce.balls) == BN.BALLS_FIRST and b.card is None and m.sim_opts is None
          and s.bounce["shape"] == "Hexagon" and m.sim_hints(s)[:2] == [("A B", "Balls"), ("◀▶▲▼", "Spin, speed")]
          and m.sim_hints(s)[-1] == ("START", "Pause"))
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
    check(f"its balls go, and each that hits a wall plays its note, the wall's own (C pentatonic round the hexagon: "
          f"{sorted(walls)}), on its own Bell, told before the ball gets there ({min(ahead, default=0):.3f} to "
          f"{max(ahead, default=0):.3f} s before) and heard BOUNCE_LATE after it does (each within "
          f"{max(hit) * 1000:.1f} ms of its wall's hit)", len(got) >= 4 and len(lights) >= len(hit) >= 4
          and walls <= {0.0, 2.0, 4.0, 7.0, 9.0, 12.0} and all(c["id"] == "Tones/Bell" and c["gain"] == SBN.BOUNCE_GAIN
                                                               for _, c in got)
          and all(-0.001 <= x <= SBN.BOUNCE_AHEAD + 0.001 for x in ahead) and max(hit) <= 0.012
          and {"do": "echo", "on": True, "secs": round(SBN.ECHO_BEATS * 60.0 / b.clock.bpm, 4)} in [c for _, c in told])
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
    tap("left")
    tap("left", repeat=True)
    tap("left", repeat=True)
    turned = b.bounce.spin
    for _ in range(40):
        tap("right", repeat=True)
    tap("up")
    tap("up")
    check(f"◀ turns it more one way (held, on and on: {spin0} to {turned}), ▶ the other, as fast as it goes at most "
          f"({b.bounce.spin}); ▲ the balls faster ({speed0} to {b.bounce.speed})",
          abs(turned - (spin0 + 3 * BN.SPIN_STEP)) < 1e-6 and b.bounce.spin == -BN.SPIN_MOST
          and abs(b.bounce.speed - (speed0 + 2 * BN.SPEED_STEP)) < 1e-6)
    tap("r")
    one = (b.bounce.sides, m.setting("bounce_shape"))
    tap("l")
    tap("l")
    two = (b.bounce.sides, m.setting("bounce_shape"))
    tap("select")
    check(f"R: the next shape, round and round ({one}); L the other way ({two}); SELECT the next scale "
          f"({m.setting('bounce_scale')}); the balls still inside it", one == (3, "Triangle") and two == (5, "Pentagon")
          and m.setting("bounce_scale") == "Blues" and b.bounce.inside())
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
          and [r[0] for r in m.board_rows()] == ["sound", "key", "scale", "echo", "snap", "leave"])
    tap("right")                                       # (sound: Pluck)
    tap("down")
    tap("right")                                       # (key: C#)
    m.sim_opts = 3
    tap("right")                                       # (echo: Off)
    tap("down")
    tap("right")                                       # (snap: On)
    rows = {k: v for k, _, v in m.board_rows()}
    echoes = [c for _, c in told if c.get("do") == "echo"]
    check(f"...its sound, key, echo and snapping, changed there ({rows}); the echo off, told ({echoes[-1:]})",
          rows["sound"] == "Pluck" and rows["key"] == "C#" and rows["echo"] == "Off" and rows["snap"] == "On"
          and [x.get("on") for x in echoes[-1:]] == [False])
    tap("start")
    m.board_tempo(120)
    c = b.clock
    t0 = time.monotonic()
    spin(3.0)
    got = notes(t0)
    beats = [c.beat(x["at"]) / SBN.BOUNCE_GRID for _, x in got]
    check(f"START again: on it goes; snapped, each note on an eighth of the Soundboard's tempo ({len(got)} notes, "
          f"{[round(x % 1, 3) for x in beats][:6]}...), on its Pluck, C# blues round the pentagon",
          b.card is None and len(got) >= 3 and all(abs(x - round(x)) < 1e-3 for x in beats)
          and all(x["id"] == "Tones/Pluck" for _, x in got)
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
    cols = {tuple(col) for col in s.bounce["colours"]}
    walls_px = sum(int((np.abs(page - np.array(col)).max(axis=2) <= 40).sum()) for col in cols)
    dim_px = sum(int((np.abs(page - np.array(g.co_mix(g.BG, col, 0.45))).max(axis=2) <= 12).sum()) for col in cols)
    balls_px = int((np.abs(page[118:430] - np.array(g.TEXT)).max(axis=2) <= 12).sum())
    check(f"the page: its walls in their notes' colours ({dim_px} px, {walls_px} lit), its balls ({balls_px} px)",
          dim_px + walls_px > 1500 and balls_px > 300)
    tap("start")
    m.sim_opts = 5
    hints = m.board_card_hints()
    tap("a")
    s = m.sim_game()
    check(f"its card's Leave Bounce ({hints}): the Soundboard's buttons again, the echo off ({m.sim_hints(s)})",
          b.bounce is None and b.card is None and s.bounce is None and told[-1][1] == {"do": "echo", "on": False}
          and m.sim_hints(s)[-1] == ("START", "More") and ("A", "Leave Bounce") in hints
          and m.setting("bounce_spin") == f"{-BN.SPIN_MOST:.2f}")
    tap("up")
    check("...and its buttons play their sounds as ever", spin(1.0, lambda: b.bank()["pads"]["up"] in b.playing))
    m.press("b")
    spin(0.2)
    m.leave()

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
