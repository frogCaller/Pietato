#!/usr/bin/env python3
"""The Soundboard's starter sounds, made here: every one of them is worked out from sums in this file (sines, noise,
envelopes), so nothing in them is anyone else's recording. Run it to make them again:

    python3 pitato/sounds/make.py            (into this folder; needs numpy)

They're 48 kHz, 16-bit, one channel: what the Soundboard plays as it is (pitato/soundplay.py). CREDITS.txt says
whose they are (nobody's: CC0)."""
import os
import sys
import wave

import numpy as np

RATE = 48000
HERE = os.path.dirname(os.path.abspath(__file__))
TAU = 2 * np.pi


# ---- what they're made with ---------------------------------------------------------------------------------------
def secs(n):
    """n seconds of time, a sample at a time."""
    return np.arange(int(round(RATE * n))) / RATE


def hiss(n, rng):
    return rng.uniform(-1.0, 1.0, int(n))


def band(x, low=None, high=None, soft=0.2):
    """x with only what's between low and high Hz left (either may be None), its edges this soft (of the edge's Hz)."""
    spec = np.fft.rfft(x)
    hz = np.fft.rfftfreq(len(x), 1 / RATE)
    gain = np.ones(len(hz))
    if low:
        gain *= 1 / (1 + np.exp(-(hz - low) / (soft * low)))
    if high:
        gain *= 1 / (1 + np.exp((hz - high) / (soft * high)))
    return np.fft.irfft(spec * gain, len(x))


def swell(n, up, down, hold=1.0):
    """An envelope n samples long: up in `up` seconds, down in `down` at its end, `hold` in between."""
    env = np.full(int(n), float(hold))
    a, d = min(int(up * RATE), int(n)), min(int(down * RATE), int(n))
    if a:
        env[:a] *= np.sin(np.linspace(0, np.pi / 2, a)) ** 2
    if d:
        env[-d:] *= np.cos(np.linspace(0, np.pi / 2, d)) ** 2
    return env


def turn(hz):
    """Where a wave is in its turn, sample by sample, for a pitch that may change (hz: a number or an array)."""
    return TAU * np.cumsum(np.broadcast_to(hz, np.shape(hz) or (1,)).astype(float)) / RATE


def rich(hz, n=None, bright=1.0, odd=False, top=9000.0):
    """A wave with its overtones (each 1/k^bright as loud; odd: only the odd ones, a square's), none above `top` Hz
    even at its highest pitch: nothing folds back as a whistle."""
    hz = np.broadcast_to(np.asarray(hz, dtype=float), (int(n),) if n else np.shape(hz))
    ph = TAU * np.cumsum(hz) / RATE
    out = np.zeros(len(hz))
    k = 1
    while k * hz.min() < top:
        if not odd or k % 2:                                   # (near the top, one fades out: no click as it goes)
            out += np.clip((top - k * hz) / (0.12 * top), 0.0, 1.0) * np.sin(k * ph) / k ** bright
        k += 1
    return out


def brass(hz, env, dark=500.0, lit=2600.0):
    """A horn's note: its overtones come and go with how hard it's blown (env, 0 to 1), as a horn's do."""
    hz = np.broadcast_to(np.asarray(hz, dtype=float), np.shape(env))
    ph = TAU * np.cumsum(hz) / RATE
    cut = dark + lit * env ** 1.5
    out = np.zeros(len(env))
    for k in range(1, 26):
        out += np.sin(k * ph) * np.exp(-k * hz / cut) / k ** 0.5
    return out * env


def after(parts, n=None):
    """Sounds laid down each at its own time: [(seconds in, the sound)...], as long as the last one ends."""
    n = n or max(int(at * RATE) + len(x) for at, x in parts)
    out = np.zeros(n)
    for at, x in parts:
        i = int(at * RATE)
        out[i:i + len(x)] += x[:max(0, n - i)]
    return out


def loud(x, peak=0.89, tail=0.05):
    """As loud as `peak` at its loudest, starting at nothing and dying away over its last `tail` seconds (no click,
    and nothing cut off short)."""
    x = x - np.mean(x)
    x = x * swell(len(x), 0.003, min(tail, len(x) / RATE / 2))
    return x * (peak / max(1e-9, np.abs(x).max()))


def squash(x, hard=1.5):
    """Its peaks pressed down a little (a bit of grit, as a loud thing has)."""
    return np.tanh(x * hard / max(1e-9, np.abs(x).max()))


# ---- the drums ----------------------------------------------------------------------------------------------------
def kick(rng, low=48.0, drop=130.0, ring=0.18, n=0.45):
    t = secs(n)
    ph = turn(low + drop * np.exp(-t / 0.03))
    body = (np.sin(ph) + 0.4 * np.sin(2 * ph) * np.exp(-t / 0.08)) * np.exp(-t / ring)   # (its overtone: a small
    tap = band(hiss(len(t), rng), 1200, 5000) * np.exp(-t / 0.006) * 0.6                 #  speaker has no bass)
    return squash(body + tap, 1.4)


def snare(rng, n=0.3):
    t = secs(n)
    skin = np.sin(turn(185 + 60 * np.exp(-t / 0.02))) * np.exp(-t / 0.06) + 0.5 * np.sin(TAU * 330 * t) * np.exp(-t / 0.04)
    wires = band(hiss(len(t), rng), 1400, 9500) * np.exp(-t / 0.085)
    return squash(0.55 * skin + 0.9 * wires, 1.3)


def metal(t):
    """The six clashing tones a drum machine's cymbals are made of."""
    return sum(np.sign(np.sin(TAU * hz * t + k)) for k, hz in enumerate((205.3, 304.4, 369.6, 522.7, 540.0, 800.0)))


def hat(rng, ring=0.03, n=0.12):
    t = secs(n)
    return band(metal(t) + 2.0 * hiss(len(t), rng), 6200, 12500) * np.exp(-t / ring)


def clap(rng, n=0.36):
    t = secs(n)
    hands = sum(np.where(t >= at, np.exp(-(t - at) / 0.006), 0.0) for at in (0.0, 0.011, 0.023))
    hands = hands + np.where(t >= 0.03, 0.8 * np.exp(-(t - 0.03) / 0.07), 0.0)
    return band(hiss(len(t), rng), 800, 4200) * hands


def tom(rng, low=105.0, n=0.5):
    t = secs(n)
    ph = turn(low + 70 * np.exp(-t / 0.05))
    return squash((np.sin(ph) + 0.35 * np.sin(2 * ph) * np.exp(-t / 0.1)) * np.exp(-t / 0.2)
                  + 0.35 * band(hiss(len(t), rng), 900, 4000) * np.exp(-t / 0.012), 1.2)


def cowbell(rng, n=0.45):
    t = secs(n)
    ring = band(np.sign(np.sin(TAU * 540 * t)) + np.sign(np.sin(TAU * 800 * t)), 450, 3400)
    return ring * (0.8 * np.exp(-t / 0.05) + 0.3 * np.exp(-t / 0.25))


def crash(rng, n=1.6, ring=0.45):
    t = secs(n)
    wash = band(0.6 * metal(t) + 3.0 * hiss(len(t), rng), 3000, 13500) * (np.exp(-t / ring) + 0.6 * np.exp(-t / 0.03))
    return squash(wash, 1.6)


def rimshot(rng):
    """Ba-dum, tss."""
    return after([(0.0, snare(rng)), (0.17, tom(rng, low=85.0, n=0.4)),
                  (0.37, 0.5 * kick(rng, n=0.3)), (0.37, 0.42 * crash(rng, n=0.95, ring=0.28))])


# ---- the rest of the starter bank ----------------------------------------------------------------------------------
def air_horn(rng):
    """Two short blasts and a long one: three horns at once, each spinning up to its note."""
    def blast(n):
        t = secs(n)
        env = swell(len(t), 0.012, 0.05)
        up = 1 - 0.07 * np.exp(-t / 0.02)                      # (it comes up to its note, and wavers a little)
        out = np.zeros(len(t))
        for k, hz in enumerate((420.0, 424.0, 505.0)):         # (two a hair apart, beating, and one a third above)
            waver = 1 + 0.004 * np.sin(TAU * (5.3 + k) * t + k)
            out += rich(hz * up * waver, bright=0.75, top=11000.0)
        air = band(hiss(len(t), rng), 2000, 9000) * 0.25
        return squash(band(out, 300, None) + air, 2.2) * env
    return after([(0.0, blast(0.11)), (0.18, blast(0.11)), (0.36, blast(0.8))])


def sad_horn(rng):
    """Wah, wah, wah, waaah: four notes going down, the last one long and sinking."""
    parts, at = [], 0.0
    for k, (hz, n) in enumerate(((293.7, 0.36), (277.2, 0.36), (261.6, 0.36), (246.9, 1.25))):
        t = secs(n)
        env = swell(len(t), 0.05, 0.12 if k < 3 else 0.5) * (0.75 + 0.25 * np.exp(-t / 0.15))
        bend = 1 - 0.03 * np.exp(-t / 0.04)
        if k == 3:                                             # (the last: slower, wavering, and sinking away)
            bend = bend * (1 - 0.06 * (t / n) ** 2) * (1 + 0.012 * np.sin(TAU * 5.2 * t) * np.minimum(1, t / 0.3))
        parts.append((at, brass(hz * bend, env, dark=380.0, lit=1500.0)))
        at += n + 0.04
    return after(parts)


def ta_da(rng):
    """A short note, then a held chord."""
    def chord(notes, n, down):
        t = secs(n)
        env = swell(len(t), 0.02, down) * (0.7 + 0.3 * np.exp(-t / 0.12))
        return sum(brass(hz * (1 - 0.02 * np.exp(-t / 0.02)), env, dark=600.0, lit=3000.0) for hz in notes)
    return after([(0.0, 0.7 * chord((392.0, 493.9, 587.3), 0.13, 0.04)),
                  (0.17, chord((523.3, 659.3, 784.0, 1046.5), 0.95, 0.45))])


def applause(rng, n=2.6, people=28):
    """A roomful of hands: each clapping at its own pace, a little apart, some further off."""
    out = np.zeros(int(n * RATE))
    for _ in range(people):
        every, far = rng.uniform(0.2, 0.3), rng.uniform(0.35, 1.0)
        pitch, at = rng.uniform(900, 2600), rng.uniform(0, 0.3)
        stops = n - rng.uniform(0.15, 0.9)                     # (they don't all stop at once)
        while at < stops:
            m = int(0.03 * RATE)
            hands = band(hiss(m, rng), pitch * 0.6, pitch * 1.9) * np.exp(-secs(0.03) / rng.uniform(0.003, 0.008))
            i = int(at * RATE)
            out[i:i + m] += (hands * far)[:max(0, len(out) - i)]
            at += every * rng.uniform(0.88, 1.12)
    room = hiss(int(0.07 * RATE), rng) * np.exp(-secs(0.07) / 0.02)   # (the room they're in)
    out = out + 0.25 * np.convolve(out, room / np.abs(room).sum(), mode="full")[:len(out)]
    return squash(out * swell(len(out), 0.15, 0.5), 1.8)


def crickets(rng, n=2.2):
    """Two of them, each with its own chirp, in a quiet night."""
    out = np.zeros(int(n * RATE))
    for hz, every, at, how in ((4300.0, 0.42, 0.05, 1.0), (4750.0, 0.57, 0.24, 0.55)):
        while at < n - 0.12:
            for k in range(3):                                 # (a chirp: three quick strokes of its wings)
                t = secs(0.014)
                stroke = np.sin(TAU * hz * t * (1 + 0.01 * k)) * np.sin(np.pi * t / 0.014) ** 2
                i = int((at + k * 0.024) * RATE)
                out[i:i + len(stroke)] += how * stroke
            at += every
    return out + 0.012 * band(hiss(len(out), rng), 2500, 9000)


def buzzer(rng, n=0.65):
    t = secs(n)
    return squash(rich(148.0, len(t), odd=True, top=5000.0) + rich(157.0, len(t), odd=True, top=5000.0), 2.0) \
        * swell(len(t), 0.008, 0.04)


def ding(rng, n=1.4, note=1318.5):
    t = secs(n)
    bell = sum(how * np.sin(TAU * note * k * t) * np.exp(-t / ring)
               for k, how, ring in ((1.0, 1.0, 0.45), (2.0, 0.45, 0.28), (3.01, 0.22, 0.16), (4.2, 0.14, 0.1),
                                    (5.43, 0.09, 0.06)))
    return bell + 0.15 * band(hiss(len(t), rng), 3000, 9000) * np.exp(-t / 0.003)


# ---- the arcade ---------------------------------------------------------------------------------------------------
def pulse(hz, n=None, top=10000.0):
    """A square wave, as an old game's chip makes."""
    return rich(hz, n, bright=1.0, odd=True, top=top)


def note(hz, n, ring=None, top=10000.0):
    """One note of a square wave, n seconds: held, or (ring) dying away; it starts and stops without a click."""
    t = secs(n)
    return pulse(hz, len(t), top=top) * swell(len(t), 0.003, 0.006) * (np.exp(-t / ring) if ring else 1.0)


def laser(rng, n=0.3):
    t = secs(n)
    return pulse(1900.0 * np.exp(-t / 0.085) + 180.0) * np.exp(-t / 0.12) * swell(len(t), 0.002, 0.03)


def pickup(rng):
    """Three quick notes going up, the last one ringing."""
    return after([(0.0, note(1318.5, 0.05)), (0.05, note(1661.2, 0.05)), (0.1, note(1975.5, 0.32, ring=0.11))])


def jump(rng, n=0.2):
    t = secs(n)
    return pulse(240.0 + 560.0 * (t / n) ** 0.8) * swell(len(t), 0.004, 0.06)


def power_up(rng):
    """Up a scale, quickly, to a held note."""
    scale = (523.3, 587.3, 659.3, 784.0, 880.0, 1046.5, 1174.7, 1318.5)
    parts = [(k * 0.055, note(hz, 0.055)) for k, hz in enumerate(scale)]
    t = secs(0.36)
    parts.append((len(scale) * 0.055, pulse(1568.0 * (1 + 0.012 * np.sin(TAU * 9 * t))) * np.exp(-t / 0.16)
                  * swell(len(t), 0.003, 0.03)))
    return after(parts)


def explosion(rng, n=1.3):
    t = secs(n)
    blast = hiss(len(t), rng)                                  # (its crack dies first, its rumble last)
    out = (band(blast, 1800, 6500) * np.exp(-t / 0.07) + band(blast, 400, 1800) * 1.4 * np.exp(-t / 0.2)
           + band(blast, None, 400, soft=0.3) * 2.2 * np.exp(-t / 0.45))
    thump = np.sin(turn(38.0 + 70.0 * np.exp(-t / 0.08))) * np.exp(-t / 0.25)
    return squash(out + 1.2 * thump, 1.8)


def boing(rng, n=0.9):
    t = secs(n)
    spring = 150.0 * (1 + 0.55 * np.exp(-t / 0.3) * np.sin(TAU * 11.0 * t)) + 90.0 * np.exp(-t / 0.2)
    return rich(spring, bright=1.6, top=5000.0) * np.exp(-t / 0.32)


def siren(rng, whoops=2, n=0.42):
    t = secs(n)
    whoop = pulse(520.0 + 760.0 * (t / n) ** 1.6, top=7000.0) * swell(len(t), 0.02, 0.03)
    return after([(k * (n + 0.03), whoop) for k in range(whoops)])


def game_over(rng):
    """Four notes falling, and a last low one that sinks."""
    parts = [(k * 0.17, note(hz, 0.16, top=8000.0)) for k, hz in enumerate((784.0, 622.3, 523.3, 392.0))]
    t = secs(0.6)
    parts.append((0.68, pulse(261.6 * (1 - 0.1 * (t / 0.6) ** 2) * (1 + 0.01 * np.sin(TAU * 6 * t)), top=8000.0)
                  * np.exp(-t / 0.3) * swell(len(t), 0.004, 0.05)))
    return after(parts)


# ---- all of them: the file each goes in, how it's made, how loud ---------------------------------------------------
SOUNDS = (   # (a square wave is loud for its size: those are kept lower, so the bank's sounds are about as loud)
    ("Air horn", air_horn, 0.8), ("Rimshot", rimshot, 0.89), ("Sad horn", sad_horn, 0.8), ("Ta-da", ta_da, 0.85),
    ("Applause", applause, 0.85), ("Crickets", crickets, 0.6), ("Ding", ding, 0.8), ("Buzzer", buzzer, 0.5),
    ("Kick", kick, 0.89), ("Snare", snare, 0.89), ("Hi-hat", hat, 0.7),
    ("Open hat", lambda rng: hat(rng, ring=0.22, n=0.6), 0.7), ("Clap", clap, 0.85), ("Tom", tom, 0.89),
    ("Cowbell", cowbell, 0.8), ("Crash", crash, 0.8),
    ("Laser", laser, 0.55), ("Pickup", pickup, 0.5), ("Jump", jump, 0.5), ("Power up", power_up, 0.45),
    ("Explosion", explosion, 0.89), ("Boing", boing, 0.85), ("Siren", siren, 0.45), ("Game over", game_over, 0.45),
)
TAILS = {"Kick": 0.12, "Tom": 0.14, "Boing": 0.2, "Cowbell": 0.12, "Crash": 0.3, "Open hat": 0.12, "Ding": 0.25,
         "Explosion": 0.3}                             # (the ones that ring on: their last moments die away this long)


def make(folder=HERE):
    os.makedirs(folder, exist_ok=True)
    made = []
    for k, (name, how, peak) in enumerate(SOUNDS):
        x = loud(how(np.random.default_rng(1000 + k)), peak, TAILS.get(name, 0.05))   # (each from its own dice:
                                                                                      #  made again, it's the same)
        pcm = np.round(x * 32767).astype("<i2")
        path = os.path.join(folder, name + ".wav")
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(pcm.tobytes())
        made.append((name, len(pcm) / RATE, os.path.getsize(path)))
    return made


if __name__ == "__main__":
    for name, length, size in make(sys.argv[1] if len(sys.argv) > 1 else HERE):
        print(f"{name + '.wav':16} {length:5.2f} s  {size / 1024:6.0f} KB")
