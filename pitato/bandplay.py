"""The Band's player (Apps > Band: band.py, bandstage.py, screens/band.py): the Soundboard's player (soundplay.py), which
it's made from, with what a band needs more. Sounds played at a time, not just now: each note's told with the moment
it's to be heard (this machine's clock, time.monotonic()), a bar or so ahead, and is mixed in at that very sample.
When that is, in the stream, comes from how fast aplay has been taking the sound (Pace): what's written now is read
by aplay a period from now, and heard its buffer later. And the instruments themselves: a bass, a guitar and keys,
each note made here from sums the first time it's wanted (a few sines that die away, as a string or a tine does), then
kept (the folder given on the command line), and a chord made of its notes.

Told as the Soundboard's player is, and besides:

    {"do": "load", "sounds": [[name, file or "synth:<bass|guitar|keys>:<notes, + between>:<seconds>[:how]"]...]}
    {"do": "at", "notes": [[when, name, how loud (0 to 1), lane, seconds (0: all of it), whose]...]}
    {"do": "play", "id": name, "gain": 0 to 1, "lane": "...", "secs": 0}     now
    {"do": "clear", "whose": "bass"}     what's still to come of that one's (none given: of everyone's), and its sound
    {"do": "stats"}                      -> {"is": "stats", "late": notes that came too late to play, "waiting": ...}

A sound in a lane ends the one before it there (a bass note, the one before; a chord, the last). A sound isn't mixed in
a little at a time, as the Soundboard's are: all of it's added at once to its player's stream to come ("whose": the
drums', the bass's... yours), so a whole band playing costs no more than one sound does; and a moment before it's
heard (SOON), a sound or so with each chunk, so a bar's first beat, where every player's starts at once, doesn't hold
the stream up. It doesn't say which sounds are playing (a band's would be all talk)."""
import collections
import heapq
import importlib.util
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def beside(name):
    """A file beside this one, loaded (run with -I, this isn't in a package)."""
    spec = importlib.util.spec_from_file_location("pitato_" + name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SP = beside("soundplay")
RATE, CHUNK = SP.RATE, SP.CHUNK
LATE = 0.02                      # seconds late a note may be and still be played (later: it's left out)
SOON = 0.1                       # seconds before a note's heard that it may be put in its player's stream already
SOON_MOST = RATE                 # ...this many frames of sound with each chunk (once they're in, the next chunk's)
FADE = 720                       # frames a sound takes to end when another takes its lane, or its time's up (15 ms)
RING = 8 * RATE                  # frames of sound to come each player's stream holds (longer than any sound)
WAITING_MOST = 6000              # notes still to come, at most
PACE_SECS, PACE_EVERY = 4.0, 0.25   # how fast aplay takes it: worked out over this long, this often
PACE_FEW = (12, 0.25)            # ...from this many looks at least, this far apart
PACE_AFTER = 0.15                # ...and none from its first moments (aplay fills its buffer at once, then keeps time)
PACE_OWN = 0.6                   # seconds of looks before how fast the card really runs is taken from them
MADE = 3                         # (the notes kept are these ones: a new number, and they're made again)
NOTES_HELD = 16                  # notes held in memory while sounds are made of them (the rest: read again, or made)
EDGE = np.linspace(1.0, 0.0, FADE, dtype=np.float32)


# ---- the instruments: a note made from sums --------------------------------------------------------------------------
def hz(midi):
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


def rise(x, secs):
    """Its first moments brought up from nothing (no click)."""
    n = min(len(x), max(1, int(secs * RATE)))
    x[:n] *= 0.5 - 0.5 * np.cos(np.linspace(0.0, np.pi, n))
    return x


def bass(midi, secs):
    """A bass string, plucked with a finger: its low sines strongest, a few above them so a small speaker has
    something of it too, the high ones gone soonest."""
    f, t = hz(midi), np.arange(int(secs * RATE)) / RATE
    x = np.zeros(len(t))
    for k, a in enumerate((1.0, 0.7, 0.45, 0.3, 0.2, 0.12, 0.08, 0.05), 1):
        x += a * np.sin(2 * np.pi * f * k * t) * np.exp(-t * (1.1 + 0.55 * k))
    return rise(x, 0.006)


def guitar(midi, secs):
    """A guitar string, picked near its end: every sine it has, each as strong as where it's picked lets it be, the
    high ones dying away sooner (and a high string's sooner than a low one's); a tick of the pick at its start."""
    f, t = hz(midi), np.arange(int(secs * RATE)) / RATE
    x = np.zeros(len(t))
    for k in range(1, 25):
        fk = f * k * (1 + 0.00007 * k * k) ** 0.5
        if fk > 9000:
            break
        a = abs(np.sin(np.pi * k * 0.21)) / k
        x += a * np.sin(2 * np.pi * fk * t) * np.exp(-t * (1.3 + 0.26 * k ** 1.25) * (f / 147.0) ** 0.25)
    n = int(0.005 * RATE)
    tick = np.random.default_rng(midi).uniform(-1.0, 1.0, n) * np.hanning(n) * 0.12
    x[:n] += np.convolve(tick, np.ones(6) / 6, "same")
    return rise(x, 0.002)


def keys(midi, secs):
    """An electric piano's tine: its own sine, a few soft ones above, a bell at its start that's gone at once, and a
    slow waver."""
    f, t = hz(midi), np.arange(int(secs * RATE)) / RATE
    quick = (f / 262.0) ** 0.3
    x = np.zeros(len(t))
    for ratio, a, d in ((1, 1.0, 1.1), (2, 0.42, 2.6), (3, 0.16, 3.8), (4, 0.07, 5.5), (6.3, 0.1, 16.0)):
        x += a * np.sin(2 * np.pi * f * ratio * t) * np.exp(-t * d * quick)
    x *= 1.0 + 0.05 * np.sin(2 * np.pi * 4.6 * t)
    return rise(x, 0.004)


VOICES = {"bass": (bass, 1.4), "guitar": (guitar, 2.0), "keys": (keys, 3.6)}   # how each is made, and how long (s)


def chord(parts, secs, how=""):
    """A sound made of notes (each as its instrument makes it, as loud as it can be): just the one; a chord held;
    strum: a chord strummed, its strings a moment apart; stab: a short one; mute: a short, dull one. 16-bit, one
    channel."""
    n = max(int(0.03 * RATE), int(secs * RATE))
    apart = int({"strum": 0.013, "stab": 0.004, "mute": 0.0}.get(how, 0.0) * RATE)
    x = np.zeros(n + apart * len(parts))
    for i, p in enumerate(parts):
        seg = p[:n]
        x[i * apart:i * apart + len(seg)] += seg
    t = np.arange(len(x)) / RATE
    if how == "stab":
        x *= np.exp(-t * 9.0)
    elif how == "mute":
        x = np.convolve(np.convolve(x, np.ones(9) / 9, "same"), np.ones(9) / 9, "same") * np.exp(-t * 26.0)
    out = max(1, min(len(x) // 2, int((0.012 if how in ("stab", "mute") else 0.05) * RATE)))
    x[-out:] *= np.linspace(1.0, 0.0, out)
    top = float(np.abs(x).max())
    if top <= 0:
        raise ValueError("there's no sound in it")
    return np.ascontiguousarray(np.round(x * (0.85 * 32767 / top)), dtype=np.int16)


# ---- when what's written is heard ---------------------------------------------------------------------------------------
class Pace:
    """How fast aplay takes the sound, and so when what's written now is heard. Each time aplay has just taken a
    chunk, how many frames it has taken in all is noted with the time. Seen late now and then (this was kept
    waiting), never early: so the line that says how many it has taken by when goes through the earliest of them,
    as steep as they all say (a sound card's clock isn't quite this machine's)."""

    def __init__(self, start=0.0):
        self.start = start                             # (looks before then aren't kept)
        self.seen = collections.deque()
        self.line = None                               # (a time, frames taken by then, frames a second)
        self.drawn = 0.0

    def add(self, t, taken):
        if t < self.start:
            return
        self.seen.append((t, taken))
        while self.seen[0][0] < t - PACE_SECS:
            self.seen.popleft()
        if t - self.drawn >= PACE_EVERY:
            self.drawn = t
            self.draw()

    def draw(self):
        if len(self.seen) < PACE_FEW[0] or self.seen[-1][0] - self.seen[0][0] < PACE_FEW[1]:
            self.line = None
            return
        ts = np.fromiter((p[0] for p in self.seen), dtype=np.float64, count=len(self.seen))
        cs = np.fromiter((p[1] for p in self.seen), dtype=np.float64, count=len(self.seen))
        t0 = float(ts[0])
        x, y = ts - t0, cs
        xm, ym = x.mean(), y.mean()
        rate = float(((x - xm) * (y - ym)).sum() / max(float(((x - xm) ** 2).sum()), 1e-12))
        if x[-1] < PACE_OWN or not 0.98 * RATE < rate < 1.02 * RATE:   # (too few looks to say, or it stopped a
            rate = float(RATE)                                          #  while: as fast as it should be)
        self.line = (t0, float((y - rate * x).max()), rate)

    def when(self, frame):
        """When aplay takes the chunk that ends at this frame (None: not known yet)."""
        if self.line is None:
            return None
        t0, base, rate = self.line
        return t0 + (frame - base) / rate


class Out(SP.Out):
    """aplay, asked besides what buffer and period the sound card gave it (-v: it says, as it starts): they aren't
    always the ones asked for (a card shared between programs has its own), and when a note's heard goes by them."""
    more = ("-v",)

    def __init__(self, device, level=0):
        self.buffer = self.period = None               # frames, once aplay's said
        super().__init__(device, level)

    def broke(self, line):
        low = line.lower().strip()
        for key in ("buffer", "period"):
            if getattr(self, key) is None and low.startswith(key.encode() + b"_size"):
                try:
                    n = int(low.split(b":", 1)[1])
                except (ValueError, IndexError):
                    continue
                if 32 <= n <= RATE * 2:
                    setattr(self, key, n)
        return b"underrun" in low                      # (-v has aplay say more when it runs dry: one line counts)

    def lag(self):
        """Frames from aplay taking a chunk to its being heard: a period (it waits for room for it), then the
        buffer."""
        if self.buffer is not None and self.period is not None and self.period <= self.buffer:
            return self.buffer + self.period
        buffer, period = SP.BUFFERS[self.level]
        return (buffer + period) * RATE // 1000000


# ---- the player ---------------------------------------------------------------------------------------------------------
class Player(SP.Player):
    card = Out

    def __init__(self, cache):
        self.notes = collections.OrderedDict()         # (an instrument, a note) -> its samples, as loud as can be
        self.waiting = []                              # the notes still to come: (when, a count, name, how loud, lane,
        self.count = 0                                 #  seconds, whose), the soonest first
        self.late = 0                                  # notes that came too late to play
        self.pace, self.pace_of = Pace(), None         # how fast aplay takes it (this aplay)
        self.frames = 0                                # frames written, in all
        self.mixed = 0.0                               # when the chunk being written was mixed
        self.rings = {}                                # whose -> its stream to come: RING frames, round and round
        self.ends = {}                                 # whose -> the frame its stream's sound ends at
        self.last = {}                                 # (whose, lane) -> (the frame its last sound starts at, it)
        self.one = np.zeros(CHUNK, dtype=np.int32)
        self.both = np.zeros((CHUNK, 2), dtype="<i2")
        super().__init__(cache)

    # -- its sounds: a file's, or made here ----------------------------------------------------------------------------
    def read(self, path):
        if not path.startswith("synth:"):
            return super().read(path)
        try:
            _, voice, notes, secs, *how = path.split(":")
            midis, secs = [int(n) for n in notes.split("+")], float(secs)
            if voice not in VOICES or not midis or len(midis) > 8 or not all(12 <= m <= 108 for m in midis) \
                    or not 0.02 <= secs <= 8:
                raise ValueError
        except ValueError:
            raise ValueError("not a sound this can make")
        return chord([self.note(voice, m) for m in midis], secs, how[0] if how else "")

    def note(self, voice, midi):
        """One note of an instrument, as loud as it can be: made the first time, and kept (here, and in its folder)."""
        got = self.notes.get((voice, midi))
        if got is not None:
            self.notes.move_to_end((voice, midi))
            return got
        kept = os.path.join(self.cache, f"{voice}-{midi}-{MADE}.wav") if self.cache else ""
        x = None
        if kept:
            try:
                rate, raw = SP.B.read_wav(kept)
                if rate == RATE and len(raw) > RATE // 10:
                    x = raw[:, 0].astype(np.float32) / 32767.0
            except (ValueError, OSError):
                pass
        if x is None:
            make, secs = VOICES[voice]
            x = make(midi, secs)
            x = (x / max(float(np.abs(x).max()), 1e-9)).astype(np.float32)
            if kept:
                try:
                    os.makedirs(self.cache, exist_ok=True)
                    SP.B.write_wav(kept, np.round(x * 32767.0).astype(np.int16))
                except OSError:
                    pass
        self.notes[(voice, midi)] = x
        while len(self.notes) > NOTES_HELD:            # (the ones used longest ago: let go of)
            self.notes.popitem(last=False)
        return x

    # -- when -----------------------------------------------------------------------------------------------------------
    def took(self, out):
        """(A chunk's just been written: aplay had taken all there was before it.)"""
        if self.pace_of is not out:                    # (aplay again: how fast it takes it, from the start)
            self.pace, self.pace_of = Pace(self.mixed + out.lag() / RATE + PACE_AFTER), out
        self.pace.add(self.mixed, self.frames)
        self.frames += CHUNK

    def heard_at(self, now):
        """When the first frame of the chunk about to be written is heard: aplay takes it a period from when it took
        the one before, and it's heard aplay's buffer later."""
        out = self.out
        took = self.pace.when(self.frames) if self.pace_of is out else None
        if took is None or abs(took - now) > 0.25:     # (not known yet, or it's stopped a while: from now)
            took = now
        return took + (out.lag() if out is not None else 1920) / RATE

    def watch(self, now, spoke=False):
        out = self.out
        last = out.breaks[-1] if out is not None and out.breaks else None
        super().watch(now, spoke)
        if out is not None and self.out is out and out.breaks and out.breaks[-1] != last:
            self.pace = Pace(now + PACE_AFTER)         # (the sound broke up: when it's heard has moved. Found again)

    # -- playing --------------------------------------------------------------------------------------------------------
    def ring(self, whose):
        got = self.rings.get(whose)
        if got is None:
            got = self.rings[whose] = np.zeros(RING, dtype=np.int32)
        return got

    @staticmethod
    def into(ring, at, x, op=np.add):
        """x added to a ring (np.subtract: taken out of it) from frame at on, round its end and on from its start if
        it comes to that. Where it is: nothing's made on the way."""
        i, n = at % RING, len(x)
        if i + n <= RING:
            op(ring[i:i + n], x, out=ring[i:i + n])
        else:
            k = RING - i
            op(ring[i:], x[:k], out=ring[i:])
            op(ring[:n - k], x[k:], out=ring[:n - k])

    def put(self, sid, at, gain=1.0, lane="", secs=0.0, whose=""):
        """A sound put in its player's stream, starting at frame at: all of it at once, as loud as it's to be, so
        playing it costs nothing more. In a lane, the sound before it there ends as this one starts (what's left of
        it is taken out again, but for a moment's fade). How many frames that took going over (0: it isn't a sound
        there is)."""
        with self.lock:
            have = self.sounds.get(sid)
        if have is None:
            return 0
        data = have[1]
        if data.ndim == 2:
            data = data.mean(axis=1)
        n = min(len(data), RING - 4 * CHUNK)
        cut = bool(secs and secs > 0 and int(secs * RATE) + FADE < n)
        if cut:
            n = int(secs * RATE) + FADE
        x = np.multiply(data[:n], max(0, min(512, int(round(gain * 256)))), dtype=np.int32, casting="unsafe")
        x >>= 8
        if cut:                                        # (its time's up before its end: it fades out there)
            x[-FADE:] = (x[-FADE:] * EDGE).astype(np.int32)
        ring, went = self.ring(whose), n
        if lane:
            was = self.last.get((whose, lane))
            if was is not None and was[0] <= at < was[0] + len(was[1]):
                tail = was[1][at - was[0]:]
                k = min(FADE, len(tail))
                self.into(ring, at, tail, np.subtract)
                self.into(ring, at, (tail[:k] * EDGE[:k]).astype(np.int32))
                went += len(tail)
            self.last[(whose, lane)] = (at, x)
        self.into(ring, at, x)
        self.ends[whose] = max(self.ends.get(whose, 0), at + n)
        return went

    def hush(self, whose=None):
        """A player's sound (everyone's: None) ended from here: what's in its stream fades out over a moment, the
        rest of it gone."""
        f = self.frames
        for tag in ([whose] if whose is not None else list(self.rings)):
            ring, end = self.rings.get(tag), self.ends.get(tag, 0)
            if ring is None or end <= f:
                continue
            k = min(FADE, end - f)
            idx = (f + np.arange(k)) % RING
            ring[idx] = (ring[idx] * EDGE[:k]).astype(np.int32)
            i, n = (f + k) % RING, min(end - f - k, RING - k)
            if n > 0:                                  # (the rest of it: gone)
                ring[i:i + n] = 0
                if i + n > RING:
                    ring[:i + n - RING] = 0
            self.ends[tag] = f + k
            for key in [key for key in self.last if key[0] == tag]:
                del self.last[key]

    def due(self, now):
        """The notes that start in the chunk about to be written: put in, each at its own frame. And the ones that
        start a moment after it (SOON), a sound or so of them a chunk: a bar's first beat, with a long sound from
        every player at once, is in before it comes, and no chunk had to wait for all of it."""
        first = self.heard_at(now)
        line = self.pace.line if self.pace_of is self.out else None
        rate = line[2] if line is not None else RATE   # (frames a second, as the sound card counts them)
        end, room = first + CHUNK / RATE, SOON_MOST
        while self.waiting:
            when = self.waiting[0][0]
            if when >= end and (room <= 0 or when >= first + SOON):
                break
            when, _, sid, gain, lane, secs, whose = heapq.heappop(self.waiting)
            if when < first - LATE:
                self.late += 1
                continue
            room -= self.put(sid, self.frames + max(0, int(round((when - first) * rate))), gain, lane, secs, whose)

    def mix(self):
        self.mixed = now = time.monotonic()
        if self.waiting:
            self.due(now)
        f, one, some = self.frames, self.one, False
        i = f % RING
        for tag, ring in self.rings.items():
            if self.ends.get(tag, 0) <= f:
                continue
            if not some:
                one[:] = 0
                some = True
            if i + CHUNK <= RING:
                seg = ring[i:i + CHUNK]
                one += seg
                seg[:] = 0
            else:
                k = RING - i
                one[:k] += ring[i:]
                one[k:] += ring[:CHUNK - k]
                ring[i:] = 0
                ring[:CHUNK - k] = 0
        if not some:
            self.limit = 1.0
            return SP.SILENCE
        if self.gain != 256:
            one *= self.gain
            one >>= 8
        peak = max(int(one.max()), -int(one.min()))
        was = self.limit
        fits = 1.0 if peak <= 32767 else 32700.0 / peak
        level = min(fits, was + (1.0 - was) * SP.LIMIT_BACK) if fits >= was else fits
        self.limit = 1.0 if level > 0.999 else level
        if was < 1.0 or level < 1.0:                   # (too loud together: turned down, and slowly back up)
            ramp = np.full(CHUNK, level, dtype=np.float32)
            if level < was:
                ramp[:SP.DOWN] = np.linspace(was, level, SP.DOWN, dtype=np.float32)
            else:
                ramp[:] = np.linspace(was, level, CHUNK, dtype=np.float32)
            one = np.clip((one * ramp).astype(np.int32), -32767, 32767)
        both = self.both
        both[:, 0] = one
        both[:, 1] = one
        return both.tobytes()

    def playing(self, now):
        """(Which sounds are playing isn't said: nobody's asked, and a band's would be all talk.)"""
        self.stale = False

    def stop_all(self, now):
        self.waiting = []
        self.soon.clear()
        self.hush()

    # -- what it's told -----------------------------------------------------------------------------------------------------
    def told(self, c, now):
        do = c.get("do")
        if do == "play":
            if isinstance(c.get("id"), str) and self.rec is None:
                gain, secs = c.get("gain", 1.0), c.get("secs", 0)
                ok = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (gain, secs))
                if self.out is None and not self.open(now, force=now - self.tried >= 0.3):
                    return                             # (the sound card won't open: not played later, out of the blue)
                if self.put(c["id"], self.frames, gain if ok else 1.0, str(c.get("lane") or ""), secs if ok else 0,
                            str(c.get("whose") or "you")):
                    self.feed()
        elif do == "at":
            for n in c.get("notes") or ():
                if not (isinstance(n, (list, tuple)) and len(n) == 6 and isinstance(n[1], str)
                        and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (n[0], n[2], n[4]))
                        and isinstance(n[3], str) and isinstance(n[5], str)):
                    continue
                if len(self.waiting) >= WAITING_MOST or abs(n[0] - now) > 600:
                    continue
                self.count += 1
                heapq.heappush(self.waiting, (float(n[0]), self.count, n[1], float(n[2]), n[3], float(n[4]), n[5]))
        elif do == "clear":
            whose = c.get("whose")
            if isinstance(whose, str) and whose:
                self.waiting = [n for n in self.waiting if n[6] != whose]
                heapq.heapify(self.waiting)
                self.hush(whose)
            else:
                self.stop_all(now)
        elif do == "stats":
            SP.say(**{"is": "stats", "late": self.late, "waiting": len(self.waiting),
                      "paced": self.pace.line is not None})
        elif do == "rest":
            self.stop_all(now)
            super().told(c, now)
        else:
            super().told(c, now)


def main():
    SP.Player = Player                                 # (soundplay's own main, with this player)
    SP.main()


if __name__ == "__main__":
    sys.exit(main())
