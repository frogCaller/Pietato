"""Party mode: each of your Pietatos that's on plays the same song or station at once, in step, through its own speaker.
The one it's started on leads. The others' clocks are set against its own first, as NTP sets a clock: a few pings, the
quickest answer the nearest (clock_offset, ClockServer). Then each song starts "at time T" by the leader's clock, from
the same place in it, on all of them. A song of yours: each takes it from the leader's web page as it plays; a station:
the leader takes it once and passes it on byte for byte (Relay, RelayServer), so all of them play the same bytes from
the same one on. Each one decodes it with FFmpeg as soon as it's told, then plays it through aplay so its first sound
comes out at T, and keeps it in step with the leader's clock from then on (a speaker's clock runs a little fast or slow:
now and then a sample's let go of, or said twice). screens/party.py starts it, and tells the others what to play."""
import collections
import fcntl
import json
import os
import queue
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

from .util import UA

PARTY_PORT = 5446            # the leader's clock (UDP) and the station it passes on (TCP)
PARTY_LEAD = 2.5             # seconds from a song being started to its playing (each one's ready by then)
PARTY_PINGS = 12             # pings to the leader's clock: the quickest answer's used
PARTY_RATE = 48000           # samples a second, as it's played (two channels, 16 bits each)
FRAME = 4                    # bytes a sample takes
PARTY_OUT = (100000, 20000)  # aplay's buffer and its period, in microseconds (the same on each one: as late, alike)
PARTY_PIPE = 0.04            # seconds of sound waiting in aplay's pipe, kept
PARTY_STEP = 0.01            # seconds between looks at how it's keeping up
PARTY_SLACK = 0.002          # seconds out of step before it's put right...
PARTY_FIX = 48               # ...a millisecond's samples at a time (let go of, or said again)
PARTY_JUMP = 0.05            # ...or, this far out, all at once
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


class PartyPlayer:
    """One song or station, played in step with the leader's clock. src: a file, or a web address (the leader's web page,
    or the station it passes on); at: when it plays, by the leader's clock; pos: from where in it (seconds); clock: the
    leader's clock now (this one's, less the offset its pings found: it can change). FFmpeg decodes it at once (as you:
    pre and you, as_you's); aplay plays it, its first sound at that time, the rest kept in step: where it is in it is a
    sum of the clock from then on (paused: as it was, till it plays on)."""

    def __init__(self, src, at, pos=0.0, device="", volume=80, clock=None, pre=(), you=None):
        self.src, self.pos0 = src, max(0.0, float(pos or 0))
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
        self.last = bytes(FRAME)                       # ...the last of them (said again, to wait a moment)
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
        latency = PARTY_OUT[0] / 1e6                   # (aplay's buffer, kept full: what's written is heard that late)
        want_fill = int(PARTY_PIPE * PARTY_RATE) * FRAME
        while not self.closed:
            a = self.aplay
            if a is None or a.poll() is not None:      # (no sound out: tried again a moment later)
                time.sleep(0.2)
                if not self.closed:
                    self.start_aplay()
                continue
            fd = a.stdin.fileno()
            fill = pipe_fill(fd) or 0
            n = (want_fill - fill) // FRAME            # samples to write now
            if n > 0:
                head = self.clock() + fill / FRAME / PARTY_RATE + latency   # (when the next one written is heard)
                data = self.next_out(head, n)
                try:
                    os.write(fd, data)
                except BlockingIOError:
                    pass
                except OSError:
                    try:
                        a.kill()
                    except OSError:
                        pass
            time.sleep(PARTY_STEP)

    def next_out(self, head, n):
        """n samples to write, the first heard at head (the leader's clock): silence till it starts (and while it's
        paused), then the song, a little let go of or said again to keep it where the clock says it should be."""
        out = bytearray()
        with self.lock:
            while len(out) < n * FRAME:
                t = head + len(out) / FRAME / PARTY_RATE
                want = self.sample_at(t)
                left = n - len(out) // FRAME
                if want is None:                       # (silence: till it starts, or plays on, or for the rest)
                    at = self.anchor[0] if self.stop_at is None else None
                    k = left if at is None or at <= t else min(left, max(1, int((at - t) * PARTY_RATE)))
                    out += bytes(k * FRAME)
                    continue
                err = want - self.next                 # (+: behind the clock; -: ahead of it)
                if abs(err) > PARTY_JUMP * PARTY_RATE or (self.played == 0 and err):
                    fix = err                          # (far out, or its very start: put right at once)
                elif abs(err) > PARTY_SLACK * PARTY_RATE:
                    fix = max(-PARTY_FIX, min(PARTY_FIX, err))
                else:
                    fix = 0
                if fix > 0:                            # (behind: those let go of)
                    have = len(self.pcm) // FRAME
                    drop = min(fix, have)
                    del self.pcm[:drop * FRAME]
                    self.next += drop
                    if drop < fix and not self.decoded:   # (not decoded yet: what's due is let go of as it comes)
                        out += bytes(left * FRAME)
                        break
                elif fix < 0:                          # (ahead: the last sound said again, a little longer, while
                    k = min(-fix, left)                #  the clock catches up with where it is in it)
                    out += (bytes(out[-FRAME:]) if len(out) >= FRAME else self.last) * k
                    continue
                left = n - len(out) // FRAME
                take = min(left, len(self.pcm) // FRAME)
                if take <= 0:
                    if self.decoded:                   # (the end: its last sound's heard then)
                        if self.done_at is None:
                            self.done_at = t
                        out += bytes(left * FRAME)
                        break
                    out += bytes(left * FRAME)         # (not decoded yet: silence, and it catches up after)
                    break
                chunk = bytes(self.pcm[:take * FRAME])
                del self.pcm[:take * FRAME]
                self.next += take
                self.played += take
                if self.volume < 100:
                    a = np.frombuffer(chunk, dtype="<i2")
                    chunk = ((a.astype(np.int32) * int(self.volume * 256 // 100)) >> 8).astype("<i2").tobytes()
                out += chunk
                self.last = chunk[-FRAME:]
        return bytes(out[:n * FRAME])

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

    def __init__(self, player, title="", artist="", length=None, lead=False):
        self.player, self.lead = player, lead
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
