"""A song's cover art, for Music: the picture named for it in its folder (cover.jpg, folder.jpg and the like), else the
one inside its file (FFmpeg gets it out once: kept small in the cache), else one found for it on the internet
(coverfind.py), else the only picture in its folder. And what Now playing makes of it: the colour its glow takes, a
soft wash of it for behind the page, the picture itself with its corners rounded, and the glow."""
import os
import subprocess

from .config import CACHE_DIR
from .util import cache_name

COVER_NAMES = ("cover", "folder", "front", "album", "artwork")   # a picture in a song's folder named like these: it
COVER_EXTS = (".jpg", ".jpeg", ".png", ".webp")
COVER_SIDE = 600                 # the most pixels a side of the one got out of a file's kept at
COVER_WAIT = 20                  # seconds FFmpeg may take over it
COVERS_MOST = 400                # ...and how many of them the cache keeps (the ones not used longest go first)
WASH_KEEP = 0.34                 # how much of the cover's own colours its wash keeps (the rest: the page's)
GLOW_REACH = 22                  # how far the glow reaches past the cover (the menus' pixels)
GLOW_REST, GLOW_STEPS = 0.45, 8  # how lit it is between beats (1: on one), and how many steps there are between


def covers_dir():
    return os.path.join(CACHE_DIR, "covers")


def found_file(path):
    """Where a cover found on the internet for a song is kept (in a folder of its own: they aren't tidied away, as
    the ones got out of songs' files are), whether or not there is one."""
    return os.path.join(covers_dir(), "found", cache_name(path, ".jpg"))


def beside(path, only=False):
    """The cover in a song's folder: a picture named for it, or (only) the one picture there is."""
    folder = os.path.dirname(path)
    try:
        names = sorted(n for n in os.listdir(folder) if n.lower().endswith(COVER_EXTS) and not n.startswith("."))
    except OSError:
        return None
    if only:
        return os.path.join(folder, names[0]) if len(names) == 1 else None
    for want in COVER_NAMES:
        for n in names:
            if os.path.splitext(n)[0].lower().startswith(want):
                return os.path.join(folder, n)
    return None


def inside(path, out, run=None):
    """The picture inside a song's file, written to out (a JPEG, COVER_SIDE a side at most): whether it has one."""
    run = run or subprocess.run
    part = out + ".part.jpg"
    size = f"scale=w='min({COVER_SIDE},iw)':h='min({COVER_SIDE},ih)':force_original_aspect_ratio=decrease"
    try:
        done = run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", path, "-an", "-map",
                    "0:v:0", "-frames:v", "1", "-vf", size, "-q:v", "3", part], stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=COVER_WAIT)
        if done.returncode == 0 and os.path.getsize(part) > 0:
            os.replace(part, out)
            return True
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        os.remove(part)
    except OSError:
        pass
    return False


def tidy(folder, most=COVERS_MOST):
    """The cache of covers, kept to most files: the ones not touched for longest are thrown away."""
    try:
        with os.scandir(folder) as found:
            files = sorted((e.stat().st_mtime, e.path) for e in found if e.is_file())
    except OSError:
        return
    for _, old in files[:max(0, len(files) - most)]:
        try:
            os.remove(old)
        except OSError:
            pass


def cover_file(path):
    """A song's cover, as a picture file, or None: it has none. (Slow the first time for a song with its picture
    inside it: not for the main loop.)"""
    if "://" in path or not os.path.isfile(path):
        return None
    named = beside(path)
    if named:
        return named
    out = os.path.join(covers_dir(), cache_name(path, ".jpg"))
    none = out[:-4] + ".none"
    if os.path.exists(out):
        try:
            os.utime(out)                              # (used just now: among the last to be thrown away)
        except OSError:
            pass
        return out
    if not os.path.exists(none):                       # (looked inside once: what it found is kept, or that it
        try:                                           #  found nothing)
            os.makedirs(covers_dir(), exist_ok=True)
            got = inside(path, out)
            if not got:
                open(none, "w").close()
            tidy(covers_dir())
            if got:
                return out
        except OSError:
            pass
    found = found_file(path)
    return found if os.path.exists(found) else beside(path, only=True)


def cover_colour(im):
    """The colour a cover's glow takes: the one there's most of among its vivid, bright ones (a sunset's orange, not
    the orange and the sea's blue stirred together), as bright as a glow is. None: a cover with hardly any colour in
    it (black and white), which gets the accent's."""
    import numpy as np
    a = np.asarray(im.convert("RGB").resize((32, 32)), dtype=np.float32).reshape(-1, 3) / 255.0
    top, low = a.max(axis=1), a.min(axis=1)
    spread = np.maximum(top - low, 1e-6)
    w = (spread / np.maximum(top, 1e-3)) ** 2 * top    # (how much each counts: vivid and bright, the most)
    if float(w.sum()) < 0.02 * len(a):
        return None
    r, g, b = a[:, 0], a[:, 1], a[:, 2]
    hue = np.where(top == r, ((g - b) / spread) % 6, np.where(top == g, (b - r) / spread + 2, (r - g) / spread + 4))
    kind = np.minimum((hue * 2).astype(int), 11)       # (twelve kinds of colour, round the wheel)
    much = np.bincount(kind, weights=w, minlength=12)
    most = int((much + 0.5 * (np.roll(much, 1) + np.roll(much, -1))).argmax())
    w = w * (np.abs((kind - most + 6) % 12 - 6) <= 1)  # (that kind, and the ones either side of it)
    c = (a * w[:, None]).sum(axis=0) / max(float(w.sum()), 1e-6)
    c = c * (max(float(c.max()), 0.82) / max(float(c.max()), 1e-3))   # (as bright as a glow is)
    return tuple(int(round(min(1.0, float(v)) * 255)) for v in c)


def mixed(c1, c2, f):
    return tuple(int(round(a + (b - a) * f)) for a, b in zip(c1, c2))


def cover_wash(im, size, page, colour, keep=WASH_KEEP):
    """A soft wash for behind a page, size big: the cover out of focus, most of the way to the page's colour (so
    the words on it read as they do on any page: keep, how much of the cover's own colours stays); with no cover,
    the page's colour with a little of the glow's at the top."""
    from PIL import Image, ImageFilter, ImageOps
    w, h = size
    if im is None:
        small = Image.new("RGB", (1, 2), page)
        small.putpixel((0, 0), mixed(page, colour, 0.2))
        return small.resize(size, Image.BILINEAR)
    small = ImageOps.fit(im.convert("RGB"), (24, max(1, 24 * h // w)), Image.BILINEAR)   # (only its big patches
    small = small.filter(ImageFilter.GaussianBlur(3))                                    #  of colour, no shapes)
    return Image.blend(Image.new("RGB", size, page), small.resize(size, Image.BICUBIC), keep)


def rounded(pic, radius):
    """A picture with its corners rounded (RGBA: see-through outside them)."""
    from PIL import Image, ImageDraw
    k = 3                                              # (drawn bigger, then made small: smooth corners)
    mask = Image.new("L", (pic.width * k, pic.height * k), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, mask.width - 1, mask.height - 1), radius=radius * k, fill=255)
    out = pic.convert("RGBA")
    out.putalpha(mask.resize(pic.size, Image.LANCZOS))
    return out


def cover_tile(im, side, radius):
    """The cover, side pixels square, its corners rounded."""
    from PIL import Image, ImageOps
    return rounded(ImageOps.fit(im.convert("RGB"), (side, side), Image.LANCZOS), radius)


def glow_mask(side, reach, radius):
    """How strongly the glow shows round a square side big, reach past it each way (L: the whole of it at its
    strongest, 255 right at the square, fading out to nothing at reach)."""
    from PIL import Image, ImageDraw, ImageFilter
    k = 4                                              # (made small and enlarged: it's soft anyway, and quick so)
    full = side + 2 * reach
    small = Image.new("L", (max(8, full // k), max(8, full // k)), 0)
    r = reach * small.width / full
    edge = r * 0.62                                    # (lit from a little outside the square, in to its middle)
    ImageDraw.Draw(small).rounded_rectangle((edge, edge, small.width - 1 - edge, small.height - 1 - edge),
                                            radius=radius / k + r * 0.3, fill=255)
    return small.filter(ImageFilter.GaussianBlur(r * 0.34)).resize((full, full), Image.BILINEAR)


def glow_step(level):
    """Which of the glow's steps a level's (0: at rest, to GLOW_STEPS - 1: on a beat)."""
    return max(0, min(GLOW_STEPS - 1, int(round(level * (GLOW_STEPS - 1)))))


def glow_strength(step):
    """How strongly the glow shows at a step (GLOW_REST of its strongest at rest, all of it on a beat)."""
    return GLOW_REST + (1.0 - GLOW_REST) * step / (GLOW_STEPS - 1)
