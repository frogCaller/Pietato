"""A 16-bit screen's few shades (the GPi Case's, and most Pis' at the console: 32 of red and of blue, 64 of green).
home.py's stepped spreads a soft picture over them in a fine, even pattern: each pixel one of the screen's own shades,
patches of it as bright as they should be, no flat blocks of one colour, its pattern lined up wherever a piece of it
is made; a picture with all 256 to a colour left as it is. Now playing's wash and its cover's glow on such a screen:
smooth there (where they were blocks of colour), the glow's piece matching the wash round it; on the rest, as they
were. Game beat's floor the same (no green cast on its grey tiles)."""
import io, os, shutil, sys, types
from paths import SP, TESTS  # noqa: E402  (this test's folder of work; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import numpy as np
from PIL import Image, ImageDraw
import pietato_all as g
from pitato import beatgame as BG
from pitato import cover as C
from pitato.screens.music import GLOW_SHOWS
from pitato.home import stepped

S = SP + "/tshades"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + "/home/u/Music")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: S + "/home/u"
g.wifi_quality = lambda: 62.0
g.cpu_temp = lambda: 48.0
ok_all = []
DEPTH = (5, 6, 5)
LEVELS = [set(round(k * 255 / (2 ** b - 1)) for k in range(2 ** b)) for b in DEPTH]


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def shown(pic):
    """What a 16-bit screen shows of a picture: each colour's top bits (5, 6, 5), as bright as they are there."""
    a = np.asarray(pic.convert("RGB")).astype(np.int32)
    return np.dstack([(a[..., 0] >> 3) * 255 / 31, (a[..., 1] >> 2) * 255 / 63, (a[..., 2] >> 3) * 255 / 31])


def patches(a, n=8):
    a = np.asarray(a, np.float64)
    h, w = a.shape[0] // n * n, a.shape[1] // n * n
    return a[:h, :w].reshape(h // n, n, w // n, n, -1).mean(axis=(1, 3))


def screens_own(pic):
    a = np.asarray(pic.convert("RGB"))
    return all(set(np.unique(a[..., c]).tolist()) <= LEVELS[c] for c in range(3))


def runs(a):
    """How long, on average, a run of one colour along a row is."""
    a = np.asarray(a)
    same = (a[:, 1:] == a[:, :-1]).all(axis=2)
    return a.shape[0] * a.shape[1] / max(1, a.shape[0] * a.shape[1] - same.sum())


# ---- stepped ------------------------------------------------------------------------------------------------
ys, xs = np.mgrid[0:96, 0:320].astype(np.float32)
soft = Image.fromarray(np.dstack([20 + xs / 8, 24 + xs / 7 + ys / 9, 30 + xs / 6 - ys / 12]).astype(np.uint8))
out = stepped(soft, DEPTH)
err = np.abs(patches(shown(out)) - patches(np.asarray(soft))).max()
cut = np.abs(patches(shown(soft)) - patches(np.asarray(soft))).mean()
check(f"stepped: each pixel one of the screen's own shades, patches of it as bright as they should be (within "
      f"{err:.2f}; plain, the screen's off by {cut:.2f}), no flat blocks (runs of {runs(shown(out)):.1f} px, "
      f"plain {runs(shown(soft)):.1f})", screens_own(out) and err < 1.5 and cut > 1.5 and runs(shown(out)) < 3
      and runs(shown(soft)) > 6)
piece = stepped(soft.crop((13, 5, 200, 60)), DEPTH, (13, 5))
check("...its pattern lined up wherever a piece of it is made", np.array_equal(np.asarray(piece),
                                                                               np.asarray(out)[5:60, 13:200]))
check("...a picture on a screen with all 256 shades left as it is", stepped(soft, 8) is soft)


# ---- Now playing ------------------------------------------------------------------------------------------------
class FB:
    w, h, same = 640, 480, True

    def __init__(self, bpp):
        self.last, self.bpp = None, bpp
        self.fields = [(11, 5), (5, 6), (0, 5)] if bpp == 16 else [(16, 8), (8, 8), (0, 8)]

    def show(self, img):
        self.last = img.copy()

    def show_part(self, img, box):
        self.show(img)

    def close(self):
        pass


n = 600
yy = np.mgrid[0:n, 0:n][0].astype(np.float32) / n
art = Image.fromarray((np.array([252, 150, 60.0]) + (np.array([120, 70, 150.0]) - np.array([252, 150, 60.0]))
                       * yy[..., None]).astype(np.uint8))
ImageDraw.Draw(art).ellipse((190, 150, 410, 370), fill=(255, 226, 170))
m = g.Media(); m.load_fonts(); m.fb = FB(16); m.active = True
m.status_sig = m.status_signature()
music = next(i for i, t in enumerate(g.LIBRARY) if t["name"] == "Music")
song = {"title": "Song", "src": f"{S}/home/u/Music/song.mp3", "sub": "", "kind": "audio"}
m.cover_for = lambda it: (art, (240, 140, 80))
m.to_player = lambda line: None
m.queue, m.qi, m.cur, m.kind = [song], 0, song, "audio"
m.proc = types.SimpleNamespace(poll=lambda: None, stdin=io.StringIO())
m.meta = {"title": "Harbour Lights", "artist": "Someone", "length": 200}
m.pos = 50
m.tab, m.view, m.now_from = music, "now", "list"
lay = m.now_layout()
pics = m.now_pics(song, lay)
wash, plain = pics["wash"], C.cover_wash(art, (lay["W"], lay["foot"]), g.BG, (240, 140, 80))
region = (300, 150, 630, 420)
err = np.abs(patches(shown(wash.crop(region))) - patches(np.asarray(plain.crop(region)))).max()
check(f"Now playing on a 16-bit screen: its wash smooth there (patches within {err:.2f} of what they should be, runs "
      f"of {runs(shown(wash.crop(region))):.1f} px; as it was, runs of {runs(shown(plain.crop(region))):.1f})",
      screens_own(wash) and err < 1.5 and runs(shown(wash.crop(region))) < 3
      and runs(shown(plain.crop(region))) > 6 and np.array_equal(np.asarray(pics["soft"]), np.asarray(plain)))
part = m.now_lit(pics)
x0, y0, x1, y1 = pics["box"]
a, w = np.asarray(part), np.asarray(wash)
ring = np.ones(a.shape[:2], bool)
r = pics["reach"]
ring[r - 2:a.shape[0] - r + 2, r - 2:a.shape[1] - r + 2] = False
unlit = (np.asarray(pics["mask"]) * GLOW_SHOWS).astype(int) == 0
inside = w[y0:y1, x0:x1]
check(f"...its cover's glow too, each pixel round the cover one of the screen's shades, its piece the same as the "
      f"wash round it where the glow's gone ({int(unlit.sum())} px)",
      all(set(np.unique(a[ring][:, c]).tolist()) <= LEVELS[c] for c in range(3)) and unlit.sum() > 100
      and np.array_equal(a[unlit], inside[unlit]) and not np.array_equal(a[ring], inside[ring]))
m.dirty = True
m.flush()
same = (np.asarray(m.fb.last)[:lay["foot"]] == w).all(axis=2).mean()
check(f"...and the page drawn on them ({same:.0%} of it the wash)", same > 0.6)
m.fb = FB(32)
m.now_made = None
pics = m.now_pics(song, lay)
check("on a screen with all 256 shades: as it was", pics["wash"] is pics["soft"]
      and np.array_equal(np.asarray(pics["wash"]), np.asarray(plain)) and pics["depth"] == 8)

# ---- Game beat ----------------------------------------------------------------------------------------------
game = BG.BeatGame("/m/song.mp3", seed=1)
game.fit(640, 480)
deep = game.background((96, 170, 228), 8)
few = game.background((96, 170, 228), DEPTH)
err = np.abs(patches(shown(few)) - patches(np.asarray(deep))).max()
tint = lambda a: (np.asarray(a, np.float64)[..., 1] - np.asarray(a, np.float64)[..., 0]).mean()   # noqa: E731
check(f"Game beat's floor on a 16-bit screen: smooth (within {err:.2f}), its grey tiles grey (green over red "
      f"{tint(shown(few)):.2f}, as it should be {tint(deep):.2f}; as it was, {tint(shown(deep)):.2f})",
      screens_own(few) and err < 1.5 and abs(tint(shown(few)) - tint(deep)) < 0.6
      and abs(tint(shown(deep)) - tint(deep)) > 1)
m.fb = FB(16)
m.bars_fit = True
m.ear = None
m.set_setting("now_art", "Game")
m.dirty = True
m.flush()
check("...as Now playing draws it there", m.now_game() and m.beat_game is not None
      and m.beat_game.back[0][2] == DEPTH and screens_own(m.fb.last.crop((0, 120, 40, 360))))
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
