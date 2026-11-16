"""A USB camera plugged into a Pietato, seen from your other Pietatos (camera.py's OwnCameras.share, media.py's
share_cameras). It answers them on a port of its own, at every address of the Pi's, and nobody else: an address that
isn't one of yours is refused. What it says it is: this Pietato's name (with two cameras, each one's own name after
it). Your others are told it's there every few seconds, each straight to it, as camera.py tells of a Pi's camera: so
it's on their Camera tab under "On your network", found to be a Pi's camera, and its picture comes. Sharing off:
nobody's told, nobody's answered. camera.py itself sharing this Pi's camera: left to it. On this Pi it answers as it
always has. (With the pretend camera from camtest/bin.)"""
import http.client, json, os, shutil, socket, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
S = SP + "/t_camshare"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
os.makedirs(HOME)
os.environ["PATH"] = SP + "/camtest/bin:" + os.environ["PATH"]
os.environ["FAKE_V4L2_STATE"] = S + "/v4l2.json"
os.environ["FAKE_FFMPEG_LOG"] = S + "/ffmpeg.log"
sys.path.append(ROOT)
sys.path.insert(0, TESTS)
import pietato_all as g
import pitato.camera as c
import pitato.media as MM

g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    if t["type"] == "camera":
        t["files"] = [S + "/home/*/camera.txt"]
import gk_static; gk_static.use_home(g, HOME)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


# ---- a pretend USB camera or two, as the kernel lists them -----------------------------------------------------
V, DEVS = S + "/sys/video4linux", S + "/dev"
os.makedirs(DEVS)
c.V4L, c.DEV = V, DEVS


def plug(k, card):
    usb = f"{S}/usbdev/1-{k + 1}"
    os.makedirs(f"{usb}/1-{k + 1}:1.0", exist_ok=True)
    open(usb + "/idVendor", "w").write("046d\n")
    open(usb + "/idProduct", "w").write("082d\n")
    os.makedirs(f"{V}/video{k}", exist_ok=True)
    open(f"{V}/video{k}/name", "w").write(card + "\n")
    open(f"{V}/video{k}/index", "w").write("0\n")
    if not os.path.islink(f"{V}/video{k}/device"):
        os.symlink(f"{usb}/1-{k + 1}:1.0", f"{V}/video{k}/device")
    open(f"{DEVS}/video{k}", "w").close()


def ask(port, path, body=None, host="127.0.0.1"):
    """(status, the answer: JSON read, or its bytes) from a camera's server on this machine."""
    conn = http.client.HTTPConnection(host, port, timeout=15)
    try:
        conn.request("POST" if body is not None else "GET", path, body=None if body is None else json.dumps(body),
                     headers={"Content-Type": "application/json"} if body is not None else {})
        r = conn.getresponse()
        data = r.read()
        return r.status, (json.loads(data) if "json" in (r.getheader("Content-Type") or "") else data)
    finally:
        conn.close()


LOCAL, SHARED = 18434, (18438, 18439)
c.PORT = 18433                                         # (where camera.py itself would be, on this machine)
own = c.OwnCameras(ports=(LOCAL,), share_ports=SHARED)
yours = set()
own.may = lambda ip: ip in yours
own.named = lambda: "Den"
check("no camera plugged in: nothing to share", own.share() == [] and own.shared == {})
plug(0, "USB2.0 HD UVC WebCam: USB2.0 HD")
got = own.share() if own.look(now=True) else []
cid = got[0]["id"] if got else ""
check(f"a USB camera plugged in: it answers on a port of its own, under this Pietato's name ({got})",
      got == [{"id": cid, "port": SHARED[0], "name": "Den"}] and len(cid) == 8)
st, said = ask(SHARED[0], "/api/ptz")
check(f"an address that isn't one of your Pietatos': refused ({st}, {said.get('error')!r}), its picture too",
      st == 403 and "your other Pietatos" in said["error"] and ask(SHARED[0], "/api/camera.jpg")[0] == 403
      and ask(SHARED[0], "/api/camera/stream")[0] == 403 and ask(SHARED[0], "/api/photos", {})[0] == 403)
yours.add("127.0.0.1")
st, said = ask(SHARED[0], "/api/ptz")
check(f"one of yours: it says what it is, as a Pi's camera does ({said.get('server')}, {said.get('name')})",
      st == 200 and said["server"] == "Pitato camera" and said["name"] == "Den" and "available" in said)
st, jpeg = ask(SHARED[0], "/api/camera.jpg")
check(f"...and its picture comes ({len(jpeg) if st == 200 else jpeg} bytes)", st == 200 and jpeg[:2] == b"\xff\xd8")
st, said = ask(LOCAL, f"/usb/{cid}/api/ptz")
check(f"on this Pi it answers as it always has ({said.get('server')}): the same camera, started once",
      st == 200 and said["server"] == "USB camera" and ask(LOCAL, f"/usb/{cid}/api/camera.jpg")[0] == 200
      and len(open(S + "/ffmpeg.log").read().splitlines()) == 1)
check("...and only at this Pi's own address there", own.server.server_address[0] == "127.0.0.1"
      and own.shared[cid][0].server_address[0] in ("", "0.0.0.0"))
check("asked again: the same port, nothing started twice", own.share() == got and len(own.shared) == 1)
plug(1, "Bird Box Cam")
own.look(now=True)
two = own.share()
check(f"a second camera: a port of its own, and each named for the camera too ({[x['name'] for x in two]})",
      [x["port"] for x in two] == list(SHARED) and [x["name"] for x in two] == [
          "Den: USB2.0 HD UVC WebCam", "Den: Bird Box Cam"] and ask(SHARED[1], "/api/ptz")[1]["name"]
      == "Den: Bird Box Cam")
os.remove(f"{DEVS}/video1")
shutil.rmtree(f"{V}/video1")
own.look(now=True)
check("...taken out again: the first one alone, under this Pietato's name", own.share() == got
      and ask(SHARED[1], "/api/ptz")[0] == 404)

# ---- camera.py itself sharing this Pi's camera (setup.sh --camera): left to it ------------------------------------
feed = c.Feed(DEVS + "/video0")
script = c.serve(feed, c.Ptz(feed), c.Shutter(feed), port=c.PORT, host="127.0.0.1")
threading.Thread(target=script.serve_forever, daemon=True).start()
check("camera.py not looked for again yet: still shared", own.share() == got)
own.script = (-1e9, False)
check("camera.py's sharing this Pi's camera itself: these aren't", own.share() == [] and own.script[1] is True)
script.shutdown(); script.server_close()
feed.stop()
own.script = (-1e9, False)
check("...gone: shared again", own.share() == got)

# ---- media mode: your others told, and only them answered -----------------------------------------------------
BEACON = 18151
MM.CAM_BEACON = BEACON
m = g.Media()
m.state["settings"].update(name="Den", share="On")
own.close()
time.sleep(0.3)
m.camera.own.ports, m.camera.own.share_ports = (LOCAL,), SHARED
m.pie.heard.clear(); m.pie.peers_kept.clear()
rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
rx.bind(("127.0.0.1", BEACON))
rx.settimeout(1.0)


def heard():
    """The beacons that came, till none does for a moment."""
    out = []
    rx.settimeout(0.4)
    while True:
        try:
            out.append(json.loads(rx.recvfrom(4096)[0].decode()))
        except socket.timeout:
            return out


check("none of your other Pietatos about: nobody's told", m.share_cameras() == 0 and heard() == [])
st, said = ask(SHARED[0], "/api/ptz")
check(f"...and nobody's answered ({st})", st == 403)
m.pie.heard["http://127.0.0.1:5432"] = {"host": "Kitchen", "seen": time.time(), "peer": True}
told = m.share_cameras()
beacons = heard()
check(f"another of yours about: told the camera's there, straight to it, as camera.py tells of a Pi's ({beacons})",
      told == 1 and beacons == [{"gpicam": 1, "id": cid, "host": socket.gethostname(), "port": SHARED[0],
                                 "name": "Den"}])
st, said = ask(SHARED[0], "/api/ptz")
check(f"...and it's answered ({st}, {said.get('name')})", st == 200 and said["name"] == "Den")
kitchen = g.Camera()                                   # (the other Pietato's Camera tab, hearing that)
kitchen.heard("127.0.0.1", json.dumps(beacons[0]).encode())
found = kitchen.found_list()
check(f"on the other one's Camera tab: under \"On your network\", by this Pietato's name ({found})",
      [(f["addr"], f["name"], kitchen.kind_shown(f["addr"])) for f in found]
      == [(f"127.0.0.1:{SHARED[0]}", "Den", "Pietato camera")])
what = g.cam_detect(found[0]["addr"])
check(f"...found to be a Pi's camera there ({what})", what and what["kind"] == "pie" and what["name"] == "Den"
      and what["server"] == "Pitato camera")
got_frames = []
kitchen.on_frame = lambda: got_frames.append(1)
kitchen.select(found[0]["addr"])
kitchen.start()
end = time.time() + 15
while kitchen.frame is None and time.time() < end:
    time.sleep(0.1)
check(f"...and watched: its picture comes ({kitchen.frame.size if kitchen.frame else None})",
      kitchen.frame is not None and kitchen.frame.size == (640, 480))
kitchen.stop()
m.state["settings"]["share"] = "Off"
check("Share with other Pietatos off: nobody's told, nobody's answered", m.share_cameras() == 0 and heard() == []
      and ask(SHARED[0], "/api/ptz")[0] == 403 and ask(SHARED[0], "/api/camera.jpg")[0] == 403)
m.state["settings"]["share"] = "On"
m.pie.heard["http://127.0.0.1:5432"]["seen"] = time.time() - 600
check("the other one not heard for a while: it isn't answered any more", ask(SHARED[0], "/api/ptz")[0] == 403)
m.camera.own.close()
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
os._exit(0)
