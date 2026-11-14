"""The Cookie (pitato/cookie.py, cookiepage.py, screens/cookie.py; nearby.py's beacons; webui.py's /api/cookie): your
Pietatos play each other at rock paper scissors for cookies. Its rules first: who got the last cookie, as one says it,
kept to what's expected; which of two is right; each Bot's habit at rock paper scissors (always the same Bot's, and
never one that locks two of them); which gets the next when the one that got the last has gone quiet; and its words:
a cookie's got, never taken. Then three Pietatos, wired to each other here: none gets the first straight away, then
the one to; two that did at once become one; a Bot's throw, won (it got a cookie, as all of them know, and it says so
in the group chat), lost and tied, too soon after the last, and sent to one that isn't the one to beat; not from one
that isn't yours, nor with sharing off; the one that got the last gone quiet for an hour (the one that's waited
longest gets the next), back again (it finds out), and one that's heard but doesn't answer; two with the same id (an
SD card copied); one that wins again and again, called a cheat by the one it beat, and the argument that follows; not
at night, in a game, or with the group chat quiet. Its page: who got the last, your throw (◀▲▶), another's throw
waiting for yours (and its Bot's, if you don't), the small cookie on the status bar and the home screen of the one
that got the last. Last, for real: this one's throw sent to another Pietato's web page (peer_pietato.py), and what it
says in the group chat getting there."""
import importlib, json, os, random, shutil, subprocess, sys, time, urllib.parse
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/tcookie"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME + "/Music")
sys.path.insert(0, TESTS)
import pietato_all as g
import numpy as np

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"; g.ASSIST_FILE = S + "/assist.json"
g.GROUP_LOG = S + "/group.json"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
import gk_static; gk_static.use_home(g, HOME)
CK = importlib.import_module("pitato.cookie")
SC = importlib.import_module("pitato.screens.cookie")
PG = importlib.import_module("pitato.cookiepage")
C = importlib.import_module("pitato.circle")
NB = importlib.import_module("pitato.nearby")
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


# ---- its rules -----------------------------------------------------------------------------------------------------
IA, IB, IC = "1111aaaa2222bbbb", "5555cccc6666dddd", "9999eeee0000ffff"      # (three Pietatos' ids: Den < Kitchen < TV)
now = time.time()
GOOD = {"n": 3, "at": IB, "name": "Kitchen\x00\n", "t": now - 60, "from": "Den", "how": "pr", "you": True, "zz": 1}
got = CK.cookie_rec(GOOD)
check(f"the cookie as another says it is, kept to what's expected ({got})",
      got == {"n": 3, "at": IB, "name": "Kitchen", "t": now - 60, "from": "Den", "how": "pr", "you": True})
check("...not one: no count, a count that's no number, no holder",
      all(CK.cookie_rec(dict(GOOD, **bad)) is None for bad in ({"n": 0}, {"n": True}, {"n": "3"}, {"n": -1},
                                                               {"at": "nobody"}, {"at": None}, {"at": IB.upper()}))
      and CK.cookie_rec("nonsense") is None and CK.cookie_rec(None) is None)
odd = CK.cookie_rec(dict(GOOD, t=float("inf"), how="rp", name="", you="yes"))
check(f"...a time that isn't one, throws that don't beat each other, no name: left out ({odd})",
      odd["t"] == 0.0 and odd["how"] == "" and odd["name"] == "A Pietato" and odd["you"] is False
      and [CK.cookie_rec(dict(GOOD, how=how))["how"] for how in ("left", "new")] == ["left", "new"])


def rec(n, at, name="X", frm="", how="new", you=False, ago=5):
    return {"n": n, "at": at, "name": name, "t": time.time() - ago, "from": frm, "how": how, "you": you}


check("of two, the one that's been somewhere new more times is the cookie; the same number, the lower id's",
      CK.cookie_newer(rec(4, IC), rec(3, IA)) and not CK.cookie_newer(rec(3, IA), rec(4, IC))
      and CK.cookie_newer(rec(3, IA), rec(3, IB)) and not CK.cookie_newer(rec(3, IB), rec(3, IA)))
check("...the same one twice isn't newer; any is newer than none, none than nothing",
      not CK.cookie_newer(rec(3, IA), rec(3, IA)) and CK.cookie_newer(rec(1, IC), None)
      and not CK.cookie_newer(None, rec(1, IC)) and not CK.cookie_newer(None, None))
says = CK.cookie_says(IA, rec(2, IA, "Den"), 2, "rpsrpsrps", 4)
back = CK.cookie_said(json.loads(json.dumps(says)))
check(f"what a beacon says of it: which one it is, the cookie, when it last had it, its Bot's last throws, how many "
      f"throws in a row it's won ({says})",
      says["id"] == IA and says["had"] == 2 and says["throws"] == "rpsrps" and says["wins"] == 4
      and back["rec"]["at"] == IA and back["throws"] == "rpsrps" and back["wins"] == 4
      and CK.cookie_says(IA, None, 0, "") == {"id": IA, "had": 0, "throws": "", "wins": 0})
check("...kept to what's expected: an older Pietato says nothing of it; nonsense is left out",
      CK.cookie_said(None) is None and CK.cookie_said({"id": "me"}) is None and CK.cookie_said("x") is None
      and CK.cookie_said({"id": IA, "rec": {"n": "many"}, "had": -3, "throws": "rXp;rm -rf" + "s" * 90, "wins": "all"})
      == {"id": IA, "rec": None, "had": 0, "throws": "ssssss", "wins": 0}
      and CK.cookie_said({"id": IA, "throws": 7, "wins": 10 ** 6}) == {"id": IA, "rec": None, "had": 0, "throws": "",
                                                                       "wins": 0})
check("a throw against another: rock beats scissors, scissors beat paper, paper beats rock; the same is a tie",
      [CK.cookie_result(a, b) for a in "rps" for b in "rps"]
      == ["tie", "lost", "won", "won", "tie", "lost", "lost", "won", "tie"])
habits = [CK.cookie_habit(f"{k:016x}") for k in range(300)]
check(f"each Bot's habit, from its id: always the same Bot's, and all six of them among many ({sorted(set(habits))})",
      set(habits) == set(CK.COOKIE_HABITS) and CK.cookie_habit(IA) == CK.cookie_habit(IA)
      and habits == [CK.cookie_habit(f"{k:016x}") for k in range(300)])
rng = random.Random(11)
lean = [CK.cookie_bot_throw("rock", "", "", rng) for _ in range(3000)]
check(f"one that leans on rock throws it more than half the time, and the others too ({lean.count('r')} of 3000)",
      1650 <= lean.count("r") <= 1950 and lean.count("p") > 400 and lean.count("s") > 400)
seq = ""
for _ in range(400):
    seq += CK.cookie_bot_throw("change", seq, "", rng)
check("one that changes never throws the same twice", all(a != b for a, b in zip(seq, seq[1:]))
      and set(seq) == set("rps"))
copies = [CK.cookie_bot_throw("copy", "r", "s", rng) for _ in range(2000)]
check(f"one that copies throws what last beat it, mostly ({copies.count('s')} of 2000); with nothing to copy, any",
      copies.count("s") >= 1500 and {CK.cookie_bot_throw("copy", "", "", rng) for _ in range(200)} == set("rps"))
rounds = [CK.cookie_bot_throw("round", "p", "", rng) for _ in range(2000)]
check(f"one that goes round throws the next after its last, mostly ({rounds.count('s')} of 2000)",
      rounds.count("s") >= 1500 and len(set(rounds)) == 3)
stuck = []
for h1 in CK.COOKIE_HABITS:                           # (one Bot trying for another's, time after time)
    for h2 in CK.COOKIE_HABITS:
        r2 = random.Random(hash((h1, h2)) & 0xffff)
        mine, theirs, beat1, beat2, won = "", "", "", "", 0
        for _ in range(300):
            a, b = CK.cookie_bot_throw(h1, mine, beat1, r2), CK.cookie_bot_throw(h2, theirs, beat2, r2)
            mine, theirs = (mine + a)[-6:], (theirs + b)[-6:]
            res = CK.cookie_result(a, b)
            won += res == "won"
            beat1, beat2 = (b if res == "lost" else beat1), (a if res == "won" else beat2)
        if won < 30:
            stuck.append((h1, h2, won))
check(f"no two habits lock the cookies between them: either beats the other often enough ({stuck})", not stuck)
said = {n: sum(CK.cookie_accuses(n, rng) for _ in range(2000)) for n in (1, 2, 3, 4, 9)}
check(f"one that's won again and again: called a cheat by the one it beat never before its third win in a row, then "
      f"more often than not, and likelier the longer it goes on (of 2000: {said})", said[1] == said[2] == 0
      and 1080 <= said[3] <= 1320 and said[3] < said[4] < said[9] and 1700 <= said[9] <= 1900)
check("the one that got the last gone quiet: the one that's waited longest gets the next; of two the same, the lower "
      "id; nobody on, none",
      CK.cookie_heir([(IC, 4), (IA, 7), (IB, 0)]) == IB and CK.cookie_heir([(IC, 2), (IA, 2), (IB, 5)]) == IA
      and CK.cookie_heir([]) is None)
check("the night, from 11 to 7", [h for h in range(24) if CK.cookie_night(h, (23, 7))] == [0, 1, 2, 3, 4, 5, 6, 23]
      and [h for h in range(24) if CK.cookie_night(h, (1, 5))] == [1, 2, 3, 4])
check("in words", [CK.cookie_beat_words(*x) for x in ("pr", "sp", "rs")]
      == ["Paper beats rock", "Scissors beat paper", "Rock beats scissors"]
      and [CK.cookie_ago(x) for x in (5, 89, 90, 3599, 3600, 86400, 3 * 86400)]
      == ["just now", "just now", "1 min ago", "59 min ago", "1 h ago", "24 h ago", "3 days ago"])
lines = {CK.cookie_line(rec(5, IA, "Den", "Kitchen", "pr"), random.Random(k)) for k in range(40)}
check(f"what the one that's got a cookie says: that it got one, which it beat, and the throws ({sorted(lines)[0]!r} "
      f"and {len(lines) - 1} more)", len(lines) == len(CK.COOKIE_WON)
      and all("Kitchen" in x and "got a cookie!" in x and "rock" in x for x in lines))
you = {CK.cookie_line(rec(5, IA, "Den", "Kitchen", "sp", you=True), random.Random(k)) for k in range(40)}
check(f"...with your throw: the two of you ({sorted(you)})", all(x.startswith("We ") and "Kitchen" in x
                                                                  and "got a cookie!" in x for x in you)
      and len(you) == 2)
after = {CK.cookie_line(rec(5, IA, "Den", "Kitchen", "left"), random.Random(k)) for k in range(9)}
check(f"...the one before it gone quiet ({sorted(after)[0]!r}); the first one ('I got a cookie!')",
      all("Kitchen" in x and x.endswith("I got a cookie!") for x in after)
      and CK.cookie_line(rec(1, IA, "Den"), random.Random(1)) == "I got a cookie!")
BAD = __import__("re").compile(r"\b(take|takes|took|taken|steal|steals|stole|stolen|bake|bakes|baked)\b|"
                               r"(has|have|keeps|kept) (the|a) cookie|stays here|come and|changed hands|"
                               r"left (it|the cookie)|the cookie's (here|mine|ours)", __import__("re").I)
said_words = list(CK.COOKIE_WON + CK.COOKIE_YOU_WON + CK.COOKIE_NEXT + CK.COOKIE_GOT) + [
    x for name, pool in C.LINES.items() if name.startswith(("cookie", "cheat")) for x in pool]
check(f"none of their words for it ({len(said_words)}) is of a cookie taken, kept, or to come and take: a cookie's got",
      len(said_words) > 30 and not [x for x in said_words if BAD.search(x)])

# ---- your Pietatos' beacons ----------------------------------------------------------------------------------------
news = NB.group_news({"id": "b" * 12, "hw": {"b": "Pi 4"}, "cookie": says}, {}, now)
check(f"a beacon told straight to this one: the cookie as it says it is, kept ({news.get('cookie')})",
      news["cookie"] == back and NB.group_news({"id": "b" * 12}, news, now)["cookie"] == back)
check("...an older Pietato's says nothing of it; nonsense isn't kept",
      NB.group_news({"id": "b" * 12, "hw": {}}, news, now)["cookie"] is None
      and NB.group_news({"id": "b" * 12, "hw": {}, "cookie": [1, 2]}, {}, now)["cookie"] is None)


# ---- three Pietatos, wired to each other here ----------------------------------------------------------------------
class FB:
    w, h = 640, 480
    real_w, real_h = 640, 480
    last = None
    def show(self, img): FB.last = img.copy()
    def show_part(self, img, box): FB.last = img.copy()
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
IPS, ALL, SAID, POSTS, DOWN = {}, [], [], [], set()


def make(name, ip, cid, accent):
    m = g.Media()
    m.state["settings"].update(name=name, accent=accent)
    m.save_state = lambda: None                       # (three of them here: their state isn't one file's)
    m.state["cookie"] = dict(m.state["cookie"], id=cid)
    m.cookie_rng = random.Random(len(ALL) + 3)
    m.cookie_bots_may = lambda wall: True             # (whatever the hour is, here)
    m.cookie_try_at = time.monotonic() + 1e6          # (its Bot's tries: when this says)
    m.circle.send = lambda url, msg, name=name: SAID.append((name, url, msg))
    m.circle.spawn = lambda fn, name: fn()
    IPS[ip] = m
    ALL.append(m)
    return m


def url_of(m):
    return f"http://{next(ip for ip, x in IPS.items() if x is m)}:5432"


def tell(*only):
    """Each one's beacon, heard by the others (as it's told straight to each of them)."""
    for ip, m in IPS.items():
        if only and m not in only:
            continue
        beacon = json.loads(json.dumps(m.share_beacon(m.own_name(), full=True)))
        for other in ALL:
            if other is not m:
                other.pie.hear(ip, beacon)


def fake_post(url, body, timeout=0):
    """A try, sent: to the web page of the one at that address, and so to its media mode."""
    ip = urllib.parse.urlsplit(url).hostname
    sender = next(i for i, x in IPS.items() if x.state["cookie"].get("id") == body["id"])
    wire = json.loads(json.dumps(dict(body, **{"from": sender})))
    POSTS.append((ip, wire))
    if ip in DOWN:
        raise OSError("connection refused")
    return json.loads(json.dumps(IPS[ip].web_cookie(wire)))


def jobs(*ms):
    for m in ms or ALL:
        while m.soon_jobs:
            m.soon_jobs.popleft()()


def settle(secs=20):
    """Every try answered, and what follows done on each one's main loop."""
    end = time.time() + secs
    while time.time() < end:
        jobs()
        if not any(m.cookie_trying for m in ALL) and not any(m.soon_jobs for m in ALL):
            return True
        time.sleep(0.01)
    return False


def look(*ms):
    for m in ms or ALL:
        m.cookie_look(time.monotonic())
    jobs()


def knows(m):
    r = m.state["cookie"].get("rec")
    return (r["n"], r["at"]) if r else None


def throws(m, way):
    m.cookie_bot = lambda: way


def chat(m):
    return [x for x in m.circle.lines() if x.get("topic") == "cookie"]


def wins(*ms):
    return [m.state["cookie"]["wins"] for m in ms or ALL]


real_post, SC.post_json = SC.post_json, fake_post
lone = g.Media()
lone.cookie_up = time.monotonic() - 1000
lone.cookie_look(time.monotonic())
check("on its own, a Pietato has no cookie, and does nothing about one (no id of its own made for it)",
      not lone.cookie_here() and lone.state["cookie"]["rec"] is None and "id" not in lone.state["cookie"])
A, B = make("Den", "10.0.0.21", IA, "Teal"), make("Kitchen", "10.0.0.22", IB, "Pink")
D = make("TV", "10.0.0.23", IC, "Gold")
basic, full = A.share_beacon("Den"), A.share_beacon("Den", full=True)
check(f"its beacon to everyone says no more than it did; the one straight to yours says which it is ({full['cookie']})",
      set(basic) == {"pietato", "id", "port", "host", "accent"}
      and full["cookie"] == {"id": IA, "had": 0, "throws": "", "wins": 0})
tell()
heard = A.pie.cookie_heard()
check(f"what your others say of it, as their beacons were heard ({[(h['name'], h['full']) for h in heard]})",
      sorted((h["name"], h["full"], h["cookie"]["id"]) for h in heard) == [("Kitchen", True, IB), ("TV", True, IC)]
      and [p["name"] for p in sorted(A.cookie_on(heard, time.time()), key=lambda p: p["name"])] == ["Kitchen", "TV"])
look()
check("just started: none of them bakes one yet (your others' word of theirs comes first)",
      [knows(m) for m in ALL] == [None, None, None])
for m in ALL:
    m.cookie_up = time.monotonic() - 100
look(B, D)
check("...a minute on: not those that aren't the one to", [knows(m) for m in ALL] == [None, None, None])
D.cookie_up = time.monotonic() - 400
look(D, A)
check(f"...the one with the lowest id does; and, after five minutes, whichever ({knows(A)}, {knows(D)})",
      knows(A) == (1, IA) and knows(D) == (1, IC) and A.cookie_here() and D.cookie_here())
check(f"it says so in the group chat ({[x['text'] for x in chat(A)]})",
      [x["text"] for x in chat(A)] == ["I got a cookie!"] and chat(A)[0]["kind"] == "chat"
      and any(who == "Den" and msg["topic"] == "cookie" for who, _, msg in SAID))
tell()
look()
check("two got the first at once: one of them is the one to beat, on all three (never two for long)",
      [knows(m) for m in ALL] == [(1, IA)] * 3 and A.cookie_here() and not B.cookie_here() and not D.cookie_here())
check("...and the one that had the other doesn't say so again", len(chat(D)) == 1 and len(chat(A)) == 1)

# a Bot's try: won
tell()
throws(A, "r"); throws(B, "p"); throws(D, "r")
POSTS.clear()
B.cookie_try_at = 0.0
before = time.monotonic()
look(B)
check("a Bot's try for it, when that's due: its throw, sent to the one that has it", settle()
      and POSTS == [("10.0.0.21", {"id": IB, "name": "Kitchen", "n": 1, "throw": "p", "you": False, "wins": 0,
                                   "from": "10.0.0.22"})])
r = B.state["cookie"]["rec"]
check(f"paper beats rock: the winner got a cookie, as both know at once ({r})",
      knows(A) == knows(B) == (2, IB) and B.cookie_here() and not A.cookie_here() and r["from"] == "Den"
      and r["how"] == "pr" and r["you"] is False and r["name"] == "Kitchen")
check("...each Bot's throw kept with its last few, and what beat the one that lost",
      A.state["cookie"]["throws"] == "r" and A.state["cookie"]["beat"] == "p" and B.state["cookie"]["throws"] == "p"
      and B.state["cookie"]["beat"] == "" and B.share_beacon("Kitchen", full=True)["cookie"]["throws"] == "p")
check(f"...and a win in a row for the one that got it, told with the rest ({wins()})", wins() == [0, 1, 0]
      and B.share_beacon("Kitchen", full=True)["cookie"]["wins"] == 1)
check(f"...the one that got it says so in the group chat, once ({[x['text'] for x in chat(B)]})",
      len(chat(B)) == 1 and "Den" in chat(B)[0]["text"] and chat(B)[0].get("about") == "Den" and not chat(A)[1:])
check(f"...and its Bot's next try isn't for a while: one of them about every ten minutes, between them all "
      f"({B.cookie_try_at - before:.0f} s)", 2 * 480 <= B.cookie_try_at - before <= 2 * 720 + 5)
check("the third doesn't know yet", knows(D) == (1, IA))
tell()
look()
check("...till it hears: then all three say the same", [knows(m) for m in ALL] == [(2, IB)] * 3 and len(chat(D)) == 1)
check("when the cookie last got to each, for whose it is if it's left: told with it",
      [m.share_beacon("x", full=True)["cookie"]["had"] for m in ALL] == [1, 2, 1])

# lost, tied, too soon, gone
POSTS.clear()
check("a try that loses: the cookie stays", D.cookie_try() and settle() and knows(B) == (2, IB) and B.cookie_here()
      and POSTS[0][1]["throw"] == "r" and D.state["cookie"]["beat"] == "p" and D.cookie_deaf is False)
check("...another straight after it: too soon (the one to beat plays one from each every few seconds)",
      D.cookie_try() and settle() and len(POSTS) == 2 and knows(B) == (2, IB) and D.state["cookie"]["throws"] == "r"
      and 0 < D.cookie_wait - time.monotonic() <= SC.COOKIE_GAP)
B.cookie_tries.clear()
throws(D, "p")
check("...the same throw: a tie, and it stays", D.cookie_try() and settle() and knows(B) == (2, IB)
      and D.state["cookie"]["throws"] == "rp" and B.state["cookie"]["throws"] == "ppp")
check(f"keeping it is a win too, and a tie changes nothing ({wins()})", wins() == [0, 2, 0]
      and POSTS[-1][1]["wins"] == 0)
got = A.web_cookie({"from": "10.0.0.23", "id": IC, "name": "TV", "n": 2, "throw": "s"})
check(f"asked of one that hasn't got it: told so, with the cookie as it knows it ({got['got']})",
      got["ok"] and got["got"] == "gone" and got["rec"]["at"] == IB)
D.state["cookie"] = dict(D.state["cookie"], rec=rec(1, IA, "Den"))
check("...so one that was behind catches up", D.cookie_try() and settle() and knows(D) == (2, IB))
bad = [B.web_cookie({"from": "10.0.0.99", "id": IC, "name": "TV", "n": 2, "throw": "s"}),
       B.web_cookie({"from": "10.0.0.23", "id": "me", "name": "TV", "n": 2, "throw": "s"}),
       B.web_cookie({"from": "10.0.0.23", "id": IC, "name": "TV", "n": 2, "throw": "dynamite"})]
B.state["settings"]["share"] = "Off"
bad.append(B.web_cookie({"from": "10.0.0.23", "id": IC, "name": "TV", "n": 2, "throw": "s"}))
check(f"not from one that isn't yours, nor nonsense, nor with sharing off ({[x.get('error') for x in bad]})",
      [x["ok"] for x in bad] == [False] * 4 and knows(B) == (2, IB) and not B.cookie_here())
B.state["settings"]["share"] = "On"
B.cookie_tries.clear()
got = B.web_cookie({"from": "10.0.0.23", "id": IC, "name": "TV", "n": 1, "throw": "s"})
check("...nor for a cookie that's moved on since (its count's another)", got["got"] == "gone" and knows(B) == (2, IB)
      and B.cookie_here())

# the one that got the last, gone quiet
jobs()
tell()
look()
KU = url_of(B)


def quiet(m, url, secs):
    m.pie.heard[url]["seen"] = time.time() - secs
    m.state["cookie"] = dict(m.state["cookie"], seen=time.time() - secs)


quiet(A, KU, 3000); quiet(D, KU, 3000)
look(A, D)
check("the one to beat not heard for 50 minutes: it still is", knows(A) == knows(D) == (2, IB))
quiet(A, KU, 3700); quiet(D, KU, 3700)
A.cookie_up = time.monotonic() - 30
look(D, A)
check("...for an hour: the next isn't got by one that isn't the one to (two have waited as long: the lower id's), "
      "nor by that one when it's only just started", knows(A) == knows(D) == (2, IB))
A.cookie_up = time.monotonic() - 500
look(D, A)
r = A.state["cookie"]["rec"]
check(f"...then it gets the next ({r})", knows(A) == (3, IA) and A.cookie_here() and r["how"] == "left"
      and r["from"] == "Kitchen" and "Kitchen" in chat(A)[-1]["text"] and knows(D) == (2, IB))
tell(A)
look(D)
check("...and your others hear so", knows(D) == (3, IA))
tell()
look(B)
check("the one that was off, back: it finds the cookie's moved on, and hasn't got it", knows(B) == (3, IA)
      and not B.cookie_here())

# one that's heard, but doesn't answer
DOWN.add("10.0.0.21")
throws(B, "p")
check("one to beat that doesn't answer a try (its web page's off)", B.cookie_try() and settle() and B.cookie_deaf
      and knows(B) == (3, IA))
B.state["cookie"] = dict(B.state["cookie"], seen=time.time() - 3700)
D.state["cookie"] = dict(D.state["cookie"], seen=time.time() - 3700)
look(B, D)
check("...for an hour, heard all the while: the next isn't got by the one it didn't answer (another has waited "
      "longer), nor by one that hasn't asked it", knows(B) == knows(D) == (3, IA))
throws(D, "p")
check("...that one's try isn't answered either", D.cookie_try() and settle() and D.cookie_deaf)
D.state["cookie"] = dict(D.state["cookie"], seen=time.time() - 3700)
look(D)
check("...so it's as good as gone: the one that's waited longest has it", knows(D) == (4, IC) and D.cookie_here()
      and D.state["cookie"]["rec"]["from"] == "Den" and D.state["cookie"]["rec"]["how"] == "left" and not D.cookie_deaf)
DOWN.clear()
tell()
look()
check("...as all three then say", [knows(m) for m in ALL] == [(4, IC)] * 3 and not A.cookie_here())
throws(A, "p"); throws(D, "r")
check("a try with the throw that wins: the cookie's back", A.cookie_try() and settle() and knows(A) == (5, IA)
      and A.cookie_here() and not D.cookie_here() and D.state["cookie"]["beat"] == "p")
tell()
look()

# two with the same id
B.state["cookie"] = dict(B.state["cookie"], id=IA)
tell()
look(A)
new_a = A.state["cookie"]["id"]
said_a = len(chat(A))
check(f"another of yours with this one's id (an SD card copied): a new one here, and the cookie it had with it "
      f"({new_a})", new_a != IA and CK.cookie_whose(new_a) and knows(A) == (6, new_a) and A.cookie_here())
tell()
look()
check("...so one of the two is the one to beat, not both (and it doesn't say it got one again)", A.cookie_here()
      and not B.cookie_here() and not D.cookie_here() and [knows(m) for m in ALL] == [(6, new_a)] * 3
      and len(chat(A)) == said_a)
B.state["cookie"] = dict(B.state["cookie"], id=IB)
IA = new_a

# one that wins again and again
JOBS = []
real_accuses = SC.cookie_accuses
SC.cookie_accuses = lambda n, rng: n >= CK.COOKIE_SUSPECT    # (every time, from the third: its chance is above)
for m in ALL:
    m.state["cookie"] = dict(m.state["cookie"], wins=0)
    m.circle.schedule = lambda after, how, data=None, who=m.own_name(): JOBS.append((who, after, how, data))


def tries(m, way, holder):
    """m's Bot throws `way` for the cookie holder has."""
    holder.cookie_tries.clear()
    throws(m, way)
    return m.cookie_try() and settle()


throws(A, "r")
ok = tries(B, "s", A) and tries(D, "s", A)
check(f"the one with the cookie keeps it twice running: nothing said of it ({wins()})", ok and wins() == [2, 0, 0]
      and not JOBS and A.cookie_here())
ok = tries(B, "s", A)
check(f"...a third time: the one it's just beaten says it must be cheating, a few seconds on ({JOBS})", ok
      and wins() == [3, 0, 0] and len(JOBS) == 1 and JOBS[0][0] == "Kitchen" and JOBS[0][2] == "cheat"
      and JOBS[0][3] == {"about": "Den", "wins": 3} and 4 <= JOBS[0][1] <= 12)
ok = tries(D, "r", A)
check("...a tie: still three, and nothing more said", ok and wins() == [3, 0, 0] and len(JOBS) == 1)
B.state["settings"]["group_talk"] = "Off"
ok = tries(B, "s", A)
B.state["settings"]["group_talk"] = "On"
check(f"...a fourth, with the group chat quiet: not said ({wins()})", ok and wins() == [4, 0, 0] and len(JOBS) == 1)
D.state["cookie"] = dict(D.state["cookie"], wins=2)
ok = tries(D, "p", A)
check(f"one that's won twice gets a cookie with its third: the one it beat says so ({JOBS[-1:]})", ok
      and D.cookie_here() and wins() == [0, 0, 3] and len(JOBS) == 2 and JOBS[1][0] == "Den"
      and JOBS[1][3] == {"about": "TV", "wins": 3})
SC.cookie_accuses = real_accuses
for m in ALL:
    del m.circle.schedule
tell()
look()
throws(D, "r")
check("(the cookie back where it was, for what follows)", tries(A, "p", D) and A.cookie_here() and wins() == [1, 0, 0])
tell()
look()

# when their Bots may try
for m in ALL:
    del m.cookie_bots_may


def at(hour, minute=0):
    return time.mktime((2026, 11, 12, hour, minute, 0, 0, 0, -1))


check("their Bots try in the day, not at night", B.cookie_bots_may(at(12)) and B.cookie_bots_may(at(7))
      and B.cookie_bots_may(at(22, 59)) and not B.cookie_bots_may(at(23)) and not B.cookie_bots_may(at(3)))
B.state["settings"]["group_talk"] = "Off"
quiet_no = not B.cookie_bots_may(at(12))
B.state["settings"]["group_talk"] = "On"
B.game = object()
game_no = not B.cookie_bots_may(at(12))
B.game = None
check("...nor with the group chat quiet, nor from one that's in a game", quiet_no and game_no
      and B.cookie_bots_may(at(12)))
tell()
POSTS.clear()
B.cookie_bots_may = lambda wall: False
B.cookie_try_at = 0.0
look(B)
held = (B.cookie_held, len(POSTS))
B.cookie_bots_may = lambda wall: True
t0 = time.monotonic()
look(B)
check(f"a try that came due in the night waits, and isn't the moment it's over (not all of them at once: "
      f"{B.cookie_try_at - t0:.0f} s on)", held == (True, 0) and not POSTS and not B.cookie_held
      and 20 <= B.cookie_try_at - t0 <= 305)
for m in ALL:
    m.cookie_try_at = time.monotonic() + 1e6

# ---- kept, and told to their Bots' models --------------------------------------------------------------------------
check(f"for their Bots' models: how cookies are got, and who got the last ({B.cookie_fact()[-58:]!r})",
      B.cookie_fact().endswith("Den got the last one, and is the one to beat for the next")
      and A.cookie_fact().endswith("You got the last one, and are the one to beat for the next")
      and not BAD.search(B.cookie_fact())
      and B.cookie_fact() in B.group_extra()["facts"])
line = dict(chat(A)[0], id="c" * 16, t=time.time())
got = C.clean_msg(line)
check("a line about the cookie, from another of yours: kept as one", got["topic"] == "cookie")
check("...answered by the one that was beaten, or by another, in words for it",
      C.reply_pool({"target_topic": "cookie", "me_about": True}) == "cookie_me"
      and C.reply_pool({"target_topic": "cookie"}) == "cookie_re"
      and all(C.builtin_line("reply", {"target_topic": "cookie", "me_about": k, "speaker": "Den"}, random.Random(n))
              in [x.format(speaker="Den") for x in C.LINES["cookie_me" if k else "cookie_re"]]
              for k in (True, False) for n in range(12)))


# ---- the argument: one of them accused of cheating, and the others taking sides -------------------------------------
class Clock:
    t = time.mktime((2026, 11, 12, 15, 0, 0, 0, 0, -1))

    def time(self):
        return self.t

    def localtime(self, t=None):
        return time.localtime(self.t if t is None else t)


clock, real_time = Clock(), C.time
NAMES = ("Den", "Kitchen", "TV")


def circles(seed, talk=True):
    """Three of them in the group chat, on a pretend clock, each hearing what the others say."""
    made = {}
    for k, name in enumerate(NAMES):
        c = made[name] = C.Circle(path=f"{S}/argue_{seed}_{name}.json", rng=random.Random(seed * 10 + k))
        c.clear()
        c.started, c.self_back_done, c.next_remark, c.next_sync = clock.t, True, clock.t + 1e9, clock.t + 1e9
        c.own = lambda name=name: {"id": (name.lower() * 4)[:12], "name": name, "accent": "", "hw": {},
                                   "doing": "on the home screen", "you": None}
        c.members = lambda name=name: [{"url": f"http://{n}", "name": n, "id": (n.lower() * 4)[:12], "seen": clock.t,
                                        "accent": "", "doing": "", "hw": {}, "you": None} for n in NAMES if n != name]
        c.send = lambda url, msg: made[url[7:]].receive(msg)
        c.spawn = lambda fn, name: fn()
        c.talk = lambda: talk
    return made


def go(made, secs):
    end = clock.t + secs
    while clock.t < end:
        clock.t += 2
        for c in made.values():
            c.tick()


def pool(name, **words):
    return {C.fill(x, words) for x in C.LINES[name]} - {""}


C.time = clock
try:
    runs = []
    for seed in range(1, 9):
        made = circles(seed)
        made["Den"].schedule(0, "cheat", {"about": "Kitchen", "wins": 3})
        go(made, 200)
        runs.append(made["Den"].lines())
    first = [r[0] for r in runs if r]
    check(f"one says another's cheating: a line to it, and about it ({sorted({m['text'] for m in first})[:3]}...)",
          len(first) == 8 and all(m["name"] == "Den" and m["topic"] == "cheat" and m["about"] == "Kitchen"
                                  and m["to"] == "Kitchen" and not m.get("re")
                                  and m["text"] in pool("cheat", about="Kitchen", wins=3) for m in first)
          and len({m["text"] for m in first}) >= 3)
    by_id = [{m["id"]: m for m in r} for r in runs]

    def deep(k, m):
        return 1 if not m.get("re") else 1 + deep(k, by_id[k][m["re"]])

    def fits(k, m):
        """A line of the argument is in the words for who's saying it: the accused's denial, an answer to its denial,
        or another's on the accusation."""
        if not m.get("re"):
            return True
        to = by_id[k][m["re"]]
        again = bool(to.get("re"))
        which = (("cheat_mine" if again else "cheat_me") if m["name"] == "Kitchen" else "cheat_back"
                 if to["name"] == "Kitchen" else "cheat_more" if again else "cheat_re")
        return m["text"] in pool(which, about="Kitchen", speaker=to["name"])
    every = [(k, m) for k, r in enumerate(runs) for m in r]
    check(f"...and what's said after it is all of that argument, each in the words for its side, three lines deep at "
          f"most, none said twice ({[len(r) for r in runs]} lines)",
          all(m["topic"] == "cheat" and m["about"] == "Kitchen" and "{" not in m["text"] and deep(k, m) <= 3
              and fits(k, m) for k, m in every) and all(len({m["text"] for m in r}) == len(r) for r in runs))
    denied = sum(any(m["name"] == "Kitchen" for m in r) for r in runs)
    backs = sum(any(m.get("re") and by_id[k][m["re"]]["name"] == "Kitchen" for m in r) for k, r in enumerate(runs))
    sides = sum(any(m["name"] == "TV" for m in r) for r in runs)
    check(f"...the accused denies it, mostly ({denied} of 8); its denial's answered, often ({backs}); the third takes "
          f"a side, now and then ({sides})", denied >= 6 and backs >= 3 and 1 <= sides)
    for r in sorted(runs, key=len)[-3:]:
        print("       " + " / ".join(f"{m['name']}: {m['text']}" for m in r))
    made = circles(21)
    made["Den"].schedule(0, "cheat", {"about": "Kitchen", "wins": 3})
    go(made, 200)
    made["TV"].schedule(0, "cheat", {"about": "Kitchen", "wins": 4})
    go(made, 200)
    again = [m for m in made["Den"].lines() if m["topic"] == "cheat" and not m.get("re")]
    clock.t += C.CHEAT_GAP
    made["TV"].schedule(0, "cheat", {"about": "Kitchen", "wins": 5})
    go(made, 200)
    later = [m for m in made["Den"].lines() if m.get("topic") == "cheat" and not m.get("re")]
    check(f"they don't have that argument twice in a row ({len(again)}); a while on, they may ({len(later)})",
          len(again) == 1 and len(later) == 2 and later[1]["name"] == "TV")
    made = circles(22, talk=False)
    made["Den"].schedule(0, "cheat", {"about": "Kitchen", "wins": 3})
    go(made, 120)
    check("nor at all with the group chat quiet", made["Den"].lines() == [])
    made = circles(23)
    made["Den"].schedule(300, "cheat", {"about": "Kitchen", "wins": 3})
    won = made["Kitchen"].new("I got a cookie! Paper beats rock, Den.", topic="cookie", about="Den")
    made["Den"].rng = type("R", (), {"random": lambda self: 0.0, "uniform": lambda self, a, b: a})()
    made["Den"].receive(won)
    check("one that's about to say the winner's cheating doesn't answer its line about its cookie as well",
          [how for _, how, _ in made["Den"].jobs] == ["cheat"])
finally:
    C.time = real_time
asked = C.model_prompt("cheat", {"about": "Kitchen", "wins": 4, "members": [], "facts": []})
check(f"for a Bot with a model: what it's asked to say ({asked.strip()[:60]}...)", "Kitchen" in asked
      and "4 wins in a row" in asked and "cheating" in asked)
mine = C.model_prompt("reply", {"speaker": "Den", "said": "Kitchen got the cookie again!?", "about": "Kitchen",
                               "target_topic": "cheat", "me_about": True, "members": []})
side = C.model_prompt("reply", {"speaker": "Den", "said": "Kitchen got the cookie again!?", "about": "Kitchen",
                               "target_topic": "cheat", "members": []})
check("...the accused, to deny it; another, to take a side", "Deny it" in mine and "Take a side" in side
      and "Kitchen cheats" in side)

real = g.Media()
real.state["cookie"] = dict(real.state["cookie"], id=IB, rec=rec(7, IB, "Kitchen", "Den", "sp"), had=7, throws="rps",
                            beat="p", said=7, seen=123.0, wins=4)
real.save_state()
again = g.Media()
check(f"the cookie's kept: as it was, the next time Pietato starts ({again.state['cookie'].get('rec', {}).get('n')})",
      again.cookie_here() and again.state["cookie"]["id"] == IB and again.state["cookie"]["throws"] == "rps"
      and again.state["cookie"]["beat"] == "p" and again.state["cookie"]["said"] == 7
      and again.cookie_beacon()["rec"]["n"] == 7 and again.cookie_beacon()["wins"] == 4)
state = json.load(open(g.STATE_FILE))
state["cookie"] = {"id": "nope", "rec": {"n": "x"}, "had": "lots", "throws": 5, "beat": "z", "seen": "then",
                   "wins": -2}
json.dump(state, open(g.STATE_FILE, "w"))
again = g.Media()
check(f"...and one that's been spoilt isn't ({again.state['cookie']})", again.state["cookie"]
      == {"rec": None, "had": 0, "throws": "", "beat": "", "said": 0, "wins": 0, "seen": 0.0}
      and not again.cookie_here())
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))

# ---- its page --------------------------------------------------------------------------------------------------------
apps = next(t for t in g.LIBRARY if t["name"] == "Apps")["children"]
ci = next(k for k, t in enumerate(g.LIBRARY) if t["name"] == "The Cookie")
check(f"Apps has The Cookie, after Group chat ({apps[5:8]})", apps[apps.index("Group chat") + 1] == "The Cookie"
      and g.LIBRARY[ci]["sim"] == "cookie" and g.LIBRARY[ci]["parent"] == "Apps" and "The Cookie" in g.COOL_SKIP
      and g.app_named("the cookie") == "The Cookie")
toasts, SHOWN = [], []
A.load_fonts(); A.fb = FB(); A.active = True
A.toast = lambda text, secs=4: (toasts.append(text), SHOWN.append(text))[0]
real_page = A.cookie_page
A.cookie_page = lambda s: (real_page(s), SHOWN.extend(s.head), SHOWN.extend(r[1] for r in s.rows))[0]
A.status_sig = A.status_signature()
DOUGH = np.array(PG.COOKIE_DOUGH)


def shot(m=A):
    """The screen, drawn again (its status bar as the main loop's look at it, every couple of seconds, has it)."""
    m.status_sig = m.status_signature()
    m.dirty = True
    m.flush()
    return np.asarray(FB.last.convert("RGB")).astype(int)


def dough(pic, box):
    x0, y0, x1, y1 = box
    return int((np.abs(pic[y0:y1, x0:x1] - DOUGH).max(axis=2) < 12).sum())


def hints(s):
    return [k for k, _ in s.hints()]


tell()
A.cookie_news = None
A.open_app(ci)
s = A.sim_game()
page = shot()
check(f"opened: its page ({s.head})", s.key == "cookie" and A.cookie_tab() and A.cookie_shown() and s.bare and s.paced
      and FB.last.size == (640, 480))
check(f"this one got the last cookie: said, and one drawn at its top and in its row "
      f"({dough(page, (14, 78, 84, 156))} px, {dough(page, (580, 170, 630, 240))} px), its row first", s.here
      and s.head == ("Den got a cookie", "Its Bot beat TV just now, paper over rock.")
      and dough(page, (14, 78, 84, 156)) > 600 and dough(page, (580, 170, 630, 240)) > 60
      and [(r[0], r[1], r[4]) for r in s.rows]
      == [("Den", "This one", True), ("Kitchen", "", False), ("TV", "", False)])
check(f"...each one's last throws beside it, and nothing to throw for ({[r[3] for r in s.rows]}, {hints(s)})",
      [r[3] for r in s.rows]
      == [A.state["cookie"]["throws"], B.state["cookie"]["throws"], D.state["cookie"]["throws"]]
      and hints(s) == ["B"] and s.frame_in(0) == PG.COOKIE_STILL)
A.state["cookie"] = dict(A.state["cookie"], wins=3)
A.pie.heard[url_of(B)]["cookie"]["wins"] = 5
rows = A.sim_game().rows
check(f"three wins in a row, or more: said under its name ({rows[0][1]!r}, {rows[1][1]!r})",
      rows[0][1] == "This one, 3 wins in a row" and rows[1][1] == "5 wins in a row" and rows[2][1] == "")
A.state["cookie"] = dict(A.state["cookie"], wins=1)
A.pie.heard[url_of(B)]["cookie"]["wins"] = 0
bar = dough(page, (60, 2, 130, 26))
A.view = "home"
home = shot()
by_date = dough(home, (0, 60, 400, 110))
check(f"a small one on its status bar, and on its home screen after the date ({bar} px, {by_date} px)",
      bar > 20 and by_date > 30 and A.status_signature()[-1] == A.assist_status())
A.open_app(ci)
A.press("left")
check(f"a throw on the one that got the last: it's for the others to beat it ({toasts[-1:]})",
      toasts[-1:] == ["The others have to beat this one next"] and not A.cookie_trying)

# another's try, with its page open: your throw
SC.COOKIE_ANSWER = 30
B.cookie_tries.clear(); A.cookie_tries.clear()
throws(B, "r"); throws(A, "s")
B.cookie_wait = 0.0
B.cookie_try()


def until(cond, secs=20, each=jobs):
    end = time.time() + secs
    while time.time() < end:
        each()
        if cond():
            return True
        time.sleep(0.01)
    return bool(cond())


asked = until(lambda: A.cookie_ask is not None, each=lambda: jobs(A))
page = shot()
s = A.sim_game()
check(f"another's try, with its page open here: it waits for your throw ({s.head})", asked
      and s.head[0] == "Kitchen wants a cookie" and s.head[1].startswith("Throw to win another.")
      and hints(s) == ["◀", "▲", "▶"] and 0.05 <= s.frame_in(0) <= 1.0 and B.cookie_trying == "bot")
A.press("up")
check("...▲, paper: beats its rock, and this one gets another", settle() and A.cookie_here() and knows(B)[1] == IA
      and A.sim_game().head == ("Your paper beat Kitchen's rock", "Den got another cookie.")
      and A.state["cookie"]["throws"][-1:] != "s" and B.state["cookie"]["beat"] == "p")
B.cookie_tries.clear(); A.cookie_tries.clear()
throws(B, "p")
B.cookie_wait = 0.0
B.cookie_try()
asked = until(lambda: A.cookie_ask is not None, each=lambda: jobs(A))
A.next_status = 99.0
A.press("left")
done = settle()
r = A.state["cookie"]["rec"]
check(f"...◀, rock, against paper: lost, and it gets a cookie ({A.sim_game().head})", asked and done
      and not A.cookie_here() and B.cookie_here() and r["how"] == "pr" and r["from"] == "Den"
      and A.sim_game().head == ("Kitchen's paper beat your rock", "Kitchen got a cookie."))
check("...its status bar looked at again at once (the small cookie's gone from it)", A.next_status == 0.0)
page = shot()
A.view = "home"
home = shot()
A.open_app(ci)
check("...gone from its top, its status bar, its home screen and its row: the plate it was on, and Kitchen's row has "
      "it, with how it came by it",
      dough(page, (14, 78, 84, 156)) == 0 and dough(page, (60, 2, 130, 26)) == 0 and not A.sim_game().here
      and dough(home, (0, 60, 400, 110)) == 0
      and [r[:2] + r[4:5] for r in A.sim_game().rows]
      == [("Den", "This one", False), ("Kitchen", "Beat Den just now", True), ("TV", "", False)])

# your try for it
tell()
A.cookie_news = None
s = A.sim_game()
check(f"another got the last: who, and your buttons ({s.head}, {hints(s)})", s.head
      == ("Kitchen got a cookie", "Beat it at rock paper scissors to win one.") and hints(s) == ["◀", "▲", "▶"])
A.cookie_tries.clear(); B.cookie_tries.clear()
throws(B, "r")
POSTS.clear()
A.press("right")
check("▶, scissors: your throw, sent as yours", A.cookie_trying == "you" and settle()
      and POSTS[-1][1]["throw"] == "s" and POSTS[-1][1]["you"] is True)
s = A.sim_game()
check(f"...its rock beats them: it gets another, and you can't throw again at once ({s.head})",
      s.head[0] == "Kitchen's rock beat your scissors"
      and s.head[1].startswith("Kitchen got another cookie. Again in ")
      and B.cookie_here() and 0.05 <= s.frame_in(0) <= 1.0 and A.state["cookie"]["throws"][-1:] != "s")
n = len(POSTS)
toasts.clear()
A.press("up")
check(f"...a throw meanwhile isn't sent ({toasts})", len(POSTS) == n and toasts and toasts[0].startswith("Again in "))
A.cookie_wait = 0.0
B.cookie_tries.clear()
A.press("up")
done = settle()
check(f"▲, paper, once you may: beats its rock, and this one gets a cookie ({A.sim_game().head})", done
      and A.cookie_here()
      and not B.cookie_here() and A.sim_game().head == ("Your paper beat Kitchen's rock", "Den got a cookie!")
      and A.state["cookie"]["rec"]["you"] is True and knows(B)[1] == IA)
check(f"...this one says so in the group chat, as the two of you ({chat(A)[-1]['text']!r})",
      chat(A)[-1]["text"].startswith("We ") and "Kitchen" in chat(A)[-1]["text"])
A.cookie_news = None
check(f"...and its page says how ({A.sim_game().head})", A.sim_game().head
      == ("Den got a cookie", "You beat Kitchen just now, paper over rock."))

# its Bot's, if you don't throw; and with its page shut
SC.COOKIE_ANSWER = 0.3
B.cookie_tries.clear(); A.cookie_tries.clear()
throws(B, "p"); throws(A, "s")
B.cookie_wait = 0.0
B.cookie_try()
check("another's try you don't answer: this one's Bot throws for it", settle() and A.cookie_here()
      and A.state["cookie"]["throws"][-1:] == "s" and A.cookie_ask is None
      and A.sim_game().head[0] == "This one's scissors beat Kitchen's paper")
A.view = "home"
A.cookie_tries.clear()
SC.COOKIE_ANSWER = 30
got = A.web_cookie({"from": "10.0.0.22", "id": IB, "name": "Kitchen", "n": A.state["cookie"]["rec"]["n"],
                    "throw": "p", "you": False})
check("...as it does at once with its page shut (nothing's asked of you elsewhere)", got["got"] == "lost"
      and got["mine"] == "s" and A.cookie_ask is None)
jobs()
A.open_app(ci)
check("B, L and R are any app's; START and SELECT do nothing here (no full screen: its buttons are along the bottom)",
      A.press_cookie(A.sim_game(), "b", False) is False and A.press_cookie(A.sim_game(), "l", False) is False
      and A.press_cookie(A.sim_game(), "start", False) is None and A.sim_opts is None
      and (A.state["settings"].update(sim_full="On") or not A.sim_full()))
A.state["settings"]["sim_full"] = "Off"

# what's said of it, popping up
A.you_noticed()
A.view = "home"
A.group_pops.clear(); A.group_pop = None
msg = C.clean_msg(dict(chat(B)[-1], id="d" * 16, t=time.time()))
A.group_heard(msg)
on_home = len(A.group_pops) + (A.group_pop is not None)
A.group_pops.clear(); A.group_pop = None
A.open_app(ci)
A.group_heard(msg)
check("a line about the cookie pops up where you are, as any line does; not on its page, which says so already",
      on_home == 1 and not A.group_pops and A.group_pop is None)

# the rest of its page's words
A.cookie_news = None
A.state["cookie"] = dict(A.state["cookie"], rec=rec(9, IC, "TV", "Den", "left"))
A.pie.heard[url_of(D)]["seen"] = time.time() - 500
s = A.sim_game()
check(f"the one that got the last, off: said, and its row ({s.head})", s.head
      == ("TV got a cookie", "It's off. After an hour off, another gets one.") and hints(s) == ["B"]
      and ("TV", "Off", None, "", True, False) in s.rows)
A.pie.hear("10.0.0.24", {"pietato": 1, "id": "e" * 12, "port": 5432, "host": "Attic", "accent": "", "hw": {"b": "Pi 3"},
                         "doing": "on"})
check("one of yours that hasn't been updated: it's there, and why it doesn't play",
      ("Attic", "Update it to play", None, "", False, True) in A.sim_game().rows)
A.state["cookie"] = dict(A.state["cookie"], rec=None)
check(f"none yet ({A.sim_game().head[0]!r})", A.sim_game().head[0] == "No cookie yet" and not A.sim_game().here)
for u in list(A.pie.heard):
    A.pie.heard[u]["seen"] = time.time() - 500
s = A.sim_game()
check(f"no other on ({s.head[0]!r}): nothing listed", s.head[0] == "It needs two Pietatos" and s.rows == []
      and hints(s) == ["B"])
A.state["settings"]["share"] = "Off"
A.state["cookie"] = dict(A.state["cookie"], rec=rec(9, A.state["cookie"]["id"], "Den"))
check(f"sharing off ({A.sim_game().head[0]!r}): out of it, and no small cookie on its bar",
      A.sim_game().head[0] == "Sharing is off" and not A.cookie_here() and A.share_beacon("Den", full=True)["cookie"])
A.state["settings"]["share"] = "On"
shot()
words = sorted({x for x in SHOWN if x} | {x["text"] for m in ALL for x in chat(m)})
check(f"all its page showed and all they said of it here ({len(words)} lines): never of a cookie taken or kept",
      len(words) > 25 and not [x for x in words if BAD.search(x)])
for x in words:
    print(f"       {x}")
A.press("b")
check("B: back to Apps' list, The Cookie picked", A.view == "list" and g.LIBRARY[A.tab]["name"] == "Apps"
      and A.tab_items()[A.sels[A.tab]]["title"] == "The Cookie")
SC.post_json = real_post

# ---- for real: a try sent to another Pietato's web page ------------------------------------------------------------
sys.path.append(ROOT + "/pitato")
import webui  # noqa: E402
r = webui.app.test_client().post("/api/cookie", data="rock", content_type="text/plain")
check(f"the web page takes a try from your network without its password, and only a try ({r.status_code})",
      r.status_code == 400 and "/api/cookie" in webui.PEER_PATHS)
procs = []


def start(name, **env):
    home = f"{S}/{name}"
    os.makedirs(home, exist_ok=True)
    p = subprocess.Popen([sys.executable, TESTS + "/peer_pietato.py", home, f"{S}/{name}.log", name,
                          "http://127.0.0.1:1", "none"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                         bufsize=1, env=dict(os.environ, **env))
    line = p.stdout.readline().split()
    procs.append(p)
    return p, (line[1] if line[:1] == ["READY"] else None)


def do(p, line):
    p.stdin.write(line + "\n")
    p.stdin.flush()
    return p.stdout.readline().strip()


M = g.Media()
M.state["settings"].update(name="Den")
M.cookie_try_at = time.monotonic() + 1e6
M.pie.heard.clear(); M.pie.peers_kept.clear()      # (the three above aren't its others)
try:
    tv, tv_url = start("tv", PITATO_COOKIE_BOT="r", PITATO_COOKIE_GAP="0")
    check(f"another Pietato up ({tv_url})", bool(tv_url))
    port = int(tv_url.rsplit(":", 1)[1])

    def hear_tv():
        M.pie.hear("127.0.0.1", json.loads(do(tv, "beacon")))

    do(tv, "hear " + json.dumps(dict(M.share_beacon("Den", full=True), port=5432)))
    hear_tv()
    there = json.loads(do(tv, "cookie look"))
    check(f"it has heard this one, and bakes the cookie ({there.get('rec')})", there["here"] and there["rec"]["n"] == 1)
    hear_tv()
    M.cookie_look(time.monotonic())
    jobs(M)
    check("...which this one hears of", knows(M) == (1, there["id"]) and not M.cookie_here())

    def try_it(way):
        """Your throw for it, sent, and answered: what its page then says at its top (None: not answered)."""
        M.cookie_wait = 0.0
        if M.cookie_try(way) and until(lambda: not M.cookie_trying, 30, each=lambda: jobs(M)):
            return (M.cookie_news or {}).get("head")
        return None

    said = try_it("s")
    check(f"a try sent to its web page: scissors against its rock, lost ({said})",
          said == "tv's rock beat your scissors" and not M.cookie_here() and json.loads(do(tv, "cookie"))["here"])
    said = try_it("r")
    check(f"...rock: a tie ({said})", said == "Both threw rock" and not M.cookie_here())
    said = try_it("p")
    there = json.loads(do(tv, "cookie"))
    check(f"...paper: the cookie's here, and it says the same ({there.get('rec')})", M.cookie_here()
          and said == "Your paper beat tv's rock" and not there["here"]
          and there["rec"]["n"] == 2 and there["rec"]["at"] == M.state["cookie"]["id"]
          and there["rec"]["name"] == "Den" and there["rec"]["how"] == "pr" and there["throws"] == "rrr")
    said = until(lambda: [x for x in json.loads(do(tv, "group log")) if x.get("topic") == "cookie"
                          and x["name"] == "Den"], 20, each=lambda: jobs(M))
    check("...and what this one says of it in the group chat gets there", said)
    got = real_post(f"{tv_url}/api/cookie", {"id": "f" * 16, "name": "x", "n": 2, "throw": "r"}, timeout=10)
    check(f"asked for one it hasn't got: told so, through its web page ({got.get('got')})", got.get("got") == "gone"
          and got["rec"]["n"] == 2)
finally:
    for p in procs:
        try:
            p.stdin.write("quit\n")
            p.stdin.flush()
        except OSError:
            pass
    for p in procs:
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
