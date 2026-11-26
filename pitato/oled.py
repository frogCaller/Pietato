"""A Waveshare 2.23inch OLED HAT on the Pi's pins (128x32, an SSD1305): bars that move with the music, as it's heard.
The HAT's own wiring: the Pi's SPI (its MOSI, clock and CE0: GPIO 10, 11 and 8), its D/C on GPIO 24 and its reset
on GPIO 25. The SPI is written to as it is (/dev/spidev0.0), and the two pins are the kernel's own GPIO lines
(/dev/gpiochipN), so nothing needs installing. What goes to the screen is what Waveshare's own driver sends: the same
start-up, then each of its four rows of 128 bytes with where it starts before it (only the rows that changed).
The bars are the sound itself, a moment of it at a time: the sound heard now (party.py's player says when each bit
of a song is heard), cut into BARS pieces, a bar as tall as its piece is loud. A bar jumps up and falls back
slowly, FPS times a second. screens/oled.py has its setting (Settings > Screen > Waveshare 2.23 OLED: only on a Pi
with its pins free); as it's turned on there, the bars come up a little once, so you can tell it's lit.
Another of your Pietatos' music too, while this Pi plays none of its own: the one playing sends its bars as they're
heard there (BarsOut: a UDP packet each, FPS times a second), and the one with the OLED takes them from your Pietatos
only (BarsIn), whichever's playing, and shows them as they come.
With no music for a while, it isn't left dark: it shows the time, the weather or a smiley face (what screens/oled.py's
oled_quiet gives it: Settings > Screen > OLED with no music), dimmer than the bars, and moved a little every minute (an
OLED left showing the same picture for hours wears it in)."""
import errno
import fcntl
import glob
import math
import os
import socket
import struct
import threading
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .theme import FONT, FONT_BOLD, FONT_UI_BOLD
from .weather import draw_wx

OLED_W, OLED_H = 128, 32
PAGES = OLED_H // 8          # its rows of bytes: each byte 8 pixels, one above the other (the top one its lowest bit)
OLED_SPI = "/dev/spidev0.0"  # the Pi's SPI, where the HAT is (CE0)
OLED_DC, OLED_RST = 24, 25   # its D/C (low: a command; high: the picture) and its reset, as the Pi numbers its pins
OLED_HZ = 1000000            # the SPI's clock
OLED_MODE = 3                # ...and its mode (the clock high when idle, read as it rises)
INIT = (0xAE,                # the screen off, while it's set up
        0x04, 0x10,          # where a row starts: its 128 columns are the chip's 4 to 131
        0x40,                # the picture's first line at the top
        0x81, 0x80,          # how bright
        0xA1,                # which way round, across
        0xA6,                # lit where a bit's 1
        0xA8, 0x1F,          # 32 lines
        0xC8,                # which way round, down
        0xD3, 0x00,          # no offset
        0xD5, 0xF0,          # its clock
        0xD8, 0x05,          # one colour, saving power
        0xD9, 0xC2,          # how long its pixels are charged
        0xDA, 0x12,          # how its lines are wired
        0xDB, 0x08,          # how hard they're driven
        0xAF)                # ...and on
COLUMN = (0x04, 0x10)        # a row from its first column (after 0xB0 + the row)
SCREEN_OFF = 0xAE
CONTRAST = 0x81              # how bright, from the next byte (INIT's: BRIGHT)
BRIGHT, DIM = 0x80, 0x40     # ...its bars, and its quiet picture (shown for hours: gentler on it, and on you at night)
RESET_WAIT = 0.1             # seconds its reset is held each way

SPI_IOC_WR_MODE, SPI_IOC_WR_BITS_PER_WORD, SPI_IOC_WR_MAX_SPEED_HZ = 0x40016B01, 0x40016B03, 0x40046B04
GPIO_GET_CHIPINFO_IOCTL = 0x8044B401         # linux/gpio.h: a chip's name, label and how many lines (68 bytes)
GPIO_V2_GET_LINE_IOCTL = 0xC250B407          # ...lines asked for (a gpio_v2_line_request: 592 bytes)
GPIO_V2_LINE_SET_VALUES_IOCTL = 0xC010B40F   # ...and set (bits, mask: 8 bytes each)
GPIO_V2_LINE_FLAG_OUTPUT = 1 << 3
CHIP_INFO, LINE_REQUEST = 68, 592
REQ_CONSUMER, REQ_FLAGS, REQ_LINES, REQ_FD = 256, 288, 560, 588   # where each part of a request is
PI_CHIPS = ("pinctrl-bcm2835", "pinctrl-bcm2711", "pinctrl-rp1")  # the chip a Pi's own pins are on (a Pi 5's: RP1)

BARS = 25                    # bars across
BAR_W, BAR_GAP = 4, 1        # a bar's width, and the dark between two
BARS_LEFT = (OLED_W - (BARS * (BAR_W + BAR_GAP) - BAR_GAP)) // 2   # ...in the middle of the screen
BAR_SECS = 0.0011            # the sound behind one bar (seconds): 25 of them, a 36th of a second
GAIN = 1.5                   # a bar's height: how loud its piece is, by this (of the screen's)
DECAY = 0.85                 # what a bar keeps each frame as it falls
FLOOR = 1e-4                 # ...down to nothing
FPS = 25.0
FRAME = 1.0 / FPS
RATE = 48000                 # samples a second, as party.py's player plays them
KEPT = 1.0                   # seconds of sound kept (what's fed is heard a moment later)
JUMP = 0.05                  # seconds out: what's fed isn't the next of it (a seek, a new player)
QUIET_GAIN = 0.01            # the volume, at least, that what's fed is made up for
IDLE_AFTER, IDLE_EVERY = 1.0, 0.25   # nothing fed and its bars down: looked at only now and then
HELLO = 0.25                 # its bars as it's turned on: up this far once, and down again (so you can tell it's lit)
QUIET_AFTER = 4.0            # seconds with no music (nothing fed, its bars down) before its quiet picture: not
                             # between two songs
DRIFT_SECS = 60.0            # its quiet picture moves a little this often...
DRIFT_TIME, DRIFT_WX, DRIFT_FACE = (6, 2), (3, 1), (40, 1)   # ...this far each way at most (across, down): the
                             # time, the weather, the face (narrow: it goes further)
OLED_PORT = 5445             # another of yours' music, as bars, is taken here (UDP)
BARS_MAGIC, BARS_VERSION = b"PO", 1
BARS_HEAD = struct.Struct(">2sBd")   # ...a packet: magic, version, when it was sent (the sender's clock), then a
                                     # byte for each bar (how loud its piece of the sound heard there now is)
THEIRS_KEPT = 0.3            # seconds another's bars are shown after its last packet (it's stopped, or gone)
OWN_FIRST = 1.0              # seconds after this Pi's own sound that another's bars aren't shown (its own come first)
HOLD = 2.5                   # seconds the one that's followed is kept to, once it's quiet, before another's taken
QUIET_SAID = 5               # (BarsOut) packets that say there's no sound, before it says no more


# ---- the HAT's wires -----------------------------------------------------------------------------------------------
def pi_chip(paths=None, lines=max(OLED_DC, OLED_RST)):
    """The GPIO chip a Pi's own pins are on, open (its label says so, whatever its number: a Pi 5's has been
    gpiochip4 and gpiochip0). OSError when there's none."""
    seen = []
    for path in sorted(glob.glob("/dev/gpiochip*")) if paths is None else paths:
        try:
            fd = os.open(path, os.O_RDWR | os.O_CLOEXEC)
        except OSError:
            continue
        info = bytearray(CHIP_INFO)
        try:
            fcntl.ioctl(fd, GPIO_GET_CHIPINFO_IOCTL, info)
        except OSError:
            os.close(fd)
            continue
        label = bytes(info[32:64]).split(b"\0")[0].decode("ascii", "replace")
        if label in PI_CHIPS and struct.unpack_from("I", info, 64)[0] > lines:
            return fd
        seen.append(label)
        os.close(fd)
    raise OSError(errno.ENODEV, f"No GPIO chip for the Pi's pins (found: {', '.join(seen) or 'none'})")


class Pins:
    """The HAT's D/C and reset pins, as outputs (low to start with): two of the kernel's GPIO lines, asked for
    together. OSError: no such chip, or another program has them."""

    def __init__(self, dc=OLED_DC, rst=OLED_RST, chips=None):
        chip = pi_chip(chips, max(dc, rst))
        req = bytearray(LINE_REQUEST)
        struct.pack_into("2I", req, 0, dc, rst)                      # (bit 0: D/C; bit 1: reset)
        struct.pack_into("31s", req, REQ_CONSUMER, b"pietato-oled")
        struct.pack_into("Q", req, REQ_FLAGS, GPIO_V2_LINE_FLAG_OUTPUT)
        struct.pack_into("I", req, REQ_LINES, 2)
        try:
            fcntl.ioctl(chip, GPIO_V2_GET_LINE_IOCTL, req)
        finally:
            os.close(chip)
        self.fd = struct.unpack_from("i", req, REQ_FD)[0]

    def set(self, dc=None, rst=None):
        bits = (1 if dc else 0) | (2 if rst else 0)
        mask = (0 if dc is None else 1) | (0 if rst is None else 2)
        fcntl.ioctl(self.fd, GPIO_V2_LINE_SET_VALUES_IOCTL, struct.pack("QQ", bits, mask))

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass


class Spi:
    """The Pi's SPI, written to."""

    def __init__(self, path=OLED_SPI, hz=OLED_HZ, mode=OLED_MODE):
        self.fd = os.open(path, os.O_WRONLY)
        for req, value in ((SPI_IOC_WR_MODE, struct.pack("B", mode)), (SPI_IOC_WR_BITS_PER_WORD, struct.pack("B", 8)),
                           (SPI_IOC_WR_MAX_SPEED_HZ, struct.pack("I", hz))):
            try:
                fcntl.ioctl(self.fd, req, value)
            except OSError as ex:                      # (a plain file, as the tests have it: just written to)
                if ex.errno != errno.ENOTTY:
                    os.close(self.fd)
                    raise

    def write(self, data):
        os.write(self.fd, data)

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass


class Wires:
    """The HAT's wires: its SPI, and its two pins. What's written is a command (D/C low) or the picture (high)."""

    def __init__(self, spi, pins):
        self.spi, self.pins = spi, pins
        self.dc = None

    def reset(self):
        for level in (1, 0, 1):
            self.pins.set(rst=level)
            time.sleep(RESET_WAIT)

    def write(self, dc, data):
        if dc != self.dc:
            self.pins.set(dc=dc)
            self.dc = dc
        self.spi.write(bytes(data))

    def command(self, data):
        self.write(0, data)

    def data(self, data):
        self.write(1, data)

    def close(self):
        self.spi.close()
        self.pins.close()


def wires(spi=OLED_SPI):
    """The HAT's wires, on this Pi. OSError: no SPI, no pins, or another program has them."""
    s = Spi(spi)
    try:
        return Wires(s, Pins())
    except OSError:
        s.close()
        raise


# ---- the screen ---------------------------------------------------------------------------------------------------
BLANK = (bytes(OLED_W),) * PAGES


class Screen:
    """The OLED: started as Waveshare's driver starts it, then shown a picture (its PAGES rows of OLED_W bytes): only
    the rows that changed are sent."""

    def __init__(self, wires):
        self.wires = wires
        self.sent = [None] * PAGES
        self.level = BRIGHT                            # (as INIT has it)
        wires.reset()
        for c in INIT:                                 # (each on its own, as Waveshare's driver sends them)
            wires.command((c,))
        self.show(BLANK)

    def bright(self, level):
        """How bright it is (0 to 255): sent only as it changes."""
        if level != self.level:
            self.wires.command((CONTRAST,))
            self.wires.command((level,))
            self.level = level

    def show(self, rows):
        for p, row in enumerate(rows):
            if row != self.sent[p]:
                self.wires.command((0xB0 + p,) + COLUMN)
                self.wires.data(row)
                self.sent[p] = row

    def close(self):
        """Dark, and off."""
        try:
            self.show(BLANK)
            self.wires.command((SCREEN_OFF,))
        except OSError:
            pass
        self.wires.close()


# ---- the bars -------------------------------------------------------------------------------------------------------
def rows_of(px):
    """The screen's picture for these bars (each one's height, in pixels): its PAGES rows of bytes."""
    cols = np.zeros(OLED_W, dtype=np.uint64)           # (each column's height)
    x = BARS_LEFT + np.arange(BARS) * (BAR_W + BAR_GAP)
    for k in range(BAR_W):
        cols[x + k] = px
    # a column's 32 pixels as bits, the top one bit 0: lit up from the bottom. Its four bytes, lowest first, are its
    # part of each row
    lit = ((np.uint64(1) << cols) - np.uint64(1)) << (np.uint64(OLED_H) - cols)
    rows = lit.astype("<u4").view(np.uint8).reshape(OLED_W, PAGES).T.tobytes()
    return tuple(rows[p * OLED_W:(p + 1) * OLED_W] for p in range(PAGES))


# ---- with no music: the time, the weather, a face -------------------------------------------------------------------
def picture_rows(img):
    """A picture (OLED_W by OLED_H, lit where it's 1) as the screen's PAGES rows of bytes: each byte 8 pixels, one
    above the other, the top one its lowest bit."""
    lit = np.asarray(img.convert("1"), dtype=np.uint8).reshape(PAGES, 8, OLED_W)
    rows = np.packbits(lit, axis=1, bitorder="little").reshape(PAGES, OLED_W)
    return tuple(bytes(r) for r in rows)


def drift(slot, most):
    """Where its quiet picture is moved to, the slot'th minute (DRIFT_SECS): (across, down), at most most each way.
    A different place each minute, the same for that minute every time."""
    h = (slot * 2654435761) & 0xFFFFFFFF
    return h % (2 * most[0] + 1) - most[0], (h >> 16) % (2 * most[1] + 1) - most[1]


_FONTS, _PICS = {}, {}


def oled_font(path, size):
    key = (path, size)
    if key not in _FONTS:
        _FONTS[key] = ImageFont.truetype(path, size)
    return _FONTS[key]


def quiet_time(text, ampm="", at=(0, 0)):
    """The time, as big as fits (its AM or PM small beside it), in the middle (moved by at)."""
    img = Image.new("1", (OLED_W, OLED_H), 0)
    d = ImageDraw.Draw(img)
    big, small = oled_font(FONT_UI_BOLD, 30), oled_font(FONT_BOLD, 9)
    tw = d.textlength(text, font=big)
    aw = d.textlength(ampm, font=small) + 3 if ampm else 0
    x, y = (OLED_W - tw - aw) / 2 + at[0], OLED_H / 2 + at[1]
    d.text((x, y), text, font=big, fill=1, anchor="lm")
    if ampm:
        d.text((x + tw + 3, d.textbbox((x, y), text, font=big, anchor="lm")[3]), ampm, font=small, fill=1, anchor="ls")
    return img


def wx_picture(name, size=28):
    """A weather picture (weather.py's), as a shape to light."""
    key = ("wx", name, size)
    if key not in _PICS:
        pic = draw_wx(name, size)
        alpha = pic.getchannel("A") if pic.mode == "RGBA" else pic.convert("L")
        _PICS[key] = alpha.point(lambda v: 255 if v > 120 else 0).convert("1")
    return _PICS[key]


def quiet_weather(temp, words, icon, at=(0, 0)):
    """The weather now: its picture, how warm, and its words (on two lines, small; left out where they don't fit), in
    the middle (moved by at)."""
    img = Image.new("1", (OLED_W, OLED_H), 0)
    d = ImageDraw.Draw(img)
    pic, big = wx_picture(icon), oled_font(FONT_UI_BOLD, 26)
    tw = d.textlength(temp, font=big)
    room = OLED_W - 4 - pic.width - 6 - tw - 6
    lines, font = [], None
    for size in (10, 9):                               # (two lines at most: smaller, before they're left out)
        font = oled_font(FONT, size)
        lines = wrap_words(d, words, font, room)
        if lines:
            break
    ww = max((d.textlength(line, font=font) for line in lines), default=0)
    x = (OLED_W - (pic.width + 6 + tw + (6 + ww if lines else 0))) / 2 + at[0]
    img.paste(1, (round(x), (OLED_H - pic.height) // 2 + at[1]), pic)
    x += pic.width + 6
    d.text((x, OLED_H / 2 + at[1]), temp, font=big, fill=1, anchor="lm")
    x += tw + 6
    for k, line in enumerate(lines):
        y = OLED_H / 2 + at[1] + (k - (len(lines) - 1) / 2) * (font.size + 2)
        d.text((x, y), line, font=font, fill=1, anchor="lm")
    return img


def wrap_words(d, words, font, room):
    """Words on two lines at most, each no wider than room: [] where they don't fit."""
    parts, lines = (words or "").split(), []
    for word in parts:
        if lines and d.textlength(lines[-1] + " " + word, font=font) <= room:
            lines[-1] += " " + word
        else:
            lines.append(word)
    if len(lines) > 2 or any(d.textlength(line, font=font) > room for line in lines):
        return []
    return lines


SMILEY = 8                   # a smiley's drawn this many times as big, then made small (its curves smooth)


def smiley():
    """A smiley face, as a shape to light: two eyes and a smile, 34 pixels across and 22 down."""
    if "smiley" not in _PICS:
        s, w, h = SMILEY, 36, 24
        big = Image.new("L", (w * s, h * s), 0)
        d = ImageDraw.Draw(big)
        cx = w * s / 2
        for side in (-1, 1):                           # (its eyes: ovals, upright)
            ex = cx + side * 11 * s
            d.ellipse((ex - 3.2 * s, 1 * s, ex + 3.2 * s, 10 * s), fill=255)
        d.arc((cx - 17 * s, -5 * s, cx + 17 * s, 23 * s), 30, 150, fill=255, width=round(2.6 * s))   # (its smile)
        lit = np.asarray(big.resize((w, h), Image.LANCZOS)) >= 128
        lit |= lit[:, ::-1]                            # (the same both sides, to the pixel)
        pic = Image.fromarray(lit.astype(np.uint8) * 255).convert("1")
        _PICS["smiley"] = pic.crop(pic.getbbox())
    return _PICS["smiley"]


def quiet_face(at=(0, 0)):
    """A smiley face, in the middle (moved by at)."""
    img = Image.new("1", (OLED_W, OLED_H), 0)
    pic = smiley()
    img.paste(1, ((OLED_W - pic.width) // 2 + at[0], (OLED_H - pic.height) // 2 + at[1]), pic)
    return img


class Heard:
    """The sound, as it's fed (feed: s16le stereo samples, the first heard at t; gain: how much quieter than the song
    they've been made, the volume: made up for, so the bars are the song's whatever the volume), kept for KEPT
    seconds. levels(now): how loud each bar's piece of the sound heard now is (0 to 1)."""

    def __init__(self, rate=RATE):
        self.rate = rate
        self.seg = max(1, int(round(rate * BAR_SECS)))
        self.ring = np.zeros(int(rate * KEPT), dtype=np.float32)
        self.end = 0                                   # samples fed in all (the ring's next place: end % its length)
        self.t_end = None                              # when the one after the last fed is heard
        self.lock = threading.Lock()

    def feed(self, pcm, t, gain=1.0):
        a = np.frombuffer(pcm, dtype="<i2")
        n = len(a) // 2
        if not n:
            return
        size = np.abs(a[:n * 2].reshape(-1, 2).sum(axis=1, dtype=np.float32)) * (0.5 / 32768.0 / max(gain, QUIET_GAIN))
        size = size[-len(self.ring):]
        with self.lock:
            if self.t_end is not None and abs(t - self.t_end) > JUMP:
                self.ring[:] = 0.0                     # (not the next of it: what's kept is of another time)
            i = (self.end + n - len(size)) % len(self.ring)
            first = min(len(size), len(self.ring) - i)
            self.ring[i:i + first] = size[:first]
            self.ring[:len(size) - first] = size[first:]
            self.end += n
            self.t_end = t + n / self.rate

    def levels(self, now):
        w = BARS * self.seg
        with self.lock:
            if self.t_end is None:
                return np.zeros(BARS)
            start = self.end + int(round((now - self.t_end) * self.rate))   # (the sample heard now)
            if start >= self.end or start < max(0, self.end - len(self.ring)):
                return np.zeros(BARS)                  # (nothing fed for now: it's stopped; or it's long gone)
            start = min(start, self.end - w)           # (the last of what's fed, if it ends within the bars)
            if start < 0:
                return np.zeros(BARS)
            win = self.ring[(start + np.arange(w)) % len(self.ring)]
        return np.minimum(win.reshape(BARS, self.seg).mean(axis=1), 1.0)


# ---- another of your Pietatos' music -----------------------------------------------------------------------------
def bars_packet(levels, sent):
    """The bars now (each 0 to 1), as a packet."""
    return BARS_HEAD.pack(BARS_MAGIC, BARS_VERSION, sent) + \
        np.clip(np.rint(np.asarray(levels, dtype=np.float64) * 255), 0, 255).astype(np.uint8).tobytes()


def read_bars(data):
    """What a packet says ((when it was sent, each bar 0 to 1)), or None: not one of these."""
    if len(data) != BARS_HEAD.size + BARS:
        return None
    magic, version, sent = BARS_HEAD.unpack_from(data)
    if magic != BARS_MAGIC or version != BARS_VERSION or not math.isfinite(sent):
        return None
    return sent, np.frombuffer(data, dtype=np.uint8, offset=BARS_HEAD.size).astype(np.float64) / 255.0


def oled_clean(o):
    """What another's beacon says of its OLED ({"port"}: where its bars are taken), kept to what makes sense, or
    None."""
    port = o.get("port") if isinstance(o, dict) else None
    if isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536:
        return None
    return {"port": port}


class BarsOut:
    """This one's music, as bars, to your other Pietatos' OLEDs: how loud each bar's piece of the sound heard now is,
    a UDP packet FPS times a second while it plays (one that's lost is lost: the next is on its way). Fed as an
    OledBars is (heard), from the player's thread. Silence is said a few times, then no more till there's sound."""

    def __init__(self, clock=time.monotonic, run=True):
        self.clock = clock
        self.heard_of = Heard()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        self.to = ()                                   # where they go: [(address, port)]
        self.fed = -1e9                                # when sound was last fed
        self.quiet = QUIET_SAID                        # packets of silence said in a row
        self.wake = threading.Event()
        self.closed = False
        if run:
            threading.Thread(target=self.run, daemon=True, name="oled-out").start()

    def aim(self, to):
        self.to = tuple(to)

    def heard(self, pcm, t, gain=1.0):
        """(The player's thread.) Sound, its first sample heard at t (this Pi's clock)."""
        if not self.to:
            return
        self.heard_of.feed(pcm, t, gain)
        self.fed = self.clock()
        self.wake.set()

    def frame(self, now):
        """The bars as they are now, sent: True if they were (False: nothing to say, after silence)."""
        levels = self.heard_of.levels(now)
        if levels.any():
            self.quiet = 0
        elif self.quiet >= QUIET_SAID:
            return False
        else:
            self.quiet += 1
        data = bars_packet(levels, now)
        for addr in self.to:
            try:
                self.sock.sendto(data, addr)
            except OSError:
                pass
        return True

    def run(self):
        due = self.clock()
        while not self.closed:
            now = self.clock()
            try:
                sent = self.frame(now)
            except Exception as ex:                    # (never its thread's end)
                print(f"oled: its bars, to your others: {ex!r}", flush=True)
                sent = False
            if not sent and now - self.fed > IDLE_AFTER:
                self.wake.clear()
                self.wake.wait(IDLE_EVERY)
                due = self.clock()
                continue
            due += FRAME
            wait = due - self.clock()
            if wait > 0:
                time.sleep(wait)
            else:
                due = self.clock()

    def close(self):
        self.closed = True
        self.to = ()
        self.wake.set()
        try:
            self.sock.close()
        except OSError:
            pass


class BarsIn:
    """Your other Pietatos' music, as bars (BarsOut's packets), taken here. named(address): who's there (None: not
    one of yours, so not listened to). Whichever's playing is followed, and kept to till it's been quiet a moment
    (HOLD); its bars go to on_bars(levels), as they come."""

    def __init__(self, on_bars, named, port=OLED_PORT, clock=time.monotonic, listen=True):
        self.on_bars, self.named, self.clock = on_bars, named, clock
        self.source = None                             # the address it follows now
        self.heard_at = -1e9                           # ...when its last packet came
        self.sent = -1e9                               # ...and when that was sent (its clock: an older one's late)
        self.closed = False
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("", port))
        self.port = self.sock.getsockname()[1]
        if listen:
            threading.Thread(target=self.listen, daemon=True, name="oled-in").start()

    def listen(self):
        while not self.closed:
            try:
                data, (ip, _) = self.sock.recvfrom(256)
            except OSError:
                if self.closed:
                    break
                time.sleep(0.1)
                continue
            try:
                self.take(data, ip, self.clock())
            except Exception as ex:                    # (never the listener's end)
                print(f"oled: another's bars: {ex!r}", flush=True)

    def take(self, data, ip, now):
        """A packet from ip, come at now: True if its bars are shown."""
        p = read_bars(data)
        if p is None or self.named(ip) is None:
            return False
        sent, levels = p
        held = now - self.heard_at < HOLD
        if self.source != ip:
            if self.source is not None and held:
                return False                           # (another's being followed: it's still playing)
            self.source, self.sent, held = ip, -1e9, False
        if sent <= self.sent and held:
            return False                               # (an older one, come late)
        self.sent, self.heard_at = sent, now
        self.on_bars(levels)
        return True

    def close(self):
        self.closed = True
        try:
            self.sock.close()
        except OSError:
            pass


class OledBars:
    """The bars on the OLED, FPS times a second, on a thread of its own: each bar up to how loud its piece of the sound
    heard now is, and falling back slowly. With nothing fed and its bars down, the screen's dark and it's looked at
    only now and then (what's fed wakes it). Another of yours' bars (told) are shown while this Pi's own sound isn't
    fed. quiet(now): its picture with no music for a while (QUIET_AFTER), as rows (None: dark), shown dimmer."""

    def __init__(self, screen, clock=time.monotonic, run=True, quiet=None):
        self.screen, self.clock, self.quiet = screen, clock, quiet
        self.resting = False                           # (its quiet picture's on the screen)
        self.heard_of = Heard()
        self.h = np.zeros(BARS)                        # each bar now (0 to 1)
        self.px = np.zeros(BARS, dtype=np.int64)       # ...and as it's drawn (pixels)
        self.last = None
        self.fed = -1e9                                # when sound was last fed (this Pi's, or another's bars)
        self.own_at = -1e9                             # ...this Pi's own
        self.theirs, self.theirs_at = None, -1e9       # another of yours' bars (0 to 1 each), and when they came
        self.up = 0.0                                  # its bars up this far, the next frame (hello's)
        self.writing = threading.Lock()                # (the screen written to by one at a time: never once it's shut)
        self.wake = threading.Event()
        self.closed = False
        if run:
            threading.Thread(target=self.run, daemon=True, name="oled").start()

    def heard(self, pcm, t, gain=1.0):
        """(The player's thread.) Sound, its first sample heard at t (this Pi's clock)."""
        self.heard_of.feed(pcm, t, gain)
        self.fed = self.own_at = self.clock()
        self.wake.set()

    def told(self, levels):
        """(BarsIn's thread.) Another of yours' bars, as its music's heard there now."""
        self.theirs, self.theirs_at = levels, self.clock()
        self.fed = self.theirs_at
        self.wake.set()

    def hello(self):
        """Its bars up a little, once, and down again: it's lit (Settings > Screen > Waveshare 2.23 OLED, as it's turned
        on)."""
        self.up, self.fed = HELLO, self.clock()
        self.wake.set()

    def frame(self, now):
        """The bars as they are now, drawn (if they've changed)."""
        new = self.heard_of.levels(now)
        theirs = self.theirs
        if theirs is not None and now - self.theirs_at <= THEIRS_KEPT and now - self.own_at > OWN_FIRST:
            new = theirs                               # (another of yours' music: this Pi plays none of its own)
        if self.up:
            new, self.up = np.maximum(new, self.up), 0.0
        fall = 1.0 if self.last is None else DECAY ** (max(0.0, now - self.last) / FRAME)
        self.last = now
        self.h = np.maximum(new, self.h * fall)
        self.h[self.h < FLOOR] = 0.0
        px = np.minimum(OLED_H, (self.h * (OLED_H * GAIN)).astype(np.int64))
        if not np.array_equal(px, self.px):
            with self.writing:
                if self.closed:
                    return
                self.screen.show(rows_of(px))
            self.px = px

    def idle(self, now):
        return not self.px.any() and now - self.fed > IDLE_AFTER

    def rest(self, now):
        """No music for a while, its bars down: its quiet picture, dimmer (as it changes). Music again (even its
        quiet start): dark at once, as bright as ever, for its bars."""
        rows = None
        if self.quiet is not None and not self.px.any() and now - self.fed > QUIET_AFTER:
            rows = self.quiet(now)
        if rows is None and not self.resting:
            return
        with self.writing:
            if self.closed:
                return
            if rows is None:
                self.screen.show(rows_of(self.px))
                self.screen.bright(BRIGHT)
            else:
                self.screen.bright(DIM)
                self.screen.show(rows)
        self.resting = rows is not None

    def run(self):
        due = self.clock()
        while not self.closed:
            now = self.clock()
            try:
                self.rest(now)
                self.frame(now)
            except Exception as ex:                    # (the SPI gone wrong, say: tried again in a moment; never
                print(f"oled: the screen: {ex!r}", flush=True)   # its thread's end)
                time.sleep(2.0)
            if self.idle(now):
                self.wake.clear()
                self.wake.wait(IDLE_EVERY)
                due = self.clock()
                continue
            due += FRAME                               # (a steady pace: only what's left of this frame is waited)
            wait = due - self.clock()
            if wait > 0:
                time.sleep(wait)
            else:
                due = self.clock()

    def picture(self):
        """Its bars as last drawn (each one's height in pixels): for the tests."""
        return self.px.copy()

    def close(self):
        self.closed = True
        self.wake.set()
        with self.writing:
            self.screen.close()
