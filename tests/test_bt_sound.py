"""Bluetooth headphones' sound (BlueALSA), against the pretend BlueZ and BlueALSA (btfake): where it goes (the
headphones, while they're connected, whatever Settings > Sound is on, as on a phone; one of the Pi's own picked there
meanwhile takes it from them, till they connect again), BlueALSA asked only while something's connected over Bluetooth,
and seldom once things settle; a song or a video moving to the headphones as they connect, and pausing, silent, as they
go (A plays on at its volume); a player that stopped as they went picked up where it was; a game's sound moving too
(its menu up as they go), through the real emulator's sound command; Settings > Sound's row and its choices (the
headphones by name), on the Pi and the web page; what Settings > Bluetooth says as they connect; no looking round
while they're on (it makes them skip); and setup.sh's BlueALSA, its sound a step lighter so it doesn't skip."""
import copy, json, os, shutil, subprocess, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, SP + "/btfake")
sys.path.insert(0, TESTS)
import setup_env as F
import pietato_all as g
from PIL import ImageDraw

S = SP + "/t_bt_sound"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
for d in ("Music", "Videos", "Games/genesis", "Pictures"):
    os.makedirs(f"{HOME}/{d}")
os.makedirs(S + "/bin")
HP, SPK, PAD = "00:1B:66:00:00:04", "8C:DE:52:00:00:0A", "E4:17:D8:00:00:01"
H = "/org/bluez/hci0/dev_" + HP.replace(":", "_")
J = "/org/bluez/hci0/dev_" + SPK.replace(":", "_")
state = copy.deepcopy(F.STATE)
state["nearby"].pop(HP)
state["devices"][HP] = {"name": "WH-1000XM4", "icon": "audio-headphones", "paired": True, "trusted": True,
                        "connected": False, "a2dp": True}
state["devices"][SPK] = {"name": "JBL Flip 5", "icon": "audio-card", "paired": True, "trusted": True,
                         "connected": False, "a2dp": True}
state["pcms"], state["seq"] = [], 0
F.use(S + "/bt", state)
g.BT_LINKS = os.environ["BT_LINKS"]          # (the kernel's links: the pretend BlueZ keeps them)

# stand-in mplayer and aplay: they say how they were started, and what they're told
MPLOG, APLOG = S + "/mplayer.log", S + "/aplay.log"
open(S + "/bin/mplayer", "w").write('''#!/usr/bin/env python3
# as mplayer -slave: what it's told while it fills its cache is dropped; "pause" toggles; a line with no "pausing"
# before it plays; "pausing ..." leaves it paused; "pausing_keep_force ..." changes nothing
import json, os, sys, time
def log(**kw):
    with open(os.environ["MPLAYER_LOG"], "a") as f:
        f.write(json.dumps(dict(kw, pid=os.getpid())) + "\\n")
argv = sys.argv[1:]
log(argv=argv)
t0, deaf = time.monotonic(), (0.4 if "-cache" in argv else 0.0)
pos = float(argv[argv.index("-ss") + 1]) if "-ss" in argv else 0.0
state = {"paused": False}
def paused(p):
    if p != state["paused"]:
        state["paused"] = p
        log(state="paused" if p else "playing")
log(state="playing")
for line in sys.stdin:
    c = line.strip()
    if c != "quit" and time.monotonic() - t0 < deaf:
        log(dropped=c)
        continue
    log(cmd=c)
    if c == "quit":
        break
    words = c.split()
    pre = words[0] if words and words[0].startswith("pausing") else ""
    rest = words[1:] if pre else words
    if rest == ["pause"] and not pre:
        paused(not state["paused"])
        continue
    was = state["paused"]
    if pre != "pausing_keep_force":
        paused(False)                          # (it plays, to do it)
    if rest == ["get_property", "pause"]:
        print("ANS_pause=" + ("yes" if state["paused"] else "no"), flush=True)
    elif rest == ["get_time_pos"]:
        print(f"ANS_TIME_POSITION={pos:.1f}", flush=True)
    if pre == "pausing" or (pre == "pausing_keep" and was):
        paused(True)
''')
open(S + "/bin/aplay", "w").write('#!/bin/sh\necho "$$ $*" >> "$APLAY_LOG"\nexec cat > /dev/null\n')
for f in ("mplayer", "aplay"):
    os.chmod(f"{S}/bin/{f}", 0o755)
os.environ["PATH"] = S + "/bin:" + os.environ["PATH"]
os.environ["MPLAYER_LOG"], os.environ["APLAY_LOG"] = MPLOG, APLOG

ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


def until(cond, secs=8.0):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return cond()


def asked():
    """BlueALSA asked, so far (busctl's calls to it)."""
    return sum(1 for line in F.log() if " busctl " in f" {line} " and "org.bluealsa" in line)


def busctl(path, method):
    subprocess.run(["busctl", "call", "org.bluez", path, "org.bluez.Device1", method], capture_output=True)


def fresh_look():
    g._bt_seen.update(at=-1e9, outs=[], links=None, moved=-1e9, here=None, away=False)


# ---- where sound goes: BlueALSA asked only while something's connected ------------------------------------------------
fresh_look()
g._bt_seen["here"] = False                    # (no BlueALSA on this Pi)
n = asked()
check("no BlueALSA: nowhere to send it, and nothing asked", g.bt_outputs() == [] and g.sound_route("Auto") == ""
      and asked() == n)
fresh_look()
F.change(lambda s: s["devices"][PAD].update(connected=False))
n = asked()
check(f"BlueALSA, nothing connected over Bluetooth ({os.listdir(g.BT_LINKS)}): asked once",
      g.bt_outputs() == [] and g.sound_place("Auto") == ("", "") and asked() == n + 1)
g._bt_seen["at"], g._bt_seen["moved"] = time.monotonic() - 10, time.monotonic() - 60
check("...and seldom after that", g.bt_outputs() == [] and asked() == n + 1)
g._bt_seen["at"] = time.monotonic() - 16
check("...but now and then (should the kernel not list the links)", g.bt_outputs() == [] and asked() == n + 2)
F.change(lambda s: s["devices"][PAD].update(connected=True))
check("a controller connected: asked at once, nothing to play through", g.bt_outputs() == [] and asked() == n + 3)
check("...not asked again straight away", g.bt_outputs() == [] and g.sound_route("Auto") == "" and asked() == n + 3)
busctl(H, "Connect")
check(f"headphones connected: there at once (a link came: asked afresh) {g.bt_outputs()}",
      g.bt_outputs() == [(H, 1)] and asked() == n + 4)
check("...sound goes to them, whatever Settings > Sound is on (as on a phone)", g.sound_route("Auto") == "bluetooth"
      and g.sound_route(None) == "bluetooth" and g.sound_route("Headphones") == "bluetooth"
      and g.sound_place("Auto") == ("bluetooth", H) and g.sound_place("Headphones") == ("bluetooth", H))
check("...mplayer's and aplay's names for them", g.sound_device(None, "bluetooth") == "alsa:device=bluealsa,alsa"
      and g.aplay_device(None, "bluetooth") == "bluealsa" and g.sound_device("Auto") == "alsa:device=bluealsa,alsa"
      and g.aplay_device("Auto") == "bluealsa" and g.sound_device("Headphones") == "alsa:device=bluealsa,alsa"
      and g.aplay_device("Headphones") == "bluealsa")
g.sound_away(True)
check("...one of the Pi's own picked in Settings > Sound meanwhile: that, headphones or not",
      g.sound_route("Headphones") == "" and g.sound_device("Headphones") == "alsa"
      and g.aplay_device("Headphones") == "" and g.bt_outputs() == [(H, 1)])
check("...their name, from BlueZ", g.bt_output_name(H) == "WH-1000XM4" and g.bt_output_name() == "WH-1000XM4"
      and g.bt_output_name("/not/bluez") == "")
busctl(J, "Connect")
check(f"a speaker connected after them: the one connected last is the one used ({g.bt_outputs()})",
      [d for d, _ in g.bt_outputs()] == [H, J] and g.sound_place("Auto") == ("bluetooth", J))
check("...and it has the sound, one of the Pi's own picked before it connected or not",
      g.sound_place("Headphones") == ("bluetooth", J))
F.change(lambda s: s["pcms"].extend([{"addr": HP, "seq": 9, "transport": "HFP-AG", "mode": "sink"},
                                     {"addr": HP, "seq": 10, "transport": "A2DP-sink", "mode": "source"}]))
check("only A2DP's, with the Pi as the player (not a headset's microphone, or the Pi as a speaker)",
      [d for d, _ in g.bt_outputs(fresh=True)] == [H, J])
F.change(lambda s: s.update(pcms=[p for p in s["pcms"] if "transport" not in p]))
n = asked()
g._bt_seen["moved"], g._bt_seen["at"] = time.monotonic() - 60, time.monotonic() - 5
g.bt_outputs()
check("settled: BlueALSA's answer is good for longer", asked() == n)
g._bt_seen["at"] = time.monotonic() - 16
g.bt_outputs()
check("...then asked again", asked() == n + 1)
busctl(J, "Disconnect")
check("the speaker disconnected: gone at once", g.bt_outputs() == [(H, 1)] and g.sound_place("Auto") == ("bluetooth", H))
F.change(lambda s: s.update(bluealsa="slow"))
check("BlueALSA slow to answer (busctl timed out): as it was, not taken for the headphones going",
      g.bt_outputs(fresh=True) == [(H, 1)])
F.change(lambda s: s.update(bluealsa=False))
check("BlueALSA not running: nowhere", g.bt_outputs(fresh=True) == [] and g.sound_route("Auto") == "")
F.change(lambda s: s.update(bluealsa=True))
check("...running again: there", g.bt_outputs(fresh=True) == [(H, 1)])

# ---- media mode ---------------------------------------------------------------------------------------------------------
for k in range(1, 4):
    open(f"{HOME}/Music/song {k}.mp3", "wb").write(b"ID3")
open(f"{HOME}/Videos/film.mp4", "wb").write(b"\0" * 64)
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
real_run = subprocess.run
subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                       if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in
                                       {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli", "vcgencmd"}
                                       else real_run(cmd, *a, **k))
g.probe_length = lambda path: 600.0


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480; last = None
    def show(self, img): FB.last = img.copy()
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
texts = []
real_text = ImageDraw.ImageDraw.text
ImageDraw.ImageDraw.text = lambda self, xy, text, *a, **k: (texts.append(str(text)), real_text(self, xy, text, *a, **k))[1]


def drawn():
    texts.clear(); m.dirty = True; m.flush()
    return list(texts)


def log():
    try:
        return [json.loads(x) for x in open(MPLOG).read().splitlines() if x.strip()]
    except OSError:
        return []


def starts():
    return [e for e in log() if "argv" in e]


def start_no(n):
    """The player's n-th start (from 1), once it's said so."""
    until(lambda: len(starts()) >= n, 5)
    st = starts()
    return st[n - 1] if len(st) >= n else {"argv": [], "pid": -1}


def still(n):
    """No more than n starts, a moment later."""
    time.sleep(0.4)
    return len(starts()) == n


def told(pid):
    return [e["cmd"] for e in log() if e.get("pid") == pid and "cmd" in e]


def now_is(pid):
    """The player's state: playing or paused (as it says)."""
    return ([e["state"] for e in log() if e.get("pid") == pid and "state" in e] or [None])[-1]


def held(pid):
    """A player started paused: paused once it listens (media mode's loop tells it)."""
    return until(lambda: (m.settle_tick(time.monotonic()), not m.settling)[1], 4) and now_is(pid) == "paused"


def opt(argv, name):
    return argv[argv.index(name) + 1] if name in argv else None


def look():
    """The next look at where the sound goes is due: it's had."""
    m.sound_look = 0.0
    m.sound_tick(time.monotonic())


m = g.Media(); m.enter()
mi = next(k for k, t in enumerate(g.LIBRARY) if t["type"] == "files" and t.get("kind") == "audio")
vi = next(k for k, t in enumerate(g.LIBRARY) if t["type"] == "files" and t.get("kind") == "video")
m.load_tab(mi); m.load_tab(vi)
songs, films = m.tab_items(mi), m.tab_items(vi)
check(f"{len(songs)} songs and {len(films)} film to play", len(songs) == 3 and len(films) == 1)
m.tab, m.view = mi, "list"
m.play(songs, 0)
first = start_no(1)
check(f"a song, with the headphones on: through them ({opt(first['argv'], '-ao')}), at its volume",
      opt(first["argv"], "-ao") == "alsa:device=bluealsa,alsa" and opt(first["argv"], "-volume") == "80"
      and m.sound_used == ("bluetooth", H) and m.view == "now" and not m.paused)
look()
check("nothing's changed: it plays on", still(1))
m.view, m.pos = "list", 100.0
busctl(H, "Disconnect")
look()
gone = start_no(2)
check(f"the headphones went: started again through the Pi's own ({opt(gone['argv'], '-ao')}), silent, "
      f"from a moment before ({opt(gone['argv'], '-ss')})", still(2) and opt(gone["argv"], "-ao") == "alsa"
      and opt(gone["argv"], "-volume") == "0" and opt(gone["argv"], "-ss") == "97" and m.cur is songs[0])
check("...paused, as a phone does", held(gone["pid"]) and m.paused and m.muted and m.sound_used == ("", ""))
check(f"...said so ({m.msg})", m.msg == "Paused: WH-1000XM4 disconnected")
check("...and you stay where you were", m.view == "list")
check("...the one before stopped", until(lambda: "quit" in told(first["pid"]), 3))
m.view = "now"
m.press("a")
check(f"A: its volume back, then it plays on ({told(gone['pid'])[-2:]})",
      until(lambda: told(gone["pid"])[-2:] == ["pausing_keep_force volume 80 1", "get_property pause"], 3)
      and now_is(gone["pid"]) == "playing" and not m.paused and not m.muted)
m.pos = 120.0
busctl(H, "Connect")
look()
back = start_no(3)
check(f"the headphones back: through them again, from where it was ({opt(back['argv'], '-ss')}), playing",
      still(3) and opt(back["argv"], "-ao") == "alsa:device=bluealsa,alsa"
      and opt(back["argv"], "-volume") == "80" and opt(back["argv"], "-ss") == "120" and not m.paused
      and not m.muted and m.sound_used == ("bluetooth", H))
check(f"...said so ({m.msg})", m.msg == "Sound through WH-1000XM4" and m.view == "now")
time.sleep(0.3)
check("...not paused", now_is(back["pid"]) == "playing" and not m.settling)
check(f"Settings > Sound's row says where it goes ({m.sound_value()})", m.sound_value() == "Auto: WH-1000XM4")

m.press("a")                                  # (you pause it)
check("paused by you", m.paused and not m.muted)
busctl(H, "Disconnect")
look()
p1 = start_no(4)
check("paused, and they go: still paused, silent", still(4) and opt(p1["argv"], "-volume") == "0"
      and held(p1["pid"]) and m.paused and m.muted)
busctl(H, "Connect")
look()
p2 = start_no(5)
check("...back while it's paused: through them, still paused", still(5)
      and opt(p2["argv"], "-ao") == "alsa:device=bluealsa,alsa" and opt(p2["argv"], "-volume") == "0"
      and held(p2["pid"]) and m.paused and m.muted)
m.press("up")
time.sleep(0.3)
check(f"...the volume changed meanwhile: kept for when it plays, still silent and paused ({told(p2['pid'])[-1:]})",
      m.volume == 85 and not any("volume 85" in c for c in told(p2["pid"])) and m.paused and m.muted
      and now_is(p2["pid"]) == "paused")
m.press("a")
check("...A: plays on, at it", until(lambda: told(p2["pid"])[-2:] == ["pausing_keep_force volume 85 1",
                                                                     "get_property pause"], 3)
      and now_is(p2["pid"]) == "playing" and not m.paused)
m.press("down")

# Settings > Sound: one of the Pi's own picked with the headphones on; them connecting again; and back to them
g.sound_cards = lambda: [("Headphones", "Headphones")]
check(f"Settings > Sound's choices on Auto: Auto and the Pi's own ({m.sound_choices()}, {m.sound_shown()})",
      m.sound_choices() == ["Auto", "Headphones"] and m.sound_shown() == "Auto")
m.set_setting("sound", "Headphones")
m.play(songs, 1)
own = start_no(6)
check(f"Settings > Sound set to a card with the headphones on: that card ({opt(own['argv'], '-ao')})",
      opt(own["argv"], "-ao") == "alsa:device=default=Headphones,alsa" and m.sound_used == ("Headphones", ""))
check(f"...its row says the card ({m.sound_value()}); the headphones are a choice, to go back to "
      f"({m.sound_choices()})", m.sound_value() == "Headphones" and m.sound_shown() == "Headphones"
      and m.sound_choices() == ["Auto", "Headphones", "WH-1000XM4"])
busctl(H, "Disconnect"); look()
check("...they go: it plays on", still(6) and not m.paused and m.sound_choices() == ["Auto", "Headphones"])
busctl(H, "Connect"); look()
again = start_no(7)
check(f"...they connect again: the sound's theirs, without a trip to Settings ({opt(again['argv'], '-ao')}, {m.msg})",
      still(7) and opt(again["argv"], "-ao") == "alsa:device=bluealsa,alsa" and m.msg == "Sound through WH-1000XM4"
      and not m.paused and m.sound_used == ("bluetooth", H))
check(f"...its row says them ({m.sound_value()}), Headphones kept for when they go ({m.setting('sound')})",
      m.sound_value() == "WH-1000XM4" and m.sound_shown() == "WH-1000XM4" and m.setting("sound") == "Headphones")
m.tab, m.view, m.set_page = m.tab_index("settings"), "list", "root"     # (◀▶ on its row, on the Pi)
m.load_tab(m.tab)
m.set_sel = m.settings_root_index("sound")
m.press("right")
look()
check(f"Settings > Sound's row, ▶ from them: Auto, still theirs ({m.sound_value()}, {m.sound_choices()})",
      still(7) and m.setting("sound") == "Auto" and m.sound_value() == "Auto: WH-1000XM4"
      and m.sound_choices() == ["Auto", "Headphones"])
m.press("left")
look()
card = start_no(8)
check(f"...◀: the Pi's Headphones, the sound off them ({opt(card['argv'], '-ao')}, {m.msg})",
      still(8) and opt(card["argv"], "-ao") == "alsa:device=default=Headphones,alsa"
      and m.msg == "Sound through Headphones" and m.sound_value() == "Headphones")
m.press("right")
look()
bt = start_no(9)
check(f"...▶: them, by name, Headphones kept ({opt(bt['argv'], '-ao')}, {m.setting('sound')}, {m.msg})",
      still(9) and opt(bt["argv"], "-ao") == "alsa:device=bluealsa,alsa" and m.setting("sound") == "Headphones"
      and m.sound_value() == "WH-1000XM4" and m.msg == "Sound through WH-1000XM4")


def web_sound_row():
    return next(r for s in m.web_settings()["sections"] for r in s["rows"] if r["key"] == "sound")


row = web_sound_row()
check(f"the web page's Settings > Sound: on them, by name ({row['value']}, {row['choices']})",
      row["value"] == "WH-1000XM4" and row["choices"] == ["Auto", "Headphones", "WH-1000XM4"] and not row.get("note"))
out = m.web_settings_do({"key": "sound", "value": "Headphones"})
look()
card = start_no(10)
check(f"...Headphones picked there: the sound off them ({out}, {opt(card['argv'], '-ao')})", out == {"ok": True}
      and still(10) and opt(card["argv"], "-ao") == "alsa:device=default=Headphones,alsa"
      and web_sound_row()["value"] == "Headphones")
out = m.web_settings_do({"key": "sound", "value": "WH-1000XM4"})
look()
bt = start_no(11)
check(f"...them by name: back to them, not kept as the choice ({out}, {opt(bt['argv'], '-ao')})",
      out == {"ok": True} and still(11) and opt(bt["argv"], "-ao") == "alsa:device=bluealsa,alsa"
      and m.setting("sound") == "Headphones" and web_sound_row()["value"] == "WH-1000XM4")
out = m.web_settings_do({"key": "sound", "value": "Auto"})
look()
row = web_sound_row()
check(f"...Auto: still theirs, and it says so ({out}, {row['value']}, {row.get('note')}, {row['choices']})",
      out == {"ok": True} and still(11) and row["value"] == "Auto" and row.get("note") == "Auto: WH-1000XM4"
      and row["choices"] == ["Auto", "Headphones"])
check("...their name isn't one of Auto's choices (Auto has them already)",
      "error" in m.web_settings_do({"key": "sound", "value": "WH-1000XM4"}) and m.setting("sound") == "Auto")
m.view = "list"
m.set_page = "root"
m.stop()

g.sound_cards = lambda: [("vc4hdmi0", "HDMI"), ("Headphones", "Headphones")]
busctl(H, "Disconnect")
g.hdmi_ports = lambda: [0]
n0 = len(starts()) + 1
m.play(songs, 1)
tv = start_no(n0)
check(f"Auto, a TV on HDMI, no headphones: the TV ({opt(tv['argv'], '-ao')})",
      opt(tv["argv"], "-ao") == "alsa:device=hdmi=vc4hdmi0.0.4.130.0.1,alsa")
g.hdmi_ports = lambda: []
look()
check("...the TV unplugged: it plays on, as before (only Bluetooth moves it)", still(n0) and not m.paused)
g.sound_cards = lambda: []
m.stop()

# a video: it moves too, and says so on the picture; one that stopped as they went picks up where it was
busctl(H, "Connect")
m.play(films, 0, start=0)
v0 = start_no(n0 + 1)
check("a film through the headphones", opt(v0["argv"], "-ao") == "alsa:device=bluealsa,alsa" and m.kind == "video")
m.pos = 300.0
busctl(H, "Disconnect")
m.proc.kill(); m.proc.wait()                  # (the player stopped as they went)
m.sound_look = time.monotonic() + 60          # (not due: it's looked at anyway, the player having stopped)
texts.clear()
m.tick()
curtain = list(texts)
v1 = start_no(n0 + 2)
check(f"...the player stopped as they went: started again where it was, paused ({opt(v1['argv'], '-ss')})",
      still(n0 + 2) and opt(v1["argv"], "-ss") == "297" and opt(v1["argv"], "-volume") == "0"
      and m.kind == "video" and m.paused and m.muted and m.cur is films[0])
check("...not taken for finished", m.state["pos"].get(films[0]["key"]) != -1)
check(f"...its curtain says why it's paused ({[x for x in curtain if 'Paused' in x]})",
      "Paused: WH-1000XM4 disconnected. A plays on" in curtain)
check(f"...said so on the picture ({m.screen_note[0] if m.screen_note else None})",
      m.screen_note and m.screen_note[0] == "Paused: WH-1000XM4 disconnected")
busctl(H, "Connect")
look()
v2 = start_no(n0 + 3)
check("...back: through them, still paused", opt(v2["argv"], "-ao") == "alsa:device=bluealsa,alsa"
      and m.paused and m.muted and opt(v2["argv"], "-ss") == "300")
dropped = lambda pid: [e["dropped"] for e in log() if e.get("pid") == pid and "dropped" in e]
check(f"...a film fills its cache first, dropping what it's told meanwhile ({dropped(v2['pid'])[:2]}): paused once "
      f"it listens", held(v2["pid"]) and dropped(v2["pid"]))
m.press("a")
check("...A: plays on, at its volume", until(lambda: told(v2["pid"])[-3:-1] == ["pausing_keep_force volume 80 1",
                                                                              "get_property pause"], 3)
      and now_is(v2["pid"]) == "playing" and not m.paused)
m.stop()
check("stopped: nothing to move", m.sound_used is None and not m.muted)
look()
check("...and nothing started", still(n0 + 3))
for presses, want in ((1, "playing"), (2, "paused")):  # (A before it's listening: it's still filling its cache)
    busctl(H, "Connect")
    k = len(starts())
    m.play(films, 0, start=0)
    start_no(k + 1)
    m.pos = 50.0
    busctl(H, "Disconnect")
    look()
    f1 = start_no(k + 2)
    for _ in range(presses):
        m.press("a")
    settled = until(lambda: (m.settle_tick(time.monotonic()), not m.settling)[1], 4)
    check(f"A {'once' if presses == 1 else 'twice'} before it's even listening: {want}, as it shows "
          f"({now_is(f1['pid'])}, dropped {len([e for e in log() if e.get('pid') == f1['pid'] and 'dropped' in e])})",
          settled and now_is(f1["pid"]) == want and m.paused == (want == "paused")
          and ("pausing_keep_force volume 80 1" in told(f1["pid"])) and not m.muted)
    m.stop()

# Plex (and Jellyfin): their own way of starting again
restarts = []
m.plex_restart = lambda target: restarts.append((target, m.start_paused))
m.plex_now = lambda: 1234.0
m.proc = subprocess.Popen(["sleep", "30"], stdin=subprocess.PIPE, text=True)
m.kind, m.cur, m.sound_used, m.paused = "plex", {"title": "x", "src": "/library/1", "dur": 3000}, ("", ""), False
busctl(H, "Disconnect"); busctl(H, "Connect")
look()
check(f"Plex: started again where it was, through them ({restarts})", restarts == [(1234.0, False)])
m.sound_used = ("bluetooth", H)
busctl(H, "Disconnect")
look()
check("...gone: started again paused", restarts[-1] == (1234.0, True))
m.proc.kill(); m.proc.wait(); m.proc, m.kind, m.cur = None, None, None
del m.plex_restart, m.plex_now

# Settings > Sound changed while the headphones play; and music in the terminal
busctl(H, "Connect")
k = len(starts())
m.play(songs, 2, show=False)
s1 = start_no(k + 1)
g.sound_cards = lambda: [("Headphones", "Headphones")]
m.set_setting("sound", "Headphones")
look()
s2 = start_no(k + 2)
check(f"Settings > Sound set to a card while the headphones play: there it goes, and says so ({m.msg})",
      opt(s1["argv"], "-ao") == "alsa:device=bluealsa,alsa" and opt(s2["argv"], "-ao") ==
      "alsa:device=default=Headphones,alsa" and m.msg == "Sound through Headphones" and not m.paused
      and not m.muted and now_is(s2["pid"]) == "playing")
m.set_setting("sound", "Auto")
look()
s3 = start_no(k + 3)
check(f"...back to Auto: the headphones again ({m.msg})", opt(s3["argv"], "-ao") == "alsa:device=bluealsa,alsa"
      and m.msg == "Sound through WH-1000XM4")
g.sound_cards = lambda: []
m.set_setting("start_song", "On")             # (music that comes back after a game or a video: not this time)
m.leave()
check("media mode closed: the music plays on in the terminal", not m.active and m.proc is not None
      and m.kind == "audio")
busctl(H, "Disconnect")
look()
check("...the headphones go: it stops (nothing in the terminal shows it's paused), and doesn't come back",
      m.proc is None and m.kind is None and still(k + 3) and m.resume_later is None
      and until(lambda: "quit" in told(s3["pid"]), 3))
m.set_setting("start_song", "Off")
m.enter()

# ---- a game: its sound moves too, through the real emulator --------------------------------------------------------------
GEN = SP + "/sega/Pitato Sega Test (World).md"
have_core = os.path.exists(SP + "/sega/cores/genesis_plus_gx_libretro.so") and os.path.exists(GEN)
if not have_core:
    print("(a game's sound moving too: needs the Genesis emulator and test game (sega), not here)")
if have_core:
    g.CORE_DIRS = (SP + "/sega/cores",)
    FBF = S + "/fb.bin"
    os.environ["PITATO_FB"] = f"{FBF}:640x480:16"; open(FBF, "wb").write(bytes(640 * 480 * 2))
    rom = f"{HOME}/Games/genesis/Pitato Sega Test (World).md"
    shutil.copy(GEN, rom)
    g.screen_picture = lambda *a, **k: None

    def plays():
        try:
            return [x.split(None, 1) + [""] for x in open(APLOG).read().splitlines()]
        except OSError:
            return []

    busctl(H, "Connect")
    gi = m.tab_index("games")
    m.load_tab(gi)
    row = next(it for it in m.tab_items(gi) if it.get("kind") == "game")
    m.tab, m.view = gi, "list"
    m.game_open(row)
    check("a game, with the headphones on", m.game is not None and m.game.wait_started(20)
          and m.game_sound == ("bluetooth", H))
    check(f"...its sound through them ({plays()[-1:]})", until(lambda: len(plays()) == 1, 5)
          and "-D bluealsa" in plays()[0][1])
    busctl(H, "Disconnect")
    look()
    check(f"the headphones went: its menu, the game paused ({m.view}, {m.msg})",
          m.view == "gamemenu" and m.game.state == "paused" and m.msg == "Paused: WH-1000XM4 disconnected"
          and m.game_sound == ("", ""))
    time.sleep(0.5)
    check("...no sound while it's paused", len(plays()) == 1)
    m.press("b")
    check(f"back to the game: its sound through the Pi's own ({plays()[-1:]})",
          until(lambda: len(plays()) == 2, 5) and "-D" not in plays()[1][1] and m.view == "game")
    busctl(H, "Connect")
    look()
    check(f"the headphones back: its sound through them, playing on ({plays()[-1:]}, {m.msg})",
          until(lambda: len(plays()) == 3, 5) and "-D bluealsa" in plays()[2][1] and m.view == "game"
          and m.msg == "Sound through WH-1000XM4" and m.game_sound == ("bluetooth", H))
    m.game.send("sound default:CARD=Headphones")
    check("the emulator's sound command: a card", until(lambda: len(plays()) == 4, 5)
          and "-D default:CARD=Headphones" in plays()[3][1])
    m.game.send("sound -")
    check("...and the system's own", until(lambda: len(plays()) == 5, 5) and "-D" not in plays()[4][1])
    m.game_end()
    check("the game over: nothing to move", m.game is None and m.game_sound is None)
else:
    print("(no Genesis core here: the game's part skipped)")

# ---- Settings > Bluetooth: connecting headphones says where the sound goes ------------------------------------------------
busctl(H, "Disconnect")
b = m.bt
b.refresh()
check("headphones connected: their sound comes up", b.connect(HP) is None
      and until(lambda: b.snapshot()["busy"] is None, 12)
      and b.snapshot()["status"] == "WH-1000XM4 is connected. Sound plays through it")
busctl(H, "Disconnect")
F.change(lambda s: s["devices"][HP].update(a2dp_after=1.5))
b.refresh()
check("...slow to come up: waited for", b.connect(HP) is None and until(lambda: b.snapshot()["busy"] is None, 12)
      and b.snapshot()["status"] == "WH-1000XM4 is connected. Sound plays through it")
busctl(H, "Disconnect")
m.set_setting("sound", "Headphones")
b.refresh()
check(f"...Settings > Sound on a card: theirs all the same ({b.snapshot()['status']})", b.connect(HP) is None
      and until(lambda: b.snapshot()["busy"] is None, 12)
      and b.snapshot()["status"] == "WH-1000XM4 is connected. Sound plays through it"
      and g.sound_place(m.setting("sound")) == ("bluetooth", H))
m.set_setting("sound", "Auto")

# looking round makes their sound skip (a Pi's Bluetooth shares its radio): stopped as they connect, and not started
# by Settings > Bluetooth opening while they're on
busctl(H, "Disconnect")
b.refresh()
b.watch("screen", True)
mark = len(F.log())
check("looking round, a page open", b.look() is None and b.snapshot()["looking"]
      and until(lambda: any("got scan on" in x for x in F.log()[mark:]), 4))
mark = len(F.log())
check("headphones connected meanwhile: done looking", b.connect(HP) is None
      and until(lambda: b.snapshot()["busy"] is None, 12) and not b.snapshot()["looking"]
      and b.snapshot()["status"] == "WH-1000XM4 is connected. Sound plays through it")
lines = F.log()[mark:]
off = next((i for i, x in enumerate(lines) if "got scan off" in x), None)
call = next((i for i, x in enumerate(lines) if " busctl " in f" {x} " and "Connect" in x), None)
check(f"...the looking stopped before they connected ({off}, {call}), and it stays stopped",
      off is not None and call is not None and off < call and not F.get()["discovering"]
      and (time.sleep(1.0) or not F.get()["discovering"]) and not b.snapshot()["looking"])
b.watch("screen", False)
until(lambda: b.thread is None, 6)
m.tab, m.view, m.set_page = m.tab_index("settings"), "list", "root"
m.load_tab(m.tab)
m.set_sel = m.settings_root_index("bluetooth")
m.press("a")
time.sleep(0.6)
check(f"Settings > Bluetooth opened with them on: not looking round ({m.set_page})",
      m.set_page == "bluetooth" and not m.bt.snapshot()["looking"] and not F.get()["discovering"])
check("...X still looks", (m.press("x"), until(lambda: m.bt.snapshot()["looking"], 2))[1]
      and until(lambda: F.get()["discovering"], 4))
m.press("b")
check("...gone from the page: done looking", m.set_page == "root"
      and until(lambda: not F.get()["discovering"] and m.bt.thread is None, 8))
busctl(H, "Disconnect")
m.bt.refresh()
m.set_sel = m.settings_root_index("bluetooth")
m.press("a")
check("...and with them off, it looks round on opening, as before", until(lambda: m.bt.snapshot()["looking"], 3))
m.press("b")
until(lambda: m.bt.thread is None, 8)
busctl(H, "Disconnect")
F.change(lambda s: s["devices"][HP].update(a2dp=False, a2dp_after=0))
b.refresh()
t0 = time.monotonic()
check("...BlueALSA never has them: just connected", b.connect(HP) is None
      and until(lambda: b.snapshot()["busy"] is None, 14) and b.snapshot()["status"] == "WH-1000XM4 is connected"
      and time.monotonic() - t0 >= 5)
busctl(H, "Disconnect")
os.environ["PATH"] = os.environ["PATH"].replace(SP + "/btfake/bin:", SP + "/btfake/bin_nb:")
os.makedirs(SP + "/btfake/bin_nb", exist_ok=True)
for f in ("busctl", "bluetoothctl", "rfkill"):
    if not os.path.exists(f"{SP}/btfake/bin_nb/{f}"):
        os.symlink(f"{SP}/btfake/bin/{f}", f"{SP}/btfake/bin_nb/{f}")
b.refresh()
check("...no BlueALSA on this Pi: run setup.sh again", b.connect(HP) is None
      and until(lambda: b.snapshot()["busy"] is None, 12)
      and b.snapshot()["status"] == "WH-1000XM4 is connected. To hear sound through it, run setup.sh again")
busctl(H, "Disconnect")
F.change(lambda s: s["devices"][HP].update(connect="profile"))
b.refresh()
check("...nothing to connect it to (no BlueALSA): the same", b.connect(HP) is None
      and until(lambda: b.snapshot()["busy"] is None, 12)
      and b.snapshot()["status"] == "To hear sound through WH-1000XM4, run setup.sh again")
os.environ["PATH"] = os.environ["PATH"].replace(SP + "/btfake/bin_nb:", SP + "/btfake/bin:")
F.change(lambda s: s["devices"][HP].update(connect="ok"))

# ---- the Bluetooth page's words -----------------------------------------------------------------------------------------
m.tab, m.view = m.tab_index("settings"), "list"
m.set_page = "root"
F.change(lambda s: s.update(powered=False))
m.bt_open()
time.sleep(0.6); m.bt.refresh()
check("Bluetooth off: turn it on for headphones too",
      "Turn it on to connect your controllers, keyboards and headphones" in drawn())
F.change(lambda s: s.update(powered=True))
m.bt_close()

# ---- setup.sh -----------------------------------------------------------------------------------------------------------
sh = open(ROOT + "/setup.sh").read()
check("setup.sh: BlueALSA and its ALSA plugin", "apt-get install -y bluez-alsa-utils libasound2-plugin-bluez" in sh)
check("...as the player only (A2DP source), its service set so", "/etc/systemd/system/bluealsa.service.d/pitato.conf"
      in sh and 'BT_ARGS="-p a2dp-source"' in sh and "ExecStart=\nExecStart=$(command -v bluealsa) $BT_ARGS" in sh
      and "systemctl restart bluealsa" in sh)
check("...not where PipeWire or PulseAudio has Bluetooth's sound",
      "command -v wireplumber >/dev/null 2>&1 || command -v pulseaudio >/dev/null 2>&1" in sh)
# its options, as setup.sh works them out, against a BlueALSA that has them (4.x's --help) and one that hasn't
start = sh.index('  BT_ARGS="-p a2dp-source"')
part = sh[start:sh.index("  install -d /etc/systemd/system/bluealsa.service.d", start)]
os.makedirs(S + "/bluealsa_new"); os.makedirs(S + "/bluealsa_old")
open(S + "/bluealsa_new/bluealsa", "w").write(
    "#!/bin/sh\ncat <<'EOF'\nUsage:\n  bluealsa -p PROFILE [OPTION]...\n\nOptions:\n  -h, --help\t\t\tprint this help\n"
    "  -p, --profile=NAME\t\tset enabled BT profiles\n  --keep-alive=SEC\t\tkeep Bluetooth transport alive\n"
    "  --a2dp-force-mono\t\ttry to force monophonic sound\n  --sbc-quality=MODE\t\tset SBC encoder quality mode\n"
    "EOF\n")
open(S + "/bluealsa_old/bluealsa", "w").write("#!/bin/sh\necho 'Usage: bluealsa [OPTION]...' >&2\nexit 1\n")
for d in ("bluealsa_new", "bluealsa_old"):
    os.chmod(f"{S}/{d}/bluealsa", 0o755)
said = {d: real_run(["bash", "-c", "set -e\n" + part + 'echo "$BT_ARGS"'], capture_output=True, text=True,
                    env=dict(os.environ, PATH=f"{S}/{d}:/usr/bin:/bin")) for d in ("bluealsa_new", "bluealsa_old")}
check(f"...a BlueALSA with them: SBC's medium (it doesn't skip) and the link kept up between songs "
      f"({said['bluealsa_new'].stdout.strip()!r})",
      said["bluealsa_new"].stdout.strip() == "-p a2dp-source --sbc-quality=medium --keep-alive=5")
check(f"...one without them (its help fails, even): just the player, as before ({said['bluealsa_old'].stdout.strip()!r})",
      said["bluealsa_old"].stdout.strip() == "-p a2dp-source" and said["bluealsa_old"].returncode == 0)
r = real_run(["bash", "-n", ROOT + "/setup.sh"], capture_output=True)
check("...and it still reads as bash", r.returncode == 0)

m.leave()
ImageDraw.ImageDraw.text = real_text
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
