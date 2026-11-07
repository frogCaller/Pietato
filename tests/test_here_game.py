"""Play here with a real game in a real browser (EmulatorJS, as the Pi gets it from npm, with its Game Boy core): picked
with Play here on, it plays on the page, and as it closes its save and where you were go back to the Pi (the emulator's
own state, out of RetroArch's wrapping, as the Pi keeps it); turned on while the game's on the Pi, the game moves to the
page and carries on from where you were there; turned off, it goes back to the Pi with where you were on the page.
While it plays on the page, the page's remote and its keyboard are the game's buttons, held as long as they're held (not
the Pi's), and its Hotkey brings up the emulator's own; the emulator shows no buttons of its own, and on a phone the
remote is under the game. Media mode's main loop, its control server and the web page; a tiny Game Boy cartridge of its
own, which counts once in its battery-backed RAM each time it starts, then writes there which of its buttons are down:
where you were is what that count says. (The page puts the save in as the game starts, so the count it makes then is
before the save's in, and the save's count is what it shows.)"""
import asyncio, os, shutil, socket, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, SP); sys.path.insert(0, TESTS); sys.path.insert(0, ROOT)
import pietato_all as g

S = SP + "/t_heregame"
shutil.rmtree(S, ignore_errors=True)
H = S + "/home/u"
for d in ("Music", "Videos", "Pictures", "Documents", "Games/gb", "Games/Saves"):
    os.makedirs(f"{H}/{d}")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
open(g.STATE_FILE, "w").write('{"settings": {}}')
g.home_dir = lambda: H
import gk_static; gk_static.use_home(g, H)
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
g.list_devices = lambda: []
g.find_core = lambda key: "/usr/lib/libretro/gambatte_libretro.so" if key in ("gb", "gbc") else None
SAVES = H + "/Games/Saves"
EJS = SP + "/ejs"                                     # (EmulatorJS's packages, as npm has them)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


def cartridge():
    """32 KB with 8 KB of battery-backed RAM (MBC1): it adds one to the RAM's first byte as it starts, then, over and
    over, writes which of its buttons are down in the next two (A 1, B 2, SELECT 4, START 8; right 1, left 2, up 4,
    down 8)."""
    rom = bytearray(32768)
    rom[0x100:0x104] = bytes([0x00, 0xC3, 0x50, 0x01])          # nop; jp 0x150
    rom[0x134:0x13B] = b"PIETATO"
    rom[0x147], rom[0x148], rom[0x149] = 0x03, 0x00, 0x02       # MBC1+RAM+BATTERY, 32 KB, 8 KB of RAM
    look = lambda which, at: [0x3E, which, 0xE0, 0x00,           # ld a,which; ldh (0x00),a: the buttons, or the d-pad
                              0xF0, 0x00, 0xF0, 0x00,            # ldh a,(0x00) twice (it settles)
                              0x2F, 0xE6, 0x0F,                  # cpl; and 0x0f: down is 1
                              0xEA, at, 0xA0]                    # ld (0xa0..),a
    prog = [0x3E, 0x0A, 0xEA, 0x00, 0x00,                        # ld a,0x0a; ld (0x0000),a: its RAM on
            0x21, 0x00, 0xA0, 0x34]                              # ld hl,0xa000; inc (hl)
    loop = look(0x10, 0x01) + look(0x20, 0x02)
    prog += loop + [0x18, (-(len(loop) + 2)) & 0xFF]             # jr: round again
    rom[0x150:0x150 + len(prog)] = bytes(prog)
    x = 0
    for b in rom[0x134:0x14D]:
        x = (x - b - 1) & 0xFF
    rom[0x14D] = x
    return bytes(rom)


open(H + "/Games/gb/Count.gb", "wb").write(cartridge())
open(SAVES + "/Count.srm", "wb").write(bytes([5]) + bytes(8191))


class UI:
    def write(self, *a): pass
    def syn(self): pass


class FB:
    w, h = 640, 480; real_w, real_h = 640, 480; last = None; frames = 0
    def show(self, img): FB.last = img.copy(); FB.frames += 1; self.frames = FB.frames
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


class FakeRun:
    """The game on the Pi (where you are, on the card as it ends: whatever's there)."""
    ended, state, error, disc, slow, cheevos, together = False, "on", None, (1, 1), False, None, None

    def __init__(self):
        self.game = {"path": H + "/Games/gb/Count.gb", "title": "Count", "system": "gb"}
        self.quits = 0

    def quit(self):
        self.quits += 1

    def pause(self):
        return True

    def __getattr__(self, name):
        return lambda *a, **k: None


g.Framebuffer = FB
m = g.Media(); m.enter()
control = g.Control()
server = g.serve_control(m, control, port=0, key="k" * 32)
port = server.server_address[1]
done = threading.Event()
errors = []


def loop():
    try:
        g.run(UI(), m, control, stop=done.is_set)
    except Exception as ex:
        import traceback; traceback.print_exc(); errors.append(ex)


threading.Thread(target=loop, daemon=True).start()
time.sleep(0.4)
opened = []
presses = []
real_press = m.press
m.press = lambda name, repeat=False: (presses.append((name, repeat)), real_press(name, repeat))[1]

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
webui.CONTROL = ("127.0.0.1", port); webui.CONTROL_KEY = S + "/control-key"
webui.EJS_DIR = S + "/emulatorjs/" + webui.EJS_VERSION


def ejs_fetch(name):                                  # (npm's packages, from the assets: checked as from npm)
    data = open(f"{EJS}/{name}-{webui.EJS_VERSION}.tgz", "rb").read()
    import base64, hashlib
    if base64.b64encode(hashlib.sha512(data).digest()).decode() != webui.EJS_SUMS[name]:
        raise ValueError("not npm's")
    return data


webui.ejs_fetch = ejs_fetch
socket.gethostname = lambda: "gpi"
threading.Thread(target=lambda: webui.app.run(host="127.0.0.1", port=5466, threaded=True), daemon=True).start()
time.sleep(1)
from playwright.async_api import async_playwright
PAGE = "http://gpi.local:5466/#screen"


def count():
    with open(SAVES + "/Count.srm", "rb") as f:
        return f.read(1)[0]


def moment():
    try:
        with open(SAVES + "/Count.state.auto", "rb") as f:
            return f.read()
    except OSError:
        return None


async def game_frame(pg, sec=60):
    """The page's game, once EmulatorJS has started it."""
    t = time.monotonic()
    while time.monotonic() - t < sec:
        f = next((f for f in pg.frames if "/play?" in f.url), None)
        if f is not None:
            try:
                if await f.evaluate("!!(window.EJS_emulator && EJS_emulator.started)"):
                    return f
            except Exception:
                pass
        await asyncio.sleep(0.25)
    return None


IN_MEMORY = """(at) => {                             // (the game's RAM as the emulator has it now: gambatte's state
  const s = EJS_emulator.gameManager.getState();        //  says "sram", its size in 3 bytes, then it. Not its save
  const label = [115, 114, 97, 109, 0];                 //  file: asked for, the page would send it to the Pi)
  for (let i = 0; i + 9 < s.length; i++) {
    if (label.every((c, k) => s[i + k] === c)) return s[i + 8 + at];
  }
  return null;
}"""


async def in_game(f, want=None, sec=10, at=0):
    """What the game's count says (its RAM's first byte; at 1: its buttons down, 2: its d-pad's): once it says want (its
    save, and where you were, put in as it starts), or as it is after sec seconds."""
    t, n = time.monotonic(), None
    while True:
        try:
            n = await f.evaluate(IN_MEMORY, at)
        except Exception:
            n = None
        if want is None or n == want or time.monotonic() - t > sec:
            return n
        await asyncio.sleep(0.25)


def arrives(what, sec=15):
    """Till what() says so (something sent to the Pi), sec seconds at most."""
    t = time.monotonic()
    while not what() and time.monotonic() - t < sec:
        time.sleep(0.2)
    return what()


async def page_toasts(pg):
    return await pg.evaluate("[...document.querySelectorAll('.toast, #toast')].map(t => t.textContent).join(' | ')")


async def web():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(args=["--autoplay-policy=no-user-gesture-required", "--use-gl=swiftshader",
                                           "--enable-unsafe-swiftshader",
                                           "--host-resolver-rules=MAP gpi.local 127.0.0.1"])   # (by the Pi's name, as on
        pg = await b.new_page(viewport={"width": 1280, "height": 900})                          #  your network: not a
        await pg.goto(PAGE)                                                                     #  secure page)
        await pg.wait_for_selector("#playHere", state="visible", timeout=10000)
        await pg.wait_for_function("typeof SCR !== 'undefined' && SCR.state && SCR.state.mode === 'media'",
                                   timeout=10000)

        # Play here on, the game picked on the Pi's screen from the page: it plays here, from its save
        await pg.click("#playHere")
        await asyncio.sleep(0.5)
        m.web_tab("Games")
        await asyncio.sleep(0.3)
        rows = m.tab_items()
        m.sels[m.tab] = next(i for i, r in enumerate(rows) if r.get("kind") == "game")
        await pg.click('.fbtn[data-b="a"]')
        f = await game_frame(pg)
        check("picked with Play here on: EmulatorJS plays it on the page, not the Pi", f is not None and m.game is None)
        if f is None:
            await pg.screenshot(path=S + "/no_game.png")
            await b.close()
            return
        n = await in_game(f, 5)
        check(f"...from its save on the Pi (5: {n})", n == 5)
        await pg.click("#hereClose")
        await asyncio.to_thread(arrives, moment)
        st = moment()
        check(f"closed: its save as it was on the Pi ({count()}), and where you were there, as the emulator's own "
              f"state ({len(st or b'')} bytes, {(st or b'')[:7]!r})", count() == 5 and st is not None and len(st) > 1000
              and not st.startswith(b"RASTATE"))

        # the game on the Pi (where you were: that), turned on: it moves to the page, and carries on from there
        open(SAVES + "/Count.srm", "wb").write(bytes([9]) + bytes(8191))   # (a save that says otherwise: where you
        os.utime(SAVES + "/Count.state.auto")                              #  were wins, as on the Pi)
        await pg.click("#playHere")                                        # (off: nothing here to send back)
        await asyncio.sleep(0.5)
        run = FakeRun()
        m.game, m.view = run, "game"
        await asyncio.sleep(0.2)
        await pg.click("#playHere")
        f = await game_frame(pg)
        n = await in_game(f, 5) if f else None
        check(f"Play here turned on while the game's on the Pi: it ends there and moves here ({run.quits}, "
              f"{m.game is None})", f is not None and run.quits == 1 and m.game is None)
        check(f"...carrying on from where you were (5), not its save (9: {n})", n == 5)
        check(f"...the page says so ({await page_toasts(pg)!r})", "Playing here now" in await page_toasts(pg)
              and "last save" not in await page_toasts(pg))
        await pg.screenshot(path=S + "/here_playing.png")

        # the remote and the keyboard: the game's buttons, held as long as they're held; never the Pi's
        presses.clear()
        box = await pg.locator('#remoteBox .fbtn[data-b="a"]').bounding_box()
        await pg.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        await pg.mouse.down()
        held = await in_game(f, 1, at=1)
        await asyncio.sleep(0.8)
        still = await in_game(f, at=1)
        await pg.mouse.up()
        let_go = await in_game(f, 0, at=1)
        check(f"the remote's A held: the game's A, down till it's let go of ({held}, {still}, then {let_go})",
              held == 1 and still == 1 and let_go == 0)
        box = await pg.locator('#remoteBox .dp[data-b="right"]').bounding_box()
        await pg.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        await pg.mouse.down()
        right = await in_game(f, 1, at=2)
        await pg.mouse.up()
        check(f"...its ▶: the game's ({right}, then {await in_game(f, 0, at=2)})", right == 1)
        on_game = await pg.evaluate("document.activeElement === document.querySelector('#hereBox iframe')")
        await pg.keyboard.down("ArrowLeft")                                # (the game's page has the keyboard: the
        await pg.keyboard.down("Enter")                                    #  web page's keys, the same buttons)
        left, a = await in_game(f, 2, at=2), await in_game(f, 1, at=1)
        await pg.keyboard.up("ArrowLeft")
        await pg.keyboard.up("Enter")
        check(f"...the keyboard: with the game in front ({on_game}), ◀ and Enter (A, not its START) held, the game's "
              f"({left}, {a}; then {await in_game(f, 0, at=2)}, {await in_game(f, 0, at=1)})",
              on_game and left == 2 and a == 1)
        await pg.locator("#hereWhat").evaluate("e => { e.tabIndex = -1; e.focus(); }")   # (...or the web page has it)
        await pg.keyboard.down("Enter")
        a = await in_game(f, 1, at=1)
        await pg.keyboard.up("Enter")
        check(f"...and with the web page in front: Enter, A too ({a}, then {await in_game(f, 0, at=1)})", a == 1)
        await pg.click('#remoteBox [data-b="select"]')
        await pg.click('#remoteBox [data-b="start"]')
        check(f"...and none of it went to the Pi ({presses})", presses == [])
        hidden = "EJS_emulator.elements.menu.classList.contains('ejs_menu_bar_hidden')"
        before = await f.evaluate(hidden)
        await pg.click('#remoteBox [data-b="hotkey"]')
        await asyncio.sleep(0.3)
        check(f"...its Hotkey: the emulator's own buttons ({before} hidden, then {await f.evaluate(hidden)})",
              before is True and await f.evaluate(hidden) is False and presses == [])
        check("...the emulator's own buttons on the screen: off", await f.evaluate(
            "EJS_emulator.virtualGamepad.style.display === 'none'"))
        check("...this page isn't the secure one: where a controller of yours works, said",
              await pg.is_visible("#herePad") and "secure page" in await pg.inner_text("#herePad"))

        # turned off: back to the Pi, with where you were here
        await f.evaluate("EJS_emulator.gameManager.restart()")             # (started again here: 5 + 1)
        n = await in_game(f, 6)
        m.game_open = lambda it: (opened.append(it), setattr(m, "game", FakeRun()))[0]
        await pg.click("#playHere")
        await asyncio.to_thread(arrives, lambda: opened)
        st = moment()
        check(f"turned off: the game's save (where it is here: {n}) back on the Pi ({count()}), where you were too, and "
              f"it carries on on the Pi ({opened})", n == 6 and count() == 6 and st is not None
              and not st.startswith(b"RASTATE") and os.path.isfile(SAVES + "/.replaced/Count.state.auto")
              and opened == [{"src": H + "/Games/gb/Count.gb", "title": "Count", "system": "gb"}])
        check(f"...and the page says so ({await page_toasts(pg)!r})", "Playing on the Pi now" in await page_toasts(pg)
              and not await pg.evaluate("!!document.querySelector('#hereBox iframe')"))
        await pg.screenshot(path=S + "/here_back.png")
        presses.clear()
        await pg.click('#remoteBox .fbtn[data-b="b"]')
        await asyncio.sleep(0.3)
        check(f"...the remote's the Pi's again ({presses})", ("b", False) in presses)

        # a phone: the remote under the game (its buttons the game's), no buttons of the emulator's own
        m.game = None
        ph = await b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True,
                              has_touch=True)
        await ph.goto(PAGE)
        await ph.wait_for_function("typeof SCR !== 'undefined' && SCR.state && SCR.state.mode === 'media'",
                                   timeout=10000)
        remote_before = await ph.is_visible("#remoteBox")
        run = FakeRun()
        m.game, m.view = run, "game"
        await asyncio.sleep(0.2)
        await ph.click("#playHere")
        f = None
        t = time.monotonic()
        while f is None and time.monotonic() - t < 30:                    # (a phone: its Start, tapped, plays it)
            f = next((x for x in ph.frames if "/play?" in x.url), None)
            await asyncio.sleep(0.25)
        if f is not None:
            await f.wait_for_selector(".ejs_start_button", timeout=30000)
            await f.tap(".ejs_start_button")
        f = await game_frame(ph)
        check(f"a phone: the remote, hidden before ({remote_before}), under the game now", f is not None
              and not remote_before and await ph.is_visible("#remoteBox"))
        if f is not None:
            pad = await f.evaluate("EJS_emulator.virtualGamepad.style.display")
            check(f"...the emulator's own buttons off, though it's a phone ({pad!r})", pad == "none")
            box = await ph.locator('#remoteBox .fbtn[data-b="a"]').bounding_box()
            await ph.touchscreen.tap(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            a_btn = await ph.locator('#remoteBox .fbtn[data-b="a"]').bounding_box()
            game_box = await ph.locator("#hereBox").bounding_box()
            check(f"...the game and the remote both on the screen ({round(game_box['height'])} px of game, the A "
                  f"button's bottom at {round(a_btn['y'] + a_btn['height'])} of 844)",
                  game_box["height"] > 200 and a_btn["y"] + a_btn["height"] <= 844)
            check("...no sideways scrolling", await ph.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            check("...the emulator's own buttons put away till they're wanted, and no tip for the Pi's screen", await
                  f.evaluate("EJS_emulator.elements.menu.classList.contains('ejs_menu_bar_hidden')")
                  and not await ph.is_visible("#tvTip"))
            await asyncio.sleep(3)                                             # (the "Playing here now" gone)
            await ph.screenshot(path=S + "/here_phone.png")
            m.game_open = lambda it: None
            await ph.click("#playHere")
            await asyncio.sleep(1.5)
            check(f"...turned off: the remote as it was (hidden: {not await ph.is_visible('#remoteBox')})",
                  not await ph.is_visible("#remoteBox"))
        await b.close()


asyncio.run(web())
done.set()
check("the loop ran without trouble", not errors)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
