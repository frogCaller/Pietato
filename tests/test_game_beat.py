"""Game beat on Now playing (beatgame.py). The floor on its own: the screen's size whatever it is (drawn at a part of
it on a big one); zombies in waves on the strong beats, never two waves running, never more than GAME_MOST, cleared
as it goes; notes thrown on the other beats, each its own colour, in the air over the next beat and landing on the one
after; the zombies plain balls in soft colours (no eyes, no arms), glowing brighter on the beat, the notes too; a
zombie that gets to the dancer cleared all the same; nothing moving while paused; a station's beats found in its bars;
a note whose zombie's gone landing all the same. Then in media mode: SELECT goes round the lofi art, Game beat and
back (kept for next time); on a Pi Zero 2 W or a Pi 3 just the lofi art and back, and Game beat kept from before not
shown there; the whole screen the floor, what's playing at its top, how far through along its foot and how many
cleared; its beats the ear's; GAME_FPS frames a second (Now playing's bars not drawn meanwhile, its ear kept), but no
more than two thirds of the time spent drawing them; none while it's paused (the screen free to rest then); a
station's too; none off Now playing. The zombies keep their distance from the dancer (KEEP), slowing as they come."""
import collections, io, math, os, shutil, sys, threading, types
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import numpy as np
import pietato_all as g
from pitato import beatgame as BG

S = SP + "/tgame"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + "/home/u/Music")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: S + "/home/u"
g.wifi_quality = lambda: 62.0
g.cpu_temp = lambda: 48.0
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


SPB = 60 / 124                                         # (a song at 124 a minute)
ACC = (96, 170, 228)                                   # (an accent with no red in it: none of the old red eyes)


def bars_at(t):
    ph = (t % SPB) / SPB
    return [max(0.0, 0.9 * math.exp(-ph * 5) - k * 0.02) for k in range(32)]


def zombie(x, y, hue=4, r=13.0, sp=0.0, born=-5.0):
    return {"x": x, "y": y, "r": r, "hp": 1, "k": "walk", "hit": 0.0, "a": 0.0, "ph": 0.0, "born": born, "sp": sp,
            "marked": 0, "hue": hue}


# ---- the floor on its own -----------------------------------------------------------------------------------
game = BG.BeatGame("/m/song.mp3", seed=5)
fits = {}
for W, H in ((640, 480), (800, 480), (1280, 720), (1920, 1080), (480, 640), (720, 720)):
    img = game.frame(W, H, 1.0, (), False, ACC)
    w, h, k = BG.game_size(W, H)
    fits[(W, H)] = (img.size == (W, H) and img.mode == "RGB" and min(w, h) < 2 * BG.GAME_LINES and w * k >= W
                    and h * k >= H, (w, h, k))
check(f"the screen's size whatever it is, drawn at a part of it on a big one ({[v[1] for v in fits.values()]})",
      all(v[0] for v in fits.values()) and fits[(1920, 1080)][1][2] == 3 and fits[(640, 480)][1][2] == 1)

game = BG.BeatGame("/m/song.mp3", seed=7)
acted, most, thrown, landed, hues, volleys, nearest = [], 0, {}, [], set(), [], 1e9
air = {}
nb = 0
for f in range(40 * 15):
    t = f / 15
    while nb * SPB <= t:
        n_was = len(game.notes)
        game.beat(nb * SPB, 0.9 if nb % 2 == 0 else 0.4, t)
        if game.size is not None:
            acted.append(game.last)
        fresh = game.notes[n_was:]
        if fresh:
            volleys.append([b["hue"] for b in fresh])
        for b in fresh:
            thrown[id(b)] = nb * SPB
            air[id(b)] = b
        nb += 1
    game.frame(640, 480, t, bars_at(t), False, ACC, progress=min(1.0, t / 60))
    most = max(most, len(game.zombies))
    hues |= {z["hue"] for z in game.zombies}
    nearest = min([nearest] + [math.hypot(z["x"] - 320, z["y"] - 240) - z["r"] for z in game.zombies])
    now_in = {id(b) for b in game.notes}
    for key in [k for k in air if k not in now_in]:
        landed.append((thrown[key], t))
        del air[key]
spawns = acted.count("spawn")
twice = any(a == b == "spawn" for a, b in zip(acted, acted[1:]))
check(f"zombies come in waves on the strong beats ({spawns} of {len(acted)} beats), never two waves running",
      len(acted) > 70 and 0.3 * len(acted) < spawns <= 0.5 * len(acted) + 1 and not twice)
check(f"never more than {BG.GAME_MOST} on the floor ({most}); cleared as it goes ({game.kills} in 40 s)",
      0 < most <= BG.GAME_MOST and game.kills > 40)
check(f"...none nearer the dancer than {BG.KEEP} px (the nearest's edge {nearest:.1f} px from it)",
      BG.KEEP - 2 <= nearest < BG.KEEP + 30)
late = [round(land - (at + 2 * SPB), 3) for at, land in landed if at > 5]
check(f"notes thrown on the other beats land {BG.NOTE_BEATS} beats on, so in the air over the next one "
      f"({len(late)} landed, {min(late, default=0)} to {max(late, default=0)} s after that beat)",
      len(late) > 40 and all(0 <= x < 1 / 15 + 0.002 for x in late))
mixed = [v for v in volleys if len(v) > 1]
check(f"each note its own colour ({len(mixed)} throws of two or more, their colours all different)",
      mixed and all(len(set(v)) == min(len(v), len(BG.NOTE_HUES)) for v in mixed)
      and all(0 <= h < len(BG.NOTE_HUES) for v in volleys for h in v))
check(f"the zombies in soft colours, many of them ({len(hues)} of {len(BG.PASTELS)})",
      len(hues) >= 5 and all(0 <= h < len(BG.PASTELS) for h in hues)
      and all(min(c) >= 160 for c in BG.PASTELS))

one = BG.BeatGame("/m/one.mp3", seed=1)
one.frame(640, 480, 10.0, (), True, ACC)
one.beat_at = 10.0 - 0.45
empty = np.asarray(one.frame(640, 480, 10.0, (), True, ACC)).astype(int)
one.zombies = [zombie(480.0, 240.0)]
off = np.asarray(one.frame(640, 480, 10.0, (), True, ACC)).astype(int)
one.beat_at = 10.0 - 0.01
on = np.asarray(one.frame(640, 480, 10.0, (), True, ACC)).astype(int)
ys, xs = np.mgrid[0:480, 0:640]
d = np.hypot(xs - 480, ys - 240)
inside = off[d < 13 * 0.75]
edge = (d > 15) & (d < 20)
halo = (d > 13 * 1.2) & (d < 13 * 1.8)
red = [int(((a[..., 0] > 200) & (a[..., 1] < 80) & (a[..., 2] < 80)).sum()) for a in (off, on)]
check(f"a zombie: a plain ball in its colour (one colour across it: {inside.std(axis=0).round(1).tolist()}), "
      f"no red eyes ({red} px), no arms (nothing darker than the floor round it)",
      inside.std(axis=0).max() < 3 and np.abs(inside.mean(axis=0) - BG.PASTELS[4]).max() < 14 and red == [0, 0]
      and (off[edge].sum(axis=1) >= empty[edge].sum(axis=1) - 3).all())
check(f"...glowing brighter on the beat ({on[halo].mean():.0f} round it, {off[halo].mean():.0f} between beats)",
      on[halo].mean() > off[halo].mean() + 8 and off[halo].mean() > empty[halo].mean() + 3)

one.zombies = []
one.notes = [{"x0": 320.0, "y0": 232.0, "x": 200.0, "y": 150.0, "s": 0.5, "time": 1.0, "at": 0.0, "tgt": None,
              "tx": 100.0, "ty": 100.0, "bend": 0.2, "lift": 20.0, "hue": 4, "vx": 0.0, "vy": 0.0,
              "tr": collections.deque(maxlen=7)}]
one.beat_at = 10.0 - 0.45
off = np.asarray(one.frame(640, 480, 10.0, (), True, ACC)).astype(int)
one.beat_at = 10.0 - 0.01
on = np.asarray(one.frame(640, 480, 10.0, (), True, ACC)).astype(int)
d = np.hypot(xs - 200, ys - 150)
left = (xs < 200 - 7) & (d > 9) & (d < 17)
head = off[154, 200]
check(f"a note in the air: in its colour ({head.tolist()}, of {BG.NOTE_HUES[4]}), glowing round it, brighter on "
      f"the beat ({on[left].mean():.0f} to {off[left].mean():.0f})",
      head[2] > head[0] + 40 and on[left].mean() > off[left].mean() + 6 and off[left].mean() > empty[left].mean() + 3)

still = BG.BeatGame("/m/still.mp3", seed=3)
still.frame(640, 480, 0.0, (), False, ACC)
still.zombies = [zombie(420.0, 240.0, sp=40.0)]
still.fire(0.0, 0.0)
still.zombies.append(zombie(100.0, 100.0, sp=40.0))
was = [(z["x"], z["y"]) for z in still.zombies] + [(b["x"], b["y"], b["s"]) for b in still.notes]
for k in range(1, 10):
    still.frame(640, 480, k / 15, bars_at(k / 15), True, ACC)
now = [(z["x"], z["y"]) for z in still.zombies] + [(b["x"], b["y"], b["s"]) for b in still.notes]
check("paused: nothing moves", was == now and len(still.notes) == 1)
still.frame(640, 480, 0.8, bars_at(0.8), False, ACC)
check("...and on again, on from where it was (no jump)", still.notes and 0 < still.notes[0]["s"] < 0.2)

near = BG.BeatGame("/m/near.mp3", seed=2)
near.frame(640, 480, 0.0, (), False, ACC)
near.zombies = [zombie(340.0, 240.0, sp=30.0)]
near.frame(640, 480, 0.05, (), False, ACC)
check(f"a zombie that gets to the dancer is cleared all the same ({near.kills} cleared, {len(near.zombies)} left)",
      near.kills == 1 and not near.zombies)

lost = BG.BeatGame("/m/lost.mp3", seed=4)
lost.frame(640, 480, 0.0, (), False, ACC)
z = zombie(420.0, 240.0, hue=1)
lost.zombies = [z]
lost.fire(0.0, 0.0)
thrown_n, colour = len(lost.notes), BG.NOTE_HUES[lost.notes[0]["hue"]] if lost.notes else None
lost.zombies.remove(z)
for k in range(1, 30):
    lost.frame(640, 480, k / 15, (), False, ACC)
    if not lost.notes:
        break
check(f"a note whose zombie's gone lands all the same, in a little burst of its colour ({thrown_n} thrown)",
      thrown_n == 1 and not lost.notes and z["marked"] == 0 and any(p[6] == colour for p in lost.bits))

station = BG.BeatGame("http://radio.example/live", seed=6)
station.frame(640, 480, 0.0, (), False, ACC)
for f in range(8 * 15):
    t = f / 15
    ph = (t % 0.5) / 0.5
    levels = [0.85 * math.exp(-ph * 6)] * 4 + [0.3] * 28
    station.hear(levels, t)
    station.frame(640, 480, t, levels, False, ACC)
check(f"a station: its beats found in its bars, its bass rising (16 in 8 s: {station.beats})",
      14 <= station.beats <= 17)


# ---- in media mode ------------------------------------------------------------------------------------------
class FB:
    w, h, same = 640, 480, True

    def __init__(self):
        self.last, self.shows = None, 0

    def show(self, img):
        self.last = img.copy(); self.shows += 1

    def show_part(self, img, box):
        self.show(img)

    def close(self):
        pass


class Ear:
    """A song's ear, as Now playing has it (ear.py): its beats by their place in the song, its bars there."""
    def __init__(self, src, beats):
        self.src, self.lock, self.closed = src, threading.Lock(), False
        self.beats = collections.deque(beats)

    def levels(self, place):
        return tuple(bars_at(place or 0.0))

    def level(self, place):
        return 0.0

    def close(self):
        self.closed = True


fake = [1000.0]
g.time.monotonic = lambda: fake[0]
m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.status_sig = m.status_signature()
music = next(i for i, t in enumerate(g.LIBRARY) if t["name"] == "Music")
items = [{"title": f"Song {k}", "src": f"{S}/home/u/Music/song{k}.mp3", "sub": "", "kind": "audio"} for k in range(3)]
m.to_player = lambda line: None
m.queue, m.qi, m.cur, m.kind = items, 0, items[0], "audio"
m.proc = types.SimpleNamespace(poll=lambda: None, stdin=io.StringIO())
m.meta = {"title": "Harbour Lights", "artist": "Someone", "length": 200}
m.pos = 50
m.tab, m.view, m.now_from = music, "now", "list"
m.heard_now = lambda: 9.9 + (fake[0] - 1000.0)       # (the song heard as the clock goes)
ear = Ear(items[0]["src"], [(10.0 + 0.5 * k, 0.9 if k % 2 == 0 else 0.4) for k in range(60)])
m.ear = ear
m.bars_fit = True
m.dirty = True
m.flush()
plain = m.fb.last

m.press("select")
said1 = m.msg
m.press("select")
said2 = m.msg
check(f"SELECT: the lofi art ({said1!r}), then Game beat ({said2!r}), kept for next time",
      m.setting("now_art") == "Game" and m.now_game() and not m.now_art() and "SELECT for Game beat" in (said1 or "")
      and "Game beat" in (said2 or "") and g.Media().setting("now_art") == "Game")
places, glows = [], []
real_render = m.render_game


def render_game():
    places.append(m.heard_now())
    real_render()


m.render_game = render_game
m.pulse_frame = lambda: glows.append(1)
m.msg = None
m.dirty = True
m.flush()
m.fb.shows = 0
waits, tooks = [], []
while fake[0] < 1002.0 - 1e-9:                         # (two seconds, the loop waiting as it's told)
    tooks.append(m.game_took)
    m.tick()
    m.flush()
    waits.append(m.tick_limit())
    fake[0] += max(0.004, waits[-1])
shot = m.fb.last
shot.save(SP + "/game_beat.png")
check(f"...{m.fb.shows / 2:.1f} frames a second ({BG.GAME_FPS}), the loop waiting no longer than the next "
      f"({max(waits):.3f} s); Now playing's bars not drawn meanwhile ({len(glows)}), its ear kept",
      BG.GAME_FPS - 1 <= m.fb.shows / 2 <= BG.GAME_FPS + 1
      and all(w <= max(1 / BG.GAME_FPS, 1.5 * t) + 0.001 for w, t in zip(waits, tooks))
      and not glows and m.ear is ear and not ear.closed)
a = np.asarray(shot).astype(int)
bg = (a[440:470, 300:600] == np.array(g.BG)).all(axis=2).mean()
check(f"...the whole screen the floor: no status bar, no buttons ({bg:.3f} of the foot the page's colour)",
      bg < 0.01 and tuple(a[4, 320]) != g.BG)
check("...what's playing at its top", (a[12:32, 18:200].max(axis=2) > 200).sum() > 40)
x = int(640 * m.pos / 200)
check(f"...how far through it is along its foot ({m.pos / 200:.0%}), how many cleared at its corner",
      np.abs(a[478, x - 6] - np.array(g.on_dark("ACCENT"))).max() < 30
      and np.abs(a[478, x + 30] - np.array(g.on_dark("LINE"))).max() < 30
      and (a[452:466, 520:630].max(axis=2) > 100).sum() > 20)
passed = sum(1 for p, _ in ear.beats if 9.9 < p <= places[-1])
check(f"...its beats the ear's (the {passed} it's passed: {m.beat_game.beats}), zombies coming "
      f"({len(m.beat_game.zombies)})", passed == m.beat_game.beats == 4 and m.beat_game.zombies)
fake[0] = m.game_next
m.game_took = 0.1
m.tick()
check(f"...a frame that took a tenth of a second to draw: the next no sooner than 0.15 s on ({m.tick_limit():.2f} s)",
      0.14 < m.tick_limit() <= 0.16)
m.flush()
check("the screen doesn't rest while it plays", m.worth_watching(fake[0]))
m.press("a")
m.dirty = True
m.flush()
m.fb.shows = 0
for _ in range(20):
    fake[0] += 0.05
    m.tick()
    m.flush()
check(f"A: paused, no more frames ({m.fb.shows}), the loop back to its usual wait ({m.tick_limit():.2f} s), "
      "the screen free to rest", m.paused and m.fb.shows <= 1 and m.tick_limit() >= 0.2
      and not m.worth_watching(fake[0]))
m.press("a")
m.press("select")
check("SELECT again: Now playing as it was", m.setting("now_art") == "Off" and not m.now_game() and not m.now_art())

m.bars_fit = False
m.press("select")
said1 = m.msg
m.press("select")
check(f"on a Pi Zero 2 W or a Pi 3: SELECT the lofi art ({said1!r}) and back, no Game beat",
      m.setting("now_art") == "Off" and "SELECT to leave it" in (said1 or "") and "Game" not in (said1 or ""))
m.set_setting("now_art", "Game")
m.msg = None
m.dirty = True
m.flush()
there = m.fb.last
check("...Game beat kept from before not shown there: Now playing as it is",
      not m.now_game() and there.getpixel((320, 470)) == g.BG and np.array_equal(np.asarray(there)[440:],
                                                                                  np.asarray(plain)[440:]))
m.press("select")
check("...SELECT from it: Now playing", m.setting("now_art") == "Off")

m.bars_fit = True
m.set_setting("now_art", "Game")
m.kind, m.cur = "radio", {"title": "Night FM", "src": "http://radio.example/stream", "sub": "Jazz", "kind": "radio"}
m.meta = {"song": "Some Tune"}
m.ear = None
m.proc = types.SimpleNamespace(poll=lambda: None, stdin=io.StringIO(), shares_sound=True)


class Tap:
    def levels(self, now, gain):
        ph = (now % 0.5) / 0.5
        return tuple([0.85 * math.exp(-ph * 6)] * 4 + [0.3] * 28)


m.sound_tap = Tap()
m.beat_game = None
for _ in range(80):
    fake[0] += 0.05
    m.tick()
    m.flush()
check(f"a station too: its beats from its bars ({m.beat_game.beats} in 4 s), no line along the foot (it's live)",
      7 <= m.beat_game.beats <= 9 and m.beat_game.song == "http://radio.example/stream"
      and np.abs(np.asarray(m.fb.last)[478, 320].astype(int) - np.array(g.on_dark("LINE"))).max() > 10)
m.press("b")
m.dirty = True
m.flush()
m.fb.shows = 0
for _ in range(10):
    fake[0] += 0.05
    m.tick()
    m.flush()
check(f"off Now playing: no frames ({m.fb.shows}), the usual wait", m.fb.shows == 0 and m.tick_limit() == 0.25
      and m.setting("now_art") == "Game")
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
