"""An ear for the song that's playing: its beats, a moment before they're heard, for Now playing's glow, and the sound
as bars (Looks), for its bars. FFmpeg decodes the song a second time, quietly and only as fast as it's played; Beats
(glow.py: an LED backlight's) finds the kick drums. Each beat and each look is kept by its place in the song, so
pausing is nothing to it; a jump to another place in the song (a seek) starts it again from there. The song itself
plays as it always has: if this fails, the glow keeps still and the bars lie flat.
A station can't be listened to twice (it's live), so its bars are MPlayer's own sound (Tap): its export filter shares
the last of what it played in a file, read as it changes."""
import collections
import math
import os
import stat
import struct
import subprocess
import tempfile
import threading
import time

import numpy as np

from .glow import Beats

EAR_RATE = 48000                 # samples a second, as Beats listens (what an LED backlight's are found at)
EAR_AHEAD = 1.2                  # seconds of the song listened to ahead of what's heard
EAR_STEP = 0.1                   # ...taken this much at a time
EAR_JUMP = 0.7                   # this far from where it thought the song was: a jump, and it starts again
EAR_BACK = 8.0                   # ...or this far back in what it's listened to (its beats there aren't all kept)
EAR_KEPT = 48                    # beats remembered
BEAT_FADE = 0.22                 # seconds: how fast the glow dies away after a beat
BEAT_SOFT = 0.5                  # the softest beat lights it this much (the hardest: all the way)
FRAME = 4                        # bytes a sample (two channels, 16 bits each)
BARS = 32                        # Now playing's bars: the sound just then, low notes first (as the Sequencer's)
BARS_WIN = 2048                  # ...samples each look is at (43 ms)
BARS_EVERY = 0.05                # ...seconds of the song from one look to the next
BARS_HZ = (40.0, 12000.0)        # ...from the lowest bar's notes to the highest's
BARS_DB = (-54.0, -6.0)          # ...a bar at nothing and at its top: this far under as loud as a sound can be
BARS_KEPT = 64                   # looks remembered (more than EAR_AHEAD's worth)
BARS_OLD = 0.25                  # ...one this much before where the song is: too old to show (none since: flat)
EXPORT_SIZE = 1024               # a station's bars: MPlayer's export filter shares this many samples a channel at once
                                 # (less than it plays at a time, so each lot's whole: a bigger one comes in pieces)
EXPORT_LEAD = 0.5                # ...that long before they're heard (the half second it keeps ahead in the sound card)
EXPORT_RATE = 44100              # ...samples a second, as most stations send them
EXPORT_EVERY = 1 / 30            # ...looked at no more often than this
SOFTVOL_TOP = 1.1                # MPlayer's volume at 100 (its -softvol-max, as it comes): what it shares is this loud


def ear_args(src, pos):
    return ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-ss", f"{max(0.0, pos):.3f}", "-i", src,
            "-vn", "-ac", "2", "-ar", str(EAR_RATE), "-f", "s16le", "-"]


def tap_file(uid=None):
    """Where MPlayer shares a station's sound (Tap): in memory (/dev/shm) where there's that, one file for each of
    you it runs as."""
    base = "/dev/shm" if os.path.isdir("/dev/shm") else tempfile.gettempdir()
    return os.path.join(base, f"pietato-bars-{os.geteuid() if uid is None else uid}")


def tap_ready(path, uid=None, gid=None):
    """That file there and MPlayer's to write (it runs as you, uid): made so, or kept as it was made before. False
    when it can't be (someone else's, no room): MPlayer stops at once when it can't make it, so it isn't asked to."""
    mine = os.geteuid() if uid is None else uid
    try:
        st = os.lstat(path)
        if stat.S_ISREG(st.st_mode) and st.st_uid == mine:
            return True
        os.unlink(path)                                # (a link, or another's: made again)
    except FileNotFoundError:
        pass
    except OSError:
        return False
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o640)
    except OSError:
        return False
    try:
        if mine != os.geteuid():
            os.fchown(fd, mine, -1 if gid is None else gid)
        return True
    except OSError:
        return False
    finally:
        os.close(fd)


EXPORTS = []                     # whether this MPlayer has its export filter: asked once


def mplayer_exports(run=subprocess.run):
    """Whether MPlayer here can share its sound (its export filter: Debian's and Ubuntu's have it)."""
    if not EXPORTS:
        try:
            said = run(["mplayer", "-af", "help"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.DEVNULL, text=True, timeout=10).stdout or ""
        except (OSError, subprocess.SubprocessError):
            said = ""
        EXPORTS.append(any(line.split()[:1] == ["export"] for line in said.splitlines()))
    return EXPORTS[0]


def bars_bands(n=BARS, win=BARS_WIN, rate=EAR_RATE, hz=BARS_HZ):
    """Which of a look's frequencies each bar has: where each starts, and where the last ends. A note's width each
    (as many times higher at its top as at its bottom, bar after bar), but one frequency at least: the lowest few.
    (As the Soundboard's player has them, soundplay.py.)"""
    edges = hz[0] * (hz[1] / hz[0]) ** (np.arange(n + 1) / n) * win / rate
    starts, at = [], 0
    for k in range(n):
        lo = max(at, int(round(edges[k])))
        starts.append(lo)
        at = max(lo + 1, int(round(edges[k + 1])))
    return np.array(starts), at


class Looks:
    """The sound as bars, as the ear hears it: a look every BARS_EVERY of the song, kept by its place in it. feed(pcm,
    place): s16le stereo samples, the first at that place (seconds into the song); at(place): the look there (each
    bar 0 to 1, low notes first), or None (none near enough)."""

    def __init__(self, rate=EAR_RATE, win=BARS_WIN):
        self.looks = collections.deque(maxlen=BARS_KEPT)
        self.lock = threading.Lock()
        self.window = np.hanning(win).astype(np.float32)
        self.starts, self.end = bars_bands(win=win, rate=rate)
        self.full = (32767.0 * 2 * win / 4) ** 2       # (a sound as loud as can be, in both channels: its power)
        self.clear()

    def clear(self):
        self.tail = np.zeros(0, dtype=np.float32)    # (the samples just before the next ones: a look's worth)
        self.due = None                               # (where in the song the next look is)
        with self.lock:
            self.looks.clear()

    def feed(self, pcm, place):
        a = np.frombuffer(pcm, dtype="<i2")
        mono = a[: len(a) // 2 * 2].reshape(-1, 2).sum(axis=1, dtype=np.float32)
        buf = np.concatenate((self.tail, mono))
        first = place - len(self.tail) / EAR_RATE     # (where buf's first sample is in the song)
        if self.due is None:
            self.due = first + BARS_WIN / EAR_RATE
        while True:
            end = int(round((self.due - first) * EAR_RATE))
            if end > len(buf):
                break
            if end >= BARS_WIN:
                look = self.look(buf[end - BARS_WIN:end])
                with self.lock:
                    self.looks.append((self.due, look))
            self.due += BARS_EVERY
        self.tail = buf[-BARS_WIN:]

    def look(self, x):
        power = np.abs(np.fft.rfft(x * self.window)[:self.end]) ** 2
        db = 10.0 * np.log10(np.add.reduceat(power, self.starts) / self.full + 1e-12)
        return tuple(float(v) for v in np.clip((db - BARS_DB[0]) / (BARS_DB[1] - BARS_DB[0]), 0.0, 1.0).round(3))

    def at(self, place):
        if place is None:
            return None
        with self.lock:
            looks = list(self.looks)
        for when, look in reversed(looks):
            if when <= place + 1e-6:
                return look if place - when <= BARS_OLD else None
        return None


class Tap:
    """A station's sound as MPlayer plays it, as bars: its export filter (mplayer -af export) shares the last samples
    it played in a file, a count before them going up with each lot, and each new lot's a look (Looks'), kept for when
    it's heard (EXPORT_LEAD on). levels(now, gain): the look heard now, or None (nothing new lately: paused, gone, or
    silenced). gain: how loud the volume has made it (what's shared is as loud as it's played), so the bars are the
    same at any volume. Read, not mapped: MPlayer makes the file afresh as it starts, and a mapping then would fault."""

    def __init__(self, path, rate=EXPORT_RATE):
        self.path = path
        self.shape = Looks(rate, EXPORT_SIZE)          # (its look(): a lot of samples as bars)
        self.kept = collections.deque(maxlen=BARS_KEPT)
        self.count, self.read_at = None, None

    def clear(self):
        self.kept.clear()
        self.count, self.read_at = None, None

    def read(self, now, gain):
        try:
            with open(self.path, "rb") as f:
                data = f.read(16 + 8 * 2 * EXPORT_SIZE)
        except OSError:
            return
        if len(data) < 16:
            return
        nch, size = struct.unpack_from("=ii", data, 0)
        count = struct.unpack_from("=Q", data, 8)[0]
        if count == self.count or not 1 <= nch <= 8 or size <= 0 or size % (2 * nch) or len(data) < 16 + size:
            return
        self.count = count
        a = np.frombuffer(data, dtype="=i2", count=size // 2, offset=16).reshape(nch, -1)[:2]
        if a.shape[1] < EXPORT_SIZE:
            return
        mono = a[:, :EXPORT_SIZE].sum(axis=0, dtype=np.float32) * (2.0 / len(a) / gain)   # (one channel: as two)
        self.kept.append((now + EXPORT_LEAD, self.shape.look(mono)))

    def levels(self, now, gain=1.0):
        if gain < 0.01:
            return None
        if self.read_at is None or now - self.read_at >= EXPORT_EVERY:
            self.read_at = now
            self.read(now, gain)
        for when, look in reversed(self.kept):
            if when <= now + 1e-6:
                return look if now - when <= BARS_OLD else None
        return None


class Ear:
    """where(): the place in the song that's heard now (seconds), or None while that's not known (paused, just
    started). level(place): how lit the glow is there, 0 (no beat lately) to 1 (a hard one, just now); levels(place):
    the bars there (Looks), or None."""

    def __init__(self, src, where, run=True, popen=subprocess.Popen):
        self.src, self.where, self.popen = src, where, popen
        self.beats = collections.deque(maxlen=EAR_KEPT)   # (its place in the song, how hard: 0 to 1)
        self.lock = threading.Lock()
        self.closed = False
        self.proc = None
        self.at = self.since = 0.0                     # the place the next sample read is; where this FFmpeg began
        self.rest = b""                                # (part of a sample, till the rest of it's read)
        self.finder = None
        self.looks = Looks()
        self.ended = False                             # (the song's all been listened to)
        if run:
            threading.Thread(target=self.run, daemon=True, name="ear").start()

    def beat(self, place, hard):
        with self.lock:
            self.beats.append((place, hard))

    def start(self, place):
        self.stop()
        self.at = self.since = max(0.0, place)
        self.rest, self.ended = b"", False
        self.finder = Beats(EAR_RATE, self.beat)
        self.looks.clear()
        with self.lock:
            self.beats.clear()
        try:
            self.proc = self.popen(ear_args(self.src, self.at), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, bufsize=0)
        except OSError:
            self.proc, self.ended = None, True         # (no FFmpeg: no beats, and it isn't tried again)

    def stop(self):
        p, self.proc = self.proc, None
        if p is not None:
            try:
                p.kill()
                p.wait(timeout=2)
            except (OSError, subprocess.SubprocessError):
                pass
            try:
                p.stdout.close()
            except (OSError, AttributeError):
                pass

    def step(self):
        """A little more of the song listened to, if it's due: whether anything was done (False: wait a moment)."""
        place = self.where()
        if place is None:
            return False
        jumped = place < self.since - EAR_JUMP or place > self.at + EAR_JUMP or place < self.at - EAR_BACK
        if self.finder is None or jumped:
            self.start(place)
        if self.proc is None or self.ended or self.at - place >= EAR_AHEAD:
            return False
        want = int(EAR_RATE * EAR_STEP) * FRAME
        try:
            data = self.proc.stdout.read(want)
        except (OSError, ValueError):
            data = b""
        if not data:
            self.ended = True                          # (the end of the song: nothing more to find)
            return False
        data = self.rest + data
        whole = len(data) // FRAME * FRAME
        self.rest = data[whole:]
        if whole:
            self.finder.feed(data[:whole], self.at)
            self.looks.feed(data[:whole], self.at)
            self.at += whole / FRAME / EAR_RATE
        return True

    def run(self):
        while not self.closed:
            try:
                busy = self.step()
            except Exception as ex:                    # (whatever it is: the glow keeps still, the song plays on)
                print(f"ear: no beats ({ex!r})", flush=True)
                break
            if not busy:
                time.sleep(0.05)
        self.stop()

    def level(self, place):
        if place is None:
            return 0.0
        with self.lock:
            beats = list(self.beats)
        best = 0.0
        for when, hard in reversed(beats):
            since = place - when
            if since < 0:                              # (not heard yet)
                continue
            if since > 6 * BEAT_FADE:
                break
            best = max(best, (BEAT_SOFT + (1.0 - BEAT_SOFT) * hard) * math.exp(-since / BEAT_FADE))
        return best

    def levels(self, place):
        return self.looks.at(place)

    def close(self):
        self.closed = True
        p = self.proc
        if p is not None:                              # (so its thread isn't left waiting on it)
            try:
                p.kill()
            except OSError:
                pass
