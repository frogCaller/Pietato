"""Another Pietato, for the tests that need two (sending a game or a video from one to the other, playing together):
its own home folder, its web page and control server on ports of their own, and its main loop, in a process of its own.
Its emulator and player are stand-ins: what it starts, plays and says goes in a log (JSON, a line each), and its
emulator's saves are written as the real one writes them when a game ends (in its folder of saves: a game played
together has its own). With presses, what's pressed and let go of in media mode (and from which controller), and the
terminal's keys, go in the log too (another Pietato controlling this one: pilot.py).

    python3 peer_pietato.py HOME LOG NAME PEER_URL PEER_NAME [slow] [presses]

It prints READY <its web page's address> once it's answering; then takes a line at a time: state (what's on its
screen, as JSON), press BUTTON (pressed, on its main loop), home (HOME on a picture, a PDF or some text: its menu),
mediahome (...on a video or Now playing), play PATH|PATH (songs of its own, the first playing), pilot (Home > Control
another Pietato: the other one picked), pilotpress BUTTON (a button of its own, while it controls the other one),
busy SECONDS (its main loop held up that long, as a slow Pi's is: answered at once),
news WHAT WHY (its emulator says WHAT, then ends: netgone, say), gamenews WHAT WHY (...and plays on: watchjoined, say),
game PATH|TITLE|SYSTEM (a game of its own, opened), send (its game, to the other one: its menu's Play on another
Pietato), endgame (its game, ended), beacon (what it tells your others it is, and doing, as JSON),
expire (another's asking to play together, not answered in time),
peer URL NAME [too] (the other one; too: another, as well), deaf SECONDS (its web page says nothing of a party that
long: a message that never gets there), set KEY VALUE (a setting), pilots (the controllers another Pietato's working
it with, as JSON), group say TEXT / log / quiet on|off / answer Yes|No (the group chat: what's said in it, as JSON,
for log), hear BEACON (another's
beacon, as JSON, heard as if it came from this machine's own address; hearfrom ADDRESS BEACON: from that address),
quit. Its emulator,
asked to open its game (nethost, watchhost), says it has (at 5442 and 5444), and the ask goes in the log.
PITATO_PILOT_GONE: seconds of nothing before one controlling it is taken to have gone.
PITATO_OWN_MUSIC: its songs are the ones in its own home's Music (not this machine's). PITATO_CLOCK_AHEAD: seconds its
clock (time.monotonic) is ahead of this machine's, as another Pi's is that's been up longer. PITATO_PING_SLOW: seconds
longer its look at a party leader's clock takes (its WiFi dozing). PITATO_PARTY_QUICK: leading a party, its looks at
who's in it and who else is on come this many times sooner. PITATO_ADDR: its own address on this machine (127.0.0.3,
say): its web page answers there, and what it asks of the others comes from there, so several of them here are told
apart as they are on a network. PITATO_WEB_PORT: its web page's port (the same again, started again)."""
import json
import os
import sys
import threading
import time

if os.environ.get("PITATO_CLOCK_AHEAD"):         # (before Pietato's loaded: its clock, from the start)
    real_clock, AHEAD = time.monotonic, float(os.environ["PITATO_CLOCK_AHEAD"])
    time.monotonic = lambda: real_clock() + AHEAD

HOME, LOG, NAME, PEER_URL, PEER_NAME = sys.argv[1:6]
ADDR = os.environ.get("PITATO_ADDR") or "127.0.0.1"
SLOW = "slow" in sys.argv[6:]
PRESSES = "presses" in sys.argv[6:]
TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("PITATO_ROOT") or os.path.dirname(TESTS)
sys.path.insert(0, TESTS)
sys.path.insert(0, ROOT)
os.environ["HOME"] = HOME
import pietato_all as g  # noqa: E402
import socket  # noqa: E402

if ADDR != "127.0.0.1":                          # (what it asks of the others on this machine: from its own address)
    real_connect = socket.create_connection

    def connect(address, timeout=socket.getdefaulttimeout(), source_address=None, **kw):
        if source_address is None and str(address[0]).startswith("127."):
            source_address = (ADDR, 0)
        return real_connect(address, timeout, source_address, **kw)
    socket.create_connection = connect
    import pitato.party as party_core  # noqa: E402
    party_core.PARTY_HOST = ADDR                 # (a party it leads: its clock and its station, there too)

lock = threading.Lock()
SAY = sys.stdout                                 # (the test's word with it; what Pietato prints goes with its errors)
sys.stdout = sys.stderr


def log(**what):
    with lock, open(LOG, "a") as f:
        f.write(json.dumps(what) + "\n")


for d in ("Music", "Videos", "Pictures", "Documents", "Games/Saves"):
    os.makedirs(os.path.join(HOME, d), exist_ok=True)
S = HOME + "/.pietato"
os.makedirs(S, exist_ok=True)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"; g.GROUP_LOG = S + "/group.json"
g.home_dir = lambda: HOME
import gk_static  # noqa: E402
gk_static.use_home(g, HOME)
socket.gethostname = lambda: NAME
real_run = g.subprocess.run
g.subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                         if isinstance(cmd, (list, tuple)) and cmd[:1] in (["chvt"], ["fgconsole"],
                                                                                            ["setterm"], ["amixer"])
                                         else real_run(cmd, *a, **k))
g.list_devices = lambda: []
g.MEDIA_VT = 99                                  # (no such console: this machine's own are left as they are)
g.find_core = lambda key: f"/fake/{key}_libretro.so"
g.bios_missing = lambda core, game=None: ""
g.built_for_other_pi = lambda core: False
import pitato.screens.together as together  # noqa: E402
together.link_core = lambda: "/fake/gambatte_libretro.so"   # (its Game Boy link cable's emulator, there)
if SLOW:
    g.slow_pi = lambda: True
if os.environ.get("PITATO_PILOT_GONE"):
    g.PILOT_GONE = float(os.environ["PITATO_PILOT_GONE"])
if os.environ.get("PITATO_OWN_MUSIC"):
    next(t for t in g.LIBRARY if t["name"] == "Music")["dirs"] = [HOME + "/Music"]
import pitato.screens.party as party_screen  # noqa: E402
if os.environ.get("PITATO_PING_SLOW"):
    real_offset = party_screen.clock_offset
    party_screen.clock_offset = lambda *a, **k: (time.sleep(float(os.environ["PITATO_PING_SLOW"])),
                                                 real_offset(*a, **k))[1]
if os.environ.get("PITATO_PARTY_QUICK"):
    for k in ("PARTY_LOOK", "PARTY_SAID", "PARTY_AGAIN", "PARTY_LOST"):
        if hasattr(party_screen, k):
            setattr(party_screen, k, getattr(party_screen, k) / float(os.environ["PITATO_PARTY_QUICK"]))


# ---- its emulator: started, and its saves written as it ends -------------------------------------------------------
def game_start(self, core, **kw):
    self.state = "on"
    self.kw = kw
    log(started=self.game["path"], system=self.game["system"], resume=kw.get("resume", True), core=core,
        saves=kw.get("saves"), net=kw.get("net", ""), options=list(kw.get("options") or ()),
        cheevos=kw.get("cheevos", True))


def game_quit(self, timeout=0):
    if getattr(self, "quitted", False):
        return
    self.quitted = True
    saves = getattr(self, "kw", {}).get("saves") or os.path.join(g.games_dir(), g.SAVES_FOLDER)
    base = os.path.join(saves, g.save_name(self.game["path"]))
    for ext in (".srm", ".state.auto"):
        with open(base + ext, "w") as f:
            f.write(f"{NAME}'s {ext}, {time.time()}")
    self.ended = True
    log(quit=self.game["path"])


def game_ask(self, line, wants, timeout=3.0):
    log(asked=line)
    if line.startswith("nethost "):
        return "nethost", "ok 5442"
    if line.startswith("watchhost "):
        return "watchhost", "ok 5444"
    return None, ""


g.GameRun.start = game_start
g.GameRun.quit = game_quit
g.GameRun.ask = game_ask
g.GameRun.send = lambda self, line: bool(line.startswith("notice ") and log(sent=line))   # (what it says on its
#                                                                                          picture, logged)
g.GameRun.pause = lambda self: True
g.GameRun.resume = lambda self: None


# ---- its player -------------------------------------------------------------------------------------------------
class Proc:
    def __init__(self):
        self.stdin = open(os.devnull, "w")
        self.stdout = iter(())
        self.stderr = iter(())
        self.returncode = None
        self.args = []

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = 0
        return 0

    def kill(self):
        self.returncode = -9


def spawn(self, args, target):
    self.started = time.monotonic()
    self.proc = Proc()
    log(play=target, args=list(args), kind=self.kind)


g.PlayerScreen.spawn = spawn


class FB:
    w, h = 640, 480
    real_w, real_h = 640, 480

    def show(self, img): pass
    def show_part(self, img, box): pass
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
m = g.Media()
m.enter()
was_toast = m.toast
m.toast = lambda text, secs=4: (log(toast=text), was_toast(text, secs))[1]
if PRESSES:                                      # (what's pressed in media mode, and by which controller)
    was_press, was_release = m.press, m.release

    def press(name, repeat=False):
        pad = m.input_pad
        log(pressed=name, repeat=repeat, pad=pad.path if pad is not None else None, view=m.view,
            guard=m.web_guard, t=time.monotonic())
        return was_press(name, repeat)

    def release(name):
        pad = m.input_pad
        log(released=name, pad=pad.path if pad is not None else None, t=time.monotonic())
        return was_release(name)
    m.press, m.release = press, release
m.pie.heard[PEER_URL] = {"host": PEER_NAME, "seen": time.time() + 3600, "peer": True}
control = g.Control()
server = g.serve_control(m, control, port=0, key="k" * 32)
open(S + "/control-key", "w").write("k" * 32)
sys.path.append(ROOT + "/pitato")
import webui  # noqa: E402
webui.HOME = HOME
webui.STATIC = S + "/static"
os.makedirs(webui.STATIC + "/fonts", exist_ok=True)
webui.STATE_FILE = g.STATE_FILE
webui.CONTROL = ("127.0.0.1", server.server_address[1])
webui.CONTROL_KEY = S + "/control-key"
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from werkzeug.serving import make_server  # noqa: E402
DEAF = [0.0]


@webui.app.before_request
def deaf():
    """Nothing about a party gets to it, for a while (deaf SECONDS)."""
    if webui.request.path == "/api/party" and time.time() < DEAF[0]:
        return "Not now", 503


web = make_server(ADDR, int(os.environ.get("PITATO_WEB_PORT") or 0), webui.app, threaded=True)
threading.Thread(target=web.serve_forever, daemon=True).start()
done = threading.Event()
TERM = type("UI", (), {"write": (lambda self, t, c, v: log(key=c, value=v)) if PRESSES else (lambda *a: None),
                       "syn": lambda *a: None})()   # (the terminal's keys)
threading.Thread(target=lambda: g.run(TERM, m,
                                      control, stop=done.is_set), daemon=True).start()
def state_now():
    """What's on its screen, for the test (read on its main loop, so never halfway through opening something)."""
    run = m.game
    inv = m.invite or {}
    v = dict(m.v)
    shown = {k: v[k] for k in ("type", "title", "path", "page", "pages", "fit", "zoom", "scroll", "sx", "top",
                               "size", "rot", "items") if k in v}
    if v.get("type") == "text":
        lines = v.get("lines") or []
        shown["first"] = lines[v["top"]] if v.get("top", 0) < len(lines) else ""
    target = m.handoff_target()
    party = m.party or {}
    gig = getattr(m, "gig", None)
    band = {"lead": gig.lead, "with": gig.leader_name, "mine": list(gig.mine), "my": gig.my, "plan": gig.plan,
            "synced": gig.lead or gig.offset is not None, "who": gig.who, "ready": len(gig.ready),
            "does": {k: list(v) for k, v in gig.does.items()}, "members": sorted(x["name"] for x in gig.members.values()),
            "playing": gig.proc is not None and gig.sound_ok is True} if gig is not None else None
    return json.dumps({"game": run.game["path"] if run else None, "kind": m.kind, "view": m.view,
                       "page": g.LIBRARY[m.tab]["name"] if m.view == "list" else m.view, "band": band,
                       "watching": (run.watching or {}).get("with") if run and run.watching else None,
                       "together": {k: v for k, v in (run.together or {}).items() if k in ("with", "host", "state")}
                       if run else None, "lobby": [(e["host"], e["title"]) for e in m.lobby_entries()],
                       "playing": type(m.proc).__name__ if m.proc else None,
                       "party_src": getattr(getattr(m.proc, "player", None), "src", None),
                       "pilot": m.pilot_out.status(time.monotonic()) if m.pilot_on() else None,
                       "cur": (m.cur or {}).get("title"), "paused": bool(m.paused),
                       "cover": (m.cur or {}).get("cover"),   # (a song from another of yours: its cover, brought here)
                       "party": {"lead": party.get("lead"), "with": party.get("name"),
                                 "members": sorted((party.get("members") or {}).values()),
                                 "offset": party.get("offset"), "n": party.get("n"),
                                 "rough": party.get("rough")} if party else None,
                       "back": [x["title"] for x in m.resume_later[0]] if m.resume_later else None,
                       "viewer": shown, "to": target[0] if target else None,
                       "file_menu": [k for k, _ in m.file_menu_items()] if m.view == "filemenu" else [],
                       "media_menu": [k for k, _ in m.media_menu_items()] if m.view == "mediamenu" else [],
                       "menu": [k for k, _ in m.game_menu_items()] if run else [],
                       "whose": (run.game.get("whose") or "") if run else None, "me": m.saves_id(),
                       "asking": [list(r) for r in m.whose["rows"]] if m.view == "whose" and m.whose else None,
                       "send": m.game_value("send") if run else "",
                       "note": m.together_note() if run else "",
                       "invite": {"host": inv.get("host"), "title": (inv.get("ident") or {}).get("title"),
                                  "link": inv.get("link"), "pick": inv.get("pick"),
                                  "games": [x["title"] for x in inv.get("games") or []]} if inv else None})


print(f"READY http://{ADDR}:{web.server_port}", file=SAY, flush=True)
try:
    for line in sys.stdin:                            # (the test says what to do here, a line at a time)
        words = line.split(None, 1)
        if not words:
            continue
        if words[0] == "quit":
            break
        if words[0] == "peer":                         # the other one's web page, now it's up (too: another)
            url, name = words[1].split()[:2]
            if words[1].split()[2:] != ["too"]:
                m.pie.heard.clear()
            m.pie.heard[url] = {"host": name, "seen": time.time() + 3600, "peer": True}
            print("ok", file=SAY, flush=True)
        elif words[0] == "deaf":                        # nothing about a party gets to it, that long
            DEAF[0] = time.time() + float(words[1])
            print("ok", file=SAY, flush=True)
        elif words[0] == "busy":                        # its main loop held up a while (answered at once)
            m.soon_jobs.append(lambda secs=float(words[1]): time.sleep(secs))
            m.wake()
            print("ok", file=SAY, flush=True)
        elif words[0] == "set":                         # a setting, as Settings sets it
            key, value = words[1].split(None, 1)
            m.set_setting(key, value.strip())
            if key == "volume":                         # (how loud it plays, now)
                m.volume = int(value)
            print("ok", file=SAY, flush=True)
        elif words[0] == "group":                       # the group chat: say TEXT, log, quiet on|off, answer Yes|No
            rest = (words[1] if len(words) > 1 else "").split(None, 1)
            got, done_it = [], threading.Event()

            def job(what=rest[0] if rest else "", arg=rest[1].strip() if len(rest) > 1 else ""):
                try:
                    c = m.circle
                    if what == "say":
                        m.you_noticed()
                        c.you_said(arg)
                    elif what == "quiet":
                        m.set_setting("group_talk", "Off" if arg == "on" else "On")
                        c.set_quiet(arg == "on")
                    elif what == "answer":
                        ask = c.open_ask()
                        got.append(json.dumps({"ok": bool(ask and c.answer(ask, arg))}))
                    elif what == "log":
                        got.append(json.dumps(c.lines()))
                finally:
                    done_it.set()
            m.soon_jobs.append(job)
            m.wake()
            done_it.wait(10)
            print(got[0] if got else "ok", file=SAY, flush=True)
        elif words[0] == "hear":                        # another's beacon, as if heard (from this machine's address)
            m.pie.hear("127.0.0.1", json.loads(words[1]))
            print("ok", file=SAY, flush=True)
        elif words[0] == "hearfrom":                    # ...or from the address given (hearfrom ADDRESS BEACON)
            addr, said = words[1].split(None, 1)
            m.pie.hear(addr, json.loads(said))
            print("ok", file=SAY, flush=True)
        elif words[0] == "beacon":                      # what it tells your others (straight to each), its web page's
            got, done_it = [], threading.Event()        # port as it really is

            def job():
                try:
                    got.append(json.dumps(dict(m.share_beacon(m.own_name(), full=True), port=web.server_port)))
                finally:
                    done_it.set()
            m.soon_jobs.append(job)
            m.wake()
            done_it.wait(10)
            print(got[0] if got else "{}", file=SAY, flush=True)
        elif words[0] == "pilots":                      # the controllers another Pietato's working it with
            pads = list(m.pads.by_path.values()) if m.pads else []
            print(json.dumps({"active": m.active, "view": m.view, "home_sel": m.home_sel, "guard": m.web_guard,
                              "pads": [{"name": p.dev.name, "kind": p.kind, "path": p.path, "down": sorted(p.down),
                                        "swapped": p.swapped} for p in pads if p.kind == "pilot"]}),
                  file=SAY, flush=True)
        elif words[0] == "state":                     # (on its main loop: never halfway through opening something)
            got, done_it = [], threading.Event()

            def job():
                try:
                    got.append(state_now())
                finally:
                    done_it.set()
            m.soon_jobs.append(job)
            m.wake()
            if not done_it.wait(10):
                got.append(state_now())
            print(got[0], file=SAY, flush=True)
        elif words[0] in ("press", "news", "gamenews", "game", "expire", "home", "mediahome", "send",
                          "endgame", "play", "pilot", "pilotpress"):   # (on its main loop, as a button would be)
            done_it = threading.Event()
            rest = words[1].split() if len(words) > 1 else []

            def job(what=words[0], rest=rest):
                try:
                    if what == "press":
                        m.press(rest[0])
                    elif what == "home":
                        m.file_home()
                    elif what == "mediahome":           # (HOME on a video or Now playing: its menu)
                        m.media_home()
                    elif what == "news" and m.game is not None:
                        m.game.net_news.append((rest[0], " ".join(rest[1:])))
                        m.game.ended = True
                    elif what == "gamenews" and m.game is not None:
                        m.game.net_news.append((rest[0], " ".join(rest[1:])))
                        if rest[0] == "watchers":
                            m.game.watchers = int(rest[1])
                    elif what == "game":
                        path, title, key = " ".join(rest).split("|")
                        m.game_open({"src": path, "title": title, "system": key})
                    elif what == "send":                # (its game's menu: Play on another Pietato)
                        m.game_send()
                    elif what == "endgame":             # (...Quit)
                        m.game_end()
                    elif what == "expire" and m.invite is not None:
                        m.invite["until"] = 0.0
                    elif what == "play":                # (songs of its own, the first of them playing)
                        songs = [g.item(p, os.path.basename(p).rsplit(".", 1)[0], "audio", p)
                                 for p in " ".join(rest).split("|")]
                        m.play(songs, 0)
                    elif what == "pilot":               # (Home > Control another Pietato: the other one, picked)
                        m.tab = m.tab_index("pilot")
                        m.view = "list"
                        m.load_tab(m.tab)
                        m.pilot_start(m.pilot_rows()[0])
                    elif what == "pilotpress":          # (a button of its own controller's, while it controls it)
                        m.pilot_press(rest[0], True)
                        m.pilot_press(rest[0], False)
                finally:
                    done_it.set()
            m.soon_jobs.append(job)
            m.wake()
            done_it.wait(10)
            print("ok", file=SAY, flush=True)
finally:
    done.set()
