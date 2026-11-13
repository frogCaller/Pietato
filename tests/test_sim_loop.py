"""Apps in the real main loop, in real time: opened with the d-pad from the home screen, Rock
Paper Scissors runs at about SIM_FPS frames a second to begin with, mostly sending just its box, and a couple of
seconds on as often as the machine has the time for (30 or 60: test_quick_frames.py has how that's worked out);
START's card stops the frames; leaving it stops them too; full screen, the same; the Fish Tank keeps up full
screen too at SIM_FPS. A button held down on the web page's remote is one press in Apps' worlds."""
import os, sys, time, shutil, threading
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from evdev import ecodes as e

S = SP + "/tsimloop"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + "/home/u")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.PADS_FILE = S + "/pads.json"
g.home_dir = lambda: S + "/home/u"
if hasattr(g, "STATIC"):
    g.STATIC = S + "/home/u/gpi-media/static"
g.subprocess.run = lambda cmd, *a, **k: type("R", (), {"stdout": "1", "returncode": 0})()
g.subprocess.Popen = lambda *a, **k: None
g.SCAN_EVERY = 0.05
g.wifi_quality = lambda: 62.0
g.cpu_temp = lambda: 48.0
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


class Ev:
    def __init__(self, t, c, v):
        self.type, self.code, self.value = t, c, v


class Info:
    bustype, vendor, product = 0x03, 1, 1


class Pad:
    def __init__(self, keys):
        self.driver, self.path, self.name, self.keys = "usbhid", "/dev/input/event71", "Test pad", keys
        self.info = Info()
        self.r, self.w = os.pipe()
        self.q = []

    def capabilities(self, verbose=False, absinfo=True):
        return {e.EV_KEY: list(self.keys)}

    def fileno(self):
        return self.r

    def send(self, *evs):
        self.q += [Ev(*x) for x in evs]
        os.write(self.w, b".")

    def read(self):
        try:
            os.read(self.r, 64)
        except OSError:
            pass
        out, self.q = self.q, []
        return iter(out)

    def close(self):
        pass


g.input_driver = lambda dev: dev.driver
pad = Pad([e.BTN_SOUTH, e.BTN_EAST, e.BTN_NORTH, e.BTN_WEST, e.BTN_START, e.BTN_SELECT, e.BTN_MODE,
           e.BTN_TL, e.BTN_TR, e.BTN_DPAD_UP, e.BTN_DPAD_DOWN, e.BTN_DPAD_LEFT, e.BTN_DPAD_RIGHT])
g.list_devices = lambda: [pad.path]
g.InputDevice = lambda path: pad
real_stat = os.stat
g.os.stat = lambda p, *a, **k: type("St", (), {"st_ino": 9})() if p.startswith("/dev/input/") else real_stat(p, *a, **k)


class UI:
    def write(self, t, c, v):
        pass

    def syn(self):
        pass


class FB:
    w, h, same = 640, 480, True
    real_w, real_h = 640, 480
    log = []                     # (when, "whole" or the box)
    count = 0

    def __init__(self):
        self.frames = 0

    def show(self, img):
        FB.log.append((time.monotonic(), "whole"))
        FB.count += 1; self.frames = FB.count; self.last = img

    def show_part(self, img, box):
        FB.log.append((time.monotonic(), tuple(box)))
        FB.count += 1; self.frames = FB.count; self.last = img

    def blank_outside(self, box):
        pass

    def invalidate(self):
        pass

    def close(self):
        pass


g.Framebuffer = FB
m = g.Media()
done, errors = threading.Event(), []
ctl = g.Control()


def loop():
    try:
        g.run(UI(), m, ctl, stop=done.is_set)
    except Exception as ex:
        import traceback; traceback.print_exc(); errors.append(ex)


th = threading.Thread(target=loop, daemon=True)
th.start()
time.sleep(0.6)


def press(code, sec=0.2):
    pad.send((e.EV_KEY, code, 1)); time.sleep(0.06); pad.send((e.EV_KEY, code, 0)); time.sleep(sec)


def since(t0):
    return [b for t, b in FB.log if t >= t0]


def drawn(quiet=0.3, most=3.0):
    """Once nothing's been drawn for a moment: a card just opened is one drawing, and a late one on a slow machine."""
    end = time.monotonic() + most
    while time.monotonic() < end and FB.log and time.monotonic() - FB.log[-1][0] < quiet:
        time.sleep(0.02)


check("the home screen at start-up", m.active and m.view == "home")
apps = [a for a, _ in m.home_apps()]
row, col = divmod(apps.index("Apps"), 5)
for _ in range(row):
    press(e.BTN_DPAD_DOWN)
for _ in range(col):
    press(e.BTN_DPAD_RIGHT)
check(f"the d-pad to its icon ({apps[m.home_sel]})", apps[m.home_sel] == "Apps")
press(e.BTN_SOUTH, 0.3)
check("A opens it: the list of sims", m.tab_type() == "group" and g.LIBRARY[m.tab]["name"] == "Apps")
SIMI = m.tab
press(e.BTN_DPAD_DOWN, 0.2)                    # (past the Clock, Notes and the Fortune Cookie)
press(e.BTN_DPAD_DOWN, 0.2)
press(e.BTN_DPAD_DOWN, 0.2)
press(e.BTN_SOUTH, 0.3)
check("A again: Rock Paper Scissors", m.tab_type() == "sim" and g.LIBRARY[m.tab]["sim"] == "rps")
G = m.sims["rps"]
press(e.BTN_SOUTH, 0.1)                        # (start now)
t0 = time.monotonic()
time.sleep(1.2)
got = since(t0)
fps = len(got) / 1.2
small = sum(b == g.SIM_BOX for b in got)
check(f"{fps:.1f} frames a second to begin with, as ever ({len(got)} in 1.2 s)", g.SIM_FPS - 3 <= fps <= g.SIM_FPS + 2)
check(f"...{small} of them just the box, {got.count('whole')} whole", small >= 0.6 * len(got) and got.count("whole") <= 2)
check(f"...it plays: {G.captures} captures by now", G.phase == "on" and G.clock > 0.8)


def settled(what):
    """A couple of seconds on, it's drawn as often as this machine has the time for (a screen that costs nothing,
    here): the rate it's settled on, and the frames in a second and a half since."""
    time.sleep(1.4)
    rate, t0 = m.sim_rate, time.monotonic()
    time.sleep(1.5)
    got = since(t0)
    lo, hi = sorted((rate or 0, m.sim_rate or 0))       # (a busy machine may change its mind meanwhile)
    fps = len(got) / 1.5
    check(f"...a couple of seconds on, a frame taking {(m.sim_cost or 0) * 1000:.1f} ms: {what} {rate} times a second "
          f"({fps:.1f})", lo >= 30 and hi in (30, 60) and 0.7 * lo <= fps <= hi + 3)
    return got


got = settled("drawn")
check(f"...mostly just its box still ({sum(b == g.SIM_BOX for b in got)} of {len(got)})",
      sum(b == g.SIM_BOX for b in got) >= 0.6 * len(got))
press(e.BTN_START, 0.3)
drawn()
t0 = time.monotonic()
time.sleep(1.0)
check(f"START's card: no frames meanwhile ({len(since(t0))})", m.sim_opts == 0 and len(since(t0)) == 0)
press(e.BTN_DPAD_DOWN); press(e.BTN_DPAD_DOWN); press(e.BTN_DPAD_RIGHT)
check(f"...Speed: {m.setting('sim_rps_speed')}", m.setting("sim_rps_speed") == "Fast" and G.speed == 120)
press(e.BTN_EAST, 0.3)
check("B closes it, and on it goes", m.sim_opts is None and len(since(time.monotonic() - 0.25)) >= 2)
clock = G.clock
press(e.BTN_TR, 0.3)
check("R: the next app, Files", g.LIBRARY[m.tab]["name"] == "Files")
press(e.BTN_TR, 0.3)
t0 = time.monotonic()
time.sleep(1.0)
check(f"R again: System; the game waits, no more frames ({len(since(t0))})",
      m.tab_type() == "system" and len(since(t0)) <= 2 and G.clock - clock < 0.5)
press(e.BTN_TL, 0.3)
press(e.BTN_TL, 0.4)
check("L, L: back to Apps' list", m.tab == SIMI)
press(e.BTN_SOUTH, 0.5)
check("...A: and on it goes", m.tab_type() == "sim" and G.clock > clock)
press(e.BTN_SELECT, 0.4)
check("SELECT: full screen", m.sim_full() and (G.w, G.h) == (640, 480))
t0 = time.monotonic()
time.sleep(1.2)
got = since(t0)
fps = len(got) / 1.2
check(f"...{fps:.1f} frames a second to begin with, each the whole screen", g.SIM_FPS - 3 <= fps <= g.SIM_FPS + 2
      and all(b == "whole" for b in got))
got = settled("the whole screen")
check("...each the whole screen still", got and all(b == "whole" for b in got))
press(e.BTN_EAST, 0.3)
press(e.BTN_DPAD_DOWN)
press(e.BTN_SOUTH, 0.5)
check(f"B, down to the Fish Tank, A: full screen too ({g.LIBRARY[m.tab]['name']})",
      m.tab_type() == "sim" and g.LIBRARY[m.tab]["sim"] == "fish" and m.sim_full())
t0 = time.monotonic()
time.sleep(2.0)
fps = len(since(t0)) / 2.0
check(f"...it keeps up: {fps:.1f} frames a second", g.SIM_FPS - 3 <= fps <= g.SIM_FPS + 2)
press(e.BTN_SELECT, 0.4)
check("SELECT: back beside its numbers", not m.sim_full() and (m.sims["fish"].w, m.sims["fish"].h) == (436, 342))
calls = []
real_call = m.aquarium.call
m.aquarium.call = lambda: (calls.append(1), real_call())[1]
ctl.ask({"cmd": "press", "button": "a"})
for _ in range(3):
    ctl.ask({"cmd": "press", "button": "a", "repeat": True})
check(f"the web page's remote: A calls your fish; held down there, it's still the one press ({len(calls)})",
      len(calls) == 1)
press(e.BTN_MODE, 0.4)
check("Home on its own: still the app, not the console", m.active and m.view == "list")
pad.send((e.EV_KEY, e.BTN_MODE, 1)); time.sleep(0.06)
press(e.BTN_DPAD_LEFT, 0.1)
pad.send((e.EV_KEY, e.BTN_MODE, 0)); time.sleep(0.4)
t0 = time.monotonic()
time.sleep(0.6)
check(f"Home and ◀: the console, nothing drawn ({len(since(t0))})", not m.active and len(since(t0)) == 0)
done.set(); th.join(3)
check("no errors", not errors and not th.is_alive())
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
