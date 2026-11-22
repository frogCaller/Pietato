"""Just the Bot's face, on the whole screen (Settings > Bot > Just its face): it looks round the room. It starts in
the middle; every so often it goes somewhere else on the screen, its eyes turning that way first, smoothly, all of it
on the screen wherever it rests, whatever its shape; more often in the middle than anywhere else; drawn only as it
changes; with something to do (listening, thinking, talking, a timer) it's back in the middle at once, and stays till
the next time it'd go somewhere; and nothing's left behind by any of its frames: the screen's always what drawing the
whole page again would give. No glow round it while music plays (it had one, which didn't look good on a GPi Case's
screen): with a song or the radio on it's drawn just as it is with nothing playing, and no ear's kept for the song.
Its X menu over it: left as it is, the main loop left to wait (it wasn't: a whole core, for as long as the menu was
open). Its chat page with the conversation, as it was; Now playing's own glow, as ever, its buttons still there for a
tap on the web page's copy of the screen after a frame of it (they weren't). Pictures saved, to look at."""
import math, os, shutil, sys, time
from paths import SP, TESTS  # noqa: E402  (this test's folder of work; the tests' own)
S = SP + "/t_faceroom"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
os.makedirs(S + "/pics")
try:
    import evdev  # noqa: F401  (what media mode reads its buttons with: a stand-in's enough here)
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import Image, ImageChops, ImageDraw
from pitato import face as F
from pitato.screens import bot as B
from pitato.screens import music as M
from pitato.fine import detail

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    if t.get("files"):
        t["files"] = [f.replace("/home/*", S + "/home/*") for f in t["files"]]
import gk_static; gk_static.use_home(g, HOME)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


# ---- the face's own part in it (face.py) -----------------------------------------------------------------------------
places = [F.roam_at(k) for k in range(3000)]
seen = {p: places.count(p) for p in set(places)}
moves = sum(a != b for a, b in zip(places, places[1:]))
check(f"where it rests: {len(seen)} places, in the middle more than anywhere else ({seen[(0, 0)]} of 3000), none past "
      f"how far it can go", len(seen) >= 6 and seen[(0, 0)] == max(seen.values()) and seen[(0, 0)] < 1500
      and all(abs(x) <= 1 and abs(y) <= 1 for x, y in seen))
check(f"...somewhere else every {F.ROAM_SLOT * 3000 / moves:.0f} seconds or so, not all the time",
      8 <= F.ROAM_SLOT * 3000 / moves <= 20)
way = F.Roam((0, 0), (1, -1), 100.0, F.ROAM_SECS, led=True)
spots = [way.at(100 + F.ROAM_SECS * i / 50) for i in range(51)]
check("its way there: from where it was to where it's going, never back on itself",
      way.at(99.0) == (0, 0) and way.at(100 + F.ROAM_SECS) == (1, -1) and way.at(500.0) == (1, -1)
      and all(a[0] <= b[0] and a[1] >= b[1] for a, b in zip(spots, spots[1:])))
check("...gently: it sets off slowly and stops slowly", spots[2][0] < 0.02 and spots[48][0] > 0.98
      and max(b[0] - a[0] for a, b in zip(spots, spots[1:])) < 0.04)
before, mid, late = way.lead(100.0 - F.ROAM_LEAD + 0.2), way.lead(100.3), way.lead(100 + F.ROAM_SECS - 0.02)
check(f"its eyes go first: turned that way before it sets off ({before}), all the way while it goes, and looking "
      f"about again as it gets there ({late})", way.lead(99.0) is None and before[:2] == (1, -1) and before[2] > 0.7
      and way.at(100.0 - F.ROAM_LEAD + 0.2) == (0, 0) and mid[2] == 1.0 and late[2] < 0.05
      and way.lead(100 + F.ROAM_SECS) is None)
check("...on its way from when its eyes turn till it's there", not way.moving(99.7) and way.moving(99.8)
      and way.moving(100.5) and not way.moving(100 + F.ROAM_SECS))
home = F.Roam((1, 0), (0, 0), 50.0, F.ROAM_HOME)
check("back to the middle, with something to do: at once, its eyes where they are", home.lead(50.1) is None
      and home.moving(50.1) and home.at(50 + F.ROAM_HOME) == (0, 0) and F.ROAM_HOME < F.ROAM_SECS / 2)
_, gaze, _, _ = F.face_state("idle", 7.0, lead=(1, -1, 1.0))
check(f"its eyes, led: where they're led ({gaze}), not where they'd glance", gaze == (1, -1)
      and F.face_state("idle", 7.0, lead=(1, -1, 0.0))[1] == F.face_state("idle", 7.0)[1])

# how far it reaches, each way: everything it draws while it goes about, inside that
SHAPES = {"as it comes": None, "its biggest": {"eye_size": 10, "eye_height": 10, "eye_gap": 10, "mouth_size": 10},
          "its smallest": {"eye_size": 0, "eye_height": 0, "eye_gap": 0, "mouth_size": 0},
          "wide apart, square": {"eye_gap": 10, "eye_corners": 0, "eye_size": 7}}
for name, steps in SHAPES.items():
    for lashes in (False, True):
        shape = F.face_shape(steps)
        left, up, right, down = F.face_reach(shape, lashes)
        n, out = 150, 0
        for i in range(120):
            look = F.ROAM_LOOKS[i % len(F.ROAM_LOOKS)]
            a = i * 2.399
            lead = (math.cos(a), math.sin(a), (i % 4) / 3) if i % 3 else None
            im = Image.new("RGB", (2 * n, 2 * n), (0, 0, 0))
            F.draw_face(ImageDraw.Draw(im), n, n, n, look, i * 0.731, (255, 255, 255), (0, 0, 0), lashes=lashes,
                        shape=shape, lead=lead)
            bb = im.getbbox()
            out += bb is None or bb[0] < n - left * n or bb[1] < n - up * n or bb[2] > n + right * n \
                or bb[3] > n + down * n
        check(f"{name}{', eyelashes' if lashes else ''}: all it draws while it goes about, within its reach "
              f"({left:.2f} left, {up:.2f} up, {right:.2f} right, {down:.2f} down, of its size; {out} of 120 out)",
              out == 0 and max(left, right) < 0.8 and up < 0.68 and down < 0.5)


# ---- the Bot's page: just its face -----------------------------------------------------------------------------------
class FB:
    w, h, same = 640, 480, True
    frames = 0

    def __init__(self):
        self.last, self.parts = None, []

    def show(self, img):
        FB.frames += 1
        self.frames = FB.frames
        self.last = img.copy()
        self.parts.append(None)

    def show_part(self, img, box):
        FB.frames += 1
        self.frames = FB.frames
        self.last = img.copy()
        self.parts.append(tuple(box))

    def close(self):
        pass


class Player:
    stdin = None

    def poll(self):
        return None


ears = []


class FakeEar:
    """The ear for the song (ear.py's, Now playing's), stood in for: a beat as hard as the test says."""
    def __init__(self, src, where):
        self.src, self.closed = src, False
        ears.append(self)

    def level(self, place):
        return level[0]

    def close(self):
        self.closed = True


M.Ear = g.Ear = FakeEar
level = [0.0]
m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
BOT = "server = 127.0.0.1:1\nmodel = x\n"


def bot_txt(extra="face_only = on\n"):
    open(HOME + "/bot.txt", "w").write(BOT + extra)
    m.friend.load(m.friend_files())


bot_txt()
m.set_setting("battery", "Off")
m.set_setting("bot_mode", "chat")
m.tab = m.tab_index("friend"); m.view = "list"; m.load_tab(m.tab)
T = [0.0]
look = ["idle"]
m.face_now = lambda: T[0]                          # (its clock, and the main loop's: the test's)
m.face_look = lambda: look[0]
W, H = 640, 480
EDGE = 30                                          # (it's always this far in from the screen's edges, at least)
BACK = m.bot_palette()[1]
SLOT = F.ROAM_SLOT


def slot_with(place, after=40):
    """The next stretch of time, from `after` on, it'd rest at `place` in (which ROAM_SLOT)."""
    return next(k for k in range(after, after + 5000) if F.roam_at(k) == place)


def whole():
    """The page drawn whole, as it is now: its picture."""
    m.dirty = True
    m.flush()
    return m.fb.last


def drawn(img, back=None):
    """Where anything's drawn on the screen's background."""
    return ImageChops.difference(img.convert("RGB"), Image.new("RGB", img.size, back or BACK)).getbbox()


def same(a, b):
    return ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox() is None


def tick():
    """The main loop's part in it, once: its face's frame if one's due, Now playing's glow's, the screen."""
    m.face_tick(T[0])
    m.pulse_tick(T[0])
    m.flush()


def run(secs, each=None, dt=1 / 60, before=None):
    """...for secs, a look every dt. each(): called after every frame that's drawn; before(): before every look."""
    end = T[0] + secs
    n = 0
    while T[0] < end:
        was = FB.frames
        if before:
            before()
        tick()
        if FB.frames != was:
            n += FB.frames - was
            if each:
                each()
        T[0] += dt
    return n


# opened: in the middle, and there till the next time it'd go somewhere
k = slot_with((1, 0))
while F.roam_at(k - 1) != (0, -1):                 # (a stretch it'd be up at the top in, then one to the right)
    k = slot_with((1, 0), k + 1)
T[0] = (k - 1) * SLOT + 2.0
whole().save(S + "/pics/opened.png")
x, y, size = m.face_shot[3]
room = m.face_room()
check(f"opened: in the middle ({x:.0f}, {y:.0f}), as big as ever ({size:.0f}); it can go {[round(v) for v in room]} "
      f"from there (left, up, right, down)", (x, y) == (W / 2, H / 2) and size > 300
      and room[0] == room[2] and 60 <= room[0] <= 140 and 25 <= room[1] <= 70 and 25 <= room[3] <= 70)
ats = []
n = run(SLOT - 2.0 - 0.05, lambda: ats.append(m.face_shot[3]))
check(f"...and stays there for that stretch, though it'd be up at the top in it ({n} frames: blinks and glances)",
      all(a[:2] == (W / 2, H / 2) for a in ats) and 0 < n < 120)

# the next stretch: its eyes turn, then it goes, and it's all on the screen all the way
track, bad, stale, parts = [], [], [], []


def follow():
    at = m.face_shot[3]
    bb = drawn(m.fb.last)
    parts.append(m.fb.parts[-1])
    track.append((T[0], at[0], at[1], (bb[0] + bb[2]) / 2 - at[0]))
    if bb[0] < EDGE or bb[1] < EDGE or bb[2] > W - EDGE \
            or bb[3] > H - EDGE:
        bad.append((round(T[0] - k * SLOT, 2), bb))
    shown = m.fb.last
    if not same(shown, whole()):
        stale.append(round(T[0] - k * SLOT, 2))


T[0] = k * SLOT - 0.02
n = run(F.ROAM_LEAD + F.ROAM_SECS + 0.3, follow)
m.fb.last.save(S + "/pics/right.png")
first = next(t for t, x, y, e in track if x > W / 2 + 0.5) - k * SLOT
led = [e for t, x, y, e in track if 0.1 < t - k * SLOT < first]
check(f"the next stretch: it goes to the right, all the way ({track[-1][1]:.0f} of {W / 2 + room[2]:.0f}), in "
      f"{n} frames", abs(track[-1][1] - (W / 2 + room[2])) < 0.5 and track[-1][2] == H / 2 and 15 <= n <= 80)
check(f"...its eyes first: turned to the right {first:.2f} s before the rest of it sets off ({led[-1]:+.0f} px)",
      0.2 <= first <= 0.4 and led and led[-1] > 12)
steps = [abs(b[1] - a[1]) + abs(b[2] - a[2]) for a, b in zip(track, track[1:])]
check(f"...smoothly: {max(steps):.1f} px at most from one frame to the next", 2 < max(steps) <= 12)
check(f"...all of it on the screen all the way, a little in from the edge ({bad[:2]})", not bad)
check(f"...and nothing left behind where it was: each frame, what the whole page drawn again gives ({stale[:3]})",
      not stale)
check(f"...just its face each time, not the whole page ({parts[1]})", all(p is not None for p in parts[1:]))
quiet = run(0.3)
check(f"there: no frames till something changes ({quiet} in the next 0.3 s)", quiet <= 6)

# ten minutes of it
track, bad, stale = [], [], []
rests = {}


def note():
    at = m.face_shot[3]
    if not m.face_roam.moving(T[0]):
        rests[(round(at[0]), round(at[1]))] = rests.get((round(at[0]), round(at[1])), 0) + 1
    bb = drawn(m.fb.last)
    if bb[0] < EDGE or bb[1] < EDGE or bb[2] > W - EDGE \
            or bb[3] > H - EDGE:
        bad.append(bb)
    track.append((at[0], at[1]))
    if len(track) % 7 == 0 and not same(m.fb.last, whole()):
        stale.append(round(T[0], 2))


n = run(600, note)
steps = [abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(track, track[1:])]
check(f"ten minutes: it rests in {len(rests)} places ({sorted(rests)})", len(rests) >= 6
      and (W // 2, H // 2) in rests)
check(f"...always all on the screen ({bad[:2]}), never jumping ({max(steps):.1f} px at most between frames, across "
      f"and down together), nothing left behind ({stale[:3]})", not bad and max(steps) <= 20 and not stale)
check(f"...drawn only as it changes: {n / 600:.1f} frames a second, all told (its blinks, its glances, and about "
      f"{(F.ROAM_LEAD + F.ROAM_SECS) * 20 / (SLOT * 3000 / moves):.1f} a second for its going about)", n / 600 < 7)

# something to do: back in the middle, at once, and there till the next time it'd go somewhere
k = slot_with((-1, 0), int(T[0] // SLOT) + 2)
T[0] = k * SLOT - 0.5
run(0.5 + F.ROAM_LEAD + F.ROAM_SECS + 1.0)
away = m.face_shot[3]
for doing in ("listening", "thinking", "talking", "alert"):
    T[0] = k * SLOT + 3.0
    look[0] = "idle"
    m.face_roam = F.Roam((-1, 0), (-1, 0), T[0], 0)   # (away on the left, as it was)
    m.face_stay = None
    whole()
    look[0] = doing
    stale = []
    n = run(F.ROAM_HOME + 0.15, lambda: stale.append(1) if not same(m.fb.last, whole()) else None)
    at = m.face_shot[3]
    bx = B.BotScreen.face_box(at)
    check(f"away on the left, and it's {doing}: in the middle {F.ROAM_HOME} s later ({at[0]:.0f}, {at[1]:.0f}; "
          f"{n} frames), all that goes with it on the screen ({bx}), nothing left behind",
          abs(away[0] - (W / 2 - room[0])) < 0.5 and (at[0], at[1]) == (W / 2, H / 2) and n >= 4 and not stale
          and bx[0] >= 0 and bx[1] >= 0 and bx[2] <= W and bx[3] <= H)
look[0] = "idle"
ats = []
run(SLOT - 3.0 - F.ROAM_HOME - 0.15 - 0.2, lambda: ats.append(m.face_shot[3][:2]))
check("...done: it stays in the middle for the rest of that stretch", ats and set(ats) == {(W / 2, H / 2)})
nxt = F.roam_at(k + 1)
run(0.2 + F.ROAM_LEAD + F.ROAM_SECS + 0.2)
at = m.face_shot[3]
check(f"...and goes about again in the next ({nxt}: {at[0]:.0f}, {at[1]:.0f})",
      (at[0] != W / 2 or at[1] != H / 2) == (nxt != (0, 0)))

# asleep (not set up): in the middle
look[0] = "sleepy"
run(SLOT * 3)
check("asleep: in the middle", m.face_shot[3][:2] == (W / 2, H / 2))
look[0] = "idle"

# a slow Pi: fewer frames on its way
k = slot_with((1, 0), int(T[0] // SLOT) + 2)
T[0] = k * SLOT - 0.5
m.face_roam, m.face_stay = F.Roam((0, 0), (0, 0), T[0], 0), k - 1   # (in the middle, till this stretch)
whole()
m.pi_slow = True
n = run(0.5 + F.ROAM_LEAD + F.ROAM_SECS + 0.2)
m.pi_slow = False
check(f"a Pi Zero: its way there in {n} frames, {B.FACE_ONLY_FPS} a second at most",
      6 <= n <= (0.7 + F.ROAM_LEAD + F.ROAM_SECS) * B.FACE_ONLY_FPS + 2 and m.face_shot[3][0] > W / 2 + room[2] - 1)

# its shape: the bigger it's made, the less room; still all on the screen
bot_txt("face_only = on\nlashes = on\neye_size = 10\neye_height = 10\neye_gap = 10\nmouth_size = 10\n")
big = m.face_room()
bad = []
for place in ((-1, 0), (1, 0), (-0.8, -1), (0.9, 0.9), (0, -1)):
    T[0] = slot_with(place, int(T[0] // SLOT) + 2) * SLOT + 5.0
    m.face_roam = F.Roam(place, place, T[0], 0)
    m.face_stay = None
    bb = drawn(whole())
    bad += [bb] if bb[0] < EDGE or bb[1] < EDGE or bb[2] > W - EDGE or bb[3] > H - EDGE else []
m.fb.last.save(S + "/pics/big-eyes.png")
check(f"its eyes as big and far apart as they go, with eyelashes: less room ({[round(v) for v in big]}), all of it "
      f"on the screen wherever it rests ({bad[:2]})", big[0] < room[0] and big[1] <= room[1] and not bad)
bot_txt()

# a bigger screen: more room
m.fb.w, m.fb.h = 960, 540
wide = m.face_room()
T[0] = slot_with((1, 0), int(T[0] // SLOT) + 2) * SLOT + 5.0
m.face_roam, m.face_stay = F.Roam((1, 0), (1, 0), T[0], 0), None
bb = drawn(whole())
check(f"a 960x540 screen: more room ({[round(v) for v in wide]}), on the screen at its far right ({bb})",
      wide[0] > room[0] and bb[2] <= 960 - EDGE and bb[0] > 480)
m.fb.w, m.fb.h = W, H

# ---- music playing: its face just as it is with nothing playing (no glow), and no ear kept for the song --------------
def a_still_time(secs=2.5):
    """A moment early in one of its stretches with its eyes open and nothing of its own due for secs (no blink, no
    glance): there, in the middle, for that stretch. The page as it is then: its picture."""
    k = int(T[0] // SLOT) + 2
    while True:
        for i in range(8):
            t = k * SLOT + 0.3 + i * 0.1
            if F.face_state("idle", t)[0] == 1 and F.face_wait("idle", t) >= secs:
                T[0] = t
                m.face_roam, m.face_stay = None, None
                return whole().copy()
        k += 1


m.queue = [{"title": "Song", "src": HOME + "/Music/song.mp3", "kind": "audio", "sub": ""}]
m.qi, m.cur = 0, m.queue[0]


def play(kind="audio", src=None):
    m.cur = dict(m.queue[0], src=src or m.queue[0]["src"], kind=kind)
    m.proc, m.kind, m.paused = Player(), kind, False


for name, kind, src in (("a song of yours", "audio", None), ("the radio", "radio", "http://10.0.0.9/live")):
    m.proc, m.kind = None, None
    bare = a_still_time()
    tick()                                         # (its face's own next look: a while off, from here)
    play(kind, src)
    level[0] = 1.0                                 # (a beat, were anything listening for one)
    n = run(0.9)
    shown = m.fb.last.copy()
    check(f"{name} playing: its face just as it is with nothing playing, no glow ({n} frames in 0.9 s; "
          f"{len({c for _, c in shown.getcolors(100000)})} colours on the screen), no ear for it",
          same(shown, bare) and same(whole(), bare) and n == 0 and not ears and not m.pulse_wanted()
          and m.ear is None)
bare.save(S + "/pics/music.png")
left = [n for n in dir(m) if n.startswith(("face_glow", "face_lit", "face_pulse"))] \
    + [n for n in dir(F) + dir(B) if "glow" in n.lower()]
check(f"...and none of its glow's code left behind ({left})", not left)

# its menu over it: left as it is, and the main loop left to wait
play()
whole()
m.press("x")
m.flush()
was = FB.frames
run(5.0)
check(f"its X menu over it: left as it is ({FB.frames - was} frames in 5 s)",
      m.friend_more is not None and FB.frames == was)
check(f"...and the main loop left to wait, as with any menu: its face's next look {m.face_next - T[0]:+.2f} s off, not "
      f"overdue", 0.1 < m.face_next - T[0] <= 0.3)
m.press("b")
tick()
check("...closed: its face again", m.friend_more is None and m.face_shot is not None and same(m.fb.last, whole()))

# ---- as they were ----------------------------------------------------------------------------------------------------
# its chat page, with the conversation: its face in its card, where it is
bot_txt("")
T[0] = slot_with((1, 0), int(T[0] // SLOT) + 2) * SLOT + 5.0
had = len(ears)
chat = whole().copy()
at = m.face_shot[3]
n = run(SLOT * 2)
check(f"its chat page with the conversation: its face in its card ({at[0]:.0f}, {at[1]:.0f}), where it stays "
      f"({n} frames), no ear", m.face_shot[3] == at and at[0] < 200 and m.face_roam is None and len(ears) == had
      and at[2] == B.FACE_SIZE)
box = m.face_shot[1]
outside = Image.new("L", (W, H), 255)
outside.paste(0, box)
outside.paste(0, (0, 0, W, m.LIST_TOP))            # (not the clock, along the top)
check("...the rest of its page untouched by its face's frames",
      ImageChops.multiply(ImageChops.difference(m.fb.last, chat).convert("L"), outside).getbbox() is None)

# Now playing: the cover's glow, as ever, and its buttons still there for a tap after a frame of it
bot_txt()
m.view = "now"
m.meta, m.pos = {"title": "Song", "length": 180.0}, 12.0
level[0] = 0.0
m.dirty = True
for _ in range(100):                               # (drawn, and again once it's looked for the song's cover)
    m.flush()
    time.sleep(0.02)
    if not m.dirty:
        break
was = FB.frames
level[0] = 1.0
T[0] += 1.0
m.pulse_tick(T[0])
check(f"Now playing: its glow's frame on a beat, as ever (step {m.now_shot[2]}): the cover's part of the screen "
      f"({m.fb.parts[-1]}), an ear for the song", FB.frames == was + 1 and m.fb.parts[-1] is not None
      and m.now_shot[2] == g.GLOW_STEPS - 1 and len(ears) == had + 1 and ears[-1].src == m.cur["src"])
taps = [t for t in m.taps_now() if t[1] == ("keys", "a")]
check(f"...and its buttons still there for a tap on the web page's copy, after it ({taps[:1]})", bool(taps))

# ---- drawn finely (a big screen: two of the picture's pixels to each of the menus'): the same, sharper ---------------
from pitato import fine
fine.set_scale(2)
m2 = g.Media(); m2.load_fonts(); m2.fb = FB(); m2.active = True
m2.fb.w, m2.fb.h = 960, 540
m2.set_setting("bot_mode", "chat")
m2.tab = m2.tab_index("friend"); m2.view = "list"; m2.load_tab(m2.tab)
m2.face_now = lambda: T[0]
m2.face_look = lambda: "idle"
m2.queue, m2.qi, m2.cur = m.queue, 0, m.queue[0]
m2.proc, m2.kind, m2.paused = Player(), "audio", False
k = slot_with((-0.9, 0.9), int(T[0] // SLOT) + 2)
T[0] = k * SLOT - 0.2
m2.dirty = True; m2.flush()
stale, parts, n, had = [], set(), 0, len(ears)
end = T[0] + 0.2 + F.ROAM_LEAD + F.ROAM_SECS * 1.5 + 1.2
while T[0] < end:
    was = FB.frames
    m2.face_tick(T[0]); m2.pulse_tick(T[0]); m2.flush()
    if FB.frames != was:
        shown = m2.fb.last
        parts.add(m2.fb.parts[-1] is not None)
        n += 1
        m2.dirty = True; m2.flush()
        if ImageChops.difference(shown.pic, m2.fb.last.pic).getbbox() is not None:
            stale.append(round(T[0] - k * SLOT, 2))
    T[0] += 1 / 60
at = m2.face_shot[3]
bb = ImageChops.difference(m2.fb.last.pic, Image.new("RGB", m2.fb.last.pic.size, BACK)).getbbox()
m2.fb.last.save(S + "/pics/fine.png")
check(f"drawn finely, on a 960x540 screen, a song playing: to a corner ({at[0]:.0f}, {at[1]:.0f}) in {n} frames, all "
      f"on the screen ({bb} of {m2.fb.last.pic.size}), nothing left behind ({stale[:3]}), no ear",
      detail(m2.fb.last) == 2 and at[0] < 480 - 60 and at[1] > 270 + 20 and n > 20 and parts == {True}
      and not stale and bb[0] >= 2 * EDGE and bb[3] <= 1080 - 2 * EDGE and len(ears) == had)
fine.set_scale(1)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
