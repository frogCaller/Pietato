"""Game saves, each Pietato's own (savesync.py, Settings > Share with other Pietatos): none of your others' ever takes
their place. A game come from another of yours is a guest: its saves in a folder of their own (Games/Saves/.guests),
with a note of whose game it is and what it came on from. A lot of saves taken from another Pietato: all of them that
aren't the same already, or none (one that doesn't come whole changes nothing); what they take the place of, and what
the other hasn't got, kept in .replaced; their age kept (two Pis' clocks needn't agree); whose they are, the Games
folder's owner's. This Pietato's own game, played on as a guest on another of yours, comes home: only on from where
this one left it (played here since, its own save stays), the newest when two have it, not from one playing it now,
one with sharing off, one from before saves were each Pietato's own, or one that answers nonsense. A guest that's gone
home (or was sent on) is let go of. And the web page's part: a game's saves listed and handed out to your network
only, without the page's password (this one's own and each guest's, never where they are on the Pi, never anything but
a game's own saves, nothing while sharing's off or what's asked for is being played); the news that a game's been
played on passed on with who sent it. Then for real: two Pietatos, one's web page on a port of its own, and this one's
media mode: a game started here is this one's own save, whatever the other has; its own game come home first when the
other played it on; a guest here asked about as the game's started (whose game: ◀▶, A; X twice forgets it); the
other's told when a guest's been played here, and one gone home is let go of."""
import io, json, os, pwd, shutil, sys, threading, time, urllib.parse, urllib.request
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from pitato import savesync as SS

S = SP + "/t_save_sync"
shutil.rmtree(S, ignore_errors=True)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def put(folder, name, data, ago):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    open(path, "wb").write(data)
    t = time.time() - ago
    os.utime(path, (t, t))
    return path


GAME = "Pokemon - Emerald Version (USA)"
ME, TV, DEN, PI4 = "aaaa1111bbbb2222", "cccc3333dddd4444", "eeee5555ffff6666", "0123456789abcdef"
HERE = S + "/here/Saves"
URLS = {"tv": "http://192.168.1.22:5432", "den": "http://192.168.1.23:5432", "pi4": "http://192.168.1.21:5432"}
OTHERS = {URLS["tv"]: S + "/tv/Saves", URLS["den"]: S + "/den/Saves", URLS["pi4"]: S + "/pi4/Saves"}
IDS = {URLS["tv"]: TV, URLS["den"]: DEN, URLS["pi4"]: PI4}
NAMES = {u: n for n, u in URLS.items()}
PEERS = [(u, NAMES[u]) for u in OTHERS]
state = {"off": set(), "playing": set(), "nonsense": set(), "old": set(), "broken": set(), "asked": [], "fetched": []}


def says(base, name):
    """What the Pietato at base says of a game's saves, as its web page does."""
    saves = OTHERS[base]
    guests = {whose: {"from": gst["from"], "base": gst["base"], "files": gst["files"],
                      "playing": (base, whose) in state["playing"]}
              for whose, gst in SS.guests_of(saves, name).items()}
    return {"ok": True, "on": True, "id": IDS[base], "name": NAMES[base], "playing": (base, "") in state["playing"],
            "files": {}, "own": SS.save_files(saves, name), "guests": guests}


def fake_ask(url):
    base, _, q = url.partition("/api/saves?game=")
    state["asked"].append(base)
    name = urllib.parse.unquote(q)
    if base in state["nonsense"]:
        return {"on": True, "id": IDS[base], "own": {".srm": {"size": -1, "age": "old", "sum": "x"}, "../x": {}},
                "guests": {"../x": 7, ME: {"files": {".srm": {"size": 3, "age": 1, "sum": "zz"}}, "base": "x"}}}
    if base in state["off"]:
        return {"ok": True, "on": False}
    if base in state["old"]:                           # (one from before saves were each Pietato's own)
        return {"ok": True, "on": True, "playing": False, "files": SS.save_files(OTHERS[base], name)}
    return says(base, name)


def fake_fetch(url, dest, size):
    base, _, q = url.partition("/api/saves/file?")
    a = dict(urllib.parse.parse_qsl(q))
    state["fetched"].append((base, a["ext"], a.get("whose", "")))
    folder = SS.guest_dir(OTHERS[base], a["whose"]) if a.get("whose") else OTHERS[base]
    data = open(os.path.join(folder, a["game"] + a["ext"]), "rb").read()
    if base in state["broken"] and a["ext"] == ".state.auto":
        data = data[:-1] + b"?"                     # (cut short on its way, as it were: the sum says so)
    open(dest, "wb").write(data)
    return len(data) == size


def here(ext, folder=HERE):
    try:
        return open(os.path.join(folder, GAME + ext), "rb").read()
    except OSError:
        return None


def age(ext, folder=HERE):
    return time.time() - os.stat(os.path.join(folder, GAME + ext)).st_mtime


def home(**kw):
    state["asked"], state["fetched"] = [], []
    return SS.home(HERE, GAME, ME, PEERS, ask=fake_ask, fetch=fake_fetch, **kw)


def guest_at(base, whose, files, ago, came_on_from, who="gpi", via="gpi"):
    """A guest on the Pietato at base: whose game it is, its saves, what it came on from."""
    folder = SS.guest_dir(OTHERS[base], whose)
    for ext, data in files.items():
        put(folder, GAME + ext, data, ago)
    SS.guest_keep(OTHERS[base], whose, GAME, who, via, came_on_from)


# ---- names --------------------------------------------------------------------------------------------------
check("a game's name for its saves: a plain file name only",
      SS.game_name(GAME) == GAME and not any(SS.game_name(n) for n in
      ("", "../x", "a/b", ".hidden", " spaced", "a\0b", "x" * 201, 7, None, ".", "..")))
check("a Pietato's word for itself: a few plain letters and figures only", SS.whose_id(ME) == ME
      and not any(SS.whose_id(x) for x in ("", "abc", "../abcdef", "ABCDEF12", "a" * 33, 7, None, "abc def")))

# ---- a lot of saves taken from another Pietato ------------------------------------------------------------------
put(HERE, GAME + ".srm", b"here srm", 5000)
put(HERE, GAME + ".state.auto", b"here state", 5000)
put(HERE, GAME + ".state", b"here slot", 5000)                      # (a save state of yours: the TV hasn't one)
put(OTHERS[URLS["tv"]], GAME + ".srm", b"tv srm", 300)
put(OTHERS[URLS["tv"]], GAME + ".state.auto", b"tv state", 300)
put(OTHERS[URLS["tv"]], GAME + ".rtc", b"tv clock", 300)
put(OTHERS[URLS["tv"]], "Other Game (USA).srm", b"another game", 10)
for u in (URLS["den"], URLS["pi4"]):
    os.makedirs(OTHERS[u], exist_ok=True)
DEST = S + "/dest"
theirs = SS.save_files(OTHERS[URLS["tv"]], GAME)
took = SS.take(DEST, GAME, URLS["tv"], theirs, fetch=fake_fetch)
check(f"a lot of saves taken into a folder of their own: all of them, and nothing of another game "
      f"({sorted(e for _, e, _ in state['fetched'])})", took is True
      and sorted(e for _, e, _ in state["fetched"]) == [".rtc", ".srm", ".state.auto"]
      and sorted(os.listdir(DEST)) == [GAME + ".rtc", GAME + ".srm", GAME + ".state.auto"]
      and here(".srm", DEST) == b"tv srm")
check(f"...as old as they are there (not just made: {age('.srm', DEST):.0f} s)", 290 < age(".srm", DEST) < 320)
state["fetched"] = []
check("...again: the same now, so nothing comes", SS.take(DEST, GAME, URLS["tv"], theirs, fetch=fake_fetch) is True
      and state["fetched"] == [])
put(DEST, GAME + ".state", b"a slot of its own", 400)
put(OTHERS[URLS["tv"]], GAME + ".srm", b"tv srm, newer", 20)
os.remove(os.path.join(OTHERS[URLS["tv"]], GAME + ".rtc"))
theirs = SS.save_files(OTHERS[URLS["tv"]], GAME)
state["fetched"] = []
took = SS.take(DEST, GAME, URLS["tv"], theirs, fetch=fake_fetch)
kept = DEST + "/.replaced"
check(f"...one of them newer there, one gone, one there's none of there: just the newer one comes "
      f"({state['fetched']}), and the folder ends with just what the other has ({sorted(os.listdir(DEST))})",
      took and [e for _, e, _ in state["fetched"]] == [".srm"] and here(".srm", DEST) == b"tv srm, newer"
      and sorted(f for f in os.listdir(DEST) if not f.startswith(".")) == [GAME + ".srm", GAME + ".state.auto"])
check(f"...what was replaced, and what the other hasn't: kept ({sorted(os.listdir(kept))})",
      sorted(os.listdir(kept)) == [GAME + ".rtc", GAME + ".srm", GAME + ".state"]
      and open(f"{kept}/{GAME}.srm", "rb").read() == b"tv srm"
      and open(f"{kept}/{GAME}.state", "rb").read() == b"a slot of its own")
check("...and nothing left over on the way", not [f for f in os.listdir(DEST) if f.endswith(".part")])
put(OTHERS[URLS["tv"]], GAME + ".srm", b"tv srm 3", 10)
put(OTHERS[URLS["tv"]], GAME + ".state.auto", b"tv state 3", 10)
state["broken"].add(URLS["tv"])
took = SS.take(DEST, GAME, URLS["tv"], SS.save_files(OTHERS[URLS["tv"]], GAME), fetch=fake_fetch)
check(f"one of them doesn't come whole: none taken, the folder as it was ({took}, {here('.srm', DEST)!r})",
      took is False and here(".srm", DEST) == b"tv srm, newer" and here(".state.auto", DEST) == b"tv state"
      and not [f for f in os.listdir(DEST) if f.endswith(".part")])
state["broken"].clear()
try:
    owner = pwd.getpwnam("gpitest")
    took = SS.take(DEST, GAME, URLS["tv"], SS.save_files(OTHERS[URLS["tv"]], GAME), fetch=fake_fetch,
                   owner=(owner.pw_uid, owner.pw_gid))
    st = os.stat(os.path.join(DEST, GAME + ".srm"))
    check(f"taken as the Games folder's owner's ({took}, {st.st_uid})", took and st.st_uid == owner.pw_uid
          and os.stat(kept).st_uid == owner.pw_uid and os.stat(DEST).st_uid == owner.pw_uid)
except KeyError:
    print("(no gpitest user here: whose they are, not looked at)")
check("...never for a name that isn't one", SS.take(DEST, "../x", URLS["tv"], {}, fetch=fake_fetch) is False)

# ---- guests: another Pietato's game here, apart ------------------------------------------------------------------
mine = SS.sums(SS.save_files(HERE, GAME))
check("no guests here yet", SS.guests_of(HERE, GAME) == {} and SS.guests_held(HERE) == []
      and SS.guest_note(HERE, TV, GAME) is None)
put(SS.guest_dir(HERE, TV), GAME + ".srm", b"the tv's game, here", 60)
check("...its saves alone, with no note: not a guest", SS.guests_of(HERE, GAME) == {})
SS.guest_keep(HERE, TV, GAME, "  tv \n", "den", {".srm": "0" * 40, ".txt": "0" * 40, ".rtc": "not a sum"})
got = SS.guests_of(HERE, GAME)
check(f"a guest: whose game it is, the one it came here from, what it came on from, its saves ({got})",
      list(got) == [TV] and got[TV]["from"] == "tv" and got[TV]["via"] == "den"
      and got[TV]["base"] == {".srm": "0" * 40} and list(got[TV]["files"]) == [".srm"]
      and SS.guests_held(HERE) == [(TV, GAME)])
check("...this Pietato's own saves: as they were", SS.sums(SS.save_files(HERE, GAME)) == mine
      and here(".srm") == b"here srm")
check("...never one with a name that isn't one, or for nobody", SS.guest_note(HERE, "../x", GAME) is None
      and SS.guest_note(HERE, TV, "../x") is None and SS.guests_of(HERE, "../x") == {})
SS.guest_gone(HERE, TV, GAME)
check(f"a guest let go of: not one any more, its saves kept beside ({os.listdir(SS.guest_dir(HERE, TV))})",
      SS.guests_of(HERE, GAME) == {} and SS.guests_held(HERE) == []
      and open(f"{SS.guest_dir(HERE, TV)}/.replaced/{GAME}.srm", "rb").read() == b"the tv's game, here")

# ---- what another Pietato says it has -----------------------------------------------------------------------------
said = SS.clean_answer(says(URLS["tv"], GAME))
check(f"what another says it has: its word for itself, its own saves, its guests ({said and sorted(said)})",
      said["id"] == TV and said["name"] == "tv" and sorted(said["own"]) == [".srm", ".state.auto"]
      and said["guests"] == {} and said["playing"] is False)
state["nonsense"].add(URLS["tv"])
said = SS.clean_answer(fake_ask(URLS["tv"] + "/api/saves?game=" + urllib.parse.quote(GAME)))
check(f"...nonsense: only as much of it as makes sense ({said})", said == {"id": TV, "name": "", "playing": False,
                                                                           "own": {}, "guests": {}})
state["nonsense"].clear()
state["old"].add(URLS["tv"])
said = SS.clean_answer(fake_ask(URLS["tv"] + "/api/saves?game=" + urllib.parse.quote(GAME)))
check(f"...one from before saves were each Pietato's own (it lists its own as anyone's to take): nothing of its "
      f"({said})", said == {"id": None, "name": "", "playing": False, "own": {}, "guests": {}})
state["old"].clear()
check("...one with sharing off, or that says nothing: none", SS.clean_answer({"ok": True, "on": False}) is None
      and SS.clean_answer(None) is None and SS.clean_answer("x") is None)

# ---- this Pietato's own game, come home -----------------------------------------------------------------------------
came = home()
check(f"nobody has played this one's game on: nothing comes, whatever they have of their own ({came}, "
      f"{state['fetched']})", came is None and state["fetched"] == [] and here(".srm") == b"here srm"
      and sorted(state["asked"]) == sorted(OTHERS))
guest_at(URLS["tv"], ME, {".srm": b"mine, on the tv", ".state.auto": b"where I was on the tv"}, 120, mine)
came = home()
check(f"the TV played it on, from just where this one left it: home from the TV ({came}, "
      f"{sorted(state['fetched'])})", came == "tv"
      and sorted(state["fetched"]) == [(URLS["tv"], ".srm", ME), (URLS["tv"], ".state.auto", ME)]
      and here(".srm") == b"mine, on the tv" and here(".state.auto") == b"where I was on the tv")
kept = HERE + "/.replaced"
check(f"...what they replaced, and the save state the guest hasn't: kept ({sorted(os.listdir(kept))})",
      open(f"{kept}/{GAME}.srm", "rb").read() == b"here srm" and here(".state") is None
      and open(f"{kept}/{GAME}.state", "rb").read() == b"here slot")
check(f"...as old as they are there ({age('.srm'):.0f} s)", 110 < age(".srm") < 140)
came = home()
check(f"again: it's home, so nothing comes ({came})", came is None and state["fetched"] == [])
check("...and that's what the TV's guest is now: this one's own", SS.is_home(
    SS.guests_of(OTHERS[URLS["tv"]], GAME)[ME]["files"],
    {"id": ME, "own": SS.save_files(HERE, GAME), "guests": {}}, ME))

# played here since the guest left: its own save stays
put(HERE, GAME + ".srm", b"played here since", 1)
guest_at(URLS["tv"], ME, {".srm": b"the tv went on", ".state.auto": b"further on the tv"}, 50, mine)
came = home()
check(f"played here since it left: the TV's guest came on from something else, so nothing comes ({came})",
      came is None and state["fetched"] == [] and here(".srm") == b"played here since")
mine = SS.sums(SS.save_files(HERE, GAME))
guest_at(URLS["tv"], ME, {".srm": b"the tv went on", ".state.auto": b"further on the tv"}, 50, mine)
guest_at(URLS["den"], ME, {".srm": b"the den, newer"}, 5, mine)
came = home()
check(f"two of them have played it on from here: the newer one's ({came})", came == "den"
      and here(".srm") == b"the den, newer" and here(".state.auto") is None)
for ext in (".srm",):
    put(HERE, GAME + ext, b"back again", 9000)
mine = SS.sums(SS.save_files(HERE, GAME))
guest_at(URLS["tv"], ME, {".srm": b"tv 4", ".state.auto": b"tv 4 state"}, 50, mine)
guest_at(URLS["den"], ME, {".srm": b"den 4"}, 500, mine)
state["playing"].add((URLS["tv"], ME))
came = home()
check(f"the TV playing it now (its saves still changing): the den's instead ({came})", came == "den"
      and here(".srm") == b"den 4")
state["playing"].clear()
put(HERE, GAME + ".srm", b"back again", 9000)
mine = SS.sums(SS.save_files(HERE, GAME))
guest_at(URLS["tv"], ME, {".srm": b"tv 5"}, 50, mine)
shutil.rmtree(SS.guest_dir(OTHERS[URLS["den"]], ME))
state["off"].add(URLS["tv"])
check(f"the TV's sharing off: from none ({home()})", home() is None and here(".srm") == b"back again")
state["off"].clear()
state["old"].add(URLS["tv"])
check("one from before saves were each Pietato's own: nothing of its", home() is None
      and here(".srm") == b"back again")
state["old"].clear()
state["nonsense"].add(URLS["den"])
came = home()
check(f"one answering nonsense: let be, the others still asked ({came})", came == "tv" and here(".srm") == b"tv 5")
state["nonsense"].clear()
put(HERE, GAME + ".srm", b"back again", 9000)
mine = SS.sums(SS.save_files(HERE, GAME))
guest_at(URLS["tv"], TV + "0", {".srm": b"someone else's game"}, 5, mine)
shutil.rmtree(SS.guest_dir(OTHERS[URLS["tv"]], ME))
check("another Pietato's guest there, even one that came on from just this: not this one's to take",
      home() is None and here(".srm") == b"back again")
check("...nor for a name or a Pietato that isn't one", SS.home(HERE, "../x", ME, PEERS, ask=fake_ask) is None
      and SS.home(HERE, GAME, "../x", PEERS, ask=fake_ask) is None and SS.home(HERE, GAME, ME, []) is None)

# a guest that's gone home, or was sent on
files = SS.save_files(HERE, GAME)
check("a guest gone home, or sent on: known by its saves being just the same there",
      SS.is_home(files, {"id": ME, "own": files, "guests": {}}, ME)
      and not SS.is_home(files, {"id": TV, "own": files, "guests": {}}, ME)
      and not SS.is_home(files, {"id": ME, "own": {}, "guests": {}}, ME) and not SS.is_home({}, None, ME)
      and SS.is_there(files, {"id": TV, "own": {}, "guests": {ME: {"files": files}}}, ME)
      and not SS.is_there(files, {"id": TV, "own": files, "guests": {}}, ME))

# telling the others
told = []
n = SS.tell_home(GAME, TV, PEERS, post=lambda url, body: told.append((url, body)))
check(f"a guest played here: the others told whose game it is ({n})", n == 3
      and told[0] == (URLS["tv"] + "/api/saves/home", {"game": GAME, "whose": TV}))
check("...never for a name or a Pietato that isn't one", SS.tell_home("../x", TV, PEERS, post=lambda u, b: 1 / 0) == 0
      and SS.tell_home(GAME, "x", PEERS, post=lambda u, b: 1 / 0) == 0)

# ---- the web page's part ------------------------------------------------------------------------------------------
H = S + "/webhome"
os.makedirs(H + "/Games/Saves")
os.environ["HOME"] = H
sys.path.insert(0, ROOT)
sys.path.append(ROOT + "/pitato")
import webui  # noqa: E402
webui.HOME = H
webui.STATIC = H + "/pietato/static"
os.makedirs(webui.STATIC + "/fonts")
web_saves = H + "/Games/Saves"
put(web_saves, GAME + ".srm", b"web srm", 60)
put(web_saves, GAME + ".state.auto", b"web state", 60)
put(web_saves, "secret.txt", b"not a save", 60)
put(SS.guest_dir(web_saves, ME), GAME + ".srm", b"web guest srm", 30)
put(SS.guest_dir(web_saves, ME), "secret.txt", b"not a save either", 30)
SS.guest_keep(web_saves, ME, GAME, "gpi", "gpi", {".srm": "1" * 40})
media = {"share": "On", "playing": None, "news": []}


def fake_pi(method, path, body=None, timeout=10, ctype="application/json", keep=()):
    u = urllib.parse.urlsplit(path)
    if method == "GET" and u.path == "/saves":
        name = SS.game_name(dict(urllib.parse.parse_qsl(u.query)).get("game"))
        if name is None:
            out = {"ok": False, "error": "Which game?"}
        elif media["share"] == "Off":
            out = {"ok": True, "on": False}
        else:                                          # (as media mode's web_saves says it)
            guests = {whose: {"from": gst["from"], "base": gst["base"], "files": gst["files"],
                              "playing": media["playing"] == (name, whose), "folder": SS.guest_dir(web_saves, whose)}
                      for whose, gst in SS.guests_of(web_saves, name).items()}
            out = {"ok": True, "on": True, "id": TV, "name": "tv", "playing": media["playing"] == (name, ""),
                   "files": {}, "own": SS.save_files(web_saves, name), "guests": guests, "folder": web_saves}
        return 200, json.dumps(out).encode(), "application/json"
    if method == "POST" and u.path in ("/savenews", "/savehome"):
        media["news"].append((u.path, body))
        return 200, b'{"ok": true}', "application/json"
    return 404, b"{}", "application/json"


webui.ask_pi = fake_pi
c = webui.app.test_client()
NET = {"base_url": "http://192.168.1.30:5432", "environ_base": {"REMOTE_ADDR": "192.168.1.21"}}
FAR = {"base_url": "http://192.168.1.30:5432", "environ_base": {"REMOTE_ADDR": "8.8.8.8"}}
open(webui.STATIC + "/webui.txt", "w").write("password = hunter2\n")   # (the page has a password: not for these)
r = c.get("/api/saves?game=" + urllib.parse.quote(GAME), **NET)
got = r.get_json()
check(f"a game's saves, to your network, without the page's password: this one's own (their sizes, ages and sums) "
      f"and each guest's ({r.status_code})", r.status_code == 200 and got["on"] and got["id"] == TV
      and sorted(got["own"]) == [".srm", ".state.auto"] and got["own"][".srm"]["size"] == 7
      and 50 < got["own"][".srm"]["age"] < 90 and list(got["guests"]) == [ME]
      and got["guests"][ME]["base"] == {".srm": "1" * 40} and got["guests"][ME]["files"][".srm"]["size"] == 13)
check("...nothing for one from before saves were each Pietato's own to take", got["files"] == {})
check("...and not where they are on the Pi", "folder" not in got and "folder" not in got["guests"][ME])
r = c.get("/api/saves/file?" + urllib.parse.urlencode({"game": GAME, "ext": ".srm"}), **NET)
check(f"...one of its own handed out ({r.status_code})", r.status_code == 200 and r.data == b"web srm")
r = c.get("/api/saves/file?" + urllib.parse.urlencode({"game": GAME, "ext": ".srm", "whose": ME}), **NET)
check(f"...and one of a guest's ({r.status_code})", r.status_code == 200 and r.data == b"web guest srm")
check("...not to anywhere else", c.get("/api/saves?game=x", **FAR).status_code == 403
      and c.get("/api/saves/file?game=x&ext=.srm", **FAR).status_code == 403
      and c.post("/api/saves/home", json={"game": GAME, "whose": ME}, **FAR).status_code == 403)
check("...never anything but a game's own saves, its own or a guest's",
      all(c.get("/api/saves/file?" + urllib.parse.urlencode(q), **NET).status_code == 404 for q in
          ({"game": "secret", "ext": ".txt"}, {"game": GAME, "ext": ".bak"}, {"game": "../" + GAME, "ext": ".srm"},
           {"game": GAME + "/..", "ext": ".srm"}, {"game": GAME, "ext": ""}, {"game": "missing", "ext": ".srm"},
           {"game": "secret", "ext": ".txt", "whose": ME}, {"game": GAME, "ext": ".guest", "whose": ME},
           {"game": GAME, "ext": ".srm", "whose": TV}, {"game": GAME, "ext": ".srm", "whose": "../" + ME},
           {"game": GAME, "ext": ".state.auto", "whose": ME}, {"game": GAME, "ext": ".srm", "whose": ".."})))
media["playing"] = (GAME, "")
check("...not this one's own while it's being played here: a guest's still",
      c.get("/api/saves/file?" + urllib.parse.urlencode({"game": GAME, "ext": ".srm"}), **NET).status_code == 404
      and c.get("/api/saves?game=" + urllib.parse.quote(GAME), **NET).get_json()["playing"] is True
      and c.get("/api/saves/file?" + urllib.parse.urlencode({"game": GAME, "ext": ".srm", "whose": ME}),
                **NET).status_code == 200)
media["playing"] = (GAME, ME)
got = c.get("/api/saves?game=" + urllib.parse.quote(GAME), **NET).get_json()
check("...nor a guest's while that's being played: this one's own still",
      got["playing"] is False and got["guests"][ME]["playing"] is True
      and c.get("/api/saves/file?" + urllib.parse.urlencode({"game": GAME, "ext": ".srm", "whose": ME}),
                **NET).status_code == 404
      and c.get("/api/saves/file?" + urllib.parse.urlencode({"game": GAME, "ext": ".srm"}), **NET).status_code == 200)
media["playing"], media["share"] = None, "Off"
check("...nor with sharing off", c.get("/api/saves?game=" + urllib.parse.quote(GAME), **NET).get_json() == {"ok": True, "on": False}
      and c.get("/api/saves/file?" + urllib.parse.urlencode({"game": GAME, "ext": ".srm"}), **NET).status_code == 404
      and c.get("/api/saves/file?" + urllib.parse.urlencode({"game": GAME, "ext": ".srm", "whose": ME}),
                **NET).status_code == 404)
media["share"] = "On"
r = c.post("/api/saves/home", json={"game": GAME, "whose": ME}, **NET)
check(f"a guest played on: the news passed on, with who sent it ({media['news']})",
      r.status_code == 200 and media["news"] == [("/savehome", {"game": GAME, "whose": ME, "home": False,
                                                                "from": "192.168.1.21"})])
r = c.post("/api/saves/home", json={"game": GAME, "whose": ME, "home": True}, **NET)
check("...and that it's gone home", r.status_code == 200 and media["news"][-1][1]["home"] is True)
check("...not without a game, or a Pietato whose it is", len(media["news"]) == 2
      and c.post("/api/saves/home", json={"whose": ME}, **NET).status_code == 400
      and c.post("/api/saves/home", json={"game": GAME}, **NET).status_code == 400
      and c.post("/api/saves/home", json={"game": GAME, "whose": "../x"}, **NET).status_code == 400
      and len(media["news"]) == 2)
r = c.post("/api/saves/news", json={"game": GAME}, **NET)
check("one from before saves were each Pietato's own, saying it's played a game: answered (and nothing's taken)",
      r.status_code == 200 and media["news"][-1][0] == "/savenews")
check("the rest of the page: still the password's", c.get("/api/info", **NET).status_code == 401)
os.remove(webui.STATIC + "/webui.txt")

# ---- for real: the other Pietato's web page on a port of its own, and this one's media mode -----------------------
from werkzeug.serving import make_server  # noqa: E402
srv = make_server("127.0.0.1", 0, webui.app, threaded=True)
port = srv.server_port
threading.Thread(target=srv.serve_forever, daemon=True).start()
OTHER = f"http://127.0.0.1:{port}"

HOME = S + "/home/u"
os.makedirs(HOME + "/Games/Saves")
ROM = HOME + "/Games/" + GAME + ".gba"
open(ROM, "wb").write(b"\0" * 64)
SAVES = HOME + "/Games/Saves"
put(SAVES, GAME + ".srm", b"this pi's own save", 7000)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
g.find_core = lambda key: f"/fake/{key}_libretro.so"
g.bios_missing = lambda core, game=None: None
g.built_for_other_pi = lambda core: False
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "", "returncode": 0})()
started = []
g.GameRun.start = lambda self, core, **kw: started.append((self.game["path"], kw.get("saves")))
g.GameRun.quit = lambda self, timeout=0: None
import pitato.screens.games as GS  # noqa: E402
GS.GUEST_WAITS = (0.2, 0.3, 0.5)                       # (looked at sooner, for the test)


class FB:
    w, h = 640, 480
    frames = 0

    def show(self, img):
        FB.frames += 1
        FB.last = img

    def show_part(self, img, box):
        FB.frames += 1

    def invalidate(self):
        pass

    def close(self):
        pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
curtains = []
was_curtain = m.render_curtain
m.render_curtain = lambda title, status, hints=None: (curtains.append(status), was_curtain(title, status, hints))[1]
m.pie.heard[OTHER] = {"host": "tv", "seen": time.time(), "peer": True}
mid = m.saves_id()
check(f"this Pietato's word for itself: made once, and kept ({mid})", SS.whose_id(mid) == mid
      and m.saves_id() == mid and json.load(open(g.STATE_FILE)).get("saves_id") == mid)
IT = {"src": ROM, "title": "Pokemon Emerald", "system": "gba"}
m.game_open(dict(IT))
mine = SAVES + "/" + GAME
check(f"a game started: this Pietato's own save, whatever the TV has of its own (newer, here) ({curtains}, {started})",
      started == [(ROM, None)] and curtains == ["Starting…"] and open(mine + ".srm", "rb").read() == b"this pi's own save")
got = m.web_saves(GAME)
check(f"...while it's played here, the others are told so ({got.get('playing')})", got["playing"] is True
      and got["id"] == mid and got["files"] == {} and sorted(got["own"]) == [".srm"])
media["news"] = []
m.game_end()
time.sleep(0.6)
check(f"played and done: nobody's told anything (its saves are its own) ({media['news']})", media["news"] == [])

# the TV played this one's game on, from where it was left here: home, as it's started
shutil.rmtree(SS.guest_dir(web_saves, ME))
base = SS.sums(SS.save_files(SAVES, GAME))
put(SS.guest_dir(web_saves, mid), GAME + ".srm", b"played on, on the tv", 120)
put(SS.guest_dir(web_saves, mid), GAME + ".state.auto", b"where you were on the tv", 120)
SS.guest_keep(web_saves, mid, GAME, "gpi", "gpi", base)
curtains.clear(); started.clear(); media["news"] = []
m.game_open(dict(IT))
check(f"the TV played it on, as its guest: home first, then it starts ({curtains}, {started})",
      started == [(ROM, None)] and curtains == ["Starting…", "Getting your game from tv…",
                                                "Carrying on from where you left it on tv"])
check("...its in-game save and where you were, here; what they replaced, kept",
      open(mine + ".srm", "rb").read() == b"played on, on the tv"
      and open(mine + ".state.auto", "rb").read() == b"where you were on the tv"
      and open(SAVES + "/.replaced/" + GAME + ".srm", "rb").read() == b"this pi's own save")
for _ in range(50):
    if media["news"]:
        break
    time.sleep(0.1)
check(f"...the TV told it's home (it lets go of it) ({media['news']})",
      media["news"] == [("/savehome", {"game": GAME, "whose": mid, "home": True, "from": "127.0.0.1"})])
m.game_end()

# the TV says it's played this one's game on (a guest of it there): taken home, unless it's been played here since
put(SS.guest_dir(web_saves, mid), GAME + ".srm", b"the tv, further on", 5)
SS.guest_keep(web_saves, mid, GAME, "gpi", "gpi", SS.sums(SS.save_files(SAVES, GAME)))
out = m.web_saves_home({"game": GAME, "whose": mid, "from": "127.0.0.1"})
for _ in range(50):
    if open(mine + ".srm", "rb").read() == b"the tv, further on":
        break
    time.sleep(0.1)
check(f"news from the TV, of this one's game played on there: taken home ({out}, {open(mine + '.srm', 'rb').read()!r})",
      out == {"ok": True} and open(mine + ".srm", "rb").read() == b"the tv, further on")
put(SAVES, GAME + ".srm", b"played here since", 2)
put(SS.guest_dir(web_saves, mid), GAME + ".srm", b"the tv, further still", 1)
out = m.web_saves_home({"game": GAME, "whose": mid, "from": "127.0.0.1"})
time.sleep(0.8)
check(f"...played here since: its own save stays ({open(mine + '.srm', 'rb').read()!r})",
      out == {"ok": True} and open(mine + ".srm", "rb").read() == b"played here since")
out = m.web_saves_home({"game": GAME, "whose": TV, "from": "127.0.0.1"})
check(f"...news of another Pietato's game: not this one's to take ({out})", out == {"ok": True})
out = m.web_saves_home({"game": GAME, "whose": mid, "from": "192.168.1.99"})
check(f"...news from one that isn't one of yours: not taken ({out})", out.get("ok") is False)
check("...one from before saves were each Pietato's own, saying it's played a game: nothing taken",
      m.web_saves_news({"game": GAME, "from": "127.0.0.1"}) == {"ok": True}
      and open(mine + ".srm", "rb").read() == b"played here since")

# a guest here: asked about as the game's started
shutil.rmtree(SS.guest_dir(web_saves, mid))
put(SS.guest_dir(SAVES, TV), GAME + ".srm", b"the tv's game", 400)
put(SS.guest_dir(SAVES, TV), GAME + ".state.auto", b"where the tv's game was", 400)
SS.guest_keep(SAVES, TV, GAME, "tv", "tv", {".srm": "2" * 40})
started.clear(); curtains.clear()
m.view = "list"
m.game_open(dict(IT))
w = m.whose or {}
check(f"a game started that has a guest here (the TV's game, sent here before): whose game, asked, this one's own "
      f"first (it's what was played here last) ({m.view}, {w.get('rows')})", m.view == "whose" and started == []
      and [r[0] for r in w["rows"]] == [TV, ""] and w["rows"][0][1:] == ("tv's game", "Played here 6 minutes ago")
      and w["rows"][1][1:] == ("This Pietato's own game", "Played here just now") and w["sel"] == 1)
frames = FB.frames
m.dirty = True; m.flush()
check("...drawn", FB.frames > frames)
m.press("x")
check("...X on this one's own: nothing to forget", m.whose is not None and m.whose["confirm"] == (None, 0.0))
m.press("left")
check("...◀: the TV's game", m.whose["sel"] == 0)
m.press("right")
m.press("a")
check(f"...▶, A: its own save, as ever ({started})", m.whose is None and started == [(ROM, None)]
      and m.game is not None and m.view == "game")
m.game_end()
started.clear()
m.view = "list"
m.game_open(dict(IT))
check("asked again the next time (this one's own, picked last: there first)", m.view == "whose" and m.whose["sel"] == 1)
m.press("left")
m.press("a")
check(f"...the TV's game: played as a guest, from its own folder of saves ({started})",
      started == [(ROM, SS.guest_dir(SAVES, TV))] and m.game.game.get("whose") == TV
      and m.saves_playing() == (GAME, TV) and m.whose_last(GAME) == TV)
got = m.web_saves(GAME)
check("...the others told that's what's being played, not this one's own", got["playing"] is False
      and got["guests"][TV]["playing"] is True)
check("...its menu: no Play together with another (its save isn't this one's)", not m.together_can())
media["news"] = []
m.game_end()
for _ in range(50):
    if media["news"]:
        break
    time.sleep(0.1)
check(f"played and done: the others told whose game was played on ({media['news'][:1]})",
      media["news"][:1] == [("/savehome", {"game": GAME, "whose": TV, "home": False, "from": "127.0.0.1"})])
time.sleep(1.5)
check("...the TV hasn't taken it home: still a guest here", list(SS.guests_of(SAVES, GAME)) == [TV])
check(f"the Pi starting in the game played last: as it was played last, nobody asked ({m.whose_last(GAME)})",
      m.whose_last(GAME) == TV)
m.set_setting("games_recent", [ROM])
started.clear()
m.view = "home"
m.game_boot()
check(f"...the TV's game again ({started})", started == [(ROM, SS.guest_dir(SAVES, TV))] and m.view == "game")
m.game_restart()
check(f"...started again where it was: still the TV's ({started[-1:]})", started[-1:] == [(ROM, SS.guest_dir(SAVES, TV))])
m.game_end(tell=False)

# the TV takes its game home: let go of here
for ext in (".srm", ".state.auto"):                    # (the TV's own saves, now: just what the guest here has)
    shutil.copy2(os.path.join(SS.guest_dir(SAVES, TV), GAME + ext), os.path.join(web_saves, GAME + ext))
out = m.web_saves_home({"game": GAME, "whose": TV, "home": True, "from": "127.0.0.1"})
for _ in range(50):
    if not SS.guests_of(SAVES, GAME):
        break
    time.sleep(0.1)
check(f"the TV says it's taken its game home: let go of here, its saves kept beside ({out})",
      out == {"ok": True} and SS.guests_of(SAVES, GAME) == {}
      and os.path.isfile(SS.guest_dir(SAVES, TV) + "/.replaced/" + GAME + ".srm"))
started.clear()
m.view = "list"
m.game_open(dict(IT))
check(f"...the game started: nobody's asked, this one's own ({started})", m.view == "game" and started == [(ROM, None)]
      and m.whose_last(GAME) == "")
m.game_end()

# a guest the TV has taken home meanwhile (it never said): found out as the game's started
put(SS.guest_dir(SAVES, TV), GAME + ".srm", b"the tv's game", 400)
put(SS.guest_dir(SAVES, TV), GAME + ".state.auto", b"where the tv's game was", 400)
SS.guest_keep(SAVES, TV, GAME, "tv", "tv", {".srm": "2" * 40})
started.clear()
m.view = "list"
m.game_open(dict(IT))
check(f"a guest the TV's taken home meanwhile: found out as the game's started, and nobody's asked ({started})",
      m.view == "game" and started == [(ROM, None)] and SS.guests_of(SAVES, GAME) == {})
m.game_end()

# X twice: forgotten
put(SS.guest_dir(SAVES, TV), GAME + ".srm", b"a game the tv has moved on from", 90000)
SS.guest_keep(SAVES, TV, GAME, "tv", "tv", {".srm": "2" * 40})
toasts = []
m.toast = lambda text, secs=4: toasts.append(text)
started.clear()
m.view = "list"
m.game_open(dict(IT))
check(f"a guest the TV's moved on from (its own save's something else now): asked ({m.whose and m.whose['rows'][0]})",
      m.view == "whose" and m.whose["rows"][0][1:] == ("tv's game", "Played here yesterday"))
m.press("left") if m.whose["sel"] else None
m.press("x")
check("...X: asked again, to be sure", m.whose is not None and m.whose["confirm"][0] == TV)
m.press("x")
check(f"...X again: forgotten here (its saves kept beside), back where you were ({toasts[-1:]}, {m.view})",
      m.whose is None and m.view == "list" and SS.guests_of(SAVES, GAME) == {} and toasts[-1:] == ["Forgotten here"]
      and started == [])
m.game_open(dict(IT))
m.view == "whose" and m.press("b")
check("...B, another time, would just go back; with no guest, the game starts", started == [(ROM, None)])
m.game_end()

m.setting = (lambda real: lambda key: "Off" if key == "share" else real(key))(m.setting)
check("sharing off: nobody asked, nobody told", m.saves_peers() == [] and m.web_saves(GAME) == {"ok": True, "on": False})
srv.shutdown()
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
