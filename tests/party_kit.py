"""Party mode's tests' own things (test_party.py, test_party_joins.py): a pretend sound card, songs whose every sample
says where in the song it is, and how far behind the clock, or apart, what was heard on them was."""
import os
import statistics
import wave

import numpy as np

RATE = 48000                 # samples a second (pitato/party.py's PARTY_RATE)

# a pretend aplay: takes the sound as a sound card would (FAKE_APLAY_SPEED_X: how fast its clock runs), with a buffer as
# long as --buffer-time says, and logs each 10 ms as it's heard (FAKE_APLAY_LOG): when, its first sample, and how loud.
# FAKE_APLAY_ONE (a file): a sound card that takes one player at a time, as HDMI's does (a second one's turned away)
APLAY = '''#!/usr/bin/env python3
import os, struct, sys, time
import numpy as np
args = sys.argv[1:]
rate = int(args[args.index("-r") + 1]) if "-r" in args else 48000
buf = next((int(a.split("=")[1]) for a in args if a.startswith("--buffer-time=")), 100000) / 1e6
speed = float(os.environ.get("FAKE_APLAY_SPEED_X", "1.0"))
if os.environ.get("FAKE_APLAY_ONE"):
    import fcntl
    card = open(os.environ["FAKE_APLAY_ONE"], "a")
    try:
        fcntl.lockf(card, fcntl.LOCK_EX | fcntl.LOCK_NB)   # (its own till it ends)
    except OSError:
        sys.stderr.write("aplay: audio open error: Device or resource busy\\n")
        sys.exit(1)
log = open(os.environ["FAKE_APLAY_LOG"], "a", buffering=1) if os.environ.get("FAKE_APLAY_LOG") else None
chunk = rate // 100
inp = sys.stdin.buffer
held, start, played = bytearray(), None, 0
while True:
    while len(held) < buf * rate * 4:
        data = inp.read(chunk * 4)
        if not data:
            sys.exit(0)
        held += data
        if start is None:
            start = time.monotonic()
    first = struct.unpack("<hh", held[:4])
    loud = float(np.sqrt(np.mean(np.frombuffer(bytes(held[:chunk * 4]), dtype="<i2").astype(np.float64) ** 2)))
    del held[:chunk * 4]
    if log:
        log.write(f"{time.monotonic():.6f} {first[0]} {first[1]} {loud:.1f}\\n")
    played += chunk
    wait = start + played / (rate * speed) - time.monotonic()
    if wait > 0:
        time.sleep(wait)
'''


def sound_card(folder):
    """The pretend aplay, in folder: the one Pietato finds first from here on."""
    os.makedirs(folder, exist_ok=True)
    with open(folder + "/aplay", "w") as f:
        f.write(APLAY)
    os.chmod(folder + "/aplay", 0o755)
    os.environ["PATH"] = folder + ":" + os.environ["PATH"]


def ramp(path, secs, first=0):
    """A song whose every sample says where in it it is: left, the place's low 15 bits; right, the rest. first:
    seconds its places start at (a song apart from another: 1000 for one, 2000 for the next)."""
    n = np.arange(RATE * secs, dtype=np.int64) + int(first * RATE)
    pcm = np.empty(2 * len(n), dtype="<i2")
    pcm[0::2], pcm[1::2] = (n & 0x7FFF).astype("<i2"), (n >> 15).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(pcm.tobytes())


def heard(log):
    """What a pretend sound card heard: [(when, where in the song (seconds) or None for silence, how loud)]."""
    out = []
    try:
        lines = open(log).read().splitlines()
    except OSError:
        return out
    for line in lines:
        t, left, right, loud = line.split()
        left, right = int(left), int(right)
        out.append((float(t), None if left == 0 and right == 0 else (right * 32768 + (left & 0x7FFF)) / RATE,
                    float(loud)))
    return out


def lag(log, at, pos=0.0, after=0.0, before=None):
    """How far behind (+) or ahead (-) of where the leader's clock says a song should be heard it was, in ms: (the
    mean, the most either way)."""
    errs = [((t - at) + pos - where) * 1000 for t, where, _ in heard(log) if where is not None and t > at + after
            and (before is None or t < before)]
    return (statistics.mean(errs), max(abs(e) for e in errs)) if errs else (None, None)


def apart(log_a, log_b, at, after=1.0):
    """How far apart two of them heard the same song (ms): the mean, and the most."""
    a, b = heard(log_a), heard(log_b)
    if not a or not b:
        return None, None
    bt = np.array([t for t, w, _ in b if w is not None])
    bw = np.array([w for t, w, _ in b if w is not None])
    errs = []
    for t, w, _ in a:
        if w is None or t < at + after:
            continue
        k = np.searchsorted(bw, w)                     # (when b heard the same place in it)
        if 0 < k < len(bw):
            tb = bt[k - 1] + (w - bw[k - 1]) * (bt[k] - bt[k - 1]) / max(bw[k] - bw[k - 1], 1e-9)
            errs.append((tb - t) * 1000)
    return (statistics.mean(errs), max(abs(e) for e in errs)) if errs else (None, None)
