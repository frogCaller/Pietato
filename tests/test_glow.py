"""TV backlight (pitato/glow.py, screens/glow.py, and the emulator's part): an LED grid behind the TV, lit by your
Pietatos' games and music. First the pieces on their own: what's sent (a picture's colours, something happening, music's
colour; anything else not taken); a picture's edges (RGB565, 0RGB1555 and XRGB8888 pictures, one with a pitch wider than
it); a hit from a game's rich presence (lives or health going down; not a timer or a score); beats in music, as they're
heard (a kick drum, loud or quiet; none in a steady hum or silence); the LEDs' bits through SPI; the grid itself (only
your Pietatos, the one it follows; a hit's red, an achievement's gold and a beat, when they're due by the sender's clock;
dark once it's quiet; how bright; turned, mirrored and in zigzag rows; dark as it's shut), over real UDP too; and
config.txt's lines for SPI. Then the emulator's part (a pretend screen): told where its colours go, each picture's edges
sent (30 a second at most; one the graphics chip drew, from the screen), an achievement's gold, a controller shaken and
lives going down: a hit. Then media mode: Settings > TV backlight (the grid on: SPI's lines into config.txt and a
restart asked for; its settings applied), the beacon saying it's there, your grids found (where a game's colours go,
said to its emulator), and music played through party mode's player for the beat: the grid pulsing as each kick drum's
heard, music's colour between, pause and seek as mplayer takes them, and a station passed through here for its song's
names. Pulse to music off, or no grid: music as ever (mplayer)."""
import os, shutil, subprocess, sys, threading, time, wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
real_run = subprocess.run                              # (FFmpeg, to make a station's sound: the test stands in for the rest)
from paths import SP, TESTS  # noqa: E402  (this test's folder of work; tests)
sys.path.insert(0, TESTS)
import numpy as np
import pietato_all as g
import pitato.glow as G
import pitato.emulator as E

S = SP + "/t_glow"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/gpi"
for d in ("Music", "Videos", "Pictures", "Documents", "Games/Saves"):
    os.makedirs(f"{HOME}/{d}")
os.makedirs(S + "/bin")
ok_all = []
RATE = 48000


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def until(cond, secs=5.0):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


# ---- what's sent --------------------------------------------------------------------------------------------------------
c = np.arange(192, dtype=np.uint8).reshape(8, 8, 3)
p = G.read_packet(G.frame_packet(c, 12.5))
check("a picture's colours: as they were sent", p["kind"] == "frame" and p["sent"] == 12.5
      and np.array_equal(p["colours"], c))
p = G.read_packet(G.event_packet("hit", 0.5, 13.0, 12.9))
check(f"...something happening: what, how hard, when ({p})", p["kind"] == "event" and p["name"] == "hit"
      and abs(p["strength"] - 0.5) < 0.01 and p["at"] == 13.0 and p["sent"] == 12.9)
p = G.read_packet(G.music_packet((96, 170, 228), 14.0))
check("...music's colour", p["kind"] == "music" and p["rgb"].tolist() == [96, 170, 228])
check("anything else: not taken", all(G.read_packet(x) is None for x in (
    b"", b"junk", G.event_packet("boom", 1, 1, 1), G.frame_packet(c, 1)[:-1], b"PG\x02F" + bytes(20),
    G.frame_packet(c, float("nan")))))
check("where a game's colours go, as media mode says it",
      G.targets(["10.0.0.7:5448", "127.0.0.1:5448", "-", "bad", "x:99999", ":5"]) == [("10.0.0.7", 5448),
                                                                                     ("127.0.0.1", 5448)])

# ---- a picture's edges --------------------------------------------------------------------------------------------------
H, W = 224, 256
RED, GREEN, BLUE, YELLOW = (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)
pic = np.zeros((H, W, 3), dtype=np.uint8)
pic[:, :int(W * .2)] = GREEN
pic[:, -int(W * .2):] = YELLOW
pic[:int(H * .2)] = RED
pic[-int(H * .2):] = BLUE


def as565(rgb):
    r, gg, b = (rgb[..., k].astype(np.uint16) for k in range(3))
    return ((r >> 3) << 11) | ((gg >> 2) << 5) | (b >> 3)


def as555(rgb):
    r, gg, b = (rgb[..., k].astype(np.uint16) for k in range(3))
    return ((r >> 3) << 10) | ((gg >> 3) << 5) | (b >> 3)


def as888(rgb):
    return (rgb[..., 0].astype(np.uint32) << 16) | (rgb[..., 1].astype(np.uint32) << 8) | rgb[..., 2]


wide = np.zeros((H, 320), dtype=np.uint16)             # (a pitch wider than the picture, as a core's can be)
wide[:, :W] = as565(pic)
edges = G.Edges()
got = {name: edges.colours(a, rgb) for name, a, rgb in (("565", wide[:, :W], G.rgb565), ("555", as555(pic), G.rgb555),
                                                         ("888", as888(pic), G.rgb888))}


def near(a, b, tol=12):
    return all(abs(int(x) - int(y)) <= tol for x, y in zip(a, b))


for name, col in got.items():
    check(f"{name}: the grid's top row from the picture's top edge, its bottom from the bottom ({col[0].tolist()[:2]}, "
          f"{col[7].tolist()[:2]})", all(near(col[0, k], RED) for k in range(8))
          and all(near(col[7, k], BLUE) for k in range(8)))
    check(f"...its sides from the sides ({col[3, 0].tolist()}, {col[4, 7].tolist()})",
          all(near(col[r, 0], GREEN) and near(col[r, 7], YELLOW) for r in range(2, 6)))
    inner = col[2:6, 2:6].astype(int)
    check(f"...the ones inside blended from the nearest ({col[3, 2].tolist()}, {col[3, 5].tolist()})",
          inner.sum() > 0 and col[3, 2, 1] > col[3, 5, 1] - 30 and col[3, 2, 0] < col[3, 5, 0]
          and inner.max() < 255 * G.INSIDE + 2)
check("each picture format: the same colours", np.abs(got["565"].astype(int) - got["888"].astype(int)).max() <= 12
      and np.abs(got["555"].astype(int) - got["888"].astype(int)).max() <= 12)
t = time.perf_counter()
for _ in range(200):
    edges.colours(wide[:, :W], G.rgb565)
each = (time.perf_counter() - t) / 200 * 1000
check(f"...quick: a picture's colours in {each:.2f} ms", each < 2.0)
small = edges.colours(np.full((3, 2), 0xFFFF, dtype=np.uint16), G.rgb565)
check("a tiny picture: fine", small.shape == (8, 8, 3) and small[0, 0].tolist() == [255, 255, 255])

# ---- a hit, from a game's rich presence ---------------------------------------------------------------------------------
hw = G.HitWatch()
said = [(text, hw.take(text)) for text in (
    "Mario in World 1-1 | Lives: 3", "Mario in World 1-2 | Lives: 3", "Mario in World 1-2 | Lives: 2",
    "Link in Hyrule ❤️x5 | Rupees 20", "Link in Hyrule ❤️x4 | Rupees 10", "Link in Hyrule ❤️x6 | Rupees 0",
    "Time 300 | Score 1200", "Time 299 | Score 900", "3 lives left", "2 lives left", "HP 12/20", "HP 10/20",
    "♥♥♥♡", "♥♥♡♡", "In a menu", "HP 9/20")]
hits = [text for text, h in said if h]
check(f"a hit: lives or health going down ({hits})", hits == ["Mario in World 1-2 | Lives: 2",
                                                              "Link in Hyrule ❤️x4 | Rupees 10", "2 lives left",
                                                              "HP 10/20", "♥♥♡♡"])
check("...a life lost: harder than health", dict(said)["Mario in World 1-2 | Lives: 2"] == 1.0
      and dict(said)["HP 10/20"] < 1.0)

# ---- beats ---------------------------------------------------------------------------------------------------------------


def kicks(secs, every=0.5, first=0.5, hum=0.05, seed=1):
    """A kick drum each `every` seconds (and a tune's hum and some hiss), as samples (-1 to 1)."""
    tt = np.arange(int(RATE * secs)) / RATE
    sig = np.zeros_like(tt)
    for b in np.arange(first, secs, every):
        m = (tt >= b) & (tt < b + 0.25)
        x = tt[m] - b
        sig[m] += 0.6 * np.sin(2 * np.pi * (60 + 40 * np.exp(-x * 30)) * x) * np.exp(-x * 12)
    sig += hum * np.sin(2 * np.pi * 440 * tt) + 0.02 * np.random.default_rng(seed).standard_normal(len(tt))
    return sig, np.arange(first, secs, every)


sig, beats = kicks(8)
for vol in (1.0, 0.05):
    found = []
    B = G.Beats(RATE, lambda when, s: found.append(when))
    pcm = (np.stack([sig, sig], -1) * vol * 32767).astype("<i2")
    for k in range(0, len(pcm), 960):                  # (20 ms at a time, as the player writes it)
        B.feed(pcm[k:k + 960].tobytes(), 100.0 + k / RATE)
    errs = [min(abs(w - 100.0 - b) for b in beats) for w in found]
    check(f"beats, {'loud' if vol == 1 else 'quiet'}: each kick drum's, as it's heard ({len(found)} of {len(beats)}, "
          f"the furthest out {max(errs) * 1000:.0f} ms)", len(found) >= len(beats) - 1 and max(errs) < 0.025)
found = []
B = G.Beats(RATE, lambda when, s: found.append(when))
hum = (np.stack([0.3 * np.sin(2 * np.pi * 80 * np.arange(RATE * 4) / RATE)] * 2, -1) * 32767).astype("<i2")
for k in range(0, len(hum), 960):
    B.feed(hum[k:k + 960].tobytes(), k / RATE)
B.feed(bytes(4 * RATE), 10.0)
check(f"...none in a steady hum, or silence ({found})", found == [])

# ---- the LEDs' bits -----------------------------------------------------------------------------------------------------
grb = bytes(range(192))
check("an LED's bytes as SPI sends them, three bits each of theirs: back as they were",
      G.from_spi(G.spi_bytes(grb)) == grb and G.spi_bytes(b"\x80")[0] == 0b11010010)
OUT = S + "/spi"
open(OUT, "wb").close()


def last_lit(path=OUT):
    """What the grid last sent the LEDs: (rows x cols x 3) green, red, blue, in the order they're wired."""
    data = open(path, "rb").read()
    n = 8 * 8 * 3 * 3
    chunk = data[-(n + len(G.RESET)):-len(G.RESET)]
    return np.frombuffer(G.from_spi(chunk), dtype=np.uint8).reshape(8, 8, 3)


# ---- the grid -----------------------------------------------------------------------------------------------------------
class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


clk = Clock()
names = {"10.0.0.7": "Living room", "10.0.0.8": "Bedroom", "127.0.0.1": G.THIS_ONE}
grid = G.Grid(G.Strip(OUT), names.get, clock=clk, listen=False, run=False)
grid.bright, grid.mirror = 1.0, False
SENDER = -100.0                                        # (the sender's clock: 100 s behind this one's)


def send(packet_of, ip, *a, late=0.0):
    """A packet from ip, as it's sent now (its clock), heard `late` seconds after."""
    return grid.take(packet_of(*a, clk.t + SENDER), ip, clk.t + late)


def settle(secs, step=1 / 60):
    img = None
    for _ in range(int(secs / step)):
        clk.t += step
        img = grid.render(clk.t)
    return img


red = np.zeros((8, 8, 3), dtype=np.uint8)
red[...] = RED
check("not one of yours: not taken", not send(G.frame_packet, "10.9.9.9", red))
check("one of yours: taken", send(G.frame_packet, "10.0.0.7", red))
img = settle(0.3)
check(f"...its colours on the grid, smoothly ({img[0, 0].round().tolist()})", near(img[0, 0], RED, 3))
grid.follow = "Bedroom"
check("following one of yours by name: another's not taken", not send(G.frame_packet, "10.0.0.7", red))
grid.follow = G.ANY
blue = np.zeros((8, 8, 3), dtype=np.uint8)
blue[...] = BLUE
send(G.frame_packet, "10.0.0.7", red)
check("following whichever's playing: another's not taken while the first goes on",
      not send(G.frame_packet, "10.0.0.8", blue))
clk.t += G.HOLD + 0.1
check("...the first quiet a moment: the other's taken", send(G.frame_packet, "10.0.0.8", blue)
      and grid.source == "10.0.0.8")
img = settle(0.3)
send(G.event_packet, "10.0.0.8", "hit", 1.0, clk.t + SENDER)
img = grid.render(clk.t)
check(f"a hit: red, at once ({img[0, 0].round().tolist()})", img[0, 0, 0] > 200 and img[0, 0, 2] < 60)
img = settle(G.HIT_SECS + 0.1)
check(f"...and gone ({img[0, 0].round().tolist()})", near(img[0, 0], BLUE, 6))
for _ in range(5):                                     # (a few packets: the clocks' difference worked out)
    send(G.frame_packet, "10.0.0.8", blue, late=0.004)
send(G.event_packet, "10.0.0.8", "beat", 1.0, clk.t + SENDER + 0.2, late=0.01)
before = grid.render(clk.t + 0.15)
at = grid.render(clk.t + 0.21)
check(f"a beat due by the sender's clock: brighter as it's due, not before ({before[0, 0].round().tolist()}, "
      f"{at[0, 0].round().tolist()})", near(before[0, 0], BLUE, 6) and at[0, 0, 2] > 250 and at[0, 0, 0] > 40)
clk.t += 1.0
grid.beat = False
send(G.event_packet, "10.0.0.8", "beat", 1.0, clk.t + SENDER)
check("...pulse to music off: none", not [e for e in grid.events if e[1] == "beat" and e[0] > clk.t - 0.5])
grid.beat = True
send(G.event_packet, "10.0.0.8", "cheevo", 1.0, clk.t + SENDER)
img = grid.render(clk.t + 0.05)
check(f"an achievement: gold ({img[0, 0].round().tolist()}, {img[4, 4].round().tolist()})",
      img[:, :, 0].mean() > 150 and img[:, :, 1].mean() > 100 and img[:, :, 2].mean() < 100)
img = settle(G.FADE_AFTER + 4 * G.FADE_TAU + G.GOLD_SECS)
check(f"nothing new a while: dark ({img.max():.1f})", img.max() < 10)
music = G.music_packet((96, 170, 228), clk.t + SENDER)
grid.take(music, "10.0.0.8", clk.t)
img = settle(1.0)
check(f"music: its colour, dimmer between beats ({img[2, 2].round().tolist()})",
      near(img[2, 2], np.array([96, 170, 228]) * G.MUSIC_BASE, 6))

# its LEDs: as bright as it's set, evened out for the eye, as it's put up and wired
grid.bright = 0.25
lit = np.frombuffer(grid.leds(np.full((8, 8, 3), 255.0)), dtype=np.uint8)
half = np.frombuffer(grid.leds(np.full((8, 8, 3), 128.0)), dtype=np.uint8)
check(f"how bright: a quarter ({lit[0]}); half of white looks half as bright ({half[0]})",
      lit.max() == 64 and 10 <= half[0] <= 16)
grid.bright = 1.0
grid.test()
pattern = grid.render(clk.t)


def wired(mirror, turn, zigzag):
    grid.mirror, grid.turn, grid.zigzag = mirror, turn, zigzag
    a = np.frombuffer(grid.leds(pattern), dtype=np.uint8).reshape(64, 3)
    return ["W" if tuple(x) == (255, 255, 255) else "R" if tuple(x) == (0, 255, 0) else "G" if tuple(x) == (255, 0, 0)
            else "." for x in a]                       # (green, red, blue: red's 0,255,0)


def rows_of(leds):
    return ["".join(leds[r * 8:(r + 1) * 8]) for r in range(8)]


plain = rows_of(wired(False, 0, False))
check(f"which way's up: its top row red, its left side green, its top left white ({plain[:2]})",
      plain[0] == "WRRRRRRR" and plain[1] == "G......." and plain[7] == "G.......")
check(f"...mirrored (facing the wall: the default) ({rows_of(wired(True, 0, False))[:2]})",
      rows_of(wired(True, 0, False))[:2] == ["RRRRRRRW", ".......G"])
check(f"...turned 90° ({rows_of(wired(False, 90, False))[:2]})",
      rows_of(wired(False, 90, False))[:2] == ["GGGGGGGW", ".......R"])
check(f"...wired in zigzag rows ({rows_of(wired(False, 0, True))[:2]})",
      rows_of(wired(False, 0, True))[:2] == ["WRRRRRRR", ".......G"])
grid.mirror, grid.turn, grid.zigzag = False, 0, False
grid.frame(clk.t)
sent = last_lit()
check("lit through SPI: what it sent the LEDs, back as it was", sent[0, 0].tolist() == [255, 255, 255]
      and sent[0, 1].tolist() == [0, 255, 0] and sent[1, 0].tolist() == [255, 0, 0])
grid.close()
check("shut: dark", last_lit().max() == 0)

# over real UDP
OUT2 = S + "/spi2"
open(OUT2, "wb").close()
live = G.Grid(G.Strip(OUT2), lambda ip: G.THIS_ONE if ip.startswith("127.") else None, port=0)
out = G.GlowOut()
out.aim([("127.0.0.1", live.port)])
green = np.zeros((8, 8, 3), dtype=np.uint8)
green[...] = GREEN
check("over UDP: a picture's colours, on the grid", until(lambda: (out.frame(green), near(live.shown[0, 0], GREEN, 20))[1]))
check("...the LEDs lit with them", until(lambda: last_lit(OUT2)[3, 3].tolist()[0] > 40))
live.close()
out.close()

# ---- config.txt: the Pi's SPI on -----------------------------------------------------------------------------------------
check("config.txt's lines: SPI, and the core clock steady (a Pi 4's, a Zero 2's; a Pi 5 has its own)",
      G.spi_lines("Raspberry Pi 4 Model B Rev 1.4") == ["dtparam=spi=on", "core_freq_min=500"]
      and G.spi_lines("Raspberry Pi Zero 2 W Rev 1.0") == ["dtparam=spi=on", "core_freq_min=400"]
      and G.spi_lines("Raspberry Pi 5 Model B Rev 1.0") == ["dtparam=spi=on"]
      and G.spi_lines("Raspberry Pi 3 Model B Plus Rev 1.3", "core_freq=450\n") == ["dtparam=spi=on",
                                                                                  "core_freq_min=450"])
CFG = S + "/config.txt"
open(CFG, "w").write("dtparam=audio=on\n[pi4]\narm_boost=1\n")
changed = G.turn_spi_on(CFG, G.spi_lines("Raspberry Pi 4 Model B"))
text = open(CFG).read()
check("...put in once, after an [all] (the rest as it was)", changed and text.startswith("dtparam=audio=on\n[pi4]\n")
      and text.endswith("# >>> pietato led grid >>>\n[all]\ndtparam=spi=on\ncore_freq_min=500\n"
                        "# <<< pietato led grid <<<\n")
      and not G.turn_spi_on(CFG, G.spi_lines("Raspberry Pi 4 Model B")) and open(CFG).read() == text)
done = subprocess.run(["sed", "-i", "/^# >>> pietato led grid >>>$/,/^# <<< pietato led grid <<<$/d", CFG])
check("...uninstall.sh's way of taking them out leaves the rest", open(CFG).read().strip()
      == "dtparam=audio=on\n[pi4]\narm_boost=1")
check("another's beacon: its grid, as much as makes sense", G.glow_clean({"port": 5448, "follow": "TV", "beat": True})
      == {"port": 5448, "follow": "TV", "beat": True} and G.glow_clean({"port": True}) is None
      and G.glow_clean({"port": 5448, "follow": "x\n"}) == {"port": 5448, "follow": "", "beat": False}
      and G.glow_clean("no") is None)


# ---- the emulator's part ---------------------------------------------------------------------------------------------
class Screen:
    def __init__(self):
        self.plan, self.turn, self.fields = None, 0, [(11, 5), (5, 6), (0, 5)]
        self.shown = 0

    def show(self, a, fmt, aspect):
        self.shown += 1

    def show_gpu(self, gpu, w, h, aspect, flipped=True):
        self.plan = {"view": np.asarray(as565(pic))}


class RA:
    def __init__(self):
        self.text = "Sonic in Green Hill | Lives: 3"

    def rich_presence(self):
        return self.text


catch = []
ear = __import__("socket").socket(__import__("socket").AF_INET, __import__("socket").SOCK_DGRAM)
ear.bind(("127.0.0.1", 0))
ear.settimeout(0.5)


def heard(secs=0.3):
    end = time.monotonic() + secs
    out = []
    while time.monotonic() < end:
        try:
            out.append(G.read_packet(ear.recv(4096)))
        except OSError:
            pass
    return out


s = E.Session.__new__(E.Session)
s.screen, s.stats, s.core, s.ra = Screen(), [0, 0, 0, 0, 0], type("Core", (), {"gpu": None, "hw": {"flipped": True}})(), None
s.picture(wide[:, :W], E.FMT_RGB565, 4 / 3)
check("no grids: nothing sampled", s.glow is None and s.screen.shown == 1)
s.command(["glow", f"127.0.0.1:{ear.getsockname()[1]}"])
for _ in range(10):
    s.picture(wide[:, :W], E.FMT_RGB565, 4 / 3)
pk = heard()
check(f"told where its colours go: each picture's edges sent, 30 a second at most ({len(pk)} of 10 pictures at once)",
      len(pk) == 1 and pk[0]["kind"] == "frame" and near(pk[0]["colours"][0, 3], RED))
time.sleep(G.GLOW_EVERY)
s.picture(None, (256, 224), 4 / 3)                    # (one the graphics chip drew)
pk = heard()
check("...one the graphics chip drew: its colours from the screen", len(pk) == 1 and near(pk[0]["colours"][7, 3], BLUE))
s.cheevo_got = E.Session.cheevo_got.__get__(s)
s.say = lambda *a: None
s.cheevos_tell = lambda *a: None
s.cheevos_counts = lambda: (1, 2)
s.screen.notice = lambda lines: None
s.cheevo_got({"title": "Rings", "points": 5})
pk = heard()
check("an achievement: gold", [p["name"] for p in pk if p["kind"] == "event"] == ["cheevo"])
s.glow_rumble(1, 0, 0xFFFF)
s.glow_rumble(0, 0, 0x1000)
none = heard(0.2)
s.glow_rumble(0, 0, 0xC000)
s.glow_rumble(0, 0, 0xC000)
pk = heard()
check(f"a controller shaken hard (player 1's): a hit, once at a time ({[(p['name'], round(p['strength'], 2)) for p in pk]})",
      none == [] and [p["name"] for p in pk] == ["hit"] and pk[0]["strength"] > 0.9)
s.ra, s.hits = RA(), G.HitWatch()
s.glow_presence()
time.sleep(G.HIT_GAP)
s.rp_next = 0.0
s.ra.text = "Sonic in Green Hill | Lives: 2"
s.glow_presence()
pk = heard()
check("lives going down, in what RetroAchievements says: a hit", [p["name"] for p in pk] == ["hit"])
s.command(["glow", "-"])
s.picture(wide[:, :W], E.FMT_RGB565, 4 / 3)
check("...nowhere now: nothing sent", heard(0.2) == [])

# ---- media mode -----------------------------------------------------------------------------------------------------------
open(S + "/bin/aplay", "w").write('''#!/usr/bin/env python3
import sys, time
args = sys.argv[1:]
rate = int(args[args.index("-r") + 1]) if "-r" in args else 48000
inp, start, played = sys.stdin.buffer, None, 0
while True:
    data = inp.read(rate // 100 * 4)
    if not data:
        break
    start = start or time.monotonic()
    played += len(data) // 4
    wait = start + played / rate - time.monotonic()
    if wait > 0:
        time.sleep(wait)
''')
os.chmod(S + "/bin/aplay", 0o755)
os.environ["PATH"] = S + "/bin:" + os.environ["PATH"]
os.environ["HOME"] = HOME
g.STATE_FILE = S + "/gpi.json"; g.CACHE_DIR = S + "/gpicache"; g.PLEX_FILE = S + "/plex.json"
g.GROUP_LOG = S + "/gpigroup.json"
g.home_dir = lambda: HOME
import gk_static; gk_static.use_home(g, HOME)
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "", "returncode": 0, "stderr": ""})()
spawned = []


class Proc:
    def __init__(self):
        self.stdin = open(os.devnull, "w")
        self.stdout, self.stderr = iter(()), iter(())
        self.returncode, self.args = None, []

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = 0
        return 0

    def kill(self):
        self.returncode = -9


def spawn(self, args, target):
    self.started = time.monotonic()
    self.proc = Proc()
    spawned.append((target, list(args)))


g.PlayerScreen.spawn = spawn


class FB:
    w, h = 640, 480
    def show(self, img): pass
    def show_part(self, img, box): pass
    def invalidate(self): pass
    def close(self): pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.set_setting("name", "gpi")
m.glow_can = lambda: True                             # (a Pi with its pins free, as far as this test goes)
m.glow_spi, m.glow_port, m.glow_configs = S + "/spi-m", 0, [S + "/m-config.txt"]
open(m.glow_spi, "wb").close()
open(S + "/m-config.txt", "w").write("dtparam=audio=on\n")
m.view, m.tab = "list", next(k for k, t in enumerate(g.LIBRARY) if t.get("type") == "settings")
m.set_page = None
keys = [k for k, _, _ in m.settings_rows()]
check("Settings: TV backlight, on a Pi that can have a grid", "glow" in keys)
m.set_sel = keys.index("glow")
m.press("a")
rows = [k for k, _, _ in m.settings_rows()]
check(f"...its page ({rows})", m.set_page == "glow" and rows == ["glow_on", "glow_follow", "glow_bright", "glow_beat",
                                                                 "glow_turn", "glow_mirror", "glow_wiring", "glow_test"])
m.render_settings()
m.set_sel = 0
m.press("right")
check(f"LED grid on: lit, SPI's lines put in config.txt, and a restart asked for ({m.glow_status()!r})",
      m.glow_grid is not None and "dtparam=spi=on" in open(S + "/m-config.txt").read() and m.glow_restart
      and [k for k, _, _ in m.settings_rows()][-1] == "glow_reboot")
m.render_settings()
grid = m.glow_grid
m.set_sel = 2
m.press("right")
m.set_sel = 5
m.press("right")
check(f"...its settings, as they're set ({grid.bright}, {grid.mirror})", grid.bright == 0.5 and grid.mirror is False)
beacon = m.share_beacon("gpi", full=True)
check(f"its beacon: there's a grid, following any of yours, pulsing to music ({beacon.get('glow')})",
      beacon.get("glow") == {"port": grid.port, "follow": "", "beat": True}
      and "glow" not in m.share_beacon("gpi"))
PEER = "http://10.0.0.7:5432"
m.pie.heard[PEER] = {"host": "tv", "seen": time.time() + 3600, "peer": True,
                     "glow": {"port": 5448, "follow": "gpi", "beat": True}}
check(f"your grids: this one's and the TV's ({m.glow_targets()})",
      m.glow_targets() == [("127.0.0.1", grid.port), ("10.0.0.7", 5448)])


class Run:
    state, ended, game = "on", False, {"path": "/x", "title": "x", "system": "nes"}

    def __init__(self):
        self.sent = []

    def send(self, line):
        self.sent.append(line)
        return True


run = Run()
m.glow_game_tick(run, time.monotonic() + 10)
m.glow_game_tick(run, time.monotonic() + 20)
check(f"a game: its emulator told where its colours go, once ({run.sent})",
      run.sent == [f"glow 127.0.0.1:{grid.port} 10.0.0.7:5448"])
del m.pie.heard[PEER]
m.glow_seen = 0.0

# music, through party mode's player, for the beat
sig, beats = kicks(14, first=0.5)
KICKS = HOME + "/Music/Kicks.wav"
with wave.open(KICKS, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE)
    w.writeframes((np.stack([sig, sig], -1) * 0.8 * 32767).astype("<i2").tobytes())
lit_in = []
was_take = grid.take


def take(data, ip, now):
    p = G.read_packet(data)
    if p is not None:
        lit_in.append((now, ip, p))
    return was_take(data, ip, now)


grid.take = take
m.volume = 100
item = g.item(KICKS, "Kicks", "audio", KICKS)
m.play([item], 0)
check(f"music, with a grid pulsing to it: on party mode's player, on its own ({type(m.proc).__name__}, "
      f"{m.party})", type(m.proc).__name__ == "PartyProc" and m.party is None and not spawned)
start = m.proc.player.anchor[0]
end = time.monotonic() + 6.0
while time.monotonic() < end:
    m.glow_tick(time.monotonic())
    time.sleep(0.02)
got_beats = [(p["at"] + min(grid.offsets["127.0.0.1"]), p["strength"]) for _, _, p in lit_in
             if p["kind"] == "event" and p["name"] == "beat"]
kicked = [t for t, _ in got_beats if t > start + 0.3]  # (the song's own start, out of silence, is a beat too)
errs = [min(abs(t - (start + b)) for b in beats) for t in kicked]
due = [b for b in beats if start + b < time.monotonic() - 0.5]
missed = [b for b in due if not any(abs(t - (start + b)) < 0.04 for t in kicked)]
check(f"...the grid told of each kick drum as it's heard ({len(kicked)}; missed {missed}; the furthest out "
      f"{max(errs or [9]) * 1000:.0f} ms)", len(due) >= 8 and not missed and max(errs or [9]) < 0.04)
musics = [p for _, _, p in lit_in if p["kind"] == "music"]
check(f"...and music's colour between (the accent's: {musics[-1]['rgb'].tolist() if musics else None})",
      len(musics) >= 6 and musics[-1]["rgb"].tolist() == [96, 170, 228])
t_beat = got_beats[-1][0] if got_beats else 0.0
pulse = grid.render(t_beat + 0.02)[4, 4].sum()
between = grid.render(t_beat + 0.3)[4, 4].sum()
check(f"...brighter on a beat than between ({pulse:.0f} > {between:.0f})", pulse > between * 1.5)
m.cmd("pause")                                         # (as the web page's remote, or the Bot, says it to mplayer)
check("pause, said as mplayer takes it: paused", until(lambda: m.proc.player.paused(), 2))
m.cmd("pause")
check("...and on again", until(lambda: not m.proc.player.paused(), 2))
here = m.proc.player.position()
m.cmd("seek 10 0")
check(f"seek, said as mplayer takes it: 10 s on ({here:.1f} to {m.proc.player.pos0:.1f})",
      type(m.proc).__name__ == "PartyProc" and abs(m.proc.player.pos0 - (here + 10)) < 1.0)
m.stop()


# a station: passed through here (its song's names)
class Station(BaseHTTPRequestHandler):
    EVERY = 4000

    def log_message(self, *a):
        pass

    def do_GET(self):
        meta = self.headers.get("Icy-MetaData") == "1"
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        if meta:
            self.send_header("icy-metaint", str(self.EVERY))
        self.end_headers()
        data, at, n = self.server.audio, 0, 0
        try:
            while at < len(data):
                piece = data[at:at + self.EVERY]
                at += len(piece)
                self.wfile.write(piece)
                if meta and len(piece) == self.EVERY:
                    n += 1
                    title = f"StreamTitle='Song {'A' if n < 8 else 'B'}';".encode()
                    title += bytes(-len(title) % 16)
                    self.wfile.write(bytes([len(title) // 16]) + title)
                self.wfile.flush()
                time.sleep(self.EVERY / 16000)
        except OSError:
            pass


LOUD = S + "/loud.mp3"
real_run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=70:d=30", "-ac", "2", "-b:a", "128k",
          LOUD], check=True)
radio = ThreadingHTTPServer(("127.0.0.1", 0), Station)
radio.audio = open(LOUD, "rb").read()
threading.Thread(target=radio.serve_forever, daemon=True).start()
station = {"title": "Pretend FM", "sub": "", "src": f"http://127.0.0.1:{radio.server_port}/live", "kind": "radio"}
m.play([station], 0)
st = m.glow_station
check(f"a station: passed through here, to party mode's player ({m.proc.player.src.split('?')[0] if m.proc else None})",
      type(m.proc).__name__ == "PartyProc" and st is not None and st["relay"] is not None
      and m.proc.player.src.startswith(f"http://127.0.0.1:{st['server'].port}/station?"))
end = time.monotonic() + 3.0
while time.monotonic() < end and m.meta.get("song") != "Song A":
    m.glow_tick(time.monotonic())
    time.sleep(0.05)
check(f"...its song's name shown ({m.meta.get('song')!r})", m.meta.get("song") == "Song A")
m.stop()
end = time.monotonic() + 5.0
while time.monotonic() < end and m.glow_station is not None:
    m.glow_tick(time.monotonic())
    time.sleep(0.05)
check("...let go of once it's not played", m.glow_station is None)

# pulse to music off (and no other grid): as ever
m.set_sel = [k for k, _, _ in m.settings_rows()].index("glow_beat")
m.press("right")
check(f"pulse to music off: its beacon says so, and music's as ever, mplayer's ({spawned[-1:] and spawned[-1][0]})",
      m.share_beacon("gpi", full=True)["glow"]["beat"] is False and not m.glow_beats_wanted()
      and (m.play([item], 0), spawned and spawned[-1][0] == KICKS)[1])
m.stop()

# the web page's Settings
sec = next((x for x in m.web_settings_now()["sections"] if x["id"] == "glow"), None)
check(f"the web page's Settings: TV backlight ({[r['key'] for r in sec['rows']] if sec else None})",
      sec is not None and [r["key"] for r in sec["rows"]][:3] == ["glow_on", "glow_follow", "glow_bright"]
      and any(r["key"] == "glow_reboot" for r in sec["rows"]))
said = m.web_settings_do({"key": "glow_bright", "value": "100%"})
check(f"...one changed there: on the grid ({said}, {grid.bright})", said == {"ok": True} and grid.bright == 1.0)
check("...which way is up, shown", m.web_settings_do({"key": "glow_test", "value": True}).get("ok")
      and grid.test_until > time.monotonic())
check("...not one of its choices: not taken", "error" in m.web_settings_do({"key": "glow_turn", "value": "45°"}))
m.set_sel = 0
m.set_page = "glow"
m.press("left")
check("LED grid off: dark, and gone from the beacon", m.glow_grid is None and "glow" not in m.share_beacon("gpi", full=True)
      and last_lit(m.glow_spi).max() == 0)
m.press("b")
check("B: back to Settings, on its row", m.set_page is None and [k for k, _, _ in m.settings_rows()][m.set_sel] == "glow")
m.glow_can = lambda: False
check("a Pi that can't have one (a PC, a GPi Case): no TV backlight in Settings",
      "glow" not in [k for k, _, _ in m.settings_rows()]
      and not any(x["id"] == "glow" for x in m.web_settings_now()["sections"]))
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
