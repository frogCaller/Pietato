"""A Raspberry Pi camera module, on its ribbon (camera.py). Found by libcamera (rpicam-hello), asked once while the Pi's
camera receivers are there (none: nothing asked at all), and named by its sensor; with this Pi's own cameras
(OwnCameras: the Camera tab, the bot, your other Pietatos), its id the same each time. Its picture from rpicam-vid
(JPEGs one after another, each whole however it comes, a thumbnail's end inside it or not), started when someone looks
and let go after; a picture you take from rpicam-still, as big as it takes them up to PI_PHOTO_WIDE wide, and the live
picture back after; something else using it, said; it doesn't turn. camera.py on a Pi of its own (setup.sh --camera)
uses it when there's no USB camera, or when camera-server.txt says device = picam. No rpicam installed: nothing
listed. (With the pretend rpicam-hello, rpicam-vid and rpicam-still from camtest/bin.)"""
import http.client, io, json, os, shutil, sys, time
from paths import SP, ROOT  # noqa: E402  (this test's folder of work; the Pietato folder)
S = SP + "/t_picam"
shutil.rmtree(S, ignore_errors=True)
os.makedirs(S)
PATH = os.environ["PATH"]
os.environ["PATH"] = SP + "/camtest/bin:" + PATH
os.environ["FAKE_RPICAM_LOG"] = LOG = S + "/rpicam.log"
os.environ["FAKE_V4L2_STATE"] = S + "/v4l2.json"
os.environ["FAKE_FFMPEG_LOG"] = S + "/ffmpeg.log"
os.environ["FAKE_PICAM"] = "imx708_wide"
os.environ["PITATO_STATIC"] = S                       # (camera-server.txt's folder: none in it yet)
sys.path.append(ROOT)
import pitato.camera as c
from PIL import Image

ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


V, DEVS = S + "/sys/video4linux", S + "/dev"
os.makedirs(V)
os.makedirs(DEVS)
c.V4L, c.DEV = V, DEVS
c.IDLE = 3                                             # (nobody looking this long: the camera's let go)
c.PORT = 18533                                         # (where camera.py itself would be, on this machine: nothing)


def node(k, name):
    """One of the Pi's own video nodes (nothing on USB behind it)."""
    os.makedirs(f"{V}/video{k}", exist_ok=True)
    open(f"{V}/video{k}/name", "w").write(name + "\n")
    open(f"{DEVS}/video{k}", "w").close()


def asked(prog):
    try:
        return [x[len(prog) + 1:] for x in open(LOG).read().splitlines() if x.startswith(prog + " ")]
    except OSError:
        return []


def forget():
    """As a Pi that's just started: libcamera not asked yet."""
    c._PI.update(sign=None, cams=[], at=-1e9, asking=False)


def settle(own, secs=5.0):
    """Looks till libcamera's answered (it's asked on a thread of its own)."""
    end = time.monotonic() + secs
    got = own.look(now=True)
    while time.monotonic() < end and (c._PI["asking"] or not got):
        time.sleep(0.05)
        got = own.look(now=True)
    return got


def ask(port, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    try:
        conn.request("POST" if body is not None else "GET", path, body=None if body is None else json.dumps(body),
                     headers={"Content-Type": "application/json"} if body is not None else {})
        r = conn.getresponse()
        data = r.read()
        return r.status, (json.loads(data) if "json" in (r.getheader("Content-Type") or "") else data)
    finally:
        conn.close()


PORT = 18534
own = c.OwnCameras(ports=(PORT,), share_ports=(18538,))
own.may = lambda ip: ip == "127.0.0.1"
own.named = lambda: "Den"

# none: the Pi's own video blocks alone (its ISP), no camera receivers
node(5, "bcm2835-isp-output0")
node(6, "bcm2835-isp-capture1")
got = [own.look(now=True) for _ in range(3)][-1]
check(f"no camera module (the Pi's ISP's nodes alone): none listed, and libcamera not asked ({asked('rpicam-hello')})",
      got == [] and asked("rpicam-hello") == [])

# the camera receivers there, and libcamera says there's no camera
os.environ["FAKE_PICAM"] = ""
node(0, "unicam-image")
node(1, "unicam-embedded")
got = settle(own, 2.0)
for _ in range(5):
    got = own.look(now=True)
check(f"the Pi's camera receivers there, libcamera saying there's no camera: none listed, asked once, not on each look "
      f"({len(asked('rpicam-hello'))})", got == [] and asked("rpicam-hello") == ["--list-cameras"])

# a Camera Module 3 Wide, found as the Pi starts
os.environ["FAKE_PICAM"] = "imx708_wide"
forget()
got = settle(own)
for _ in range(5):
    got = own.look(now=True)
cid = got[0]["id"] if got else ""
check(f"a Camera Module 3 Wide: listed with this Pi's own cameras, by its name ({got}), libcamera asked once for it "
      f"({len(asked('rpicam-hello'))} times in all)",
      [(x["name"], x["addr"], x["dev"]) for x in got] == [("Pi Camera Module 3 Wide", f"127.0.0.1:{PORT}/usb/{cid}",
                                                             "picam:0")]
      and len(cid) == 8 and len(asked("rpicam-hello")) == 2)
forget()
again = settle(own)
check(f"...its id the same when libcamera's asked again (as the Pi starts again): {again and again[0]['id']}",
      [x["id"] for x in again] == [cid])

# its picture
t0 = time.monotonic()
status, jpeg = ask(PORT, f"/usb/{cid}/api/camera.jpg")
took = time.monotonic() - t0
im = Image.open(io.BytesIO(jpeg)) if status == 200 else None
if im is not None:
    im.load()
vid = asked("rpicam-vid")
check(f"its picture: a JPEG, whole ({im and im.size}, in {took:.1f} s), from rpicam-vid on the camera, nothing on the "
      f"Pi's screen, JPEGs one after another to camera.py ({vid})",
      status == 200 and im is not None and im.size == (640, 480)
      and vid == ["-n -t 0 --camera 0 --width 640 --height 480 --framerate 15 --codec mjpeg --quality 70 --flush -o -"])
feed = own.cams[cid][0]
a, n = feed.frame()
b, n2 = feed.frame(newer_than=n)
c2, n3 = feed.frame(newer_than=n2)
whole = all(x and x[:2] == b"\xff\xd8" and x[-2:] == b"\xff\xd9" and b"thumb" in x for x in (a, b, c2))
check(f"...more, as they come, each whole (the end of the thumbnail inside each not taken for its own: {whole}), "
      f"one after another ({n} {n2} {n3})", whole and n < n2 < n3 and len({a, b, c2}) >= 2)
status, info = ask(PORT, f"/usb/{cid}/api/info")
status2, ptz = ask(PORT, f"/usb/{cid}/api/ptz")
check(f"...it says what it is ({info.get('name')}, {info.get('camera', {}).get('card')}); it doesn't turn "
      f"({ptz.get('available')})", status == 200 and info.get("name") == "Pi Camera Module 3 Wide"
      and info["camera"]["running"] is True and status2 == 200 and ptz.get("available") is False)

# a picture you take
status, took = ask(PORT, f"/usb/{cid}/api/photos", {})
name = (took.get("photo") or {}).get("name", "") if isinstance(took, dict) else ""
status2, photo = ask(PORT, f"/usb/{cid}/api/photos/{name}") if name else (0, b"")
size = Image.open(io.BytesIO(photo)).size if status2 == 200 else None
still = asked("rpicam-still")
check(f"a picture taken: by rpicam-still, as big as the camera takes them, no wider than {c.PI_PHOTO_WIDE} "
      f"({size}; {still})", status == 200 and size == (2592, 1458) and len(still) == 1
      and still[0].startswith("-n -t 1000 --camera 0 --width 2592 --height 1458 -o "))
before = feed.seq
status, jpeg = ask(PORT, f"/usb/{cid}/api/camera.jpg")
fresh, _ = feed.frame(newer_than=before)
check(f"...and the live picture back after it ({status}, rpicam-vid started again: {len(asked('rpicam-vid'))})",
      status == 200 and jpeg[:2] == b"\xff\xd8" and fresh is not None and len(asked("rpicam-vid")) == 2)

# nobody looking: let go
end = time.monotonic() + 8
while time.monotonic() < end and feed.running():
    time.sleep(0.2)
check("nobody looking for a few seconds: the camera's let go (rpicam-vid stopped)", not feed.running())

# something else using it
os.environ["FAKE_PICAM_BUSY"] = "1"
feed.failed_at, feed.at = -1e9, -1e9                   # (its last picture long gone)
status, said = ask(PORT, f"/usb/{cid}/api/camera.jpg")
check(f"something else using the camera: said ({status}: {said.get('error') if isinstance(said, dict) else len(said)})",
      status == 503 and isinstance(said, dict) and said.get("error") == "Something else is using the camera")
del os.environ["FAKE_PICAM_BUSY"]

# for your other Pietatos
shared = own.share()
check(f"shared with your other Pietatos, as a USB camera is: under this Pietato's name ({shared})",
      [(x["id"], x["name"]) for x in shared] == [(cid, "Den")])
own.close()

# camera.py on a Pi of its own (setup.sh --camera)
f = c.Feed()
dev = f.configure()
check(f"camera.py on a Pi of its own, with no USB camera: its camera module ({dev}, {f.card})",
      dev == "picam:0" and f.card == "Pi Camera Module 3 Wide")
open(S + "/camera-server.txt", "w").write("device = picam\n")
f2 = c.Feed()
check(f"...or when camera-server.txt says device = picam ({f2.configure()})", f2.dev == "picam:0"
      and f2.card == "Pi Camera Module 3 Wide")
os.remove(S + "/camera-server.txt")

# Raspberry Pi OS's camera programs not installed
os.environ["PATH"] = PATH
forget()
n = len(asked("rpicam-hello"))
bare = c.OwnCameras(ports=(PORT + 1,), share_ports=())
got = [bare.look(now=True) for _ in range(3)][-1]
time.sleep(0.3)
got = bare.look(now=True)
check(f"rpicam not installed: no camera module listed, nothing asked ({got})",
      got == [] and len(asked("rpicam-hello")) == n)
bare.close()

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
