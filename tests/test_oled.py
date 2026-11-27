"""An OLED HAT (pitato/oled.py, screens/oled.py): a Waveshare 2.23inch OLED on a Pi's pins, showing bars that move with
the music, or a picture. First the pieces on their own: what's asked of the kernel for its two pins (the numbers and
the shapes of linux/gpio.h, written out again here; the chip a Pi's own pins are on, whatever its number, a Pi 5's
too; none, or the pins taken); its SPI; a command or the picture, by its D/C pin; the screen started as Waveshare's
driver starts it, then only the rows that changed, and dark and off as it's shut; the picture for the bars (as that
driver packs one: 25 bars, 4 wide, up from the bottom); the sound as it's heard (the sound heard now, not what's just
been written; whatever the volume; nothing for now, a jump); and the bars themselves (as tall as the sound's loud, up
at once, falling slowly, drawn only as they change, 25 times a second). Then media mode: Settings > Screen > Waveshare
2.23 OLED only on a Pi with its pins free (not in a GPi Case, on a handheld or a PC); picked, it's lit, and music
plays through party mode's player (a song already playing moved to it), its bars up as the loud part of a song is
heard, whatever the volume; one that's in another's party, by its leader's clock; an LED backlight on the same pin
turned off for it, and the other way round; the Pi's SPI not on (turned on in config.txt, a restart asked for; the LED
backlight's own part left as it is), its pins taken; the web page's Settings; and dark as Pietato goes. And another of
your Pietatos' music: the one playing sends its bars as they're heard there (a packet each, to yours with an OLED lit,
as their beacons say; its music on party mode's player for it), and the one with the OLED takes them from your
Pietatos only, whichever's playing, and shows them while its own Pi plays nothing. And a picture in place of its bars,
the same row's other choices (◀ ▶ through them all, round and round), there whatever plays: the time (as the clock's
set), the weather (the time while there's none, or it's old), your stocks' and coins' prices one at a time (fetched
for it every few minutes, the prices alone, while the Finance tab isn't open), the Bot's own face (as its Character
has it, blinking and glancing about), or each in turn; dimmer than the bars, moved a little each minute, drawn only as
it changes; no music moved to party mode's player for one, nor your others' bars asked for. Set to its bars with no
music for a while: the time, gone at once as music's heard (even its quiet start), not shown between two songs."""
import ctypes, errno, os, shutil, socket, sys, threading, time, wave
from paths import SP, TESTS  # noqa: E402  (this test's folder of work; tests)
sys.path.insert(0, TESTS)
import numpy as np
from PIL import Image
import pietato_all as g
import pitato.oled as O
import pitato.screens.oled as SO
import pitato.glow as G
import pitato.face as FACE

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
dot = (b"\x01" + bytes(127), bytes(128), bytes(128), bytes(128))    # (one pixel lit: its top left)
check("a picture upside down: its last row first, each from its other end, each byte's pixels the other way up (a "
      "dot at its top left: at its bottom right); twice, as it was",
      O.turned(dot) == (bytes(128), bytes(128), bytes(128), bytes(127) + b"\x80")
      and O.turned(O.turned(tuple(rows))) == tuple(rows) and O.turned(O.BLANK) == O.BLANK)
fw = FakeWires()
scr = O.Screen(fw, flip=True)
n = len(fw.log)
scr.show(dot)
lit = fw.lit()
check("the screen, upside down (a Pi that sits the other way up): started just the same, and each picture sent "
      "turned: the dot's at the bottom right, and only that row's sent",
      fw.log[:1 + len(WAVESHARE)] == [("reset",)] + [("c", bytes((c,))) for c in WAVESHARE]
      and fw.log[n:] == [("c", b"\xb3\x04\x10"), ("d", bytes(127) + b"\x80")] and lit[31, 127] == 1
      and lit.sum() == 1 and scr.shown == dot)
n = len(fw.log)
scr.turn(False)
back, sent = fw.lit(), len(fw.log) - n
scr.turn(False)
check(f"...turned the right way up as it is: what it shows, sent again that way (the two rows that changed: {sent} "
      f"writes), and nothing when it's that way already", back[0, 0] == 1 and back.sum() == 1 and sent == 4
      and len(fw.log) == n + sent and scr.flip is False and O.Screen(FakeWires()).flip is False)

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

# a picture in place of its bars: for the quiet alone (its bars picked), or whatever plays (a picture picked)
pic = O.quiet_time("7:49", "PM")
check("a picture as the screen's rows: each byte 8 pixels down, the top one its lowest bit (as the bars' are)",
      (FakeWires.lit(type("W", (), {"rows": lambda self: O.picture_rows(pic)})()) == np.asarray(pic, np.uint8)).all()
      and O.picture_rows(Image.new("1", (128, 32), 0)) == O.BLANK)
quiet_rows, asked, pin, again = O.picture_rows(pic), [], False, None


def a_picture(now, quiet):
    """As screens/oled.py's: one for the quiet alone (its bars picked), or (pin) whatever plays."""
    asked.append((now, quiet))
    return (quiet_rows, again) if (quiet or pin) and quiet_rows is not None else None


fw = FakeWires()
bars = O.OledBars(O.Screen(fw), clock=clock, run=False, picture=a_picture)
clock.t = 3000.0
bars.fed = clock.t                                     # (music, a moment ago)
n0 = len(fw.log)
bars.rest(clock.t + O.QUIET_AFTER - 0.5)
check(f"no music for a moment (between two songs, say): not quiet yet: still dark, nothing sent ({asked})",
      len(fw.log) == n0 and asked == [(clock.t + O.QUIET_AFTER - 0.5, False)] and not bars.resting)
bars.rest(clock.t + O.QUIET_AFTER + 0.1)
dim_at = fw.log.index(("c", bytes([O.CONTRAST])), n0) if ("c", bytes([O.CONTRAST])) in fw.log[n0:] else -1
check(f"...for a while: quiet: the picture for it, dimmer (the bars: {O.BRIGHT:#x}; this: {O.DIM:#x}), dimmed "
      f"before it's drawn", fw.rows() == list(quiet_rows) and fw.log[dim_at + 1] == ("c", bytes([O.DIM]))
      and dim_at >= n0 and all(x[0] == "c" or k > dim_at for k, x in enumerate(fw.log[n0:], n0)) and bars.resting
      and asked[-1][1] is True and not bars.pinned)
n = len(fw.log)
bars.rest(clock.t + O.QUIET_AFTER + 0.4)
check("...the same again: nothing sent", len(fw.log) == n and len(asked) == 3)
bars.fed = clock.t = clock.t + 10                      # (music again: its quiet start)
bars.rest(clock.t)
bars.frame(clock.t)
check("music again (its quiet start, even): dark at once, as bright as ever", fw.heights() == [0] * 25
      and fw.log[-2:] == [("c", bytes([O.CONTRAST])), ("c", bytes([O.BRIGHT]))] and not bars.resting)
feed(bars.heard_of, pcm_of(np.full(RATE // 2, 1.0)), clock.t)
bars.frame(clock.t + 0.1)
check(f"...its bars, as loud as it is ({fw.heights()[:2]})", fw.heights() == [32] * 25)
for k in range(80):                                    # (over: its bars fall)
    bars.frame(clock.t + 0.6 + k * 0.04)
bars.rest(clock.t + 4.0)
check("...a moment after it's over: dark still", fw.heights() == [0] * 25 and not bars.resting)
bars.rest(clock.t + O.QUIET_AFTER + 4.0)
check("...quiet a while after: the picture again", fw.rows() == list(quiet_rows) and bars.resting)
kept, quiet_rows = quiet_rows, None
bars.rest(clock.t + O.QUIET_AFTER + 4.3)
check("...no picture for it any more: dark, as bright as ever for the next bars", fw.heights() == [0] * 25
      and fw.log[-1] == ("c", bytes([O.BRIGHT])) and not bars.resting)
n = len(fw.log)
bars.rest(clock.t + O.QUIET_AFTER + 4.6)
check("...and left so", len(fw.log) == n)
quiet_rows, pin = kept, True                           # (a picture picked: whatever plays)
bars.fed = clock.t = clock.t + 20
feed(bars.heard_of, pcm_of(np.full(RATE // 2, 1.0)), clock.t)
bars.frame(clock.t + 0.1)
up, n = fw.heights(), len(fw.log)
bars.rest(clock.t + 0.2)
check(f"a picture picked while music plays (its bars are up: {up[:1]}): the picture, dimmer, in their place",
      up == [32] * 25 and fw.rows() == list(quiet_rows) and bars.resting and bars.pinned
      and fw.log[n:n + 2] == [("c", bytes([O.CONTRAST])), ("c", bytes([O.DIM]))])
bars.wake.clear()
bars.heard(pcm_of(np.full(480, 1.0)).tobytes(), clock.t + 0.5)
woke = bars.wake.is_set()
bars.poke()
check("...what's played doesn't wake it (its picture's not for the quiet alone); what's picked next does (poke)",
      not woke and bars.wake.is_set())
bars.wake.clear()
n = len(fw.log)
bars.rest(clock.t + 0.5)
check("...the music still playing: the picture stays, nothing sent", len(fw.log) == n and bars.resting)
again = 0.05
bars.rest(clock.t + 0.6)
soon = bars.again
again = 30.0
bars.rest(clock.t + 0.7)
late = bars.again
again = 0.0001
bars.rest(clock.t + 0.8)
check(f"...asked for again as soon as it says (a blink's next frame: {soon}), a quarter of a second at most "
      f"({late}), never at once ({bars.again})", soon == 0.05 and late == O.IDLE_EVERY and bars.again == 0.02)
again, pin = None, False                               # (its bars picked again, music playing)
bars.fed = clock.t = clock.t + 5
feed(bars.heard_of, pcm_of(np.full(RATE // 2, 1.0)), clock.t)
bars.rest(clock.t + 0.05)
dark = fw.heights() == [0] * 25 and fw.log[-1] == ("c", bytes([O.BRIGHT])) and not bars.resting and not bars.pinned
bars.frame(clock.t + 0.1)
check("its bars picked again: dark at once, as bright as ever, and up from nothing as the music's heard",
      dark and fw.heights() == [32] * 25)
plain = O.OledBars(O.Screen(FakeWires()), clock=clock, run=False)
plain.fed = clock.t - 100
plain.rest(clock.t)
check("one with no picture to show (none given): dark with no music, as ever",
      plain.screen.wires.heights() == [0] * 25 and not plain.resting)

# on its own thread, a picture picked: the music's bars never drawn over it
fw = FakeWires()
shown, pin = O.picture_rows(O.quiet_time("19:49", "")), True
quiet_rows = shown
bars = O.OledBars(O.Screen(fw), picture=a_picture)
up = until(lambda: fw.rows() == list(shown), 2)
t0 = time.monotonic()
for k in range(40):                                    # (most of a second of loud music, as a player feeds it)
    bars.heard(pcm_of(np.full(960, 1.0)).tobytes(), t0 + k * 0.02)
    time.sleep(0.02)
    if fw.rows() != list(shown):
        up = False
check(f"on its own thread, a picture picked: there at once, and loud music's bars never drawn over it ({up})",
      up and fw.rows() == list(shown) and bars.resting)
quiet_rows = O.picture_rows(O.quiet_time("19:50", ""))
bars.poke()
check("...what it shows changed (poke): shown at once", until(lambda: fw.rows() == list(quiet_rows), 0.2))
bars.close()
pin, quiet_rows = False, kept

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
      f"{max(during or [0])}), only the rows that change sent (a steady tone: few), never more than its "
      f"{O.FPS:.0f} frames a second's worth ({frames} rows)",
      idle == 0 and max(early or [0]) == 0 and min(during or [0]) >= 12 and 3 <= frames <= 4 * 30)
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
QUIET_WAS, O.QUIET_AFTER = O.QUIET_AFTER, 1e9          # (the bars first: the time with no music has its own part)
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
check(f"a Pi on a TV or monitor: Settings > Screen > Waveshare 2.23 OLED, the last of its rows but an e-ink's (the "
      f"HAT that goes there instead: test_eink.py): one row, all it can show to cycle through "
      f"({m.settings_rows()[r.index('oled')] if 'oled' in r else None})",
      m.oled_can() and r[-2:] == ["oled", "eink"] and r[0] == "screen"
      and m.settings_rows()[-2] == ("oled", "Waveshare 2.23 OLED", ["Off", "Music bars", "Time", "Weather", "Prices",
                                                                    "Face", "Each in turn"])
      and m.settings_place("oled") == ("display", len(r) - 2)
      and "oled" not in [k for k, _, _ in m.settings_root_rows()])
check("...no second row for what it shows with no music (nor a setting for it): Off, to begin with",
      "oled_quiet" not in r and "oled_quiet" not in g.SETTINGS_DEFAULT and g.SETTINGS_DEFAULT["oled"] == "Off"
      and not any("no music" in label for _, label, _ in m.settings_rows()))
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

# its bars picked while a song plays: moved to the player that says what's heard, once the row's stayed on them
m.pos = 1.0
m.view, m.tab = "list", SETTINGS                       # (Settings again, the song playing on)
m.set_sel = rows().index("oled")
m.press("right")
fw = made[-1][1]
due = m.oled_catch_at - time.monotonic()
check(f"its bars picked with a song playing on the plain player: the song's left alone as the row's pressed (it may "
      f"be on its way past them, to a picture), for a moment ({due:.1f} s)", m.oled is not None
      and type(m.proc).__name__ == "Proc" and SO.OLED_SETTLE - 0.5 < due <= SO.OLED_SETTLE)
m.oled_tick(m.oled_catch_at - 0.1)
check("...not moved before then", type(m.proc).__name__ == "Proc" and m.oled_catch_at)
m.press("right")
seen_was = m.oled_seen
m.oled_tick(time.monotonic() + 60)
m.oled_seen = seen_was
check(f"...▶ again before then, on to a picture ({m.setting('oled')}): never moved (no bars to show it by)",
      m.setting("oled") == "Time" and not m.oled_catch_at and type(m.proc).__name__ == "Proc"
      and made[-1][1] is fw and not m.oled_wanted())
m.press("left")
m.oled_tick(m.oled_catch_at - 0.1)
still = type(m.proc).__name__
m.oled_tick(m.oled_catch_at)
check(f"...◀ back to its bars, and left on them: the song's moved to party mode's player, from where it was "
      f"({still}, then {type(m.proc).__name__}, {getattr(getattr(m.proc, 'player', None), 'pos0', None)})",
      m.setting("oled") == "Music bars" and still == "Proc" and type(m.proc).__name__ == "PartyProc"
      and m.proc.player.pos0 == 1.0 and not m.oled_catch_at)
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
      and wr.get("status") == "Restart the Pi to turn its SPI on" and wr.get("choices") == g.OLED_CHOICES)
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
check(f"the web page's Settings: Waveshare 2.23 OLED, the last of Screen's but an e-ink's ({wr.get('label')!r}, "
      f"{wr.get('value')!r}, {wr.get('note')!r})",
      wr.get("kind") == "choice" and wr.get("value") == "Off" and wr.get("label") == "Waveshare 2.23 OLED"
      and wr.get("note") == "The OLED HAT on the Pi's pins, and what it shows: bars that move with the music (this "
                            "Pi's or another of yours'), the time, the weather, your Finance prices, the Bot's face, "
                            "or each of those four in turn."
      and [(s["title"], s["rows"][0]["key"], [r["key"] for r in s["rows"][-2:]])
           for s in m.web_settings()["sections"] if s["id"] == "screen"] == [("Screen", "screen", ["oled", "eink"])]
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

# ---- a picture in place of its bars: the time, the weather, prices, the Bot's face ---------------------------------
WALL = time.mktime((2026, 11, 25, 19, 49, 30, 0, 0, -1))   # (7:49 in the evening, here)
m.oled_wall = lambda: WALL
slot = int(WALL // O.DRIFT_SECS)
m.set_setting("clock", "12-hour")


def pic(now=0.0, quiet=False):
    """Its picture's rows at `now`, music playing (or, quiet, none for a while). None: its bars."""
    got = m.oled_picture(now, quiet)
    return got[0] if got is not None else None


time_now = O.picture_rows(O.quiet_time("7:49", "PM", at=O.drift(slot, O.DRIFT_TIME)))
m.set_setting("oled", "Music bars")
check("set to its bars: no picture while music plays; the time once there's been none for a while (not left dark)",
      m.oled_picture(0, False) is None and pic(0, True) == time_now and m.oled_bars() and m.oled_wanted())
m.set_setting("oled", "Time")
got = pic()
check("Time: the time, as the clock's set (12-hour: 7:49 with a small PM), moved a little for this minute, and "
      "there whether music's playing or not", got == time_now and pic(1, True) == time_now)
check("...asked again in the same minute: the same, not drawn again", pic(1) is got)
check("...its music isn't moved to party mode's player for it, nor are your others' bars asked for",
      not m.oled_bars() and not m.oled_wanted() and m.oled_beacon() is None)
m.oled_wall = lambda: WALL + 60
moved = pic(2)
check(f"...the next minute: somewhere else ({O.drift(slot, O.DRIFT_TIME)} to {O.drift(slot + 1, O.DRIFT_TIME)}), "
      f"never far", moved != got and moved == O.picture_rows(O.quiet_time("7:50", "PM",
                                                                         at=O.drift(slot + 1, O.DRIFT_TIME))))
spots = {O.drift(k, O.DRIFT_TIME) for k in range(200)}
check(f"...a different place most minutes ({len(spots)} of {13 * 5}), never more than {O.DRIFT_TIME} away",
      len(spots) > 40 and all(abs(x) <= 6 and abs(y) <= 2 for x, y in spots))
m.oled_wall = lambda: WALL
m.set_setting("clock", "24-hour")
time_24 = O.picture_rows(O.quiet_time("19:49", "", at=O.drift(slot, O.DRIFT_TIME)))
check("...24-hour: 19:49, no AM or PM", pic(3) == time_24)

# upside down: the row under its own and the e-ink's, while it's on
m.view, m.tab, m.set_page = "list", SETTINGS, "display"
m.oled_pick("Time")
up = until(lambda: tuple(fw.rows()) == time_24, 3)
r = rows()
last = m.settings_rows()[-1]
m.set_sel = r.index("hat_flip") if "hat_flip" in r else 0
m.press("right")
over = until(lambda: tuple(fw.rows()) == O.turned(time_24), 3)
wr = web_rows()
check(f"lit, one more row under its own and the e-ink's: {last[1] if last else None!r} ({r[-3:]}); ▶ there: On "
      f"({m.setting('hat_flip')!r}): the picture it shows turned round at once ({up}, {over}); the web page's "
      f"Settings has the row too ({(wr.get('hat_flip') or {}).get('label')!r})",
      r[-3:] == ["oled", "eink", "hat_flip"] and last == ("hat_flip", "OLED upside down", ["Off", "On"])
      and m.hat_on() == "OLED" and g.SETTINGS_DEFAULT["hat_flip"] == "Off" and m.setting("hat_flip") == "On"
      and m.oled.screen.flip is True and up and over and wr["hat_flip"]["label"] == "OLED upside down"
      and wr["hat_flip"]["value"] == "On" and wr["hat_flip"]["choices"] == ["Off", "On"]
      and [x["key"] for s in m.web_settings()["sections"] if s["id"] == "screen" for x in s["rows"]][-3:]
      == ["oled", "eink", "hat_flip"])
m.oled_wall = lambda: WALL + 60
m.oled.poke()
next_min = O.picture_rows(O.quiet_time("19:50", "", at=O.drift(slot + 1, O.DRIFT_TIME)))
later = until(lambda: tuple(fw.rows()) == O.turned(next_min), 3)
m.oled_wall = lambda: WALL
m.oled.poke()
until(lambda: tuple(fw.rows()) == O.turned(time_24), 3)
said = m.web_settings_do({"key": "hat_flip", "value": "Off"})
back = until(lambda: tuple(fw.rows()) == time_24, 3)
odd = [m.web_settings_do({"key": "hat_flip", "value": "Sideways"}),
       m.web_settings_do({"key": "oled_flip", "value": "On"})]
check(f"...the next minute's picture: upside down too ({later}); Off, picked on the web page ({said}): the right "
      f"way up again ({back}); something it can't be: not taken ({odd})", later and said == {"ok": True} and back
      and m.oled.screen.flip is False and m.setting("hat_flip") == "Off" and all("error" in x for x in odd))
m.hat_flip_pick("On")
m.oled_pick("Off")
m.oled_pick("Time")
fw2 = made[-1][1]
again = until(lambda: tuple(fw2.rows()) == O.turned(time_24), 3)
gone_row = (m.oled_pick("Off"), "hat_flip" in rows(), "hat_flip" in web_rows(),
            m.web_settings_do({"key": "hat_flip", "value": "Off"}))
check(f"...kept: lit again later, its picture's upside down from the start ({again}); with neither HAT on, no such "
      f"row, here or on the web page ({gone_row[1:]})", again and fw2 is not fw and gone_row[1:3] == (False, False)
      and "error" in gone_row[3] and m.hat_on() == "")
m.set_setting("hat_flip", "Off")
m.oled_pick("Time")
fw = made[-1][1]
m.set_sel = rows().index("oled")
m.set_setting("oled", "Weather")
wx_was = (m.weather.data, m.weather.t)
m.weather.data, m.weather.t = None, 0.0
check("Weather, with none yet: the time instead", pic(4) == time_24)
m.weather.data, m.weather.t = {"temp": 61.6, "code": 2, "is_day": True}, WALL - 600
check("...with some: its picture, how warm and its words (Partly cloudy)", pic(5) == O.picture_rows(
    O.quiet_weather("62°", "Partly cloudy", "partly_day", at=O.drift(slot, O.DRIFT_WX))))
m.weather.data["is_day"] = False
check("...at night, the night's picture", pic(6) == O.picture_rows(
    O.quiet_weather("62°", "Partly cloudy", "partly_night", at=O.drift(slot, O.DRIFT_WX))))
m.weather.t = WALL - SO.QUIET_WX_OLD - 60
check("...hours old (the WiFi's down, say): the time instead", pic(7) == time_24)
m.weather.t = WALL - 600

# the face: the Bot's own, as its Character has it
def lit_of(rows):
    """A picture's rows as its pixels (32 by 128: 1 where lit)."""
    return np.unpackbits(np.frombuffer(b"".join(rows), np.uint8).reshape(4, 1, 128), axis=1,
                         bitorder="little").reshape(32, 128)


def runs(on):
    """The stretches of a line that are lit: [(first, last)]."""
    out, at = [], None
    for k, v in enumerate(list(on) + [False]):
        if v and at is None:
            at = k
        elif not v and at is not None:
            out.append((at, k - 1))
            at = None
    return out


AHEAD = next(t for t in np.arange(0.5, 90, 0.5) if FACE.face_state("idle", t)[:2] == (1.0, (0, 0))
             and FACE.face_wait("idle", t) > 0.3)       # (a moment it looks straight ahead, its eyes open)
m.set_setting("oled", "Face")
shape, lashes = m.oled_face()
face = pic(AHEAD)
check("Face: the Bot's own face (face.py's), the shape its Character gives it, moved a little each minute",
      shape == FACE.face_shape(m.bot_steps()) and lashes is False
      and face == O.picture_rows(O.quiet_face(shape, lashes, AHEAD, at=O.face_drift(slot, shape, lashes))))
plain = lit_of(O.picture_rows(O.quiet_face(shape, lashes, AHEAD)))
bands = runs(plain.any(axis=1))
eyes = runs(plain[bands[0][0]:bands[0][1] + 1].any(axis=0)) if bands else []
mouth = runs(plain[bands[-1][0]:bands[-1][1] + 1].any(axis=0)) if len(bands) == 2 else []
eye_w = [b - a + 1 for a, b in eyes]
mouth_w = mouth[0][1] - mouth[0][0] + 1 if len(mouth) == 1 else 999
check(f"...two big eyes (each {eye_w} across, {bands[0][1] - bands[0][0] + 1 if bands else 0} down) and a little "
      f"mouth under them ({mouth_w} across, {bands[-1][1] - bands[-1][0] + 1 if bands else 0} down): not a smile as "
      f"wide as the face", len(bands) == 2 and len(eyes) == 2 and min(eye_w) >= 9 and eye_w[0] == eye_w[1]
      and bands[0][1] - bands[0][0] + 1 >= 14 and mouth_w <= eye_w[0] + 2 and bands[1][1] - bands[1][0] + 1 <= 4
      and eyes[0][0] < mouth[0][0] and mouth[0][1] < eyes[1][1]
      and abs((mouth[0][0] + mouth[0][1]) - (eyes[0][0] + eyes[1][1])) <= 1)
check(f"...all of it on the screen wherever its eyes look, a pixel to spare for the minute's move "
      f"({O.face_fit(shape, lashes)})", all(
          not lit_of(O.picture_rows(O.quiet_face(shape, lashes, t)))[[0, -1]].any()
          for t in np.arange(0.0, 60.0, 0.37)))
BLINK = FACE._blink_at(int(AHEAD // 4) + 1)[0]         # (its next blink but one's start)
shut = m.oled_picture(BLINK + FACE.BLINK / 2)
eyes_shut = lit_of(shut[0])
check(f"...it blinks, as the Bot's does: its eyes shut (a line each) halfway through one, and it's asked for again "
      f"in a twentieth of a second ({shut[1]:.2f})", shut[0] != face and shut[1] <= 0.05
      and max(b - a + 1 for a, b in runs(eyes_shut[:20].any(axis=1))) <= 3
      and m.oled_picture(AHEAD)[1] > 0.05)
LOOKS = next(t for t in np.arange(1.0, 200, 3.0) if abs(FACE.face_state("idle", t)[1][0]) >= 0.7)
glance = lit_of(pic(LOOKS))
check("...and glances about: its eyes and mouth to one side", glance.any() and not np.array_equal(
    np.nonzero(glance.any(axis=0))[0][[0, -1]], np.nonzero(lit_of(face).any(axis=0))[0][[0, -1]]))
wide = FACE.face_shape({"eye_size": 10, "eye_height": 10, "eye_gap": 10, "mouth_size": 10})
reach = O.face_fit(wide, True)[2]
check(f"...a Character with the biggest eyes, furthest apart, and eyelashes: still all on the screen, moved less far "
      f"each minute (it reaches {reach} either side)", all(
          not lit_of(O.picture_rows(O.quiet_face(wide, True, AHEAD, at=O.face_drift(k, wide, True))))[
              :, [0, -1]].any() and abs(O.face_drift(k, wide, True)[0]) <= 64 - reach for k in range(120))
      and max(abs(O.face_drift(k, shape, lashes)[0]) for k in range(200)) > 30)
m.set_setting("oled", "Each in turn")
kinds = []
for k in range(6):
    m.oled_wall = lambda k=k: WALL + k * SO.QUIET_TURN
    m.oled_picture(10)
    kinds.append(m.oled_quiet_key[0])
check(f"Each in turn, with no prices here: the other three in turn, {SO.QUIET_TURN:.0f} seconds each ({kinds})",
      len(set(kinds[:3])) == 3 and kinds[:3] == kinds[3:] and "price" not in kinds)
m.weather.data = None
kinds = []
for k in range(4):
    m.oled_wall = lambda k=k: WALL + k * SO.QUIET_TURN
    m.oled_picture(11)
    kinds.append(m.oled_quiet_key[0])
check(f"...with no weather: the time and the face ({kinds})", sorted(set(kinds)) == ["face", "time"]
      and kinds[0] != kinds[1])
m.weather.data, m.weather.t = wx_was

# your stocks' and coins' prices
stocks_was, coins_was = (m.stocks.stocks, m.stocks.quotes), (m.crypto.coins, m.crypto.quotes)
m.stocks.stocks = [{"symbol": "AAPL", "name": "Apple Inc."}, {"symbol": "TSLA", "name": "Tesla, Inc."}]
m.stocks.quotes = {"AAPL": {"t": WALL - 120, "d": {"price": 235.86, "currency": "USD", "kind": "EQUITY",
                                                   "change_1d": 1.2391}},
                   "TSLA": {"t": WALL - SO.QUIET_WX_OLD - 60, "d": {"price": 350.1, "currency": "USD",
                                                                     "change_1d": -3.0}}}
m.crypto.coins = [{"id": "bitcoin", "symbol": "BTC", "name": "Bitcoin"},
                  {"id": "dogecoin", "symbol": "DOGE", "name": "Dogecoin"}]
m.crypto.quotes = {"bitcoin": {"t": WALL - 60, "d": {"price": 97140.2, "change_24h": -2.3104}},
                   "dogecoin": {"t": WALL - 60, "d": {"price": 0.123412, "change_24h": None}}}
mine = m.oled_prices(WALL)
check(f"Prices: the Finance app's stocks, then its coins, as they're written there, how far they've moved today; "
      f"one fetched hours ago left out ({mine})", mine == [("AAPL", "$235.86", 1.24), ("BTC", "$97,140", -2.31),
                                                            ("DOGE", "$0.1234", None)])
m.set_setting("oled", "Prices")
m.oled_wall = lambda: WALL
first = pic(12)
k0 = int(WALL // SO.PRICE_SECS) % 3
check(f"...one at a time: its ticker, how far it's moved and its price ({m.oled_quiet_key[1:4]})",
      first == O.picture_rows(O.quiet_price(*mine[k0], at=O.drift(slot, O.DRIFT_WX))))
seen = []
for k in range(6):
    m.oled_wall = lambda k=k: WALL + k * SO.PRICE_SECS
    m.oled_picture(13)
    seen.append(m.oled_quiet_key[1])
check(f"...each for {SO.PRICE_SECS:.0f} seconds, then the next, round and round ({seen})", len(set(seen[:3])) == 3
      and seen[:3] == seen[3:])
for q in list(m.stocks.quotes.values()) + list(m.crypto.quotes.values()):
    q["t"] -= SO.QUIET_WX_OLD
m.oled_wall = lambda: WALL
check("...none that aren't hours old (no WiFi, say): the time instead", pic(14) == time_24)
for q in list(m.stocks.quotes.values()) + list(m.crypto.quotes.values()):
    q["t"] += SO.QUIET_WX_OLD
m.set_setting("oled", "Each in turn")
m.weather.data, m.weather.t = {"temp": 61.6, "code": 2, "is_day": True}, WALL - 600
m.stocks.quotes["TSLA"]["t"] = WALL - 10 * SO.QUIET_WX_OLD
kinds, start = [], WALL - WALL % 300                    # (a whole turn of them: 15 + 15 + 3 prices of 5 + 15 seconds)
for k in range(int(60 / SO.PRICE_SECS)):
    m.oled_wall = lambda k=k: start + k * SO.PRICE_SECS
    m.oled_picture(15)
    key = m.oled_quiet_key
    kinds.append(key[1] if key[0] == "price" else key[0])
turns = [x for k, x in enumerate(kinds) if k == 0 or kinds[k - 1] != x]
check(f"Each in turn: the time, the weather, each price, the face, one after another ({turns})",
      turns == ["time", "weather", "AAPL", "BTC", "DOGE", "face"]
      and kinds.count("time") == kinds.count("weather") == kinds.count("face") == 3)
m.weather.data, m.weather.t = wx_was
m.set_setting("oled", "Prices")
fetched, peers = [], []
m.stocks.fetch_quote = lambda sym: fetched.append(sym)
m.crypto.fetch_quote = lambda cid: fetched.append(cid)
m.stocks.from_peer = m.crypto.from_pie = lambda job, ttl: peers.append(job) and False
g.edit_config("finance.txt", {"stocks": "AAPL, MSFT", "coins": "bitcoin"}, head="")
m.stocks.quotes["AAPL"]["t"] = time.time() - 30        # (just fetched: not again yet)
m.oled_prices_at, m.oled_seen = 0.0, 0.0
m.oled_tick(time.monotonic())
until(lambda: not m.oled_prices_busy, 5)
check(f"...fetched for it: the prices alone, of your stocks and coins as finance.txt has them, not one just fetched, "
      f"your other Pietatos asked first ({fetched}, {peers})", fetched == ["MSFT", "bitcoin"]
      and peers == [("quote", "MSFT"), ("quote", "bitcoin")] and m.stocks.symbols() == ["AAPL", "MSFT"])
m.oled_seen = 0.0
m.oled_tick(time.monotonic())
check("...not again a moment later", fetched == ["MSFT", "bitcoin"] and not m.oled_prices_busy)
m.oled_prices_at, m.oled_seen, m.stocks.running = 0.0, 0.0, True
m.oled_tick(time.monotonic())
check("...nor while the Finance tab's open (it fetches them)", fetched == ["MSFT", "bitcoin"]
      and not m.oled_prices_busy)
m.stocks.running = False
m.set_setting("oled", "Time")
m.oled_prices_at, m.oled_seen = 0.0, 0.0
m.oled_tick(time.monotonic())
check("...nor while it isn't showing them", fetched == ["MSFT", "bitcoin"] and not m.oled_prices_busy)
del m.stocks.fetch_quote, m.crypto.fetch_quote, m.stocks.from_peer, m.crypto.from_pie
(m.stocks.stocks, m.stocks.quotes), (m.crypto.coins, m.crypto.quotes) = stocks_was, coins_was
m.oled_wall = lambda: WALL
font_was = O.FONT_UI_BOLD
O.FONT_UI_BOLD, m.oled_quiet_key = S + "/no-such-font.otf", None
O._FONTS.clear()
broken = [m.oled_picture(13), m.oled_picture(14)]
O.FONT_UI_BOLD = font_was
O._FONTS.clear()
check("...one that can't be drawn (its font's gone): none (its bars, dark), said once, and the OLED goes on",
      broken == [None, None] and m.oled_quiet_said and m.oled is not None)
m.oled_quiet_said = False
asked_wx = []
m.weather.refresh = lambda *a, **k: asked_wx.append(1)
m.set_setting("oled", "Weather")
m.oled_seen = 0.0
m.oled_tick(time.monotonic())
m.set_setting("oled", "Time")
m.oled_seen = 0.0
m.oled_tick(time.monotonic())
check(f"...the weather fetched again when it's due, for it (only while it shows it: {len(asked_wx)})",
      asked_wx == [1])
del m.weather.refresh

# on its own thread: what the row's set to, as it's cycled through, music or none
O.QUIET_AFTER = 0.4
m.set_setting("clock", "12-hour")
m.view, m.tab, m.set_page = "list", SETTINGS, "display"
m.oled_pick("Music bars")
m.set_sel = rows().index("oled")
shown = until(lambda: fw.rows() == list(time_now), 4)
check(f"the OLED, set to its bars, with no music for a while: the time, dimmer ({shown})", shown
      and ("c", bytes([O.DIM])) in fw.log and m.oled.resting and not m.oled.pinned)
m.oled_heard(pcm_of(np.full(RATE // 5, 0.8)).tobytes(), time.monotonic() + 0.05, 1.0)
lit_again = until(lambda: not m.oled.resting and (fw.heights() or [0])[0] > 0, 3)
check(f"...music: its bars at once, as bright as ever ({lit_again})", lit_again
      and fw.log[fw.log.index(("c", bytes([O.DIM]))):].count(("c", bytes([O.BRIGHT]))) >= 1)
back = until(lambda: fw.rows() == list(time_now), 4)
check(f"...over: the time again ({back})", back)
m.press("right")
check(f"▶ on its row: the next of its choices, Time ({m.setting('oled')!r}), with no new start of the OLED "
      f"({len(made)} made)", m.setting("oled") == "Time" and made[-1][1] is fw and m.oled is not None
      and m.oled_in is None and m.oled_value() == "Time")
t0, fed_was = time.monotonic(), m.oled.fed
stayed = True
for k in range(30):                                    # (loud music, most of a second of it: the time stays up)
    m.oled_heard(pcm_of(np.full(960, 0.9)).tobytes(), t0 + k * 0.02, 1.0)
    time.sleep(0.02)
    stayed = stayed and fw.rows() == list(time_now)
check(f"...music playing: the time stays, no bars over it ({stayed}): its sound isn't passed on to the OLED at all",
      stayed and m.oled.fed == fed_was)
t0 = time.monotonic()
for k in range(20):                                    # (...a bit that reaches it all the same: just as it's picked)
    m.oled.heard(pcm_of(np.full(960, 0.9)).tobytes(), t0 + k * 0.02)
    time.sleep(0.02)
    stayed = stayed and fw.rows() == list(time_now)
check(f"...and sound that reaches it all the same (played just as it's picked, say): the time stays ({stayed})",
      stayed and m.oled.pinned and m.oled.resting)
m.press("right")
m.weather.data, m.weather.t = {"temp": 61.6, "code": 2, "is_day": True}, WALL - 600
weather_now = O.picture_rows(O.quiet_weather("62°", "Partly cloudy", "partly_day", at=O.drift(slot, O.DRIFT_WX)))
check("▶: Weather, shown at once", m.setting("oled") == "Weather" and until(lambda: fw.rows() == list(weather_now), 1))
m.weather.data, m.weather.t = wx_was
m.press("right")
m.press("right")
m.oled.picture_of = lambda now, quiet: m.oled_picture(AHEAD, quiet)   # (its face held still, to look at)
m.oled.poke()
check(f"▶▶: past Prices to Face ({m.setting('oled')!r}): the Bot's face, shown", m.setting("oled") == "Face"
      and until(lambda: fw.rows() == list(face), 1))
m.oled.picture_of = m.oled_picture
m.press("right")
m.press("right")
made_was = len(made)
check(f"▶▶: Each in turn, then round to Off: dark and off ({m.setting('oled')!r})", m.setting("oled") == "Off"
      and m.oled is None and fw.closed)
m.press("left")
fw = made[-1][1]
check(f"◀ from Off: round to the last, Each in turn: lit again, a picture at once ({m.setting('oled')!r})",
      m.setting("oled") == "Each in turn" and m.oled is not None and not fw.closed
      and until(lambda: m.oled.resting and fw.rows() == list(m.oled_quiet_rows) != list(O.BLANK), 1)
      and m.oled_in is None and len(made) == made_was + 1)
wr = web_rows()["oled"]
check(f"the web page's Settings: the same choices on its one row ({wr['choices']})",
      wr["choices"] == ["Off", "Music bars", "Time", "Weather", "Prices", "Face", "Each in turn"]
      and wr["value"] == "Each in turn" and "oled_quiet" not in web_rows() and "face" in wr["note"]
      and m.web_settings_do({"cmd": "settings", "key": "oled", "value": "Face"}) == {"ok": True}
      and m.setting("oled") == "Face" and made[-1][1] is fw
      and "error" in m.web_settings_do({"cmd": "settings", "key": "oled", "value": "Smiley"})
      and "error" in m.web_settings_do({"cmd": "settings", "key": "oled_quiet", "value": "Time"}))
m.dirty = True
m.flush()
FB.last.convert("RGB").save(S + "/settings_oled_face.png")
pics = [O.quiet_time("7:49", "PM"), O.quiet_time("19:49", ""), O.quiet_weather("62°", "Partly cloudy", "partly_day"),
        O.quiet_weather("104°", "Thunderstorm, hail", "storm"), O.quiet_price("AAPL", "$235.86", 1.24),
        O.quiet_price("BTC", "$97,140", -2.31), O.quiet_price("BRK-B", "$1,234.56", -0.08),
        O.quiet_price("^GSPC", "5,912.17"), O.quiet_face(shape, lashes, AHEAD),
        O.quiet_face(shape, lashes, BLINK + FACE.BLINK / 2), O.quiet_face(shape, lashes, LOOKS),
        O.quiet_face(wide, True, AHEAD)]
sheet = Image.new("L", (128 * 4 + 8, (32 * 4 + 8) * len(pics)), 60)
for k, p in enumerate(pics):
    sheet.paste(p.convert("L").resize((128 * 4, 32 * 4), Image.NEAREST), (4, 4 + k * (32 * 4 + 8)))
sheet.save(S + "/oled_quiet.png")
O.QUIET_AFTER = QUIET_WAS
m.active = False
m.shutdown()
check("Pietato going: its OLED dark and off", m.oled is None and fw.closed and fw.log[-1] == ("c", b"\xae"))

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
sys.exit(0 if all(ok_all) else 1)
