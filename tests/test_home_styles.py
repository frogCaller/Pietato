"""Settings > Home screen style: Bright, Glass (to start with) and Cards (Minimal's gone: one picked before is
Glass now), each drawn its own way, and each with every app's line along the bottom, what's playing popping up, and
the weather there once Weather knows where you are (and not before). Cards on a bigger screen: a TV's as far
apart across as down; an ultrawide's in two rows of taller cards (▶, ▼ and ▲ going through them); the GPi
Case's as ever. Settings > Background: the dark ones as ever, and brighter ones with them (strong colours, pale
ones), the home screen's words in the ink each needs; A on its row opens a page of them all."""
import io, json, os, shutil, subprocess, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from PIL import ImageDraw
S = SP + "/t_home_styles"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME + "/Music"); os.makedirs(HOME + "/Pictures")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
json.dump({"settings": {"location": {"name": "Portland", "admin1": "Oregon", "country": "US", "lat": 45.5, "lon": -122.6}}},
          open(g.STATE_FILE, "w"))
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
real_run = subprocess.run
subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                       if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in
                                       {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli", "vcgencmd"}
                                       else real_run(cmd, *a, **k))
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480; last = None
    def show(self, img): FB.last = img.copy()
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
said = []
inked = {}                                           # what's said: the colour it's in (the last, if said twice)
real_text = ImageDraw.ImageDraw.text


def drawn(m):
    """What the home screen says (and with which font), drawn afresh."""
    said.clear(); inked.clear()
    ImageDraw.ImageDraw.text = lambda self, xy, text, *a, **k: (said.append((str(text), k.get("font"), xy)),
                                                              inked.__setitem__(str(text), k.get("fill")),
                                                              real_text(self, xy, text, *a, **k))[2]
    try:
        m.home_base = (None, None)
        m.dirty = True; m.flush()
    finally:
        ImageDraw.ImageDraw.text = real_text
    return [t for t, _, _ in said]


def near(a, b, tol=14):
    return max(abs(x - y) for x, y in zip(a[:3], b[:3])) <= tol


m = g.Media(); m.enter()
m.weather.data = {"code": 2, "is_day": True, "temp": 68, "days": [{"hi": 72, "lo": 55}]}
apps = [a for a, _ in m.home_apps()]
F = m.fonts

# ---- the setting
rows = [r[0] for r in m.settings_rows()]
row = m.settings_rows()[rows.index("home_style")]
check(f"Settings has it, after Background ({row[1]}: {row[2]})", rows.index("home_style") == rows.index("wallpaper") + 1
      and row[1] == "Home screen style" and row[2] == ["Bright", "Glass", "Cards"])
check("Glass to start with", m.setting("home_style") == "Glass" and m.home_style() == "Glass")
for old, new in (("Original", "Bright"), ("Style 2", "Glass"), ("Style 3", "Glass"), ("Style 4", "Cards"),
                 ("Minimal", "Glass")):
    m.state["settings"]["home_style"] = old
    assert m.setting("home_style") == new and m.home_style() == new, (old, m.setting("home_style"))
check("one picked by its earlier name (Original, Style 2...): the same one, by its name now; Minimal: Glass", True)
m.state["settings"]["home_style"] = "Glass"
m.tab = m.tab_index("settings"); m.view = "list"; m.set_page = "root"; m.set_sel = rows.index("home_style")
seen = []
for _ in range(3):
    m.press("right"); seen.append(m.setting("home_style"))
check(f"right goes through them all and round ({seen})", seen == ["Cards", "Bright", "Glass"])
check("...and it's kept", json.load(open(g.STATE_FILE))["settings"]["home_style"] == "Glass")
m.state["settings"]["home_style"] = "Teletext"
check("one it doesn't know: Glass", m.home_style() == "Glass")
m.go_home()

shots = {}
for style in ["Bright", "Glass", "Cards"]:
    m.set_setting("home_style", style)
    m.view = "home"; m.home_sel = apps.index("Games")
    t0 = time.perf_counter()
    texts = drawn(m)
    took = time.perf_counter() - t0
    img = FB.last.convert("RGB"); shots[style] = img
    slots = g.home_layout(len(apps), 5)
    x0, y0, x1, y1 = m.card_box(apps.index("Games"), slots, 5, 0)
    missing = []
    for k, name in enumerate(apps):                 # every app's line along the bottom
        m.home_sel = k
        if g.HOME_ICONS[name][1] not in drawn(m):
            missing.append(name)
    m.home_sel = apps.index("Games")
    check(f"{style}: drawn ({took * 1000:.0f} ms the first time), every app's line at the bottom (missing: {missing})",
          not missing)
    texts = drawn(m)                                # (Games picked again)
    img = FB.last.convert("RGB")
    fonts = {t: f for t, f, _ in said}
    clock = next(t for t, f, _ in said if ":" in t and len(t) <= 8)
    if style == "Bright":
        date = next((t for t in texts if "day, " in t), None)
        check("...the time big and bold (the typeface the others have), the date under it",
              fonts[clock] is F["home1_clock"] and fonts.get(date) is F["home1_date"])
        check("...an accent ring round the app picked", near(img.getpixel((int(x0) - 5, int((y0 + y1) / 2))), g.ACCENT))
        check("...its name bold, the others' not", fonts.get("Games") is F["home1_label_b"]
              and fonts.get("Music") is F["home_label"])
        check("...the buttons straight on the background, a thin line over them (no bar of their own)",
              near(img.getpixel((100, 480 - m.FOOTER + 4)), g.LINE, 4)
              and img.getpixel((5, 470)) == g.wallpaper("Midnight", (640, 480)).getpixel((5, 470)))
        tile = m.home_icon("Games")
        check(f"...bright tiles, white glyphs (Games: {tile.getpixel((10, 6))[:3]})", tile.size == (72, 72)
              and near(tile.getpixel((10, 6)), (58, 152, 96), 4) and near(img.getpixel((int(x0 + 36), int(y0 + 30))),
                                                                          (246, 248, 250), 40))
    elif style == "Glass":
        check("...the time thin (Inter)", fonts[clock] is F["home_clock"])
        check("...the app picked: a bright edge", sum(img.getpixel((int(x0 + 37), int(y0 + 1)))) > 450)
        check("...a thin line over the buttons", near(img.getpixel((100, 480 - m.FOOTER + 4)), g.LINE, 4)
              and not near(img.getpixel((5, 480 - m.FOOTER + 4)), g.LINE, 4))
    else:
        check("...an accent line by the time", near(img.getpixel((18, 60)), g.ACCENT))
        check("...cards: the picked one edged in the accent", near(img.getpixel((int((x0 + x1) / 2), int(y0))), g.ACCENT, 30))
        check(f"...as wide as fit ({x1 - x0:.0f} x {y1 - y0:.0f})", x1 - x0 == 108 and y1 - y0 == 92)
        check("...Home on its card", "Home" in texts)
        a_x = next(xy for t, f, xy in said if t == "A")[0]
        check("...rings round the buttons' letters", near(img.getpixel((int(a_x) - 10, 456)), (150, 158, 170), 40)
              and near(img.getpixel((int(a_x), 456 - 6)), img.getpixel((int(a_x), 456 - 6)), 0))

# ---- Cards on a bigger screen: a TV's as far apart as its rows are; an ultrawide's in two rows of taller cards ----
def card_gaps(cols):
    """(a card's width and height, the gap across, the gap down) for the cards just drawn."""
    slots = g.home_layout(len(apps), cols)
    a, b, c = (m.card_box(k, slots, cols, 0) for k in (0, 1, cols))
    return round(a[2] - a[0]), round(a[3] - a[1]), round(b[0] - a[2]), round(c[1] - a[3])


m.set_setting("home_style", "Cards")
m.view, m.home_sel = "home", 0
m.fb.w, m.fb.h = 960, 540                           # (a TV's, its menus 960 x 540)
texts = drawn(m)
wide, high, across, down = card_gaps(m.home_columns(len(apps)))
check(f"Cards on a TV: five across, as far apart across as down, none drawn out wide ({wide} x {high}, {across} "
      f"across, {down} down)", m.home_columns(len(apps)) == 5 and across == down == 27 and wide <= 1.75 * high
      and "Settings" in texts)
m.fb.w, m.fb.h = 1140, 480                          # (an ultrawide's: 3440 x 1440, its menus 1140 x 480)
texts = drawn(m)
cols = m.home_columns(len(apps))
wide, high, across, down = card_gaps(cols)
check(f"...on an ultrawide: two rows, {cols} across, taller cards as far apart across as down ({wide} x {high}, "
      f"{across} across, {down} down), every app on it", cols == 8 and high == 118 and across == down == 26
      and m.home_rows_fit() == 2 and all(n in texts for n in ("Home", "Games", "Settings")))
glyph_y = next(xy for t, f, xy in said if t == "Home")[1]
x0, y0, x1, y1 = m.card_box(0, g.home_layout(len(apps), cols), cols, 0)
check(f"...its name lower down a taller card, in the middle of it with its glyph ({glyph_y - y0:.0f} of {y1 - y0:.0f})",
      y1 - glyph_y == 16 + (118 - 92) // 2)
moves = []
for b in ("right",) * 8 + ("down", "up"):
    m.press(b); moves.append(apps[m.home_sel % len(apps)])
check(f"...▶ along the top row and on to the next; ▼ and ▲ to the nearest below and above ({moves})",
      moves[:8] == apps[1:9] and moves[8] == apps[8] and moves[9] in apps[:8])
m.set_setting("home_style", "Glass")
check(f"...Glass's on an ultrawide: three rows as ever ({m.home_columns(len(apps))} across)",
      m.home_columns(len(apps)) == 5 and m.home_rows_fit() == 3)
del m.fb.w, m.fb.h                                  # (the GPi Case's again)
m.set_setting("home_style", "Cards")
check(f"...and on the GPi Case as ever ({card_gaps(5)})",
      m.home_columns(len(apps)) == 5 and card_gaps(5) == (108, 92, 14, 12))

# the pop-up, in each
radio = {"key": "r1", "title": "Jazz Radio", "kind": "radio", "src": "http://192.168.1.20:8000/jazz", "sub": ""}
m.spawn = lambda args, target: (setattr(m, "proc", type("P", (), {"poll": lambda self: None, "stdin": io.StringIO(),
                                                                  "wait": lambda self, timeout=None: 0,
                                                                  "kill": lambda self: None})()),
                                setattr(m, "started", time.monotonic()))
m.play([radio], 0, show=False)
m.meta["song"] = "Take Five"
for style in ["Bright", "Glass", "Cards"]:
    m.set_setting("home_style", style)
    m.view = "home"; m.home_sel = 0
    m.pop_now()
    texts = drawn(m)
    check(f"{style}: what's playing pops up, START said", "ON THE RADIO" in texts and "Jazz Radio" in texts
          and "Take Five" in texts and "Now playing" in texts)
    m.np_until = 0.0
    texts = drawn(m)
    check(f"{style}: ...and goes", "ON THE RADIO" not in texts and "Now playing" not in texts and "68°" in texts)
m.stop()

# ---- the weather on the home screen: there once Weather knows where you are, not before (no setting for it)
check("no 'On the home screen' setting", "widget" not in [r[0] for r in m.settings_rows()])
for style in ["Bright", "Glass", "Cards"]:
    m.set_setting("home_style", style)
    m.view = "home"
    texts = drawn(m)
    with_place = "68°" in texts
    loc = m.state["settings"].pop("location")
    texts = drawn(m)
    m.state["settings"]["location"] = loc
    check(f"{style}: the weather with a place ({with_place}), none without ({'68°' not in texts})",
          with_place and "68°" not in texts)
old_state = {"settings": {"widget": "Just the time", "home_style": "Minimal", "location": loc}}
json.dump(old_state, open(g.STATE_FILE, "w"))
m2 = g.Media()
check(f"a save from before: its 'Just the time' forgotten, Minimal shown as Glass ({m2.setting('home_style')})",
      "widget" not in m2.state["settings"] and m2.setting("home_style") == "Glass" and m2.home_style() == "Glass")

# ---- the backgrounds: the home screen's words take the ink each needs (as ever on a dark one; white, a soft shadow
# under them, on a strong colour; dark on a pale one), and its tiles go with it
def home_on(style, wall, pop=False):
    """The home screen drawn in this style over this background: (the picture, what it says, the time as said)."""
    m.set_setting("home_style", style); m.set_setting("wallpaper", wall)
    m.view = "home"; m.home_sel = apps.index("Games")
    if pop:
        m.pop_now()
    texts = drawn(m)
    return FB.last.convert("RGB"), texts, next(t for t in texts if ":" in t and len(t) <= 8)


def is_dark(c):
    return max(c[:3]) < 110


def tile_look(img, name="Files"):
    """(how light an app's tile is, about; its darkest and its lightest part)."""
    x0, y0, x1, y1 = (int(v) for v in m.card_box(apps.index(name), g.home_layout(len(apps), 5), 5, 0))
    part = np.asarray(img.crop((x0 + 8, y0 + 8, x1 - 8, y1 - 8)).convert("L"))
    return float(part.mean()), int(part.min()), int(part.max())


import numpy as np
about = g.HOME_ICONS["Games"][1]
for style in ["Bright", "Glass", "Cards"]:
    img, texts, clock = home_on(style, "Midnight")
    as_ever = texts.count(clock) == 1 and inked[clock] == g.TEXT
    dim = tile_look(img)
    tile = m.home_icon("Files")
    img, texts, clock = home_on(style, "Candy")
    check(f"{style} on a strong colour (Candy): the time white, a soft shadow under it; on a dark one, as ever",
          as_ever and inked[clock] == (255, 255, 255) and texts.count(clock) == 2
          and (style == "Cards" or inked["Music"][0] > 240) and inked[about][0] > 230)
    check(f"...its tiles as on a dark one ({tile_look(img)[0]:.0f}, {dim[0]:.0f})",
          m.home_icon("Files") is tile and abs(tile_look(img)[0] - dim[0]) < 12)
    img, texts, clock = home_on(style, "Peach")
    check(f"{style} on a pale one (Peach): the time, the apps' names and the line along the bottom dark, said once",
          is_dark(inked[clock]) and texts.count(clock) == 1 and is_dark(inked["Music"]) and is_dark(inked[about])
          and is_dark(inked["68°"]))
    light = tile_look(img)
    if style == "Bright":
        check("...its tiles as bright as ever", m.home_icon("Files") is tile)
    else:
        check(f"...{'light glass tiles, their glyphs dark' if style == 'Glass' else 'white cards'} "
              f"({light[0]:.0f}, from {light[1]} to {light[2]}; on a dark one {dim[0]:.0f}, from {dim[1]} to {dim[2]})",
              light[0] > dim[0] + 50 and light[2] > 225 and light[1] < 120 and dim[0] < 120 and dim[2] > 180
              and m.home_icon("Files") is not tile)
for wall in ("Aurora", "Snow", "Candy"):               # (Glass, the app picked: its tile's shadow fades away under
    img, texts, clock = home_on("Glass", wall)         #  it evenly, not cut short where its name is drawn afresh:
    x0, y0, x1, y1 = (int(v) for v in m.card_box(apps.index("Games"), g.home_layout(len(apps), 5), 5, 0))
    cut = y1 + m.home_geometry()[3] - 11               #  on Aurora that was a step of 22 in one row, among 1s and 2s)
    down = [sum(img.getpixel((x0 + 8, y))) for y in range(cut - 4, cut + 4)]
    steps = [b - a for a, b in zip(down, down[1:])]
    check(f"Glass on {wall}: the picked tile's shadow fades away under it evenly, no edge (row by row: {steps})",
          max(steps) - min(steps) <= 12)
m.play([radio], 0, show=False)
m.meta["song"] = "Take Five"
for style in ["Bright", "Glass", "Cards"]:
    img, texts, clock = home_on(style, "Midnight", pop=True)
    as_ever = inked["Jazz Radio"] == g.TEXT
    img, texts, clock = home_on(style, "Peach", pop=True)
    x0 = next(xy for t, f, xy in said if t == "Jazz Radio")[0]
    check(f"{style} on a pale one: what's playing pops up on a light card, its words dark (a dark one: as ever)",
          as_ever and is_dark(inked["Jazz Radio"]) and is_dark(inked["Take Five"])
          and min(img.getpixel((int(x0) + 200, 40))) > 200)
m.stop(); m.np_until = 0.0
from PIL import Image
Image.new("RGB", (800, 600), (250, 250, 250)).save(HOME + "/Pictures/white.png")
m.set_setting("picture", HOME + "/Pictures/white.png")
img, texts, clock = home_on("Glass", "Picture")
check(f"a picture of yours, even a white one: darkened, the words light as ever ({img.getpixel((5, 5))})",
      inked[clock] == g.TEXT and max(img.getpixel((5, 5))) < 160 and m.home_ink() is g.INK["light"])
m.set_setting("picture", "")
img, texts, clock = home_on("Glass", "Picture")
check("...Picture with none picked yet: Midnight's look", inked[clock] == g.TEXT
      and img.getpixel((5, 5)) == g.wallpaper("Midnight", (640, 480)).getpixel((5, 5)))
m.state["settings"]["wallpaper"] = "Teletext"
img, texts, clock = home_on("Glass", "Teletext")
check("...one it doesn't know: Midnight's too", inked[clock] == g.TEXT
      and img.getpixel((5, 5)) == g.wallpaper("Midnight", (640, 480)).getpixel((5, 5)))

# ---- Settings > Background: ◀ ▶ on its row as ever; A opens a page of them all, a little picture each
m.set_setting("wallpaper", "Midnight"); m.set_setting("home_style", "Glass")
m.tab = m.tab_index("settings"); m.view = "list"; m.set_page = "root"
m.set_sel = [r[0] for r in m.settings_rows()].index("wallpaper")
texts = drawn(m)
check("Settings > Background: ◀ ▶ change it, A shows them all", "Change" in texts and "See them all" in texts)
m.press("right")
check(f"...▶: the next ({m.setting('wallpaper')})", m.setting("wallpaper") == g.WALLPAPERS[1])
m.press("left"); m.press("left")
check(f"...◀ from the first: round to the last, a picture of yours ({m.setting('wallpaper')})",
      m.setting("wallpaper") == "Picture")
m.press("right")
m.press("a")
texts = drawn(m)
cols = m.wall_layout()[0]
check(f"...A: a page of them all by name, {cols} across, the one in use picked",
      m.set_page == "wallpaper" and all(w in texts for w in g.WALLPAPERS) and cols == 5
      and g.WALLPAPERS[m.set_sel] == m.setting("wallpaper") == "Midnight" and "Use this" in texts)
m.press("down"); m.press("down"); m.press("right")
check(f"...▼ ▼ ▶: two rows down and one along ({g.WALLPAPERS[m.set_sel]}), nothing changed yet",
      m.set_sel == 2 * cols + 1 and m.setting("wallpaper") == "Midnight")
m.press("a")
check(f"...A: that one's the background ({m.setting('wallpaper')}), kept, the page still up",
      m.setting("wallpaper") == g.WALLPAPERS[2 * cols + 1] and m.set_page == "wallpaper"
      and json.load(open(g.STATE_FILE))["settings"]["wallpaper"] == g.WALLPAPERS[2 * cols + 1])
m.set_sel = g.WALLPAPERS.index("Picture")
texts = drawn(m)
check("...on Picture: A picks one of yours", "Pick a picture" in texts and "One of your own" in texts)
m.press("b")
check("...B: back to Settings, on its row", m.set_page == "root"
      and m.settings_rows()[m.set_sel][0] == "wallpaper")
small = FB.w, FB.h
FB.w, FB.h = 480, 320                               # (a small handheld's screen)
m.press("a"); m.set_sel = len(g.WALLPAPERS) - 1
texts = drawn(m)
check(f"...on a small screen: four across, the page going down to the one picked ({m.wall_layout()[:5]})",
      m.wall_layout()[0] == 4 and "Picture" in texts and "Midnight" not in texts)
m.set_sel = 0
texts = drawn(m)
check("...and back up", "Midnight" in texts and "Picture" not in texts and "▼" in texts)
FB.w, FB.h = 960, 540                               # (a TV's)
texts = drawn(m)
cols, cw, ch, pw, ph, top = m.wall_layout()
check(f"...on a TV: five across still, bigger pictures, every one on the page ({pw} x {ph})",
      cols == 5 and pw > 120 and ph > 64 and all(w in texts for w in g.WALLPAPERS)
      and top + 4 * ch <= 540 - m.FOOTER)
FB.w, FB.h = small
m.press("b")
m.set_setting("wallpaper", "Midnight")
m.go_home()

# ---- the grid's kept, but not across styles
m.set_setting("home_style", "Cards"); m.view = "home"; m.dirty = True; m.flush()
base = m.home_base
m.home_sel = 2; m.dirty = True; m.flush()
check("the grid's drawn once while the pick moves", m.home_base is base)
m.set_setting("home_style", "Glass"); m.dirty = True; m.flush()
check("...and afresh for another style", m.home_base is not base and m.home_base[0][0] == "Glass")
os.makedirs(S + "/shots", exist_ok=True)
for style, img in shots.items():
    img.save(S + f"/shots/{style.replace(' ', '')}.png")
m.leave()

# ---- the background on a big TV: a smooth sweep, no bands or blocks (its colours' steps dithered)
import numpy as np


def edges(a, k=12):
    """How sharply its colour turns anywhere down the middle, averaged k rows at a time (what the eye sees of it from
    the sofa): a band's edge turns sharply (a whole step at once, before the change: 1 or more); a smooth sweep
    hardly at all, however steep."""
    col = a[:, a.shape[1] // 2 - 40:a.shape[1] // 2 + 40].astype(float).mean(axis=1)
    sweep = col[:len(col) // k * k].reshape(-1, k, 3).mean(axis=1)
    return np.abs(np.diff(sweep, n=2, axis=0)).max()


SHIFT = np.array([3, 2, 3], np.uint8)                  # (an RGB565 screen: the bits each colour loses)
for name in ("Midnight", "Aurora", "Dusk", "Ocean", "Forest"):
    a = np.asarray(g.wallpaper(name, (1920, 1080)))
    turn = edges(a)
    check(f"{name} at 1920 x 1080: a smooth sweep, no band's edge or block anywhere ({turn:.2f}; it was 1.0 to 1.2)",
          turn < 0.4 and np.array_equal(a, np.asarray(g.wallpaper(name, (1920, 1080)))))
    b = np.asarray(g.wallpaper(name, (640, 480), depth=(5, 6, 5)))
    kept = b >> SHIFT                                  # (the steps a 16-bit screen keeps of it)
    exact = np.rint(kept * (255 / ((1 << (8 - SHIFT.astype(int))) - 1))).astype(np.uint8)
    turn = edges(kept.astype(float) * (1 << SHIFT), 24)
    check(f"...on a 16-bit screen (the GPi Case's): dithered to its own steps, kept as they are, no band's edge "
          f"({turn:.2f}; it was 4.3 to 6)", np.array_equal(b, exact) and turn < 2.0)

# ---- the backgrounds themselves: the dark ones as they were, and brighter ones: strong colours, pale ones
names = [w for w in g.WALLPAPERS if w != "Picture"]
check(f"Settings > Background: {len(g.WALLPAPERS)} to pick from, each with a look of its own, Midnight first (what it "
      f"starts with), a picture of yours last",
      sorted(names) == sorted(g.WALLS) and len(set(g.WALLPAPERS)) == len(g.WALLPAPERS) >= 20
      and g.WALLPAPERS[0] == "Midnight" == g.SETTINGS_DEFAULT["wallpaper"] and g.WALLPAPERS[-1] == "Picture")
AT = [(40, 30), (320, 240), (600, 60), (100, 440), (560, 400)]
WAS = {"Midnight": [(18, 22, 30), (14, 18, 24), (18, 21, 29), (11, 14, 19), (12, 15, 20)],
       "Dusk": [(58, 38, 85), (57, 37, 70), (89, 53, 95), (20, 17, 36), (45, 30, 55)],
       "Ocean": [(21, 94, 126), (14, 63, 88), (11, 69, 100), (12, 43, 62), (7, 31, 49)],
       "Forest": [(24, 73, 52), (27, 64, 44), (40, 92, 61), (10, 26, 20), (21, 47, 32)],
       "Aurora": [(35, 81, 97), (37, 60, 96), (43, 71, 136), (15, 36, 44), (24, 39, 73)],
       "Black": [(0, 0, 0)] * 5}
off = {name: max(max(abs(a - b) for a, b in zip(g.wallpaper(name, (640, 480)).getpixel(xy), c))
                 for xy, c in zip(AT, was)) for name, was in WAS.items()}
check(f"the ones there were: as they were ({off})", max(off.values()) <= 3)


def lum(rgb):
    """How light a colour is to the eye, 0 to 1 (as contrast is worked out from)."""
    c = np.asarray(rgb, np.float64) / 255
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return c[..., 0] * 0.2126 + c[..., 1] * 0.7152 + c[..., 2] * 0.0722


def stands_out(ink, part):
    """How far a colour stands out from nearly all of a part of a picture (the contrast between them, 1 to 21)."""
    a, b = lum(ink), lum(part)
    return float(np.percentile((np.maximum(a, b) + 0.05) / (np.minimum(a, b) + 0.05), 5))


WORDS = {"time": (20, 20, 240, 108), "weather": (400, 20, 620, 108), "names1": (40, 206, 600, 222),
         "names2": (40, 312, 600, 328), "names3": (40, 417, 600, 433), "foot": (28, 456, 612, 476)}
kinds, least = {}, {}
for name in names:
    a = np.asarray(g.wallpaper(name, (640, 480)))
    ink = g.wall_ink(name)
    kinds.setdefault(ink, []).append(name)
    light = float(lum(a).mean())
    for where, (x0, y0, x1, y1) in WORDS.items():      # (Glass's on the GPi Case's screen: where its words are)
        key = "label" if where.startswith("names") else "text"
        least[name, where] = stands_out(g.INK[ink][key], a[y0:y1, x0:x1])
    if (light > 0.45) != (ink == "dark") or (ink == "light" and light > 0.12):
        check(f"{name}: its ink ({ink}) goes with how light it is ({light:.2f})", False)
worst = min(least, key=least.get)
check(f"each one's ink goes with it: light on the dark ones ({len(kinds['light'])}), white on strong colours "
      f"({len(kinds['white'])}), dark on pale ones ({len(kinds['dark'])})",
      set(kinds) == {"light", "white", "dark"} and len(kinds["white"]) >= 4 and len(kinds["dark"]) >= 5
      and g.wall_ink("Picture") == g.wall_ink("Teletext") == "light")
check(f"...and the home screen's words stand out from every one, where they are (least: {worst[0]}'s {worst[1]}, "
      f"{least[worst]:.1f} to 1)", least[worst] >= 3.0)
for name in ("Rainbow", "Snow", "Peach"):              # (new ones with no shape down their middle)
    a = np.asarray(g.wallpaper(name, (1920, 1080)))
    check(f"{name} at 1920 x 1080: a smooth sweep too ({edges(a):.2f})", edges(a) < 0.4)
    b = np.asarray(g.wallpaper(name, (640, 480), depth=(5, 6, 5)))
    kept = b >> SHIFT
    check("...and on a 16-bit screen: dithered to its own steps",
          np.array_equal(b, np.rint(kept * (255 / ((1 << (8 - SHIFT.astype(int))) - 1))).astype(np.uint8)))
t0 = time.perf_counter()
for name in names:
    g.wallpaper(name, (640, 480), depth=(5, 6, 5))
took = (time.perf_counter() - t0) / len(names)
check(f"made once each, when it's picked: {took * 1000:.0f} ms a background on this machine, about", took < 1.0)
sizes = {name: g.wallpaper(name, (960, 540)).size for name in ("Arcade", "Sky", "Space", "Candy")}
check("the ones with shapes (a sun, clouds, stars, bubbles): made at any size",
      set(sizes.values()) == {(960, 540)} and g.wallpaper("Sky", (1140, 480)).size == (1140, 480)
      and g.wallpaper("Arcade", (2, 2)).size == (2, 2))
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
