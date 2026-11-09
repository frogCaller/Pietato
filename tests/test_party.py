"""Party mode (pitato/party.py, screens/party.py): your Pietatos playing the same song or station at once, in step.
First its parts on their own: the leader's clock and another's pings of it (an offset found as NTP finds one, the
quickest answer the nearest; none without the party's key); a station passed on (its song titles taken out of the
sound, and kept; each one that takes it gets the same bytes from the same one on); and the players, against pretend
sound cards (aplay here logs when each bit is heard): two started for the same time play the same sound at the same
moment, one told late or whose sound card's clock runs fast or slow too, they pause and play on together, and a
song's end is known; and kept in step without a click (a tone through it, a sound card taking it a period at a time
as ALSA does, one running fast and kept waiting a moment, a pause faded out and in). Then two Pietatos: this one
("gpi") and the TV's in a process of its own (peer_pietato.py, "tv"). A song plays here; HOME's menu has Party mode;
the TV's asked, sets its clock against this one's, and from then on plays what this one plays, in step (taken from
this one's web page): A here pauses both, A on the TV plays both on, R on the TV skips both to the next song. A song
from the web (as the Internet Archive's are): each takes it from there, in step. Then a station, passed on by this
one: both play the same bytes, in step; the TV leaves, and the party's over here. Ended from HOME's menu: the TV
stops, this one plays on, on its own. Last, this one in another's party, with a game on here: the party's next song
isn't played over the game; it leaves the party instead."""
import json, math, os, shutil, statistics, subprocess, sys, threading, time, wave
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
real_run = subprocess.run                              # (FFmpeg, to make a station's sound: the test stands in for the rest)
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import numpy as np
import pietato_all as g
import pitato.party as P

S = SP + "/t_party"
shutil.rmtree(S, ignore_errors=True)
HOME, TV = S + "/gpi", S + "/tv"
for h in (HOME, TV):
    for d in ("Music", "Videos", "Pictures", "Documents", "Games/Saves"):
        os.makedirs(f"{h}/{d}")
os.makedirs(S + "/bin")
ok_all = []
RATE = P.PARTY_RATE


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


# a pretend aplay: takes the sound as a sound card would (FAKE_APLAY_SPEED_X: how fast its clock runs), with a buffer as
# long as --buffer-time says, and logs each 10 ms as it's heard: when, its first sample, and how loud it is
open(S + "/bin/aplay", "w").write('''#!/usr/bin/env python3
import os, struct, sys, time
import numpy as np
args = sys.argv[1:]
rate = int(args[args.index("-r") + 1]) if "-r" in args else 48000
buf = next((int(a.split("=")[1]) for a in args if a.startswith("--buffer-time=")), 100000) / 1e6
speed = float(os.environ.get("FAKE_APLAY_SPEED_X", "1.0"))
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
''')
os.chmod(S + "/bin/aplay", 0o755)
os.environ["PATH"] = S + "/bin:" + os.environ["PATH"]


def ramp(path, secs):
    """A song whose every sample says where in it it is: left, the place's low 15 bits; right, the rest."""
    import wave
    n = np.arange(RATE * secs, dtype=np.int64)
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


# ---- the leader's clock, and another's pings of it --------------------------------------------------------------------
TOKEN = "t" * 22
clock = P.ClockServer(TOKEN, port=0)
got = P.clock_offset("127.0.0.1", clock.port, TOKEN)
check(f"another's pings of the leader's clock: the same clock here, so no offset ({got})",
      got is not None and abs(got[0]) < 0.002 and got[1] < 0.05)
clock.close()
clock = P.ClockServer(TOKEN, port=0, clock=lambda: time.monotonic() + 123.456)
got = P.clock_offset("127.0.0.1", clock.port, TOKEN)
check(f"...a leader whose clock is 123.456 s on: found to a millisecond ({got})",
      got is not None and abs(got[0] - 123.456) < 0.001)
check("...without the party's key: no answer", P.clock_offset("127.0.0.1", clock.port, "x" * 22, n=2, timeout=0.2)
      is None)
clock.close()


# ---- a station, passed on --------------------------------------------------------------------------------------------
class Station(BaseHTTPRequestHandler):
    """A pretend internet station: its sound (its server's audio, as it comes: a little at a time), with its song's
    title put in every EVERY bytes, as Icecast does when it's asked to (Icy-MetaData: 1)."""
    EVERY = 4000

    def log_message(self, *a):
        pass

    def do_GET(self):
        meta = self.headers.get("Icy-MetaData") == "1"
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("icy-br", "128")
        if meta:
            self.send_header("icy-metaint", str(self.EVERY))
        self.end_headers()
        data, at, n = self.server.audio, 0, 0
        try:
            while at < len(data):
                piece = data[at:at + self.EVERY]
                at += len(piece)
                self.wfile.write(piece)
                if meta and len(piece) == self.EVERY:
                    n += 1
                    title = f"StreamTitle='Song {'A' if n < 6 else 'B'}';".encode()
                    title += bytes(-len(title) % 16)
                    self.wfile.write(bytes([len(title) // 16]) + title)
                self.wfile.flush()
                time.sleep(self.EVERY / 16000)         # (128 kb/s: as it would come)
        except OSError:
            pass


STATION_AUDIO = bytes((i * 7) % 251 for i in range(160000))
station = ThreadingHTTPServer(("127.0.0.1", 0), Station)
station.audio = STATION_AUDIO
threading.Thread(target=station.serve_forever, daemon=True).start()
STATION = f"http://127.0.0.1:{station.server_port}/stream"
relay = P.Relay(STATION)
check("a station passed on: it's coming", relay.ready(5))
time.sleep(2.0)
data, upto = relay.take(0, timeout=1)
check(f"...the song titles taken out of the sound: what's kept is its sound alone ({len(data)} bytes)",
      len(data) > 20000 and data == STATION_AUDIO[:len(data)])
check(f"...the latest title kept ({relay.song!r})", relay.song in ("Song A", "Song B"))
server = P.RelayServer(TOKEN, port=0)
server.relay = relay
start = relay.start_byte(behind=0.5)
got = {}


def take(name):
    import urllib.request
    with urllib.request.urlopen(f"http://127.0.0.1:{server.port}/station?token={TOKEN}&from={start}", timeout=5) as r:
        got[name] = r.read(30000)
jobs = [threading.Thread(target=take, args=(n,)) for n in ("one", "two")]
for j in jobs:
    j.start()
for j in jobs:
    j.join(10)
check(f"...two take it from the same byte ({start}): both get the same bytes, from there on",
      got.get("one") and got.get("one") == got.get("two") == STATION_AUDIO[start:start + 30000])
try:
    import urllib.request
    urllib.request.urlopen(f"http://127.0.0.1:{server.port}/station?token={'x' * 22}&from=0", timeout=5)
    nokey = False
except Exception:
    nokey = True
check("...not without the party's key", nokey)
time.sleep(4)
check(f"...its title, a new song ({relay.song!r})", relay.song == "Song B")
relay.close()
server.close()

# ---- the players, against pretend sound cards ----------------------------------------------------------------------
SONG = S + "/ramp.wav"
ramp(SONG, 30)


def player(name, at, pos=0.0, speed=1.0, clock=None, src=SONG):
    os.environ["FAKE_APLAY_LOG"], os.environ["FAKE_APLAY_SPEED_X"] = f"{S}/{name}.log", str(speed)
    return P.PartyPlayer(src, at, pos=pos, volume=100, clock=clock)


at = time.monotonic() + 1.5
a = player("a", at)
b = player("b", at, speed=1.001)                       # (its sound card's clock runs fast: ten times more than one does)
time.sleep(0.6)
c = player("c", at, speed=0.999)                       # (told late, and its clock runs slow)
time.sleep(1.5 + 6)
la, lb, lc = (lag(f"{S}/{n}.log", at, after=1.0) for n in "abc")
NEAR = 2 * P.PARTY_SLACK * 1000 + 1                    # (ms: each is kept within PARTY_SLACK of the clock, so two are
                                                       #  within twice that of each other; and a millisecond, measuring)
check(f"two players for the same time: each heard where the clock says, as near as its sound card can say (mean "
      f"{la[0]:.1f} ms, at most {la[1]:.1f}; {lb[0]:.1f}, {lb[1]:.1f}; {lc[0]:.1f}, {lc[1]:.1f})" if None not in la + lb + lc
      else "two players for the same time", None not in la + lb + lc and max(la[1], lb[1], lc[1]) < 35
      and max(la[0], lb[0], lc[0]) - min(la[0], lb[0], lc[0]) < NEAR)
ab, cb = apart(f"{S}/a.log", f"{S}/b.log", at), apart(f"{S}/a.log", f"{S}/c.log", at)
check(f"...one whose sound card runs fast, and one told late whose runs slow: in step with it all the same "
      f"({ab}, {cb})", ab[0] is not None and cb[0] is not None and abs(ab[0]) < NEAR and abs(cb[0]) < NEAR)
p_at = time.monotonic() + 0.4
for pl in (a, b, c):
    pl.pause_at(p_at)
time.sleep(1.2)
pos = [round(pl.position(), 3) for pl in (a, b, c)]
check(f"...paused together: all at the same place ({pos})", all(pl.paused() for pl in (a, b, c))
      and max(pos) - min(pos) < 0.002)
silent = [h for h in heard(f"{S}/a.log") if p_at + 0.15 < h[0] < p_at + 1.0]
check(f"...and silent ({len(silent)} bits heard meanwhile, none of the song)", silent
      and all(w is None for _, w, _ in silent))
r_at = time.monotonic() + 0.4
for pl in (a, b, c):
    pl.resume_at(r_at)
time.sleep(2.0)
on = [h for h in heard(f"{S}/a.log") if h[0] > r_at + 0.2 and h[1] is not None]
check(f"...on again together, from where they were ({on[0][1] if on else None:.3f} s, paused at {pos[0]:.3f})"
      if on else "...on again together", on and abs(on[0][1] - (pos[0] + (on[0][0] - r_at))) < 0.03
      and abs(apart(f"{S}/a.log", f"{S}/c.log", r_at, after=0.3)[0]) < NEAR)
for pl in (a, b, c):
    pl.close()
short = S + "/short.wav"
ramp(short, 2)
at = time.monotonic() + 0.5
d = player("d", at, src=short)
proc = P.PartyProc(d, title="Ramp", lead=True)
proc.stdin.write("pausing_keep volume 50 1\n")
proc.stdin.write("pausing_keep_force get_time_pos\n")
proc.stdin.write("get_property pause\n")
lines = [next(proc.stdout), next(proc.stdout)]
check(f"as media mode's player sees it: its volume, how far it's got, whether it's paused ({lines})",
      d.volume == 50 and lines[0].startswith("ANS_TIME_POSITION=") and lines[1] == "ANS_pause=no\n")
end = time.time() + 6
while proc.poll() is None and time.time() < end:
    time.sleep(0.1)
check(f"...the leader's: its end, once it's been heard ({time.monotonic() - at:.1f} s in)", proc.poll() == 0
      and 2.0 <= time.monotonic() - at < 3.5)
e = player("e", time.monotonic() + 0.3, src=short)
other = P.PartyProc(e, title="Ramp")
time.sleep(3.0)
check("...another's: not ended (it waits for the leader's next)", other.poll() is None)
other.stdin.write("quit\n")
check("...quit: ended", other.poll() == 0 and e.closed)

# ---- clean sound: kept in step without a click ----------------------------------------------------------------------
GULPS = S + "/gulps"                                   # (a pretend aplay that takes its sound a period at a time, as
os.makedirs(GULPS)                                     #  ALSA does, playing it at its sound card's rate; all it's given
open(GULPS + "/aplay", "w").write('''#!/usr/bin/env python3
import os, sys, time
args = sys.argv[1:]
rate = int(args[args.index("-r") + 1]) if "-r" in args else 48000
buf = next((int(a.split("=")[1]) for a in args if a.startswith("--buffer-time=")), 100000) / 1e6
per = next((int(a.split("=")[1]) for a in args if a.startswith("--period-time=")), 20000) / 1e6
speed = float(os.environ.get("FAKE_SPEED", "1.0"))
out = open(os.environ["FAKE_OUT"], "ab", buffering=0)
inp, period = sys.stdin.buffer, int(per * rate) * 4
held, start, played = 0, None, 0
while True:
    if start is not None:
        done = int((time.monotonic() - start) * rate * speed) - played
        if done > 0:
            played += min(done, held)
            held -= min(done, held)
    if held * 4 + period <= buf * rate * 4:
        data = inp.read(period)
        if not data:
            break
        out.write(data)
        held += len(data) // 4
        if start is None and held * 4 >= buf * rate * 4 - period:
            start = time.monotonic()
        continue
    time.sleep(per / 4)
''')                                                    #  written to FAKE_OUT)
os.chmod(GULPS + "/aplay", 0o755)
TONE = S + "/tone.wav"
tt = np.arange(RATE * 20) / RATE
tone = (8000 * np.sin(2 * np.pi * 1000 * tt)).astype("<i2")
with wave.open(TONE, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(np.stack([tone, tone], -1).tobytes())
LIMIT = 3 * 8000 * (2 * np.pi * 1000 / RATE) ** 2       # (a tone's own second difference, at most, three times over)
was_path = os.environ["PATH"]
os.environ["PATH"] = GULPS + ":" + was_path
for speed, pause in (("1.0", True), ("1.001", False)):
    os.environ["FAKE_OUT"], os.environ["FAKE_SPEED"] = f"{S}/tone-{speed}.raw", speed
    open(os.environ["FAKE_OUT"], "wb").close()
    t0 = time.monotonic() + 0.5
    pl = P.PartyPlayer(TONE, t0, volume=100)
    if pause:                                          # (paused a moment, and on again: faded out, and in)
        pl.pause_at(t0 + 3.0)
        time.sleep(3.6)
        pl.resume_at(time.monotonic() + 0.2)
    else:                                              # (kept from it a moment, as a busy Pi can: Python's taken up
        time.sleep(3.0)                                #  with a big sort a third of a second; it jumps to put that
        big = [math.sin(k) for k in range(1200000)]    #  right, faded across)
        big.sort()
        del big
    time.sleep(10.0 - 3.6 if pause else 7.0)
    drift = (pl.drift or 0.0) / RATE * 1000
    pl.close()
    out = np.frombuffer(open(os.environ["FAKE_OUT"], "rb").read(), dtype="<i2").reshape(-1, 2)[:, 0].astype(np.float64)
    on = np.nonzero(np.abs(out) > 100)[0]
    out = out[on[0]:on[-1] - 240] if len(on) > 1000 else out
    clicks = int(np.sum(np.abs(np.diff(out, 2)) > LIMIT))
    check(f"a tone through it, its sound card {'as fast as the clock' if speed == '1.0' else 'running fast'}"
          f"{', paused and on again' if pause else ', kept waiting a moment'}: kept in step ({drift:+.1f} ms) without "
          f"a click ({clicks})",
          clicks == 0 and abs(drift) < P.PARTY_SLACK * 1000 + 1)
os.environ["PATH"] = was_path

# ---- two Pietatos ------------------------------------------------------------------------------------------------------
SONGS = [HOME + "/Music/One.wav", HOME + "/Music/Two.wav"]
for p in SONGS:
    ramp(p, 25)
os.environ["HOME"] = HOME
g.STATE_FILE = S + "/gpi.json"; g.CACHE_DIR = S + "/gpicache"; g.PLEX_FILE = S + "/plex.json"
g.GROUP_LOG = S + "/gpigroup.json"
g.home_dir = lambda: HOME
import gk_static; gk_static.use_home(g, HOME)
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "", "returncode": 0, "stderr": ""})()
spawned = []


class Proc:
    def __init__(self):
        self.stdin = open(os.devnull, "w")
        self.stdout, self.stderr = iter(()), iter(())
        self.returncode, self.args = None, []

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = 0
        return 0

    def kill(self):
        self.returncode = -9


def spawn(self, args, target):
    self.started = time.monotonic()
    self.proc = Proc()
    spawned.append((target, list(args)))


g.PlayerScreen.spawn = spawn


class FB:
    w, h = 640, 480
    def show(self, img): pass
    def show_part(self, img, box): pass
    def invalidate(self): pass
    def close(self): pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.set_setting("name", "gpi")
m.volume = 100                                         # (as loud as it goes: each sample says where in the song it is)
toasts = []
was_toast = m.toast
m.toast = lambda text, secs=4: (toasts.append(text), was_toast(text, secs))[1]
control = g.Control()
server = g.serve_control(m, control, port=0, key="k" * 32)
open(S + "/control-key", "w").write("k" * 32)
sys.path.append(ROOT + "/pitato")
import webui
webui.HOME = HOME
webui.STATIC = S + "/gpistatic"
os.makedirs(webui.STATIC + "/fonts")
webui.STATE_FILE = g.STATE_FILE
webui.CONTROL = ("127.0.0.1", server.server_address[1])
webui.CONTROL_KEY = S + "/control-key"
import logging; logging.getLogger("werkzeug").setLevel(logging.ERROR)
from werkzeug.serving import make_server
web = make_server("127.0.0.1", 0, webui.app, threaded=True)
threading.Thread(target=web.serve_forever, daemon=True).start()
MINE = f"http://127.0.0.1:{web.server_port}"


def pump(secs=0.0, until=None):
    """This one's main loop, a while: what the TV's web page asked of it, done; its ticks."""
    end = time.time() + secs
    while True:
        for job in control.take():
            try:
                out = m.web_command(job["cmd"])
            except Exception as ex:
                out = {"error": repr(ex)}
            control.done(job, out)
        while m.soon_jobs:
            m.soon_jobs.popleft()()
        if m.party is not None:
            m.party_tick(time.monotonic())
        if (until is not None and until()) or time.time() > end:
            return until() if until is not None else None
        time.sleep(0.02)


LOG = S + "/tv.log"
open(LOG, "w").close()
env = dict(os.environ, FAKE_APLAY_LOG=S + "/tvsound.log", FAKE_APLAY_SPEED_X="1.003")   # (the TV's sound card)
tv = subprocess.Popen([sys.executable, TESTS + "/peer_pietato.py", TV, LOG, "tv", MINE, "gpi"],
                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1, env=env)
line = tv.stdout.readline().split()
if line[:1] != ["READY"]:
    print("FAIL the TV's Pietato didn't start", line)
    sys.exit(1)
THEIRS = line[1]
m.pie.heard[THEIRS] = {"host": "tv", "seen": time.time() + 3600, "peer": True}
reply = []


def tv_do(text):
    """Said to the TV (waiting for its answer on a thread: this one's main loop goes on meanwhile)."""
    t = threading.Thread(target=lambda: (tv.stdin.write(text + "\n"), tv.stdin.flush(),
                                         reply.append(tv.stdout.readline().strip())), daemon=True)
    n = len(reply)
    t.start()
    pump(10, lambda: len(reply) > n)
    return reply[-1] if len(reply) > n else ""


def tv_state():
    return json.loads(tv_do("state") or "{}")


def tv_said(key, since=0):
    rows = [json.loads(x) for x in open(LOG).read().splitlines()[since:] if x.strip()]
    hits = [r for r in rows if key in r]
    return hits[-1] if hits else None


tv_do("set volume 100")
os.environ["FAKE_APLAY_LOG"], os.environ["FAKE_APLAY_SPEED_X"] = S + "/gpisound.log", "1.0"
queue = [g.item(p, os.path.basename(p)[:-4], "audio", p) for p in SONGS]
m.play(queue, 0)
check("a song plays here (on its own player)", spawned and spawned[-1][0] == SONGS[0] and m.view == "now")
m.media_home()
items = m.media_menu_items()
check(f"HOME on Now playing: Party mode, in its menu ({items})", ("party", "Party mode") in items)
m.media_menu["sel"] = [k for k, _ in items].index("party")
done = threading.Event()
threading.Thread(target=lambda: (m.press("a"), done.set()), daemon=True).start()
pump(15, done.is_set)
st = tv_state()
check(f"...picked: the TV's asked, and it's in ({toasts[-1:]}; the TV: {st.get('party')})",
      m.party_leading() and list(m.party["members"].values()) == ["tv"] and toasts[-1] == "Party mode with tv"
      and (st.get("party") or {}).get("with") == "gpi")
pump(1.0)
st = tv_state()
check(f"...the TV's set its clock against this one's ({st['party']['offset']})",
      st["party"]["offset"] is not None and abs(st["party"]["offset"]) < 0.005)
check(f"...the song again, on a party player here ({type(m.proc).__name__}) and there ({st['playing']}, "
      f"{st['cur']!r})", type(m.proc).__name__ == "PartyProc" and st["playing"] == "PartyProc" and st["cur"] == "One")
at = m.proc.player.anchor[0]
pump(at - time.monotonic() + 5.0)
mine, theirs = lag(S + "/gpisound.log", at, pos=m.proc.player.pos0, after=1.0), \
    lag(S + "/tvsound.log", at, pos=m.proc.player.pos0, after=1.0)
check(f"...both heard where the clock says, the TV's from this one's web page (here {mine}; the TV {theirs})",
      None not in mine + theirs and abs(mine[0] - theirs[0]) < 5 and max(mine[1], theirs[1]) < 40)
pause_at = time.monotonic()
m.view = "now"
m.press("a")
pump(1.5)
st = tv_state()
check(f"A here: both paused ({m.paused}, {st['paused']})", m.paused and st["paused"] and m.proc.player.paused())
tv_do("press start")                                   # (the TV's Now playing, from its home screen)
tv_do("press a")
pump(1.5)
st = tv_state()
check(f"A on the TV: both play on ({m.paused}, {st['paused']})", not m.paused and not st["paused"]
      and not m.proc.player.paused())
tv_do("press r")
pump(1.0)
st = tv_state()
check(f"R on the TV: both on to the next song ({m.cur['title']!r}, {st['cur']!r})", m.cur["title"] == "Two"
      and st["cur"] == "Two" and type(m.proc).__name__ == "PartyProc")
at = m.proc.player.anchor[0]
pump(at - time.monotonic() + 3.0)
mine, theirs = lag(S + "/gpisound.log", at, after=1.0), lag(S + "/tvsound.log", at, after=1.0)
check(f"...in step there too (here {mine}; the TV {theirs})", None not in mine + theirs
      and abs(mine[0] - theirs[0]) < 5)

# ---- a song from the web (as the Internet Archive's are): each takes it from there -------------------------------------
os.makedirs(S + "/web")
ramp(S + "/web/Three.wav", 25)


class Songs(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=S + "/web", **k)

    def log_message(self, *a):
        pass


songs = ThreadingHTTPServer(("127.0.0.1", 0), Songs)
threading.Thread(target=songs.serve_forever, daemon=True).start()
THREE = f"http://127.0.0.1:{songs.server_port}/Three.wav"
m.play([g.item(THREE, "Three", "audio", THREE)], 0)
pump(1.0)
st = tv_state()
check(f"a song from the web, in the party: each takes it from there (here {m.proc.player.src}; the TV "
      f"{st['party_src']})", type(m.proc).__name__ == "PartyProc" and m.proc.player.src == THREE
      and st["party_src"] == THREE and st["cur"] == "Three")
at = m.proc.player.anchor[0]
pump(at - time.monotonic() + 3.0)
mine, theirs = lag(S + "/gpisound.log", at, after=1.0), lag(S + "/tvsound.log", at, after=1.0)
check(f"...in step (here {mine}; the TV {theirs})", None not in mine + theirs and abs(mine[0] - theirs[0]) < 5)

# ---- a station, passed on by this one ------------------------------------------------------------------------------
LOUD = S + "/loud.mp3"                                 # (a tone getting louder and louder, then quiet again, and again:
real_run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i",   # what's heard when, from how loud)
                "aevalsrc=0.5*mod(t\\,1.3)/1.3*sin(2*PI*440*t):s=48000:d=40", "-ac", "2", "-b:a", "128k", LOUD],
               check=True)
radio = ThreadingHTTPServer(("127.0.0.1", 0), Station)
radio.audio = open(LOUD, "rb").read()
threading.Thread(target=radio.serve_forever, daemon=True).start()
it = {"title": "Pretend FM", "sub": "", "src": f"http://127.0.0.1:{radio.server_port}/live", "kind": "radio"}
m.play([it], 0)
st = tv_state()
check(f"a station, in the party: passed on by this one ({m.party['relay'] and m.party['relay'].url}), both playing it "
      f"({type(m.proc).__name__}, {st['playing']} {st['cur']!r})", m.party["relay"] is not None
      and type(m.proc).__name__ == "PartyProc" and st["playing"] == "PartyProc" and st["cur"] == "Pretend FM"
      and m.proc.player.src.startswith(f"http://127.0.0.1:{P.PARTY_PORT}/station?"))
at = m.proc.player.anchor[0]
pump(at - time.monotonic() + 6.0)


def envelope(log, t0, t1):
    """How loud it was, each 10 ms from t0 to t1."""
    h = [(t, loud) for t, _, loud in heard(log) if t0 <= t <= t1]
    ts = np.arange(t0, t1, 0.01)
    return np.interp(ts, [t for t, _ in h], [x for _, x in h]) if len(h) > 10 else None


mine, theirs = envelope(S + "/gpisound.log", at + 1.0, at + 5.5), envelope(S + "/tvsound.log", at + 1.0, at + 5.5)
best = None
if mine is not None and theirs is not None:
    mine, theirs = mine - mine.mean(), theirs - theirs.mean()
    scores = {k: float(np.dot(mine[max(0, k):len(mine) + min(0, k)], theirs[max(0, -k):len(theirs) - max(0, k)]))
              for k in range(-30, 31)}
    best = max(scores, key=scores.get) * 10
check(f"...the same sound heard on both at the same moment ({best} ms apart, to the nearest 10)",
      best is not None and abs(best) <= 10)

# ---- the TV leaves (HOME's menu there) -------------------------------------------------------------------------------
tv_do("mediahome")                                     # (on the TV's Now playing)
st = tv_state()
check(f"on the TV, HOME's menu on Now playing: Leave the party ({st.get('media_menu')})",
      st.get("media_menu") == ["back", "party"])
tv_do("press down")
tv_do("press a")
pump(6, lambda: m.party is None)
check(f"...picked: the party's over here, nobody left in it ({toasts[-1:]})", m.party is None
      and toasts[-1] == "Your other Pietatos left the party")
st = tv_state()
check(f"...the TV's stopped ({st['playing']}), and this one plays on, on its own player ({spawned[-1][0]})",
      st["playing"] is None and st["party"] is None and spawned[-1][0].startswith("http://127.0.0.1:")
      and type(m.proc).__name__ == "Proc")

# ---- ended from here -----------------------------------------------------------------------------------------------
m.play(queue, 0)
m.media_home()
m.media_menu["sel"] = [k for k, _ in m.media_menu_items()].index("party")
done = threading.Event()
threading.Thread(target=lambda: (m.press("a"), done.set()), daemon=True).start()
pump(15, done.is_set)
check("party mode again", m.party_leading() and type(m.proc).__name__ == "PartyProc")
since = len(open(LOG).read().splitlines())
m.media_home()
items = m.media_menu_items()
check(f"...HOME's menu here: End party mode ({items})", items == [("back", "Back to the music"),
                                                                   ("party", "End party mode")])
m.media_menu["sel"] = 1
m.press("a")
pump(2)
st = tv_state()
check(f"...picked: the TV stops, and says so ({tv_said('toast', since)})", st["playing"] is None and st["party"] is None
      and tv_said("toast", since) == {"toast": "gpi's party is over"})
check(f"...this one plays on, on its own player, from where it was ({spawned[-1]})", m.party is None
      and spawned[-1][0] == SONGS[0] and type(m.proc).__name__ == "Proc" and toasts[-1] == "Party mode's over")

# ---- this one in another's party, with a game on here ---------------------------------------------------------------
m.stop()
token = "p" * 22
said = m.web_party({"from": "127.0.0.1", "kind": "start", "token": token, "port": P.PARTY_PORT})
check(f"this one asked to join the TV's party: it's in ({said})", said == {"ok": True} and m.party_on()
      and not m.party_leading() and m.party["name"] == "tv")
m.game = type("Run", (), {"attract": False, "ended": False})()     # (a game started here meanwhile)
said = m.web_party({"from": "127.0.0.1", "kind": "play", "token": token, "at": time.monotonic() + 2.0, "pos": 0,
                    "item": {"kind": "audio", "title": "One"}, "src": {"web": "/api/handoff/file?token=" + "x" * 22}})
check(f"...a game on here when the party's next song comes: it isn't played over the game, and this one leaves the "
      f"party ({said})", said == {"ok": False, "error": "It's playing a game"} and m.party is None
      and type(m.proc).__name__ != "PartyProc")
m.game = None
tv_do("quit")
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
