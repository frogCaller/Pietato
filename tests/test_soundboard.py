"""The Soundboard, in Apps (pitato/soundbank.py, soundplay.py, soundboard.py, screens/soundboard.py). Its starter pack:
two dozen sounds, each just what pitato/sounds/make.py makes (nobody's recording), with their credits (public domain,
CC0). Its banks' file: read, written and kept in order (a sound on one button at most, a new one of yours on My
sounds' first free one, one that's gone off its button). Its player, on its own, against a pretend sound card (aplay
here takes the sound as ALSA would, a period at a time, and logs when each is heard): a sound's heard a moment after
it's asked for; two at once are both heard; one asked for again starts again; stopping stops them; the volume; too loud
together, turned down rather than left to crackle; where the sound goes; the sound card let go of and taken up again,
busy, and breaking up (a longer buffer: aplay says so, and is asked to in English whatever language the Pi's set up
in); an mp3, an ogg and WAVs of other kinds (through FFmpeg, once: kept); what isn't a sound; and a recording, its
silence trimmed (arecord's a pretend one too). Then the app in media mode: in
Apps, its page on the GPi Case's screen, every button its own sound, L and R through the banks, SELECT stopping them,
START's card (B there goes back; no Record a sound without a microphone); a file put in your Soundboard folder on its
button without anything started again, taken out, changed; the web page's word that something changed; and with a USB
microphone, a sound recorded and put on a button from the controller."""
import json, os, shutil, signal, subprocess, sys, threading, time, wave
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import numpy as np
import pietato_all as g
import pitato.soundbank as B
import pitato.soundboard as SBD
import pitato.listen as L
import pitato.fine as FINE

S = SP + "/t_soundboard"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
for d in (HOME, S + "/bin", S + "/static", S + "/cache", S + "/files", S + "/rec"):
    os.makedirs(d)
ok_all = []
RATE = 48000
PLAYER = ROOT + "/pitato/soundplay.py"
SOUNDS = ROOT + "/pitato/sounds"


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def until(cond, secs=5.0, step=0.01):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(step)
    return bool(cond())


# a pretend aplay: takes the sound a period at a time into a buffer as long as --buffer-time says and plays it at the
# sound card's rate, as ALSA does; logs each period (when it took it, where in the stream it is, how loud, where its
# first sound is, each channel's sum, how far apart the two are), when it starts playing and when it runs dry.
# FAKE_APLAY_BUSY: a file that, while it's there, means something else has the sound card. FAKE_APLAY_BREAKS: it says
# the sound ran dry this many times (on its shortest buffer). Like the real one on a Pi set up in another language,
# it says all that in that language (German here) unless it's run with LC_ALL=C: the player reads what it says, so
# that's how it has to run it.
open(S + "/bin/aplay", "w").write('''#!/usr/bin/env python3
import os, sys, time
import numpy as np
args = sys.argv[1:]
plain = os.environ.get("LC_ALL") == "C"
BUSY_SAYS = "Device or resource busy" if plain else "Das Geraet oder die Ressource ist belegt"
DRY_SAYS = "underrun" if plain else "Unterlauf"
rate = int(args[args.index("-r") + 1]) if "-r" in args else 48000
buf = next((int(a.split("=")[1]) for a in args if a.startswith("--buffer-time=")), 100000)
per = next((int(a.split("=")[1]) for a in args if a.startswith("--period-time=")), 20000)
log = open(os.environ["FAKE_APLAY_LOG"], "a", buffering=1)
busy = os.environ.get("FAKE_APLAY_BUSY")
if busy and os.path.exists(busy):
    time.sleep(0.05)
    sys.stderr.write(f"aplay: main:831: audio open error: {BUSY_SAYS}\\n")
    log.write(f"# busy {time.monotonic():.6f}\\n")
    sys.exit(1)
time.sleep(0.03)                                       # (opening a sound card takes a moment)
pf, bf = per * rate // 1000000, buf * rate // 1000000
log.write(f"# open {time.monotonic():.6f} buffer {buf} period {per} args {' '.join(args)}\\n")
breaks = int(os.environ.get("FAKE_APLAY_BREAKS") or 0) if buf <= 32000 else 0
start, offset, written = None, 0, 0
def whole(n):
    out = b""
    while len(out) < n:
        d = os.read(0, n - len(out))
        if not d:
            return None
        out += d
    return out
while True:
    now = time.monotonic()
    played = offset if start is None else offset + int((now - start) * rate)
    if start is not None and played >= written:        # (it ran dry)
        sys.stderr.write("%s!!! (at least %.3f ms long)\\n" % (DRY_SAYS, (played - written) / rate * 1000)); sys.stderr.flush()
        log.write(f"# underrun {now:.6f}\\n")
        start, offset, played = None, written, written
    if written - played + pf > bf:
        time.sleep(0.0004)
        continue
    data = whole(pf * 4)
    if data is None:
        break
    x = np.frombuffer(data, dtype="<i2").reshape(-1, 2).astype(np.int64)
    loud = np.nonzero(np.abs(x).max(axis=1) > 200)[0]
    log.write(f"{time.monotonic():.6f} {written} {int(np.abs(x).max())} {int(loud[0]) if len(loud) else -1} "
              f"{int(np.abs(x[:, 0]).sum())} {int(np.abs(x[:, 1]).sum())} {int(np.abs(x[:, 0] - x[:, 1]).sum())}\\n")
    written += pf
    if start is None and written - offset + pf > bf:   # (its buffer's full: it starts playing)
        start = time.monotonic()
        log.write(f"# start {start:.6f} at {offset}\\n")
    if breaks and written > rate // 4:
        breaks -= 1
        sys.stderr.write(DRY_SAYS + "!!! (at least 12.000 ms long)\\n"); sys.stderr.flush()
        time.sleep(0.05)
''')
# a pretend arecord: half a second of a quiet room (a microphone that leans a little one way), a second of a tone,
# then the room again, at a microphone's pace. FAKE_AREC: "silent" the room and nothing else; "busy" it won't open
open(S + "/bin/arecord", "w").write('''#!/usr/bin/env python3
import math, os, random, struct, sys, time
args = sys.argv[1:]
rate = int(args[args.index("-r") + 1]) if "-r" in args else 16000
how = open(os.environ["FAKE_AREC"]).read().strip() if os.path.exists(os.environ.get("FAKE_AREC", "")) else ""
open(os.environ["FAKE_AREC_LOG"], "a").write(" ".join(args) + "\\n")
if how == "busy":
    sys.stderr.write("arecord: main:831: audio open error: " + ("Device or resource busy" if os.environ.get("LC_ALL") == "C"
                                                                else "Das Geraet oder die Ressource ist belegt") + "\\n")
    sys.exit(1)
out, rnd = sys.stdout.buffer, random.Random(3)
t0, n, step = time.monotonic(), 0, rate // 50
while True:
    buf = bytearray()
    for k in range(n, n + step):
        t = k / rate
        v = rnd.randint(-40, 40) + 120
        if how != "silent" and 0.5 <= t < 1.5:
            v += int(9000 * math.sin(2 * math.pi * 660 * t) * min(1.0, (t - 0.5) * 40, (1.5 - t) * 40))
        buf += struct.pack("<h", max(-32768, min(32767, v)))
    try:
        out.write(buf); out.flush()
    except BrokenPipeError:
        sys.exit(0)
    n += step
    wait = t0 + n / rate - time.monotonic()
    if wait > 0:
        time.sleep(wait)
''')
for name in ("aplay", "arecord"):
    os.chmod(f"{S}/bin/{name}", 0o755)
REAL_PATH = os.environ["PATH"]
os.environ["PATH"] = S + "/bin:" + REAL_PATH
os.environ.pop("LC_ALL", None)                         # (what aplay and arecord say is in English because the player asks)
ALOG, RLOG, BUSY, AREC = S + "/aplay.log", S + "/arecord.log", S + "/busy", S + "/arec-how"
os.environ.update(FAKE_APLAY_LOG=ALOG, FAKE_AREC_LOG=RLOG, FAKE_APLAY_BUSY=BUSY, FAKE_AREC=AREC)


def alog():
    """The pretend sound card's log: (its periods: when taken, where in the stream, how loud, where its first sound
    is, each channel's sum, how far apart the two are; its other lines)."""
    periods, notes = [], []
    try:
        lines = open(ALOG).read().splitlines()
    except OSError:
        return periods, notes
    for ln in lines:
        if ln.startswith("#"):
            notes.append(ln[2:])
        elif len(ln.split()) == 7:
            t, at, peak, first, left, right, apart = ln.split()
            periods.append((float(t), int(at), int(peak), int(first), int(left), int(right), int(apart)))
    return periods, notes


def heard_at(since_line=0):
    """When the first sound after that line of the log is heard (as the sound card plays it), or None."""
    start = offset = None
    lines = open(ALOG).read().splitlines()
    for ln in lines:
        if ln.startswith("# start"):
            start, offset = float(ln.split()[2]), int(ln.split()[4])
    for ln in lines[since_line:]:
        if ln.startswith("#") or len(ln.split()) != 7:
            continue
        t, at, peak, first = ln.split()[:4]
        if int(first) >= 0 and start is not None:
            return start + (int(at) + int(first) - offset) / RATE
    return None


def log_lines():
    try:
        return len(open(ALOG).read().splitlines())
    except OSError:
        return 0


def tone(path, secs=1.0, rate=RATE, channels=1, lead=0.0, width=2, f=440.0, right=None, amp=0.5):
    """A WAV file: a tone (lead: seconds of silence before it; right: the other channel's own note)."""
    n, n0 = int(secs * rate), int(lead * rate)
    t = np.arange(n) / rate
    env = np.minimum(1.0, np.minimum(t, secs - t) * 200)
    cols = [np.concatenate([np.zeros(n0), np.sin(2 * np.pi * (f if c == 0 or right is None else right) * t) * env * amp])
            for c in range(channels)]
    x = np.stack(cols, axis=1)
    with wave.open(path, "wb") as w:
        w.setnchannels(channels); w.setsampwidth(width); w.setframerate(rate)
        if width == 1:
            w.writeframes((x * 127 + 128).astype(np.uint8).tobytes())
        elif width == 2:
            w.writeframes((x * 32767).astype("<i2").tobytes())
        else:
            v = (x * 8388607).astype("<i4").reshape(-1)
            w.writeframes(b"".join(int(s).to_bytes(4, "little", signed=True)[:3] for s in v))
    return path


def wav_of(path):
    with wave.open(path) as w:
        n, rate, ch, width = w.getnframes(), w.getframerate(), w.getnchannels(), w.getsampwidth()
        x = np.frombuffer(w.readframes(n), dtype="<i2").reshape(-1, ch) if width == 2 else None
    return n / rate, rate, ch, width, x


# ---- the starter pack ---------------------------------------------------------------------------------------------
pack = sorted(n for n in os.listdir(SOUNDS) if n.endswith(".wav"))
shapes = {n: wav_of(f"{SOUNDS}/{n}") for n in pack}
check(f"the starter pack: {len(pack)} sounds, each 48 kHz, 16-bit, one channel, a few seconds at most "
      f"({sum(os.path.getsize(f'{SOUNDS}/{n}') for n in pack) >> 10} KB in all)",
      len(pack) == 24 and all(s[1:4] == (48000, 1, 2) and 0.05 < s[0] <= 4.0 for s in shapes.values())
      and sum(os.path.getsize(f"{SOUNDS}/{n}") for n in pack) < 3 << 20)
check("...none silent, none clipped, each starting and ending quietly (no click)",
      all(3000 < int(np.abs(s[4]).max()) < 32000 and abs(int(s[4][0, 0])) < 1500 and abs(int(s[4][-1, 0])) < 400
          for s in shapes.values()))
made = subprocess.run([sys.executable, SOUNDS + "/make.py", S + "/made"], capture_output=True, text=True)
same = [n for n in pack if os.path.isfile(f"{S}/made/{n}")
        and open(f"{S}/made/{n}", "rb").read() == open(f"{SOUNDS}/{n}", "rb").read()]


def as_made(n):
    """The sound's the one made here just now: as long, and no sample of it more than one step (of 32768) from it.
    (Another machine's sums can come out a hair different in their last place: a step, here and there, at most.)"""
    if not os.path.isfile(f"{S}/made/{n}"):
        return False
    a, b = shapes[n], wav_of(f"{S}/made/{n}")
    return a[:4] == b[:4] and int(np.abs(a[4].astype(np.int32) - b[4].astype(np.int32)).max()) <= 1


check(f"...each just what make.py there makes, from sums (no recording of anyone's): {len(same)} of {len(pack)} the "
      f"same byte for byte, the rest within a step ({made.stderr.strip()[-80:]})", made.returncode == 0
      and all(as_made(n) for n in pack) and sorted(os.listdir(S + "/made")) == pack)
credits = open(SOUNDS + "/CREDITS.txt").read()
check("...their credits: made for Pietato, public domain (CC0 1.0, with its address), every one of them named",
      "CC0 1.0" in credits and "creativecommons.org/publicdomain/zero/1.0" in credits and "public domain" in credits
      and all(n[:-4] in credits for n in pack))
third = open(ROOT + "/THIRD-PARTY-LICENSES.md").read()
check("...in THIRD-PARTY-LICENSES.md, in the README (a line or two), in what setup.sh puts on the Pi, and with each "
      "release's licences", "pitato/sounds" in third and "CC0" in third
      and "pitato/sounds" in open(ROOT + "/README.md").read()
      and sum("oundboard" in ln for ln in open(ROOT + "/README.md").read().splitlines()) <= 2
      and 'install -m 644 "$f" /usr/local/share/pitato/pitato/sounds/' in open(ROOT + "/setup.sh").read()
      and "pitato/sounds/CREDITS.txt" in open(ROOT + "/image/licenses.py").read())
starters = B.starter_sounds()
check(f"...the banks it comes on: Starter, Drums and Arcade, eight sounds each, every sound of the pack on one button "
      f"({len(starters)})", [n for n, _ in B.STARTER_BANKS] == ["Starter", "Drums", "Arcade"]
      and all(sorted(p) == sorted(B.PADS) for _, p in B.STARTER_BANKS)
      and sorted(f"{B.STARTER}{s}.wav" for _, p in B.STARTER_BANKS for s in p.values()) == starters
      and starters == [B.STARTER + n for n in pack])

# ---- the banks' file ----------------------------------------------------------------------------------------------
banks, off, placed = B.arrange(None, [], starters)
check("no file yet, no sounds of yours: the starter pack's three banks, nothing to write",
      [b["name"] for b in banks] == ["Starter", "Drums", "Arcade"] and not off and not placed
      and banks[0]["pads"]["up"] == "Starter/Air horn.wav" and banks[1]["pads"]["b"] == "Starter/Kick.wav")
banks, off, placed = B.arrange(None, ["Laugh.mp3", "boo.OGG", "notes.txt", ".hidden.wav", "a/b.wav"], starters)
check(f"...with sounds of yours: each on My sounds' first free button, in the order they came ({placed}); what isn't "
      f"a sound's name left out", placed == ["Laugh.mp3", "boo.OGG"] and banks[3]["name"] == "My sounds"
      and banks[3]["pads"]["up"] == "Laugh.mp3" and banks[3]["pads"]["left"] == "boo.OGG")
text = B.dumps(banks, off)
again = B.arrange(text, ["Laugh.mp3", "boo.OGG"], starters)
check("...written and read back: the same, with nothing new to write; a file you can read (its banks in brackets, a "
      "button and its sound a line)", again == (banks, off, []) and "[My sounds]\nup = Laugh.mp3\nleft = boo.OGG\n" in text
      and "[Starter]\nup = Starter/Air horn.wav\n" in text and text.startswith("#"))
many = [f"s{k:02d}.wav" for k in range(11)]
b2, o2, p2 = B.arrange(text, ["Laugh.mp3", "boo.OGG"] + many, starters)
check(f"...more of yours than My sounds has buttons: on into My sounds 2 ({[b['name'] for b in b2][3:]})",
      [b["name"] for b in b2][3:] == ["My sounds", "My sounds 2"] and p2 == many
      and sum(1 for v in b2[3]["pads"].values() if v) == 8 and sum(1 for v in b2[4]["pads"].values() if v) == 5)
b3, o3, p3 = B.arrange(text, ["boo.OGG"], starters)
check("...one of yours gone from the folder: off its button (the others stay where they were), not written for that "
      "alone", b3[3]["pads"]["up"] is None and b3[3]["pads"]["left"] == "boo.OGG" and not p3 and not o3)
odd = ("# mine\n[A]\nup = Laugh.mp3\nleft = Laugh.mp3\nsideways = boo.OGG\nx = Nowhere.wav\n\n[A]\ndown=Starter/Ding.wav\n"
       "[]\n[ ]\nup = Starter/Kick.wav\noff = Starter/Ding.wav\noff = boo.OGG\njunk\n")
b4, o4, p4 = B.arrange(odd, ["Laugh.mp3", "boo.OGG", "new.wav"], starters)
check(f"...a file written by hand, with mistakes in it: a sound on two buttons keeps the first, a button that isn't one "
      f"and a sound that isn't there are left out, two banks of a name told apart ({[b['name'] for b in b4]}), a bank "
      f"with no name isn't one; one of yours taken off its button stays off ({o4}), and a new one still goes on My "
      f"sounds", [b["name"] for b in b4] == ["A", "A 2", "My sounds"]
      and b4[0]["pads"] == dict(dict.fromkeys(B.PADS), up="Laugh.mp3")
      and b4[1]["pads"] == dict(dict.fromkeys(B.PADS), down="Starter/Ding.wav")
      and o4 == ["boo.OGG"] and p4 == ["new.wav"] and b4[2]["pads"]["up"] == "new.wav")
bb, oo, _ = B.arrange(text, ["Laugh.mp3", "boo.OGG"], starters)
B.put(bb, oo, "Laugh.mp3", 0, "a")
check("a sound put on a button that has one, from a button of its own: the two change places",
      bb[0]["pads"]["a"] == "Laugh.mp3" and bb[3]["pads"]["up"] == "Starter/Ding.wav")
B.put(bb, oo, "boo.OGG", 0, "b", swap=False)
check("...or it just moves there: what was on that button comes off it, and the one it left is free",
      bb[0]["pads"]["b"] == "boo.OGG" and bb[3]["pads"]["left"] is None and B.where(bb, "Starter/Buzzer.wav") is None)
B.put(bb, oo, "Laugh.mp3", 1, "x", swap=False)
B.put(bb, oo, "boo.OGG", 1, "x", swap=False)
check(f"...one of yours that comes off a button is kept as taken off ({oo}): not put back on one by itself",
      oo == ["Laugh.mp3"] and B.arrange(B.dumps(bb, oo), ["Laugh.mp3", "boo.OGG"], starters)[2] == []
      and B.where(B.arrange(B.dumps(bb, oo), ["Laugh.mp3", "boo.OGG"], starters)[0], "Laugh.mp3") is None)
B.put(bb, oo, "Laugh.mp3", 3, "y")
B.lift(bb, oo, 3, "y")
B.renamed(bb, oo, "Laugh.mp3", "Ha.mp3")
B.renamed(bb, oo, "boo.OGG", "Boo.ogg")
check("...put back, taken off again, renamed: still off, by its new name; one on a button, on it by its new name",
      oo == ["Ha.mp3"] and bb[1]["pads"]["x"] == "Boo.ogg")
B.forget(bb, oo, "Ha.mp3")
B.forget(bb, oo, "Boo.ogg")
check("...deleted: nowhere", not oo and B.where(bb, "Boo.ogg") is None and bb[1]["pads"]["x"] is None)
n = B.bank_add(bb, "  Party [time]\n ")
B.bank_rename(bb, n, "Drums")
B.bank_move(bb, n, 0)
check(f"a bank added (its name tidied: on one line, no brackets), renamed to a name there is (told apart), moved "
      f"first ({[b['name'] for b in bb]})", [b["name"] for b in bb] == ["Drums 2", "Starter", "Drums", "Arcade", "My sounds"])
left = B.starters_off(bb, starters)
back = B.starter_back(bb, starters)
check(f"the starter pack's sounds that are on no button ({[x.split('/')[1][:-4] for x in left]}), put back: each on its "
      f"own button in its own bank where that's free ({back})", sorted(left) == ["Starter/Buzzer.wav", "Starter/Clap.wav"]
      and back == (2, 1) and bb[1]["pads"]["b"] == "Starter/Buzzer.wav"
      and bb[2]["pads"]["x"] == "Starter/Clap.wav" and not B.starters_off(bb, starters) and len(bb) == 5)
B.put(bb, oo, "Starter/Kick.wav", 0, "a")
B.bank_drop(bb, oo, 1)
left = B.starters_off(bb, starters)
back = B.starter_back(bb, starters)
check(f"...a bank deleted: its sounds on no button ({len(left)} of the starter pack's); put back: in a bank of that "
      f"name again ({[b['name'] for b in bb]}, {back})", len(left) == 7 and back == (7, 4) and bb[-1]["name"] == "Starter"
      and not B.starters_off(bb, starters) and bb[-1]["pads"]["up"] == "Starter/Air horn.wav"
      and bb[-1]["pads"]["a"] is None and B.starter_back(bb, starters) == (0, None))
taken = [{"name": "Starter", "pads": {pad: "Mine.wav" if pad != "y" else None for pad in B.PADS}}]
back = B.starter_back(taken, starters[:3] + ["Starter/Crickets.wav"])
check(f"...their own buttons taken: its own if it's free, the bank's first free one, and the rest in a new bank "
      f"({[b['name'] for b in taken]}, {back})", back[0] == 4 and taken[0]["pads"]["y"] == "Starter/Crickets.wav"
      and [b["name"] for b in taken] == ["Starter", "Starter 2", "Arcade"] and taken[1]["pads"]["up"] == "Starter/Air horn.wav")
full = [{"name": f"B{k}", "pads": dict.fromkeys(B.PADS)} for k in range(B.BANKS_MOST)]
check(f"...no more than {B.BANKS_MOST} banks", B.bank_add(full) is None and len(full) == B.BANKS_MOST)
check("names that won't do as a sound's: a path, a hidden file, another kind of file, a name with a line break",
      all(B.sound_name(x) is None for x in ("../x.wav", "a/b.wav", ".x.wav", "x.txt", "x.wav\n", "x\ny.wav", ".wav", "", None, 5))
      and all(B.sound_name(x) == x for x in ("x.wav", "My Laugh (2).MP3", "été.ogg")))
for k, name in enumerate(("old.wav", "mid.mp3", "new.ogg")):
    open(f"{S}/files/{name}", "wb").write(b"x" * (k + 1))
    os.utime(f"{S}/files/{name}", (1000 + k, 1000 + k))
os.makedirs(S + "/files/folder.wav")
open(S + "/files/empty.wav", "wb").close()
check(f"your folder, looked at: its sounds, the oldest first (a folder and an empty file aren't sounds): "
      f"{B.your_sounds(S + '/files')}", B.your_sounds(S + "/files") == ["old.wav", "mid.mp3", "new.ogg"]
      and B.your_sounds(S + "/nowhere") == [] and B.scan(S + "/files")[0][2] == 1)
quiet = (np.random.default_rng(1).integers(-40, 41, RATE) + 150).astype(np.int16)        # a room, a microphone leaning
said_ = (np.sin(np.arange(RATE // 2) * 2 * np.pi * 300 / RATE) * 5000).astype(np.int16) + 150
cut = B.trimmed(np.concatenate([quiet, said_, quiet, quiet]))
faint = B.trimmed(np.concatenate([quiet, (said_ - 150) // 8 + 150, quiet]))
check(f"a recording, trimmed: two seconds of a quiet room round half a second of sound, {len(cut) / RATE:.2f} s kept "
      f"(a little before it, its tail after), brought up to a good level ({int(np.abs(cut).max())}), faded at its "
      f"ends; a faint one, brought up no more than eight times ({int(np.abs(faint).max())}: the room isn't made "
      f"loud); a room alone: nothing", 0.6 < len(cut) / RATE < 0.75 and 28000 < int(np.abs(cut).max()) <= 32767
      and abs(int(cut[0])) < 200 and abs(int(cut[-1])) < 200 and 4000 < int(np.abs(faint).max()) < 6000
      and B.trimmed(np.concatenate([quiet, quiet])) is None and B.trimmed(np.zeros(100, np.int16)) is None)
check("...Recording 1, 2, 3: the next number not taken", B.recording_name([]) == "Recording 1.wav"
      and B.recording_name(["recording 1.WAV", "Recording 2.wav", "x.mp3"]) == "Recording 3.wav")


# ---- the player, on its own ---------------------------------------------------------------------------------------
class Player:
    def __init__(self, cache=S + "/cache", **env):
        self.said = []
        self.p = subprocess.Popen([sys.executable, "-I", PLAYER, cache], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  env=dict(os.environ, **env), text=True, bufsize=1)
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        for line in self.p.stdout:
            self.said.append((time.monotonic(), json.loads(line)))

    def tell(self, **c):
        self.p.stdin.write(json.dumps(c) + "\n")
        self.p.stdin.flush()

    def got(self, what, **more):
        return [m for _, m in self.said if m.get("is") == what and all(m.get(k) == v for k, v in more.items())]

    def playing(self):
        return next((m["ids"] for _, m in reversed(self.said) if m["is"] == "playing"), [])

    def sound(self):
        return next((m for _, m in reversed(self.said) if m["is"] == "sound"), None)

    def cpu(self):
        f = open(f"/proc/{self.p.pid}/stat").read().rsplit(")", 1)[1].split()
        return (int(f[11]) + int(f[12])) / os.sysconf("SC_CLK_TCK")

    def quit(self):
        try:
            self.tell(do="quit")
        except (OSError, ValueError):
            pass
        try:
            return self.p.wait(5)
        except subprocess.TimeoutExpired:
            self.p.kill()
            return None


def sid(name):
    return f"{B.STARTER}{name}.wav"


every = [[s, B.path_of(s, HOME + "/Soundboard")] for s in starters]
p = Player()
t0 = time.monotonic()
p.tell(do="load", sounds=every)
until(lambda: len(p.got("ready")) == 24, 15)
secs = {m["id"]: m["secs"] for m in p.got("ready")}
check(f"the player: the starter pack read and ready in {time.monotonic() - t0:.2f} s, each as long as its file "
      f"(a silent start aside), none it can't play", len(secs) == 24 and not p.got("bad")
      and all(shapes[s[len(B.STARTER):]][0] - 0.06 <= secs[s] <= shapes[s[len(B.STARTER):]][0] + 0.01 for s in secs))
check("...the sound card's left alone till it's wanted", log_lines() == 0 and p.sound() is None)
p.tell(do="volume", v=80)
p.tell(do="warm")
until(lambda: p.sound() is not None, 5)
periods, notes = alog()
opened = next((n for n in notes if n.startswith("open")), "")
check(f"...wanted: aplay, two 16-bit channels at 48 kHz, a short buffer (32 ms, in 8 ms periods), where ALSA sends "
      f"it ({opened[opened.find('args'):]}); and it says so ({p.sound()})",
      "-t raw -f S16_LE -c 2 -r 48000 --buffer-time=32000 --period-time=8000" in opened and " -D" not in opened
      and "-q" in opened and p.sound() == {"is": "sound", "ok": True, "buffer": 32, "paced": True})
time.sleep(1.0)
c0, w0, n0 = p.cpu(), time.monotonic(), len(alog()[0])
time.sleep(3.0)
used, periods = (p.cpu() - c0) / (time.monotonic() - w0), alog()[0]
check(f"...nothing playing: silence, kept going (so a TV's or headphones' sound stays awake), at the sound card's "
      f"pace ({(len(periods) - n0) / 3:.0f} periods a second), never running dry; and it costs "
      f"{used * 100:.1f}% of a processor", all(x[2] == 0 for x in periods) and 110 < (len(periods) - n0) / 3 < 140
      and not any(n.startswith("underrun") for n in alog()[1]) and used < 0.08)
lates = []
for k in range(8):
    time.sleep(0.4)
    mark, t = log_lines(), time.monotonic()
    p.tell(do="play", id=sid("Kick"))
    until(lambda: heard_at(mark) is not None, 2)
    at = heard_at(mark)
    lates.append((at - t) * 1000 if at else 9999)
    until(lambda: p.playing() == [], 2)
check(f"a sound asked for: heard {sorted(lates)[len(lates) // 2]:.0f} ms later (the most of eight times: "
      f"{max(lates):.0f} ms), the buffer and a little", sorted(lates)[len(lates) // 2] < 70 and max(lates) < 150)
n_said = len(p.said)
p.tell(do="play", id=sid("Air horn"))
until(lambda: p.playing() == [sid("Air horn")], 2)
t_on = next(t for t, m in p.said[n_said:] if m["is"] == "playing" and m["ids"])
until(lambda: p.playing() == [], 4)
t_off = p.said[-1][0]
check(f"...it says which is playing as it starts, and when it's over ({t_off - t_on:.2f} s after, for a sound of "
      f"{secs[sid('Air horn')]:.2f} s)", abs((t_off - t_on) - secs[sid("Air horn")]) < 0.2)
p.tell(do="play", id=sid("Applause"))
time.sleep(0.15)
p.tell(do="play", id=sid("Ding"))
until(lambda: p.playing() == sorted([sid("Applause"), sid("Ding")]), 2)
check(f"two at once: both playing ({[x.split('/')[1] for x in p.playing()]})",
      p.playing() == sorted([sid("Applause"), sid("Ding")]))
until(lambda: p.playing() == [], 6)
p.tell(do="play", id=sid("Sad horn"))
t1 = time.monotonic()
time.sleep(0.5)
n_said = len(p.said)
p.tell(do="play", id=sid("Sad horn"))
t2 = time.monotonic()
until(lambda: p.playing() == [], 6)
t_end = p.said[-1][0]
changes = [m for _, m in p.said[n_said:] if m["is"] == "playing"]
check(f"one asked for again while it plays: from its start again (over {t_end - t2:.2f} s after the second time, the "
      f"sound's {secs[sid('Sad horn')]:.2f} s), one sound all along, not two",
      abs((t_end - t2) - secs[sid("Sad horn")]) < 0.2 and t_end - t1 > secs[sid("Sad horn")] + 0.3 and changes == [{"is": "playing", "ids": []}])
p.tell(do="play", id=sid("Applause"))
p.tell(do="play", id=sid("Siren"))
until(lambda: len(p.playing()) == 2, 2)
time.sleep(0.3)
t = time.monotonic()
p.tell(do="stop")
until(lambda: p.playing() == [], 2)
took = p.said[-1][0] - t
time.sleep(0.25)
tail = [x for x in alog()[0] if x[0] > t + 0.15]
check(f"stopped: all of them, at once ({took * 1000:.0f} ms till it says none's playing), and silence after "
      f"({len(tail)} periods)", took < 0.2 and len(tail) > 5 and all(x[2] == 0 for x in tail))


def loudest(name, wait=None):
    mark = len(alog()[0])
    p.tell(do="play", id=sid(name))
    until(lambda: p.playing() != [], 2)
    until(lambda: p.playing() == [], wait or secs[sid(name)] + 2)
    time.sleep(0.1)
    return max((x[2] for x in alog()[0][mark:]), default=0)


full_peak = loudest("Kick")
p.tell(do="volume", v=20)
quarter = loudest("Kick")
p.tell(do="volume", v=0)
none = loudest("Kick")
p.tell(do="volume", v=80)
check(f"the volume: at 80, the kick's loudest is {full_peak}; at 20, {quarter} (a quarter); at 0, {none}",
      abs(quarter / full_peak - 0.25) < 0.03 and none == 0 and 15000 < full_peak < 32767)
p.tell(do="volume", v=100)
mark = len(alog()[0])
for name in ("Air horn", "Applause", "Explosion", "Crash", "Ta-da", "Siren", "Buzzer", "Sad horn"):
    p.tell(do="play", id=sid(name))
time.sleep(1.0)
p.tell(do="stop")
until(lambda: p.playing() == [], 2)
time.sleep(0.2)
loud = [x[2] for x in alog()[0][mark:] if x[2] > 0]
flat = sum(1 for v in loud if v >= 32767)
raw = sum(np.abs(shapes[n + ".wav"][4][:RATE, 0].astype(np.int64)).max() for n in ("Air horn", "Applause", "Explosion", "Crash"))
check(f"eight loud ones at once, the volume full (together they'd be several times too loud: four of them alone "
      f"{raw}): turned down to fit, not left to crackle ({flat} of {len(loud)} periods touch the top, the loudest "
      f"{max(loud)})", raw > 60000 and max(loud) <= 32767 and flat <= len(loud) * 0.1 and max(loud) > 20000)
p.tell(do="volume", v=80)
breaks = sum(1 for n in alog()[1] if n.startswith("underrun"))
check(f"...and no break in the sound through all of that, or hardly ({breaks}: a busy machine may hold it up once)",
      breaks <= 1)
p.tell(do="device", device="plughw:CARD=Speaker,DEV=0")
until(lambda: sum(1 for n in alog()[1] if n.startswith("open")) == 2, 3)
check("the sound sent somewhere else (Settings > Sound, Bluetooth headphones): aplay again, there",
      alog()[1][-2].startswith("open") and alog()[1][-2].endswith("-D plughw:CARD=Speaker,DEV=0")
      and until(lambda: p.sound() and p.sound()["ok"], 2))
p.tell(do="rest")
time.sleep(0.3)
mark = log_lines()
time.sleep(0.4)
check("let go of (something else is to play): aplay stopped, nothing more sent", log_lines() == mark)
t = time.monotonic()
p.tell(do="play", id=sid("Ding"))
until(lambda: heard_at(mark) is not None, 3)
check(f"...and a sound asked for takes it up again ({(heard_at(mark) - t) * 1000:.0f} ms till it's heard, the sound "
      f"card opened first)", heard_at(mark) is not None and heard_at(mark) - t < 0.5)
until(lambda: p.playing() == [], 4)
open(BUSY, "w").close()
p.tell(do="device", device="")
until(lambda: p.sound() and p.sound()["ok"] is False, 3)
check(f"something else has the sound card: it says so ({p.sound()})", p.sound()["ok"] is False
      and "busy" in p.sound()["why"].lower())
n_said, mark = len(p.said), log_lines()
p.tell(do="play", id=sid("Air horn"))
time.sleep(0.6)
os.remove(BUSY)
until(lambda: p.sound() and p.sound()["ok"], 5)
time.sleep(0.6)
check("...a sound asked for meanwhile isn't played later, out of the blue; and once the sound card's free, it's taken "
      "up again by itself", p.sound()["ok"] and heard_at(mark) is None
      and not any(m["is"] == "playing" and m["ids"] for _, m in p.said[n_said:]))
code = p.quit()
time.sleep(0.2)
mark = log_lines()
time.sleep(0.3)
check(f"told to quit: it does (exit code {code}), and aplay with it", code == 0 and log_lines() == mark)

os.remove(ALOG)
p = Player(FAKE_APLAY_BREAKS="3")
p.tell(do="load", sounds=every[:4])
p.tell(do="warm")
until(lambda: p.sound() and p.sound().get("buffer") == 64, 6)
opens = [n for n in alog()[1] if n.startswith("open")]
check(f"the sound breaking up (three times running, a sound card that can't keep up with so short a buffer): a "
      f"longer one ({[o.split()[3] for o in opens]} µs)", [o.split()[3] for o in opens] == ["32000", "64000"]
      and p.sound() == {"is": "sound", "ok": True, "buffer": 64, "paced": True})
p.p.stdin.close()
check("media mode gone (its end of the pipe closed): the player goes too", p.p.wait(5) == 0)

os.remove(ALOG)
p = Player(PITATO_SOUNDBOARD_PACED="0")
p.tell(do="load", sounds=every)
p.tell(do="warm")
until(lambda: p.sound() is not None and len(p.got("ready")) == 24, 10)
time.sleep(0.5)
lates = []
for k in range(5):
    time.sleep(0.3)
    mark, t = log_lines(), time.monotonic()
    p.tell(do="play", id=sid("Snare"))
    until(lambda: heard_at(mark) is not None, 2)
    lates.append((heard_at(mark) - t) * 1000 if heard_at(mark) else 9999)
    until(lambda: p.playing() == [], 2)
check(f"where the pipe can't say when it's been emptied (how full it is looked at every few ms instead): the same "
      f"({sorted(lates)[2]:.0f} ms to a sound, no breaks)", p.sound()["paced"] is False and sorted(lates)[2] < 70
      and not any(n.startswith("underrun") for n in alog()[1]))
p.p.send_signal(signal.SIGTERM)
check("stopped from outside: it ends cleanly", p.p.wait(5) == 0)

# ---- sounds of every kind -----------------------------------------------------------------------------------------
F = S + "/kinds"
os.makedirs(F)
src = tone(S + "/src.wav", 1.0, lead=0.5)
ff = shutil.which("ffmpeg", path=REAL_PATH)
kinds = {"plain.wav": tone(F + "/plain.wav", 1.0, lead=0.5), "cd.wav": tone(F + "/cd.wav", 1.0, 44100, 2, lead=0.5),
         "low.wav": tone(F + "/low.wav", 1.0, 22050, 1, lead=0.5, width=1),
         "fine.wav": tone(F + "/fine.wav", 1.0, 48000, 2, lead=0.5, width=3),
         "two.wav": tone(F + "/two.wav", 1.0, 48000, 2, f=330, right=880),
         "long.wav": tone(F + "/long.wav", 34.0, 16000)}
for name, args in (("song.mp3", ["-c:a", "libmp3lame", "-b:a", "128k"]), ("clip.ogg", ["-c:a", "libvorbis"])):
    got = subprocess.run([ff, "-v", "error", "-y", "-i", src] + args + [F + "/" + name], capture_output=True, text=True)
    if got.returncode == 0:
        kinds[name] = F + "/" + name
open(F + "/words.mp3", "w").write("these are words, not a sound\n" * 50)
open(F + "/list.mp3", "w").write("#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXTINF:10,\n" + src + "\n#EXT-X-ENDLIST\n")
os.symlink(src, F + "/link.wav")
os.remove(ALOG)
p = Player(S + "/cache2")
files = [[n, F + "/" + n] for n in sorted(os.listdir(F))]
p.tell(do="load", sounds=files)
until(lambda: len(p.got("ready")) + len(p.got("bad")) == len(files), 60)
secs = {m["id"]: m["secs"] for m in p.got("ready")}
bad = {m["id"]: m["why"] for m in p.got("bad")}
check(f"sounds of every kind: WAVs at 48, 44.1 and 22 kHz, 8, 16 and 24 bits, one channel or two, "
      f"{'an mp3, an ogg' if 'song.mp3' in kinds and 'clip.ogg' in kinds else 'NO MP3 OR OGG MADE'}: each ready, a "
      f"second long, the half second of silence before it gone ({ {k: v for k, v in secs.items() if k != 'long.wav'} })",
      "song.mp3" in kinds and "clip.ogg" in kinds
      and all(0.97 <= secs.get(n, 0) <= 1.06 for n in ("plain.wav", "cd.wav", "low.wav", "fine.wav", "two.wav", "link.wav", "song.mp3", "clip.ogg")))
check(f"...a long one: its first half minute ({secs.get('long.wav')} s)", secs.get("long.wav") == 30.0)
check(f"...what isn't a sound, whatever it's called: said so, and nothing more ({bad}); a list of other files named as "
      f"an mp3 isn't followed", set(bad) == {"words.mp3", "list.mp3"} and all(bad.values()))
kept = sorted(os.listdir(S + "/cache2"))
check(f"...the ones FFmpeg read are kept as it made them ({len(kept)}: all but the plain ones at 48 kHz), yours",
      len(kept) == 5 and all(n.endswith(".wav") for n in kept))
p.tell(do="warm")
until(lambda: p.sound() is not None, 3)
mark = len(alog()[0])
p.tell(do="play", id="two.wav")
until(lambda: p.playing() == ["two.wav"], 2)
until(lambda: p.playing() == [], 3)
time.sleep(0.1)
sides = [x[4:7] for x in alog()[0][mark:] if x[2] > 3000]
check(f"...one with a different sound on each side: left and right kept apart ({len(sides)} periods)",
      len(sides) > 60 and all(apart > (a + b) * 0.2 for a, b, apart in sides))
mark = len(alog()[0])
p.tell(do="play", id="plain.wav")
until(lambda: p.playing() == ["plain.wav"], 2)
until(lambda: p.playing() == [], 3)
time.sleep(0.1)
sides = [x[4:7] for x in alog()[0][mark:] if x[2] > 3000]
check(f"...one with a single channel: the same on both sides ({len(sides)} periods)",
      len(sides) > 60 and all(a == b and apart == 0 for a, b, apart in sides))
tone(F + "/plain.wav", 0.4)
p.tell(do="load", sounds=files)
until(lambda: len(p.got("ready", id="plain.wav")) == 2, 5)
check(f"a file changed where it is: read again ({p.got('ready', id='plain.wav')[-1]['secs']} s now), the others left as "
      f"they were", p.got("ready", id="plain.wav")[-1]["secs"] == 0.4 and len(p.got("ready")) == len(secs) + 1)
p.tell(do="play", id="long.wav")
until(lambda: p.playing() == ["long.wav"], 2)
p.tell(do="load", sounds=[f for f in files if f[0] != "long.wav"])
check("...one taken away while it plays: it stops", until(lambda: p.playing() == [], 2))
p.quit()
open(S + "/bin/ffmpeg", "w").write("#!/bin/sh\necho ffmpeg >> " + S + "/ffmpeg-ran\nexit 1\n")
os.chmod(S + "/bin/ffmpeg", 0o755)
p = Player(S + "/cache2")
t0 = time.monotonic()
p.tell(do="load", sounds=[f for f in files if f[0] in ("song.mp3", "clip.ogg", "cd.wav", "fine.wav")])
until(lambda: len(p.got("ready")) == 4, 10)
check(f"the next time: there at once, as kept ({time.monotonic() - t0:.2f} s, FFmpeg not run again)",
      len(p.got("ready")) == 4 and not os.path.exists(S + "/ffmpeg-ran"))
shutil.copy(kinds.get("song.mp3", src), F + "/new.mp3")
p.tell(do="load", sounds=[["low.wav", F + "/low.wav"], ["new.mp3", F + "/new.mp3"]])
until(lambda: len(p.got("ready")) + len(p.got("bad")) == 6, 10)
check(f"...without FFmpeg at all: a plain WAV at another rate still plays ({p.got('ready', id='low.wav')}), an mp3 "
      f"can't ({p.got('bad')})", len(p.got("ready", id="low.wav")) == 1
      and 0.97 <= p.got("ready", id="low.wav")[0]["secs"] <= 1.06 and [m["id"] for m in p.got("bad")] == ["new.mp3"]
      and os.path.exists(S + "/ffmpeg-ran"))
p.quit()
os.remove(S + "/bin/ffmpeg")

# ---- recording ----------------------------------------------------------------------------------------------------
os.remove(ALOG)
REC = S + "/rec/Soundboard"
p = Player()
p.tell(do="load", sounds=every[:8])
p.tell(do="warm")
until(lambda: len(p.got("ready")) == 8 and p.sound() is not None, 10)
p.tell(do="play", id=every[0][0])
until(lambda: p.playing() != [], 2)
p.tell(do="rec", mic="plughw:CARD=Mic,DEV=0", folder=REC)
until(lambda: len(p.got("level")) >= 3, 3)
check(f"recording: arecord, one 16-bit channel at 48 kHz from the microphone given "
      f"({open(RLOG).read().strip()}); what was playing stops", open(RLOG).read().strip()
      == "-q -f S16_LE -r 48000 -c 1 -t raw -D plughw:CARD=Mic,DEV=0" and until(lambda: p.playing() == [], 2))
p.tell(do="play", id=every[1][0])
time.sleep(1.9)
levels = [(m["secs"], m["peak"]) for m in p.got("level")]
check(f"...how loud it is, and how long so far, about ten times a second ({len(levels)} in {levels[-1][0]:.1f} s): "
      f"quiet, then loud ({max(v for _, v in levels):.2f}), then quiet; and nothing's played meanwhile",
      15 <= len(levels) <= 30 and max(v for s_, v in levels if s_ < 0.45) < 0.02
      and max(v for s_, v in levels if 0.7 < s_ < 1.4) > 0.25 and p.playing() == [])
p.tell(do="rec_stop", keep=True)
until(lambda: p.got("recorded"), 5)
got = p.got("recorded")[-1]
shape = wav_of(REC + "/Recording 1.wav") if os.path.isfile(REC + "/Recording 1.wav") else None
check(f"...kept: {got}, a file in the folder given (made for it), 48 kHz, 16-bit, one channel",
      got.get("name") == "Recording 1.wav" and shape is not None and shape[1:4] == (48000, 1, 2)
      and os.listdir(REC) == ["Recording 1.wav"])
x = shape[4][:, 0].astype(np.int64)
first = int(np.argmax(np.abs(x) > 4000))
last = len(x) - int(np.argmax(np.abs(x[::-1]) > 4000))
check(f"...its silence trimmed: the second of sound from 2.4 s of recording ({shape[0]:.2f} s, the sound from "
      f"{first / RATE * 1000:.0f} ms in to {(len(x) - last) / RATE * 1000:.0f} ms before its end); the microphone's "
      f"lean taken out (its average {x.mean():.0f}), and brought up ({np.abs(x).max()})",
      1.1 < shape[0] < 1.3 and got["secs"] == round(shape[0], 2) and first / RATE < 0.06 and 0.1 < (len(x) - last) / RATE < 0.2
      and abs(x.mean()) < 30 and 28000 < np.abs(x).max() <= 32767)
p.tell(do="rec", mic="plughw:CARD=Mic,DEV=0", folder=REC)
time.sleep(1.2)
p.tell(do="rec_stop", keep=False)
until(lambda: len(p.got("recorded")) == 2, 5)
check(f"dropped: nothing kept ({p.got('recorded')[-1]})", p.got("recorded")[-1]["name"] is None
      and p.got("recorded")[-1]["why"] == "dropped" and os.listdir(REC) == ["Recording 1.wav"])
open(AREC, "w").write("silent")
p.tell(do="rec", mic="", folder=REC)
time.sleep(0.8)
p.tell(do="rec_stop", keep=True)
until(lambda: len(p.got("recorded")) == 3, 5)
check(f"a quiet room and nothing else: nothing kept, and it says nothing was heard ({p.got('recorded')[-1]}); no "
      f"microphone named: arecord's own choice", p.got("recorded")[-1] == {"is": "recorded", "name": None, "why": "quiet"}
      and os.listdir(REC) == ["Recording 1.wav"] and open(RLOG).read().splitlines()[-1] == "-q -f S16_LE -r 48000 -c 1 -t raw")
open(AREC, "w").write("busy")
p.tell(do="rec", mic="plughw:CARD=Mic,DEV=0", folder=REC)
until(lambda: len(p.got("recorded")) == 4, 5)
check(f"a microphone that won't open: it says so, in arecord's words ({p.got('recorded')[-1]})",
      p.got("recorded")[-1]["name"] is None and p.got("recorded")[-1]["why"] == "mic"
      and "busy" in p.got("recorded")[-1]["said"])
os.remove(AREC)
p.tell(do="rec", mic="plughw:CARD=Mic,DEV=0", folder=REC)
time.sleep(1.8)
p.tell(do="rec_stop")
until(lambda: len(p.got("recorded")) == 5, 5)
check("the next one kept: Recording 2", p.got("recorded")[-1]["name"] == "Recording 2.wav"
      and sorted(os.listdir(REC)) == ["Recording 1.wav", "Recording 2.wav"])
p.tell(do="load", sounds=[["Recording 1.wav", REC + "/Recording 1.wav"]])
until(lambda: p.got("ready", id="Recording 1.wav"), 5)
mark, t = log_lines(), time.monotonic()
p.tell(do="play", id="Recording 1.wav")
until(lambda: heard_at(mark) is not None, 2)
check(f"...and played like any other, at once ({(heard_at(mark) - t) * 1000:.0f} ms)", heard_at(mark) - t < 0.15)
p.quit()

# ---- the app, in media mode -----------------------------------------------------------------------------------------
os.remove(ALOG)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/mcache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
g.STATIC = S + "/static"
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
g.home_dir = lambda: HOME
A = S + "/asound"                                      # (the sound cards there are: one that plays, no microphone)
os.makedirs(A + "/card0/pcm0p")
HDMI = " 0 [vc4hdmi0       ]: vc4-hdmi - vc4-hdmi-0\n                      vc4-hdmi-0\n"
MIC = " 1 [Device         ]: USB-Audio - USB PnP Sound Device\n                      USB PnP Sound Device at usb-1\n"
open(A + "/cards", "w").write(HDMI)
os.makedirs(S + "/v4l")
L.ASOUND, L.V4L = A, S + "/v4l"
real_run = subprocess.run
subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                       if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in
                                       {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli", "vcgencmd"}
                                       else real_run(cmd, *a, **k))


class FB:
    w, h = 640, 480
    real_w, real_h = 640, 480
    s = 1
    last = None
    frames = 0
    def show(self, img): FB.last = img.copy(); FB.frames += 1; self.frames = FB.frames
    def show_part(self, img, box): self.show(img)
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
m = g.Media()
m.enter()
toasts = []
was_toast = m.toast
m.toast = lambda text, secs=4: (toasts.append(text), was_toast(text, secs))[1]


def flush():
    m.dirty = True
    m.flush()
    return np.asarray(FB.last.convert("RGB")).astype(int)


def spin(secs=0.3, cond=None):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        m.tick()
        if cond is not None and cond():
            return True
        time.sleep(0.01)
    return bool(cond()) if cond is not None else None


def near(page, box, colour, tol=24):
    """How many of a box's pixels are about that colour."""
    x0, y0, x1, y1 = box
    return int((np.abs(page[y0:y1, x0:x1] - np.array(colour)).max(axis=2) <= tol).sum())


def players():
    """The Soundboard's players running now (by their command lines)."""
    out = []
    for pid in os.listdir("/proc"):
        if pid.isdigit():
            try:
                cmd = open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0")
            except OSError:
                continue
            if PLAYER.encode() in cmd:
                out.append(int(pid))
    return out


apps = next(t for t in g.LIBRARY if t["name"] == "Apps")
si = next(k for k, t in enumerate(g.LIBRARY) if t["name"] == "Soundboard")
ai = g.LIBRARY.index(apps)
check("Apps has the Soundboard (after the LED backlight, before the Band), and it's not one of the Bot's "
      "\"something cool\"", apps["children"][apps["children"].index("LED backlight"):][:3]
      == ["LED backlight", "Soundboard", "Band"] and g.LIBRARY[si]["sim"] == "sound"
      and "Soundboard" in g.COOL_SKIP and g.app_named("the soundboard") == "Soundboard")
check("nothing of it runs before it's opened", m.board is None and players() == [] and not os.path.exists(ALOG))
m.open_app(ai)
m.sels[ai] = next(k for k, it in enumerate(m.tab_items()) if it["title"] == "Soundboard")
m.press("a")
check("A on it in Apps opens it", m.tab == si and m.view == "list" and m.board_shown())
spin(3, lambda: m.board is not None and len(m.board.ready) == 24 and m.board.sound_ok)
b = m.board
pids = players()
check(f"...its player's started with it (one process, of its own), has read the starter pack ({len(b.ready)} ready) "
      f"and has the sound card open, where Settings > Sound says ({alog()[1][0].split('args')[1].strip()})",
      len(pids) == 1 and b.proc is not None and b.proc.pid in pids + [os.getppid()] + [b.proc.pid] and len(b.ready) == 24
      and not b.bad and b.sound_ok is True and len(alog()[1]) >= 1)
check(f"...its banks: {[x['name'] for x in b.banks]}, the first on the page; your Soundboard folder made, nothing "
      f"written yet", [x["name"] for x in b.banks] == ["Starter", "Drums", "Arcade"] and b.at == 0
      and os.path.isdir(HOME + "/Soundboard") and not os.path.exists(S + "/static/soundboard.txt"))
page = flush()
s = m.sim_game()
boxes = {pad: (x, 78 + y, x + w, 78 + y + h) for pad, (x, y, w, h) in s.boxes().items()}
check(f"its page, on the GPi Case's screen: the bank's name and which it is ({s.bank}), a tile for each of the eight "
      f"buttons, laid out as on a controller (the d-pad's on the left, up above left and right above down; X, Y, A and "
      f"B on the right), all on the screen, none over another",
      s.bank == (0, 3, "Starter") and sorted(boxes) == sorted(B.PADS)
      and all(0 <= x0 < x1 <= 640 and 78 + SBD.TOP <= y0 < y1 <= 432 for x0, y0, x1, y1 in boxes.values())
      and boxes["up"][3] < boxes["left"][1] < boxes["left"][3] < boxes["down"][1] and boxes["left"][2] < boxes["right"][0]
      and boxes["right"][2] < boxes["y"][0] and boxes["x"][3] < boxes["y"][1] and boxes["y"][2] < boxes["a"][0]
      and boxes["a"][3] < boxes["b"][1] and boxes["up"][0] == boxes["down"][0] and boxes["x"][0] == boxes["b"][0])
check(f"...each with its sound's name ({ {k: v[0] for k, v in s.pads.items()} })",
      {k: v for k, v in s.pads.items()} == {pad: (name, "ready") for pad, name in dict(B.STARTER_BANKS)["Starter"].items()})
caps = {pad: near(page, (boxes[pad][0] + 8, boxes[pad][1] + 8, boxes[pad][0] + 40, boxes[pad][1] + 38), SBD.PAD_COLOUR[pad])
        for pad in B.PADS}
check(f"...and its button's own mark, each in a colour of its own ({len(set(SBD.PAD_COLOUR.values()))} colours: "
      f"{min(caps.values())} pixels of it or more)", min(caps.values()) > 150 and len(set(SBD.PAD_COLOUR.values())) == 8)
hints = m.sim_hints(s)
check(f"...its buttons along the bottom: {hints}", hints == [("L R", "Bank"), ("SELECT", "Stop"), ("START", "Back, more")])
taps = {w[1]: box for box, w in m.taps_now() if w[0] == "keys"}
check("...each tile tapped (the web page's copy of the screen, a touch screen) is its button pressed; the bank's "
      "name, L or R", all(tuple(taps.get(pad, ())) == boxes[pad] for pad in B.PADS) and "l" in taps and "r" in taps
      and taps["l"][2] <= taps["r"][0])
want = dict(B.STARTER_BANKS)["Starter"]
ok_each = []
for pad in B.PADS:
    m.press(pad)
    ok = spin(1.5, lambda: sid(want[pad]) in b.playing)
    page = flush()
    lit = near(page, boxes[pad], SBD.PAD_COLOUR[pad])
    others = max(near(page, boxes[q], SBD.PAD_COLOUR[q]) for q in B.PADS if q != pad and sid(want[q]) not in b.playing)
    ok_each.append((pad, ok, lit, others))
    m.press("select")
    spin(1.0, lambda: not b.playing)
area = (boxes["a"][2] - boxes["a"][0]) * (boxes["a"][3] - boxes["a"][1])
check(f"each of the eight buttons plays the sound that's on it, and its tile lights up in its colour while it plays "
      f"(most of its {area} pixels: {[(p_, n_) for p_, _, n_, _ in ok_each]}; the others', their marks alone)",
      all(ok and lit > area * 0.6 and others < area * 0.15 for _, ok, lit, others in ok_each))
check("...SELECT stopped each", not b.playing)
m.press("x"); m.press("up"); m.press("a")
spin(1.0, lambda: len(b.playing) == 3)
check(f"three pressed one after another: all three at once ({sorted(x.split('/')[1] for x in b.playing)})",
      b.playing == {sid("Applause"), sid("Air horn"), sid("Ding")})
m.press("select")
spin(1.0, lambda: not b.playing)
mark = len(alog()[0])
m.press("down")
spin(4, lambda: sid("Sad horn") in b.playing)
spin(4, lambda: not b.playing)
once = len([x for x in alog()[0][mark:] if x[2] > 2000])
mark = len(alog()[0])
m.press("down")
spin(0.25)
for k in range(12):
    m.press("down", repeat=True)                       # (held down: the menus' way of moving on and on)
    spin(0.03)
spin(4, lambda: not b.playing)
held = len([x for x in alog()[0][mark:] if x[2] > 2000])
check(f"a button held down plays its sound once, not again and again (the sad horn: {held * 8} ms of sound, as when "
      f"it's pressed and let go, {once * 8} ms)", once > 100 and abs(held - once) <= 3)
m.press("b")
spin(1.0, lambda: sid("Buzzer") in b.playing)
check("B is a button like the others here: its sound, and the page stays", sid("Buzzer") in b.playing and m.tab == si
      and m.board_shown())
m.press("select")
m.press("r")
spin(0.3)
s = m.sim_game()
check(f"R: the next bank ({s.bank}), its sounds on the buttons ({s.pads['b'][0]}, {s.pads['a'][0]}...)",
      s.bank == (1, 3, "Drums") and s.pads["b"] == ("Kick", "ready") and b.at == 1)
m.press("b")
check("...and its buttons play them", spin(1.0, lambda: sid("Kick") in b.playing))
m.press("r"); m.press("r")
check("...round and round: R past the last is the first", m.sim_game().bank[0] == 0)
m.press("l")
check("...L the other way; L2 and R2 too", m.sim_game().bank[0] == 2 and (m.press("r2"), m.sim_game().bank[0])[1] == 0
      and (m.press("l2"), m.sim_game().bank[0])[1] == 2)
m.press("r")
m.set_setting("sim_full", "On")
page = flush()
check("no full screen for it (Apps' others' SELECT): its page is the whole of it, its buttons along the bottom",
      not m.sim_full() and near(page, (0, 432, 640, 480), g.BG, 6) > 15000 and m.sim_hints(m.sim_game()) == hints)
m.set_setting("sim_full", "Off")
spin(2, lambda: not b.playing)

# START's card
m.press("start")
page = flush()
rows = m.board_rows()
check(f"START: its card ({[r[1] for r in rows]}): no Record a sound, with no microphone; its buttons "
      f"{m.sim_hints(m.sim_game())}", m.sim_opts == 0 and [r[0] for r in rows] == ["bank", "volume"]
      and m.sim_hints(m.sim_game()) == [("▲▼", "Choose"), ("◀▶", "Change"), ("A", "Done"), ("B", "Back to Apps")]
      and not any(w == ("keys", "a") and box == boxes["a"] for box, w in m.taps_now()))
m.press("up")
spin(0.3)
check("...the buttons are the card's while it's up: no sound", not b.playing and m.sim_opts == 1)
m.press("down")
m.press("right")
check("...◀▶ on Bank: the next bank, behind it", b.at == 1 and m.board_rows()[0][2] == "Drums")
m.press("down")
vol = m.volume
m.press("left"); m.press("left")
spin(0.3)
m.press("right", repeat=True)
spin(0.2)
check(f"...on Volume: quieter and louder (kept as the players' own: {vol}, {m.volume})", m.volume == vol - 5
      and m.board_rows()[1][2] == str(vol - 5) and b.volume == m.volume)
m.press("a")
check("...A: on with the Soundboard, where it was", m.sim_opts is None and m.board_shown() and b.at == 1)
m.press("start")
m.press("start")
check("...START again too", m.sim_opts is None and m.board_shown())
m.press("b")
spin(0.5, lambda: sid("Kick") in b.playing)
m.press("start")
m.press("select")
check("...SELECT stops the sounds from there as well", spin(1.0, lambda: not b.playing) and m.sim_opts is not None)
pid = b.proc.pid
m.press("b")
spin(0.3)
check("...B there goes back to Apps, the Soundboard picked in its list",
      m.tab == ai and m.view == "list" and m.tab_items()[m.sels[ai]]["title"] == "Soundboard" and m.sim_opts is None)
gone = until(lambda: players() == [], 4)
mark = log_lines()
time.sleep(0.3)
check("...and its player's gone with its page (and aplay with it: nothing holds the sound card)", gone and b.proc is None
      and log_lines() == mark)
check("...the bank you were on is kept for next time", m.setting("board_bank") == "Drums")
m.press("a")
spin(3, lambda: len(b.ready) == 24 and b.sound_ok)
check("opened again: its player again, the bank you were on", m.board_shown() and len(players()) == 1
      and players() != [pid] and m.sim_game().bank == (1, 3, "Drums"))

# your own sounds: a file put in the folder
tone(S + "/laugh.wav", 0.6)
shutil.copy(S + "/laugh.wav", HOME + "/Soundboard/Laugh.wav")
t0 = time.monotonic()
spin(3, lambda: "Laugh.wav" in b.ready)
took = time.monotonic() - t0
s = m.sim_game()
check(f"a file put in your Soundboard folder: on a button {took:.1f} s later, nothing started again (the same player): "
      f"My sounds' first ({s.bank}, {s.pads}), shown and said ({toasts[-1:]})",
      took < 2.5 and players() != [] and s.bank == (3, 4, "My sounds") and s.pads == {"up": ("Laugh", "ready")}
      and toasts[-1:] == ["Laugh is on Up in My sounds"])
filed = open(S + "/static/soundboard.txt").read()
check("...and written to the banks' file, yours, with the starter pack's banks as they are",
      "[My sounds]\nup = Laugh.wav\n" in filed and "[Drums]\nup = Starter/Hi-hat.wav\n" in filed
      and os.stat(S + "/static/soundboard.txt").st_uid == os.stat(HOME).st_uid)
m.press("up")
check("...its button plays it", spin(1.0, lambda: "Laugh.wav" in b.playing))
spin(1.5, lambda: not b.playing)
for k, name in enumerate(("One.wav", "Two.wav")):
    shutil.copy(S + "/laugh.wav", f"{HOME}/Soundboard/{name}")
    os.utime(f"{HOME}/Soundboard/{name}", (time.time() + k, time.time() + k))
spin(3, lambda: "Two.wav" in b.ready)
check(f"two more: on the next free buttons, in the order they came ({m.sim_game().pads})",
      m.sim_game().pads == {"up": ("Laugh", "ready"), "left": ("One", "ready"), "right": ("Two", "ready")})
tone(HOME + "/Soundboard/One.wav", 1.5)
spin(8, lambda: b.ready.get("One.wav") == 1.5)
check(f"one changed where it is (the same name, another sound): read again ({b.ready.get('One.wav')} s)",
      b.ready.get("One.wav") == 1.5)
open(HOME + "/Soundboard/Broken.mp3", "w").write("not a sound at all\n" * 30)
spin(4, lambda: "Broken.mp3" in b.bad)
page = flush()
n_toasts = len(toasts)
m.press("down")
spin(0.3)
check(f"one that can't be played: on its button all the same, marked ({m.sim_game().pads.get('down')}), and pressed, "
      f"it says why ({toasts[n_toasts:]}) and nothing plays", m.sim_game().pads.get("down") == ("Broken", "bad")
      and len(toasts) == n_toasts + 1 and toasts[-1].startswith("Broken can't be played") and not b.playing)
os.remove(HOME + "/Soundboard/Broken.mp3")
os.remove(HOME + "/Soundboard/Two.wav")
spin(3, lambda: "right" not in m.sim_game().pads)
check(f"files taken out of the folder: off their buttons ({m.sim_game().pads}), the rest where they were",
      m.sim_game().pads == {"up": ("Laugh", "ready"), "left": ("One", "ready")})
# the web page changes the file (as webui.py does), and says so
text = open(S + "/static/soundboard.txt").read().replace("[My sounds]\nup = Laugh.wav\nleft = One.wav",
                                                           "[My sounds]\nb = Laugh.wav\n[Party]\nx = One.wav")
tmp = S + "/static/.soundboard.txt.part"
open(tmp, "w").write(text)
os.replace(tmp, S + "/static/soundboard.txt")
t0 = time.monotonic()
said = m.web_command({"cmd": "soundboard", "changed": True})
spin(0.2, lambda: m.sim_game().pads == {"b": ("Laugh", "ready")})
check(f"the web page's Soundboard moves a sound, adds a bank, and says so: here at once "
      f"({(time.monotonic() - t0) * 1000:.0f} ms; {m.sim_game().pads}, {[x['name'] for x in b.banks]}), the bank on "
      f"the page still the one you're on ({said})", m.sim_game().pads == {"b": ("Laugh", "ready")}
      and [x["name"] for x in b.banks][-2:] == ["My sounds", "Party"] and m.sim_game().bank == (3, 5, "My sounds")
      and said == {"ok": True, "open": True} and time.monotonic() - t0 < 0.25)
text = open(S + "/static/soundboard.txt").read().replace("[Party]\nx = One.wav", "[Party]\ny = One.wav")
open(tmp, "w").write(text)
os.replace(tmp, S + "/static/soundboard.txt")
m.press("r")
check("...and without its saying so (the file edited by hand): within a second or so",
      spin(2.5, lambda: m.sim_game().pads == {"y": ("One", "ready")}))
m.press("y")
check("...its sounds play from where they are now", spin(1.0, lambda: "One.wav" in b.playing))
m.press("select")
spin(0.5, lambda: not b.playing)

# something else has the sound card; the Bot talks
open(BUSY, "w").close()
m.board_tell(do="device", device="plughw:CARD=Other")
b.device = "plughw:CARD=Other"
spin(3, lambda: b.sound_ok is False)
n_toasts = len(toasts)
m.press("y")
spin(0.3)
page = flush()
check(f"something else has the sound card: the page says so quietly ({m.sim_game().trouble!r}), and a button pressed "
      f"says why there's no sound ({toasts[n_toasts:]})", b.sound_ok is False
      and m.sim_game().trouble == "No sound: something else has it" and toasts[n_toasts:] == ["No sound: something else has it"])
os.remove(BUSY)
check("...free again: it plays again, by itself", spin(6, lambda: b.sound_ok is True) and m.sim_game().trouble == ""
      and (m.press("y"), spin(1.0, lambda: "One.wav" in b.playing))[1])
m.press("select")
spin(3, lambda: b.device == "" or True)                # (back where Settings > Sound says, at its next look)
spin(3, lambda: b.device != "plughw:CARD=Other" and b.sound_ok is True)
m.voice.speaking = True
spin(0.6)
mark = log_lines()
spin(0.4)
check("the Bot talking: the sound card's its, meanwhile (let go of here)", b.rested and log_lines() == mark)
m.voice.speaking = False
check("...done: taken up again", spin(3, lambda: not b.rested and b.sound_ok is True and log_lines() > mark))
os.kill(b.proc.pid, signal.SIGKILL)
old = b.proc.pid
check("its player stopped by something else: started again, its sounds ready again",
      spin(6, lambda: b.proc is not None and b.proc.pid != old and "One.wav" in b.ready and b.sound_ok))
old = b.proc.pid
os.kill(old, signal.SIGSTOP)                           # (a player that takes nothing in: stuck)
t0 = time.monotonic()
lot = [["x" * 150 + str(k), "/nowhere/" + "y" * 150] for k in range(300)]
for k in range(8):
    m.board_tell(do="load", sounds=lot)
took = time.monotonic() - t0
back = spin(8, lambda: b.proc is not None and b.proc.pid != old and "One.wav" in b.ready and b.sound_ok)
check(f"one that's stuck, and told a great deal: media mode doesn't wait on it ({took * 1000:.0f} ms for all of that), "
      f"stops it, and starts another", took < 0.5 and back and old not in players())
told = []
real_tell = m.board_tell
m.board_tell = lambda **what: (told.append(what), real_tell(**what))[1]
was_ready = b.ready.pop("One.wav")
m.press("y")
spin(0.2)
b.ready["One.wav"] = was_ready
check(f"a button whose sound isn't read yet (its name still dim): nothing asked for, so nothing's played late "
      f"({told})", not any(t.get("do") == "play" for t in told))
m.board_tell = real_tell

# a wide screen
FB.w, FB.h, FB.real_w, FB.real_h = 960, 540, 960, 540
m.fb = FB()
m.forget_drawn()                                       # (the menus are another size now)
page = flush()
s = m.sim_game()
wide = {pad: (x, 78 + y, x + w, 78 + y + h) for pad, (x, y, w, h) in s.boxes().items()}
check(f"a bigger screen: its tiles bigger, still all on it between the bars ({wide['up'][2] - wide['up'][0]} by "
      f"{wide['up'][3] - wide['up'][1]})", all(0 <= x0 < x1 <= 960 and 118 <= y0 < y1 <= 492 for x0, y0, x1, y1 in wide.values())
      and wide["up"][2] - wide["up"][0] > 200 and page.shape[:2] == (540, 960))
FB.w, FB.h, FB.real_w, FB.real_h = 640, 480, 640, 480
m.fb = FB()
m.forget_drawn()
plain = flush()
FB.s = 2                                               # (a screen with pixels for it, a 4K TV: drawn twice as finely)
m.fine_scale()
fine = flush()
pic = FB.last
card_ok = (m.press("start"), flush(), m.press("a"))[1].shape == plain.shape
check(f"drawn finely (twice the pixels each way: {getattr(getattr(pic, 'pic', pic), 'size', None)}), it's the same page "
      f"(its usual-size copy {np.abs(fine - plain).mean():.2f} levels from the plain one, on average), START's card too",
      FINE.detail(pic) == 2 and pic.pic.size == (1280, 960) and np.abs(fine - plain).mean() < 3.0 and card_ok)
FB.s = 1
m.fine_scale()
flush()

# ---- a microphone: a sound recorded, and put on a button --------------------------------------------------------------
m.press("l")                                           # (My sounds)
m.press("start")
check("still no Record a sound on START's card", [r[0] for r in m.board_rows()] == ["bank", "volume"])
os.makedirs(A + "/card1/pcm0c")
open(A + "/card1/usbid", "w").write("0c76:161f\n")
open(A + "/cards", "w").write(HDMI + MIC)
spin(3.5, lambda: b.mic is not None)
check(f"a USB microphone plugged in: Record a sound is there ({[r[1] for r in m.board_rows()]}, {b.mic})",
      [r[0] for r in m.board_rows()] == ["bank", "volume", "rec"] and b.mic == "plughw:CARD=Device,DEV=0")
shutil.rmtree(A + "/card1")
open(A + "/cards", "w").write(HDMI)
spin(3.5, lambda: b.mic is None)
check("...taken out: gone again, with nothing said", [r[0] for r in m.board_rows()] == ["bank", "volume"])
os.makedirs(A + "/card1/pcm0c")
open(A + "/card1/usbid", "w").write("0c76:161f\n")
open(A + "/cards", "w").write(HDMI + MIC)
spin(3.5, lambda: b.mic is not None)
m.press("down"); m.press("down")
check(f"...its row: {m.sim_hints(m.sim_game())}", m.sim_hints(m.sim_game())
      == [("▲▼", "Choose"), ("A", "Record"), ("START", "Done"), ("B", "Back to Apps")])
stopped = []
m.ears.stop = lambda: stopped.append("stop")
m.ears.want = ("hey potato", "")                       # (the Bot's listening, with that microphone)
listened = []
m.listen_now = lambda quiet=False: listened.append(quiet)
open(RLOG, "w").close()
m.press("a")
spin(1.0, lambda: b.rec is not None and b.rec["secs"] > 0.3)
page = flush()
s = m.sim_game()
check(f"A: recording, with that microphone ({open(RLOG).read().strip()[-30:]}); the Bot stops listening meanwhile "
      f"({stopped}); the page says so, how long and how loud ({s.rec}); its buttons {m.sim_hints(s)}",
      b.rec is not None and open(RLOG).read().strip().endswith("-D plughw:CARD=Device,DEV=0") and stopped == ["stop"]
      and s.rec is not None and s.rec[0] > 0.3 and m.sim_hints(s) == [("A", "Keep it"), ("B", "Cancel")]
      and m.sim_opts is None and near(page, (148, 190, 492, 320), g.ROW, 4) > 20000)
m.press("up"); m.press("start"); m.press("l")
spin(1.6)
check("...the other buttons wait", b.rec is not None and not b.playing and m.sim_game().bank[2] == "My sounds")
m.press("a")
spin(5, lambda: b.rec is None and b.placing is not None and "Recording 1.wav" in b.ready)
rec1 = HOME + "/Soundboard/Recording 1.wav"
shape = wav_of(rec1) if os.path.isfile(rec1) else (0,)
s = m.sim_game()
check(f"A: kept, its silence trimmed ({shape[0]:.2f} s, of three and a half recorded round a second of sound), a "
      f"file in your Soundboard folder; the Bot listens again ({listened})",
      1.1 < shape[0] < 1.3 and listened[-1:] == [True] and b.placing == "Recording 1.wav")
check(f"...on My sounds' next free button meanwhile, like any new sound ({s.pads}), and the page asks for the button "
      f"it's to go on ({s.placing}; {m.sim_hints(s)})", s.pads.get("up") == ("Recording 1", "ready") and s.placing == ("Recording 1", "up")
      and m.sim_hints(s) == [("L R", "Bank"), ("SELECT", "Hear it"), ("START", "More")])
m.press("select")
check("...SELECT: heard first", spin(1.5, lambda: "Recording 1.wav" in b.playing))
spin(2, lambda: not b.playing)
m.press("l"); m.press("l"); m.press("l")               # (My sounds, Arcade, Drums, Starter)
check("...L and R: another bank", m.sim_game().bank[2] == "Starter" and b.placing == "Recording 1.wav")
n_toasts = len(toasts)
m.press("a")
spin(0.5)
s = m.sim_game()
filed = open(S + "/static/soundboard.txt").read()
check(f"...the button pressed is the one it goes on ({s.pads['a']}; {toasts[n_toasts:]}); what was there is where it "
      f"was (nothing's lost: {B.where(b.banks, sid('Ding'))}); written to the banks' file",
      s.pads["a"] == ("Recording 1", "ready") and toasts[n_toasts:] == ["Recording 1 is on A in Starter"]
      and b.placing is None and B.where(b.banks, sid("Ding")) == (3, "up") and "a = Recording 1.wav" in filed
      and "[My sounds]\nup = Starter/Ding.wav\nb = Laugh.wav" in filed)
m.press("a")
check("...and plays there, now", spin(1.5, lambda: "Recording 1.wav" in b.playing) and not b.placing)
m.press("select")
spin(1, lambda: not b.playing)
m.press("start"); m.press("down"); m.press("down"); m.press("a")
spin(2.2, lambda: False)
m.press("b")
spin(2, lambda: b.rec is None)
check("another, and B instead of A: dropped, nothing kept, no button asked for",
      b.rec is None and b.placing is None and sorted(os.listdir(HOME + "/Soundboard")) == ["Laugh.wav", "One.wav", "Recording 1.wav"])
open(AREC, "w").write("silent")
m.press("start"); m.press("down"); m.press("down"); m.press("a")
spin(1.0)
n_toasts = len(toasts)
m.press("a")
spin(3, lambda: b.rec is None)
check(f"a quiet room: nothing kept, and it says nothing was heard ({toasts[n_toasts:]})",
      toasts[n_toasts:] == ["Nothing was heard"] and b.placing is None and len(os.listdir(HOME + "/Soundboard")) == 3)
os.remove(AREC)
m.press("start"); m.press("down"); m.press("down"); m.press("a")
spin(2.0)
m.press("a")
spin(4, lambda: b.placing is not None)
m.press("start")
rows = m.board_rows()
check(f"another kept; START instead of a button: its card ({[r[1] for r in rows]}; {m.sim_hints(m.sim_game())})",
      b.placing == "Recording 2.wav" and [r[0] for r in rows] == ["stay", "again", "delete"]
      and rows[0][1] == "Leave it on Left in My sounds"
      and m.sim_hints(m.sim_game()) == [("▲▼", "Choose"), ("A", "OK"), ("SELECT", "Hear it"), ("B", "Not now")])
flush()
m.press("b")
check("...B: back to the buttons, still to be put on one", m.sim_opts is None and b.placing == "Recording 2.wav")
m.press("start"); m.press("down"); m.press("down")
n_toasts = len(toasts)
m.press("a")
spin(0.5)
check(f"...Delete it: gone, from the folder and its button ({toasts[n_toasts:]})",
      not os.path.exists(HOME + "/Soundboard/Recording 2.wav") and b.placing is None and toasts[n_toasts:] == ["Deleted"]
      and B.where(b.banks, "Recording 2.wav") is None and m.sim_opts is None)
m.press("start"); m.press("down"); m.press("down"); m.press("a")
spin(2.0)
m.press("a")
spin(4, lambda: b.placing is not None)
m.press("start"); m.press("down"); m.press("a")
spin(1.0, lambda: b.rec is not None)
check("...Record it again: that one gone, and recording", b.rec is not None and b.placing is None
      and not os.path.exists(HOME + "/Soundboard/Recording 2.wav"))
spin(1.9)
m.press("a")
spin(4, lambda: b.placing is not None)
m.press("start"); m.press("a")
check(f"...Leave it where it is: there it stays ({B.where(b.banks, 'Recording 2.wav')})", b.placing is None
      and m.sim_opts is None and B.where(b.banks, "Recording 2.wav") == (3, "left"))
open(AREC, "w").write("busy")
m.press("start"); m.press("down"); m.press("down")
n_toasts = len(toasts)
m.press("a")
spin(3, lambda: len(toasts) > n_toasts)
check(f"a microphone that won't open: said, and nothing more ({toasts[n_toasts:]})",
      toasts[n_toasts:] == ["The microphone didn't answer"] and b.rec is None and b.placing is None)
os.remove(AREC)
m.press("start"); m.press("down"); m.press("down"); m.press("a")
spin(0.8, lambda: b.rec is not None)
m.go_home()
spin(0.5)
check("leaving in the middle of a recording (HOME): dropped, its player gone, the Bot listening again",
      until(lambda: players() == [], 4) and b.rec is None and b.proc is None and listened[-1] is True
      and sorted(os.listdir(HOME + "/Soundboard")) == ["Laugh.wav", "One.wav", "Recording 1.wav", "Recording 2.wav"])
m.leave()

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
