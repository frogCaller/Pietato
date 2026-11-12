"""The web page's Soundboard (pitato/webui.py, templates/index.html; pitato/soundbank.py). First what the page asks
of the Pi: its banks and sounds; a sound added (a wav, mp3 or ogg and nothing else, by a name that's safe, on My
sounds' first free button or the one it was dropped on), heard, renamed, deleted; put on a button (what was there
comes off it, or the two change places), on a bank, taken off; a bank added, renamed, moved, deleted; the starter
pack's put back; a recording (a WAV from the page), its silence trimmed on the Pi. Only the page asks: not another
site, not a form. Then the page itself, in a browser, with media mode running and its Soundboard open: the banks'
buttons laid out as on a controller; sounds added with the button, and dropped on the page and on a button; dragged
onto a button, from button to button, onto a bank; picked and placed by tapping (a phone); played here; renamed and
deleted (asked twice); banks added, named, moved and deleted; a sound recorded with the browser's microphone (a
pretend one), and where a browser won't give a microphone, the way to the secure page. Each change is on the Pi's
Soundboard at once (it's told: its own look every so often is turned off here), and what changes on the Pi shows on
the page. And the page's server installed as setup.sh installs it (on its own, pitato's folder beside it): the
Soundboard there too."""
import asyncio, io, json, logging, os, shutil, subprocess, sys, threading, time, wave
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import numpy as np
import pietato_all as g
import pitato.soundbank as SBK
from werkzeug.serving import make_server

S = SP + "/t_web_soundboard"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
for d in (HOME, S + "/bin", S + "/static/fonts", S + "/up", S + "/asound/card0/pcm0p", S + "/v4l"):
    os.makedirs(d)
ok_all = []
FOLDER = HOME + "/Soundboard"
FILED = S + "/static/soundboard.txt"


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def until(cond, secs=5.0):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return bool(cond())


def wav(secs=0.5, rate=48000, lead=0.0, f=500.0, amp=12000):
    """A WAV file's bytes: a tone, with silence before and after it."""
    n0 = int(lead * rate)
    t = np.arange(int(secs * rate)) / rate
    x = np.concatenate([np.zeros(n0), np.sin(2 * np.pi * f * t) * amp, np.zeros(n0)]).astype("<i2")
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(x.tobytes())
    return out.getvalue()


def length(path):
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate(), w.getframerate(), w.getnchannels(), w.getsampwidth()


# ---- what the page asks of the Pi ---------------------------------------------------------------------------------
sys.path.append(ROOT + "/pitato")
import webui
webui.HOME, webui.STATIC = HOME, S + "/static"
webui.CONTROL = ("127.0.0.1", 1)                       # (media mode isn't running yet: nothing answers there)
webui.settings = lambda: {}
c = webui.app.test_client()
H = {"X-Pitato-Page": "1"}


def ask(**body):
    return c.post("/api/soundboard", json=body)


def at(d, sid):
    return next((s["at"] for s in d["sounds"] if s["id"] == sid), "gone")


r = c.get("/api/soundboard", headers=H)
d = r.get_json()
check(f"the page asks for the Soundboard: its banks ({[b['name'] for b in d['banks']]}), eight buttons each "
      f"({d['pads']}), every sound there is ({len(d['sounds'])}, the starter pack's marked so) with the button it's on; "
      f"nothing written for that", r.status_code == 200 and [b["name"] for b in d["banks"]] == ["Starter", "Drums", "Arcade"]
      and d["pads"] == list(SBK.PADS) and len(d["sounds"]) == 24 and all(s.get("starter") for s in d["sounds"])
      and at(d, "Starter/Ding.wav") == [0, "a"] and d["starters_off"] == 0 and d["folder"] == "~/Soundboard"
      and not os.path.exists(FILED) and os.path.isdir(FOLDER))
check("...only the page asks (its own word with each request, which another site can't add); not another site at all",
      c.get("/api/soundboard").status_code == 403
      and c.get("/api/soundboard", headers=dict(H, **{"Sec-Fetch-Site": "cross-site"})).status_code == 403
      and c.put("/api/soundboard/sound?name=x.wav", data=wav()).status_code == 403
      and c.post("/api/soundboard", data="do=delete&id=x.wav", content_type="application/x-www-form-urlencoded").status_code == 415
      and c.post("/api/soundboard", json={"do": "bank_add"}, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403)
r = c.put("/api/soundboard/sound?name=Laugh.wav", data=wav(), headers=H)
d = r.get_json()
check(f"a sound added: a file in your Soundboard folder ({os.listdir(FOLDER)}), on My sounds' first free button "
      f"({at(d, 'Laugh.wav')}), first in the list, and the banks' file written",
      r.status_code == 200 and d["id"] == "Laugh.wav" and os.listdir(FOLDER) == ["Laugh.wav"]
      and d["banks"][3]["name"] == "My sounds" and at(d, "Laugh.wav") == [3, "up"] and d["sounds"][0]["id"] == "Laugh.wav"
      and d["sounds"][0]["name"] == "Laugh" and "[My sounds]\nup = Laugh.wav\n" in open(FILED).read())
r = c.put("/api/soundboard/sound?name=laugh.WAV", data=wav(), headers=H)
check(f"...one of that name already (whatever its capitals): kept beside it ({r.get_json().get('id')})",
      r.get_json().get("id") == "laugh 2.WAV" and sorted(os.listdir(FOLDER)) == ["Laugh.wav", "laugh 2.WAV"])
bad = {n: c.put("/api/soundboard/sound?" + webui.urllib.parse.urlencode({"name": n}), data=b"x" * 20, headers=H).status_code
       for n in ("evil.sh", "notes.txt", "song.mp4", "", "nothing", ".wav")}
check(f"...what isn't a wav, mp3 or ogg: not taken ({bad})", set(bad.values()) == {415}
      and sorted(os.listdir(FOLDER)) == ["Laugh.wav", "laugh 2.WAV"])
r = c.put("/api/soundboard/sound?name=.hidden.wav", data=wav(), headers=H)
check(f"...a name that would hide it: kept in plain sight ({r.get_json().get('id')})", r.get_json().get("id") == "hidden.wav")
os.remove(FOLDER + "/hidden.wav")
r = c.put("/api/soundboard/sound?name=..%2F..%2Fup%2Fout.wav", data=wav(), headers=H)
check(f"...a name with a path in it: kept by its own name, in the folder ({r.get_json().get('id')})",
      r.status_code == 200 and r.get_json()["id"] == "....upout.wav".lstrip(".") and not os.path.exists(S + "/up/out.wav")
      and all(os.path.dirname(os.path.realpath(os.path.join(FOLDER, n))) == os.path.realpath(FOLDER) for n in os.listdir(FOLDER)))
os.remove(FOLDER + "/" + r.get_json()["id"])
B = webui.soundbank()
big, B.SOUND_BYTES = B.SOUND_BYTES, 1000
r = c.put("/api/soundboard/sound?name=Big.wav", data=wav(), headers=H)
B.SOUND_BYTES = big
most, B.FILES_MOST = B.FILES_MOST, 2
r2 = c.put("/api/soundboard/sound?name=More.wav", data=wav(), headers=H)
B.FILES_MOST = most
check(f"...one too big, or one more than it takes: said, nothing kept ({r.status_code}: {r.get_json()['error']}; "
      f"{r2.status_code}: {r2.get_json()['error']})", r.status_code == 413 and r2.status_code == 409
      and sorted(os.listdir(FOLDER)) == ["Laugh.wav", "laugh 2.WAV"] and c.put("/api/soundboard/sound?name=e.wav", data=b"", headers=H).status_code == 400)
r = c.put("/api/soundboard/sound?name=Drop.ogg&bank=0&pad=a", data=b"OggS" + bytes(60), headers=H)
d = r.get_json()
check(f"one dropped on a button: on it ({d['banks'][0]['pads']['a']}); what was there, on no button ({at(d, 'Starter/Ding.wav')})",
      d["banks"][0]["pads"]["a"] == "Drop.ogg" and at(d, "Starter/Ding.wav") is None and d["starters_off"] == 1
      and not any(v == "Drop.ogg" for v in d["banks"][3]["pads"].values()))
r = c.get("/api/soundboard/sound?id=Laugh.wav")
r2 = c.get("/api/soundboard/sound?id=Starter/Kick.wav")
r3 = c.get("/api/soundboard/sound?id=Drop.ogg")
check(f"a sound, to hear in the browser: yours and the starter pack's, each as what it is ({r.mimetype}, {r3.mimetype})",
      r.status_code == 200 and r.data == wav() and r.mimetype == "audio/wav" and r2.status_code == 200
      and r2.data == open(ROOT + "/pitato/sounds/Kick.wav", "rb").read() and r3.mimetype == "audio/ogg")
open(HOME + "/plex.txt", "w").write("token = secret\n")
open(HOME + "/mine.wav", "wb").write(wav())
os.symlink(HOME + "/plex.txt", FOLDER + "/token.wav")
os.symlink("/etc/hostname", FOLDER + "/host.wav")
os.symlink(HOME + "/mine.wav", FOLDER + "/Linked.wav")
outside = {i: c.get("/api/soundboard/sound?" + webui.urllib.parse.urlencode({"id": i})).status_code
           for i in ("../../../etc/hostname", "Starter/../soundbank.py", "Starter/make.py", "/etc/hostname", "token.wav",
                     "host.wav", "nothing.wav", "")}
check(f"...nothing else by that way: not a file outside the folder, a link to one, or a link to a file with a token "
      f"in it ({outside}); a link to a sound elsewhere in your home folder is one",
      set(outside.values()) == {404} and c.get("/api/soundboard/sound?id=Linked.wav").status_code == 200)
for n in ("token.wav", "host.wav", "Linked.wav"):
    os.remove(FOLDER + "/" + n)
d = c.get("/api/soundboard", headers=H).get_json()
r = ask(do="put", id="Laugh.wav", bank=1, pad="x")
d = r.get_json()
check(f"a sound put on a button with one on it: there ({d['banks'][1]['pads']['x']}); the one that was comes off "
      f"({at(d, 'Starter/Clap.wav')}), and the button it left is free", d["banks"][1]["pads"]["x"] == "Laugh.wav"
      and at(d, "Starter/Clap.wav") is None and d["banks"][3]["pads"]["up"] is None)
d = ask(do="put", id="Laugh.wav", bank=1, pad="y", swap=True).get_json()
check(f"...from one button to another (the page says which): the two change places ({d['banks'][1]['pads']['x']}, "
      f"{d['banks'][1]['pads']['y']})", d["banks"][1]["pads"]["y"] == "Laugh.wav" and d["banks"][1]["pads"]["x"] == "Starter/Cowbell.wav")
d = ask(do="put", id="laugh 2.WAV", bank=1, pad="y").get_json()
d2 = c.get("/api/soundboard", headers=H).get_json()
check(f"...one of yours that comes off a button stays off (on no button: {at(d, 'Laugh.wav')}), at the next look too",
      at(d, "Laugh.wav") is None and at(d2, "Laugh.wav") is None and "off = Laugh.wav" in open(FILED).read())
d = ask(do="bank_put", id="Laugh.wav", bank=3).get_json()
r = ask(do="bank_put", id="Starter/Ding.wav", bank=2)
check(f"onto a bank: its first free button ({at(d, 'Laugh.wav')}), and no longer among those taken off; a full bank "
      f"says so ({r.status_code}: {r.get_json().get('error')})", at(d, "Laugh.wav") == [3, "up"]
      and "off = Laugh.wav" not in open(FILED).read() and r.status_code == 409 and "full" in r.get_json()["error"])
d = ask(do="lift", bank=1, pad="y").get_json()
check(f"taken off its button: on none ({at(d, 'laugh 2.WAV')}), still in the list and the folder",
      at(d, "laugh 2.WAV") is None and "laugh 2.WAV" in os.listdir(FOLDER))
r = ask(do="rename", id="laugh 2.WAV", name="Big laugh")
d = r.get_json()
check(f"renamed: the file ({sorted(os.listdir(FOLDER))}), by its new name in the list, its ending kept",
      r.status_code == 200 and d["id"] == "Big laugh.WAV" and "Big laugh.WAV" in os.listdir(FOLDER)
      and "laugh 2.WAV" not in os.listdir(FOLDER) and at(d, "Big laugh.WAV") is None)
d = ask(do="put", id="Big laugh.WAV", bank=3, pad="b").get_json()
d = ask(do="rename", id="Big laugh.WAV", name="Ha ha.wav").get_json()
check(f"...one on a button: on it still, by its new name ({d['banks'][3]['pads']['b']})",
      d["id"] == "Ha ha.WAV" and d["banks"][3]["pads"]["b"] == "Ha ha.WAV")
codes = {k: ask(do="rename", id=i, name=n).status_code for k, (i, n) in {
    "to one there is": ("Ha ha.WAV", "LAUGH"), "a starter": ("Starter/Ding.wav", "Dong"), "no name": ("Ha ha.WAV", "  "),
    "a path": ("Ha ha.WAV", "../../x"), "one that isn't": ("Nope.wav", "x")}.items()}
check(f"...not to a name there is, not to none; the starter pack's keep theirs ({codes}); a path in a name is just "
      f"letters ({sorted(os.listdir(FOLDER))})", codes["to one there is"] == 409 and codes["a starter"] == 404
      and codes["no name"] == 400 and codes["one that isn't"] == 404
      and all(os.path.dirname(os.path.realpath(os.path.join(FOLDER, n))) == os.path.realpath(FOLDER) for n in os.listdir(FOLDER)))
mine = [s["id"] for s in c.get("/api/soundboard", headers=H).get_json()["sounds"] if not s.get("starter")]
gone = [n for n in mine if n not in ("Laugh.wav", "Drop.ogg")]
for n in gone:
    r = ask(do="delete", id=n)
d = r.get_json()
check(f"deleted: the file gone, and off its button ({sorted(os.listdir(FOLDER))}); the starter pack's can't be "
      f"({ask(do='delete', id='Starter/Ding.wav').status_code})", sorted(os.listdir(FOLDER)) == ["Drop.ogg", "Laugh.wav"]
      and all(at(d, n) == "gone" for n in gone) and ask(do="delete", id="Starter/Ding.wav").status_code == 404
      and os.path.exists(ROOT + "/pitato/sounds/Ding.wav"))
r = ask(do="bank_add", name="Party [1]\n")
d = r.get_json()
n = d["bank"]
d = ask(do="bank_rename", bank=n, name="Drums").get_json()
d = ask(do="bank_move", bank=n, to=0).get_json()
check(f"a bank added, renamed (to a name there is: told apart), moved first: {[b['name'] for b in d['banks']]}",
      n == 4 and [b["name"] for b in d["banks"]] == ["Drums 2", "Starter", "Drums", "Arcade", "My sounds"] and d["bank"] == 0)
d = ask(do="bank_delete", bank=1).get_json()
check(f"a bank deleted: its sounds stay, on no button ({d['starters_off']} of the starter pack's now)",
      [b["name"] for b in d["banks"]] == ["Drums 2", "Drums", "Arcade", "My sounds"] and d["starters_off"] == 9
      and at(d, "Drop.ogg") is None and "Drop.ogg" in os.listdir(FOLDER))
r = ask(do="starter")
d = r.get_json()
check(f"the starter pack's put back on buttons: all of them ({[b['name'] for b in d['banks']]}, {d['starters_off']} on "
      f"none); again: nothing to do ({ask(do='starter').status_code})", d["starters_off"] == 0
      and [b["name"] for b in d["banks"]][-1] == "Starter" and at(d, "Starter/Clap.wav") == [1, "y"]
      and at(d, "Starter/Ding.wav") == [4, "a"]
      and ask(do="starter").status_code == 409)
r = c.put("/api/soundboard/sound?rec=1", data=wav(1.0, 44100, lead=0.7, amp=3000), headers=H)
d = r.get_json()
rec = FOLDER + "/Recording 1.wav"
got = length(rec) if os.path.isfile(rec) else (0, 0, 0, 0)
check(f"a recording from the page (2.4 s, a second of sound in it): kept as Recording 1, its silence trimmed "
      f"({got[0]:.2f} s), on a button ({at(d, 'Recording 1.wav')})", r.status_code == 200 and d["id"] == "Recording 1.wav"
      and 1.1 < got[0] < 1.3 and got[1:] == (44100, 1, 2) and at(d, "Recording 1.wav") is not None)
r = c.put("/api/soundboard/sound?rec=1", data=wav(0.0, 48000, lead=0.5), headers=H)
r2 = c.put("/api/soundboard/sound?rec=1", data=b"not a recording at all", headers=H)
check(f"...silence: nothing kept, and said ({r.status_code}: {r.get_json()['error']}); what isn't a recording: not "
      f"kept ({r2.status_code})", r.status_code == 422 and r.get_json()["error"] == "Nothing was heard"
      and r2.status_code == 422 and sorted(os.listdir(FOLDER)) == ["Drop.ogg", "Laugh.wav", "Recording 1.wav"])
check("...nothing left half done in the folder, or beside the banks' file",
      not [n for n in os.listdir(FOLDER) if n.startswith(".")] and sorted(os.listdir(S + "/static")) == ["fonts", "soundboard.txt"])
info = c.get("/api/info", headers=H).get_json()
check("the banks' file is one of the settings files (Files > Settings has it, to keep a copy of or put back)",
      "soundboard.txt" in info["settingsFiles"])
for n in os.listdir(FOLDER):
    os.remove(FOLDER + "/" + n)
os.remove(FILED)

# ---- installed, as setup.sh puts it on a Pi: the page's server on its own, with pitato's folder beside it ----------
import importlib.util
setup = open(ROOT + "/setup.sh").read()
T = S + "/installed"
steps = (setup[setup.index("rm -rf /usr/local/share/pitato/pitato "):setup.index("python3 -m compileall")]
         + setup[setup.index('step "Installing the web page'):setup.index("cat > /etc/systemd/system/pitato-web.service")])
rest = steps.replace("/usr/local/share/pitato", "")
safe = not any(x in rest for x in ("/usr/", "/etc/", "/var/", "/boot", "systemctl", "apt-get"))   # (only its own folder)
d2, heard, kept, where, files = {}, None, None, "", []
if safe:
    subprocess.run(["bash", "-c", "set -e\nHERE=" + ROOT + "\n" + steps.replace("/usr/local/share/pitato", T)
                    .replace('step "', 'echo "')], check=True, capture_output=True)
    spec = importlib.util.spec_from_file_location("webui_installed", T + "/webui.py")
    w2 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w2)
    w2.HOME, w2.STATIC, w2.KNOWS = S + "/home/installed", S + "/static_installed", True
    w2.CONTROL, w2.settings = ("127.0.0.1", 1), lambda: {}
    os.makedirs(w2.HOME); os.makedirs(w2.STATIC)
    c2 = w2.app.test_client()
    d2 = c2.get("/api/soundboard", headers=H).get_json() or {}
    heard = c2.get("/api/soundboard/sound?id=Starter/Ding.wav")
    kept = c2.put("/api/soundboard/sound?name=Mine.wav", data=wav(), headers=H)
    where = os.path.relpath(w2.soundbank().__file__, T)
    files = sorted(os.listdir(T + "/pitato/sounds"))
check(f"installed as setup.sh does (the page's server on its own, pitato's folder beside it: {where}): the Soundboard "
      f"there too, the starter pack with its credits ({len(d2.get('sounds', []))} sounds of {len(files)} files), one "
      f"heard, one of yours kept", safe and where == "pitato/soundbank.py" and not os.path.exists(T + "/soundbank.py")
      and len(d2.get("sounds", [])) == 24 and [b["name"] for b in d2.get("banks", [])] == ["Starter", "Drums", "Arcade"]
      and "CREDITS.txt" in files and len([n for n in files if n.endswith(".wav")]) == 24
      and heard.status_code == 200 and heard.data == open(ROOT + "/pitato/sounds/Ding.wav", "rb").read()
      and kept.status_code == 200 and os.listdir(S + "/home/installed/Soundboard") == ["Mine.wav"]
      and "up = Mine.wav" in open(S + "/static_installed/soundboard.txt").read())

# ---- the page, in a browser, with media mode running and its Soundboard open --------------------------------------
open(S + "/bin/aplay", "w").write("#!/bin/sh\nexec cat > /dev/null\n")
os.chmod(S + "/bin/aplay", 0o755)
os.environ["PATH"] = S + "/bin:" + os.environ["PATH"]
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/mcache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
g.STATIC = S + "/static"
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
g.home_dir = lambda: HOME
import pitato.listen as L
open(S + "/asound/cards", "w").write(" 0 [vc4hdmi0       ]: vc4-hdmi - vc4-hdmi-0\n                      vc4-hdmi-0\n")
L.ASOUND, L.V4L = S + "/asound", S + "/v4l"
g.BOARD_LOOK = g.BOARD_DEEP = 3600.0                   # (it doesn't look by itself, here: only when it's told)
real_run = subprocess.run
subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                       if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in
                                       {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli", "vcgencmd"}
                                       else real_run(cmd, *a, **k))


class FB:
    w, h = 640, 480
    real_w, real_h = 640, 480
    last = None
    frames = 0
    def show(self, img): FB.last = img; FB.frames += 1; self.frames = FB.frames
    def show_part(self, img, box): self.show(img)
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


class UI:
    def write(self, *a): pass
    def syn(self): pass


g.Framebuffer = FB
g.list_devices = lambda: []
m = g.Media()
m.enter()
control = g.Control()
server = g.serve_control(m, control, port=0, key="k" * 32)
done = threading.Event()
threading.Thread(target=lambda: g.run(UI(), m, control, stop=done.is_set), daemon=True).start()
for f in os.listdir(ROOT + "/static/fonts"):
    shutil.copy(ROOT + "/static/fonts/" + f, S + "/static/fonts/")
webui.FONTS_DIR = S + "/static/fonts"
open(S + "/control-key", "w").write("k" * 32)
webui.STATE_FILE = g.STATE_FILE; webui.NET_ROOT = g.NET_ROOT
webui.CONTROL = ("127.0.0.1", server.server_address[1]); webui.CONTROL_KEY = S + "/control-key"
logging.getLogger("werkzeug").setLevel(logging.ERROR)
web = make_server("127.0.0.1", 0, webui.app, threaded=True)
threading.Thread(target=web.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{web.server_port}"
opened = c.post("/api/pi/open", json={"app": "Soundboard"}, headers=H)
check(f"media mode's Soundboard, opened ({opened.get_json()}): its player running, its sounds ready",
      until(lambda: m.board is not None and m.board.proc is not None and len(m.board.ready) == 24, 15))
b = m.board
for name, f in (("Laugh.wav", 500), ("Wilhelm scream.wav", 700), ("Door bell.wav", 900), ("Drop.wav", 300), ("Onto.wav", 350)):
    open(f"{S}/up/{name}", "wb").write(wav(0.4, f=f))
open(S + "/up/notes.txt", "w").write("not a sound\n")


def on_pi(sid):
    """Where media mode's Soundboard has a sound: (its bank's name, the button), or None."""
    hit = SBK.where(b.banks, sid)
    return (b.banks[hit[0]]["name"], hit[1]) if hit else None


LOOK = """(() => {
  const q = (s) => [...document.querySelectorAll(s)];
  const box = (x) => { const r = x.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top), Math.round(r.right), Math.round(r.bottom)]; };
  return {
    banks: q('.sb-bank:not(.plus)').map((x) => x.textContent),
    bank: (document.querySelector('.sb-bank[aria-selected=true]') || {}).textContent,
    title: (document.querySelector('.sb-board-h h4') || {}).textContent,
    pads: Object.fromEntries(q('.sb-pad').map((x) => [x.dataset.pad, x.classList.contains('free') ? null : x.querySelector('.sb-name').textContent])),
    boxes: Object.fromEntries(q('.sb-pad').map((x) => [x.dataset.pad, box(x)])),
    playing: q('.sb-pad.playing').map((x) => x.dataset.pad),
    mine: q('.sb-list .sb-row').map((x) => [x.dataset.id, x.querySelector('.sb-t') ? x.querySelector('.sb-t').textContent : '', x.querySelector('.sb-where').textContent]),
    pack: q('.sb-pack .sb-row').length,
    picked: q('.sb-row.picked').map((x) => x.dataset.id),
    hint: (document.querySelector('.sb-hint') || {}).textContent,
    sub: document.querySelector('.content-h .src').textContent,
    toast: document.querySelector('#toast').classList.contains('show') ? document.querySelector('#toast').textContent : '',
    wide: document.documentElement.scrollWidth - window.innerWidth,
    hash: location.hash,
  };
})()"""
DROP = """async ([sel, name, bytes]) => {
  const dt = new DataTransfer();
  dt.items.add(new File([new Uint8Array(bytes)], name, {type: 'audio/wav'}));
  const where = sel ? document.querySelector(sel) : document.body;
  for (const kind of ['dragenter', 'dragover', 'drop']) where.dispatchEvent(new DragEvent(kind, {dataTransfer: dt, bubbles: true, cancelable: true}));
}"""
from playwright.async_api import async_playwright


async def browse():
    async with async_playwright() as pw:
        br = await pw.chromium.launch(args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])
        ctx = await br.new_context(viewport={"width": 1180, "height": 900}, permissions=["microphone"])
        pg = await ctx.new_page()
        oops = []
        pg.on("pageerror", lambda e: oops.append(str(e)))
        await pg.goto(URL + "/#library")
        await pg.wait_for_selector(".ltab", timeout=15000)
        tabs = await pg.eval_on_selector_all(".ltab", "bs => bs.map((b) => b.textContent)")
        await pg.click(".ltab:has-text('Soundboard')")
        await pg.wait_for_selector(".sb-pad", timeout=10000)
        got = await pg.evaluate(LOOK)
        check(f"the page: Soundboard in its Library ({'Soundboard' in tabs}); its banks ({got['banks']}), the first one's "
              f"eight buttons with their sounds ({got['pads']}), none of your own yet ({got['sub']!r}), the starter "
              f"pack's listed under ({got['pack']})", "Soundboard" in tabs and got["banks"] == ["Starter", "Drums", "Arcade"]
              and got["bank"] == "Starter" == got["title"]
              and got["pads"] == dict(SBK.STARTER_BANKS)["Starter"] and got["mine"] == [] and got["pack"] == 24
              and got["sub"] == "Yours go in ~/Soundboard")
        bx = got["boxes"]
        check("...the buttons laid out as on a controller: the d-pad's on the left (up, left and right, down), X, Y, A "
              "and B on the right, none over another, all on the page",
              bx["up"][3] <= bx["left"][1] and bx["left"][3] <= bx["down"][1] and bx["left"][2] <= bx["right"][0]
              and bx["right"][2] <= bx["y"][0] and bx["x"][3] <= bx["y"][1] and bx["y"][2] <= bx["a"][0]
              and bx["a"][3] <= bx["b"][1] and abs(bx["up"][0] - bx["down"][0]) <= 1 and abs(bx["x"][0] - bx["b"][0]) <= 1
              and got["wide"] <= 0)
        # sounds added with the button
        await pg.set_input_files(".sb input[type=file]", [S + "/up/Laugh.wav", S + "/up/notes.txt", S + "/up/Wilhelm scream.wav"])
        await pg.wait_for_function("document.querySelectorAll('.sb-list .sb-row').length === 2", timeout=10000)
        got = await pg.evaluate(LOOK)
        here = until(lambda: on_pi("Wilhelm scream.wav") == ("My sounds", "left"), 1.5)
        check(f"Add sounds, two sounds and a file that isn't one: the two are in your folder "
              f"({sorted(os.listdir(FOLDER))}), on My sounds' first buttons ({got['pads']}), the bank shown, the newest "
              f"first in the list ({[r[1] for r in got['mine']]}); the other's left out, and said",
              sorted(os.listdir(FOLDER)) == ["Laugh.wav", "Wilhelm scream.wav"] and got["bank"] == "My sounds"
              and got["pads"]["up"] == "Laugh" and got["pads"]["left"] == "Wilhelm scream"
              and [r[1] for r in got["mine"]] == ["Wilhelm scream", "Laugh"]
              and got["toast"] == "Wilhelm scream is on Left in My sounds. One file wasn't a wav, mp3 or ogg"
              and got["sub"] == "2 sounds of yours, in ~/Soundboard")
        check(f"...and media mode's Soundboard has them at once ({on_pi('Laugh.wav')}, {on_pi('Wilhelm scream.wav')}: "
              f"told, not at its own next look), ready to play ({sorted(x for x in b.ready if not x.startswith('Starter'))})",
              here and on_pi("Laugh.wav") == ("My sounds", "up")
              and until(lambda: {"Laugh.wav", "Wilhelm scream.wav"} <= set(b.ready), 5))
        # dragging
        await pg.click(".sb-bank:has-text('Starter')")
        await pg.drag_and_drop(".sb-row[data-id='Laugh.wav']", ".sb-pad[data-pad='a']")
        await pg.wait_for_function("document.querySelector('.sb-pad[data-pad=a] .sb-name').textContent === 'Laugh'", timeout=6000)
        got = await pg.evaluate(LOOK)
        ding = await pg.evaluate("document.querySelector(\".sb-row[data-id='Starter/Ding.wav'] .sb-where\").textContent")
        check(f"a sound dragged from the list onto a button: on it ({got['pads']['a']}); what was there, on no button "
              f"({ding!r}); on the Pi too ({on_pi('Laugh.wav')})", got["pads"]["a"] == "Laugh" and ding == "On no button"
              and until(lambda: on_pi("Laugh.wav") == ("Starter", "a") and on_pi("Starter/Ding.wav") is None, 1.5))
        await pg.drag_and_drop(".sb-pad[data-pad='a']", ".sb-pad[data-pad='b']")
        await pg.wait_for_function("document.querySelector('.sb-pad[data-pad=b] .sb-name').textContent === 'Laugh'", timeout=6000)
        got = await pg.evaluate(LOOK)
        check(f"...from one button onto another: the two change places ({got['pads']['a']}, {got['pads']['b']})",
              got["pads"]["a"] == "Buzzer" and got["pads"]["b"] == "Laugh"
              and until(lambda: on_pi("Starter/Buzzer.wav") == ("Starter", "a"), 1.5))
        await pg.drag_and_drop(".sb-row[data-id='Starter/Ding.wav']", ".sb-bank:has-text('My sounds')")
        await pg.wait_for_function("document.querySelector('.sb-bank[aria-selected=true]').textContent === 'My sounds'", timeout=6000)
        got = await pg.evaluate(LOOK)
        check(f"...onto a bank: its first free button, and that bank shown ({got['pads']})",
              got["bank"] == "My sounds" and got["pads"]["up"] == "Ding" and until(lambda: on_pi("Starter/Ding.wav") == ("My sounds", "up"), 1.5))
        await pg.drag_and_drop(".sb-row[data-id='Wilhelm scream.wav']", ".sb-bank:has-text('Drums')")
        await pg.wait_for_timeout(500)
        got = await pg.evaluate(LOOK)
        check(f"...onto a full one: said, and nothing moves ({got['toast']!r})", "Drums is full" in got["toast"]
              and on_pi("Wilhelm scream.wav") == ("My sounds", "left"))
        await pg.click(".sb-pad[data-pad='up'] .sb-off", force=True)
        await pg.wait_for_function("document.querySelector('.sb-pad[data-pad=up]').classList.contains('free')", timeout=6000)
        check("a button's ×: its sound taken off it", until(lambda: on_pi("Starter/Ding.wav") is None, 1.5))
        # files dropped: on the page, and on a button
        await pg.evaluate(DROP, [None, "Drop.wav", list(open(S + "/up/Drop.wav", "rb").read())])
        await pg.wait_for_selector(".sb-row[data-id='Drop.wav']", timeout=8000)
        got = await pg.evaluate(LOOK)
        check(f"a file dropped anywhere on the page: a sound, on My sounds' next free button ({got['pads']}); the page "
              f"stays here (not off to Files: {got['hash']})", got["pads"]["up"] == "Drop" and got["hash"] == "#library"
              and "Drop.wav" in os.listdir(FOLDER) and until(lambda: on_pi("Drop.wav") == ("My sounds", "up"), 1.5))
        await pg.click(".sb-bank:has-text('Arcade')")
        await pg.evaluate(DROP, [".sb-pad[data-pad='x']", "Onto.wav", list(open(S + "/up/Onto.wav", "rb").read())])
        await pg.wait_for_selector(".sb-row[data-id='Onto.wav']", timeout=8000)
        got = await pg.evaluate(LOOK)
        check(f"...dropped on a button: on that one ({got['pads']['x']}, in {got['bank']})", got["bank"] == "Arcade"
              and got["pads"]["x"] == "Onto" and until(lambda: on_pi("Onto.wav") == ("Arcade", "x"), 1.5)
              and on_pi("Starter/Power up.wav") is None)
        # heard here
        await pg.click(".sb-pad[data-pad='x']")
        await pg.wait_for_function("document.querySelectorAll('.sb-pad.playing').length === 1", timeout=5000)
        got = await pg.evaluate(LOOK)
        row = await pg.evaluate("document.querySelector(\".sb-row[data-id='Onto.wav']\").classList.contains('playing')")
        gone = True
        try:
            await pg.wait_for_function("document.querySelectorAll('.sb-pad.playing').length === 0", timeout=5000)
        except Exception:
            gone = False
        check(f"a button clicked: its sound plays here, in the browser, the button lit while it does ({got['playing']}; "
              f"its row in the list too: {row}), and not after", got["playing"] == ["x"] and row and gone)
        await pg.click(".sb-row[data-id='Starter/Applause.wav'] .sb-play")
        await pg.wait_for_function("document.querySelector(\".sb-row[data-id='Starter/Applause.wav']\").classList.contains('playing')", timeout=5000)
        await pg.click(".sb-row[data-id='Starter/Applause.wav'] .sb-play")
        await pg.wait_for_timeout(200)
        check("...a sound's own button in the list plays it, and stops it", not await pg.evaluate(
            "document.querySelector(\".sb-row[data-id='Starter/Applause.wav']\").classList.contains('playing')"))
        # renamed, deleted
        await pg.click(".sb-row[data-id='Wilhelm scream.wav'] .linkbtn:has-text('Rename')")
        await pg.fill(".sb-row .sb-in", "Scream")
        await pg.keyboard.press("Enter")
        await pg.wait_for_selector(".sb-row[data-id='Scream.wav']", timeout=6000)
        check(f"Rename: the file's ({sorted(os.listdir(FOLDER))}), still on its button there ({on_pi('Scream.wav')})",
              "Scream.wav" in os.listdir(FOLDER) and "Wilhelm scream.wav" not in os.listdir(FOLDER)
              and until(lambda: on_pi("Scream.wav") == ("My sounds", "left"), 1.5))
        await pg.click(".sb-row[data-id='Scream.wav'] .linkbtn:has-text('Rename')")
        await pg.fill(".sb-row .sb-in", "Never")
        await pg.keyboard.press("Escape")
        await pg.wait_for_selector(".sb-row[data-id='Scream.wav'] .sb-t", timeout=6000)
        check("...Esc: left as it was", "Scream.wav" in os.listdir(FOLDER) and "Never.wav" not in os.listdir(FOLDER))
        await pg.click(".sb-row[data-id='Scream.wav'] .linkbtn:has-text('Delete')")
        await pg.wait_for_selector(".sb-row[data-id='Scream.wav'] .linkbtn.armed", timeout=3000)
        armed = await pg.evaluate("document.querySelector(\".sb-row[data-id='Scream.wav'] .linkbtn.armed\").textContent")
        still = "Scream.wav" in os.listdir(FOLDER)
        await pg.click(".sb-row[data-id='Scream.wav'] .linkbtn.armed")
        await pg.wait_for_function("!document.querySelector(\".sb-row[data-id='Scream.wav']\")", timeout=6000)
        check(f"Delete: asked first ({armed!r}, the file still there: {still}), pressed again it's gone, from the folder "
              f"and the Pi's buttons", armed == "Sure?" and still and "Scream.wav" not in os.listdir(FOLDER)
              and until(lambda: on_pi("Scream.wav") is None and not any(x["pads"].get("left") for x in b.banks if x["name"] == "My sounds"), 1.5))
        packed = await pg.evaluate("document.querySelectorAll('.sb-pack .sb-row .linkbtn').length")
        check("...the starter pack's have no Rename or Delete", packed == 0)
        # banks
        await pg.click(".sb-bank.plus")
        await pg.wait_for_selector(".sb-board-h .sb-in", timeout=6000)
        await pg.fill(".sb-board-h .sb-in", "Party")
        await pg.keyboard.press("Enter")
        await pg.wait_for_function("[...document.querySelectorAll('.sb-bank')].some((x) => x.textContent === 'Party')", timeout=6000)
        got = await pg.evaluate(LOOK)
        check(f"+: a bank added, named as it's made ({got['banks']}), shown, empty; on the Pi ({[x['name'] for x in b.banks]})",
              got["banks"][-1] == "Party" and got["bank"] == "Party" and not any(got["pads"].values())
              and until(lambda: [x["name"] for x in b.banks][-1] == "Party", 1.5))
        await pg.click(".sb-move.back")
        await pg.wait_for_function("[...document.querySelectorAll('.sb-bank:not(.plus)')].map((x) => x.textContent).indexOf('Party') === 3", timeout=6000)
        got = await pg.evaluate(LOOK)
        check(f"...moved earlier ({got['banks']}), still the one shown", got["banks"].index("Party") == 3 and got["bank"] == "Party"
              and until(lambda: [x["name"] for x in b.banks].index("Party") == 3, 1.5))
        await pg.click(".sb-tools .linkbtn:has-text('Rename')")
        await pg.fill(".sb-board-h .sb-in", "Jingles")
        await pg.keyboard.press("Enter")
        await pg.wait_for_function("[...document.querySelectorAll('.sb-bank')].some((x) => x.textContent === 'Jingles')", timeout=6000)
        await pg.drag_and_drop(".sb-row[data-id='Drop.wav']", ".sb-pad[data-pad='y']")
        await pg.wait_for_function("document.querySelector('.sb-pad[data-pad=y] .sb-name').textContent === 'Drop'", timeout=6000)
        await pg.click(".sb-tools .linkbtn:has-text('Delete')")
        await pg.wait_for_selector(".sb-tools .linkbtn.armed", timeout=3000)
        await pg.click(".sb-tools .linkbtn.armed")
        await pg.wait_for_function("![...document.querySelectorAll('.sb-bank')].some((x) => x.textContent === 'Jingles')", timeout=6000)
        where = await pg.evaluate("document.querySelector(\".sb-row[data-id='Drop.wav'] .sb-where\").textContent")
        check(f"...renamed, a sound put in it, and deleted (asked first): the bank's gone, its sound isn't ({where!r})",
              where == "On no button" and "Drop.wav" in os.listdir(FOLDER) and until(lambda: "Jingles" not in [x["name"] for x in b.banks], 1.5))
        back = await pg.evaluate("(document.querySelector('.sb-pack-h .linkbtn') || {}).textContent")
        await pg.click(".sb-pack-h .linkbtn")
        await pg.wait_for_function("!document.querySelector('.sb-pack-h .linkbtn')", timeout=6000)
        check(f"the starter pack's that are on no button ({back!r}): put back on their own buttons",
              back == "Put the 2 on no button back" and until(lambda: on_pi("Starter/Ding.wav") is not None
                                                             and on_pi("Starter/Power up.wav") is not None, 1.5))
        # a recording, with the browser's microphone (Chromium's pretend one: a beep now and then)
        n_before = len(os.listdir(FOLDER))
        await pg.click(".sb-do .btn2:has-text('Record')")
        await pg.wait_for_selector(".sb-rec .sb-time", timeout=8000)
        await pg.wait_for_function("document.querySelector('.sb-rec .sb-time').textContent >= '0:02'", timeout=8000)
        level = await pg.evaluate("document.querySelector('.sb-meter i').style.width")
        await pg.click(".sb-rec .btn2:has-text('Stop')")
        await pg.wait_for_selector(".sb-row[data-id='Recording 1.wav']", timeout=10000)
        got = await pg.evaluate(LOOK)
        rec = length(FOLDER + "/Recording 1.wav")
        check(f"Record, with the browser's microphone: how long and how loud while it records ({level}); Stop: kept on "
              f"the Pi as Recording 1 ({rec[0]:.2f} s of the two and more recorded, {rec[1]} Hz, one channel), on a "
              f"button ({[r_ for r_ in got['mine'] if r_[0] == 'Recording 1.wav']}), and on the Pi's",
              0.05 < rec[0] <= 3.0 and rec[2:] == (1, 2) and level.endswith("%") and len(os.listdir(FOLDER)) == n_before + 1
              and until(lambda: on_pi("Recording 1.wav") is not None, 1.5) and "Recording 1 is on" in got["toast"])
        await pg.click(".sb-do .btn2:has-text('Record')")
        await pg.wait_for_selector(".sb-rec .sb-time", timeout=8000)
        await pg.wait_for_timeout(600)
        await pg.click(".sb-rec .linkbtn:has-text('Cancel')")
        await pg.wait_for_selector(".sb-do .btn2:has-text('Record')", timeout=5000)
        await pg.wait_for_timeout(400)
        check("...Cancel: nothing kept", len(os.listdir(FOLDER)) == n_before + 1)
        # what changes on the Pi shows here
        open(FOLDER + "/From the Pi.wav", "wb").write(wav(0.3))
        m.soon(lambda: m.board_look(time.monotonic(), force=True))     # (as its own look would, in a second)
        seen = True
        try:
            await pg.wait_for_selector(".sb-row[data-id='From the Pi.wav']", timeout=8000)
        except Exception:
            seen = False
        check("a sound that turns up on the Pi (a file put in the folder, one recorded there): on the page in a moment, "
              "without it being loaded again", seen)
        check(f"nothing went wrong on the page through all that ({oops})", not oops)
        await ctx.close()

        # a browser that won't give a microphone on this page
        ctx = await br.new_context(viewport={"width": 1180, "height": 900})
        pg = await ctx.new_page()
        await pg.add_init_script("Object.defineProperty(window, 'isSecureContext', {get: () => false});")
        await pg.goto(URL + "/#library")
        await pg.wait_for_selector(".ltab", timeout=15000)
        await pg.click(".ltab:has-text('Soundboard')")
        await pg.wait_for_selector(".sb-pad", timeout=10000)
        await pg.click(".sb-do .btn2:has-text('Record')")
        await pg.wait_for_selector(".sb-list .secure-note a", timeout=5000)
        link = await pg.evaluate("document.querySelector('.sb-list .secure-note a').href")
        check(f"where a browser won't give a page its microphone (not the secure page): no recording, and the way to "
              f"the secure page instead ({link})", link == "https://127.0.0.1:5443/#library"
              and await pg.evaluate("!document.querySelector('.sb-rec')"))
        # files dragged over another of the Library's pages still go to Files
        await pg.click(".ltab:has-text('Radio')")
        await pg.wait_for_timeout(300)
        await pg.evaluate("""() => { const dt = new DataTransfer(); dt.items.add(new File(['x'], 'x.txt'));
          document.body.dispatchEvent(new DragEvent('dragenter', {dataTransfer: dt, bubbles: true, cancelable: true})); }""")
        await pg.wait_for_timeout(300)
        check("files dragged over the rest of the page go to Files, as before",
              not (await pg.evaluate("location.hash")).startswith("#library"))
        await ctx.close()

        # a phone
        ctx = await br.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        pg = await ctx.new_page()
        oops = []
        pg.on("pageerror", lambda e: oops.append(str(e)))
        await pg.goto(URL + "/#library")
        await pg.wait_for_selector(".ltab", timeout=15000)
        await pg.tap(".ltab:has-text('Soundboard')")
        await pg.wait_for_selector(".sb-pad", timeout=10000)
        await pg.tap(".sb-bank:has-text('My sounds')")
        got = await pg.evaluate(LOOK)
        bx = got["boxes"]
        check(f"on a phone: the page no wider than its screen ({got['wide']}), the d-pad's buttons above the letters', "
              f"each wide enough for a name ({bx['up'][2] - bx['up'][0]} px)", got["wide"] <= 0 and bx["down"][3] <= bx["x"][1]
              and bx["up"][2] - bx["up"][0] >= 150 and all(v[0] >= 0 and v[2] <= 390 for v in bx.values()))
        await pg.tap(".sb-row[data-id='Laugh.wav'] .sb-t")
        got = await pg.evaluate(LOOK)
        check(f"...a sound tapped is picked up ({got['picked']}; {got['hint']!r})", got["picked"] == ["Laugh.wav"]
              and got["hint"] == "Tap a button to put Laugh on it.")
        await pg.tap(".sb-pad[data-pad='down']")
        await pg.wait_for_function("document.querySelector('.sb-pad[data-pad=down] .sb-name').textContent === 'Laugh'", timeout=6000)
        got = await pg.evaluate(LOOK)
        check(f"...and the button tapped next is where it goes ({got['pads']['down']}; on the Pi: {on_pi('Laugh.wav')}); "
              f"nothing's picked after ({got['picked']})", got["pads"]["down"] == "Laugh" and got["picked"] == []
              and until(lambda: on_pi("Laugh.wav") == ("My sounds", "down"), 1.5))
        await pg.tap(".sb-row[data-id='Laugh.wav'] .sb-t")
        await pg.tap(".sb-row[data-id='Laugh.wav'] .sb-t")
        got = await pg.evaluate(LOOK)
        check(f"...tapped again instead: put down ({got['picked']}), and nothing went wrong ({oops})",
              got["picked"] == [] and not oops)
        await br.close()


asyncio.run(browse())
filed = open(FILED).read()
check("the banks' file at the end of all that: one the Pi reads back as the page left it",
      SBK.arrange(filed, SBK.your_sounds(FOLDER), SBK.starter_sounds())[0] == b.banks or until(
          lambda: SBK.arrange(open(FILED).read(), SBK.your_sounds(FOLDER), SBK.starter_sounds())[0] == b.banks, 3))
done.set()
web.shutdown()

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
