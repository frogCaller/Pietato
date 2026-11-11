"""The web page's Sound here, in a real browser: the Pi's sound as it comes (a pretend arecord's: every sample a count,
so anything left out or played twice shows), lined up to play on the page's sound clock (a pretend one that notes what's
lined up, when, and how fast). Steady: each piece straight after the last, a little ahead of now, none of it left out,
and the Pi told how late it's heard. The page's clock a little fast, then a little slow, beside the Pi's: played a
hair slower, then faster, and it never runs out. A hiccup on the way (a third of a second held up, then all of it at
once): it runs out once and goes on from the newest of what came, faded in, with more lined up than before, and no
further behind the Pi than that (what was held up and comes in several lots is taken back before any of it plays).
All of it held up a good second: the same, and what's far behind is let go. Each piece starts on a sample of the
player's own. Then with the browser's own sound: it plays, at the Pi's rate."""
import asyncio, logging, os, shutil, socket, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, SP); sys.path.insert(0, TESTS); sys.path.insert(0, ROOT)
import pietato_all as g

S = SP + "/t_web_soundhere"
shutil.rmtree(S, ignore_errors=True)
H = S + "/home/u"
for d in ("Music", "Videos", "Pictures", "Documents"):
    os.makedirs(f"{H}/{d}")
os.makedirs(S + "/bin"); os.makedirs(S + "/asound/Loopback")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
open(g.STATE_FILE, "w").write('{"settings": {}}')
g.home_dir = lambda: H
import gk_static; gk_static.use_home(g, H)
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
g.list_devices = lambda: []
ok_all = []
PORT, COUNT = 5475, 30000


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


# a pretend arecord: 20 ms at a time, each sample the one before's count and one (round at COUNT); with a number in
# the file HOLD, what comes in that many seconds is held up, then sent all at once (a hiccup on its way to the page)
HOLD = S + "/hold"
open(S + "/bin/arecord", "w").write(f'''#!/usr/bin/env python3
import array, os, sys, time
out, n, k, i, start = sys.stdout.buffer, 960, 0, 0, time.monotonic()
kept, till = [], 0.0
while True:
    a = array.array("h", bytes(n * 4))
    for j in range(n):
        a[2 * j] = a[2 * j + 1] = (i + j) % {COUNT}
    i += n
    if sys.byteorder == "big":
        a.byteswap()
    kept.append(a.tobytes())
    try:
        till = time.monotonic() + float(open({HOLD!r}).read())
        os.remove({HOLD!r})
    except (OSError, ValueError):
        pass
    if time.monotonic() >= till:
        try:
            out.write(b"".join(kept)); out.flush()
        except (BrokenPipeError, OSError):
            break
        kept = []
    k += 1
    time.sleep(max(0, start + k * 0.02 - time.monotonic()))
''')
os.chmod(S + "/bin/arecord", 0o755)
os.environ["PATH"] = S + "/bin:" + os.environ["PATH"]


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
logging.getLogger("werkzeug").setLevel(logging.ERROR)
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
webui.LOOPBACK = S + "/asound/Loopback"
socket.gethostname = lambda: "gpi"
threading.Thread(target=lambda: webui.app.run(host="127.0.0.1", port=PORT, threaded=True), daemon=True).start()
time.sleep(1)
try:
    from playwright.async_api import async_playwright
except ImportError:                                    # (not on the Pi's Python here: left to the other run)
    async_playwright = None

# the page's sound clock, a pretend one: what's lined up noted (when it plays, how many samples, how fast, when that
# was, its last sample's count); its time goes on as the browser's does, times window.__speed
FAKE = """
window.__speed = 1; window.__lined = []; window.__asked = null;
(() => {
  let at = performance.now(), t = 0;
  const now = () => { const p = performance.now(); t += (p - at) / 1000 * window.__speed; at = p; return t; };
  window.AudioContext = class {
    constructor(o) { window.__asked = o || null; this.sampleRate = (o && o.sampleRate) || 44100; this.state = "running";
                     this.destination = {}; this.outputLatency = 0.02; }
    get currentTime() { return now(); }
    resume() { return Promise.resolve(); }
    close() { this.state = "closed"; return Promise.resolve(); }
    createBuffer(c, n, rate) {
      const ch = [new Float32Array(n), new Float32Array(n)];
      return { length: n, sampleRate: rate, duration: n / rate, getChannelData: (i) => ch[i] };
    }
    createBufferSource() {
      const s = { buffer: null, playbackRate: { value: 1 }, connect() {}, note: null,
                  start(when) {
                    const l = s.buffer.getChannelData(0), r = s.buffer.getChannelData(1), n = s.buffer.length;
                    s.note = { when, n, rate: s.playbackRate.value, now: now(), same: l[n - 1] === r[n - 1],
                               last: Math.round(l[n - 1] * 32768), first: Math.round(l[0] * 32768), stopped: null };
                    window.__lined.push(s.note);
                  },
                  stop() { s.note.stopped = now(); } };   // (taken back: when; before it's begun, it's never heard)
      return s;
    }
  };
})();
"""


def joins(lined):
    """What's lined up, piece after piece: how far the furthest start is from the end of the piece before (seconds),
    how many were lined up to play before now, and how many don't go on from the count the one before ended on."""
    apart, late, left = 0.0, 0, 0
    for a, b in zip(lined, lined[1:]):
        apart = max(apart, abs(b["when"] - (a["when"] + a["n"] / 48000 / a["rate"])))
        left += (b["last"] - a["last"]) % COUNT != b["n"] % COUNT
    late = sum(p["when"] < p["now"] for p in lined)
    return apart, late, left


TAKEN = []                                             # pieces taken back: (when it would have begun, when it was)


async def lined_up(pg):
    """What's lined up to play now: the pieces not taken back since (those are noted)."""
    every = await pg.evaluate("window.__lined")
    TAKEN[:] = [(p["when"], p["stopped"]) for p in every if p["stopped"] is not None]
    return [p for p in every if p["stopped"] is None]


async def web():
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1280, "height": 900})
        await ctx.add_init_script(FAKE)
        pg = await ctx.new_page()
        await pg.goto(f"http://localhost:{PORT}/#screen")
        await pg.wait_for_function("typeof SCR !== 'undefined' && SCR.state && SCR.state.mode === 'media'",
                                   timeout=10000)
        await pg.click("#soundHere")
        await pg.wait_for_function("window.__lined.length > 20", timeout=10000)
        asked = await pg.evaluate("window.__asked")
        check(f"Sound here on: the browser's sound asked for at the Pi's rate ({asked})",
              (asked or {}).get("sampleRate") == 48000)

        async def snd():
            return await pg.evaluate("({gaps: SND.gaps, want: SND.want, need: SND.need, late: SND.late, "
                                     "rate: SND.rate, skip: SND.skip, now: SND.ctx.currentTime})")

        # steady: five seconds of it with nothing in its way (this machine kept it waiting meanwhile: five more)
        await asyncio.sleep(1.0)
        part, was, now = [], await snd(), None
        for go in range(5):
            was, taken = await snd(), len(TAKEN)
            await asyncio.sleep(5.0)
            lined, now = await lined_up(pg), await snd()
            part = [x for x in lined if x["now"] > was["now"]]
            if now["gaps"] == was["gaps"] and now["want"] == was["want"] and len(TAKEN) == taken \
                    and all(x["rate"] == 1 for x in part):
                break
            print(f"(kept waiting by this machine, {was} to {now}: looked at again)", flush=True)
        apart, late, left = joins(part)
        ahead = sorted(x["when"] - x["now"] for x in part)
        check(f"steady: each piece straight after the last ({len(part)} of them, the furthest {apart * 1e6:.1f} "
              f"millionths of a second off), none lined up too late ({late}), none of it left out ({left})",
              len(part) > 200 and apart < 2e-6 and late == 0 and left == 0 and all(x["same"] for x in part))
        off = [x["when"] * 48000 - round(x["when"] * 48000) for x in part]   # (how far from a sample of the player's)
        check(f"...each starting on a sample of the player's own (asked for a hair before it, so it's not rounded on "
              f"to the next: {min(off):.4f} to {max(off):.4f} of a sample), so they join as they were cut",
              bool(off) and all(-0.0011 < x < -0.0009 for x in off))
        check(f"...a little ahead of now (from {ahead[0] * 1000:.0f} to {ahead[-1] * 1000:.0f} ms, "
              f"{now['want'] * 1000:.0f} wanted: a bit more than the longest it's been kept waiting), and it didn't "
              f"run out ({now})", now["want"] - 0.03 < ahead[0] and ahead[-1] < now["want"] + 0.08
              and now["gaps"] == was["gaps"] and (now["gaps"] > 0 or abs(now["want"] - 0.15) < 1e-9))
        said = webui.SOUND.late()
        check(f"...the Pi's told how late it's heard here: that far ahead, the browser's own part and the Pi's "
              f"({said})", said is not None and abs(said - (now["late"] + webui.SOUND_OWN)) < 0.03
              and 0.02 + ahead[0] - 0.01 < now["late"] < 0.02 + ahead[-1] + 0.01)
        title = await pg.get_attribute("#soundHere", "title")
        check(f"...and the switch says so ({title!r})", title.startswith("The Pi's sound plays here, 0.")
              and " s behind it" in title and title.endswith(". Tap to hear it on the Pi again")
              and ("cut out" in title) == (now["gaps"] > 0))

        # this one's clock and the Pi's, not quite agreeing
        g0, n0 = now["gaps"], len(await lined_up(pg))
        await pg.evaluate("window.__speed = 1.003")
        await asyncio.sleep(16.0)
        lined = await lined_up(pg)
        slow = min(x["rate"] for x in lined[-100:])
        await pg.evaluate("window.__speed = 0.997")
        await asyncio.sleep(22.0)
        lined = await lined_up(pg)
        fast = max(x["rate"] for x in lined[-100:])
        await pg.evaluate("window.__speed = 1")
        now = await snd()
        _, late, left = joins(lined[n0 - 1:])
        check(f"this one's clock a little fast beside the Pi's: played a hair slower ({slow:.4f}); a little slow: a "
              f"hair faster ({fast:.4f}); it never ran out ({now['gaps'] - g0}), and none of it was left out ({left})",
              0.995 <= slow < 1.0 and 1.0 < fast <= 1.005 and (now["gaps"] > g0 or (left == 0 and late == 0)))
        if now["gaps"] > g0:
            print(f"(kept waiting by this machine meanwhile: {now})", flush=True)

        # a hiccup on its way
        await asyncio.sleep(3.0)
        lined, was = await lined_up(pg), await snd()
        n0 = len(lined)
        open(HOLD, "w").write("0.33")
        await asyncio.sleep(3.0)
        lined, now = await lined_up(pg), await snd()
        late = [k for k, x in enumerate(lined) if k >= n0 and k and x["when"] - (
            lined[k - 1]["when"] + lined[k - 1]["n"] / 48000 / lined[k - 1]["rate"]) > 1e-4]
        _, _, left = joins(lined[n0 - 1:])
        check(f"a hiccup on its way (a third of a second held up, then all at once): it runs out once "
              f"({now['gaps'] - was['gaps']}; a gap before piece {late}), and goes on from the newest of what came "
              f"({left} place where it doesn't go straight on)", now["gaps"] == was["gaps"] + 1 and len(late) == 1
              and left == 1)
        after = lined[late[0]] if late else {"first": 1, "when": 0, "now": 0}
        check(f"...a moment from then, as much lined up as it was kept waiting and a bit ({was['want'] * 1000:.0f} ms "
              f"before, {now['want'] * 1000:.0f} now), faded in ({after['first']})",
              max(0.3, was["want"]) <= now["want"] <= 0.5 and after["first"] == 0
              and abs(after["when"] - after["now"] - now["want"]) < 0.02)
        ahead = sorted(x["when"] - x["now"] for x in lined[-30:])
        title = await pg.get_attribute("#soundHere", "title")
        cuts = "(it's cut out once)" if now["gaps"] == 1 else f"(it's cut out {now['gaps']} times)"
        check(f"...no further behind the Pi than that (from {ahead[0] * 1000:.0f} to {ahead[-1] * 1000:.0f} ms ahead "
              f"of now), and the switch says it cut out ({title!r})", now["want"] - 0.03 < ahead[0]
              and ahead[-1] < now["want"] + 0.08 and cuts in title)

        # the same again, now that much is lined up: it doesn't run out
        was = now
        n0 = len(lined)
        open(HOLD, "w").write("0.3")
        await asyncio.sleep(3.0)
        lined, now = await lined_up(pg), await snd()
        _, late, left = joins(lined[n0 - 1:])
        check(f"another like it: enough's lined up now, and it doesn't run out ({now['gaps'] - was['gaps']}; {left} "
              f"left out, {late} too late)", now["gaps"] == was["gaps"] and left == 0 and late == 0)

        # all of it held up a good second
        was = now
        n0 = len(lined)
        open(HOLD, "w").write("1.3")
        await asyncio.sleep(4.5)
        lined, now = await lined_up(pg), await snd()
        _, _, left = joins(lined[n0 - 1:])
        ahead = [x["when"] - x["now"] for x in lined[-20:]]
        check(f"a good second held up: it runs out again ({now['gaps'] - was['gaps']}), what's far behind is let go "
              f"({left} places where it doesn't go straight on), and it's a moment behind again (from "
              f"{min(ahead) * 1000:.0f} to {max(ahead) * 1000:.0f} ms ahead, {now['want'] * 1000:.0f} wanted: no "
              f"more than {0.6 * 1000:.0f})", now["gaps"] == was["gaps"] + 1 and 1 <= left <= 3 and not now["skip"]
              and max(ahead) < now["want"] + 0.1 and min(ahead) > now["want"] - 0.03 and now["want"] <= 0.6 + 1e-9
              and sum(x["when"] < x["now"] for x in lined[n0:]) == 0)

        check(f"what was held up and let go ({len(TAKEN)} pieces taken back): none of it had begun to play",
              all(stopped < when for when, stopped in TAKEN))
        await pg.click("#soundHere")
        await asyncio.sleep(0.5)
        n = len(await pg.evaluate("window.__lined"))
        await asyncio.sleep(0.5)
        check("Sound here off: no more lined up", n == len(await pg.evaluate("window.__lined"))
              and await pg.get_attribute("#soundHere", "aria-pressed") == "false")
        await ctx.close()

        # the browser's own sound
        pg = await b.new_page(viewport={"width": 1280, "height": 900})
        await pg.goto(f"http://localhost:{PORT}/#screen")
        await pg.wait_for_function("typeof SCR !== 'undefined' && SCR.state && SCR.state.mode === 'media'",
                                   timeout=10000)
        await pg.click("#soundHere")
        await asyncio.sleep(3.0)
        real = await pg.evaluate("SND.ctx ? ({state: SND.ctx.state, rate: SND.ctx.sampleRate, gaps: SND.gaps, "
                                 "ahead: SND.at / SND.ctx.sampleRate - SND.ctx.currentTime, late: SND.late}) : null")
        check(f"with the browser's own sound: it plays, at the Pi's rate, a little ahead of now ({real})",
              real is not None and real["rate"] == 48000 and (real["state"] != "running" or (
                  0.02 < real["ahead"] < 0.6 and real["late"] > 0.02)))
        await b.close()


if async_playwright:
    asyncio.run(web())
else:
    print("(no browser for this Python: the web page in a browser is left to the other run)")
done.set()
check("the loop ran without trouble", not errors)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
