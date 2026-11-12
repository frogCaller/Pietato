"""A frame of Apps' worlds made quicker, and the screen just as it was. The real Framebuffer, written to stand-in
screens (files): the usual 16-bit and 32-bit pixels packed the quick ways give the bytes the general way does; a
part that's most of the way across goes as whole rows in one go, a narrow one a row at a time, and what's on the
screen is the picture either way (the GPi Case's screen, one with rows longer than its pixels, one that starts
further down); a TV's doubled pixels, mapped or written, are the picture's, each twice (four times on a 4K one),
on its side too. Rock Paper Scissors' pieces put on the picture the quick way make the picture PIL's own paste
does, and it goes back to that for good if the quick way can't be had. And how often it's drawn: 20 times a second
to begin with, as ever; 30 or 60 where a frame leaves the machine the time, a couple of seconds on; back down if
frames get dearer, but not for a little; worked out afresh for another size of it; the other apps as ever."""
import os, random, shutil, sys
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
try:
    import evdev  # noqa: F401
except ImportError:
    sys.path.insert(0, SP + "/evdevlib")
sys.path.insert(0, TESTS)
import numpy as np
import pietato_all as g
from PIL import Image
from pitato import fine as F, screen as SC, sims as SIMS

S = SP + "/tquick"
shutil.rmtree(S, ignore_errors=True)
os.makedirs(S + "/home/u")
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


RGB16 = [(11, 5), (5, 6), (0, 5)]
BGRX = [(16, 8), (8, 8), (0, 8)]
rnd = np.random.default_rng(8)


def noise(w, h):
    return Image.fromarray(rnd.integers(0, 256, (h, w, 3), dtype=np.uint8), "RGB")


def general(img, fields, bpp):
    """A picture's pixels for a screen, the general way (a field at a time): rows of them."""
    a = np.asarray(img.convert("RGB"), dtype=np.uint32)
    px = np.zeros(a.shape[:2], dtype=np.uint32)
    for c, (off, ln) in enumerate(fields):
        px |= (a[..., c] >> (8 - ln)) << off
    return px.astype("<u2" if bpp == 16 else "<u4")


# ---- packed the quick ways: the same bytes ------------------------------------------------------------------------
pictures = [noise(640, 480), noise(1, 1), noise(3, 7), noise(617, 2), noise(45, 17)]
ramp = Image.new("RGB", (256, 3))
ramp.putdata([(v, v, v) for v in range(256)] + [(v, 255 - v, 0) for v in range(256)] + [(0, v, 255 - v) for v in range(256)])
pictures.append(ramp)
SC.PIL_565[0] = None
first = SC.rgb565(pictures[0])
pil = SC.PIL_565[0]
check(f"16-bit pixels: PIL's own way tried once, and {'used: it makes the same bytes' if pil else 'not there (or not the same): numpy as ever'}",
      pil in (True, False) and first == general(pictures[0], RGB16, 16).tobytes())
check("...every picture the same bytes as the general way", all(SC.rgb565(p) == general(p, RGB16, 16).tobytes()
                                                                 for p in pictures) and SC.PIL_565[0] == pil)
SC.PIL_565[0] = False
check("...and numpy's way, where PIL hasn't one: the same", all(SC.rgb565(p) == general(p, RGB16, 16).tobytes()
                                                                 for p in pictures))
SC.PIL_565[0] = pil
check("32-bit pixels, blue first: the bytes PIL packs itself, and the general way's",
      all(SC.bgrx(p) == p.tobytes("raw", "BGRX") == general(p, BGRX, 32).tobytes() for p in pictures))


# ---- the screen's file: what's on it is the picture ------------------------------------------------------------
def screen(name, w, h, bpp, fields, turn=0, stride=None, yo=0, mapped=True):
    """A stand-in screen (a file, every byte 0xA5 to begin with), and the real Framebuffer on it."""
    path = f"{S}/fb_{name}"
    stride = stride or w * bpp // 8
    with open(path, "wb") as f:
        f.write(b"\xa5" * (stride * (h + yo)))
    fb = object.__new__(g.Framebuffer)
    fb.f = open(path, "r+b", buffering=0)
    fb.turn = turn
    fb.setup(w, h, 0, yo, bpp, fields, stride)
    if not mapped:
        fb.mem = None                                  # (one that can't be mapped: written to, a row at a time)
    return fb, path


def on_screen(fb, path):
    """Its pixels now (rows of them), and everything else in its file (between its rows, above them)."""
    bp = fb.bpp // 8
    raw = np.frombuffer(open(path, "rb").read(), dtype=np.uint8).reshape(-1, fb.stride)
    px = raw[fb.yo:, :fb.dev_w * bp].copy().view("<u2" if bp == 2 else "<u4")
    return px, raw[:fb.yo], raw[fb.yo:, fb.dev_w * bp:]


def writes(fb, do):
    """What do() writes to the screen's file: [(where, how many bytes)]."""
    got, real = [], os.pwrite
    SC.os.pwrite = lambda fd, data, at: (got.append((at, len(data))) if len(data) else None, real(fd, data, at))[1]
    try:
        do()
    finally:
        SC.os.pwrite = real
    return got


def changed(img, box):
    """The picture with something new in that box, and nowhere else."""
    out = img.copy()
    out.paste(noise(box[2] - box[0], box[3] - box[1]), box[:2])
    return out


SC.pi_model = lambda: "Raspberry Pi Zero 2 W Rev 1.0"   # (pictures as ever, not drawn finely: fine ones further on)
BOXES = (("the Bot's desk", tuple(g.CO_DIRTY)), ("an app's box", tuple(g.SIM_BOX)), ("its box and its numbers", tuple(g.SIM_DIRTY)),
         ("a narrow one", (100, 69, 300, 384)), ("one at the corner", (400, 300, 640, 480)),
         ("the whole width", (0, 200, 640, 260)), ("one pixel", (639, 479, 640, 480)))
for name, bpp, fields, stride, yo in (("the GPi Case's", 16, RGB16, None, 0), ("a 32-bit one its size", 32, BGRX, None, 0),
                                      ("one whose rows are longer than its pixels", 16, RGB16, 1288, 0),
                                      ("one that starts further down its memory", 16, RGB16, None, 8)):
    fb, path = screen(f"same_{bpp}_{stride}_{yo}", 640, 480, bpp, fields, stride=stride, yo=yo)
    a = noise(640, 480)
    whole = writes(fb, lambda: fb.show(a))
    px, above, between = on_screen(fb, path)
    ok = fb.same and fb.memory() is None and (px == general(a, fields, bpp)).all()
    one_go = len(whole) == 1 if stride is None else len(whole) == 480
    said = []
    for label, box in BOXES:
        b = changed(a, box)
        got = writes(fb, lambda: fb.show_part(b, box))
        px, above, between = on_screen(fb, path)
        wide = (box[2] - box[0]) * 5 >= 640 * 3
        rows, bp = box[3] - box[1], bpp // 8
        want = [((box[1] + yo) * fb.stride, 640 * rows * bp)] if wide and stride is None else \
            [((box[1] + yo + r) * fb.stride + (0 if wide else box[0]) * bp, (640 if wide else box[2] - box[0]) * bp)
             for r in range(rows)]
        ok = ok and (px == general(b, fields, bpp)).all() and got == want and fb.last is b
        said.append(f"{label} {len(got)}")
        a = b
    check(f"{name} screen: the whole picture {'in one go' if stride is None else 'a row at a time'}, then parts of it, "
          f"each as it should be on the screen (writes: {', '.join(said)})", ok and one_go)
    check("...and nothing written but its pixels (what's between its rows, and above them, as it was)",
          (above == 0xA5).all() and (between == 0xA5).all())


class NoNumber:
    """A screen's file that hasn't a number to write to it by: sought and written, as ever."""
    def __init__(self, path):
        self.f, self.sought = open(path, "r+b", buffering=0), 0

    def seek(self, at):
        self.sought += 1
        return self.f.seek(at)

    def write(self, data):
        return self.f.write(data)


fb, path = screen("nonumber", 640, 480, 16, RGB16)
fb.f = NoNumber(path)
a = noise(640, 480)
fb.show(a)
b = changed(a, (100, 69, 300, 384))
got = writes(fb, lambda: fb.show_part(b, (100, 69, 300, 384)))
check(f"a screen's file with no number to write by: sought and written as ever ({fb.f.sought} times), the same "
      f"picture on it", got == [] and fb.f.sought == 1 + 315 and (on_screen(fb, path)[0] == general(b, RGB16, 16)).all())
other = NoNumber(path).f
fb.f = other
c = changed(b, (0, 10, 640, 20))
got = writes(fb, lambda: fb.show_part(c, (0, 10, 640, 20)))
check(f"...and given another file: that one's number, found afresh ({len(got)} write)", len(got) == 1
      and (on_screen(fb, path)[0] == general(c, RGB16, 16)).all())

# ---- a TV: each pixel twice, or four times ---------------------------------------------------------------------------
for name, (w, h), bpp, fields, k in (("a 1080p TV", (1920, 1080), 32, BGRX, 2), ("a 1080p TV at 16 bits", (1920, 1080), 16, RGB16, 2),
                                     ("a 4K TV", (3840, 2160), 32, BGRX, 4)):
    seen = []
    for mapped in (True, False):
        fb, path = screen(f"tv_{w}_{bpp}_{int(mapped)}", w, h, bpp, fields, mapped=mapped)
        a = noise(fb.w, fb.h)
        fb.show(a)
        box = (290, 190, 700, 461)
        b = changed(a, box)
        got = writes(fb, lambda: fb.show_part(b, box))
        px = on_screen(fb, path)[0]
        want = np.repeat(np.repeat(general(b, fields, bpp), k, 0), k, 1)
        seen.append(((fb.w, fb.h) == (w // k, h // k) and fb.sharp and (fb.memory() is not None) == mapped
                     and px.shape == want.shape and (px == want).all(), len(got)))
    check(f"{name}: the menus' pixels, each {k} x {k} of its own, the whole picture and then a part: right, mapped "
          f"(nothing written: {seen[0][1]}) and written a row at a time ({seen[1][1]} rows)", seen[0][0] and seen[1][0]
          and seen[0][1] == 0 and seen[1][1] == (461 - 190) * k)
sides, a = [], None
for mapped in (True, False):
    fb, path = screen(f"side_{int(mapped)}", 1920, 1080, 32, BGRX, turn=90, mapped=mapped)
    if a is None:                                      # (the same two pictures, both ways)
        a = noise(fb.w, fb.h)
        b = changed(a, (10, 20, 200, 300))
    fb.show(a)
    first = on_screen(fb, path)[0]
    fb.show_part(b, (10, 20, 200, 300))
    sides.append((first, on_screen(fb, path)[0]))
differ = int((sides[0][0] != sides[0][1]).sum())
check(f"a TV on its side (the menus {fb.w} x {fb.h}, scaled to it): the same pixels mapped and written, the whole "
      f"picture and then a part of it ({differ} of its pixels changed by that)",
      (sides[0][0] == sides[1][0]).all() and (sides[0][1] == sides[1][1]).all() and sides[0][1].shape == (1080, 1920)
      and 0 < differ < 1080 * 1920 // 4 and len(np.unique(sides[0][1])) > 1000)

# a picture drawn finely, on a 4K TV: each of its pixels twice
SC.pi_model = lambda: "Raspberry Pi 5 Model B Rev 1.0"
seen = []
for mapped in (True, False):
    fb, path = screen(f"fine_{int(mapped)}", 3840, 2160, 32, BGRX, mapped=mapped)
    F.set_scale(fb.s)
    im = F.Image.new("RGB", (fb.w, fb.h), (40, 120, 200))
    im.pic.paste(noise(*im.pic.size), (0, 0))
    fb.show(im)
    im2 = im.copy()
    im2.pic.paste(noise(400, 300), (600, 400))         # (the menus' 300, 200 to 500, 350: all of it in the box)
    fb.show_part(im2, (290, 190, 510, 360))
    px = on_screen(fb, path)[0]
    want = np.repeat(np.repeat(general(im2.pic, BGRX, 32), 2, 0), 2, 1)
    seen.append((fb.s, fb.rep) == (2, 2) and (px == want).all())
F.set_scale(1)
check("a picture drawn finely on a 4K TV: its own pixels, each 2 x 2, the whole of it and then a part: right, mapped "
      "and written", all(seen))
SC.pi_model = lambda: "Raspberry Pi Zero 2 W Rev 1.0"

# ---- Rock Paper Scissors' pieces: the quick way's picture is paste's -------------------------------------------------
QUICK = SIMS.RPS_QUICK
QUICK[0] = True
same, kept = [], True
for size, at in (((436, 342), (14, 80)), ((640, 480), (0, 0))):
    for r in ("Small", "Medium", "Large"):
        s = SIMS.RockPaperScissors(size[0], size[1], random.Random(3), {"size": r, "count": 30})
        s.start()
        for _ in range(40):
            s.update(0.05)
        s.x[0], s.y[0] = s.r, s.r                       # (some at the walls, and past them: their pictures' corners
        s.x[1], s.y[1] = s.w - s.r, s.h - s.r           #  off the picture's edge)
        s.x[2], s.y[2] = 0, s.h / 2
        s.x[3], s.y[3] = s.w, 0
        out = []
        for quick in (True, False):
            QUICK[0] = quick
            img = Image.new("RGB", (640, 480), SIMS.SIM_FLOOR)
            s.draw(img, *at)
            out.append(img.tobytes())
            kept = kept and QUICK[0] == quick
        same.append(out[0] == out[1] and out[0] != Image.new("RGB", (640, 480), SIMS.SIM_FLOOR).tobytes())
check(f"Rock Paper Scissors' pieces put on the picture the quick way: the picture PIL's own paste makes, in its box "
      f"and on the whole screen, every size of them, at the walls too ({same.count(True)} of {len(same)})",
      all(same) and kept)
same = []
for fs in (2, 3):
    F.set_scale(fs)
    s = SIMS.RockPaperScissors(772, 406, random.Random(4), {"size": "Medium", "count": 30})
    s.start()
    for _ in range(40):
        s.update(0.05)
    s.x[0], s.y[0] = 0.25, 0.75                         # (between the menus' pixels: where a fine picture can put it)
    s.x[1], s.y[1] = s.w, s.h
    out = []
    for quick in (True, False):
        QUICK[0] = quick
        img = F.Image.new("RGB", (960, 540), SIMS.SIM_FLOOR)
        s.draw(img, 14, 80)
        out.append(img.pic.tobytes())
        kept = kept and QUICK[0] == quick and F.detail(img) == fs
    same.append(out[0] == out[1])
F.set_scale(1)
check(f"...drawn finely too (twice, three times): the same picture ({same})", all(same) and kept)


class Odd:
    """A picture whose inside can't be had the quick way."""
    def __init__(self, img):
        self.img = img

    def load(self):
        raise AttributeError("no such thing here")

    def paste(self, *a):
        return self.img.paste(*a)


QUICK[0] = True
s = SIMS.RockPaperScissors(436, 342, random.Random(3), {"size": "Medium", "count": 30})
s.start()
plain = Image.new("RGB", (640, 480), SIMS.SIM_FLOOR)
QUICK[0] = False
s.draw(plain, 14, 80)
QUICK[0] = True
odd = Odd(Image.new("RGB", (640, 480), SIMS.SIM_FLOOR))
F_detail = SIMS.detail
SIMS.detail = lambda img: 1
try:
    s.draw(odd, 14, 80)
finally:
    SIMS.detail = F_detail
check("...a picture it can't be done to: pasted as ever, the same picture", odd.img.tobytes() == plain.tobytes())


class Core:
    """PIL's inner picture, but one that takes a piece another way than this."""
    def paste(self, *a):
        raise TypeError("not like that")


class Inner:
    def __init__(self, img):
        self.img, self.im = img, Core()

    def load(self):
        pass

    def paste(self, *a):
        return self.img.paste(*a)


inner = Inner(Image.new("RGB", (640, 480), SIMS.SIM_FLOOR))
SIMS.detail = lambda img: 1
try:
    s.draw(inner, 14, 80)
finally:
    SIMS.detail = F_detail
check(f"...a PIL that takes a piece another way: pasted as ever from then on, for good ({QUICK[0]}), the same picture",
      inner.img.tobytes() == plain.tobytes() and QUICK[0] is False)
QUICK[0] = True

# ---- how often it's drawn -------------------------------------------------------------------------------------------
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: S + "/home/u"
g.wifi_quality = lambda: 62.0
g.cpu_temp = lambda: 48.0


class FB:
    w, h, same = 640, 480, True
    count = 0

    def __init__(self):
        self.last, self.frames = None, 0

    def show(self, img):
        self.last = img; FB.count += 1; self.frames = FB.count

    def show_part(self, img, box):
        self.show(img)

    def close(self):
        pass


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.pi_slow = False
rps = SIMS.RockPaperScissors(436, 342, random.Random(1))
fish = next(c for c in SIMS.Sim.__subclasses__() if c.key == "fish")
check(f"Rock Paper Scissors is the one that's drawn as often as there's time for ({rps.smooth}); the Fish Tank and the "
      f"rest, as ever ({[c.key for c in SIMS.Sim.__subclasses__() if getattr(c, 'smooth', False)]})",
      rps.smooth is True and [c.key for c in SIMS.Sim.__subclasses__() if getattr(c, "smooth", False)] == ["rps"])
BASE = g.SIM_FPS


def run(cost, secs, t, sim=rps, step=0.01):
    """Frames costing that much for a while (from t), as the main loop has them: when the next is due asked first,
    then the frame drawn, and how long it took. The rates it was drawn at, in turn, and when it's over."""
    rates = []
    end = t + secs
    while t < end - 1e-9:
        fps = m.sim_fps(sim, t)
        m.sim_frame_took(sim, cost, t)
        if not rates or rates[-1] != fps:
            rates.append(fps)
        t += step
    return rates, t


t = 100.0
check(f"just opened: {BASE} frames a second, as ever, nothing known of what one costs",
      m.sim_fps(rps, t) == BASE and m.sim_cost is None)
rates, t = run(0.002, 1.9, t)
check(f"...and for its first couple of seconds, however cheap ({rates})", rates == [BASE])
rates, t = run(0.002, 1.0, t)
check(f"a frame taking 2 ms: 60 a second from then on ({rates})", rates == [BASE, 60] and m.sim_rate == 60)
rates, t = run(0.0045, 4.0, t)
check(f"...frames a little dearer than 60 has the time for (4.5 ms): it stays, not back and forth ({rates})",
      rates == [60])
rates, t = run(0.006, 1.5, t)
check(f"...dearer still (6 ms): 30 a second ({rates})", rates == [60, 30] and m.sim_rate == 30)
rates, t = run(0.002, 0.4, t)
check(f"...cheap again at once: still 30, a rate's kept a couple of seconds before another's tried ({rates})",
      rates == [30])
rates, t = run(0.002, 1.5, t)
check(f"...then 60 again ({rates})", rates == [30, 60])
rates, t = run(0.012, 3.0, t)
check(f"a frame taking 12 ms: 30 a second, a quarter of the time between at 60 being 4 ms ({rates})", rates[-1] == 30)
rates, t = run(0.030, 6.0, t)
check(f"a frame taking 30 ms: {BASE} a second, as ever ({rates})", rates[-1] == BASE and m.sim_rate == BASE)
rates, t = run(0.002, 3.0, t)
check(f"...and up again once they're cheap ({rates})", rates[-1] == 60)
full = [False]
m.sim_full = lambda: full[0]
full[0] = True
rates, t = run(0.020, 1.9, t)
check(f"made the whole screen: worked out afresh from its first frame there, {BASE} a second while it is ({rates}), "
      f"then what its frames there leave time for", rates == [60, BASE] and run(0.020, 3.0, t)[0] == [BASE])
t += 3.0
rates, t = run(0.002, 3.0, t)
check(f"...cheap there too: 60 ({rates})", rates[-1] == 60)
rates, t = run(0.0005, 5.0, t, sim=fish(436, 342, random.Random(1)))
check(f"the Fish Tank, however cheap: {BASE} a second, as ever ({rates})", rates == [BASE])


class TV(FB):
    w, h, same = 853, 480, False


m.fb, m.pi_slow = TV(), True
slow = g.SIM_FPS_BIG
rates, t = run(0.030, 6.0, t + 10)
check(f"a Pi Zero on a TV, a frame taking 30 ms: {slow} a second, as ever ({rates})", rates == [60, slow])
rates, t = run(0.015, 6.0, t)
check(f"...15 ms: {BASE} ({rates}); never more than a frame's cost leaves room for", rates == [slow, BASE])
check(f"what it's given to go by: half the time between frames at 20 and 30 a second, a quarter at 60 "
      f"({g.SIM_SMOOTH}); a rate kept {g.SIM_SETTLE} s, and a little leeway either way ({g.SIM_KEEN})",
      g.SIM_SMOOTH == ((20, 0.5), (30, 0.5), (60, 0.25)) and g.SIM_SETTLE == 2.0 and g.SIM_KEEN[0] < 1 < g.SIM_KEEN[1])
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
