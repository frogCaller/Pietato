"""Music's pages. Now playing (Radio's too): the song's cover, big, with a glow in its colour (it follows the beat
while the battery saver's off), what's playing beside it, how far through it is and the buttons under it, all on a soft
wash of the cover. A song with no cover, or a station: a sign in its place, and the accent colour's glow. And Music's
list: the picked song's cover beside it, a wash of it behind. (SELECT on Now playing: lofi art on the whole screen
instead, screens/player.py.)"""
import collections
import os
import threading
import time

from ..theme import ACCENT, BG, BODY, look, MUTED, ROW, TEXT
from ..cover import (cover_colour, cover_file, cover_tile, cover_wash, COVER_SIDE, GLOW_REACH, glow_mask, glow_step,
                     glow_strength, mixed, rounded)
from ..ear import Ear
from ..library import LIBRARY
from ..util import clock

NOW_RADIUS = 12                  # the cover's corners
PULSE_FPS = 15                   # the glow's frames a second, while it follows the beat
POS_NEAR = 0.3                   # the player's word on where the song is, this near what was expected: the same
                                 # run of it (its tenths of a second evened out); further: a jump, taken as said
POS_KEPT = 3.0                   # ...and how long its word's good for (seconds)
GLOW_MOST = 0.9                  # how much of the glow's colour shows at its strongest
COVERS_KEPT = 12                 # songs' covers kept ready (each COVER_SIDE a side at most)
LIST_COVER = 212                 # the picked song's cover, beside Music's list (the menus' pixels)
LIST_WAIT = 0.2                  # seconds a song stays picked before its cover's looked for (one scrolled past: not)
LIST_KEEP = 0.26                 # how much of the cover's colours the list's wash keeps (less than Now playing's)
LIST_NARROW = 560                # a screen narrower than this: just the list


class MusicScreen:
    """Music's Now playing (the cover and its glow, the words, the line of how far through, the buttons), and the
    cover beside its list."""

    covers = None                # songs' covers lately looked for: {song: (its picture, its glow's colour)}, each
                                 # None for a song with none
    cover_want = None            # (the song whose cover's wanted next, how long to wait first)
    cover_busy = False           # ...and that there's a thread looking
    cover_lock = threading.Lock()
    now_made = None              # what Now playing's made of for this song and screen: (what for, the pictures)
    now_shot = None              # Now playing as last drawn: (the picture, the pictures it's made of, the glow's step,
                                 # the screen's frame count then)
    list_made = None             # ...and the list's (what for, the pictures): kept on the page while the next
                                 # song's cover is found
    list_pics = None             # ...the ones on the page now
    ear = None                   # listening to the song for its beats (ear.py), while the glow follows them
    pulse_next = 0.0             # when the glow's next frame is due
    pos_off, pos_off_at = None, 0.0   # where the song is, less the clock (as the player last said, and when)

    # -- covers --------------------------------------------------------------------------------------------------
    def cover_for(self, it, wait=0.0):
        """A song's cover and its glow's colour: (picture, colour), (None, None) for a song that has none, or None
        while it's still being found (the page is drawn again when it is). wait: seconds it must stay the one
        wanted before it's looked for."""
        src = it.get("src") or ""
        if it.get("kind") != "audio" or not src or "://" in src:
            return None, None
        if self.covers is None:
            self.covers = collections.OrderedDict()
        hit = self.covers.get(src)
        if hit is not None:
            return hit
        with self.cover_lock:
            self.cover_want = (src, wait)
            start, self.cover_busy = not self.cover_busy, True
        if start:
            threading.Thread(target=self.cover_loop, daemon=True, name="cover").start()
        return None

    def cover_loop(self):
        """Finds the cover that's wanted (the latest asked for: one no longer wanted isn't looked for), till there's
        none to find."""
        from PIL import Image
        while True:
            with self.cover_lock:
                want = self.cover_want
                if want is None or want[0] in self.covers:
                    self.cover_busy = False
                    return
            src, wait = want
            if wait:
                time.sleep(wait)
                if self.cover_want != want:
                    continue
            im = colour = None
            try:
                found = cover_file(src)
                if found:
                    im = Image.open(found)
                    im.draft("RGB", (COVER_SIDE, COVER_SIDE))
                    im = im.convert("RGB")
                    im.thumbnail((COVER_SIDE, COVER_SIDE))
                    colour = cover_colour(im)
            except Exception as ex:                    # (a picture that won't open: no cover)
                print(f"cover: {ex!r}", flush=True)
                im = colour = None
            self.covers[src] = (im, colour)
            while len(self.covers) > COVERS_KEPT:
                self.covers.popitem(last=False)
            self.dirty = True

    # -- where the song is, between the player's words on it -----------------------------------------------------
    def pos_said(self, pos):
        """The player's said where the song is (to a tenth of a second, about once a second)."""
        now = time.monotonic()
        off, was = pos - now, self.pos_off
        fresh = was is None or now - self.pos_off_at > POS_KEPT or abs(off - was) > POS_NEAR
        self.pos_off = off if fresh else was + 0.25 * (off - was)
        self.pos_off_at = now

    def heard_now(self):
        """The place in the song that's heard now (seconds), or None: it's paused, or the player's not said lately."""
        now = time.monotonic()
        if self.paused or self.pos_off is None or now - self.pos_off_at > POS_KEPT:
            return None
        return now + self.pos_off

    # -- the glow, following the beat ------------------------------------------------------------------------------
    def pulse_wanted(self):
        """Now playing's glow follows the beat: a song of yours (a file) on it, the battery saver off."""
        it = self.cur or {}
        return bool(self.active and self.view == "now" and self.kind == "audio" and self.proc is not None
                    and self.setting("now_art") != "On" and not self.resting and not self.saver_on()
                    and "://" not in (it.get("src") or "") and not self.proc_owns_screen())

    def pulse_tick(self, now):
        """(Main loop.) The ear for the song on Now playing, kept or let go; the glow's next frame, when it's due."""
        if not self.pulse_wanted():
            if self.ear is not None:
                self.ear_stop()
            return
        src = self.cur["src"]
        if self.ear is None or self.ear.src != src:
            self.ear_stop()
            self.ear = Ear(src, self.heard_now)
        if self.paused:
            self.pos_off = None                        # (where it is, said afresh when it plays on)
        if now >= self.pulse_next:
            self.pulse_next = now + 1.0 / PULSE_FPS
            self.pulse_frame()

    def ear_stop(self):
        ear, self.ear = self.ear, None
        if ear is not None:
            ear.close()

    def pulse_step(self):
        """How lit the glow is now: which of its steps."""
        ear = self.ear
        return glow_step(ear.level(self.heard_now())) if ear is not None and self.pulse_wanted() else 0

    def pulse_frame(self):
        """The glow a frame on: just the cover and its glow go to the screen, the rest as the page was drawn. (The
        whole page again if something else has been on the screen since; none while a notice or a bubble's up.)"""
        shot, fb = self.now_shot, self.fb
        if self.msg or getattr(self, "group_pop", None) or self.bored_said():
            return
        if self.dirty or shot is None or shot[3] != getattr(fb, "frames", None) or not hasattr(fb, "show_part"):
            self.dirty = True
            return
        img, pics, was, _ = shot
        step = self.pulse_step()
        if step == was:
            return
        box = pics["box"]
        img.paste(self.now_lit(pics, step), (box[0], box[1]))
        fb.show_part(img, box)
        self.now_shot = (img, pics, step, getattr(fb, "frames", None))

    # -- Now playing's pictures --------------------------------------------------------------------------------------
    def now_layout(self):
        """Where things go on this screen (the menus' pixels): the cover a square on the left, as big as leaves room
        under it for the line and the buttons."""
        W, H = self.fb.w, self.fb.h
        top, foot = self.STATUS_H, H - self.FOOTER
        room = foot - top
        side = max(120, min(int(W * 0.36), room - 172))
        ax = max(24, int(W * 0.06))
        ay = top + max(GLOW_REACH + 2, (room - side - 116) // 2)
        return {"W": W, "H": H, "foot": H if self.full_app() else foot, "side": side, "ax": ax, "ay": ay,
                "tx": ax + side + 30, "bar": ay + side + 30, "keys": ay + side + 92}

    def now_pics(self, it, lay):
        """What Now playing's made of for this song on this screen: the wash behind it, and the cover (or the sign in
        its place) with its glow, lit as each step has it. Made once, and kept till the song or the screen changes."""
        from PIL import Image
        from ..fine import made_fine, scale
        im, colour = self.cover_for(it) or (None, None)
        radio = self.kind == "radio"
        colour = colour or ACCENT
        s = scale()
        key = (it.get("src"), im is not None, radio, lay["W"], lay["foot"], lay["side"], lay["ax"], lay["ay"], s, BG,
               colour)
        if self.now_made is not None and self.now_made[0] == key:
            return self.now_made[1]
        side, reach = lay["side"], GLOW_REACH             # (each picture: s of its pixels to one of the menus')
        tile = cover_tile(im, side * s, NOW_RADIUS * s) if im is not None else \
            rounded(Image.new("RGB", (side * s, side * s), ROW), NOW_RADIUS * s)
        box = (lay["ax"] - reach, lay["ay"] - reach, lay["ax"] + side + reach, lay["ay"] + side + reach)
        pics = {"wash": made_fine(cover_wash(im, (lay["W"] * s, lay["foot"] * s), BG, colour), s),
                "tile": made_fine(tile, s), "colour": colour, "box": box, "reach": reach, "lit": {}, "s": s,
                "mask": glow_mask(side * s, reach * s, NOW_RADIUS * s),
                "sign": None if im is not None else ("radio" if radio else "note")}
        self.now_made = (key, pics)
        return pics

    def now_lit(self, pics, step):
        """The cover and its glow, lit as step says, on their piece of the wash (a picture the size of the glow's
        box): made once for each step."""
        from PIL import Image as Plain
        from ..fine import Image, ImageDraw, made_fine
        hit = pics["lit"].get(step)
        if hit is not None:
            return hit
        s, box, mask, tile, reach = pics["s"], pics["box"], pics["mask"], pics["tile"], pics["reach"]
        part = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), BG)
        part.paste(pics["wash"].crop(box), (0, 0))
        strength = glow_strength(step) * GLOW_MOST
        part.paste(made_fine(Plain.new("RGB", mask.size, pics["colour"]), s), (0, 0),
                   made_fine(mask.point(lambda v: int(v * strength)), s))
        part.paste(tile, (reach, reach), tile)
        if pics["sign"]:
            self.cover_sign(ImageDraw.Draw(part), reach + tile.width / 2, reach + tile.height / 2, pics["sign"])
        pics["lit"][step] = part
        return part

    def cover_sign(self, d, x, y, sign):
        """What stands in for a cover, in the middle of its square: a note, or a station's little broadcast sign."""
        if sign == "radio":
            y += 18
            d.ellipse((x - 9, y - 9, x + 9, y + 9), fill=ACCENT)
            for r in (26, 44, 62):
                d.arc((x - r, y - r, x + r, y + r), 225, 315, fill=ACCENT, width=5)
        else:
            d.text((x, y), "♪", font=self.fonts["note"], fill=ACCENT, anchor="mm")

    # -- Now playing ---------------------------------------------------------------------------------------------------
    def now_words(self, it):
        """(what's playing, who by, the record it's on, what's said small under them)."""
        if self.kind == "radio":
            return it.get("title", ""), self.meta.get("song") or it.get("sub") or "", "", \
                f"Station {self.qi + 1} of {len(self.queue)}"
        src = it.get("src", "")
        folder = os.path.basename(os.path.dirname(src)) if "://" not in src else ""
        return (self.meta.get("title") or it.get("title", ""), self.meta.get("artist") or folder,
                self.meta.get("album") or "", f"Track {self.qi + 1} of {len(self.queue)}")

    @staticmethod
    def now_inks(colour):
        """(the glow's colour as a line or a lit button has it, the small words' colour, an empty line's): each
        clear on the wash, on a dark page or a light one."""
        lit = colour if look() == "Dark" else mixed(colour, TEXT, 0.35)
        return lit, mixed(MUTED, BODY, 0.6), mixed(BG, TEXT, 0.2)

    def now_buttons(self, d, lay, colour, radio):
        """The buttons' drawings under the line: back, play or pause, on; shuffle on the left (lit while it's on),
        the volume on the right. Each can be tapped, on the web page's copy of the screen."""
        lit, soft, _ = self.now_inks(colour)
        F, W = self.fonts, lay["W"]
        cx, y, ax = W // 2, lay["keys"], lay["ax"]
        d.ellipse((cx - 23, y - 23, cx + 23, y + 23), fill=TEXT)
        if self.paused:
            d.polygon([(cx - 7, y - 11), (cx - 7, y + 11), (cx + 12, y)], fill=BG)
        else:
            d.rectangle((cx - 9, y - 10, cx - 3, y + 10), fill=BG)
            d.rectangle((cx + 3, y - 10, cx + 9, y + 10), fill=BG)
        for way, x in ((-1, cx - 82), (1, cx + 82)):   # (a triangle and a bar: the one before, the next)
            d.polygon([(x - 8 * way, y - 11), (x - 8 * way, y + 11), (x + 9 * way, y)], fill=TEXT)
            d.rectangle((x + 10 * way - 2, y - 11, x + 10 * way + 2, y + 11), fill=TEXT)
        self.tappable((cx - 34, y - 30, cx + 34, y + 30), "keys", "a")
        self.tappable((cx - 116, y - 30, cx - 48, y + 30), "keys", "left" if radio else "l")
        self.tappable((cx + 48, y - 30, cx + 116, y + 30), "keys", "right" if radio else "r")
        if not radio:                                  # shuffle: two lines that cross, an arrowhead on each
            ink = lit if self.shuffle else soft
            x0, x1, up, dn = ax + 2, ax + 30, y - 7, y + 7
            for a, b in ((dn, up), (up, dn)):
                d.line([(x0, a), (x0 + 8, a), (x1 - 12, b), (x1 - 5, b)], fill=ink, width=2, joint="curve")
                d.polygon([(x1 - 6, b - 5), (x1 - 6, b + 5), (x1, b)], fill=ink)
            self.tappable((ax - 12, y - 26, ax + 46, y + 26), "keys", "y")
        d.text((W - ax, y), f"Volume {self.volume}", font=F["small"], fill=soft, anchor="rm")

    def render_now(self):
        if self.setting("now_art") == "On":
            return self.render_lofi()
        F = self.fonts
        img, d = self.canvas()
        it = self.cur or {"title": "", "src": "", "sub": ""}
        radio = self.kind == "radio"
        lay = self.now_layout()
        W, ax, ay, side = lay["W"], lay["ax"], lay["ay"], lay["side"]
        pics = self.now_pics(it, lay)
        colour = pics["colour"]
        lit, soft, empty = self.now_inks(colour)
        img.paste(pics["wash"], (0, 0))
        step = self.pulse_step()
        img.paste(self.now_lit(pics, step), (pics["box"][0], pics["box"][1]))
        if not self.full_app():
            self.status_bar(d)

        title, by, record, small = self.now_words(it)
        tx = lay["tx"]
        tw = W - tx - 24
        y = ay + 20
        if radio:
            d.text((tx, y - 2), "LIVE", font=F["key"], fill=ACCENT, anchor="lm")
            y += 30
        for line in self.wrap(d, title, F["big"], tw, 3 if side >= 200 and not radio else 2):
            d.text((tx, y), line, font=F["big"], fill=TEXT, anchor="lm")
            y += 31
        y += 3
        for line in self.wrap(d, by, F["row"], tw, 2 if radio else 1) if by else ():
            d.text((tx, y), line, font=F["row"], fill=BODY, anchor="lm")
            y += 27
        if record:
            d.text((tx, y + 1), self.fit(d, record, F["small"], tw), font=F["small"], fill=BODY, anchor="lm")
        foot = ay + side - 10
        nxt = None if radio or self.shuffle or self.qi + 1 >= len(self.queue) else self.queue[self.qi + 1]["title"]
        if nxt:
            d.text((tx, foot), self.fit(d, "Next: " + nxt, F["small"], tw), font=F["small"], fill=soft, anchor="lm")
            foot -= 22
        d.text((tx, foot), small, font=F["small"], fill=soft, anchor="lm")

        bar = lay["bar"]
        if not radio:
            length = self.meta.get("length") or (self.length(it) if it.get("kind") else 0) or 0
            d.rounded_rectangle((ax, bar, W - ax, bar + 5), radius=2, fill=empty)
            if length:
                frac = min(self.pos / length, 1)
                d.rounded_rectangle((ax, bar, ax + max(5, (W - 2 * ax) * frac), bar + 5), radius=2, fill=lit)
            d.text((ax, bar + 21), clock(self.pos), font=F["small"], fill=BODY, anchor="lm")
            if length:
                d.text((W - ax, bar + 21), clock(length), font=F["small"], fill=soft, anchor="rm")
            hints = [("A", "Pause" if not self.paused else "Play"), ("◀▶", "Seek"),
                     ("L R", "Prev/next"), ("Y", "Shuffle"), ("SELECT", "Art"), ("B", "List")]
        else:
            hints = [("A", "Pause" if not self.paused else "Play"), ("◀▶", "Station"),
                     ("▲▼", "Volume"), ("SELECT", "Art"), ("B", "List")]
        self.now_buttons(d, lay, colour, radio)
        self.footer(d, hints)
        self.fb.show(img)
        self.now_shot = (img, pics, step, getattr(self.fb, "frames", None))

    # -- Music's list: the picked song's cover beside it -----------------------------------------------------------
    def music_side(self, img, items, sel):
        """(Music's list, as it's drawn.) How much of the list's right is the picked song's cover's: none on another
        tab, with no songs, or on a narrow screen. A soft wash of the cover goes behind the list (the one before
        stays while the picked song's is found)."""
        tab = LIBRARY[self.tab]
        if tab.get("type") != "files" or tab.get("kind") != "audio" or not items or self.fb.w < LIST_NARROW:
            return 0
        from ..fine import made_fine, scale
        W, s = self.fb.w, scale()
        it = items[min(sel, len(items) - 1)]
        area = (W, self.fb.h - self.HEADER - self.FOOTER - 1)
        got = self.cover_for(it, LIST_WAIT)
        key = (it.get("src"), area, s, BG)
        if got is not None and (self.list_made is None or self.list_made[0] != key):
            im = got[0]
            self.list_made = (key, {
                "wash": None if im is None else made_fine(
                    cover_wash(im, (area[0] * s, area[1] * s), BG, ACCENT, LIST_KEEP), s),
                "tile": None if im is None else made_fine(cover_tile(im, LIST_COVER * s, NOW_RADIUS * s), s)})
        pics = self.list_made[1] if self.list_made is not None and self.list_made[0][1:] == key[1:] else None
        self.list_pics = pics
        if pics is not None and pics["wash"] is not None:
            img.paste(pics["wash"], (0, self.HEADER + 1))
        return LIST_COVER + 8

    def music_panel(self, img, d, it):
        """The picked song's cover beside the list (no cover: a note in its place), and the folder it's in under
        it. A tap on it plays the song."""
        F, W = self.fonts, self.fb.w
        px, py = W - LIST_COVER - 16, self.list_top() + 4
        pics = self.list_pics
        if pics is not None and pics["tile"] is not None:
            img.paste(pics["tile"], (px, py), pics["tile"])
        else:
            d.rounded_rectangle((px, py, px + LIST_COVER, py + LIST_COVER), radius=NOW_RADIUS, fill=ROW)
            self.cover_sign(d, px + LIST_COVER / 2, py + LIST_COVER / 2, "note")
        self.tappable((px - 6, py - 4, W, self.fb.h - self.FOOTER), "keys", "a")
        y = py + LIST_COVER + 14
        if y + 18 > self.fb.h - self.FOOTER:           # (a short screen: the cover's all there's room for)
            return
        folder = os.path.basename(os.path.dirname(it.get("src", "")))
        for line in self.wrap(d, folder, F["small_b"], LIST_COVER, 2) if folder else ():
            d.text((px, y), line, font=F["small_b"], fill=BODY, anchor="lt")
            y += 19
