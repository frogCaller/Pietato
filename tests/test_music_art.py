"""Music's cover art. A song's cover: the picture named for it in its folder, else the one inside its file (FFmpeg gets
it out once, kept in the cache, and a song with none isn't looked into twice), else the only picture in its folder;
the colour its glow takes (the one there's most of, not a stir of them all; none from a grey cover). The ear: beats
found a moment ahead of what's heard, kept by their place in the song, a jump starting it again, the glow dying away
after each. Now playing: the cover on the left with its glow, a wash of it behind, the words, the line in the cover's
colour, the buttons (each tappable); a note for a song with no cover, a sign for a station; the glow following the
beat with the battery saver off (just its box drawn, between whole pages), still with it on, paused, on lofi art, off
the page. Music's grid: every song a square with its cover (made small once and kept on disk, a folder's shared
by its songs), its name and its folder's under it, the picked one bigger with a glow, the D-pad moving about it, A
playing as before, only the covers near the screen looked at, another tab still a list. Covers from the internet
(Y on the grid): who a song's by from its tags or its file's name, MusicBrainz asked which record it's on (the sure
match only, no compilation's, never more than a question a second), the Cover Art Archive for its picture, a
record's songs sharing one, what isn't found not asked about again for a month, the WiFi down said. A light page,
and a screen drawn finely. Last, for real: FFmpeg listening to a song with a kick drum every half second."""
import io, os, shutil, subprocess, sys, threading, time, types
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import numpy as np
import pietato_all as g
from PIL import Image, ImageDraw
from pitato import cover as C, ear as E, fine
from pitato.screens import music as M

S = SP + "/tmusicart"
shutil.rmtree(S, ignore_errors=True)
ALBUM, LOOSE, ONE = S + "/home/u/Music/Low Tide", S + "/home/u/Music/Loose", S + "/home/u/Music/One Picture"
for folder in (ALBUM, LOOSE, ONE):
    os.makedirs(folder)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: S + "/home/u"
g.wifi_quality = lambda: 62.0
g.cpu_temp = lambda: 48.0
ok_all = []
real_run, real_clock = subprocess.run, time.monotonic


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def near(a, b, by=40):
    return all(abs(int(x) - int(y)) <= by for x, y in zip(a, b))


def picture(path, kind):
    """A made-up cover: a sun over the sea (orange, and some blue), green hills, or a grey one."""
    n = 600
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32) / n
    if kind == "sun":
        a = np.array([252, 150, 60.0]) + (np.array([200, 96, 60.0]) - np.array([252, 150, 60.0])) * yy[..., None]
        im = Image.fromarray(a.astype(np.uint8))
        d = ImageDraw.Draw(im)
        d.ellipse((190, 150, 410, 370), fill=(255, 226, 170))
        d.rectangle((0, 470, n, n), fill=(30, 60, 150))
    elif kind == "hills":
        a = np.zeros((n, n, 3), np.float32)
        a[..., 0], a[..., 1], a[..., 2] = 40 + 30 * xx, 170 + 50 * yy, 110
        im = Image.fromarray(a.astype(np.uint8))
    else:
        im = Image.fromarray((np.dstack([xx, xx, xx]) * 255).astype(np.uint8))
    im.save(path, quality=92)


picture(ALBUM + "/Cover.JPG", "sun")
picture(ALBUM + "/back of the sleeve.jpg", "grey")
picture(S + "/hills.jpg", "hills")
picture(ONE + "/scan.png", "hills")
TONE = S + "/tone.wav"                                 # (a kick drum every half second, and a quiet note over it)
real_run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
          "aevalsrc=0.6*sin(2*PI*60*t)*exp(-12*mod(t\\,0.5))+0.1*sin(2*PI*440*t):s=48000:d=12", TONE], check=True)
SONG, INSIDE, BARE, LONE = ALBUM + "/03 Harbour Lights.mp3", LOOSE + "/Green Hours.mp3", LOOSE + "/demo.mp3", \
    ONE + "/only.mp3"
for out in (SONG, BARE, LONE):
    real_run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", TONE, "-b:a", "96k", out], check=True)
real_run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", TONE, "-i", S + "/hills.jpg", "-map", "0:a", "-map",
          "1:v", "-c:v", "mjpeg", "-disposition:v", "attached_pic", "-id3v2_version", "3", "-b:a", "96k", INSIDE],
         check=True)

# ---- a song's cover ---------------------------------------------------------------------------------------------
check(f"the picture named for it in the song's folder, whatever its capitals ({os.path.basename(C.beside(SONG))})",
      C.beside(SONG) == ALBUM + "/Cover.JPG" and C.beside(BARE) is None)
check("...the only picture in a folder: only when that's asked for; two pictures, neither named: none",
      C.beside(LONE) is None and C.beside(LONE, only=True) == ONE + "/scan.png"
      and C.beside(SONG, only=True) is None)
runs = []


def counted(args, **kw):
    runs.append(args)
    return real_run(args, **kw)


C.subprocess.run = counted
got = C.cover_file(INSIDE)
im = Image.open(got)
check(f"the picture inside a song's file: got out with FFmpeg, kept in the cache ({im.size}, {im.format})",
      got.startswith(S + "/cache/covers/") and got.endswith(".jpg") and im.format == "JPEG" and max(im.size) == 600
      and len(runs) == 1 and near(im.convert("RGB").getpixel((300, 300)), (55, 195, 110)))
check("...and the next time it's there already: no FFmpeg", C.cover_file(INSIDE) == got and len(runs) == 1)
check("a song with no picture inside it, in a folder with none: no cover, and it's looked into once",
      C.cover_file(BARE) is None and C.cover_file(BARE) is None and len(runs) == 2
      and sum(n.endswith(".none") for n in os.listdir(S + "/cache/covers")) == 1)
check("...one whose folder has just the one picture: that", C.cover_file(LONE) == ONE + "/scan.png")
check("the named one in its folder comes first: its file isn't looked into at all",
      C.cover_file(SONG) == ALBUM + "/Cover.JPG" and len(runs) == 3)
check("a song that isn't a file here (a web address, one that's gone): no cover, nothing run",
      C.cover_file("http://10.0.0.5/a.mp3") is None and C.cover_file(S + "/gone.mp3") is None and len(runs) == 3)
big = S + "/big.mp3"
picture(S + "/huge.png", "sun")
Image.open(S + "/huge.png").resize((1400, 900)).save(S + "/huge.png")
real_run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", TONE, "-i", S + "/huge.png", "-map", "0:a", "-map",
          "1:v", "-c:v", "png", "-disposition:v", "attached_pic", "-id3v2_version", "3", "-b:a", "96k", big],
         check=True)
os.makedirs(S + "/out", exist_ok=True)
check("a big one inside (1400 x 900, a PNG): kept 600 across, its shape as it was",
      C.inside(big, S + "/out/big.jpg") and Image.open(S + "/out/big.jpg").size in ((600, 386), (600, 385)))
check("...FFmpeg not there, or a file that isn't a song: no cover, nothing left behind",
      not C.inside(big, S + "/out/no.jpg", run=lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
      and not C.inside(S + "/hills.jpg" + ".nope", S + "/out/no2.jpg")
      and sorted(os.listdir(S + "/out")) == ["big.jpg"])
C.subprocess.run = real_run
os.makedirs(S + "/many")
for k in range(12):
    open(S + f"/many/{k:02d}.jpg", "w").close()
    os.utime(S + f"/many/{k:02d}.jpg", (1000 + k, 1000 + k))
os.utime(S + "/many/03.jpg")                           # (one of the old ones, used just now)
C.tidy(S + "/many", most=5)
check(f"the cache kept to so many: the ones not used for longest go ({sorted(os.listdir(S + '/many'))})",
      sorted(os.listdir(S + "/many")) == ["03.jpg", "08.jpg", "09.jpg", "10.jpg", "11.jpg"])
sun = C.cover_colour(Image.open(ALBUM + "/Cover.JPG"))
hills = C.cover_colour(Image.open(S + "/hills.jpg"))
check(f"the glow's colour: the one there's most of ({sun}: orange, with no blue stirred in; the hills' {hills})",
      sun[0] > 200 and sun[0] > sun[1] > sun[2] and sun[2] < 120 and hills[1] > 200 and hills[1] > hills[0] + 60)
check("...as bright as a glow is, and none from a grey cover", max(sun) >= 208 and max(hills) >= 208
      and C.cover_colour(Image.open(ALBUM + "/back of the sleeve.jpg")) is None)
wash = C.cover_wash(Image.open(ALBUM + "/Cover.JPG"), (640, 400), (17, 19, 24), sun)
top, foot = wash.getpixel((320, 20)), wash.getpixel((320, 390))
check(f"its wash: the page's colour with some of the cover's, top to bottom ({top}, {foot})", wash.size == (640, 400)
      and top[0] > foot[0] + 20 and foot[2] > top[2] - 5 and max(top) < 140)
plain = C.cover_wash(None, (640, 400), (17, 19, 24), (96, 170, 228))
check("...with no cover: the page's colour, a little of the glow's at the top", plain.getpixel((5, 398))
      == (17, 19, 24) and plain.getpixel((5, 0))[2] > 40)
steps = [C.glow_step(v) for v in (0.0, 0.07, 0.5, 1.0, 3.0, -1.0)]
check(f"the glow's steps: {steps}, lit {C.glow_strength(0):.2f} at rest to {C.glow_strength(C.GLOW_STEPS - 1):.2f}",
      steps == [0, 0, 4, 7, 7, 0] and C.glow_strength(0) == C.GLOW_REST and C.glow_strength(C.GLOW_STEPS - 1) == 1.0)

# ---- the ear -----------------------------------------------------------------------------------------------------
RATE = E.EAR_RATE


def kicks(start, secs):
    """What FFmpeg would give of a song with a kick on every half second, from start on (s16le stereo)."""
    t = start + np.arange(int(secs * RATE)) / RATE
    wave = 0.6 * np.sin(2 * np.pi * 60 * t) * np.exp(-12 * np.mod(t, 0.5)) + 0.05 * np.sin(2 * np.pi * 440 * t)
    return np.repeat((wave * 32767).astype("<i2"), 2).tobytes()


started = []


class Decoder:
    """A pretend FFmpeg: the song from where it's asked for, as fast as it's read."""

    def __init__(self, args, **kw):
        self.at = float(args[args.index("-ss") + 1])
        started.append(self.at)
        self.stdout = io.BytesIO(kicks(self.at, 30.0 - self.at))
        self.killed = False

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return 0


place = [None]
ear = E.Ear("/music/kicks.mp3", lambda: place[0], run=False, popen=Decoder)
check("the ear, before the player's said where the song is: nothing listened to", not ear.step() and started == []
      and ear.level(None) == 0.0)
place[0] = 2.0
n = 0
while ear.step():
    n += 1
found = [round(p, 2) for p, _ in ear.beats]
check(f"the song at 2.0 s: listened to from there, {E.EAR_AHEAD} s ahead and no further ({ear.at:.2f}, in {n} goes)",
      started == [2.0] and E.EAR_AHEAD <= ear.at - 2.0 <= E.EAR_AHEAD + E.EAR_STEP + 0.01 and n in (12, 13))
while place[0] < 4.0:                                  # (the song plays on, and it's asked as it does)
    place[0] = round(place[0] + 0.05, 2)
    while ear.step():
        pass
found = [round(p, 2) for p, _ in ear.beats]
check(f"...on as the song goes on: its beats, each by its place in the song ({found})", started == [2.0]
      and all(abs(p * 2 - round(p * 2)) < 0.08 for p in found) and len(found) >= 3 and max(found) > 4.0)
beat = max(p for p in found if p <= 4.01)
lv = [ear.level(beat - 0.02), ear.level(beat + 0.03), ear.level(beat + 0.2), ear.level(beat + 0.45)]
check(f"the glow at a beat: little left of the one before, lit on it, dying away after "
      f"({[round(v, 2) for v in lv]})", lv[0] < 0.2 and lv[1] > 0.45 and lv[1] > lv[2] > lv[3] and lv[3] < 0.15)
place[0] = 3.2
check("a little way back, in what it's listened to already: no need to start again", not ear.step()
      and started == [2.0])
first = ear.proc
place[0] = 20.0
ear.step()
check("a jump on: the first FFmpeg stopped, another from there, the old beats let go", started == [2.0, 20.0]
      and first.killed and all(p >= 20.0 for p, _ in ear.beats))
place[0] = 1.0
ear.step()
check("...and a jump back past where it began", started == [2.0, 20.0, 1.0])
place[0] = 29.5
ear.step()
while ear.step():
    pass
check("the end of the song: nothing more to listen to, and no fuss", ear.ended and not ear.step())
ear.close()
ear.stop()
check("closed: its FFmpeg stopped", ear.proc is None and ear.closed)
broke = E.Ear("/music/kicks.mp3", lambda: 1.0, run=False,
              popen=lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
check("no FFmpeg: no beats, the glow still, and it isn't tried again and again", not broke.step() and not broke.step()
      and broke.level(1.0) == 0.0)

# ---- Now playing --------------------------------------------------------------------------------------------------
class FB:
    same = True
    count = 0

    def __init__(self, w=640, h=480):
        self.w, self.h = w, h
        self.last, self.shows, self.parts = None, 0, []

    def show(self, img):
        self.last = img.copy(); self.shows += 1; FB.count += 1; self.frames = FB.count

    def show_part(self, img, box):
        self.parts.append(tuple(box)); self.last = img.copy(); FB.count += 1; self.frames = FB.count

    def close(self):
        pass


fake = [1000.0]
g.time.monotonic = lambda: fake[0]
MUSIC = next(i for i, t in enumerate(g.LIBRARY) if t["name"] == "Music")
SONGS = [ALBUM + f"/0{k} Song.mp3" for k in (1, 2)] + [SONG, INSIDE, BARE]
for p in SONGS[:2]:
    shutil.copy(SONG, p)


def media(w=640, h=480, scale=1, look="Dark"):
    fine.set_scale(scale)
    m = g.Media(); m.fonts = None; m.load_fonts(); m.fb = FB(w, h); m.active = True
    m.save_state = lambda: None
    g.set_look(look)
    m.status_sig = m.status_signature()
    m.said = []
    m.to_player = lambda line: m.said.append(line)
    m.proc = types.SimpleNamespace(poll=lambda: None, stdin=io.StringIO())
    m.items[MUSIC] = [g.item(p, g.title_of(p), "audio", p) for p in SONGS]
    m.tab = MUSIC
    m.state["settings"]["battery"] = "On"
    return m


def playing(m, i, title="", artist="", album="", pos=84.0, length=238.0):
    items = m.items[MUSIC]
    m.queue, m.qi, m.cur, m.kind = items, i, items[i], "audio"
    m.meta = {k: v for k, v in (("title", title), ("artist", artist), ("album", album), ("length", length)) if v}
    m.pos, m.shuffle, m.paused = pos, False, False
    m.view, m.now_from = "now", "list"


gate = threading.Event()                               # (shut: a cover that's looked for isn't found yet)
real_cover_file = M.cover_file
M.cover_file = lambda path: (gate.wait(10), real_cover_file(path))[1]


def found(m, secs=8.0):
    """The covers wanted, found (the thread that looks, done); the next one looked for waits again."""
    gate.set()
    end = time.time() + secs
    while m.cover_busy and time.time() < end:
        real_sleep(0.02)
    gate.clear()
    return not m.cover_busy


real_sleep = time.sleep


def shot(m, name=None):
    m.dirty = True
    m.flush()
    im = m.fb.last
    im = im.pic if hasattr(im, "pic") else im
    if name:
        im.save(f"{SP}/out/{name}.png")
    return np.asarray(im.convert("RGB")).astype(int)


def words(m):
    """(Every word drawn on the page, as the last picture has them: looked for where they go.)"""
    return m.now_words(m.cur)


m = media()
playing(m, 2, "Harbour Lights", "The Night Ferries", "Low Tide")
lay = m.now_layout()
ax, ay, side = lay["ax"], lay["ay"], lay["side"]
a0 = shot(m)
check(f"Now playing, the cover not found yet: a note in its square ({side} px, at {ax}, {ay}), the accent's glow",
      m.cover_for(m.cur) is None and near(a0[ay + 6, ax + side // 2], g.ROW, 6)
      and (np.abs(a0[ay + 40:ay + side - 40, ax + 40:ax + side - 40] - np.array(g.ACCENT)).max(axis=2) < 40).any())
check("...and it's found", found(m) and m.cover_for(m.cur)[0] is not None and m.dirty)
a = shot(m, "now")
sun_at = a[ay + int(side * 0.43), ax + side // 2]
check(f"the cover's on the page: its sun in the middle {tuple(sun_at)}, its sea at the foot, its corners rounded",
      near(sun_at, (255, 226, 170), 16) and near(a[ay + side - 12, ax + side // 2], (30, 60, 150), 30)
      and not near(a[ay + 1, ax + 1], a[ay + 12, ax + 12], 12))
colour = m.now_made[1]["colour"]
out, far = a[ay + side // 2, ax - 5], a[ay + side // 2, ax - C.GLOW_REACH - 8 if ax > C.GLOW_REACH + 8 else 2]
check(f"its glow, in its colour {colour}: beside it {tuple(out)}, gone a little further out {tuple(far)}",
      colour == sun and out[0] > far[0] + 25 and out[0] > out[2] + 40)
check("a wash of it behind the page (not the plain page), up behind the status bar too",
      not near(a[200, 600], g.BG, 6) and not near(a[8, 320], g.BG, 6) and a[200, 600].max() < 120)
check("...the buttons along the bottom on the page's own colour, as ever", near(a[470, 320], g.BG, 2))
bar = lay["bar"]
frac = ax + (640 - 2 * ax) * 84 / 238
line, rest = a[bar + 2, int(frac) - 20], a[bar + 2, int(frac) + 30]
check(f"the line of how far through: in the cover's colour as far as it's got {tuple(line)}, then empty {tuple(rest)}",
      near(line, colour, 12) and not near(rest, colour, 60))
tx = lay["tx"]


def ink(a, box, colour, by=40):
    """Some of what's drawn in box is this colour."""
    x0, y0, x1, y1 = box
    return bool((np.abs(a[y0:y1, x0:x1] - np.array(colour)).max(axis=2) < by).any())


check(f"what's playing, who by, the record, beside the cover ({words(m)})", words(m) == (
    "Harbour Lights", "The Night Ferries", "Low Tide", "Track 3 of 5") and ink(a, (tx, ay + 6, 620, ay + 34), g.TEXT)
    and ink(a, (tx, ay + 40, 620, ay + 68), g.BODY) and ink(a, (tx, ay + 70, 620, ay + 92), g.BODY)
    and not ink(a, (tx, ay + 100, 620, ay + side - 60), g.TEXT, 30))
def drawn_buttons(m):
    """The buttons drawn under the line (not the hints along the bottom): what a tap on each presses, and where."""
    return {what[1]: box for box, what in m.taps if what[0] == "keys" and bar < box[1] and box[3] <= 480 - m.FOOTER}


taps = drawn_buttons(m)
keys = lay["keys"]
check(f"the buttons under the line, each tappable: {sorted(k for k in taps if len(k) < 3)}",
      all(k in taps for k in ("a", "l", "r", "y")) and taps["a"][0] < 320 < taps["a"][2]
      and taps["l"][2] <= taps["a"][0] and taps["r"][0] >= taps["a"][2] and taps["y"][2] < taps["l"][0]
      and near(a[keys, 320 - 18], g.TEXT, 8) and near(a[keys, 320 - 6], g.BG, 8))
m.paused = True
p = shot(m)
check("paused: the middle one's a triangle (play)", near(p[keys, 320 - 2], g.BG, 8) and near(p[keys, 320 + 6], g.BG, 8)
      and near(p[keys - 9, 320 + 8], g.TEXT, 8))
m.paused = False
m.shuffle = True
sh = shot(m)
check("shuffle on: its drawing lit in the cover's colour (off: not)",
      ink(sh, (ax, keys - 12, ax + 34, keys + 12), colour, 30)
      and not ink(a, (ax, keys - 12, ax + 34, keys + 12), colour, 30))
m.shuffle = False
for key, did in (("a", "pause"), ("right", "seek 10 0"), ("l", None)):
    m.said.clear()
    skipped = []
    m.skip = lambda d: skipped.append(d)
    m.press(key)
    check(f"{key}: as before ({m.said or skipped})", (did in m.said) if did else skipped == [-1])
del m.skip
m.paused = False
m.press("b")
check("B: the list", m.view == "list")
m.view = "now"

# a song with its picture inside it, one with none, a station
playing(m, 3, "Green Hours", "Paper Lanterns")
shot(m)
found(m)
b = shot(m, "now_inside")
check(f"the next song: its own cover and colour {m.now_made[1]['colour']}, the line in it",
      m.now_made[1]["colour"] == hills and near(b[ay + side // 2, ax + side // 2], (55, 195, 110), 24)
      and near(b[bar + 2, ax + 30], hills, 12))
playing(m, 4)
shot(m)
found(m)
c = shot(m, "now_none")
check(f"a song with no cover: a note in its square, the accent's glow and line, its folder under its name "
      f"({words(m)})", m.cover_for(m.cur) == (None, None) and m.now_made[1]["colour"] == g.ACCENT
      and words(m)[:3] == ("demo", "Loose", "") and near(c[ay + 6, ax + side // 2], g.ROW, 6)
      and near(c[bar + 2, ax + 30], g.ACCENT, 12))
station = {"title": "Pretend FM", "src": "http://10.0.0.9/live", "sub": "Jazz", "kind": "radio", "key": "r1"}
m.queue, m.qi, m.cur, m.kind, m.meta = [station], 0, station, "radio", {"song": "Somebody - A Song"}
r = shot(m, "now_radio")
taps = drawn_buttons(m)
check(f"a station: its sign, LIVE, what's on, no line and no shuffle ({words(m)}; taps {sorted(taps)})",
      words(m) == ("Pretend FM", "Somebody - A Song", "", "Station 1 of 1") and "y" not in taps and "left" in taps
      and not ink(r, (ax, bar, 600, bar + 6), g.ACCENT, 20) and ink(r, (tx, ay + 8, tx + 60, ay + 30), g.ACCENT))

# ---- the glow, following the beat -----------------------------------------------------------------------------
playing(m, 2, "Harbour Lights", "The Night Ferries", "Low Tide")
shot(m)
found(m)
shot(m)
made = []


class PretendEar:
    def __init__(self, src, where):
        self.src, self.where, self.closed, self.lit = src, where, False, 0.0
        made.append(self)

    def level(self, place):
        return self.lit if place is not None else 0.0

    def close(self):
        self.closed = True


M.Ear = PretendEar
m.tick()
check("the battery saver on: no ear for the beat, the glow still, the loop waiting as it does",
      not m.pulse_wanted() and m.ear is None and made == [] and m.tick_limit() == 0.25)
m.state["settings"]["battery"] = "Off"
m.tick()
check("the battery saver off: an ear for the song that's playing", m.pulse_wanted() and len(made) == 1
      and made[0].src == SONG and m.ear is made[0])
m.next_query = 1e12                                    # (the player isn't asked where it is, for now: said here)
m.pos_said(84.0)
at0 = m.heard_now()
fake[0] += 0.4
check(f"where the song is, between the player's words on it ({at0:.2f}, then {m.heard_now():.2f} a moment on)",
      abs(at0 - 84.0) < 1e-6 and abs(m.heard_now() - 84.4) < 1e-6)
fake[0] += 0.6
m.pos_said(85.1)                                       # (its word's to a tenth: evened out, not jumped to)
check(f"...the player's next word a tenth out: evened out ({m.heard_now():.3f})", 85.0 < m.heard_now() < 85.05)
m.pos_said(120.0)
check("...and a jump (a seek): taken as it says", abs(m.heard_now() - 120.0) < 1e-6)
box = m.now_made[1]["box"]
shot(m)
m.fb.parts.clear(); m.fb.shows = 0
m.pulse_next = 0.0
m.tick()
check("no beat: nothing drawn", m.fb.parts == [] and m.fb.shows == 0)
made[0].lit = 1.0
fake[0] += 0.1
m.tick()
lit = np.asarray(m.fb.last.convert("RGB")).astype(int)
out_lit = lit[ay + side // 2, ax - 5]
check(f"a beat: just the cover and its glow go to the screen {m.fb.parts}, the glow brighter beside it "
      f"({tuple(out)} to {tuple(out_lit)})", m.fb.parts == [box] and m.fb.shows == 0 and out_lit[0] > out[0] + 20
      and near(lit[ay + int(side * 0.43), ax + side // 2], (255, 226, 170), 16)
      and (lit[bar - 2:, :] == a[bar - 2:, :]).all()
      and box == (ax - C.GLOW_REACH, ay - C.GLOW_REACH, ax + side + C.GLOW_REACH, ay + side + C.GLOW_REACH))
check(f"...the loop looks again when its next frame's due ({m.tick_limit():.3f} s)",
      0 < m.tick_limit() <= 1 / 15 + 1e-6)
fake[0] += 0.02
m.tick()
check("...not before", len(m.fb.parts) == 1)
seen = []
for lv in (0.8, 0.8, 0.5, 0.2, 0.0, 0.0):
    made[0].lit = lv
    fake[0] += 0.07
    m.tick()
    seen.append(m.now_shot[2])
check(f"it dies away a step at a time, drawn only as it changes ({seen}: {len(m.fb.parts)} frames)",
      seen == [6, 6, 4, 1, 0, 0] and len(m.fb.parts) == 5 and len(m.now_made[1]["lit"]) == 5)
made[0].lit = 1.0
m.toast("Volume 60")
fake[0] += 0.07
m.tick()
check("a notice up: the glow waits (it would draw over it)", len(m.fb.parts) == 5)
m.msg = None
m.next_query = 0.0                                     # (the player asked where it is, as it is each second: the
fake[0] += 0.07                                        #  page is drawn again for its line)
m.tick()
m.flush()
check(f"the page drawn again whole (how far through it is): the glow as it is now on it ({m.said[-1:]})",
      m.fb.shows == 1 and m.now_shot[2] == 7 and len(m.fb.parts) == 5 and "get_time_pos" in m.said[-1])
m.next_query = 1e12
m.press("a")
m.flush()
fake[0] += 0.07
made[0].lit = 0.3
parts = len(m.fb.parts)
m.tick()
check("paused: the glow rests, where the song is isn't guessed at, and the loop waits as it does", m.paused
      and m.heard_now() is None and m.pulse_step() == 0 and m.pos_off is None and m.tick_limit() == 0.25)
m.press("a")
m.pos_said(121.0)
m.press("select")
m.tick()
check("lofi art on: no ear", m.now_art() and m.ear is None and made[0].closed)
m.press("select")
m.msg = None
m.tick()
check("...off again: one again", m.ear is made[1] and not made[1].closed)
m.press("b")
m.tick()
check("off Now playing (the list): the ear let go, the loop's usual wait", m.ear is None and made[1].closed
      and m.tick_limit() == 0.25)
m.view = "now"
m.tick()
m.kind, m.cur = "radio", station
m.tick()
check("a station on it: no ear", m.ear is None and made[2].closed and len(made) == 3)

# ---- Music's grid --------------------------------------------------------------------------------------------
def ready(m, secs=10.0):
    """The grid's covers, all got ready (the ones it wants now)."""
    gate.set()
    end = time.time() + secs
    while (m.cover_busy or m.music_tile_next() is not None) and time.time() < end:
        real_sleep(0.02)
    gate.clear()
    return m.music_tile_next() is None


def at(lay, i, top=0):
    """Where the grid's i-th song's cover is (its left and top)."""
    return lay["x"] + (i % lay["cols"]) * lay["dx"], lay["y"] + (i // lay["cols"] - top) * lay["dy"]


playing(m, 2, "Harbour Lights", "The Night Ferries", "Low Tide")
m.state["settings"]["battery"] = "On"
m.view = "list"
m.sels[MUSIC] = 0
gl = m.music_layout()
cols, rows, gs = gl["cols"], gl["rows"], gl["side"]
check(f"Music: a grid of its songs, {cols} across and {rows} down on this screen, each cover {gs} px, all of it "
      f"between the tabs and the buttons", m.music_grid() and (cols, rows) == (4, 2) and 110 <= gs <= 140
      and gl["y"] - M.GRID_GLOW - M.GRID_RAISED >= m.HEADER and gl["y"] + rows * gl["dy"] <= 480 - m.FOOTER
      and gl["x"] >= 20 and gl["x"] + (cols - 1) * gl["dx"] + gs <= 620)
runs.clear()
C.subprocess.run = counted
G0 = shot(m)
x1, y1 = at(gl, 1)
check("its covers not ready yet: a note in each square, and a thread getting them ready", m.tiles_busy
      and near(G0[y1 + 6, x1 + 20], g.ROW, 6) and ink(G0, (x1 + 30, y1 + 30, x1 + gs - 30, y1 + gs - 30), g.ACCENT))
check("...ready", ready(m) and m.dirty)
G = shot(m, "grid")
x3, y3 = at(gl, 3)
x4, y4 = at(gl, 4)
check("each song's cover in its square: the folder's, the one inside the file, a note for one with none",
      near(G[y1 + int(gs * 0.43), x1 + gs // 2], (255, 226, 170), 20)
      and near(G[y3 + gs // 2, x3 + gs // 2], (55, 195, 110), 24) and near(G[y4 + 6, x4 + 20], g.ROW, 6)
      and not near(G[y1 + 1, x1 + 1], G[y1 + 12, x1 + 12], 12))
thumbs = sorted(n for n in os.listdir(S + "/cache/thumbs") if f"-m{gs}." in n)
check(f"...kept on disk at the grid's size: one for the folder's cover (its three songs share it), one for the "
      f"song with its own ({len(thumbs)}); nothing looked into twice ({len(runs)} FFmpeg)", len(thumbs) == 2
      and m.song_tiles[SONGS[0]] == m.song_tiles[SONGS[1]] == m.song_tiles[SONG] != m.song_tiles[INSIDE]
      and m.song_tiles[BARE] is None and len(runs) == 0)
x0, y0 = at(gl, 0)
beside, plain = G[y0 + gs // 2, x0 - M.GRID_RAISED - 5], G[y1 + gs // 2, x1 + gs + 8]
check(f"the picked one: a little bigger, a glow in its cover's colour round it {tuple(beside)} (the others: none "
      f"{tuple(plain)})", near(G[y0 - 4, x0 + gs // 2], (250, 150, 62), 30) and beside[0] > beside[2] + 40
      and near(plain, g.BG, 4) and near(G[y1 - 4, x1 + gs // 2], g.BG, 4))
x2, y2 = at(gl, 2)
check("each one's name under it, and the folder it's in; the one that's playing marked in the accent's colour",
      ink(G, (x0, y0 + gs + 8, x0 + gs, y0 + gs + 26), g.TEXT)
      and ink(G, (x1, y1 + gs + 8, x1 + gs, y1 + gs + 26), g.BODY)
      and ink(G, (x2, y2 + gs + 8, x2 + gs, y2 + gs + 26), g.ACCENT, 30)
      and not ink(G, (x1, y1 + gs + 8, x1 + gs, y1 + gs + 26), g.ACCENT, 30)
      and ink(G, (x1, y1 + gs + 27, x1 + gs, y1 + gs + 44), g.MUTED))
taps = [(box, what) for box, what in m.taps if what[0] == "sel"]
check("a tap on a cover picks that song", [w[-1] for _, w in taps] == [0, 1, 2, 3, 4]
      and all(b[0] <= at(gl, i)[0] and b[2] >= at(gl, i)[0] + gs and b[1] <= at(gl, i)[1]
              for i, (b, _) in enumerate(taps))
      and all(taps[i][0][2] <= taps[i + 1][0][0] for i in range(3)))
moves = []
for key in ("right", "right", "right", "right", "down", "up", "left", "left", "down"):
    m.press(key)
    moves.append(m.sels[MUSIC])
check(f"the D-pad moves about it: across, down a row, up one ({moves})", moves == [1, 2, 3, 4, 4, 0, 0, 0, 4])
played = []
m.play = lambda queue, i, **k: played.append((len(queue), i))
m.press("a")
del m.play
check(f"A: that song plays, all of them after it as before ({played})", played == [(5, 4)])
m.press("start")
check("START: Now playing, as before", m.view == "now")
m.view = "list"
MANY = SONGS + [f"{LOOSE}/extra {k:02d}.mp3" for k in range(31)]
for p in MANY[5:]:
    shutil.copy(BARE, p)
m.items[MUSIC] = [g.item(p, g.title_of(p), "audio", p) for p in MANY]
m.sels[MUSIC] = 0
shot(m)
ready(m)
looked = len(m.song_tiles)
check(f"a lot of songs: only the ones on the screen and the rows just under them are looked at ({looked} of "
      f"{len(MANY)})", looked == (rows + M.GRID_AHEAD) * cols)
for _ in range(5):
    m.press("down")
D = shot(m)
check(f"down past the foot of the screen: it scrolls a row at a time (the top row's now {m.tops[MUSIC]}), the picked "
      f"one still on it", m.sels[MUSIC] == 20 and m.tops[MUSIC] == 4
      and near(D[at(gl, 20, 4)[1] + 6, at(gl, 20, 4)[0] + 20], g.ROW, 8))
ready(m)
C.subprocess.run = real_run
again = media()
again.view = "list"
shot(again)
runs.clear()
C.subprocess.run = counted
ready(again)
A2 = shot(again)
C.subprocess.run = real_run
check(f"another time: its covers come from the ones kept on disk (no FFmpeg: {len(runs)}), none made again",
      len(runs) == 0 and near(A2[y1 + int(gs * 0.43), x1 + gs // 2], (255, 226, 170), 20)
      and sorted(n for n in os.listdir(S + "/cache/thumbs") if f"-m{gs}." in n) == thumbs)
M.GRID_IDLE = 0.3
again.view = "home"
end = time.time() + 5
while again.tiles_busy and time.time() < end:
    real_sleep(0.05)
check("off the grid: the thread that gets them ready stops by itself", not again.tiles_busy)
M.GRID_IDLE = 10.0
VIDEOS = next(i for i, t in enumerate(g.LIBRARY) if t["name"] == "Videos")
m.items[VIDEOS] = [g.item(S + f"/v{k}.mp4", f"Video {k}", "video", S + f"/v{k}.mp4") for k in range(3)]
m.tab = VIDEOS
V = shot(m)
m.press("down")
check("another tab (Videos): a list, as it was", not m.music_grid() and near(V[m.list_top() + 24, 600], g.ROW, 6)
      and m.sels[VIDEOS] == 1)
m.tab = MUSIC
m.fb = FB(480, 640)
nl = m.music_layout()
check(f"a narrow screen: three across ({nl['cols']} by {nl['rows']}, {nl['side']} px)", nl["cols"] == 3
      and nl["x"] + 2 * nl["dx"] + nl["side"] <= 480 - nl["x"] + 1 and nl["rows"] >= 2)
m.items[MUSIC] = []
m.fb = FB()
E0 = shot(m)
check("no songs: the page saying so, as before", not m.music_grid() and ink(E0, (100, 180, 540, 300), g.TEXT))

# ---- covers from the internet ---------------------------------------------------------------------------------
from pitato import coverfind as CF   # noqa: E402
import json, urllib.error, urllib.parse   # noqa: E401, E402

names = {n: CF.from_name(f"/m/{n}.mp3") for n in (
    "Paper Lanterns - Green Hours", "03 Harbour Lights", "3. The Tide - Low", "99 Luftballons", "01_Artist_-_Song",
    "50 Cent - In Da Club", "12 - Somebody - A Song - Live")}
check(f"who a song's by and its name, from its file's name: {list(names.values())[:3]}", names == {
    "Paper Lanterns - Green Hours": ("Paper Lanterns", "Green Hours"), "03 Harbour Lights": ("", "Harbour Lights"),
    "3. The Tide - Low": ("The Tide", "Low"), "99 Luftballons": ("", "99 Luftballons"),
    "01_Artist_-_Song": ("Artist", "Song"), "50 Cent - In Da Club": ("50 Cent", "In Da Club"),
    "12 - Somebody - A Song - Live": ("Somebody", "A Song - Live")})
check("two names being one: marks, capitals and what's in brackets don't matter; a short one inside a longer isn't it",
      CF.same("Nevermind", "nevermind (Remastered 2011)") and CF.same("Sgt. Pepper's Lonely Hearts Club Band",
                                                                     "Sgt Peppers Lonely Hearts Club Band")
      and CF.same("Beyoncé", "Beyonce") and not CF.same("Queen", "Queen II")
      and not CF.same("Low Tide", "Low Tide Blues")
      and not CF.same("", "") and not CF.same("Abbey Road", "Let It Be"))
check(f"a name as the search takes it: {CF.said('AC/DC: Back in Black (Live)')}", CF.said('AC/DC: Back in Black (Live)')
      == '"AC\\/DC\\: Back in Black"' and CF.said('"Heroes"') == '"\\"Heroes\\""')
TAGGED = S + "/home/u/Music/Tagged"
os.makedirs(TAGGED)
T1, T2, T3, T4, T5 = (TAGGED + "/01 a.mp3", TAGGED + "/02 b.mp3", TAGGED + "/Paper Lanterns - Green Hours.mp3",
                      TAGGED + "/track7.mp3", TAGGED + "/Nobody - Nothing.mp3")
for out, tags in ((T1, ("The Night Ferries", "Low Tide", "Night Bus")), (T2, ("The Night Ferries", "Low Tide", "")),
                  (T3, None), (T4, None), (T5, None)):
    meta = [x for k, v in zip(("artist", "album", "title"), tags or ()) if v for x in ("-metadata", f"{k}={v}")]
    real_run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", TONE, "-t", "1", *meta, "-b:a", "64k", out],
             check=True)
picture(TAGGED + "/one.png", "grey")
picture(TAGGED + "/two.png", "grey")                    # (two pictures, neither named for it: not a cover)
check(f"a song's tags, as ffprobe reads them ({CF.song_tags(T1)}); none: its name says what it can ({CF.wanted(T3)})",
      CF.song_tags(T1) == {"artist": "The Night Ferries", "album": "Low Tide", "title": "Night Bus"}
      and CF.wanted(T2) == ("The Night Ferries", "Low Tide", "b")
      and CF.wanted(T3) == ("Paper Lanterns", "", "Green Hours")
      and CF.wanted(T4) == ("", "", "track7")
      and CF.song_tags(S + "/gone.mp3") == {"artist": "", "album": "", "title": ""})


def jpeg(kind):
    picture(S + "/net.jpg", kind)
    return open(S + "/net.jpg", "rb").read()


SUN, HILLS = jpeg("sun"), jpeg("hills")
credit = lambda who: [{"name": who, "artist": {"id": "a1", "name": who}}]   # noqa: E731
GROUPS = {"release-groups": [
    {"id": "rg-blues", "score": "100", "title": "Low Tide Blues", "artist-credit": credit("The Night Ferries")},
    {"id": "rg-other", "score": 100, "title": "Low Tide", "artist-credit": credit("Somebody Else")},
    {"id": "rg-low-tide", "score": 98, "title": "Low Tide", "primary-type": "Album",
     "artist-credit": credit("The Night Ferries")},
    {"id": "rg-unsure", "score": 60, "title": "Low Tide", "artist-credit": credit("The Night Ferries")}]}
SONGS_SAID = {"recordings": [
    {"id": "r0", "score": 100, "title": "Green Hours (karaoke)", "artist-credit": credit("Some Tribute Band"),
     "releases": [{"id": "x", "release-group": {"id": "rg-tribute", "primary-type": "Album"}}]},
    {"id": "r1", "score": "100", "title": "Green Hours", "artist-credit": credit("Paper Lanterns"), "releases": [
        {"id": "l1", "title": "Now That's Music 7", "release-group": {
            "id": "rg-hits", "primary-type": "Album", "secondary-types": ["Compilation"]}},
        {"id": "l2", "title": "Green Hours", "release-group": {"id": "rg-single", "primary-type": "Single"}},
        {"id": "l3", "title": "Lanterns", "release-group": {"id": "rg-album", "primary-type": "Album"}}]}]}
net, down = [], [False]


def internet(url):
    net.append(url)
    if down[0]:
        raise urllib.error.URLError("no route to host")
    q = urllib.parse.unquote(url)
    if "musicbrainz.org/ws/2/release-group?" in url:
        return json.dumps(GROUPS if 'releasegroup:"Low Tide"' in q and 'artist:"The Night Ferries"' in q
                          else {"release-groups": []}).encode()
    if "musicbrainz.org/ws/2/recording?" in url:
        return json.dumps(SONGS_SAID if 'recording:"Green Hours"' in q and 'artist:"Paper Lanterns"' in q
                          else {"recordings": []}).encode()
    art = {"rg-low-tide": SUN, "rg-single": HILLS, "rg-album": None}
    mbid = url.split("/release-group/")[1].split("/")[0]
    if url.startswith("https://coverartarchive.org/release-group/") and url.endswith("/front-500") and art.get(mbid):
        return art[mbid]
    raise urllib.error.HTTPError(url, 404, "Not Found", None, None)


asks = []
check(f"the records a song might be on: the one its tags name, by that artist, and sure enough "
      f"({CF.records('The Night Ferries', 'Low Tide', 'Night Bus', lambda w, q: asks.append((w, q)) or GROUPS)})",
      CF.records("The Night Ferries", "Low Tide", "Night Bus", lambda w, q: GROUPS) == ["rg-low-tide"]
      and asks == [("release-group", 'releasegroup:"Low Tide" AND artist:"The Night Ferries"')])
check("...no album said: the ones a song of that name by that artist is on, its own record before a single, never a "
      "compilation's", CF.records("Paper Lanterns", "", "Green Hours", lambda w, q: SONGS_SAID)
      == ["rg-album", "rg-single"] and CF.records("", "Low Tide", "x", lambda w, q: 1 / 0) == []
      and CF.records("Paper Lanterns", "", "", lambda w, q: 1 / 0) == [])
clock, naps = [50.0], []


def nap(secs):
    naps.append(round(secs, 2))
    clock[0] += secs


finder = CF.CoverFinder(fetch=internet, pause=nap, clock=lambda: clock[0])
got_for, steps = [], []
finder.on_found = got_for.append
finder.on_change = lambda: steps.append(finder.done)
check("Y's search, for five songs with no cover", finder.start([T1, T2, T3, T4, T5, SONG], thread=False)
      and not finder.busy and finder.total == 6 and steps[-1] == 6)
who = [u.split("/")[2] for u in net]
check(f"...found for three of them ({finder.note!r}): {[os.path.basename(p) for p in got_for]}", got_for == [T1, T2, T3]
      and finder.found == 3 and finder.note == "Found covers for 3 songs")
check(f"...MusicBrainz asked once for the record, the Cover Art Archive once for its picture, the record's second "
      f"song not at all; a song with no album: its name; one nobody knows: asked, and none ({len(net)} in all)",
      who == ["musicbrainz.org", "coverartarchive.org", "musicbrainz.org", "coverartarchive.org", "coverartarchive.org",
              "musicbrainz.org"] and "release-group" in net[0] and net[1].endswith("/rg-low-tide/front-500")
      and "recording" in net[2] and net[3].endswith("/rg-album/front-500") and net[4].endswith("/rg-single/front-500"))
check(f"...never two questions to MusicBrainz within {CF.MB_GAP} s (it waited {naps})", naps == [CF.MB_GAP, CF.MB_GAP]
      and "Pietato/" in CF.agent()["User-Agent"] and "( https://github.com/" in CF.agent()["User-Agent"])
f1, f2, f3 = C.found_file(T1), C.found_file(T2), C.found_file(T3)
check("each kept where a song's cover is looked for: the record's two songs share the one picture",
      C.cover_file(T1) == f1 and C.cover_file(T2) == f2 and C.cover_file(T3) == f3 and os.path.samefile(f1, f2)
      and near(Image.open(f1).convert("RGB").getpixel((300, 300)), (255, 226, 170), 20)
      and near(Image.open(f3).convert("RGB").getpixel((300, 300)), (55, 195, 110), 24))
check("...one with nothing to go by (no tags, a name that says nothing): not asked about; neither it nor the one "
      "nobody knows is asked about again for a month", C.cover_file(T4) is None and CF.missed(T4) and CF.missed(T5)
      and not CF.missed(T5, now=time.time() + CF.MISS_KEPT + 60) and not CF.missed(T1))
net.clear()
finder.start([T1, T2, T3, T4, T5], thread=False)
check(f"again: nothing to ask ({finder.note!r})", net == [] and finder.note == "No covers found for these songs")
os.remove(C.found_file(T5)[:-4] + ".none")
os.remove(C.found_file(T4)[:-4] + ".none")
down[0] = True
finder.start([T5, T4, T5, T5, T5, T5], thread=False)
check(f"the WiFi down: it gives up after {CF.NET_GIVES_UP} with no answer, and says so ({finder.note!r}); nothing's "
      f"put down as not found", len(net) == CF.NET_GIVES_UP
      and finder.note == "Couldn't reach MusicBrainz. Check the WiFi"
      and not CF.missed(T5))
down[0] = False
bad = CF.CoverFinder(fetch=lambda url: b"<html>not a picture</html>" if "coverart" in url else internet(url),
                     pause=nap, clock=lambda: clock[0])
os.remove(f1); os.remove(f2)
bad.start([T1], thread=False)
check("what comes back isn't a picture: not kept, none found", C.cover_file(T1) is None and bad.found == 0)
os.remove(C.found_file(T1)[:-4] + ".none")

# Y on the grid
m.items[MUSIC] = [g.item(p, g.title_of(p), "audio", p) for p in (T1, T2, T3, T4)]
m.sels[MUSIC] = 0
m.view = "list"
m.tiles = None
shot(m)
ready(m)
Y0 = shot(m)
hints = [w[1] for _, w in m.taps if w[0] == "keys"]
check(f"the grid's buttons: Y finds covers ({hints})", "y" in hints and "a" in hints and "b" in hints
      and near(Y0[y1 + 6, x1 + 20], g.ROW, 6))
made_finders = []
M.CoverFinder = lambda: made_finders.append(CF.CoverFinder(fetch=internet, pause=lambda s: None)) or made_finders[-1]
m.press("y")
end = time.time() + 10
while m.cover_finder.busy and time.time() < end:
    real_sleep(0.02)
check(f"Y: it says it's looking ({m.msg!r})", m.msg == "Finding covers for the songs with none"
      and len(made_finders) == 1)
m.msg = None
m.tick()
check(f"...and what it found, for the two that had none ({m.msg!r})", m.msg == "Found covers for 2 songs")
m.msg = None
shot(m)
ready(m)
Y1 = shot(m, "grid_found")
check("...their covers on the grid now, the one it couldn't find still a note",
      near(Y1[y1 + int(gs * 0.43), x1 + gs // 2], (255, 226, 170), 20) and near(Y1[y3 + 6, x3 + 20], g.ROW, 6)
      and near(Y1[at(gl, 2)[1] + gs // 2, at(gl, 2)[0] + gs // 2], (55, 195, 110), 24))
m.cover_finder.busy = True
m.cover_finder.done, m.cover_finder.total = 2, 4
shot(m)
hints = [w[1] for _, w in m.taps if w[0] == "keys"]
m.press("y")
check(f"while it's looking: no Y along the bottom, and Y says it's at it already ({m.msg!r})", "y" not in hints
      and m.msg == "Finding covers already")
m.cover_finder.busy = False
m.msg = None
playing(m, 2)
m.covers.clear()
shot(m)
found(m)
P2 = shot(m)
check("Now playing has the cover that was found too", near(P2[ay + side // 2, ax + side // 2], (55, 195, 110), 24))
m.view = "list"
m.press("x")
H = shot(m)
m.press("a")
check("Controls (X) on Music: its own page, Y among its buttons", m.view == "list"
      and ink(H, (20, 80, 320, 300), g.TEXT))

# ---- a light page, a big screen, Full screen apps -----------------------------------------------------------
m = media(look="Light")
playing(m, 2, "Harbour Lights", "The Night Ferries", "Low Tide")
shot(m)
found(m)
la = shot(m, "now_light")
check(f"a light page: a pale wash {tuple(la[200, 600])}, dark words, the line a darker one of the cover's colour",
      la[200, 600].min() > 150 and ink(la, (tx, ay + 6, 620, ay + 34), g.TEXT) and g.TEXT[0] < 60
      and la[bar + 2, ax + 30][0] < sun[0] - 30 and la[bar + 2, ax + 30][0] > la[bar + 2, ax + 30][2] + 40)
m = media(960, 540, scale=2)
playing(m, 2, "Harbour Lights", "The Night Ferries", "Low Tide")
shot(m)
found(m)
m.dirty = True
m.flush()
big = m.fb.last
lay2 = m.now_layout()
pic = np.asarray(big.pic.convert("RGB")).astype(int)
check(f"a big screen drawn finely: twice the pixels ({big.pic.size}), the cover {lay2['side']} of the menus' across "
      f"and sharp", big.pic.size == (1920, 1080) and fine.detail(big) == 2 and lay2["side"] > side
      and near(pic[2 * (lay2["ay"] + int(lay2["side"] * 0.43)), 2 * (lay2["ax"] + lay2["side"] // 2)],
               (255, 226, 170), 16)
      and m.now_made[1]["tile"].pic.size == (2 * lay2["side"], 2 * lay2["side"]))
m = media()
m.state["settings"]["app_full"] = "On"
playing(m, 2, "Harbour Lights", "The Night Ferries", "Low Tide")
shot(m)
found(m)
fa = shot(m, "now_full")
check("Full screen apps: the wash to the foot of the screen, no status bar, no buttons along the bottom",
      not near(fa[474, 320], g.BG, 6) and not ink(fa, (0, 0, 640, 24), g.BODY, 30) and m.now_layout()["ay"] > ay)
fine.set_scale(1)
g.set_look("Dark")

# ---- for real: FFmpeg, listening --------------------------------------------------------------------------------
M.Ear = E.Ear
g.time.monotonic = real_clock
t0 = time.monotonic()
ear = E.Ear(SONG, lambda: time.monotonic() - t0 + 2.0)
end = time.time() + 10
while time.time() < end and len(ear.beats) < 4:
    time.sleep(0.05)
got = [round(p, 2) for p, _ in ear.beats]
ahead = ear.at - (time.monotonic() - t0 + 2.0)
check(f"FFmpeg and a song with a kick every half second: its beats found on the half seconds ({got}), "
      f"{ahead:.1f} s ahead of what's heard", len(got) >= 4 and all(abs(p * 2 - round(p * 2)) < 0.1 for p in got)
      and -0.5 < ahead <= E.EAR_AHEAD + 0.3)
ear.close()
time.sleep(0.3)
check("...closed: its FFmpeg gone", ear.proc is None or ear.proc.poll() is not None)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
os._exit(0)
