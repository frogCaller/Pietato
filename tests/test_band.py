"""The Band, in Apps (pitato/band.py, bandplay.py, bandstage.py, screens/band.py): your Pietatos play together, each
its own instrument, and you play along. First the music itself: every song's parts are whole bars, a bar of a part
plays only notes of its chord or of the song's five (so it's in key), each level's busier than the one before, and
two Pietatos work out the very same bars, the same shape of the song and the same throw of the dice from the song and
its seed alone. Then its player on its own, against a pretend sound card (aplay here reads a period, waits for room in
the card's buffer and writes it, as the real one does, and keeps every sample with when the card started): the
instruments' notes are made at their right pitch, and kept; a note told for a moment is heard at that moment, to a
millisecond or two, on a card that keeps time, one that runs fast or slow, and with a longer buffer; one told too
late is left out; a sound in a lane ends the one before it there; one player's sound can be taken out and the others'
left; and it never clips. Then the app in media mode, on its own: in Apps, its page, SELECT counts a bar in and the
whole band plays in time, the chord and the buttons going with the bar; your buttons play your instrument at once and
it's yours while you do (the Pietato's own part on it stops, and comes back); L and R pick it; START's card (the
song, the tempo: on from where it was, the volume; B there goes back, and its player's gone). Who decides: a decision
model on your bot's computer (a stand-in here) is asked for each player's next four bars, and what it picks is played;
one that answers late, or not at all, isn't waited for (the dice's pick stands). In another's band: asked in by one of
your others (not by anyone else), this one opens its page, sets its clock against the other's, takes the plan and its
instrument, plays in step with a clock five seconds from its own, says what it's doing, and goes back where it was
when the band's over; in a game, it isn't asked in; START's card there has Timing (this one's sound a little earlier
or later than the others': a TV's slow with it), and its next bars are played that much early. Last, two Pietatos
for real: this one and another in a process of its own, each with a sound card of its own; opened here, the other
joins and takes an instrument, both play in step, its own buttons change its instrument and stop the band for both,
and leaving here sends it home."""
import json, os, shutil, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import numpy as np
import pietato_all as g
import pitato.band as B
import pitato.soundbank as SB
import pitato.screens.band as BS
import pitato.bandstage as STAGE
import pitato.listen as L

S = SP + "/t_band"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
for d in (HOME, S + "/bin", S + "/static", S + "/out"):
    os.makedirs(d)
ok_all = []
RATE = 48000
PLAYER = ROOT + "/pitato/bandplay.py"
DRUMS = SB.starter_dir()


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


# ---- the music ------------------------------------------------------------------------------------------------------
def pcs(name):
    return set(B.chord(name)[2])


def midi_of(sid):
    return int(sid[1:]) if sid[1:].isdigit() else None


whole = all(len(line) == B.STEPS for parts in B.PARTS.values() for seat, levels in parts.items() for lv in levels
            for line in (lv if isinstance(lv, tuple) else (lv,)))
check(f"the songs ({[s['name'] for s in B.SONGS]}): each a tempo, a feel that has its parts, and chords in fours of "
      f"bars; every part sixteen steps to the bar", whole and len(B.SONGS) >= 4
      and all(len(s["chart"]) % B.SECTION == 0 and s["feel"] in B.PARTS and B.BPM[0] <= s["bpm"] <= B.BPM[1]
              and set(B.PARTS[s["feel"]]) == set(B.SEATS) for s in B.SONGS))
bad, roots, busier, loaded = [], [], [], []
for s in B.SONGS:
    names = dict(B.sounds(s, B.SEATS, None, DRUMS))
    five = {(B.NOTES.index(s["home"][0]) + i) % 12 for i in B.SCALES[s["home"][1]]}
    chart = s["chart"]
    for seat in B.SEATS:
        counts = []
        for level in (1, 2, 3):
            n_notes = 0
            for n in range(len(chart)):
                now, then = chart[n], chart[(n + 1) % len(chart)]
                evs = B.bar(s, seat, n, level, seed=3)
                n_notes += len(evs)
                for at, sid, gain, lane, long in evs:
                    loaded.append(sid in names and 0 <= at < B.BEATS and 0 < gain <= 1.2)
                    mid = midi_of(sid)
                    if seat == "bass":
                        lead = (B.chord(then)[0] - 1) % 12
                        ok = mid % 12 in pcs(now) | {(B.chord(now)[0] + 9) % 12, (B.chord(now)[0] + 10) % 12, lead}
                        if at == 0:
                            roots.append(mid % 12 == B.chord(now)[0])
                    elif seat in ("guitar", "keys") and mid is not None:
                        ok = mid % 12 in pcs(now)
                    elif seat in ("guitar", "keys"):   # (a chord: made of its notes, and nothing else)
                        ok = {int(x) % 12 for x in names[sid].split(":")[2].split("+")} <= pcs(now)
                    else:
                        ok = sid in B.DRUM_FILES
                    if not ok:
                        bad.append((s["name"], seat, level, n, sid))
            counts.append(n_notes)
        busier.append(counts[0] <= counts[1] <= counts[2] and counts[0] < counts[2])
        if seat in ("guitar", "keys"):                 # a solo: the song's five notes, a chord's on the strong beats
            for n in range(len(chart) * 2):
                for at, sid, gain, lane, long in B.bar(s, seat, n, 2, solo=True, seed=n // 4):
                    loaded.append(sid in names)
                    if midi_of(sid) % 12 not in five or (at in (0.0, 2.0) and five & pcs(chart[n % len(chart)])
                                                         and midi_of(sid) % 12 not in pcs(chart[n % len(chart)])):
                        bad.append((s["name"], seat, "solo", n, sid))
check(f"every bar of every part, at every level: only its chord's notes (the bass: those, its sixth and seventh, and "
      f"the note that leads to the next chord; a solo: the song's five, the chord's own on the strong beats); the bass "
      f"on the chord's root as each bar starts ({bad[:3]})", not bad and all(roots) and len(roots) >= 60)
check("...each level busier than the one before, and every sound a part plays is one its player's told of",
      all(busier) and all(loaded) and len(loaded) > 2000)
rock, blues = B.song("rock"), B.song("blues")
check(f"a shuffle (the Blues): the notes between the beats come late, two thirds of the way "
      f"({B.step_at(2, 1.0):.3f}); evenly otherwise ({B.step_at(2, 0.0)})", abs(B.step_at(2, 1.0) - 2 / 3) < 1e-9
      and B.step_at(2, 0.0) == 0.5 and B.step_at(6, 0.0) == 1.5 and B.step_at(16, 0.0) == 4.0
      and any(abs(at % 1 - 2 / 3) < 1e-6 for at, *_ in B.bar(blues, "drums", 0, 2)))
same = all(B.bar(s, seat, n, lv, seed=sd) == B.bar(s, seat, n, lv, seed=sd) and B.form(sd, n) == B.form(sd, n)
           and B.dice(sd, seat, n) == B.dice(sd, seat, n) and B.bar(s, "keys", n, 2, solo=True, seed=sd)
           == B.bar(s, "keys", n, 2, solo=True, seed=sd)
           for s in B.SONGS for seat in B.SEATS for n in range(8) for lv in (1, 3) for sd in (0, 7))
out = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); import pitato.band as B; "
                      "print(([B.dice(7, s, n) for s in B.SEATS for n in range(6)], B.bar(B.song('funk'), 'keys', 5, 2, "
                      "solo=True, seed=7), B.form(7, 9)))", ROOT], capture_output=True, text=True).stdout.strip()
here = str(([B.dice(7, s, n) for s in B.SEATS for n in range(6)], B.bar(B.song("funk"), "keys", 5, 2, solo=True, seed=7),
            B.form(7, 9)))
check("two Pietatos work out the same bars, the same shape of the song and the same throw of the dice, from the song "
      "and its seed alone (another process has them the same)", same and out == here)
shape = [B.form(0, k) for k in range(40)]
check(f"the song's shape: it starts small ({shape[0]}), everyone's in before long, the guitar and the keys each have "
      f"a solo, never both at once, and it goes round", sum(1 for v in shape[0].values() if v) <= 2
      and all(shape[4].values()) and any(r["keys"] == "solo" for r in shape) and any(r["guitar"] == "solo" for r in shape)
      and not any(r["keys"] == "solo" and r["guitar"] == "solo" for r in shape) and shape[16] == shape[2]
      and B.form(1, 6)["guitar"] == B.form(0, 6)["keys"])
check("what a player does with it: as it is, busier, simpler, sitting out, a fill, a solo",
      B.played(2, "follow") == (2, False, False) and B.played(2, "lift") == (3, False, False)
      and B.played(3, "lift")[0] == 3 and B.played(2, "ease") == (1, False, False) and B.played(1, "ease")[0] == 1
      and B.played(3, "rest") == (0, False, False) and B.played(2, "fill") == (2, False, True)
      and B.played("solo", "follow") == (2, True, False) and B.played("solo", "ease") == (1, False, False)
      and B.played(1, "solo")[1] and B.played(0, "follow")[0] == 0)
fills = [n for n in range(8) if any(e[1] == "tom" for e in B.bar(rock, "drums", n, 2, fill=True, seed=1))]
check("the drums' fill is the bar's last two beats; a crash starts the bar after",
      all(e[0] >= 2 for n in range(4) for e in B.bar(rock, "drums", n, 2, fill=True, seed=n) if e[1] == "tom") and fills
      and B.bar(rock, "drums", 0, 2, crash=True)[0][1] == "crash"
      and B.bar(rock, "drums", 0, 2, fill=True)[:6] == B.bar(rock, "drums", 0, 2)[:6])
throws = [B.dice(5, seat, n) for seat in B.SEATS for n in range(60)]
check("the dice: the song's own part mostly, a fill from the drums often, and the guitar and the keys simpler while "
      "another solos or a person plays one of them", throws.count("follow") > 100 and "lift" in throws
      and "fill" in [B.dice(5, "drums", n) for n in range(20)] and "fill" not in [B.dice(5, "bass", n) for n in range(60)]
      and B.dice(5, "guitar", 3, {"keys": "solo"}) == "ease" and B.dice(5, "keys", 3, {}, "guitar") == "ease"
      and all(t in B.SEAT_CHOICES[seat] for seat in B.SEATS for t in [B.dice(5, seat, n) for n in range(40)]))
state, says, choices = B.ask(B.song("funk"), 102, "keys", 5, 0, ("follow", 2), {"drums": "fill", "guitar": "solo"}, ("bass", 2))
check(f"what a decision model's asked: the song, what it has this player and the others do next, what they're doing "
      f"now, a person playing along; its choices, each with what it means ({list(choices)})",
      state["song"] == "Funk" and state["tempo"] == 102 and "the_song_has_you" in state
      and state["the_others_now"] == {"Drums": B.CHOICES["fill"], "Guitar": B.CHOICES["solo"]}
      and state["a_person_is_playing"] == {"instrument": "Bass", "how_busily_1_to_3": 2}
      and list(choices) == list(B.SEAT_CHOICES["keys"]) and "keys" in says and "solo" not in B.SEAT_CHOICES["drums"]
      and json.dumps(state))
pad_ok = []
for s in B.SONGS:
    five = {(B.NOTES.index(s["home"][0]) + i) % 12 for i in B.SCALES[s["home"][1]]}
    for seat in B.SEATS:
        mine = dict(B.sounds(s, (), seat, DRUMS))
        for name in s["chart"]:
            p = B.pads(s, seat, name)
            pad_ok.append(sorted(p) == sorted(B.PADS) and all(v[1] in mine for v in p.values()))
            if seat != "drums":
                pad_ok.append(all(midi_of(p[k][1]) % 12 in five for k in ("down", "left", "right", "up"))
                              and midi_of(p["down"][1]) < midi_of(p["left"][1]) < midi_of(p["right"][1])
                              < midi_of(p["up"][1]))
            if seat == "bass":
                pad_ok.append(midi_of(p["a"][1]) % 12 == B.chord(name)[0] and all(midi_of(p[k][1]) % 12 in pcs(name)
                                                                               for k in "abxy"))
check("your buttons: on the drums, one each; on the others, A, B, X and Y go with the bar's chord (the bass: its "
      "root on A) and the d-pad's four are notes of the song's own, low to high (down, left, right, up)", all(pad_ok))

# ---- a pretend aplay, as the real one works a sound card --------------------------------------------------------------
# It reads a period from its pipe, then waits till the card's buffer has room for it (the card plays at its own steady
# rate: FAKE_SPEED times as fast as it should), and writes it there. The card starts playing once its buffer's full.
# Every sample is kept (FAKE_PCM), with when the card started and from which frame (FAKE_LOG): so when any sample was
# heard is start + (its frame - that frame) / rate. FAKE_BREAKS: it says the sound ran dry this many times (on its
# shortest buffer). FAKE_GRANTS: the buffer and period the card gives it, whatever was asked (a card shared between
# programs has its own); asked what it was given (-v), it says, as the real one does.
open(S + "/bin/aplay", "w").write('''#!/usr/bin/env python3
import os, sys, time
args = sys.argv[1:]
rate = int(args[args.index("-r") + 1]) if "-r" in args else 48000
buf = next((int(a.split("=")[1]) for a in args if a.startswith("--buffer-time=")), 100000)
per = next((int(a.split("=")[1]) for a in args if a.startswith("--period-time=")), 20000)
speed = float(os.environ.get("FAKE_SPEED") or 1.0)
pf, bf = per * rate // 1000000, buf * rate // 1000000
if os.environ.get("FAKE_GRANTS"):
    bf, pf = (int(v) for v in os.environ["FAKE_GRANTS"].split(","))
if "-v" in args:
    sys.stderr.write("Plug PCM: Hardware PCM card 0 'pretend' device 0 subdevice 0\\nIts setup is:\\n"
                     f"  stream       : PLAYBACK\\n  rate         : {rate}\\n  buffer_size  : {bf}\\n"
                     f"  period_size  : {pf}\\n  period_time  : {pf * 1000000 // rate}\\n  avail_min    : {pf}\\n")
    sys.stderr.flush()
log = open(os.environ["FAKE_LOG"], "a", buffering=1)
pcm = open(os.environ["FAKE_PCM"], "ab", buffering=0)
base = os.path.getsize(os.environ["FAKE_PCM"]) // 4
log.write(f"open {time.monotonic():.6f} {bf} {pf} {base} {' '.join(args)}\\n")
breaks = int(os.environ.get("FAKE_BREAKS") or 0) if buf <= 32000 else 0
written, start, offset = 0, None, 0
def played(now):
    return offset if start is None else offset + int((now - start) * rate * speed)
def whole(n):
    out = b""
    while len(out) < n:
        d = os.read(0, n - len(out))
        if not d:
            return None
        out += d
    return out
while True:
    data = whole(pf * 4)
    if data is None:
        break
    while True:
        now = time.monotonic()
        if start is not None and played(now) >= written:
            sys.stderr.write("underrun!!! (at least 1.000 ms long)\\n"); sys.stderr.flush()
            log.write(f"underrun {now:.6f}\\n")
            start, offset = None, written
        if written - played(now) + pf <= bf:
            break
        time.sleep(0.0002)
    pcm.write(data)
    written += pf
    if start is None and written - offset >= bf:
        start = time.monotonic()
        log.write(f"start {start:.6f} {base + offset}\\n")
    if breaks and written > rate // 4:
        breaks -= 1
        sys.stderr.write("underrun!!! (at least 12.000 ms long)\\n"); sys.stderr.flush()
        time.sleep(0.05)
''')
os.chmod(S + "/bin/aplay", 0o755)
os.environ["PATH"] = S + "/bin:" + os.environ["PATH"]


class Card:
    """A pretend sound card's record: what it was given, and when it was heard."""

    def __init__(self, name, speed=1.0):
        self.log, self.pcm, self.speed = f"{S}/out/{name}.log", f"{S}/out/{name}.pcm", speed
        for f in (self.log, self.pcm):
            open(f, "w").close()

    def env(self, **more):
        return dict(os.environ, FAKE_LOG=self.log, FAKE_PCM=self.pcm, FAKE_SPEED=str(self.speed), **more)

    def lines(self, kind):
        return [ln.split() for ln in open(self.log) if ln.startswith(kind)]

    def frames(self):
        raw = np.fromfile(self.pcm, dtype="<i2")
        return raw[:len(raw) - len(raw) % 2].reshape(-1, 2)

    def when(self, frame):
        """When a frame of what it was given was heard."""
        starts = [(float(a), int(b)) for _, a, b in (x[:3] for x in self.lines("start")) if int(b) <= frame]
        t, off = starts[-1]
        return t + (frame - off) / (RATE * self.speed)

    def frame_at(self, t):
        """The frame heard at a time."""
        starts = [(float(a), int(b)) for _, a, b in (x[:3] for x in self.lines("start")) if float(a) <= t]
        t0, off = starts[-1]
        return off + int(round((t - t0) * RATE * self.speed))

    def onsets(self, thr=600, quiet=0.03, since=0):
        """The frames where a sound starts after silence."""
        x = np.abs(self.frames()[since:, 0].astype(np.int32))
        loud = np.nonzero(x > thr)[0]
        if not len(loud):
            return []
        gaps = np.nonzero(np.diff(loud) > quiet * RATE)[0]
        return [since + int(loud[0])] + [since + int(loud[i + 1]) for i in gaps]

    def out_ms(self, times, **how):
        """How far from each of those times a sound was heard to start (ms), in order."""
        return [(self.when(f) - t) * 1000 for f, t in zip(self.onsets(**how), times)]

    def loud(self, t0, t1):
        """How loud it was between two times (its RMS, of 32768)."""
        x = self.frames()[self.frame_at(t0):self.frame_at(t1), 0].astype(np.float64)
        return float(np.sqrt((x ** 2).mean())) if len(x) else 0.0


class Player:
    def __init__(self, card, cache=S + "/cache", **env):
        self.card = card
        self.p = subprocess.Popen([sys.executable, "-I", PLAYER, cache], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  env=card.env(**env), bufsize=0)
        self.said = []
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        for line in self.p.stdout:
            try:
                self.said.append(json.loads(line))
            except ValueError:
                pass

    def tell(self, **what):
        self.p.stdin.write((json.dumps(what) + "\n").encode())

    def got(self, kind):
        return [x for x in list(self.said) if x.get("is") == kind]

    def load(self, sounds, secs=60):
        """Told its sounds: True once it's said of each that it's ready, or that it can't be made."""
        names = {s[0] for s in sounds}
        self.tell(do="load", sounds=[list(s) for s in sounds])
        return until(lambda: names <= {x.get("id") for x in list(self.said) if x.get("is") in ("ready", "bad")}, secs)

    def stats(self):
        n = len(self.got("stats"))
        self.tell(do="stats")
        until(lambda: len(self.got("stats")) > n, 2)
        return self.got("stats")[-1]

    def quit(self):
        try:
            self.tell(do="quit")
        except OSError:
            pass
        return self.p.wait(5)


def close(errs, most=3.0, nearly=8.0):
    """Sounds heard when they were meant: about on it as a rule, and none far out (a busy machine may hold one up)."""
    errs = sorted(abs(e) for e in errs)
    return bool(errs) and errs[len(errs) // 2] <= most / 2 and errs[int(len(errs) * 0.8)] <= most and errs[-1] <= nearly


# ---- its player, on its own -----------------------------------------------------------------------------------------
everything = B.sounds(rock, B.SEATS, "keys", DRUMS)
card = Card("a")
p = Player(card)
t = time.monotonic()
ok = p.load(everything)
first = time.monotonic() - t
kept = sorted(os.listdir(S + "/cache"))
check(f"its player makes a song's sounds the first time it's told of them ({len(p.got('ready'))} of {len(everything)}: "
      f"the drums' from the starter pack, the rest from sums, {first:.1f} s here), and keeps each note it made "
      f"({len(kept)} of them)", ok and len(p.got("ready")) == len(everything) and not p.got("bad")
      and len(kept) > 30 and all(n.endswith(".wav") and n.split("-")[0] in ("bass", "guitar", "keys") for n in kept))
pitch = []
for n in ("bass-33", "guitar-57", "keys-69", "keys-81"):
    fn = next(x for x in kept if x.startswith(n + "-"))
    rate, x = SB.read_wav(S + "/cache/" + fn)
    x = x[:, 0].astype(np.float64)
    spec = np.abs(np.fft.rfft(x[:RATE] * np.hanning(RATE)))
    want = 440.0 * 2 ** ((int(n.split("-")[1]) - 69) / 12)
    lo, hi = int(want * 0.5), int(want * 8)
    top = (lo + int(np.argmax(spec[lo:hi]))) * rate / RATE
    ratio = top / want
    pitch.append((n, round(top, 1), rate == RATE and abs(ratio - round(ratio)) < 0.03 and 1 <= round(ratio) <= 3
                  and abs(int(x[0])) < 2000 and abs(int(x[-1])) < 300 and 20000 < np.abs(x).max() <= 32767
                  and np.abs(x[:2400]).max() > 4 * np.abs(x[-2400:]).max()))
check(f"...each at its own pitch (its loudest sine is the note's own, or one just above it: {[(n, hz) for n, hz, _ in pitch]}), "
      f"starting and ending quietly, dying away as it goes", all(ok for _, _, ok in pitch))
bad_spec = p.load([["x1", "synth:kazoo:60:1"], ["x2", "synth:bass:400:1"], ["x3", "synth:bass:40:99"], ["x4", "synth:"],
                   ["hat", DRUMS + "/Hi-hat.wav"], ["kick", DRUMS + "/Kick.wav"], ["b33", "synth:bass:33:1.4"],
                   ["b40", "synth:bass:40:1.4"]], 20)
check(f"...what it can't make, it says so ({[b['id'] for b in p.got('bad')]}), and goes on",
      bad_spec and sorted(b["id"] for b in p.got("bad")) == ["x1", "x2", "x3", "x4"])
p.tell(do="warm")
until(lambda: p.got("sound"), 5)
time.sleep(2.5)
T0 = time.monotonic() + 0.4
times = [T0 + k * 0.2 for k in range(20)]
p.tell(do="at", notes=[[t, "hat", 0.9, "hat", 0, "drums"] for t in times])
late = [time.monotonic() - 0.5, "kick", 0.9, "", 0, "drums"]
p.tell(do="at", notes=[late, [T0 + 2.0, "nothing", 0.9, "", 0, "drums"], "junk", [T0, "kick"]])
time.sleep(0.4 + 20 * 0.2 + 0.4)
st = p.stats()
errs = card.out_ms(times)
check(f"a note told for a moment is heard at that moment ({len(errs)} of them: from {min(errs):+.2f} to {max(errs):+.2f} "
      f"ms out), through a {p.got('sound')[-1].get('buffer')} ms buffer", len(errs) == 20 and close(errs)
      and p.got("sound")[-1] == {"is": "sound", "ok": True, "buffer": 32, "paced": True} and not card.lines("underrun"))
check(f"...one told too late is left out, and said so ({st}); one that isn't a sound, or isn't a note at all, is "
      f"passed over", st["late"] == 1 and st["waiting"] == 0 and st["paced"] is True and len(card.onsets()) == 20)
# lanes: a bass note ends the one before it; without a lane, they ring on together
t1 = time.monotonic() + 0.3
p.tell(do="at", notes=[[t1, "b33", 0.9, "bass", 0, "bass"], [t1 + 0.3, "b40", 0.9, "bass", 0, "bass"]])
time.sleep(1.6)
t2 = time.monotonic() + 0.3
p.tell(do="at", notes=[[t2, "b33", 0.9, "", 0, "bass"], [t2 + 0.3, "b40", 0.9, "", 0, "bass"]])
time.sleep(1.6)
t3 = time.monotonic() + 0.3
p.tell(do="at", notes=[[t3 + 0.3, "b40", 0.9, "bass", 0, "bass"]])
time.sleep(1.6)


def tone(t0, t1, hz):
    """How much of a sine of hz there was between two times."""
    x = card.frames()[card.frame_at(t0):card.frame_at(t1), 0].astype(np.float64)
    k = np.arange(len(x)) / RATE
    return abs(np.dot(x, np.exp(-2j * np.pi * hz * k))) / max(1, len(x))


low, high = 440 * 2 ** ((33 - 69) / 12), 440 * 2 ** ((40 - 69) / 12)
cut, ring, alone = tone(t1 + 0.4, t1 + 0.7, low), tone(t2 + 0.4, t2 + 0.7, low), tone(t3 + 0.4, t3 + 0.7, low)
check(f"a sound in a lane ends the one before it there: a bass note, the note before (what's left of it {cut:.0f}, "
      f"against {ring:.0f} when it rings on; a note on its own {alone:.0f})", cut < ring * 0.2 and ring > 300
      and tone(t1 + 0.4, t1 + 0.7, high) > 300 and abs(tone(t1 + 0.4, t1 + 0.7, high) - tone(t3 + 0.4, t3 + 0.7, high))
      < 0.25 * tone(t3 + 0.4, t3 + 0.7, high))
# a note cut short: it ends there
t4 = time.monotonic() + 0.3
p.tell(do="at", notes=[[t4, "b33", 0.9, "bass", 0.15, "bass"]])
time.sleep(0.9)
check(f"a note that's told how long it is ends there ({card.loud(t4 + 0.25, t4 + 0.5):.0f} after it, "
      f"{card.loud(t4 + 0.02, t4 + 0.14):.0f} in it)", card.loud(t4 + 0.25, t4 + 0.5) < 5 < card.loud(t4 + 0.02, t4 + 0.14) / 100)
# one player's sound taken out, the others' left
t5 = time.monotonic() + 0.3
p.tell(do="at", notes=[[t5, "b33", 0.9, "bass", 0, "bass"], [t5 + 1.0, "b40", 0.9, "bass", 0, "bass"]]
       + [[t5 + 0.5 + k * 0.2, "hat", 0.9, "hat", 0, "drums"] for k in range(5)])
time.sleep(0.5)
tc = time.monotonic()
p.tell(do="clear", whose="bass")
time.sleep(1.4)
hats = [f for f in card.onsets(since=card.frame_at(tc + 0.02)) if card.when(f) < t5 + 1.6]
check(f"one player's sound taken out (the bass: you've taken it over): what's playing of it ends, what was to come of "
      f"it doesn't ({tone(tc + 0.1, tc + 0.4, low):.0f}, {tone(t5 + 1.1, t5 + 1.4, high):.0f}); the others' goes on "
      f"({len(hats)} of the drums')", tone(tc + 0.1, tc + 0.4, low) < 20 and tone(t5 + 1.1, t5 + 1.4, high) < 20
      and len(hats) >= 4)
# now: your own buttons
mark = len(card.frames())
t6 = time.monotonic()
p.tell(do="play", id="kick", gain=0.9, lane="", secs=0, whose="you")
time.sleep(0.4)
on = card.onsets(since=mark)
took = (card.when(on[0]) - t6) * 1000 if on else None
check(f"a sound asked for now (your own buttons) is heard at once ({took:.0f} ms after)", on and took < 80)
# everything at once, as loud as it goes: turned down, never clipped
t7 = time.monotonic() + 0.3
p.tell(do="volume", v=100)
p.tell(do="at", notes=[[t7 + k * 0.01, sid, 1.0, "", 0, who] for k, (sid, who) in
                       enumerate([("kick", "drums"), ("b33", "bass"), ("b40", "bass"), ("kick", "you"), ("hat", "drums")] * 6)])
time.sleep(1.5)
x = card.frames()[card.frame_at(t7):card.frame_at(t7 + 1.0)].astype(np.int32)
flat = int((np.abs(x[:, 0]) >= 32767).sum())
check(f"thirty sounds at once, as loud as they go: turned down together rather than clipped (its loudest "
      f"{int(np.abs(x).max())}, {flat} samples at the top), both channels the same", 20000 < np.abs(x).max() <= 32767
      and flat < 40 and np.array_equal(x[:, 0], x[:, 1]))
p.tell(do="at", notes=[[time.monotonic() + 0.6, "kick", 0.9, "", 0, "drums"]])
p.tell(do="rest")
waiting = p.stats()["waiting"]
time.sleep(0.3)
mark = len(card.frames())
time.sleep(0.6)
check("let go of (the Bot's talking): what was to come is forgotten, and nothing more's played",
      waiting == 0 and len(card.frames()) == mark)
check(f"told to quit: it does (exit code {p.quit()})", p.p.returncode == 0)

# a second time: its notes are there already; a card that runs fast, one that runs slow, a longer buffer
cards = {"fast": Card("fast", 1.003), "slow": Card("slow", 0.996), "long": Card("long"), "own": Card("own", 1.002)}
ps = {"fast": Player(cards["fast"]), "slow": Player(cards["slow"], PITATO_SOUNDBOARD_PACED="0"),
      "long": Player(cards["long"], FAKE_BREAKS="3"), "own": Player(cards["own"], FAKE_GRANTS="2048,1024")}
t = time.monotonic()
ok = ps["fast"].load(everything, 20)
again = time.monotonic() - t
check(f"its player started again has the notes it kept ({again:.2f} s for all of them now)", ok and again < max(1.0, first))
for x in ps.values():
    x.load([["hat", DRUMS + "/Hi-hat.wav"]], 10)
    x.tell(do="warm")
until(lambda: ps["long"].got("sound") and ps["long"].got("sound")[-1].get("buffer") == 64, 8)
time.sleep(2.5)
T0 = time.monotonic() + 0.4
times = [T0 + k * 0.2 for k in range(20)]
for x in ps.values():
    x.tell(do="at", notes=[[t, "hat", 0.9, "hat", 0, "drums"] for t in times])
time.sleep(0.4 + 20 * 0.2 + 0.4)
errs = {k: cards[k].out_ms(times, since=cards[k].frame_at(T0 - 0.2)) for k in ps}
for x in ps.values():
    x.quit()
check(f"...and the notes are heard when they're meant on a card that runs fast ({max(map(abs, errs['fast'])):.2f} ms "
      f"out at most), on one that runs slow, looked at every few ms ({max(map(abs, errs['slow'])):.2f}), through "
      f"the longer buffer it takes when the sound breaks up ({ps['long'].got('sound')[-1].get('buffer')} ms: "
      f"{max(map(abs, errs['long'])):.2f}), and on a card that gives a buffer and a period of its own, not the ones "
      f"asked for ({cards['own'].lines('open')[-1][2:4]} frames: {max(map(abs, errs['own'])):.2f})",
      all(len(e) == 20 and close(e) for e in errs.values()) and ps["long"].got("sound")[-1].get("buffer") == 64
      and cards["own"].lines("open")[-1][2:4] == ["2048", "1024"] and "-v" in cards["own"].lines("open")[-1])

# ---- the app, in media mode -----------------------------------------------------------------------------------------
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/mcache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
g.STATIC = S + "/static"
for t in g.LIBRARY:                                    # (the settings files the tabs read: this test's own)
    if "files" in t:
        t["files"] = [S + "/static/" + os.path.basename(f) for f in t["files"]]
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
g.home_dir = lambda: HOME
A = S + "/asound"
os.makedirs(A + "/card0/pcm0p")
open(A + "/cards", "w").write(" 0 [vc4hdmi0       ]: vc4-hdmi - vc4-hdmi-0\n                      vc4-hdmi-0\n")
os.makedirs(S + "/v4l")
L.ASOUND, L.V4L = A, S + "/v4l"
real_run = subprocess.run
subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                       if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in
                                       {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli", "vcgencmd"}
                                       else real_run(cmd, *a, **k))
mine = Card("den")
os.environ.update(FAKE_LOG=mine.log, FAKE_PCM=mine.pcm, FAKE_SPEED="1.0")
BS.random = type("Dice", (), {"randrange": staticmethod(lambda n: 4)})   # (the song's seed: the same shape every time here)


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
m.set_setting("name", "den")
toasts = []
was_toast = m.toast
m.toast = lambda text, secs=4: (toasts.append(text), was_toast(text, secs))[1]
told = []                                              # what its player's told: (when, what)
was_tell = m.band_tell
m.band_tell = lambda **w: (told.append((time.monotonic(), w)), was_tell(**w))[1]
control = g.Control()                                  # (its control server and web page: the other one's word comes in there)
server = g.serve_control(m, control, port=0, key="k" * 32)
open(S + "/control-key", "w").write("k" * 32)


def spin(secs=0.3, cond=None):
    """This one's main loop, a while: its ticks, and what its web page was asked by another."""
    end = time.monotonic() + secs
    while True:
        for job in control.take():
            try:
                out = m.web_command(job["cmd"])
            except Exception as ex:
                out = {"error": repr(ex)}
            control.done(job, out)
        m.tick()
        if cond is not None and cond():
            return True
        if time.monotonic() >= end:
            return bool(cond()) if cond is not None else None
        time.sleep(0.01)


def flush():
    m.dirty = True
    m.flush()
    return np.asarray(FB.last.convert("RGB")).astype(int)


def players():
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


def notes_told(since=0.0, seat=None):
    """The notes its player's been told since then: [(when it's to be heard, the sound, whose)]."""
    return sorted((n[0], n[1], n[5]) for t, w in told if t >= since and w.get("do") == "at" for n in w["notes"]
                  if seat is None or n[5] == seat)


apps = next(t for t in g.LIBRARY if t["name"] == "Apps")
bi = next(k for k, t in enumerate(g.LIBRARY) if t["name"] == "Band")
check("Apps has the Band (after the Soundboard), and it's not one of the Bot's \"something cool\"",
      apps["children"][apps["children"].index("Soundboard"):][:3] == ["Soundboard", "Band", "Mandelbrot Set"]
      and g.LIBRARY[bi]["sim"] == "band" and "Band" in g.COOL_SKIP and g.app_named("the band") == "Band")
m.open_app(g.LIBRARY.index(apps))
rows = [it["title"] for it in m.tab_items()]
m.sels[m.tab] = rows.index("Band")
m.press("a")
spin(8, lambda: m.gig is not None and m.gig.loaded and len(m.gig.ready) == len(m.gig.loaded) and m.gig.sound_ok)
G = m.gig
s = m.sim_game()
page = flush()
boxes = {pad: (x, 78 + y, x + w, 78 + y + h) for pad, (x, y, w, h) in s.boxes().items()}
check(f"A on it in Apps opens it: its player's started (one process, of its own), this one has all four instruments "
      f"{G.mine}, their sounds ready ({len(G.ready)}), and nothing's playing yet (\"{s.song[2]}\")",
      m.band_shown() and len(players()) == 1 and G.lead and G.mine == B.SEATS and not G.bad and not G.plan["on"]
      and s.song == ("Rock", 116, "SELECT starts the band") and s.now[2] is None and mine.loud(time.monotonic() - 0.5,
                                                                                                time.monotonic() - 0.1) == 0)
check(f"its page: the four players ({[x[1] for x in s.seats]}), yours marked ({[x[1] for x in s.seats if x[5]]}), and "
      f"your instrument's buttons laid out as on a controller, all on the screen below them, each with what it plays "
      f"({ {k: v[0] for k, v in s.pads.items()} })", [x[0] for x in s.seats] == list(B.SEATS)
      and [x[0] for x in s.seats if x[5]] == ["keys"] and sorted(boxes) == sorted(B.PADS)
      and all(0 <= x0 < x1 <= 640 and 78 + STAGE.BandStage.top_px <= y0 < y1 <= 432 for x0, y0, x1, y1 in boxes.values())
      and boxes["up"][3] < boxes["left"][1] and boxes["left"][3] < boxes["down"][1] and boxes["right"][2] < boxes["y"][0]
      and s.pads["a"] == ("Am", "ready") and s.pads["down"][0] == "A4" and all(v[1] == "ready" for v in s.pads.values())
      and m.sim_hints(s) == [("L R", "Instrument"), ("SELECT", "Start"), ("START", "Back, more")])
t = time.monotonic()
m.press("select")
spin(0.2)
P = G.plan
beat = 60.0 / P["bpm"]
check(f"SELECT: the band starts, a bar counted in first (\"{m.sim_game().song[2]}\"; its first beat "
      f"{P['t0'] - t:.2f} s from now)", P["on"] and m.sim_game().song[2] == "Counting in…"
      and BS.BAND_LEAD + 4 * beat - 0.1 < P["t0"] - t < BS.BAND_LEAD + 4 * beat + 0.3
      and m.sim_hints(m.sim_game())[1] == ("SELECT", "Stop"))
spin(P["t0"] - time.monotonic() + 6 * beat)
taps = mine.out_ms([P["t0"] + (k - 4) * beat for k in range(5)], thr=300)
s = m.sim_game()
check(f"...the count-in's four taps and the song's first beat are heard when they're meant ({[round(e, 2) for e in taps]} "
      f"ms out)", len(taps) == 5 and close(taps))
check(f"...and the band plays: who's in ({[(x[1], x[4]) for x in s.seats]}), the bar's chord and the next one's "
      f"({s.now[:2]}), the beat ({s.now[2]}), nobody named (it's all this one)",
      s.now[:2] == ("F", "C") and s.now[2] in (0, 1, 2, 3) and [x[4] > 0 for x in s.seats] == [True, False, False, True]
      and all(x[2] == "" for x in s.seats) and mine.loud(P["t0"] + 0.1, P["t0"] + 2.0) > 200)
bar0 = [(round((t - P["t0"]) / beat, 3), sid, who) for t, sid, who in notes_told() if P["t0"] - 0.01 <= t < P["t0"] + 4 * beat - 0.01]
want0 = sorted((round(at, 3), sid, seat) for seat in B.SEATS for at, sid, *_ in
               B.bar(rock, seat, 0, B.played(B.form(4, 0)[seat], G.picks[(seat, 0)][0])[0], seed=4))
ahead = [w["notes"][0][0] - t for t, w in told if w.get("do") == "at"]
check(f"each bar's notes are with its player before the bar starts ({min(ahead):.2f} s ahead at least): the song's "
      f"first bar, just as the music has it for the four of them ({len(bar0)} notes)", bar0 == want0 and len(bar0) > 6
      and min(ahead) > 0.1 and max(ahead) < BS.BAND_AHEAD + 4 * beat + 0.5)
spin(P["t0"] + 8.2 * beat - time.monotonic())
s = m.sim_game()
check(f"...the next bar: its chord on the page ({s.now[0]}), and on your buttons ({s.pads['a'][0]}, "
      f"{s.pads['x'][0]}); the d-pad's stay ({s.pads['down'][0]})", s.now[0] == "C" and s.pads["a"][0] == "C"
      and s.pads["down"][0] == "A4" and s.pads["x"][0] != "E4")
# your buttons
since = time.monotonic()
mark = len(told)
m.press("a")
spin(0.05)
plays = [w for t, w in told[mark:] if w.get("do") == "play"]
clears = [w for t, w in told[mark:] if w.get("do") == "clear"]
s = m.sim_game()
check(f"A: your instrument's chord, at once ({plays}); the instrument's yours now ({[x[2] for x in s.seats if x[5]]}), "
      f"this one's own part on it stopped ({clears}), the button lit",
      len(plays) == 1 and plays[0]["id"] == "kC" and plays[0]["whose"] == "you" and clears == [{"do": "clear", "whose": "keys"}]
      and [x[2] for x in s.seats] == ["", "", "", "You"] and "a" in s.lit)
m.press("up"); m.press("x")
spin(2.2 * 4 * beat - 0.3)
mid = notes_told(since + 0.3, "keys")
others = notes_told(since + 0.3, "drums")
spin(2.6 * 4 * beat)
back = notes_told(since + 2 * 4 * beat, "keys")
s = m.sim_game()
check(f"...while it's yours this one plays the other three ({len(others)} of the drums' notes, {len(mid)} of the "
      f"keys'); a couple of bars after your last note it has the keys again ({len(back)} notes; "
      f"{[x[2] for x in s.seats if x[5]]})", not mid and len(others) > 8 and len(back) >= 1 and s.seats[3][2] == "")
m.press("r")
spin(0.4)
s = m.sim_game()
check(f"R: your buttons play the next instrument ({[x[1] for x in s.seats if x[5]]}: {s.pads['a'][0]}, "
      f"{s.pads['b'][0]}...), kept for next time", [x[0] for x in s.seats if x[5]] == ["drums"]
      and s.pads["a"] == ("Kick", "ready") and m.setting("band_seat") == "drums")
m.press("l")
spin(0.2)
check("L: back to the one before", m.gig.my == "keys" and m.sim_game().pads["down"][0] == "A4")
# START's card
m.press("start")
spin(0.1)
rows = m.band_rows()
check(f"START: its card ({[(r[1], r[2]) for r in rows]}), over the page; the band plays on behind it",
      [r[0] for r in rows] == ["song", "tempo", "seat", "volume"] and rows[0][2] == "Rock" and rows[1][2] == "116"
      and m.sim_opts == 0 and m.sim_hints(m.sim_game())[-1] == ("B", "Back to Apps") and flush() is not None)
m.press("down")
at_was = m.band_bar()
n_was = G.plan["n"]
m.press("right"); m.press("right")
spin(0.1)
at_now = m.band_bar()
check(f"...Tempo, ▶ twice: faster ({G.plan['bpm']}), from where the song is (bar {at_was[0] + 1} still), kept",
      G.plan["bpm"] == 124 and at_now[0] == at_was[0] and G.plan["n"] > n_was and G.plan["on"]
      and m.setting("band_bpm_rock") == 124 and {"do": "clear"} in [w for _, w in told[-6:]])
m.press("down"); m.press("down")
vol = m.volume
m.press("left")
spin(0.3)
check(f"...Volume, ◀: quieter ({m.volume}), and its player's told", m.volume == vol - g.VOLUME_STEP
      and {"do": "volume", "v": m.volume} in [w for _, w in told[-8:]])
m.press("up"); m.press("up"); m.press("up")
t = time.monotonic()
m.press("right")
spin(0.3)
G = m.gig
check(f"...Song, ▶: the next one ({B.song(G.plan['song'])['name']}, {G.plan['bpm']}), from the top with a bar counted "
      f"in, its sounds told to its player", G.plan["song"] == "blues" and G.plan["bpm"] == 92 and G.plan["on"]
      and G.plan["t0"] > t + 2 and m.setting("band_song") == "blues"
      and any(w.get("do") == "load" for tt, w in told if tt >= t))
m.press("a")
spin(0.2)
check("...A: on with the band", m.sim_opts is None and m.band_shown() and G.card is None)
m.press("select")
spin(0.6)
quiet_from = time.monotonic()
spin(0.8)
check("SELECT again: the band stops", not m.gig.plan["on"] and mine.loud(quiet_from + 0.1, quiet_from + 0.7) < 3
      and m.sim_game().song[2] == "SELECT starts the band")
mark = len(mine.frames())
t = time.monotonic()
m.press("b")
spin(0.5)
on = mine.onsets(since=mark, thr=300)
check(f"...your buttons still play ({(mine.when(on[0]) - t) * 1000:.0f} ms after B)" if on else "...your buttons still play",
      on and mine.when(on[0]) - t < 0.12)
m.set_setting("band_song", "rock")
m.set_setting("band_bpm_rock", 116)
m.press("start"); m.press("b")
spin(0.3)
check("START, then B: back to Apps, and its player's gone", m.view == "list" and m.tab_type() == "group"
      and m.gig is None and until(lambda: players() == [], 4))

# ---- who decides: a decision model on your bot's computer (a stand-in) ---------------------------------------------------
class Fake:
    models = {"llama3.2:3b": ["completion"], "tev1:latest": ["completion", "decision"]}
    slow = 0.05
    picks = {"bass": "rest", "keys": "solo", "drums": "fill", "guitar": "ease"}
    asked = []


class Ollama(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def answer(self, code, obj):
        data = json.dumps(obj).encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except OSError:                                # (the one that asked has stopped waiting)
            pass

    def do_GET(self):
        if self.path == "/api/tags":
            return self.answer(200, {"models": [{"name": n} for n in Fake.models]})
        self.answer(404, {"error": "not found"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if self.path == "/api/show":
            return self.answer(200, {"capabilities": Fake.models.get(body.get("model"), [])})
        if self.path == "/v1/systemone":
            q = (body.get("questions") or {}).get("pick") or {}
            seat = next((s for s in B.SEATS if f"play the {s} " in q.get("instructions", "")), "")
            Fake.asked.append((time.monotonic(), seat, body))
            time.sleep(Fake.slow)
            pick = Fake.picks.get(seat, "follow")
            return self.answer(200, {"model": body.get("model"), "answers": {"pick": {"type": "choice", "choice": pick,
                                                                                    "confidence": 0.7}}})
        self.answer(404, {"error": "not found"})


srv = ThreadingHTTPServer(("127.0.0.1", 0), Ollama)
threading.Thread(target=srv.serve_forever, daemon=True).start()
with open(S + "/static/bot.txt", "w") as f:
    f.write(f"server = 127.0.0.1:{srv.server_address[1]}\nmodel = llama3.2:3b\n")
m.open_app(bi)
spin(8, lambda: m.gig is not None and m.gig.models and len(m.gig.ready) == len(m.gig.loaded or [1]))
G = m.gig
m.press("start")
rows = m.band_rows()
check(f"your bot's computer has a decision model: START's card has Who decides ({rows[-1][2]}; the models there that "
      f"can't decide aren't offered)", G.models == ["tev1:latest"] and rows[-1][:2] == ("decides", "Who decides")
      and rows[-1][2] == "tev1:latest")
m.press("a")
told.clear()
m.press("select")
P = G.plan
beat = 60.0 / P["bpm"]
spin(P["t0"] - time.monotonic() + 4.5 * 4 * beat, lambda: False)
by = {seat: G.picks.get((seat, 1)) for seat in B.SEATS}
sec1 = [(seat, sid) for t, sid, seat in notes_told() if P["t0"] + 16 * beat - 0.01 <= t < P["t0"] + 32 * beat - 0.01]
first_ask = min(t for t, seat, body in Fake.asked)
st = Fake.asked[0][2]
check(f"it's asked what each of this one's players does with its next four bars ({len(Fake.asked)} asks, the first "
      f"{P['t0'] - first_ask:.1f} s before the song's first beat), told of the song and the band "
      f"({sorted(st['state'])[:3]}...), one at a time", len(Fake.asked) >= 8 and first_ask < P["t0"]
      and st["model"] == "tev1:latest" and st["state"]["song"] == "Rock" and "the_song_has_you" in st["state"]
      and set(st["questions"]["pick"]["criteria"]) <= set(B.CHOICES))
check(f"...and what it picks is what's played: for the second four bars {by}; the bass sits them out, the keys solo "
      f"({len([1 for seat, sid in sec1 if seat == 'bass'])} bass notes, {len([1 for seat, sid in sec1 if seat == 'keys'])} "
      f"of the keys')", by == {seat: (Fake.picks[seat], "tev1:latest") for seat in B.SEATS}
      and not [1 for seat, sid in sec1 if seat == "bass"] and len([1 for seat, sid in sec1 if seat == "keys"]) > 8
      and all(midi_of(sid) is not None for seat, sid in sec1 if seat == "keys")
      and m.sim_game().seats[1][3] == "sitting out" and m.sim_game().seats[3][3] == "solo")
Fake.slow, Fake.picks = 30.0, dict.fromkeys(B.SEATS, "rest")
n_asked = len(Fake.asked)
slow_from = time.monotonic()
G.wanted = {}
at = m.band_bar()
later = at[0] // 4 + 2
spin(P["t0"] + (later * 16 + 2) * beat - time.monotonic())
by = {seat: G.picks.get((seat, later)) for seat in B.SEATS}
ahead = [w["notes"][0][0] - t for t, w in told if t >= slow_from and w.get("do") == "at"]
check(f"one that's slow to answer isn't waited for: the band plays on, every bar with its player in time "
      f"({min(ahead, default=0):.2f} s ahead at least), and the dice's pick stands ({by}); and the fill it picked for "
      f"the drums was played, a crash after it", all(v is not None and v[1] == BS.DICE for v in by.values())
      and len(Fake.asked) > n_asked and mine.loud(time.monotonic() - 1.0, time.monotonic() - 0.2) > 100
      and len(ahead) >= 4 and min(ahead) > 0.1 and 2 in G.crash and any(sid == "crash" for _, sid, _ in notes_told()))
m.press("start"); m.press("down"); m.press("down"); m.press("down"); m.press("down")
m.press("right")
n_asked = len(Fake.asked)
check(f"Who decides, ▶: {m.band_rows()[-1][2]} (kept), and nobody's asked any more",
      m.band_rows()[-1][2] == BS.DICE and m.setting("band_decides") == BS.DICE and m.band_decider(G) == "")
m.press("b")
spin(0.4)
os.remove(S + "/static/bot.txt")
check("...back in Apps", m.gig is None and until(lambda: players() == [], 4) and len(Fake.asked) <= n_asked + 1)
m.set_setting("band_decides", "")

# ---- in another's band (the other one: a stand-in) ----------------------------------------------------------------------
posted = []
REAL_POST, REAL_OFFSET = BS.band_post, BS.clock_offset
BS.band_post = lambda url, body, timeout=3.0: (posted.append((url, body)),            # (asked in by this one, it
                                               None if body["kind"] == "start" else {"ok": True})[1]   # doesn't answer)
BS.clock_offset = lambda host, port, token, **k: (5.0, 0.001)      # (its clock: five seconds on from this one's)
KITCHEN = "http://127.0.0.1:9"
m.pie.heard[KITCHEN] = {"host": "kitchen", "seen": time.time() + 3600, "peer": True}
TOKEN = "k" * 22
m.go_home()
spin(0.3)
r1 = m.web_band({"kind": "start", "token": TOKEN, "port": BS.BAND_PORT, "from": "10.0.0.99"})
r2 = m.web_band({"kind": "start", "token": "short", "from": "127.0.0.1"})
r3 = m.web_band({"kind": "plan", "token": TOKEN, "plan": {}, "seat": "bass", "from": "127.0.0.1"})
check(f"asked into a band by something that isn't one of your Pietatos, or without a proper word for the band, or "
      f"told a plan for one it isn't in: no ({r1['error']}; {r2['error']}; {r3['error']})",
      r1 == {"ok": False, "error": "Not one of your Pietatos"} and not r2["ok"] and not r3["ok"] and m.gig is None
      and m.view == "home")
m.game = type("Game", (), {"attract": False, "ended": False})()
r = m.web_band({"kind": "start", "token": TOKEN, "port": BS.BAND_PORT, "from": "127.0.0.1"})
m.game = None
check(f"in a game: it isn't asked in ({r})", r == {"ok": False, "error": "It's playing a game"} and m.gig is None)
r = m.web_band({"kind": "start", "token": TOKEN, "port": BS.BAND_PORT, "members": 0, "from": "127.0.0.1"})
spin(0.5, lambda: m.gig is not None and m.gig.offset is not None)
G = m.gig
check(f"asked in by one of yours, on its home screen: in ({r}, \"{toasts[-1]}\"), its page up, its clock set against "
      f"the other's ({G.offset} s on), nothing of its own to play till it's told", r == {"ok": True, "want": "keys"}
      and m.band_shown() and not G.lead and G.leader == KITCHEN and G.leader_name == "kitchen" and G.offset == 5.0
      and G.mine == () and toasts[-1] == "In kitchen's band" and G.was == ("home", m.tab) or G.was[0] == "home")
spin(3, lambda: G.proc is not None and G.sound_ok)
told.clear()
bpm = 120
beat = 0.5
T0 = time.monotonic() + 5.0 + 1.5 + 4 * beat            # (by the other one's clock)
plan = {"n": 7, "song": "funk", "bpm": bpm, "t0": T0, "seed": 4, "on": True}
who = {"drums": "den", "bass": "kitchen", "guitar": "kitchen", "keys": "kitchen"}
r = m.web_band({"kind": "plan", "token": TOKEN, "plan": plan, "seat": "drums", "who": who,
                "does": {"bass": ["lift", "tev1:latest"], "keys": ["solo", "Dice"]}, "person": ["guitar", 2], "from": "127.0.0.1"})
mark = len(mine.frames())
spin(1.5 + 4 * beat + 4 * beat + 0.3)
taps = mine.out_ms([T0 - 5.0 + (k - 4) * beat for k in range(5)], thr=300, since=mark)
s = m.sim_game()
check(f"told the plan and its instrument (the drums): it plays just that ({sorted({w for _, _, w in notes_told()})}), in "
      f"step by the other's clock ({[round(e, 2) for e in taps]} ms out); its page has who's on what "
      f"({[(x[1], x[2]) for x in s.seats]}) and what they're doing ({[x[3] for x in s.seats]})",
      r == {"ok": True} and G.mine == ("drums",) and {w for _, _, w in notes_told()} == {"drums"} and len(taps) == 5
      and close(taps) and [x[2] for x in s.seats] == ["den", "kitchen", "kitchen", "kitchen"]
      and s.seats[1][3] == "busier" and s.seats[3][3] == "solo" and s.song[:2] == ("Funk", 120) and G.person == ("guitar", 2))
said = [b for u, b in posted if b.get("kind") == "status"]
check(f"...and it says what it's doing to the one leading ({said[-1] if said else None})", said and said[-1]["token"] == TOKEN
      and said[-1]["does"]["drums"][0] in B.SEAT_CHOICES["drums"] and said[-1]["you"] is None
      and all(u == KITCHEN for u, b in posted))
# Timing: this one's sound a little earlier than the others' (a TV's slow with it)
m.press("start")
keys = [r[0] for r in m.band_rows()]
m.sim_opts = keys.index("early") if "early" in keys else 0
m.press("left"); m.press("left"); m.press("left")
row = m.band_rows()[m.sim_opts]
m.press("a")
T1 = time.monotonic() + 5.0 + 1.5 + 4 * beat
r = m.web_band({"kind": "plan", "token": TOKEN, "plan": dict(plan, n=8, t0=T1), "seat": "drums", "who": who, "does": {},
                "person": None, "from": "127.0.0.1"})
spin(0.4)
mark = len(mine.frames())
spin(1.1 + 4 * beat + 4 * beat + 0.3)
taps = mine.out_ms([T1 - 5.0 + (k - 4) * beat for k in range(5)], thr=300, since=mark)
place = "band_early_" + (G.place or "own")
check(f"in a band with others, START's card has Timing ({keys}): ◀ three times, and this one plays {row[2]} from its "
      f"next bars on ({[round(e, 1) for e in taps]} ms from the beat), kept for where its sound goes ({place})",
      keys == ["seat", "volume", "early"] and row == ("early", "Timing", "30 ms early") and m.setting(place) == 30
      and r == {"ok": True} and len(taps) == 5 and close([e + 30.0 for e in taps]) and m.sim_opts is None)
m.set_setting(place, 40)
m.press("start")
m.sim_opts = keys.index("early") if "early" in keys else 0
for _ in range(6):
    m.press("right")
late = m.band_rows()[m.sim_opts][2]
m.set_setting(place, BS.BAND_EARLY[0])
m.press("left")
check(f"...▶: later ({late}), and no further than it goes ({m.band_rows()[m.sim_opts][2]})", late == "20 ms late"
      and m.setting(place) == BS.BAND_EARLY[0] and m.band_rows()[m.sim_opts][2] == f"{BS.BAND_EARLY[0]} ms early")
m.set_setting(place, 0)
m.press("a")
spin(0.1)
posted.clear()
m.press("r")
m.press("select")
m.press("x")
spin(BS.BAND_SAY_EVERY + 0.5)
kinds = [b["kind"] for u, b in posted]
you = [b for u, b in posted if b.get("kind") == "status" and b.get("you")]
check(f"its own buttons: R asks for another instrument, SELECT asks the one leading to stop or start the band, and "
      f"playing along is said ({kinds}; {you[-1]['you'] if you else None})", {"kind": "seat", "token": TOKEN, "want": "drums"}
      in [b for u, b in posted] and {"kind": "ask", "what": "toggle", "token": TOKEN} in [b for u, b in posted]
      and you and you[-1]["you"][0] == "drums" and G.plan["on"])
r = m.web_band({"kind": "plan", "token": TOKEN, "plan": dict(plan, on=False, n=9), "seat": "", "who": who, "does": {},
                "person": None, "from": "127.0.0.1"})
spin(0.6)
quiet_from = time.monotonic()
spin(0.6)
check("told it's stopped, and that it has no instrument: silence", r == {"ok": True} and G.mine == () and not G.plan["on"]
      and mine.loud(quiet_from + 0.1, quiet_from + 0.5) < 3)
r = m.web_band({"kind": "stop", "token": TOKEN, "from": "127.0.0.1"})
spin(0.5)
check(f"the band's over: it says so (\"{toasts[-1]}\"), and it's back where it was (its home screen), its player gone",
      r == {"ok": True} and toasts[-1] == "kitchen's band is over" and m.view == "home" and m.gig is None
      and until(lambda: players() == [], 4))
m.open_app(bi)                                         # opened here by yourself, then asked in: it stays on its page after
spin(0.5)
big = "z" * 22
m.gig.token = "a" * 22
r = m.web_band({"kind": "start", "token": big, "port": BS.BAND_PORT, "members": 0, "from": "127.0.0.1"})
check(f"two that both started one, nobody in either yet: one gives way, by their bands' words ({r.get('error')})",
      r["ok"] is False and r["band"] == {"token": "a" * 22} and m.gig.lead)
r = m.web_band({"kind": "start", "token": big, "port": BS.BAND_PORT, "members": 2, "from": "127.0.0.1"})
spin(0.3)
G = m.gig
check("...and into one that has others in it already", r["ok"] and not G.lead and G.token == big and G.was is None)
G.heard = time.monotonic() - BS.BAND_GONE - 1
spin(0.3)
check("the one leading gone quiet: this one's on its own again, here, with all four",
      m.band_shown() and m.gig.lead and m.gig.mine == B.SEATS and m.gig.token != big and not m.gig.plan["on"])
m.go_home()
spin(0.4)
m.pie.heard.clear()

# ---- two Pietatos: this one ("den"), and the TV's in a process of its own ("tv") -----------------------------------------
BS.band_post, BS.clock_offset = REAL_POST, REAL_OFFSET
sys.path.append(ROOT + "/pitato")
import webui
webui.HOME = HOME
webui.STATIC = S + "/webstatic"
os.makedirs(webui.STATIC + "/fonts")
webui.STATE_FILE = g.STATE_FILE
webui.CONTROL = ("127.0.0.1", server.server_address[1])
webui.CONTROL_KEY = S + "/control-key"
import logging; logging.getLogger("werkzeug").setLevel(logging.ERROR)
from werkzeug.serving import make_server
web = make_server("127.0.0.1", 0, webui.app, threaded=True)
threading.Thread(target=web.serve_forever, daemon=True).start()
MINE = f"http://127.0.0.1:{web.server_port}"
TV, LOG = S + "/tv", S + "/tv.log"
os.makedirs(TV)
open(LOG, "w").close()
theirs = Card("tv", 1.002)                              # (the TV's sound card: its clock a little fast)
tv = subprocess.Popen([sys.executable, TESTS + "/peer_pietato.py", TV, LOG, "tv", MINE, "den"],
                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1, env=theirs.env())
line = tv.stdout.readline().split()
if line[:1] != ["READY"]:
    print("FAIL the TV's Pietato didn't start", line)
    sys.exit(1)
THEIRS = line[1]
reply = []


def tv_do(text):
    """Said to the TV (waiting for its answer on a thread: this one's main loop goes on meanwhile)."""
    t = threading.Thread(target=lambda: (tv.stdin.write(text + "\n"), tv.stdin.flush(),
                                         reply.append(tv.stdout.readline().strip())), daemon=True)
    n = len(reply)
    t.start()
    spin(10, lambda: len(reply) > n)
    return reply[-1] if len(reply) > n else ""


def tv_band():
    st = json.loads(tv_do("state") or "{}")
    return st.get("page"), st.get("band") or {}


r = webui.app.test_client().post("/api/band", json={"kind": "dance", "token": TOKEN})
check(f"the web page takes what your Pietatos say of the band, and only that ({r.status_code})", r.status_code == 400
      and "/api/band" in webui.PEER_PATHS)
page_was = tv_band()[0]
m.pie.heard[THEIRS] = {"host": "tv", "seen": time.time() + 3600, "peer": True}
toasts.clear()
m.open_app(bi)
spin(8, lambda: m.gig is not None and m.gig.members)
G = m.gig
spin(1.0)
page, band = tv_band()
check(f"opened here: the TV (on its {page_was} screen) is asked in, opens its page, and takes an instrument "
      f"(\"{toasts[-1] if toasts else ''}\"): this one has the rest {G.mine}", page_was == "home" and page == "Band"
      and band.get("lead") is False and band.get("with") == "den" and [x["name"] for x in G.members.values()] == ["tv"]
      and G.mine == ("drums", "bass", "guitar") and G.who["keys"] == "tv" and toasts[-1:] == ["tv is on keys"])
spin(4, lambda: len(G.ready) == len(G.loaded or [1]))
mark_den, mark_tv = len(mine.frames()), len(theirs.frames())
m.press("select")
P = G.plan
beat = 60.0 / P["bpm"]
spin(P["t0"] - time.monotonic() + 9 * beat)
page, band = tv_band()
taps = mine.out_ms([P["t0"] + (k - 4) * beat for k in range(4)], thr=300, since=mark_den)
on_tv = theirs.onsets(thr=300, since=mark_tv)
tv_out = (theirs.when(on_tv[0]) - P["t0"]) * 1000 if on_tv else None
s = m.sim_game()
check(f"SELECT here: both play, each its own. The TV has the plan (its instrument: {band.get('mine')}), its clock set "
      f"against this one's, and its first chord is heard on the song's first beat ({tv_out:+.2f} ms out, through its "
      f"own card), as this one's count-in is ({[round(e, 2) for e in taps]})" if tv_out is not None else "SELECT here: both play",
      band.get("plan", {}).get("on") and band["plan"]["t0"] == P["t0"] and band["mine"] == ["keys"] and band["synced"]
      and tv_out is not None and abs(tv_out) < 8 and len(taps) == 4 and close(taps)
      and mine.loud(P["t0"] + 0.2, P["t0"] + 3 * beat) > 100)
spin(BS.BAND_SAY_EVERY + 1.0)
page, band = tv_band()
check(f"...each knows what the others are doing: here, the TV's keys ({G.does.get('keys')}, on the page as "
      f"\"{s.seats[3][2]}\"); there, this one's three ({sorted(band.get('does', {}))}, {band.get('who')})",
      G.does.get("keys", ("",))[0] in B.CHOICES and m.sim_game().seats[3][2] == "tv" and m.sim_game().seats[0][2] == "den"
      and sorted(band.get("does", {})) == ["bass", "drums", "guitar"]
      and band.get("who") == {"drums": "den", "bass": "den", "guitar": "den", "keys": "tv"})
tv_do("press r")
spin(4, lambda: G.who.get("drums") == "tv")
spin(BS.BAND_SAY_EVERY + 1.5, lambda: tv_band()[1].get("mine") == ["drums"])
page, band = tv_band()
check(f"R on the TV: it asks for the next instrument and has it ({band.get('mine')}); this one has the keys again "
      f"{G.mine}", band.get("mine") == ["drums"] and G.mine == ("bass", "guitar", "keys") and G.who["drums"] == "tv")
tv_do("press select")
spin(3, lambda: not G.plan["on"])
spin(1.0)
page, band = tv_band()
check("SELECT on the TV: the band stops, for both", not G.plan["on"] and band["plan"]["on"] is False)
tv_do("press start")
tv_do("press b")
spin(4, lambda: not G.members)
page, band = tv_band()
check(f"START, then B on the TV: it's out of the band (\"{toasts[-1]}\"), and this one has all four again",
      not G.members and G.mine == B.SEATS and toasts[-1] == "tv left the band" and not band)
G.left.clear()
G.asked.clear()
tv_do("press b")                                       # (the TV: back on its home screen)
spin(8, lambda: G.members)
page, band = tv_band()
check(f"...asked in again a while after (it's on its {page} page)", bool(G.members) and page == "Band")
m.press("start"); m.press("b")
spin(4, lambda: m.gig is None and tv_band()[0] != "Band")
page, band = tv_band()
said = [json.loads(x).get("toast") for x in open(LOG).read().splitlines() if "toast" in x]
check(f"START, then B here: the band's over, and the TV's back where it was (its {page} screen: \"{said[-1]}\")",
      m.gig is None and page == "home" and not band and said[-1] == "den's band is over")
try:
    tv.stdin.write("quit\n")
    tv.stdin.flush()
    tv.wait(5)
except (OSError, subprocess.TimeoutExpired):
    tv.kill()
check("and nothing's left running", until(lambda: players() == [], 5))
m.go_home()
spin(0.3)
m.leave()

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
