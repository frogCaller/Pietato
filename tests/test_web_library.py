"""The web page's Library in a real browser, and what's playing on its bar. All the library has is listed down its
left in two lots (what there is to watch and listen to, then the rest), each by its name; on a phone it's a page of
buttons instead: one tapped opens it with the way back, and Library again brings the page of them back. While
something plays on the Pi (a stand-in says so), its name is on the page's bar wherever you are but at the screen,
with Pause and Stop: the Pi is asked for each, and the name tapped is the screen. In Settings, the part picked in its
index is the one lit (the last ones too, that can't reach the top of the page), and then whichever you scroll to. The
page's own letters come from
the Pi (Fredoka for its headings, Atkinson Hyperlegible for the rest) and nothing else in its fonts folder does;
nothing's wider than a phone, and nothing goes wrong on the page. Media mode's main loop, its control server and
the web page, as a Pi has them."""
import asyncio, os, shutil, socket, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, SP); sys.path.insert(0, TESTS); sys.path.insert(0, ROOT)
import pietato_all as g

S = SP + "/t_weblib"
shutil.rmtree(S, ignore_errors=True)
H = S + "/home/u"
for d in ("Music", "Videos", "Pictures", "Documents"):
    os.makedirs(f"{H}/{d}")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
open(g.STATE_FILE, "w").write('{"settings": {"name": "Den"}}')
g.home_dir = lambda: H
import gk_static; gk_static.use_home(g, H)
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
g.list_devices = lambda: []
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


class UI:
    def write(self, *a): pass
    def syn(self): pass


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480; last = None; frames = 0
    def show(self, img): FB.last = img.copy(); FB.frames += 1; self.frames = FB.frames
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
m = g.Media(); m.enter()
m.glow_can = lambda: False                             # (no LEDs on this one: no LED backlight in its library)

# something playing, as far as the page is told: its name, paused or not; what the page asks of it, noted
PLAY = {"on": False, "paused": False, "asked": []}
real_state = m.web_state_now


def state_now():
    st = real_state()
    if PLAY["on"]:
        st["playing"] = {"title": "Steamboat Days", "sub": "1928", "src": "ia:steamboat/days.mp4", "kind": "video",
                         "pos": 90.0, "length": 420.0, "paused": PLAY["paused"], "song": ""}
    return st


def player(do):
    PLAY["asked"].append(do)
    if do == "pause":
        PLAY["paused"] = not PLAY["paused"]
    elif do == "stop":
        PLAY["on"] = False
    return {"ok": True}


m.web_state_now, m.web_player = state_now, player
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

import logging; logging.getLogger("werkzeug").setLevel(logging.ERROR)
sys.path.append(ROOT + "/pitato")
import webui
os.environ["HOME"] = H
webui.HOME = H; webui.STATIC = S + "/pitato/static"; os.makedirs(webui.STATIC + "/fonts")
for f in os.listdir(ROOT + "/static/fonts"):
    shutil.copy(ROOT + "/static/fonts/" + f, webui.STATIC + "/fonts/")
webui.FONTS_DIR = webui.STATIC + "/fonts"
open(S + "/pitato/setup.sh", "w").write("echo\n")
open(S + "/control-key", "w").write("k" * 32)
webui.THUMBS = H + "/.cache/pitato/thumbs"; webui.STATE_FILE = g.STATE_FILE; webui.NET_ROOT = g.NET_ROOT
webui.CONTROL = ("127.0.0.1", server.server_address[1]); webui.CONTROL_KEY = S + "/control-key"
socket.gethostname = lambda: "gpi"

# ---- the page's letters: its own two, from the Pi; nothing else from that folder ------------------------------------
c = webui.app.test_client()
NET = {"base_url": "http://gpi.local:5432"}
got = {n: c.get("/static/fonts/" + n, **NET) for n in ("fredoka-latin.woff2", "fredoka-latin-ext.woff2",
                                                        "next-latin.woff2", "Inter-Regular.otf", "OFL.txt")}
check(f"the page's letters from the Pi: Fredoka's and Atkinson Hyperlegible's ({[r.status_code for r in got.values()]})",
      all(got[n].status_code == 200 and got[n].mimetype == "font/woff2" and got[n].data[:4] == b"wOF2"
          for n in ("fredoka-latin.woff2", "fredoka-latin-ext.woff2", "next-latin.woff2")))
check("...nothing else in its fonts folder (the Pi's own screen's fonts, the licence)",
      got["Inter-Regular.otf"].status_code == 404 and got["OFL.txt"].status_code == 404)
page = open(ROOT + "/templates/index.html", encoding="utf-8").read()
ofl = open(ROOT + "/static/fonts/OFL.txt", encoding="utf-8").read()
check("...each asked for by the page, and credited beside the fonts (OFL.txt)",
      all(f"url(static/fonts/{n})" in page for n in ("fredoka-latin.woff2", "fredoka-latin-ext.woff2", "next-latin.woff2"))
      and "Fredoka (fredoka-latin.woff2, fredoka-latin-ext.woff2)" in ofl and "The Fredoka Project Authors" in ofl)

# ---- the web page in a browser ------------------------------------------------------------------------------------
PORT = 5473
threading.Thread(target=lambda: webui.app.run(host="127.0.0.1", port=PORT, threaded=True), daemon=True).start()
time.sleep(1)
try:
    from playwright.async_api import async_playwright
except ImportError:                                    # (not on the Pi's Python here: the Pi's side is tested)
    async_playwright = None
WATCH = ["Cartoons", "Films", "News", "Sports", "Radio"]          # (Your streams: once there are some)
MORE = ["Cameras", "Bot", "Draw", "Fish Tank"]                    # (LED backlight: on a Pi with LEDs)


async def web():
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        pg = await b.new_page(viewport={"width": 1280, "height": 900})
        oops = []
        pg.on("pageerror", lambda e: oops.append(str(e)))
        await pg.goto(f"http://localhost:{PORT}/#library")
        await pg.wait_for_selector("#ltabs .ltab", state="visible", timeout=10000)
        rail = await pg.evaluate("""Array.from(document.querySelector("#ltabs").children).map((e) =>
          (e.classList.contains("lgrp") ? "# " : "") + e.textContent)""")
        check(f"a computer: all the library has, down its left in two lots ({rail})",
              rail == ["# Watch and listen"] + WATCH + ["# More"] + MORE)
        box = await pg.evaluate("""(() => { const r = (s) => document.querySelector(s).getBoundingClientRect();
          const t = r("#ltabs"), c = r("#content"), l = r(".library");
          return [t.left - l.left, t.right <= c.left, t.height > 300, document.querySelectorAll("#ltabs .ltab svg").length]; })()""")
        check(f"...beside what's picked, each with its picture ({box})",
              box[0] < 4 and box[1] and box[2] and box[3] == len(WATCH + MORE))
        on = await pg.evaluate("""Array.from(document.querySelectorAll('#ltabs .ltab[aria-selected="true"]')).map((e) => e.textContent)""")
        check(f"...Cartoons first, its folders beside it and a box to search them ({on})", on == ["Cartoons"]
              and await pg.is_visible("#side .fold") and await pg.is_visible("#search") and not await pg.is_visible("#libBack"))
        await pg.click('#ltabs .ltab:text-is("Draw")')
        await pg.wait_for_selector(".dr-paper canvas", timeout=5000)
        on = await pg.evaluate("""Array.from(document.querySelectorAll('#ltabs .ltab[aria-selected="true"]')).map((e) => e.textContent)""")
        check(f"Draw picked: its page, nothing to search ({on})", on == ["Draw"] and not await pg.is_visible("#search")
              and not await pg.is_visible("#side .fold"))
        fonts = await pg.evaluate("""(async () => { await document.fonts.ready;
          const f = (s) => getComputedStyle(document.querySelector(s)).fontFamily.split(",")[0].replace(/"/g, "");
          return [f("#name"), f(".content-h h3"), f(".vbtn"), f("body"), document.fonts.check('600 20px "Fredoka"')]; })()""")
        check(f"the Pi's name, a heading and the page's own words in its letters ({fonts})",
              fonts[:4] == ["Fredoka", "Fredoka", "Fredoka", "Hyperlegible"] and fonts[4] is True)

        # what's playing: on the bar, but not at the screen
        check("nothing playing: nothing about it on the bar", not await pg.is_visible("#mini"))
        PLAY["on"] = True
        await pg.wait_for_selector("#mini", state="visible", timeout=6000)
        said = await pg.evaluate("""[document.querySelector("#miniTitle").textContent, document.querySelector("#miniSub").textContent,
          document.querySelector("#miniPause").getAttribute("aria-label")]""")
        check(f"something playing on the Pi: its name on the page's bar, with Pause ({said})",
              said == ["Steamboat Days", "1928", "Pause"])
        await pg.click("#miniPause")
        await pg.wait_for_function("""document.querySelector("#miniPause").getAttribute("aria-label") === "Play" """, timeout=6000)
        check(f"...Pause: asked of the Pi, and it's Play ({PLAY['asked']})", PLAY["asked"] == ["pause"] and PLAY["paused"])
        await pg.click(".vbtn[data-view='settings']")
        await pg.wait_for_selector("#setList .set-sec", timeout=8000)
        check("...in Settings, in Files: still there", await pg.is_visible("#mini"))

        # Settings' index: the part picked is the one lit
        async def lit():
            return await pg.evaluate("""(document.querySelector('#setIndex button[aria-current="true"]') || {})
              .textContent || null""")
        parts = await pg.evaluate("""Array.from(document.querySelectorAll("#setIndex button"), (b) => b.textContent)""")
        first = await lit()
        await pg.click("#setIndex button:last-child")
        await asyncio.sleep(1.5)
        last = await lit()
        check(f"Settings' index: its first part lit to start with, and the last one once it's picked, though it "
              f"can't reach the top of the page ({first!r}, then {last!r}, of {len(parts)})",
              len(parts) >= 5 and first == parts[0] and last == parts[-1])
        await pg.click("#setIndex button:nth-child(3)")
        await asyncio.sleep(1.5)
        third = await lit()
        top = await pg.evaluate("""document.querySelectorAll("#setList > .set-sec")[2].getBoundingClientRect().top""")
        check(f"...the third picked: lit, and at the top of the page ({third!r}, {top:.0f} px down)",
              third == parts[2] and 0 < top < 200)
        await pg.mouse.move(700, 500)
        await pg.mouse.wheel(0, -30000)
        await asyncio.sleep(0.8)
        up = await lit()
        await pg.mouse.wheel(0, 30000)
        await asyncio.sleep(0.8)
        down = await lit()
        check(f"...scrolled by hand, to the top and to the bottom: the part you've come to ({up!r}, {down!r})",
              up == parts[0] and down in parts[2:])
        await pg.mouse.wheel(0, -30000)

        # Settings > Background: a little picture of each, in full rows; one clicked is the Pi's background
        await pg.wait_for_function("""(() => { const p = document.querySelectorAll(".set-walls img.wall-pic");
          return p.length > 5 && Array.from(p).every((i) => i.complete && i.naturalWidth > 0); })()""", timeout=15000)
        walls = await pg.evaluate("""Array.from(document.querySelectorAll(".set-walls .wall-sw"), (b) => {
          const r = b.getBoundingClientRect(), i = b.querySelector("img");
          return [b.textContent.trim(), b.getAttribute("aria-pressed"), i ? i.naturalWidth : 0, Math.round(r.top)]; })""")
        tops = sorted(set(w[3] for w in walls))
        check(f"Settings > Background: a little picture of each ({len(walls)}), the one in use marked, in rows of five "
              f"({len(tops)} rows)", [w[0] for w in walls] == g.WALLPAPERS[:-1] + ["Your picture"]
              and [w[0] for w in walls if w[1] == "true"] == [m.setting("wallpaper")] == ["Midnight"]
              and all(w[2] == 192 for w in walls[:-1]) and [sum(w[3] == t for w in walls) for t in tops] == [5, 5, 5, 5])
        await pg.click('.set-walls .wall-sw:has-text("Candy")')
        await pg.wait_for_function("""(() => { const b = document.querySelector('.set-walls .wall-sw[aria-pressed="true"]');
          return b && b.textContent.trim() === "Candy"; })()""", timeout=8000)
        check(f"...one clicked: the Pi's background, and marked ({m.setting('wallpaper')})",
              m.setting("wallpaper") == "Candy")
        await pg.click('.set-walls .wall-sw:has-text("Your picture")')
        await asyncio.sleep(0.6)
        check("...Your picture: its pictures to pick from, under them; nothing changed until one's picked",
              await pg.evaluate("""!!document.querySelector(".set-walls ~ *")""") and m.setting("wallpaper") == "Candy")
        await pg.click('.set-walls .wall-sw:has-text("Midnight")')
        await pg.wait_for_function("""(() => { const b = document.querySelector('.set-walls .wall-sw[aria-pressed="true"]');
          return b && b.textContent.trim() === "Midnight"; })()""", timeout=8000)
        check("...another clicked: that one, the pictures put away", m.setting("wallpaper") == "Midnight"
              and not await pg.evaluate("""!!document.querySelector(".set-walls ~ *")"""))
        await pg.click(".vbtn[data-view='files']")
        await asyncio.sleep(0.3)
        here = await pg.is_visible("#mini")
        await pg.click("#miniOpen")
        await pg.wait_for_function("document.body.dataset.view === 'screen'", timeout=5000)
        check("...its name tapped: the Pi's screen, with all its buttons, and no bar there",
              here and not await pg.is_visible("#mini") and await pg.is_visible("#player")
              and (await pg.text_content("#pTitle")) == "Steamboat Days")
        await pg.click(".vbtn[data-view='library']")
        await pg.wait_for_selector("#mini", state="visible", timeout=5000)
        await pg.click("#mini [data-do='stop']")
        await pg.wait_for_selector("#mini", state="hidden", timeout=6000)
        check(f"...Stop: asked of the Pi, and the bar's gone ({PLAY['asked']})", PLAY["asked"] == ["pause", "stop"])
        await pg.screenshot(path=S + "/library.png")

        # a phone: a page of buttons, one opened, and back
        ph = await b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True,
                              has_touch=True)
        ph.on("pageerror", lambda e: oops.append(str(e)))
        await ph.goto(f"http://localhost:{PORT}/#library")
        await ph.wait_for_selector("#ltabs .ltab", state="visible", timeout=10000)
        tiles = await ph.evaluate("""Array.from(document.querySelectorAll("#ltabs .ltab")).map((e) => {
          const r = e.getBoundingClientRect(); return [e.textContent, Math.round(r.width), Math.round(r.height)]; })""")
        check(f"a phone, the first time: a page of buttons, all the library has ({[t[0] for t in tiles]})",
              [t[0] for t in tiles] == WATCH + MORE and all(t[1] >= 150 and t[2] >= 60 for t in tiles)
              and not await ph.is_visible("#content") and not await ph.is_visible("#libBack"))
        await ph.screenshot(path=S + "/library_phone.png")
        await ph.evaluate("window.scrollTo(0, 400)")
        await ph.tap('#ltabs .ltab:text-is("Fish Tank")')
        await ph.wait_for_selector(".ft-stage canvas", timeout=6000)
        check("...one tapped: its page from the top, the buttons gone, the way back above it",
              not await ph.is_visible("#ltabs .ltab") and await ph.is_visible("#libBack")
              and await ph.evaluate("window.scrollY") == 0)
        await ph.tap("#libBack")
        check("...Library, above it: the page of buttons again", await ph.is_visible("#ltabs .ltab")
              and not await ph.is_visible("#content"))
        await ph.tap('#ltabs .ltab:text-is("Radio")')
        await ph.wait_for_selector("#content .tile, #content .note", timeout=8000)
        await ph.tap(".dock button[data-view='library']")
        check("...Library on the bottom bar, there already: the page of buttons too",
              await ph.is_visible("#ltabs .ltab") and not await ph.is_visible("#content"))
        await ph.reload()
        await ph.wait_for_selector("#content .tile, #content .note", timeout=10000)
        check("...the page opened again: where you were (Radio), not the buttons",
              not await ph.is_visible("#ltabs .ltab") and await ph.is_visible("#libBack"))
        PLAY.update(on=True, paused=False)
        await ph.wait_for_selector("#mini", state="visible", timeout=6000)
        spot = await ph.evaluate("""(() => { const r = (s) => document.querySelector(s).getBoundingClientRect();
          return [Math.round(r("#mini").bottom), Math.round(r(".dock").top), innerHeight]; })()""")
        check(f"what's playing, on a phone: over the bottom bar, clear of it ({spot})", spot[0] <= spot[1] and spot[0] > spot[2] - 200)
        wide = await ph.evaluate("document.documentElement.scrollWidth")
        check(f"...nothing wider than the phone ({wide})", wide <= 390)
        await ph.tap(".dock button[data-view='settings']")
        await ph.wait_for_selector(".set-walls .wall-sw", timeout=8000)
        rows = await ph.evaluate("""(() => { const t = Array.from(document.querySelectorAll(".set-walls .wall-sw"),
          (b) => Math.round(b.getBoundingClientRect().top)); return Array.from(new Set(t), (y) => t.filter((v) => v === y).length); })()""")
        wide = await ph.evaluate("document.documentElement.scrollWidth")
        check(f"...Settings > Background on a phone: four across, nothing wider than it ({rows}, {wide})",
              rows == [4] * 5 and wide <= 390)
        await ph.screenshot(path=S + "/settings_phone.png")
        PLAY["on"] = False
        check(f"nothing went wrong on the page ({oops})", not oops)
        await b.close()


if async_playwright:
    asyncio.run(web())
else:
    print("(no browser for this Python: the web page in a browser is left to the other run)")
done.set()
check("the loop ran without trouble", not errors)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
