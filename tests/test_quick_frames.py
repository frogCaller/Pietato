"""A frame of Apps' worlds made quicker, and the screen just as it was. The real Framebuffer, written to stand-in
screens (files): the usual 16-bit and 32-bit pixels packed the quick ways give the bytes the general way does; a
part that's most of the way across goes as whole rows in one go, a narrow one a row at a time, and what's on the
screen is the picture either way (the GPi Case's screen, one with rows longer than its pixels, one that starts
further down); a TV's doubled pixels, mapped or written, are the picture's, each twice (four times on a 4K one),
on its side too. And how often a world's drawn: 20 times a second, 10 on a Pi Zero's TV."""
import os, shutil, sys
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
BOXES = (("a wide one in the middle", (100, 69, 548, 384)), ("an app's box", tuple(g.SIM_BOX)),
         ("its box and its numbers", tuple(g.SIM_DIRTY)),
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

# ---- how often a world's drawn ---------------------------------------------------------------------------------------
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: S + "/home/u"
g.wifi_quality = lambda: 62.0
g.cpu_temp = lambda: 48.0


class FB:
    w, h, same = 640, 480, True

    def __init__(self):
        self.last, self.frames = None, 0

    def show(self, img):
        self.last = img

    def show_part(self, img, box):
        self.show(img)

    def close(self):
        pass


class TV(FB):
    w, h, same = 853, 480, False


m = g.Media(); m.load_fonts(); m.fb = FB(); m.active = True
m.pi_slow = False
rates = [m.sim_fps()]
m.fb = TV()
rates.append(m.sim_fps())
check(f"a world's drawn {g.SIM_FPS} times a second, on a TV too ({rates})", rates == [20, 20] and g.SIM_FPS == 20)
m.pi_slow = True
rates = [m.sim_fps()]
m.fb = FB()
rates.append(m.sim_fps())
check(f"...a Pi Zero on a TV: {g.SIM_FPS_BIG}, each of them scaled up; on its own screen, as ever ({rates})",
      rates == [10, 20] and g.SIM_FPS_BIG == 10)
check("...and none of them more often than that: nothing's left of the one that was",
      not [c.key for c in SIMS.Sim.__subclasses__() if getattr(c, "smooth", False)]
      and not [n for n in ("SIM_SMOOTH", "SIM_SETTLE", "SIM_KEEN", "RockPaperScissors") if hasattr(SIMS, n)]
      and not [n for n in ("sim_frame_took", "sim_cost", "sim_rate") if hasattr(m, n)])
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
