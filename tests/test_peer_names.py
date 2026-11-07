"""Names for your Pietatos (Settings > Other Pietatos): this one's own, and each of your others on your network, so a
house of Pietatos all called the same tells apart in the send menus. This one's name goes in its beacon (what your
others call it) and at the top of its web page; another's, changed here, is asked of that one (from your network only,
with its web page's password when it has one: typed here) and said by its own beacon from then on, and called that here
at once. Media mode's main loop, its control server and its web page; another Pietato (peer_pietato.py, with its web
page and its main loop, in a process of its own); and the Settings page in a real browser."""
import asyncio, json, os, shutil, socket, subprocess, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, SP); sys.path.insert(0, TESTS); sys.path.insert(0, ROOT)
import pietato_all as g

S = SP + "/t_peernames"
shutil.rmtree(S, ignore_errors=True)
H, DEN = S + "/gpi", S + "/den"
for h in (H, DEN):
    for d in ("Music", "Videos", "Pictures", "Documents"):
        os.makedirs(f"{h}/{d}")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
open(g.STATE_FILE, "w").write('{"settings": {}}')
g.home_dir = lambda: H
import gk_static; gk_static.use_home(g, H)
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
g.list_devices = lambda: []
real_hostname = socket.gethostname
socket.gethostname = lambda: "gpi"
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


def until(cond, sec=5):
    t = time.monotonic()
    while not cond() and time.monotonic() - t < sec:
        time.sleep(0.05)
    return cond()


class UI:
    def write(self, *a): pass
    def syn(self): pass


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480; last = None; frames = 0
    def show(self, img): FB.last = img.copy(); FB.frames += 1; self.frames = FB.frames
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


# ---- the other one: the den's Pietato ------------------------------------------------------------------------------
LOG = S + "/den.log"
den = subprocess.Popen([sys.executable, TESTS + "/peer_pietato.py", DEN, LOG, "raspberrypi", "http://127.0.0.1:9",
                        "gpi"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
ready = den.stdout.readline().split()
DEN_URL = ready[1] if ready[:1] == ["READY"] else ""
check(f"the den's Pietato is up ({DEN_URL})", DEN_URL.startswith("http://127.0.0.1:"))
DEN_STATE = DEN + "/.pietato/state.json"
DEN_PW = DEN + "/.pietato/static/webui.txt"


def den_name():
    try:
        return (json.load(open(DEN_STATE)).get("settings") or {}).get("name")
    except (OSError, ValueError):
        return None


# ---- this one ------------------------------------------------------------------------------------------------------
g.Framebuffer = FB
m = g.Media(); m.enter()
control = g.Control()
server = g.serve_control(m, control, port=0, key="k" * 32)
done = threading.Event()
errors = []


def loop():
    try:
        g.run(UI(), m, control, stop=done.is_set)
    except Exception as ex:
        import traceback; traceback.print_exc(); errors.append(ex)


threading.Thread(target=loop, daemon=True).start()
time.sleep(0.4)
beacons = []
m.share_now_real = m.share_now
m.share_now = lambda: beacons.append(m.share_beacon(m.own_name()))


def heard_den(name="raspberrypi", accent="Green"):
    port = int(DEN_URL.rsplit(":", 1)[1])
    m.pie.heard.pop(DEN_URL, None)
    m.pie.hear("127.0.0.1", {"pietato": 1, "id": "den0den0den0", "port": port, "host": name, "accent": accent})


heard_den()
import logging; logging.getLogger("werkzeug").setLevel(logging.ERROR)
sys.path.append(ROOT + "/pitato")
import webui
webui.HOME = H; webui.STATIC = S + "/gpi/.pietato/static"; os.makedirs(webui.STATIC + "/fonts")
for f in os.listdir(ROOT + "/static/fonts"):
    shutil.copy(ROOT + "/static/fonts/" + f, webui.STATIC + "/fonts/")
webui.FONTS_DIR = webui.STATIC + "/fonts"
open(S + "/control-key", "w").write("k" * 32)
webui.STATE_FILE = g.STATE_FILE; webui.NET_ROOT = g.NET_ROOT
webui.CONTROL = ("127.0.0.1", server.server_address[1]); webui.CONTROL_KEY = S + "/control-key"
client = webui.app.test_client()
PAGE = {"headers": {"X-Pitato-Page": "1"}}


def section():
    return next(x for x in m.web_settings()["sections"] if x["id"] == "share")


# ---- Settings > Other Pietatos -------------------------------------------------------------------------------------
sec = section()
rows = {r["kind"]: r for r in sec["rows"]}
peer = rows.get("peer") or {}
check(f"Settings has Other Pietatos: this one's name, sharing, and each of yours on now ({sec['title']}, "
      f"{[r['kind'] for r in sec['rows']]})", sec["title"] == "Other Pietatos"
      and [r["kind"] for r in sec["rows"]] == ["text", "choice", "peer"])
check(f"...this one's name: none yet, the Pi's own in its place ({rows['text']})",
      rows["text"]["key"] == "name" and rows["text"]["value"] == "" and rows["text"]["placeholder"] == "gpi")
check(f"...the den's: its name, where it is, its colour, that it's on ({peer})", peer.get("value") == "raspberrypi"
      and peer.get("url") == DEN_URL and peer.get("where") == "127.0.0.1" and peer.get("seen") == "On now"
      and peer.get("colour", "").startswith("#") and "." not in peer.get("key", "."))

# this one's own name
r = client.post("/api/pi/settings", json={"key": "name", "value": "  Living   room "}, **PAGE)
check(f"named here: Living room ({r.get_json()})", r.status_code == 200 and m.own_name() == "Living room"
      and m.setting("name") == "Living room")
check(f"...its beacon says so, at once ({beacons[-1:]})", beacons and beacons[-1]["host"] == "Living room"
      and m.share_beacon(m.own_name())["host"] == "Living room")
check(f"...and so does its web page ({client.get('/api/info', **PAGE).get_json()['name']})",
      client.get("/api/info", **PAGE).get_json()["name"] == "Living room")
r = client.post("/api/pi/settings", json={"key": "name", "value": "x" * 41}, **PAGE)
check(f"...a name too long: said, and the old one kept ({r.get_json()})", "too long" in r.get_json().get("error", "")
      and m.own_name() == "Living room")
r = client.post("/api/pi/settings", json={"key": "name", "value": ""}, **PAGE)
check(f"...none: the Pi's own name again ({r.get_json().get('said')}, {m.own_name()})", m.own_name() == "gpi"
      and client.get("/api/info", **PAGE).get_json()["name"] == "gpi")
client.post("/api/pi/settings", json={"key": "name", "value": "Living room"}, **PAGE)

# another one's name, from here
r = client.post("/api/peer_name", json={"url": DEN_URL, "name": "Den"}, **PAGE)
check(f"the den's, changed here: asked of it, and it's called that ({r.get_json()}, {den_name()})",
      r.status_code == 200 and den_name() == "Den")
check(f"...called that here at once too, as in the send menus ({m.pie.peer_list()}, {m.saves_peers()})",
      (DEN_URL, "Den") in m.pie.peer_list() and any(u == DEN_URL and h.startswith("Den") for u, h in m.saves_peers()))
r = client.post("/api/peer_name", json={"url": "http://127.0.0.1:9", "name": "Attic"}, **PAGE)
check(f"...not one of yours on now: nothing asked ({r.status_code}, {r.get_json()})", r.status_code == 404)
r = client.post("/api/peer_name", json={"url": DEN_URL, "name": " "}, **PAGE)
check(f"...no name: said ({r.get_json()})", r.status_code == 400 and den_name() == "Den")
open(DEN_PW, "w").write("password = sesame\n")
r = client.post("/api/peer_name", json={"url": DEN_URL, "name": "Kids' room"}, **PAGE)
check(f"its web page has a password: asked for ({r.status_code}, {r.get_json()})", r.status_code == 409
      and r.get_json().get("kind") == "password" and den_name() == "Den")
r = client.post("/api/peer_name", json={"url": DEN_URL, "name": "Kids' room", "password": "open up"}, **PAGE)
check(f"...a wrong one: said ({r.get_json()})", r.status_code == 409 and "isn't its" in r.get_json()["error"]
      and den_name() == "Den")
r = client.post("/api/peer_name", json={"url": DEN_URL, "name": "Kids' room", "password": "sesame"}, **PAGE)
check(f"...its password: renamed ({r.get_json()}, {den_name()})", r.status_code == 200 and den_name() == "Kids' room")
os.remove(DEN_PW)

# this one, renamed by another of yours: from your network only, with its page's password when it has one
far = client.post("/api/name", json={"name": "Garage"}, base_url="http://192.168.1.30:5432",
                  environ_base={"REMOTE_ADDR": "8.8.8.8"})
check(f"renamed by another: not from outside your network ({far.status_code})", far.status_code == 403
      and m.own_name() == "Living room")
open(webui.STATIC + "/webui.txt", "w").write("password = sesame\n")
near = client.post("/api/name", json={"name": "Garage"}, base_url="http://192.168.1.30:5432",
                   environ_base={"REMOTE_ADDR": "192.168.1.31"})
check(f"...nor without its page's password, when it has one ({near.status_code})", near.status_code == 401
      and m.own_name() == "Living room")
os.remove(webui.STATIC + "/webui.txt")
near = client.post("/api/name", json={"name": "Garage"}, base_url="http://192.168.1.30:5432",
                   environ_base={"REMOTE_ADDR": "192.168.1.31"})
check(f"...from your network: renamed ({near.status_code}, {m.own_name()})", near.status_code == 200
      and m.own_name() == "Garage")
client.post("/api/pi/settings", json={"key": "name", "value": "Living room"}, **PAGE)

m.set_setting("share", "Off")
rows = section()["rows"]
check(f"sharing off: none looked for, and it says so ({[r['kind'] for r in rows]})",
      [r["kind"] for r in rows] == ["text", "choice", "info"] and "sharing off" in rows[-1]["value"])
m.set_setting("share", "On")
heard_den("Kids' room")

# ---- the Settings page, in a browser -------------------------------------------------------------------------------
threading.Thread(target=lambda: webui.app.run(host="127.0.0.1", port=5467, threaded=True), daemon=True).start()
time.sleep(1)
from playwright.async_api import async_playwright


async def web():
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        pg = await b.new_page(viewport={"width": 1280, "height": 900})
        await pg.goto("http://localhost:5467/#settings")
        await pg.wait_for_selector("#set-share .set-row", timeout=10000)
        check(f"the page: its name at the top ({await pg.inner_text('#name')})", await pg.inner_text("#name") == "Living room")
        row = pg.locator(f'#set-share .set-row[data-key="peer_{"".join(c if c.isalnum() else "_" for c in DEN_URL)}"]')
        check(f"...the den in Other Pietatos: where it is, and its name to change "
              f"({await row.locator('.peer-name').inner_text()}, {await row.locator('input').first.input_value()})",
              await row.count() == 1 and await row.locator(".peer-name").inner_text() == "The one at 127.0.0.1"
              and await row.locator("input").first.input_value() == "Kids' room")
        inp = row.locator("input").first
        await inp.fill("Bedroom")
        await row.locator("button", has_text="Rename").click()
        check(f"...renamed there: Bedroom ({den_name()})", await asyncio.to_thread(until, lambda: den_name() == "Bedroom"))
        await asyncio.sleep(1.2)
        check(f"...and shown by its new name ({await row.locator('input').first.input_value()})",
              await row.locator("input").first.input_value() == "Bedroom")
        open(DEN_PW, "w").write("password = sesame\n")
        await inp.fill("Guest room")
        await row.locator("button", has_text="Rename").click()
        pw_in = row.locator("input[type=password]")
        try:
            await pw_in.wait_for(state="visible", timeout=5000)
        except Exception:
            pass
        check("...its page has a password: a place to type it", await pw_in.is_visible() and den_name() == "Bedroom")
        await pw_in.fill("sesame")
        await row.locator("button", has_text="Rename").click()
        check(f"...typed: renamed ({den_name()})", await asyncio.to_thread(until, lambda: den_name() == "Guest room"))
        os.remove(DEN_PW)
        mine = pg.locator('#set-share .set-row[data-key="name"] input')
        await mine.fill("Kitchen")
        await pg.locator('#set-share .set-row[data-key="name"] button', has_text="Save").click()
        named = await asyncio.to_thread(until, lambda: m.own_name() == "Kitchen")
        try:
            await pg.wait_for_function("document.querySelector('#name').textContent === 'Kitchen'", timeout=5000)
        except Exception:
            pass
        check(f"this one renamed on its page: its name at the top too ({m.own_name()}, "
              f"{await pg.inner_text('#name')})", named and await pg.inner_text("#name") == "Kitchen")
        ph = await b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True,
                              has_touch=True)
        await ph.goto("http://localhost:5467/#settings")
        await ph.wait_for_selector("#set-share .peer-name", timeout=10000)
        await ph.locator("#set-share").scroll_into_view_if_needed()
        check("...a phone: no sideways scrolling", await ph.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        await ph.locator("#set-share").screenshot(path=S + "/other_pietatos_phone.png")
        await b.close()


asyncio.run(web())
den.stdin.write("quit\n"); den.stdin.flush()
done.set()
check("the loop ran without trouble", not errors)
socket.gethostname = real_hostname
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
