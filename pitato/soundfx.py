"""The Soundboard's effects and Bounce's own sounds (soundplay.py plays them): numpy only, made for a Pi Zero 2 W, so
every chunk costs a few dozen numpy calls and no more.

    Tone   a tilt: 0.5 = untouched, under it a low-pass (0 = muffled), over it a high shelf (1 = glassy)
    Echo   a ping-pong delay: distinct repeats from side to side, each only a touch darker (the wet sound only)
    Space  a reverb: the input smeared by four allpasses, then sixteen delay lines fed back through a mixing
           matrix, at half the rate (the wet sound only)
    Bus    the three chained: tone(x) + echo + space(tone(x) + echo)   (DEFAULTS: settings to start from)

    tone(name, midi)   one note of an instrument (int16, mono): Bell, Marimba, Kalimba, Glass, Pluck, Pad
    drone(midi)        a soft held pad on the root and fifth that loops without a seam (int16, stereo)

The effects take and give float32 (chunk, 2) arrays on the int16 scale (the Bus: int32). What run() gives back is a
buffer of the effect's own (or the input itself, when there's nothing to do): read it before the next run(), and
don't write to it. go() is run() for a caller that knows already whether its chunk is silence.

A numpy call on a few hundred frames costs more for being called than for the sums, and several times more when
its arrays aren't plain blocks of memory. So the layout is chosen to keep them plain: (chunk, 2) throughout, rings
sliced along their length, and the reverb's sums left to one matrix product.
"""
import cmath
import math
import random

import numpy as np

F32 = np.float32
QUIET = 0.05                     # a chunk whose squares add up to less than this is silence
DEFAULTS = dict(space=0.4, echo=0.3, echo_secs=0.3, tone=0.5)       # a Bus as Bounce's sliders start (bounce.py)
NAMES = ("Bell", "Marimba", "Kalimba", "Glass", "Pluck", "Pad")


def _ramp(a, b, n):
    """n steps from a (not included) to b, as a column: a gain glided over a chunk."""
    return (a + (b - a) * np.arange(1, n + 1, dtype=np.float64) / n).astype(F32)[:, None]


class _Fx:
    """What the three effects share."""

    def _base(self, rate, chunk):
        self.rate, self.c = int(rate), int(chunk)
        self.zero = np.zeros((chunk, 2), F32)
        self.left = 0                                  # chunks of tail still to come

    def run(self, x):
        if self.resting():
            return self.rest(x)
        if x.dtype != F32 or not x.flags.c_contiguous:
            x = np.ascontiguousarray(x, dtype=F32)
        flat = x.reshape(-1)
        y = self.go(x, float(np.dot(flat, flat)) > QUIET)
        return self.zero if y is None else y

    def rest(self, x):
        return self.zero

    def ringing(self):
        return self.left > 0


class Tone(_Fx):
    """Darker or brighter, around NEUTRAL (untouched: the input itself is given back). Under it, a low-pass of two
    equal poles, its corner (3 dB down) falling from 5 kHz to 300 Hz at 0. Over it, a high shelf: the input plus
    what one pole at 2 kHz doesn't pass, so the top comes up by as much as 12 dB at 1 (half of that at 1 to
    1.5 kHz) and the bottom stays as it was. A pole's recursion, y[n] = a*y[n-1] + (1-a)*x[n], is done as a
    running sum over the chunk: y[n] = a**n * sum(x[k] * a**-k), in float64 (a**-k gets big), left and right
    summed at once as the two halves of complex numbers.

    The shelf adds level (up to 4 times, for what's all top): whoever plays the Bus's output must clip it."""
    NEUTRAL = 0.5
    LOW = (300.0, 5000.0)                              # the low-pass's corner (Hz) at 0, and just under NEUTRAL
    SHELF = (2000.0, 13.0)                             # the shelf's pole (Hz), and its boost at 1 (dB, at the very top)

    def __init__(self, rate=48000, chunk=384):
        self._base(rate, chunk)
        self.t = np.zeros((chunk, 2), np.float64)
        self.sums = self.t.reshape(-1).view(np.complex128)
        self.t32 = np.zeros((chunk, 2), F32)
        self.y = np.zeros((chunk, 2), F32)
        self.y2 = np.zeros((chunk, 2), F32)
        self.z = self.z2 = 0j                          # a * the last frame out of each pole: where the next chunk
                                                       # starts
        self.amt = self.want = self.NEUTRAL
        self.cur = None
        self.cool = True                               # nothing left in the filter
        self.heard = False                             # the chunk before had sound in it

    def set(self, amount):
        self.want = min(1.0, max(0.0, float(amount)))

    def cutoff(self, amount):
        """Where the low-pass is 3 dB down (Hz): even steps of amount are even musical steps."""
        return self.LOW[0] * (self.LOW[1] / self.LOW[0]) ** (min(amount, self.NEUTRAL) / self.NEUTRAL)

    def boost(self, amount):
        """How far the shelf lifts the top (dB)."""
        return self.SHELF[1] * max(0.0, amount - self.NEUTRAL) / (1.0 - self.NEUTRAL)

    def _design(self, amount):
        if amount == self.NEUTRAL:
            return None
        if amount < self.NEUTRAL:                      # two poles: each sits above the corner they make together
            hz, two, wet, dry = self.cutoff(amount) / math.sqrt(math.sqrt(2.0) - 1.0), True, 1.0, 0.0
        else:                                          # x + g * (x - lowpass(x))
            g = 10.0 ** (self.boost(amount) / 20.0) - 1.0
            hz, two, wet, dry = self.SHELF[0], False, -g, 1.0 + g
        a = math.exp(-2 * math.pi * hz / self.rate)
        a = max(a, 1e-290 ** (1.0 / self.c))           # (a**-k has to fit in a float64 to the chunk's end)
        k = np.repeat(np.arange(self.c, dtype=np.float64), 2).reshape(self.c, 2)
        return dict(up=(1 - a) * a ** -k, dn=a ** k * (wet * (1 - a) if two else wet), ac=a ** self.c,
                    ac1=a ** self.c * (1 - a), i1=1 / (1 - a), two=two, dry=dry)

    def _filter(self, d, x, y):
        t, sums = self.t, self.sums
        np.multiply(x, d["up"], out=t)
        sums[0] += self.z
        np.add.accumulate(sums, out=sums)
        self.z = sums[-1] * d["ac"]
        if d["two"]:                                   # the second pole: the first's sums are its input, but for
            sums[0] += self.z2 * d["i1"]               # (1-a): that's in dn, and taken off what's carried over
            np.add.accumulate(sums, out=sums)
            self.z2 = sums[-1] * d["ac1"]
        else:
            self.z2 = 0j
        t *= d["dn"]
        np.copyto(y, t, casting="same_kind")
        if d["dry"]:
            np.multiply(x, d["dry"], out=self.t32)
            y += self.t32
        return y

    def go(self, x, live=True):
        if self.want != self.amt:
            old, self.cur, self.amt = self.cur, self._design(self.want), self.want
            if self.heard:                             # a new setting under a sound: the old and the new, crossfaded
                z, z2 = self.z, self.z2
                a = self._filter(old, x, self.y2) if old else x
                self.z, self.z2 = z, z2
                b = self._filter(self.cur, x, self.y) if self.cur else x
                np.subtract(b, a, out=self.t32)
                self.t32 *= _ramp(0.0, 1.0, self.c)
                np.add(a, self.t32, out=self.y)
                self.heard, self.cool = live, False
                if not self.cur or not live:
                    self.clear()
                return self.y
        self.heard = live
        if self.cur is None or (self.cool and not live):
            return x
        y = self._filter(self.cur, x, self.y)
        self.cool = False
        if not live:                                   # that was the filter running out: nothing's left in it
            self.clear()
        return y

    def resting(self):
        return self.amt == self.NEUTRAL and self.want == self.NEUTRAL

    def rest(self, x):
        self.heard = True                              # (for all it knows)
        return x

    def ringing(self):
        return False

    def clear(self):
        self.z = self.z2 = 0j
        self.cool = True


class Echo(_Fx):
    """A ping-pong delay. The ring holds what's to be heard secs later, as loud as it will be heard: each chunk
    written is the input (left and right together, nearly all to the left) plus what's heard now, its speakers
    swapped, quieter, and smoothed a very little over three frames (so each repeat is a touch darker: 1 dB less
    at 8 kHz, and still crisp). So the wet sound is just a slice of the ring. The swap costs nothing: the ring
    looked at from one number further on is frames of (right, the next left)."""
    SECS = (0.08, 0.8)
    PAN = (1.0, 0.2)                                   # the first repeat, left and right
    SMOOTH = 6.0                                       # a repeat's frames: (1, SMOOTH, 1) of the one before's

    def __init__(self, rate=48000, chunk=384):
        self._base(rate, chunk)
        c = self.c
        self.n = c * (int(self.SECS[1] * rate) // c + 4)
        self.flat = np.zeros(2 * self.n, F32)
        self.ring = self.flat.reshape(self.n, 2)
        self.swap = self.flat[1:-1].reshape(self.n - 1, 2)          # (right, the next left)
        self.t = np.zeros((c, 2), F32)
        self.t2 = np.zeros((c, 2), F32)
        self.w = 0                                     # the frame the next chunk's written at
        self.amt = self.want = 0.0
        self.d = self.d_want = self._frames(0.3)
        self._adopt()

    def _frames(self, secs):
        secs = min(self.SECS[1], max(self.SECS[0], float(secs)))
        return max(self.c + 3, int(round(secs * self.rate)))

    def set(self, amount, secs=None):
        self.want = min(1.0, max(0.0, float(amount)))
        if secs is not None:
            self.d_want = self._frames(secs)

    def gains(self, amount):
        """How much of each repeat comes back (0.35: a few repeats; 0.7: a long trail), and how loud the first
        is, of the input (10 dB under it at 0.3, 4 dB under at 1)."""
        return 0.35 + 0.35 * amount, 0.63 * amount ** 0.575

    def _adopt(self):
        self.amt, self.d = self.want, self.d_want
        self.fb, lvl = self.gains(self.amt)
        self.q = self.fb / (self.SMOOTH + 2.0)
        self.mix = np.array([self.PAN, self.PAN], F32) * F32(lvl * 0.5)     # (frames, 2) @ this: the input's way in
        reps = math.log(5e-4) / math.log(self.fb)      # repeats until it's 66 dB down
        self.tail = int((reps + 1) * self.d / self.c) + 2

    def _tap(self, d):
        """What was written d frames ago, and what it is swapped: c + 2 frames of each, from the frame before."""
        r, k = (self.w - d - 1) % self.n, self.c + 2
        if r + k < self.n:
            return self.ring[r:r + k], self.swap[r:r + k]
        flat = np.concatenate((self.flat[2 * r:], self.flat[:2 * (r + k - self.n) + 1]))    # (round the ring's end)
        return flat[:-1].reshape(k, 2), flat[1:].reshape(k, 2)

    def go(self, x, live=True):
        new = self.want != self.amt or self.d_want != self.d
        if new and self.left <= 0:                     # nothing sounding: the new settings, at once
            self._adopt()
            new = False
        if live and self.amt:
            self.left = self.tail
        elif self.left <= 0:
            return None
        c, q = self.c, self.q
        src, back = self._tap(self.d)
        wr = self.ring[self.w:self.w + c]
        np.matmul(x, self.mix, out=self.t)
        if new:                                        # glided: the gains, and from the old time to the new
            d0 = self.d
            self._adopt()
            np.matmul(x, self.mix, out=self.t2)
            self.t2 -= self.t
            self.t2 *= _ramp(0.0, 1.0, c)
            self.t += self.t2
            q = _ramp(q, self.q, c)
            if self.d != d0:
                fade = (np.arange(c + 2, dtype=F32) / F32(c + 1))[:, None]
                src2, back2 = self._tap(self.d)
                src, back = src + (src2 - src) * fade, back + (back2 - back) * fade
            self.left = self.tail
        np.add(back[:-2], back[2:], out=wr)
        np.multiply(back[1:-1], F32(self.SMOOTH), out=self.t2)
        wr += self.t2
        wr *= q
        wr += self.t
        self.w = (self.w + c) % self.n
        self.left -= 1
        if self.left <= 0:
            self.clear()
            return None
        return src[1:-1]

    def resting(self):
        return not self.want and self.left <= 0

    def clear(self):
        self.flat[:] = 0
        self.left = 0


def _primes_from(lengths):
    """Each length moved up to the next prime no other has: delay lines that never fall in step."""
    out = []
    for n in lengths:
        n = int(n) | 1
        while n in out or any(n % k == 0 for k in range(3, int(n ** 0.5) + 1, 2)):
            n += 2
        out.append(n)
    return out


class Space(_Fx):
    """A reverb at half the rate. N delay lines (23 to 97 ms) are the rows of one ring; all are read at the same
    column, and each is written its own delay further on. So a chunk is one matrix product: the rows as read (the
    lines, under them the smear's delays, and the input) times a matrix that holds the decay, the mixing of the
    lines into each other (a Hadamard matrix: nothing lost, every line into every line), the smear, the input's
    way in and the taps out. The product comes out a row for each frame, so one sum along it (each frame plus
    some of the frame before) does two jobs: each line's new chunk loses a little of its top (so the tail
    darkens), and the taps get their in-between frames, for the full rate. Then the lines are written, and four
    columns of it are the wet sound. Turned to 0, it's the smallest room with nothing going in: what's sounding
    dies away in half a second.

    The smear is what keeps a sharp attack from coming back as separate slaps: before the lines, the input (left
    and right together) goes through allpasses one after another, which turn one click into hundreds over a
    tenth of a second and leave the tone as it was. Each is a delay of a chunk or more (so it's more rows of the
    same ring, and what an allpass does at once, y = v - g*x and v' = x + g*y, is more of the same matrix), and
    the click itself, straight through them, is left out: the wash swells in rather than knocks."""
    N = 16
    MS = (23.0, 97.0)            # the shortest and longest lines
    SMEAR = (8.3, 9.7, 11.3, 13.1)                     # the allpasses' delays (ms; no less than a chunk)
    SMEAR_G = (0.35, 0.6)        # ...and how much each feeds back: this and the amount, and at most
    SEED = 0                     # which signs the lines get (one of the smoother of a few dozen tried)

    def __init__(self, rate=48000, chunk=384):
        assert chunk % 2 == 0
        self._base(rate, chunk)
        n, h, hr = self.N, chunk // 2, rate / 2.0
        self.h = h
        self.na = na = len(self.SMEAR)
        low = max(self.MS[0] * hr / 1000, h + 2)
        both = _primes_from([max(ms * hr / 1000, h + 2) for ms in self.SMEAR]
                            + [low * (self.MS[1] / self.MS[0]) ** (i / (n - 1.0)) for i in range(n)])
        self.ad, self.d = ad, d = both[:na], both[na:]
        self.len = ln = h * ((max(both) + h) // h + 1)              # the ring: a whole number of chunks
        rows = n + na + 4                              # the ring's: the lines, the smear, the input (4)
        self.k = k = n + 4 + na                        # the product's: the lines, the wet sound (4), the smear
        self.ring = np.zeros((rows, ln), F32)
        self.u = np.zeros((h + 1, k), F32)             # the product: a row for each frame (the first: the last of
        self.v = np.zeros((h + 1, k), F32)             # the chunk before); and with some of the frame before added
        self.v2 = np.zeros((h + 1, k), F32)
        self.out = np.zeros((chunk, 2), F32)
        self.out4 = self.out.reshape(h, 4)             # (two frames to a row: left, right, left, right)
        rnd = random.Random(self.SEED)
        sign = lambda: np.array([rnd.choice((-1.0, 1.0)) for _ in range(n)])
        half = lambda: np.array(rnd.sample([-1.0, 1.0] * (n // 2), n))
        had = np.array([[1.0]])
        while len(had) < n:
            had = np.block([[had, had], [had, -had]])
        self.mix = (had[rnd.sample(range(n), n)] * sign()) / math.sqrt(n)
        ins = [(sign(), half())[0] for _ in range(3)]  # (three drawn, one used: the signs after stay as they were)
        self.inp = ins[0] / math.sqrt(n)               # the smeared input's way into each line
        s = sign()
        self.taps = np.stack((s, s * half()))          # left and right: nothing in common
        # where each row's chunk is written, for each place the ring can be: whole, or in two where it wraps
        cols = [(i, d[i], self.v[1:, i]) for i in range(n)] + [(n + j, ad[j], self.v[1:, n + 4 + j]) for j in range(na)]
        self.writes = []
        for ph in range(ln // h):
            todo = []
            for row, far, col in cols:
                q = (ph * h + far) % ln
                if q + h <= ln:
                    todo.append((self.ring[row, q:q + h], col))
                else:
                    todo += [(self.ring[row, q:], col[:ln - q]), (self.ring[row, :q + h - ln], col[ln - q:])]
            self.writes.append(todo)
        self.ph = 0
        self.amt = self.want = 0.0
        self.cur = self._design(0.0)

    def _smear(self, g):
        """The allpasses as rows of the matrix: what each writes, and what the last gives the lines."""
        n, na = self.N, self.na
        a = np.zeros(n + na + 4)
        a[n + na:] = 0.5                               # in: left and right, the even frames and the odd, as one
        rows = np.zeros((na, n + na + 4))
        for j in range(na):
            y = -g * a
            y[n + j] += 1.0
            rows[j] = a + g * y
            a = y
        a[n + na:] = 0.0                               # (the click itself, straight through: left out)
        return rows, a

    def set(self, amount):
        self.want = min(1.0, max(0.0, float(amount)))

    def decay(self, amount):
        """Seconds the tail takes to fall 60 dB (at the low end: the top's gone sooner)."""
        return 0.3 + 5.7 * amount ** 1.5

    def _design(self, amount, wet=0.0):
        """All a setting comes to. At 0: nothing goes in, and what's left is as loud as it was (wet)."""
        n, na, h, hr = self.N, self.na, self.h, self.rate / 2.0
        d = np.array(self.d, dtype=np.float64)
        g = 10.0 ** (-3.0 * d / (self.decay(amount) * hr))          # each line: what a trip round it keeps
        b = np.minimum(0.45, (0.28 - 0.2 * amount) * d / d.mean())  # ...and how much of its top it loses
        m = np.zeros((self.k, n + na + 4))
        m[:n, :n] = (1 - b)[:, None] * self.mix * g
        smear, fed = self._smear(min(self.SMEAR_G[1], self.SMEAR_G[0] + amount))   # (a small room: less of it,
                                                                                    #  or it rings)
        m[:n] += ((1 - b) * self.inp)[:, None] * fed
        m[n + 4:] = smear
        if amount:
            wet = 10.0 ** ((-18.0 + 15.0 * amount) / 20.0) * min(1.0, amount / 0.08)
            wet *= math.sqrt(1.0 - float(np.mean(g * g)))           # (a longer tail: no louder for it)
        else:
            m[:, n + na:] = 0.0                        # (what's in the smear still drains into the lines)
        m[n:n + 2, :n] = self.taps * (wet * 0.5)       # the taps, for the frames between (half this and half the
        m[n + 2:n + 4, :n] = self.taps * wet           # one before: 1 in 'before' below), and for the frames themselves
        before = np.concatenate((b / (1 - b), [1.0, 1.0, 0.0, 0.0], np.zeros(na)))  # how much of the frame before
        tail = int((self.decay(amount) * 1.15 + 0.2) * self.rate / self.c)     # chunks till it's 69 dB down
        return dict(m=np.ascontiguousarray(m.T, dtype=F32), before=np.tile(before, h).astype(F32), wet=wet, tail=tail)

    def _lines(self, d, src, v):
        """The rows' next chunk and the wet sound, into v's columns."""
        k = self.k
        np.matmul(src, d["m"], out=self.u[1:])
        uf, vf = self.u.reshape(-1), v.reshape(-1)
        np.multiply(uf[:-k], d["before"], out=vf[k:])
        vf[k:] += uf[k:]
        return v

    def go(self, x, live=True):
        new = self.want != self.amt
        if new and self.left <= 0:                     # nothing sounding: the new setting, at once
            self.cur, self.amt, new = self._design(self.want), self.want, False
        cur = self.cur
        if live and self.amt:
            self.left = cur["tail"]
        elif self.left <= 0:
            return None
        n, h, ring, u = self.N, self.h, self.ring, self.u
        ph = self.ph
        p = ph * h
        self.ph = (ph + 1) % len(self.writes)
        ring[n + self.na:, p:p + h] = x.reshape(h, 4).T             # the input: a row each for left and right,
        src = ring[:, p:p + h].T                                    # ...even frames and odd
        v = self._lines(cur, src, self.v)
        if new:                                        # the old setting's rows and wet sound and the new one's,
            self.v2[:] = v                             # crossfaded
            self.amt = self.want
            self.cur = cur = self._design(self.want, cur["wet"])
            self._lines(cur, src, v)
            v -= self.v2
            v[1:] *= _ramp(0.0, 1.0, h)
            v += self.v2
            self.left = cur["tail"]
        for to, col in self.writes[ph]:
            to[:] = col
        self.out4[:] = v[1:, n:n + 4]
        u[0] = u[-1]
        self.left -= 1
        if self.left <= 0:
            self.clear()
        return self.out

    def resting(self):
        return not self.want and self.left <= 0

    def clear(self):
        self.ring[:] = 0
        self.u[:] = 0
        self.left = 0


class Bus:
    """The three chained, for Bounce's bus: int32 (chunk, 2) in and out.
    out = tone(x) + echo(tone(x)) + space(tone(x) + echo)."""

    def __init__(self, rate=48000, chunk=384):
        self.tone, self.echo, self.space = Tone(rate, chunk), Echo(rate, chunk), Space(rate, chunk)
        self.f = np.zeros((chunk, 2), F32)
        self.flat = self.f.reshape(-1)
        self.s = np.zeros((chunk, 2), F32)
        self.o = np.zeros((chunk, 2), np.int32)

    def set(self, space=None, echo=None, echo_secs=None, tone=None):
        if space is not None:
            self.space.set(space)
        if echo is not None or echo_secs is not None:
            self.echo.set(self.echo.want if echo is None else echo, echo_secs)
        if tone is not None:
            self.tone.set(tone)

    def ringing(self):
        return self.echo.left > 0 or self.space.left > 0

    def clear(self):
        self.tone.clear()
        self.echo.clear()
        self.space.clear()

    def run(self, x):
        f, tone, echo, space = self.f, self.tone, self.echo, self.space
        np.copyto(f, x, casting="unsafe")
        live = float(np.dot(self.flat, self.flat)) > QUIET
        s = tone.go(f, live)
        if not live and s is f and echo.left <= 0 and space.left <= 0:
            return x
        e = echo.go(s, live) if echo.want or echo.left > 0 else None
        if e is not None:
            s = np.add(s, e, out=self.s)
        r = space.go(s, live or e is not None) if space.want or space.left > 0 else None
        if r is not None:
            s = np.add(s, r, out=self.s)
        if s is f:
            return x
        np.copyto(self.o, s, casting="unsafe")
        return self.o


# ---- the instruments ----

SECS = {"Bell": 2.4, "Marimba": 1.3, "Kalimba": 1.8, "Glass": 2.5, "Pluck": 1.7, "Pad": 2.5}
LOUD = {"Pad": 0.30}             # the peak, of full scale (the others: 0.42)
TOP = 9000.0                     # no overtone's made above this (Hz): a note played higher still has room
TILT = 5000.0                    # ...and they're softer as they near it


def _sines(f, n, rate, parts):
    """Overtones added up: each (times the note, how loud, seconds to fall to 1/e). All start at zero, rising."""
    t = np.arange(n, dtype=np.float64) / rate
    t32 = t.astype(F32)
    x = np.zeros(n, F32)
    for ratio, amp, secs in parts:
        fk = f * ratio
        if fk > TOP:
            continue
        cyc = t * fk
        cyc -= np.floor(cyc)                           # (kept within a turn: float32 is exact enough then)
        s = np.sin((cyc * (2 * math.pi)).astype(F32))
        if secs:
            s *= np.exp(t32 * F32(-1.0 / secs))
        x += s * F32(amp / (1.0 + (fk / TILT) ** 2))
    return x


def tone(name, midi, rate=48000):
    """One note: int16, mono, at most 2.5 s."""
    if name not in SECS:
        raise ValueError("no instrument called %r" % (name,))
    f = 440.0 * 2.0 ** ((midi - 69) / 12.0)
    n = int(SECS[name] * rate)
    k = (261.63 / f) ** 0.35                           # higher notes die away sooner
    hz = 1.0 / f
    rise, fall = 0.002, 0.04
    if name == "Bell":             # a soft bell: its overtones a little out of tune, two of them beating slowly
        parts = ((1, 1.0, 1.0 * k), (1 + 0.6 * hz, 0.3, 1.0 * k), (2, 0.4, 0.55 * k), (2 + 0.9 * hz, 0.1, 0.55 * k),
                 (2.76, 0.2, 0.32 * k), (4.07, 0.09, 0.2 * k), (5.4, 0.035, 0.12 * k))
    elif name == "Marimba":        # a wooden bar: the note, and a knock two octaves up that's gone at once
        parts = ((1, 1.0, 0.42 * k), (2, 0.04, 0.2 * k), (4, 0.22, 0.08 * k), (10, 0.05, 0.025 * k))
    elif name == "Kalimba":        # a metal tine: nearly pure, with a short high ting as it's let go
        parts = ((1, 1.0, 0.8 * k), (2, 0.1, 0.35 * k), (3, 0.04, 0.2 * k), (6.27, 0.12, 0.06 * k))
    elif name == "Glass":          # a rubbed glass: slow to speak, long, shimmering
        parts = ((1, 1.0, 1.3 * k), (1 + 0.4 * hz, 0.4, 1.3 * k), (2.003, 0.18, 0.8 * k), (3.01, 0.07, 0.5 * k),
                 (4.2, 0.03, 0.2 * k))
        rise = 0.03
    elif name == "Pluck":          # a string plucked a quarter of the way along: the higher overtones gone first
        parts = [(j * math.sqrt(1 + 0.00025 * j * j), math.sin(j * math.pi * 0.28) / j ** 1.1, 0.9 * k / (1 + 0.45 * j))
                 for j in range(1, 15)]
    else:                          # a pad: three of it a few cents apart, coming up slowly
        parts = [(j * 2.0 ** (cents / 1200.0), a, 0) for cents in (-6.0, 0.0, 7.0)
                 for j, a in ((1, 1.0), (2, 0.32), (3, 0.12), (4, 0.05))]
        rise, fall = 0.14, 0.3
    x = _sines(f, n, rate, parts)
    if name == "Pad":
        x *= np.exp(np.arange(n, dtype=F32) * F32(-1.0 / (1.6 * rate)))
    x -= x.mean()
    for edge in (x[:int(rise * rate)], x[:-int(fall * rate) - 1:-1]):      # in from nothing, and out to it
        edge *= 0.5 - 0.5 * np.cos(np.pi * np.arange(len(edge), dtype=F32) / len(edge))
    return (x * (LOUD.get(name, 0.42) * 32767.0 / float(np.abs(x).max()))).astype(np.int16)


DRONE_PEAK, DRONE_RMS = 0.25, 0.10                     # of full scale: steady, not peaky
DRONE_BAND = (350.0, 1800.0)                           # where its overtones are let through (Hz), gently


def drone(midi, secs=4.0, rate=48000):
    """A held pad on the root and its fifth, slowly moving: int16 (n, 2), to be looped. midi is the key's own
    root (55 to 66: G3 to F#4). It's made as a spectrum and turned into sound in one step: a dozen overtones of
    the root and eight of the fifth, weighted to sit between 250 Hz and 2 kHz (a small speaker has nothing
    under that), each as three voices a couple of cents apart, the low one mostly in the left speaker and the
    high one mostly in the right. Every voice turns a whole number of times in the loop, so its end runs into
    its start, and their beating against each other is the slow movement. Then the level is evened out: the
    slow swells are ridden down (most of the way), and the peaks are rounded off (tanh, hard enough that the
    peak is DRONE_PEAK when the RMS is DRONE_RMS). Both are the same all the way round the loop: still no seam."""
    f = 440.0 * 2.0 ** ((midi - 69) / 12.0)
    n = int(round(secs * rate))
    spec = np.zeros((2, n // 2 + 1), np.complex128)
    parts = [(j, 1.0 / j ** 0.7) for j in range(1, 13)] + [(1.5 * j, 0.6 / j ** 0.7) for j in range(1, 9)]
    for i, (ratio, amp) in enumerate(parts):
        fk = f * ratio
        if fk > min(4000.0, 0.4 * rate):
            continue
        amp /= math.sqrt(1.0 + (DRONE_BAND[0] / fk) ** 4) * (1.0 + (fk / DRONE_BAND[1]) ** 2)
        turns = int(round(fk * n / rate))
        apart = max(1, int(round(turns * 0.001)))
        for j, (off, left, right) in enumerate(((-apart, 1.0, 0.25), (0, 0.7, 0.7), (apart, 0.25, 1.0))):
            turn = amp * cmath.exp(2j * math.pi * (((3 * i + j) * 0.618034) % 1.0))
            spec[0, turns + off] += left * turn
            spec[1, turns + off] += right * turn
    out = np.fft.irfft(spec, n, axis=1).astype(F32)
    # the slow swells, ridden: its power over a quarter second (round the loop's end), and most of that undone
    w = max(1, min(n // 2, int(0.125 * rate)))
    p = out[0] * out[0] + out[1] * out[1]
    run = np.cumsum(np.concatenate((p[-w:], p, p[:w])), dtype=np.float64)
    env = run[2 * w:] - run[:-2 * w]
    out *= ((env.mean() / env) ** 0.4).astype(F32)
    # the peaks, rounded: how hard, found on every eighth frame
    some = np.ascontiguousarray(out[:, ::8])
    top = float(np.abs(out).max())
    lo, hi = 0.02 / top, 20.0 / top
    for _ in range(14):
        k = math.sqrt(lo * hi)
        y = np.tanh(some * F32(k))
        if math.tanh(k * top) > DRONE_PEAK / DRONE_RMS * math.sqrt(float(np.mean(y * y))):
            lo = k                                     # still too peaky: harder
        else:
            hi = k
    out = np.tanh(out * F32(math.sqrt(lo * hi)))
    out -= out.mean(axis=1, keepdims=True)
    return (out.T * (DRONE_PEAK * 32767.0 / float(np.abs(out).max()))).astype(np.int16)


if __name__ == "__main__":                             # what it costs on this computer: python3 soundfx.py
    import sys
    import time
    note = tone("Bell", 60).astype(F32)
    x = np.zeros((48000 * 4, 2), F32)                  # (four seconds of a note every quarter second)
    for at in range(0, len(x) - len(note), 12000):
        x[at:at + len(note)] += note[:, None] * F32(0.3 + (at % 7) / 10)
    chunks = [np.ascontiguousarray(x[i:i + 384]).astype(np.int32) for i in range(0, len(x) - 383, 384)]
    print("python %s, numpy %s" % (sys.version.split()[0], np.__version__))

    def median(make, items, runs=5):
        """What the median chunk takes (microseconds), in the best of a few runs: this computer's other work left
        out."""
        best = []
        for _ in range(runs):
            run, took = make().run, []
            for c in items:
                t = time.perf_counter()
                run(c)
                took.append(time.perf_counter() - t)
            best.append(sorted(took)[len(took) // 2] * 1e6)
        return min(best)

    for label, sets in (("as they start", DEFAULTS), ("all the way up", dict(space=1, echo=1, echo_secs=0.8, tone=0))):
        def make(sets=sets):
            bus = Bus()
            bus.set(**sets)
            return bus
        us = median(make, chunks)
        print("the effects, %s: %.0f microseconds for each 8 ms of sound (%.1f%% of a core)" % (label, us, us / 80))
    floats = [c.astype(F32) for c in chunks]
    print("each effect, off: " + ", ".join("%s %.1f" % (fx.__name__, median(fx, floats))
                                           for fx in (Tone, Echo, Space)) + " microseconds")
    for name in NAMES:
        t = time.perf_counter()
        tone(name, 60)
        print("%s: made in %.0f ms" % (name, (time.perf_counter() - t) * 1000))
    t = time.perf_counter()
    drone(60)
    print("the drone: made in %.0f ms" % ((time.perf_counter() - t) * 1000))
