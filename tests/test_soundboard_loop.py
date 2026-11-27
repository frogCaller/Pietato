"""The Soundboard's loops and notes (pitato/soundplay.py, screens/soundboard.py). Its player, on its own, against a
pretend sound card that logs when each period of sound is heard: a loop's sounds heard at their beats, evenly, at the
tempo it's told, and from the moment a new tempo's told; a sound in it that isn't to be heard before a beat isn't; the
click, quiet, on each beat and higher on a bar's first; a sound played as a note (higher: shorter, lower: longer); a
loop of nothing, or of nonsense, and none at all. Then the app in media mode: START's card's first row (START, then
A) records a layer and stops it, the buttons pressed meanwhile played back round and round where they were pressed
(snapped to the beat, or not); more layers; its last row drops the last (the one recording, if one is); SELECT never
records now (it's the banks'); START held clears it all; START tapped, its card; A, B, X or Y held and the d-pad, its
sound as notes of a scale, the note on its tile, and into the loop; the tempo, the loop's length and the space on
START's card; the page as it goes."""
import json, math, os, shutil, subprocess, sys, threading, time, wave
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
sys.path.insert(0, ROOT)
import numpy as np

S = SP + "/t_soundboard_loop"
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


# ---- the player on its own -----------------------------------------------------------------------------------------
if not ONLY or "player" in ONLY:
    KICK, LONG = burst(S + "/files/kick.wav"), burst(S + "/files/long.wav", secs=0.4, amp=12000, f=300.0)
    p = Player()
    p.tell(do="load", sounds=[["kick", KICK], ["long", LONG]])
    p.tell(do="volume", v=100)
    p.tell(do="warm")
    until(lambda: p.got("ready", id="kick") and p.got("ready", id="long") and p.got("sound", ok=True), 5)
    time.sleep(0.6)                                    # (its sound card open a while: it knows when a frame's heard)
    mark = log_at()
    t0 = time.monotonic() + 0.4
    p.tell(do="loop", hits=[[0, "kick", 0, -1e9], [1, "kick", 0, -1e9], [2, "kick", 0, -1e9], [3, "kick", 0, -1e9]],
           beats=4, bpm=120, b0=0.0, t0=t0, click=False)
    time.sleep(3.0)
    hits, _ = heard(mark)
    want = [t0 + 0.5 * k for k in range(len(hits))]
    off = [(h[0] - w) * 1000 for h, w in zip(hits, want)]
    gaps = [(b[0] - a[0]) * 1000 for a, b in zip(hits, hits[1:])]
    check(f"a loop at 120 beats a minute: its sound heard on each beat, half a second apart "
          f"({[round(g, 1) for g in gaps]} "
          f"ms), each when the clock says that beat's heard ({[round(o, 1) for o in off]} ms)",
          len(hits) >= 5 and all(abs(g - 500) <= 1.0 for g in gaps) and all(abs(o) <= 4.0 for o in off)
          and spread(off) <= 1.5)
    # a new tempo from the beat it's at now: the same beat, from then on 150 a minute
    now = time.monotonic()
    beat_now = (now + 0.05 - t0) * 2.0
    mark = log_at()
    p.tell(do="loop", hits=[[0, "kick", 0, -1e9], [1, "kick", 0, -1e9], [2, "kick", 0, -1e9], [3, "kick", 0, -1e9]],
           beats=4, bpm=150, b0=beat_now, t0=now + 0.05, click=False)
    time.sleep(2.0)
    hits, _ = heard(mark)
    gaps = [(b[0] - a[0]) * 1000 for a, b in zip(hits, hits[1:])][1:]
    first = math_ceil = int(beat_now) + 1
    want0 = now + 0.05 + (first - beat_now) * 0.4
    near = min((abs(h[0] - want0) for h in hits), default=9) * 1000
    check(f"...told 150 a minute, from the beat it's at: 400 ms apart from then on "
          f"({[round(g, 1) for g in gaps]}), its "
          f"next beat where the new tempo puts it ({near:.1f} ms out)",
          len(gaps) >= 3 and all(abs(g - 400) <= 1.0 for g in gaps) and near <= 4.0)
    # half beats, and one that isn't to be heard before beat 12 of the clock's
    now = time.monotonic()
    b_now = (now - t0) * 2.0
    mark = log_at()
    later = float(int(b_now) + 4)
    p.tell(do="loop", hits=[[0, "kick", 0, -1e9], [0.5, "kick", 0, later]], beats=1, bpm=120, b0=0.0, t0=t0,
           click=False)
    time.sleep(3.2)
    hits, _ = heard(mark)
    beats = [round((h[0] - t0) * 2.0, 2) for h in hits]
    early = [b for b in beats if b % 1 > 0.25 and b < later - 0.3]
    halves = [b for b in beats if b % 1 > 0.25 and b > later - 0.3]
    check(f"a loop a beat long, a sound on its beat and one half way through that isn't heard before beat {later:.0f}: "
          f"on each beat, then each half beat from there ({beats})",
          not early and len(halves) >= 3 and all(abs(b - round(b * 2) / 2) <= 0.01 for b in beats))
    # the click: on each beat, quiet, higher on a bar's first
    mark = log_at()
    p.tell(do="loop", hits=[], beats=4, bpm=120, b0=0.0, t0=t0, click=True)
    time.sleep(2.6)
    ticks, _ = heard(mark)
    beats = [round((h[0] - t0) * 2.0, 2) for h in ticks]
    firsts = [h[1] for h in ticks if round((h[0] - t0) * 2.0) % 4 == 0]
    others = [h[1] for h in ticks if round((h[0] - t0) * 2.0) % 4 != 0]
    check(f"the click, with nothing in the loop: a tick on each beat ({beats}), quiet ({firsts[:2]}, {others[:3]} of "
          f"32767), the bar's first beat's louder", len(ticks) >= 4 and all(abs(b - round(b)) <= 0.01 for b in beats)
          and firsts and others and max(firsts + others) < 9000 and min(firsts) > max(others))
    # a loop of nothing (no sounds, no click), and of nonsense
    p.tell(do="loop", hits=[], beats=4, bpm=120, b0=0.0, t0=t0, click=False)
    time.sleep(0.3)
    mark = log_at()
    time.sleep(1.2)
    quiet = not heard(mark)[0]
    for bad in ({"hits": "x"}, {"hits": [[9, "kick", 0, 0]], "beats": 4, "bpm": 120, "b0": 0, "t0": t0},
                {"hits": [[0, "kick", 99, 0]], "beats": 4, "bpm": 120, "b0": 0, "t0": t0},
                {"hits": [[0, "kick", 0, 0]], "beats": 4, "bpm": "fast", "b0": 0, "t0": t0},
                {"hits": [[0, "nothing", 0, 0]], "beats": 4, "bpm": 120, "b0": 0, "t0": t0},
                {"hits": [[0, "kick", 0, 0]], "beats": 4, "bpm": 120, "b0": float("nan"), "t0": t0}):
        p.tell(do="loop", **bad)
    p.tell(do="play", id="kick", semis="up")
    p.tell(do="play", id="kick", semis=40)
    mark = log_at()
    time.sleep(1.2)
    check(f"a loop of nothing: silence; of nonsense (a sound past its end, too high a note, a tempo that isn't one, a "
          f"sound it hasn't got...), none, and a note that isn't one isn't played ({heard(mark)[0][:3]})",
          quiet and not heard(mark)[0] and p.p.poll() is None)
    # a sound played as a note: an octave higher, half as long; an octave lower, twice
    lengths = {}
    for semis in (0, 12, -12, 7):
        mark = log_at()
        p.tell(do="play", id="long", semis=semis)
        time.sleep(1.2)
        _, per = heard(mark)
        loud = [w for w, peak, is_loud in per if peak > 400]
        lengths[semis] = (max(loud) - min(loud)) if loud else 0.0
    ratio = {k: round(v / lengths[0], 2) for k, v in lengths.items() if lengths[0]}
    check(f"a sound played as a note: an octave up, half as long; an octave down, twice; a fifth up, 2/3 ({ratio})",
          lengths[0] > 0.3 and abs(ratio[12] - 0.5) < 0.08 and abs(ratio[-12] - 2.0) < 0.15
          and abs(ratio[7] - 0.667) < 0.08)
    p.tell(do="loop")
    time.sleep(0.3)
    mark = log_at()
    time.sleep(1.0)
    check("no loop at all: silence", not heard(mark)[0])
    p.quit()


# ---- the app, in media mode -----------------------------------------------------------------------------------------
if not ONLY or "app" in ONLY:
    import pietato_all as g
    import pitato.beatlink as BL
    import pitato.listen as L
    import pitato.screens.soundboard as SB
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
    BL.BEAT_HOST, BL.BEAT_PORT = "127.0.0.3", 25460    # (this one's shared beat: an address of its own)
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
    m.saves_peers = lambda addr=None: []              # (on its own, to start with)
    toasts = []
    was_toast = m.toast
    m.toast = lambda text, secs=4: (toasts.append(text), was_toast(text, secs))[1]
    told = []
    was_tell = m.board_tell
    m.board_tell = lambda **c: (told.append(c), was_tell(**c))[1]

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

    def tap(name):
        m.press(name)
        m.release(name)
        spin(0.03)

    def loops():
        return [c for c in told if c.get("do") == "loop"]

    def at(key):
        """Which of its card's rows that is."""
        return [r[0] for r in m.board_rows()].index(key)

    def rec():
        """START, then A: its card's first row (Record a loop, Add to the loop, Stop recording)."""
        tap("start")
        tap("a")

    def drop():
        """START, ▲, then A: its card's last row (Drop the last layer, or this one)."""
        tap("start")
        tap("up")
        label = m.board_rows()[m.sim_opts % len(m.board_rows())][1]
        tap("a")
        return label

    def until_t(when):
        while time.monotonic() < when:
            m.tick()
            time.sleep(0.001)

    apps = next(t_ for t_ in g.LIBRARY if t_["name"] == "Apps")
    ai = g.LIBRARY.index(apps)
    m.open_app(ai)
    m.sels[ai] = next(k for k, it in enumerate(m.tab_items()) if it["title"] == "Soundboard")
    m.press("a")
    spin(4, lambda: m.board is not None and len(m.board.ready) == 24 and m.board.sound_ok)
    b = m.board
    s = m.sim_game()
    check(f"Apps > Soundboard: its buttons along the bottom: SELECT's the banks' now, and the loop's on START's card "
          f"({m.sim_hints(s)})", m.board_shown()
          and m.sim_hints(s) == [("L R", "Sequencer, Bounce"), ("SELECT", "Bank"), ("START", "More"), ("HOME", "Back")])
    tap("start")
    rows = m.board_rows()
    check(f"START tapped: its card, Record a loop first ({m.sim_hints(m.sim_game())[1]}), then the bank, the volume, "
          f"the loop's tempo, length, snapping, click and the notes' scale ({[(k, v) for k, _, v in rows]}); nothing "
          f"to drop yet", m.sim_opts == 0 and b.card == "more" and rows[0] == ("loop", "Record a loop", None)
          and m.sim_hints(m.sim_game())[1] == ("A", "Record")
          and [(k, v) for k, _, v in rows][3:] == [("tempo", "100 BPM"), ("bars", "2 bars"), ("snap", "On"),
                                                  ("click", "On"), ("scale", "Major"), ("space", "Off")])
    from PIL import Image as PILImage, ImageDraw as PILDraw
    probe = PILDraw.Draw(PILImage.new("RGB", (1, 1)))
    how = m.wrap(probe, SB.BOARD_HOW, m.fonts["small"], 404 - 44, lines=3)
    check(f"...and how its buttons go now, all of it in the card's three lines ({how})", len(how) <= 3
          and not how[-1].endswith("…") and " ".join(how).startswith("L and R: the Sequencer and Bounce. SELECT: the "
                                                                      "next bank. START held clears the loop."))
    img, (cx, cy) = m.board_opts_card(s)
    (bx0, by0, bx1, by1), _ = m.sim_box()
    m.sim_opts = len(rows) - 1
    img2, (cx2, cy2) = m.board_opts_card(s)
    check(f"...on the GPi Case's screen, as many rows as fit, the one picked among them ({img.size[1]} px of the box's "
          f"{by1 - by0})", cy >= by0 and cy + img.size[1] <= by1 and cy2 + img2.size[1] <= by1)
    m.sim_opts = 0
    tap("start")
    spin(0.1)
    check("...START there closes it, and letting go of it doesn't open it again", m.sim_opts is None and b.card is None)
    m.press("start")
    spin(0.6)
    slow = (m.sim_opts, list(toasts))
    spin(0.5)
    m.release("start")
    spin(0.1)
    check(f"START held, nothing in the loop: every sound stopped, and no card ({toasts[-1:]}); a slow press of it "
          f"(over half a second) isn't that yet: its card, still ({slow})", slow == (0, [])
          and m.sim_opts is None and toasts[-1:] == ["Stopped"] and told[-1] == {"do": "stop"})

    # a layer: four sounds a little late on four beats, snapped to them, played back round and round
    m.board_tempo(120)
    m.set_setting("board_click", "Off")                 # (the click's its player's: heard here, it'd be counted)
    tap("select")
    hat = b.bank()["pads"]["up"]
    check(f"(SELECT: the Drums bank: {b.bank()['name']}, {hat.split('/')[-1]} on ▲; and nothing's recording)",
          b.at == 1 and b.ready.get(hat, 9) < 0.45 and b.take is None and not b.layers)
    rec()
    tap("start")
    stop_row = (m.board_rows()[0], m.sim_hints(m.sim_game())[1], m.board_rows()[-1])
    tap("start")
    check(f"START, then A (its card's first row): a layer's recording (nothing for its player yet: the click's off, as "
          f"it's set), the card gone; the row's to stop it now ({stop_row[0][1]!r}, {stop_row[1]}), and the last row "
          f"to drop it ({stop_row[2][1]!r})", b.take is not None and loops()[-1] == {"do": "loop"}
          and stop_row == (("loop", "Stop recording", None), ("A", "Stop"), ("drop", "Drop this layer", None))
          and m.sim_opts is None and b.card is None and m.sim_game().loop["rec"] is True)
    c = b.clock
    first = math.ceil(c.beat(time.monotonic())) + 2
    mark = log_at()
    for k in range(4):
        until_t(c.at(first + k) + 0.03)
        m.press("up")
        m.release("up")
    spin(0.25)
    rec()
    spin(0.3)
    layer = b.layers[0] if b.layers else None
    check(f"...START, then A again: kept, the four where they were played, each to its beat though played late "
          f"({[h[0] for h in layer[1]] if layer else None}, a {layer[0] if layer else 0}-beat loop)",
          b.take is None and len(b.layers) == 1 and layer[0] == 8
          and [h[0] for h in layer[1]] == [float((first + k) % 8) for k in range(4)])
    on = heard(mark)[0]
    lates = [round((t_ - c.at(first + k)) * 1000) for k, (t_, _) in enumerate(on[:8])]
    check(f"...while it recorded, each heard once as it was played (a moment late, as played), not again from the loop "
          f"({lates} ms after its beat)", len([t_ for t_, _ in on if t_ < c.at(first + 4)]) == 4)
    mark = log_at()
    until_t(c.at(first + 8 + 4))
    spin(0.1)
    on = [t_ for t_, _ in heard(mark)[0] if c.at(first + 8) - 0.1 < t_ < c.at(first + 12)]
    out = [round((t_ - c.at(first + 8 + k)) * 1000, 1) for k, t_ in enumerate(on)]
    check(f"...and the next time round, each on its very beat ({out} ms from it)",
          len(on) == 4 and all(abs(x) <= 4 for x in out))

    # without snapping, as it was played; its card's last row: that layer's gone
    m.set_setting("board_click", "On")
    m.set_setting("board_snap", "Off")
    tap("start")
    more_row = m.board_rows()[0][1]
    tap("a")
    c = b.clock
    beat = math.ceil(c.beat(time.monotonic())) + 1.3
    until_t(c.at(beat))
    tap("up")
    rec()
    pos = b.layers[-1][1][0][0] if len(b.layers) == 2 else None
    check(f"a loop there already: the row's {more_row!r}; snapping off: as it was played ({pos} of the loop's 8 beats, "
          f"played at {beat % 8:.2f})", more_row == "Add to the loop" and pos is not None
          and abs(pos - beat % 8) < 0.03)
    m.set_setting("board_snap", "On")
    m.press("select")
    spin(0.8)
    m.release("select")
    spin(0.1)
    check(f"SELECT held: the next bank, once, and nothing dropped ({b.bank()['name']}, {len(b.layers)} layers)",
          b.at == 2 and len(b.layers) == 2 and b.take is None and toasts[-1:] != ["The last layer's gone"])
    tap("select")
    tap("select")                                       # (Drums again)
    label = drop()
    spin(0.1)
    check(f"its card's last row, {label!r} (START, ▲, A): the last layer's gone, the card too ({len(b.layers)} layer, "
          f"{toasts[-1:]})", label == "Drop the last layer" and b.at == 1 and len(b.layers) == 1 and b.take is None
          and toasts[-1:] == ["The last layer's gone"] and m.sim_opts is None)
    rec()
    clicked = loops()[-1].get("click")
    tap("up")
    label = drop()
    check(f"...while one's recording (the click on, as it's set: {clicked}), {label!r}: that one's dropped with what "
          f"was played in it, the ones before kept ({toasts[-1:]})", label == "Drop this layer" and len(b.layers) == 1
          and b.take is None and clicked is True and toasts[-1:] == ["That layer's gone"])
    rec()
    rec()
    check("...and one stopped with nothing played in it: not kept", len(b.layers) == 1 and b.take is None)

    # notes: A held, and the d-pad
    told.clear()
    snare = b.bank()["pads"]["a"]
    m.press("a")
    tap("up")
    spin(0.05)
    together = [(c_.get("id"), c_.get("semis", 0)) for c_ in told if c_.get("do") == "play"]
    check(f"A, and the d-pad as it goes down (together, as drums are played): each its own sound, no notes "
          f"({together}, {m.sim_game().held_note})",
          together == [(snare, 0), (hat, 0)] and m.sim_game().held_note is None)
    m.release("a")
    told.clear()
    m.press("a")
    spin(SB.NOTE_HOLD + 0.1)
    names = [m.sim_game().held_note]
    plays = []
    for way in ("up", "up", "down", "right", "left") + ("up",) * 9:
        m.press(way)
        m.release(way)
        spin(0.03)
        names.append(m.sim_game().held_note[1])
    plays = [c_.get("semis", 0) for c_ in told if c_.get("do") == "play"]
    check(f"A held: its sound, then the d-pad plays it as notes of the scale (▲ a note higher, ▼ lower, ▶ again, ◀ its "
          f"own), the note on A's tile ({names})", names[0] == ("a", "C")
          and names[1:6] == ["D", "E", "D", "D", "C"] and names[-1] == "High C"
          and plays[:6] == [0, 2, 4, 2, 2, 0] and plays[-1] == 12 and max(plays) == 12
          and all(c_.get("id") == snare for c_ in told if c_.get("do") == "play"))
    page_note = flush()
    m.release("a")
    spin(0.05)
    page_none = flush()
    a = m.sim_game().boxes()["a"]
    box = (a[0] + a[2] - 70, 78 + a[1] + 4, a[0] + a[2] - 4, 78 + a[1] + 40)
    diff = int((np.abs(page_note[box[1]:box[3], box[0]:box[2]] - page_none[box[1]:box[3], box[0]:box[2]])
                .max(axis=2) > 60).sum())
    check(f"...let go of A: no more notes (the d-pad's its own again), and the note's off its tile ({diff} pixels)",
          m.sim_game().held_note is None and diff > 30)
    told.clear()
    tap("up")
    check("...the d-pad's own sound again",
          [c_ for c_ in told if c_.get("do") == "play"] == [{"do": "play", "id": hat}])
    rec()
    c = b.clock
    first = math.ceil(c.beat(time.monotonic())) + 1
    until_t(c.at(first))
    m.press("a")
    until_t(c.at(first + 1))
    m.press("up"); m.release("up")
    until_t(c.at(first + 2))
    m.press("up"); m.release("up")
    m.release("a")
    rec()
    got = sorted((h[0], h[2]) for h in b.layers[-1][1])
    check(f"...played while a layer records: in it, each its note ({got})",
          got == sorted([(float(first % 8), 0), (float((first + 1) % 8), 2), (float((first + 2) % 8), 4)]))

    # the page as it goes
    rec()
    spin(0.1)
    hue = dict(g.ACCENTS)

    def dot(pic, rgb):
        """Pixels of that colour where the loop's mark is (the page's top left)."""
        return int((np.abs(pic[78 + 6:78 + 34, 8:34] - np.array(rgb)).max(axis=2) <= 30).sum())

    red = dot(flush(), hue["Red"])
    s = m.sim_game()
    rec_line = s.loop
    rec()
    spin(0.1)
    green = dot(flush(), hue["Green"])
    s = m.sim_game()
    check(f"the page: recording, a red mark ({red} px), the beat and the bar ({rec_line}); playing, a green one "
          f"({green} px), how many layers ({s.loop}), the tempo at the right", rec_line["rec"] and not s.loop["rec"]
          and s.loop["layers"] == 2 and s.loop["bpm"] == 120 and 1 <= s.loop["beat"] <= 4 and 1 <= s.loop["bar"] <= 2
          and red >= 40 and green >= 40)
    n0 = FB.frames
    end = time.monotonic() + 2.0
    while time.monotonic() < end:                      # (media mode's own loop: a look, and drawn when that says so)
        m.tick()
        if m.dirty:
            m.flush()
        time.sleep(0.005)
    drawn = FB.frames - n0
    check(f"...drawn again once a beat, not more ({drawn} times in 2 s at 120 a minute)", 3 <= drawn <= 6)

    # START's card: the tempo, the loop's length, snapping, the click, the scale
    tap("start")
    m.sim_opts = at("tempo")
    for _ in range(3):
        m.press("right")
    tempo = (b.clock.bpm, m.setting("board_bpm"))
    m.sim_opts = at("bars")
    m.press("right")
    m.sim_opts = at("snap")
    m.press("right")
    m.sim_opts = at("click")
    m.press("left")
    m.sim_opts = at("scale")
    m.press("right")
    vals = [v for _, _, v in m.board_rows()[at("tempo"):at("scale") + 1]]
    check(f"START's card: ◀▶ change the tempo ({tempo}), the loop's length, snapping, the click and the scale ({vals})",
          tempo == (123, "123") and vals == ["123 BPM", "4 bars", "Off", "Off", "Minor"] and loops()[-1]["bpm"] == 123)
    for key in ("bars", "snap", "click", "scale"):
        k = m.sim_opts = at(key)
        while m.board_rows()[k][2] not in ("2 bars", "On", "Major"):
            m.press("right")
    m.sim_opts = at("space")
    m.press("right")
    m.press("right", repeat=True)
    m.press("left")
    space = [c for c in told if c.get("do") == "space"]
    check(f"...and Space, ◀▶ (held: on and on): the Soundboard's own sounds in a room, kept, its player told "
          f"({m.board_rows()[m.sim_opts][2]}, {space[-3:]})", m.setting("board_space") == "1"
          and [c["v"] for c in space[-3:]] == [0.1, 0.2, 0.1] and m.board_rows()[m.sim_opts][2] == "1")
    m.press("left")
    check(f"...back to Off ({m.board_rows()[m.sim_opts][2]})", m.board_rows()[m.sim_opts][2] == "Off"
          and m.setting("board_space") == "0")
    tap("start")

    # leaving it and coming back: the loop's still there
    had = [list(x) for x in b.layers]
    tap("start")
    m.sim_home()
    spin(0.5)
    left = not m.board_shown() and b.proc is None
    m.press("a")
    spin(3, lambda: b.proc is not None and len(b.ready) == 24)
    spin(0.3)
    check("back in Apps and in again: the loop's as it was, and its player's told it again",
          left and [list(x) for x in b.layers] == had and loops() and loops()[-1].get("hits"))

    # START held: the loop's cleared, and every sound stopped
    told.clear()
    m.press("start")
    spin(1.1)
    m.release("start")
    spin(0.1)
    check(f"START held: the loop's cleared, every sound stopped, and no card ({toasts[-1:]}); nothing to drop on its "
          f"card now ({m.board_rows()[0][1]!r} first, {m.board_rows()[-1][1]!r} last)",
          not b.layers and b.take is None and {"do": "loop"} in told and {"do": "stop"} in told
          and m.sim_opts is None and toasts[-1:] == ["Loop cleared"] and m.board_rows()[0][1] == "Record a loop"
          and m.board_rows()[-1][0] == "space")

    # the beat shared with another of yours
    other = BL.Link("pie-den", "127.0.0.2", BL.BEAT_PORT)
    theirs = BL.Clock(90, 7.0, time.monotonic() - 1, 3, time.monotonic() - 50, "pie-den")
    m.saves_peers = lambda addr=None: [("http://127.0.0.2:5432", "Den")]
    end = time.monotonic() + 3
    while time.monotonic() < end and b.clock.bpm != 90:
        theirs = other.tick(theirs, ["127.0.0.3"])
        spin(0.05)
    now = time.monotonic()
    check(f"another of yours with its Soundboard open: this one takes its beat ({b.clock.bpm:.0f} a minute, "
          f"{abs(b.clock.beat(now) - theirs.beat(now)) * 1000:.1f} thousandths of a beat apart)",
          b.clock.bpm == 90 and abs(b.clock.beat(now) - theirs.beat(now)) < 0.005)
    web = m.board_web_loop()
    check(f"...the web page's told so: the tempo's the shared one, and in time with whom, by name ({web['bpm']}, "
          f"{web['with']})", web["bpm"] == 90 and web["with"] == ["Den"] and web["open"] is True)
    tap("start")
    m.sim_opts = at("tempo")
    m.press("left")
    tap("start")
    end = time.monotonic() + 2
    while time.monotonic() < end and theirs.bpm != 89:
        theirs = other.tick(theirs, ["127.0.0.3"])
        spin(0.05)
    check(f"...a new tempo here: it has it too ({theirs.bpm:.0f})", theirs.bpm == 89)
    other.close()
    m.saves_peers = lambda addr=None: []
    spin(1.5)
    check(f"...it closes its Soundboard: this one goes on with the same beat, in time with nobody now "
          f"({m.board_web_loop()['with']})", b.clock.bpm == 89 and m.board_web_loop()["with"] == [])
    m.press("b")
    spin(0.3)
    m.leave()

# ---- the beat, shared: two Pietatos' ends of it, on one machine (each at an address of its own) ------------------
if not ONLY or "link" in ONLY:
    import pitato.beatlink as BL
    PORT = 25450
    far = 1000.0                                       # (the other one's clock: a thousand seconds on from this one's)
    A = BL.Link("pie-a", "127.0.0.2", PORT)
    Bk = BL.Link("pie-b", "127.0.0.3", PORT, clock=lambda: time.monotonic() + far)
    ca = BL.Clock.new(100, time.monotonic() - 30, "pie-a")              # (A: open half a minute already)
    cb = BL.Clock.new(140, time.monotonic() + far, "pie-b")             # (B: just opened, by its own clock)

    def run(secs, a_peers=("127.0.0.3",), b_peers=("127.0.0.2",)):
        global ca, cb
        end = time.monotonic() + secs
        while time.monotonic() < end:
            ca = A.tick(ca, a_peers) if A is not None else ca
            cb = Bk.tick(cb, b_peers) if Bk is not None else cb
            time.sleep(0.05)

    def apart():
        """How far apart the two beats are, in beats, at the same moment."""
        now = time.monotonic()
        return abs(ca.beat(now) - cb.beat(now + far))

    run(2.5)
    check(f"two Soundboards open, one for half a minute, one just now: the new one takes the other's beat, its tempo "
          f"and where it is, though its clock's a thousand seconds on ({cb.bpm:.0f} a minute, {apart() * 1000:.1f} "
          f"thousandths of a beat apart); the one playing already keeps its own ({ca.bpm:.0f})",
          cb.bpm == 100 and ca.bpm == 100 and apart() < 0.004 and ca.who == "pie-a" and A.with_whom(time.monotonic())
          == ["127.0.0.3"])
    ca = ca.retimed(120, time.monotonic(), "pie-a")
    A.say_now()
    run(1.5)
    check(f"...a new tempo on the first: the other has it, from the same beat ({cb.bpm:.0f}, {apart() * 1000:.1f} "
          f"thousandths apart)", cb.bpm == 120 and apart() < 0.004)
    cb = cb.retimed(90, time.monotonic() + far, "pie-b")
    Bk.say_now()
    run(1.5)
    check(f"...and one on the second: the first has that ({ca.bpm:.0f}, {apart() * 1000:.1f} thousandths apart)",
          ca.bpm == 90 and apart() < 0.004 and ca.rev == 2)
    cb = BL.Clock(cb.bpm, cb.b0 + 0.05, cb.t0, cb.rev, cb.set, cb.who)  # (the second's slipped a twentieth of a beat)
    run(1.5)
    check(f"...one slipped out of step: put right by what the one that set the beat says ({apart() * 1000:.1f})",
          apart() < 0.004)
    stranger = BL.Link("pie-x", "127.0.0.4", PORT)
    win = BL.Clock(200, 0, time.monotonic(), 9, time.monotonic() - 99, "pie-x")
    for _ in range(10):
        stranger.tick(win, ["127.0.0.2"])
        stranger.say_now()
        A.sock.sendto(b"not json", ("127.0.0.3", PORT))
        A.sock.sendto(json.dumps({"k": "pietato-beat", "bpm": "fast"}).encode(), ("127.0.0.3", PORT))
        run(0.1)
    stranger.close()
    check(f"...a Pietato that isn't one of yours says a beat that'd win; nonsense comes: neither changes "
          f"({ca.bpm:.0f})",
          ca.bpm == 90 and cb.bpm == 90)
    was = (ca.bpm, ca.b0, ca.t0)
    Bk.close()
    Bk = None
    run(GONE_WAIT := 1.5, b_peers=())
    check("...the second closes its Soundboard: the first goes on with the beat as it was",
          (ca.bpm, ca.b0, ca.t0) == was)
    old = BL.Clock.new(100, 50.0, "pie-z")
    new = BL.Clock.new(100, 60.0, "pie-a")
    tie = BL.Clock.new(100, 50.02, "pie-a")
    check("which beat wins: changed more times; else the one set first; set at once, the lower word",
          new.retimed(90, 61.0).wins(old) and old.wins(new) and not new.wins(old) and tie.wins(old)
          and not old.wins(tie))
    A.close()

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
sys.exit(0 if all(ok_all) else 1)
