"""Settings > App pages: the pages inside the apps, Dark (as ever, to start with) or Light. Light: a pale page with
white rows and cards and dark words, on every tab and its pages, the accent a deeper one of its kind (to read against
white), a notice a dark pill (to stand out). The home screen keeps its background and its words, whatever the pages
are. Picked on the Pi or the web page, kept for next time, and nothing drawn before in the other look is left on the
screen: every page comes out as it does on one that started in that look, and back in Dark, to the pixel as it was.
What's dark anyway keeps its light words (the black before a video, Now playing's art). Notes starts on paper with
dark ink on a light page, till you pick; the Clock's dial is white, its hands dark."""
import json, os, shutil, subprocess, sys, time, types
from paths import SP, TESTS  # noqa: E402  (this test's folder of work; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
import numpy as np
import pitato.theme as T
import pitato.clock as CLOCK

S = SP + "/t_look"
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
NOW = time.struct_time((2026, 11, 7, 10, 7, 0, 5, 311, 0))   # ...and its clock (the Clock's hands too)
real_strftime, real_localtime = time.strftime, time.localtime
time.strftime = lambda fmt, t=None: real_strftime(fmt, NOW if t is None else t)
time.localtime = lambda secs=None: NOW if secs is None else real_localtime(secs)
CLOCK.time = types.SimpleNamespace(time=time.time, strftime=time.strftime, localtime=lambda secs=None: NOW)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480; last = None
    def show(self, img): FB.last = img.copy()
    def show_part(self, img, box): FB.last = img.copy()
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
DARK, LIGHT = T.PALETTES["Dark"], T.PALETTES["Light"]


def tab(name):
    return next(k for k, t in enumerate(g.LIBRARY) if t["name"] == name)


def drawn(m):
    m.dirty = True
    m.flush()
    return FB.last.convert("RGB")


def pale(img):
    """How much of a picture is light (each of its colours over 200), 0 to 1."""
    a = np.asarray(img)
    return float((a.min(axis=2) > 200).mean())


def has(img, colour):
    """How many of a picture's pixels are this colour."""
    return int((np.asarray(img) == np.array(colour, np.uint8)).all(axis=2).sum())


def lum(c):
    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2])


def contrast(a, b):
    hi, lo = max(lum(a), lum(b)), min(lum(a), lum(b))
    return (hi + 0.05) / (lo + 0.05)


LISTS = ("TV", "Music", "Radio", "Photos", "Videos", "Games", "Weather", "Apps", "Files")


def walk(m):
    """Its pages, one after another, each drawn: {what: its picture}. (The same from one walk to the next: the time
    stands still, and nothing on them moves.)"""
    out = {}
    for name in LISTS:
        m.go_home(); m.open_app(tab(name)); m.tick()
        out[name] = drawn(m)
    m.go_home(); m.open_app(tab("Finance")); m.tick()
    out["Finance*"] = drawn(m)                       # (*: what it says depends on when: looked at, not compared)
    m.go_home(); m.open_app(tab("Settings"))
    m.set_page, m.set_sel = "root", m.settings_root_index("look")
    for _ in range(100):                             # (Bluetooth's row: once it knows whether there is any)
        if m.bt_value() != "…":
            break
        m.tick(); time.sleep(0.05)
    out["Settings"] = drawn(m)
    m.set_sel = m.settings_root_index("wallpaper"); m.press("a")
    out["Settings > Background"] = drawn(m)
    m.press("b")
    m.set_page, m.set_sel = "root", m.settings_root_index("look")
    m.help_from, m.view = "list", "help"
    out["Controls"] = drawn(m)
    m.view = "list"
    m.open_keyboard("Town or city", "Port", lambda t: None)
    out["the keyboard"] = drawn(m)
    m.kb = None
    m.view = "list"
    m.go_home(); m.open_app(tab("Clock")); m.tick()
    out["Clock"] = drawn(m)
    m.press("a"); m.tick()                            # (its other look: big figures)
    out["Clock, in figures"] = drawn(m)
    m.press("a")
    m.go_home()
    out["the home screen"] = drawn(m)
    return out


m = g.Media(); m.enter()

# ---- the setting, and Dark as ever
rows = m.settings_root_rows()
keys = [k for k, _, _ in rows]
row = next((r for r in rows if r[0] == "look"), None)
check(f"Settings has App pages, after the accent colour: Dark or Light ({row})",
      row == ("look", "App pages", ["Dark", "Light"]) and keys.index("look") == keys.index("accent") + 1)
check("it starts Dark, as ever: the colours every module draws with are the ones they were",
      m.setting("look") == "Dark" and T.look() == "Dark" and g.BG == (16, 19, 23) and g.TEXT == (236, 239, 243)
      and g.ROW == (31, 37, 46) and g.ACCENT == dict(T.ACCENTS)["Blue"]
      and all(vars(mod)[k] == v for mod in g._mods for k, v in DARK.items() if k in vars(mod)))
dark = walk(m)
check(f"...and its pages are dark ({ {k: round(pale(v), 2) for k, v in dark.items()} })",
      all(pale(v) < 0.2 for k, v in dark.items()) and all(has(dark[k], DARK["BG"]) > 100000 for k in LISTS))

# ---- Light, picked on the Pi
m.open_app(tab("Settings"))
m.set_page, m.set_sel = "root", m.settings_root_index("look")
m.press("right")
theirs = {mod.__name__.split(".", 1)[1]: vars(mod) for mod in g._mods}
home_mods = [n for n in theirs if n in T.OWN_LOOK]
check(f"▶ on it: Light, kept ({m.setting('look')}), and every module that draws has the light colours",
      m.setting("look") == "Light" and T.look() == "Light"
      and json.load(open(g.STATE_FILE))["settings"].get("look") == "Light"
      and all(d[k] == v for n, d in theirs.items() if n not in T.OWN_LOOK for k, v in LIGHT.items() if k in d)
      and theirs["screens.draw"]["BG"] == LIGHT["BG"] and theirs["screens.finance"]["PI_BG"] == (255, 255, 255))
check(f"...but for the home screen's ({home_mods}): its background's colours and the accent as they were",
      sorted(home_mods) == ["home", "screens.home"]
      and all(theirs[n][k] == v for n in home_mods for k, v in DARK.items() if k in theirs[n])
      and theirs["screens.home"]["ACCENT"] == dict(T.ACCENTS)["Blue"]
      and theirs["screens.draw"]["ACCENT"] == T.ACCENTS_LIGHT["Blue"])
light = walk(m)
shares = {k: round(pale(v), 2) for k, v in light.items()}
check(f"every page is light now: a pale page, white rows, dark words ({shares}; Settings > Background has its "
      f"pictures of them all, dark ones too)",
      all(pale(light[k]) > (0.5 if k == "Settings > Background" else 0.9) for k in light if k != "the home screen")
      and all(has(light[k], LIGHT["BG"]) > 100000 for k in LISTS)
      and all(has(light[k], DARK["BG"]) == 0 for k in LISTS))
same_home = light["the home screen"].tobytes() == dark["the home screen"].tobytes()
check("...the home screen as it was, to the pixel (its background, its words, its accent, its buttons)", same_home)
if not same_home:
    dark["the home screen"].save(SP + "/look_home_dark.png"); light["the home screen"].save(SP + "/look_home_light.png")
check("the Finance card's white there, its words dark (it was black, its words white)",
      has(light["Finance*"], (255, 255, 255)) > 100000 and has(dark["Finance*"], (0, 0, 0)) > 100000
      and has(light["Finance*"], (0, 0, 0)) == 0)
check("the Clock on a light page: its dial white, its hands and figures dark (on a dark one: as ever)",
      has(light["Clock"], CLOCK.ON_PALE["face"]) > 20000 and has(light["Clock"], CLOCK.FACE) == 0
      and has(dark["Clock"], CLOCK.FACE) > 20000 and has(dark["Clock"], CLOCK.ON_PALE["face"]) == 0
      and has(light["Clock, in figures"], CLOCK.ON_PALE["text"]) > 500
      and has(dark["Clock, in figures"], CLOCK.ON_DARK["text"]) > 500)

# ---- nothing drawn before is left: as one that started Light draws them
json.dump({"settings": {"look": "Light"}}, open(g.STATE_FILE, "w"))
m2 = g.Media(); m2.enter()
fresh = walk(m2)
differ = [k for k in light if not k.endswith("*") and light[k].tobytes() != fresh[k].tobytes()]
check(f"each page as one that started in Light draws it, to the pixel: nothing kept from Dark is left "
      f"({differ or 'none differ'})", m2.setting("look") == "Light" and not differ)
for k in differ:
    light[k].save(f"{SP}/look_{k.replace(' ', '_')}_changed.png"); fresh[k].save(f"{SP}/look_{k.replace(' ', '_')}_fresh.png")

# ---- the accent on a light page; what reads against what
m2.set_setting("accent", "Gold")
check(f"an accent picked on a light page: a deeper one of its kind ({g.ACCENT}), the home screen's as ever",
      theirs["screens.draw"]["ACCENT"] == T.ACCENTS_LIGHT["Gold"] == g.ACCENT
      and theirs["screens.home"]["ACCENT"] == dict(T.ACCENTS)["Gold"] and g.BADGE["dir"] == T.ACCENTS_LIGHT["Gold"])
m2.set_setting("accent", "Blue")
reads = {name: round(contrast(c, LIGHT["ROW"]), 1) for name, c in T.ACCENTS_LIGHT.items()}
check(f"each accent reads against a white row ({reads}), and there's one for every accent there is",
      set(T.ACCENTS_LIGHT) == {a for a, _ in T.ACCENTS} and all(v >= 3.9 for v in reads.values()))
words = {k: round(contrast(LIGHT[k], LIGHT["BG"]), 1) for k in ("TEXT", "BODY", "MUTED", "WARN", "DONE")}
check(f"the page's words read against it ({words}), as they do on a dark one",
      words["TEXT"] >= 12 and words["BODY"] >= 6 and words["MUTED"] >= 3 and words["WARN"] >= 3.5
      and words["DONE"] >= 3 and contrast(DARK["MUTED"], DARK["BG"]) >= 3)

# ---- a notice; what's dark anyway
m2.go_home(); m2.open_app(tab("TV")); m2.tick()
m2.toast("Saved")
img = drawn(m2)
check("a notice on a light page: a dark pill, its words light (it stands out)",
      has(img, LIGHT["PILL"]) > 1500 and has(img, LIGHT["PILL_TEXT"]) > 20)
m2.msg = None
m2.render_curtain("A film", "Starting…")
img = FB.last.convert("RGB")
check("the black before a video: its words light, as ever (dark ones wouldn't show)",
      has(img, (0, 0, 0)) > 250000 and has(img, DARK["TEXT"]) > 200 and has(img, LIGHT["TEXT"]) == 0)
check("...on_dark gives a dark page's colours whatever the pages are, the accent too",
      T.on_dark("TEXT") == DARK["TEXT"] and T.on_dark("ACCENT") == dict(T.ACCENTS)["Blue"]
      and T.on_dark("KEY_FILL") == DARK["KEY_FILL"])

# ---- Notes: on paper with dark ink on a light page, till you pick; the Soundboard's buttons
m2.go_home(); m2.open_app(tab("Notes")); m2.tick()
note = m2.sims["notes"]
img = drawn(m2)
check(f"Notes on a light page: paper and dark ink, till you pick ({note.values['paper']}, {note.values['ink']})",
      (note.values["paper"], note.values["ink"]) == ("Paper", "Ink") and has(img, dict(g.NOTE_PAPERS)["Paper"]) > 150000)
m2.go_home()
m2.set_setting("look", "Dark")
check(f"...back on a dark one: Night and White, as ever ({note.values['paper']}, {note.values['ink']})",
      (note.values["paper"], note.values["ink"]) == ("Night", "White"))
m2.set_setting("sim_notes_paper", "Navy")
note.configure({"paper": "Navy"})
m2.set_setting("look", "Light")
check(f"one you picked is kept, whatever the pages are, and the other with it ({note.values['paper']}, "
      f"{note.values['ink']}: white on navy still reads)", (note.values["paper"], note.values["ink"]) == ("Navy", "White"))
m2.set_setting("sim_notes_paper", None)
from pitato.soundboard import Soundboard
board = Soundboard(616, 356)
board.pads = {"a": ("Ding", "ready")}
tile = board.tile("a", 120, 60).convert("RGB")
m2.sims["sound"] = board
m2.set_setting("look", "Dark")
again = board.tile("a", 120, 60).convert("RGB")
check("the Soundboard's buttons, kept as pictures: drawn again in the page's colours when they change",
      has(tile, LIGHT["BG"]) > 0 and has(tile, DARK["BG"]) == 0 and has(again, DARK["BG"]) > 0
      and has(again, LIGHT["BG"]) == 0 and board.backdrop == DARK["BG"])
del m2.sims["sound"]

# ---- Dark again: to the pixel as it was
back = walk(m2)
differ = [k for k in dark if not k.endswith("*") and dark[k].tobytes() != back[k].tobytes()]
check(f"Dark again: every page to the pixel as it was before ({differ or 'none differ'}), the colours too",
      not differ and T.look() == "Dark" and g.BG == DARK["BG"] and g.ACCENT == dict(T.ACCENTS)["Blue"]
      and all(vars(mod)[k] == v for mod in g._mods for k, v in DARK.items() if k in vars(mod)))
for k in differ:
    dark[k].save(f"{SP}/look_{k.replace(' ', '_')}_before.png"); back[k].save(f"{SP}/look_{k.replace(' ', '_')}_after.png")

# ---- the web page
sec = [r for s in m2.web_settings()["sections"] for r in s["rows"] if r["key"] == "look"]
check(f"the web page's Settings has it too ({sec})",
      len(sec) == 1 and sec[0]["label"] == "App pages" and sec[0]["choices"] == ["Dark", "Light"]
      and sec[0]["value"] == "Dark")
r1 = m2.web_settings_do({"key": "look", "value": "Light"})
r2 = m2.web_settings_do({"key": "look", "value": "Sepia"})
check(f"...picked there: Light ({r1}); something else: refused ({r2})",
      r1 == {"ok": True} and m2.setting("look") == "Light" and T.look() == "Light" and "error" in r2
      and m2.setting("look") == "Light")
m2.set_setting("look", "Dark")

# ---- what it costs: nothing, drawn; a moment, changed
m2.go_home(); m2.open_app(tab("TV")); m2.tick()
t0 = time.perf_counter()
for _ in range(20):
    drawn(m2)
plain = (time.perf_counter() - t0) / 20
m2.set_setting("look", "Light")
t0 = time.perf_counter()
for _ in range(20):
    drawn(m2)
lit = (time.perf_counter() - t0) / 20
t0 = time.perf_counter()
m2.set_setting("look", "Dark")
took = time.perf_counter() - t0
check(f"a light page costs what a dark one does to draw ({plain * 1000:.1f} and {lit * 1000:.1f} ms here), and "
      f"changing takes a moment ({took * 1000:.1f} ms)", lit < plain * 1.5 + 0.004 and took < 0.25)
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
