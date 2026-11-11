"""LED backlight: an 8x8 grid of WS2812B LEDs behind your TV (or a strip of them round its edges: each LED takes the
colour of the grid's edge nearest it), lit with the colours along the edges of the game you're playing, on another of
your Pietatos (or this one). The one playing samples each picture's edges (Edges) and sends them
over UDP about 30 times a second (GlowOut: a packet each, nothing waiting for an answer). What happens in the game goes
the same way, a packet each: a hit (its rich presence says the lives or health went down: HitWatch; or it shook the
controller), an achievement, and music's beats as they're heard (Beats: party.py's player finds them, as it plays).
The one with the grid (Grid) takes them from your Pietatos only, follows one of them (or whichever's playing), smooths
the colours, flashes red or gold or with the beat, and lights the LEDs through the Pi's SPI (Strip: GPIO 10, its MOSI,
so nothing needs installing). With nothing lighting it, it shows a colour of your own (or a rainbow), or goes dark.
A light of your own on the network (an ESP32 board's LED: esp32/pietato_led) is sent the same packets: it says it's
there (Lamps), and keeps time itself. screens/glow.py has its page in Apps (backlight.py draws it), and says where a
game's colours go."""
import collections
import errno
import fcntl
import ipaddress
import math
import os
import random
import re
import socket
import struct
import threading
import time

import numpy as np

GLOW_PORT = 5448             # an LED grid takes its colours here (UDP)
GLOW_W = GLOW_H = 8          # its LEDs, across and down
GLOW_EVERY = 1 / 30          # seconds between a game's pictures sampled (a packet each)
EDGE_BAND = 0.15             # how far in from a picture's edges its colours are taken (a share of its size)
EDGE_PER = 6                 # ...a few pixels each way, in each LED's part of it
INSIDE = 0.8                 # the LEDs behind the middle of the TV: as bright as this, of the edges' blend
MAGIC, VERSION = b"PG", 1
HEAD = struct.Struct(">2sBcd")   # magic, version, kind (F: a picture's colours; E: something happening; M: music),
EVENT = struct.Struct(">dB")     # when it was sent (the sender's clock). E: when it shows (its clock too), how hard
LAMP_PORT = 5449             # a light of your own on the network (an ESP32's LED) says it's there, here (UDP: kind L,
LAMP = struct.Struct(">H")   # then how many LEDs it has, and its name), every couple of seconds
LAMP_HEARD = 8.0             # ...and is lit, as a grid is, for this long after it last said so
LAMPS_MOST = 64              # no more of them than this
LAMPS_EACH = 2               # a game's picture goes to this many of them, in turn (30 pictures a second: so 60 packets
                             # a second in all, however many there are; a beat or a hit goes to every one at once)
LAMP_NAME = 24               # bytes of a light's name
EVENTS = ("hit", "cheevo", "beat")
HIT_GAP = 0.4                # seconds: one hit at a time (a game shaking the controller does it again and again)
RUMBLE_HIT = 0x3000          # how hard a game shakes player 1's controller before it's a hit
BEAT_FRAME = 1024            # samples looked at, at a time, for a beat (21 ms)...
BEAT_HOP = 512               # ...each half that on from the one before
BEAT_BASS = (40.0, 180.0)    # what's listened to for a beat (Hz): the bass, a kick drum's
BEAT_GAP = 0.28              # seconds: beats at least this far apart
BEAT_RISE = 1.7              # a beat: the bass rising this much more than it has been, lately
BEAT_KEEP = 1.5              # ...lately: seconds
BEAT_OVER = 0.6              # ...and by more than this much of how loud it's usually been
BEAT_QUIET = 1e3             # ...and quieter than this: silence (its bass, as the FFT has it, summed)
HOLD = 2.5                   # seconds a grid keeps following one (any of yours): another's taken once it's quiet
FADE_AFTER = 1.5             # seconds with nothing new: the grid goes dark, slowly
TAU, FADE_TAU = 0.06, 0.5    # seconds its colours take to follow the picture (and to go dark)
OFFSET_KEEP = 200            # packets an offset's worked out from (the quickest: the clocks' difference)
MUSIC_BASE = 0.4             # music's colour, between beats
BEAT_TAU, BEAT_GAIN = 0.12, 1.6   # a beat: how fast it dies away, and how much brighter
HIT_SECS, GOLD_SECS = 0.5, 1.4    # a hit's red, an achievement's gold: how long they take to go
RED, GOLD = np.array([255.0, 0.0, 0.0]), np.array([255.0, 180.0, 30.0])
GAMMA = 2.2                  # an LED's brightness as it's seen
RATE = 60.0                  # the grid lit this often (a second)
SPI_DEV = "/dev/spidev0.0"   # the Pi's SPI: its MOSI is GPIO 10 (pin 19)
SPI_HZ = 2400000             # three of its bits to each of an LED's: 0 goes as 100, 1 as 110 (0.42 µs each)
SPI_IOC_WR_MODE, SPI_IOC_WR_BITS_PER_WORD, SPI_IOC_WR_MAX_SPEED_HZ = 0x40016B01, 0x40016B03, 0x40046B04
RESET = bytes(100)           # (low for 330 µs after: the LEDs show what they've been sent)
THIS_ONE = "This one"        # a grid following the Pietato it's on
ANY = "Any of yours"         # ...or whichever of yours is playing
NOBODY = "Nobody"            # ...or none of them: just its own colour
COLOURS = (("Off", None), ("Warm white", (255, 194, 110)), ("White", (255, 255, 255)), ("Red", (255, 0, 0)),
           ("Orange", (255, 142, 0)), ("Yellow", (255, 218, 0)), ("Green", (0, 255, 40)), ("Teal", (0, 230, 190)),
           ("Blue", (20, 80, 255)), ("Purple", (182, 0, 255)), ("Pink", (255, 80, 167)), ("Rainbow", "rainbow"))
                             # its own colour, with nothing else lighting it (as it's seen: LEDs' brightness evened out)
COLOUR_TAU = 0.2             # seconds its own colour takes to come in
RAINBOW_SECS = 12.0          # seconds a rainbow takes to go round once
LIVELY = 0.3                 # seconds since its colours last changed: still changing (its picture drawn again soon)
STRIP_LEAST, STRIP_MOST = 8, 300   # LEDs on a strip (at most: one SPI write, 9 bytes each)
STARTS = ("Bottom left", "Top left", "Top right", "Bottom right", "Bottom middle")   # where a strip's first LED is
TV_W, TV_H = 16.0, 9.0       # a TV's shape: a strip's LEDs shared out along its sides as long as they are


# ---- a picture's edges -----------------------------------------------------------------------------------------------
def rgb565(v):
    v = v.astype(np.uint32)
    return np.stack((((v >> 11) & 31) * (255 / 31), ((v >> 5) & 63) * (255 / 63), (v & 31) * (255 / 31)), -1)


def rgb555(v):
    v = v.astype(np.uint32)
    return np.stack((((v >> 10) & 31) * (255 / 31), ((v >> 5) & 31) * (255 / 31), (v & 31) * (255 / 31)), -1)


def rgb888(v):
    v = v.astype(np.uint32)
    return np.stack((((v >> 16) & 255) * 1.0, ((v >> 8) & 255) * 1.0, (v & 255) * 1.0), -1)


def rgb_fields(fields):
    """Pixels as a screen keeps them (each colour's place and length: the framebuffer's), as red, green and blue."""
    def rgb(v):
        v = v.astype(np.uint32)
        return np.stack([((v >> off) & ((1 << ln) - 1)) * (255 / ((1 << ln) - 1)) for off, ln in fields[:3]], -1)
    return rgb


def rainbow(rows, cols, t, wheel=False):
    """A rainbow across the grid, corner to corner (or round its middle, a wheel: a strip round the TV has every colour
    once), going round as time goes on (rows x cols x 3, 0 to 255)."""
    if wheel:
        y, x = np.mgrid[0:rows, 0:cols]
        h = (np.arctan2(y - (rows - 1) / 2, x - (cols - 1) / 2) / (2 * np.pi) + t / RAINBOW_SECS) % 1.0
    else:
        h = ((np.arange(rows)[:, None] + np.arange(cols)[None, :]) / (rows + cols) + t / RAINBOW_SECS) % 1.0
    k = (np.array([5.0, 3.0, 1.0]) + h[..., None] * 6) % 6
    return 255.0 * (1 - np.clip(np.minimum(k, 4 - k), 0, 1))


def colour_of(name):
    """A colour's name (COLOURS'): what it is (an RGB, "rainbow"), or None for Off (or a name that isn't one)."""
    return dict(COLOURS).get(name)


def strip_points(n, start="Bottom left", clockwise=True, bottom=True):
    """Where each of a strip's n LEDs is round the TV, as you look at it: (x, y) from its top left, 0 to 1 across and
    down. Its first LED at `start`, the rest going round (clockwise as you look at it, or not), shared out evenly along
    the sides with LEDs (the bottom too, or not: a TV on a stand)."""
    loop = 2 * (TV_W + TV_H)                    # (round the TV clockwise from its top left: top, right, bottom, left)
    at = {"Top left": 0.0, "Top right": TV_W, "Bottom right": TV_W + TV_H, "Bottom middle": 1.5 * TV_W + TV_H}.get(
        start, 2 * TV_W + TV_H)
    steps = 20000
    d = (np.arange(steps) + 0.5) * loop / steps
    u = (at + (d if clockwise else -d)) % loop
    used = np.ones(steps, dtype=bool) if bottom else ~((u > TV_W + TV_H) & (u < 2 * TV_W + TV_H))
    along = np.cumsum(used)                      # (how far along its LEDs, at each step)
    k = np.searchsorted(along, (np.arange(n) + 0.5) * along[-1] / n).clip(0, steps - 1)
    u = u[k]
    sides = [u < TV_W, u < TV_W + TV_H, u < 2 * TV_W + TV_H]
    x = np.select(sides, [u, np.full_like(u, TV_W), 2 * TV_W + TV_H - u], 0.0)
    y = np.select(sides, [np.zeros_like(u), u - TV_W, np.full_like(u, TV_H)], loop - u)
    return np.stack([x / TV_W, y / TV_H], axis=1)


def strip_weights(points, cols=GLOW_W, rows=GLOW_H):
    """How each strip LED's colour comes from the grid's picture (a row for each LED, a column for each of the
    picture's LEDs): from the nearest ones on its edge, the nearer the more."""
    cx = (points[:, 0] * cols - 0.5).clip(0, cols - 1)
    cy = (points[:, 1] * rows - 0.5).clip(0, rows - 1)
    x0 = np.floor(cx).astype(int).clip(0, cols - 2)
    y0 = np.floor(cy).astype(int).clip(0, rows - 2)
    fx, fy = cx - x0, cy - y0
    w = np.zeros((len(points), rows * cols))
    i = np.arange(len(points))
    for dy, wy in ((0, 1 - fy), (1, fy)):
        for dx, wx in ((0, 1 - fx), (1, fx)):
            np.add.at(w, (i, (y0 + dy) * cols + x0 + dx), wy * wx)
    return w


def border_cells(cols=GLOW_W, rows=GLOW_H):
    """The grid's outer LEDs, in a steady order: (row, column)."""
    out = [(0, c) for c in range(cols)] + [(rows - 1, c) for c in range(cols)]
    out += [(r, 0) for r in range(1, rows - 1)] + [(r, cols - 1) for r in range(1, rows - 1)]
    return out


def blend(cols=GLOW_W, rows=GLOW_H, inside=INSIDE):
    """How each LED's colour comes from the outer ones' (a row for each LED, a column for each outer one): the outer
    ones their own; the ones inside, the nearest outer ones' in their row and column, the nearer the more."""
    edge = border_cells(cols, rows)
    at = {rc: k for k, rc in enumerate(edge)}
    m = np.zeros((rows * cols, len(edge)))
    for r in range(rows):
        for c in range(cols):
            if (r, c) in at:
                m[r * cols + c, at[(r, c)]] = 1.0
                continue
            near = ((0, c, r), (rows - 1, c, rows - 1 - r), (r, 0, c), (r, cols - 1, cols - 1 - c))
            w = np.array([1.0 / d ** 2 for _, _, d in near])
            for (rr, cc, _), x in zip(near, w / w.sum()):
                m[r * cols + c, at[(rr, cc)]] += x * inside
    return m


class Edges:
    """The colours along a picture's edges, for the grid: its top row from the picture's top edge (an eighth of the
    way across each), its bottom row from the bottom, its sides' from the sides; the LEDs inside blended from those.
    A few pixels each, so a big picture costs no more than a small one."""

    def __init__(self, cols=GLOW_W, rows=GLOW_H, band=EDGE_BAND, per=EDGE_PER):
        self.cols, self.rows, self.band, self.per = cols, rows, band, per
        self.mix = blend(cols, rows)
        self.shape, self.ys, self.xs = None, None, None

    def plan(self, h, w):
        """Where each outer LED's pixels are, in a picture h by w."""
        bh, bw = max(1, int(h * self.band)), max(1, int(w * self.band))

        def span(a, b):
            return np.linspace(a, max(a, b - 1), self.per).round().astype(np.intp)
        ys, xs = [], []
        for r, c in border_cells(self.cols, self.rows):
            if r == 0:
                y, x = span(0, bh), span(c * w // self.cols, (c + 1) * w // self.cols)
            elif r == self.rows - 1:
                y, x = span(h - bh, h), span(c * w // self.cols, (c + 1) * w // self.cols)
            else:
                y = span(r * h // self.rows, (r + 1) * h // self.rows)
                x = span(0, bw) if c == 0 else span(w - bw, w)
            yy, xx = np.meshgrid(y, x, indexing="ij")
            ys.append(yy.ravel())
            xs.append(xx.ravel())
        self.shape, self.ys, self.xs = (h, w), np.array(ys), np.array(xs)

    def colours(self, a, rgb):
        """The grid's colours (rows x cols x 3, 0 to 255) from a picture (its pixels, as rgb() reads them)."""
        if a.shape[:2] != self.shape:
            self.plan(a.shape[0], a.shape[1])
        edge = rgb(a[self.ys, self.xs]).mean(axis=1)  # (each outer LED's)
        out = self.mix @ edge
        return out.reshape(self.rows, self.cols, 3).clip(0, 255).astype(np.uint8)


# ---- packets ---------------------------------------------------------------------------------------------------------
def frame_packet(colours, sent):
    h, w = colours.shape[:2]
    return HEAD.pack(MAGIC, VERSION, b"F", sent) + bytes((w, h)) + np.asarray(colours, dtype=np.uint8).tobytes()


def event_packet(name, strength, at, sent):
    return HEAD.pack(MAGIC, VERSION, b"E", sent) + EVENT.pack(at, max(0, min(255, int(round(strength * 255))))) \
        + name.encode()


def music_packet(rgb, sent):
    return HEAD.pack(MAGIC, VERSION, b"M", sent) + bytes(max(0, min(255, int(v))) for v in rgb[:3])


def read_packet(data):
    """What a packet says ({"kind", "sent", ...}), or None: not one of these, or not right."""
    if len(data) < HEAD.size or len(data) > 4096:
        return None
    magic, version, kind, sent = HEAD.unpack_from(data)
    if magic != MAGIC or version != VERSION or not math.isfinite(sent):
        return None
    rest = data[HEAD.size:]
    if kind == b"F" and len(rest) >= 2:
        w, h = rest[0], rest[1]
        if 1 <= w <= 32 and 1 <= h <= 32 and len(rest) == 2 + w * h * 3:
            return {"kind": "frame", "sent": sent,
                    "colours": np.frombuffer(rest[2:], dtype=np.uint8).reshape(h, w, 3).astype(np.float64)}
    elif kind == b"E" and len(rest) > EVENT.size:
        at, strength = EVENT.unpack_from(rest)
        name = rest[EVENT.size:].decode("ascii", "replace")
        if name in EVENTS and math.isfinite(at):
            return {"kind": "event", "sent": sent, "at": at, "name": name, "strength": strength / 255}
    elif kind == b"M" and len(rest) == 3:
        return {"kind": "music", "sent": sent, "rgb": np.array(list(rest), dtype=np.float64)}
    return None


def lamp_packet(name, count, sent):
    """What a light of your own says, to say it's there (esp32/pietato_led says it; this is for the tests)."""
    return HEAD.pack(MAGIC, VERSION, b"L", sent) + LAMP.pack(max(1, min(0xFFFF, int(count)))) \
        + name.encode("utf-8", "replace")[:LAMP_NAME]


def read_lamp(data):
    """A light's word that it's there ({"name", "count": its LEDs}), or None: not one, or not right."""
    if not HEAD.size + LAMP.size <= len(data) <= HEAD.size + LAMP.size + LAMP_NAME:
        return None
    magic, version, kind, sent = HEAD.unpack_from(data)
    (count,) = LAMP.unpack_from(data, HEAD.size)
    if magic != MAGIC or version != VERSION or kind != b"L" or not count:
        return None
    name = "".join(c for c in data[HEAD.size + LAMP.size:].decode("utf-8", "replace") if c.isprintable()).strip()
    return {"name": name or "light", "count": count}


def on_your_network(ip):
    """An address on your own network (a private one, or this Pi's own)."""
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return a.is_private or a.is_link_local or a.is_loopback


class Lamps:
    """Lights of your own on the network (an ESP32's own LED, or a strip on one: esp32/pietato_led), found by
    themselves: each says it's there every couple of seconds (UDP, to everyone on your network), and is lit as your
    grids are for as long as it does: music's beats, a game's colours, a hit, an achievement. Each takes those at
    GLOW_PORT, as a grid does, and keeps time itself: a beat is one small packet to each. Only ones on your network."""

    def __init__(self, port=LAMP_PORT, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.heard = {}                                # address -> (when it last said it's there, its name, its LEDs)
        self.closed = False
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.bind(("", port))
        except OSError:
            self.sock.close()
            raise
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self.listen, daemon=True, name="lamps").start()

    def listen(self):
        while not self.closed:
            try:
                data, addr = self.sock.recvfrom(256)
            except OSError:
                if self.closed:
                    return
                time.sleep(0.5)
                continue
            self.take(data, addr[0], self.clock())

    def take(self, data, ip, now):
        """A packet from ip, heard at now: True if it's a light of yours saying it's there."""
        p = read_lamp(data)
        if p is None or not on_your_network(ip):
            return False
        with self.lock:
            if ip not in self.heard and len(self.heard) >= LAMPS_MOST:
                self.heard = {k: v for k, v in self.heard.items() if now - v[0] <= LAMP_HEARD}
                if len(self.heard) >= LAMPS_MOST:
                    return False
            self.heard[ip] = (now, p["name"], p["count"])
        return True

    def on(self, now=None):
        """The lights there now: [(address, name, its LEDs)], by address."""
        now = self.clock() if now is None else now
        with self.lock:
            self.heard = {k: v for k, v in self.heard.items() if now - v[0] <= LAMP_HEARD}
            return [(ip, v[1], v[2]) for ip, v in sorted(self.heard.items())]

    def close(self):
        self.closed = True
        try:
            self.sock.close()
        except OSError:
            pass


def targets(words):
    """Where a game's colours go, as media mode says them ("10.0.0.7:5448 127.0.0.1:5448", or "-" for nowhere):
    [(address, port)]. A light of your own has a + before it ("+10.0.0.9:5448": lamp_targets() has just those)."""
    out = []
    for w in words:
        host, _, port = w[1:].rpartition(":") if w.startswith("+") else w.rpartition(":")
        if re.fullmatch(r"[A-Za-z0-9.-]{1,253}", host or "") and port.isdigit() and 0 < int(port) < 65536:
            out.append((host, int(port)))
    return out


def lamp_targets(words):
    """Those of them that are lights of your own (a + before each): a picture's colours go to them a few at a time."""
    return targets([w for w in words if w.startswith("+")])


def target_words(to, lamps=()):
    """...and how media mode says them, for these [(address, port)] (the ones in lamps: lights of your own)."""
    return " ".join(("+" if a in lamps else "") + f"{a[0]}:{a[1]}" for a in to) or "-"


class GlowOut:
    """A Pietato's colours and what happens, to your LED grids: a UDP packet each (one that's lost is lost: the next
    one's on its way)."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        self.to = ()                                   # everywhere it goes
        self.grids = ()                                # ...the grids among them: every picture
        self.lamps = ()                                # ...and the lights of your own: a few each picture, in turn
        self.turn = 0

    def aim(self, to, lamps=()):
        """Where it goes: [(address, port)]. Those also in lamps are lights of your own (an ESP32's LED: there can be
        a lot of them, each showing one colour): a picture goes to LAMPS_EACH of them at a time, in turn, so a game
        sends no more for sixty of them than for two. What happens (a beat, a hit) goes to all of them at once."""
        lamps = set(lamps)
        self.to = tuple(to)
        self.grids = tuple(a for a in self.to if a not in lamps)
        self.lamps = tuple(a for a in self.to if a in lamps)

    def send(self, data, to=None):
        for addr in self.to if to is None else to:
            try:
                self.sock.sendto(data, addr)
            except OSError:
                pass

    def frame(self, colours):
        if not self.to:
            return
        data = frame_packet(colours, self.clock())
        self.send(data, self.grids)
        n = len(self.lamps)
        if n:
            self.turn %= n
            each = min(n, LAMPS_EACH)
            self.send(data, [self.lamps[(self.turn + k) % n] for k in range(each)])
            self.turn += each

    def event(self, name, strength=1.0, at=None, lamps=True):
        """Something happening (now, or at): to all of them (lamps False: just the grids, not the lights of your own)."""
        to = self.to if lamps else self.grids
        if to:
            now = self.clock()
            self.send(event_packet(name, strength, now if at is None else at, now), to)

    def music(self, rgb):
        if self.to:
            self.send(music_packet(rgb, self.clock()))

    def close(self):
        self.to = self.grids = self.lamps = ()
        try:
            self.sock.close()
        except OSError:
            pass


# ---- a hit, from what RetroAchievements says you're doing ------------------------------------------------------------
LABEL = r"(lives|life|hp|health|hearts?|energy|armou?r|shields?|❤️?|♥|💖|💗|💓)"
AFTER = re.compile(LABEL + r"[\s:=]*(?:[x×]\s*)?(\d{1,5})", re.I)        # "Lives: 3", "HP 12/20", "❤x3"
BEFORE = re.compile(r"(\d{1,5})\s?" + r"(lives|life|hp|hearts?)\b", re.I)   # "3 lives"
HEARTS = re.compile(r"(?:(?:❤️?|♥)\s?){2,}")                       # "❤❤❤" (one each)
HIT_WEIGHT = {"lives": 1.0, "life": 1.0}                               # (a life lost: the most; health: a bit less)


def hit_numbers(text):
    """The lives and health in a game's rich presence ("Mario in World 1-2 | Lives: 3"): {label: number}."""
    out = {}
    for m in AFTER.finditer(text or ""):
        out.setdefault(norm_label(m.group(1)), int(m.group(2)))
    for m in BEFORE.finditer(text or ""):
        out.setdefault(norm_label(m.group(2)), int(m.group(1)))
    for m in HEARTS.finditer(text or ""):
        out.setdefault("hearts", len(re.findall(r"❤|♥", m.group(0))))
    return out


def norm_label(word):
    w = word.lower().replace("️", "")
    return {"heart": "hearts", "❤": "hearts", "♥": "hearts", "💖": "hearts", "💗": "hearts", "💓": "hearts",
            "armour": "armor", "shields": "shield"}.get(w, w)


class HitWatch:
    """A hit, from a game's rich presence (what RetroAchievements says you're doing, lives and health with it): one of
    its numbers going down. take(text): how hard (0: none)."""

    def __init__(self):
        self.was = {}

    def take(self, text):
        now = hit_numbers(text)
        hit = 0.0
        for k, v in now.items():
            if k in self.was and v < self.was[k]:
                hit = max(hit, HIT_WEIGHT.get(k, 0.7))
        self.was = now
        return hit


# ---- music's beats ---------------------------------------------------------------------------------------------------
class Beats:
    """Beats in what's played (a song, a station), as they're heard: the bass rising suddenly, more than it has been
    lately (a kick drum), at most one each BEAT_GAP. feed(pcm, t): s16le stereo samples, the first one heard at t (the
    player's clock); on_beat(when it's heard, how hard: 0 to 1)."""

    def __init__(self, rate, on_beat):
        self.rate, self.on_beat = rate, on_beat
        self.buf = np.zeros(0, dtype=np.float32)
        self.t0 = None
        self.window = np.hanning(BEAT_FRAME).astype(np.float32)
        f = np.fft.rfftfreq(BEAT_FRAME, 1.0 / rate)
        self.bass = (f >= BEAT_BASS[0]) & (f <= BEAT_BASS[1])
        self.prev = None
        self.rises = collections.deque(maxlen=max(4, int(BEAT_KEEP * rate / BEAT_HOP)))
        self.loud = collections.deque(maxlen=max(4, int(BEAT_KEEP * rate / BEAT_HOP)))
        self.last = -1e9

    def feed(self, pcm, t):
        a = np.frombuffer(pcm, dtype="<i2")
        if len(a) < 2:
            return
        mono = a[: len(a) // 2 * 2].reshape(-1, 2).mean(axis=1, dtype=np.float32)
        if self.t0 is None or abs(t - (self.t0 + len(self.buf) / self.rate)) > 0.05:
            self.buf, self.t0, self.prev = mono, t, None   # (a jump: it starts again from here)
        else:
            self.buf = np.concatenate((self.buf, mono))
        while len(self.buf) >= BEAT_FRAME:
            bass = float(np.abs(np.fft.rfft(self.buf[:BEAT_FRAME] * self.window))[self.bass].sum())
            when = self.t0 + BEAT_FRAME / 2 / self.rate
            self.buf = self.buf[BEAT_HOP:]
            self.t0 += BEAT_HOP / self.rate
            if bass < BEAT_QUIET:                      # (silence: nothing to go by, and none of it kept)
                self.prev = None
                continue
            if self.prev is not None:
                rise = max(0.0, bass - self.prev)
                lately = sum(self.rises) / len(self.rises) if self.rises else 0.0
                loud = max(self.loud)
                usual = sum(self.loud) / len(self.loud)
                warm = len(self.rises) >= self.rises.maxlen // 3   # (heard a moment first: what's usual for it)
                if warm and rise > BEAT_RISE * lately and rise > 0.1 * loud and rise > BEAT_OVER * usual \
                        and when - self.last >= BEAT_GAP:
                    self.last = when
                    self.on_beat(when, min(1.0, rise / (0.5 * loud)))
                self.rises.append(rise)
            self.loud.append(bass)
            self.prev = bass


# ---- the grid --------------------------------------------------------------------------------------------------------
ONE = (0b100, 0b110)


def spi_byte(v):
    bits = 0
    for k in range(7, -1, -1):
        bits = (bits << 3) | ONE[(v >> k) & 1]
    return bits.to_bytes(3, "big")


SPI_LUT = np.frombuffer(b"".join(spi_byte(v) for v in range(256)), dtype=np.uint8).reshape(256, 3)


def spi_bytes(grb):
    """An LED's green, red and blue bytes, as SPI sends them: three bits each of theirs (0 as 100, 1 as 110)."""
    return SPI_LUT[np.frombuffer(bytes(grb), dtype=np.uint8)].tobytes()


def from_spi(data):
    """What spi_bytes made, back as the bytes it was made from (for the tests)."""
    bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8)).reshape(-1, 3)
    return np.packbits(bits[:, 1].reshape(-1, 8)).tobytes()


class Strip:
    """The LEDs, through the Pi's SPI (its MOSI, GPIO 10, to the grid's DIN)."""

    def __init__(self, path=SPI_DEV, hz=SPI_HZ):
        self.fd = os.open(path, os.O_WRONLY)
        for req, value in ((SPI_IOC_WR_MODE, struct.pack("B", 0)), (SPI_IOC_WR_BITS_PER_WORD, struct.pack("B", 8)),
                           (SPI_IOC_WR_MAX_SPEED_HZ, struct.pack("I", hz))):
            try:
                fcntl.ioctl(self.fd, req, value)
            except OSError as ex:                      # (a plain file, as the tests have it: just written to)
                if ex.errno != errno.ENOTTY:
                    os.close(self.fd)
                    raise

    def show(self, grb):
        os.write(self.fd, spi_bytes(grb) + RESET)

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass


class Grid:
    """An LED grid behind the TV, lit by your Pietatos (by this one too): a game's colours, music's beats, a hit's red
    and an achievement's gold. named(address): who's there (one of yours, by name; THIS_ONE for this one; None: not
    one of yours, so not listened to). follow: ANY (whichever of yours is playing: the one it's following, till it's
    quiet a moment), THIS_ONE, one of yours by name, or NOBODY. With nothing lighting it: its own colour (an RGB, or
    "rainbow"), or dark (None). Lit RATE times a second, its colours smoothed, as bright as `bright` lets them (and
    LEDs' brightness made to look even); turned, mirrored and in zigzag rows to suit how it's put up and wired
    (test(): its top row red, its left side green, its top left white, so you can tell). Or a strip round the TV
    (set_strip): each of its LEDs lit as the grid's edge nearest it would be."""

    def __init__(self, strip, named, port=GLOW_PORT, clock=time.monotonic, cols=GLOW_W, rows=GLOW_H, listen=True,
                 run=True):
        self.strip, self.named, self.clock = strip, named, clock
        self.cols, self.rows = cols, rows
        self.lock = threading.Lock()
        self.writing = threading.Lock()               # (the LEDs written to by one at a time: never once it's shut)
        self.bright, self.turn, self.mirror, self.zigzag, self.follow, self.beat = 0.25, 0, True, False, ANY, True
        self.colour = None                            # its own colour, with nothing else lighting it (None: dark)
        self.source = None                            # the address it follows now
        self.heard = {}                               # address -> when last heard (this one's clock)
        self.offsets = {}                             # address -> its packets' (heard - sent), lately
        self.target = np.zeros((rows, cols, 3))       # the last picture's colours
        self.shown = np.zeros((rows, cols, 3))        # ...as they are now, on their way there
        self.music = None
        self.frame_at = self.music_at = -1e9
        self.events = []                              # (when it shows, this one's clock; what; how much)
        self.test_until = 0.0
        self.last_t = None
        self.sent, self.sent_at = None, -1e9
        self.seen, self.changed_at = None, -1e9       # its colours as last lit (as they're seen), and when they changed
        self.on_strip = None                          # a strip's LEDs: (where each is round the TV, how its colour
                                                      # comes from the grid's), or None: the grid itself
        self.dark_to = STRIP_MOST                     # LEDs to send dark past its own (whatever was lit before it)
        self.closed = False
        self.sock = None
        if listen:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(("", port))
            self.port = self.sock.getsockname()[1]
            threading.Thread(target=self.listen, daemon=True, name="glow-in").start()
        if run:
            threading.Thread(target=self.run, daemon=True, name="glow-out").start()

    # -- what's heard ----------------------------------------------------------------------------------------------
    def listen(self):
        while not self.closed:
            try:
                data, (ip, _) = self.sock.recvfrom(4096)
            except OSError:
                if self.closed:
                    break
                time.sleep(0.1)
                continue
            try:
                self.take(data, ip, self.clock())
            except Exception as ex:                    # (never the listener's end)
                print(f"glow: {ex!r}", flush=True)

    def follows(self, who):
        if self.follow == NOBODY:
            return False
        if self.follow == ANY:
            return True
        return who == self.follow

    def take(self, data, ip, now):
        """A packet from ip, heard at now: True if it's one this grid shows."""
        p = read_packet(data)
        if p is None:
            return False
        who = self.named(ip)
        if who is None or not self.follows(who):
            return False
        with self.lock:
            if self.source != ip:
                if self.source is not None and now - self.heard.get(self.source, -1e9) < HOLD:
                    return False                       # (another's being followed: it's still playing)
                self.source = ip
            self.heard[ip] = now
            off = self.offsets.setdefault(ip, collections.deque(maxlen=OFFSET_KEEP))
            off.append(now - p["sent"])
            if p["kind"] == "frame":
                c = p["colours"]
                if c.shape != self.target.shape:
                    c = np.array([[c[r * c.shape[0] // self.rows, k * c.shape[1] // self.cols]
                                   for k in range(self.cols)] for r in range(self.rows)])
                self.target, self.frame_at = c, now
            elif p["kind"] == "music":
                self.music, self.music_at = p["rgb"], now
            elif p["kind"] == "event":
                if p["name"] == "beat" and not self.beat:
                    return True
                at = p["at"] + min(off)               # (its clock as this one's: the quickest packet's difference)
                self.events = [e for e in self.events if now - e[0] < 3.0] + [(max(at, now - 0.05), p["name"],
                                                                               p["strength"])]
        return True

    # -- lighting it ---------------------------------------------------------------------------------------------------
    def test(self, secs=8.0):
        """Its top row red, its left side green and its top left white, a few seconds: which way's which."""
        self.test_until = self.clock() + secs

    def render(self, now):
        """The grid's colours now, as they're seen from in front of the TV (rows x cols x 3, 0 to 255)."""
        with self.lock:
            if now < self.test_until:
                img = np.zeros((self.rows, self.cols, 3))
                img[:, 0] = (0, 255, 0)
                img[0, :] = (255, 0, 0)
                img[0, 0] = (255, 255, 255)
                return img
            dt = 0.0 if self.last_t is None else max(0.0, min(0.5, now - self.last_t))
            self.last_t = now
            lit = self.follow != NOBODY                # (nobody's games: just its own colour)
            if lit and now - self.frame_at < FADE_AFTER:
                goal, tau = self.target, TAU
            elif lit and self.music is not None and now - self.music_at < FADE_AFTER:
                goal, tau = np.broadcast_to(self.music * MUSIC_BASE, self.shown.shape), TAU * 3
            elif isinstance(self.colour, str):
                goal, tau = rainbow(self.rows, self.cols, now, wheel=self.on_strip is not None), COLOUR_TAU
            elif self.colour is not None:
                goal, tau = np.broadcast_to(np.array(self.colour, dtype=float), self.shown.shape), COLOUR_TAU
            else:
                goal, tau = np.zeros_like(self.shown), FADE_TAU
            self.shown += (goal - self.shown) * (1 - math.exp(-dt / tau))
            img = self.shown.copy()
            for at, name, s in self.events:
                age = now - at
                if age < 0:
                    continue
                if name == "beat":
                    p = s * math.exp(-age / BEAT_TAU)
                    img = img * (1 + BEAT_GAIN * p) + 60 * p
                elif name == "hit" and age < HIT_SECS:
                    r = s * (1 - age / HIT_SECS) ** 2
                    img = img * (1 - r) + RED * r
                elif name == "cheevo" and age < GOLD_SECS:
                    g = 1 - age / GOLD_SECS
                    twinkle = np.array(random.Random(int(at * 1000) + int(age * 12)).choices((0.55, 1.0),
                                       k=self.rows * self.cols)).reshape(self.rows, self.cols, 1)
                    img = img * (1 - g) + GOLD * g * twinkle
            self.events = [e for e in self.events if now - e[0] < 3.0]
        return img.clip(0, 255)

    def set_strip(self, n, start="Bottom left", clockwise=True, bottom=True):
        """A strip of n LEDs round the TV (strip_points), not the grid."""
        points = strip_points(max(STRIP_LEAST, min(STRIP_MOST, int(n))), start, clockwise, bottom)
        self.dark_to = max(self.dark_to, self.count())   # (the LEDs it had lit, past its new end: dark)
        self.on_strip = (points, strip_weights(points, self.cols, self.rows))

    def set_grid(self):
        """The grid itself again."""
        self.dark_to = max(self.dark_to, self.count())
        self.on_strip = None

    def count(self):
        """Its LEDs."""
        got = self.on_strip
        return self.rows * self.cols if got is None else len(got[0])

    def lit(self):
        """A strip's LEDs as they're lit now, as they're seen (brightness aside): (where each is round the TV, n x 2,
        0 to 1 across and down; their colours, n x 3, 0 to 255), or None (the grid: picture() is it as it's lit)."""
        got, seen = self.on_strip, self.seen
        if got is None or seen is None:
            return None
        return got[0], got[1] @ seen.reshape(-1, 3)

    def leds(self, img):
        """A picture of the grid (as seen from in front) as the LEDs take it: as bright as it's set, evened out for the
        eye, turned and mirrored as it's put up, each LED's green, red and blue, in the order they're wired (a strip's:
        each of its LEDs as the grid's edge nearest it, in the order they go round)."""
        got = self.on_strip
        if got is not None:
            a = got[1] @ img.reshape(-1, 3)
            a = ((a / 255.0).clip(0, 1) ** GAMMA * 255.0 * self.bright).round().clip(0, 255).astype(np.uint8)
            return a[:, [1, 0, 2]].tobytes()
        a = ((img / 255.0) ** GAMMA * 255.0 * self.bright).round().clip(0, 255).astype(np.uint8)
        if self.mirror:
            a = a[:, ::-1]
        a = np.rot90(a, -(self.turn // 90) % 4)
        if self.zigzag:
            a = a.copy()
            a[1::2] = a[1::2, ::-1]
        return a[..., [1, 0, 2]].tobytes()

    def frame(self, now):
        """The grid lit as it is now (again now and then, even if it's the same: an LED that missed it gets it)."""
        img = self.render(now)
        if self.seen is None or np.abs(img - self.seen).max() >= 1.0:
            self.changed_at = now
        self.seen = img
        data = self.leds(img)
        n = len(data) // 3
        if self.dark_to > n:                           # (LEDs past its end that were lit, by it or before it: dark)
            data += bytes(3 * (self.dark_to - n))
        if data != self.sent or now - self.sent_at > 0.5:
            self.sent, self.sent_at = data, now
            with self.writing:
                if not self.closed:
                    self.strip.show(data)
                    self.dark_to = n

    def run(self):
        while not self.closed:
            try:
                self.frame(self.clock())
            except OSError as ex:                      # (the SPI gone wrong: tried again in a moment)
                print(f"glow: the LEDs: {ex}", flush=True)
                time.sleep(2.0)
            time.sleep(1 / RATE)

    def picture(self):
        """Its colours as last lit, as they're seen from in front (rows x cols x 3, 0 to 255; brightness aside), or
        None before it's been lit: for its picture on the screen (Apps > LED backlight) and on the web page."""
        return self.seen

    def lively(self, now):
        """Its colours are changing (a game, music, a rainbow, a colour coming in): its picture's drawn again soon."""
        return now - self.changed_at < LIVELY or now < self.test_until

    def now_following(self):
        """Who it's showing now (an address), or None."""
        with self.lock:
            src = self.source
            if src is not None and self.clock() - self.heard.get(src, -1e9) < FADE_AFTER:
                return src
            return None

    def close(self):
        self.closed = True
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
        with self.writing:
            try:
                self.strip.show(bytes(max(self.dark_to, self.count()) * 3))   # (dark, as it goes)
            except OSError:
                pass
            self.strip.close()


# ---- the Pi's SPI, turned on ---------------------------------------------------------------------------------------------
CONFIG_TXT = ("/boot/firmware/config.txt", "/boot/config.txt")
BLOCK = ("# >>> pietato led grid >>>", "# <<< pietato led grid <<<")   # its part of config.txt (uninstall.sh takes it out)
PI_MODEL = "/proc/device-tree/model"


def core_clock(model, said=""):
    """The Pi's core clock (MHz), as it is when it's busy, to keep it at (its SPI's clock follows it, and the LEDs
    need that steady); None for a Pi 5, whose SPI has a clock of its own. said: vcgencmd get_config core_freq's."""
    if "Raspberry Pi 5" in model or "Compute Module 5" in model:
        return None
    m = re.search(r"core_freq=(\d+)", said or "")
    if m and int(m.group(1)) > 0:
        return int(m.group(1))
    return 500 if re.search(r"Pi 4|Pi 400|Compute Module 4", model) else 400


def spi_lines(model, said=""):
    """config.txt's lines for the grid: SPI on, and the core clock kept where it is when busy."""
    core = core_clock(model, said)
    return ["dtparam=spi=on"] + ([f"core_freq_min={core}"] if core else [])


def config_with_spi(text, lines):
    """config.txt with the grid's lines in it (its own part, at the end: an [all], so they're for every Pi), or None
    if it has them already."""
    want = "\n".join([BLOCK[0], "[all]"] + list(lines) + [BLOCK[1]])
    if BLOCK[0] in text and BLOCK[1] in text:
        start, rest = text.split(BLOCK[0], 1)
        old = BLOCK[0] + rest.split(BLOCK[1], 1)[0] + BLOCK[1]
        if old == want:
            return None
        return text.replace(old, want)
    return text.rstrip("\n") + "\n\n" + want + "\n"


def turn_spi_on(path, lines):
    """The grid's lines into config.txt (safely: written whole, then put in its place). True if it changed (the Pi
    needs restarting), False if they were there; OSError if it can't be written."""
    with open(path) as f:
        text = f.read()
    new = config_with_spi(text, lines)
    if new is None:
        return False
    tmp = path + ".pietato"
    with open(tmp, "w") as f:
        f.write(new)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return True


def glow_clean(g):
    """What another's beacon says of its LED grid ({"port", "follow", "beat"}), kept to what makes sense, or None."""
    if not isinstance(g, dict):
        return None
    port, follow = g.get("port"), g.get("follow")
    if isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536:
        return None
    follow = follow if isinstance(follow, str) and len(follow) <= 60 and not re.search(r"[\x00-\x1f]", follow) else ""
    return {"port": port, "follow": follow, "beat": g.get("beat") is True}
