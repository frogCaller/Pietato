"""An e-Paper HAT (pitato/eink.py, screens/eink.py): a Waveshare 2.13inch e-Paper HAT on a Pi's pins. First the
pieces on their own: what's asked of the kernel for its four pins (the numbers and shapes of linux/gpio.h, written out
again here: three outputs, and BUSY read, pulled down), its SPI (4 MHz, mode 0); a command and what goes with it, a
byte at a time, and a picture all at once; a picture packed as the panel takes it (turned, a bit a pixel, upside down
too); then what the panel's sent, byte for byte what Waveshare's driver for it sends (its V4, the one kind of panel
there is here): started, a whole picture, what's changed, white, asleep; a panel that never says it's done. Then
when it's drawn: whole as it's turned on and as you pick something, in part as the picture changes, nothing while
it's the same, never two in a hurry, whole again once it's had enough partial ones (a new kind of picture counting
for more), white and asleep before it's let go of (unless it's wanted again by then, or another HAT's to have its
pins). Its pictures: everything at once, the time, the weather, your prices, the Bot's face. And media mode: Settings >
Screen > Waveshare 2.13 e-ink only on a Pi with its pins free, with one more row while it's on (upside down, the
OLED's too); each choice's picture, as the clock, the weather, your prices, the Bot and what's playing have it; each
in turn, a minute each; one at a time with the OLED and the LED backlight; the Pi's SPI not on, its pins taken; the
web page's Settings; and white as Pietato goes."""
import ctypes, errno, os, shutil, sys, time
from paths import ROOT, SP, TESTS  # noqa: E402  (the Pietato folder; this test's folder of work; tests)
sys.path.insert(0, TESTS)
import numpy as np
from PIL import Image
import pietato_all as g
import pitato.eink as E
import pitato.oled as O
import pitato.screens.eink as SE
import pitato.screens.oled as SO
import pitato.glow as G
import pitato.face as FACE

S = SP + "/t_eink"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/gpi"
for d in ("Music", "Videos", "Pictures", "Documents", "Games/Saves"):
    os.makedirs(f"{HOME}/{d}")
ok_all = []


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


# ---- its pins: what's asked of the kernel ----------------------------------------------------------------------------
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


OUTPUT, INPUT, PULL_DOWN = 1 << 3, 1 << 2, 1 << 9      # (gpio_v2_line_flag's)
check(f"the kernel's number for lines read ({E.GPIO_V2_LINE_GET_VALUES_IOCTL:#x}), and its flags for a line that's "
      f"read and one pulled down ({E.GPIO_V2_LINE_FLAG_INPUT}, {E.GPIO_V2_LINE_FLAG_BIAS_PULL_DOWN}): as linux/gpio.h "
      f"makes them", E.GPIO_V2_LINE_GET_VALUES_IOCTL == ioc(3, 0x0E, Values) and E.GPIO_V2_LINE_FLAG_INPUT == INPUT
      and E.GPIO_V2_LINE_FLAG_BIAS_PULL_DOWN == PULL_DOWN)
check(f"its pins, as the HAT's wired: D/C {E.EINK_DC}, reset {E.EINK_RST}, BUSY {E.EINK_BUSY}, power {E.EINK_PWR}; "
      f"the Pi's SPI ({E.EINK_SPI}) at {E.EINK_HZ // 1000000} MHz, mode {E.EINK_MODE}",
      (E.EINK_DC, E.EINK_RST, E.EINK_BUSY, E.EINK_PWR) == (25, 17, 24, 18) and E.EINK_SPI == "/dev/spidev0.0"
      and (E.EINK_HZ, E.EINK_MODE) == (4000000, 0))
SPI_MODE, SPI_BITS, SPI_HZ = 0x40016B01, 0x40016B03, 0x40046B04   # (linux/spi/spidev.h: its mode, word and clock)


class Kernel:
    """The kernel's GPIO chips, as far as the e-ink's pins go: each chip a file (its label and lines), a request for
    lines answered with a file of its own, what's set on it kept, and what's read from it as this says (levels).
    And an SPI: what's set of it kept."""

    def __init__(self, chips, busy=(), pulls=True):
        self.chips, self.busy, self.pulls = {}, set(busy), pulls   # path -> (label, lines); pins another program
        self.asked, self.set, self.lines, self.pins = [], [], {}, {}   # has; whether it'll pull a pin up or down
        self.levels = {}                               # pin -> what's read from it
        self.open, self.closed, self.spi = {}, [], []
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
            self.closed.append(self.open.pop(fd, None) or tuple(self.pins.pop(fd)))
            self.lines.pop(fd, None)
        return real_close(fd)

    def ioctl(self, fd, req, arg=0, *a):
        if fd in self.open and req == ioc(2, 0x01, ChipInfo):
            label, lines = self.chips[self.open[fd]]
            arg[:] = bytes(ChipInfo(name=b"gpiochip", label=label.encode(), lines=lines))
            return 0
        if fd in self.open and req == ioc(3, 0x07, Request):
            r = Request.from_buffer_copy(bytes(arg))
            pins = list(r.offsets[:r.num_lines])
            self.asked.append({"chip": self.chips[self.open[fd]][0], "pins": pins, "by": r.consumer.decode(),
                               "flags": r.config.flags, "attrs": r.config.num_attrs})
            if self.busy & set(pins):
                raise OSError(errno.EBUSY, "Device or resource busy")
            if not self.pulls and r.config.flags & PULL_DOWN:
                raise OSError(errno.EINVAL, "Invalid argument")
            r.fd = real_open(S + "/lines", os.O_RDWR | os.O_CREAT)
            self.lines[r.fd], self.pins[r.fd] = [0] * len(pins), pins
            arg[:] = bytes(r)
            return 0
        if fd in self.lines and req == ioc(3, 0x0F, Values):
            v = Values.from_buffer_copy(bytes(arg))
            for k in range(len(self.lines[fd])):
                if v.mask >> k & 1:
                    self.lines[fd][k] = v.bits >> k & 1
            self.set.append(tuple(self.lines[fd]))
            return 0
        if fd in self.lines and req == ioc(3, 0x0E, Values):
            v = Values.from_buffer_copy(bytes(arg))
            v.bits = sum((1 << k) for k, pin in enumerate(self.pins[fd]) if v.mask >> k & 1 and self.levels.get(pin))
            arg[:] = bytes(v)
            return 0
        if req in (SPI_MODE, SPI_BITS, SPI_HZ):
            self.spi.append((req, int.from_bytes(arg, "little")))
            return 0
        return real_ioctl(fd, req, arg, *a)


real_open, real_close, real_ioctl = os.open, os.close, E.fcntl.ioctl


class Patched:
    """The module's os.open, os.close and ioctl, the pretend kernel's for a while."""

    def __init__(self, kernel):
        self.k = kernel

    def __enter__(self):
        E.os.open, E.os.close, E.fcntl.ioctl = self.k.os_open, self.k.os_close, self.k.ioctl
        return self.k

    def __exit__(self, *a):
        E.os.open, E.os.close, E.fcntl.ioctl = real_open, real_close, real_ioctl


PI5 = [("gpio-brcmstb@107d508500", 32), ("gpio-brcmstb@107d508520", 4), ("gpio-brcmstb@107d517c00", 17),
       ("gpio-brcmstb@107d517c20", 6), ("pinctrl-rp1", 54)]
with Patched(Kernel(PI5)) as k:
    pins = E.PaperPins(chips=k.paths())
    asked = list(k.asked)
    pins.set(pwr=1)
    pins.set(rst=1)
    pins.set(dc=1)
    pins.set(dc=0, rst=0)
    idle = pins.busy()
    k.levels[24] = 1
    at_work = pins.busy()
    k.levels[25] = 1                                   # (another pin high: not BUSY)
    k.levels[24] = 0
    done = pins.busy()
    pins.close()
check(f"a Pi 5: its pins are on the chip that says it's theirs, asked for as two lots: D/C, reset and power as "
      f"outputs, BUSY to be read, pulled down ({asked})",
      asked == [{"chip": "pinctrl-rp1", "pins": [25, 17, 18], "by": "pietato-eink", "flags": OUTPUT, "attrs": 0},
                {"chip": "pinctrl-rp1", "pins": [24], "by": "pietato-eink", "flags": INPUT | PULL_DOWN, "attrs": 0}])
check(f"...each set on its own, the others left as they were ({k.set})",
      k.set == [(0, 0, 1), (0, 1, 1), (1, 1, 1), (0, 0, 1)])
check(f"...BUSY read: low (it's done), high (at work), low again ({idle}, {at_work}, {done})",
      (idle, at_work, done) == (False, True, False))
check(f"...the chip let go of once they're had, and both lots as it's shut ({k.closed[-2:]}, {len(k.open)} open)",
      sorted(k.closed[-2:], key=len) == [(24,), (25, 17, 18)] and not k.open and not k.lines)
with Patched(Kernel([("pinctrl-bcm2711", 58)], busy=[24])) as k:
    try:
        E.PaperPins(chips=k.paths())
        why = None
    except OSError as ex:
        why = ex.errno
check(f"BUSY's pin taken by another program (an OLED HAT's there, say): said, and the three it had are let go of "
      f"({why}, {k.closed})", why == errno.EBUSY and not k.open and not k.lines and (25, 17, 18) in k.closed)
with Patched(Kernel([("pinctrl-bcm2835", 54)], busy=[17])) as k:
    try:
        E.PaperPins(chips=k.paths())
        why = None
    except OSError as ex:
        why = ex.errno
check(f"...its reset taken: said, nothing kept ({why})", why == errno.EBUSY and not k.open and not k.lines
      and len(k.asked) == 1)
with Patched(Kernel([("gpio-brcmstb@107d508500", 32)])) as k:
    try:
        E.PaperPins(chips=k.paths())
        why = None
    except OSError as ex:
        why = ex.errno
check(f"no chip that's a Pi's own pins: none ({why})", why == errno.ENODEV and not k.asked)
with Patched(Kernel([("pinctrl-bcm2835", 54)], pulls=False)) as k:
    pins = E.PaperPins(chips=k.paths())
    k.levels[24] = 1
    at_work = pins.busy()
    pins.close()
flags = [a["flags"] for a in k.asked]
check(f"a kernel that won't pull a pin down: BUSY read as it is (the HAT drives it itself) ({flags}, {at_work})",
      flags == [OUTPUT, INPUT | PULL_DOWN, INPUT] and at_work is True and not k.lines and not k.open)
SPIFILE = S + "/spidev"
open(SPIFILE, "wb").close()
with Patched(Kernel([("pinctrl-bcm2711", 58)])) as k:
    real_glob = O.glob.glob
    O.glob.glob = lambda pattern: k.paths() if "gpiochip" in pattern else real_glob(pattern)
    try:
        w = E.paper_wires(SPIFILE)
    finally:
        O.glob.glob = real_glob
    w.command(0x12)
    w.command(0x11, 0x03)
    w.close()
check(f"its wires on this Pi: the SPI at 4 MHz, mode 0, 8 bits a word ({k.spi}), and its pins",
      sorted(k.spi) == [(SPI_MODE, 0), (SPI_BITS, 8), (SPI_HZ, 4000000)]
      and [a["pins"] for a in k.asked] == [[25, 17, 18], [24]])
check(f"...shut: its reset, D/C and power low (its power's cut), and all of it let go of ({k.set[-1]})",
      k.set[-1] == (0, 0, 0) and not k.lines and open(SPIFILE, "rb").read() == b"\x12\x11\x03")
with Patched(Kernel([("pinctrl-bcm2711", 58)], busy=[25])) as k:
    real_glob = O.glob.glob
    O.glob.glob = lambda pattern: k.paths() if "gpiochip" in pattern else real_glob(pattern)
    fds = len(os.listdir("/proc/self/fd"))
    try:
        E.paper_wires(SPIFILE)
        why = None
    except OSError as ex:
        why = ex.errno
    finally:
        O.glob.glob = real_glob
check(f"...its pins taken: said, and its SPI let go of too ({why})", why == errno.EBUSY
      and len(os.listdir("/proc/self/fd")) == fds)


# ---- its wires: a command, what goes with it, a picture --------------------------------------------------------------
class FakePins:
    def __init__(self, log):
        self.log, self.closed, self.busy_for = log, False, 0

    def set(self, dc=None, rst=None, pwr=None):
        self.log.append(tuple((n, v) for n, v in (("dc", dc), ("rst", rst), ("pwr", pwr)) if v is not None))

    def busy(self):
        self.busy_for -= 1
        return self.busy_for >= 0

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
E.RESET_HIGH, E.RESET_LOW, E.PULSE_LOW, E.BUSY_LOOK = 0.02, 0.002, 0.001, 0.001
w = E.PaperWires(FakeSpi(log), FakePins(log))
t0 = time.monotonic()
w.reset()
took = time.monotonic() - t0
check(f"its reset: high, low for a moment, high again ({log}; {took * 1000:.0f} ms)",
      log == [(("rst", 1),), (("rst", 0),), (("rst", 1),)] and 0.04 <= took < 1.0)
del log[:]
w.command(0x01, 0xF9, 0x00, 0x00)
w.command(0x12)
w.command(0x11, 0x03)
check(f"a command: D/C low for it, high for what goes with it, each of those bytes on its own (as Waveshare's driver "
      f"sends them), D/C moved only as it changes ({log})",
      log == [(("dc", 0),), ("spi", b"\x01"), (("dc", 1),), ("spi", b"\xf9"), ("spi", b"\x00"), ("spi", b"\x00"),
              (("dc", 0),), ("spi", b"\x12"), ("spi", b"\x11"), (("dc", 1),), ("spi", b"\x03")])
del log[:]
w.command(0x24)
w.lots(bytes(range(250)) * 16)
w.lots(b"\x55" * 10000)
sizes = [len(x[1]) for x in log if x[0] == "spi"]
check(f"a picture: all at once (its {sizes[1]} bytes in one write), or in as few writes as the SPI takes "
      f"({sizes[2:]})", sizes == [1, 4000, 4096, 4096, 1808] and log[2] == (("dc", 1),)
      and b"".join(x[1] for x in log[4:]) == b"\x55" * 10000 and E.SPI_MOST == 4096)
del log[:]
w.pulse()
check(f"before a partial refresh: its reset low for a moment ({log})", log == [(("rst", 0),), (("rst", 1),)])
w.pins.busy_for = 5
t0 = time.monotonic()
came = w.wait(2.0)
check(f"waited for: till BUSY's low ({came}, {(time.monotonic() - t0) * 1000:.0f} ms, looked at {5 - w.pins.busy_for} "
      f"times)", came is True and w.pins.busy_for == -1 and time.monotonic() - t0 < 1.5)
w.pins.busy_for = 10 ** 9
t0 = time.monotonic()
came = w.wait(0.15)
took = time.monotonic() - t0
check(f"...BUSY never low: given up on, after as long as it's given ({came}, {took:.2f} s)",
      came is False and 0.15 <= took < 1.5)
w.hurry = True
t0 = time.monotonic()
came = w.wait(5.0)
check(f"...and at once, as it's let go of ({came}, {(time.monotonic() - t0) * 1000:.0f} ms)",
      came is False and time.monotonic() - t0 < 1.0)
del log[:]
w.power(1)
w.close()
check(f"its power on; shut: its reset, D/C and power low, its SPI and its pins let go of ({log})",
      log == [(("pwr", 1),), (("dc", 0), ("rst", 0), ("pwr", 0))] and w.spi.closed and w.pins.closed)


# ---- a picture, as the panel takes it --------------------------------------------------------------------------------
def unpacked(buf):
    """What the panel shows of these bytes, the way you look at it: 250 by 122, True where it's black."""
    native = np.unpackbits(np.frombuffer(buf, np.uint8).reshape(250, 16), axis=1)[:, :122] == 0
    return np.rot90(native, -1)                        # (its lines run down the picture: turned back)


blank = Image.new("1", (250, 122), 1)
buf = E.packed(blank)
check(f"a white picture, packed: {len(buf)} bytes, 250 lines of 16 (122 pixels: the last 6 bits of a line are "
      f"nothing), a bit a pixel, 1 for white", len(buf) == 4000 == E.EINK_FRAME and E.EINK_ROW == 16
      and buf == (b"\xff" * 15 + b"\xc0") * 250 and (E.EINK_W, E.EINK_H) == (250, 122))
dots = blank.copy()
for at in ((0, 0), (249, 0), (0, 121), (249, 121), (100, 37)):
    dots.putpixel(at, 0)
buf = E.packed(dots)
want = bytearray((b"\xff" * 15 + b"\xc0") * 250)
for x, y in ((0, 0), (249, 0), (0, 121), (249, 121), (100, 37)):   # (turned a quarter: the picture's left is its end)
    want[(249 - x) * 16 + y // 8] &= ~(0x80 >> (y % 8)) & 0xFF
check("...black pixels: each one's bit 0, in the line and byte Waveshare's driver puts it (the picture turned a "
      "quarter turn, as its getbuffer turns one that's wider than it's tall)", buf == bytes(want)
      and buf[249 * 16] == 0x7F and buf[15] == 0x80)
check("...and back again: what the panel shows is the picture", (unpacked(buf) == (np.asarray(dots) == 0)).all())
flipped = E.packed(dots, flip=True)
check("...upside down: the same picture turned half a turn", flipped != buf
      and (unpacked(flipped) == np.rot90(np.asarray(dots) == 0, 2)).all())
grey = Image.new("L", (250, 122), 255)
grey.putpixel((3, 4), 0)
check("...any picture that size (grey, say): made black and white", len(E.packed(grey)) == 4000
      and unpacked(E.packed(grey))[4, 3] and unpacked(E.packed(grey)).sum() == 1)


# ---- the panel: what it's sent ---------------------------------------------------------------------------------------
class FakeWires:
    """The HAT's wires, kept: ("power", on), ("reset",), ("pulse",), ("c", a command, what goes with it...), ("lots",
    a picture), ("wait",), ("close",). stuck: BUSY never goes low."""

    def __init__(self, stuck=False, fails=None):
        self.log, self.hurry, self.closed, self.stuck, self.fails = [], False, False, stuck, fails
        self.waits = 0

    def power(self, on):
        self.log.append(("power", on))

    def reset(self):
        self.log.append(("reset",))

    def pulse(self):
        self.log.append(("pulse",))

    def command(self, c, *data):
        if self.fails:
            raise OSError(errno.EIO, "Input/output error")
        self.log.append(("c", c) + tuple(data))

    def lots(self, data):
        self.log.append(("lots", bytes(data)))

    def wait(self, limit=None):
        self.log.append(("wait",))
        self.waits += 1
        return not self.stuck

    def close(self):
        self.closed = True
        self.log.append(("close",))

    def frames(self):
        """Each refresh there's been: [(how: "full", "part" or "white", what the panel shows of it)]."""
        out, new, old = [], None, None
        for k, x in enumerate(self.log):
            if x[:2] == ("c", 0x24):
                new, old = self.log[k + 1][1], None
            elif x[:2] == ("c", 0x26):
                old = self.log[k + 1][1]
            elif x[:2] == ("c", 0x20) and new is not None:
                how = self.log[k - 1][2]
                out.append(("white" if new == b"\xff" * 4000 else "full" if old == new and how == 0xF7
                            else "part" if old is None and how == 0xFF else "?", new))
                new = None
        return out

    def last(self):
        f = self.frames()
        return f[-1] if f else (None, None)


WINDOW = [("c", 0x44, 0x00, 0x0F), ("c", 0x45, 0x00, 0x00, 0xF9, 0x00), ("c", 0x4E, 0x00), ("c", 0x4F, 0x00, 0x00)]
START = [("reset",), ("wait",), ("c", 0x12), ("wait",), ("c", 0x01, 0xF9, 0x00, 0x00), ("c", 0x11, 0x03)] + WINDOW \
    + [("c", 0x3C, 0x05), ("c", 0x21, 0x00, 0x80), ("c", 0x18, 0x80), ("wait",)]
A, B = E.packed(dots), E.packed(Image.new("1", (250, 122), 0))   # (two pictures: some dots, and all black)
fw = FakeWires()
p = E.Paper(fw)
check(f"the panel: its power on as it's had ({fw.log})", fw.log == [("power", 1)])
del fw.log[:]
p.start()
check("started, as Waveshare's driver starts it (a V4): reset, waited for; its software reset, waited for; its 250 "
      "lines; how a picture's written; all of its memory, from its first corner; its border, its two memories, its "
      "own thermometer; waited for", fw.log == START)
del fw.log[:]
p.full(A)
check("a whole picture: started, then written into both of its memories (what's to show, and what a partial refresh "
      "takes as there already), and shown with a full refresh (0xF7), waited for",
      fw.log == START + [("c", 0x24), ("lots", A), ("c", 0x26), ("lots", A), ("c", 0x22, 0xF7), ("c", 0x20), ("wait",)]
      and fw.frames() == [("full", A)])
del fw.log[:]
p.partial(B)
check("what's changed: its reset low for a moment, its border, lines and memory set again, the picture written into "
      "the one memory, and shown with a partial refresh (0xFF), waited for",
      fw.log == [("pulse",), ("c", 0x3C, 0x80), ("c", 0x01, 0xF9, 0x00, 0x00), ("c", 0x11, 0x03)] + WINDOW
      + [("c", 0x24), ("lots", B), ("c", 0x22, 0xFF), ("c", 0x20), ("wait",)] and fw.frames() == [("part", B)])
del fw.log[:]
p.clear()
check("white: started, all 1s written, a full refresh", fw.log == START + [("c", 0x24), ("lots", b"\xff" * 4000),
                                                                           ("c", 0x22, 0xF7), ("c", 0x20), ("wait",)]
      and fw.frames() == [("white", b"\xff" * 4000)])
del fw.log[:]
p.sleep()
p.shut()
check(f"asleep (its deep sleep, keeping its memory), and let go of ({fw.log})",
      fw.log == [("c", 0x10, 0x01), ("close",)] and fw.closed)
NOTICE = ROOT + "/licenses/waveshare-epd.txt"
check("one kind of panel, and no other's to pick: no V3's waveforms here (nor Waveshare's notice for them, which "
      "went with them), and a panel isn't told which it is",
      not any(hasattr(E, n) for n in ("VERSIONS", "LUT_FULL", "LUT_PARTIAL", "WRITE_LUT")) and not hasattr(p, "v3")
      and not os.path.exists(NOTICE) and "waveshare-epd" not in open(ROOT + "/THIRD-PARTY-LICENSES.md").read()
      and "eink_version" not in g.SETTINGS_DEFAULT)
fw = FakeWires(stuck=True)
p = E.Paper(fw)
p.full(A)
check(f"a panel that never says it's done (BUSY stays high): said (not answered), waited for the once, not at each "
      f"step ({fw.waits})", p.answered is False and fw.waits == 1 and fw.frames() == [("full", A)])


# ---- when it's drawn -------------------------------------------------------------------------------------------------
class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


clock = Clock()
show = {"img": dots, "wait": None, "kind": "time"}
asked = []


def picture(now):
    asked.append(now)
    return (show["img"], show["wait"], show["kind"]) if show["img"] is not None else None


def pic_of(*at, base=None):
    """A picture: white, with these pixels black."""
    im = (base or blank).copy()
    for xy in at:
        im.putpixel(xy, 0)
    return im


fw = FakeWires()
ps = E.PaperShow(E.Paper(fw), picture, clock=clock, run=False)
del fw.log[:]
drew = ps.step(clock.t)
check(f"as it's turned on: what it should show is asked for, and drawn whole (a full refresh: clean) "
      f"({[f[0] for f in fw.frames()]})", drew is True and fw.frames() == [("full", A)] and asked == [1000.0]
      and (ps.fulls, ps.parts) == (1, 0) and not ps.note)
n = len(fw.log)
clock.t += 5
drew = ps.step(clock.t)
check(f"asked again, the picture the same: nothing sent ({len(fw.log) - n}), asked again in {ps.again} seconds (no "
      f"sooner said)", drew is False and len(fw.log) == n and ps.again == E.IDLE == 2.0)
show["wait"] = 0.4
ps.step(clock.t)
quick = ps.again
show["wait"] = 0.0001
ps.step(clock.t)
check(f"...as soon as it says (the minute's nearly up, say: {quick}), never at once ({ps.again}), every couple of "
      f"seconds at least", quick == 0.4 and ps.again == E.LEAST == 0.1)
show["wait"] = None
show["img"] = pic_of((7, 7))
clock.t += 60
drew = ps.step(clock.t)
check(f"the picture changed (the next minute): only what's changed is drawn (a partial refresh: no flash) "
      f"({[f[0] for f in fw.frames()]})", drew and fw.frames()[-1] == ("part", E.packed(show["img"]))
      and (ps.fulls, ps.parts) == (1, 1))
show["img"] = pic_of((8, 8))
clock.t += 1.0
n = len(fw.log)
drew = ps.step(clock.t)
check(f"changed again a second later (a song skipped): not yet (never two within {E.EINK_GAP:.0f} seconds), looked at "
      f"again once that's up ({ps.again:.1f} s)", drew is False and len(fw.log) == n and abs(ps.again - 2.0) < 1e-6
      and E.EINK_GAP == 3.0)
clock.t += 2.0
drew = ps.step(clock.t)
check("...then: drawn, as it is by then", drew and fw.frames()[-1] == ("part", E.packed(show["img"])))
for k in range(58):                                    # (the time, a minute at a time)
    show["img"] = pic_of((k, 20))
    clock.t += 60
    ps.step(clock.t)
kinds = [f[0] for f in fw.frames()]
check(f"a picture that changes each minute (the time): {E.FULL_AFTER} partial refreshes, one after another "
      f"({kinds.count('part')}, {kinds.count('full')} full)", kinds == ["full"] + ["part"] * 60 and ps.worn == 60
      and E.FULL_AFTER == 60)
show["img"] = pic_of((1, 30))
clock.t += 60
ps.step(clock.t)
show["img"] = pic_of((2, 30))
clock.t += 60
ps.step(clock.t)
kinds = [f[0] for f in fw.frames()]
check(f"...then a full one (each partial one leaves a little of what was there), and partial ones again "
      f"({kinds[-3:]})", kinds[-3:] == ["part", "full", "part"] and kinds.count("full") == 2 and ps.worn == 1
      and fw.frames()[-1][1] == E.packed(show["img"]))
turns = []
for k in range(14):                                    # (Each in turn: a whole new picture each minute)
    show["img"], show["kind"] = pic_of((k, 50), (k, 51)), ("weather", "prices", "face", "time")[k % 4]
    clock.t += 60
    ps.step(clock.t)
    turns.append(fw.frames()[-1][0])
check(f"a whole new picture each minute (Each in turn): each counts as {E.NEW_PICTURE} partial refreshes, so a full "
      f"one every {E.FULL_AFTER // E.NEW_PICTURE + 1}th ({turns})",
      turns == ["part"] * 5 + ["full"] + ["part"] * 6 + ["full", "part"])
show["kind"] = "face"
clock.t += 60
n = len(fw.frames())
ps.poke(fresh=True)
woke = ps.wake.is_set()
ps.step(clock.t)
check("what it shows picked in Settings (poke, fresh): woken, and drawn whole, though the picture's the same",
      woke and len(fw.frames()) == n + 1 and fw.frames()[-1][0] == "full" and not ps.fresh)
ps.wake.clear()
show["img"] = pic_of((30, 30))
ps.poke(fresh=True, settle=E.EINK_SETTLE)
n = len(fw.frames())
drew = ps.step(clock.t + 0.1)
wait = ps.again
show["img"] = pic_of((31, 31))                         # (the row pressed on, to the next)
drew2 = ps.step(clock.t + E.EINK_SETTLE + 0.01)
check(f"...the row on its way past (each pick waited on {E.EINK_SETTLE} s): nothing drawn for the one it passed "
      f"({drew}, again in {wait:.1f} s), the one it stops on drawn whole, though that's within {E.EINK_GAP:.0f} s",
      drew is False and abs(wait - 0.7) < 1e-6 and drew2 is True and len(fw.frames()) == n + 1
      and fw.frames()[-1] == ("full", E.packed(show["img"])))
clock.t += E.STALE - 10
n = len(fw.frames())
ps.step(clock.t)
same = len(fw.frames()) == n
clock.t += 20
ps.step(clock.t)
check("a picture that hasn't changed for a day (the Bot's face): refreshed whole all the same, once",
      same and len(fw.frames()) == n + 1 and fw.frames()[-1] == ("full", E.packed(show["img"]))
      and not ps.step(clock.t + 1))
ps.turn(True)
not_yet = ps.flip, ps.wake.is_set()
clock.t += 60
ps.step(clock.t)
check(f"upside down, picked: taken before it's next drawn, never part-way through a refresh ({not_yet}): the same "
      f"picture, turned, drawn whole", not_yet == (False, True) and ps.flip is True
      and fw.frames()[-1] == ("full", E.packed(show["img"], True)) and fw.log[-3] == ("c", 0x22, 0xF7)
      and ps.turned is None)
ps.turn(False)
clock.t += 60
ps.step(clock.t)
check("...and back: the right way up", fw.frames()[-1] == ("full", E.packed(show["img"]))
      and fw.log[-3] == ("c", 0x22, 0xF7) and ps.flip is False)
show["img"] = pic_of((40, 40))
ps.poke(fresh=True)
real_full = ps.paper.full


def full_and_asked(buf):
    """(A pick made while it's being drawn.)"""
    real_full(buf)
    ps.poke(fresh=True)


ps.paper.full = full_and_asked
clock.t += 60
ps.step(clock.t)
ps.paper.full = real_full
n = len(fw.frames())
clock.t += 60
ps.step(clock.t)
check("a full refresh asked for while one's being drawn (a pick, just then): not lost: drawn whole again after it",
      ps.fresh is False and len(fw.frames()) == n + 1 and fw.frames()[-1] == ("full", E.packed(show["img"])))
show["img"] = None
clock.t += 60
n = len(fw.log)
check("nothing to show: left as it is", ps.step(clock.t) is False and len(fw.log) == n)

# a panel that isn't answering, and one that can't be written to
fw = FakeWires(stuck=True)
ps = E.PaperShow(E.Paper(fw), picture, clock=clock, run=False)
show["img"] = dots
ps.step(clock.t)
check(f"a panel that never says it's done: said ({ps.note!r}), tried again in a minute ({ps.again:.0f} s), whole",
      ps.note == "It isn't answering" == E.NO_ANSWER and ps.again == E.EINK_RETRY == 60.0 and ps.shown is None)
fw.stuck = False
clock.t += 60
ps.step(clock.t)
check("...answering again: drawn whole, and nothing's said", fw.frames()[-1] == ("full", A) and not ps.note
      and ps.shown == A)
fw = FakeWires()
ps = E.PaperShow(E.Paper(fw), picture, clock=clock, run=False)
fw.fails = True
try:
    ps.step(clock.t)
    why = None
except OSError as ex:
    why = ex.errno
check(f"one that can't be written to (the SPI gives an error): said ({ps.note!r}), tried again in a minute",
      why == errno.EIO and ps.note == "It can't be written to" and ps.again == 60.0 and ps.shown is None)

# off: white first, asleep, let go of
E.SLEEP_WAIT, E.QUICK_WAIT = 1.5, 0.05                 # (asleep before its power's cut: a second or two, as it is)
fw = FakeWires()
ps = E.PaperShow(E.Paper(fw), picture, clock=time.monotonic, run=False)
ps.step(time.monotonic())
del fw.log[:]
ps.off()
check(f"set to Off: not at once (the row may be on its way past: {E.OFF_SETTLE} s)", ps.going() and not ps.closed
      and 1.9 < ps.off_at - time.monotonic() <= E.OFF_SETTLE and not fw.log and ps.wake.is_set())
back = ps.on()
check("...wanted again by then: it carries on, drawn whole", back is True and not ps.going() and ps.fresh
      and ps.off_at is None)
ps.off(after=0.0)
gone = ps.leave()
check(f"...left on Off: made white (what's left on paper stays for good), put to sleep, and let go of ({gone})",
      gone is True and ps.closed and fw.closed and fw.log == START + [
          ("c", 0x24), ("lots", b"\xff" * 4000), ("c", 0x22, 0xF7), ("c", 0x20), ("wait",), ("c", 0x10, 0x01),
          ("close",)])
check("...and on again after that: not this one (a new one's started)", ps.on() is False)
fw = FakeWires()
ps = E.PaperShow(E.Paper(fw), picture, clock=time.monotonic)
shown = until(lambda: fw.frames() == [("full", A)], 2)
ps.off(after=0.05)
white = until(lambda: fw.last()[0] == "white", 2)
back = ps.on()                                         # (white already, asleep, not yet let go of)
again = until(lambda: fw.last() == ("full", A), 3)
check(f"on its own thread: drawn as it starts ({shown}); set to Off, white a moment later ({white}); wanted again "
      f"while it waits, asleep, before its power's cut (as Waveshare's driver waits): it carries on, drawn whole "
      f"({back}, {again})", shown and white and back and again and not ps.closed and not fw.closed)
show["img"] = pic_of((9, 9))
ps.poke()
check("...what it shows changed (poke): looked at now, but not drawn within a few seconds of the last",
      not until(lambda: fw.last()[1] == E.packed(show["img"]), 0.5))
E.EINK_GAP = 0.0
ps.poke()
check("...(no wait between two, here): drawn in part", until(lambda: fw.last() == ("part", E.packed(show["img"])), 2))
ps.off(after=0.0)
closed = until(lambda: ps.closed and fw.closed, 3)
check(f"...Off, and left there: white, asleep, and let go of after the wait ({closed}); its thread's done",
      closed and fw.log[-2:] == [("c", 0x10, 0x01), ("close",)] and fw.frames()[-1][0] == "white"
      and until(lambda: not ps.thread.is_alive(), 2))
fw = FakeWires()
ps = E.PaperShow(E.Paper(fw), picture, clock=time.monotonic)
until(lambda: len(fw.frames()) == 1, 2)
t0 = time.monotonic()
ps.close(clear=True, wait=3.0)
took = time.monotonic() - t0
check(f"Pietato going (close): white, asleep and let go of, waited for, with no long wait ({took:.2f} s); not to be "
      f"had back", ps.closed and fw.closed and fw.frames()[-1][0] == "white" and took < E.SLEEP_WAIT - 0.5
      and not ps.thread.is_alive() and ps.on() is False)
fw = FakeWires()
ps = E.PaperShow(E.Paper(fw), picture, clock=time.monotonic)
until(lambda: len(fw.frames()) == 1, 2)
t0 = time.monotonic()
ps.close(clear=False, wait=3.0)
check(f"another HAT's to have its pins (close, as it is): let go of at once, not made white "
      f"({time.monotonic() - t0:.2f} s)", ps.closed and fw.closed and [f[0] for f in fw.frames()] == ["full"]
      and fw.hurry and time.monotonic() - t0 < 1.0)
E.EINK_GAP = 3.0


# ---- its pictures ----------------------------------------------------------------------------------------------------
def ink(img):
    """A picture's black: 122 rows of 250, True where it's black."""
    return np.asarray(img.convert("1")) == 0


def runs(on):
    """The stretches of a line that are black: [(first, last)]."""
    out, at = [], None
    for k, v in enumerate(list(on) + [False]):
        if v and at is None:
            at = k
        elif not v and at is not None:
            out.append((at, k - 1))
            at = None
    return out


def pieces(on):
    """How many separate pieces of black there are (touching at a side or a corner: the same piece)."""
    on, n = on.copy(), 0
    for y, x in zip(*np.nonzero(on)):
        if not on[y, x]:
            continue
        n += 1
        todo = [(y, x)]
        on[y, x] = False
        while todo:
            cy, cx = todo.pop()
            for ny in range(max(0, cy - 1), min(on.shape[0], cy + 2)):
                for nx in range(max(0, cx - 1), min(on.shape[1], cx + 2)):
                    if on[ny, nx]:
                        on[ny, nx] = False
                        todo.append((ny, nx))
    return n


def box_of(on):
    ys, xs = np.nonzero(on)
    return (xs.min(), ys.min(), xs.max(), ys.max()) if len(xs) else None


check("a blank picture: white paper, 250 by 122", E.sheet().size == (250, 122) and E.sheet().mode == "1"
      and not ink(E.sheet()).any())
NAMES = ("sun", "moon", "partly_day", "partly_night", "overcast", "fog", "rain", "heavyrain", "snow", "storm")
wx = {n: ink(E.ink_wx(n, 60)) for n in NAMES}
check(f"the weather's pictures, for paper: one for each kind there is (weather.py's {len(NAMES)}), black on white, "
      f"each its own", all(v.shape == (60, 60) and 200 < v.sum() < 2400 for v in wx.values())
      and len({v.tobytes() for v in wx.values()}) == len(NAMES)
      and set(NAMES) >= {g.wx_icon_name(c, d) for c in list(g.WX_CODES) + [None] for d in (True, False)})
check(f"...what's in front has a white edge round it, so the two don't run together: two clouds are two pieces "
      f"({pieces(wx['overcast'])}), a sun and its cloud ({pieces(wx['partly_day'])}: the cloud, the sun, its rays), a "
      f"storm's bolt and its cloud ({pieces(wx['storm'])})", pieces(wx["overcast"]) == 2 and pieces(wx["storm"]) == 2
      and 4 <= pieces(wx["partly_day"]) <= 10 and pieces(wx["partly_night"]) == 2 and pieces(wx["sun"]) == 9
      and pieces(wx["moon"]) == 1 and pieces(wx["fog"]) == 4 and pieces(wx["rain"]) == 4
      and pieces(wx["heavyrain"]) == 5 and pieces(wx["snow"]) == 6)
check("...small ones too (a day in the forecast), and one it doesn't know: a cloud",
      all(30 < ink(E.ink_wx(n, 20)).sum() < 300 for n in NAMES) and pieces(ink(E.ink_wx("whatever", 60))) == 1
      and E.ink_wx("sun", 60) is E.ink_wx("sun", 60))

t1 = ink(E.ink_time("7:49", "PM", "Wednesday, November 25"))
t2 = ink(E.ink_time("12:49", "PM", "Wednesday, November 25"))
t3 = ink(E.ink_time("19:49", "", "Wednesday, November 25"))
b1, b2 = box_of(t1[:92]), box_of(t2[:92])
check(f"Time: the time as big as fits across ({b1[2] - b1[0] + 1} of 250 for 7:49 PM, its figures {b1[3] - b1[1] + 1} "
      f"tall; 12:49 PM, wider, a little smaller: {b2[3] - b2[1] + 1}), the date under it",
      b1[3] - b1[1] + 1 >= 60 and 50 <= b2[3] - b2[1] + 1 < b1[3] - b1[1] + 1 and b2[2] - b2[0] + 1 >= 215
      and t1[98:116].any() and not t1[92:96].any() and (t1[96:] == t2[96:]).all())
check("...a margin left all round, whatever the time; no AM or PM for a 24-hour clock",
      all(not t[:, :6].any() and not t[:, -6:].any() and not t[:4].any() and not t[-4:].any() for t in (t1, t2, t3))
      and (t3 != t2).any())
nodate = ink(E.ink_time("7:49", "PM"))
check("...with no date: the time, in the middle", abs((box_of(nodate)[1] + box_of(nodate)[3]) / 2 - 60.5) <= 2)

DAYS = (("Thu", "rain", "64°", "50°"), ("Fri", "sun", "70°", "52°"), ("Sat", "overcast", "66°", "49°"))
w1 = ink(E.ink_weather("62°", "Partly cloudy", "partly_day", "68°", "51°", DAYS))
w2 = ink(E.ink_weather("62°", "Partly cloudy", "partly_day", "68°", "51°"))
w3 = ink(E.ink_weather("-3°", "Light snow", "snow"))
cols = [w1[84:, 8 + k * 78:8 + (k + 1) * 78] for k in range(3)]
check(f"Weather: its picture and how warm it is, big; its words, and today's high and low; a line, and the next three "
      f"days under it, each in its third ({[int(c.sum()) for c in cols]})", w1[82, 8:242].all() and not w1[80].any()
      and all(c.sum() > 150 for c in cols) and len({c.tobytes() for c in cols}) == 3
      and all(not c[:, :3].any() and not c[:, -3:].any() for c in cols) and w1[:80].sum() > 1500)
check("...with no days to come (the forecast came from another of yours): no line, all of it bigger, in the middle",
      not any(r.all() for r in w2[:, 8:242]) and box_of(w2)[3] - box_of(w2)[1] > box_of(w1[:80])[3] - box_of(w1[:80])[1]
      and abs((box_of(w2)[0] + box_of(w2)[2]) / 2 - 125) <= 4 and abs((box_of(w3)[1] + box_of(w3)[3]) / 2 - 61) <= 6)
long_wx = ink(E.ink_weather("104°", "Thunderstorm with heavy hail, later", "storm", "108°", "88°"))
d = E.ImageDraw.Draw(E.sheet())
f14 = E.oled_font(E.FONT, 14)
cut = E.fit_text(d, "A very long name for a song that goes on and on and on", f14, 120)
check(f"...words too long for their room: cut, with … ({cut!r}), never over the edge",
      cut.endswith("…") and d.textlength(cut, font=f14) <= 120 and len(cut) > 8 and not long_wx[:, -8:].any()
      and E.fit_text(d, "Short", f14, 120) == "Short")

PRICES = [("AAPL", "$235.86", 1.24), ("BTC", "$97,140", -2.31), ("DOGE", "$0.1234", None),
          ("BRK-B", "$1,234.56", -0.08)]
p4 = ink(E.ink_prices(PRICES))
lines = [y for y in range(122) if p4[y, 10:240].all()]
check(f"Prices: four at once, a row each with a line between ({lines}): the ticker, the price, and how far it's moved",
      lines == [32, 61, 90] and all(p4[y0 + 4:y0 + 25, 10:80].any() and p4[y0 + 4:y0 + 25, 100:200].any()
                                    for y0 in (3, 32, 61, 90)) and E.PRICE_ROWS == 4)
up, down = p4[3:32, 190:201], p4[32:61, 190:201]
ua, da = [r for r in (runs(row) for row in up) if r], [r for r in (runs(row) for row in down) if r]
check(f"...an arrow up for one that's risen (narrow at the top: {ua[0]}, wide below: {ua[-1]}), down for one that's "
      f"fallen ({da[0]}, {da[-1]}), neither where that isn't known",
      ua and da and ua[0][0][1] - ua[0][0][0] < ua[-1][0][1] - ua[-1][0][0]
      and da[0][0][1] - da[0][0][0] > da[-1][0][1] - da[-1][0][0] and not p4[63:89, 190:].any())
p2, p1 = ink(E.ink_prices(PRICES[:2])), ink(E.ink_prices([("^GSPC", "5,912.17", 0.4)]))
check("...fewer: bigger, in the middle; more than four: the first four (the rest have their turn the next minute)",
      [y for y in range(122) if p2[y, 10:240].all()] == [61] and p2.sum() > p4[:61].sum()
      and not any(p1[y, 10:240].all() for y in range(122)) and abs((box_of(p1)[1] + box_of(p1)[3]) / 2 - 61) <= 3
      and (ink(E.ink_prices(PRICES + [("ETH", "$3,400", 2.0)])) == p4).all() and not ink(E.ink_prices([])).any())

SHAPE = FACE.face_shape()
f_idle = ink(E.ink_face_page("idle", SHAPE, False))
bands = runs(f_idle.any(axis=1))
eyes = runs(f_idle[bands[0][0]:bands[0][1] + 1].any(axis=0)) if bands else []
mouth = runs(f_idle[bands[-1][0]:bands[-1][1] + 1].any(axis=0)) if len(bands) == 2 else []
eye = f_idle[bands[0][0]:bands[0][1] + 1, eyes[0][0]:eyes[0][1] + 1] if eyes else np.zeros((1, 1), bool)
check(f"Face: the Bot's own face (face.py's), as big as fits: two big eyes ({[b - a + 1 for a, b in eyes]} across, "
      f"{bands[0][1] - bands[0][0] + 1 if bands else 0} down) and a little mouth under them "
      f"({mouth[0][1] - mouth[0][0] + 1 if mouth else 0} across), top to bottom of the paper",
      len(bands) == 2 and len(eyes) == 2 and len(mouth) == 1 and bands[0][0] <= 10 and bands[1][1] >= 111
      and eyes[0][1] - eyes[0][0] >= 30 and bands[0][1] - bands[0][0] >= 50
      and mouth[0][1] - mouth[0][0] < eyes[0][1] - eyes[0][0]
      and abs((mouth[0][0] + mouth[0][1]) / 2 - 124.5) <= 2 and abs((eyes[0][0] + eyes[1][1]) / 2 - 124.5) <= 2)
mid_eye = eye.shape[0] // 2
check(f"...a glint in each eye, left white (the white in an eye's box: its four corners and the glint, "
      f"{pieces(~eye)} pieces; black right across its middle)", pieces(~eye) == 5
      and eye[mid_eye - 4:mid_eye + 12].all() and (~eye[4:mid_eye, 4:eye.shape[1] // 2]).sum() >= 12)
looks = {look: ink(E.ink_face_page(look, SHAPE, False)) for look in SE.EINK_LOOKS}
check(f"...its look when the Bot's happy, sad, cool or curious: each its own ({list(looks)}), all of it on the paper",
      len({v.tobytes() for v in looks.values()}) == len(SE.EINK_LOOKS) == 5
      and all(not v[:, :12].any() and not v[:, -12:].any() and not v[:4].any() and not v[-4:].any() and v.sum() > 800
              for v in looks.values()))
wide = FACE.face_shape({"eye_size": 10, "eye_height": 10, "eye_gap": 10, "mouth_size": 10})
small = FACE.face_shape({"eye_size": 0, "eye_height": 0, "eye_gap": 0, "mouth_size": 0})
f_wide, f_lash = ink(E.ink_face_page("idle", wide, False)), ink(E.ink_face_page("idle", wide, True))
f_small = ink(E.ink_face_page("idle", small, False))
check("...the shape its Character gives it (the biggest eyes, the furthest apart; the smallest; eyelashes): as big as "
      "fits, each time", (f_wide != f_idle).any() and (f_small != f_idle).any()
      and box_of(f_wide)[2] - box_of(f_wide)[0] > box_of(f_idle)[2] - box_of(f_idle)[0]
      and box_of(f_lash)[2] - box_of(f_lash)[0] > box_of(f_wide)[2] - box_of(f_wide)[0]
      and pieces(f_lash) == pieces(f_wide) == 3
      and all(not v[:, :12].any() and not v[:, -12:].any() and not v[:4].any() and not v[-4:].any()
              and (box_of(v)[3] - box_of(v)[1] >= 100 or box_of(v)[2] - box_of(v)[0] >= 210)
              for v in (f_wide, f_lash, f_small)))

FACE_IDLE = ("idle", SHAPE, False)
a_song = ink(E.ink_all("7:49", "PM", "Wed, Nov 25", ("62°", "partly_day"), FACE_IDLE, ("song", "Loud in the middle")))
a_two = ink(E.ink_all("7:49", "PM", "Wed, Nov 25", ("62°", "partly_day"), FACE_IDLE, ("prices", tuple(PRICES[:2]))))
a_one = ink(E.ink_all("7:49", "PM", "Wed, Nov 25", ("62°", "partly_day"), FACE_IDLE,
                      ("prices", (PRICES[3], PRICES[0]))))
a_words = ink(E.ink_all("7:49", "PM", "Wed, Nov 25", ("62°", "partly_day"), FACE_IDLE,
                        ("words", "Partly cloudy, high 68° low 51°")))
a_bare = ink(E.ink_all("7:49", "PM", "Wed, Nov 25", None, FACE_IDLE, None))
head, mid, foot = a_song[:24], a_song[26:94], a_song[98:]
check("Everything: along the top, the date on the left and the weather now on the right (its picture, how warm); in "
      "the middle, the Bot's face on the left and the time, big; a line; and a line of words along the bottom",
      head[:, 8:100].any() and head[:, 190:242].any() and not head[:, 110:180].any()
      and mid[:, 8:66].sum() > 500 and not mid[:, 67:76].any() and mid[:, 78:242].sum() > 1500
      and a_song[96, 8:242].all() and not a_song[95].any() and foot.any()
      and box_of(mid[:, 78:])[3] - box_of(mid[:, 78:])[1] >= 40)
check("...its face is the one Face shows, small", pieces(mid[:, 8:66]) == pieces(f_idle) == 3
      and (ink(E.ink_face((58, 60), "idle", SHAPE, False)) == a_song[30:90, 8:66]).all())
check("...the song that's playing, a little note before it", foot[:, 9:19].sum() > 30 and foot[:, 23:200].any()
      and not foot[:, 19:23].any())
r2 = runs(a_two[98:].any(axis=0))
check("...or two of your prices, one each side, an arrow each for how they've moved (no room for by how much)",
      a_two[98:, 8:120].any() and a_two[98:, 140:242].any() and r2[0][0] == 8 and r2[-1][1] == 241
      and not a_two[98:, 122:138].any())
check("...two that don't fit: the first, with how far it's moved; and with nothing playing and no prices, the "
      "weather's words", a_one[98:, 8:150].any() and not a_one[98:, 180:].any() and (a_one != a_two).any()
      and a_words[98:, 8:200].any() and (a_words[:96] == a_song[:96]).all())
check("...no weather: the date alone; nothing for the bottom: no line, the face and the time bigger for it",
      a_bare[:24, 8:100].any() and not a_bare[:24, 110:].any() and not any(r[8:242].all() for r in a_bare)
      and box_of(a_bare[26:])[3] > box_of(mid)[3] and (a_bare[:24, :100] == a_song[:24, :100]).all())
long_all = ink(E.ink_all("12:49", "PM", "Wed, Nov 25", ("104°", "storm"), ("cool", wide, True),
                         ("song", "A very long name for a song that goes on and on and on and on")))
check("...the widest of everything (12:49 PM, 104°, a long song, glasses and eyelashes): all of it on the paper, "
      "nothing over anything else", not long_all[:, :6].any() and not long_all[:, -6:].any()
      and not long_all[26:94, 67:76].any() and long_all[96, 8:242].all())
sheet = Image.new("L", (3 * 262 + 12, 5 * 134 + 12), 120)
shots = [E.ink_all("7:49", "PM", "Wed, Nov 25", ("62°", "partly_day"), FACE_IDLE, ("song", "Loud in the middle")),
         E.ink_all("7:49", "PM", "Wed, Nov 25", ("62°", "partly_day"), FACE_IDLE, ("prices", tuple(PRICES[:2]))),
         E.ink_all("12:49", "PM", "Wed, Nov 25", ("104°", "storm"), ("cool", wide, True),
                   ("song", "A very long name for a song that goes on and on and on and on")),
         E.ink_all("19:49", "", "Wed, Nov 25", None, ("happy", SHAPE, False), None),
         E.ink_time("7:49", "PM", "Wednesday, November 25"), E.ink_time("19:49", "", "Wednesday, November 25"),
         E.ink_weather("62°", "Partly cloudy", "partly_day", "68°", "51°", DAYS),
         E.ink_weather("104°", "Thunderstorm with heavy hail, later", "storm", "108°", "88°"),
         E.ink_weather("-3°", "Light snow", "snow"), E.ink_prices(PRICES), E.ink_prices(PRICES[:2]),
         E.ink_prices([("^GSPC", "5,912.17", 0.4)]), E.ink_face_page("idle", SHAPE, False),
         E.ink_face_page("sad", SHAPE, False), E.ink_face_page("curious", wide, True)]
for k, pic in enumerate(shots):
    sheet.paste(pic.convert("L"), (12 + (k % 3) * 262, 12 + (k // 3) * 134))
sheet.save(S + "/eink_pictures.png")

# ---- media mode ------------------------------------------------------------------------------------------------------
os.environ["HOME"] = HOME
g.STATE_FILE = S + "/gpi.json"; g.CACHE_DIR = S + "/gpicache"; g.PLEX_FILE = S + "/plex.json"
g.GROUP_LOG = S + "/gpigroup.json"
g.home_dir = lambda: HOME
import gk_static; gk_static.use_home(g, HOME)
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "", "returncode": 0, "stderr": ""})()


class FB:
    w, h = 640, 480
    last = None
    def show(self, img): FB.last = img.copy()
    def show_part(self, img, box): FB.last = img.copy()
    def invalidate(self): pass
    def close(self): pass


E.EINK_SETTLE = SE.EINK_SETTLE = 0.05                  # (a pick's waited on only a moment, here)
E.OFF_SETTLE, E.SLEEP_WAIT, E.QUICK_WAIT, E.EINK_GAP = 1.0, 0.3, 0.05, 0.0
m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.set_setting("name", "gpi")
SETTINGS = next(k for k, t in enumerate(g.LIBRARY) if t.get("type") == "settings")
m.view, m.tab, m.set_page = "list", SETTINGS, "display"   # (Settings > Screen: its rows are there)
CHOICES = ["Off", "Everything", "Time", "Weather", "Prices", "Face", "Each in turn"]


def rows():
    return [k for k, _, _ in m.settings_rows()]


def web_rows():
    return {r["key"]: r for s in m.web_settings()["sections"] for r in s["rows"]}


def on_row(key):
    m.set_sel = rows().index(key)


# where it can be
MODEL = S + "/model"
open(MODEL, "w").write("Raspberry Pi 4 Model B Rev 1.5\x00")
check(f"this machine (no Pi): no e-ink in Settings > Screen, here or on the web page ({m.eink_can()})",
      not m.eink_can() and "eink" not in rows() and "eink" not in web_rows() and "hat_flip" not in rows())
SO.PI_MODEL, SO.is_pc, SO.is_handheld = MODEL, (lambda: False), (lambda: False)
m.case = None
r = rows()
check(f"a Pi on a TV or monitor: Settings > Screen > Waveshare 2.13 e-ink, under the OLED's row, the last there: one "
      f"row, all it can show to cycle through ({m.settings_rows()[-1] if r else None})", m.eink_can()
      and r[-2:] == ["oled", "eink"] and m.settings_rows()[-1] == ("eink", "Waveshare 2.13 e-ink", CHOICES)
      and g.EINK_CHOICES == CHOICES and m.settings_place("eink") == ("display", len(r) - 1)
      and "eink" not in [k for k, _, _ in m.settings_root_rows()])
check("...Off, to begin with; its other row (upside down) not there till it's on, and none for which panel it is",
      (g.SETTINGS_DEFAULT["eink"], g.SETTINGS_DEFAULT["hat_flip"]) == ("Off", "Off") and m.eink_value() == "Off"
      and m.eink is None and "hat_flip" not in r and "hat_flip" not in web_rows()
      and not any("version" in label.lower() for _, label, _ in g.SETTINGS_PAGES["display"])
      and not set(g.SETTINGS_DEFAULT) & {"eink_version", "eink_flip"})
m.case = "2w"
in_case = m.eink_can(), "eink" in rows(), "eink" in web_rows()
m.case = None
SO.is_handheld = lambda: True
on_handheld = m.eink_can(), "eink" in rows()
SO.is_handheld, SO.is_pc = (lambda: False), (lambda: True)
on_pc = m.eink_can(), "eink" in rows()
SO.is_pc = lambda: False
check(f"...not in a GPi Case (its screen has the pins: {in_case}), on a handheld ({on_handheld}) or a PC ({on_pc})",
      in_case == (False, False, False) and on_handheld == (False, False) and on_pc == (False, False) and m.eink_can())

# what there is to show: the time, the weather, your prices, the Bot's face
WALL = time.mktime((2026, 11, 25, 19, 49, 30, 0, 0, -1))   # (7:49 in the evening, on a Wednesday)
NOW = time.localtime(WALL)
MINUTE = int(WALL // 60)
m.eink_wall = lambda: WALL
m.set_setting("clock", "12-hour")
SHORT, LONG = time.strftime("%a, %b ", NOW) + "25", time.strftime("%A, %B ", NOW) + "25"
m.weather.data = {"temp": 61.6, "code": 2, "is_day": True, "days": [
    {"date": "2026-11-24", "code": 0, "hi": 70.2, "lo": 55.1},        # (yesterday's: the forecast's a day old)
    {"date": "2026-11-25", "code": 2, "hi": 68.4, "lo": 50.6},
    {"date": "2026-11-26", "code": 61, "hi": 63.5, "lo": 49.9},
    {"date": "2026-11-27", "code": 0, "hi": 70.0, "lo": 52.2},
    {"date": "2026-11-28", "code": 3, "hi": 66.1, "lo": 48.8},
    {"date": "2026-11-29", "code": 71, "hi": 40.0, "lo": 30.0}]}
m.weather.t = WALL - 600
WX = ("62°", "Partly cloudy", "partly_day", "68°", "51°",
      (("Thu", "rain", "64°", "50°"), ("Fri", "sun", "70°", "52°"), ("Sat", "overcast", "66°", "49°")))
check(f"the weather for it (the Weather app's): how warm, its words and picture, today's high and low (today's, by its "
      f"date, though the forecast began yesterday), and the next three days ({m.eink_weather(WALL)})",
      m.eink_weather(WALL) == WX)
m.stocks.stocks = [{"symbol": s, "name": s} for s in ("AAPL", "MSFT", "NVDA")]
m.stocks.quotes = {"AAPL": {"t": WALL - 120, "d": {"price": 235.86, "currency": "USD", "change_1d": 1.2391}},
                   "MSFT": {"t": WALL - 120, "d": {"price": 420.5, "currency": "USD", "change_1d": 0.5}},
                   "NVDA": {"t": WALL - 120, "d": {"price": 140.11, "currency": "USD", "change_1d": -1.0}}}
m.crypto.coins = [{"id": "bitcoin", "symbol": "BTC", "name": "Bitcoin"},
                  {"id": "dogecoin", "symbol": "DOGE", "name": "Dogecoin"}]
m.crypto.quotes = {"bitcoin": {"t": WALL - 60, "d": {"price": 97140.2, "change_24h": -2.3104}},
                   "dogecoin": {"t": WALL - 60, "d": {"price": 0.123412, "change_24h": None}}}
MINE = m.oled_prices(WALL)
check(f"your prices for it (the Finance app's, as the OLED has them): {MINE}", MINE == [
    ("AAPL", "$235.86", 1.24), ("MSFT", "$420.50", 0.5), ("NVDA", "$140.11", -1.0), ("BTC", "$97,140", -2.31),
    ("DOGE", "$0.1234", None)])
SHAPE_NOW, LASHES_NOW = m.oled_face()
m.face_look = lambda: "idle"
FACE_NOW = ("idle", SHAPE_NOW, LASHES_NOW)
PAIR = tuple(MINE[(MINUTE + k) % 5] for k in range(2))


def same(img, want):
    return img is not None and (ink(img) == ink(want)).all()


def pic(pick=None):
    """What it'd show now, set to this: (the picture, seconds till it's asked again, its kind)."""
    if pick is not None:
        m.set_setting("eink", pick)
    return m.eink_picture(0) or (None, None, None)


img, wait, kind = pic("Everything")
check(f"Everything: the date, the weather now, the Bot's face, the time, and (nothing playing) two of your prices, "
      f"as they stand ({PAIR[0][0]}, {PAIR[1][0]}); asked again in a couple of seconds ({wait}), in case a song starts",
      kind == "all" and same(img, E.ink_all("7:49", "PM", SHORT, ("62°", "partly_day"), FACE_NOW, ("prices", PAIR)))
      and wait == SE.EINK_LOOK == 2.0 and SHORT == "Wed, Nov 25")
check("...asked again while nothing's changed: the same picture, not drawn again", pic()[0] is img)
m.eink_wall = lambda: WALL + 29.2
late = pic()
m.eink_wall = lambda: WALL + 30
check(f"...near the end of a minute: asked again just as the next begins ({late[1]:.2f} s), and it's the next "
      f"minute's then: the time, and the next two prices", abs(late[1] - 0.85) < 0.01 and late[0] is img and same(
          pic()[0], E.ink_all("7:50", "PM", SHORT, ("62°", "partly_day"), FACE_NOW,
                              ("prices", tuple(MINE[(MINUTE + 1 + k) % 5] for k in range(2))))))
m.eink_wall = lambda: WALL
seen = set()
for k in range(5):
    m.eink_wall = lambda k=k: WALL + 60 * k
    pic()
    seen.update(x[0] for x in m.eink_key[6][1])
m.eink_wall = lambda: WALL
check(f"...all of your prices, two at a time, a minute each ({sorted(seen)})", seen == {x[0] for x in MINE})
song = g.item(HOME + "/Music/Loud in the middle.wav", "Loud in the middle", "audio", HOME + "/Music/x.wav")
m.proc, m.kind, m.cur = type("P", (), {"poll": lambda self: None})(), "audio", song
check("...a song playing: its name along the bottom, in place of the prices (as the status bar names it)",
      m.eink_song() == "Loud in the middle" and same(pic()[0], E.ink_all(
          "7:49", "PM", SHORT, ("62°", "partly_day"), FACE_NOW, ("song", "Loud in the middle"))))
m.kind, m.meta["song"] = "radio", "A Band - Their Song"
check("...the radio: the song the station says it's playing", same(pic()[0], E.ink_all(
    "7:49", "PM", SHORT, ("62°", "partly_day"), FACE_NOW, ("song", "A Band - Their Song"))))
m.kind = "video"
check("...a video's not a song: your prices", m.eink_song() == "" and pic()[0] is not None
      and m.eink_key[6] == ("prices", PAIR))
m.proc, m.kind, m.cur = None, None, None
m.meta.pop("song", None)
stocks_was, coins_was = m.stocks.stocks, m.crypto.coins
m.stocks.stocks, m.crypto.coins = [], []
check("...no prices: the weather's words, and today's high and low", same(pic()[0], E.ink_all(
    "7:49", "PM", SHORT, ("62°", "partly_day"), FACE_NOW, ("words", "Partly cloudy, high 68° low 51°"))))
m.weather.t = WALL - SE.EINK_OLD - 60
check("...the weather hours old too (no WiFi): the date, the face and the time, nothing along the bottom",
      same(pic()[0], E.ink_all("7:49", "PM", SHORT, None, FACE_NOW, None)) and m.eink_weather(WALL) is None)
m.weather.t = WALL - 600
m.stocks.stocks, m.crypto.coins = stocks_was, coins_was
m.set_setting("clock", "24-hour")
check("...a 24-hour clock: 19:49, no AM or PM", same(pic()[0], E.ink_all(
    "19:49", "", SHORT, ("62°", "partly_day"), FACE_NOW, ("prices", PAIR))))
img, wait, kind = pic("Time")
check(f"Time: the time, as the clock's set, and the date in full ({LONG})", kind == "time"
      and same(img, E.ink_time("19:49", "", LONG)) and LONG == "Wednesday, November 25")
m.set_setting("clock", "12-hour")
check("...12-hour: 7:49 PM", same(pic()[0], E.ink_time("7:49", "PM", LONG)))
img, wait, kind = pic("Weather")
check("Weather: now, today's high and low, and the next three days", kind == "weather"
      and same(img, E.ink_weather(*WX)))
days_was = m.weather.data["days"]
m.weather.data["days"] = days_was[:2]
check("...a forecast with no days to come: without them", same(pic()[0], E.ink_weather(*WX[:5])))
del m.weather.data["days"]
check("...with no days at all (as another of yours gives it): how warm, and its words",
      same(pic()[0], E.ink_weather("62°", "Partly cloudy", "partly_day")))
m.weather.data["days"] = days_was
m.weather.t = WALL - SE.EINK_OLD - 60
img, wait, kind = pic()
check("...hours old (the WiFi's down, say): the time instead", kind == "time"
      and same(img, E.ink_time("7:49", "PM", LONG)))
m.weather.t = WALL - 600
img, wait, kind = pic("Prices")
p_now = MINUTE % 2
check(f"Prices: four at a time (five of them: two lots, a minute each; this minute's: {p_now + 1})", kind == "prices"
      and same(img, E.ink_prices(MINE[p_now * 4:p_now * 4 + 4])))
m.eink_wall = lambda: WALL + 60
check("...the next minute: the others", same(pic()[0], E.ink_prices(MINE[(1 - p_now) * 4:(1 - p_now) * 4 + 4])))
m.eink_wall = lambda: WALL
for q in list(m.stocks.quotes.values()) + list(m.crypto.quotes.values()):
    q["t"] -= SO.QUIET_WX_OLD
img, wait, kind = pic()
check("...none that aren't hours old: the time instead", kind == "time" and same(img, E.ink_time("7:49", "PM", LONG)))
for q in list(m.stocks.quotes.values()) + list(m.crypto.quotes.values()):
    q["t"] += SO.QUIET_WX_OLD
img, wait, kind = pic("Face")
check("Face: the Bot's face, as its Character has it", kind == "face"
      and same(img, E.ink_face_page("idle", SHAPE_NOW, LASHES_NOW)))
m.face_look = lambda: "happy"
happy = pic()[0]
m.face_look = lambda: "thinking"
busy = pic()[0]
check("...how it felt about what it last said (happy), for as long as its own face shows it; not what it's doing "
      "this second (thinking, talking: gone before paper's caught up)",
      same(happy, E.ink_face_page("happy", SHAPE_NOW, LASHES_NOW)) and same(busy, img))
m.face_look = lambda: 1 / 0
check("...the Bot not there to ask: as it's always looked", same(pic()[0], img))
m.face_look = lambda: "idle"
conf_was = dict(m.friend.conf)
m.friend.conf.update(eye_size="9", eye_gap="8", lashes="on")
shape2, lashes2 = m.oled_face()
check("...its Character changed (bigger eyes, further apart, eyelashes): its face on paper too",
      lashes2 is True and shape2 != SHAPE_NOW and same(pic()[0], E.ink_face_page("idle", shape2, True))
      and not same(pic()[0], img))
m.friend.conf.clear()
m.friend.conf.update(conf_was)
kinds = []
for k in range(10):
    m.eink_wall = lambda k=k: (MINUTE - MINUTE % 5 + k) * 60 + 5.0
    got = pic("Each in turn")
    kinds.append(got[2] if got[2] != "prices" else "prices " + m.eink_key[1][0][0])
m.eink_wall = lambda: WALL
check(f"Each in turn: the time, the weather, your prices (each lot) and the face, a minute each, round and round "
      f"({kinds[:5]})", kinds[:5] == ["time", "weather", "prices AAPL", "prices DOGE", "face"]
      and kinds[5:] == kinds[:5])
m.weather.t = WALL - SE.EINK_OLD - 60
m.stocks.stocks, m.crypto.coins = [], []
kinds = []
for k in range(4):
    m.eink_wall = lambda k=k: (MINUTE - MINUTE % 2 + k) * 60 + 5.0
    kinds.append(pic()[2])
m.eink_wall = lambda: WALL
check(f"...with no weather and no prices: the time and the face ({kinds})", kinds == ["time", "face"] * 2)
m.weather.t = WALL - 600
m.stocks.stocks, m.crypto.coins = stocks_was, coins_was
check("set to Off: nothing", pic("Off") == (None, None, None))
font_was = E.FONT_UI_BOLD
E.FONT_UI_BOLD, m.eink_key = S + "/no-such-font.otf", None
O._FONTS.clear()
broken = [pic("Time"), pic()]
E.FONT_UI_BOLD = font_was
O._FONTS.clear()
check("a picture that can't be drawn (its font's gone): nothing (the paper's left as it is), said once",
      broken == [(None, None, None)] * 2 and m.eink_said)
m.eink_said = False
m.set_setting("eink", "Off")

# picked: drawn
made = []


def make_wires(spi):
    made.append((spi, FakeWires()))
    return made[-1][1]


def drawn(fw, how, want, secs=3.0):
    """Its last refresh is this one (in time)."""
    return until(lambda: fw.last() == (how, E.packed(want)), secs)


m.eink_wires = make_wires
m.eink_spi = S + "/spidev"
m.glow_configs = [S + "/config.txt"]
open(S + "/config.txt", "w").write("dtparam=audio=on\n")
on_row("eink")
m.dirty = True
m.flush()
m.press("right")
fw = made[-1][1] if made else None
ALL_NOW = E.ink_all("7:49", "PM", SHORT, ("62°", "partly_day"), FACE_NOW, ("prices", PAIR))
check(f"▶ on its row: Everything: its wires had, on the Pi's SPI ({made[-1][0] if made else None}), its power on, "
      f"and kept ({m.setting('eink')!r}, {m.eink_value()!r})", m.eink is not None and len(made) == 1
      and made[0][0] == m.eink_spi and fw.log[0] == ("power", 1) and m.setting("eink") == "Everything"
      and m.eink_value() == "Everything" and not m.eink_note and m.eink_lit())
check("...and drawn whole: everything, as it is now", drawn(fw, "full", ALL_NOW) and len(fw.frames()) == 1)
check("...its SPI's there: config.txt left as it is", open(S + "/config.txt").read() == "dtparam=audio=on\n"
      and not m.eink_restart)
r = rows()
check(f"...its other row is there now, under it: E-ink upside down, and that's all ({r[-3:]})",
      r[-3:] == ["oled", "eink", "hat_flip"]
      and m.settings_rows()[-1] == ("hat_flip", "E-ink upside down", ["Off", "On"]) and m.hat_on() == "E-ink")
m.dirty = True
m.flush()
FB.last.convert("RGB").save(S + "/settings_eink.png")
m.press("right")
check(f"▶: Time ({m.setting('eink')!r}): drawn whole, on the same wires (no new start)", m.setting("eink") == "Time"
      and drawn(fw, "full", E.ink_time("7:49", "PM", LONG)) and len(made) == 1)
n = len(fw.frames())
m.eink_wall = lambda: WALL + 60
m.eink.poke()
check("...the next minute: only what's changed drawn (a partial refresh)",
      drawn(fw, "part", E.ink_time("7:50", "PM", LONG)) and len(fw.frames()) == n + 1)
m.eink_wall = lambda: WALL
m.eink.poke()
drawn(fw, "part", E.ink_time("7:49", "PM", LONG))
n = len(fw.frames())
E.EINK_SETTLE = SE.EINK_SETTLE = 0.6                   # (as long as it's really waited on, near enough)
m.press("right")
m.press("right")
m.press("right")
stopped = drawn(fw, "full", E.ink_face_page(*FACE_NOW))
E.EINK_SETTLE = SE.EINK_SETTLE = 0.05
check(f"▶▶▶, one after another: past Weather and Prices to Face ({m.setting('eink')!r}): the one it stops on "
      f"drawn, whole, and not the ones it passed ({[f[0] for f in fw.frames()[n:]]})", m.setting("eink") == "Face"
      and stopped and len(fw.frames()) == n + 1)

# upside down
on_row("hat_flip")
m.press("right")
TURNED = E.packed(E.ink_face_page(*FACE_NOW), True)
check(f"E-ink upside down, ▶: On ({m.setting('hat_flip')!r}): the same picture, turned, drawn whole (a full "
      f"refresh), on the same wires", m.setting("hat_flip") == "On" and until(lambda: fw.last() == ("full", TURNED), 3)
      and fw.log[-3] == ("c", 0x22, 0xF7) and len(made) == 1 and m.eink.flip is True)
m.press("right")
check("...▶: Off: the right way up again", m.setting("hat_flip") == "Off"
      and drawn(fw, "full", E.ink_face_page(*FACE_NOW)) and m.eink.flip is False)

# Off
on_row("eink")
n = len(fw.frames())
m.eink_pick("Each in turn")
until(lambda: len(fw.frames()) > n and fw.last()[0] == "full", 3)
n = len(fw.frames())
m.press("right")
off_now = m.setting("eink"), m.eink_value(), m.eink.going(), fw.closed
m.press("right")
check(f"▶ from Each in turn: Off, but not white yet (the row may be on its way past: {off_now}); ▶ again, to "
      f"Everything: the same paper carries on, drawn whole, never made white", off_now == ("Off", "Off", True, False)
      and m.setting("eink") == "Everything" and m.eink_lit() and drawn(fw, "full", ALL_NOW) and len(made) == 1
      and "white" not in [f[0] for f in fw.frames()[n:]])
m.press("left")
check(f"◀: Off, and left there: its other rows go ({rows()[-1]})", m.setting("eink") == "Off"
      and rows()[-1] == "eink")
gone = until(lambda: m.eink.closed and fw.closed, 3)
check(f"...made white a moment later (what's on paper stays for good), put to sleep, and let go of ({gone})", gone
      and fw.frames()[-1][0] == "white" and fw.log[-2:] == [("c", 0x10, 0x01), ("close",)] and not m.eink_lit()
      and m.eink_value() == "Off")
m.press("left")
fw = made[-1][1]
check(f"◀ from Off: round to Each in turn: new wires had, and drawn ({len(made)})", len(made) == 2 and m.eink_lit()
      and m.setting("eink") == "Each in turn" and until(lambda: fw.last()[0] == "full", 3))
m.eink_pick("Time")
drawn(fw, "full", E.ink_time("7:49", "PM", LONG))


class Going:
    """A paper that's just this moment gone off for good: not to be had back, its pins not yet let go of."""
    note = ""

    def __init__(self):
        self.calls = []

    def on(self):
        self.calls.append("on")
        return False

    def going(self):
        return True

    def close(self, clear=True, wait=None):
        self.calls.append(("close", wait, len(made)))


real, old = m.eink, Going()
m.eink = old
m.eink_pick("Face")
check(f"turned on again the moment the last one's gone off for good: that one's waited for (its pins let go of) "
      f"before new wires are had ({old.calls})", old.calls == ["on", ("close", SE.DROP_WAIT, 2)] and len(made) == 3
      and m.eink is not old and m.eink_lit() and drawn(made[-1][1], "full", E.ink_face_page(*FACE_NOW)))
m.eink.close(clear=False, wait=2)
m.eink = real
m.eink_pick("Time")
drawn(fw, "full", E.ink_time("7:49", "PM", LONG))

# its weather and prices, fetched when they're due
asked_wx, asked_prices = [], []
m.weather.refresh = lambda *a, **k: asked_wx.append(m.setting("eink"))
m.oled_prices_due = lambda: asked_prices.append(m.setting("eink"))
for choice in CHOICES[1:]:
    m.set_setting("eink", choice)
    m.eink_seen = 0.0
    m.eink_tick(time.monotonic())
m.eink_tick(time.monotonic())
check(f"media mode's loop, every couple of seconds: the weather fetched when it's due while the paper shows it "
      f"({asked_wx}), and your prices ({asked_prices})", asked_wx == ["Everything", "Weather", "Each in turn"]
      and asked_prices == ["Everything", "Prices", "Each in turn"])
m.eink_pick("Off")
m.eink_seen = 0.0
m.eink_tick(time.monotonic())
check("...not while it's off", len(asked_wx) == 3 and len(asked_prices) == 3)
del m.weather.refresh, m.oled_prices_due
until(lambda: m.eink.closed, 3)


# an OLED HAT, and an LED backlight: one of the three at a time
class OledWires:
    def __init__(self):
        self.log, self.closed = [], False

    def reset(self):
        self.log.append(("reset",))

    def command(self, data):
        self.log.append(("c", bytes(data)))

    def data(self, data):
        self.log.append(("d", bytes(data)))

    def close(self):
        self.closed = True


oleds = []
m.oled_wires = lambda spi: oleds.append(OledWires()) or oleds[-1]
m.oled_spi = m.eink_spi
open(m.eink_spi, "ab").close()
m.eink_pick("Everything")
fw = made[-1][1]
drawn(fw, "full", ALL_NOW)
m.msg = ""
on_row("oled")
m.press("right")
m.press("right")                                       # (to Time: no sockets needed for it, here)
check(f"the OLED turned on (its HAT goes on the same pins): the e-ink's let go of at once, as it is (not made white: "
      f"no time for that), and set to Off, and that's said ({m.msg!r})", m.oled is not None and m.eink is None
      and m.setting("eink") == "Off" and fw.closed and fw.hurry and "white" not in [f[0] for f in fw.frames()]
      and m.msg == "The e-ink is off: the OLED uses its pins" and rows()[-2:] == ["eink", "hat_flip"]
      and len(oleds) == 1)
its_row = m.settings_rows()[-1]
m.hat_flip_pick("On")
check(f"...the one row under them is the OLED's now ({its_row[1]!r}), and On there turns the OLED's picture round",
      its_row == ("hat_flip", "OLED upside down", ["Off", "On"]) and m.hat_on() == "OLED"
      and m.oled.screen.flip is True)
m.msg = ""
on_row("eink")
m.press("right")
fw = made[-1][1]
check(f"...and the e-ink turned on again: the OLED goes off ({m.msg!r}); the row's the e-ink's "
      f"({m.settings_rows()[-1][1]!r}), still On: its picture's upside down from the start", m.oled is None
      and oleds[-1].closed and m.setting("oled") == "Off" and m.eink_lit()
      and until(lambda: fw.last() == ("full", E.packed(ALL_NOW, True)), 3)
      and m.msg == "The OLED is off: the e-ink uses its pins"
      and m.settings_rows()[-1] == ("hat_flip", "E-ink upside down", ["Off", "On"]) and m.eink.flip is True)
m.hat_flip_pick("Off")
drawn(fw, "full", ALL_NOW)
m.glow_can = lambda: True
m.glow_spi, m.glow_port = S + "/spi-leds", 0
open(m.glow_spi, "wb").close()
m.msg = ""
m.glow_pick("glow_on", "On")
check(f"the LED backlight turned on (its LEDs are on the pin the e-ink's pictures are sent on): the e-ink's let go "
      f"of, and that's said ({m.msg!r})", m.glow_grid is not None and m.eink is None and m.setting("eink") == "Off"
      and fw.closed and m.msg == "The e-ink is off: the LEDs use its pin")
m.msg = ""
on_row("eink")
m.press("right")
fw = made[-1][1]
check(f"...and the e-ink turned on again: the LEDs go off ({m.msg!r})", m.glow_grid is None
      and m.setting("glow_on") == "Off" and m.eink_lit()
      and m.msg == "The LED backlight is off: the e-ink uses its pin")
drawn(fw, "full", ALL_NOW)
m.eink_drop()
n = len(made)
m.set_setting("eink", "Time")
m.set_setting("glow_on", "On")
m.eink_start()
both = m.eink, m.eink_value()
m.set_setting("glow_on", "Off")
m.set_setting("oled", "Time")
m.eink_start()
check(f"both set, somehow, as it starts: the LEDs keep the pin ({both[1]!r}), or the OLED its pins "
      f"({m.eink_value()!r}), and its row says so", both == (None, "The LED backlight has its pin") and m.eink is None
      and m.eink_value() == "The OLED has its pins" and len(made) == n)
m.set_setting("oled", "Off")
vars(m).pop("glow_can")
m.glow_restart = False
open(S + "/config.txt", "w").write("dtparam=audio=on\n")

# at start-up
m.eink_start()
fw = made[-1][1]
check("at start-up, set to something: its wires had, and it's drawn", len(made) == n + 1 and m.eink_lit()
      and drawn(fw, "full", E.ink_time("7:49", "PM", LONG)) and m.eink_value() == "Time")
m.eink_start()
check("...once", len(made) == n + 1)
m.eink_drop()

# the Pi's SPI not on, its pins taken, a panel that isn't answering
m.eink_spi = S + "/no-spidev"
m.msg = ""
on_row("eink")
m.press("right")
conf = open(S + "/config.txt").read()
check(f"the Pi's SPI not on: turned on in config.txt, and a restart asked for ({m.msg!r}; its row: "
      f"{m.eink_value()!r})", m.eink is None and m.eink_restart and "dtparam=spi=on" in conf
      and conf.startswith("dtparam=audio=on\n") and G.BLOCK[0] in conf
      and m.msg == "Restart the Pi to turn its SPI on for the e-ink" and m.eink_value() == "Restart the Pi"
      and m.setting("eink") == "Everything")
wr = web_rows().get("eink") or {}
check(f"...the web page's Settings say so too ({wr.get('status')!r})", wr.get("value") == "Everything"
      and wr.get("status") == "Restart the Pi to turn its SPI on" and wr.get("tone") == "")
m.eink_pick("Off")
m.eink_restart = False
open(S + "/config.txt", "w").write("dtparam=audio=on\n")
m.eink_spi = S + "/spidev"


def taken(spi):
    raise OSError(errno.EBUSY, "Device or resource busy")


m.eink_wires = taken
m.msg = ""
m.press("right")
check(f"its pins taken by another program: said ({m.msg!r}; its row: {m.eink_value()!r})", m.eink is None
      and m.eink_value() == "Its pins are in use" and m.msg == "The e-ink can't be used: its pins are in use"
      and (web_rows()["eink"].get("status"), web_rows()["eink"].get("tone")) == ("Its pins are in use", "bad"))
m.eink_pick("Off")
check("...Off: nothing's said of it any more", m.eink_value() == "Off" and "status" not in web_rows()["eink"])
m.eink_wires = lambda spi: made.append((spi, FakeWires(stuck=True))) or made[-1][1]
m.press("right")
fw = made[-1][1]
said = until(lambda: m.eink_value() == "It isn't answering", 3)
check(f"a panel that never says it's done (BUSY stays high): its row says it isn't answering ({said}), here and on "
      f"the web page", said and web_rows()["eink"].get("status") == "It isn't answering"
      and web_rows()["eink"].get("tone") == "bad" and m.setting("eink") == "Everything")
m.dirty, m.eink_seen = False, 0.0
m.eink_tick(time.monotonic())
redrawn, m.dirty, m.eink_seen = m.dirty, False, 0.0
m.eink_tick(time.monotonic())
check(f"...media mode's loop sees its row's changed, and Settings is drawn again, the once ({redrawn}, {m.dirty})",
      redrawn is True and m.dirty is False and m.eink_noted == "It isn't answering")
m.eink_drop()
m.eink_wires = make_wires

# the web page's Settings
wr = web_rows()
screen = [s for s in m.web_settings()["sections"] if s["id"] == "screen"][0]
check(f"the web page's Settings: Waveshare 2.13 e-ink, the last of Screen's, with all it can show "
      f"({wr['eink']['choices']})", wr["eink"]["kind"] == "choice" and wr["eink"]["value"] == "Off"
      and wr["eink"]["label"] == "Waveshare 2.13 e-ink" and wr["eink"]["choices"] == CHOICES
      and wr["eink"]["note"].startswith("The e-Paper HAT on the Pi's pins, and what it shows: ")
      and [r["key"] for r in screen["rows"]][-2:] == ["oled", "eink"] and "status" not in wr["eink"])
said = m.web_settings_do({"key": "eink", "value": "Weather"})
fw = made[-1][1]
wr = web_rows()
check(f"...picked there: drawn ({said}), and its other row is there to pick: E-ink upside down", said == {"ok": True}
      and m.setting("eink") == "Weather" and drawn(fw, "full", E.ink_weather(*WX))
      and [r["key"] for r in [s for s in m.web_settings()["sections"] if s["id"] == "screen"][0]["rows"]][-3:]
      == ["oled", "eink", "hat_flip"] and wr["hat_flip"]["choices"] == ["Off", "On"]
      and wr["hat_flip"]["value"] == "Off" and wr["hat_flip"]["label"] == "E-ink upside down"
      and "other way up" in wr["hat_flip"]["note"] and "eink_version" not in wr)
said = m.web_settings_do({"key": "hat_flip", "value": "On"})
check(f"...upside down picked there ({said}): drawn that way up", said == {"ok": True}
      and until(lambda: fw.last() == ("full", E.packed(E.ink_weather(*WX), True))
                and fw.log[-3] == ("c", 0x22, 0xF7), 3) and web_rows()["hat_flip"]["value"] == "On")
said = [m.web_settings_do({"key": "eink", "value": "Fireworks"}),
        m.web_settings_do({"key": "hat_flip", "value": "Sideways"}),
        m.web_settings_do({"key": "eink_version", "value": "V3"}),
        m.web_settings_do({"key": "eink_flip", "value": "On"})]
check(f"...something they can't be, or a row there isn't any more (which panel it is): not taken ({said})",
      all("error" in x for x in said) and (m.setting("eink"), m.setting("hat_flip")) == ("Weather", "On")
      and m.setting("eink_version") is None)
m.hat_flip_pick("Off")
m.case = "2w"
said = m.web_settings_do({"key": "eink", "value": "Off"})
m.case = None
check(f"...where there can't be one: no such setting to pick ({said})", "error" in said
      and m.setting("eink") == "Weather")
said = m.web_settings_do({"key": "eink", "value": "Off"})
gone = until(lambda: m.eink.closed, 3)
check(f"...Off there: white, asleep, let go of ({gone}); its other row isn't there to pick",
      said == {"ok": True} and gone and fw.frames()[-1][0] == "white" and "hat_flip" not in web_rows()
      and "error" in m.web_settings_do({"key": "hat_flip", "value": "On"}))

# Pietato going
m.eink_pick("Time")
fw = made[-1][1]
drawn(fw, "full", E.ink_time("7:49", "PM", LONG))
t0 = time.monotonic()
m.active = False
m.shutdown()
took = time.monotonic() - t0
check(f"Pietato going: its e-ink made white (not left showing the time it stopped at), put to sleep and let go of, "
      f"before it's gone ({took:.1f} s)", m.eink is None and fw.closed and fw.frames()[-1][0] == "white"
      and fw.log[-2:] == [("c", 0x10, 0x01), ("close",)] and took < 6)

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
