"""Your Pietatos' group chat (pitato/circle.py, screens/group.py, nearby.py's beacons, webui.py's /api/group): what
each is made of, sized up; three of them on a pretend clock, talking (remarks now and then, answers, not too many, not
at night), one going quiet (missed by one of them only, then you're asked whether it'll be back: No, a goodbye, and
it isn't listed; back, and it's welcomed), you saying something (answered), Quiet (on all of them; they still answer
you), where you are (a hello where you've come to), and one that was off catching up. Then media mode's part: the page,
its buttons, a line popping up where you are (not in a game), the beacon told straight to yours saying more than the
one to everyone, and a line from one that isn't yours turned away. Last, two real Pietatos (peer_pietato.py) saying
lines to each other through their web pages, and a third catching up."""
import importlib, io, json, os, random, shutil, subprocess, sys, time, urllib.error
from paths import SP, TESTS  # noqa: E402  (this test's folder of work; tests)
S = SP + "/tgroup"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME + "/Music")
sys.path.insert(0, TESTS)
import pietato_all as g

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"; g.ASSIST_FILE = S + "/assist.json"
g.GROUP_LOG = S + "/group.json"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
import gk_static; gk_static.use_home(g, HOME)
C = importlib.import_module("pitato.circle")
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


# ---- what each is made of ------------------------------------------------------------------------------------------
BOARDS = ("Raspberry Pi Zero 2 W Rev 1.0", "Raspberry Pi 4 Model B Rev 1.4", "Raspberry Pi 5 Model B Rev 1.0",
          "Raspberry Pi 3 Model B Plus Rev 1.3", "Raspberry Pi Compute Module 4 Rev 1.0", "Raspberry Pi 400 Rev 1.0")
check("a Pi's board, short", [C.board_short(b) for b in BOARDS]
      == ["Pi Zero 2 W", "Pi 4", "Pi 5", "Pi 3B+", "Pi CM4", "Pi 400"])
check("...sized up: a Pi 5 over a Pi 4 over a Zero 2 W over a Zero; a handheld a bit over a Zero 2 W; a PC by its "
      "cores",
      C.board_power("Raspberry Pi 5 Model B") > C.board_power("Raspberry Pi 4 Model B") >
      C.board_power("Raspberry Pi Zero 2 W") > C.board_power("Raspberry Pi Zero W") and
      C.board_power("R36S", "handheld") == 1.2 and C.board_power("", "pc", 8, 3.0) == 21.6)
hw = C.hardware("Raspberry Pi 4 Model B Rev 1.4", "pi", (1920, 1080), "")
check(f"this one's, for the others ({hw})", hw["b"] == "Pi 4" and hw["s"] == 3.0 and hw["x"] == "1920x1080"
      and hw["c"] >= 1 and "k" not in hw)
gpi = C.hardware("Raspberry Pi Zero 2 W Rev 1.0", "pi", (640, 480), "GPi Case 2W")
check(f"...in words ({C.hw_words(gpi)})", C.hw_words(gpi).startswith("a Pi Zero 2 W in a GPi Case 2W (")
      and "a 640x480 screen" in C.hw_words(gpi))
check("another's, kept to what's expected", C.hw_clean({"b": "Pi 5\x00\n", "c": 4, "r": True, "s": float("inf"),
                                                         "x": "1920x1080; rm", "k": 7, "zz": 1})
      == {"b": "Pi 5", "c": 4}
      and C.hw_clean("nonsense") == {})

# ---- a line of it -----------------------------------------------------------------------------------------------
GOOD = {"id": "0123456789abcdef", "t": time.time() - 5, "by": "aaaaaaaaaaaa", "name": "Kitchen", "who": "bot",
        "kind": "chat", "text": "Hello  there\n", "accent": "Gold", "topic": "weather", "to": "Den"}
got = C.clean_msg(GOOD)
check(f"a line from another of yours, kept as it should be ({got})", got and got["text"] == "Hello there"
      and got["accent"] == "Gold" and got["topic"] == "weather" and got["to"] == "Den")
check("...a bad one isn't: no id, a time to come, no words, an answer that isn't Yes or No",
      all(C.clean_msg(dict(GOOD, **bad)) is None for bad in ({"id": "zz"}, {"t": time.time() + 3600}, {"text": "  "},
                                                             {"t": True}, {"kind": "answer", "choice": "Maybe"}))
      and C.clean_msg(["no"]) is None)
check("...its kind, accent and topic only if they're ones there are", C.clean_msg(dict(GOOD, kind="hack", accent="Neon",
                                                                                      topic="rm"))
      == {k: v for k, v in dict(got, kind="chat").items() if k not in ("accent", "topic")})


# ---- three of them, on a pretend clock -----------------------------------------------------------------------------
class Clock:
    t = time.mktime((2026, 11, 8, 12, 0, 0, 0, 0, -1))

    def time(self):
        return self.t

    def localtime(self, t=None):
        return time.localtime(self.t if t is None else t)


clock = Clock()
real_time = C.time
C.time = clock
PIES = []


class Pie:
    def __init__(self, name, board, n):
        self.name, self.url, self.id = name, f"http://10.0.0.{n}:5432", f"{n:02d}" + "a" * 10
        self.hw = C.hardware(board, "pi", (640, 480))
        self.on, self.doing, self.you, self.talk = True, "on the home screen", None, True
        self.seen, self.models = {}, False
        PIES.append(self)
        self.start()

    def start(self):
        c = self.circle = C.Circle(path=f"{S}/sim_{self.name}.json", rng=random.Random(len(self.name) * 7))
        c.clear()
        c.started = clock.t
        c.own = lambda: {"id": self.id, "name": self.name, "accent": "", "hw": self.hw, "doing": self.doing,
                         "you": self.you}
        c.members = lambda: [{"url": q.url, "name": q.name, "id": q.id, "seen": self.seen[q.url], "accent": "",
                              "doing": q.doing if q.on else "", "hw": q.hw, "you": q.you if q.on else None}
                             for q in PIES if q is not self and q.url in self.seen]
        c.send = lambda url, msg: self.peer(url).circle.receive(msg)
        c.fetch = lambda url, since: self.peer(url).circle.since(since)
        c.spawn = lambda fn, name: fn()
        c.talk = lambda: self.talk
        c.set_talk = lambda on: setattr(self, "talk", on)
        c.extra = lambda: {"weather": "52°F and cloudy", "person": "Sam", "hey": "Ahoy!", "ok": ("Aye!",)}

    def peer(self, url):
        q = next(q for q in PIES if q.url == url)
        if not q.on:
            raise OSError("not answering")
        return q

    def lines(self, since=0, **match):
        return [m for m in self.circle.lines() if m["t"] >= since and all(m.get(k) == v for k, v in match.items())]


def run(secs, step=2):
    end = clock.t + secs
    while clock.t < end:
        clock.t += step
        for p in PIES:
            if not p.on:
                continue
            for q in PIES:
                if q is not p and q.on and int(clock.t) % 20 < step:
                    p.seen[q.url] = clock.t
            p.circle.tick()


den = Pie("Den", "Raspberry Pi Zero 2 W Rev 1.0", 11)
kitchen = Pie("Kitchen", "Raspberry Pi 4 Model B Rev 1.4", 12)
bedroom = Pie("Bedroom", "Raspberry Pi Zero 2 W Rev 1.0", 13)
run(600)
t0 = clock.t
run(4 * 3600)
said = den.lines(t0)
check(f"four hours together: they talk now and then ({len(said)} lines)", 6 <= len(said) <= 80)
check("...the same on each of them", [m["id"] for m in den.circle.lines()] == [m["id"] for m in kitchen.circle.lines()]
      == [m["id"] for m in bedroom.circle.lines()])
remarks = [m for m in said if m.get("topic")]
check(f"...remarks of their own about the weather, what another's doing, who's bigger "
      f"({sorted({m['topic'] for m in remarks})})",
      len(remarks) >= 3 and len({m["topic"] for m in remarks}) >= 2)
answers = [m for m in said if m.get("re")]
check(f"...and answers to them ({len(answers)}), at most two to a line, none answering itself",
      answers and all(sum(1 for x in said if x.get("re") == m["id"]) <= 2 for m in said)
      and all(m["name"] != den.circle.find(m["re"])["name"] for m in answers))
check("...no more than ten an hour from one", all(sum(1 for m in p.lines(t0) if clock.t - 3600 <= m["t"]) <= 10
                                                  for p in PIES))
check("...in words with nothing left out ({...} filled in)", all("{" not in m["text"] and m["text"] for m in said))
for m in said[:12]:
    print(f"       {m['name']}: {m['text']}")

# ---- one goes quiet -------------------------------------------------------------------------------------------
t0 = clock.t
kitchen.on = False
run(400)
quiet = den.lines(t0, kind="quiet")
asks = den.lines(t0, kind="ask")
lead = min(den.id, bedroom.id)
check(f"one goes quiet: the others wonder where it went, one of them only ({[m['text'] for m in quiet]})",
      len(quiet) == 1 and quiet[0]["about"] == "Kitchen" and quiet[0]["by"] == lead)
check(f"...then you're asked, by name, whether it'll be back ({[m['text'] for m in asks]})",
      len(asks) == 1 and asks[0]["text"] == "Will Kitchen come back?" and asks[0]["by"] == lead)
ask = bedroom.circle.open_ask()
check("...on each of them: the question you haven't answered", ask and den.circle.open_ask()["id"] == ask["id"])
t0 = clock.t
bedroom.circle.answer(ask, "No")
run(60)
bye = den.lines(t0, kind="bye")
check(f"No (on another): a goodbye, from the one you answered on ({[m['text'] for m in bye]})",
      len(bye) == 1 and bye[0]["name"] == "Bedroom" and den.lines(t0, kind="answer")[0]["choice"] == "No")
check("...not asked again, and it isn't listed", den.circle.open_ask() is None and bedroom.circle.open_ask() is None
      and [r["name"] for r in den.circle.roster()] == ["Den", "Bedroom"])
run(2 * 3600)
check("...nor missed again while it's gone", not den.lines(t0, kind="quiet") and not den.lines(t0, kind="ask"))
t0 = clock.t
kitchen.on = True
kitchen.start()
kitchen.seen = {}
run(300)
check(f"back after all: welcomed, and listed again ({[m['text'] for m in den.lines(t0, kind='back')]})",
      den.lines(t0, kind="back", about="Kitchen") and "Kitchen" in [r["name"] for r in den.circle.roster()])
check(f"...and it caught up on what it missed while it was off ({len(kitchen.circle.lines())} lines)",
      ask["id"] in [m["id"] for m in kitchen.circle.lines()])
check("...without answering any of it now", not [m for m in kitchen.lines(t0) if m["by"] == kitchen.id
                                                 and m.get("re") and den.circle.find(m["re"])["t"] < t0])

# ---- you -----------------------------------------------------------------------------------------------------------
t0 = clock.t
den.you = clock.t
mine = den.circle.you_said("Hi everyone!")
run(10)
reply = [m for m in den.lines(t0) if m.get("re") == mine["id"] and m["by"] == den.id]
check(f"you say hi: the one you're at says hi back at once ({[m['text'] for m in reply]})",
      len(reply) == 1 and mine["who"] == "you" and kitchen.circle.find(mine["id"]))
check("...the others have it too", bedroom.circle.find(mine["id"]) is not None)
check("...where you are: at it", den.circle.where_you_are() == ("Den", "") and den.circle.you_here()
      and kitchen.circle.where_you_are() == ("Den", den.url) and not kitchen.circle.you_here())
t0 = clock.t
moved = 0
for _ in range(6):                                     # (now and then: you go to another, and come back)
    bedroom.you = clock.t + 1
    run(200)
    den.you = clock.t + 1
    run(200)
    moved = len(den.lines(t0, kind="moved")) + len(bedroom.lines(t0, kind="moved"))
    if moved:
        break
hello = den.lines(t0, kind="moved")
check(f"you go from one to another: the one you've come to says hello ({[m['text'] for m in hello]})",
      moved and all(m["by"] == (den.id if m["name"] == "Den" else bedroom.id) for m in hello))

# ---- quiet --------------------------------------------------------------------------------------------------------
t0 = clock.t
den.circle.set_quiet(True)
run(4)
check("Quiet, said on one: all of them quiet", [p.talk for p in PIES] == [False] * 3)
check(f"...the one you said it on says okay ({[m['text'] for m in den.lines(t0, by=den.id)]})",
      len(den.lines(t0, by=den.id, kind="chat")) == 1)
run(3 * 3600)
check("...and none of them says anything of its own for hours", len(den.lines(t0)) == 2)
t1 = clock.t
mine = kitchen.circle.you_said("Anyone there?")
run(10)
check("...they still answer you", [m for m in den.lines(t1) if m.get("re") == mine["id"]])
t0 = clock.t
bedroom.circle.set_quiet(False)
run(4)
check("Talk again (on another): all of them talk", [p.talk for p in PIES] == [True] * 3)
run(3 * 3600)
check("...and they do", any(m.get("topic") for m in den.lines(t0)))

# ---- at night -----------------------------------------------------------------------------------------------------
day = time.localtime(clock.t)
clock.t = time.mktime((day.tm_year, day.tm_mon, day.tm_mday + 1, 0, 0, 0, 0, 0, -1))
for p in PIES:
    p.seen = {q.url: clock.t for q in PIES if q is not p}
t0 = clock.t
run(6 * 3600)
check("at night they don't talk of their own accord", not [m for m in den.lines(t0) if m.get("topic")])

# ---- sizing each other up -------------------------------------------------------------------------------------
small = {"members": [], "my_power": 1.0, "weather": "", "doing": ""}
c = den.circle
pick = None
for _ in range(40):
    out = c.remark_topic(dict(small), [{"name": "Kitchen", "hw": kitchen.hw, "doing": ""},
                                       {"name": "Bedroom", "hw": bedroom.hw, "doing": ""}])
    if out.get("topic") == "team":
        pick = out
        break
check(f"two small ones against a Pi 4: one asks the other to team up ({pick})",
      pick and pick["ally"] == "Bedroom" and pick["other"] == "Kitchen" and pick["to"] == "Bedroom")
line = C.builtin_line("remark", dict(pick, own="Den", my_power=1.0, their_power=3.0), random.Random(1))
check(f"...in words ({line})", "Bedroom" in line or "Kitchen" in line)
big = C.builtin_line("reply", {"target_kind": "chat", "target_topic": "team", "me_about": True, "speaker": "Den",
                               "my_power": 3.0}, random.Random(2))
check(f"...and the big one answers ({big})", big in C.LINES["team_them"])
check("a jab at this one: it answers back, not as an onlooker",
      C.reply_pool({"target_kind": "chat", "target_topic": "tease", "me_named": True}) == "tease_me"
      and C.reply_pool({"target_kind": "chat", "target_topic": "tease"}) == "look_on")
check("what you said, roughly, picks its words", [C.you_pool(x) for x in ("hi all", "good night!", "thanks so much",
                                                                          "how are you all?", "what's 2+2?", "ok")]
      == ["you_hi", "you_bye", "you_thanks", "you_how", "you_ask", "you"])

# ---- with a model ---------------------------------------------------------------------------------------------------
asked = []
text = C.model_words("remark", dict(pick, own="Den", my_hw=den.hw, members=[
    {"name": "Den", "self": True, "on": True, "hw": den.hw, "doing": "on the home screen"},
    {"name": "Kitchen", "on": True, "hw": kitchen.hw, "doing": "playing Tetris", "you_here": True},
    {"name": "Bedroom", "on": False, "hw": bedroom.hw}], person="Sam", voice="You talk like a pirate."),
    lambda system, prompt: asked.append((system, prompt)) or '"Den: Ahoy, Bedroom! Team up?"')
check(f"a model's words, tidied: no name in front, no quotes ({text})", text == "Ahoy, Bedroom! Team up?")
system, prompt = asked[0]
check("...it's told who it is, what it's made of, who else is there (gone quiet too) and how it talks",
      "You are Den" in system and "Pi Zero 2 W" in system and "Kitchen, a Pi 4" in system and "(gone quiet)" in system
      and "Sam" in system and "pirate" in system and "Never mean" in system)
check("...and what's going on, and what to say", "Kitchen: playing Tetris (Sam is with it)" in prompt
      and "team up against Kitchen" in prompt)
C.time = real_time

# ---- media mode's part ---------------------------------------------------------------------------------------
class FB:
    w, h, real_w, real_h = 640, 480, 640, 480
    last = None

    def show(self, img): FB.last = img
    def show_part(self, img, box): FB.last = img
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
json.dump({"settings": {"name": "Den", "accent": "Teal"}}, open(g.STATE_FILE, "w"))
m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
check("Apps has Group chat, first", next(t for t in g.LIBRARY if t["name"] == "Apps")["children"][0] == "Group chat"
      and g.LIBRARY[m.tab_index("chat")]["parent"] == "Apps")
now = time.time()
K = "http://10.0.0.21:5432"
m.pie.hear("10.0.0.21", {"pietato": 1, "id": "bbbbbbbbbbbb", "port": 5432, "host": "Kitchen", "accent": "Gold",
                         "doing": "playing Tetris", "you": 30, "hw": {"b": "Pi 4", "c": 4, "r": 3.7, "s": 3.0}})
h = m.pie.heard[K]
check(f"a beacon told straight to this one: what it's doing, what it's made of, when you were there ({h})",
      h["doing"] == "playing Tetris" and h["hw"]["b"] == "Pi 4" and abs(h["you"] - (now - 30)) < 5
      and h["id"] == "b" * 12)
m.pie.hear("10.0.0.21", {"pietato": 1, "id": "bbbbbbbbbbbb", "port": 5432, "host": "Kitchen", "accent": "Gold"})
check("...the one to everyone doesn't say: what was heard is kept", m.pie.heard[K]["doing"] == "playing Tetris"
      and m.pie.heard[K]["hw"]["b"] == "Pi 4")
check("...kept on disk with the rest (its colour and what it is too)", m.pie.peers_kept[K]["hw"]["b"] == "Pi 4")
members = m.group_members()
check(f"the group's members, from the beacons ({members})", len(members) == 1 and members[0]["name"] == "Kitchen"
      and members[0]["id"] == "b" * 12)
basic, full = m.share_beacon("Den"), m.share_beacon("Den", full=True)
check(f"this one's beacon to everyone says no more than it did ({basic})",
      set(basic) == {"pietato", "id", "port", "host", "accent"})
m.you_noticed()
full = m.share_beacon("Den", full=True)
check(f"...straight to yours: what it's doing and what it's made of, and that you're here ({full})",
      full["doing"] and full["hw"]["c"] >= 1 and full["you"] == 0)
m.tab, m.view = m.tab_index("chat"), "list"
m.load_tab(m.tab)
m.dirty = True; m.flush()
check("the page: drawn", FB.last is not None and FB.last.size == (640, 480))
check("...where you are, and what each is doing", [(r["name"], r["you_here"]) for r in m.circle.roster()]
      == [("Den", True), ("Kitchen", False)] and m.group_doing() == "in the group chat")
said = []
m.group_send = lambda url, msg: said.append((url, msg))
m.circle.send = m.group_send
m.circle.spawn = lambda fn, name: fn()
m.press("a")
check("A: a box to say something in", m.view == "keys")
m.kb["text"] = "Hello all"
m.close_keyboard(True)
check(f"...said, and told to the others ({said})", said and said[0][0] == K and said[0][1]["text"] == "Hello all"
      and said[0][1]["who"] == "you")
m.press("y")
m.tick()
check("Y: quiet, on all of them (told to them)", m.setting("group_talk") == "Off" and said[-1][1]["kind"] == "talk"
      and said[-1][1]["on"] is False)
m.press("y")
m.tick()
check("...Y again: they talk again", m.setting("group_talk") == "On" and said[-1][1]["on"] is True)
check(f"a line from one of yours, kept ({m.web_group({'from': '10.0.0.21', 'msg': dict(GOOD, id='1' * 16)})})",
      m.circle.find("1" * 16) is not None)
check("...from one that isn't, turned away",
      not m.web_group({"from": "10.0.0.99", "msg": dict(GOOD, id="2" * 16)})["ok"]
      and m.circle.find("2" * 16) is None and not m.web_group_since(0, "10.0.0.99")["ok"])
got = m.web_group_since(now - 60, "10.0.0.21")
check("what's been said, for one of yours that was off", got["ok"] and "1" * 16 in [x["id"] for x in got["msgs"]])
m.view, m.tab = "home", 0
m.group_heard(dict(GOOD, id="3" * 16, text="Pop!"))
check("a line come while you're here, on the home screen: it pops up",
      m.group_pop and m.group_pop["msg"]["text"] == "Pop!")
m.dirty = True; m.flush()
m.group_pop["until"] = 0
m.group_tick(time.monotonic())
check("...for a while", m.group_pop is None)
m.game = type("Run", (), {"ended": False, "game": {"title": "Tetris"}})()
m.group_heard(dict(GOOD, id="4" * 16, text="Not now"))
check("...not over a game", m.group_pop is None and m.group_doing() == "playing Tetris")
m.game = None
m.you_at = time.time() - 3600
m.group_heard(dict(GOOD, id="5" * 16, text="Nobody here"))
check("...nor where you aren't", m.group_pop is None)

# its camera, looking for someone moving
GS = importlib.import_module("pitato.screens.group")
from PIL import Image as PImage, ImageDraw as PDraw  # noqa: E402


def jpeg(boxes=(), noise=0):
    im = PImage.new("RGB", (640, 480), (40, 44, 48))
    d = PDraw.Draw(im)
    for b in boxes:
        d.rectangle(b, fill=(220, 200, 180))
    if noise:
        im = PImage.blend(im, PImage.effect_noise((640, 480), 40).convert("RGB"), noise)
    buf = io.BytesIO()
    im.save(buf, "JPEG")
    return buf.getvalue()


empty, empty2, grainy = GS.eyes_small(jpeg()), GS.eyes_small(jpeg()), GS.eyes_small(jpeg(noise=0.08))
someone = GS.eyes_small(jpeg([(220, 80, 380, 470)]))
check("its camera: nothing moving (a grainy picture too), nothing noticed; someone come in, noticed",
      not GS.eyes_moved(empty, empty2) and not GS.eyes_moved(empty, grainy) and GS.eyes_moved(empty, someone)
      and GS.eyes_small(b"not a picture") is None)

# one of yours that hasn't the group chat yet (an older Pietato): not asked again for a while
calls = []


def older(url, body, timeout=0):
    calls.append(url)
    raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)


GS.post_json = older
type(m).group_send(m, "http://10.0.0.30:5432", dict(GOOD))
type(m).group_send(m, "http://10.0.0.30:5432", dict(GOOD))
check(f"one of yours without the group chat (not updated yet): asked once, then left a while ({calls})",
      calls == ["http://10.0.0.30:5432/api/group"] and type(m).group_fetch(m, "http://10.0.0.30:5432", 0) == [])

# ---- two real Pietatos, and a third ----------------------------------------------------------------------------------
procs = []


def start(name, peer_url="http://127.0.0.1:1", peer_name="none"):
    home = f"{S}/{name}"
    os.makedirs(home, exist_ok=True)
    p = subprocess.Popen([sys.executable, TESTS + "/peer_pietato.py", home, f"{S}/{name}.log", name, peer_url,
                          peer_name], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    line = p.stdout.readline().split()
    procs.append(p)
    return p, (line[1] if line[:1] == ["READY"] else None)


def do(p, line):
    p.stdin.write(line + "\n")
    p.stdin.flush()
    return p.stdout.readline().strip()


def log_of(p):
    return json.loads(do(p, "group log"))


def until(cond, secs=20):
    end = time.time() + secs
    while time.time() < end:
        got = cond()
        if got:
            return got
        time.sleep(0.3)
    return cond()


try:
    a, a_url = start("attic")
    b, b_url = start("basement", a_url, "attic")
    check("two Pietatos up", a_url and b_url)
    do(a, f"peer {b_url} basement")
    do(a, "group say Hello from the attic")
    got = until(lambda: [x for x in log_of(b) if x["text"] == "Hello from the attic"])
    check(f"a line said on one: on the other, through its web page ({got[:1]})", got and got[0]["who"] == "you"
          and got[0]["name"] == "attic")
    reply = until(lambda: [x for x in log_of(b) if x.get("re") == got[0]["id"] and x["name"] == "attic"])
    check(f"...and the one you said it on answers, there too ({[x['text'] for x in reply]})", reply)
    c3, c_url = start("closet", a_url, "attic")
    mine = {x["id"] for x in log_of(a)}
    caught = until(lambda: mine <= {x["id"] for x in log_of(c3)}, 25)
    check("one that was off catches up from another as it comes on", caught)
    do(b, "group quiet on")
    check("Quiet on one: on the others too", until(lambda: any(x["kind"] == "talk" for x in log_of(a))))
finally:
    for p in procs:
        try:
            p.stdin.write("quit\n")
            p.stdin.flush()
        except OSError:
            pass
    for p in procs:
        try:
            p.wait(5)
        except subprocess.TimeoutExpired:
            p.kill()

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
os._exit(0)
