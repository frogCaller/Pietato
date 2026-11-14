"""An agent that answers in words (OpenClaw, Hermes), connected both ways by agent_link.py, run as on its computer
against the web page and media mode, both running, and against pretend agents that speak as the real ones do (their
chat API: OpenAI's shape, a key, the conversation kept by them). Setting up: the Pi hands the script out; it remembers
the Pietato, keeps a copy of itself, and writes the skill for whichever agent is there (and where you say). What the
skill runs: status, open, home, files, play, press, player, type, pose, screen, list, on one of several; what it
can't do (a prompt for the agent typed through it isn't sent; a wrong button, folder or name is said). Listening: a
prompt typed on the Bot at work goes to the agent with its key, in one conversation; the Bot acts out its tools and
its typing; what it answers shows on a card (whose it is, markdown taken out; a long one gone through with up and
down; X reads it out loud; B closes it and SELECT shows it again; the next prompt closes it); elsewhere, a word that
it's there. An agent that can't answer, one that's off, a wrong key, another API with --url (sent the turns itself),
a web page with a password, and --remove."""
import json, os, shutil, socket, stat, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
H = SP + "/tlink"
shutil.rmtree(H, ignore_errors=True)
for d in ("pi/Music/Album", "pi/Videos", "pi/Pictures", "pi/Documents", "pi/Games", "laptop", "bare", "both"):
    os.makedirs(f"{H}/{d}")
open(f"{H}/pi/Music/Album/01 A Song.mp3", "wb").write(b"x" * 64)
open(f"{H}/pi/Documents/Shopping.txt", "w").write("eggs\nmilk\n")
os.environ["HOME"] = H + "/pi"
socket.gethostname = lambda: "gpi"
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, ROOT)
sys.path.insert(0, TESTS)
sys.path.append(ROOT + "/pitato")   # (webui.py is in the pitato folder)
import webui
import pietato_all as g
from werkzeug.serving import make_server
import logging; logging.getLogger("werkzeug").setLevel(logging.ERROR)
webui.HOME, webui.STATIC, webui.KNOWS = H + "/pi", H + "/pi/gpi-media/static", True
os.makedirs(webui.STATIC)
g.STATE_FILE = H + "/state.json"; g.PLEX_FILE = H + "/plex.json"; g.CACHE_DIR = H + "/cache"
g.PROMPT_ACK, g.PROMPT_KEEP, g.PROMPT_LISTEN, g.PROMPT_WAIT = 1.5, 6.0, 3.0, 2.0   # (quicker)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


def until(cond, secs=8.0):
    end = time.time() + secs
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return bool(cond())


class FB:
    w, h, same = 640, 480, True
    last, frames = None, 0
    def show(self, img): self.last = img; self.frames += 1
    def show_part(self, img, box): self.last = img; self.frames += 1
    def close(self): pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.status_sig = m.status_signature()
aloud, stopped = [], []
m.say_aloud = lambda text=None: (aloud.append(text), setattr(m.voice, "speaking", True), (True, ""))[2]
m.voice.stop = lambda *a, **k: (stopped.append(1), setattr(m.voice, "speaking", False))
may_see = m.web_may_see
m.web_may_see = lambda path: path.startswith(H + "/pi/") or may_see(path)   # (the Pi's home folder, here)
played = []
m.play = lambda items, i=0, **k: played.append(items[i])   # (nothing's really played)
m.web_radio = lambda genre=None, query=None: {"stations": [
    ["Jazz One", "Jazz, 128k", "http://radio.example/one", "uuid-1", ""],
    ["Jazz Two", "", "http://radio.example/two", "uuid-2", ""]] if "jazz" in (query or "") else []}
control = g.Control()
cport, key = free_port(), "k3y"
g.serve_control(m, control, port=cport, key=key)
LOCK = threading.RLock()                                # (media mode does one thing at a time, as its loop does)


def pump():
    """The web page's requests, answered as media mode's loop answers them (pitato/app.py)."""
    while True:
        for job in control.take():
            out = {"error": "Something went wrong on the Pi"}
            try:
                cmd = job["cmd"]
                with LOCK:
                    m.web_guard = True
                    if cmd.get("cmd") == "press":
                        out = {"ok": True} if cmd.get("button") in g.BUTTONS else {"error": "No such button"}
                        if "ok" in out:
                            m.press(cmd["button"])
                    elif cmd.get("cmd") == "type":
                        out = m.web_type(cmd.get("text"), cmd.get("enter") is True)
                    else:
                        out = m.web_command(cmd)
                    m.dirty = True
                    m.flush()
            finally:
                control.done(job, out)
        time.sleep(0.01)


threading.Thread(target=pump, daemon=True).start()
with open(H + "/control-key", "w") as f:
    f.write(key)
webui.CONTROL, webui.CONTROL_KEY = ("127.0.0.1", cport), H + "/control-key"
wport = free_port()
httpd = make_server("127.0.0.1", wport, webui.app, threaded=True)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
PI = f"127.0.0.1:{wport}"
LAPTOP, BARE, BOTH = H + "/laptop", H + "/bare", H + "/both"
BASE = {k: v for k, v in os.environ.items()
        if not k.startswith(("OPENCLAW", "API_SERVER", "HERMES", "PITATO")) and k.lower() not in ("http_proxy", "https_proxy")}
BASE["PATH"] = os.pathsep.join(p for p in BASE.get("PATH", "").split(os.pathsep)
                               if not os.path.exists(os.path.join(p, "openclaw")))   # (no real OpenClaw's command)


def run(home, *args, script=None, secs=30):
    """agent_link.py, as on the agent's computer (its home folder): (how it ended, what it said)."""
    r = subprocess.run([sys.executable, script or f"{home}/.pietato/agent_link.py", *args], capture_output=True, text=True,
                       env=dict(BASE, HOME=home), cwd=home, timeout=secs)
    return r.returncode, (r.stdout + r.stderr).strip()


def tick():
    with LOCK:
        m.dirty = True
        m.flush()


# ---- the Pi hands the script out, and it's set up ---------------------------------------------------------------------
import urllib.request
got = urllib.request.urlopen(f"http://{PI}/agent_link.py", timeout=10)
body = got.read()
open(LAPTOP + "/agent_link.py", "wb").write(body)
check(f"the Pi hands the script out ({len(body)} bytes, {got.headers.get('Content-Disposition')})",
      body == open(ROOT + "/pitato/agent_link.py", "rb").read() and "agent_link.py" in got.headers.get("Content-Disposition", ""))
code, said = run(LAPTOP, script=LAPTOP + "/agent_link.py")
check(f"run with nothing: it says what it takes ({said.splitlines()[-1]!r})", code == 1 and "name or address" in said)
code, said = run(LAPTOP, "127.0.0.1:9", script=LAPTOP + "/agent_link.py")
check(f"a Pi that isn't there: said, and nothing's changed ({said.splitlines()[0][:60]!r})", code == 1
      and "isn't answering" in said and "Nothing was changed" in said and not os.path.exists(LAPTOP + "/.pietato"))
os.makedirs(LAPTOP + "/.hermes")
code, said = run(LAPTOP, PI, script=LAPTOP + "/agent_link.py")
link = json.load(open(LAPTOP + "/.pietato/link.json"))
skill_h = LAPTOP + "/.hermes/skills/pietato/SKILL.md"
check(f"set up, on a computer with Hermes: the Pietato's remembered by its own name, in a file that's yours only "
      f"({link}, {oct(stat.S_IMODE(os.stat(LAPTOP + '/.pietato/link.json').st_mode))})", code == 0
      and link == {"pietatos": {"gpi": {"url": f"http://{PI}", "password": ""}}, "first": "gpi"}
      and stat.S_IMODE(os.stat(LAPTOP + "/.pietato/link.json").st_mode) == 0o600 and "gpi is set up" in said)
check("...a copy of the script is kept, the skill is written for Hermes (which lists its skills as it starts: "
      "it says to restart it), and it says what to do next",
      open(LAPTOP + "/.pietato/agent_link.py", "rb").read() == body and os.path.isfile(skill_h)
      and f"Hermes has the skill: {LAPTOP}/.hermes/skills/pietato" in said and "listen" in said.splitlines()[-1]
      and "restart it" in said and not os.path.exists(LAPTOP + "/.openclaw"))
text = open(skill_h).read()
head = text.split("---")[1].strip().splitlines()
kept_cmd = f"{sys.executable} {LAPTOP}/.pietato/agent_link.py"
says = head[1].split(": ", 1)[1]
check(f"the skill: a name, what it's for on one line (no colon in it, and what matters in the 57 characters Hermes "
      f"lists: {says[:57]!r}), and each command spelt out with where the script is kept ({head[0]!r}, {len(head)} "
      f"lines of heading)", head[0] == "name: pietato" and head[1].startswith("description: Play music, videos and radio")
      and ":" not in says and " #" not in says and "Pietato" in says[:57]
      and len(head) == 4 and all(f"    {kept_cmd} {c} " in text for c in
                                 ("status", "screen", "press", "open", "home", "files", "play", "radio", "player",
                                  "type", "pose")) and "Don't press home" in text and "--on NAME" not in text)
check("...the Bot waves, if it's at work", until(lambda: m.coder.current() == "hello" or m.coder.heard, 3))

# ---- what the skill runs ------------------------------------------------------------------------------------------------
tick()
code, said = run(LAPTOP, "status")
check(f"status: where it is, that nothing's playing, the volume ({said!r})", code == 0
      and said.splitlines() == ["gpi is showing: Home", "Nothing is playing.", f"Volume: {m.volume}"])
code, said = run(LAPTOP, "open", "music")
check(f"open, by a name near enough: that app's on the screen ({said!r}, {m.where_text()!r})", code == 0
      and said == "gpi is showing Music." and m.where_text() == "Music")
code, said = run(LAPTOP, "open", "Nothing Like It")
check(f"...one there isn't: it says which there are ({said[:70]!r})", code == 1 and "There's no app called" in said
      and "Music" in said and "Bot" in said)
code, said = run(LAPTOP, "files", "music")
code2, said2 = run(LAPTOP, "files", "music", "Album")
check(f"files: a folder, and one in it ({said.splitlines()}, {said2.splitlines()})", code == 0 and code2 == 0
      and said.splitlines() == ["gpi, music: 1 there", "  [folder] Album"]
      and said2.splitlines() == ["gpi, music/Album: 1 there", "  01 A Song.mp3"])
code, said = run(LAPTOP, "files", "settings")
check(f"...only your media folders, not the Pi's settings and their keys ({said[:60]!r})", code == 1
      and "takes a folder first" in said)
code, said = run(LAPTOP, "play", "documents", "Shopping.txt")
check(f"play: a file of yours, opened on its screen ({said!r}, the screen: {m.view})", code == 0
      and "Shopping.txt" in said and m.view == "text")
code, said = run(LAPTOP, "play", "documents", "Nothing.txt")
check(f"...one that isn't there: said ({said!r})", code == 1 and "isn't there" in said and "<" not in said)
code, said = run(LAPTOP, "radio", "jazz")
code2, said2 = run(LAPTOP, "radio", "jazz", "--play", "2")
code3, said3 = run(LAPTOP, "radio", "polka")
check(f"radio: stations found by name, and one of them played ({said.splitlines()[:2]}, {said2!r}; none: {said3!r})",
      code == 0 and [x.strip() for x in said.splitlines()[:2]] == ["1. Jazz One (Jazz, 128k)", "2. Jazz Two"] and code2 == 0
      and said2 == "gpi is playing Jazz Two." and [p["src"] for p in played] == ["http://radio.example/two"]
      and played[0]["kind"] == "radio" and code3 == 0 and "No station found" in said3)
code, said = run(LAPTOP, "home")
check(f"home: its home screen ({said!r}, {m.view})", code == 0 and m.view == "home")
sel = m.home_sel
code, said = run(LAPTOP, "press", "right", "right", "left")
check(f"press: buttons, in order ({said!r}: the home screen's pick went {sel} to {m.home_sel})", code == 0
      and said == "Pressed right right left on gpi." and m.home_sel == sel + 1)
code, said = run(LAPTOP, "press", "a", "turbo")
check(f"...a button there isn't: nothing pressed ({said[:40]!r})", code == 1 and "press takes buttons" in said
      and m.view == "home")
vol = m.volume
code, said = run(LAPTOP, "player", "quieter")
code2, said2 = run(LAPTOP, "player", "pause")
check(f"player: quieter ({said!r}); pause with nothing playing: said ({said2!r})", code == 0 and m.volume < vol
      and said == f"gpi: volume {m.volume}." and code2 == 1 and "Nothing is playing" in said2)
code, said = run(LAPTOP, "pose", "reading")
check(f"pose: what the Bot acts out ({said!r}, {m.coder.current()})", code == 0 and until(lambda: m.coder.current() == "reading", 3))
code, said = run(LAPTOP, "screen")
shot = LAPTOP + "/.pietato/screen-gpi.png"
code2, said2 = run(LAPTOP, "screen", H + "/laptop/pics/now.png")
check(f"screen: its picture saved where the script keeps things, or where it's told ({said!r})", code == 0 and code2 == 0
      and open(shot, "rb").read(8) == b"\x89PNG\r\n\x1a\n" and said == f"gpi's screen is saved as {shot}"
      and os.path.getsize(H + "/laptop/pics/now.png") > 1000)
code, said = run(LAPTOP, "type", "hello")
check(f"type with no box open on the screen: said ({said!r})", code == 1 and "no box to type in" in said)
code, said = run(LAPTOP, "dance", "now")
code2, said2 = run(LAPTOP, "--help")
check(f"a command there isn't: said, with those there are ({said[:40]!r}); --help has the rest", code == 1
      and said.startswith("dance isn't a command. There's: listen, status") and code2 == 0 and "agent_link.py listen" in said2
      and "API_SERVER_KEY" in said2)

# ---- the Bot at work: its card on connecting an agent has one for these two ------------------------------------------
with LOCK:
    m.web_guard = False
    m.set_setting("bot_mode", "work")
    m.view = "home"
    m.home_sel = [a for a, _ in m.home_apps()].index("Bot")
    m.press("a")
    on_page = m.on_coder_page()
    m.press("start")
    h1 = m.coder_hints(m.coder.snapshot(time.monotonic()))
    m.dirty = True; m.flush(); one = m.fb.last.convert("RGB").tobytes()
    m.press("right")
    h2 = m.coder_hints(m.coder.snapshot(time.monotonic()))
    m.dirty = True; m.flush(); two = m.fb.last.convert("RGB").tobytes()
    page = m.coder_help_page
    m.press("left")
    back = m.coder_help_page
    m.press("b")
check(f"the Bot at work; START's card on connecting Claude Code has another, for OpenClaw and Hermes (left and right: "
      f"{h1[0]}, {h2[0]})", on_page and h1[0] == ("◀▶", "OpenClaw, Hermes") and h2[0] == ("◀▶", "Claude Code")
      and page == 1 and back == 0 and one != two and not m.coder_help and m.on_coder_page())

# ---- pretend agents, speaking as the real ones do ------------------------------------------------------------------------
HKEY, OKEY = "hermes-key-0123456789abcdef", "openclaw-token-0123456789"
ANSWER = {"text": "**Done.** I looked in `notes.txt`:\n\n- eggs\n- milk\n\n## Next\nNothing else to do."}
seen = {"hermes": [], "openclaw": [], "other": []}
mode = {"hermes": "ok", "openclaw": "ok"}


class Agent(BaseHTTPRequestHandler):
    """An agent's chat API. which: whose ways it has (hermes: X-Hermes-Session-Id and its tool events; openclaw:
    the "user" it's given, openclaw/default; other: nothing kept, an answer all at once)."""
    which, keyed = "other", ""
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def send(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def allowed(self):
        if self.keyed and self.headers.get("Authorization") != "Bearer " + self.keyed:
            self.send({"error": {"message": "Invalid API key", "type": "invalid_request_error"}}, 401)
            return False
        return True

    def do_GET(self):
        if not self.allowed():
            return
        model = {"hermes": "hermes-agent", "openclaw": "openclaw/default"}.get(self.which, "some-model")
        self.send({"object": "list", "data": [{"id": model, "object": "model"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if not self.allowed():
            return
        seen[self.which].append({"path": self.path, "body": body, "session": self.headers.get("X-Hermes-Session-Id"),
                                 "accept": self.headers.get("Accept")})
        how = mode.get(self.which, "ok")
        if how == "off":                                  # (OpenClaw with its chat API not turned on)
            return self.send({"error": {"message": "Not Found"}}, 404)
        if how == "fails":
            return self.send({"error": {"message": "The model isn't answering", "type": "server_error"}}, 500)
        said = body["messages"][-1]["content"]
        text = ANSWER["text"] if "notes" in said else f"You said: {said} ({len(body['messages'])} in all)"
        if self.which == "other":
            return self.send({"choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                                           "finish_reason": "stop"}]})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def chunk(line):
            data = (line + "\n\n").encode()
            self.wfile.write(b"%x\r\n%s\r\n" % (len(data), data))
            self.wfile.flush()

        def piece(delta, finish=None):
            chunk("data: " + json.dumps({"object": "chat.completion.chunk",
                                         "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}))
        piece({"role": "assistant"})
        if self.which == "hermes" and "notes" in said:    # (it reads a file first, and says so, as Hermes does)
            chunk("event: hermes.tool.progress\ndata: " + json.dumps(
                {"tool": "read_file", "label": "read_file: notes.txt", "toolCallId": "c1", "status": "running"}))
            time.sleep(0.6)
            chunk(": keepalive")
            chunk("event: hermes.tool.progress\ndata: " + json.dumps(
                {"tool": "read_file", "toolCallId": "c1", "status": "completed"}))
        for word in text.split(" "):
            piece({"content": word + " "})
        if how == "slow":
            time.sleep(1.2)
        piece({}, "stop")
        chunk("data: [DONE]")
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()


def serve(which, keyed):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), type("A", (Agent,), {"which": which, "keyed": keyed}))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[1]


hport, oport, xport = serve("hermes", HKEY), serve("openclaw", OKEY), serve("other", "")


class Listener:
    """agent_link.py listen, running on the agent's computer."""

    def __init__(self, home, *args, env=None):
        self.p = subprocess.Popen([sys.executable, "-u", f"{home}/.pietato/agent_link.py", "listen", *args],
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                  env=dict(BASE, HOME=home, **(env or {})), cwd=home)
        self.lines = []
        threading.Thread(target=lambda: self.lines.extend(iter(self.p.stdout.readline, "")), daemon=True).start()

    def said(self, words):
        return any(words in line for line in self.lines)

    def stop(self):
        self.p.terminate()
        try:
            self.p.wait(5)
        except subprocess.TimeoutExpired:
            self.p.kill()


def quiet():
    """Nobody listening any more (a request from a listener that's gone has had its wait)."""
    return until(lambda: not m.prompts.listening(), g.PROMPT_WAIT + g.PROMPT_LISTEN + 4)


def type_prompt(text, web=False):
    """A on the Bot at work, the prompt typed (on a keyboard), START."""
    with LOCK:
        m.web_guard = web
        m.press("a")
        if m.view != "keys":
            return False
        for ch in text:
            m.keyboard_key("char", ch)
        m.web_guard = web
        m.press("start")
    return True


def answered(n, secs=12):
    return until(lambda: m.coder_reply is not None and m.coder_reply["n"] >= n, secs)


# ---- listening: nothing to hand prompts to ---------------------------------------------------------------------------
code, said = run(BARE, "listen", script=LAPTOP + "/agent_link.py")
check(f"listen with no Pietato set up: said ({said[:40]!r})", code == 1 and "No Pietato is set up" in said)
open(LAPTOP + "/.hermes/.env", "w").write("API_SERVER_PORT=9\n")   # (nothing answers there)
code, said = run(LAPTOP, "listen")
check(f"listen, Hermes's API not on: how to turn it on, and that its key wants 16 characters ({said[:50]!r})", code == 1
      and "API_SERVER_ENABLED=true" in said and "16 characters or more" in said and "hermes gateway" in said)
open(LAPTOP + "/.hermes/.env", "w").write(f"# keys\nAPI_SERVER_ENABLED=true\nAPI_SERVER_KEY='wrong-key-0123456789'\nAPI_SERVER_PORT={hport}\n")
code, said = run(LAPTOP, "listen")
check(f"...a key that isn't its key: said ({said!r})", code == 1 and "said no (401)" in said and "--key" in said)

# ---- listening: Hermes -----------------------------------------------------------------------------------------------------
open(LAPTOP + "/.hermes/.env", "w").write(f"API_SERVER_ENABLED=true\nexport API_SERVER_KEY={HKEY}\nAPI_SERVER_PORT={hport}\n")
poses = []
was_ask = m.coder.ask
m.coder.ask = lambda name, **k: (poses.append(name), was_ask(name, **k))[1]
L = Listener(LAPTOP)
check(f"listen, Hermes's API on (its key and port from ~/.hermes/.env): it asks the Pi for prompts ({L.lines[:1]})",
      until(m.prompts.listening, 8) and until(lambda: L.said(f"go to Hermes at http://127.0.0.1:{hport}"), 3))
del poses[:]
m.msg = None
typed = type_prompt("what is in my notes file")
check("a prompt typed on the Bot at work: Hermes gets it, with its key, in a conversation of this Pietato's",
      typed and until(lambda: len(seen["hermes"]) == 1, 6) and seen["hermes"][0]["path"] == "/v1/chat/completions"
      and seen["hermes"][0]["session"] == "pietato-gpi" and seen["hermes"][0]["body"]["model"] == "hermes-agent"
      and seen["hermes"][0]["body"]["messages"] == [{"role": "user", "content": "what is in my notes file"}]
      and seen["hermes"][0]["body"]["stream"] is True)
check(f"...what it answers shows on a card over its desk: whose it is, its markdown taken out "
      f"({m.coder_reply and m.coder_reply['text']!r})", answered(1) and m.coder_reply["agent"] == "Hermes"
      and m.coder_reply["text"] == "Done. I looked in notes.txt:\n\n- eggs\n- milk\n\nNext\nNothing else to do."
      and m.coder_reply["open"] and not m.coder_reply["failed"])
check(f"...the Bot acted it out on the way: thinking, reading as Hermes read a file, typing its answer, done ({poses})",
      until(lambda: poses[-1:] == ["done"], 3) and [p for k, p in enumerate(poses) if k == 0 or p != poses[k - 1]]
      == ["thinking", "reading", "typing", "done"])
tick()
hints = m.coder_hints(m.coder.snapshot(time.monotonic()))
box = m.fb.last.convert("RGB").crop((30, 300, 610, 420)).getcolors(100000)
check(f"...its buttons: {hints}; a short answer's card leaves the Bot in sight", hints == [("A", "Prompt"), ("X", "Read it"), ("B", "Close")]
      and not m.coder_reply["covers"] and max(n for n, _ in box) > 20000)
with LOCK:
    m.press("x")
    reading = m.coder_hints(m.coder.snapshot(time.monotonic()))[1]
    m.press("x")
    vol = m.volume
    m.press("down")
    quieter = m.volume
    m.press("up")
check(f"X: read out loud in your Bot's voice; X again stops ({aloud}, {reading}, {stopped}); up and down are the "
      f"volume's as ever, over a card with nothing more to go through ({vol}, {quieter}, {m.volume})",
      aloud == [m.coder_reply["text"]] and reading == ("X", "Stop") and stopped == [1] and not m.coder_reply_aloud
      and quieter < vol == m.volume and m.coder_reply["open"])
with LOCK:
    m.press("b")
    closed = not m.coder_reply["open"] and m.on_coder_page()
    last = m.coder_hints(m.coder.snapshot(time.monotonic()))[-1]
    m.press("select")
check(f"B closes the card (the Bot at work is still there), and SELECT shows it again ({last})", closed
      and last == ("SELECT", "Answer") and m.coder_reply["open"])
typed = type_prompt("and again")
check("the next prompt: the card for the one before closes as it's sent; the same conversation, kept by Hermes "
      "(only the new words are sent)", typed and not (m.coder_reply["open"] and m.coder_reply["n"] == 1) and answered(2)
      and seen["hermes"][1]["session"] == "pietato-gpi" and len(seen["hermes"][1]["body"]["messages"]) == 1
      and m.coder_reply["text"] == "You said: and again (1 in all)")

# a long answer
ANSWER["text"] = "Here is all of it.\n\n" + " ".join(f"Line {k} of the long answer it gave, word after word." for k in range(60))
typed = type_prompt("read my notes out, all of them")
check("a long answer: its card is over the whole page (nothing moves under it), with where you are in it",
      typed and answered(3) and (tick() or True) and m.coder_reply["covers"] and m.coder_reply["most"] > 0
      and m.coder_hints(m.coder.snapshot(time.monotonic()))[0] == ("▲▼", "More"))
with LOCK:
    vol = m.volume
    top0 = m.coder_reply["top"]
    m.press("down"); m.press("down")
    top2 = m.coder_reply["top"]
    for _ in range(80):
        m.press("down", repeat=True)
    end = m.coder_reply["top"]
    m.press("up")
    up = m.coder_reply["top"]
    m.coder_next = 0.0
    m.tick()
    still = m.coder_next == 0.0                         # (no frame of the Bot's is due: it's under the card)
check(f"...up and down go through it, to its end and no further (from line {top0}: {top2}, {end}, {up}); the volume's as "
      f"it was", top0 == 0 and top2 == 2 * g.REPLY_STEP and end == m.coder_reply["most"] and up == end - g.REPLY_STEP
      and m.volume == vol and still)
check(f"...no more of it than the Pi keeps ({len(m.coder_reply['text'])} characters)",
      20 < len(m.coder_reply["text"]) <= g.REPLY_MAX)

# elsewhere in media mode
with LOCK:
    m.press("b")
    m.go_home()
    m.msg = None
typed_at = len(seen["hermes"])
with LOCK:
    m.prompts.put("one from before, sent as you left")
check(f"its answer while you're elsewhere: a word that it's on the Bot at work ({m.msg!r})", answered(4)
      and until(lambda: m.msg == "Your agent has answered: it's on the Bot at work", 3) and len(seen["hermes"]) == typed_at + 1)

# an agent that can't answer, and one that stops answering
with LOCK:
    m.web_tab("Bot")
mode["hermes"] = "fails"
del poses[:]
typed = type_prompt("this one fails")
check(f"an agent that can't answer: the card says so, the Bot shows something went wrong, and it goes on listening "
      f"({m.coder_reply and m.coder_reply['text']!r})", typed and answered(5) and m.coder_reply["failed"]
      and "The model isn't answering" in m.coder_reply["text"] and until(lambda: poses[-1:] == ["error"], 3)
      and until(m.prompts.listening, 4))
tick()
mode["hermes"] = "ok"
typed = type_prompt("and this one works")
check("...and the next one is answered", typed and answered(6) and not m.coder_reply["failed"]
      and m.coder_reply["text"].startswith("You said: and this one works"))

# the web page's remote, and the skill, can't send a prompt
with LOCK:
    m.web_guard = False
    m.press("a")
    box_open = m.view == "keys"
before = len(seen["hermes"])
code, said = run(LAPTOP, "type", "delete everything", "--enter")
check(f"a prompt typed through the skill (type, into the prompt's box): not sent, as the web page's remote's isn't "
      f"({m.msg!r})", box_open and code == 0 and "not with the web page's remote" in (m.msg or "")
      and not m.prompts.queue and len(seen["hermes"]) == before)
L.stop()
check(f"what it printed on the computer: each prompt, and its answer ({len(L.lines)} lines)",
      L.said("> what is in my notes file") and L.said("- eggs") and L.said("> this one fails"))
check("the listener gone: nobody's listening, and A says so", quiet() and not m.prompts.listening())

# ---- listening: OpenClaw ------------------------------------------------------------------------------------------------
os.makedirs(BOTH + "/.openclaw"); os.makedirs(BOTH + "/.hermes")
json.dump({"gateway": {"port": oport, "auth": {"mode": "token", "token": OKEY},
                       "http": {"endpoints": {"chatCompletions": {"enabled": True}}}}},
          open(BOTH + "/.openclaw/openclaw.json", "w"))
code, said = run(BOTH, PI, "--name", "living room", "--skills", BOTH + "/my skills", script=LAPTOP + "/agent_link.py")
code2, said2 = run(BOTH, PI, "--name", "Kitchen", script=LAPTOP + "/agent_link.py")
link = json.load(open(BOTH + "/.pietato/link.json"))
check(f"set up on a computer with both agents, under a name of your choosing, a folder of your own for the skill too: "
      f"each has it ({sorted(link['pietatos'])})", code == 0 and code2 == 0
      and all(os.path.isfile(f"{BOTH}/{d}/pietato/SKILL.md") for d in (".openclaw/skills", ".hermes/skills", "my skills"))
      and "OpenClaw has the skill" in said and "Hermes has the skill" in said and "your folder has the skill" in said)
check("...set up again under another name: the same Pietato, called that now",
      link == {"pietatos": {"Kitchen": {"url": f"http://{PI}", "password": ""}}, "first": "Kitchen"})
open(BOTH + "/.pietato/link.json", "w").write(json.dumps(
    {"pietatos": {"Kitchen": {"url": f"http://{PI}", "password": ""}, "Den": {"url": "http://127.0.0.1:9", "password": ""}},
     "first": "Kitchen"}))
code, said = run(BOTH, "list")
code2, said2 = run(BOTH, "status", "--on", "den")
code3, said3 = run(BOTH, "status", "--on", "Attic")
check(f"with several: list has them, --on picks one (one that's off: said; one there isn't: which there are) "
      f"({said.splitlines()})", code == 0 and said.splitlines()[0].startswith("Den  http://127.0.0.1:9")
      and "(the one used when you don't say)" in said.splitlines()[1] and code2 == 1 and "isn't answering" in said2
      and code3 == 1 and "There's: Kitchen, Den" in said3)
L = Listener(BOTH, "--agent", "openclaw", "--on", "Den")
check("listen, to a Pietato that's off: it says so, and keeps trying", until(lambda: L.said("isn't answering"), 10)
      and L.p.poll() is None)
L.stop()
mode["openclaw"] = "off"
L = Listener(BOTH, "--agent", "openclaw")
check(f"listen --agent openclaw (its token and port from ~/.openclaw/openclaw.json): prompts go to OpenClaw ({L.lines[:1]})",
      until(m.prompts.listening, 8) and until(lambda: L.said(f"go to OpenClaw at http://127.0.0.1:{oport}"), 3))
with LOCK:
    m.web_tab("Bot")
    m.press("b") if m.view == "keys" else None
typed = type_prompt("hello openclaw")
n = m.coder_reply["n"]
check(f"OpenClaw with its chat API not turned on: the card says how to turn it on ({m.coder_reply['text'][:60]!r})",
      typed and answered(n) and until(lambda: m.coder_reply["failed"] and "chatCompletions.enabled" in m.coder_reply["text"], 8))
mode["openclaw"] = "ok"
n = m.coder_reply["n"]
typed = type_prompt("hello again")
check("...turned on: it gets the prompt with its token, as openclaw/default, in a conversation it keeps by the name "
      "it's given", typed and answered(n + 1) and seen["openclaw"][-1]["body"]["model"] == "openclaw/default"
      and seen["openclaw"][-1]["body"]["user"] == "pietato-Kitchen" and seen["openclaw"][-1]["session"] is None
      and len(seen["openclaw"][-1]["body"]["messages"]) == 1 and m.coder_reply["agent"] == "OpenClaw"
      and m.coder_reply["text"] == "You said: hello again (1 in all)")
L.stop()
quiet()

# OpenClaw's settings file with comments in it (it allows them): its own command is asked instead, which won't show keys
JS5 = H + "/commented"
os.makedirs(JS5 + "/.openclaw"); os.makedirs(JS5 + "/bin")
shutil.copytree(BOTH + "/.pietato", JS5 + "/.pietato")
with open(JS5 + "/.openclaw/openclaw.json", "w") as f:
    f.write('// my gateway\n{gateway: {port: %d, auth: {token: "%s"}}}\n' % (oport, OKEY))
with open(JS5 + "/bin/openclaw", "w") as f:
    f.write('#!/bin/sh\n[ "$3" = gateway.port ] && echo %d && exit 0\n'
            '[ "$3" = gateway.auth.token ] && echo __OPENCLAW_REDACTED__ && exit 0\nexit 1\n' % oport)
os.chmod(JS5 + "/bin/openclaw", 0o755)
with_cmd = {"PATH": JS5 + "/bin" + os.pathsep + BASE["PATH"]}
r = subprocess.run([sys.executable, JS5 + "/.pietato/agent_link.py", "listen"], capture_output=True, text=True,
                   env=dict(BASE, HOME=JS5, **with_cmd), cwd=JS5, timeout=60)
said = (r.stdout + r.stderr).strip()
L = Listener(JS5, "--key", OKEY, env=with_cmd)
check(f"OpenClaw's settings file with comments in it: its port comes from its own command, which doesn't show its "
      f"token ({said!r}); given with --key, it listens", r.returncode == 1
      and f"OpenClaw's API at http://127.0.0.1:{oport} said no (401)" in said and "--key" in said
      and until(lambda: L.said(f"go to OpenClaw at http://127.0.0.1:{oport}"), 8))
L.stop()
quiet()

# ---- another API, by --url: it's sent the turns each time ---------------------------------------------------------------
L = Listener(BOTH, "--url", f"http://127.0.0.1:{xport}/v1", "--model", "some-model")
until(m.prompts.listening, 8)
n = m.coder_reply["n"]
type_prompt("first")
ok1 = answered(n + 1)
type_prompt("second")
ok2 = answered(n + 2)
check(f"another agent's API, by --url (an answer all at once, no conversation kept): it's sent the turns so far each "
      f"time ({m.coder_reply['text']!r})", ok1 and ok2 and m.coder_reply["text"] == "You said: second (3 in all)"
      and [x["role"] for x in seen["other"][-1]["body"]["messages"]] == ["user", "assistant", "user"]
      and m.coder_reply["agent"] == "" and seen["other"][-1]["body"]["model"] == "some-model")
tick()
with LOCK:
    title_ok = m.coder_reply_shown() is not None
L.stop()
quiet()
check("...and its card says Your agent", title_ok)

# ---- what the web page takes for an answer -------------------------------------------------------------------------------
def post(path, data, headers=None):
    req = urllib.request.Request(f"http://{PI}{path}", data=data, method="POST",
                                 headers=dict({"Content-Type": "application/json"}, **(headers or {})))
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as ex:
        try:
            return ex.code, json.loads(ex.read() or b"{}")
        except ValueError:
            return ex.code, {}


n = m.coder_reply["n"]
r1 = post("/coder/reply", b"not json")
r2 = post("/coder/reply", json.dumps({"text": "   "}).encode())
r3 = post("/coder/reply", json.dumps({"text": 7}).encode())
r4 = post("/coder/reply", json.dumps({"text": "x" * 70000}).encode())
r5 = post("/coder/reply", json.dumps({"text": "a\x00b\tc\r\n\n\n\nd", "agent": "Some\nAgent " + "x" * 40, "failed": "yes"}).encode())
check(f"POST /coder/reply: JSON with its words ({r1[0]}, {r2}, {r3[0]}, too big: {r4[0]}); odd characters and a long "
      f"name tidied ({m.coder_reply['text']!r}, {m.coder_reply['agent']!r})", r1[0] == 400 and r2[1].get("ok") is False
      and r3[1].get("ok") is False and r4[0] == 413 and r5 == (200, {"ok": True}) and m.coder_reply["n"] == n + 1
      and m.coder_reply["text"] == "a b c\n\nd" and len(m.coder_reply["agent"]) <= g.REPLY_AGENT_MAX
      and "\n" not in m.coder_reply["agent"] and m.coder_reply["failed"] is False)

# ---- a web page with a password ----------------------------------------------------------------------------------------
with open(webui.STATIC + "/webui.txt", "w") as f:
    f.write("password = s3cret\n")
webui.settings.cache_clear() if hasattr(webui.settings, "cache_clear") else None
locked = until(lambda: post("/coder/reply", json.dumps({"text": "hi"}).encode())[0] == 401, 5)
got = urllib.request.urlopen(f"http://{PI}/agent_link.py", timeout=10).status
r = post("/coder/reply", json.dumps({"text": "with the password"}).encode(), {"Authorization": "Bearer s3cret"})
check(f"a web page with a password: an answer needs it, as a token ({r}); the script is still handed out ({got})",
      locked and r == (200, {"ok": True}) and got == 200 and m.coder_reply["text"] == "with the password")
code, said = run(LAPTOP, "status")
code2, said2 = run(LAPTOP, PI, "--password", "wrong", script=LAPTOP + "/agent_link.py")
code3, said3 = run(LAPTOP, PI, "--password", "s3cret", script=LAPTOP + "/agent_link.py")
code4, said4 = run(LAPTOP, "status")
code5, said5 = run(LAPTOP, "pose", "thinking")
check(f"...the skill without it: said ({said!r}); set up with a wrong one: nothing changed; with the right one: "
      f"it works again, the Bot's poses too (Hermes has the skill listed already: no word of restarting it)",
      code == 1 and "--password" in said and code2 == 1 and "Nothing was changed" in said2
      and code3 == 0 and "Hermes has the skill" in said3 and "restart it" not in said3
      and code4 == 0 and said4.startswith("gpi is showing") and code5 == 0
      and json.load(open(LAPTOP + "/.pietato/link.json"))["pietatos"]["gpi"]["password"] == "s3cret")
L = Listener(LAPTOP, "--new")
n = m.coder_reply["n"]
with LOCK:
    m.web_tab("Bot")
ok = until(m.prompts.listening, 8) and type_prompt("with a password on the page")
check("...and listening: prompts and answers go both ways with it", ok and answered(n + 1)
      and m.coder_reply["text"].startswith("You said: with a password on the page"))
L.stop()
nxt = subprocess.run([sys.executable, "-c", "import agent_link as a; print(a.thread_of(a.load(), 'gpi'))"],
                     capture_output=True, text=True, env=dict(BASE, HOME=LAPTOP), cwd=LAPTOP + "/.pietato").stdout.strip()
check(f"listen --new: a new conversation for your agent ({seen['hermes'][-1]['session']}), said on the computer; "
      f"listening after that carries it on ({nxt})", seen["hermes"][-1]["session"] == "pietato-gpi-1"
      and L.said("This is a new conversation") and nxt == "pietato-gpi-1")

# ---- taking it out again ---------------------------------------------------------------------------------------------
code, said = run(BOTH, "--remove", "--skills", BOTH + "/my skills")
check(f"--remove: your Pietatos forgotten, the skill out of each agent's folder and yours ({said.splitlines()})", code == 0
      and not os.path.exists(BOTH + "/.pietato") and not any(os.path.exists(f"{BOTH}/{d}/pietato") for d in
                                                              (".openclaw/skills", ".hermes/skills", "my skills"))
      and os.path.isdir(BOTH + "/.openclaw/skills") and os.path.isfile(BOTH + "/.openclaw/openclaw.json"))
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
