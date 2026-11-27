"""A Pietato with no screen (a Pi with nothing on HDMI has no /dev/fb0). Media mode starts all the same, the menus
drawn in memory for the web page, which shows them and works them: its picture of the screen (black for a moment,
before anything's drawn), where it is, a tap, an app opened, a song played. What draws on the screen itself has
nowhere to, and says so: a video (picked on the Pi, on the web page, or sent from another Pietato), a game, one of
Apps' programs, Chromium. Attract mode never starts. With nobody at the web page it rests, whatever Battery saver
says: nothing's drawn, Wi-Fi's left as it is, music plays on, and the page looking wakes it. Settings > Screen says
there's none. To the terminal and back: still none. A screen plugged in later takes the menus, where they were. With a
screen from the start, none of this: a video plays, and it rests only as Battery saver says. Then the real main loop
(app.py) and the control server, with no screen: media mode as it starts, the page's picture, its remote, the
terminal and media mode again from the page, resting till the page looks."""
import contextlib, io, json, os, shutil, sys, threading, time, urllib.request
from paths import SP, TESTS  # noqa: E402  (this test's folder of work; tests)
S = SP + "/t_noscreen"
shutil.rmtree(S, ignore_errors=True)
H = S + "/home/u"
for d in ("Music", "Videos", "Pictures", "Documents"):
    os.makedirs(f"{H}/{d}")
open(f"{H}/Music/song.mp3", "wb").write(b"x")
open(f"{H}/Videos/film.mp4", "wb").write(b"x")
sys.path.insert(0, TESTS)
import pietato_all as g
import pitato.screens.rest as R
from PIL import Image

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.PLEX_FILE = S + "/plex.json"; g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
open(g.STATE_FILE, "w").write('{"settings": {"battery": "Off"}}')
g.home_dir = lambda: H
for t in g.LIBRARY:
    if t.get("files"):
        t["files"] = [f.replace("/home/*", S + "/home/*") for f in t["files"]]
import gk_static; gk_static.use_home(g, H)
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
wifi = []
R.wifi_dev = lambda: "wlan0"
R.wifi_power_save = lambda dev, on=None: (wifi.append((dev, on)), False)[1]
R.REST_AFTER, R.REST_UNSEEN, R.REST_WATCHED, R.BATTERY_LOOK = 0.6, 0.6, 1.0, 0.05
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


class NoFb(g.Framebuffer):
    """The real one, where there's no /dev/fb0 to open."""
    tried = 0

    def __init__(self, *a, **k):
        NoFb.tried += 1
        raise FileNotFoundError(2, "No such file or directory", "/dev/fb0")


class Proc:
    """A player, as far as media mode asks of one."""
    def __init__(self): self.stdin, self.gone = io.StringIO(), None
    def poll(self): return self.gone
    def wait(self, timeout=None): self.gone = 0
    def kill(self): self.gone = -9


def said(fn, *a, **k):
    """What it prints, doing that."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn(*a, **k)
    return out.getvalue()


def settle(cond, secs=5):
    end = time.time() + secs
    while time.time() < end:
        m.tick(); m.rest_tick(time.monotonic()); m.flush()
        if cond():
            return True
        time.sleep(0.05)
    return False


def picture(shot):
    return Image.open(io.BytesIO(shot[0])).convert("RGB")


# ---- no screen: media mode all the same, drawn for the web page ------------------------------------------------------
g.Framebuffer = NoFb
m = g.Media()
played = []


def spawn(args, target):
    played.append((list(args), target))
    m.proc = Proc()


m.spawn = spawn
m.case = None
words = said(m.enter)
check(f"no screen: media mode starts all the same, the menus the GPi Case's size, in memory ({words.strip()!r})",
      m.active and m.no_screen() and isinstance(m.fb, g.NoScreen) and (m.fb.w, m.fb.h) == (640, 480)
      and "no screen" in words and "media mode unavailable" not in words and NoFb.tried == 1)
shot = m.web_shot()
check("the web page's picture of the screen, before anything's drawn: black for a moment, not an error",
      bool(shot) and shot[1] == "image/png" and picture(shot).size == (640, 480) and picture(shot).getbbox() is None)
m.flush()
shot = m.web_shot()
check(f"...then the menus, as they're drawn (picture {shot[2]})", m.fb.last is not None
      and picture(shot).size == (640, 480) and picture(shot).getbbox() is not None and shot[2] == m.fb.frames > 0)
st = m.web_state()
check(f"where it is, for the web page ({st['mode']}, {st['where']}, {st['canvas']})", st["mode"] == "media"
      and st["where"] == "Home screen" and st["canvas"] == [640, 480] and st["size"] == [640, 480])
k = [name for name, _ in m.home_apps()].index("Radio")
box = next(b for b, w in m.taps if w == ("sel", "attr", "home_sel", k))
names, r = m.web_touch({"cmd": "tap", "x": (box[0] + box[2]) / 2 / m.fb.w, "y": (box[1] + box[3]) / 2 / m.fb.h})
for name in names:                                     # (app.py presses what a tap stands for)
    m.press(name)
m.flush()
check(f"a tap on the web page's picture: the app under it, opened ({names}, {r}, {m.where_text()})",
      names == ["a"] and r == {"ok": True} and m.view == "list" and m.where_text() == "Radio")
r = m.web_command({"cmd": "open", "app": "Music"})
m.flush()
check(f"an app opened from the web page ({r}, {m.where_text()})", r == {"ok": True} and m.view == "list"
      and m.where_text() == "Music")
r = m.web_command({"cmd": "play", "items": [{"src": f"{H}/Music/song.mp3"}], "index": 0, "where": "Music"})
check(f"a song played from the web page: it plays ({r}, {[t for _, t in played]})", r.get("ok") is True
      and [t for _, t in played] == [f"{H}/Music/song.mp3"] and m.kind == "audio" and "-novideo" in played[0][0])

# ---- what draws on the screen itself: nowhere to, and says so --------------------------------------------------------
m.stop(); played.clear(); m.msg = None
film = g.item(f"{H}/Videos/film.mp4", "film", "video", f"{H}/Videos/film.mp4")
m.here_begin(False)
m.play([film], 0)
out = m.here_end({"ok": True})
check(f"a video picked on the Pi: not played, and said, on the web page too ({m.msg!r}, {out})", played == []
      and m.proc is None and m.msg == "There's no screen here for a video" and out.get("note") == m.msg)
r = m.web_command({"cmd": "play", "items": [{"src": f"{H}/Videos/film.mp4"}], "index": 0, "where": "Videos"})
check(f"...played from the web page: it's told why not ({r})", r == {"error": "There's no screen to play it on"}
      and played == [])
m.here_begin(True)
m.play([film], 0)
out = m.here_end({"ok": True})
check(f"...with Play here on: the page plays it itself, as ever ({out.get('play', {}).get('kind')})",
      out.get("play", {}).get("kind") == "video" and played == [])
r = m.handoff_take_media({"media": "video", "title": "film", "src": "https://example.org/film.mp4", "pos": 0},
                         "http://10.0.0.7:5432", "Den")
check(f"...sent from another of yours: not taken, so it stays there ({r})", r.get("ok") is False
      and "no screen" in r.get("error", ""))
r = m.handoff_take_media({"media": "radio", "title": "Jazz", "src": "http://radio.example/jazz", "pos": 0},
                         "http://10.0.0.7:5432", "Den")
check(f"...a station sent from another: taken ({r})", r == {"ok": True})
m.soon_jobs.clear()
why = m.game_cant({"path": f"{H}/Games/gb/Zelda.gb", "title": "Zelda", "system": "gb"})
check(f"a game: can't start here, and why ({why})", why == ("There's no screen here for a game", 4))
m.msg = None
m.prog_start("cmatrix")
check(f"one of Apps' programs: not started ({m.msg!r})", m.prog is None
      and m.msg == "There's no screen here for cmatrix")
m.chromium_here, m.msg = (lambda: True), None
m.state.setdefault("www", {})["chromium_seen"] = True
m.chromium_open()
check(f"Chromium: not started ({m.msg!r})", m.chromium is None and m.view != "chromium"
      and m.msg == "There's no screen here for Chromium")
now = time.monotonic()
m.go_home(); m.msg = None
m.stirred, m.web_watched = now - 100000, 0.0
check(f"Attract mode (it's {m.setting('attract')}): never, with no screen", m.setting("attract") != "Off"
      and not m.attract_ready(now))
rows = dict((k, v) for k, v, _ in m.settings_root_rows())
check(f"Settings > Screen's row: {m.settings_page_value('display')!r}", rows["display"] == "Screen"
      and m.settings_page_value("display") == "No screen")

# ---- nobody at the web page: it rests, whatever Battery saver says ---------------------------------------------------
m.stirred, m.web_watched = time.monotonic(), 0.0
check(f"Battery saver's {m.setting('battery')}, on mains power: off, but it may rest all the same",
      not m.saver_on() and m.rests())
words = said(settle, lambda: m.resting, 3)
check(f"nothing happening, and nobody at the web page: it rests ({words.strip()!r})", m.resting
      and "no screen" in words and wifi == [])
n = m.fb.frames
m.dirty = True
settle(lambda: False, 0.3)
check("...nothing's drawn meanwhile, and the main loop looks around once a second",
      m.fb.frames == n and m.tick_limit() == g.REST_TICK)
shot = m.web_shot()                                    # (the page looking: it wakes, as from a button)
settle(lambda: m.fb.frames > n, 2)
check("the web page looking at the screen: awake, and drawn again", not m.resting and m.fb.frames > n
      and picture(m.web_shot()).getbbox() is not None)
end = time.time() + 1.3
while time.time() < end:                               # (the page goes on looking: longer than it waits to rest)
    m.web_shot(); m.tick(); m.rest_tick(time.monotonic()); m.flush(); time.sleep(0.05)
check("...and it stays awake while the page goes on looking", not m.resting)
m.proc, m.kind, m.view = Proc(), "audio", "now"
m.cur = g.item(f"{H}/Music/song.mp3", "song", "audio", f"{H}/Music/song.mp3")
music = m.proc
said(settle, lambda: m.resting, 3)
check("a song playing, Now playing up, nobody at the page: it rests, and the song plays on", m.resting
      and m.proc is music and m.kind == "audio")
m.proc, m.kind, m.cur, m.view = None, None, None, "home"
r = m.web_command({"cmd": "open", "app": "Radio"})     # (app.py stirs it for anything done on the page: here, by hand)
m.stir()
check(f"something done on the web page: awake, and done ({r}, {m.where_text()})", not m.resting
      and m.where_text() == "Radio")

# ---- to the terminal and back: still none ----------------------------------------------------------------------------
m.leave()
check("to the terminal: media mode's closed, as ever", not m.active and m.fb is None and not m.no_screen())
words = said(m.enter)
check("...and back: no screen still, the menus for the web page again", m.active and m.no_screen()
      and "no screen" in words)

# ---- a screen plugged in later: the menus go on it -------------------------------------------------------------------
m.web_command({"cmd": "open", "app": "Music"})
m.flush()
m.screen_look = 0.0
tried = NoFb.tried
m.screen_tick(time.monotonic())
m.screen_tick(time.monotonic())                        # (asked again at once: not looked for again yet)
check(f"no screen yet: looked for now and then, not every time ({NoFb.tried - tried})", NoFb.tried == tried + 1
      and m.no_screen())


class TV:
    """A TV, come since: the menus a little bigger on it."""
    w, h = 960, 540; real_w, real_h = 1920, 1080
    shown = []

    def __init__(self):
        self.last, self.frames = None, 0

    def show(self, img):
        self.last = img; TV.shown.append(img.size); self.frames += 1

    def close(self): pass


g.Framebuffer = TV
m.screen_look = 0.0
words = said(m.screen_tick, time.monotonic())
m.flush()
check(f"a screen's turned up: the menus go on it, its size, where they were ({words.strip()!r}, {TV.shown[-1:]}, "
      f"{m.where_text()})", isinstance(m.fb, TV) and not m.no_screen() and TV.shown[-1:] == [(960, 540)]
      and m.where_text() == "Music" and "screen" in words)
m.here_begin(False); played.clear(); m.msg = None
m.play([film], 0)
m.here_end({"ok": True})
check(f"...a video plays on it ({[t for _, t in played]})", [t for _, t in played] == [f"{H}/Videos/film.mp4"]
      and m.kind == "video" and "-vo" in played[0][0])
m.stop(); m.proc = None
m.go_home()
m.stirred, m.web_watched = time.monotonic(), 0.0
settle(lambda: m.resting, 1.5)
check("...and it rests only as Battery saver says: Off, never", not m.resting and not m.rests())
now = time.monotonic()
m.stirred = now - 100000
check("...Attract mode's time comes, as ever", m.attract_ready(now))
m.leave()

# ---- the real main loop, and the control server the web page talks to, with no screen ---------------------------------
g.Framebuffer = NoFb
g.list_devices = lambda: []


class UI:
    def write(self, *a): pass
    def syn(self): pass


m = g.Media()
m.spawn = spawn
m.case = None
control = g.Control()
server = g.serve_control(m, control, port=0, key="k" * 32)
port = server.server_address[1]
done = threading.Event()
errors = []


def loop():
    try:
        g.run(UI(), m, control, stop=done.is_set)
    except Exception as ex:
        import traceback; traceback.print_exc(); errors.append(ex)


def wait_for(cond, secs=5):
    end = time.time() + secs
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def post(what, body):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/{what}", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Pitato-Key": "k" * 32})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def get(what):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/{what}", headers={"X-Pitato-Key": "k" * 32})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


threading.Thread(target=loop, daemon=True).start()
check("the main loop, as the Pi starts (At start-up: Home screen): media mode, with no screen",
      wait_for(lambda: m.active and m.no_screen() and m.fb.last is not None, 5))
pic = Image.open(io.BytesIO(get("screen"))).convert("RGB")
st = json.loads(get("state"))
check(f"the web page: its picture of the screen, and where it is ({pic.size}, {st['mode']}, {st['where']})",
      pic.size == (640, 480) and pic.getbbox() is not None and st["mode"] == "media" and st["where"] == "Home screen")
sel = m.home_sel
out = post("press", {"button": "right"})
check(f"its remote: a button, pressed ({out}, {sel} -> {m.home_sel})", out.get("ok") is True
      and wait_for(lambda: m.home_sel != sel, 2))
out = post("mode", {"to": "terminal"})
check(f"to the terminal from the page ({out})", out == {"ok": True} and wait_for(lambda: not m.active, 3))
out = post("mode", {"to": "media"})
check(f"...and media mode again: it starts, where it once said there's no screen for it ({out})",
      out == {"ok": True} and m.active and m.no_screen())
out = post("play", {"items": [{"src": f"{H}/Videos/film.mp4"}], "index": 0, "where": "Videos"})
check(f"a video from the page: told why not ({out})", out == {"error": "There's no screen to play it on"})
check("nobody at the page for a while: resting", wait_for(lambda: m.resting, 5))
time.sleep(0.3)                                       # (its dark frame's shown as it starts to rest: the frames
n = m.fb.frames                                       #  asked for come after that one)
got = []
threading.Thread(target=lambda: got.append(get(f"screen?after={n}&wait=5")), daemon=True).start()
check("the page asks for the screen's picture: awake, and it gets the menus",
      wait_for(lambda: not m.resting, 3) and wait_for(lambda: bool(got), 8)
      and Image.open(io.BytesIO(got[0])).convert("RGB").getbbox() is not None)
done.set()
time.sleep(0.5)
server.shutdown()
check(f"no errors in the main loop ({errors})", not errors)

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
sys.exit(0 if all(ok_all) else 1)
