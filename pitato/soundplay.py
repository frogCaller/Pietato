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
    {"do": "play", "id": name, "semis": 0, "gain": 1}
                                                   one played (from its start again, if it's playing), at its own pitch
                                                   or this many semitones higher (lower: less than 0), as loud as it
                                                   is or this much of that; one of its own sounds too (Tones/Pluck)
    {"do": "loop", "hits": [[beat, name, semis, from, beats, gain]...], "beats": 8, "bpm": 100, "b0": 0.0,
     "t0": when, "click": true}                    the loop, played round and round: each sound at its beat of its
                                                   layer's loop, that many beats long ("beats", if it doesn't say),
                                                   from: not before that beat; gain: how loud, of the sound as it is
                                                   (1, if it doesn't say); at the tempo, beat b0 heard at t0
                                                   (time.monotonic()); click: a quiet tick on each beat. A name can
                                                   be one of its own sounds (Tones/Pluck: the Sequencer's lead, at
                                                   its note). Without hits or click: no loop
    {"do": "note", "id": name, "semis": 2.5, "gain": 0.8, "at": when, "pan": -0.3}
                                                   Bounce's (bounce.py): a wall's note, so many semitones from the
                                                   sound's own (Tones/Bell, Tones/Marimba...: its own sounds, made here
                                                   from middle C's), heard at when (time.monotonic(): as soon as it can
                                                   be, if that's gone by), or now without it, from the left (-1) or the
                                                   right (1); a few at a time (BOUNCE_MOST), each faded in and no
                                                   longer than BOUNCE_SECS
    {"do": "tone", "id": "Tones/Bell"}             one of its own sounds made ready (it takes a moment)
    {"do": "fx", "space": 0.4, "echo": 0.3, "tone": 0.5, "secs": 0.45}
                                                   Bounce's notes through its effects (soundfx.py), each 0 to 1: a
                                                   room round them (its reverb), an echo this far apart, and their
                                                   tone (0.5: as they are, less: darker, more: brighter)
    {"do": "drone", "level": 0.2, "note": 60}      a soft chord held under them, on that note (level 0: none)
    {"do": "space", "v": 0.3}                      the Soundboard's own sounds in a room too (its reverb), 0 to 1
    {"do": "pitch", "id": name}                    a sound's own note, as near as it can tell
    {"do": "bars", "on": true}                     the Sequencer's page is up: the sound said as bars, as it plays
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
    {"is": "pitch", "id": name, "midi": 57.3}      a sound's own note (MIDI, with its cents), or null: it hasn't one
    {"is": "bars", "v": [0 to 99, ...]}            the sound just now, how loud in each of BARS bands of notes (low
                                                   ones first), whatever the volume: twenty times a second while
                                                   there's any, then all 0 once, and no more till there is again
    {"is": "sound", "ok": false, "why": "..."}     the sound card won't open (or has gone); true: it's open
    {"is": "level", "peak": 0 to 1, "secs": 2.1}   recording: how loud just now, how long so far
    {"is": "recorded", "name": "Recording 2.wav", "secs": 1.4}    kept, its silence trimmed ("name": null: not, "why")
"""
import bisect
import collections
import fcntl
import gc
import hashlib
import heapq
import itertools
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
GAIN_MOST = 1.5                  # how loud a loop's sound or a Bounce note is played, at most (of the sound as it is)
LOOP_HITS_MOST = 2000            # sounds in a loop, at most
CLICK_LOUD = (7000, 4500)        # how loud the loop's click is, on a bar's first beat and the others (of 32768)
BOUNCE_MOST = 6                  # Bounce's notes at a time (one more: the oldest fades out), so a Pi Zero keeps up
BOUNCE_SECS = 2.5                # seconds of a Bounce note played, at most (then it fades out)
BOUNCE_LATE = 64                 # Bounce's notes waiting for their time, at most
FADE_IN = 96                     # frames a Bounce note fades in over (2 ms): no click as it starts
TONE_ROOT = 60                   # the note Bounce's own sounds are played from (MIDI: bounce.py's TONE_ROOT)
TONE_ROOTS = (48, 60, 72)        # ...each made at these, and a note played from the nearest (it sounds as it should)
DRONE_SECS = 4.0                 # its drone: a loop this long
DRONE_GLIDE = 1.0                # ...seconds it takes to come and go, or go from one key to another
DRONE_SPACE = 0.6                # ...how much of it goes into the space round the notes
DRONE_MOST = 0.8                 # ...how loud it is, all the way up (of the loop as it's made)
PITCH_HZ = (55.0, 1500.0)        # a sound's own note is looked for between these
BARS = 32                        # the Sequencer's bars: the sound just now, low notes first (sequencer.py's BARS)
BARS_WIN = 2048                  # ...frames of it each look is at (43 ms)
BARS_EVERY = 0.044               # ...seconds between looks, at least (every sixth chunk: twenty times a second)
BARS_HZ = (40.0, 12000.0)        # ...from the lowest bar's notes to the highest's
BARS_DB = (-54.0, -6.0)          # ...a bar at nothing and at its top: this far under as loud as a sound can be
PLAIN = dict(os.environ, LC_ALL="C")   # what aplay and arecord run with: what they say is read here, so in English


def beside(name):
    """A module beside this (run with -I, this isn't in a package): soundbank.py (WAV files, a recording's silence
    trimmed), soundfx.py (Bounce's effects and its own sounds)."""
    spec = importlib.util.spec_from_file_location("pitato_" + name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = beside("soundbank")
FX = beside("soundfx")
TONES = {"Tones/" + name: FX.SECS[name] for name in FX.NAMES}   # Bounce's own sounds, and how long each is
EDGE = np.linspace(1.0, 0.0, FADE, dtype=np.float32)   # a fade out
EDGE_CHUNK = np.linspace(1.0, 0.0, CHUNK, dtype=np.float32)[:, None]   # ...over a whole chunk
RISE = np.linspace(0.0, 1.0, FADE_IN, dtype=np.float32)   # a fade in


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
    __slots__ = ("id", "data", "pos", "fade", "wait", "rate", "gain", "shown", "rise", "left", "bounce", "pan")

    def __init__(self, sid, data, wait=0, rate=1.0, gain=1.0):
        self.id, self.data, self.pos, self.fade = sid, data, 0, None
        self.wait, self.rate, self.gain, self.shown = wait, rate, gain, True
        self.rise = 0                  # frames of its fade in still to come (Bounce's notes)
        self.left = None               # ...frames of it to be played before it fades out (None: all of it)
        self.bounce = False            # ...one of Bounce's (through its effects; a few at a time)
        self.pan = None                # ...how loud on the left and on the right, of gain (None: both as it is)


def click_sound(accent):
    """The loop's click: a short tick, higher on a bar's first beat."""
    t = np.arange(int(0.012 * RATE)) / RATE
    x = np.sin(2 * np.pi * (2400.0 if accent else 1600.0) * t) * np.exp(-t / 0.0025)
    return (x * CLICK_LOUD[0 if accent else 1]).astype(np.int16)


def make_tone(sid, root=TONE_ROOT):
    """One of Bounce's own sounds (Tones/Bell, Tones/Marimba...), at that note (middle C, unless it says)."""
    return FX.tone(sid[6:], root, RATE)


def pan_of(p):
    """How loud on the left and on the right, a note heard from p (-1: all left, 1: all right; 0: both as it is)."""
    p = max(-1.0, min(1.0, float(p)))
    return (1.0 - max(0.0, p), 1.0 + min(0.0, p))


def pitch_of(data):
    """A sound's own note (MIDI, with its cents) from its loudest part, or None: it hasn't a clear one (a drum, a
    noise). Where the sound most nearly repeats itself: its first such place that's nearly the best."""
    x = data.astype(np.float32)
    if x.ndim == 2:
        x = x.mean(axis=1)
    win = 4096
    if len(x) < win // 2:
        return None
    win = min(win, len(x))
    at = int(np.argmax(np.abs(x)))
    start = max(0, min(at + int(0.02 * RATE), len(x) - win))
    seg = x[start:start + win]
    seg = (seg - seg.mean()) * np.hanning(len(seg))
    if np.max(np.abs(seg)) < 300:
        return None
    f = np.fft.rfft(seg, 2 * len(seg))
    ac = np.fft.irfft(f * np.conj(f))[:len(seg)]
    if ac[0] <= 0:
        return None
    ac = ac / ac[0]
    lo, hi = int(RATE / PITCH_HZ[1]), min(int(RATE / PITCH_HZ[0]), len(seg) - 2)
    if hi <= lo + 2:
        return None
    best = float(np.max(ac[lo:hi]))
    if best < 0.55:
        return None
    lag = next((k for k in range(lo + 1, hi) if ac[k] >= 0.85 * best and ac[k] >= ac[k - 1] and ac[k] >= ac[k + 1]),
               None)
    if lag is None:                                    # (its best at the edge: lower than a note's looked for)
        return None
    a, b, c = ac[lag - 1], ac[lag], ac[lag + 1]
    bend = (a - c) / (2 * (a - 2 * b + c)) if a - 2 * b + c else 0.0
    return round(69 + 12 * math.log2(RATE / (lag + bend) / 440.0), 2)


def bars_bands(n=BARS, win=BARS_WIN, rate=RATE, hz=BARS_HZ):
    """Which of a look's frequencies each bar has: where each starts, and where the last ends. A note's width each
    (as many times higher at its top as at its bottom, bar after bar), but one frequency at least: the lowest few."""
    edges = hz[0] * (hz[1] / hz[0]) ** (np.arange(n + 1) / n) * win / rate
    starts, at = [], 0
    for k in range(n):
        lo = max(at, int(round(edges[k])))
        starts.append(lo)
        at = max(lo + 1, int(round(edges[k + 1])))
    return np.array(starts), at


def loop_from(c):
    """What a "loop" says, checked: its layers' sounds, by how long a loop each goes round in ([(beats, hits sorted by
    beat, their beats)]), the tempo, beat b0 and when it's heard (t0), and the click. None: no loop. A hit: [its
    beat, the sound, semitones from its own note, the beat it's heard from, how long a loop it goes round in (beats:
    the loop's, if it doesn't say), how loud (of the sound as it is: 1, if it doesn't say)]."""
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
            gain = float(h[5]) if len(h) > 5 else 1.0
        except (TypeError, ValueError, IndexError):
            continue
        if (isinstance(sid, str) and 1 <= n <= 64 and 0 <= p < n and abs(semis) <= SEMIS_MOST
                and math.isfinite(after) and 0 <= gain <= GAIN_MOST):
            groups.setdefault(n, []).append((p, sid, semis, after, gain))
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
        self.bounce_wait = []                          # Bounce's notes waiting for their time: (when, n, samples...)
        self.bounce_n = itertools.count()
        self.bacc = np.zeros((CHUNK, 2), dtype=np.int32)
        self.fx = FX.Bus(RATE, CHUNK)                  # Bounce's effects: its notes' tone, echo and space
        self.fx_space = (0.0, 0.0)                     # ...how much space Bounce wants, and the Soundboard's own sounds
        self.fx_send = (0.0, 0.0)                      # ...and so how much of each goes into it
        self.fx_stop = False                           # ...everything stopped: what's ringing fades out at once
        self.fx_f = np.zeros((CHUNK, 2), dtype=np.float32)
        self.fx_o = np.zeros((CHUNK, 2), dtype=np.float32)
        self.fx_in = np.zeros((CHUNK, 2), dtype=np.float32)
        self.fx_t = np.zeros((CHUNK, 2), dtype=np.float32)
        self.drone = None                              # its drone, sounding: {"note", "loop", "at", "gain", "to"}
        self.drones_going = []                         # ...ones going (from other keys)
        self.drone_want = (0.0, None)                  # ...how loud it's wanted (0 to 1), on what note
        self.to_make, self.made = [], {}               # Bounce's own sounds and drones: being made, and made
        self.bars_on = False                           # the Sequencer's bars are wanted: the sound, said as bars
        self.bars_tail = np.zeros(BARS_WIN, dtype=np.float32)   # ...the last of what was mixed (left and right, added)
        self.bars_left = 0                             # ...frames of it that aren't silence yet
        self.bars_said = 0.0                           # ...when they were last said
        self.bars_none = True                          # ...and that there were none (no more's said till there are)
        self.bars_at, self.bars_end = bars_bands()
        self.bars_window = np.hanning(BARS_WIN).astype(np.float32)
        threading.Thread(target=self.maker, daemon=True, name="tones").start()
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

    def maker(self):
        """(A thread of its own.) Bounce's own sounds and its drones, made as they're wanted: a moment's work each,
        which the sound mustn't wait for. ("tone", the sound, at which note) or ("drone", its note)."""
        while True:
            with self.lock:
                while not self.to_make:
                    self.lock.wait()
                key = self.to_make[0]
            try:
                data = FX.tone(key[1][6:], key[2], RATE) if key[0] == "tone" else FX.drone(key[1], DRONE_SECS, RATE)
            except Exception as ex:                    # (never the maker's end)
                print(f"soundplay: {key} couldn't be made ({ex!r})", file=sys.stderr, flush=True)
                data = None
            with self.lock:
                self.made[key] = data
                self.to_make.remove(key)
            self.poke()

    def make(self, key):
        """One of Bounce's own sounds, or a drone, to be made (if it isn't, and isn't being)."""
        with self.lock:
            if key not in self.made and key not in self.to_make:
                self.to_make.append(key)
                self.lock.notify_all()

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
        data = self.mix()
        if out.write(data):
            self.wrote = True
            now = time.monotonic()
            self.heard_from(now, out)
            self.took(out)
            if self.bars_on:
                self.bars_take(data, now)

    def bars_take(self, data, now):
        """(feed's, with the Sequencer's page up.) A chunk as it was mixed, kept; and the sound as bars, said BARS_EVERY
        apart: how loud it is in each bar's notes, 0 to 99, whatever the volume. Silence: said once, then no more."""
        tail = self.bars_tail
        if data is SILENCE:
            if self.bars_left <= 0:                    # (nothing but silence in it)
                if not self.bars_none:
                    self.bars_none = True
                    say(**{"is": "bars", "v": [0] * BARS})
                return
            tail[:-CHUNK] = tail[CHUNK:]
            tail[-CHUNK:] = 0
            self.bars_left -= CHUNK
        else:
            x = np.frombuffer(data, dtype="<i2").reshape(-1, 2)
            tail[:-CHUNK] = tail[CHUNK:]
            np.add(x[:, 0], x[:, 1], out=tail[-CHUNK:], dtype=np.float32, casting="unsafe")
            self.bars_left = BARS_WIN
        if now - self.bars_said < BARS_EVERY:
            return
        self.bars_said = now
        power = np.abs(np.fft.rfft(tail * self.bars_window)[:self.bars_end]) ** 2
        full = 32767.0 * 2 * BARS_WIN / 4 * max(1, self.gain) / 256.0   # (a sound as loud as can be, at this volume)
        db = 10.0 * np.log10(np.add.reduceat(power, self.bars_at) / (full * full) + 1e-12)
        v = np.clip((db - BARS_DB[0]) / (BARS_DB[1] - BARS_DB[0]) * 99.0, 0, 99).astype(int).tolist()
        none = not any(v)
        if none and self.bars_none:
            return
        self.bars_none = none
        say(**{"is": "bars", "v": v})

    def bars_set(self, on):
        """The Sequencer's page is up (its bars are wanted), or it isn't any more. (Told as it is already: nothing.)"""
        if bool(on) != self.bars_on:
            self.bars_on = bool(on)
            self.bars_clear()

    def bars_clear(self):
        self.bars_tail[:] = 0
        self.bars_left, self.bars_said, self.bars_none = 0, 0.0, True

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
                    p, sid, semis, after, gain = hits[i]
                    beat = kk * n + p
                    if beat >= after:
                        data, semis = self.loop_sound(sid, semis)
                        if data is not None:
                            self.start(sid, data, semis, wait=int((beat - ba) / per * RATE), shown=False, gain=gain)
                    i += 1
        if lp["click"]:
            beat = math.ceil(ba)
            if beat < bb:
                self.start(None, self.clicks[0 if beat % 4 == 0 else 1], 0, wait=int((beat - ba) / per * RATE))

    def loop_sound(self, sid, semis):
        """A loop's sound, and the semitones it's played at from there: one of the Soundboard's as it was read, or one
        of the player's own (the Sequencer's lead: made at the note nearest the one wanted). None: not there yet."""
        if sid in TONES:
            return self.bounce_tone(sid, semis)
        have = self.sounds.get(sid)
        return (have[1] if have is not None else None), semis

    def bounce_tone(self, sid, semis=0.0):
        """One of Bounce's own sounds, as made at the note nearest the one wanted, and the semitones from there: (its
        samples, semitones), or (None, ...) while it's being made (asked for now)."""
        root = min(TONE_ROOTS, key=lambda r: abs(TONE_ROOT + semis - r))
        key = ("tone", sid, root)
        data = self.made.get(key)
        if data is None:
            self.make(key)
        return data, semis - (root - TONE_ROOT)

    def bounce_play(self, sid, semis, gain, at, now, pan=None):
        """A Bounce note: heard at at (time.monotonic()) if that's to come, else as soon as it can be; from the left
        or the right (pan: -1 to 1), or from both as it is."""
        if sid in TONES:
            data, semis = self.bounce_tone(sid, semis)
        else:
            data = (self.sounds.get(sid) or (None, None))[1]
        if data is None:
            return
        if self.out is None and not self.open(now, force=now - self.tried >= 0.3):
            return
        wait = 0
        if at is not None and self.base is not None:
            ta = self.base + self.fed / RATE           # (when the next chunk mixed is heard)
            if at >= ta + CHUNK / RATE:                # (later than that: it waits its turn)
                if len(self.bounce_wait) < BOUNCE_LATE:
                    heapq.heappush(self.bounce_wait, (at, next(self.bounce_n), data, semis, gain, pan))
                return
            wait = max(0, int((at - ta) * RATE))
        self.bounce_start(data, semis, gain, wait, pan)
        self.feed()

    def bounce_due(self):
        """Bounce's notes heard in the chunk about to be mixed: started at their very frames."""
        if not self.bounce_wait or self.base is None or self.rec is not None:
            return
        ta = self.base + self.fed / RATE
        while self.bounce_wait and self.bounce_wait[0][0] < ta + CHUNK / RATE:
            at, _, data, semis, gain, pan = heapq.heappop(self.bounce_wait)
            self.bounce_start(data, semis, gain, max(0, int((at - ta) * RATE)), pan)

    def bounce_start(self, data, semis, gain, wait, pan=None):
        """A Bounce note started: one of only BOUNCE_MOST (one more: the oldest fades out), fading in, and no longer
        than BOUNCE_SECS."""
        live = [v for v in self.voices if v.bounce and v.fade is None]
        for v in live[:max(0, len(live) + 1 - BOUNCE_MOST)]:
            v.fade = FADE                              # (one not heard yet, told with this one: not heard at all)
            if not v.pos:
                self.voices.remove(v)
        v = Voice(None, data, max(0, min(CHUNK - 1, wait)), 2.0 ** (semis / 12.0) if semis else 1.0, gain)
        v.shown, v.bounce, v.rise, v.left = False, True, FADE_IN, int(BOUNCE_SECS * RATE)
        if pan is not None and pan != 0:
            v.pan = np.array(pan_of(pan), dtype=np.float32) * np.float32(gain)
        self.voices.append(v)
        live = [v for v in self.voices if v.fade is None]
        for v in live[:max(0, len(live) - VOICES_MOST)]:
            v.fade = FADE

    def start(self, sid, data, semis=0, wait=0, shown=True, gain=1.0):
        """A sound started (the same one playing: it fades out as this one starts), at a pitch of its own, so many
        frames into the next chunk. Not shown: a loop's (not said to be playing: its button isn't lit for it, as the
        page would be drawn for every sound of the loop's). gain: how loud, of the sound as it is."""
        for v in self.voices:
            if v.id == sid and v.fade is None:
                v.fade = FADE
        v = Voice(sid, data, max(0, min(CHUNK - 1, wait)), 2.0 ** (semis / 12.0) if semis else 1.0, gain)
        v.shown = shown and sid is not None
        self.voices.append(v)
        live = [v for v in self.voices if v.fade is None]
        for v in live[:max(0, len(live) - VOICES_MOST)]:
            v.fade = FADE
        if shown and sid is not None:
            self.heard.pop(sid, None)
            self.stale = True

    def fx_ringing(self):
        """Something of the effects still to be heard with no sound going in: an echo or a space dying away, the
        drone."""
        fx = self.fx
        return fx.echo.left > 0 or fx.space.left > 0 or self.drone is not None or bool(self.drones_going)

    def fx_wanted(self):
        """The effects have something to do: they're set to (Bounce's, the Soundboard's space), or still ringing."""
        fx = self.fx
        return not fx.tone.resting() or fx.echo.want > 0 or fx.space.want > 0 or self.fx_ringing()

    def mix(self):
        """The next chunk: the sounds playing, added up (silence, with none); Bounce's through its effects, and the
        Soundboard's own into the space too if START's card says so."""
        self.loop_due()
        self.bounce_due()
        if not self.voices and not self.fx_ringing():
            self.limit = 1.0
            return SILENCE
        acc = self.acc
        acc[:] = 0
        effects = self.fx_wanted()
        bacc = self.bacc if effects else acc           # (Bounce's notes: through its effects, then added in)
        if effects:
            bacc[:] = 0
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
            if v.rise and m:                           # (a Bounce note, starting: faded in)
                k = min(m, v.rise)
                seg = seg[:m].astype(np.float32)
                ramp = RISE[FADE_IN - v.rise:FADE_IN - v.rise + k]
                seg[:k] *= ramp if seg.ndim == 1 else ramp[:, None]
                v.rise -= k
            if v.pan is not None and m:                # (a Bounce note from one side: louder there, and as loud as
                seg = (seg[:m, None] if seg.ndim == 1 else seg[:m]) * v.pan   # its gain says)
            elif v.gain != 1.0:
                seg = seg[:m] * v.gain
            if m:
                into = bacc if v.bounce else acc
                seg = seg[:m].astype(np.int32) if seg.dtype.kind == "f" else seg[:m]
                if seg.ndim == 1:
                    into[o:o + m] += seg[:, None]
                else:
                    into[o:o + m] += seg
            if v.left is not None:                     # (a Bounce note: no longer than BOUNCE_SECS)
                v.left -= m
                if v.left <= 0 and v.fade is None:
                    v.fade = FADE
            v.pos += m if v.rate == 1.0 else m * v.rate
            if v.pos < len(v.data) - (0 if v.rate == 1.0 else 1) and (v.fade is None or v.fade > 0) and m:
                going.append(v)
        if len(going) != len(self.voices):
            self.voices, self.stale = going, True
        if effects:
            self.effects(acc, bacc)
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

    def effects(self, acc, bacc):
        """(mix's.) Bounce's notes (bacc) through its tone, then its echo, then its space (soundfx.py); its drone with
        them; and the Soundboard's own sounds (acc) into the space too, as much as START's card says: all of it added
        into acc. Everything stopped: what's ringing faded out over this chunk, and gone."""
        fx, f, o = self.fx, self.fx_f, self.fx_o
        np.copyto(f, bacc, casting="unsafe")
        flat = f.reshape(-1)
        live = float(np.dot(flat, flat)) > FX.QUIET
        s = fx.tone.go(f, live)
        np.copyto(o, s)
        e = fx.echo.go(s, live) if fx.echo.want or fx.echo.left > 0 else None
        if e is not None:
            o += e
        d = self.drone_chunk()
        if fx.space.want or fx.space.left > 0:
            (mine, theirs), into = self.fx_send, o
            if mine != 1.0 or d is not None or theirs:     # (Bounce's notes as they are: what goes in, as it is)
                into = self.fx_in
                np.multiply(o, mine, out=into)
                if d is not None:
                    np.multiply(d, DRONE_SPACE, out=self.fx_t)
                    into += self.fx_t
                if theirs:
                    np.multiply(acc, theirs, out=self.fx_t, casting="unsafe")
                    into += self.fx_t
            if not (live and mine) and e is None:
                flat = into.reshape(-1)
                live = float(np.dot(flat, flat)) > FX.QUIET
            r = fx.space.go(into, live or e is not None)
            if r is not None:
                o += r
        if d is not None:
            o += d
        if self.fx_stop:
            o *= EDGE_CHUNK
            fx.clear()
            self.fx_stop = False
        np.add(acc, o, out=acc, casting="unsafe")

    def drone_chunk(self):
        """(effects'.) The drone's next chunk (float32), gliding to how loud it's wanted, and from one key's to the
        next's; None: there's none."""
        out = None
        step = CHUNK / (DRONE_GLIDE * RATE)
        for dr in self.drones_going + ([self.drone] if self.drone is not None else []):
            loop, at, g0 = dr["loop"], dr["at"], dr["gain"]
            n = len(loop)
            seg = loop[at:at + CHUNK] if at + CHUNK <= n else np.concatenate((loop[at:], loop[:at + CHUNK - n]))
            dr["at"] = (at + CHUNK) % n
            g1 = min(dr["to"], g0 + step) if dr["to"] > g0 else max(dr["to"], g0 - step)
            dr["gain"] = g1
            x = seg * np.linspace(g0, g1, CHUNK, dtype=np.float32)[:, None] if g0 != g1 else seg * np.float32(g1)
            out = x if out is None else out + x
        self.drones_going = [dr for dr in self.drones_going if dr["gain"] > 0]
        if self.drone is not None and self.drone["gain"] <= 0 and self.drone["to"] <= 0:
            self.drone = None
        return out

    def drone_set(self, level, note):
        """Its drone (told): as loud as level (0 to 1), on note (MIDI). Another note: the one sounding goes as the new
        one comes (made first, a thread's work: drone_made)."""
        to = DRONE_MOST * max(0.0, min(1.0, level))
        self.drone_want = (to, note)
        dr = self.drone
        if dr is not None and dr["note"] != note:      # (another key: this one goes, as the new one comes)
            dr["to"] = 0.0
            self.drones_going.append(dr)
            self.drone = None
        elif dr is not None:
            dr["to"] = to
        if to > 0 and note is not None and self.drone is None:
            self.make(("drone", note))
            self.drone_made()

    def drone_made(self):
        """The drone wanted, if it's made now (and not sounding yet): it comes in."""
        to, note = self.drone_want
        loop = self.made.get(("drone", note)) if note is not None else None
        if to > 0 and loop is not None and self.drone is None:
            self.drone = {"note": note, "loop": loop.astype(np.float32), "at": 0, "gain": 0.0, "to": to}
            with self.lock:                            # (another key's, no longer wanted: let go of)
                for key in [k for k in self.made if k[0] == "drone" and k[1] != note]:
                    del self.made[key]

    def fx_set(self, c):
        """Bounce's effects as told (soundfx.py: each 0 to 1), and the Soundboard's own sounds' space: the space as
        much as the most either wants, each going into it as much as it wants of that."""
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)   # noqa: E731
        fx = self.fx
        if num(c.get("tone")):
            fx.tone.set(c["tone"])
        if num(c.get("echo")):
            fx.echo.set(c["echo"], c["secs"] if num(c.get("secs")) else None)
        mine, theirs = self.fx_space
        if num(c.get("space")):
            mine = max(0.0, min(1.0, float(c["space"])))
        if num(c.get("pads")):
            theirs = max(0.0, min(1.0, float(c["pads"])))
        self.fx_space = (mine, theirs)
        most = max(mine, theirs)
        fx.space.set(most)
        self.fx_send = (mine / most, theirs / most) if most else (0.0, 0.0)

    def play(self, sid, now, semis=0, gain=1.0):
        if sid in TONES:                               # (one of its own: the Sequencer's lead, heard as it's picked)
            data, semis = self.bounce_tone(sid, semis)
            if data is None:
                return                                 # (being made: there in a moment)
        else:
            with self.lock:
                have = self.sounds.get(sid)
                if have is None and sid in dict(self.want) and sid not in self.bad:
                    self.soon[sid] = now               # (not read yet: played as soon as it is, if that's soon)
            if have is None:
                return
            self.soon.pop(sid, None)
            data = have[1]
        if self.out is None and not self.open(now, force=now - self.tried >= 0.3):
            return                                     # (the sound card won't open: not played later, out of the blue)
        self.start(sid, data, semis, gain=gain)        # (playing: that one fades out as this one starts)
        self.feed()

    def stop_all(self, now):
        for v in self.voices:
            if v.fade is None:
                v.fade = FADE
        self.soon.clear()
        self.bounce_wait = []
        self.fx_stop = self.fx.ringing()               # (an echo or a space dying away: gone, without a click)
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
            semis, gain = c.get("semis", 0), c.get("gain", 1.0)
            if (isinstance(c.get("id"), str) and self.rec is None and type(semis) is int and abs(semis) <= SEMIS_MOST
                    and isinstance(gain, (int, float)) and not isinstance(gain, bool) and 0 <= gain <= GAIN_MOST):
                self.play(c["id"], now, semis, gain)
        elif do == "loop":
            self.loop = loop_from(c)
        elif do == "note":                             # (Bounce's: a wall's note)
            sid, semis, gain, at = c.get("id"), c.get("semis", 0), c.get("gain", 1.0), c.get("at")
            num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)   # noqa: E731
            pan = c.get("pan")
            if (isinstance(sid, str) and self.rec is None and num(semis) and abs(semis) <= SEMIS_MOST and num(gain)
                    and 0 <= gain <= GAIN_MOST and (at is None or num(at))
                    and (pan is None or (num(pan) and abs(pan) <= 1))):
                self.bounce_play(sid, float(semis), float(gain), at, now, pan)
        elif do == "tone":                             # (one of Bounce's own sounds, made ready)
            if c.get("id") in TONES:
                for root in TONE_ROOTS:
                    self.make(("tone", c["id"], root))
        elif do == "bars":                             # (the Sequencer's page: the sound as bars, while it's up)
            self.bars_set(c.get("on") is True)
        elif do == "fx":
            self.fx_set(c)
        elif do == "space":
            self.fx_set({"pads": c.get("v")})
        elif do == "drone":
            level, note = c.get("level"), c.get("note")
            if isinstance(level, (int, float)) and not isinstance(level, bool) and math.isfinite(level):
                self.drone_set(float(level), note if type(note) is int and 12 <= note <= 96 else None)
        elif do == "pitch":
            sid = c.get("id")
            data = (make_tone(sid) if sid in TONES else (self.sounds.get(sid) or (None, None))[1]) \
                if isinstance(sid, str) else None
            if data is not None:
                say(**{"is": "pitch", "id": sid, "midi": pitch_of(data)})
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
            self.bounce_wait = []
            self.fx.clear()
            self.close()
            self.ok, self.stale = None, True
            if self.bars_on and not self.bars_none:    # (the Sequencer's bars: nothing's heard now)
                self.bars_clear()
                say(**{"is": "bars", "v": [0] * BARS})
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
        if self.drone is None and self.drone_want[0] > 0:
            self.drone_made()                          # (made now, perhaps: its drone comes in)
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
