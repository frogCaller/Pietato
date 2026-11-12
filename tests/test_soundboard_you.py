"""The Soundboard runs as you, not root (screens/soundboard.py, pitato/asyou.py): its player a process of your home
folder's owner (gpitest here), in its group and the audio, video and render ones and no others, with no new
privileges, a little ahead of the menus; aplay, arecord and FFmpeg, which it starts, the same (FFmpeg behind
everything else). What it makes is yours: your Soundboard folder, a recording in it, the sounds FFmpeg read kept in
your .cache; and the banks' file, which media mode writes (as root), is yours too. Your home folder root's: as root,
as before. The Band's player (bandplay.py, made from the Soundboard's) the same, the notes it makes kept in your
.cache. In a mount namespace of its own: everything it makes is on a tmpfs at /srv there."""
import json, os, pwd, grp, shutil, subprocess, sys, time, wave

from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
if os.environ.get("ASYOU_NS") != "1":
    os.execvpe("unshare", ["unshare", "-m", sys.executable, os.path.abspath(__file__)], dict(os.environ, ASYOU_NS="1"))
subprocess.run(["mount", "--make-rprivate", "/"], check=True)
subprocess.run(["mount", "-t", "tmpfs", "-o", "mode=755", "tmpfs", "/srv"], check=True)

sys.path.insert(0, TESTS)
import numpy as np  # noqa: E402
import pietato_all as g  # noqa: E402
import pitato.asyou as AY  # noqa: E402
import pitato.listen as L  # noqa: E402
import pitato.soundbank as B  # noqa: E402

T, USER = "/srv/board", "gpitest"
HOME, OUT = T + "/home", T + "/out"
me = pwd.getpwnam(USER)
gid_of = {n: grp.getgrnam(n).gr_gid for n in ("audio", "video", "render") if n in {x.gr_name for x in grp.getgrall()}}
want_groups = sorted({me.pw_gid, *gid_of.values()} - {0})
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def read(path):
    try:
        return open(path).read()
    except OSError:
        return ""


def said(path):
    return dict(line.split("=", 1) if "=" in line else (line.split(":")[0], line.split(":")[1].strip())
                for line in read(path).splitlines() if line.strip())


def status(pid):
    out = {}
    for line in read(f"/proc/{pid}/status").splitlines():
        k, _, v = line.partition(":")
        if k in ("Uid", "Gid", "Groups", "NoNewPrivs"):
            out[k] = v.split()
    return out


for d in (T + "/bin", HOME, OUT, T + "/media", T + "/static", T + "/asound/card0/pcm0p", T + "/asound/card1/pcm0c", T + "/v4l"):
    os.makedirs(d, exist_ok=True)
for d in (HOME, OUT, T + "/static"):
    os.chown(d, me.pw_uid, me.pw_gid)
WHO = ("""{ echo "uid=$(id -u)"; echo "groups=$(id -G)"; grep -E '^NoNewPrivs' /proc/self/status; echo "home=$HOME"; """
       """echo "nice=$(awk '{print $19}' /proc/self/stat)"; } """)
real_ffmpeg = shutil.which("ffmpeg")
for name, body in {
    "aplay": f"#!/bin/sh\n{WHO} > {OUT}/aplay.txt\nexec cat > /dev/null\n",
    "arecord": f"#!/bin/sh\n{WHO} > {OUT}/arecord.txt\nexec {sys.executable} {T}/bin/tone.py\n",
    "ffmpeg": f"#!/bin/sh\n{WHO} > {OUT}/ffmpeg.txt\nexec {real_ffmpeg} \"$@\"\n",
    "tone.py": "import math, struct, sys, time\nout = sys.stdout.buffer\nt0, n = time.monotonic(), 0\nwhile True:\n"
               "    out.write(b''.join(struct.pack('<h', int(9000 * math.sin(k * 0.08)) if 24000 <= k < 60000 else 0)"
               " for k in range(n, n + 960)))\n    out.flush()\n    n += 960\n"
               "    time.sleep(max(0, t0 + n / 48000 - time.monotonic()))\n",
}.items():
    open(f"{T}/bin/{name}", "w").write(body)
    os.chmod(f"{T}/bin/{name}", 0o755)
os.environ["PATH"] = T + "/bin:" + os.environ["PATH"]
open(T + "/asound/cards", "w").write(
    " 0 [vc4hdmi0       ]: vc4-hdmi - vc4-hdmi-0\n                      vc4-hdmi-0\n"
    " 1 [Device         ]: USB-Audio - USB PnP Sound Device\n                      USB PnP Sound Device at usb-1\n")
open(T + "/asound/card1/usbid", "w").write("0c76:161f\n")
L.ASOUND, L.V4L = T + "/asound", T + "/v4l"

AY.AS_YOU = True                                  # (tests/paths.py keeps the other tests' as root)
g.STATE_FILE = T + "/media/state.json"; g.CACHE_DIR = T + "/media/cache"; g.PLEX_FILE = T + "/media/plex.json"
g.STATIC = T + "/static"
json.dump({"settings": {}}, open(g.STATE_FILE, "w"))
g.home_dir = lambda: HOME
real_run = subprocess.run
subprocess.run = lambda cmd, *a, **k: (type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
                                       if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) in
                                       {"chvt", "fgconsole", "setterm", "amixer", "iw", "iwgetid", "nmcli", "vcgencmd"}
                                       else real_run(cmd, *a, **k))


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480; last = None
    def show(self, img): FB.last = img
    def show_part(self, img, box): FB.last = img
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
m = g.Media()
m.enter()
m.ears.stop()
m.listen_now = lambda quiet=False: None           # (the Bot's own listening: not this test's)


def spin(secs=0.3, cond=None):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        m.tick()
        if cond is not None and cond():
            return True
        time.sleep(0.01)
    return bool(cond()) if cond is not None else None


def owner(path):
    try:
        st = os.lstat(path)
    except OSError:
        return None
    return st.st_uid, st.st_gid


si = next(k for k, t in enumerate(g.LIBRARY) if t["name"] == "Soundboard")
m.open_app(si)
spin(8, lambda: m.board is not None and len(m.board.ready) == 24 and "home=" in read(OUT + "/aplay.txt"))
b = m.board
pid = b.proc.pid if b.proc is not None else 0
st = status(pid)
nice = os.getpriority(os.PRIO_PROCESS, pid) if pid else None
check(f"the Soundboard's player: as you ({st.get('Uid')}), in your group and the audio, video and render ones, no "
      f"others ({st.get('Groups')}); its sounds read ({len(b.ready)})", st.get("Uid") == [str(me.pw_uid)] * 4
      and st.get("Gid") == [str(me.pw_gid)] * 4 and sorted(int(x) for x in st.get("Groups", [])) == want_groups
      and len(b.ready) == 24)
check(f"...no new privileges (sudo can't take it to root: {st.get('NoNewPrivs')}), a little ahead of the menus "
      f"({nice}), which only root could have given it", st.get("NoNewPrivs") == ["1"] and nice == g.BOARD_NICE and nice < 0)
w = said(OUT + "/aplay.txt")
check(f"...aplay, which it starts: as you too ({w.get('uid')}, {w.get('groups')}), no new privileges, your home its "
      f"home", w.get("uid") == str(me.pw_uid) and sorted(int(x) for x in w.get("groups", "").split()) == want_groups
      and w.get("NoNewPrivs") == "1" and w.get("home") == HOME)
check(f"...your Soundboard folder, made for it: yours ({owner(HOME + '/Soundboard')})",
      owner(HOME + "/Soundboard") == (me.pw_uid, me.pw_gid))

# a sound at another rate: read through FFmpeg, as you, behind everything else; kept in your .cache
other = HOME + "/Soundboard/Beep.wav"
with wave.open(other, "wb") as wv:
    wv.setnchannels(2); wv.setsampwidth(2); wv.setframerate(44100)
    t = np.arange(22050) / 44100
    wv.writeframes(np.repeat((np.sin(2 * np.pi * 500 * t) * 9000).astype("<i2"), 2).tobytes())
os.chown(other, me.pw_uid, me.pw_gid)
spin(8, lambda: "Beep.wav" in b.ready)
w = said(OUT + "/ffmpeg.txt")
kept = HOME + "/.cache/pitato/soundboard"
names = os.listdir(kept) if os.path.isdir(kept) else []
check(f"a sound FFmpeg has to read: FFmpeg as you ({w.get('uid')}), no new privileges, behind everything else (nice "
      f"{w.get('nice')}); what it made kept in your .cache, yours ({names}, {owner(kept)})",
      "Beep.wav" in b.ready and w.get("uid") == str(me.pw_uid) and w.get("NoNewPrivs") == "1"
      and int(w.get("nice", "0")) > 0 and len(names) == 1
      and all(owner(p) == (me.pw_uid, me.pw_gid) for p in (HOME + "/.cache", kept, kept + "/" + (names or ["x"])[0])))
filed = T + "/static/" + B.FILE
check(f"the banks' file, written by media mode (root) for the new sound: yours, for anyone to read "
      f"({owner(filed)}, {oct(os.stat(filed).st_mode & 0o777) if os.path.exists(filed) else None})",
      owner(filed) == (me.pw_uid, me.pw_gid) and os.stat(filed).st_mode & 0o777 == 0o644
      and "up = Beep.wav" in read(filed))

# recording
spin(4, lambda: b.mic is not None)
m.press("start"); m.press("down"); m.press("down"); m.press("a")
spin(3, lambda: b.rec is not None and b.rec["secs"] > 1.4)
w = said(OUT + "/arecord.txt")
m.press("a")
spin(6, lambda: b.placing is not None)
rec = HOME + "/Soundboard/Recording 1.wav"
check(f"a recording: arecord as you ({w.get('uid')}, no new privileges: {w.get('NoNewPrivs')}); the file it's kept in, "
      f"yours ({owner(rec)}, {oct(os.stat(rec).st_mode & 0o777) if os.path.exists(rec) else None})",
      w.get("uid") == str(me.pw_uid) and w.get("NoNewPrivs") == "1" and owner(rec) == (me.pw_uid, me.pw_gid)
      and b.placing == "Recording 1.wav")
m.press("x")
spin(0.5)
check(f"...put on a button: the banks' file still yours ({owner(filed)})", owner(filed) == (me.pw_uid, me.pw_gid)
      and "x = Recording 1.wav" in read(filed))
left = [n for n in os.listdir(T + "/static") if n != B.FILE]
check(f"...and nothing else left in the static folder ({left}), nothing of root's in your Soundboard folder",
      not left and all(owner(os.path.join(HOME, "Soundboard", n)) == (me.pw_uid, me.pw_gid)
                       for n in os.listdir(HOME + "/Soundboard")))
m.go_home()
spin(0.5)
gone = spin(4, lambda: not os.path.exists(f"/proc/{pid}") or status(pid) == {})
check("leaving it: its player's gone", gone and b.proc is None)

# the Band's player (Apps > Band: screens/band.py), made from the Soundboard's: the same
os.remove(OUT + "/aplay.txt")
m.open_app(next(k for k, t in enumerate(g.LIBRARY) if t["name"] == "Band"))
spin(15, lambda: m.gig is not None and m.gig.loaded and len(m.gig.ready) == len(m.gig.loaded)
     and "home=" in read(OUT + "/aplay.txt"))
G = m.gig
pid = G.proc.pid if G.proc is not None else 0
st = status(pid)
nice = os.getpriority(os.PRIO_PROCESS, pid) if pid else None
w = said(OUT + "/aplay.txt")
kept = HOME + "/.cache/pitato/band"
names = os.listdir(kept) if os.path.isdir(kept) else []
check(f"the Band's player: as you ({st.get('Uid')}), in your groups and no others, no new privileges "
      f"({st.get('NoNewPrivs')}), ahead of the menus ({nice}); its aplay as you too ({w.get('uid')}); the notes it made "
      f"({len(names)}) kept in your .cache, yours", st.get("Uid") == [str(me.pw_uid)] * 4
      and st.get("Gid") == [str(me.pw_gid)] * 4 and sorted(int(x) for x in st.get("Groups", [])) == want_groups
      and st.get("NoNewPrivs") == ["1"] and nice == g.BOARD_NICE and w.get("uid") == str(me.pw_uid)
      and w.get("NoNewPrivs") == "1" and len(names) > 20 and len(G.ready) == len(G.loaded)
      and all(owner(p) == (me.pw_uid, me.pw_gid) for p in [kept] + [kept + "/" + n for n in names]))
m.go_home()
spin(0.5)
gone = spin(4, lambda: not os.path.exists(f"/proc/{pid}") or status(pid) == {})
check("...and gone as its page is left", gone and m.gig is None)

# your home folder root's: as root, as before
os.remove(OUT + "/aplay.txt")
ROOTS = T + "/roots"
os.makedirs(ROOTS)
g.home_dir = lambda: ROOTS
m.board = None
m.open_app(si)
spin(8, lambda: m.board is not None and len(m.board.ready) == 24 and "home=" in read(OUT + "/aplay.txt"))
b = m.board
pid = b.proc.pid if b.proc is not None else 0
st = status(pid)
check(f"your home folder root's: its player as root, as before ({st.get('Uid')}), still ahead of the menus "
      f"({os.getpriority(os.PRIO_PROCESS, pid) if pid else None})", st.get("Uid") == ["0"] * 4
      and os.getpriority(os.PRIO_PROCESS, pid) == g.BOARD_NICE and len(b.ready) == 24)
m.go_home()
spin(0.5)
m.leave()

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
