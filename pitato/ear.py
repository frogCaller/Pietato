"""An ear for the song that's playing: its beats, a moment before they're heard, for Now playing's glow. FFmpeg decodes
the song a second time, quietly and only as fast as it's played; Beats (glow.py: an LED backlight's) finds the kick
drums. Each beat is kept by its place in the song, so pausing is nothing to it; a jump to another place in the song
(a seek) starts it again from there. The song itself plays as it always has: if this fails, the glow keeps still."""
import collections
import math
import subprocess
import threading
import time

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


def ear_args(src, pos):
    return ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-ss", f"{max(0.0, pos):.3f}", "-i", src,
            "-vn", "-ac", "2", "-ar", str(EAR_RATE), "-f", "s16le", "-"]


class Ear:
    """where(): the place in the song that's heard now (seconds), or None while that's not known (paused, just
    started). level(place): how lit the glow is there, 0 (no beat lately) to 1 (a hard one, just now)."""

    def __init__(self, src, where, run=True, popen=subprocess.Popen):
        self.src, self.where, self.popen = src, where, popen
        self.beats = collections.deque(maxlen=EAR_KEPT)   # (its place in the song, how hard: 0 to 1)
        self.lock = threading.Lock()
        self.closed = False
        self.proc = None
        self.at = self.since = 0.0                     # the place the next sample read is; where this FFmpeg began
        self.rest = b""                                # (part of a sample, till the rest of it's read)
        self.finder = None
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

    def close(self):
        self.closed = True
        p = self.proc
        if p is not None:                              # (so its thread isn't left waiting on it)
            try:
                p.kill()
            except OSError:
                pass
