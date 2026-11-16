"""An OLED HAT's bars (pitato/oled.py, screens/oled.py): a Waveshare 2.23inch OLED on a Pi's pins, showing bars that
move with the music. First the pieces on their own: what's asked of the kernel for its two pins (the numbers and the
shapes of linux/gpio.h, written out again here; the chip a Pi's own pins are on, whatever its number, a Pi 5's too;
none, or the pins taken); its SPI; a command or the picture, by its D/C pin; the screen started as Waveshare's driver
starts it, then only the rows that changed, and dark and off as it's shut; the picture for the bars (as that driver
packs one: 25 bars, 4 wide, up from the bottom); the sound as it's heard (the sound heard now, not what's just been
written; whatever the volume; nothing for now, a jump); and the bars themselves (as tall as the sound's loud, up at
once, falling slowly, drawn only as they change, 25 times a second). Then media mode: Settings > Screen > Waveshare
2.23 OLED only on a Pi with its pins free (not in a GPi Case, on a handheld or a PC); picked, it's lit, and music
plays through party mode's player (a song already playing moved to it), its bars up as the loud part of a song is
heard, whatever the volume; one that's in another's party, by its leader's clock; an LED backlight on the same pin
turned off for it, and the other way round; the Pi's SPI not on (turned on in config.txt, a restart asked for; the
LED backlight's own part left as it is), its pins taken; the web page's Settings; and dark as Pietato goes. And
another of your Pietatos' music: the one playing sends its bars as they're heard there (a packet each, to yours with
an OLED lit, as their beacons say; its music on party mode's player for it), and the one with the OLED takes them
from your Pietatos only, whichever's playing, and shows them while its own Pi plays nothing."""
import ctypes, errno, os, shutil, socket, sys, threading, time, wave
from paths import SP, TESTS  # noqa: E402  (this test's folder of work; tests)
sys.path.insert(0, TESTS)
import numpy as np
import pietato_all as g
import pitato.oled as O
import pitato.screens.oled as SO
import pitato.glow as G

S = SP + "/t_oled"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/gpi"
for d in ("Music", "Videos", "Pictures", "Documents", "Games/Saves"):
    os.makedirs(f"{HOME}/{d}")
os.makedirs(S + "/bin")
ok_all = []
RATE = 48000
O.RESET_WAIT = 0.001                                   # (its reset: not waited for here)


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


# ---- its two pins: what's asked of the kernel ---------------------------------------------------------------------------
# (linux/gpio.h, written out again: the shapes the kernel takes, and the numbers it knows them by)
class ChipInfo(ctypes.Structure):
    _fields_ = [("name", ctypes.c_char * 32), ("label", ctypes.c_char * 32), ("lines", ctypes.c_uint32)]


class Attr(ctypes.Structure):
    _fields_ = [("id", ctypes.c_uint32), ("padding", ctypes.c_uint32), ("values", ctypes.c_uint64)]


class ConfigAttr(ctypes.Structure):
    _fields_ = [("attr", Attr), ("mask", ctypes.c_uint64)]


class Config(ctypes.Structure):
    _fields_ = [("flags", ctypes.c_uint64), ("num_attrs", ctypes.c_uint32), ("padding", ctypes.c_uint32 * 5),
                ("attrs", ConfigAttr * 10)]


class Request(ctypes.Structure):
    _fields_ = [("offsets", ctypes.c_uint32 * 64), ("consumer", ctypes.c_char * 32), ("config", Config),
                ("num_lines", ctypes.c_uint32), ("event_buffer_size", ctypes.c_uint32),
                ("padding", ctypes.c_uint32 * 5), ("fd", ctypes.c_int32)]


class Values(ctypes.Structure):
    _fields_ = [("bits", ctypes.c_uint64), ("mask", ctypes.c_uint64)]


def ioc(way, nr, shape):
    return (way << 30) | (ctypes.sizeof(shape) << 16) | (0xB4 << 8) | nr


check(f"the kernel's numbers for a chip's name, lines asked for and lines set ({O.GPIO_GET_CHIPINFO_IOCTL:#x}, "
      f"{O.GPIO_V2_GET_LINE_IOCTL:#x}, {O.GPIO_V2_LINE_SET_VALUES_IOCTL:#x}): as linux/gpio.h makes them",
      O.GPIO_GET_CHIPINFO_IOCTL == ioc(2, 0x01, ChipInfo) and O.GPIO_V2_GET_LINE_IOCTL == ioc(3, 0x07, Request)
      and O.GPIO_V2_LINE_SET_VALUES_IOCTL == ioc(3, 0x0F, Values))
check(f"...and how big each is, and where its parts are ({O.CHIP_INFO}, {O.LINE_REQUEST}; {O.REQ_CONSUMER}, "
      f"{O.REQ_FLAGS}, {O.REQ_LINES}, {O.REQ_FD})",
      (O.CHIP_INFO, O.LINE_REQUEST) == (ctypes.sizeof(ChipInfo), ctypes.sizeof(Request))
      and O.REQ_CONSUMER == Request.consumer.offset and O.REQ_FLAGS == Request.config.offset + Config.flags.offset
      and O.REQ_LINES == Request.num_lines.offset and O.REQ_FD == Request.fd.offset
      and ChipInfo.label.offset == 32 and ChipInfo.lines.offset == 64 and O.GPIO_V2_LINE_FLAG_OUTPUT == 8)


class Kernel:
    """The kernel's GPIO chips, as far as the OLED's pins go: each chip a file (its label and lines), a request for
    lines answered with a file of its own, and what's set on it kept."""

    def __init__(self, chips, busy=()):
        self.chips, self.busy = {}, set(busy)          # path -> (label, lines); pins another program has
        self.asked, self.set, self.lines = [], [], {}
        self.open, self.closed = {}, []
        for k, (label, lines) in enumerate(chips):
            path = f"{S}/gpiochip{k}-{len(os.listdir(S))}"
            open(path, "wb").close()
            self.chips[path] = (label, lines)

    def paths(self):
        return list(self.chips)

    def os_open(self, path, flags, *a):
        fd = real_open(path, flags, *a)
        if path in self.chips:
            self.open[fd] = path
        return fd

    def os_close(self, fd):
        if fd in self.open or fd in self.lines:
            self.closed.append(self.open.pop(fd, None) or "lines")
            self.lines.pop(fd, None)
        return real_close(fd)

    def ioctl(self, fd, req, arg=0, *a):
        if fd in self.open and req == ioc(2, 0x01, ChipInfo):
            label, lines = self.chips[self.open[fd]]
            info = ChipInfo(name=b"gpiochip", label=label.encode(), lines=lines)
            arg[:] = bytes(info)
            return 0
        if fd in self.open and req == ioc(3, 0x07, Request):
            r = Request.from_buffer_copy(bytes(arg))
            pins = list(r.offsets[:r.num_lines])
            self.asked.append({"chip": self.chips[self.open[fd]][0], "pins": pins, "by": r.consumer.decode(),
                               "flags": r.config.flags, "attrs": r.config.num_attrs})
            if self.busy & set(pins):
                raise OSError(errno.EBUSY, "Device or resource busy")
            r.fd = real_open(S + "/lines", os.O_RDWR | os.O_CREAT)
            self.lines[r.fd] = [0] * len(pins)         # (outputs: low, with nothing said of them)
            arg[:] = bytes(r)
            return 0
        if fd in self.lines and req == ioc(3, 0x0F, Values):
            v = Values.from_buffer_copy(bytes(arg))
            for k in range(len(self.lines[fd])):
                if v.mask >> k & 1:
                    self.lines[fd][k] = v.bits >> k & 1
            self.set.append(tuple(self.lines[fd]))
            return 0
        return real_ioctl(fd, req, arg, *a)


real_open, real_close, real_ioctl = os.open, os.close, O.fcntl.ioctl


class Patched:
    """The module's os.open, os.close and ioctl, the pretend kernel's for a while."""

    def __init__(self, kernel):
        self.k = kernel

    def __enter__(self):
        O.os.open, O.os.close, O.fcntl.ioctl = self.k.os_open, self.k.os_close, self.k.ioctl
        return self.k

    def __exit__(self, *a):
        O.os.open, O.os.close, O.fcntl.ioctl = real_open, real_close, real_ioctl


PI5 = [("gpio-brcmstb@107d508500", 32), ("gpio-brcmstb@107d508520", 4), ("gpio-brcmstb@107d517c00", 17),
       ("gpio-brcmstb@107d517c20", 6), ("pinctrl-rp1", 54)]
with Patched(Kernel(PI5)) as k:
    pins = O.Pins(chips=k.paths())
    asked = list(k.asked)
    pins.set(dc=1)
    pins.set(rst=1)
    pins.set(dc=0)
    pins.close()
check(f"a Pi 5: its pins are on the chip that says it's theirs (not the first), asked for together as outputs "
      f"({asked})", asked == [{"chip": "pinctrl-rp1", "pins": [24, 25], "by": "pietato-oled", "flags": 8, "attrs": 0}])
check(f"...each set on its own, the other left as it was ({k.set}); the chip let go of once they're had, and "
      f"they too as it's shut ({k.closed.count('lines')}, {len(k.open)} left open)",
      k.set == [(1, 0), (1, 1), (0, 1)] and k.closed.count("lines") == 1 and not k.open and len(k.closed) == 6)
for label in ("pinctrl-bcm2835", "pinctrl-bcm2711"):
    with Patched(Kernel([(label, 58), ("raspberrypi-exp-gpio", 8)])) as k:
        O.Pins(chips=k.paths()).close()
    check(f"a Pi's own pins ({label}): asked of it", [a["chip"] for a in k.asked] == [label])
with Patched(Kernel([("gpio-brcmstb@107d508500", 32), ("some-other-chip", 54)])) as k:
    try:
        O.Pins(chips=k.paths())
        why = None
    except OSError as ex:
        why = ex.errno
check(f"no chip that's a Pi's own pins: no pins, and no other chip's are touched ({why}, {k.asked})",
      why == errno.ENODEV and not k.asked and not k.open)
with Patched(Kernel([("pinctrl-bcm2711", 58)], busy=[25])) as k:
    try:
        O.Pins(chips=k.paths())
        why = None
    except OSError as ex:
        why = ex.errno
check(f"its pins taken by another program: said, and the chip's let go of ({why})",
      why == errno.EBUSY and not k.open and not k.lines)

# ---- its SPI, and a command or the picture -------------------------------------------------------------------------
OUT = S + "/spi"
open(OUT, "wb").close()
spi = O.Spi(OUT)
spi.write(b"\x01\x02")
spi.write(bytes((3,)))
spi.close()
check("its SPI: written to as it is (a plain file here)", open(OUT, "rb").read() == b"\x01\x02\x03")


class FakePins:
    def __init__(self, log):
        self.log, self.closed = log, False

    def set(self, dc=None, rst=None):
        self.log.append(("dc", dc) if dc is not None else ("rst", rst))

    def close(self):
        self.closed = True


class FakeSpi:
    def __init__(self, log):
        self.log, self.closed = log, False

    def write(self, data):
        self.log.append(("spi", bytes(data)))

    def close(self):
        self.closed = True


log = []
w = O.Wires(FakeSpi(log), FakePins(log))
w.reset()
w.command((0xAE,))
w.command((0x04, 0x10))
w.data(b"\xff\x00")
w.data(b"\x0f")
w.command((0xAF,))
check(f"its wires: reset high, low, high; D/C low for a command, high for the picture, moved only when it changes "
      f"({log})", log == [("rst", 1), ("rst", 0), ("rst", 1), ("dc", 0), ("spi", b"\xae"), ("spi", b"\x04\x10"),
                          ("dc", 1), ("spi", b"\xff\x00"), ("spi", b"\x0f"), ("dc", 0), ("spi", b"\xaf")])
w.close()
check("...shut: its SPI and its pins let go of", w.spi.closed and w.pins.closed)


# ---- the screen ----------------------------------------------------------------------------------------------------
class FakeWires:
    """The HAT's wires, kept: ("reset",), ("c", a command's bytes), ("d", the picture's)."""

    def __init__(self, fails=None):
        self.log, self.closed, self.fails = [], False, fails

    def reset(self):
        self.log.append(("reset",))

    def command(self, data):
        if self.fails:
            raise OSError(self.fails, os.strerror(self.fails))
        self.log.append(("c", bytes(data)))

    def data(self, data):
        self.log.append(("d", bytes(data)))

    def close(self):
        self.closed = True

    def rows(self):
        """The picture on the screen now: its four rows, as they were last sent."""
        rows, at = [bytes(128)] * 4, None
        for kind, *rest in self.log:
            if kind == "c" and len(rest[0]) == 3 and 0xB0 <= rest[0][0] <= 0xB3:
                at = rest[0][0] - 0xB0
            elif kind == "d":
                rows[at] = rest[0]
        return rows

    def lit(self):
        """...as pixels: 32 down by 128 across (as Waveshare's driver packs them: a byte 8 pixels, the top its bit 0)."""
        a = np.frombuffer(b"".join(self.rows()), dtype=np.uint8).reshape(4, 128)
        return np.unpackbits(a[:, None, :], axis=1, bitorder="little").reshape(32, 128)

    def heights(self):
        """...and each bar's height (its columns all the same, lit up from the bottom, dark between and beside)."""
        lit = self.lit()
        cols = [int(c) for c in lit.sum(axis=0)]
        solid = all((lit[32 - h:, x] == 1).all() and (lit[:32 - h, x] == 0).all() for x, h in enumerate(cols))
        bars = [cols[2 + 5 * i:6 + 5 * i] for i in range(25)]
        gaps = [x for x in range(128) if x < 2 or x > 125 or (x - 2) % 5 == 4]
        return [b[0] for b in bars] if solid and all(len(set(b)) == 1 for b in bars) \
            and not any(cols[x] for x in gaps) else None


WAVESHARE = [0xAE, 0x04, 0x10, 0x40, 0x81, 0x80, 0xA1, 0xA6, 0xA8, 0x1F, 0xC8, 0xD3, 0x00, 0xD5, 0xF0, 0xD8, 0x05,
             0xD9, 0xC2, 0xDA, 0x12, 0xDB, 0x08, 0xAF]     # (its SSD1305.py's Init, command by command)
fw = FakeWires()
scr = O.Screen(fw)
start = fw.log[:1 + len(WAVESHARE)]
check(f"the screen: reset, then started as Waveshare's driver starts it, each command on its own ({len(start) - 1})",
      start == [("reset",)] + [("c", bytes((c,))) for c in WAVESHARE])
rest = fw.log[1 + len(WAVESHARE):]
check("...then dark: each of its four rows, where it starts before it (0xB0 + the row, column 4), then its 128 bytes",
      rest == [x for p in range(4) for x in (("c", bytes((0xB0 + p, 0x04, 0x10))), ("d", bytes(128)))])
n = len(fw.log)
rows = [bytes(128), bytes(128), bytes(128), b"\x80" * 128]
scr.show(tuple(rows))
check(f"a picture: only the rows that changed are sent ({fw.log[n:][0][1].hex()}, {len(fw.log) - n} writes)",
      fw.log[n:] == [("c", b"\xb3\x04\x10"), ("d", b"\x80" * 128)])
n = len(fw.log)
scr.show(tuple(rows))
check("...the same one again: nothing", len(fw.log) == n)
scr.close()
check(f"shut: dark, then off, and its wires let go of ({[x[1].hex() for x in fw.log[n:]][-1]})",
      fw.log[n:] == [("c", b"\xb3\x04\x10"), ("d", bytes(128)), ("c", b"\xae")] and fw.closed)

# ---- the picture for the bars ----------------------------------------------------------------------------------------
rng = np.random.default_rng(3)
same = True
for _ in range(40):
    px = rng.integers(0, 33, 25)
    img = np.zeros((32, 128), dtype=np.uint8)           # (drawn as his own visualizer draws them, a rectangle each)
    for i, h in enumerate(px):
        if h:
            img[32 - h:, 2 + 5 * i:6 + 5 * i] = 1
    packed = np.packbits(img.reshape(4, 8, 128), axis=1, bitorder="little").tobytes()   # (...and as his driver packs it)
    same = same and b"".join(O.rows_of(px)) == packed
check(f"the bars' picture: {O.BARS} bars, {O.BAR_W} wide with {O.BAR_GAP} between, {O.BARS_LEFT} dark each side, up "
      f"from the bottom: packed as Waveshare's driver packs a picture", same and (O.BARS, O.BAR_W, O.BAR_GAP,
                                                                               O.BARS_LEFT) == (25, 4, 1, 2))
check("...none, and all of them all the way up", b"".join(O.rows_of(np.zeros(25, int))) == bytes(512)
      and b"".join(O.rows_of(np.full(25, 32))).count(b"\xff") == 4 * 100)


# ---- the sound, as it's heard ----------------------------------------------------------------------------------------
def pcm_of(sig, vol=1.0):
    """Samples (-1 to 1) as the player writes them: 16 bits, both sides the same, as loud as the volume makes them."""
    return (np.stack([sig, sig], -1) * vol * 32767).astype("<i2")


def feed(h, pcm, t0, gain=1.0, step=480):
    """...fed as it writes them: 10 ms at a time, each piece's first sample heard at its own time."""
    for k in range(0, len(pcm), step):
        h.feed(pcm[k:k + step].tobytes(), t0 + k / RATE, gain)


quiet, loud = np.zeros(RATE // 2), np.full(RATE // 2, 0.4)
h = O.Heard()
feed(h, pcm_of(np.concatenate([quiet, loud, quiet])), 100.0)     # (heard from 100.0: loud from 100.5 to 101.0)
lv = {t: h.levels(t) for t in (100.25, 100.45, 100.6, 100.9, 101.2)}
check(f"what's heard now, not what's just been written: nothing before its loud half second, as loud as it is "
      f"through it, nothing after ({[round(float(v.max()), 3) for v in lv.values()]})",
      all(lv[t].max() == 0 for t in (100.25, 100.45, 101.2)) and len(lv[100.6]) == 25
      and all(abs(lv[t] - 0.4).max() < 0.001 for t in (100.6, 100.9)))
check(f"...a bar is {h.seg} samples of it ({h.seg / RATE * 1000:.2f} ms), the {O.BARS} of them the next "
      f"{O.BARS * h.seg / RATE * 1000:.0f} ms", h.seg == 53)
check(f"nothing fed for now (it's stopped), or from before any of it: nothing ({h.levels(101.6).max()}, "
      f"{h.levels(99.0).max()})", h.levels(101.6).max() == 0 and h.levels(99.0).max() == 0)
sig = 0.5 * np.sin(2 * np.pi * 90 * np.arange(RATE) / RATE)
full, low = O.Heard(), O.Heard()
feed(full, pcm_of(sig), 50.0)
feed(low, pcm_of(sig, 0.3), 50.0, gain=0.3)
a, b = full.levels(50.5), low.levels(50.5)
check(f"the volume down: the bars are the song's all the same ({a.mean():.3f} at full, {b.mean():.3f} at 30%; a "
      f"low note's bars are its wave: {a.min():.2f} to {a.max():.2f})", abs(a - b).max() < 0.005
      and 0.25 < a.mean() < 0.37 and a.max() > 0.45 and a.min() < 0.2)
h = O.Heard()
feed(h, pcm_of(loud), 10.0)                            # (heard from 10.0 to 10.5...)
feed(h, pcm_of(quiet), 30.0)                           # (...then a seek: what's fed next is heard from 30.0)
check(f"a jump (a seek): what was kept isn't shown as part of what's heard now ({h.levels(29.99).max()}, "
      f"{h.levels(30.2).max()})", h.levels(29.99).max() == 0 and h.levels(30.2).max() == 0)
h = O.Heard()
feed(h, pcm_of(np.full(RATE * 3, 0.25)), 0.0)          # (more than it keeps: a second)
check(f"three seconds fed: the last of it is there, the first long gone ({h.levels(2.5).max():.2f}, "
      f"{h.levels(1.5).max():.2f})", abs(h.levels(2.5).max() - 0.25) < 0.001 and h.levels(1.5).max() == 0)


# ---- the bars ----------------------------------------------------------------------------------------------------------
class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


clock = Clock()
fw = FakeWires()
bars = O.OledBars(O.Screen(fw), clock=clock, run=False)
n0 = len(fw.log)
bars.frame(clock.t)
check("the bars, with nothing playing: dark, and nothing sent", len(fw.log) == n0 and fw.heights() == [0] * 25
      and bars.idle(clock.t + 2))
feed(bars.heard_of, pcm_of(np.concatenate([np.full(RATE // 10, 0.2), np.zeros(RATE // 2)])), 1000.0)
bars.fed = clock.t                                     # (heard from now: a tenth of a second of it, then quiet)
clock.t = 1000.04
bars.frame(clock.t)
check(f"sound: every bar as tall as it's loud, by one and a half of the screen's height, as his visualizer has them "
      f"({fw.heights()})", fw.heights() == [int(0.2 * 32 * 1.5)] * 25 and fw.heights()[0] == 9 and not bars.idle(clock.t))
falls, sends = [], []
for k in range(1, 40):
    clock.t = 1000.1 + k * 0.04
    n = len(fw.log)
    bars.frame(clock.t)
    falls.append(fw.heights()[0])
    sends.append(len(fw.log) - n)
want = [int(0.2 * 0.85 ** (k + 1.5) * 48) for k in range(1, 40)]
check(f"quiet again: they fall slowly, 0.85 of what they were each frame ({falls[:12]}), down to nothing",
      falls[0] < 9 and all(abs(a - b) <= 1 for a, b in zip(falls, want)) and falls[-1] == 0
      and falls == sorted(falls, reverse=True))
check(f"...drawn only as they change ({sum(1 for s in sends if s)} of {len(sends)} frames sent anything; "
      f"{max(sends)} writes at most: a row or two)", all(s in (0, 2, 4) for s in sends)
      and sum(1 for s in sends if s) == len(set(falls)) - (1 if falls[0] == 9 else 0))
bars.h[:] = 0
bars.frame(clock.t + 0.04)
feed(bars.heard_of, pcm_of(np.full(RATE // 2, 1.0)), clock.t + 0.1)
bars.frame(clock.t + 0.3)
check(f"as loud as can be: all the way up, no further ({fw.heights()[:3]})", fw.heights() == [32] * 25)
clock.t += 5.0
bars.frame(clock.t)
was_idle = bars.idle(clock.t) and fw.heights() == [0] * 25
bars.hello()
hello = []
for k in range(1, 30):
    bars.frame(clock.t + k * 0.04)
    hello.append(fw.heights()[0])
clock.t += 3.0
check(f"hello (as it's turned on): its bars up a little, once, and down again ({hello[:8]}...), then left alone",
      was_idle and hello[0] == int(0.25 * 48) and hello == sorted(hello, reverse=True) and hello[-1] == 0
      and len(set(fw.heights())) == 1 and bars.idle(clock.t))
bars.close()
check("shut: dark and off", fw.heights() == [0] * 25 and fw.log[-1] == ("c", b"\xae") and fw.closed)
n = len(fw.log)
bars.frame(clock.t + 1)
check("...and nothing's written to it after that", len(fw.log) == n)

# on its own thread, by the clock
fw = FakeWires()
bars = O.OledBars(O.Screen(fw))
n0 = len(fw.log)
time.sleep(0.6)
idle = len(fw.log) - n0
t0 = time.monotonic() + 0.15
tone = pcm_of(0.5 * np.sin(2 * np.pi * 300 * np.arange(RATE) / RATE))


def writer():
    for k in range(0, len(tone), 480):                 # (as a player does: each piece a little before it's heard)
        wait = t0 + k / RATE - 0.12 - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        bars.heard(tone[k:k + 480].tobytes(), t0 + k / RATE)


threading.Thread(target=writer, daemon=True).start()
seen = []
end = t0 + 1.0
while time.monotonic() < end:
    hs = fw.heights()
    seen.append((time.monotonic() - t0, max(hs) if hs else -1))
    time.sleep(0.01)
frames = sum(1 for x in fw.log[n0:] if x[0] == "d")
early = [h for t, h in seen if t < -0.05]
during = [h for t, h in seen if 0.15 < t < 0.9]
check(f"on its own thread: nothing sent while nothing plays ({idle}); a second of a tone, written a moment before "
      f"it's heard: dark till it's heard ({max(early or [0])}), its bars up while it is ({min(during or [0])} to "
      f"{max(during or [0])}), drawn about {O.FPS:.0f} times a second ({frames} rows sent)",
      idle == 0 and max(early or [0]) == 0 and min(during or [0]) >= 12 and 20 <= frames <= 4 * 30)
until(lambda: fw.heights() == [0] * 25, 3)
bars.close()
check("...down again once it's over, and shut", fw.heights() == [0] * 25 and fw.closed)

# ---- another of your Pietatos' music: its bars sent, and taken -------------------------------------------------------
lv = np.array([0.0, 1.0, 0.5] + [0.2] * 22)
pkt = O.bars_packet(lv, 12.5)
got = O.read_bars(pkt)
check(f"a packet of bars: when it was sent, and each bar, to a 255th ({len(pkt)} bytes)",
      len(pkt) == O.BARS_HEAD.size + 25 and got[0] == 12.5 and abs(got[1] - lv).max() <= 1 / 255)
check("...anything else: not one of these", all(O.read_bars(x) is None for x in (
    pkt[:-1], pkt + b"\0", b"PG" + pkt[2:], pkt[:2] + b"\x02" + pkt[3:], G.music_packet((1, 2, 3), 0.0), b"")))
check("what a beacon says of an OLED: where its bars are taken, or nothing",
      O.oled_clean({"port": 5445, "more": 1}) == {"port": 5445}
      and all(O.oled_clean(x) is None for x in (None, {}, {"port": 0}, {"port": True}, {"port": "5445"},
                                                {"port": 70000}, "5445", [5445])))
catch = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
catch.bind(("127.0.0.1", 0))
catch.settimeout(0.5)


def caught():
    """The next packet's bars, or None (none came)."""
    try:
        return O.read_bars(catch.recv(256))
    except OSError:
        return None


clock.t = 2000.0
out = O.BarsOut(clock=clock, run=False)
out.heard(pcm_of(loud).tobytes(), 2000.0)
check("the one playing, with nobody to tell: nothing kept, nothing sent", out.heard_of.t_end is None
      and out.frame(2000.1) is False and caught() is None)
out.aim([("127.0.0.1", catch.getsockname()[1])])
feed(out.heard_of, pcm_of(np.concatenate([loud, quiet])), 2000.0)   # (loud till 2000.5, then quiet)
sent1 = out.frame(2000.2)
b1 = caught()
check(f"...with one of yours' OLED to tell: its bars as the sound's heard, a packet "
      f"({b1 and round(float(b1[1].max()), 2)})", sent1 is True and b1 is not None and b1[0] == 2000.2
      and abs(b1[1] - 0.4).max() <= 1 / 255)
said = [out.frame(2000.6 + k * 0.04) for k in range(O.QUIET_SAID + 3)]
zeros = [caught() for _ in range(O.QUIET_SAID)]
check(f"...quiet again: said {O.QUIET_SAID} times, then nothing more ({said})",
      said == [True] * O.QUIET_SAID + [False] * 3 and all(z is not None and not z[1].any() for z in zeros)
      and caught() is None)
out.close()
check("...shut: nothing more goes", out.frame(2001.0) is False and caught() is None)

taken = []
theirs = {"10.0.0.7": "Den", "10.0.0.8": "Kitchen"}
ins = O.BarsIn(taken.append, theirs.get, port=0, clock=clock, listen=False)
check("the one with the OLED: bars from an address that isn't one of yours aren't taken",
      ins.take(pkt, "10.0.0.99", 100.0) is False and taken == [])
check("...from one of yours: taken", ins.take(pkt, "10.0.0.7", 100.0) is True and len(taken) == 1
      and abs(taken[0] - lv).max() <= 1 / 255)
check("...an older packet, come late: not shown", ins.take(O.bars_packet(lv, 12.4), "10.0.0.7", 100.02) is False
      and ins.take(O.bars_packet(lv, 12.54), "10.0.0.7", 100.04) is True and len(taken) == 2)
check("...another of yours, while that one's playing: not yet",
      ins.take(O.bars_packet(lv, 500.0), "10.0.0.8", 100.1) is False and len(taken) == 2)
check(f"...once it's been quiet {O.HOLD} seconds: the other's",
      ins.take(O.bars_packet(lv, 500.1), "10.0.0.8", 100.04 + O.HOLD + 0.1) is True and ins.source == "10.0.0.8")
check("...one that's started again (its clock too): taken again after the same quiet",
      ins.take(O.bars_packet(lv, 3.0), "10.0.0.8", 200.0) is True and len(taken) == 4)
check("...not a packet of bars: nothing", ins.take(b"hello", "10.0.0.8", 200.1) is False)
ins.close()
fw = FakeWires()
bars = O.OledBars(O.Screen(fw), clock=clock, run=False)
clock.t = 3000.0
bars.told(np.full(25, 0.5))
bars.frame(clock.t)
first = fw.heights()
bars.frame(clock.t + 0.2)
held = fw.heights()
fell = []
for k in range(1, 40):
    bars.frame(clock.t + O.THEIRS_KEPT + k * 0.04)
    fell.append(fw.heights()[0])
check(f"another's bars on the OLED: as tall as they're loud there ({first[0]}), kept while they're new ({held[0]}), "
      f"and falling once no more come ({fell[:6]}...)", first == [24] * 25 and held == [24] * 25
      and fell == sorted(fell, reverse=True) and fell[0] < 24 and fell[-1] == 0)
clock.t = 3010.0
feed(bars.heard_of, pcm_of(np.full(RATE // 2, 0.2)), 3010.0)
bars.own_at = bars.fed = clock.t                       # (this Pi's own song, heard from now)
bars.told(np.full(25, 1.0))
bars.frame(3010.1)
own = fw.heights()
clock.t = 3010.1 + O.OWN_FIRST + 0.5
bars.told(np.full(25, 1.0))
bars.frame(clock.t)
check(f"...this Pi's own music comes first ({own[0]}, not 32); once it's over, another's again ({fw.heights()[0]})",
      own == [9] * 25 and fw.heights() == [32] * 25)
bars.close()
ins = O.BarsIn(taken.append, lambda ip: "This one" if ip.startswith("127.") else None, port=0)
out = O.BarsOut()
out.aim([("127.0.0.1", ins.port)])
n = len(taken)
t0 = time.monotonic() + 0.1
out.heard(pcm_of(np.full(RATE // 2, 0.3)).tobytes(), t0)
came = until(lambda: len(taken) >= n + 8, 2)
loudest = max((float(x.max()) for x in taken[n:]), default=0)
until(lambda: time.monotonic() > t0 + 1.2, 3)
m1 = len(taken)
time.sleep(0.3)
check(f"over the network (here, to itself): {m1 - n} packets for half a second of sound, about {O.FPS:.0f} a second, "
      f"as loud as it is ({loudest:.2f}), and none once it's over", came and 8 <= m1 - n <= 30
      and abs(loudest - 0.3) < 0.01 and len(taken) == m1)
out.close()
ins.close()
catch.close()

# ---- media mode -----------------------------------------------------------------------------------------------------
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
    last = None
    def show(self, img): FB.last = img.copy()
    def show_part(self, img, box): FB.last = img.copy()
    def invalidate(self): pass
    def close(self): pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.set_setting("name", "gpi")
m.oled_port = 0                                        # (your others' bars: taken at any port that's free, here)
SETTINGS = next(k for k, t in enumerate(g.LIBRARY) if t.get("type") == "settings")
m.view, m.tab, m.set_page = "list", SETTINGS, "display"   # (Settings > Screen: its row's there)


def rows():
    return [k for k, _, _ in m.settings_rows()]


def web_rows():
    return {r["key"]: r for s in m.web_settings()["sections"] for r in s["rows"]}


# where it can be
MODEL = S + "/model"
open(MODEL, "w").write("Raspberry Pi 4 Model B Rev 1.5\x00")
check(f"this machine (no Pi): no OLED in Settings > Screen, here or on the web page ({m.oled_can()})",
      not m.oled_can() and "oled" not in rows() and "oled" not in web_rows() and rows()[0] == "screen")
SO.PI_MODEL, SO.is_pc, SO.is_handheld = MODEL, (lambda: False), (lambda: False)
m.case = None
r = rows()
check(f"a Pi on a TV or monitor: Settings > Screen > Waveshare 2.23 OLED, the last of its rows: Off, or Music bars "
      f"({m.settings_rows()[r.index('oled')] if 'oled' in r else None})", m.oled_can() and r[-1] == "oled"
      and r[0] == "screen" and m.settings_rows()[-1] == ("oled", "Waveshare 2.23 OLED", ["Off", "Music bars"])
      and m.settings_place("oled") == ("display", len(r) - 1)
      and "oled" not in [k for k, _, _ in m.settings_root_rows()])
m.case = "2w"
in_case = m.oled_can(), "oled" in rows(), "oled" in web_rows()
m.case = None
SO.is_handheld = lambda: True
on_handheld = m.oled_can(), "oled" in rows()
SO.is_handheld, SO.is_pc = (lambda: False), (lambda: True)
on_pc = m.oled_can(), "oled" in rows()
SO.is_pc = lambda: False
check(f"...not in a GPi Case (its screen has the pins: {in_case}), on a handheld ({on_handheld}) or a PC ({on_pc})",
      in_case == (False, False, False) and on_handheld == (False, False) and on_pc == (False, False) and m.oled_can())

# picked: lit
made = []


def make_wires(spi):
    made.append((spi, FakeWires()))
    return made[-1][1]


m.oled_wires = make_wires
m.oled_spi = S + "/spidev"
open(m.oled_spi, "wb").close()
m.glow_configs = [S + "/config.txt"]
open(S + "/config.txt", "w").write("dtparam=audio=on\n")
m.set_sel = rows().index("oled")
m.dirty = True
m.flush()
check(f"its row: Off ({m.oled_value()!r}), and nothing's lit", m.oled_value() == "Off" and m.oled is None
      and not m.oled_wanted())
m.press("right")
fw = made[-1][1] if made else None
check(f"▶: Music bars: the OLED's started, on the Pi's SPI ({made[-1][0] if made else None}), and kept "
      f"({m.setting('oled')!r}, {m.oled_value()!r})", m.oled is not None and m.oled_wanted() and len(made) == 1
      and made[0][0] == m.oled_spi and fw.log[:2] == [("reset",), ("c", b"\xae")] and ("c", b"\xaf") in fw.log
      and m.setting("oled") == "Music bars" and m.oled_value() == "Music bars" and not m.oled_note)
check("...its SPI's there: config.txt left as it is", open(S + "/config.txt").read() == "dtparam=audio=on\n"
      and not m.oled_restart)
came_up = until(lambda: (fw.heights() or [0])[0] >= 8, 2)
check(f"...and its bars come up once, to say it's lit, and go down again ({came_up})",
      came_up and until(lambda: fw.heights() == [0] * 25, 3))
m.dirty = True
m.flush()
FB.last.convert("RGB").save(S + "/settings_oled.png")

# music: through party mode's player, its bars as it's heard
tt = np.arange(RATE * 4) / RATE
song = np.where((tt >= 1.5) & (tt < 2.5), 0.5 * np.sin(2 * np.pi * 440 * tt), 0.0)
SONG = HOME + "/Music/Loud in the middle.wav"
with wave.open(SONG, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE)
    w.writeframes(pcm_of(song).tobytes())
item = g.item(SONG, "Loud in the middle", "audio", SONG)


def watch(upto):
    """The tallest bar on the OLED, every hundredth of a second, till the song's `upto` seconds in: [(seconds into
    the song, its height)]. (A look while it's between two of its rows: not kept.)"""
    start, out = m.proc.player.anchor[0], []
    while time.monotonic() < start + upto:
        m.glow_tick(time.monotonic())
        hs = fw.heights()
        if hs is not None:
            out.append((time.monotonic() - start, max(hs)))
        time.sleep(0.01)
    return out


def bars_seen(seen):
    before = [h for t, h in seen if 0.3 < t < 1.35]
    during = [h for t, h in seen if 1.7 < t < 2.45]
    after = [h for t, h in seen if 3.3 < t < 3.6]
    return before, during, after


for vol in (100, 30):
    m.volume = vol
    m.play([item], 0)
    on = type(m.proc).__name__
    seen = watch(3.7)
    before, during, after = bars_seen(seen)
    check(f"a song, at volume {vol}: on party mode's player, on its own ({on}), and its bars are its sound as it's "
          f"heard: dark through its quiet start ({max(before or [-1])}), up through its loud second "
          f"({min(during or [-1])} to {max(during or [-1])} of 32), down again after ({max(after or [-1])})",
          on == "PartyProc" and m.party is None and not spawned and before and max(before) == 0
          and during and min(during) >= 14 and max(during) <= 26 and after and max(after) == 0)
    m.stop()
m.volume = 100

# in another's party: by its leader's clock
m.party = {"lead": False, "offset": 5.0}
tone1 = pcm_of(np.full(4800, 0.3)).tobytes()
m.oled_heard(tone1, time.monotonic() + 5.0 + 0.2, 1.0)   # (heard 0.2 s from now, as the leader's clock has it)
t_end = m.oled.heard_of.t_end
m.party = None
check(f"in another's party: its sound's times are the leader's clock, made this one's "
      f"({t_end - time.monotonic():.2f} s from now)", 0.2 < t_end - time.monotonic() < 0.31)

# off: music as ever
m.set_sel = rows().index("oled")
m.press("left")
check(f"◀: Off: dark and off, and let go of ({m.setting('oled')!r})", m.oled is None and m.setting("oled") == "Off"
      and fw.closed and fw.log[-1] == ("c", b"\xae") and fw.heights() == [0] * 25)
m.play([item], 0)
check(f"...and music's as ever, the plain player's ({spawned[-1:] and spawned[-1][0]})",
      spawned and spawned[-1][0] == SONG and type(m.proc).__name__ == "Proc")

# turned on while a song plays: moved to the player that says what's heard
m.pos = 1.0
m.view, m.tab = "list", SETTINGS                       # (Settings again, the song playing on)
m.set_sel = rows().index("oled")
m.press("right")
fw = made[-1][1]
check(f"turned on with a song playing on the plain player: the song's moved to party mode's player, from where it "
      f"was ({type(m.proc).__name__}, {getattr(getattr(m.proc, 'player', None), 'pos0', None)})",
      m.oled is not None and type(m.proc).__name__ == "PartyProc" and m.proc.player.pos0 == 1.0)
seen = watch(1.5)
during = [h for t, h in seen if 0.75 < t < 1.4]         # (from a second in: its loud second's from 0.5 to 1.5 now)
check(f"...and shown from there ({min(during or [-1])} to {max(during or [-1])})", during and min(during) >= 14)
m.stop()

# your LEDs, with the OLED on: as they were without it
m.lamps_port = 0
m.lamps_start()


def board():
    """An ESP32 board on the network, saying it's there."""
    return m.glow_lamps.take(G.lamp_packet("Desk", 1, 0.0), "10.0.0.9", time.monotonic())


def ticks(secs):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        m.glow_tick(time.monotonic())
        time.sleep(0.02)


m.set_setting("glow_beat", "Off")
there = board()
m.glow_seen = 0.0
m.play([item], 0)
ticks(1.4)
check(f"a board on the network, Pulse to music off: the song's on party mode's player for the OLED alone "
      f"({type(m.proc).__name__}, beats found: {getattr(m.proc.player, 'beats', None) is not None}), and nothing of "
      f"it goes to the board, as on the plain player ({m.glow_to}, {m.glow_out})",
      there and type(m.proc).__name__ == "PartyProc" and m.proc.player.beats is None
      and m.glow_to == [("10.0.0.9", G.GLOW_PORT)] and m.glow_out is None)
m.stop()
m.set_setting("glow_beat", "On")
m.glow_lamps.heard.clear()                             # (the board's gone...)
m.glow_seen = 0.0
m.play([item], 0)
first = m.proc
ticks(0.3)
none_yet = first.player.beats is None
board()                                                # (...and turns up again, just into the next song)
m.glow_seen = m.glow_mind_at = 0.0
ticks(0.3)
check(f"Pulse to music on, and a board turning up just into a song that's there for the OLED alone: the song's moved "
      f"to a player that finds its beats, as from the plain player (none before: {none_yet}; now: "
      f"{getattr(m.proc.player, 'beats', None) is not None})", none_yet and m.proc is not first
      and type(m.proc).__name__ == "PartyProc" and m.proc.player.beats is not None and m.oled is not None)
second = m.proc
m.glow_mind_at = 0.0
ticks(0.9)
check(f"...once, and its colour goes to the board now ({m.glow_out is not None})", m.proc is second
      and m.glow_out is not None and m.glow_out.to == (("10.0.0.9", G.GLOW_PORT),))
m.stop()
m.lamps_stop()
out, m.glow_out = m.glow_out, None
if out is not None:
    out.close()
m.glow_to, m.glow_seen = (), 0.0

# an LED backlight on the same pin: one of them
m.glow_can = lambda: True
m.glow_spi, m.glow_port = S + "/spi-leds", 0
open(m.glow_spi, "wb").close()
m.msg = ""
took = m.glow_pick("glow_on", "On")
check(f"the LED backlight turned on (its LEDs are on the same pin): the OLED goes off, and that's said "
      f"({m.msg!r})", took is True and m.glow_grid is not None and m.oled is None and m.setting("oled") == "Off"
      and fw.closed and m.msg == "The OLED is off: the LEDs use its pin")
m.msg = ""
m.set_sel = rows().index("oled")
m.press("right")
fw = made[-1][1]
check(f"...and the OLED turned on again: the LEDs go off ({m.msg!r})", m.oled is not None
      and m.glow_grid is None and m.setting("glow_on") == "Off" and m.setting("oled") == "Music bars"
      and m.msg == "The LED backlight is off: the OLED uses its pin")
m.oled_stop()
m.set_setting("glow_on", "On")
m.oled_start()
check(f"both set, somehow: the LEDs keep the pin, and its row says so ({m.oled_value()!r})", m.oled is None
      and m.oled_value() == "The LED backlight has its pin")
m.set_setting("glow_on", "Off")
vars(m).pop("glow_can")

# the Pi's SPI not on
m.oled_pick("Off")
check("(the LED backlight, turned on before: its own lines went into config.txt, and a restart was asked for)",
      "core_freq_min" in open(S + "/config.txt").read() and m.glow_restart)
open(S + "/config.txt", "w").write("dtparam=audio=on\n")
m.glow_restart = False
m.oled_spi = S + "/no-spidev"
m.msg = ""
m.press("right")
conf = open(S + "/config.txt").read()
check(f"the Pi's SPI not on: turned on in config.txt, and a restart asked for ({m.msg!r}; its row: "
      f"{m.oled_value()!r})", m.oled is None and m.oled_restart and "dtparam=spi=on" in conf
      and "core_freq_min" not in conf and conf.startswith("dtparam=audio=on\n") and G.BLOCK[0] in conf
      and m.msg == "Restart the Pi to turn its SPI on for the OLED" and m.oled_value() == "Restart the Pi"
      and m.setting("oled") == "Music bars")
wr = web_rows().get("oled") or {}
check(f"...the web page's Settings say so too ({wr.get('status')!r})", wr.get("value") == "Music bars"
      and wr.get("status") == "Restart the Pi to turn its SPI on" and wr.get("choices") == ["Off", "Music bars"])
m.oled_pick("Off")
m.oled_restart = False
grid_part = G.config_with_spi("dtparam=audio=on\n", ["dtparam=spi=on", "core_freq_min=500"])
open(S + "/config.txt", "w").write(grid_part)
m.oled_pick("Music bars")
check(f"...with the LED backlight's own lines there already: left as they are ({m.oled_value()!r})",
      open(S + "/config.txt").read() == grid_part and not m.oled_restart and m.oled_value() == "No SPI here")
m.oled_pick("Off")
m.oled_spi = S + "/spidev"

# its pins taken, or none
for err, says in ((errno.EBUSY, "Its pins are in use"), (errno.ENODEV, "No GPIO here")):
    def no_wires(spi, err=err):
        raise OSError(err, os.strerror(err))
    m.oled_wires = no_wires
    m.msg = ""
    m.oled_pick("Music bars")
    check(f"its pins not to be had ({os.strerror(err)}): not lit, and said ({m.msg!r})", m.oled is None
          and m.oled_value() == says and m.msg == f"The OLED can't be lit: {says[0].lower()}{says[1:]}"
          and web_rows()["oled"].get("tone") == "bad")
    m.oled_pick("Off")
bad = []


def bad_wires(spi):
    bad.append(FakeWires(fails=errno.EIO))
    return bad[-1]


m.oled_wires = bad_wires
m.oled_pick("Music bars")
check(f"the screen not answering as it's started: not lit, its wires let go of ({m.oled_value()!r})",
      m.oled is None and bad and bad[0].closed and m.oled_value() == "Input/output error")
m.oled_pick("Off")
m.oled_wires = make_wires

# the web page's Settings
wr = web_rows().get("oled") or {}
check(f"the web page's Settings: Waveshare 2.23 OLED, the last of Screen's ({wr.get('label')!r}, "
      f"{wr.get('value')!r}, {wr.get('note')!r})",
      wr.get("kind") == "choice" and wr.get("value") == "Off" and wr.get("label") == "Waveshare 2.23 OLED"
      and wr.get("note") == "The OLED HAT on the Pi's pins: bars that move with the music, this Pi's or another "
                            "of yours'."
      and [(s["title"], s["rows"][0]["key"], s["rows"][-1]["key"]) for s in m.web_settings()["sections"]
           if s["id"] == "screen"] == [("Screen", "screen", "oled")]
      and "status" not in wr)
said = m.web_settings_do({"key": "oled", "value": "Music bars"})
fw = made[-1][1]
check(f"...picked there: lit ({said})", said == {"ok": True} and m.oled is not None and web_rows()["oled"]["value"]
      == "Music bars")
said = m.web_settings_do({"key": "oled", "value": "Fireworks"})
check(f"...something it can't be: not taken ({said})", "error" in said and m.setting("oled") == "Music bars")
m.case = "2w"
said = m.web_settings_do({"key": "oled", "value": "Off"})
m.case = None
check(f"...where there can't be one: no such setting to pick ({said})", "error" in said
      and m.setting("oled") == "Music bars")

# ---- another of your Pietatos' music, on this one's OLED ----------------------------------------------------------
m.oled_stop()
m.oled_start()
fw = made[-1][1]
beacon = m.share_beacon("gpi", full=True)
check(f"lit: your others' music is listened for, and its beacon says where ({beacon.get('oled')})",
      m.oled_in is not None and beacon.get("oled") == {"port": m.oled_in.port} and m.oled_in.port > 0
      and "oled" not in m.share_beacon("gpi"))
news = g.group_news(dict(beacon, hw={}), {}, time.time())
kept = g.group_news({"id": "x"}, news, time.time())
check(f"...as one of your others takes it from its beacon ({news.get('oled')}), and keeps it from the one to "
      f"everyone ({kept.get('oled')})", news.get("oled") == {"port": m.oled_in.port} == kept.get("oled")
      and g.group_news(dict(beacon, hw={}, oled={"port": "x"}), {}, time.time()).get("oled") is None)
teller = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def tell(level, secs):
    """Another of yours, playing: its bars, this loud, for this long (from this Pi itself, here)."""
    end = time.monotonic() + secs
    while time.monotonic() < end:
        teller.sendto(O.bars_packet(np.full(25, level), time.monotonic()), ("127.0.0.1", m.oled_in.port))
        time.sleep(0.04)


threading.Thread(target=tell, args=(0.5, 0.8), daemon=True).start()
up = until(lambda: (fw.heights() or [0])[0] == 24, 2)
down = until(lambda: fw.heights() == [0] * 25, 4)
check(f"one of yours playing: its bars are on this one's OLED as they come ({up}), and down once it stops ({down})",
      up and down)
PEER = "http://10.0.0.7:5432"
check("...bars from somewhere that isn't one of yours: not shown",
      m.oled_in.take(O.bars_packet(np.full(25, 1.0), 1.0), "10.0.0.7", time.monotonic() + 10) is False)
m.pie.heard[PEER] = {"host": "den", "seen": time.time() + 3600, "peer": True}
m.glow_names = None
check("...from one of yours, by its address: shown",
      m.oled_in.take(O.bars_packet(np.full(25, 1.0), 2.0), "10.0.0.7", time.monotonic() + 20) is True)
until(lambda: fw.heights() == [0] * 25, 4)
m.play([item], 0)                                      # (this one's own song: quiet for its first second and a half)
start = m.proc.player.anchor[0]
threading.Thread(target=tell, args=(1.0, 1.0), daemon=True).start()
tall = []
while time.monotonic() < start + 1.3:
    hs = fw.heights()
    if hs is not None and time.monotonic() > start + 0.3:
        tall.append(max(hs))
    time.sleep(0.01)
check(f"its own music playing (quiet, just now) while another's bars come: its own are shown ({max(tall or [-1])})",
      tall and max(tall) == 0)
m.stop()
del m.pie.heard[PEER]
m.glow_names = None
m.oled_pick("Off")
check("turned off: no more listened for, and its beacon says nothing of it", m.oled_in is None
      and "oled" not in m.share_beacon("gpi", full=True))

# ---- this one's music, on another of yours' OLED --------------------------------------------------------------------
catch = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
catch.bind(("127.0.0.1", 0))
catch.settimeout(0.02)
THERE = "http://127.0.0.1:5432"                        # (one of yours with an OLED lit: here, this Pi itself)


def oled_there(on=True):
    m.pie.heard[THERE] = {"host": "den", "seen": time.time() + 3600, "peer": True}
    if on:
        m.pie.heard[THERE]["oled"] = {"port": catch.getsockname()[1]}


def look():
    m.oled_seen = 0.0
    m.oled_tick(time.monotonic())


def heard_there(upto):
    """Its bars as they come there, till the song's `upto` seconds in: [(seconds into the song, the tallest)]."""
    start, got = m.proc.player.anchor[0], []
    while time.monotonic() < start + upto:
        look()
        try:
            p = O.read_bars(catch.recv(256))
        except OSError:
            continue
        if p is not None:
            got.append((time.monotonic() - start, float(p[1].max())))
    return got


check(f"no OLED here, none on your others: music's the plain player's ({m.oled_peers()})", m.oled_peers() == []
      and not m.oled_wanted())
oled_there(False)
check("...one of yours on, with no OLED: still", m.oled_peers() == [] and not m.oled_wanted())
oled_there()
check(f"one of yours has its OLED lit: this one's music is wanted on party mode's player ({m.oled_peers()})",
      m.oled_peers() == [("127.0.0.1", catch.getsockname()[1])] and m.oled_wanted())
m.set_setting("share", "Off")
off = m.oled_peers()
m.set_setting("share", "On")
check(f"...not with Share with other Pietatos off ({off})", off == [] and m.oled_wanted())
spawned.clear()
m.play([item], 0)
on = type(m.proc).__name__
look()
got = heard_there(3.7)
before, during, after = bars_seen(got)
check(f"a song here: on party mode's player ({on}), its bars sent there as it's heard: {len(got)} packets, quiet "
      f"through its start ({max(before or [-1]):.2f}), as loud as it is through its loud second "
      f"({min(during or [-1]):.2f} to {max(during or [-1]):.2f}), and no more once it's quiet "
      f"({len(after)} after)", on == "PartyProc" and not spawned and m.oled_out is not None and m.oled is None
      and len(got) >= 20 and max(before or [0]) == 0 and during and min(during) >= 0.29 and max(during) <= 0.55
      and not any(h for h in after))
m.stop()
del m.pie.heard[THERE]
m.oled_out.fed = time.monotonic() - 100
look()
check("that one gone: its bars' sender's let go of, and the next song's the plain player's", m.oled_out is None
      and not m.oled_wanted())
m.play([item], 0)
plain = type(m.proc).__name__
oled_there()
look()
moved = type(m.proc).__name__
check(f"a song only just begun on the plain player ({plain}) when one of yours' OLED turns up: moved to party "
      f"mode's player ({moved})", plain == "Proc" and moved == "PartyProc")
m.stop()
del m.pie.heard[THERE]
look()
m.play([item], 0)
m.started = time.monotonic() - SO.OLED_CATCH - 5       # (well under way)
oled_there()
look()
check(f"...one well under way: left as it is; the next has them ({type(m.proc).__name__})",
      type(m.proc).__name__ == "Proc" and m.oled_wanted())
m.stop()
del m.pie.heard[THERE]
look()
catch.close()
m.set_setting("oled", "Music bars")

# at start-up, and as it goes
m.oled_stop()
m.oled_start()
fw = made[-1][1]
check("at start-up, set to Music bars: lit", m.oled is not None and ("c", b"\xaf") in fw.log)
m.oled_start()
check("...once", len([x for x in made if x[1] is fw]) == 1 and made[-1][1] is fw)
m.active = False
m.shutdown()
check("Pietato going: its OLED dark and off", m.oled is None and fw.closed and fw.log[-1] == ("c", b"\xae"))

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
sys.exit(0 if all(ok_all) else 1)
