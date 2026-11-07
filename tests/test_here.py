"""Play here, on the Pi's side: in a web page's request with it on, what would play on the Pi is handed to the page
instead, if a browser can play it (a video or a song of yours with the rest of its kind, a cartoon from archive.org, a
station; a game EmulatorJS plays, with where its save is), and played on the Pi as ever, with why, if not (Plex, a live
channel, an .avi, a Dreamcast game, a game in more than one file, a file outside your home folder); with it off, or
outside a web page's request, nothing changes. Turned on while a game's on the Pi, the game moves to the page (where
you are with it, when the browser's emulator is the Pi's); turned off, it comes back. A save sent back from the page
puts aside where you left off on the Pi, so the Pi never takes you back to before it."""
import json, os, shutil, sys
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g

S = SP + "/t_here"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
for d in ("Videos", "Music/Album", "Games/gb", "Games/ps1", "Games/dc", "Games/BIOS", ".hidden"):
    os.makedirs(f"{HOME}/{d}")
for f in ("Videos/a.mp4", "Videos/b.avi", "Videos/c.mkv", "Music/Album/1.mp3", "Music/Album/2.flac", "Music/Album/3.wma",
          "Games/gb/Zelda.gb", "Games/ps1/Disc.chd", "Games/ps1/Two.cue", "Games/dc/Game.gdi", "Games/BIOS/scph1001.bin",
          ".hidden/x.mp4"):
    open(f"{HOME}/{f}", "wb").write(b"\0" * 64)
os.makedirs(S + "/outside")
open(S + "/outside/o.mp4", "wb").write(b"\0")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"
g.home_dir = lambda: HOME
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


m = g.Media()
played = []
m.spawn = lambda args, target: played.append(target)


def ask(fn, *a):
    """As a web page's request with Play here on: (what's handed over, the answer)."""
    m.here_begin(True)
    took = fn(*a)
    return took, m.here_end({"ok": True})


def it(path, kind, **kw):
    return g.item(path, os.path.basename(path), kind, path, **kw)


vids = [it(f"{HOME}/Videos/{n}", "video") for n in ("a.mp4", "b.avi", "c.mkv")]
m.state["pos"][vids[0]["key"]] = 95.0
took, out = ask(m.here_take, vids, 0)
p = out.get("play", {})
check(f"a video of yours: handed over, with the others a browser plays ({p})", took and p["kind"] == "video"
      and [r["url"] for r in p["items"]] == ["/api/home/Videos/a.mp4", "/api/home/Videos/c.mkv"] and p["index"] == 0
      and p["start"] == 95.0)
took, out = ask(m.here_take, vids, 1)
check(f"an .avi: not handed over, and why ({out})", not took and "play" not in out and "browser can't" in out["note"])
songs = [it(f"{HOME}/Music/Album/{n}", "audio", sub="Someone") for n in ("1.mp3", "2.flac", "3.wma")]
took, out = ask(m.here_take, songs, 1)
p = out.get("play", {})
check(f"a song: it, and its album with it ({[r['title'] for r in p.get('items', [])]}, {p.get('index')})",
      took and p["kind"] == "audio" and len(p["items"]) == 2 and p["index"] == 1 and p["items"][1]["sub"] == "Someone")
toon = g.item("ia:popeye-1936/Popeye The Sailor.mp4", "Popeye", "video", "ia:popeye-1936/Popeye The Sailor.mp4")
took, out = ask(m.here_take, [toon], 0)
check(f"a cartoon: from archive.org ({out['play']['items'][0]['url']})", took and out["play"]["items"][0]["url"]
      == "https://archive.org/download/popeye-1936/Popeye%20The%20Sailor.mp4")
radio = g.item("url:http://radio.example/jazz", "Jazz", "radio", "http://radio.example/jazz")
took, out = ask(m.here_take, [radio], 0)
check(f"a station: its stream ({out['play']})", took and out["play"]["kind"] == "radio"
      and out["play"]["items"][0]["url"] == "http://radio.example/jazz")
for what, row, word in (("Plex", g.item("plex:1", "A film", "plexvideo", "plex:1"), "Plex"),
                        ("a live channel", g.item("plexlive:9", "News", "live", "plexlive:9"), "Live"),
                        ("a file outside your home folder", it(S + "/outside/o.mp4", "video"), "That one plays on the Pi"),
                        ("one in a hidden folder", it(f"{HOME}/.hidden/x.mp4", "video"), "That one plays on the Pi")):
    took, out = ask(m.here_take, [row], 0)
    check(f"{what}: plays on the Pi, and says so ({out})", not took and word in out.get("note", ""))
check("...nothing played meanwhile", played == [])
m.here_begin(False)
took = m.here_take(vids, 0)
m.here_end({"ok": True})
check("Play here off: nothing handed over", not took)
check("...nor outside a web page's request", not m.here_take(vids, 0) and m.web_here is False)

game = dict(it(f"{HOME}/Games/gb/Zelda.gb", "game"), system="gb")
took, out = ask(m.here_take_game, game)
check(f"a Game Boy game: EmulatorJS's core, the game, where its save is ({out.get('play')})", took and out["play"] == {
    "kind": "game", "title": "Zelda.gb", "core": "gambatte", "rom": "Games/gb/Zelda.gb", "bios": "",
    "save": "Saves/Zelda.srm", "moment": False})
ps1 = dict(it(f"{HOME}/Games/ps1/Disc.chd", "game"), system="ps1")
took, out = ask(m.here_take_game, ps1)
check(f"a PlayStation game: with its BIOS from Games/BIOS ({out['play']['bios']})", took
      and out["play"]["core"] == "pcsx_rearmed" and out["play"]["bios"] == "Games/BIOS/scph1001.bin")
cue = dict(it(f"{HOME}/Games/ps1/Two.cue", "game"), system="ps1")
took, out = ask(m.here_take_game, cue)
check(f"one in more than one file: on the Pi ({out})", not took and "more than one file" in out["note"])
dc = dict(it(f"{HOME}/Games/dc/Game.gdi", "game"), system="dc")
took, out = ask(m.here_take_game, dc)
check(f"a Dreamcast game: on the Pi ({out})", not took and "plays on the Pi" in out["note"])
check("an error's answer stays as it was", m.here_end({"error": "x"}) == {"error": "x"})

# ---- where you are in a game: with it, when the browser's emulator is the Pi's --------------------------------------
SAVES = HOME + "/Games/Saves"
os.makedirs(SAVES, exist_ok=True)
open(SAVES + "/Zelda.state.auto", "wb").write(b"moment")
pi_core = {"gb": "/usr/lib/libretro/mgba_libretro.so"}
g.find_core = lambda key: pi_core.get(key)
took, out = ask(m.here_take_game, game)
check(f"the Pi plays Game Boy games with mGBA, the browser with gambatte: just its save ({out['play']})",
      took and out["play"]["moment"] is False and "state" not in out["play"])
pi_core["gb"] = "/usr/lib/libretro/gambatte_libretro.so"
took, out = ask(m.here_take_game, game)
check(f"...the Pi with gambatte too: where you left off, with it ({out['play']})",
      took and out["play"]["moment"] is True and out["play"]["state"] == "Saves/Zelda.state.auto")
os.makedirs(HOME + "/Games/genesis")
open(HOME + "/Games/genesis/Sonic.md", "wb").write(b"\0" * 64)
pi_core["genesis"] = "/usr/lib/libretro/genesis_plus_gx_libretro.so"
sonic = dict(it(f"{HOME}/Games/genesis/Sonic.md", "game"), system="genesis")
took, out = ask(m.here_take_game, sonic)
check(f"a Genesis game: the browser's segaMD is Genesis Plus GX, the Pi's ({out['play']['core']}, "
      f"{out['play']['moment']}); none kept: nothing to pick up", took and out["play"]["core"] == "segaMD"
      and out["play"]["moment"] is True and "state" not in out["play"])


class FakeRun:
    """A game on the Pi: its quitting noted (where you are, written as it ends)."""
    ended, state, error, disc, slow, cheevos, together, attract = False, "on", None, (1, 1), False, None, None, False

    def __init__(self, it):
        self.game = {"path": it["src"], "title": it["title"], "system": it["system"]}
        self.quits = 0

    def quit(self):
        self.quits += 1
        open(SAVES + "/Zelda.state.auto", "wb").write(b"moment, as it ended")

    def __getattr__(self, name):
        return lambda *a, **k: None


toasts = []
m.toast = lambda text, secs=4: toasts.append(text)
m.active = True
os.remove(SAVES + "/Zelda.state.auto")
run = FakeRun(game)
m.game, m.view = run, "game"
out = m.web_command({"cmd": "here_move"})
check(f"Play here turned on while a game's on the Pi: it ends there, where you are kept, and moves to the page with "
      f"it ({out}, {toasts})", run.quits == 1 and m.game is None and m.view != "game"
      and out.get("play", {}).get("state") == "Saves/Zelda.state.auto" and out["play"]["rom"] == "Games/gb/Zelda.gb"
      and toasts[-1] == "Playing on the web page now" and m.web_here is False)
out = m.web_command({"cmd": "here_move"})
check(f"...nothing on the Pi now: nothing moves ({out})", out == {"ok": True})
run = FakeRun(game)
run.together = {"link": False}
m.game, m.view = run, "game"
out = m.web_command({"cmd": "here_move"})
check(f"a game played together: it stays, and why ({out})", run.quits == 0 and m.game is run
      and "together" in out.get("note", "") and "play" not in out)
gd = dict(it(f"{HOME}/Games/dc/Game.gdi", "game"), system="dc")
run = FakeRun(gd)
m.game, m.view = run, "game"
out = m.web_command({"cmd": "here_move"})
check(f"a Dreamcast game: it stays on the Pi, and why ({out})", run.quits == 0 and m.game is run
      and "plays on the Pi" in out.get("note", ""))
m.attract = {"kind": "game", "run": run, "game": run.game}
m.attract_on = lambda: True
out = m.web_command({"cmd": "here_move"})
check(f"a game playing by itself: not yours, nothing moves ({out})", out == {"ok": True} and run.quits == 0)
del m.attract_on
m.attract = None
m.game = None

opened = []
m.web_ready = lambda: True
m.game_cant = lambda g: None
m.game_open = lambda it: (opened.append(it), setattr(m, "game", FakeRun(it)))[0]
out = m.web_command({"cmd": "here_back", "rom": "Games/gb/Zelda.gb"})
check(f"Play here turned off: the game from the page carries on on the Pi ({out}, {opened})",
      out == {"ok": True} and opened == [{"src": f"{HOME}/Games/gb/Zelda.gb", "title": "Zelda", "system": "gb"}])
out = m.web_command({"cmd": "here_back", "rom": "Games/gb/Zelda.gb"})
check(f"...a game on the Pi already: it isn't put aside for it ({out})", "error" in out and len(opened) == 1)
m.game = None
for rom in ("Videos/a.mp4", "../outside/o.mp4", "/etc/passwd", "Games/gb/Nope.gb", ""):
    out = m.web_command({"cmd": "here_back", "rom": rom})
    check(f"...{rom or 'nothing'}: not a game of yours, nothing opened ({out})", "error" in out and len(opened) == 1)

# ---- the web page's side: a save that comes back puts aside where you left off on the Pi ---------------------------
sys.path.append(ROOT + "/pitato")
import webui
webui.HOME = HOME
c = webui.app.test_client()
H = {"headers": {"X-Pitato-Page": "1"}}
for ext in (".state.auto", ".state.auto.cheevos"):
    open(SAVES + "/Zelda" + ext, "wb").write(b"older")
r = c.put("/api/upload?folder=games&exists=replace&path=Saves/Zelda.srm", data=b"newer save", **H)
check(f"a save from the page: in, and where you left off on the Pi (older) put aside ({r.status_code})",
      r.status_code == 200 and open(SAVES + "/Zelda.srm", "rb").read() == b"newer save"
      and not os.path.exists(SAVES + "/Zelda.state.auto") and not os.path.exists(SAVES + "/Zelda.state.auto.cheevos")
      and open(SAVES + "/.replaced/Zelda.state.auto", "rb").read() == b"older")
open(SAVES + "/Zelda.state.auto.cheevos", "wb").write(b"older progress")
r = c.put("/api/upload?folder=games&exists=replace&path=Saves/Zelda.state.auto", data=b"where you were", **H)
check(f"...where you were, from the page as it closed: in, the old achievements' progress put aside ({r.status_code})",
      r.status_code == 200 and open(SAVES + "/Zelda.state.auto", "rb").read() == b"where you were"
      and not os.path.exists(SAVES + "/Zelda.state.auto.cheevos"))
open(HOME + "/Games/gb/Zelda.state.auto", "wb").write(b"not in Saves")
r = c.put("/api/upload?folder=games&exists=replace&path=gb/Zelda.srm", data=b"x", **H)
check("...a save anywhere else in Games: nothing put aside", r.status_code == 200
      and os.path.exists(HOME + "/Games/gb/Zelda.state.auto"))
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
