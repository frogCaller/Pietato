"""The Soundboard's sounds and banks (Apps > Soundboard): the starter pack that comes with Pietato (the sounds folder
beside this file), your own (the Soundboard folder of your home folder: wav, mp3, ogg), and which sound is on which
button of which bank, kept in static/soundboard.txt:

    # sounds taken off their buttons (a new file goes on the first free button of My sounds by itself)
    off = Old one.wav
    [Starter]
    up = Starter/Air horn.wav
    a = Starter/Ding.wav
    [My sounds]
    up = Laugh.mp3

A bank has eight buttons (PADS). A sound is on one button at most. Media mode reads all this
(screens/soundboard.py), its player plays the files (soundplay.py), and the web page changes it (webui.py). Each of
those loads this file on its own, so there's nothing in it but Python's own (and numpy, where sound itself is looked
at: a recording's silence trimmed)."""
import os
import struct

EXTS = (".wav", ".mp3", ".ogg")
PADS = ("up", "left", "right", "down", "x", "y", "a", "b")   # a bank's buttons, in the order new sounds fill them
FOLDER = "Soundboard"            # in your home folder
FILE = "soundboard.txt"          # in the static folder
STARTER = "Starter/"             # how one of the starter pack's sounds is named in that file
MINE = "My sounds"               # the bank new sounds of yours go in (My sounds 2, 3... as each fills)
BANKS_MOST = 24
NAME_MOST = 28                   # letters in a bank's name
FILES_MOST = 400                 # sounds of yours looked at, at most
SOUND_BYTES = 40 << 20           # the biggest file taken as a sound
RATE = 48000                     # what the player plays at, and recordings are kept at
REC_MOST = 20.0                  # seconds a recording may be
STARTER_BANKS = (
    ("Starter", {"up": "Air horn", "left": "Rimshot", "right": "Ta-da", "down": "Sad horn",
                 "x": "Applause", "y": "Crickets", "a": "Ding", "b": "Buzzer"}),
    ("Drums", {"up": "Hi-hat", "left": "Tom", "right": "Crash", "down": "Open hat",
               "x": "Clap", "y": "Cowbell", "a": "Snare", "b": "Kick"}),
    ("Arcade", {"up": "Jump", "left": "Laser", "right": "Pickup", "down": "Boing",
                "x": "Power up", "y": "Explosion", "a": "Siren", "b": "Game over"}),
)
HEAD = ("# The Soundboard's banks (Apps > Soundboard): a bank's name in [brackets], then the sound on each of its\n"
        "# buttons (up, left, right, down, x, y, a, b). A sound is a file in your Soundboard folder, or one that came\n"
        "# with Pietato (Starter/...). \"off\" is one taken off its button: a new file goes on a button by itself.\n"
        "# The web page's Soundboard keeps this file for you.\n")


# ---- the sounds there are ------------------------------------------------------------------------------------------
def starter_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds")


def starter_sounds(folder=None):
    """The starter pack's sounds, as the banks name them: ["Starter/Air horn.wav"...]."""
    try:
        names = sorted(n for n in os.listdir(folder or starter_dir()) if n.lower().endswith(".wav"))
    except OSError:
        return []
    return [STARTER + n for n in names]


def is_starter(sid):
    return isinstance(sid, str) and sid.startswith(STARTER)


def sound_name(name):
    """A file's name, if it's one a sound of yours can have (a wav, mp3 or ogg, on one line, not hidden), or None."""
    if not isinstance(name, str) or not name or name.startswith(".") or "/" in name or "\\" in name:
        return None
    if name != name.strip() or not all(c.isprintable() for c in name) or len(name.encode()) > 240:
        return None
    return name if os.path.splitext(name)[1].lower() in EXTS and os.path.splitext(name)[0] else None


def scan(folder):
    """The sounds in your Soundboard folder (not in folders inside it), oldest first, so a new one comes last:
    [(its name, when it was last changed, its size)]. OSError: the folder can't be read."""
    found = []
    with os.scandir(folder) as it:
        for e in it:
            if sound_name(e.name) is None:
                continue
            try:
                st = e.stat()
                plain = e.is_file()
            except OSError:
                continue
            if plain and 0 < st.st_size <= SOUND_BYTES:
                found.append((st.st_mtime_ns, e.name.lower(), e.name, st.st_size))
            if len(found) >= FILES_MOST * 4:
                break
    return [(name, when, size) for when, _, name, size in sorted(found)][:FILES_MOST]


def your_sounds(folder):
    """...just their names ([]: there's no such folder, or it can't be read)."""
    try:
        return [name for name, _, _ in scan(folder)]
    except OSError:
        return []


def path_of(sid, folder, starter=None):
    """Where a sound's file is: one of the starter pack's, or one of yours in `folder`. None: not a sound's name."""
    if is_starter(sid):
        name = sid[len(STARTER):]
        return os.path.join(starter or starter_dir(), name) if sound_name(name) else None
    return os.path.join(folder, sid) if sound_name(sid) else None


def title(sid):
    """What a sound's called on a button: its file's name, without the ending."""
    return os.path.splitext((sid or "").rsplit("/", 1)[-1])[0]


def clean_bank(name):
    """A bank's name fit for its line in the file, and a button: on one line, no brackets, not too long."""
    name = "".join(c if c.isprintable() and c not in "[]" else " " for c in str(name or ""))
    return " ".join(name.split())[:NAME_MOST].strip()


def free_name(taken, stem, ext):
    """stem + ext, or "stem 2", "stem 3"... when that's one of `taken` (whatever its capitals)."""
    low = {t.lower() for t in taken}
    name, n = stem + ext, 1
    while name.lower() in low:
        n += 1
        name = f"{stem} {n}{ext}"
    return name


def recording_name(taken):
    """The next recording's file: Recording 1.wav, Recording 2.wav..."""
    low = {t.lower() for t in taken}
    n = 1
    while f"recording {n}.wav" in low:
        n += 1
    return f"Recording {n}.wav"


# ---- which is on which button ----------------------------------------------------------------------------------------
def parse(text):
    """static/soundboard.txt, read: ([[a bank's name, {button: sound}]...], [sounds taken off their buttons])."""
    banks, off, cur = [], [], None
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            name = clean_bank(line[1:-1])
            cur = [name, {}] if name and len(banks) < BANKS_MOST else None
            if cur:
                banks.append(cur)
            continue
        key, eq, value = line.partition("=")
        key, value = key.strip().lower(), value.strip()
        if not eq or not value:
            continue
        if key == "off":
            off.append(value)
        elif cur is not None and key in PADS and key not in cur[1]:
            cur[1][key] = value
    return banks, off


def dumps(banks, off=()):
    """...and written: the banks as they are, and what's off its button."""
    lines = [HEAD]
    lines += [f"off = {name}" for name in off]
    for b in banks:
        lines.append(f"[{b['name']}]")
        lines += [f"{pad} = {b['pads'][pad]}" for pad in PADS if b["pads"].get(pad)]
    return "\n".join(lines).rstrip("\n") + "\n"


def named_apart(banks):
    """Each bank's name its own (a second "Drums" is "Drums 2")."""
    seen = set()
    for b in banks:
        b["name"] = free_name(seen, b["name"] or "Bank", "")
        seen.add(b["name"])
    return banks


def arrange(text, yours, starters):
    """The banks as they are now: (banks, off, placed). banks: [{"name", "pads": {button: sound or None}}]. text:
    what static/soundboard.txt says (None: there's none yet, and the starter pack is on its three banks). A sound
    that isn't there any more is on no button; a sound on two buttons keeps the first. Each of yours that's on no
    button, and wasn't taken off one, goes on the first free button of My sounds (My sounds 2... as each fills):
    placed, the ones this put there just now (something to write the file for). No banks at all: an empty My
    sounds."""
    yours = [n for n in yours if sound_name(n)]
    have = set(starters) | set(yours)
    if text is None:
        raw, off = [[name, {pad: f"{STARTER}{s}.wav" for pad, s in pads.items()}] for name, pads in STARTER_BANKS], []
        raw = [b for b in raw if any(s in have for s in b[1].values())]
    else:
        raw, off = parse(text)
    seen, banks = set(), []
    for name, pads in raw:
        row = {}
        for pad in PADS:
            sid = pads.get(pad)
            row[pad] = sid if sid in have and sid not in seen else None
            seen.add(row[pad])
        banks.append({"name": name, "pads": row})
    seen.discard(None)
    named_apart(banks)
    mine = set(yours)
    off = [n for n in dict.fromkeys(off) if n in mine and n not in seen]
    gone, placed = set(off), []
    for name in yours:
        if name in seen or name in gone:
            continue
        if place(banks, name):
            placed.append(name)
        else:
            off.append(name)                           # (no room in any bank, and no room for another: off, for now)
    if not banks:
        banks.append({"name": MINE, "pads": dict.fromkeys(PADS)})
    return banks, off, placed


def place(banks, sid):
    """A new sound of yours, on the first free button of My sounds (or My sounds 2...: made, as each fills). False:
    there's no room left."""
    for b in banks:
        if b["name"] == MINE or b["name"].startswith(MINE + " "):
            pad = free_pad(b)
            if pad:
                b["pads"][pad] = sid
                return True
    if len(banks) >= BANKS_MOST:
        return False
    banks.append({"name": free_name([b["name"] for b in banks], MINE, ""), "pads": dict.fromkeys(PADS)})
    banks[-1]["pads"][PADS[0]] = sid
    return True


def free_pad(bank):
    return next((pad for pad in PADS if not bank["pads"].get(pad)), None)


def where(banks, sid):
    """(which bank, which button) a sound is on, or None."""
    for i, b in enumerate(banks):
        for pad in PADS:
            if b["pads"].get(pad) == sid:
                return i, pad
    return None


def put(banks, off, sid, i, pad, swap=True):
    """A sound put on a button. From another button, the two change places (swap), or it just moves there. What was
    on that button, if it has nowhere to go, comes off it (kept: one of yours is among those taken off, so it isn't
    put back on a button by itself). False: no such bank or button."""
    if not (0 <= i < len(banks)) or pad not in PADS:
        return False
    was, old = where(banks, sid), banks[i]["pads"].get(pad)
    if was == (i, pad):
        return True
    banks[i]["pads"][pad] = sid
    if sid in off:
        off.remove(sid)
    if was:
        banks[was[0]]["pads"][was[1]] = old if swap else None
    if old and not (was and swap) and not is_starter(old) and old not in off:
        off.append(old)
    return True


def lift(banks, off, i, pad):
    """A button's sound taken off it (kept, among your sounds)."""
    if not (0 <= i < len(banks)) or pad not in PADS:
        return False
    old, banks[i]["pads"][pad] = banks[i]["pads"].get(pad), None
    if old and not is_starter(old) and old not in off:
        off.append(old)
    return True


def forget(banks, off, sid):
    """A sound that's gone (its file deleted): off its button, and off the list of those taken off."""
    at = where(banks, sid)
    if at:
        banks[at[0]]["pads"][at[1]] = None
    if sid in off:
        off.remove(sid)


def renamed(banks, off, old, new):
    """A sound of yours with a new name: on the same button, by that name."""
    at = where(banks, old)
    if at:
        banks[at[0]]["pads"][at[1]] = new
    if old in off:
        off[off.index(old)] = new


def bank_add(banks, name=""):
    """A new, empty bank at the end: its number, or None (that's as many as there can be)."""
    if len(banks) >= BANKS_MOST:
        return None
    banks.append({"name": free_name([b["name"] for b in banks], clean_bank(name) or "Bank", ""),
                  "pads": dict.fromkeys(PADS)})
    return len(banks) - 1


def bank_rename(banks, i, name):
    name = clean_bank(name)
    if not (0 <= i < len(banks)) or not name:
        return False
    banks[i]["name"] = free_name([b["name"] for k, b in enumerate(banks) if k != i], name, "")
    return True


def bank_drop(banks, off, i):
    """A bank gone: its sounds stay, off their buttons."""
    if not (0 <= i < len(banks)):
        return False
    for pad in PADS:
        lift(banks, off, i, pad)
    del banks[i]
    return True


def bank_move(banks, i, to):
    """A bank moved to another place in their order (L and R go through them in it)."""
    if not (0 <= i < len(banks)) or not (0 <= to < len(banks)):
        return False
    banks.insert(to, banks.pop(i))
    return True


def starters_off(banks, starters):
    """The starter pack's sounds that are on no button."""
    on = {sid for b in banks for sid in b["pads"].values() if sid}
    return [sid for sid in starters if sid not in on]


def starter_back(banks, starters):
    """The starter pack's sounds that are on no button, put back on buttons: each on its own in its own bank
    (Starter, Drums, Arcade) if that's free, else on that bank's first free one; those there's no room for (or whose
    bank's gone) in a new bank of that name. (How many went back, the first bank that got one.)"""
    left, count, first = set(starters_off(banks, starters)), 0, None
    for name, pads in STARTER_BANKS:
        row = {pad: f"{STARTER}{s}.wav" for pad, s in pads.items()}
        row = {pad: sid for pad, sid in row.items() if sid in left}
        if not row:
            continue
        i = next((k for k, b in enumerate(banks) if b["name"] == name), None)
        if i is not None:
            for pad, sid in list(row.items()):         # (its own button, if nothing's taken it)
                if not banks[i]["pads"].get(pad):
                    banks[i]["pads"][pad] = sid
                    del row[pad]
            for pad, sid in list(row.items()):         # (...or the first free one there)
                free = free_pad(banks[i])
                if free:
                    banks[i]["pads"][free] = sid
                    del row[pad]
            got = sum(1 for sid in banks[i]["pads"].values() if sid in left)
            if got:
                count, first = count + got, i if first is None else first
        if row and len(banks) < BANKS_MOST:
            banks.append({"name": free_name([b["name"] for b in banks], name, ""),
                          "pads": {pad: row.get(pad) for pad in PADS}})
            count, first = count + len(row), len(banks) - 1 if first is None else first
    return count, first


# ---- sound itself: a WAV file read and written, a recording's silence trimmed -------------------------------------
def wav_shape(f):
    """A WAV file's own words about itself (f: it, open): {"pcm", "rate", "channels", "bits", "at", "frames"}; at:
    where its samples start. ValueError: it isn't one."""
    head = f.read(12)
    if len(head) < 12 or head[:4] != b"RIFF" or head[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    fmt = None
    for _ in range(64):                                # (its parts, one after another: its format, then its samples)
        part = f.read(8)
        if len(part) < 8:
            break
        kind, size = part[:4], struct.unpack("<I", part[4:])[0]
        if kind == b"fmt ":
            body = f.read(size + (size & 1))
            if len(body) < 16:
                break
            tag, channels, rate, _, _, bits = struct.unpack("<HHIIHH", body[:16])
            if tag == 0xFFFE and len(body) >= 26:      # (the long way of saying it: its real kind is further in)
                tag = struct.unpack("<H", body[24:26])[0]
            fmt = (tag, channels, rate, bits)
        elif kind == b"data":
            if fmt is None:
                break
            tag, channels, rate, bits = fmt
            if channels < 1 or bits < 8 or rate < 1:
                break
            at = f.tell()
            f.seek(0, 2)
            size = min(size, f.tell() - at)
            return {"pcm": tag == 1, "rate": rate, "channels": channels, "bits": bits, "at": at,
                    "frames": size // (channels * (bits // 8))}
        else:
            f.seek(size + (size & 1), 1)
    raise ValueError("not a WAV file")


def read_wav(path, most=None):
    """A WAV file's samples, as numpy has them: (its rate, an array of 16-bit numbers, a row a moment, a column a
    channel). most: no more than this many seconds of it. ValueError: it isn't one this can read (8, 16, 24 or 32
    bits, not squeezed)."""
    import numpy as np
    with open(path, "rb") as f:
        w = wav_shape(f)
        if not w["pcm"] or w["bits"] not in (8, 16, 24, 32):
            raise ValueError("a kind of WAV file this can't read")
        frames = w["frames"] if most is None else min(w["frames"], int(most * w["rate"]))
        f.seek(w["at"])
        raw = f.read(frames * w["channels"] * (w["bits"] // 8))
    width = w["bits"] // 8
    raw = raw[:len(raw) - len(raw) % (width * w["channels"])]
    if width == 1:
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.int16) - 128) << 8
    elif width == 2:
        x = np.frombuffer(raw, dtype="<i2")
    elif width == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        x = (b[:, 1].astype(np.int16) | (b[:, 2].astype(np.int8).astype(np.int16) << 8))
    else:
        x = (np.frombuffer(raw, dtype="<i4") >> 16).astype(np.int16)
    return w["rate"], x.reshape(-1, w["channels"])


def wav_bytes(samples, rate=RATE):
    """16-bit samples (a column a channel, or just a row of them) as a WAV file's bytes."""
    import numpy as np
    x = np.asarray(samples, dtype="<i2")
    channels = 1 if x.ndim == 1 else x.shape[1]
    data = x.tobytes()
    head = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + struct.pack(
        "<IHHIIHH", 16, 1, channels, rate, rate * channels * 2, channels * 2, 16) + b"data" + struct.pack("<I", len(data))
    return head + data


def write_wav(path, samples, rate=RATE):
    """...kept as a file: written beside where it goes, then put there whole."""
    tmp = os.path.join(os.path.dirname(path), "." + os.path.basename(path) + ".part")
    try:
        with open(tmp, "wb") as f:
            f.write(wav_bytes(samples, rate))
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


TRIM_STEP = 0.01                 # seconds of a recording looked at at a time
TRIM_FLOOR = 0.012               # as loud as this (of all it can be) at least, to count as sound: a quiet room isn't
TRIM_BELOW = 0.08                # ...and as loud as this much of the recording's loudest moment
TRIM_BEFORE, TRIM_AFTER = 0.03, 0.15   # seconds kept before the sound starts, and after it ends (its tail)
TRIM_LOUD = 0.9                  # what a quiet recording's loudest moment is brought up to
TRIM_GAIN = 8.0                  # ...but never made more than this many times louder (a room's hum stays hum)


def trimmed(samples, rate=RATE):
    """A recording with the silence before and after it gone: from just before its first sound to a little after its
    last, its start and end faded in and out (no click), and brought up if it's quiet. One channel of it. None:
    there's no sound in it."""
    import numpy as np
    x = np.asarray(samples)
    if x.ndim > 1:
        x = x.astype(np.int32).mean(axis=1)
    x = x.astype(np.float32) / 32768.0
    step = max(1, int(rate * TRIM_STEP))
    n = len(x) // step
    if n < 3:
        return None
    x = x - float(np.mean(x))                          # (a microphone's steady lean one way: not sound)
    peaks = np.abs(x[:n * step]).reshape(n, step).max(axis=1)
    top = float(peaks.max())
    if top < TRIM_FLOOR:
        return None
    loud = np.nonzero(peaks >= max(TRIM_FLOOR, top * TRIM_BELOW))[0]
    a = max(0, int(loud[0]) * step - int(rate * TRIM_BEFORE))
    b = min(len(x), (int(loud[-1]) + 1) * step + int(rate * TRIM_AFTER))
    out = x[a:b].copy()
    edge = min(len(out) // 2, int(rate * 0.006))
    if edge:
        ramp = np.linspace(0.0, 1.0, edge, dtype=np.float32)
        out[:edge] *= ramp
        out[-edge:] *= ramp[::-1]
    out *= min(TRIM_GAIN, TRIM_LOUD / top) if top < TRIM_LOUD else 1.0
    return np.clip(np.round(out * 32767.0), -32768, 32767).astype("<i2")
