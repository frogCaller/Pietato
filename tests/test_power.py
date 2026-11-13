"""The case's power switch: found among the input devices, and switched off it shuts the Pi down,
in the terminal (no drawing, systemd's own lines) and in media mode ('Shutting down' that stays). The Pi's asked to
once what's playing has ended, whatever goes wrong ending it, and regardless if that gets stuck; and a GPi Case's
switch is looked at too, not just listened to: off with the Pi still on (its change missed, or the Pi didn't go), it's
asked again. Told to stop, Pietato goes within seconds, even with its tidying up stuck."""
import io, os, signal, subprocess, sys, time, shutil, threading
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import pietato_all as g
from evdev import ecodes as e
REAL_POPEN = subprocess.Popen          # (the real one: Pietato's own is a stand-in from here on)

S = SP + "/t60"
shutil.rmtree(S, ignore_errors=True); os.makedirs(S + "/home/u")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.PADS_FILE = S + "/pads.json"
open(g.STATE_FILE, "w").write('{"settings": {"start": "Terminal"}}')   # (this one starts in the terminal)
g.home_dir = lambda: S + "/home/u"
if hasattr(g, "STATIC"):
    g.STATIC = S + "/home/u/gpi-media/static"
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0})()
g.SCAN_EVERY = 0.05
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what)


class Ev:
    def __init__(self, t, c, v):
        self.type, self.code, self.value = t, c, v


class Info:
    def __init__(self, bustype, vendor=1, product=1):
        self.bustype, self.vendor, self.product = bustype, vendor, product


class FakeDev:
    n = 100

    def __init__(self, name, keys, bustype=0x19, driver=None):
        FakeDev.n += 1
        self.driver = ("gpio-keys" if bustype == 0x19 else "usbhid") if driver is None else driver
        self.path = f"/dev/input/event{FakeDev.n}"
        self.name, self.keys = name, keys
        self.info = Info(bustype)
        self.r, self.w = os.pipe()
        self.q, self.gone, self.closed = [], False, False

    def capabilities(self, verbose=False, absinfo=True):
        return {e.EV_KEY: list(self.keys)} if self.keys else {}

    def fileno(self):
        return self.r

    def send(self, *evs):
        self.q += [Ev(*x) for x in evs]
        os.write(self.w, b".")

    def read(self):
        try:
            os.read(self.r, 64)
        except OSError:
            pass
        if self.gone:
            raise OSError(19, "No such device")
        out, self.q = self.q, []
        return iter(out)

    def close(self):
        self.closed = True

    def active_keys(self, verbose=False):
        if self.gone:
            raise OSError(19, "No such device")
        return list(getattr(self, "held", ()))


# ---- which devices are a power switch ------------------------------------------------------------
g.input_driver = lambda dev: dev.driver
switch = FakeDev("shutdown_button@1a", [e.KEY_POWER])
pi5 = FakeDev("pwr_button", [e.KEY_POWER])
usb_kbd = FakeDev("USB keyboard with a power key", [e.KEY_A, e.KEY_POWER], bustype=0x03)
plain = FakeDev("gpio_keys", [e.KEY_VOLUMEUP])
check("the gpio-shutdown overlay's key is the power switch", g.is_power_switch(switch))
check("a USB keyboard's power key isn't", not g.is_power_switch(usb_kbd) and not g.is_power_switch(usb_kbd, True))
check("another power key on the Pi's pins only counts on a GPi Case",
      not g.is_power_switch(pi5) and g.is_power_switch(pi5, gpi=True))
check("keys on the Pi's pins without a power key don't", not g.is_power_switch(plain, gpi=True))
ir = FakeDev("gpio_ir_recv", [e.KEY_POWER, e.KEY_VOLUMEUP], driver="")
check("a remote's power button (an IR receiver on the Pi's pins) never does", not g.is_power_switch(ir, gpi=True))
named = FakeDev("shutdown_button@3", [e.KEY_POWER], driver="")
check("...nor anything without the gpio-keys driver, whatever its name", not g.is_power_switch(named, gpi=True))
check("a device without bus info doesn't (and doesn't fail)",
      not g.is_power_switch(type("D", (), {"path": "/dev/input/event9", "name": "x", "info": None})()))

cfg = S + "/config.txt"
open(cfg, "w").write("[all]\n# >>> gpi-case setup >>>\ndtoverlay=gpicase-dpi\n# <<< gpi-case setup <<<\n")
g.CONFIG_TXT = (S + "/missing.txt", cfg)
check("a GPi Case set up by setup.sh is told from config.txt", g.gpi_case_set_up())
open(cfg, "w").write("[all]\ndtoverlay=vc4-kms-v3d\n")
check("...and any other Pi isn't", not g.gpi_case_set_up())

# ---- the main loop, with the switch plugged in -------------------------------------------------------
pad = FakeDev("GPi Case 2W gamepad", [e.BTN_SOUTH, e.BTN_EAST, e.BTN_START, e.BTN_SELECT], bustype=0x03)
plugged = [pad, switch, usb_kbd]
devs = {d.path: d for d in [pad, switch, usb_kbd, pi5]}
g.list_devices = lambda: [d.path for d in plugged]
g.InputDevice = lambda path: devs[path]
real_stat = os.stat
g.os.stat = lambda p, *a, **k: type("St", (), {"st_ino": hash(p) % 1000})() if p.startswith("/dev/input/") else real_stat(p, *a, **k)

popens, lines_shown, stopping = [], [], {"now": False}


class FakePopen:
    def __init__(self, cmd, *a, **k):
        popens.append(list(cmd))


g.subprocess.Popen = FakePopen
g.show_shutdown_lines = lambda: lines_shown.append(time.monotonic())
g.system_stopping = lambda: stopping["now"]


class UI:
    def __init__(self):
        self.out = []

    def write(self, t, c, v):
        self.out.append((c, v))

    def syn(self):
        pass


class FB:
    w, h = 640, 480
    real_w, real_h = 1920, 1080
    frames = []

    def show(self, img):
        FB.frames.append(img.copy())

    def blank_outside(self, box):
        pass

    def invalidate(self):
        pass

    def close(self):
        pass


g.Framebuffer = FB
ui = UI()
m = g.Media()
done = threading.Event()
errors = []


def loop():
    try:
        g.run(ui, m, None, stop=done.is_set)
    except Exception as ex:
        import traceback; traceback.print_exc(); errors.append(ex)


out = io.StringIO()
real_stdout = sys.stdout
th = threading.Thread(target=loop, daemon=True)
th.start()
time.sleep(0.4)
check("the switch is watched, not taken for a controller",
      list(m.pads.power) == [switch.path] and switch.path not in m.pads.by_path and not switch.closed)
check("the USB keyboard isn't watched", usb_kbd.path not in m.pads.power)


def wait(sec=0.15):
    time.sleep(sec)


# terminal mode: switched off
check("terminal mode to start with", not m.active)
switch.send((e.EV_KEY, e.KEY_POWER, 1)); wait()
check("terminal: switched off -> systemctl poweroff", popens == [["systemctl", "poweroff"]])
check("terminal: systemd's own lines asked for, nothing drawn", len(lines_shown) == 1 and not FB.frames)
check("terminal: no keys typed for it", ui.out == [])
switch.send((e.EV_KEY, e.KEY_POWER, 0)); wait()
switch.send((e.EV_KEY, e.KEY_POWER, 1)); wait()
check("switched on and off again while it's going: once is enough", len(popens) == 1)

# media mode: switched off
m.halting = 0.0
popens.clear(); lines_shown.clear()
m.enter(); wait(0.3)
check("media mode open", m.active and FB.frames)
FB.frames.clear()
switch.send((e.EV_KEY, e.KEY_POWER, 1)); wait()
check("media: switched off -> systemctl poweroff", popens == [["systemctl", "poweroff"]])
check("media: 'Shutting down' drawn, no console lines asked for", len(FB.frames) == 1 and not lines_shown)
FB.frames[-1].save(SP + "/power_media.png")
n = len(FB.frames)
m.toast("Something new", 3); m.dirty = True; wait(0.3)
check("media: nothing draws over 'Shutting down'", len(FB.frames) == n)
view = (m.view, m.tab, m.active)
pad.send((e.EV_KEY, e.BTN_SOUTH, 1)); wait(); pad.send((e.EV_KEY, e.BTN_SOUTH, 0)); wait()
pad.send((e.EV_KEY, e.BTN_START, 1)); wait(); pad.send((e.EV_KEY, e.BTN_START, 0)); wait(0.5)
check("media: the controller's presses go nowhere while it shuts down",
      (m.view, m.tab, m.active) == view and len(FB.frames) == n and not popens[1:])

# the web page is told
control = g.Control()
server = g.serve_control(m, control, port=0)
import json, urllib.request
done.set(); th.join(2); done.clear()
th = threading.Thread(target=lambda: g.run(ui, m, control, stop=done.is_set), daemon=True); th.start(); wait(0.3)
key = open(g.CONTROL_KEY).read().strip() if os.path.exists(g.CONTROL_KEY) else ""
req = urllib.request.Request(f"http://127.0.0.1:{server.server_address[1]}/press", data=json.dumps({"button": "b"}).encode(),
                             headers={"Content-Type": "application/json", "X-Pitato-Key": key})
try:
    got = json.loads(urllib.request.urlopen(req, timeout=10).read())
except urllib.error.HTTPError as ex:
    got = json.loads(ex.read() or b"{}")
check(f"the web page's remote is told it's shutting down: {got}", got.get("error") == "The Pi is shutting down"
      and len(FB.frames) == n)

# the Pi didn't go: after a while the menu comes back and says so
m.halting = time.monotonic() + 0.2; wait(0.5)
check("still here later: the menu's back, saying it didn't shut down",
      len(FB.frames) > n and m.msg == "The Pi didn't shut down")

# systemd-logind got there first: no second poweroff
m.halting = 0.0
popens.clear()
stopping["now"] = True
switch.send((e.EV_KEY, e.KEY_POWER, 1)); wait()
check("already shutting down: no second poweroff", popens == [])
stopping["now"] = False

# Shut down in the menu: 'Shutting down' stays put too
m.halting = 0.0
popens.clear(); FB.frames.clear()
m.confirm = ("poweroff", time.monotonic() + 4)
m.system_action({"src": "poweroff"})
n = len(FB.frames)
m.dirty = True; wait(0.3)
check("menu's Shut down: poweroff, and nothing draws over it",
      popens == [["systemctl", "poweroff"]] and n == 1 and len(FB.frames) == 1)

# what's playing is ended first, then the Pi's asked; whatever goes wrong ending it, or however long it takes
m.halting = 0.0
popens.clear(); FB.frames.clear()
order = []
real_popen_init, real_stop = FakePopen.__init__, m.stop
FakePopen.__init__ = lambda self, cmd, *a, **k: (order.append("asked"), real_popen_init(self, cmd, *a, **k))[1]
m.stop = lambda: (order.append("ended"), real_stop())[1]
switch.send((e.EV_KEY, e.KEY_POWER, 1)); wait(0.3)
check(f"what's playing is ended (a game saved) before the Pi's asked to shut down ({order})",
      order == ["ended", "asked"] and popens == [["systemctl", "poweroff"]])


def failing():
    order.append("ended")
    raise RuntimeError("the player won't stop")


m.halting = 0.0
popens.clear(); FB.frames.clear(); order.clear()
m.stop = failing
buf = io.StringIO()
sys.stdout = buf
try:
    switch.send((e.EV_KEY, e.KEY_POWER, 1)); wait(0.3)
finally:
    sys.stdout = real_stdout
check(f"...something going wrong ending it: the Pi's asked all the same ({order}), and it's in the log",
      order == ["ended", "asked"] and popens == [["systemctl", "poweroff"]] and "the player won't stop" in buf.getvalue())
check("...'Shutting down' on the screen all the same, the loop still going", len(FB.frames) == 1 and th.is_alive()
      and not errors)


def stuck():
    order.append("ended")
    time.sleep(1.2)
    order.append("unstuck")
    real_stop()


m.halting = 0.0
popens.clear(); FB.frames.clear(); order.clear()
g.HALT_TIDY = 0.3
m.stop = stuck
switch.send((e.EV_KEY, e.KEY_POWER, 1)); wait(0.8)
check(f"...ending it stuck: the Pi's asked regardless, a moment on ({order})", order == ["ended", "asked"]
      and popens == [["systemctl", "poweroff"]])
wait(1.0)
for _ in range(20):                                # (the screen says so once it's unstuck: a moment more, on a slow day)
    if FB.frames:
        break
    wait(0.1)
check(f"...once: not again when it comes unstuck ({order}, {len(popens)} asked, {len(FB.frames)} drawn)",
      order == ["ended", "asked", "unstuck"] and len(popens) == 1 and len(FB.frames) == 1)
g.HALT_TIDY = 8.0
FakePopen.__init__, m.stop = real_popen_init, real_stop

# a GPi Case's switch, looked at as well as listened to: off, with the Pi still on
sel = g.selectors.DefaultSelector()
open(cfg, "w").write("# >>> gpi-case setup >>>\n")
pads = g.Pads(sel)
pads.scan(0.0, force=True)
check("a GPi Case: its switch found", list(pads.power) == [switch.path])
check("...on: nothing to do", not pads.switched_off(0.0) and not pads.switched_off(100.0))
held = g.Pads(g.selectors.DefaultSelector())      # (another start, the switch reading off from the first)
switch.held = [e.KEY_POWER]
held.scan(0.0, force=True)
buf = io.StringIO()
sys.stdout = buf
try:
    looks = [held.switched_off(10.0 * k) for k in range(6)]
finally:
    sys.stdout = real_stdout
check(f"...reading off from the start (a pin held low, say): never taken for switched off, or the Pi would shut down "
      f"each time it started; said once ({buf.getvalue().strip()!r})", not any(looks)
      and buf.getvalue().count("reads off already") == 1)
switch.held = []
held.switched_off(100.0)
switch.held = [e.KEY_POWER]
check("......till it's been seen on: then off is off", [held.switched_off(t) for t in (110.0, 120.0)] == [False, True])
first, soon, later = pads.switched_off(200.0), pads.switched_off(200.0 + g.POWER_LOOK - 0.1), pads.switched_off(200.0 + g.POWER_LOOK)
check(f"...off, and nothing heard of it changing: seen the second time it's looked at, {g.POWER_LOOK:.0f} s on "
      f"({first}, {soon}, {later})", (first, soon, later) == (False, False, True))
check("...and every time after, while it stays off", pads.switched_off(300.0) and pads.switched_off(400.0))
switch.held = []
check("...on again: no more", not pads.switched_off(500.0) and not pads.switched_off(600.0))
switch.held = [e.KEY_POWER]
switch.gone = True
check("...a switch that can't be read: left alone", not pads.switched_off(700.0) and not pads.switched_off(800.0))
switch.gone = False
open(cfg, "w").write("[all]\ndtoverlay=vc4-kms-v3d\n")
other = g.Pads(g.selectors.DefaultSelector())
other.scan(0.0, force=True)
check("any other Pi's power key is a button (it's let go of again): never looked at so",
      list(other.power) == [switch.path] and not other.switched_off(0.0) and not other.switched_off(100.0))
switch.held = []
for d in (pad, switch, usb_kbd):
    d.closed = False

# ...in the main loop: its change missed, the Pi's asked all the same; still off after it didn't go, asked again
done.set(); th.join(2); done.clear()
open(cfg, "w").write("# >>> gpi-case setup >>>\n")
g.POWER_LOOK = 0.1
m.halting = 0.0
popens.clear(); FB.frames.clear()
th = threading.Thread(target=lambda: g.run(ui, m, control, stop=done.is_set), daemon=True); th.start(); wait(0.5)
check("a GPi Case, its switch on: nothing asked", m.pads.gpi and list(m.pads.power) == [switch.path] and not popens)
n = len(FB.frames)
switch.held = [e.KEY_POWER]                        # (off, and no word of it changing)
wait(0.6)
check(f"...off, its change missed: the Pi's asked to shut down, and the screen says so ({popens})",
      popens == [["systemctl", "poweroff"]] and len(FB.frames) == n + 1)
wait(0.5)
check("...once, while it's on its way", len(popens) == 1)
m.halting = time.monotonic() + 0.1; wait(0.8)
check(f"...it didn't go, and the switch is still off: asked again ({len(popens)})", len(popens) == 2)
switch.held = []
m.halting = time.monotonic() + 0.1; wait(0.6)
check("...switched on again meanwhile: not asked any more", len(popens) == 2 and m.msg == "The Pi didn't shut down")
# ...and by its pin itself: the pin says off -> the Pi shuts down, though nothing came from the kernel's key
m.halting = 0.0
popens.clear()
pin_off = [False]
m.power_pin = type("W", (), {"off": lambda self, now: pin_off[0]})()
wait(0.4)
check("its pin watched, and on: nothing asked", not popens)
pin_off[0] = True; wait(0.4)
check(f"the pin off, nothing from the kernel's key: the Pi's asked to shut down ({popens})",
      popens == [["systemctl", "poweroff"]])
wait(0.4)
check("...once, while it's on its way", len(popens) == 1)
pin_off[0] = False
m.halting = 0.0
m.power_pin = None
made = []
real_watch, was_case = g.SwitchWatch, m.case
g.SwitchWatch = lambda *a, **k: made.append(1) or "a watch"
m.case = None
m.power_start()
check("any other Pi: no pin watched", not made and m.power_pin is None)
m.case = "2w"
m.power_start(); m.power_start()
check("a GPi Case: its pin watched, from start-up (once)", made == [1] and m.power_pin == "a watch")
g.SwitchWatch, m.case, m.power_pin = real_watch, was_case, None
check("no errors in the loop, still", not errors and th.is_alive())

done.set(); th.join(2); done.clear()
open(cfg, "w").write("[all]\ndtoverlay=vc4-kms-v3d\n")
g.POWER_LOOK = 5.0
m.halting = 0.0
th = threading.Thread(target=lambda: g.run(ui, m, control, stop=done.is_set), daemon=True); th.start(); wait(0.3)

# the switch unplugged (the overlay removed, say): dropped quietly
switch.gone = True; plugged.remove(switch); switch.send(); wait(0.3)
check("a switch that's gone is dropped", switch.path not in m.pads.power and not errors)
done.set(); th.join(2)
check("no errors in the loop", not errors)

# ---- a GPi Case without the switch: said once ---------------------------------------------------------
import contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    sel = g.selectors.DefaultSelector()
    open(cfg, "w").write("# >>> gpi-case setup >>>\n")
    plugged[:] = [pad]
    pads = g.Pads(sel)
    pads.scan(time.monotonic(), force=True)
    pads.scan(time.monotonic(), force=True)
check("GPi Case, no switch found: said once", buf.getvalue().count("power switch: not found") == 1)

# ---- the real show_shutdown_lines: only ever signals systemd -------------------------------------------
import importlib
gk = importlib.reload(g)
sent = []
real_kill = os.kill
gk.os.kill = lambda pid, sig: sent.append((pid, sig))
try:
    gk.show_shutdown_lines()
finally:
    gk.os.kill = real_kill
first = open("/proc/1/comm").read().strip()
check("PID 1 isn't systemd here: no signal sent" if first != "systemd" else "systemd: SIGRTMIN+20",
      sent == ([] if first != "systemd" else [(1, gk.signal.SIGRTMIN + 20)]))

# ---- a GPi Case's switch by its pin itself: for when the kernel's key says nothing ---------------------------------
says = {"pinctrl": "", "raspi-gpio": ""}
real_run_out = g.run_out
g.run_out = lambda cmd, timeout=3: says.get(cmd[0], "") if cmd[-1] == "26" else ""
levels = []
for a, b in (("26: ip    pu | hi // GPIO26 = input\n", ""), ("26: ip    pu | lo // GPIO26 = input\n", ""),
             ("26: ip    -- | hi // GPIO26 = input\n27: op -- -- | hi // GPIO27 = output\n", ""),   # (a Pi Zero 2 W's)
             ("26: ip    -- | lo // GPIO26 = input\n27: op -- -- | hi // GPIO27 = output\n", ""),
             ("26: a2    pn | lo // GPIO26 = DPI_D22\n", ""), ("26: op dh pn | hi // GPIO26 = output\n", ""),
             ("27: ip    pu | lo // GPIO27 = input\n", ""), ("", "GPIO 26: level=1 fsel=0 func=INPUT pull=UP\n"),
             ("", "GPIO 26: level=0 fsel=0 func=INPUT\n"), ("", "GPIO 26: level=0 fsel=6 alt=2 func=DPI_D22\n"),
             ("", "")):
    says["pinctrl"], says["raspi-gpio"] = a, b
    levels.append(g.input_level(26))
check(f"the pin's level, as pinctrl or raspi-gpio has it: high or low when it's an input, no telling when it's put to "
      f"another use, or neither's there ({levels})",
      levels == [True, False, True, False, None, None, None, True, False, None, None])
g.run_out = real_run_out


def watched(readings, every=3.0, **k):
    """A watch given these readings, one each `every` seconds from 0: (it, what it said, when it first says off)."""
    it = iter(readings)
    w = g.SwitchWatch(read=lambda: next(it), start=False, **k)
    buf, off_at, t = io.StringIO(), None, 0.0
    sys.stdout = buf
    try:
        for _ in readings:
            w.look(t)
            for dt in (0.0, 1.0, 2.0):                 # (asked between looks too, as the main loop asks)
                if off_at is None and w.off(t + dt):
                    off_at = t + dt
            t += every
    finally:
        sys.stdout = real_stdout
    return w, buf.getvalue(), off_at


H, L, N = True, False, None
w, said, at = watched([H] * 6)
check(f"its pin high (the switch on): watched once it's been so {g.POWER_ARM:.0f} s on end, and said so",
      w.armed and at is None and said.count("is watched too") == 1)
w, said, at = watched([H] * 5 + [L] * 4)                     # (high from 0 to 12, low from 15)
check(f"...then low: switched off, once it's been so {g.POWER_SETTLE} s, two looks running ({at})",
      at is not None and 15.0 + g.POWER_SETTLE <= at <= 16.0 + g.POWER_SETTLE)
w, said, at = watched([H] * 5 + [L, H, H, L, H, H])
check("...low for a moment and high again (a knock): not off", at is None and w.armed)
w, said, at = watched([L] * 12)
check(f"low from the start (a pin that's held low: no telling it from a switch turned off): never taken for off, or "
      f"the Pi would shut down each time it started; said once ({said.strip()!r})",
      at is None and not w.armed and said.count("is low already") == 1)
w, said, at = watched([H, H, L, L, L, L, L, L])
check("...high only a moment first (not long enough to be the switch on): the same", at is None and not w.armed)
w, said, at = watched([L, L] + [H] * 5 + [L] * 3)            # (low to 3, high from 6 to 18, low from 21)
check(f"...low to begin with, then high a good while, then low: off after all ({at})",
      at is not None and 21.0 + g.POWER_SETTLE <= at <= 22.0 + g.POWER_SETTLE)
w = g.SwitchWatch(read=lambda: None, start=False)
buf = io.StringIO()
sys.stdout = buf
try:
    for k in range(3):
        w.look(2.0 * k)
finally:
    sys.stdout = real_stdout
said = buf.getvalue()
check(f"a pin that can't be read from the start (no pinctrl, or not an input): not looked at any more, and said once "
      f"({said.strip()!r})", w.blind and not w.off(60.0) and said.count("can't be read") == 1)
w, said, at = watched([H] * 5 + [N, N, N, N, H, L, L])       # (...low from 30)
check(f"...one that was read before, and then can't be for a while: still watched, and off is seen after ({at})",
      not w.blind and "can't be read" not in said and at is not None and at >= 30.0 + g.POWER_SETTLE)
w, said, at = watched([H] * 5 + [L, N, L, L])                # (low at 15, no telling at 18, low from 21)
check(f"...a look that fails between two that say low: off a look later, no sooner ({at})",
      at is not None and at >= 21.0 + g.POWER_SETTLE)


def broken():
    raise OSError("no such thing")


w = g.SwitchWatch(read=broken, start=False)
buf = io.StringIO()
sys.stdout = buf
try:
    for k in range(4):
        w.look(3.0 * k)
finally:
    sys.stdout = real_stdout
check("...reading it going wrong: the same, no error", w.blind and not w.off(60.0))
w = g.SwitchWatch(read=lambda: None, every=0.01)
w.thread.join(2)
check("...its thread ends then, not looking for ever", not w.thread.is_alive())

# ---- told to stop (the Pi shutting down): it tidies up and goes, and goes anyway if that gets stuck ---------------
STOPPING = r"""
import sys, time
sys.path.insert(0, sys.argv[1])
import pietato_all as g
import pitato.app as APP


class Part:
    def start(self):
        pass


class Media:
    shrinker, updater = Part(), Part()

    def __getattr__(self, name):                       # (whatever else main() starts: nothing, here)
        return lambda *a, **k: None

    def shutdown(self):
        print("tidying up", flush=True)
        if sys.argv[2] == "stuck":
            time.sleep(60)


def run(ui, media, control):
    print("running", flush=True)
    time.sleep(60)


APP.Media, APP.run, APP.EXIT_WAIT = Media, run, 0.6
APP.UInput = lambda *a, **k: None
APP.handheld_profile = lambda: None
APP.move_old_places = lambda: None
APP.Control = lambda: None
APP.control_key = lambda: ""
APP.serve_control = lambda *a, **k: None
APP.main()
"""


def stopped(how):
    """Pietato's own main(), told to stop as systemd tells it (SIGTERM) once it's running: (how it ended, what it
    said, how long it took to go)."""
    p = REAL_POPEN([sys.executable, "-c", STOPPING, TESTS, how], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                   text=True)
    said = [p.stdout.readline()]
    t0 = time.monotonic()
    p.send_signal(signal.SIGTERM)
    try:
        said.append(p.communicate(timeout=20)[0])
    except subprocess.TimeoutExpired:
        p.kill()
        said.append(p.communicate()[0] + "(killed: it never went)")
    return p.returncode, "".join(said), time.monotonic() - t0


code, said, took = stopped("fine")
check(f"told to stop: it tidies up and goes at once ({took:.2f} s, {code})", code == 0 and "running" in said
      and "tidying up" in said and "goes as it is" not in said and took < 0.5)
code, said, took = stopped("stuck")
check(f"...its tidying up stuck: it goes all the same, a moment on ({took:.2f} s, {code}): a shutdown never waits long "
      "for it", code == 0 and "tidying up" in said and "still tidying up, so it goes as it is" in said
      and 0.5 <= took < 5)

print("ALL OK" if all(ok_all) else "FAILED")
