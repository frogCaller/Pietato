"""Apps' Fish Tank, between your Pietatos (pitato/fishtank.py has the tank itself): this one's fish lives on all the
time; it tells your others where it is a few times a second (straight to each, on the beacons' port, while anyone's
watching: a screen with its Fish Tank open, or a web page's; now and then, when nobody is), and hears theirs; and it
answers the web page's Fish Tank: the whole grid as it is now, a fish's picture, food dropped in, the grid arranged."""
import collections
import io
import json
import math
import random
import socket
import time
import urllib.parse

from ..cameras import CAM_BEACON
from ..config import clean_name
from ..library import LIBRARY
from ..theme import ACCENTS
from ..fishtank import Aquarium, FISH_KINDS, FISH_WAGS, FOOD_MOST, GRID_MOST, LOOKS, fish_picture, FishTank

FISH_TICK = 0.1              # seconds between moves of this one's fish (media mode's main loop)
FISH_SAYS = (0.25, 2.0)      # seconds between telling your others where it is: while anyone's watching, or not
FISH_GONE = 4.5              # another not heard from for this long: its tank's gone from the grid
FISH_WATCHED = 10.0          # the web page's Fish Tank asked this lately: someone's watching
FISH_HEARD = 64              # what's heard from your others, waiting for the main loop, at most
FISH_PICS = 64               # fish pictures kept for the web page
FISH_PIC_SIZES = (48, 160)   # ...px long, at least and at most


def num(v, lo, hi):
    """A number from another Pietato, if it's one between lo and hi; else None."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
        return None
    return float(v)


def clean_decor(d):
    """Another tank's decorations, kept to what's expected (or {} when they aren't)."""
    if not isinstance(d, dict):
        return {}
    plants = []
    for p in (d.get("plants") or [])[:8] if isinstance(d.get("plants"), list) else []:
        if not (isinstance(p, list) and len(p) == 6 and isinstance(p[4], str) and len(p[4]) == 7
                and p[4][0] == "#" and all(ch in "0123456789abcdefABCDEF" for ch in p[4][1:])):
            continue
        u, h, w, ph = num(p[0], 0, 1), num(p[1], 0, 1), num(p[2], 0, 0.1), num(p[3], -10, 10)
        if None not in (u, h, w, ph):
            plants.append([u, h, w, ph, p[4].lower(), p[5] is True])
    rocks = []
    for r in (d.get("rocks") or [])[:4] if isinstance(d.get("rocks"), list) else []:
        if isinstance(r, list) and len(r) == 3:
            u, size, light = num(r[0], 0, 1), num(r[1], 0, 0.2), num(r[2], 0, 1)
            if None not in (u, size, light):
                rocks.append([u, size, light])
    stone = num(d.get("stone"), 0, 1)
    return {"plants": plants, "rocks": rocks, "stone": stone,
            "light": d.get("light") if d.get("light") in ("Day", "Night") else "Day"}


def hex_colour(rgb):
    return "#%02x%02x%02x" % tuple(rgb)


class FishScreen:
    """This Pietato's part of the big tank (fish_setup: media mode's start)."""

    def fish_setup(self):
        self.aquarium = aq = Aquarium()
        self.fish_next = self.fish_said = 0.0
        self.fish_web_at = -1e9      # when the web page's Fish Tank last asked (monotonic)
        self.fish_sock = None
        self.fish_heard_q = collections.deque(maxlen=FISH_HEARD)   # (from the beacons' listener: the main loop's)
        self.fish_pics = {}          # (kind, tail, size) -> a PNG, for the web page
        self.fish_snap = None        # the whole grid now, for the web page (made on the main loop)
        seed = self.setting("fish_seed")
        if isinstance(seed, int) and not isinstance(seed, bool):
            aq.seed = seed
        grid = self.setting("fish_grid")
        if isinstance(grid, dict):
            cells = self.fish_cells(grid.get("cells"))
            t = num(grid.get("t"), 0, 1e11)
            if cells is not None and t is not None:
                aq.arrange(cells, t)
        self.fish_prefs()

    def fish_prefs(self):
        """Its name, colour, fish, bubbles and light, as they are now (START's card on its Fish Tank sets them)."""
        aq = self.aquarium
        aq.me, aq.accent = self.own_name(), self.setting("accent") or ""
        aq.kind = self.sim_value(FishTank, "kind")
        aq.bubbles_on = self.sim_value(FishTank, "bubbles") != "Off"
        aq.light = self.sim_value(FishTank, "light") or "Day"

    @staticmethod
    def fish_cells(cells):
        """A grid's cells, from the web page or another Pietato: {name: (c, r)}, or None when they aren't."""
        if not isinstance(cells, dict) or len(cells) > 64:
            return None
        out = {}
        for name, at in cells.items():
            if not (isinstance(name, str) and isinstance(at, (list, tuple)) and len(at) == 2):
                return None
            c, r = at
            if any(isinstance(v, bool) or not isinstance(v, int) or not -GRID_MOST < v < 2 * GRID_MOST for v in (c, r)):
                return None
            out[clean_name(name, 40)] = (c, r)
        return out

    def on_fish_page(self):
        return self.on_sim_page() and LIBRARY[self.tab].get("sim") == "fish"

    def fish_watched(self, now):
        """Someone's watching the fish: this one's Fish Tank on its screen, a web page's, or another's says so."""
        return (self.on_fish_page() or now - self.fish_web_at < FISH_WATCHED
                or any(o.get("w") for o in self.aquarium.others.values()))

    # -- the main loop -----------------------------------------------------------------------------------------------
    def fish_tick(self, now):
        """(Media mode's main loop.) What's been heard, put in; this one's fish moved on; your others told."""
        if now < self.fish_next:
            return
        dt = min(0.5, now - (self.fish_next - FISH_TICK)) if self.fish_next else FISH_TICK
        self.fish_next = now + FISH_TICK
        aq = self.aquarium
        sharing = self.setting("share") != "Off"
        while self.fish_heard_q:
            self.fish_take(*self.fish_heard_q.popleft())
        for oid, o in list(aq.others.items()):
            o["age"] = now - o["at"]
            if not sharing or o["age"] > FISH_GONE:
                del aq.others[oid]
        self.fish_prefs()
        try:
            aq.tick(dt)
        except Exception as ex:                        # (never the main loop's end)
            print(f"fish tank: {ex!r}", flush=True)
            aq.fish = None
        if aq.ate_new:                                 # (another's food, eaten: it's told at once, so it's gone there)
            aq.ate_new = False
            self.fish_said = 0.0
        watched = self.fish_watched(now)
        if now - self.fish_web_at < FISH_WATCHED:      # (the web page's: the grid as it is now)
            aq.follow(now)
            self.fish_snap = aq.snapshot(time.time())
        if sharing and now - self.fish_said >= FISH_SAYS[0 if watched else 1]:
            self.fish_said = now
            self.fish_tell(watched)

    def fish_tell(self, watched):
        """Where this one's fish is (and its food, decorations, the grid as arranged), straight to each of yours."""
        aq = self.aquarium
        msg = dict(aq.wire(), fishtank=1, id=self.share_id, name=aq.me, accent=aq.accent,
                   w=bool(self.on_fish_page() or time.monotonic() - self.fish_web_at < FISH_WATCHED))
        data = json.dumps(msg, separators=(",", ":")).encode()
        if len(data) > 4000:                           # (the listener's size, at most: the food left out)
            msg["food"] = []
            data = json.dumps(msg, separators=(",", ":")).encode()
        ips = sorted({urllib.parse.urlsplit(u).hostname for u, _ in self.pie.peer_list()} - {None})
        if not ips:
            return
        try:
            if self.fish_sock is None:
                self.fish_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            for ip in ips:
                try:
                    self.fish_sock.sendto(data, (ip, CAM_BEACON))
                except OSError:
                    pass
        except OSError:
            self.fish_sock = None

    def fish_heard(self, ip, msg):
        """(The beacons' listener.) Another Pietato's fish, food and tank: for the main loop, if it's one of yours."""
        if self.setting("share") == "Off" or not isinstance(msg.get("id"), str) or msg["id"] == self.share_id:
            return
        if not any(urllib.parse.urlsplit(u).hostname == ip for u, _ in self.pie.peer_list()):
            return
        self.fish_heard_q.append((msg, time.monotonic()))
        self.wake()

    def fish_take(self, msg, at):
        """What another said, checked, and kept: its fish, its food, what its fish ate, its tank's look, the grid."""
        aq = self.aquarium
        oid, name = clean_name(msg.get("id"), 24), clean_name(msg.get("name"), 40)
        if not oid or not name or name == aq.me or any(o["name"] == name for k, o in aq.others.items() if k != oid):
            return                                     # (two of the same name: one in the grid, the first)
        got = {"name": name, "at": at, "age": 0.0, "w": msg.get("w") is True, "decor": clean_decor(msg.get("decor")),
               "accent": msg.get("accent") if isinstance(msg.get("accent"), str) and msg["accent"] in dict(ACCENTS)
               else "", "fish": None, "food": [], "ate": []}
        f = msg.get("fish")
        if isinstance(f, dict) and isinstance(f.get("tank"), str):
            vals = [num(f.get("u"), -0.5, 1.5), num(f.get("v"), -0.5, 1.5), num(f.get("vx"), -2, 2),
                    num(f.get("vy"), -2, 2)]
            if None not in vals and f.get("face") in (1, -1):
                got["fish"] = {"tank": clean_name(f["tank"], 40), "u": vals[0], "v": vals[1], "vx": vals[2],
                               "vy": vals[3], "face": f["face"],
                               "kind": f.get("kind") if f.get("kind") in LOOKS else FISH_KINDS[0]}
        for fl in (msg.get("food") or [])[:FOOD_MOST] if isinstance(msg.get("food"), list) else []:
            if isinstance(fl, list) and len(fl) == 4 and isinstance(fl[0], int) and isinstance(fl[1], str):
                u, v = num(fl[2], -0.5, 1.5), num(fl[3], -0.5, 1.5)
                if u is not None and v is not None:
                    got["food"].append((fl[0], clean_name(fl[1], 40), u, v))
        for a in (msg.get("ate") or [])[:40] if isinstance(msg.get("ate"), list) else []:
            if isinstance(a, list) and len(a) == 2 and isinstance(a[0], str) and isinstance(a[1], int):
                got["ate"].append((clean_name(a[0], 40), a[1]))
        grid = msg.get("grid")
        if isinstance(grid, dict):
            cells, t = self.fish_cells(grid.get("cells")), num(grid.get("t"), 0, time.time() + 300)
            if cells is not None and t is not None and aq.arrange(cells, t):
                self.set_setting("fish_grid", {"t": t, "cells": {n: list(v) for n, v in cells.items()}})
        aq.others[oid] = got

    # -- the web page (the control server's thread: it only reads what the main loop made) -----------------------------
    def web_fish(self):
        """GET /api/pi/fish: the whole grid now (each tank, every fish and flake), for the web page's Fish Tank."""
        self.fish_web_at = time.monotonic()
        snap = self.fish_snap
        if snap is None:                              # (the first ask: made here, once, the main loop's after this)
            for _ in range(3):
                try:
                    snap = self.aquarium.snapshot(time.time())
                    break
                except Exception:                      # (changed under it by the main loop: again)
                    time.sleep(0.02)
        out = dict(snap or {"t": time.time(), "tanks": [], "fish": [], "food": [], "cols": 1, "rows": 1})
        colours = {n: hex_colour(c) for n, c in ACCENTS}
        out["tanks"] = [dict(t, colour=colours.get(t.get("accent"), "#e4e8ee")) for t in out.get("tanks", [])]
        named = {t["name"]: t["colour"] for t in out["tanks"]}
        out["fish"] = [dict(f, colour=named.get(f["name"], "#e4e8ee")) for f in out.get("fish", [])]
        out["now"] = time.time()
        out["sharing"] = self.setting("share") != "Off"
        return out

    def web_fish_pic(self, kind, tail, size):
        """GET /api/pi/fishpic: a fish's picture (a PNG, facing right), for the web page to draw."""
        if kind not in LOOKS:
            return None
        try:
            tail, size = int(tail), int(size)
        except (TypeError, ValueError):
            return None
        tail = max(0, min(FISH_WAGS - 1, tail))
        size = max(FISH_PIC_SIZES[0], min(FISH_PIC_SIZES[1], size))
        key = (kind, tail, size)
        png = self.fish_pics.get(key)
        if png is None:
            buf = io.BytesIO()
            fish_picture(kind, size, math.sin(tail / FISH_WAGS * 2 * math.pi)).save(buf, "PNG")
            png = buf.getvalue()
            if len(self.fish_pics) >= FISH_PICS:
                self.fish_pics.clear()
            self.fish_pics[key] = png
        return png

    def web_fish_feed(self, cmd):
        """POST fishfeed: a pinch of food in a tank (the web page's tap on it)."""
        name = cmd.get("tank")
        if not isinstance(name, str) or not self.aquarium.feed(clean_name(name, 40)):
            return {"error": "That tank isn't there now"}
        self.fish_said = 0.0                           # (the others told at once)
        return {"ok": True}

    def web_fish_grid(self, cmd):
        """POST fishgrid: the grid as you arranged it on the web page: kept here, and told to your others."""
        cells = self.fish_cells(cmd.get("cells"))
        if cells is None:
            return {"error": "That isn't a grid"}
        t = time.time()
        if not self.aquarium.arrange(cells, max(t, self.aquarium.stored_t + 0.001)):
            return {"error": "That isn't a grid"}
        self.set_setting("fish_grid", {"t": self.aquarium.stored_t, "cells": {n: list(v) for n, v in cells.items()}})
        self.aquarium.regrid()
        self.fish_said = 0.0
        self.fish_snap = None
        return {"ok": True}

    # -- its buttons, on its Fish Tank ----------------------------------------------------------------------------------
    def fish_new_look(self):
        """Y: the plants and rocks somewhere new (kept, and the others see it too)."""
        self.aquarium.seed = random.randrange(1 << 30)
        self.set_setting("fish_seed", self.aquarium.seed)
        self.fish_said = 0.0
