"""The bars every page has. The status bar: a WiFi mark at its right, a dot and three arcs over it, as many of the four
lit as the signal's strong; with no WiFi, struck through and orange, the words beside it. The tabs: the one that's up
in a pill, no line under it. The buttons along the bottom: A, B, X and Y each a dot in that button's own colour, L and
R little squares and a word (START) a pill, those outlined; a hint's two buttons (L R) side by side, each its own;
one lit in the accent while what it turns on is on. They're spread over the room there is, no closer than ever and no
further apart than they belong together, each tappable halfway to its neighbours, and a note at the right keeps its
place. On a light page they're in a light page's colours; the home screen's are a dark page's, whatever the pages
are."""
import json, os, shutil, subprocess, sys, time
from paths import SP, TESTS  # noqa: E402  (this test's folder of work; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
import numpy as np
import pitato.theme as T
import pitato.screens.draw as DR
from PIL import Image as PILImage, ImageDraw as PILDraw

S = SP + "/t_bars"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
for d in ("Music", "Videos", "Pictures", "Documents"):
    os.makedirs(f"{HOME}/{d}")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
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
g.cpu_temp = lambda: 48.0                            # (the status bar: the same from one drawing to the next)
NOW = time.struct_time((2026, 11, 7, 10, 7, 0, 5, 311, 0))
real_strftime, real_localtime = time.strftime, time.localtime
time.strftime = lambda fmt, t=None: real_strftime(fmt, NOW if t is None else t)
time.localtime = lambda secs=None: NOW if secs is None else real_localtime(secs)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480; last = None; frames = 0
    def show(self, img): FB.last = img.copy(); FB.frames += 1
    def show_part(self, img, box): FB.last = img.copy(); FB.frames += 1
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
texts = []
real_text = PILDraw.ImageDraw.text


def spy(self, xy, text, *a, **k):
    texts.append((str(text), xy[0], xy[1], k.get("font"), k.get("anchor")))
    return real_text(self, xy, text, *a, **k)


def tab(name):
    return next(k for k, t in enumerate(g.LIBRARY) if t["name"] == name)


def drawn():
    """The screen, drawn again: its picture (numbers), and what was written on it, where."""
    del texts[:]
    PILDraw.ImageDraw.text = spy
    m.dirty = True
    m.flush()
    PILDraw.ImageDraw.text = real_text
    return np.asarray(FB.last.convert("RGB")).astype(int), list(texts)


def near(pic, box, colour, tol=10):
    """How many of a box's pixels are that colour, or close to it."""
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    return int((np.abs(pic[y0:y1, x0:x1] - np.array(colour)).max(axis=2) <= tol).sum())


def px(pic, x, y):
    return tuple(int(v) for v in pic[int(round(y)), int(round(x))])


def wide(text, font):
    return m.fonts[font].getlength(text)


def foot(hints, **kw):
    """The buttons along the bottom, drawn on a page of their own: (its picture, what was written and where, where a
    tap does what)."""
    img, d = m.canvas()
    was, m.taps_new = getattr(m, "taps_new", None), []
    del texts[:]
    PILDraw.ImageDraw.text = spy
    m.footer(d, hints, pill=False, **kw)
    PILDraw.ImageDraw.text = real_text
    taps, m.taps_new = m.taps_new, was
    return np.asarray(img.convert("RGB")).astype(int), list(texts), taps


def laid(hints, wrote):
    """Where each hint is: [(its buttons' left edge, its words' right edge, [each button's middle])]."""
    keys = [(t, x) for t, x, _, f, a in wrote if f is m.fonts["key"] and a == "mm"]
    words = [(t, x) for t, x, _, f, a in wrote if f is m.fonts["small"] and a == "lm"]
    out, k = [], 0
    for n, h in enumerate(hints):
        parts = PARTS(h[0])
        mids = [x for _, x in keys[k:k + len(parts)]]
        k += len(parts)
        first = 22 if len(parts[0]) == 1 else max(wide(parts[0], "key") + 14, 24)
        out.append((mids[0] - first / 2, words[n][1] + wide(h[1], "small"), mids))
    return out


PARTS = getattr(DR, "key_parts", lambda label: [label])
GAPS = getattr(DR, "HINT_GAPS", (18, 18))
PAD = getattr(DR, "TAB_PAD", 0)
HUES = dict(T.ACCENTS)
m = g.Media(); m.enter()
W, H = FB.w, FB.h
RIM = DR.mix(g.ROW, g.MUTED, 0.45)                    # (a pill's outline, as the drawing mixes it)
FY = H - m.FOOTER // 2                                # (the buttons along the bottom: their middle)

# ---- the tabs
m.open_app(tab("Apps")); m.tick()
DR.wifi_quality = lambda: 60.0
page, wrote = drawn()
names = [(t, x, f) for t, x, y, f, a in wrote if f in (m.fonts["tab"], m.fonts["tab_b"]) and a == "lm"]
up = [(t, x) for t, x, f in names if f is m.fonts["tab_b"]]
ty = m.STATUS_H + (m.HEADER - m.STATUS_H) // 2 - 2
x0 = 20 + (up[0][1] if up else 0) - PAD               # (the strip's own picture is put down 20 in)
x1 = x0 + wide("Apps", "tab_b") + 2 * PAD
rim_px = near(page, (x0 + 14, ty - 14, x1 - 14, ty - 13), RIM, 6)
check(f"the tabs: the one that's up (Apps) bold, in a pill ({rim_px} px of its outline along its top, of "
      f"{round(x1 - x0 - 28)}; inside it {px(page, x0 + 5, ty)}, a little lighter than the page's {g.BG}), the others "
      f"plain ({[t for t, _, f in names if f is m.fonts['tab']][:3]}...)", [t for t, _ in up] == ["Apps"]
      and PAD >= 8 and rim_px >= (x1 - x0 - 28) * 0.9 and px(page, x0 + 5, ty) == DR.mix(g.BG, g.ROW, 0.85)
      and len(names) >= 4)
strip = near(page, (0, m.STATUS_H, W, m.HEADER), g.ACCENT, 8)
check(f"...and no line under it, in the accent or any colour ({strip} px of the accent between the status bar and "
      f"the page)", strip == 0)
after = sorted(x for t, x, f in names if x > up[0][1]) if up else []
before = sorted((x, t) for t, x, f in names if up and x < up[0][1])
check("...its pill clear of the names either side of it (as far from them as they are from each other)",
      (not after or 20 + after[0] >= x1 + 19) and (not before or 20 + before[-1][0] + wide(before[-1][1], "tab")
                                                   <= x0 - 19))
taps = [box for box, what in m.taps_now() if what == ("tab", tab("Apps"))]
check(f"...and a tap anywhere on it is that tab's ({taps})", len(taps) == 1 and taps[0][0] <= x0 and taps[0][2] >= x1
      and taps[0][1] <= ty - 14 and taps[0][3] >= ty + 14)
m.press("r"); m.tick()
page2, wrote2 = drawn()
up2 = [t for t, x, y, f, a in wrote2 if f is m.fonts["tab_b"] and a == "lm"]
check(f"R: the next tab's in it instead ({up2})", up2 == [g.LIBRARY[m.strip_tab()]["name"]] and up2 != ["Apps"]
      and near(page2, (0, m.STATUS_H, W, m.HEADER), RIM, 6) > 40)
m.press("l"); m.tick()

# ---- the status bar's WiFi mark
SY = m.STATUS_H // 2 + 1
MW, MH = getattr(DR, "WIFI_SIZE", (20, 16))


def mark(quality, hotspot=False):
    """The status bar's right end with that signal: (the picture, what's written there, the mark's box)."""
    DR.wifi_quality = lambda: quality
    m.hotspot_st["up"] = hotspot
    pic, wrote = drawn()
    m.hotspot_st["up"] = False
    said = [(t, x, f) for t, x, y, f, a in wrote if a == "rm" and t in ("No WiFi", "Hotspot")]
    right = W - 20 - (wide(said[0][0], "status_b" if said[0][2] is m.fonts["status_b"] else "status") + 7
                      if said else 0)
    return pic, said, (right - MW, SY - MH // 2 - 1, right, SY + MH // 2 - 1)


def spans(pic, box, colour, tol=60):
    """How wide the mark's lit part is at its top (its first three rows) and at its bottom (its last three)."""
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    lit = np.abs(pic[y0:y1, x0:x1] - np.array(colour)).max(axis=2) <= tol
    rows = [np.flatnonzero(r) for r in lit]
    rows = [(r.max() - r.min() + 1) if len(r) else 0 for r in rows]
    return max(rows[:4]), max(rows[-4:])


pic4, said4, box4 = mark(60.0)
lit4, top4 = near(pic4, box4, g.TEXT, 60), spans(pic4, box4, g.TEXT)
pic2, said2, box2 = mark(30.0)
lit2, dim2 = near(pic2, box2, g.TEXT, 60), near(pic2, box2, g.LINE, 12)
pic1, said1, box1 = mark(10.0)
lit1 = near(pic1, box1, g.TEXT, 60)
check(f"the status bar, WiFi on and strong: a mark at its right end, nothing said: a dot with arcs over it, wider "
      f"the higher they are ({top4[0]} px across at its top, {top4[1]} at its bottom), all of it lit ({lit4} px)",
      said4 == [] and box4[2] == W - 20 and top4[0] >= 14 and 2 <= top4[1] <= 7 and lit4 >= 60
      and near(pic4, box4, g.WARN, 30) == 0)
check(f"...weaker: less of it lit ({lit2} px at half strength, the rest there but dim: {dim2} px; {lit1} px at its "
      f"weakest, the dot alone)", said2 == [] and lit4 > lit2 > lit1 >= 6 and dim2 >= 20
      and spans(pic1, box1, g.TEXT)[0] == 0 and near(pic2, box2, g.WARN, 30) == 0)
pic0, said0, box0 = mark(None)
warn0 = near(pic0, box0, g.WARN, 60)
across = [int((np.abs(pic0[int(box0[1] + r), int(box0[0]):int(box0[2])] - np.array(g.WARN)).max(axis=1) <= 90).sum())
          for r in (2, MH // 2, MH - 3)]
check(f"...no WiFi: the words at its right end, bold, in orange ({[(t, x) for t, x, _ in said0]}), and the mark "
      f"before them in orange too ({warn0} px), struck through (orange on each of its rows, top to bottom: {across}), "
      f"none of it white", [(t, x) for t, x, _ in said0] == [("No WiFi", W - 20)]
      and said0[0][2] is m.fonts["status_b"] and warn0 >= 40 and min(across) >= 1
      and near(pic0, box0, g.TEXT, 30) == 0)
pich, saidh, boxh = mark(None, hotspot=True)
check(f"...its own hotspot up: Hotspot, quietly, as ever ({[(t, x) for t, x, _ in saidh]}), the mark there, not "
      f"struck through, not orange", [(t, x) for t, x, _ in saidh] == [("Hotspot", W - 20)]
      and saidh[0][2] is m.fonts["status"] and near(pich, boxh, g.WARN, 40) == 0 and near(pich, boxh, g.LINE, 12) >= 30)
DR.wifi_quality = lambda: 60.0

# ---- the buttons along the bottom
SIX = [("A", "On/off"), ("B", "Stop"), ("X", "Sound"), ("Y", "Mutate"), ("START", "More"), ("HOME", "Back")]
pic, wrote, taps = foot(SIX)
at = laid(SIX, wrote)
dots = {k: px(pic, at[n][2][0] - 8, FY) for n, (k, _) in enumerate(SIX[:4])}
check(f"along the bottom: A, B, X and Y each a dot in that button's own colour ({dots})",
      dots == {"A": HUES["Red"], "B": HUES["White"], "X": HUES["Pink"], "Y": HUES["Gold"]})
letters = {k: px(pic, at[n][2][0], FY - 11) for n, (k, _) in enumerate(SIX[:4])}
pills = {k: (px(pic, at[n][2][0], FY - 11), px(pic, at[n][2][0], FY + 8)) for n, (k, _) in enumerate(SIX) if n >= 4}
check(f"...a word a pill, outlined, the page's row colour inside ({pills}; the outline {RIM})",
      all(v == (RIM, g.ROW) for v in pills.values()) and len(pills) == 2)
gaps = [at[n + 1][0] - at[n][1] for n in range(len(at) - 1)]
check(f"...spread over the room there is: as far apart as each other ({[round(v, 1) for v in gaps]}), the first where "
      f"it always was ({at[0][0]:.0f}), the last one's words ending at the right edge ({at[-1][1]:.0f} of {W - 20})",
      max(gaps) - min(gaps) <= 1.0 and GAPS[0] <= min(gaps) and max(gaps) <= GAPS[1] and at[0][0] == 20
      and W - 22 <= at[-1][1] <= W - 20 and GAPS[1] > GAPS[0])
keys = sorted((box, what[1]) for box, what in taps if what[0] == "keys")
meet = [round(keys[n + 1][0][0] - keys[n][0][2], 1) for n in range(len(keys) - 1)]
check(f"...each tappable, its button and its words, halfway to the next ({[k for _, k in keys]}; between them: "
      f"{meet})", [k for _, k in keys] == ["a", "b", "x", "y", "start", "home"] and all(abs(v) <= 0.6 for v in meet)
      and all(box[0] <= at[n][0] and box[2] >= at[n][1] and box[1] == H - m.FOOTER and box[3] == H
              for n, (box, _) in enumerate(keys)))
TWO = [("A", "Open"), ("B", "Back")]
pic, wrote, taps = foot(TWO)
at2 = laid(TWO, wrote)
check(f"...two of them: together at the left, no further apart than {GAPS[1]} px ({at2[1][0] - at2[0][1]:.0f}), not "
      f"one at each end", at2[0][0] == 20 and abs(at2[1][0] - at2[0][1] - GAPS[1]) <= 0.6 and at2[1][1] < W / 2)
LR = [("L R", "Instrument"), ("SELECT", "Start"), ("Y", "Shuffle", True)]
pic, wrote, taps = foot(LR)
at3 = laid(LR, wrote)
mids = at3[0][2]
sq = [(px(pic, x, FY - 11), px(pic, x - 8, FY), px(pic, x - 11, FY - 11)) for x in mids]
halves = sorted((box[0], box[2], what[1]) for box, what in taps if what[0] == "keys" and what[1] in ("l", "r"))
check(f"...a hint's two buttons (L R): each its own, side by side ({[round(x) for x in mids]}), little squares, "
      f"outlined, their corners round ({sq}); the left one L's to tap, the right one R's ({halves})",
      PARTS("L R") == ["L", "R"] and len(mids) == 2 and mids[1] - mids[0] == 22 + getattr(DR, "KEY_GAP", 0)
      and all(s == (RIM, g.ROW, g.BG) for s in sq) and [h[2] for h in halves] == ["l", "r"]
      and len(halves) == 2 and abs(halves[0][1] - halves[1][0]) <= 0.6
      and m.key_w(PILDraw.Draw(PILImage.new("RGB", (4, 4))), "L R") == 48)
check(f"...two words (SEL ST), a word or a pair of arrows: one ({PARTS('SEL ST')}, {PARTS('START')}, "
      f"{PARTS('◀▶')}), and A B two dots", PARTS("SEL ST") == ["SEL ST"] and PARTS("START") == ["START"]
      and PARTS("◀▶") == ["◀▶"] and PARTS("A B") == ["A", "B"] and PARTS("A") == ["A"])
lit = px(pic, at3[2][2][0] - 8, FY)
check(f"...one that's on (Shuffle): lit, in the accent, not its own colour ({lit})", lit == g.ACCENT)
NOTE = "12 of 40"
pic, wrote, taps = foot(SIX[:3], right=NOTE)
at4 = laid(SIX[:3], wrote)
note = [(x, a) for t, x, y, f, a in wrote if t == NOTE]
check(f"...with a note at the right ({note}): it's there, the buttons at the left ({at4[-1][1]:.0f})",
      note == [(W - 20, "rm")] and at4[-1][1] + 16 <= W - 20 - wide(NOTE, "small"))
pic, wrote, taps = foot(SIX, right=NOTE)
at5 = laid(SIX, wrote)
note = [(x, a) for t, x, y, f, a in wrote if t == NOTE]
fits = at5[0][0] + sum(b - a for a, b, _ in at5) + GAPS[0] * 5 + 16 + wide(NOTE, "small") <= W - 20
check(f"...and with as many buttons as there's room for beside it ({'it fits' if fits else 'it does not fit'}): "
      f"{'they stop short of it' if fits else 'it is left out, the buttons all there'} ({at5[-1][1]:.0f})",
      len(at5) == 6 and ((note == [(W - 20, "rm")] and at5[-1][1] + 15 <= W - 20 - wide(NOTE, "small")) if fits
                         else note == []))
CREDIT = "Open-Meteo"
pic, wrote, taps = foot(SIX, credit=CREDIT)
shown = [t for t, x, y, f, a in wrote if f is m.fonts["small"] and a == "lm"]
last = max(x + wide(t, "small") for t, x, y, f, a in wrote if f is m.fonts["small"] and a == "lm")
check(f"...a credit (where the numbers come from) is always there, and what would run into it is left out "
      f"({shown}, ending at {last:.0f})", [(x, a) for t, x, y, f, a in wrote if t == CREDIT] == [(W - 20, "rm")]
      and 1 <= len(shown) < 6 and last <= W - 20 - wide(CREDIT, "small") - 17)
fit6 = m.hints_room(SIX + [("SELECT", "Something long to say"), ("L R", "And another one")], keep=("A", "B"))
pic, wrote, taps = foot(fit6)
at6 = laid(fit6, wrote)
check(f"...more than fit: the ones that do ({len(fit6)} of 8), none past the right edge ({at6[-1][1]:.0f})",
      2 <= len(fit6) < 8 and at6[-1][1] <= W - 12 and fit6[:2] == SIX[:2])

# ---- a light page
m.set_setting("look", "Light")
light = T.PALETTES["Light"]
pic, wrote, taps = foot(SIX)
at7 = laid(SIX, wrote)
dots = {k: px(pic, at7[n][2][0] - 8, FY) for n, (k, _) in enumerate(SIX[:4])}
pill = (px(pic, at7[4][2][0], FY - 11), px(pic, at7[4][2][0], FY + 8))
check(f"a light page: the dots in a light page's colours, deeper to read against it ({dots}), a pill white, with a "
      f"grey outline ({pill})", dots == {k: T.ACCENTS_LIGHT[h] for k, h in (("A", "Red"), ("B", "White"),
                                                                                ("X", "Pink"), ("Y", "Gold"))}
      and pill == (DR.mix(light["ROW"], light["MUTED"], 0.45), light["ROW"]) and g.ROW == light["ROW"])
m.open_app(tab("Apps")); m.tick()
page, wrote = drawn()
up = [(t, x) for t, x, y, f, a in wrote if f is m.fonts["tab_b"] and a == "lm"]
x0 = 20 + up[0][1] - PAD
check(f"...the tab that's up: its pill white on the pale page ({px(page, x0 + 5, ty)})", [t for t, _ in up] == ["Apps"]
      and px(page, x0 + 5, ty) == DR.mix(light["BG"], light["ROW"], 0.85))
m.go_home(); m.tick()
home, wrote = drawn()
a_mid = [x for t, x, y, f, a in wrote if t == "A" and f is m.fonts["key"]]
check(f"...the home screen's, on its dark background: a dark page's, whatever the pages are (A: "
      f"{px(home, a_mid[0] - 8, FY) if a_mid else None})", len(a_mid) == 1
      and px(home, a_mid[0] - 8, FY) == HUES["Red"])
m.set_setting("look", "Dark")
m.go_home(); m.tick()
home, wrote = drawn()
a_mid = [x for t, x, y, f, a in wrote if t == "A" and f is m.fonts["key"]]
start = [x for t, x, y, f, a in wrote if t in ("Y",) and f is m.fonts["key"]]
check(f"Dark again, the home screen: A red, Y gold ({px(home, a_mid[0] - 8, FY) if a_mid else None}, "
      f"{px(home, start[0] - 8, FY) if start else None})", len(a_mid) == 1
      and px(home, a_mid[0] - 8, FY) == HUES["Red"] and len(start) == 1 and px(home, start[0] - 8, FY) == HUES["Gold"])

m.active = False
m.shutdown()
n_bad = ok_all.count(False)
print("ALL OK" if not n_bad else f"FAILED {n_bad}")
sys.exit(1 if n_bad else 0)
