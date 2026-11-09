"""Party mode: each of your Pietatos that's on plays the same song or station at once, in step, through its own speaker.
The one it's started on leads. The others' clocks are set against its own first, as NTP sets a clock: a few pings, the
quickest answer the nearest (clock_offset, ClockServer). Then each song starts "at time T" by the leader's clock, from
the same place in it, on all of them. A song of yours: each takes it from the leader's web page as it plays; a station:
the leader takes it once and passes it on byte for byte (Relay, RelayServer), so all of them play the same bytes from
the same one on. Each one decodes it with FFmpeg as soon as it's told, then plays it through aplay so its first sound
comes out at T, and keeps it in step with the leader's clock from then on (a speaker's clock runs a little fast or slow:
now and then it's played a hair faster or slower, for a moment). screens/party.py starts it, and tells the others what
to play."""
import collections
import fcntl
import json
import os
import queue
import random
import socket
import struct
import subprocess
import termios
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

from .glow import Beats
from .util import UA

PARTY_PORT = 5446            # the leader's clock (UDP) and the station it passes on (TCP)
PARTY_LEAD = 2.5             # seconds from a song being started to its playing (each one's ready by then)
PARTY_PINGS = 12             # pings to the leader's clock: the quickest answer's used
PARTY_RATE = 48000           # samples a second, as it's played (two channels, 16 bits each)
FRAME = 4                    # bytes a sample takes
PARTY_OUT = (100000, 20000)  # aplay's buffer and its period, in microseconds (the same on each one: as late, alike)
PARTY_PIPE = 0.04            # seconds of sound waiting in aplay's pipe, kept (more when this one's busy: half again
PARTY_PIPE_MOST = 0.25       # as long as it's lately been kept from looking, up to this, so aplay never runs out)
PARTY_STEP = 0.01            # seconds between looks at how it's keeping up
PARTY_FIT = 4.0              # seconds of how much aplay had taken when that a straight line's drawn through: when it'll
                             # take what's written next (it takes a period at a time: a look at a moment can be a period
                             # out either way; the line goes through the middle of them)
PARTY_SETTLE = 0.4           # seconds how far out of step it is is worked out over, from that
PARTY_SLACK = 0.002          # seconds out of step before it's put right (2 ms: as far as sound goes in 70 cm): played
PARTY_EVEN = 0.0004          # a little faster or slower till it's this near
PARTY_NEAR = 0.0008          # ...or this far out for PARTY_WAIT seconds on end (a sound card that keeps time: still
PARTY_WAIT = 3.0             # as near to the clock as the rest)
PARTY_TRIM = 0.003           # ...at most this much faster or slower (0.3%: too little to hear)
PARTY_PULL = 2.0             # ...a second out: this much faster or slower (and as much less for less)
PARTY_JUMP = 0.05            # ...or, this far out, all at once (faded across: no click)
PARTY_FADE = 0.005           # seconds a sound fades in after silence, or out into a pause
PARTY_DECODED = 30.0         # seconds of sound decoded ahead, at most
PARTY_KEEP = 4 << 20         # bytes of a station the leader keeps, to pass on (a few minutes of it)
PARTY_BEHIND = 3.0           # seconds of a station a start is from, behind the newest that's come (each one's ready)


# ---- the leader's clock ---------------------------------------------------------------------------------------------
class ClockServer:
    """The leader's clock, for the others: a ping with the party's key is answered at once, with this one's clock
    (time.monotonic()) and the ping's own time, so the one that sent it can tell how long it took."""

    def __init__(self, token, port=PARTY_PORT, clock=time.monotonic):
        self.token, self.clock = token, clock
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("", port))
        self.port = self.sock.getsockname()[1]
        self.closed = False
        threading.Thread(target=self.serve, daemon=True, name="party-clock").start()

    def serve(self):
        while not self.closed:
            try:
                data, addr = self.sock.recvfrom(512)
            except OSError:
                if self.closed:
                    break
                time.sleep(0.05)
                continue
            now = self.clock()
            try:
                msg = json.loads(data.decode())
                t0 = msg.get("t0")
                if msg.get("token") != self.token or isinstance(t0, bool) or not isinstance(t0, (int, float)):
                    continue
                self.sock.sendto(json.dumps({"t0": t0, "t": now}).encode(), addr)
            except (ValueError, AttributeError, OSError):
                continue

    def close(self):
        self.closed = True
        try:
            self.sock.close()
        except OSError:
            pass


def clock_offset(host, port, token, n=PARTY_PINGS, timeout=0.3):
    """The leader's clock less this one's (both time.monotonic()), as near as the quickest of n pings says: (the
    offset, how long that ping took to come back), or None when none came back."""
    best = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    except OSError:
        return None
    with s:
        s.settimeout(timeout)
        for _ in range(n):
            t0 = time.monotonic()
            try:
                s.sendto(json.dumps({"token": token, "t0": t0}).encode(), (host, port))
                while True:                            # (a late answer to an earlier ping: not this one's)
                    data, _ = s.recvfrom(512)
                    t1 = time.monotonic()
                    msg = json.loads(data.decode())
                    if isinstance(msg, dict) and msg.get("t0") == t0:
                        break
            except (OSError, ValueError):
                continue
            t = msg.get("t")
            if isinstance(t, bool) or not isinstance(t, (int, float)):
                continue
            rtt = t1 - t0
            if best is None or rtt < best[1]:
                best = (t - (t0 + t1) / 2, rtt)
            time.sleep(0.005)
    return best


# ---- a station, passed on ------------------------------------------------------------------------------------------
class Relay:
    """A station, taken once by the leader and passed on, byte for byte, to each of yours (and to its own player): each
    starts from the same byte, so each plays the same sound at once. The song titles some stations send in with the
    sound (ICY) are taken out of it, and the latest kept (song). The last PARTY_KEEP bytes are kept."""

    def __init__(self, url, keep=PARTY_KEEP, timeout=10.0):
        self.url, self.keep, self.timeout = url, keep, timeout
        self.cond = threading.Condition()
        self.buf, self.first, self.total = bytearray(), 0, 0   # what's kept; the byte it starts at; all that's come
        self.song, self.kind, self.rate = "", "audio/mpeg", 0  # its latest title; what it is; bytes a second
        self.began = None
        self.gone = None
        self.closed = False
        self.resp = None
        threading.Thread(target=self.run, daemon=True, name="party-relay").start()

    def run(self):
        try:
            req = urllib.request.Request(self.url, headers=dict(UA, **{"Icy-MetaData": "1"}))
            self.resp = resp = urllib.request.urlopen(req, timeout=self.timeout)
            every = int(resp.headers.get("icy-metaint") or 0)
            self.kind = (resp.headers.get("Content-Type") or "audio/mpeg").split(";")[0].strip() or "audio/mpeg"
            try:
                self.rate = int(str(resp.headers.get("icy-br") or "0").split(",")[0]) * 1000 // 8
            except ValueError:
                self.rate = 0
            while not self.closed:
                if every:
                    data = self.read(resp, every)
                    n = self.read(resp, 1)[0] * 16
                    if n:
                        self.title(self.read(resp, n))
                else:
                    data = resp.read(8192)
                    if not data:
                        raise OSError("the station ended")
                self.add(data)
        except Exception as ex:                        # (whatever it is: the station's gone)
            with self.cond:
                self.gone = str(ex) or type(ex).__name__
                self.cond.notify_all()

    @staticmethod
    def read(resp, n):
        out = bytearray()
        while len(out) < n:
            chunk = resp.read(n - len(out))
            if not chunk:
                raise OSError("the station ended")
            out += chunk
        return bytes(out)

    def title(self, meta):
        text = meta.rstrip(b"\0").decode("utf-8", "replace")
        start = text.find("StreamTitle='")
        if start >= 0:
            end = text.find("';", start + 13)
            song = text[start + 13:end if end >= 0 else len(text)].strip()
            if song:
                self.song = song[:200]

    def add(self, data):
        with self.cond:
            now = time.monotonic()
            if self.began is None:
                self.began = now
            self.buf += data
            self.total += len(data)
            if len(self.buf) > self.keep:
                cut = len(self.buf) - self.keep
                del self.buf[:cut]
                self.first += cut
            if now - self.began > 4 and self.total > 32768:   # (how fast it comes, once it's been coming a while)
                measured = int(self.total / (now - self.began))
                self.rate = measured if not self.rate else (self.rate * 7 + measured) // 8
            self.cond.notify_all()

    def ready(self, timeout):
        """It's coming (some bytes are here), waited for up to timeout seconds: True; or False (it isn't: gone)."""
        end = time.monotonic() + timeout
        with self.cond:
            while not self.total and self.gone is None:
                left = end - time.monotonic()
                if left <= 0:
                    break
                self.cond.wait(left)
            return self.total > 0

    def start_byte(self, behind=PARTY_BEHIND):
        """Where a start is from: a few seconds behind the newest byte that's come (all of yours have it at once)."""
        with self.cond:
            back = int(behind * (self.rate or 16000))
            return max(self.first, self.total - back)

    def take(self, at, timeout=5.0):
        """The bytes from at on that have come (waited for, up to timeout seconds, if none has yet): (them, where the
        next ones start), or (b"", at) when none came (or it's gone)."""
        end = time.monotonic() + timeout
        with self.cond:
            at = max(at, self.first)                   # (too far behind: from the oldest one kept)
            while self.total <= at and self.gone is None and not self.closed:
                left = end - time.monotonic()
                if left <= 0:
                    return b"", at
                self.cond.wait(left)
            data = bytes(self.buf[at - self.first:])
            return data, at + len(data)

    def close(self):
        self.closed = True
        try:
            if self.resp is not None:
                self.resp.close()
        except Exception:
            pass
        with self.cond:
            self.cond.notify_all()


class RelayServer(ThreadingHTTPServer):
    """The leader's station, for the others to play (and its own player): GET /station?token=...&from=BYTE gives it
    from that byte on, as it comes, for as long as it's taken. Only with the party's key."""
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, token, port=PARTY_PORT):
        self.token, self.relay = token, None
        super().__init__(("", port), RelayHandler)
        self.port = self.server_address[1]
        threading.Thread(target=self.serve_forever, daemon=True, name="party-relay-server").start()

    def close(self):
        try:
            self.shutdown()
            self.server_close()
        except OSError:
            pass


class RelayHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        q = urllib.parse.parse_qs(u.query)
        relay = self.server.relay
        try:
            at = int((q.get("from") or ["0"])[0])
        except ValueError:
            at = -1
        if u.path != "/station" or (q.get("token") or [""])[0] != self.server.token or relay is None or at < 0:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", relay.kind)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            while self.server.relay is relay and not relay.closed:
                data, at = relay.take(at)
                if not data:
                    if relay.gone is not None:
                        break
                    continue
                self.wfile.write(data)
                self.wfile.flush()
        except OSError:
            pass


# ---- playing it, in step ----------------------------------------------------------------------------------------------
def pipe_fill(fd):
    """Bytes waiting in a pipe (None: can't tell)."""
    try:
        return struct.unpack("i", fcntl.ioctl(fd, termios.FIONREAD, b"\0\0\0\0"))[0]
    except (OSError, TypeError, ValueError):
        return None


class Pace:
    """How fast aplay's taking the sound, and when it'll take a given sample: a straight line through how much it had
    taken when, over the last PARTY_FIT seconds (from a moment after it starts: it fills its buffer at once first),
    drawn again every tenth of a second."""

    def __init__(self, start):
        self.start = start + PARTY_OUT[0] / 1e6 + 0.15
        self.seen = collections.deque()
        self.line = None                               # (t0, taken then, from where on the line, samples a second)
        self.drawn = 0.0

    def add(self, t, taken):
        if t < self.start:
            return
        self.seen.append((t, taken))
        while self.seen[0][0] < t - PARTY_FIT:
            self.seen.popleft()
        if t - self.drawn >= 0.1:
            self.drawn = t
            self.line = self.draw()

    def draw(self):
        """The line through them, once there's enough of them and it's a likely one (as fast as the usual rate, near
        enough); else None."""
        if len(self.seen) < 20 or self.seen[-1][0] - self.seen[0][0] < 0.3:
            return None
        ts = np.fromiter((p[0] for p in self.seen), dtype=np.float64, count=len(self.seen))
        cs = np.fromiter((p[1] for p in self.seen), dtype=np.float64, count=len(self.seen))
        x, y = ts - ts[0], cs - cs[0]
        xm, ym = x.mean(), y.mean()
        rate = float(((x - xm) * (y - ym)).sum() / max(((x - xm) ** 2).sum(), 1e-12))
        if not 0.98 * PARTY_RATE < rate < 1.02 * PARTY_RATE:
            return None
        return float(ts[0]), float(cs[0]), float(ym - rate * xm), rate

    def when(self, sample, t, taken):
        """When aplay takes sample (counted from its start), by this one's clock: from the line, if there is one; else
        from how much it's taken now, at the usual rate."""
        if self.line is not None:
            t0, c0, base, rate = self.line
            if abs(c0 + base + rate * (t - t0) - taken) < 3 * PARTY_OUT[1] / 1e6 * PARTY_RATE:
                return t0 + (sample - c0 - base) / rate
            self.seen.clear()                          # (it stopped a moment, or jumped: a new line from here)
            self.line = None
        return t + (sample - taken) / PARTY_RATE


class PartyPlayer:
    """One song or station, played in step with the leader's clock. src: a file, or a web address (the leader's web page,
    or the station it passes on); at: when it plays, by the leader's clock; pos: from where in it (seconds); clock: the
    leader's clock now (this one's, less the offset its pings found: it can change). FFmpeg decodes it at once (as you:
    pre and you, as_you's); aplay plays it, its first sound at that time, the rest kept in step: where it is in it is a
    sum of the clock from then on (paused: as it was, till it plays on)."""

    def __init__(self, src, at, pos=0.0, device="", volume=80, clock=None, pre=(), you=None, on_beat=None):
        self.src, self.pos0 = src, max(0.0, float(pos or 0))
        self.beats = Beats(PARTY_RATE, on_beat) if on_beat is not None else None   # (an LED grid's: glow.py)
        self.clock = clock or time.monotonic
        self.device, self.volume = device, volume
        self.lock = threading.Lock()
        self.pcm = bytearray()                         # decoded, not played yet
        self.next = 0                                  # ...the sample (from pos0) its first is
        self.decoded = False                           # FFmpeg's done (the rest is here)
        self.anchor = (float(at), 0)                   # (the leader's clock, the sample it plays at): on from there
        self.stop_at = None                            # (when it pauses, the sample it pauses on): paused from then
        self.done_at = None                            # when its last sound plays (the leader's clock), once it's known
        self.played = 0                                # samples written to aplay of it (not silence)
        self.x = 0.0                                   # where it is: a fraction of a sample on from self.next
        self.drift = None                              # how far out of step it is, worked out over a while (samples:
                                                       # + behind the clock, - ahead of it)
        self.trim = 1.0                                # samples taken for each one played (a little more or less:
                                                       # faster or slower, to put it right)
        self.landing = False                           # ...put right: on to a whole sample again, smoothly
        self.off_since = None                          # ...when it was last more than PARTY_NEAR out (and still is)
        self.fade = 0                                  # samples left of a fade in (after silence, or a jump)
        self.xfade = None                              # ...what it was playing before a jump (and how much of it's
                                                       #  gone): faded out as it goes on
        self.until = None                              # ...ahead after a jump: silence till then (the leader's clock)
        self.closed = False
        self.aplay = None
        args = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error"]
        if self.pos0 > 0:
            args += ["-ss", f"{self.pos0:.3f}"]        # (from there: as quick on a Pi, and the same on each one)
        args += ["-i", src, "-vn", "-ac", "2", "-ar", str(PARTY_RATE), "-f", "s16le", "-"]
        self.ffmpeg = subprocess.Popen(list(pre) + args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL, bufsize=0, **(you or {}))
        self.start_aplay()
        threading.Thread(target=self.decode, daemon=True, name="party-decode").start()
        threading.Thread(target=self.play, daemon=True, name="party-play").start()

    # -- the sound out -----------------------------------------------------------------------------------------------
    def start_aplay(self):
        cmd = ["aplay", "-q", "-t", "raw", "-f", "S16_LE", "-c", "2", "-r", str(PARTY_RATE),
               f"--buffer-time={PARTY_OUT[0]}", f"--period-time={PARTY_OUT[1]}"]
        if self.device:
            cmd += ["-D", self.device]
        try:
            self.aplay = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL, bufsize=0)
            os.set_blocking(self.aplay.stdin.fileno(), False)
        except OSError:
            self.aplay = None

    def set_device(self, device):
        """Its sound elsewhere now (Bluetooth headphones came, or went): aplay again, there; it stays in step."""
        if device == self.device:
            return
        self.device = device
        old = self.aplay
        self.start_aplay()
        if old is not None:
            try:
                old.stdin.close()
            except OSError:
                pass
            old.kill()

    def set_volume(self, v):
        self.volume = max(0, min(100, v))

    # -- decoding ---------------------------------------------------------------------------------------------------
    def decode(self):
        out = self.ffmpeg.stdout
        while not self.closed:
            with self.lock:
                full = len(self.pcm) >= PARTY_DECODED * PARTY_RATE * FRAME
            if full:
                time.sleep(0.05)
                continue
            try:
                data = out.read(16384)
            except (OSError, ValueError):
                data = b""
            if not data:
                break
            with self.lock:
                self.pcm += data
        with self.lock:
            self.decoded = True

    # -- the timeline --------------------------------------------------------------------------------------------------
    def sample_at(self, t):
        """The sample to be heard at t (the leader's clock), or None for silence then (before it starts; paused)."""
        at, s = self.anchor
        if self.stop_at is not None and t >= self.stop_at[0]:
            return None
        if t < at:
            return None
        return s + int(round((t - at) * PARTY_RATE))

    def position(self):
        """Where in it what's heard now is (seconds)."""
        t = self.clock()
        with self.lock:
            s = self.sample_at(t)
            if s is None:
                s = self.stop_at[1] if self.stop_at is not None and t >= self.stop_at[0] else self.anchor[1]
        return self.pos0 + max(0, s) / PARTY_RATE

    def paused(self):
        return self.stop_at is not None and self.clock() >= self.stop_at[0]

    def pause_at(self, t):
        """Paused at t (the leader's clock), on the sample heard then."""
        with self.lock:
            s = self.sample_at(t)
            if s is not None:
                self.stop_at = (float(t), s)

    def resume_at(self, t):
        """Played on at t (the leader's clock), from the sample it paused on."""
        with self.lock:
            if self.stop_at is not None:
                self.anchor, self.stop_at = (float(t), self.stop_at[1]), None

    def done(self):
        """Its last sound's been heard (a song's end: the leader goes on to the next)."""
        return self.done_at is not None and self.clock() >= self.done_at

    # -- feeding aplay ------------------------------------------------------------------------------------------------
    def play(self):
        latency = PARTY_OUT[0] / 1e6                   # (aplay's buffer, kept full: what it takes is heard that late)
        was, pending, sent, pace = None, b"", 0, None
        last, away = None, 0.0                         # (when it last looked; the longest between looks, lately)
        while not self.closed:
            a = self.aplay
            if a is None or a.poll() is not None:      # (no sound out: tried again a moment later)
                time.sleep(0.2)
                if not self.closed:
                    self.start_aplay()
                continue
            if a is not was:                           # (a new aplay: how fast it takes it, from the start)
                was, pending, sent, pace = a, b"", 0, Pace(time.monotonic())
            fd = a.stdin.fileno()
            t0 = time.monotonic()
            fill = pipe_fill(fd) or 0
            now = time.monotonic()
            away = max(now - last if last is not None else 0.0, away * 0.998)
            last = now
            want_fill = int(min(PARTY_PIPE_MOST, max(PARTY_PIPE, away * 1.5)) * PARTY_RATE) * FRAME
            taken = (sent - fill) / FRAME              # (samples aplay's taken so far)
            if now - t0 < 0.002:                       # (a look that took a while, kept waiting: not on the line)
                pace.add((t0 + now) / 2, taken)
            n = (want_fill - fill - len(pending)) // FRAME   # samples to write now
            if n > 0:
                first = (sent + len(pending)) / FRAME  # (the first of them: when aplay takes it, and it's heard then)
                head = pace.when(first, now, taken) + latency + (self.clock() - time.monotonic())
                data = self.next_out(head, n)
                if self.beats is not None:             # (its beats, as they'll be heard: your TV backlight's)
                    try:
                        self.beats.feed(data, head)
                    except Exception as ex:
                        print(f"party: no beats ({ex!r})", flush=True)
                        self.beats = None
                pending += data
            if pending:                                # (all of it, in order: what the pipe can't take yet, next time)
                try:
                    k = os.write(fd, pending)
                except BlockingIOError:
                    k = 0
                except OSError:
                    k = 0
                    try:
                        a.kill()
                    except OSError:
                        pass
                sent += k
                pending = pending[k:]
            time.sleep(PARTY_STEP * (0.5 + random.random()))   # (never in time with aplay's own gulps: its line's
                                                               #  through the middle of them, not one side)

    def next_out(self, head, n):
        """n samples to write, the first heard at head (the leader's clock): silence till it starts (and while it's
        paused), then the song, kept where the clock says it should be: played a fraction faster or slower when it's
        out of step (worked out over a while), all at once only when it's far out (or at its start)."""
        out = []                                       # (pieces: each samples x 2, floats)
        rate = PARTY_RATE
        with self.lock:
            i = 0
            measured = False
            while i < n:
                t = head + i / rate
                left = n - i
                if self.until is not None and t < self.until:   # (ahead, after a jump: silence till the clock's there)
                    k = min(left, max(1, int(np.ceil((self.until - t) * rate))))
                    out.append(np.zeros((k, 2), dtype=np.float32))
                    i += k
                    continue
                self.until = None
                want = self.sample_at(t)
                if want is None:                       # (silence: till it starts, or plays on, or for the rest)
                    at = self.anchor[0] if self.stop_at is None else None
                    k = left if at is None or at <= t else min(left, max(1, int((at - t) * rate)))
                    out.append(np.zeros((k, 2), dtype=np.float32))
                    i += k
                    self.fade, self.xfade = int(PARTY_FADE * rate), None   # (a fade in when it plays again)
                    continue
                if self.stop_at is not None and self.stop_at[0] > t:   # (a pause coming: up to it, this time)
                    left = min(left, max(1, int(np.ceil((self.stop_at[0] - t) * rate))))
                err = want - (self.next + self.x)      # (+: behind the clock; -: ahead of it)
                if self.played == 0 or (abs(err) > PARTY_JUMP * rate and abs(self.drift or 0.0) > PARTY_JUMP * rate / 2):
                    if self.jump(err, out, left, t):   # (far out, or its very start: put right at once)
                        break
                    i = sum(len(p) for p in out)
                    continue
                if not measured:                       # (how far out it is, worked out over a while)
                    measured = True
                    k = min(1.0, n / rate / PARTY_SETTLE)
                    self.drift = err if self.drift is None else self.drift + (err - self.drift) * k
                    self.steer(t)
                got = self.take(left)
                if got is None:                        # (nothing to play now)
                    if self.decoded and self.done_at is None:
                        self.done_at = t               # (the end: its last sound's heard then)
                    out.append(np.zeros((left, 2), dtype=np.float32))
                    break
                out.append(self.shaped(got, t))
                i += len(got)
        a = np.concatenate(out)[:n] if out else np.zeros((n, 2), dtype=np.float32)
        return np.clip(np.rint(a), -32768, 32767).astype("<i2").tobytes()

    def jump(self, err, out, left, t):
        """Put right at once: behind, what's due let go of; ahead, silence till the clock gets there. At its start, it
        fades in; in the middle, what it was playing fades out across the jump (into what's due, or the silence): no
        click. True: the rest of this is silence (it isn't decoded that far yet, or it's over)."""
        fresh = self.played == 0
        fade = int(PARTY_FADE * PARTY_RATE)
        was = None if fresh else self.peek(fade)       # (what it was about to play)
        self.x, self.drift, self.trim, self.landing, self.off_since = 0.0, 0.0, 1.0, False, None
        self.until = None
        e = int(round(err))
        if e > 0:                                      # (behind: what's due let go of)
            drop = min(e, len(self.pcm) // FRAME)
            del self.pcm[:drop * FRAME]
            self.next += drop
            if drop < e:
                if self.decoded and self.done_at is None:
                    self.done_at = t                   # (it's over: what was due is past its end)
                out.append(self.fading(was, left))     # (or not decoded yet: let go of as it comes)
                self.fade, self.xfade = fade, None
                return True
            if was is None or not len(was):
                self.fade = fade
            else:
                self.xfade = (was, 0)                  # (faded out as what's due now's faded in: take's)
        elif e < 0:                                    # (ahead: silence till the clock's there, it faded out into it)
            self.until = t - e / PARTY_RATE
            k = min(-e, left)
            out.append(self.fading(was, k))
            self.fade, self.xfade = fade, None
            return False
        elif fresh:
            self.fade = fade
        self.played = max(1, self.played)              # (in step from here)
        return False

    def peek(self, k):
        """The next k samples it'd play (fewer at its end), just as take would make them, not taken: floats."""
        have = len(self.pcm) // FRAME
        k = min(k, int((have - 2 - self.x) / self.trim) + 1) if have >= 2 else 0
        if k <= 0:
            return np.zeros((0, 2), dtype=np.float32)
        pos = self.x + self.trim * np.arange(k, dtype=np.float64)
        i0 = pos.astype(np.int64)
        f = (pos - i0).astype(np.float32)[:, None]
        src = np.frombuffer(bytes(self.pcm[:(int(i0[-1]) + 2) * FRAME]), dtype="<i2").reshape(-1, 2).astype(np.float32)
        return src[i0] * (1 - f) + src[i0 + 1] * f

    def fading(self, was, k):
        """k samples: was, faded out (as loud as it's set), then silence."""
        a = np.zeros((k, 2), dtype=np.float32)
        if was is not None and len(was) and k:
            m = min(k, len(was))
            ramp = 1.0 - np.arange(1, m + 1, dtype=np.float32) / (len(was) + 1)
            a[:m] = was[:m] * (ramp * self.volume / 100.0)[:, None]
        return a

    def steer(self, t):
        """Faster or slower, from how far out of step it is (t: when, by the leader's clock): a little, while it's more
        than PARTY_SLACK out (or PARTY_NEAR, for a while), till it's within PARTY_EVEN."""
        d = self.drift / PARTY_RATE                    # (seconds: + behind, so a little faster)
        if self.trim == 1.0:
            if abs(d) < PARTY_NEAR:
                self.off_since = None
                return
            if abs(d) < PARTY_SLACK:
                if self.off_since is None:
                    self.off_since = t
                if t - self.off_since < PARTY_WAIT:
                    return
        if abs(d) < PARTY_EVEN:
            self.landing, self.off_since = True, None  # (the next piece: as near as can be to its own speed, ending
            return                                     #  on a whole sample, then just as they are)
        self.landing = False
        self.trim = 1.0 + max(-PARTY_TRIM, min(PARTY_TRIM, d * PARTY_PULL))

    def take(self, k):
        """Up to k samples, from where it is, at self.trim of the decoded ones each (in between two: a mix of them);
        None when there are none to take."""
        have = len(self.pcm) // FRAME
        if self.trim == 1.0 and self.x == 0.0:         # (in step: just as they are)
            k = min(k, have)
            if k <= 0:
                return None
            got = np.frombuffer(bytes(self.pcm[:k * FRAME]), dtype="<i2").reshape(-1, 2).astype(np.float32)
            del self.pcm[:k * FRAME]
            self.next += k
            self.played += k
            return self.crossed(got)
        r = self.trim
        k = min(k, int((have - 2 - self.x) / r) + 1 if have >= 2 else 0)
        if k <= 0:
            return None
        if self.landing and k >= 64:                   # (ending on a whole sample: a hair faster or slower for it)
            r = (round(self.x + k) - self.x) / k
        pos = self.x + r * np.arange(k, dtype=np.float64)
        i0 = pos.astype(np.int64)
        f = (pos - i0).astype(np.float32)[:, None]
        src = np.frombuffer(bytes(self.pcm[:(int(i0[-1]) + 2) * FRAME]), dtype="<i2").reshape(-1, 2).astype(np.float32)
        got = src[i0] * (1 - f) + src[i0 + 1] * f
        end = self.x + r * k
        used = int(round(end)) if self.landing and k >= 64 else int(end)
        del self.pcm[:used * FRAME]
        self.next += used
        self.x = max(0.0, end - used)
        if self.landing and k >= 64:                   # (on a whole sample: just as they are, from here)
            self.x, self.trim, self.landing = 0.0, 1.0, False
        self.played += k
        return self.crossed(got)

    def crossed(self, got):
        """What it takes, with what it was playing before a jump faded out across the first of it (as what it takes
        fades in)."""
        if self.xfade is None:
            return got
        was, at = self.xfade
        m = min(len(was) - at, len(got))
        g = (np.arange(at + 1, at + m + 1, dtype=np.float32) / (len(was) + 1))[:, None]
        got[:m] = was[at:at + m] * (1 - g) + got[:m] * g
        at += m
        self.xfade = None if at >= len(was) else (was, at)
        return got

    def shaped(self, a, t):
        """Samples as they're heard: as loud as it's set, faded in after silence or a jump, and out into a pause that's
        coming (t: when the first is heard)."""
        gain = np.full(len(a), self.volume / 100.0, dtype=np.float32)
        if self.fade > 0:
            total = int(PARTY_FADE * PARTY_RATE)
            k = min(self.fade, len(a))
            done = total - self.fade
            gain[:k] *= (done + np.arange(1, k + 1, dtype=np.float32)) / total
            self.fade -= k
        if self.stop_at is not None:                   # (a pause on its way: faded out into it)
            stop = self.stop_at[0]
            times = t + np.arange(len(a), dtype=np.float64) / PARTY_RATE
            near = (times >= stop - PARTY_FADE) & (times < stop)
            if near.any():
                gain[near] *= ((stop - times[near]) / PARTY_FADE).astype(np.float32)
        return a * gain[:, None]

    def close(self):
        self.closed = True
        for p in (self.ffmpeg, self.aplay):
            if p is None:
                continue
            try:
                p.kill()
                p.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass


class PartyProc:
    """A PartyPlayer, as media mode's player sees mplayer (screens/player.py): lines to it (volume, how far it's got, its
    title), answers from it, and poll(). lead: the leader's (its song's end is the end: it goes on to the next); the
    others' wait for the next song from the leader."""

    def __init__(self, player, title="", artist="", length=None, lead=False, control=None):
        self.player, self.lead = player, lead
        self.control = control                         # pause, and seek: media mode's to do (all of them, in a party)
        self.title, self.artist, self.length = title, artist, length
        self.lines = queue.Queue()
        self.stdin, self.stdout, self.stderr = self, self, iter(())
        self.returncode = None
        self.args = []
        self.said = collections.deque(maxlen=12)

    # (mplayer's slave mode, as much of it as media mode says to music)
    def write(self, text):
        for line in str(text).splitlines():
            words = line.split()
            while words and words[0] in ("pausing", "pausing_keep", "pausing_toggle", "pausing_keep_force"):
                words = words[1:]
            if not words:
                continue
            c = words[0]
            if c == "quit":
                self.kill()
            elif c == "volume" and len(words) > 1:
                try:
                    self.player.set_volume(float(words[1]))
                except ValueError:
                    pass
            elif c == "get_time_pos":
                self.say(f"ANS_TIME_POSITION={self.player.position():.1f}")
            elif c == "get_time_length" and self.length:
                self.say(f"ANS_LENGTH={self.length:.1f}")
            elif c == "get_meta_title" and self.title:
                self.say(f"ANS_META_TITLE='{self.title}'")
            elif c == "get_meta_artist" and self.artist:
                self.say(f"ANS_META_ARTIST='{self.artist}'")
            elif c == "get_property" and words[1:2] == ["pause"]:
                self.say(f"ANS_pause={'yes' if self.player.paused() else 'no'}")
            elif c == "pause" and self.control is not None:
                self.control("pause", None)
            elif c == "seek" and len(words) > 1 and self.control is not None:
                try:
                    self.control("seek", (float(words[1]), int(words[2]) if len(words) > 2 else 0))
                except ValueError:
                    pass

    def flush(self):
        pass

    def say(self, line):
        self.lines.put(line + "\n")

    def __iter__(self):
        return self

    def __next__(self):
        line = self.lines.get()
        if line is None:
            self.lines.put(None)                       # (for any other reader too)
            raise StopIteration
        return line

    def poll(self):
        if self.returncode is None and (self.player.closed or (self.lead and self.player.done())):
            self.returncode = 0
            self.lines.put(None)
        return self.returncode

    def wait(self, timeout=None):
        self.kill()
        return 0

    def kill(self):
        self.player.close()
        if self.returncode is None:
            self.returncode = 0
            self.lines.put(None)

    terminate = kill


def probe(path):
    """A song's title, artist and length (seconds), as FFmpeg's ffprobe reads them: ("", "", None) when it can't."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:format_tags=title,artist",
                              "-of", "json", path], capture_output=True, text=True, timeout=5).stdout
        fmt = json.loads(out or "{}").get("format") or {}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return "", "", None
    tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}
    try:
        length = float(fmt.get("duration"))
    except (TypeError, ValueError):
        length = None
    return str(tags.get("title") or "")[:200], str(tags.get("artist") or "")[:200], length
