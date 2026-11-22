"""The Soundboard's effects and Bounce's own sounds (pitato/soundfx.py), on their own: each bypassed or off, exactly
what went in (or nothing); never anything but numbers, and never louder and louder, at their most with the loudest
noise; their tails ringing only as long as they should, and the next sound clean after them; the echo's repeats at
their very frames, from one side then the other, each quieter and darker; the space longer and louder as it's turned
up, wide, with no echo of itself, darker as it dies away; the tone softer up high the more it's turned down, and the
same whatever the chunks; every change of setting without a click; the three in a row as the player has them;
Bounce's instruments in tune at each note they're made at, soft at both ends, quick to make; the drone a loop with no
seam; and other rates and chunk sizes."""
import math
import os
import sys
import time
import traceback
from paths import ROOT  # noqa: E402  (the Pietato folder)
sys.path.insert(0, os.path.join(ROOT, "pitato"))

import numpy as np

import soundfx as fx

ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


R, C = 48000, 384


def render(unit, x, extra=0.0, sets=None):
    """x through unit a chunk at a time (extra: seconds of silence after it); sets: {chunk number: set()'s
    arguments}. The output, copied chunk by chunk as a caller would read it."""
    n = (len(x) + int(extra * R) + C - 1) // C * C
    xx = np.zeros((n, 2), x.dtype)
    xx[:len(x)] = x
    out = np.zeros_like(xx)
    for k, i in enumerate(range(0, n, C)):
        if sets and k in sets:
            unit.set(**sets[k]) if isinstance(sets[k], dict) else unit.set(*sets[k])
        y = unit.run(xx[i:i + C])
        assert y.shape == (C, 2) and y.dtype == x.dtype, (y.shape, y.dtype)
        out[i:i + C] = y
    return out


def noise(secs, amp=32767.0, seed=1, mono=False):
    rnd = np.random.default_rng(seed)
    x = rnd.uniform(-amp, amp, (int(secs * R), 1 if mono else 2)).astype(np.float32)
    return np.repeat(x, 2, axis=1) if mono else x


def click(at=0, amp=10000.0, n=C):
    x = np.zeros((n, 2), np.float32)
    x[at] = amp
    return x


def sine(hz, secs, amp=10000.0):
    s = (amp * np.sin(2 * np.pi * hz * np.arange(int(secs * R)) / R)).astype(np.float32)
    return np.stack((s, s), axis=1)


def db(x):
    return 10 * math.log10(float(np.mean(np.square(x, dtype=np.float64))) + 1e-30)


def rt60(ir):
    """Seconds to fall 60 dB, from the slope between 5 and 35 dB down."""
    left = np.cumsum(np.square(ir, dtype=np.float64).sum(axis=1)[::-1])[::-1]
    left = 10 * np.log10(left / left[0] + 1e-30)
    return (int(np.argmax(left < -35)) - int(np.argmax(left < -5))) / R * 2


def idle_after(unit, x, most):
    """Seconds after x ends that unit still rings (asserts it's no more than most)."""
    render(unit, x)
    silence = np.zeros((C, 2), x.dtype)
    for k in range(int(most * R / C) + 2):
        if not unit.ringing():
            return k * C / R
        unit.run(silence)
    raise AssertionError("still ringing %.1f s after its input stopped" % most)


# ---- the checks ----

def passthrough():
    x = noise(0.1)
    t = fx.Tone(R, C)
    first = x[:C]
    assert t.run(first) is first                       # (not even copied)
    assert np.array_equal(render(t, x)[:len(x)], x) and not t.ringing()
    for unit in (fx.Echo(R, C), fx.Space(R, C)):
        assert not np.any(render(unit, x)) and not unit.ringing()
    bus = fx.Bus(R, C)
    xi = x.astype(np.int32)
    assert np.array_equal(render(bus, xi)[:len(xi)], xi) and not bus.ringing()
    bus.set(space=0.0, echo=0.0, echo_secs=0.4, tone=1.0)
    assert np.array_equal(render(bus, xi)[:len(xi)], xi)
    # ...and a Bus with only its tone on gives just what Tone gives
    bus.set(tone=0.4)
    t.set(0.4)
    want = render(t, x.astype(np.int32).astype(np.float32))
    assert np.max(np.abs(render(bus, xi) - want)) <= 1.0


def finite():
    x = noise(0.6, seed=2)
    x[int(0.2 * R):int(0.4 * R)] = 0
    for unit, args in ((fx.Tone(R, C), (0.2,)), (fx.Echo(R, C), (0.8, 0.1)), (fx.Space(R, C), (0.7,))):
        unit.set(*args)
        assert np.all(np.isfinite(render(unit, x, 1.0)))
    bus = fx.Bus(R, C)
    bus.set(space=1.0, echo=1.0, echo_secs=0.08, tone=0.0)
    y = render(bus, x.astype(np.int32), 1.0)
    assert y.dtype == np.int32 and np.any(y)


def stable():
    x = noise(2.0, seed=3)                             # two seconds of full-scale noise
    for unit, args, most in ((fx.Tone(R, C), (0.0,), 1.01), (fx.Echo(R, C), (1.0, 0.08), 1.6),
                             (fx.Space(R, C), (1.0,), 1.6)):
        unit.set(*args)
        y = render(unit, x, 9.0)
        peak = float(np.abs(y).max())
        assert peak <= most * 32767, (type(unit).__name__, peak / 32767)
        after = [db(y[int(s * R):int((s + 1) * R)]) for s in (2.0, 3.0, 5.0, 7.0)]
        assert all(b < a - 3 or b < -200 for a, b in zip(after, after[1:])), (type(unit).__name__, after)
    bus = fx.Bus(R, C)
    bus.set(space=1.0, echo=1.0, echo_secs=0.8, tone=0.0)
    y = render(bus, x.astype(np.int32), 20.0).astype(np.float64)
    assert np.abs(y).max() <= 3 * 32767
    after = [db(y[int(s * R):int((s + 2) * R)]) for s in (2.0, 5.0, 8.0, 11.0)]
    assert all(b < a - 3 for a, b in zip(after, after[1:])), after
    assert not np.any(y[-C:]) and not bus.ringing()


def ringing_ends():
    x = noise(0.3, amp=20000.0, seed=4)
    for make, args in ((fx.Echo, (0.5, 0.2)), (fx.Echo, (1.0, 0.8)), (fx.Space, (0.2,)), (fx.Space, (1.0,))):
        unit = make(R, C)
        assert not unit.ringing()
        unit.set(*args)
        render(unit, x[:C])
        assert unit.ringing()
        if make is fx.Echo:
            most = 0.2 + args[1] * (2 + math.log(5e-4) / math.log(unit.gains(args[0])[0]))
        else:
            most = unit.decay(args[0]) * 1.15 + 0.3
        took = idle_after(unit, x, most)
        assert took > 0.1, took
        # the next sound starts clean: just what a new one would give
        again, fresh = render(unit, click(7), 1.0), make(R, C)
        fresh.set(*args)
        first = render(fresh, click(7), 1.0)
        assert np.any(first) and np.allclose(again, first, rtol=1e-4, atol=0.01), np.abs(again - first).max()
    # turned to 0 while it rings: soon over, and nothing after
    for unit, args, off, most in ((fx.Echo(R, C), (1.0, 0.3), (0.0, 0.3), 3.0), (fx.Space(R, C), (1.0,), (0.0,), 0.8)):
        unit.set(*args)
        render(unit, x)
        unit.set(*off)
        took = idle_after(unit, x[:0], most)
        assert not np.any(render(unit, x)) and not unit.ringing(), type(unit).__name__


def echo_timing():
    for secs in (0.25, 0.123, 0.08, 0.8):
        e = fx.Echo(R, C)
        e.set(1.0, secs)
        d = int(round(secs * R))
        y = render(e, click(100), secs * 5 + 0.1)
        first = int(np.nonzero(np.abs(y).sum(axis=1))[0][0])
        assert first == 100 + d, (secs, first - 100, d)
        assert int(np.argmax(np.abs(y).sum(axis=1))) == 100 + d
        side, sizes, tops = [], [], []
        for k in range(1, 6):                          # each repeat: where it is, which side, how bright
            rep = y[100 + k * d - 16:100 + k * d + 16].astype(np.float64)
            assert np.abs(rep).max() > 0 and abs(int(np.argmax(np.abs(rep).sum(axis=1))) - 16) <= k, (secs, k)
            power = np.square(rep).sum(axis=0)
            side.append(power[0] > power[1])
            sizes.append(float(power.sum()))
            tops.append(float(np.square(np.diff(rep, axis=0)).sum() / power.sum()))
            assert max(power) > 4 * min(power), (secs, k, power)
        assert side == [True, False, True, False, True], side
        assert all(b < a for a, b in zip(sizes, sizes[1:])), sizes
        assert all(b < a for a, b in zip(tops, tops[1:])), tops
    quiet, loud = fx.Echo(R, C), fx.Echo(R, C)         # more of it: louder, and more repeats
    quiet.set(0.3, 0.2)
    loud.set(1.0, 0.2)
    a, b = render(quiet, click(), 2.0), render(loud, click(), 2.0)
    assert np.abs(a).max() < np.abs(b).max() <= 0.5 * 10000
    assert db(a[int(0.9 * R):]) < db(b[int(0.9 * R):]) - 12


def reverb():
    took, loud = [], []
    for amount in (0.1, 0.3, 0.5, 0.75, 1.0):
        s = fx.Space(R, C)
        s.set(amount)
        ir = render(s, click(), 8.0).astype(np.float64)
        took.append(rt60(ir))
        loud.append(db(ir))
        assert abs(took[-1] / s.decay(amount) - 1) < 0.25, (amount, took[-1], s.decay(amount))
        left, right = ir[:, 0], ir[:, 1]
        corr = float((left * right).sum() / math.sqrt((left * left).sum() * (right * right).sum()))
        assert abs(corr) < 0.2, (amount, corr)
        assert abs(db(left) - db(right)) < 1.5
        # no echo of itself in the tail: its autocorrelation (with its dying away evened out) has no peak
        for side in (left, right):
            seg = side[int(0.15 * R):int((0.15 + min(1.0, max(0.3, s.decay(amount) * 0.5))) * R)]
            seg = seg / (np.sqrt(np.convolve(seg * seg, np.ones(480) / 480, "same")) + 1e-9)
            ac = np.fft.irfft(np.abs(np.fft.rfft(seg, 2 * len(seg))) ** 2)[:len(seg) // 2]
            ac /= ac[0]
            assert np.abs(ac[96:]).max() < 0.2, (amount, float(np.abs(ac[96:]).max()), int(np.argmax(np.abs(ac[96:]))))
        # darker as it dies away: the share of it above 4 kHz, early and late
        spec = lambda seg: np.abs(np.fft.rfft(seg)) ** 2
        top = lambda seg: 10 * math.log10(spec(seg)[int(4000 * len(seg) / R):].sum() / spec(seg).sum())
        t = took[-1]
        assert top(left[int(0.03 * R):int((0.03 + 0.2 * t) * R)]) > top(left[int(0.5 * t * R):int(0.8 * t * R)]) + 3
    assert all(b > a * 1.3 for a, b in zip(took, took[1:])), took
    assert 4.5 <= took[-1] <= 6.5 and took[0] < 0.7, took
    assert all(b > a + 1 for a, b in zip(loud, loud[1:])), loud
    # a mono sound in: a wide one out
    s = fx.Space(R, C)
    s.set(0.5)
    y = render(s, noise(1.0, amp=8000.0, seed=6, mono=True), 2.0).astype(np.float64)
    corr = float((y[:, 0] * y[:, 1]).sum() / math.sqrt((y[:, 0] ** 2).sum() * (y[:, 1] ** 2).sum()))
    assert abs(corr) < 0.3, corr
    # nothing before the first of it (23 ms)
    s.clear()
    ir = render(s, click(), 1.0)
    assert not np.any(ir[:int(0.02 * R)]) and np.any(ir[:int(0.03 * R)])


def tone_response():
    def gain(amount, hz):
        t = fx.Tone(R, C)
        t.set(amount)
        x = sine(hz, 0.4)
        y = render(t, x)[:len(x)]
        return db(y[len(x) // 2:]) - db(x[len(x) // 2:])
    assert gain(0.3, 200) - gain(0.3, 8000) >= 12, gain(0.3, 200) - gain(0.3, 8000)
    assert gain(0.9, 200) - gain(0.9, 8000) <= 1, gain(0.9, 200) - gain(0.9, 8000)
    assert gain(0.0, 200) > -1.5 and gain(0.0, 4000) < -12 and gain(0.0, 1000) > -9
    drops = [gain(a, 200) - gain(a, 6000) for a in (0.0, 0.2, 0.4, 0.6, 0.8, 0.95, 1.0)]
    assert all(b < a for a, b in zip(drops, drops[1:])) and drops[-1] == 0, drops
    assert 600 <= fx.Tone(R, C).cutoff(0.0) <= 900
    # the same whatever the chunks: 384 frames at a time, or 128
    x = noise(0.2, amp=9000.0, seed=7)[:C * 24]
    a, small = fx.Tone(R, C), fx.Tone(R, 128)
    a.set(0.35)
    small.set(0.35)
    whole = render(a, x)
    parts = np.concatenate([small.run(x[i:i + 128]).copy() for i in range(0, len(x), 128)])
    assert np.allclose(whole, parts, atol=0.05), np.abs(whole - parts).max()


def glides():
    """Settings changed under a steady sine: no step from one frame to the next much above the sine's own."""
    x = sine(440.0, 4.0)
    step = float(np.abs(np.diff(x[:, 0])).max())       # the sine's own biggest step
    def jump(unit, sets, xx=x):
        y = render(unit, xx, 0.3, sets).astype(np.float64)
        return float(np.abs(np.diff(y, axis=0)).max()), float(np.abs(y).max())
    def check(name, make, before, sets, slack=1.2, xx=x):
        steady = 0.0
        for args in [before] + list(sets.values()):    # how big a step it makes when left alone at each setting
            unit = make()
            unit.set(**args) if isinstance(args, dict) else unit.set(*args)
            steady = max(steady, jump(unit, None, xx)[0])
        unit = make()
        unit.set(**before) if isinstance(before, dict) else unit.set(*before)
        got = jump(unit, sets, xx)[0]
        assert got <= slack * max(steady, step * 0.2) + 2, (name, got, steady, step)
    check("tone", lambda: fx.Tone(R, C), (1.0,), {30: (0.2,), 70: (0.9,), 110: (0.0,), 150: (1.0,), 200: (0.5,),
                                                  201: (0.6,), 202: (0.1,)})
    check("echo level", lambda: fx.Echo(R, C), (0.3, 0.25), {90: (1.0, 0.25), 180: (0.1, 0.25), 260: (0.0, 0.25),
                                                             330: (0.8, 0.25)})
    check("echo time", lambda: fx.Echo(R, C), (0.7, 0.25), {90: (0.7, 0.4), 150: (0.7, 0.11), 151: (0.7, 0.3),
                                                            230: (0.7, 0.8), 400: (0.7, 0.08)})
    check("space", lambda: fx.Space(R, C), (0.2,), {60: (0.9,), 150: (0.4,), 151: (0.45,), 152: (0.5,), 250: (0.0,),
                                                    300: (1.0,), 420: (0.0,)})
    xi = x.astype(np.int32)
    check("bus", lambda: fx.Bus(R, C), dict(space=0.4, echo=0.3, echo_secs=0.3, tone=0.8),
          {80: dict(space=1.0, echo=1.0, echo_secs=0.5, tone=0.1), 200: dict(space=0.0, echo=0.0, tone=1.0),
           300: dict(space=0.6, echo=0.5, echo_secs=0.2, tone=0.5)}, xx=xi)
    # ...and a sound cut dead with an echo and reverb on it: they carry on, and die away smoothly
    bus = fx.Bus(R, C)
    bus.set(space=0.6, echo=0.5, echo_secs=0.2, tone=0.5)
    x = sine(480.0, 0.4)[:C * 50].astype(np.int32)     # (whole turns of it: it stops as it crosses zero)
    y = render(bus, x, 1.0).astype(np.float64)
    step = float(np.abs(np.diff(x[:, 0])).max())
    assert np.any(y[C * 50:]) and np.abs(np.diff(y[C * 50 - 1:], axis=0)).max() <= step * 1.5


def bus_chain():
    x = (noise(1.0, amp=6000.0, seed=8) * np.linspace(1, 0, R)[:, None] ** 4).astype(np.int32)
    bus, t, e, s = fx.Bus(R, C), fx.Tone(R, C), fx.Echo(R, C), fx.Space(R, C)
    bus.set(space=0.5, echo=0.6, echo_secs=0.15, tone=0.6)
    t.set(0.6)
    e.set(0.6, 0.15)
    s.set(0.5)
    got = render(bus, x, 1.0)
    xx = np.zeros((len(got), 2), np.float32)
    xx[:len(x)] = x
    want = np.zeros_like(xx)
    for i in range(0, len(xx), C):
        dry = t.run(xx[i:i + C]).copy()
        wet = e.run(dry).copy()
        want[i:i + C] = dry + wet + s.run(dry + wet)
    assert np.abs(got - want).max() <= 1.5, np.abs(got - want).max()
    assert bus.ringing()
    bus.clear()
    assert not bus.ringing() and not np.any(bus.run(np.zeros((C, 2), np.int32)))


def pitch_of(x, near):
    """The strongest overtone within a few semitones of near (Hz)."""
    n = 1 << 18
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)), n))
    lo, hi = int(near * 0.8 * n / R), int(near * 1.25 * n / R)
    k = lo + int(np.argmax(spec[lo:hi]))
    a, b, c = np.log(spec[k - 1:k + 2])
    return (k + 0.5 * (a - c) / (a - 2 * b + c)) * R / n, spec, k


def instruments():
    assert set(fx.NAMES) == {"Bell", "Marimba", "Kalimba", "Glass", "Pluck", "Pad"}
    for name in fx.NAMES:
        for midi in (48, 60, 72):
            x = fx.tone(name, midi, R)
            assert x.dtype == np.int16 and x.ndim == 1 and R * 0.5 <= len(x) <= R * 2.5, (name, len(x))
            peak = int(np.abs(x.astype(np.int32)).max())
            want = 0.30 if name == "Pad" else 0.42
            assert abs(peak / 32767 - want) < 0.005, (name, midi, peak / 32767)
            f = x.astype(np.float64)
            assert x[0] == 0 and np.abs(f[:int(0.0005 * R)]).max() < 0.2 * peak            # in from nothing
            assert np.abs(f[int(0.003 * R):int(0.3 * R)]).max() > 0.5 * peak                # ...and soon there
            assert np.abs(f[-48:]).max() < 0.003 * peak and abs(x[-1]) <= 1, (name, midi)   # out to nothing
            assert abs(f.mean()) < 0.001 * peak, (name, midi, f.mean())                     # no DC
            hz = 440.0 * 2 ** ((midi - 69) / 12.0)
            got, spec, k = pitch_of(f, hz)
            cents = 1200 * math.log2(got / hz)
            assert abs(cents) <= 10, (name, midi, cents)
            assert spec[k] >= 0.999 * spec[int(40 * len(spec) / (R / 2)):].max(), (name, midi)   # it's the loudest
            top = spec[int(11000 * len(spec) / (R / 2)):].max() / spec[k]                   # nothing up high to
            assert top < 1e-3, (name, midi, top)                                            # fold over when shifted
            took = []
            for _ in range(3):
                t = time.perf_counter()
                fx.tone(name, midi, R)
                took.append(time.perf_counter() - t)
            assert min(took) <= 0.15, (name, midi, min(took))   # (here, on a busy computer: the Pi takes longer)
        assert np.array_equal(fx.tone(name, 60), fx.tone(name, 60))
    try:
        fx.tone("Kazoo", 60)
        raise AssertionError("an instrument it hasn't")
    except ValueError:
        pass


def drone_loops():
    for midi, secs in ((48, 4.0), (43, 4.0), (57, 2.5)):
        x = fx.drone(midi, secs, R)
        assert x.dtype == np.int16 and x.shape == (int(round(secs * R)), 2)
        f = x.astype(np.float64)
        peak = np.abs(f).max()
        assert abs(peak / 32767 - 0.25) < 0.005, peak / 32767
        assert abs(f.mean(axis=0)).max() < 1.0                                  # no DC
        # nothing in it but what turns a whole number of times in the loop: all of it in a few dozen places of
        # its spectrum (a seam would be spread over every one)
        spec = np.sort(np.abs(np.fft.rfft(f[:, 0])) ** 2)
        assert spec[:-64].sum() < 1e-6 * spec.sum(), spec[:-64].sum() / spec.sum()
        # ...and the step from its end to its start is like any other in it, and the bend there too
        inside = np.abs(np.diff(f, axis=0)).max()
        assert np.abs(f[0] - f[-1]).max() <= inside
        both = np.concatenate((f[-4:], f[:4]))
        assert np.abs(np.diff(both, 2, axis=0)).max() <= np.abs(np.diff(f, 2, axis=0)).max() + 2
        hz = 440.0 * 2 ** ((midi - 69) / 12.0)
        got = pitch_of(f[:, 0], hz)[0]
        assert abs(1200 * math.log2(got / hz)) < 15, (midi, got, hz)
        corr = float((f[:, 0] * f[:, 1]).sum() / math.sqrt((f[:, 0] ** 2).sum() * (f[:, 1] ** 2).sum()))
        assert 0.3 < corr < 0.98, corr                                          # wide, but one sound
        fifth = pitch_of(f[:, 0], hz * 1.5)[0]
        assert abs(1200 * math.log2(fifth / (hz * 1.5))) < 15


def other_sizes():
    """Not only 48 kHz and 384 frames."""
    for rate, chunk in ((44100, 256), (48000, 512)):
        bus = fx.Bus(rate, chunk)
        bus.set(space=0.6, echo=0.6, echo_secs=0.21, tone=0.5)
        x = np.zeros((chunk, 2), np.int32)
        x[3] = 9000
        out = [bus.run(x).copy()]
        for _ in range(int(rate * 0.6 / chunk)):
            out.append(bus.run(np.zeros((chunk, 2), np.int32)).copy())
        y = np.concatenate(out)
        d = int(round(0.21 * rate))
        assert abs(y[3 + d, 0]) > 4 * np.abs(y[d - 40:3 + d]).max(), "the echo's first repeat, where it should be"
        assert np.any(y[:d]) and np.abs(y).max() < 9000 and bus.ringing()


SAYS = (("bypassed or off: exactly what went in, or nothing", passthrough),
        ("never anything but numbers", finite),
        ("never louder and louder, at their most with the loudest noise", stable),
        ("their tails ring only as long as they should; the next sound clean after them", ringing_ends),
        ("the echo: its repeats at their very frames, from one side then the other, each quieter and darker",
         echo_timing),
        ("the space: longer and louder turned up, wide, no echo of itself, darker as it dies away", reverb),
        ("the tone: softer up high the more it's turned down, the same whatever the chunks", tone_response),
        ("every change of setting without a click", glides),
        ("the three in a row, as the player has them", bus_chain),
        ("Bounce's instruments: in tune at each note, soft at both ends, quick to make", instruments),
        ("the drone: a loop with no seam, in tune, wide", drone_loops),
        ("other rates and chunk sizes", other_sizes))
with np.errstate(over="raise", invalid="raise", divide="raise"):
    for what, run in SAYS:
        t0 = time.perf_counter()
        try:
            run()
            why = ""
        except Exception as ex:                        # (an assert's: what it found)
            why = f": {type(ex).__name__} {ex}"[:300]
            traceback.print_exc()
        check(f"{what} ({time.perf_counter() - t0:.1f} s){why}", not why)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
