"""Apps' list, and what its worlds to watch share, in media mode (the game of Rock Paper Scissors itself:
test_sim.py; the Fish Tank's fish: test_fishtank.py). The list as it is: Group chat after the Fish Tank, and no
Game of Life or Mandelbrot Set any more, in the list or behind it (asked for by name, they're not there). Then
each world opened from the list: its frames, the box's round corners, START's options (each changes, and is kept;
a new start when the card closes, for those that need one), full screen for every one of them, each waiting
while you're elsewhere, and B back."""
import os, shutil, sys
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import pietato_all as g
S = SP + "/tsims"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + "/home/u")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: S + "/home/u"
g.wifi_quality = lambda: 62.0
g.cpu_temp = lambda: 48.0
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


# ---- in media mode: every sim -----------------------------------------------------------------------------
class FB:
    w, h, same = 640, 480, True
    count = 0

    def __init__(self):
        self.parts, self.wholes, self.last = [], 0, None
        self.frames = 0

    def show(self, img):
        self.last = img.copy(); self.wholes += 1; FB.count += 1; self.frames = FB.count

    def show_part(self, img, box):
        self.last = img.copy(); self.parts.append(tuple(box)); FB.count += 1; self.frames = FB.count

    def close(self):
        pass


fake = [1000.0]
g.time.monotonic = lambda: fake[0]
m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.status_sig = m.status_signature()


def frames(secs, step=0.05):
    n = 0
    end = fake[0] + secs
    while fake[0] < end - 1e-9:
        fake[0] += step
        m.tick()
        if m.dirty:
            n += 1
        m.flush()
    return n


m.view = "home"
m.home_sel = [a for a, _ in m.home_apps()].index("Apps")
m.press("a")
SIMI = m.tab
corner = (g.SIM_BOX[0], g.SIM_BOX[1])
SHOWN = [it["title"] for it in m.tab_items()]          # (Apps' list as it is here: LED backlight only on a Pi with LEDs)
check(f"Apps' list here: all of them but the LED backlight ({len(SHOWN)})",
      SHOWN == [n for n in g.LIBRARY[SIMI]["children"] if n != "LED backlight"])
check(f"...Group chat after the Fish Tank, and The Cookie after it: {SHOWN[:9]}", SHOWN == [
    "Clock", "Notes", "Fortune Cookie", "Rock Paper Scissors", "Fish Tank", "Group chat", "The Cookie", "Soundboard",
    "Band", "Konami code", "cmatrix", "hollywood", "nyancat", "cacafire", "htop"])
gone = ("Game of Life", "Mandelbrot Set")
check(f"...no Game of Life or Mandelbrot Set: not in the list, not among the apps, nothing of theirs behind it "
      f"({sorted(g.SIMS)})", not [n for n in gone if n in SHOWN or any(t["name"] == n for t in g.LIBRARY)]
      and "life" not in g.SIMS and "mandel" not in g.SIMS and not hasattr(g, "Life") and not hasattr(g, "Mandelbrot")
      and not os.path.exists(ROOT + "/pitato/mandelbrot.py"))
check("...asked for by name, the Bot knows of neither (the Fish Tank, it does)",
      g.app_named("game of life") is None and g.app_named("life") is None and g.app_named("the mandelbrot set") is None
      and g.app_named("mandelbrot") is None and g.app_named("the fish tank") == "Fish Tank")
WORLDS = ("Rock Paper Scissors", "Fish Tank")          # (the worlds to watch that go by the buttons they share)
for name in WORLDS:
    row = SHOWN.index(name)
    while m.sels[SIMI] != row:
        m.press("down")
    m.press("a")
    s = m.sim_game()
    key = s.key
    check(f"{name}: opens from the list", m.tab_type() == "sim" and g.LIBRARY[m.tab]["name"] == name)
    m.fb.parts.clear(); m.fb.wholes = 0
    n = frames(1.5)
    check(f"...{n / 1.5:.0f} frames a second, mostly just the box", g.SIM_FPS - 2 <= n / 1.5 <= g.SIM_FPS + 2
          and len(m.fb.parts) >= 0.6 * (len(m.fb.parts) + m.fb.wholes))
    shot = m.fb.last
    check("...the box's round corner and edge stay as they are", shot.getpixel(corner) == g.BG
          and shot.getpixel((corner[0] + 1, corner[1] + 1)) == g.BG)
    hints = [label for _, label, *_ in m.sim_hints(s)]
    check(f"...its buttons: {hints}", hints[-1] == "Options" and s.poke_label in hints + ["Shake"])
    if key == "rps":
        m.press("a")                                   # (the round starts)
        frames(0.5)
        m.press("a")
        frames(0.5)
        check("...A pauses (and says so)", s.paused and m.sim_card[0] == ("paused",))
        clock = s.clock
        frames(1)
        check("...nothing moves meanwhile", s.clock == clock)
        m.press("a")
        m.press("x")
        m.press("y")
        check("...X and Y: a shake, and a new round", not s.paused and s.clock == 0)
    m.press("start")
    rows = [k for k, _, _, _ in m.sim_rows(type(s))]
    check(f"...START: its options {rows}", m.sim_opts == 0 and rows[-1] == "full" and len(rows) == len(s.options) + 1)
    m.dirty = True; m.flush()
    m.fb.last.save(f"{SP}/sims_opts_{key}.png")
    for i, (k, label, ways, default) in enumerate(s.options):
        before = s.values[k]
        m.press("right")
        now = s.values[k]
        saved = m.setting(f"sim_{key}_{k}")
        if not (now == saved and now != before and now in ways):
            check(f"...{label}: {before} -> {now} (kept: {saved})", False)
        m.press("down")
    check("...each option changes, and is kept", True)
    m.press("b")
    check("...B closes it: a new start for the options that need one", m.sim_opts is None and not s.needs_restart())
    m2 = g.Media()
    check("...kept for next time", all(m2.sim_value(type(s), k) == s.values[k] for k, _, _, _ in s.options))
    m.press("select")
    frames(0.5)
    check(f"...SELECT: full screen ({s.w} x {s.h})", m.sim_full() and (s.w, s.h) == (640, 480))
    m.msg = None
    m.fb.parts.clear(); m.fb.wholes = 0
    frames(1)
    shot = m.fb.last
    check("...just the world: no clock, no numbers, no buttons", m.fb.wholes >= 18 and not m.fb.parts
          and shot.getpixel((630, 10)) != g.BG and shot.getpixel((320, 470)) != g.BG)
    shot.save(f"{SP}/sims_full_{key}.png")
    m.press("select")
    frames(0.2)
    check("...SELECT again: back beside its numbers", not m.sim_full() and (s.w, s.h) == (436, 342))
    m.press("b")
    check("...B: back to the list, it picked", m.tab == SIMI and m.sels[SIMI] == row)
while m.sels[SIMI] != len(SHOWN) - 1:
    m.press("down")
m.press("down")
check("down from the last goes round to the first", m.sels[SIMI] == 0)

# full screen is for every world; each waits while you're elsewhere
m.sels[SIMI] = SHOWN.index("Rock Paper Scissors")
m.press("a")
rps = m.sim_game()
if rps.phase == "ready":
    m.press("a")
frames(0.5)
m.press("select")
m.press("b")
m.press("down")
m.press("a")
check("full screen once is full screen for every world", m.sim_full() and m.sim_game().key == "fish")
m.press("select")
clock = rps.clock
frames(1.0)                                            # (a second in the Fish Tank)
m.press("b")
m.sels[SIMI] = SHOWN.index("Rock Paper Scissors")
m.press("a")
frames(0.05)
check(f"each waits while you're elsewhere (its clock at {clock:.2f} s, now {rps.clock:.2f})",
      rps.clock - clock <= 0.11 and m.sim_game() is rps and rps.clock > 0)
check("a world follows held buttons itself only where it says so (Snake does; these, the usual repeat)",
      not m.holds_buttons() and not m.takes_repeats("a") and not m.takes_repeats("left"))
m.press("b")
m.press("b")
check("B from the list: home", m.view == "home")
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
