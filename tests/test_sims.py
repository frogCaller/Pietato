"""Apps' list, and what its worlds to watch share, in media mode (the Fish Tank's fish: test_fishtank.py). Apps' icon
on the home screen; the list as it is: Group chat after the Fish Tank, and no Game of Life, Mandelbrot Set, Rock Paper
Scissors or The Cookie any more, in the list or behind it (asked for by name, they're not there). Then a world opened
from the list: its frames (mostly just its box), the box's round corners, START's options (each changes, and is kept;
nothing's drawn meanwhile; R and L from there), a notice over it, full screen (kept, its card's buttons, off from
the card, back at once the next time), for every one of them, each waiting while you're elsewhere, B back, and saved
options that are broken."""
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


apps = [a for a, _ in m.home_apps()]
check(f"Apps' icon on the home screen, by the Bot ({len(apps)} icons, {g.home_cols(len(apps))} across)",
      apps[apps.index("Bot") + 1] == "Apps" and len(apps) == 15 and g.home_cols(15) == 5)
icon = g.draw_icon("Apps")
check("...a sun, an orbit and three bodies on it", icon.size == (84, 84)
      and len(set(icon.tobytes()[i:i + 4] for i in range(0, 84 * 84 * 4, 4))) > 200)
m.view = "home"
m.home_sel = apps.index("Apps")
m.dirty = True; m.flush()
m.press("a")
SIMI = m.tab
corner = (g.SIM_BOX[0], g.SIM_BOX[1])
SHOWN = [it["title"] for it in m.tab_items()]
check(f"A opens Apps: its list, all of them ({len(SHOWN)}); no LED backlight (the web page's Library has it), no Notes "
      f"or Fortune Cookie", m.tab_type() == "group" and g.LIBRARY[m.tab]["name"] == "Apps"
      and SHOWN == g.LIBRARY[SIMI]["children"]
      and not {"LED backlight", "Notes", "Fortune Cookie"} & set(SHOWN))
rows = [(it["title"], it.get("icon")) for it in m.tab_items()]
check(f"...Group chat after the Fish Tank, each with its badge: {rows[:6]}", rows == [
    ("Clock", "TIME"), ("Fish Tank", "FISH"), ("Group chat", "CHAT"),
    ("Sequencer", "BEAT"), ("Band", "JAM"), ("Konami code", "CHEAT"), ("cmatrix", "CODE"), ("hollywood", "HACK"),
    ("nyancat", "NYAN"), ("cacafire", "HEAT"), ("htop", "PROC")])
gone = ("Game of Life", "Mandelbrot Set", "Rock Paper Scissors", "The Cookie")
check(f"...no Game of Life, Mandelbrot Set, Rock Paper Scissors or The Cookie: not in the list, not among the apps, "
      f"nothing of theirs behind it ({sorted(g.SIMS)})",
      not [n for n in gone if n in SHOWN or any(t["name"] == n for t in g.LIBRARY)]
      and not {"life", "mandel", "rps", "cookie"} & set(g.SIMS)
      and not [n for n in ("Life", "Mandelbrot", "RockPaperScissors", "rps_sprite", "CookiePage", "CookieScreen",
                           "cookie_said") if hasattr(g, n)]
      and not [f for f in ("mandelbrot.py", "cookie.py", "cookiepage.py", "screens/cookie.py")
               if os.path.exists(ROOT + "/pitato/" + f)]
      and "cookie" not in m.state and not [a for a in dir(m) if "cookie" in a or "rps" in a])
check("...asked for by name, the Bot knows of none of them (the Fish Tank, it does)",
      not [n for n in ("game of life", "life", "the mandelbrot set", "mandelbrot", "rock paper scissors", "cookie",
                       "the cookie") if g.app_named(n) is not None] and g.app_named("the fish tank") == "Fish Tank")

# ---- a world to watch, opened from the list -----------------------------------------------------------------------
name = "Fish Tank"
row = SHOWN.index(name)
while m.sels[SIMI] != row:
    m.press("down")
m.press("a")
s = m.sim_game()
key = s.key
check(f"{name}: opens from the list", m.tab_type() == "sim" and g.LIBRARY[m.tab]["name"] == name and key == "fish")
m.fb.parts.clear(); m.fb.wholes = 0
n = frames(1.5)
check(f"...{n / 1.5:.0f} frames a second, mostly just the box ({len(m.fb.parts)} in part, {m.fb.wholes} whole)",
      g.SIM_FPS - 2 <= n / 1.5 <= g.SIM_FPS + 2 and len(m.fb.parts) >= 0.6 * (len(m.fb.parts) + m.fb.wholes)
      and set(m.fb.parts) <= {g.SIM_BOX, g.SIM_DIRTY})
lim = m.tick_limit()
check(f"...the loop wakes up for the next one ({lim:.3f} s)", 0 <= lim <= 0.05)
shot = m.fb.last
check("...the box's round corner and edge stay as they are", shot.getpixel(corner) == g.BG
      and shot.getpixel((corner[0] + 1, corner[1] + 1)) == g.BG)
hints = [label for _, label, *_ in m.sim_hints(s)]
check(f"...its buttons: {hints}", hints[-1] == "Options" and s.poke_label in hints)
m.press("start")
rows = [k for k, _, _, _ in m.sim_rows(type(s))]
check(f"...START: its options {rows}", m.sim_opts == 0 and rows[-1] == "full" and len(rows) == len(s.options) + 1)
m.dirty = True; m.flush()
m.fb.last.save(f"{SP}/sims_opts_{key}.png")
clock = s.clock
n = frames(1)
check(f"...it waits meanwhile: no frames ({n}), and its time stands still", n == 0 and s.clock == clock)
for i, (k, label, ways, default) in enumerate(s.options):
    before = s.values[k]
    m.press("right")
    now = s.values[k]
    saved = m.setting(f"sim_{key}_{k}")
    if not (now == saved and now != before and now in ways):
        check(f"...{label}: {before} -> {now} (kept: {saved})", False)
    m.press("down")
check("...each option changes, and is kept", True)
check("...down past them: Full screen, the last row", m.sim_opts == len(s.options) and rows[m.sim_opts] == "full")
m.press("down")
check("...down again goes round to the top", m.sim_opts == 0)
m.press("b")
check("...B closes it: a new start for the options that need one", m.sim_opts is None and not s.needs_restart())
m2 = g.Media()
check("...kept for next time", all(m2.sim_value(type(s), k) == s.values[k] for k, _, _, _ in s.options))
m.press("start"); m.press("r")
check("...R from the options: the next app (Files), the card closed",
      g.LIBRARY[m.tab]["name"] == "Files" and m.sim_opts is None)
m.press("l")
check("...L back: Apps' list, it picked", m.tab == SIMI and m.sels.get(SIMI, 0) == row)
m.press("a")
check("...A: back in it, the same one", m.tab_type() == "sim" and m.sim_game() is s)

# a notice over it
frames(0.3)
m.toast("Your timer's done", 4)
m.fb.parts.clear(); m.fb.wholes = 0
frames(0.3)
tile = m.sim_tile("Your timer's done", "small", g.PILL_TEXT, g.PILL)
px = m.fb.last.getpixel((int((640 - (tile.width - 2 + 32)) / 2) + 8, 480 - m.FOOTER - 46 + 17))
check(f"a notice shows over the box ({m.fb.wholes} whole, {px})", m.fb.wholes >= 1 and px == g.PILL)

# full screen: just the world
frames(4.5)
m.fb.parts.clear(); m.fb.wholes = 0
r = m.press("select")
check(f"SELECT: full screen, kept, and how to leave it said ('{m.msg}')", r is None and m.setting("sim_full") == "On"
      and m.sim_full() and "SELECT" in (m.msg or ""))
frames(0.5)
check(f"...the box is the whole screen now ({s.w} x {s.h})", (s.w, s.h) == (640, 480))
m.msg = None
m.fb.parts.clear(); m.fb.wholes = 0
n = frames(1)
shot = m.fb.last
check(f"...just the world: no clock, no numbers, no buttons; {n} frames a second, each the whole screen",
      m.fb.wholes >= 18 and m.fb.wholes == n and not m.fb.parts
      and shot.getpixel((630, 10)) != g.BG and shot.getpixel((320, 470)) != g.BG)
shot.save(f"{SP}/sims_full_{key}.png")
m.press("start")
m.dirty = True; m.flush()
shot = m.fb.last
check("...START there: the options card, with its buttons along the bottom", m.sim_opts == 0
      and shot.getpixel((320, 480 - 2)) == g.BG)
shot.save(f"{SP}/sims_full_options_{key}.png")
for _ in s.options:
    m.press("down")
m.press("right")
check("...Full screen: Off, from the card: back beside its numbers", not m.sim_full() and (s.w, s.h) == (436, 342))
m.press("b")
m.fb.parts.clear(); m.fb.wholes = 0
frames(1)
check(f"...and frames send just the box again ({len(m.fb.parts)} in part, {m.fb.wholes} whole)",
      len(m.fb.parts) >= 0.6 * (len(m.fb.parts) + m.fb.wholes))
m.press("select")
check("SELECT again: full screen", m.sim_full())
check("...kept for next time", g.Media().sim_full())
m.press("b")
check("B from full screen: Apps' list, still kept", m.tab == SIMI and m.sels[SIMI] == row and m.sim_full())
m.press("b")
check("...B again: home", m.view == "home" and m.sim_full())
m.press("a"); m.press("a")
m.dirty = True; m.flush()
check("...and it opens full screen again", m.sim_game() is s and m.sim_full() and (s.w, s.h) == (640, 480)
      and m.fb.last.getpixel((2, 2)) != g.BG)
m.press("select")
frames(0.2)
check("SELECT: back beside its numbers", not m.sim_full() and m.setting("sim_full") == "Off"
      and (s.w, s.h) == (436, 342))
m.state["settings"]["sim_full"] = "Maybe"
check("a broken saved value: not full screen", not m.sim_full())
m.state["settings"]["sim_full"] = "Off"
m.press("b")
check("B: back to the list, it picked", m.tab == SIMI and m.sels[SIMI] == row)
while m.sels[SIMI] != len(SHOWN) - 1:
    m.press("down")
m.press("down")
check("down from the last goes round to the first", m.sels[SIMI] == 0)

# full screen is for every world; each waits while you're elsewhere
m.sels[SIMI] = row
m.press("a")
frames(0.5)
m.press("select")
m.press("b")
m.sels[SIMI] = SHOWN.index("Clock")
m.press("a")
check("full screen once is full screen for every world", m.sim_full() and m.sim_game().key == "clock")
m.press("select")
clock = s.clock
frames(1.0)                                            # (a second with the Clock)
m.press("b")
m.sels[SIMI] = row
m.press("a")
frames(0.05)
check(f"each waits while you're elsewhere (its clock at {clock:.2f} s, now {s.clock:.2f})",
      s.clock - clock <= 0.11 and m.sim_game() is s and s.clock > 0)
frames(0.5)
check(f"...and goes on from there ({s.clock:.2f} s)", 0.3 <= s.clock - clock <= 0.61)
check("a world follows held buttons itself only where it says so (Snake does; these, the usual repeat)",
      not m.holds_buttons() and not m.takes_repeats("a") and not m.takes_repeats("left"))
m.press("b")
m.press("b")
check("B from the list: home", m.view == "home")

# saved options that are broken
m3 = g.Media(); m3.load_fonts(); m3.fb = FB(); m3.active = True
m3.state["settings"].update(sim_fish_light="Dusk", sim_fish_kind=7)
m3.tab = next(i for i, t in enumerate(g.LIBRARY) if t.get("sim") == "fish")
f3 = m3.sim_game()
check(f"broken saved options: the usual ones instead ({f3.values})", f3.values["light"] == "Day"
      and f3.values["kind"] in dict((k, ways) for k, _, ways, _ in f3.options)["kind"])
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
