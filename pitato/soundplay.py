"""The Soundboard's player (Apps > Soundboard: soundboard.py, screens/soundboard.py): a process of its own, run as you,
that plays the sounds on the buttons and records new ones. The sounds wait in memory (48 kHz, 16-bit), so a button's
sound starts at once: as many as you like at a time, mixed here into one stream for aplay, a little at a time (CHUNK)
through a pipe that holds one chunk and no more (the next is written as aplay takes that one, so this sleeps in
between, and what's mixed is next in line), and a short buffer at the sound card (BUFFERS: a longer one only once
the sound has broken up on the shorter). With nothing playing it's silence that's sent: the sound card stays open,
a TV or Bluetooth headphones stay awake, and the next sound isn't cut short at its start. A sound played again while
it plays starts again (the one playing fades out in a few ms, so there's no click); so do they all when they're
stopped. Too loud together, they're all turned down for that moment rather than left to crackle.

A WAV file at 48 kHz is read as it is; anything else (an mp3, an ogg, a WAV at another rate) goes through FFmpeg once
and is kept as it came out (the folder given on the command line), so it's there at once the next time.

Told what to do a line of JSON at a time (stdin), it says what happens the same way (stdout):

    {"do": "load", "sounds": [[name, file]...]}    the sounds there are (the ones wanted soonest first)
    {"do": "play", "id": name, "semis": 0}         one played (from its start again, if it's playing), at its own pitch
                                                   or this many semitones higher (lower: less than 0)
    {"do": "loop", "hits": [[beat, name, semis, from, beats]...], "beats": 8, "bpm": 100, "b0": 0.0, "t0": when,
     "click": true}                                the loop, played round and round: each sound at its beat of its
                                                   layer's loop, that many beats long ("beats", if it doesn't say),
                                                   from: not before that beat; at the tempo, beat b0 heard at t0
                                                   (time.monotonic()); click: a quiet tick on each beat. Without hits
                                                   or click: no loop
    {"do": "stop"}                                 all of them stopped
    {"do": "volume", "v": 0 to 100}
    {"do": "device", "device": aplay's -D}         where the sound goes ("": where ALSA would send it)
    {"do": "warm"}, {"do": "rest"}                 the sound card opened ready; let go of
    {"do": "rec", "mic": arecord's -D, "folder": where a recording's kept}
    {"do": "rec_stop", "keep": true or false}
    {"do": "quit"}                                 (or stdin closed)

    {"is": "ready", "id": name, "secs": 1.2}       a sound, read and ready
    {"is": "bad", "id": name, "why": "..."}        ...or one it can't play
    {"is": "playing", "ids": [...]}                the ones heard now, each time that changes
    {"is": "sound", "ok": false, "why": "..."}     the sound card won't open (or has gone); true: it's open
    {"is": "level", "peak": 0 to 1, "secs": 2.1}   recording: how loud just now, how long so far
    {"is": "recorded", "name": "Recording 2.wav", "secs": 1.4}    kept, its silence trimmed ("name": null: not, "why")
"""
import bisect
import collections
import fcntl
import gc
import hashlib
import importlib.util
import json
import math
import os
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import threading
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RATE = 48000
CHUNK = 384                      # frames mixed at a time (8 ms)
CHUNK_BYTES = CHUNK * 4
SILENCE = bytes(CHUNK_BYTES)
BUFFERS = ((32000, 8000), (64000, 16000), (120000, 30000))   # aplay's buffer and period (microseconds): each in turn
BREAKS = (3, 10.0)               # ...this many breaks in the sound within this many seconds: the next, longer one
TICK = 0.004                     # seconds between looks at how full aplay's pipe is, where it can't say itself
WATCH = 0.25                     # seconds between looks at whether aplay's still there
F_SETPIPE_SZ, F_GETPIPE_SZ = getattr(fcntl, "F_SETPIPE_SZ", 1031), getattr(fcntl, "F_GETPIPE_SZ", 1032)
PACED = os.environ.get("PITATO_SOUNDBOARD_PACED") != "0"   # (the tests': 0, the pipe looked at every few ms instead)
OPEN_AGAIN = 1.5                 # seconds before a sound card that wouldn't open is tried again
OPEN_LATER = (3, 6.0)            # ...after it wouldn't this many times running, this long (there may be none at all)
HEARD_AFTER = 0.06               # seconds a sound's still heard after its last was mixed (it's in the buffers)
FADE = 384                       # frames a sound takes to fade out when it's stopped or started again (8 ms)
VOICES_MOST = 16                 # sounds at a time (one more: the oldest fades out)
SECS_MOST = 30.0                 # seconds of a sound that are played
MEMORY_MOST = 64 << 20           # bytes of sounds kept ready (the ones wanted soonest)
QUIET_START = 48                 # a sound starts where it's first louder than this (of 32768): no wait before it
KEPT_MOST = (120, 160 << 20)     # sounds FFmpeg made, kept: how many, how many bytes (the oldest go)
PLAY_SOON = 1.5                  # seconds a sound asked for before it's ready is still wanted
LEVEL_EVERY = 0.08               # seconds between a recording's levels
LIMIT_BACK = 0.04                # how much of the way back to full the limiter comes, each chunk
DOWN = 24                        # frames it takes to turn everything down, when it's too loud together
LEAD_SECS = 2.0                  # seconds of writes the quickest is taken from: when a frame written is heard (one
                                 # that went straight after the one before, aplay filling its buffer, says nothing)
SEMIS_MOST = 24                  # semitones a sound's played higher or lower, at most
LOOP_HITS_MOST = 2000            # sounds in a loop, at most
CLICK_LOUD = (7000, 4500)        # how loud the loop's click is, on a bar's first beat and the others (of 32768)
PLAIN = dict(os.environ, LC_ALL="C")   # what aplay and arecord run with: what they say is read here, so in English


def soundbank():
    """soundbank.py, beside this (run with -I, this isn't in a package): WAV files, a recording's silence trimmed."""
    spec = importlib.util.spec_from_file_location("pitato_soundbank", os.path.join(HERE, "soundbank.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = soundbank()
EDGE = np.linspace(1.0, 0.0, FADE, dtype=np.float32)   # a fade out


def say(**what):
    try:
        sys.stdout.write(json.dumps(what) + "\n")
        sys.stdout.flush()
    except (OSError, ValueError):
        raise SystemExit(0)                            # (media mode's gone)


def gentler():
    """What FFmpeg, reading a sound, runs as: after everything else (this process may be before it)."""
    try:
        os.nice(15)
    except OSError:
        pass


def stop_proc(p, wait=0.4):
    if p is None:
        return
    try:
        p.terminate()
        p.wait(wait)
    except (OSError, subprocess.TimeoutExpired):
        try:
            p.kill()
            p.wait(2)
        except (OSError, subprocess.TimeoutExpired):
            pass
    for f in (p.stdin, p.stdout, p.stderr):
        try:
            if f is not None:
                f.close()
        except OSError:
            pass


# ---- a sound, read ----------------------------------------------------------------------------------------------------
def kept_path(cache, path, st):
    key = hashlib.sha1(f"{path}\0{st.st_mtime_ns}\0{st.st_size}".encode("utf-8", "surrogateescape")).hexdigest()
    return os.path.join(cache, key + ".wav")


def kept_tidy(cache):
    """The sounds FFmpeg made, kept: no more than KEPT_MOST of them (the ones used longest ago go)."""
    try:
        files = []
        for n in os.listdir(cache):
            p = os.path.join(cache, n)
            if n.endswith((".wav", ".part")) and os.path.isfile(p):
                st = os.stat(p)
                files.append((st.st_mtime, st.st_size, p))
    except OSError:
        return
    files.sort(reverse=True)
    count = size = 0
    for _, n, p in files:
        count, size = count + 1, size + n
        if count > KEPT_MOST[0] or size > KEPT_MOST[1] or p.endswith(".part"):
            try:
                os.remove(p)
            except OSError:
                pass


def through_ffmpeg(path):
    """A sound as FFmpeg reads it: 48 kHz, two channels, SECS_MOST of it at most. None: it can't (or isn't there).
    It's read as what its name says it is (a .mp3 as an mp3): a file that's really a list of others is no sound."""
    kind = {".wav": "wav", ".mp3": "mp3", ".ogg": "ogg"}.get(os.path.splitext(path)[1].lower())
    if kind is None:
        return None
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe", "-f", kind, "-i", path,
           "-vn", "-sn", "-dn", "-t", str(SECS_MOST), "-ac", "2", "-ar", str(RATE), "-f", "s16le", "pipe:1"]
    try:
        got = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             timeout=90, preexec_fn=gentler)
    except (OSError, subprocess.SubprocessError):
        return None
    data = got.stdout[:len(got.stdout) - len(got.stdout) % 4]
    if not data:
        return None
    return np.frombuffer(data, dtype="<i2").reshape(-1, 2)


def at_rate(rate, x):
    """A sound at another rate, at 48 kHz (plainly: the way without FFmpeg)."""
    n = int(len(x) * RATE / rate)
    if n < 1 or len(x) < 2:
        return None
    t = np.arange(n, dtype=np.float64) * (rate / RATE)
    was = np.arange(len(x), dtype=np.float64)
    cols = [np.interp(t, was, x[:, c]) for c in range(min(2, x.shape[1]))]
    return np.clip(np.round(np.stack(cols, axis=1)), -32768, 32767).astype(np.int16)


def tidy(x):
    """A sound ready to play: one row of samples if its two channels are the same (half the memory), starting where
    it's first heard (a button's sound shouldn't begin with a wait), SECS_MOST of it at most, its very end faded (a
    file that just stops would click)."""
    if x.ndim == 2 and x.shape[1] == 1:
        x = x[:, 0]
    elif x.ndim == 2 and x.shape[1] > 2:
        x = x[:, :2]
    if x.ndim == 2 and np.array_equal(x[:, 0], x[:, 1]):
        x = x[:, 0]
    loud = np.abs(x.astype(np.int32)) > QUIET_START
    if loud.ndim == 2:
        loud = loud.any(axis=1)
    first = int(np.argmax(loud)) if loud.any() else len(x)
    x = x[max(0, first - RATE // 1000):int(SECS_MOST * RATE) + max(0, first - RATE // 1000)]
    if len(x) < RATE // 200:
        raise ValueError("there's no sound in it")
    x = np.array(x, dtype=np.int16, order="C")        # (its own, to change: the end faded)
    n = min(len(x) // 2, RATE // 400)                  # 2.5 ms
    edge = np.linspace(1.0, 0.0, n, dtype=np.float32)
    x[-n:] = (x[-n:] * (edge if x.ndim == 1 else edge[:, None])).astype(np.int16)
    return x


def read_sound(path, cache):
    """A file's sound, ready to play. ValueError, OSError: it can't be."""
    st = os.stat(path)
    if not 0 < st.st_size <= B.SOUND_BYTES:
        raise ValueError("it's too big" if st.st_size else "it's empty")
    plain = None
    if path.lower().endswith(".wav"):
        try:
            rate, x = B.read_wav(path, most=SECS_MOST + 5)
            if rate == RATE and x.shape[1] <= 2:
                return tidy(x)
            plain = (rate, x)
        except (ValueError, OSError):
            pass
    kept = kept_path(cache, path, st) if cache else None
    if kept:
        try:
            rate, x = B.read_wav(kept)
            if rate == RATE and len(x):
                os.utime(kept)                         # (used just now)
                return tidy(x)
        except (ValueError, OSError):
            pass
    x = through_ffmpeg(path)
    if x is None and plain is not None:
        x = at_rate(*plain)
    if x is None or not len(x):
        raise ValueError("it can't be read")
    x = tidy(x)
    if kept:
        try:
            os.makedirs(cache, exist_ok=True)
            B.write_wav(kept, x)
        except OSError:
            pass
    return x


# ---- the sound card: aplay ----------------------------------------------------------------------------------------------
class Out:
    """aplay, fed through a pipe that holds a chunk and no more: what's mixed is next in line, and is heard a buffer
    later. The pipe is a page long, which for the kernel is one piece: full with one chunk in it, and ready to be
    written to again once aplay has taken that chunk (paced: select says so, and nothing has to keep looking).
    Where it can't be made that short, how full it is is looked at every few ms instead."""
    more = ()                                          # (what else aplay's asked: bandplay.py's asks what it was given)

    def __init__(self, device, level=0):
        self.device, self.level = device, level
        self.breaks = []                               # when the sound broke up (aplay says: it ran dry)
        self.said = ""                                 # the last thing aplay said
        self.left = b""
        self.gone = False                              # a write failed for good: aplay's stopped
        buffer, period = BUFFERS[level]
        cmd = ["aplay", "-q", "-t", "raw", "-f", "S16_LE", "-c", "2", "-r", str(RATE), f"--buffer-time={buffer}",
               f"--period-time={period}"] + list(self.more) + (["-D", device] if device else [])
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                  bufsize=0, env=PLAIN)
        self.fd, self.err = self.p.stdin.fileno(), self.p.stderr.fileno()
        self.paced = False
        try:
            page = os.sysconf("SC_PAGE_SIZE")
            fcntl.fcntl(self.fd, F_SETPIPE_SZ, page)
            self.paced = CHUNK_BYTES <= fcntl.fcntl(self.fd, F_GETPIPE_SZ) <= page and PACED
        except (OSError, ValueError):
            pass
        os.set_blocking(self.fd, False)
        os.set_blocking(self.err, False)
        self.started = self.looked = time.monotonic()

    def fill(self):
        """Bytes waiting in the pipe (None: it can't say)."""
        try:
            return struct.unpack("i", fcntl.ioctl(self.fd, termios.FIONREAD, b"\0\0\0\0"))[0]
        except (OSError, TypeError, ValueError):
            return None

    def write(self, data):
        """True: taken. False: not now (the pipe's full), or never again (gone)."""
        try:
            return os.write(self.fd, data) == len(data)
        except BlockingIOError:
            return False
        except OSError:
            self.gone = True
            return False

    def alive(self):
        return not self.gone and self.p.poll() is None

    def hear(self, now):
        """What aplay says (it only speaks when something's wrong): kept, and each time the sound ran dry counted.
        True: it has broken up often enough lately for a longer buffer."""
        try:
            data = os.read(self.err, 4096)
        except (BlockingIOError, OSError):
            return False
        lines = (self.left + data).split(b"\n")
        self.left = lines.pop()[-200:]
        for line in lines:
            text = line.decode("utf-8", "replace").strip()
            if text:
                self.said = text[-160:]
            if self.broke(line):
                self.breaks.append(now)
        self.breaks = [t for t in self.breaks if now - t <= BREAKS[1]]
        return len(self.breaks) >= BREAKS[0] and self.level + 1 < len(BUFFERS)

    def broke(self, line):
        """A line aplay said: True if it says the sound ran dry."""
        return b"underrun" in line.lower() or b"xrun" in line.lower()

    def why(self):
        """Why it stopped, in aplay's words (the last of them)."""
        try:
            data = os.read(self.err, 4096)
        except (BlockingIOError, OSError):
            data = b""
        lines = [ln.strip() for ln in (self.left + data).decode("utf-8", "replace").splitlines() if ln.strip()]
        return (lines[-1] if lines else self.said)[-160:]

    def close(self):
        stop_proc(self.p)


class Voice:
    """A sound, playing: where it's got to, and how much of its fade out is left (None: it isn't fading); how many
    frames of the next chunk go by before it starts (a loop's sound, at its very frame); how fast it's played (a
    note: 2 ** (semitones / 12)), and how loud (1: as it is)."""
    __slots__ = ("id", "data", "pos", "fade", "wait", "rate", "gain", "shown")

    def __init__(self, sid, data, wait=0, rate=1.0, gain=1.0):
        self.id, self.data, self.pos, self.fade = sid, data, 0, None
        self.wait, self.rate, self.gain, self.shown = wait, rate, gain, True


def click_sound(accent):
    """The loop's click: a short tick, higher on a bar's first beat."""
    t = np.arange(int(0.012 * RATE)) / RATE
    x = np.sin(2 * np.pi * (2400.0 if accent else 1600.0) * t) * np.exp(-t / 0.0025)
    return (x * CLICK_LOUD[0 if accent else 1]).astype(np.int16)


def loop_from(c):
    """What a "loop" says, checked: its layers' sounds, by how long a loop each goes round in ([(beats, hits sorted by
    beat, their beats)]), the tempo, beat b0 and when it's heard (t0), and the click. None: no loop."""
    try:
        beats, bpm = float(c.get("beats")), float(c.get("bpm"))
        b0, t0 = float(c.get("b0")), float(c.get("t0"))
    except (TypeError, ValueError):
        return None
    if not (1 <= beats <= 64 and 20 <= bpm <= 300 and math.isfinite(b0) and math.isfinite(t0)):
        return None
    hits = c.get("hits")
    groups = {}
    for h in (hits if isinstance(hits, list) else ())[:LOOP_HITS_MOST]:
        try:
            p, sid, semis, after = float(h[0]), h[1], int(h[2]), float(h[3])
            n = float(h[4]) if len(h) > 4 else beats
        except (TypeError, ValueError, IndexError):
            continue
        if (isinstance(sid, str) and 1 <= n <= 64 and 0 <= p < n and abs(semis) <= SEMIS_MOST
                and math.isfinite(after)):
            groups.setdefault(n, []).append((p, sid, semis, after))
    click = c.get("click") is True
    if not groups and not click:
        return None
    out = []
    for n, hs in sorted(groups.items()):
        hs.sort(key=lambda h: h[0])
        out.append((n, hs, [h[0] for h in hs]))
    return {"groups": out, "bpm": bpm, "b0": b0, "t0": t0, "click": click}


# ---- the player ---------------------------------------------------------------------------------------------------------
class Player:
    card = Out                                         # (how it plays: aplay, as above)

    def __init__(self, cache):
        self.cache = cache
        self.out = None
        self.device, self.level = "", 0
        self.resting = True                            # the sound card's let go of (till a sound's played, or "warm")
        self.tried = -1e9                              # when it last wouldn't open
        self.fails = 0                                 # ...and how many times running
        self.ok = None                                 # what's been said of it
        self.voices = []
        self.gain = 205                                # the volume, of 256
        self.limit = 1.0                               # ...and how far everything's turned down, too loud together
        self.acc = np.zeros((CHUNK, 2), dtype=np.int32)
        self.heard = {}                                # a sound just over -> till when it's still heard
        self.said_playing = []
        self.lock = threading.Condition()
        self.want = []                                 # [(name, file)], the ones wanted soonest first
        self.sounds = {}                               # name -> (its file as it was read: path, when, size; samples)
        self.bad = {}                                  # name -> (its file as it was, why)
        self.news = []                                 # what the reader has to say (the main loop says it)
        self.soon = {}                                 # a sound asked for before it's ready -> when
        self.fresh = False                             # the sounds wanted have changed (the reader looks again)
        self.stale = True                              # which sounds are playing may have changed (said if so)
        self.wrote = False                             # a chunk's been written since select last said there was room
        self.rec = None
        self.fed = 0                                   # frames written to aplay since it opened: the loop's clock
        self.wrote_at = None                           # ...and when the last chunk was
        self.lead = collections.deque()                # (when, when its first frame was written) the quickest lately
        self.base = None                               # ...and so when aplay's first frame is heard (monotonic)
        self.loop = None                               # the loop (loop_from), played round and round
        self.clicks = (click_sound(True), click_sound(False))
        self.ramp = np.arange(CHUNK, dtype=np.float64)
        self.buf = b""
        self.done = False
        self.wake_r, self.wake_w = os.pipe()
        os.set_blocking(self.wake_r, False)
        os.set_blocking(self.wake_w, False)
        threading.Thread(target=self.reader, daemon=True, name="sounds").start()

    # -- the sounds, read as they're wanted (a thread of its own: playing doesn't wait for it) ------------------------
    def reader(self):
        if self.cache:
            kept_tidy(self.cache)
        while True:
            with self.lock:
                while not self.fresh:
                    self.lock.wait()
                self.fresh = False
                want = list(self.want)
                names = {sid for sid, _ in want}
                for sid in [s for s in self.sounds if s not in names]:
                    del self.sounds[sid]               # (no longer wanted: let go of)
                for sid in [s for s in self.bad if s not in names]:
                    del self.bad[sid]
            used = 0
            for sid, path in want:                     # (the ones wanted soonest first, while there's memory for them)
                try:
                    st = os.stat(path)
                    key = (path, st.st_mtime_ns, st.st_size)
                except OSError:
                    key = (path, 0, 0)
                with self.lock:
                    if self.fresh:
                        break                          # (told anew meanwhile: from the top, in that order)
                    have, bad = self.sounds.get(sid), self.bad.get(sid)
                    if have is not None and (have[0] != key or used >= MEMORY_MOST):
                        del self.sounds[sid]           # (its file's changed: read again. Or there's no room for it)
                        have = None
                if have is not None:
                    used += have[1].nbytes
                    continue
                if used >= MEMORY_MOST or (bad is not None and bad[0] == key):
                    continue
                try:
                    data, why = self.read(path), None
                except (ValueError, OSError) as ex:
                    data = None
                    why = (ex.strerror if isinstance(ex, OSError) and ex.strerror else str(ex)) or "it can't be read"
                except Exception as ex:                # (never the reader's end)
                    data, why = None, repr(ex)[:80]
                with self.lock:
                    if (sid, path) not in self.want:
                        continue
                    if data is None:
                        self.bad[sid] = (key, why)
                        self.news.append({"is": "bad", "id": sid, "why": why})
                    else:
                        used += data.nbytes
                        self.bad.pop(sid, None)
                        self.sounds[sid] = (key, data)
                        self.news.append({"is": "ready", "id": sid, "secs": round(len(data) / RATE, 2)})
                self.poke()

    def read(self, path):
        """(The reader's.) A sound's samples, from what it was told is its file (bandplay.py: or what it's made of)."""
        return read_sound(path, self.cache)

    def poke(self):
        try:
            os.write(self.wake_w, b"x")
        except OSError:
            pass

    # -- the sound card -------------------------------------------------------------------------------------------------
    def sound(self, ok, why=""):
        """Said, when it changes: the sound card's open (why: its buffer's ms, and whether its pipe's paced), or
        isn't (why not)."""
        if self.ok != (ok, why):
            self.ok = (ok, why)
            say(**({"is": "sound", "ok": True, "buffer": why[0], "paced": why[1]} if ok
                   else {"is": "sound", "ok": False, "why": why}))

    def open(self, now, force=False):
        """The sound card opened, if it isn't (and wasn't tried a moment ago). True: it's open."""
        if self.out is not None:
            return True
        if not force and now - self.tried < (OPEN_AGAIN if self.fails < OPEN_LATER[0] else OPEN_LATER[1]):
            return False
        self.resting = False
        try:
            self.out = self.card(self.device, self.level)
        except OSError as ex:
            self.tried, self.fails = now, self.fails + 1
            self.sound(False, f"aplay: {ex.strerror or ex}")
            return False
        self.fed, self.base, self.wrote_at = 0, None, None
        self.lead.clear()
        return True

    def close(self):
        out, self.out = self.out, None
        if out is not None:
            out.close()
        self.limit = 1.0

    def watch(self, now, spoke=False):
        """The sound card as it is: gone (it wouldn't open, or was unplugged), said, and tried again every so often
        while it's wanted; the sound breaking up (spoke: aplay has something to say), a longer buffer."""
        out = self.out
        if out is None:
            if not self.resting:
                self.open(now)
            return
        out.looked = now
        if not out.alive():
            why = out.why()
            self.close()
            self.tried, self.fails = now, self.fails + 1
            self.voices = []
            self.soon.clear()
            self.stale = True
            self.sound(False, why or "the sound stopped")
            return
        if spoke and out.hear(now):
            self.level += 1
            self.close()
            self.open(now, force=True)
            return
        if now - out.started > 0.35:
            self.fails = 0
            self.sound(True, (BUFFERS[out.level][0] // 1000, out.paced))

    def feed(self, room=False):
        """The next chunk mixed and written, if aplay's pipe is ready for it: empty, when it's paced (room: select
        said it could be written to); less than half a chunk in it, when it isn't."""
        out = self.out
        if out is None:
            return
        n = out.fill()
        if out.paced:
            if n:
                if room:                               # (room, with a chunk still in it: not the pipe it was taken
                    out.paced = False                  # for. How full it is is looked at instead, from here on)
                return
        elif n is None or n >= CHUNK_BYTES // 2:
            return
        if out.write(self.mix()):
            self.wrote = True
            self.heard_from(time.monotonic(), out)
            self.took(out)

    def took(self, out):
        """A chunk's been written (bandplay.py keeps count: how fast aplay takes them is how it keeps time)."""

    def heard_from(self, now, out):
        """A chunk's been written: when aplay's first frame is heard, from the quickest of the writes lately that
        waited for aplay to take the one before (one written late, the Pi busy, says nothing of when it's heard; nor
        does one aplay took at once, filling its buffer). aplay takes a chunk, waits a period for room for it, and
        it's heard its buffer after that."""
        if self.wrote_at is not None and now - self.wrote_at >= CHUNK / RATE / 2:
            v = now - self.fed / RATE
            lead = self.lead
            while lead and lead[-1][1] >= v:
                lead.pop()
            lead.append((now, v))
            while lead[0][0] < now - LEAD_SECS:
                lead.popleft()
            buffer, period = BUFFERS[out.level]
            self.base = lead[0][1] + (buffer + period) / 1e6
        self.wrote_at = now
        self.fed += CHUNK

    def loop_due(self):
        """The loop's sounds (and its clicks) heard in the chunk about to be mixed: started at their very frames."""
        lp = self.loop
        if lp is None or self.base is None or self.rec is not None:
            return
        per = lp["bpm"] / 60.0
        ta = self.base + self.fed / RATE
        ba = lp["b0"] + (ta - lp["t0"]) * per
        bb = ba + CHUNK / RATE * per
        for n, hits, at in lp["groups"]:
            k = math.floor(ba / n)
            for kk in (k, k + 1):                      # (a chunk can go over the loop's end)
                lo, hi = ba - kk * n, bb - kk * n
                if hi <= 0 or lo >= n:
                    continue
                i = bisect.bisect_left(at, max(lo, 0.0))
                while i < len(hits) and at[i] < hi:
                    p, sid, semis, after = hits[i]
                    beat = kk * n + p
                    if beat >= after:
                        have = self.sounds.get(sid)
                        if have is not None:
                            self.start(sid, have[1], semis, wait=int((beat - ba) / per * RATE), shown=False)
                    i += 1
        if lp["click"]:
            beat = math.ceil(ba)
            if beat < bb:
                self.start(None, self.clicks[0 if beat % 4 == 0 else 1], 0, wait=int((beat - ba) / per * RATE))

    def start(self, sid, data, semis=0, wait=0, shown=True):
        """A sound started (the same one playing: it fades out as this one starts), at a pitch of its own, so many
        frames into the next chunk. Not shown: a loop's (not said to be playing: its button isn't lit for it, as the
        page would be drawn for every sound of the loop's)."""
        for v in self.voices:
            if v.id == sid and v.fade is None:
                v.fade = FADE
        v = Voice(sid, data, max(0, min(CHUNK - 1, wait)), 2.0 ** (semis / 12.0) if semis else 1.0)
        v.shown = shown and sid is not None
        self.voices.append(v)
        live = [v for v in self.voices if v.fade is None]
        for v in live[:max(0, len(live) - VOICES_MOST)]:
            v.fade = FADE
        if shown and sid is not None:
            self.heard.pop(sid, None)
            self.stale = True

    def mix(self):
        """The next chunk: the sounds playing, added up (silence, with none)."""
        self.loop_due()
        if not self.voices:
            self.limit = 1.0
            return SILENCE
        acc = self.acc
        acc[:] = 0
        going = []
        for v in self.voices:
            o = 0
            if v.wait:                                 # (a loop's sound: it starts so far into the chunk)
                o, v.wait = v.wait, 0
            room = CHUNK - o
            if v.rate == 1.0:
                seg = v.data[v.pos:v.pos + room]
                m = len(seg)
            else:                                      # (a note: the sound played faster or slower)
                idx = v.pos + self.ramp[:room] * v.rate
                m = int(np.searchsorted(idx, len(v.data) - 1))
                i0 = idx[:m].astype(np.int64)
                fr = (idx[:m] - i0).astype(np.float32)
                x0, x1 = v.data[i0].astype(np.float32), v.data[i0 + 1].astype(np.float32)
                seg = x0 + (x1 - x0) * (fr if x0.ndim == 1 else fr[:, None])
            if v.fade is not None:
                m = min(m, v.fade)
                edge = EDGE[FADE - v.fade:FADE - v.fade + m]
                seg = seg[:m] * (edge if seg.ndim == 1 else edge[:, None])
                v.fade -= m
            if v.gain != 1.0:
                seg = seg[:m] * v.gain
            if m:
                seg = seg[:m].astype(np.int32) if seg.dtype.kind == "f" else seg[:m]
                if seg.ndim == 1:
                    acc[o:o + m] += seg[:, None]
                else:
                    acc[o:o + m] += seg
            v.pos += m if v.rate == 1.0 else m * v.rate
            if v.pos < len(v.data) - (0 if v.rate == 1.0 else 1) and (v.fade is None or v.fade > 0) and m:
                going.append(v)
        if len(going) != len(self.voices):
            self.voices, self.stale = going, True
        if self.gain != 256:
            acc *= self.gain
            acc >>= 8
        peak = max(int(acc.max()), -int(acc.min()))
        was = self.limit
        fits = 1.0 if peak <= 32767 else 32700.0 / peak
        now = min(fits, was + (1.0 - was) * LIMIT_BACK) if fits >= was else fits
        self.limit = 1.0 if now > 0.999 else now
        if was < 1.0 or now < 1.0:                     # (too loud together: turned down, and slowly back up)
            ramp = np.full(CHUNK, now, dtype=np.float32)
            if now < was:
                ramp[:DOWN] = np.linspace(was, now, DOWN, dtype=np.float32)   # (down at once, without a click)
            else:
                ramp[:] = np.linspace(was, now, CHUNK, dtype=np.float32)
            acc = (acc * ramp[:, None]).astype(np.int32)
            np.clip(acc, -32767, 32767, out=acc)
        return acc.astype("<i2").tobytes()

    def play(self, sid, now, semis=0):
        with self.lock:
            have = self.sounds.get(sid)
            if have is None and sid in dict(self.want) and sid not in self.bad:
                self.soon[sid] = now                   # (not read yet: played as soon as it is, if that's soon)
        if have is None:
            return
        self.soon.pop(sid, None)
        if self.out is None and not self.open(now, force=now - self.tried >= 0.3):
            return                                     # (the sound card won't open: not played later, out of the blue)
        self.start(sid, have[1], semis)                # (playing: that one fades out as this one starts)
        self.feed()

    def stop_all(self, now):
        for v in self.voices:
            if v.fade is None:
                v.fade = FADE
        self.soon.clear()
        self.stale = True

    def playing(self, now):
        """The sounds heard now, said when they change (one that's just ended is still in the buffers a moment)."""
        self.stale = False
        live = {v.id for v in self.voices if v.fade is None and v.shown} if self.out is not None else set()
        for sid in self.said_playing:
            if sid not in live and sid not in self.heard:
                self.heard[sid] = now + HEARD_AFTER
        for sid in [s for s, t in self.heard.items() if now >= t or s in live]:
            del self.heard[sid]
        ids = sorted(live | set(self.heard))
        if ids != self.said_playing:
            self.said_playing = ids
            say(**{"is": "playing", "ids": ids})

    # -- recording ------------------------------------------------------------------------------------------------------
    def rec_start(self, mic, folder, now):
        if self.rec is not None:
            return
        self.stop_all(now)
        cmd = ["arecord", "-q", "-f", "S16_LE", "-r", str(RATE), "-c", "1", "-t", "raw"] + (["-D", mic] if mic else [])
        err = tempfile.TemporaryFile()                 # (a file, not a pipe: arecord says something at every overrun)
        try:
            p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=err, bufsize=0,
                                 env=PLAIN)
        except OSError as ex:
            err.close()
            say(**{"is": "recorded", "name": None, "why": "mic", "said": f"arecord: {ex.strerror or ex}"})
            return
        os.set_blocking(p.stdout.fileno(), False)
        self.rec = {"p": p, "err": err, "fd": p.stdout.fileno(), "parts": [], "bytes": 0, "odd": b"", "folder": folder,
                    "t0": now, "peak": 0, "level_at": now}

    def rec_read(self, now):
        r = self.rec
        try:
            data = os.read(r["fd"], 65536)
        except BlockingIOError:
            return
        except OSError:
            data = b""
        if not data:                                   # (arecord's stopped: the microphone's gone, or wouldn't open)
            self.rec_end(r["bytes"] > RATE // 2, now, gone=True)
            return
        data = r["odd"] + data
        r["odd"] = data[len(data) - len(data) % 2:]
        data = data[:len(data) - len(data) % 2]
        if not data:
            return
        r["parts"].append(data)
        r["bytes"] += len(data)
        x = np.frombuffer(data, dtype="<i2")
        r["peak"] = max(r["peak"], int(x.max()), -int(x.min()))
        if now - r["level_at"] >= LEVEL_EVERY:
            say(**{"is": "level", "peak": round(min(1.0, r["peak"] / 32768.0), 3), "secs": round(r["bytes"] / (2 * RATE), 2)})
            r["peak"], r["level_at"] = 0, now
        if r["bytes"] >= int(B.REC_MOST * RATE) * 2:
            self.rec_end(True, now)

    def rec_end(self, keep, now, gone=False):
        """The recording's over: kept (its silence trimmed, a file in your Soundboard folder), or not."""
        r, self.rec = self.rec, None
        if r is None:
            return
        stop_proc(r["p"])
        said = ""
        try:
            r["err"].seek(0)
            lines = [ln.strip() for ln in r["err"].read().decode("utf-8", "replace").splitlines() if ln.strip()]
            said = lines[-1][-160:] if lines else ""
        except (OSError, ValueError):
            pass
        r["err"].close()
        if not keep:
            say(**{"is": "recorded", "name": None, "why": "mic" if gone else "dropped", "said": said})
            return
        x = np.frombuffer(b"".join(r["parts"]), dtype="<i2")
        y = B.trimmed(x, RATE)
        if y is None or len(y) < RATE // 10:
            say(**{"is": "recorded", "name": None, "why": "quiet"})
            return
        try:
            os.makedirs(r["folder"], exist_ok=True)
            name = B.recording_name(os.listdir(r["folder"]))
            B.write_wav(os.path.join(r["folder"], name), y)
        except OSError as ex:
            say(**{"is": "recorded", "name": None, "why": "file", "said": ex.strerror or str(ex)})
            return
        say(**{"is": "recorded", "name": name, "secs": round(len(y) / RATE, 2)})

    # -- what it's told ---------------------------------------------------------------------------------------------------
    def told(self, c, now):
        do = c.get("do")
        if do == "play":
            semis = c.get("semis", 0)
            if isinstance(c.get("id"), str) and self.rec is None and type(semis) is int and abs(semis) <= SEMIS_MOST:
                self.play(c["id"], now, semis)
        elif do == "loop":
            self.loop = loop_from(c)
        elif do == "stop":
            self.stop_all(now)
        elif do == "load":
            want = [(s[0], s[1]) for s in c.get("sounds") or ()
                    if isinstance(s, (list, tuple)) and len(s) == 2 and all(isinstance(v, str) for v in s)]
            names = {s for s, _ in want}
            for v in self.voices:
                if v.id not in names and v.fade is None:
                    v.fade = FADE                      # (one that's gone, playing: it fades out)
                    self.stale = True
            with self.lock:
                self.want, self.fresh = want, True
                self.lock.notify_all()
        elif do == "volume":
            try:
                self.gain = max(0, min(256, int(round(float(c.get("v", 80)) * 256 / 100))))
            except (TypeError, ValueError):
                pass
        elif do == "device":
            device = c.get("device") if isinstance(c.get("device"), str) else ""
            if device != self.device:
                was_open = self.out is not None
                self.close()
                self.device, self.level, self.tried, self.ok, self.fails = device, 0, -1e9, None, 0
                if was_open:
                    self.open(now, force=True)
        elif do == "warm":
            self.resting = False
            self.open(now)
        elif do == "rest":
            self.resting = True
            self.voices = []
            self.soon.clear()
            self.close()
            self.ok, self.stale = None, True
        elif do == "rec":
            if isinstance(c.get("folder"), str) and c["folder"]:
                self.rec_start(c.get("mic") if isinstance(c.get("mic"), str) else "", c["folder"], now)
        elif do == "rec_stop":
            self.rec_end(c.get("keep") is not False, now)
        elif do == "quit":
            self.done = True

    def read_told(self, now):
        try:
            data = os.read(0, 65536)
        except BlockingIOError:
            return
        except OSError:
            data = b""
        if not data:
            self.done = True                           # (media mode's gone, or done with this)
            return
        lines = (self.buf + data).split(b"\n")
        self.buf = lines.pop()[-65536:]
        for line in lines:
            try:
                c = json.loads(line)
            except ValueError:
                continue
            if isinstance(c, dict):
                self.told(c, now)

    def read_news(self, now):
        try:
            os.read(self.wake_r, 4096)
        except (BlockingIOError, OSError):
            pass
        with self.lock:
            news, self.news = self.news, []
        for n in news:
            say(**n)
            if n["is"] == "ready" and now - self.soon.pop(n["id"], -1e9) <= PLAY_SOON:
                self.play(n["id"], now)

    def run(self):
        os.set_blocking(0, False)
        while not self.done:
            out = self.out
            reads = [0, self.wake_r]
            if self.rec is not None:
                reads.append(self.rec["fd"])
            if out is not None:
                reads.append(out.err)
            paced = out is not None and out.paced
            wait = WATCH if paced else TICK if out is not None else 1.0
            if self.heard:
                wait = max(0.0, min(wait, min(self.heard.values()) - time.monotonic()))
            try:
                ready, room, _ = select.select(reads, (out.fd,) if paced else (), (), wait)
            except (OSError, ValueError):
                ready, room = reads, ()
            self.wrote = False
            if room and not self.voices and not ready and not self.heard and not self.stale:
                self.feed(True)                        # (nothing playing: silence, and that's all there is to do)
                if out.gone or time.monotonic() - out.looked >= WATCH:
                    self.watch(time.monotonic())
                continue
            now = time.monotonic()
            if 0 in ready:
                self.read_told(now)
            if self.wake_r in ready:
                self.read_news(now)
            if self.rec is not None and self.rec["fd"] in ready:
                self.rec_read(now)
            spoke = out is not None and out.err in ready
            if spoke or out is None or out.gone or now - out.looked >= WATCH:
                self.watch(now, spoke)
            self.feed(bool(room) and not self.wrote and self.out is out)
            if self.stale or self.heard:
                self.playing(now)
        if self.rec is not None:
            self.rec_end(False, time.monotonic())
        self.close()


def main():
    cache = sys.argv[1] if len(sys.argv) > 1 else ""
    gc.disable()                                       # (nothing here goes round in circles, and a pause would be heard)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    player = Player(cache)
    try:
        player.run()
    finally:
        if player.rec is not None:
            stop_proc(player.rec["p"])
        player.close()


if __name__ == "__main__":
    main()
