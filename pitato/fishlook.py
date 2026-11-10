"""How the Fish Tank looks (pitato/fishtank.py has what happens in it): a tank's water, drawn once and kept (back); a
flake of food (a little picture, kept); and the fish themselves (fish_picture: each kind's own, simply drawn, like a
cartoon: flat colours, a dark outline, a few marks; a picture for each place its tail swings to, each drawn once and
kept)."""
import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

WATER = {"Day": ((96, 196, 230), (14, 64, 122)), "Night": ((30, 70, 112), (4, 14, 34))}   # (at the surface, deep down)
LIGHT = {"Day": (226, 246, 255), "Night": (150, 190, 240)}   # light from above: its colour


def mix(a, b, t):
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def rnd_for(*key):
    return random.Random("|".join(str(k) for k in key))


# ---- a tank's water: drawn once ----------------------------------------------------------------------------------
def water(pw, ph, depth0, depth1, light, top, sides):
    """The water, darker the deeper it is in the grid (depth0 to depth1: this tank's top and bottom, 0 the surface,
    1 the grid's bottom), lighter up the middle where the light comes down, darker towards its glass (vignette). An
    RGB array (worked out a row and a column at a time: quick)."""
    hi, deep = (np.array(c, np.float32) for c in WATER[light])
    y = np.linspace(depth0, depth1, ph, dtype=np.float32)
    row = hi + (deep - hi) * np.clip(y, 0, 1)[:, None] ** 0.8                  # (ph, 3)
    x = np.linspace(-1, 1, pw, dtype=np.float32)
    glow = np.clip(1.0 - y * 1.6, 0, 1) * (0.14 if top else 0.06)            # (ph,): up the middle...
    across = np.exp(-(x * 1.1) ** 2)                                          # (pw,): ...in the middle
    vy, vx = vignette(pw, ph, sides)
    col = row[:, None, :] * (1 + glow[:, None, None] * across[None, :, None])
    col *= (vy[:, None] * vx[None, :])[:, :, None]
    return np.clip(col, 0, 255)


def rays(pw, ph, seed, light, depth0):
    """Soft beams of light from the surface, fading as they go down: an L picture (drawn small, then made big)."""
    lay = Image.new("L", (max(8, pw // 4), max(8, ph // 4)), 0)
    d = ImageDraw.Draw(lay)
    r = rnd_for("rays", seed)
    w, h = lay.size
    for _ in range(5):
        x = r.uniform(-0.25, 1.0) * w
        spread, lean = r.uniform(0.03, 0.08) * w, r.uniform(0.1, 0.35) * h
        d.polygon([(x, 0), (x + spread, 0), (x + spread * 1.8 + lean, h), (x + lean, h)], fill=r.randint(22, 44))
    lay = lay.filter(ImageFilter.GaussianBlur(max(1, w // 50)))
    fade = np.clip(1.0 - (depth0 + np.linspace(0, 1, h, dtype=np.float32) * 0.6) * 1.3, 0, 1)[:, None]
    a = np.asarray(lay, np.float32) * fade * (0.55 if light == "Night" else 1.0)
    return Image.fromarray(a.astype(np.uint8), "L").resize((pw, ph), Image.BILINEAR)


def vignette(pw, ph, sides):
    """Darker towards a tank's edges with no tank beyond (a little at the others, so the screens still feel like one):
    (down, across), each way's own."""
    x = np.linspace(-1, 1, pw, dtype=np.float32)
    y = np.linspace(-1, 1, ph, dtype=np.float32)
    kx = np.where(x < 0, 1.0 if "l" in sides else 0.35, 1.0 if "r" in sides else 0.35)
    ky = np.where(y < 0, 0.6 if "t" in sides else 0.25, 1.0 if "b" in sides else 0.35)
    return 1 - 0.18 * (np.abs(y) * ky) ** 2.5, 1 - 0.2 * (np.abs(x) * kx) ** 2.5


def back(pw, ph, seed, light, depth0, depth1, top, sides):
    """A tank's water (pw x ph pixels): darker the deeper it is, light coming down from the surface, the surface itself
    along the top of a tank at the top, and its glass at the sides with no tank beyond them (sides: which those are,
    of "l", "r", "t", "b"). An RGB picture."""
    pic = Image.fromarray(water(pw, ph, depth0, depth1, light, top, sides).astype(np.uint8), "RGB")
    pic.paste(LIGHT[light], (0, 0), rays(pw, ph, seed, light, depth0))
    if top:                                           # (the surface, seen from below: silvery)
        band = max(3, int(ph * 0.035))
        a = np.linspace(1, 0, band, dtype=np.float32) ** 1.6 * (150 if light == "Day" else 90)
        sheen = Image.fromarray(np.repeat(a[:, None], pw, axis=1).astype(np.uint8), "L")
        pic.paste(mix(LIGHT[light], (255, 255, 255), 0.3), (0, 0), sheen)
    if sides:                                         # (the glass: a fine line of light at its edges)
        d = ImageDraw.Draw(pic)
        line = mix(LIGHT[light], (0, 0, 0), 0.25)
        k = max(1, ph // 300)
        if "l" in sides:
            d.line([(k, 0), (k, ph)], fill=line, width=k)
        if "r" in sides:
            d.line([(pw - 1 - k, 0), (pw - 1 - k, ph)], fill=line, width=k)
    return pic


# ---- food -----------------------------------------------------------------------------------------------------------
def flake_picture(size, turn, seed):
    """A flake of fish food, turning as it sinks: an outlined bit, like the fish."""
    K = 4
    n = max(3, int(size * 3 + 2))
    pic = Image.new("RGBA", (n * K, n * K), (0, 0, 0, 0))
    r = rnd_for("flake", seed)
    pts = []
    for i in range(6):
        a = i / 6 * 2 * math.pi + turn
        rr = size * K * r.uniform(0.65, 1.1)
        pts.append((n * K / 2 + math.cos(a) * rr, n * K / 2 + math.sin(a) * rr * 0.6))
    col = r.choice([(222, 128, 56), (198, 92, 44), (232, 168, 74), (132, 160, 64)])
    d = ImageDraw.Draw(pic)
    d.polygon(pts, fill=col + (255,))
    d.line(pts + [pts[0]], fill=(60, 34, 22, 255), width=max(1, int(size * K * 0.25)), joint="curve")
    return pic.reduce(K)


# ---- the fish -------------------------------------------------------------------------------------------------------
def smooth(points, n=4):
    """A line through points, rounded (Catmull-Rom): n more between each two."""
    if len(points) < 3:
        return list(points)
    pts = [points[0]] + list(points) + [points[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2 + (-a + 3 * b - 3 * c + d) * t3)
                             for a, b, c, d in zip(p0, p1, p2, p3)))
    out.append(points[-1])
    return out


def runs(points, corners, n=4):
    """A shape through points, rounded between its corners (the indices that stay sharp)."""
    cut = sorted(set([0, len(points) - 1] + list(corners)))
    out = []
    for a, b in zip(cut, cut[1:]):
        seg = smooth(points[a:b + 1], n)
        out += seg if not out else seg[1:]
    return out


# Each kind: its colours; its body's outline (from its tail to its nose: along it, and how far up, or down; it's 1 long,
# nose to tail tip); its tail (its outline from where it joins on, which points stay sharp, where its lines go); its
# fins ((from, to) along its back or belly, their outline, which points stay sharp, how many lines), and the one on its
# side (where it's joined on, its outline, its lines); its eye (where, how big); its markings.
KINDS = {
    "Goldfish": dict(
        body=(247, 146, 30), fin=(241, 94, 38), ray=(206, 68, 28), mark=(253, 192, 84), ink=(38, 24, 20),
        top=[(-0.22, -0.055), (-0.13, -0.08), (-0.01, -0.135), (0.13, -0.168), (0.27, -0.162), (0.38, -0.123),
             (0.45, -0.066), (0.485, 0.0)],
        low=[(-0.22, 0.055), (-0.13, 0.075), (-0.01, 0.125), (0.13, 0.152), (0.27, 0.146), (0.38, 0.112),
             (0.45, 0.06), (0.485, 0.0)],
        tail=([(0.03, -0.055), (-0.07, -0.125), (-0.17, -0.205), (-0.275, -0.24), (-0.245, -0.14), (-0.195, -0.05),
               (-0.165, 0.0), (-0.195, 0.05), (-0.245, 0.14), (-0.275, 0.24), (-0.17, 0.205), (-0.07, 0.125),
               (0.03, 0.055)], (0, 3, 6, 9, 12),
              [(-0.25, -0.2), (-0.22, -0.11), (-0.17, -0.035), (-0.17, 0.035), (-0.22, 0.11), (-0.25, 0.2)]),
        dorsal=(0.16, -0.12, [(0.11, -0.24), (0.02, -0.3), (-0.08, -0.3), (-0.14, -0.21)], (), 4),
        anal=(-0.04, -0.15, [(-0.1, 0.17), (-0.185, 0.215), (-0.165, 0.135)], (2,), 2),
        pelvic=(0.1, 0.0, [(0.07, 0.19), (0.0, 0.245), (0.01, 0.175)], (2,), 2),
        pectoral=((0.23, 0.07), [(0.19, 0.13), (0.11, 0.205), (0.08, 0.175), (0.14, 0.1)], 3),
        eye=(0.335, -0.045, 0.053), marks="scales"),
    "Clownfish": dict(
        body=(250, 124, 34), fin=(248, 116, 30), ray=(208, 80, 20), mark=(252, 252, 246), ink=(30, 22, 22),
        top=[(-0.2, -0.06), (-0.11, -0.09), (0.02, -0.145), (0.17, -0.17), (0.31, -0.145), (0.42, -0.085),
             (0.475, 0.0)],
        low=[(-0.2, 0.06), (-0.11, 0.085), (0.02, 0.13), (0.17, 0.15), (0.31, 0.125), (0.42, 0.07), (0.475, 0.0)],
        tail=([(0.03, -0.055), (-0.05, -0.1), (-0.13, -0.13), (-0.195, -0.095), (-0.215, 0.0), (-0.195, 0.095),
               (-0.13, 0.13), (-0.05, 0.1), (0.03, 0.055)], (0, 8),
              [(-0.17, -0.09), (-0.2, -0.03), (-0.2, 0.03), (-0.17, 0.09)]),
        dorsal=(0.22, -0.14, [(0.18, -0.215), (0.11, -0.245), (0.05, -0.205), (-0.04, -0.255), (-0.12, -0.22)],
                (3,), 4),
        anal=(-0.03, -0.15, [(-0.07, 0.19), (-0.14, 0.205), (-0.165, 0.13)], (), 2),
        pelvic=(0.13, 0.05, [(0.1, 0.21), (0.04, 0.24), (0.05, 0.17)], (2,), 2),
        pectoral=((0.26, 0.06), [(0.21, 0.12), (0.14, 0.175), (0.11, 0.135), (0.16, 0.075)], 3),
        eye=(0.345, -0.05, 0.058), marks="bands"),
    "Betta": dict(
        body=(54, 92, 212), fin=(146, 62, 196), ray=(196, 128, 238), mark=(104, 146, 242), ink=(26, 22, 50),
        top=[(-0.12, -0.05), (-0.03, -0.07), (0.1, -0.095), (0.24, -0.098), (0.36, -0.075), (0.44, -0.04),
             (0.47, 0.0)],
        low=[(-0.12, 0.05), (-0.03, 0.07), (0.1, 0.09), (0.24, 0.09), (0.36, 0.068), (0.44, 0.036), (0.47, 0.0)],
        tail=([(0.03, -0.05), (-0.08, -0.14), (-0.2, -0.205), (-0.32, -0.195), (-0.395, -0.085), (-0.405, 0.06),
               (-0.355, 0.2), (-0.26, 0.3), (-0.15, 0.29), (-0.06, 0.16), (0.03, 0.05)], (0, 10),
              [(-0.29, -0.16), (-0.36, -0.05), (-0.37, 0.07), (-0.32, 0.19), (-0.21, 0.26)]),
        dorsal=(0.12, -0.1, [(0.06, -0.2), (-0.06, -0.27), (-0.17, -0.25), (-0.21, -0.13)], (), 4),
        anal=(0.17, -0.1, [(0.1, 0.2), (-0.02, 0.3), (-0.16, 0.315), (-0.21, 0.2)], (), 5),
        pelvic=(0.25, 0.2, [(0.21, 0.2), (0.14, 0.3), (0.17, 0.18)], (1,), 1),
        pectoral=((0.29, 0.04), [(0.25, 0.085), (0.19, 0.115), (0.19, 0.08), (0.24, 0.05)], 2),
        eye=(0.37, -0.03, 0.046), marks="scales"),
    "Angelfish": dict(
        body=(230, 234, 240), fin=(214, 220, 230), ray=(170, 178, 194), mark=(48, 52, 66), ink=(34, 38, 52),
        top=[(-0.13, -0.05), (-0.05, -0.11), (0.07, -0.2), (0.19, -0.225), (0.31, -0.17), (0.41, -0.08),
             (0.455, 0.0)],
        low=[(-0.13, 0.05), (-0.05, 0.11), (0.07, 0.195), (0.19, 0.21), (0.31, 0.15), (0.41, 0.07), (0.455, 0.0)],
        tail=([(0.03, -0.05), (-0.05, -0.1), (-0.12, -0.15), (-0.32, -0.33), (-0.175, -0.1), (-0.155, 0.0),
               (-0.175, 0.1), (-0.32, 0.33), (-0.12, 0.15), (-0.05, 0.1), (0.03, 0.05)], (0, 3, 7, 10),
              [(-0.2, -0.17), (-0.14, -0.06), (-0.14, 0.06), (-0.2, 0.17)]),
        dorsal=(0.18, -0.1, [(0.12, -0.34), (0.0, -0.5), (-0.17, -0.63), (-0.155, -0.42), (-0.13, -0.2)], (3,), 4),
        anal=(0.14, -0.1, [(0.08, 0.32), (-0.04, 0.48), (-0.17, 0.61), (-0.155, 0.4), (-0.13, 0.18)], (3,), 4),
        pelvic=None,
        streamers=[[(0.21, 0.18), (0.18, 0.34), (0.12, 0.52)], [(0.18, 0.19), (0.15, 0.33), (0.08, 0.48)]],
        pectoral=((0.28, 0.05), [(0.23, 0.095), (0.16, 0.125), (0.165, 0.085), (0.22, 0.055)], 2),
        eye=(0.35, -0.065, 0.05), marks="stripes"),
    "Neon tetra": dict(
        body=(190, 200, 210), fin=(214, 226, 236), ray=(168, 184, 200), mark=(36, 198, 255), ink=(30, 34, 48),
        top=[(-0.2, -0.04), (-0.1, -0.06), (0.04, -0.1), (0.19, -0.118), (0.33, -0.098), (0.43, -0.055),
             (0.475, 0.0)],
        low=[(-0.2, 0.04), (-0.1, 0.055), (0.04, 0.09), (0.19, 0.104), (0.33, 0.085), (0.43, 0.045), (0.475, 0.0)],
        tail=([(0.03, -0.04), (-0.07, -0.09), (-0.165, -0.155), (-0.13, -0.06), (-0.105, 0.0), (-0.13, 0.06),
               (-0.165, 0.155), (-0.07, 0.09), (0.03, 0.04)], (0, 2, 4, 6, 8),
              [(-0.14, -0.11), (-0.11, -0.03), (-0.11, 0.03), (-0.14, 0.11)]),
        dorsal=(0.1, -0.02, [(0.06, -0.2), (0.0, -0.215), (-0.02, -0.14)], (1,), 2),
        anal=(0.0, -0.14, [(-0.05, 0.15), (-0.14, 0.165), (-0.155, 0.1)], (), 2),
        pelvic=(0.15, 0.08, [(0.11, 0.17), (0.05, 0.19), (0.07, 0.13)], (1,), 1),
        pectoral=((0.28, 0.05), [(0.23, 0.09), (0.17, 0.115), (0.18, 0.08), (0.23, 0.055)], 2),
        eye=(0.37, -0.025, 0.05), marks="neon"),
}


def fish_size(kind):
    """How big a kind's picture is, for its length: (across, down)."""
    k = KINDS.get(kind, KINDS["Goldfish"])
    up = max([-y for _, y in k["top"]] + [-y for _, y in k["dorsal"][2]] + [-y for _, y in k["tail"][0]]) + 0.05
    down = max([y for _, y in k["low"]] + [y for _, y in k["anal"][2]] + [y for _, y in k["tail"][0]]
               + [y for s in k.get("streamers", ()) for _, y in s]) + 0.05
    return 1.12, 2 * max(up, down)


def fish_picture(kind, length, wag):
    """A fish facing right, length px from its nose to its tail's tip (its middle in the picture's middle), its tail
    at wag (-1 to 1): flat colours, a dark outline, a few marks (drawn twice as big and made smaller, for smooth
    edges). RGBA."""
    k = KINDS.get(kind, KINDS["Goldfish"])
    K = 2
    L = length * K
    across, down = fish_size(kind)
    W, H = int(length * across + 4) * K, int(length * down + 4) * K
    cx, cy = W / 2, H / 2
    pic = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(pic)
    ink = k["ink"] + (255,)
    lw = max(2, int(round(L * 0.017)))                 # (its outline)
    fw = max(1, int(round(L * 0.008)))                 # (the lines in its fins)
    x_root = k["top"][0][0]

    def bend(x):                                      # (its body bends a little with its tail)
        return wag * 0.03 * max(0.0, (0.1 - x) / 0.32) ** 1.5

    def P(x, y):
        return cx + x * L, cy + (y + bend(x)) * L

    top = smooth(k["top"], 5)
    low = smooth(k["low"], 5)

    def edge_y(curve, x):                             # (its outline's height at x)
        for (xa, ya), (xb, yb) in zip(curve, curve[1:]):
            if xa <= x <= xb:
                return ya + (yb - ya) * ((x - xa) / max(1e-9, xb - xa))
        return curve[0][1] if x < curve[0][0] else curve[-1][1]

    def outlined(pts, fill, width=lw):
        d.polygon(pts, fill=fill)
        d.line(pts + [pts[0]], fill=ink, width=width, joint="curve")
        r = width / 2
        d.ellipse((pts[0][0] - r, pts[0][1] - r, pts[0][0] + r, pts[0][1] + r), fill=ink)

    fin = k["fin"] + (255,)
    ray = k["ray"] + (255,)

    def fin_shape(x0, x1, edge, corners, rays, side):
        """A fin on its back (side -1) or under it (1): from x0 to x1 along its outline, out to its edge."""
        curve = top if side < 0 else low
        a = (x0, edge_y(curve, x0) - side * 0.03)
        b = (x1, edge_y(curve, x1) - side * 0.03)
        pts = runs([a] + edge + [b], (0, len(edge) + 1) + tuple(c + 1 for c in corners), 5)
        outlined([P(*p) for p in pts], fin)
        for i in range(1, rays + 1):
            t = i / (rays + 1)
            bx = x0 + (x1 - x0) * t
            ex, ey = pts[int(t * (len(pts) - 1))]
            by = edge_y(curve, bx)
            d.line([P(bx, by), P(bx + (ex - bx) * 0.8, by + (ey - by) * 0.8)], fill=ray, width=fw)

    # its tail, swinging round where it joins
    pts, corners, tips = k["tail"]
    turn = wag * 0.3
    rx, ry = P(x_root + 0.015, 0.0)
    c, s = math.cos(turn), math.sin(turn)

    def T(dx, dy):
        return rx + (dx * c - dy * s) * L, ry + (dx * s + dy * c) * L
    outlined([T(*p) for p in runs(pts, corners, 5)], fin)
    for dx, dy in tips:
        d.line([T(0.0, 0.0), T(dx * 0.85, dy * 0.85)], fill=ray, width=fw)
    # the fins behind its body
    for name, side in (("dorsal", -1), ("anal", 1), ("pelvic", 1)):
        if k.get(name):
            fin_shape(*k[name], side)
    for line in k.get("streamers", ()):                # (an angelfish's long threads)
        pts = [P(*p) for p in smooth(line, 4)]
        d.line(pts, fill=ink, width=fw + lw, joint="curve")
        d.line(pts, fill=fin, width=max(1, fw), joint="curve")
    # its body: its colour and markings, kept inside its outline
    outline = [P(*p) for p in top] + [P(*p) for p in low[::-1][1:-1]]
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    bx0, by0 = int(min(xs)) - 2, int(min(ys)) - 2
    bw, bh = int(max(xs)) + 3 - bx0, int(max(ys)) + 3 - by0
    layer = Image.new("RGBA", (bw, bh), k["body"] + (255,))
    mask = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(mask).polygon([(x - bx0, y - by0) for x, y in outline], fill=255)
    m = ImageDraw.Draw(layer)
    mark = k["mark"] + (255,)

    def Q(x, y):
        px, py = P(x, y)
        return px - bx0, py - by0

    def band(x, half_w, bow, colour, edge):
        """A band across its body at x (bowed towards its nose in the middle, by bow), half_w wide each side."""
        y0, y1 = edge_y(top, x) - 0.02, edge_y(low, x) + 0.02
        left, right = [], []
        for i in range(9):
            y = y0 + (y1 - y0) * i / 8
            off = bow * (1 - ((y - (y0 + y1) / 2) / ((y1 - y0) / 2)) ** 2)
            left.append(Q(x - half_w + off, y))
            right.append(Q(x + half_w + off, y))
        m.polygon(left + right[::-1], fill=colour)
        if edge:
            m.line(left, fill=ink, width=fw + 1, joint="curve")
            m.line(right, fill=ink, width=fw + 1, joint="curve")

    marks = k["marks"]
    if marks == "scales":                             # (a few scales: little arcs)
        for row, y in enumerate((-0.075, 0.0, 0.075)):
            for col in range(4):
                x = 0.15 - col * 0.085 - (0.04 if row == 1 else 0.0)
                if not (edge_y(top, x) + 0.04 < y < edge_y(low, x) - 0.04) or x < x_root + 0.08:
                    continue
                px, py = Q(x, y)
                r = 0.034 * L
                m.arc((px - r * 1.6, py - r, px + r * 0.4, py + r), -70, 70, fill=mark, width=fw + 1)
    elif marks == "bands":                            # (a clownfish's white bands, edged in black)
        band(0.255, 0.032, -0.02, mark, True)
        band(0.04, 0.042, 0.035, mark, True)
        band(-0.185, 0.022, 0.0, mark, True)
    elif marks == "stripes":                          # (an angelfish's dark stripes)
        band(0.29, 0.02, 0.0, mark, False)
        band(0.1, 0.03, 0.0, mark, False)
        band(-0.08, 0.022, 0.0, mark, False)
    elif marks == "neon":                             # (a neon tetra's glowing line, and red behind it)
        m.polygon([Q(-0.24, 0.005), Q(0.0, 0.005), Q(0.1, 0.04), Q(0.12, 0.2), Q(-0.24, 0.2)], fill=(230, 52, 76, 255))
        line = [Q(*p) for p in smooth([(-0.19, -0.02), (0.05, -0.03), (0.25, -0.04), (0.36, -0.035)], 4)]
        m.line(line, fill=mark, width=max(2, int(L * 0.038)), joint="curve")
        m.line(line, fill=(190, 244, 255, 255), width=max(1, int(L * 0.012)), joint="curve")
    pic.paste(layer, (bx0, by0), mask)
    d.line(outline + [outline[0]], fill=ink, width=lw, joint="curve")
    # its gill, eye and mouth
    ex, ey, er = k["eye"]
    gx, gy = P(ex + 0.02, 0.0)
    d.arc((gx - 0.13 * L, gy - 0.13 * L, gx + 0.05 * L, gy + 0.12 * L), 128, 222, fill=ink, width=fw + 1)
    px, py = P(ex, ey)
    R = er * L
    d.ellipse((px - R, py - R, px + R, py + R), fill=(255, 255, 255, 255), outline=ink, width=max(1, lw - 1))
    pr = R * 0.58
    qx, qy = px + R * 0.22, py + R * 0.05
    d.ellipse((qx - pr, qy - pr, qx + pr, qy + pr), fill=ink)
    hr = R * 0.22
    d.ellipse((qx - pr * 0.1 - hr, qy - pr * 0.45 - hr, qx - pr * 0.1 + hr, qy - pr * 0.45 + hr),
              fill=(255, 255, 255, 255))
    mx, my = P(k["top"][-1][0] - 0.055, 0.035)
    mr = 0.04 * L
    d.arc((mx - mr, my - mr * 1.4, mx + mr, my + mr * 0.6), 30, 120, fill=ink, width=fw + 1)
    # its fin on its side, paddling
    (ax, ay), edge, rays = k["pectoral"]
    flap = wag * 0.25
    cf, sf = math.cos(flap), math.sin(flap)
    rot = [(ax + (x - ax) * cf - (y - ay) * sf, ay + (x - ax) * sf + (y - ay) * cf) for x, y in edge]
    pts = runs([(ax, ay)] + rot + [(ax, ay)], (0, len(rot) + 1), 5)
    outlined([P(*p) for p in pts], fin, max(1, lw - 1))
    for i in range(1, rays + 1):
        x, y = rot[min(len(rot) - 1, i)]
        d.line([P(ax, ay), P(ax + (x - ax) * 0.75, ay + (y - ay) * 0.75)], fill=ray, width=fw)
    return pic.reduce(K)
