"""Music's cover art. A song's cover: the picture named for it in its folder, else the one inside its file (FFmpeg gets
it out once, kept in the cache, and a song with none isn't looked into twice), else the only picture in its folder;
the colour its glow takes (the one there's most of, not a stir of them all; none from a grey cover). The ear: beats
found a moment ahead of what's heard, kept by their place in the song, a jump starting it again, the glow dying away
after each; and the sound as bars, a look every twentieth of a second, by its place in the song too. Now playing:
the cover on the left with its glow, a wash of it behind, the words, the line in the cover's colour, the buttons
(each tappable); a note for a song with no cover, a sign for a station; the cover's glow still, beat or no beat (it
followed the beat once), the ear kept for the bars with the battery saver on or off, none paused, on lofi art, off the
page; and the bars under the words (just their box drawn as they move, falling back, flat with nothing to show; none
with no room for them; there with the battery saver on too; none on a Pi Zero 2 W or a Pi 3, nor an ear there for
anything); a station's from its sound as MPlayer shares it (its
export filter's file, read: the bars when it's heard, the same at any volume, flat silenced, paused or with nothing
new; MPlayer told so for a station only, and played again without it when it stops over its file; for real too, an
MPlayer sharing a low note). Music's grid: every song a square with its cover (made small once and
kept on disk, a folder's shared
by its songs), its name under it, the picked one bigger with a glow all round it, the D-pad moving about it (off
either end, round to the other: right on the last song is the first; a held D-pad stops at the ends), A
playing as before, only the covers near the screen looked at, another tab still a list. Covers from the internet
(Y on the grid): a song's name and who it's by from its tags or its file's name (either way round), the iTunes
Store's search asked first (the likeliest of its answers, never more than twenty questions a minute, told that's too
many: once more, later), then MusicBrainz for which record it's on (the sure match only, no compilation's, never more
than a question a second) and the Cover Art Archive for its picture, a record's songs sharing one, what isn't found
not asked about again for a month, the WiFi down said. Your other
Pietatos first: asked which of the songs they have covers for (the same file name and size), those copied here, only
one of yours answered. A light page, and a screen drawn finely. Last, for real: another Pietato (peer_pietato.py)
asked for its covers through its web page, and FFmpeg listening to a song with a kick drum every half second."""
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
low = int(np.argmax(E.bars_bands()[0] > 60 * E.BARS_WIN / RATE)) - 1   # (the bar the kick's 60 Hz is in)
mid = int(np.argmax(E.bars_bands()[0] > 440 * E.BARS_WIN / RATE)) - 1  # (...and the note's 440)
on, off = ear.levels(beat + 0.1), ear.levels(beat + 0.45)     # (a look: what's heard the 43 ms before it)
whens = [round(w, 3) for w, _ in ear.looks.looks]
check(f"its bars, a look every {E.BARS_EVERY} s of the song ({whens[-3:]}), {E.BARS} of them: just after a kick, the "
      f"kick's bar high ({on and on[low]}), all but gone before the next ({off and off[low]}); the note's steady "
      f"({on and on[mid]}, {off and off[mid]}); nothing at the top ({on and on[-1]})",
      on is not None and off is not None and len(on) == E.BARS and on[low] > 0.7 and off[low] < 0.35
      and abs(on[mid] - off[mid]) < 0.12 and 0.35 < on[mid] < 0.8 and on[-1] == 0.0 == off[-1]
      and all(abs(b_ - a_ - E.BARS_EVERY) < 1e-6 for a_, b_ in zip(whens, whens[1:])))
check("...and none for where it doesn't know (paused), nor where it hasn't listened yet",
      ear.levels(None) is None and ear.levels(ear.at + 1.0) is None)
place[0] = 3.2
check("a little way back, in what it's listened to already: no need to start again", not ear.step()
      and started == [2.0])
first = ear.proc
place[0] = 20.0
ear.step()
check("a jump on: the first FFmpeg stopped, another from there, the old beats and bars let go",
      started == [2.0, 20.0] and first.killed and all(p >= 20.0 for p, _ in ear.beats)
      and all(w >= 20.0 for w, _ in ear.looks.looks) and ear.levels(3.9) is None)
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
toasted = []
was_toast, m.toast = m.toast, lambda text, secs=4: toasted.append(text)
as_ever = m.next_index(1)
m.press("y")
first = (m.shuffle, m.repeat, toasted[-1])
m.press("y")
second = (m.shuffle, m.repeat, toasted[-1])
rp = shot(m)
spot = (slice(keys - 14, keys + 14), slice(ax - 2, ax + 36))
check(f"Y goes round: shuffle ({first}), then the one song again and again ({second}): its drawing a loop with a 1 "
      f"in it, lit in the cover's colour", first == (True, False, "Shuffle")
      and second == (False, True, "Repeat this song") and ink(rp, (ax, keys - 12, ax + 34, keys + 12), colour, 30)
      and not np.array_equal(rp[spot], sh[spot]) and not np.array_equal(rp[spot], a[spot]))
loop = rp[keys - 9:keys + 10, ax + 2:ax + 33]          # (the loop, 31 across and 19 down)
lit_in = lambda rows, cols: np.nonzero(np.abs(rp[rows, cols] - np.array(colour)).max(axis=2) < 100)   # noqa: E731
across = lit_in(slice(keys - 3, keys + 7), slice(ax + 7, ax + 28))[1]     # (its 1: below the arrowhead,
down = lit_in(slice(keys - 6, keys + 7), slice(ax + 7, ax + 21))[0]       #  and to the left of it)
mid = (float(across.min() + across.max() + 1) / 2 + 5, float(down.min() + down.max() + 1) / 2 - 6) if len(across) \
    else None
check(f"...its 1 in the loop's middle, across and up and down (the loop's is at 15.5, 0.5 from the buttons' line: "
      f"the 1's is at {mid})", mid is not None and abs(mid[0] - 15.5) <= 1 and abs(mid[1] - 0.5) <= 1
      and ink(loop, (0, 8, 2, 11), colour, 30) and ink(loop, (29, 8, 31, 11), colour, 30))
check(f"...the song played through: it's the next ({m.next_index(1, ended=True)}, of {m.qi}); skipped with R, the "
      f"one after it as ever ({m.next_index(1)}); and one that stopped as soon as it started isn't played again and "
      f"again", m.next_index(1, ended=True) == m.qi and m.next_index(1) == as_ever and as_ever != m.qi
      and m.next_index(1, ended=False) == as_ever)
m.press("y")
check(f"...and round to in order again ({m.shuffle}, {m.repeat}, {toasted[-1]!r}): the next, when it's played "
      f"through", (m.shuffle, m.repeat, toasted[-1]) == (False, False, "In order")
      and m.next_index(1, ended=True) == as_ever and np.array_equal(shot(m)[spot], a[spot]))
m.toast = was_toast
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

# ---- the ear, for the bars (the cover's glow as it is, beat or no beat) ----------------------------------------
playing(m, 2, "Harbour Lights", "The Night Ferries", "Low Tide")
shot(m)
found(m)
shot(m)
made = []


class PretendEar:
    def __init__(self, src, where):
        self.src, self.where, self.closed, self.lit, self.bars = src, where, False, 0.0, None
        made.append(self)

    def level(self, place):
        return self.lit if place is not None else 0.0

    def levels(self, place):
        return self.bars if place is not None else None

    def close(self):
        self.closed = True


M.Ear = PretendEar
m.tick()
made[0].lit = 1.0
check(f"the battery saver on: an ear all the same (for the bars: they move on a battery too), the loop looking again "
      f"for the bars' next frame ({m.tick_limit():.3f} s)", m.bars_wanted() and len(made) == 1 and m.ear is made[0]
      and 0 < m.tick_limit() <= 1 / 15 + 1e-6)
made[0].lit = 0.0
m.state["settings"]["battery"] = "Off"
m.tick()
check("the battery saver off: the same ear for the song that's playing", len(made) == 1 and made[0].src == SONG
      and m.ear is made[0])
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
shot(m)
m.fb.parts.clear(); m.fb.shows = 0
m.pulse_next = 0.0
m.tick()
check("no beat: nothing drawn", m.fb.parts == [] and m.fb.shows == 0)
made[0].lit = 1.0
fake[0] += 0.1
m.tick()
check("a beat: nothing drawn either (the cover's glow stays as it is)", m.fb.parts == [] and m.fb.shows == 0)
check(f"...the loop looks again when the bars' next frame's due ({m.tick_limit():.3f} s)",
      0 < m.tick_limit() <= 1 / 15 + 1e-6)
m.next_query = 0.0                                     # (the player asked where it is, as it is each second: the
fake[0] += 0.07                                        #  page is drawn again for its line)
m.tick()
m.flush()
whole = np.asarray(m.fb.last.convert("RGB")).astype(int)
check(f"the page drawn again whole (how far through it is), a beat or not: the cover's glow on it as it was "
      f"({tuple(whole[ay + side // 2, ax - 5])}, {tuple(out)}) ({m.said[-1:]})", m.fb.shows == 1
      and tuple(whole[ay + side // 2, ax - 5]) == tuple(out) and "get_time_pos" in m.said[-1]
      and not hasattr(m, "pulse_step") and not hasattr(C, "glow_step"))
m.next_query = 1e12
m.press("a")
m.flush()
fake[0] += 0.07
made[0].lit = 0.3
parts = len(m.fb.parts)
m.tick()
check("paused: where the song is isn't guessed at, and the loop waits as it does", m.paused
      and m.heard_now() is None and m.pos_off is None and m.tick_limit() == 0.25)
m.press("a")
m.pos_said(121.0)
m.press("select")
m.tick()
check("lofi art on: no ear", m.now_art() and m.ear is None and made[0].closed)
m.press("select")
m.press("select")                                      # (past Game beat, on a machine quick enough for it)
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

# ---- Now playing's bars --------------------------------------------------------------------------------------------
playing(m, 2, "Harbour Lights", "The Night Ferries", "Low Tide")
m.tick()
bear = made[-1]
m.pos_said(84.0)
ramp = tuple(round(k / (M.BARS - 1), 3) for k in range(M.BARS))
bear.bars = ramp
p0 = shot(m)
lay = m.now_layout()
nb = m.now_bars
lit_ink, _, empty_ink = m.now_inks(m.now_made[1]["colour"])
bx0, by0, bx1, by1 = nb[0] if nb else (0, 0, 1, 1)
bw = (bx1 - bx0) / M.BARS
top_bar = p0[by0 + 3, int(bx0 + (M.BARS - 1) * bw + bw * 0.35)]
check(f"the bars on Now playing, the battery saver off: under the words, over the small ones ({nb and nb[0]}), as "
      f"far from the cover and from the screen's edge as the cover is from its own ({lay['ax']} px), {M.BARS} of them "
      f"across, the loudest up to their top in the glow's colour ({tuple(top_bar)}, {lit_ink}), the quietest a line",
      nb is not None and nb[1] == ramp and bx0 == 2 * lay["ax"] + lay["side"] and bx1 == lay["W"] - lay["ax"]
      and M.BARS_LEAST <= by1 - by0 <= round(lay["side"] * M.BARS_MOST) + 1 and by0 >= lay["ay"] + 90
      and by1 <= lay["ay"] + lay["side"] - 52 and near(top_bar, lit_ink, 10)
      and not near(p0[by1 - 8, int(bx0 + bw * 0.35)], lit_ink, 30))
m.fb.parts.clear(); m.fb.shows = 0
bear.bars = tuple(reversed(ramp))
fake[0] += 0.07
m.tick()
want = tuple(max(v, round(w * M.BARS_FALL, 3)) if w * M.BARS_FALL >= 0.01 else v
             for v, w in zip(reversed(ramp), ramp))
check(f"the next frame, the sound changed: just their box goes to the screen ({m.fb.parts}), each bar up at once "
      f"to what's heard, or falling back a little ({m.now_bars[1][-3:]})", m.fb.parts == [nb[0]]
      and m.fb.shows == 0 and m.now_bars[1] == want)
bear.bars = None
for _ in range(14):
    fake[0] += 0.07
    m.tick()
n_parts = len(m.fb.parts)
fake[0] += 0.07
m.tick()
check(f"nothing to show (a moment after a seek): they fall back, then lie flat, and aren't drawn again "
      f"({n_parts} frames)", all(v == 0.0 for v in m.now_bars[1]) and 3 <= n_parts <= 15
      and len(m.fb.parts) == n_parts)
playing(m, 2, "Harbour Lights Over the Water at the End of the Long Summer Night", "The Night Ferries", "Low Tide")
shot(m)
check("a name that takes three lines: no room left for them, none", m.now_bars is None)
playing(m, 2, "Harbour Lights", "The Night Ferries", "Low Tide")
m.state["settings"]["battery"] = "On"
shot(m)
on_saver = m.now_bars
m.state["settings"]["battery"] = "Off"
m.kind, m.cur = "radio", station
shot(m)
check(f"...the battery saver on: there all the same ({on_saver and on_saver[0]}); a station MPlayer isn't sharing the "
      f"sound of: none", on_saver is not None and on_saver[0] == nb[0] and m.now_bars is None)
m.tick()

# ---- a station's bars: its sound as MPlayer shares it (ear.py's Tap) -----------------------------------------------
import collections, struct  # noqa: E401, E402
TAPF = f"{SP}/bars-tap"


def shared(count, hz, amp, path=TAPF, nch=2):
    """A lot of a station's sound as MPlayer's export filter leaves it: how many channels, how many bytes, the count,
    then each channel's samples in turn."""
    n = E.EXPORT_SIZE
    s = np.rint(amp * 32767 * np.sin(2 * np.pi * hz * np.arange(n) / E.EXPORT_RATE)).astype("=i2")
    with open(path, "wb") as f:
        f.write(struct.pack("=iiQ", nch, 2 * n * nch, count) + np.tile(s, nch).tobytes())


bands = E.bars_bands(win=E.EXPORT_SIZE, rate=E.EXPORT_RATE)[0]
note_bar = int(np.argmax(bands > 90 * E.EXPORT_SIZE / E.EXPORT_RATE)) - 1   # (the bar a 90 Hz note's in)
plain_proc = m.proc
m.proc = types.SimpleNamespace(poll=lambda: None, stdin=io.StringIO(), shares_sound=True)
m.sound_tap, m.volume, m.muted = E.Tap(TAPF), 50, False
shared(1, 90, 0.25 * 0.5 * E.SOFTVOL_TOP)           # (a low note, as loud as half volume plays it)
shot(m)
first = m.now_bars
fake[0] += E.EXPORT_LEAD
m.pulse_next = 0.0
m.tick()
half = m.now_bars[1] if m.now_bars else None
check(f"a station MPlayer shares the sound of: its bars too, flat as it starts ({first and max(first[1])}), then "
      f"up with what it played half a second before, as it's heard now: its low note's bar "
      f"({half and half[note_bar]}), "
      f"the loop looking again for the next frame ({m.tick_limit():.3f} s)", first is not None
      and max(first[1]) == 0.0 and half is not None and half[note_bar] > 0.5
      and max(half[note_bar + 6:]) < 0.05 and 0 < m.tick_limit() <= 1 / 15 + 1e-6)
at_half = m.sound_tap.kept[-1][1]
m.volume = 100
shared(2, 90, 0.25 * E.SOFTVOL_TOP)                 # (...and as loud as full volume plays it)
fake[0] += 0.1
m.now_heard()
at_full = m.sound_tap.kept[-1][1]
check(f"...the same at full volume as at half ({at_full[note_bar]}, {at_half[note_bar]})", len(m.sound_tap.kept) == 2
      and max(abs(a_ - b_) for a_, b_ in zip(at_full, at_half)) < 0.01)
fake[0] += E.EXPORT_LEAD
m.muted = True
silenced = m.now_heard()
m.muted, m.paused = False, True
paused = m.now_heard()
m.paused = False
heard = m.now_heard()
fake[0] += 1.0
check("...silenced (it starts silent and paused), or paused: flat; nothing new from it for a moment: flat too",
      silenced is None and paused is None and heard is not None and m.now_heard() is None)

E.EXPORTS[:] = [True]                                 # (an MPlayer that can share its sound: told to, for a station)
real_tap_file = M.tap_file
M.tap_file = lambda uid=None: f"{SP}/bars-{uid}"
spawned = []
m.spawn = lambda args, target: spawned.append((list(args), target))
m.proc = None
m.play([station], 0)
told = spawned[-1][0] if spawned else []
there = M.tap_file(M.as_you()[1].get("user"))
m.play(m.items[MUSIC], 2)
check(f"a station played: MPlayer told to share its sound in a file that's ready for it ({told[-6:]}); a song: not "
      f"(the ear hears that)", told[-4:] == ["-af-add", f"export={there}:{E.EXPORT_SIZE}", "-volume", str(m.volume)]
      and os.path.isfile(there) and m.sound_tap.path == there and "-af-add" not in spawned[-1][0])
E.EXPORTS[:] = [False]
m.play([station], 0)
check("...an MPlayer that can't: not told", "-af-add" not in spawned[-1][0])
E.EXPORTS[:] = [True]
p = types.SimpleNamespace(args=told[:-2] + ["http://10.0.0.9/live"], said=["Exiting... (End of file)"])
not_it = m.sound_share_again(p)
p.said = collections.deque(["[export] Exporting to file: " + there, "[export] Could not open/create file: " + there,
                            "[libaf] Reinitialization did not work, audio filter 'export' returned error code -2",
                            "Error at audio filter chain pre-init!", "Exiting... (Fatal error)"])
spawned.clear()
again = m.sound_share_again(p)
check(f"a station that stopped at once over that file: played again straight away without it ({spawned[-1:]}), and "
      f"MPlayer not told to after that; one that stopped for something else: left to what's done then",
      not not_it and again and spawned == [(told[:-4], "http://10.0.0.9/live")] and m.sound_share_off
      and m.sound_share_args() == [])
m.sound_share_off = False
del m.spawn
p = None
m.kind = "radio"
m.spawn(["true", "-af-add", f"export={there}:{E.EXPORT_SIZE}"], "x")
shares = getattr(m.proc, "shares_sound", None)
m.spawn(["true"], "x")
check("...what it was told is kept with the player (so the bars know)", shares is True
      and getattr(m.proc, "shares_sound", None) is False)
m.stop()
if shutil.which("mplayer"):                            # (for real: an MPlayer sharing a low note)
    low_note = f"{SP}/low-note.mp3"                    # (FFmpeg's sine is an eighth as loud as can be: half, then)
    real_run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
              "sine=frequency=90:duration=6", "-af", "volume=4", "-ar", "44100", "-ac", "2", low_note], check=True)
    args = m.sound_share_args()
    mp = subprocess.Popen(["mplayer", "-slave", "-quiet", "-novideo", "-softvol", "-ao", "null", "-volume", "50"]
                          + args + [low_note], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, text=True)
    t0, looks = real_clock(), []
    while real_clock() - t0 < 2.5:
        look = m.sound_tap.levels(real_clock(), 0.5 * E.SOFTVOL_TOP)
        if look is not None:
            looks.append(look)
        real_sleep(1 / 15)
    mp.stdin.write("quit\n")
    mp.stdin.flush()
    mp.wait(10)
    best = max(looks, key=lambda v: v[note_bar]) if looks else None
    check(f"for real: MPlayer told as a station is shares what it plays ({len(looks)} looks in 2.5 s), its low note's "
          f"bar up ({best and best[note_bar]}), the high ones low ({best and max(best[16:])})", len(looks) >= 15
          and best[note_bar] > 0.5 and max(best[16:]) < best[note_bar] / 3)
    r = real_run(["mplayer", "-slave", "-quiet", "-novideo", "-softvol", "-ao", "null", "-af-add",
                  f"export={SP}/no-such-folder/bars:{E.EXPORT_SIZE}", low_note], stdin=subprocess.DEVNULL,
                 capture_output=True, text=True, timeout=30)
    said = collections.deque((ln.strip() for ln in (r.stdout + r.stderr).splitlines() if ln.strip()), maxlen=12)
    m.spawn = lambda args, target: spawned.append((list(args), target))
    spawned.clear()
    again = m.sound_share_again(types.SimpleNamespace(
        args=["mplayer", "-af-add", f"export={SP}/no-such-folder/bars:2048", "http://10.0.0.9/live"], said=said))
    del m.spawn
    check(f"...and one that can't make its file stops at once, saying so ({list(said)[-2:]}): played again without",
          r.returncode != 0 and again and spawned == [(["mplayer"], "http://10.0.0.9/live")])
    m.sound_share_off = False
M.tap_file = real_tap_file
m.proc = plain_proc

# a Pi Zero 2 W or a Pi 3: no bars (they'd cost it too much), nor an ear
playing(m, 2, "Harbour Lights", "The Night Ferries", "Low Tide")
m.state["settings"]["battery"] = "On"
m.ear_stop()
m.bars_fit = None
real_slow = M.slow_pi
M.slow_pi = lambda: True
shot(m)
m.tick()
saver_on = (m.now_bars, m.ear, m.bars_wanted())
m.state["settings"]["battery"] = "Off"
m.tick()
no_ear = m.ear is None
shot(m)
no_bars = m.now_bars
check(f"a Pi Zero 2 W or a Pi 3: no bars, nor an ear for them, with the battery saver on ({saver_on}) or off "
      f"({no_ear}, {no_bars}); MPlayer not told to share a station's sound", saver_on == (None, None, False)
      and no_ear and no_bars is None and m.sound_share_args() == [])
M.slow_pi = real_slow
m.bars_fit = None
m.ear_stop()

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
off, mid = M.GRID_RAISED + 3, gs // 2                   # (three pixels out from the picked cover, on each side of it)
lit = [G[y0 + mid, x0 - off], G[y0 + mid, x0 + gs - 1 + off], G[y0 - off, x0 + mid], G[y0 + gs - 1 + off, x0 + mid]]
plain = G[y1 + mid, x1 + gs + 8]
check(f"the picked one: a little bigger, a glow in its cover's colour round it, the same on all four sides "
      f"{[tuple(int(v) for v in p) for p in lit]} (the others: none {tuple(plain)})",
      near(G[y0 - M.GRID_RAISED + 1, x0 + mid], (250, 150, 62), 30)
      and all(p[0] > p[2] + 25 and near(p, lit[0], 10) for p in lit)
      and near(G[y0 + mid, x0 - M.GRID_RAISED - M.GRID_GLOW - 2], g.BG, 6)
      and near(plain, g.BG, 4) and near(G[y1 - 4, x1 + mid], g.BG, 4))
masks = [np.asarray(C.glow_mask(*sized)).astype(int) for sized in (
    (gs + 2 * M.GRID_RAISED, M.GRID_GLOW, M.GRID_RADIUS), (230, C.GLOW_REACH, M.NOW_RADIUS), (460, 44, 24))]
check(f"...the glow itself, as it's made (the grid's, Now playing's): the same left and right, above and below, on "
      f"any Pillow, and fading to nothing at its edge ({[int(a[0].max()) for a in masks]} of 255)",
      all(np.abs(a - a[:, ::-1]).max() == 0 and np.abs(a - a[::-1]).max() == 0 and a[0].max() <= 8
          and a.max() == 255 for a in masks))
x2, y2 = at(gl, 2)
check("each one's name under it, clear of the glow; the one that's playing marked in the accent's colour",
      ink(G, (x0, y0 + gs + 14, x0 + gs, y0 + gs + 30), g.TEXT)
      and ink(G, (x1, y1 + gs + 14, x1 + gs, y1 + gs + 30), g.BODY)
      and ink(G, (x2, y2 + gs + 14, x2 + gs, y2 + gs + 30), g.ACCENT, 30)
      and not ink(G, (x1, y1 + gs + 14, x1 + gs, y1 + gs + 30), g.ACCENT, 30)
      and not ink(G, (x0, y0 + gs + M.GRID_RAISED + M.GRID_GLOW, x0 + gs, y0 + gs + 14), g.TEXT, 60))
taps = [(box, what) for box, what in m.taps if what[0] == "sel"]
check("a tap on a cover picks that song", [w[-1] for _, w in taps] == [0, 1, 2, 3, 4]
      and all(b[0] <= at(gl, i)[0] and b[2] >= at(gl, i)[0] + gs and b[1] <= at(gl, i)[1]
              for i, (b, _) in enumerate(taps))
      and all(taps[i][0][2] <= taps[i + 1][0][0] for i in range(3)))
moves = []
for key in ("right", "right", "right", "right", "left", "up", "down", "down"):
    m.press(key)
    moves.append(m.sels[MUSIC])
check(f"the D-pad moves about it: across, back one, and up and down between its rows ({moves}); down where "
      f"there's no song under: the last one", moves == [1, 2, 3, 4, 3, 4, 0, 4]
      and M.MusicScreen.music_step(m, 1, "down", 5, 4) == 4)
m.sels[MUSIC] = 4
rounds = []
for key, held in (("right", False), ("left", False), ("left", True), ("right", True), ("right", False),
                  ("left", True), ("up", False), ("down", False), ("up", True)):
    m.press(key, repeat=held)
    rounds.append(m.sels[MUSIC])
check(f"off the end, round to the start: right on the last song is the first, left on the first the last; up from "
      f"the top row and down from the bottom one go round too; a held D-pad stops at the ends ({rounds})",
      rounds == [0, 4, 3, 4, 0, 0, 4, 0, 0])
step = lambda sel, way, n=10: M.MusicScreen.music_step(m, sel, way, n, 4)   # noqa: E731  (ten songs, four across)
check("...in a longer grid: down from the bottom row to the same place in the top one, up from the top to the "
      "bottom (the last song, where the bottom row's short)", (step(9, "right"), step(0, "left"), step(9, "down"),
                                                              step(8, "down"), step(1, "up"), step(3, "up"),
                                                              step(5, "down"), step(6, "down"), step(5, "up"))
      == (0, 9, 1, 0, 9, 9, 9, 9, 1) and step(0, "right", 1) == 0 and step(0, "down", 1) == 0
      and step(2, "up", 3) == 2)
m.sels[MUSIC] = 4
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
check(f"the two sides of a song's file's name, a track number left off: {list(names.values())[:3]}", names == {
    "Paper Lanterns - Green Hours": ("Paper Lanterns", "Green Hours"), "03 Harbour Lights": ("", "Harbour Lights"),
    "3. The Tide - Low": ("The Tide", "Low"), "99 Luftballons": ("", "99 Luftballons"),
    "01_Artist_-_Song": ("Artist", "Song"), "50 Cent - In Da Club": ("50 Cent", "In Da Club"),
    "12 - Somebody - A Song - Live": ("Somebody", "A Song - Live")})
check("two names being one: marks, capitals, what's in brackets and who else is on it don't matter; a short one "
      "inside a longer isn't it",
      CF.same("Nevermind", "nevermind (Remastered 2011)") and CF.same("Sgt. Pepper's Lonely Hearts Club Band",
                                                                     "Sgt Peppers Lonely Hearts Club Band")
      and CF.same("Beyoncé", "Beyonce") and not CF.same("Queen", "Queen II")
      and not CF.same("Low Tide", "Low Tide Blues")
      and not CF.same("", "") and not CF.same("Abbey Road", "Let It Be")
      and CF.same("Stay ft. Somebody", "Stay (feat. Somebody Else)")
      and CF.bare("Stay (Live) [Official Video]") == "Stay"
      and CF.bare("(Untitled)") == "(Untitled)" and CF.bare("Lift Off") == "Lift Off")
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


def tagged(**tags):
    """A pretend ffprobe: these are the song's tags."""
    return lambda *a, **k: type("Ran", (), {"stdout": json.dumps({"format": {"tags": tags}}).encode()})


check(f"a song's tags, as ffprobe reads them ({CF.song_tags(T1)}); none: its name says what it can, which side of "
      f"it is which not known ({CF.wanted(T3)})",
      CF.song_tags(T1) == {"artist": "The Night Ferries", "album": "Low Tide", "title": "Night Bus"}
      and CF.wanted(T2) == ("The Night Ferries", "Low Tide", "b", False)
      and CF.wanted(T3) == ("Paper Lanterns", "", "Green Hours", True)
      and CF.wanted(T4) == ("", "", "track7", False)
      and CF.song_tags(S + "/gone.mp3") == {"artist": "", "album": "", "title": ""})
band, one = ("The Band", "", "Song One", False), "/m/Song One - The Band.mp3"
check("...a tag for one of the two: the other is the side of the name that isn't it, whichever way round the name is",
      CF.wanted(one, tagged(artist="The Band")) == band and CF.wanted(one, tagged(title="Song One")) == band
      and CF.wanted("/m/The Band - Song One.mp3", tagged(artist="The Band")) == band
      and CF.wanted("/m/The Band - Song One.mp3", tagged(title="Song One")) == band
      and CF.wanted("/m/07 Song One.mp3", tagged(artist="The Band")) == band
      and CF.wanted("/m/Song One.mp3", tagged(title="Song One")) == ("", "", "Song One", False)
      and CF.wanted(one, tagged(artist="Them", title="It", album="Theirs")) == ("Them", "Theirs", "It", False))


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


def sold(who, name, art, record=""):
    """One of the iTunes Store's answers, as its search gives them (the parts that are looked at)."""
    return {"wrapperType": "track", "kind": "song", "artistName": who, "trackName": name, "collectionName": record,
            "artworkUrl100": f"https://is1-ssl.mzstatic.com/image/thumb/Music/{art}/100x100bb.jpg"}


def big(art):
    return f"https://is1-ssl.mzstatic.com/image/thumb/Music/{art}/600x600bb.jpg"


DAYS = [sold("Some Tribute Band", "Blinding Days (Karaoke Version)", "karaoke"),
        sold("The Weekenders", "Blinding Days", "days", "After Days")]
RECORDS = [sold("Various Artists", "", "various", "After Days"),
           sold("The Weekenders", "", "deluxe", "After Days (Deluxe)"),
           sold("The Weekenders", "", "before", "Before Days")]
LIKE = [sold("Somebody Else", "Another Song", "neither"), sold("The Weekenders", "Deep Cut", "theirs"),
        sold("The Wknd", "Blinding Days", "named")]
asks = []
check("the iTunes Store's answers for a song: the one of that name by that artist, its picture at the size a cover's "
      "kept", CF.shop_art("The Weekenders", "", "Blinding Days (Official Video)", False,
                          lambda w, q: asks.append((w, q)) or DAYS) == big("days")
      and asks == [("song", "The Weekenders Blinding Days")])
check("...a file's name may have the two either way round (\"Song - Artist\"); what tags say isn't turned round",
      CF.shop_art("Blinding Days", "", "The Weekenders", True, lambda w, q: DAYS) == big("days")
      and CF.shop_art("Blinding Days", "", "The Weekenders", False, lambda w, q: DAYS) is None)
check("...none by that name and artist: that name by whoever (who it's by, spelt another way) before another of the "
      "artist's; nothing like it, no picture, or nobody it's by: none",
      CF.shop_art("The Weekenders", "", "Blinding Days", False, lambda w, q: LIKE) == big("named")
      and CF.shop_art("The Weekenders", "", "Blinding Days", False, lambda w, q: LIKE[:2]) == big("theirs")
      and CF.shop_art("The Weekenders", "", "Blinding Days", False, lambda w, q: LIKE[:1]) is None
      and CF.shop_art("The Weekenders", "", "Blinding Days", False, lambda w, q: [
          dict(DAYS[1], artworkUrl100="http://elsewhere/100x100bb.jpg"),
          {"artistName": "The Weekenders", "trackName": "Blinding Days"}]) is None
      and CF.shop_art("", "", "Blinding Days", False, lambda w, q: 1 / 0) is None)
asks.clear()
check("...a record its tags name: that record's picture, by that artist before anybody's; no such record there: the "
      "song's asked about", CF.shop_art("The Weekenders", "After Days", "Hardest", False,
                                        lambda w, q: asks.append((w, q)) or RECORDS) == big("deluxe")
      and asks == [("album", "The Weekenders After Days")]
      and CF.shop_art("The Weekenders", "After Days", "Hardest", False, lambda w, q: RECORDS[:1]) == big("various")
      and CF.shop_art("The Weekenders", "Days Gone", "Blinding Days", False,
                      lambda w, q: RECORDS if w == "album" else DAYS) == big("days"))
STORE = {}                                             # what the pretend Store has: {(what, words): its answers}
PICTURES = {"days": "sun", "deluxe": "hills", "home": "sun"}
net, down, busy = [], [False], [0]


def internet(url):
    net.append(url)
    if down[0]:
        raise urllib.error.URLError("no route to host")
    q = urllib.parse.unquote(url)
    if url.startswith("https://itunes.apple.com/search?"):
        if busy[0]:                                    # (too many questions, it says)
            busy[0] -= 1
            raise urllib.error.HTTPError(url, 403, "Forbidden", None, None)
        said = dict(urllib.parse.parse_qsl(url.split("?", 1)[1]))
        got = STORE.get((said["entity"], said["term"]), []) if said["media"] == "music" else []
        return json.dumps({"resultCount": len(got), "results": got}).encode()
    if url.startswith("https://is1-ssl.mzstatic.com/") and url.endswith("/600x600bb.jpg"):
        kind = PICTURES.get(url.split("/")[-2])
        if kind:
            return SUN if kind == "sun" else HILLS
    if "musicbrainz.org/ws/2/release-group?" in url:
        return json.dumps(GROUPS if 'releasegroup:"Low Tide"' in q and 'artist:"The Night Ferries"' in q
                          else {"release-groups": []}).encode()
    if "musicbrainz.org/ws/2/recording?" in url:
        return json.dumps(SONGS_SAID if 'recording:"Green Hours"' in q and 'artist:"Paper Lanterns"' in q
                          else {"recordings": []}).encode()
    if url.startswith("https://coverartarchive.org/release-group/") and url.endswith("/front-500"):
        art = {"rg-low-tide": SUN, "rg-single": HILLS}.get(url.split("/release-group/")[1].split("/")[0])
        if art:
            return art
    raise urllib.error.HTTPError(url, 404, "Not Found", None, None)


asks = []
check(f"MusicBrainz: the records a song might be on: the one its tags name, by that artist, and sure enough "
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
check("Y's search, for five songs with no cover, none of them the Store's", finder.start(
    [T1, T2, T3, T4, T5, SONG], thread=False) and not finder.busy and finder.total == 6 and steps[-1] == 6)
who = [u.split("/")[2] for u in net]
check(f"...found for three of them ({finder.note!r}): {[os.path.basename(p) for p in got_for]}", got_for == [T1, T2, T3]
      and finder.found == 3 and finder.note == "Found covers for 3 songs")
STORE_, MB_, ART_ = "itunes.apple.com", "musicbrainz.org", "coverartarchive.org"
check(f"...the Store asked first (for a record its tags name, then for the song); then MusicBrainz, once for the "
      f"record, and the Cover Art Archive for its picture; the record's second song: nobody. A song with no album: "
      f"by its name. One nobody knows: MusicBrainz asked with its name's two sides both ways round ({len(net)} in all)",
      who == [STORE_, STORE_, MB_, ART_, STORE_, MB_, ART_, ART_, STORE_, MB_, MB_]
      and "entity=album" in net[0] and "term=The%20Night%20Ferries%20Low%20Tide&" in net[0] and "entity=song" in net[1]
      and "release-group" in net[2] and net[3].endswith("/rg-low-tide/front-500")
      and "recording" in net[5] and net[6].endswith("/rg-album/front-500") and net[7].endswith("/rg-single/front-500")
      and 'recording:"Nothing" AND artist:"Nobody"' in urllib.parse.unquote(net[9])
      and 'recording:"Nobody" AND artist:"Nothing"' in urllib.parse.unquote(net[10]))
check(f"...never two questions to MusicBrainz within {CF.MB_GAP} s (it waited {naps})", naps == [CF.MB_GAP] * 3
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
os.remove(C.found_file(T5)[:-4] + CF.MISS)
os.remove(C.found_file(T4)[:-4] + CF.MISS)
down[0] = True
finder.start([T5, T4, T5, T5, T5, T5], thread=False)
check(f"the WiFi down: it gives up after {CF.NET_GIVES_UP} songs with no answer from either, and says so "
      f"({finder.note!r}); nothing's put down as not found", len(net) == 2 * CF.NET_GIVES_UP
      and finder.note == "Couldn't look covers up. Check the WiFi" and not CF.missed(T5))
down[0] = False
bad = CF.CoverFinder(fetch=lambda url: b"<html>not a picture</html>" if "coverart" in url else internet(url),
                     pause=nap, clock=lambda: clock[0])
os.remove(f1); os.remove(f2)
bad.start([T1], thread=False)
check("what comes back isn't a picture: not kept, none found", C.cover_file(T1) is None and bad.found == 0)
os.remove(C.found_file(T1)[:-4] + CF.MISS)
STORED = S + "/home/u/Music/Stored"                     # ...and songs the Store does know
os.makedirs(STORED)
V1, V2, V3, V4, V5 = (STORED + "/Blinding Days - The Weekenders.mp3", STORED + "/02 hardest.mp3",
                      STORED + "/03 cheers.mp3", STORED + "/Home Song - Sombody Misspelt.mp3",
                      STORED + "/Nobody - Heard Of.mp3")
for out in (V1, V2, V3, V4, V5):
    shutil.copy(BARE, out)
TAGS = {V2: dict(artist="The Weekenders", album="After Days", title="Hardest To Love"),
        V3: dict(artist="The Weekenders", album="After Days", title="Save Your Cheers")}
STORE.update({("song", "Blinding Days The Weekenders"): DAYS, ("album", "The Weekenders After Days"): RECORDS,
              ("song", "Home Song Sombody Misspelt"): [sold("Somebody Misspelled", "Home Song", "home")],
              ("song", "Nobody Heard Of"): [sold("Somebody", "Something Else", "neither")]})
open(C.found_file(V1)[:-4] + ".none", "w").close()      # (what the version before left by a song it couldn't find)
net.clear(); naps.clear(); got_for.clear()
shop = CF.CoverFinder(fetch=internet, run=lambda cmd, **k: tagged(**TAGS.get(cmd[-1], {}))(), pause=nap,
                      clock=lambda: clock[0])
shop.on_found = got_for.append
shop.start([V1, V2, V3, V4, V5], thread=False)
who = [u.split("/")[2] for u in net]
check(f"songs the Store knows ({shop.note!r}): one question each and then its picture, a record's second song "
      f"neither; one it has nothing like: MusicBrainz asked, and none",
      got_for == [V1, V2, V3, V4] and shop.note == "Found covers for 4 songs" and CF.missed(V5)
      and who == [STORE_, "is1-ssl.mzstatic.com"] * 3 + [STORE_, MB_, MB_]
      and net[1] == big("days") and net[3] == big("deluxe") and net[5] == big("home"))
check("...a file called \"Song - Artist\" has its cover (the last version's word that it has none isn't gone by), "
      "the record's two songs share theirs, and a song whose artist's misspelt has one",
      near(Image.open(C.found_file(V1)).convert("RGB").getpixel((300, 258)), (255, 226, 170), 20)
      and os.path.samefile(C.found_file(V2), C.found_file(V3))
      and near(Image.open(C.found_file(V2)).convert("RGB").getpixel((300, 300)), (55, 195, 110), 24)
      and C.cover_file(V4) == C.found_file(V4) and naps == [CF.MB_GAP])
os.remove(C.found_file(V5)[:-4] + CF.MISS)
busy[0] = 1
naps.clear()
shop.start([V5], thread=False)
check(f"the Store saying that's too many questions: left alone for {CF.SHOP_BUSY:.0f} s, then asked once more "
      f"({naps})", [n for n in naps if n] == [CF.SHOP_BUSY, CF.MB_GAP] and CF.missed(V5) and shop.found == 0)
os.remove(C.found_file(V5)[:-4] + CF.MISS)
busy[0] = 99
shop.start([V5, V5, V5, V5, V5], thread=False)
check(f"...and still saying so: MusicBrainz is asked all the same, the song's not put down as having none, and it "
      f"stops after {CF.NET_GIVES_UP} ({shop.note!r})", not CF.missed(V5) and shop.done == CF.NET_GIVES_UP
      and shop.note == "Couldn't look covers up. Try again in a minute" and MB_ in net[-1])
busy[0] = 0
naps.clear()
quick, waited = CF.CoverFinder(fetch=internet, pause=nap, clock=lambda: clock[0]), None
for k in range(CF.SHOP_MOST + 2):
    quick.shop("song", f"anything {k}")
    if k == CF.SHOP_MOST - 1:
        waited = list(naps)
check(f"the Store's never asked more than {CF.SHOP_MOST} questions in a minute: that many straight off ({waited}), "
      f"the next when the first is a minute old ({naps})", waited == [] and naps == [CF.SHOP_SPAN, 0.0])

# ---- covers from your other Pietatos ----------------------------------------------------------------------------
SHARED = S + "/home/u/Music/Shared"
os.makedirs(SHARED)
U1, U2, U3 = SHARED + "/one.mp3", SHARED + "/two.mp3", SHARED + "/Lost Song - Nobody.mp3"
for k, out in enumerate((U1, U2, U3)):                  # (each a different length: its size says which it is)
    real_run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", TONE, "-t", str(1 + k), "-b:a", "64k", out],
             check=True)
OTHER = S + "/other/Music"                              # another Pietato's Music: the same songs, and covers
os.makedirs(OTHER + "/A")
os.makedirs(OTHER + "/B")
shutil.copy(U1, OTHER + "/A/ONE.mp3")                   # (the same song, whatever its name's capitals)
shutil.copy(U2, OTHER + "/B/two.mp3")
shutil.copy(BARE, OTHER + "/B/Lost Song - Nobody.mp3")  # (the name of one here, but not that song: another size)
picture(OTHER + "/A/folder.jpg", "sun")
other = media()
del other.items[MUSIC]                                  # (Music never opened on it: it looks in its folder)
TAB = g.LIBRARY[MUSIC]


def theirs(answer, *a):
    """The other Pietato answering: its Music is OTHER."""
    was, TAB["dirs"] = TAB["dirs"], [OTHER]
    try:
        return answer(*a)
    finally:
        TAB["dirs"] = was


picture(S + "/found.jpg", "hills")
os.makedirs(os.path.dirname(C.found_file(OTHER + "/B/two.mp3")), exist_ok=True)
shutil.copy(S + "/found.jpg", C.found_file(OTHER + "/B/two.mp3"))    # (one it found on the internet itself)
check("a cover that's to hand, with no looking inside a file: the folder's, one found before; none: none",
      C.cover_at_hand(OTHER + "/A/ONE.mp3") == OTHER + "/A/folder.jpg"
      and C.cover_at_hand(OTHER + "/B/two.mp3") == C.found_file(OTHER + "/B/two.mp3")
      and C.cover_at_hand(OTHER + "/B/Lost Song - Nobody.mp3") is None
      and C.cover_at_hand(S + "/gone.mp3") is None)
keys = [CF.song_key(p) for p in (U1, U2, U3)]
yours = [True]
other.saves_peers = lambda ip=None: yours[0] if ip is not None else []
said = theirs(other.web_covers, {"songs": keys + [["nope.mp3", 5], "junk", ["x"]], "from": "10.0.0.7"})
check(f"another of yours asks which of its songs this one has covers for (the same name and size): {said}",
      said == {"ok": True, "have": [0, 1]} and keys[0] == ["one.mp3", os.path.getsize(U1)]
      and MUSIC not in other.items)
sent = other.web_cover_file("one.mp3", str(os.path.getsize(U1)), "10.0.0.7")
check(f"...and for one of them: a JPEG, no bigger than a cover's kept ({len(sent or b'')} bytes)",
      sent[:2] == b"\xff\xd8"
      and Image.open(io.BytesIO(sent)).size == (600, 600)
      and other.web_cover_file("Lost Song - Nobody.mp3", os.path.getsize(U3), "10.0.0.7") is None
      and other.web_cover_file("lost song - nobody.mp3", os.path.getsize(BARE), "10.0.0.7") is None
      and other.web_cover_file("../../etc/passwd", "5", "10.0.0.7") is None
      and other.web_cover_file("one.mp3", "lots", "10.0.0.7") is None)
yours[0] = False
check("not one of yours asking, or sharing off: told so, and given nothing",
      other.web_covers({"songs": keys, "from": "10.0.0.99"})["ok"] is False
      and other.web_cover_file("one.mp3", os.path.getsize(U1), "10.0.0.99") is None
      and (yours.__setitem__(0, True) or other.state["settings"].__setitem__("share", "Off")
           or other.web_covers({"songs": keys, "from": "10.0.0.7"})["ok"] is False))
other.state["settings"]["share"] = "On"
posted, fetched = [], []


def lan_post(url, body, timeout=None):
    posted.append((url, len(body["songs"])))
    if "10.0.0.9:" in url:
        raise OSError("no route to host")
    return theirs(other.web_covers, dict(body, **{"from": "10.0.0.7"}))


def lan_fetch(url):
    fetched.append(url)
    if url.startswith("http://10.0.0.8:5432/api/covers/file?"):
        q = dict(urllib.parse.parse_qsl(url.split("?", 1)[1]))
        got = other.web_cover_file(q["name"], q["size"], "10.0.0.7")
        if got is None:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return got
    return internet(url)


net.clear()
lan = CF.CoverFinder(fetch=lan_fetch, post=lan_post, pause=nap, clock=lambda: clock[0],
                     peers=lambda: [("http://10.0.0.9:5432", "Attic"), ("http://10.0.0.8:5432", "Kitchen")])
got_for.clear()
lan.on_found = got_for.append
lan.known = lambda path: path == SONG
lan.start([SONG, U1, U2, U3], thread=False)
check(f"Y with others of yours on: they're asked first (one that doesn't answer: the next), what they have copied "
      f"here ({lan.note!r})", got_for == [U1, U2] and lan.shared == 2 and lan.found == 2 and lan.done == 4
      and lan.note == "Found covers for 2 songs, 2 from your other Pietatos"
      and posted == [("http://10.0.0.9:5432/api/covers", 3), ("http://10.0.0.8:5432/api/covers", 3)])
check("...the folder's cover from one, the one it had found from the other: kept here as these songs' covers",
      C.cover_file(U1) == C.found_file(U1) and C.cover_file(U2) == C.found_file(U2)
      and near(Image.open(C.found_file(U1)).convert("RGB").getpixel((300, 258)), (255, 226, 170), 20)
      and near(Image.open(C.found_file(U2)).convert("RGB").getpixel((300, 300)), (55, 195, 110), 24))
check(f"...only what's left is looked up on the internet ({len(net)} questions: nobody knows it), and the song known "
      f"to have a cover wasn't looked at", [u.split("/")[2] for u in net] == [STORE_, MB_, MB_] and CF.missed(U3)
      and len([u for u in fetched if "/api/covers/file" in u]) == 2)
sys.path.append(ROOT + "/pitato")
import webui  # noqa: E402
web = webui.app.test_client()
check("the web page takes these from your other Pietatos without its password, and only these",
      "/api/covers" in webui.PEER_PATHS and "/api/covers/file" in webui.PEER_PATHS
      and web.post("/api/covers", json={"songs": "all of them"}).status_code == 400
      and web.post("/api/covers", json={"songs": [["a", 1]] * 201}).status_code == 400
      and web.post("/api/covers", data="x", content_type="text/plain").status_code == 400)

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
M.CoverFinder = lambda **kw: made_finders.append(
    CF.CoverFinder(fetch=internet, pause=lambda s: None, **kw)) or made_finders[-1]
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

# ---- for real: another Pietato, asked through its web page -------------------------------------------------------
TV = S + "/tv"
os.makedirs(TV + "/Music/Tide")
shutil.copy(U1, TV + "/Music/Tide/one.mp3")
shutil.copy(U2, TV + "/Music/two.mp3")                  # (it has this song too, but no cover for it)
picture(TV + "/Music/Tide/cover.jpg", "hills")
os.remove(C.found_file(U1)); os.remove(C.found_file(U2))
tv = subprocess.Popen([sys.executable, TESTS + "/peer_pietato.py", TV, S + "/tv.log", "tv", "http://127.0.0.1:1",
                       "none"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1,
                      env=dict(os.environ, PITATO_OWN_MUSIC="1"))
try:
    line = tv.stdout.readline().split()
    tv_url = line[1] if line[:1] == ["READY"] else ""
    keys = [CF.song_key(U1), CF.song_key(U2)]

    def tell(words):
        tv.stdin.write(words + "\n")
        tv.stdin.flush()
        return tv.stdout.readline().strip()

    def tv_cover():
        """Its cover for the first of them, asked for as the finder asks (a JPEG, or what it says instead)."""
        try:
            return CF.fetch(f"{tv_url}/api/covers/file?" + urllib.parse.urlencode({"name": "one.mp3",
                                                                                   "size": keys[0][1]}))
        except urllib.error.HTTPError as ex:
            return ex.code

    tell("peer http://10.0.0.9:5432 Attic")                # (its only other Pietato: not at this address)
    first = CF.post_json(tv_url + "/api/covers", {"songs": keys}, timeout=10)
    check(f"another Pietato up ({tv_url}); this isn't one of its own asking: it says nothing of its covers ({first})",
          bool(tv_url) and first.get("ok") is False and "have" not in first and tv_cover() == 404)
    tell("hear " + json.dumps(dict(m.share_beacon("Den", full=True), port=5432)))
    net.clear()
    real = CF.CoverFinder(fetch=lambda url: CF.fetch(url) if url.startswith(tv_url) else internet(url),
                          pause=lambda secs: None, peers=lambda: [(tv_url, "tv")])
    real.start([U1, U2], thread=False)
    check(f"...heard it: asked through its web page (Music never opened there), the cover it has for one of the two "
          f"comes over ({real.note!r})", real.shared == 1 and real.found == 1
          and real.note == "Found covers for 1 song, 1 from your other Pietatos"
          and C.cover_file(U1) == C.found_file(U1)
          and near(Image.open(C.found_file(U1)).convert("RGB").getpixel((300, 300)), (55, 195, 110), 24)
          and C.cover_file(U2) is None and tv_cover()[:2] == b"\xff\xd8" and net == [])
finally:
    tv.kill()

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
here = ear.levels(time.monotonic() - t0 + 2.0)
check(f"FFmpeg and a song with a kick every half second: its beats found on the half seconds ({got}), "
      f"{ahead:.1f} s ahead of what's heard, and its bars there ({here and len(here)})", len(got) >= 4
      and all(abs(p * 2 - round(p * 2)) < 0.1 for p in got) and -0.5 < ahead <= E.EAR_AHEAD + 0.3
      and here is not None and len(here) == E.BARS and max(here) > 0.3)
ear.close()
time.sleep(0.3)
check("...closed: its FFmpeg gone", ear.proc is None or ear.proc.poll() is not None)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
os._exit(0)
