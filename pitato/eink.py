"""A Waveshare 2.13inch e-Paper HAT on the Pi's pins (250x122, black and white): the time, the weather, your prices,
the Bot's face, or all of it at once.
The HAT's own wiring: the Pi's SPI (its MOSI, clock and CE0: GPIO 10, 11 and 8), its D/C on GPIO 25, its reset on
GPIO 17, BUSY on GPIO 24 (high while the panel's at work) and its power on GPIO 18. It's written to as oled.py writes
its HAT: the SPI as it is (/dev/spidev0.0) and the kernel's own GPIO lines (/dev/gpiochipN), so nothing needs
installing. What goes to the panel is what Waveshare's own driver for it sends (its V4, the one sold now: an older
V3 panel wants its waveforms sent too, and shows nothing here).
Paper isn't a screen that's drawn all the time. A picture's put on it whole (a full refresh: it flashes black and
white for a couple of seconds, and is clean), and after that only what's changed is (a partial refresh: quick, no
flash, though each leaves a little of what was there). So: a full one as it's turned on and as you pick what it
shows, partial ones as the picture changes, and a full one again once it's had FULL_AFTER of those (a whole new
picture counts as NEW_PICTURE of them). Never two within EINK_GAP seconds, and nothing at all while the picture's
the same: what it shows changes about once a minute at most, which is what the panel's made for.
PaperShow is its thread: it asks what to show (screens/eink.py's eink_picture, as Settings > Screen > Waveshare
2.13 e-ink is set) and puts it there. Turned off, it goes white first (a picture left on paper stays for good),
then to sleep, and its pins are let go of."""
import errno
import fcntl
import math
import os
import struct
import threading
import time

from PIL import Image, ImageDraw

from .face import draw_face
from .oled import (GPIO_V2_GET_LINE_IOCTL, GPIO_V2_LINE_FLAG_OUTPUT, GPIO_V2_LINE_SET_VALUES_IOCTL, LINE_REQUEST,
                   OLED_SPI, REQ_CONSUMER, REQ_FD, REQ_FLAGS, REQ_LINES, Spi, oled_font, pi_chip)
from .theme import FONT, FONT_BOLD, FONT_UI_BOLD

EINK_W, EINK_H = 250, 122    # the picture, as you look at it: the HAT's long side across
EINK_ROW = (EINK_H + 7) // 8        # bytes in one of the panel's own lines (its short side: 122 pixels, a bit each)
EINK_FRAME = EINK_ROW * EINK_W      # ...and in a whole picture (250 of them)
EINK_SPI = OLED_SPI          # the Pi's SPI, where the HAT is (CE0)
EINK_DC, EINK_RST, EINK_BUSY, EINK_PWR = 25, 17, 24, 18   # its pins, as the Pi numbers them
EINK_HZ, EINK_MODE = 4000000, 0   # the SPI's clock, and its mode
SPI_MOST = 4096              # bytes in one write to the SPI, at most (the kernel's own limit)
GPIO_V2_LINE_GET_VALUES_IOCTL = 0xC010B40E   # linux/gpio.h: lines read (bits, mask: 8 bytes each)
GPIO_V2_LINE_FLAG_INPUT, GPIO_V2_LINE_FLAG_BIAS_PULL_DOWN = 1 << 2, 1 << 9
RESET_HIGH, RESET_LOW = 0.02, 0.002   # its reset: high this long, low this long, high again
PULSE_LOW = 0.001            # ...and before a partial refresh: low just this long
BUSY_LOOK = 0.01             # seconds between looks at BUSY, while it's waited for
BUSY_LIMIT = 20.0            # ...and how long it's waited for at most (a full refresh takes two or three)
SLEEP_WAIT = 2.0             # seconds asleep before its power's cut (as Waveshare's driver waits)
QUICK_WAIT = 0.2             # ...as Pietato goes: it can't wait long

# the panel's commands (an SSD1680's), as Waveshare's driver uses them
SW_RESET, DRIVER_OUTPUT, DEEP_SLEEP = 0x12, 0x01, 0x10
DATA_ENTRY, TEMP_SENSOR, DO_UPDATE = 0x11, 0x18, 0x20
UPDATE_1, UPDATE_2 = 0x21, 0x22
WRITE_NEW, WRITE_OLD = 0x24, 0x26   # a picture into its two memories: what's to show, and what a partial refresh
                                    # takes as there already
BORDER = 0x3C
RAM_X, RAM_Y, AT_X, AT_Y = 0x44, 0x45, 0x4E, 0x4F
FULL, PART = 0xF7, 0xFF      # how it refreshes (UPDATE_2's byte): whole, and in part

FULL_AFTER = 60              # partial refreshes before a full one (each leaves a little of what was there)...
NEW_PICTURE = 10             # ...a whole new picture counting as this many (Each in turn: a full one every few)
EINK_GAP = 3.0               # seconds between two refreshes, at least (what's picked in Settings: at once)
EINK_SETTLE = 0.8            # seconds a pick's waited on before it's drawn (the row's on its way past, to another)
OFF_SETTLE = 2.0             # ...and before it goes white and off (on its way past Off)
STALE = 24 * 3600.0          # a picture that hasn't changed for a day: refreshed all the same (good for the paper)
IDLE, LEAST = 2.0, 0.1       # seconds between looks at what it should show: at most, and at least
EINK_RETRY = 60.0            # seconds till it's tried again, when the panel didn't answer
NO_ANSWER = "It isn't answering"      # (BUSY stayed high: Settings says so on its row)
NO_WRITE = "It can't be written to"   # (the SPI or a pin gave an error)


# ---- the HAT's wires -----------------------------------------------------------------------------------------------
class PaperPins:
    """The HAT's pins: its D/C, reset and power as outputs (low to start with), and BUSY as an input, pulled down (as
    Waveshare's driver has it: read as it is, on a kernel that won't pull a pin): the kernel's GPIO lines, asked for
    as two lots. OSError: no such chip, or another program has them."""

    def __init__(self, dc=EINK_DC, rst=EINK_RST, pwr=EINK_PWR, busy=EINK_BUSY, chips=None):
        chip = pi_chip(chips, max(dc, rst, pwr, busy))
        try:
            self.fd = self.ask(chip, (dc, rst, pwr), GPIO_V2_LINE_FLAG_OUTPUT)   # (bit 0: D/C; 1: reset; 2: power)
            try:
                try:
                    self.busy_fd = self.ask(chip, (busy,), GPIO_V2_LINE_FLAG_INPUT | GPIO_V2_LINE_FLAG_BIAS_PULL_DOWN)
                except OSError as ex:
                    if ex.errno == errno.EBUSY:
                        raise
                    self.busy_fd = self.ask(chip, (busy,), GPIO_V2_LINE_FLAG_INPUT)
            except OSError:
                os.close(self.fd)
                raise
        finally:
            os.close(chip)

    @staticmethod
    def ask(chip, lines, flags):
        req = bytearray(LINE_REQUEST)
        struct.pack_into(f"{len(lines)}I", req, 0, *lines)
        struct.pack_into("31s", req, REQ_CONSUMER, b"pietato-eink")
        struct.pack_into("Q", req, REQ_FLAGS, flags)
        struct.pack_into("I", req, REQ_LINES, len(lines))
        fcntl.ioctl(chip, GPIO_V2_GET_LINE_IOCTL, req)
        return struct.unpack_from("i", req, REQ_FD)[0]

    def set(self, dc=None, rst=None, pwr=None):
        bits = mask = 0
        for k, level in enumerate((dc, rst, pwr)):
            if level is not None:
                mask |= 1 << k
                bits |= (1 if level else 0) << k
        fcntl.ioctl(self.fd, GPIO_V2_LINE_SET_VALUES_IOCTL, struct.pack("QQ", bits, mask))

    def busy(self):
        """The panel's at work (BUSY's high)."""
        got = bytearray(struct.pack("QQ", 0, 1))
        fcntl.ioctl(self.busy_fd, GPIO_V2_LINE_GET_VALUES_IOCTL, got)
        return bool(got[0] & 1)

    def close(self):
        for fd in (self.fd, self.busy_fd):
            try:
                os.close(fd)
            except OSError:
                pass


class PaperWires:
    """The HAT's wires: its SPI, and its pins. A command goes with D/C low, and what goes with it with D/C high: each
    of those bytes on its own, as Waveshare's driver sends them, and a picture all at once."""

    def __init__(self, spi, pins):
        self.spi, self.pins = spi, pins
        self.dc = None
        self.hurry = False                             # (it's being let go of: BUSY isn't waited for any more)

    def power(self, on):
        self.pins.set(pwr=on)

    def reset(self):
        for level, secs in ((1, RESET_HIGH), (0, RESET_LOW), (1, RESET_HIGH)):
            self.pins.set(rst=level)
            time.sleep(secs)

    def pulse(self):
        """Its reset low for a moment: before a partial refresh."""
        self.pins.set(rst=0)
        time.sleep(PULSE_LOW)
        self.pins.set(rst=1)

    def write(self, dc, data):
        if dc != self.dc:
            self.pins.set(dc=dc)
            self.dc = dc
        self.spi.write(bytes(data))

    def command(self, c, *data):
        self.write(0, (c,))
        for b in data:
            self.write(1, (b,))

    def lots(self, data):
        """A picture (what a command's just said is coming): in as few writes as the SPI takes."""
        for k in range(0, len(data), SPI_MOST):
            self.write(1, data[k:k + SPI_MOST])

    def wait(self, limit=BUSY_LIMIT):
        """Till the panel says it's done (BUSY low): True. False: it hasn't in limit seconds (or it's being let go
        of)."""
        end = time.monotonic() + limit
        while self.pins.busy():
            if self.hurry or time.monotonic() >= end:
                return False
            time.sleep(BUSY_LOOK)
        return True

    def close(self):
        """Its reset, D/C and power low (its power cut), and all of it let go of."""
        try:
            self.pins.set(dc=0, rst=0, pwr=0)
        except OSError:
            pass
        self.spi.close()
        self.pins.close()


def paper_wires(spi=EINK_SPI):
    """The HAT's wires, on this Pi. OSError: no SPI, no pins, or another program has them."""
    s = Spi(spi, EINK_HZ, EINK_MODE)
    try:
        return PaperWires(s, PaperPins())
    except OSError:
        s.close()
        raise


# ---- the panel -----------------------------------------------------------------------------------------------------
def packed(img, flip=False):
    """A picture (EINK_W by EINK_H; black where it's 0) as the panel takes it: EINK_FRAME bytes, a bit a pixel (1:
    white), turned to the panel's own way round (its lines run down the picture), as Waveshare's driver packs one.
    flip: upside down."""
    im = img.convert("1")
    if flip:
        im = im.rotate(180)
    return im.rotate(90, expand=True).tobytes("raw")


class Paper:
    """The panel, told what Waveshare's driver tells it: started, a whole picture (full), what's changed (partial),
    white (clear), asleep (sleep). answered: it said it was done each time it was waited for (set True before a
    refresh, to see)."""

    def __init__(self, wires):
        self.wires = wires
        self.answered = True
        wires.power(1)

    def wait(self):
        if self.answered and not self.wires.wait():    # (once it hasn't answered: not waited for again this time)
            self.answered = False

    def window(self):
        """The whole of its memory, written from its first corner."""
        c = self.wires.command
        c(RAM_X, 0x00, (EINK_H - 1) >> 3)
        c(RAM_Y, 0x00, 0x00, (EINK_W - 1) & 0xFF, (EINK_W - 1) >> 8)
        c(AT_X, 0x00)
        c(AT_Y, 0x00, 0x00)

    def start(self):
        w = self.wires
        w.reset()
        self.wait()
        w.command(SW_RESET)
        self.wait()
        w.command(DRIVER_OUTPUT, 0xF9, 0x00, 0x00)
        w.command(DATA_ENTRY, 0x03)
        self.window()
        w.command(BORDER, 0x05)
        w.command(UPDATE_1, 0x00, 0x80)
        w.command(TEMP_SENSOR, 0x80)
        self.wait()

    def refresh(self, how):
        self.wires.command(UPDATE_2, how)
        self.wires.command(DO_UPDATE)
        self.wait()

    def full(self, buf):
        """A whole picture, drawn afresh (it flashes), and kept as what partial refreshes start from."""
        w = self.wires
        self.start()
        w.command(WRITE_NEW)
        w.lots(buf)
        w.command(WRITE_OLD)
        w.lots(buf)
        self.refresh(FULL)

    def partial(self, buf):
        """A picture, only what's changed of it drawn (no flash)."""
        w = self.wires
        w.pulse()
        w.command(BORDER, 0x80)
        w.command(DRIVER_OUTPUT, 0xF9, 0x00, 0x00)
        w.command(DATA_ENTRY, 0x03)
        self.window()
        w.command(WRITE_NEW)
        w.lots(buf)
        self.refresh(PART)

    def clear(self):
        """White all over."""
        self.start()
        self.wires.command(WRITE_NEW)
        self.wires.lots(b"\xff" * EINK_FRAME)
        self.refresh(FULL)

    def sleep(self):
        self.wires.command(DEEP_SLEEP, 0x01)

    def shut(self):
        self.wires.close()


class PaperShow:
    """The paper shown what it should show, on a thread of its own. picture(now): (the picture, seconds till it's
    asked again, what kind of picture it is), or None (nothing to show: it's left as it is). Drawn only when it's
    changed: in part, or whole (see the top of this file). note: what's wrong with it ("" when nothing is)."""

    def __init__(self, paper, picture, flip=False, clock=time.monotonic, run=True):
        self.paper, self.picture_of, self.flip, self.clock = paper, picture, flip, clock
        self.shown, self.kind = None, None             # what's on the paper (as its bytes; None: not known)
        self.asked, self.heeded = 1, 0                 # full refreshes asked for (just turned on, or just picked),
        self.turned = None                             # and done; upside down or not, picked and not yet taken
        self.worn = 0                                  # partial refreshes since the last full one
        self.drawn_at = -1e9                           # when it was last refreshed
        self.settle = -1e9                             # nothing's drawn till then (a pick, a moment ago)
        self.fulls = self.parts = 0                    # (how many of each it's done)
        self.note = ""
        self.again = LEAST
        self.off_at = None                             # when it's to go white and off (None: it isn't)
        self.blank, self.quick = True, False           # ...white first; and with no long wait (Pietato's going)
        self.final = False                             # ...and for good (close: on doesn't undo it)
        self.closed = False
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True, name="eink") if run else None
        if run:
            self.thread.start()

    # -- told what's wanted (any thread) -----------------------------------------------------------------------------
    @property
    def fresh(self):
        """A full refresh is due next (asked for, and not done yet)."""
        return self.asked != self.heeded

    def poke(self, fresh=False, settle=0.0):
        """What it shows may have changed: looked at now. fresh: with a full refresh. settle: after this long."""
        if fresh:
            self.asked += 1
        if settle:
            self.settle = self.clock() + settle
        self.wake.set()

    def turn(self, flip, settle=0.0):
        """Upside down or not, picked: taken before it's next drawn (never part-way through a refresh), and drawn
        whole."""
        self.turned = bool(flip)
        self.poke(fresh=True, settle=settle)

    def off(self, after=None):
        """White and off, after a moment (OFF_SETTLE, unless it's said), unless it's wanted again by then (on)."""
        with self.lock:
            if not self.closed and self.off_at is None:
                self.off_at = self.clock() + (OFF_SETTLE if after is None else after)
                self.blank, self.quick = True, False
        self.wake.set()

    def on(self):
        """Wanted after all: True, and it carries on (with a full refresh). False: it's off and let go of."""
        with self.lock:
            if self.closed or self.final:
                return False
            self.off_at = None
        self.poke(fresh=True, settle=EINK_SETTLE)
        return True

    def going(self):
        """It's on its way off (or off)."""
        return self.closed or self.off_at is not None

    def close(self, clear=True, wait=None):
        """Off now: white first, asleep, and let go of (Pietato's going). Not clear: let go of at once, as it is
        (another HAT's to have its pins). wait: seconds it's waited for."""
        with self.lock:
            self.final = True
            if not self.closed:
                self.off_at, self.blank, self.quick = -1e9, bool(clear), True
        if not clear:
            self.paper.wires.hurry = True              # (whatever it's waiting on the panel for: given up)
        self.wake.set()
        t = self.thread
        if t is None:
            self.leave()                               # (the tests: no thread of its own)
        elif wait and t is not threading.current_thread():
            t.join(wait)

    # -- its thread --------------------------------------------------------------------------------------------------
    def step(self, now):
        """What it should show now: drawn if it's changed (True), in part or whole."""
        if now < self.settle:
            self.again = max(LEAST, self.settle - now)
            return False
        got = self.picture_of(now) if self.picture_of is not None else None
        if got is None:
            self.again = IDLE
            return False
        img, wait, kind = got
        self.again = max(LEAST, min(IDLE, IDLE if wait is None else wait))
        p, asked = self.paper, self.asked              # (asked for again while this one's drawn: done after it)
        turned, self.turned = self.turned, None
        if turned is not None:
            self.flip = turned
        fresh = asked != self.heeded
        buf = packed(img, self.flip)
        same = buf == self.shown
        if same and not fresh and now - self.drawn_at < STALE:
            return False
        if not fresh and self.shown is not None and now - self.drawn_at < EINK_GAP:
            self.again = max(LEAST, min(self.again, EINK_GAP - (now - self.drawn_at)))
            return False
        cost = 1 if kind == self.kind else NEW_PICTURE
        full = fresh or self.shown is None or same or self.worn + cost > FULL_AFTER
        p.answered = True
        try:
            (p.full if full else p.partial)(buf)
        except OSError:
            self.shown, self.note, self.again = None, NO_WRITE, EINK_RETRY
            raise
        self.fulls, self.parts = self.fulls + full, self.parts + (not full)
        self.worn = 0 if full else self.worn + cost
        self.shown, self.kind, self.heeded, self.drawn_at = buf, kind, asked, now
        self.note = "" if p.answered else NO_ANSWER
        if not p.answered:                             # (BUSY never went low: nothing's known of what's on it)
            self.shown, self.again = None, EINK_RETRY
        return True

    def leave(self):
        """White (unless it's let go of as it is), asleep, and let go of: True. False: wanted again before it was let
        go of (it carries on)."""
        if self.closed:
            return True
        blank = self.blank
        try:
            if blank:
                self.paper.answered = True
                self.paper.clear()
            self.paper.sleep()
        except OSError as ex:
            print(f"eink: going off: {ex}", flush=True)
        self.shown = None                              # (white, or not known: drawn whole, if it carries on)
        began = self.clock()
        while True:
            with self.lock:
                if self.off_at is None:
                    return False
                left = began + (0.0 if not blank else QUICK_WAIT if self.quick else SLEEP_WAIT) - self.clock()
                if left <= 0 or self.thread is None:
                    self.closed = True
                    break
            time.sleep(min(left, 0.05))
        self.paper.shut()
        return True

    def run(self):
        while not self.closed:
            self.wake.clear()                          # (woken from here on: seen at its next wait, not lost)
            now = self.clock()
            off = self.off_at
            if off is not None and now >= off:
                if self.leave():
                    print("eink: the e-ink's off", flush=True)
                    return
                continue
            try:
                self.step(now)
            except Exception as ex:                    # (the SPI gone wrong, say: tried again in a while; never
                print(f"eink: the paper: {ex!r}", flush=True)   # its thread's end)
                self.again = EINK_RETRY
            wait = self.again
            off = self.off_at
            if off is not None:
                wait = max(0.0, min(wait, off - self.clock()))
            self.wake.wait(wait)


# ---- its pictures --------------------------------------------------------------------------------------------------
_INK = {}
WX_BIG = 4                   # a weather picture's drawn this many times as big, then made small
FACE_BIG = 4                 # ...and the face
FACE_T = 0.05                # the moment of the face that's drawn (its eyes open, looking ahead)
FACE_INK = 145               # black where the face is at least this dark (of 255): the glint in its eye left white
PAD = 8                      # the pictures' margin


def sheet():
    """A blank picture: white paper."""
    return Image.new("1", (EINK_W, EINK_H), 1)


def kept(key, make):
    """A picture drawn once and kept (a few hundred at most)."""
    if key not in _INK:
        if len(_INK) > 300:
            _INK.clear()
        _INK[key] = make()
    return _INK[key]


def fit_font(d, text, path, sizes, room):
    """The biggest of these sizes that text fits room in (the last, if none does)."""
    font = None
    for size in sizes:
        font = oled_font(path, size)
        if d.textlength(text, font=font) <= room:
            break
    return font


def fit_text(d, text, font, room):
    """Text cut to fit room, with … where it's cut."""
    if d.textlength(text, font=font) <= room:
        return text
    while text and d.textlength(text.rstrip() + "…", font=font) > room:
        text = text[:-1]
    return text.rstrip() + "…" if text else ""


def paste_ink(img, pic, at):
    """A black-on-white picture put on the sheet: its black, over what's there (its white leaves that as it is)."""
    img.paste(0, (int(round(at[0])), int(round(at[1]))), pic.point(lambda v: 0 if v else 255))


def ink_wx(name, size):
    """A weather picture for paper (weather.py's shapes): black, with a white edge round what's in front of
    something."""
    def make():
        big = size * WX_BIG
        k = big / 120
        im = Image.new("L", (big, big), 255)
        d = ImageDraw.Draw(im)
        edge = 5                                       # (the white round what's in front: of the picture's 120)

        def box(x0, y0, x1, y1, grow=0.0):
            return ((x0 - grow) * k, (y0 - grow) * k, (x1 + grow) * k, (y1 + grow) * k)

        def pts(*at):
            return [(x * k, y * k) for x, y in at]

        def sun(cx, cy, r):
            for t in range(8):
                a = math.radians(t * 45)
                d.line(pts((cx + math.cos(a) * r * 1.4, cy + math.sin(a) * r * 1.4),
                           (cx + math.cos(a) * r * 1.85, cy + math.sin(a) * r * 1.85)), fill=0,
                       width=max(1, int(r * 0.26 * k)))
            d.ellipse(box(cx - r, cy - r, cx + r, cy + r), fill=0)

        def moon(cx, cy, r):
            d.ellipse(box(cx - r, cy - r, cx + r, cy + r), fill=0)
            d.ellipse(box(cx - r * 0.35, cy - r * 1.15, cx + r * 1.45, cy + r * 0.65), fill=255)

        def cloud(x, y, w, grow=0.0, fill=0):
            h = w * 0.5
            d.ellipse(box(x + w * 0.08, y + h * 0.35, x + w * 0.48, y + h * 1.0, grow), fill=fill)
            d.ellipse(box(x + w * 0.26, y, x + w * 0.74, y + h * 0.95, grow), fill=fill)
            d.ellipse(box(x + w * 0.56, y + h * 0.28, x + w * 0.94, y + h * 1.0, grow), fill=fill)
            d.rounded_rectangle(box(x, y + h * 0.55, x + w, y + h * 1.12, grow), radius=(h * 0.28 + grow) * k,
                                fill=fill)

        def front_cloud(x, y, w):
            cloud(x, y, w, edge, 255)
            cloud(x, y, w)

        if name == "sun":
            sun(60, 60, 26)
        elif name == "moon":
            moon(58, 60, 34)
        elif name == "partly_day":
            sun(78, 40, 18)
            front_cloud(8, 48, 86)
        elif name == "partly_night":
            moon(80, 38, 22)
            front_cloud(8, 48, 86)
        elif name == "overcast":
            cloud(36, 18, 74)
            front_cloud(6, 44, 90)
        elif name == "fog":
            for i, (x0, x1) in enumerate(((18, 102), (8, 92), (24, 108), (14, 84))):
                d.rounded_rectangle(box(x0, 30 + i * 17, x1, 39 + i * 17), radius=4.5 * k, fill=0)
        else:                                          # rain, heavyrain, snow, storm (and anything else: a cloud)
            cloud(10, 12, 100)
            if name == "storm":
                bolt = ((62, 62), (42, 94), (58, 94), (50, 118), (80, 82), (64, 82), (74, 62))
                d.line(pts(*bolt, *bolt[:2]), fill=255, width=int(2 * edge * k), joint="curve")   # (all the way
                #                                                                    round: its first corner too)
                d.polygon(pts(*bolt), fill=0)
            elif name == "snow":
                for x, y in ((34, 86), (60, 98), (86, 86), (46, 110), (74, 110)):
                    d.ellipse(box(x - 5.5, y - 5.5, x + 5.5, y + 5.5), fill=0)
            elif name in ("rain", "heavyrain"):
                for x in ((30, 52, 74, 96) if name == "heavyrain" else (38, 62, 86)):
                    d.line(pts((x, 78), (x - 8, 104)), fill=0, width=int(7 * k))
        return im.resize((size, size), Image.BOX).point(lambda v: 255 if v >= 128 else 0).convert("1")
    return kept(("wx", name, size), make)


def ink_reach(look, shape=None, lashes=False):
    """How far the face reaches from its middle, of its size: (left, up, right, down). Found by drawing it once."""
    def make():
        n = 200
        im = Image.new("RGB", (4 * n, 4 * n), (255, 255, 255))
        draw_face(ImageDraw.Draw(im), 2 * n, 2 * n, n, look, FACE_T, (0, 0, 0), (255, 255, 255),
                  font=oled_font(FONT_BOLD, round(n * 0.2)), lashes=lashes, shape=shape, lead=(0, 0, 1))
        b = im.convert("L").point(lambda v: 255 if v < FACE_INK else 0).getbbox() or (n, n, 3 * n, 3 * n)
        return (2 * n - b[0]) / n, (2 * n - b[1]) / n, (b[2] - 2 * n) / n, (b[3] - 2 * n) / n
    return kept(("reach", look, tuple(sorted((shape or {}).items())), bool(lashes)), make)


def ink_face(size, look="idle", shape=None, lashes=False):
    """The Bot's face (face.py's, the shape its Character gives it), as big as fits in size (across, down), in its
    middle: black on white, looking straight ahead."""
    def make():
        w, h = size
        left, up, right, down = ink_reach(look, shape, lashes)
        big = min(w / (left + right), h / (up + down))
        s = FACE_BIG
        im = Image.new("RGB", (w * s, h * s), (255, 255, 255))
        cx = (w - (left + right) * big) / 2 + left * big
        cy = (h - (up + down) * big) / 2 + up * big
        draw_face(ImageDraw.Draw(im), cx * s, cy * s, big * s, look, FACE_T, (0, 0, 0), (255, 255, 255),
                  font=oled_font(FONT_BOLD, max(6, round(big * s * 0.2))), lashes=lashes, shape=shape,
                  lead=(0, 0, 1))
        return im.convert("L").resize((w, h), Image.BOX).point(lambda v: 255 if v >= FACE_INK else 0).convert("1")
    return kept(("face", tuple(size), look, tuple(sorted((shape or {}).items())), bool(lashes)), make)


def arrow(d, x, y, up, size=7):
    """A little arrow, up or down, its top left at x, y."""
    d.polygon([(x, y + size), (x + size, y + size), (x + size / 2, y)] if up
              else [(x, y), (x + size, y), (x + size / 2, y + size)], fill=0)


def quaver(d, x, y):
    """A little note (a song's playing), its top left at x, y."""
    d.ellipse((x, y + 8, x + 5, y + 12), fill=0)
    d.rectangle((x + 4, y, x + 5, y + 10), fill=0)
    d.polygon([(x + 5, y), (x + 9, y + 3), (x + 9, y + 6), (x + 5, y + 3)], fill=0)


def time_in(d, clock, ampm, box, sizes):
    """The time as big as fits in a box (of these sizes), its AM or PM small after it: in the box's middle."""
    x0, y0, x1, y1 = box
    small = oled_font(FONT_BOLD, 14 if sizes[0] < 70 else 16)
    aw = d.textlength(ampm, font=small) + 4 if ampm else 0
    big = fit_font(d, clock, FONT_UI_BOLD, sizes, x1 - x0 - aw)
    tw = d.textlength(clock, font=big)
    top, bottom = d.textbbox((0, 0), "0123456789", font=big, anchor="ls")[1::2]
    x = x0 + (x1 - x0 - tw - aw) / 2
    base = y0 + (y1 - y0 - (bottom - top)) / 2 - top
    d.text((x, base), clock, font=big, fill=0, anchor="ls")
    if ampm:
        d.text((x + tw + 4, base), ampm, font=small, fill=0, anchor="ls")


def ink_time(clock, ampm="", date=""):
    """Time: the time, as big as fits, and the date under it."""
    img = sheet()
    d = ImageDraw.Draw(img)
    time_in(d, clock, ampm, (PAD, 6, EINK_W - PAD, 92 if date else EINK_H - 6), range(92, 40, -2))
    if date:
        d.text((EINK_W / 2, 96), fit_text(d, date, oled_font(FONT, 16), EINK_W - 2 * PAD), font=oled_font(FONT, 16),
               fill=0, anchor="ma")
    return img


def ink_weather(temp, words, icon, high="", low="", days=()):
    """Weather: its picture, how warm, its words, and today's high and low; the next days along the bottom (days:
    [(its name, its picture's name, its high, its low)], three at most)."""
    img = sheet()
    d = ImageDraw.Draw(img)
    days = list(days)[:3]
    strip = 40 if days else 0
    top = EINK_H - strip
    pic = ink_wx(icon, 60 if days else 76)
    big, sf = oled_font(FONT_UI_BOLD, 44 if days else 56), oled_font(FONT, 13)
    room = EINK_W - 2 * PAD - pic.width - 14
    wf = fit_font(d, words, FONT_BOLD, (14, 13, 12), room)
    words = fit_text(d, words, wf, room)
    hl = "  ".join(x for x in (f"High {high}" if high else "", f"Low {low}" if low else "") if x)
    tw = max(d.textlength(temp, font=big), d.textlength(words, font=wf), d.textlength(hl, font=sf))
    x = (EINK_W - (pic.width + 14 + tw)) / 2
    paste_ink(img, pic, (x, (top - pic.height) / 2))
    x += pic.width + 14
    num = d.textbbox((0, 0), "0123456789°", font=big, anchor="ls")
    y = (top - (-num[1] + 5 + 14 + ((3 + 13) if hl else 0))) / 2
    d.text((x, y - num[1]), temp, font=big, fill=0, anchor="ls")
    y += -num[1] + 5
    d.text((x + 1, y), words, font=wf, fill=0, anchor="la")
    if hl:
        d.text((x + 1, y + 14 + 3), hl, font=sf, fill=0, anchor="la")
    if days:
        d.line((PAD, top, EINK_W - PAD, top), fill=0)
        col = (EINK_W - 2 * PAD) / len(days)
        df, tf = oled_font(FONT_BOLD, 12), oled_font(FONT, 12)
        for k, (day, dicon, dhi, dlo) in enumerate(days):
            small = ink_wx(dicon, 20)
            mid = PAD + col * k + col / 2
            w = d.textlength(day, font=df) + 5 + small.width
            d.text((mid - w / 2, top + 13), day, font=df, fill=0, anchor="lm")
            paste_ink(img, small, (mid + w / 2 - small.width, top + 13 - small.height / 2 - 1))
            d.text((mid, top + 30), f"{dhi} {dlo}".strip(), font=tf, fill=0, anchor="mm")
    return img


PRICE_ROWS = 4               # prices on the paper at once, at most


def ink_prices(prices):
    """Prices: your stocks' and coins', PRICE_ROWS at most: each one's ticker, its price, and how far it's moved
    today (an arrow up or down, and by how much)."""
    img = sheet()
    d = ImageDraw.Draw(img)
    prices = list(prices)[:PRICE_ROWS]
    n = max(1, len(prices))
    row = min(40, (EINK_H - 6) / n)
    size = {1: 26, 2: 24, 3: 20}.get(n, 17)
    cf = oled_font(FONT, 12)
    top = (EINK_H - row * n) / 2
    cw = max([d.textlength(f"{abs(c):.2f}%", font=cf) + 11 for _, _, c in prices if c is not None] or [0])
    for k, (symbol, price, change) in enumerate(prices):
        mid = top + row * k + row / 2
        if k:
            d.line((10, top + row * k, EINK_W - 10, top + row * k), fill=0)
        right = EINK_W - 10 - (cw + 8 if cw else 0)
        pf = fit_font(d, price, FONT_UI_BOLD, range(size + 2, 11, -1), right - 10 - 44)
        d.text((right, mid), price, font=pf, fill=0, anchor="rm")
        room = right - d.textlength(price, font=pf) - 10 - 10
        sf = fit_font(d, symbol, FONT_BOLD, range(size - 2, 10, -1), room)
        d.text((10, mid), fit_text(d, symbol, sf, room), font=sf, fill=0, anchor="lm")
        if change is not None:
            x = EINK_W - 10 - cw
            arrow(d, x, mid - 4, change >= 0)
            d.text((x + 11, mid), f"{abs(change):.2f}%", font=cf, fill=0, anchor="lm")
    return img


def ink_face_page(look="idle", shape=None, lashes=False):
    """Face: the Bot's face, as big as fits."""
    img = sheet()
    paste_ink(img, ink_face((EINK_W - 32, EINK_H - 16), look, shape, lashes), (16, 8))
    return img


def ink_all(clock, ampm="", date="", wx=None, face=None, foot=None):
    """Everything: the date and the weather now along the top, the Bot's face and the time in the middle, and a line
    along the bottom. wx: (how warm, its picture's name). face: (its look, its shape, whether it has eyelashes).
    foot: ("song", its name), ("prices", [(ticker, price, moved)]: two with an arrow each when they fit, else the
    first with how far it's moved), or ("words", some); None for no line."""
    img = sheet()
    d = ImageDraw.Draw(img)
    hf, ff = oled_font(FONT_BOLD, 14), oled_font(FONT, 14)
    right = EINK_W - PAD
    if wx:
        tw = d.textlength(wx[0], font=hf)
        d.text((right, 13), wx[0], font=hf, fill=0, anchor="rm")
        pic = ink_wx(wx[1], 22)
        right -= tw + 5 + pic.width
        paste_ink(img, pic, (right, 13 - pic.height / 2 - 1))
        right -= 8
    d.text((PAD, 13), fit_text(d, date, hf, right - PAD), font=hf, fill=0, anchor="lm")
    foot_h = 26 if foot else 0
    y0, y1 = 26, EINK_H - foot_h - (2 if foot else 6)
    x0 = PAD
    if face:
        size = (58, y1 - y0 - 8)
        paste_ink(img, ink_face(size, *face), (PAD, y0 + 4))
        x0 = PAD + size[0] + 12
    time_in(d, clock, ampm, (x0, y0, EINK_W - PAD, y1), range(64, 30, -2))
    if not foot:
        return img
    d.line((PAD, EINK_H - foot_h, EINK_W - PAD, EINK_H - foot_h), fill=0)
    mid = EINK_H - foot_h / 2 + 1
    kind, what = foot
    if kind == "song":
        quaver(d, PAD + 1, mid - 7)
        d.text((PAD + 15, mid), fit_text(d, what, ff, EINK_W - 2 * PAD - 15), font=ff, fill=0, anchor="lm")
    elif kind == "prices":
        bf, cf = oled_font(FONT_BOLD, 13), oled_font(FONT, 12)

        def wide(symbol, price, change):
            return d.textlength(symbol, font=bf) + 5 + d.textlength(price, font=ff) + (12 if change is not None else 0)

        def one(x, symbol, price, change, far):
            d.text((x, mid), symbol, font=bf, fill=0, anchor="lm")
            x += d.textlength(symbol, font=bf) + 5
            d.text((x, mid), price, font=ff, fill=0, anchor="lm")
            x += d.textlength(price, font=ff)
            if change is not None:
                arrow(d, x + 5, mid - 4, change >= 0)
                if far:
                    d.text((x + 15, mid), f"{abs(change):.2f}%", font=cf, fill=0, anchor="lm")

        if len(what) >= 2 and wide(*what[0]) + 16 + wide(*what[1]) <= EINK_W - 2 * PAD:
            one(PAD, *what[0], False)
            one(EINK_W - PAD - 1 - wide(*what[1]), *what[1], False)
        elif what:
            symbol, price, change = what[0]
            room = EINK_W - 2 * PAD - d.textlength(price, font=ff) - 5 - (
                15 + d.textlength(f"{abs(change):.2f}%", font=cf) if change is not None else 0)
            one(PAD, fit_text(d, symbol, bf, room), price, change, True)
    else:
        d.text((PAD, mid), fit_text(d, what, ff, EINK_W - 2 * PAD), font=ff, fill=0, anchor="lm")
    return img
