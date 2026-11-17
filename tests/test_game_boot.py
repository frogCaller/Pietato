"""Settings > At start-up's Game: the Pi starts in the game you played last, from where you were (the Game Boy feeling).
Its choices: Home screen, Terminal, Game. With Game, the app's loop (app.py, as the Pi starts it) opens media mode
and the game played last that's still there, picking up where you were, with no song over it (even with Random song
at start-up on); none played yet: the home screen, saying so; a new screen size to ask about first: no game over it.
The power switch, with the game going: where you are saved (the game ended, as when you leave it) before the Pi
shuts down. And where you are is saved as it plays, not only as it ends: a real game (a test core, where there's
one: tests/run.py --list) saving every moment here (every minute on a Pi), killed as a flat battery would, and
started again: it picks up from the last one.
At start-up's Desktop, on a system with a desktop it can start (not among its choices on any other): as the machine
starts, Pietato stops and the desktop starts in its place; Pietato started again after that (from the desktop's menu,
Restart media mode, an update) opens on the home screen; its desktop gone since: the home screen."""
import json, os, signal, shutil, sys, threading, time
from paths import SP, TESTS  # noqa: E402  (this test's folder of work; tests)
sys.path.insert(0, TESTS)
import pietato_all as g  # noqa: E402
from evdev import ecodes as e  # noqa: E402

S = SP + "/t_game_boot"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
GAMES = HOME + "/Games"
for d in ("nes", "gb", "Saves"):
    os.makedirs(f"{GAMES}/{d}")
os.makedirs(S + "/bin")
NES = f"{GAMES}/nes/Test Game (USA).nes"
GB = f"{GAMES}/gb/Other Game.gb"
open(NES, "wb").write(b"NES\x1a\x01\x01" + bytes(10) + bytes(range(256)) * 64)
open(GB, "wb").write(bytes(0x150))
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.PADS_FILE = S + "/pads.json"
g.home_dir = lambda: HOME
g.find_core = lambda system: "/cores/" + system + "_libretro.so"   # (stand-ins: no game really starts here)
g.bios_missing = lambda core, path=None: None
real_run, real_popen = g.subprocess.run, g.subprocess.Popen
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0})()
g.SCAN_EVERY = 0.05
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def settings(**s):
    json.dump({"settings": s}, open(g.STATE_FILE, "w"))


class Ev:
    def __init__(self, t, c, v):
        self.type, self.code, self.value = t, c, v


class Info:
    def __init__(self, bustype, vendor=1, product=1):
        self.bustype, self.vendor, self.product = bustype, vendor, product


class FakeDev:
    n = 300

    def __init__(self, name, keys, bustype=0x19, driver=None):
        FakeDev.n += 1
        self.driver = ("gpio-keys" if bustype == 0x19 else "usbhid") if driver is None else driver
        self.path = f"/dev/input/event{FakeDev.n}"
        self.name, self.keys = name, keys
        self.info = Info(bustype)
        self.r, self.w = os.pipe()
        self.q, self.gone, self.closed = [], False, False

    def capabilities(self, verbose=False, absinfo=True):
        return {e.EV_KEY: list(self.keys)} if self.keys else {}

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
        self.closed = True


g.input_driver = lambda dev: dev.driver
switch = FakeDev("shutdown_button@1a", [e.KEY_POWER])
pad = FakeDev("GPi Case 2W gamepad", [e.BTN_SOUTH, e.BTN_EAST, e.BTN_START, e.BTN_SELECT], bustype=0x03)
devs = {d.path: d for d in (pad, switch)}
g.list_devices = lambda: list(devs)
g.InputDevice = lambda path: devs[path]
real_stat = os.stat
g.os.stat = lambda p, *a, **k: type("St", (), {"st_ino": hash(p) % 1000})() if str(p).startswith("/dev/input/") \
    else real_stat(p, *a, **k)
happened = []                                     # (what was done, in order: a game's start, its end, poweroff)


class FakePopen:
    def __init__(self, cmd, *a, **k):
        happened.append(list(cmd))


g.subprocess.Popen = FakePopen
g.show_shutdown_lines = lambda: None
g.system_stopping = lambda: False


def game_start(self, core, **kw):
    happened.append(("start", self.game["path"], kw.get("resume", True)))
    self.state = "on"
    self.p = type("P", (), {"pid": 0, "stdin": open(os.devnull, "w"), "poll": lambda me: None,
                            "wait": lambda me, timeout=None: 0, "kill": lambda me: None})()


def game_quit(self, timeout=None):
    happened.append(("quit", self.game["path"]))
    self.ended = True


g.GameRun.start = game_start
g.GameRun.quit = game_quit
g.GameRun.pause = lambda self: True
g.GameRun.resume = lambda self: None
g.GameRun.alive = lambda self: not getattr(self, "ended", False)


class UI:
    def write(self, t, c, v):
        pass

    def syn(self):
        pass


class FB:
    w, h = 640, 480
    real_w, real_h = 640, 480
    frames = []
    def show(self, img): FB.frames.append(1)
    def show_part(self, img, box): FB.frames.append(1)
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB


def boot(**s):
    """The Pi starting, with these settings: media mode's loop (app.py's), on a thread. (media, its stop)"""
    settings(**s)
    happened.clear()
    m = g.Media()
    done = threading.Event()
    th = threading.Thread(target=lambda: g.run(UI(), m, None, stop=done.is_set), daemon=True)
    th.start()
    time.sleep(0.6)
    return m, done


def until(cond, secs=5.0):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return bool(cond())


# ---- the setting ------------------------------------------------------------------------------------------------
choices = {k: c for k, _, c in g.SETTINGS}["start"]
check(f"At start-up: Home screen, Terminal (as they were: one press from the first), and Game ({choices})",
      choices == ["Home screen", "Terminal", "Game"])
settings(start="Game", start_song="On")
m = g.Media()
check(f"...Game: media mode at start-up, the game too, and no song over it, even with Random song at start-up on "
      f"({m.boot_media}, {m.boot_game}, {m.boot_song})", m.boot_media and m.boot_game and not m.boot_song)
settings(start="Game", resolution_try="1920x1080")
m = g.Media()
check("...a new screen size to ask about first: media mode for that, no game over it", m.boot_media and not m.boot_game)
settings(start="Home screen")
check("...Home screen and Terminal, as they were", g.Media().boot_media and not g.Media().boot_game
      and (settings(start="Terminal") or not g.Media().boot_media))

# ---- At start-up > Desktop: on a system with a desktop, as the machine starts ---------------------------------------
def start_choices(m):
    return {k: c for k, _, c in m.settings_root_rows()}["start"]


real_has_desktop = g.has_desktop
settings(start="Home screen")
m = g.Media()
check(f"no desktop here: At start-up's choices as they were ({start_choices(m)})",
      start_choices(m) == ["Home screen", "Terminal", "Game"])
g.has_desktop = lambda: True                           # (a system with a desktop it can start: system.py)
check(f"a system with a desktop: Desktop too, after the rest ({start_choices(m)})",
      start_choices(m) == ["Home screen", "Terminal", "Game", "Desktop"])
m.settings_pick("start", "Desktop")
check(f"...picked: kept, and it says how to come back from the desktop ({m.msg!r})", m.setting("start") == "Desktop"
      and m.msg == "It starts in the desktop. Pietato's in the desktop's menu"
      and m.desktop_back() == "Pietato in the desktop's menu comes back here")
m = g.Media()
check(f"...its cue as the machine starts, and the home screen for any start after ({m.boot_desktop}, {m.boot_media})",
      m.boot_desktop and m.boot_media and not m.boot_game)
JOB = ["systemd-run", "--no-block", "--collect", "--unit=pietato-desktop", "sh", "-c",
       "systemctl stop pitato; systemctl start display-manager || { systemctl start getty@tty1; systemctl start "
       "pitato; }"]
happened.clear()
m.first = True                                         # (the machine's just started: app.py's main says so)
done = threading.Event()
threading.Thread(target=lambda: g.run(UI(), m, None, stop=done.is_set), daemon=True).start()
time.sleep(0.6)
check(f"the machine starts: Pietato stops and the desktop starts in its place, by a job of its own (the desktop not "
      f"starting: Pietato again, and the console's sign-in), nothing of Pietato's on the screen meanwhile ({happened}, "
      f"{m.active})",
      happened == [JOB] and not m.active and not m.boot_song)
done.set()
m, done = boot(start="Desktop")
check(f"Pietato started again after that (from the desktop's menu, Restart media mode, an update): the home screen, "
      f"the desktop left alone ({m.view}, {happened})", until(lambda: m.active) and m.view == "home" and not happened)
done.set()
g.STARTED = S + "/started"
check("Pietato's first start since the machine did: said once, and noted", g.first_start() and not g.first_start()
      and os.path.exists(S + "/started"))
g.STARTED = S + "/nowhere/started"
check("...nowhere to note it: never the first", not g.first_start())
g.has_desktop = lambda: False
settings(start="Desktop")
m = g.Media()
check(f"its desktop gone since: the home screen at start-up, and Desktop not among its choices ({m.setting('start')})",
      m.setting("start") == "Home screen" and m.boot_media and not m.boot_desktop
      and start_choices(m) == ["Home screen", "Terminal", "Game"]
      and m.desktop_back() == "Restarting the computer comes back to Pietato")
g.has_desktop = real_has_desktop

# ---- the Pi starting: the game played last, from where you were ---------------------------------------------------
gone = f"{GAMES}/gb/Deleted Since.gb"
m, done = boot(start="Game", start_song="On", games_recent=[gone, NES, GB])
check(f"the Pi starts: media mode, and the game played last that's still there, picking up where you were "
      f"({happened[:1]}, {m.view})", m.active and m.view == "game" and m.game is not None
      and happened[:1] == [("start", NES, True)])
check("...no song started over it", not any(isinstance(h, list) and "mplayer" in " ".join(h) for h in happened)
      and m.proc is None)

# ---- the power switch, with the game going -------------------------------------------------------------------------
happened.clear()
switch.send((e.EV_KEY, e.KEY_POWER, 1))
until(lambda: ["systemctl", "poweroff"] in happened)
check(f"the power switch: where you are saved (the game ended, as you'd leave it), then the Pi shuts down "
      f"({happened})", happened[:2] == [("quit", NES), ["systemctl", "poweroff"]])
switch.send((e.EV_KEY, e.KEY_POWER, 0))
done.set()
time.sleep(0.3)

# ---- none played yet ------------------------------------------------------------------------------------------------
m, done = boot(start="Game")
check(f"no game played yet: the home screen, saying so ({m.view}, {m.msg!r})", m.active and m.view == "home"
      and m.game is None and "Play a game first" in str(m.msg) and not any(h[0] == "start" for h in happened
                                                                          if isinstance(h, tuple)))
done.set()
time.sleep(0.3)

# ---- where you are, saved as it plays: a real game, a flat battery -----------------------------------------------------
CORE = SP + "/cheevos_test/testcore_libretro.so"
if not os.path.isfile(CORE):
    print("(no test core here: the game itself isn't played. tests/run.py --list says what it needs)", flush=True)
else:
    import importlib
    import pitato.games as GM
    GM = importlib.reload(GM)                      # (the real GameRun, not the stand-ins above)
    g.subprocess.run, g.subprocess.Popen = real_run, real_popen
    FBF = S + "/fb.bin"
    open(FBF, "wb").write(bytes(640 * 480 * 2))
    os.environ["PITATO_FB"] = f"{FBF}:640x480:16"
    os.environ["PITATO_AUTO_EVERY"] = "1"           # (a second here, for the test; a minute on a Pi)
    open(S + "/bin/aplay", "w").write("#!/bin/sh\nexec cat > /dev/null\n")
    os.chmod(S + "/bin/aplay", 0o755)
    os.environ["PATH"] = S + "/bin:" + os.environ["PATH"]
    GM.home_dir = lambda: HOME
    GM.games_dir = lambda: GAMES
    base = f"{GAMES}/Saves/{GM.save_name(NES)}"
    run = GM.GameRun({"path": NES, "title": "Test Game", "system": "nes"})
    run.start(CORE, sound="", volume=80, picture="Fit", fb=FBF, resume=True, cheevos=False)
    on = until(lambda: run.state == "on" or run.ended, 20)
    saved = until(lambda: os.path.isfile(base + ".state.auto"), 6)
    first = os.path.getsize(base + ".state.auto") if saved else 0
    check(f"a game playing: where you are saved as it plays, before it's left ({first} bytes)",
          on and run.state == "on" and saved and first > 0 and run.p.poll() is None)
    t0 = os.path.getmtime(base + ".state.auto")
    again = until(lambda: os.path.getmtime(base + ".state.auto") > t0, 6)
    check("...and again a while later", again)
    os.kill(run.p.pid, signal.SIGKILL)               # (the battery runs out)
    run.p.wait()
    left = os.path.getsize(base + ".state.auto")
    check(f"the battery runs out mid-game: the last one's there, whole ({left} bytes)", left == first)
    run = GM.GameRun({"path": NES, "title": "Test Game", "system": "nes"})
    run.start(CORE, sound="", volume=80, picture="Fit", fb=FBF, resume=True, cheevos=False)
    on = until(lambda: run.state == "on" or run.ended, 20)
    check(f"...started again: it picks up from there ({run.state}, resumed: {run.resumed})", on and run.resumed)
    run.quit()
    until(lambda: run.ended, 10)

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
