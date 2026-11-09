"""What everyone's playing (screens/lobby.py): this one (the handheld, "gpi") and the TV's Pietato in a process of its own
(peer_pietato.py, "tv"), each with its web page. The TV plays a game: its beacon says which (and whether it can be watched
or joined); here, the home screen shows it top right ("tv is playing", the game, its console), with X Watch and SELECT
Join. X: the TV's asked, opens its game to watch (with a key) and says so on its picture as this one comes; this one
runs the TV's game too (its emulator, --watch), from its own copy (or one copied over from the TV first), and nothing of
it is kept here: its menu is Back, Volume, Picture and Stop watching, and the group chat hears it's watching. The TV's
game ending: this one's ends too, and says why. SELECT: this one joins it as player 2 (playing together, asked for from
here). A game that can't be watched, or a game for one: said so. Sharing off: no lobby. The beacon's game, from another:
only what makes sense of it is kept."""
import json, os, shutil, subprocess, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
import pitato.nearby as N

S = SP + "/t_lobby"
shutil.rmtree(S, ignore_errors=True)
HOME, TV = S + "/gpi", S + "/tv"
for h in (HOME, TV):
    for d in ("Music", "Videos", "Pictures", "Documents", "Games/Saves", "Games/nes", "Games/genesis", "Games/gba",
              "Games/n64"):
        os.makedirs(f"{h}/{d}")
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


# ---- what another's beacon says it's playing: only what makes sense of it ------------------------------------------
check("a game in another's beacon: kept as it is, when it makes sense",
      N.game_clean({"title": "Contra", "system": "nes", "watch": True, "join": False, "with": "Den", "watchers": 2})
      == {"title": "Contra", "system": "nes", "watch": True, "join": False, "with": "Den", "watchers": 2})
check("...and not when it doesn't (no title, a console's name that isn't one, numbers that aren't)",
      N.game_clean({"system": "nes"}) is None and N.game_clean({"title": "x", "system": "NES!"}) is None
      and N.game_clean("Contra") is None
      and N.game_clean({"title": "  x\n", "system": "nes", "watch": 1, "watchers": True, "with": 5})
      == {"title": "x", "system": "nes", "watch": False, "join": False, "with": "", "watchers": 0})

# ---- this one: the handheld ------------------------------------------------------------------------------------------
CONTRA = "Contra (USA)"
ROM = HOME + "/Games/nes/" + CONTRA + ".nes"
open(ROM, "wb").write(bytes(range(256)) * 96)
os.environ["HOME"] = HOME
g.STATE_FILE = S + "/gpi.json"; g.CACHE_DIR = S + "/gpicache"; g.PLEX_FILE = S + "/plex.json"
g.GROUP_LOG = S + "/gpigroup.json"
g.home_dir = lambda: HOME
import gk_static; gk_static.use_home(g, HOME)
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "", "returncode": 0, "stderr": ""})()
g.find_core = lambda key: f"/fake/{key}_libretro.so"
g.bios_missing = lambda core, game=None: ""
g.built_for_other_pi = lambda core: False
starts, told = [], []


def game_start(self, core, **kw):
    self.state = "on"
    self.kw = kw
    starts.append((self.game["path"], core, kw))


def game_quit(self, timeout=0):
    self.ended = True


g.GameRun.start = game_start
g.GameRun.quit = game_quit
g.GameRun.ask = lambda self, line, wants, timeout=3.0: (None, "")
g.GameRun.send = lambda self, line: True
g.GameRun.pause = lambda self: True
g.GameRun.resume = lambda self: None


class FB:
    w, h = 640, 480
    last = None
    def show(self, img): FB.last = img
    def show_part(self, img, box): pass
    def invalidate(self): pass
    def close(self): pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.set_setting("name", "gpi")
toasts = []
was_toast = m.toast
m.toast = lambda text, secs=4: (toasts.append(text), was_toast(text, secs))[1]
m.saves_tell = lambda run: told.append(run.game["path"])
m.share_now = lambda: None                             # (its beacon: asked for below, when it's wanted)
control = g.Control()
server = g.serve_control(m, control, port=0, key="k" * 32)
open(S + "/control-key", "w").write("k" * 32)
sys.path.append(ROOT + "/pitato")
import webui
webui.HOME = HOME
webui.STATIC = S + "/gpistatic"
os.makedirs(webui.STATIC + "/fonts")
webui.STATE_FILE = g.STATE_FILE
webui.CONTROL = ("127.0.0.1", server.server_address[1])
webui.CONTROL_KEY = S + "/control-key"
import logging; logging.getLogger("werkzeug").setLevel(logging.ERROR)
from werkzeug.serving import make_server
web = make_server("127.0.0.1", 0, webui.app, threaded=True)
threading.Thread(target=web.serve_forever, daemon=True).start()
MINE = f"http://127.0.0.1:{web.server_port}"

# ---- the other one: the TV's --------------------------------------------------------------------------------------------
LOG = S + "/tv.log"
open(LOG, "w").close()
shutil.copy(ROM, TV + "/Games/nes/" + CONTRA + ".nes")    # (the same game)
AXE = TV + "/Games/genesis/Golden Axe (USA).md"         # (one only it has)
open(AXE, "wb").write(b"\x05" * 8192)
open(TV + "/Games/gba/Golden Sun (USA).gba", "wb").write(b"\x02" * 4096)
open(TV + "/Games/n64/Mario Kart 64 (USA).z64", "wb").write(b"\x06" * 4096)
tv = subprocess.Popen([sys.executable, TESTS + "/peer_pietato.py", TV, LOG, "tv", MINE, "gpi"],
                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
line = tv.stdout.readline().split()
if line[:1] != ["READY"]:
    print("FAIL the TV's Pietato didn't start", line)
    sys.exit(1)
THEIRS = line[1]


def tv_do(text):
    tv.stdin.write(text + "\n")
    tv.stdin.flush()
    return tv.stdout.readline().strip()


def tv_state():
    return json.loads(tv_do("state"))


def tv_said(key, since=0, secs=8.0):
    end = time.time() + secs
    while True:
        rows = [json.loads(x) for x in open(LOG).read().splitlines()[since:] if x.strip()]
        hits = [r for r in rows if key in r]
        if hits or time.time() > end:
            return hits[-1] if hits else None
        time.sleep(0.1)


def tv_lines():
    return len(open(LOG).read().splitlines())


def tv_plays(path, title, key):
    tv_do(f"game {path}|{title}|{key}")
    st = tv_state()
    beacon = json.loads(tv_do("beacon"))
    m.pie.hear("127.0.0.1", beacon)                    # (its beacon, told straight to this one)
    return st, beacon


def home():
    m.game = None
    m.view = "home"
    m.dirty = True
    m.flush()


st, beacon = tv_plays(TV + "/Games/nes/" + CONTRA + ".nes", CONTRA, "nes")
check(f"the TV plays Contra: its beacon says so ({beacon.get('game')})", st["game"].endswith(CONTRA + ".nes")
      and beacon.get("game") == {"title": CONTRA, "system": "nes", "watch": True, "join": True, "with": "",
                                 "watchers": 0})
entries = m.lobby_entries()
check(f"here, the lobby: the TV, playing Contra ({[(e['host'], e['title']) for e in entries]})",
      [(e["host"], e["title"], e["url"]) for e in entries] == [("tv", CONTRA, THEIRS)])
home()
FB.last.convert("RGB").save(S + "/home_lobby.png")
check(f"...on the home screen: top right, with X Watch and SELECT Join ({m.lobby_hints()})",
      m.lobby_hints() == [("X", "Watch"), ("SELECT", "Join")] and m.lobby_words(entries[0], 1)
      == ("tv is playing", CONTRA, "NES"))
m.set_setting("share", "Off")
check("sharing off: no lobby", m.lobby_entries() == [] and m.lobby_hints() == [])
m.set_setting("share", "On")

# ---- X: watching it ----------------------------------------------------------------------------------------------------
since = tv_lines()
home()
m.press("x")
asked = tv_said("asked", since)
check(f"X: the TV's asked, and opens its game to watch, with a key ({asked})",
      asked is not None and asked["asked"].startswith("watchhost 5444 ") and len(asked["asked"].split()) == 3)
key = asked["asked"].split()[2]
path, core, kw = starts[-1] if starts else (None, None, {})
check(f"...this one runs it too, from its own copy: the TV's buttons play it ({kw.get('watch')})",
      path == ROM and kw.get("watch") == f"127.0.0.1:5444:{key}" and kw.get("resume") is False
      and kw.get("cheevos") is False and kw.get("saves", "").startswith(S + "/gpicache/watch")
      and m.view == "game" and m.game.watching == {"with": "tv", "url": THEIRS})
check(f"...its menu: Back, Volume, Picture and Stop watching ({m.game_menu_items()})",
      [k for k, _ in m.game_menu_items()] == ["resume", "volume", "picture", "quit"]
      and dict(m.game_menu_items())["quit"] == "Stop watching" and m.watch_note() == "Watching tv's game")
check(f"...the group chat hears it's watching ({m.group_doing()!r})", m.group_doing() == f"watching tv play {CONTRA}")
check(f"...and this one's beacon doesn't say it's playing it ({m.lobby_mine()})", m.lobby_mine() is None)
tv_do("gamenews watchjoined -")
tv_do("gamenews watchers 1")
said = tv_said("sent", since)
check(f"on the TV: this one's come, said on its picture ({said})", said == {"sent": "notice gpi is watching"})
beacon = json.loads(tv_do("beacon"))
check(f"...and its beacon says one's watching ({beacon['game']['watchers']})", beacon["game"]["watchers"] == 1)
m.game.net_news.append(("watchgone", "it left"))      # (the TV's game over: so's the emulator here, which says why)
m.game.ended = True
m.game_tick(time.monotonic())
check(f"the TV's game ends: so does this one's, and it says why ({toasts[-1:]})", m.game is None
      and toasts[-1] == "tv ended the game")
check("...nothing of it told as yours (no saves)", told == [])

# ---- SELECT: joining it as player 2 ----------------------------------------------------------------------------------
since = tv_lines()
home()
m.press("select")
asked = tv_said("asked", since)
check(f"SELECT: the TV's asked, and opens its game to this one alone ({asked})",
      asked is not None and asked["asked"].startswith("nethost 5442 ") and asked["asked"].endswith(" 127.0.0.1"))
key = asked["asked"].split()[2]
path, core, kw = starts[-1]
check(f"...this one joins it, as player 2 ({kw.get('net')})", path == ROM and kw.get("net") == f"127.0.0.1:5442:{key}"
      and m.game.together.get("with") == "tv" and m.game.together.get("host") is False)
st = tv_state()
check(f"...the TV's waiting for this one to join ({st['together']}), and says so on its picture",
      st["together"] == {"with": "gpi", "host": True, "state": "coming"}
      and tv_said("sent", since) == {"sent": "notice gpi is joining as player 2"})
beacon = json.loads(tv_do("beacon"))
check(f"...its beacon: no joining it now ({beacon['game']})", beacon["game"]["join"] is False)
m.pie.hear("127.0.0.1", beacon)
m.game_end()
home()
m.press("select")
check(f"...SELECT again: said so ({toasts[-1]})", toasts[-1] == "tv is playing with someone already")

# ---- a game this one hasn't got; ones that can't be watched or joined --------------------------------------------------
st, beacon = tv_plays(AXE, "Golden Axe (USA)", "genesis")
check(f"the TV plays a game this one hasn't got ({beacon['game']['title']})", beacon["game"]["title"] == "Golden Axe (USA)")
home()
n = len(starts)
m.press("x")
mine = HOME + "/Games/genesis/Golden Axe (USA).md"
end = time.time() + 10
while len(starts) == n and time.time() < end:
    while m.soon_jobs:
        m.soon_jobs.popleft()()
    time.sleep(0.05)
check(f"X: copied over from the TV first, then watched ({toasts[-2:]})", len(starts) > n and starts[-1][0] == mine
      and os.path.isfile(mine) and open(mine, "rb").read() == open(AXE, "rb").read()
      and starts[-1][2].get("watch", "").startswith("127.0.0.1:5444:"))
m.game_end()
st, beacon = tv_plays(TV + "/Games/gba/Golden Sun (USA).gba", "Golden Sun (USA)", "gba")
home()
m.press("select")
check(f"a Game Boy Advance game: to watch, not to join ({m.lobby_hints()}, {toasts[-1]!r})",
      m.lobby_hints() == [("X", "Watch")] and toasts[-1] == "That game is one player's")
st, beacon = tv_plays(TV + "/Games/n64/Mario Kart 64 (USA).z64", "Mario Kart 64 (USA)", "n64")
home()
m.press("x")
check(f"an N64 game: neither ({m.lobby_hints()}, {toasts[-1]!r})", m.lobby_hints() == []
      and toasts[-1] == "That game can't be watched")
tv_do("quit")
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
