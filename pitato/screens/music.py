"""Music's pages. Its songs: a grid of their covers, each with its name under it, the picked one raised a little with
a glow in its cover's colour. Now playing (Radio's too): the song's cover, big, with a glow in its colour (it follows
the beat while the battery saver's off), what's playing beside it, how far through it is and the buttons under it, all
on a soft wash of the cover. A song with no cover, or a station: a sign in its place, and the accent colour's glow.
(SELECT on Now playing: lofi art on the whole screen instead, screens/player.py.)"""
import collections
import os
import threading
import time

from ..theme import ACCENT, BG, BODY, look, MUTED, ROW, TEXT
from ..config import CACHE_DIR
from ..cover import (cover_at_hand, cover_colour, cover_file, cover_tile, cover_wash, COVER_SIDE, covers_dir,
                     found_file, GLOW_REACH, glow_mask, glow_step, glow_strength, mixed, rounded, tidy)
from ..coverfind import cover_bytes, cover_from, CoverFinder, covers_had
from ..ear import Ear
from ..library import LIBRARY, LISTEN_KINDS
from ..util import cache_name, clock, find_files

NOW_RADIUS = 12                  # the cover's corners
PULSE_FPS = 15                   # the glow's frames a second, while it follows the beat
POS_NEAR = 0.3                   # the player's word on where the song is, this near what was expected: the same
                                 # run of it (its tenths of a second evened out); further: a jump, taken as said
POS_KEPT = 3.0                   # ...and how long its word's good for (seconds)
GLOW_MOST = 0.68                 # how much of the glow's colour shows at its strongest (on a beat)
GRID_LIT = 0.75                  # ...and round the picked cover in Music's grid
COVERS_KEPT = 12                 # songs' covers kept ready for Now playing (each COVER_SIDE a side at most)
GRID_GAP = 16                    # Music's grid: the least between two covers (the menus' pixels)...
GRID_WORDS = 38                  # ...the room under each for its name, and the gap to the next row
GRID_SIDE = (96, 190)            # ...a cover's side: no smaller, no bigger
GRID_RADIUS = 10                 # ...its corners
GRID_RAISED = 4                  # ...how much bigger the picked one is, each way
GRID_GLOW = 9                    # ...and how far its glow reaches
GRID_AHEAD = 2                   # rows below the ones on the screen whose covers are got ready too
SONGS_FRESH = 60.0               # seconds a list of this one's songs, made for another of yours, is good for
TILES_KEPT = 80                  # covers kept ready at the grid's size
GRID_IDLE = 10.0                 # seconds off the grid before the thread that gets them ready stops


class MusicScreen:
    """Music's Now playing (the cover and its glow, the words, the line of how far through, the buttons), and the
    cover beside its list."""

    covers = None                # songs' covers lately looked for: {song: (its picture, its glow's colour)}, each
                                 # None for a song with none
    cover_want = None            # the song whose cover's wanted next
    cover_busy = False           # ...and that there's a thread looking
    cover_lock = threading.Lock()
    now_made = None              # what Now playing's made of for this song and screen: (what for, the pictures)
    now_shot = None              # Now playing as last drawn: (the picture, the pictures it's made of, the glow's step,
                                 # the screen's frame count then)
    song_tiles = None            # the grid's covers: {song: which of the tiles is its, or None: it has no cover}
    tiles = None                 # ...{which: (the picture at the grid's size, its glow's colour)}, the ones lately used
    tiles_busy = False           # ...and that there's a thread getting them ready
    cover_finder = None          # finding covers for the songs with none (Y on the grid), once asked
    songs_named = None           # this one's songs by name and size, for another of yours that asks for covers:
                                 # (the list they were made from, {(name, size): path})
    ear = None                   # listening to the song for its beats (ear.py), while the glow follows them
    pulse_next = 0.0             # when the glow's next frame is due
    pos_off, pos_off_at = None, 0.0   # where the song is, less the clock (as the player last said, and when)

    # -- covers --------------------------------------------------------------------------------------------------
    def cover_for(self, it):
        """A song's cover and its glow's colour, for Now playing: (picture, colour), (None, None) for a song that
        has none, or None while it's still being found (the page is drawn again when it is). A song that plays here
        from another of your Pietatos: its cover there, once it's been brought here (cover_bring)."""
        src = it.get("src") or ""
        if "://" in src:
            src = "cover:" + it["cover"] if it.get("cover") else ""
        if it.get("kind") != "audio" or not src:
            return None, None
        if self.covers is None:
            self.covers = collections.OrderedDict()
        hit = self.covers.get(src)
        if hit is not None:
            return hit
        with self.cover_lock:
            self.cover_want = src
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
                src = self.cover_want
                if src is None or src in self.covers:
                    self.cover_busy = False
                    return
            im = colour = None
            try:
                found = src[6:] if src.startswith("cover:") else cover_file(src)   # (one brought here: the picture)
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

    def cover_bring(self, it, url, name, size):
        """A song that plays here from another of your Pietatos (sent here to play, or its party's): its cover there
        brought here for Now playing (it["cover"], once it's come), the song known by its file's name and size there,
        as the grid's are. The same song here with a cover: that one. Here with none: the one brought is kept as
        its own, so it needn't be looked for."""
        if not isinstance(name, str) or not name or "/" in name or type(size) is not int or size < 0:
            return

        def bring():
            try:
                mine = self.music_songs().get((name.lower(), size))
                pic = cover_at_hand(mine) if mine else None
                if not pic:
                    pic = found_file(mine) if mine else os.path.join(covers_dir(), "from",
                                                                     cache_name(f"{name.lower()}:{size}", ".jpg"))
                    if os.path.exists(pic):
                        os.utime(pic)                  # (used just now: among the last to be thrown away)
                    elif not cover_from(url, name, size, pic):
                        return
                    elif mine:
                        self.music_cover_found(mine)   # (on the grid too)
                    else:
                        tidy(os.path.dirname(pic))
            except Exception as ex:
                print(f"cover: {ex!r}", flush=True)
                return
            it["cover"] = pic
            self.dirty = True
        threading.Thread(target=bring, daemon=True, name="cover-bring").start()

    def cover_kept(self, url, path, name, size):
        """(Its thread.) A song another of your Pietatos sent to keep has come: its cover there kept with it, if the
        song has none of its own here (in its folder, or inside it)."""
        try:
            if not cover_file(path) and cover_from(url, name, size, found_file(path)):
                self.music_cover_found(path)
        except Exception as ex:
            print(f"cover: {ex!r}", flush=True)

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

    def music_tick(self, now):
        """(Main loop.) Now playing's glow, and what the search for covers says when it's done."""
        f = self.cover_finder
        if f is not None and not f.busy and f.note:
            note, f.note = f.note, ""
            self.toast(note, 5)
        self.pulse_tick(now)

    def pulse_tick(self, now):
        """The ear for the song on Now playing, kept or let go; the glow's next frame, when it's due."""
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
        img, pics, was, shown = shot
        step = self.pulse_step()
        if step == was:
            return
        box = pics["box"]
        img.paste(self.now_lit(pics, step), (box[0], box[1]))
        fb.show_part(img, box)
        self.now_shot = (img, pics, step, getattr(fb, "frames", None))
        self.taps_kept(shown)                          # (its buttons are where they were, for a tap on the web page's
                                                       #  copy of the screen)

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
        """The buttons' drawings under the line: back, play or pause, on; Y's on the left (shuffle: lit while it's on;
        a loop with a 1 in it while the one song's played again and again), the volume on the right. Each can be
        tapped, on the web page's copy of the screen."""
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
        if not radio:
            x0, x1, up, dn = ax + 2, ax + 30, y - 7, y + 7
            if self.repeat:                            # the one song, again and again: a loop, a 1 in it
                d.rounded_rectangle((x0, up - 2, x1 + 2, dn + 2), radius=9, outline=lit, width=2)
                d.polygon([(x1 - 8, up - 6), (x1 - 8, up + 2), (x1 - 2, up - 2)], fill=lit)
                l, t, r, b = d.textbbox((0, 0), "1", font=F["badge"])   # (the figure itself in the loop's middle,
                d.text(((x0 + x1 + 2 - l - r) // 2, y - (t + b) // 2), "1", font=F["badge"], fill=lit)   # not its line)
            else:                                      # shuffle: two lines that cross, an arrowhead on each
                ink = lit if self.shuffle else soft
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
        nxt = None if radio or self.shuffle or self.repeat or self.qi + 1 >= len(self.queue) \
            else self.queue[self.qi + 1]["title"]
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
            hints = [("A", "Pause" if not self.paused else "Play"), ("◀▶", "Seek"), ("L R", "Prev/next"),
                     ("Y", "In order" if self.repeat else "Repeat" if self.shuffle else "Shuffle"),   # (what it
                     ("SELECT", "Art"), ("B", "List")]                                                #  does next)
        else:
            hints = [("A", "Pause" if not self.paused else "Play"), ("◀▶", "Station"),
                     ("▲▼", "Volume"), ("SELECT", "Art"), ("B", "List")]
        self.now_buttons(d, lay, colour, radio)
        self.footer(d, hints)
        self.fb.show(img)
        self.now_shot = (img, pics, step, getattr(self.fb, "frames", None))

    # -- Music's grid: every song a tile -----------------------------------------------------------------------------
    def music_grid(self):
        """Music's page is its grid of covers: its tab, with songs in it."""
        tab = LIBRARY[self.tab]
        return tab.get("type") == "files" and tab.get("kind") == "audio" and bool(self.items.get(self.tab))

    def music_find_covers(self):
        """Y on the grid: covers for the songs that have none, from your other Pietatos and the internet
        (coverfind.py)."""
        if self.cover_finder is None:
            self.cover_finder = CoverFinder(peers=self.saves_peers)
            self.cover_finder.on_change = self.music_changed
            self.cover_finder.on_found = self.music_cover_found
            self.cover_finder.known = lambda path: bool((self.song_tiles or {}).get(path))
        f = self.cover_finder
        if f.busy:
            self.toast("Finding covers already", 2)
        elif f.start(it["src"] for it in self.tab_items() if it["kind"] == "audio"):
            self.toast("Finding covers for the songs with none", 3)

    # -- covers, for another of your Pietatos that asks (Y on its Music) ------------------------------------------
    def music_songs(self):
        """This one's songs, by what says one's the same song as another Pietato's: {(file name in small letters,
        size): path}. Looked for afresh if it's a while since (Music needn't have been opened here)."""
        made, now = self.songs_named, time.monotonic()
        if made is None or not 0 <= now - made[0] < SONGS_FRESH:
            tab = next(t for t in LIBRARY if t.get("type") == "files" and t.get("kind") == "audio")
            named = {}
            for path in find_files(tab["dirs"], tab["exts"]):
                try:
                    named.setdefault((os.path.basename(path).lower(), os.path.getsize(path)), path)
                except OSError:
                    pass
            made = self.songs_named = (now, named)
        return made[1]

    def web_covers(self, cmd):
        """POST /api/covers (the control server's thread): another of yours lists songs of its own with no cover
        ([[file name, size]]). Which of them this one has a cover for: their numbers in that list."""
        if self.setting("share") == "Off" or not self.saves_peers(str(cmd.get("from") or "")):
            return {"ok": False, "error": "Not one of yours"}
        songs = cmd.get("songs")
        if not isinstance(songs, list):
            return {"ok": False, "error": "What's that?"}
        return {"ok": True, "have": covers_had(songs, self.music_songs())}

    def web_cover_file(self, name, size, asker):
        """GET /api/covers/file: the cover this one has for that song (a JPEG's bytes), for another of yours; None:
        it has none, or it isn't one of yours asking. The song: one of this one's Music, or one it's sent that one (or
        is playing on it), wherever it is here; its cover got out of its file now, if it hasn't been."""
        if self.setting("share") == "Off" or not self.saves_peers(str(asker or "")):
            return None
        try:
            key = (str(name or "").lower(), int(size))
            path = self.music_songs().get(key) or self.handoff_keys().named(*key)
            found = cover_file(path) if path else None
            return cover_bytes(found) if found else None
        except (OSError, ValueError, TypeError):
            return None

    def music_changed(self):
        """(The finder's thread.) It's got somewhere: the page drawn again."""
        self.dirty = True

    def music_cover_found(self, path):
        """(The finder's thread.) A song has a cover now: looked for afresh, on the grid and on Now playing."""
        if self.song_tiles is not None:
            self.song_tiles.pop(path, None)
        if self.covers is not None:
            self.covers.pop(path, None)
        self.dirty = True

    def music_hints(self, hints):
        """The grid's buttons along the bottom: the list's, and Y to find covers (what gives way, if they don't all
        fit: Controls and Tabs, which the Controls page has)."""
        f = self.cover_finder
        if f is None or not f.busy:
            hints = hints[:1] + [("Y", "Find covers")] + hints[1:]
        return self.hints_room(hints, keep=("A", "Y", "B", "START"))

    def music_layout(self):
        """The grid on this screen (the menus' pixels): cols by rows of covers, each side big, the first at x, y, the
        next dx across and dy down. As many columns as the screen's wide; two rows, where covers a little smaller
        make room for them."""
        W, H = self.fb.w, self.fb.h
        y = self.HEADER + GRID_GLOW + GRID_RAISED + 4  # (room over the top row for the picked one's glow)
        room = H - self.FOOTER - 2 - y
        cols = 3 if W < 560 else 4 if W < 800 else 5 if W < 1120 else 6
        side = min(GRID_SIDE[1], (W - 40 - (cols - 1) * GRID_GAP) // cols)
        if room // (side + GRID_WORDS) < 2 and room // 2 - GRID_WORDS >= GRID_SIDE[0]:
            side = room // 2 - GRID_WORDS
        side = max(GRID_SIDE[0], side)
        gap = max(GRID_GAP, min(28, (W - 40 - cols * side) // (cols - 1)))
        return {"cols": cols, "rows": max(1, room // (side + GRID_WORDS)), "side": side,
                "x": (W - cols * side - (cols - 1) * gap) // 2, "y": y, "dx": side + gap, "dy": side + GRID_WORDS}

    def music_step(self, sel, way, n, cols):
        """Where a press of the D-pad (not one that's held) goes from a song in the grid: on to the next, and off
        either end round to the other (right of the last: the first). Up from the top row and down from the bottom
        one go round too, in the same column."""
        if way in ("left", "right"):
            return (sel + (1 if way == "right" else -1)) % n
        last = (n - 1) // cols * cols                  # (where the bottom row starts)
        if way == "down":
            return sel + cols if sel + cols < n else sel % cols if sel >= last else n - 1
        return sel - cols if sel >= cols else min(last + sel, n - 1)

    def music_tile(self, it, px):
        """A song's cover at the grid's size (px of the screen's own pixels a side) and its glow's colour, or (None,
        None): it has none, or it's not ready yet (the thread that gets them ready draws the page again)."""
        if self.tiles is None or getattr(self, "tiles_px", None) != px:   # (another size of screen: all afresh)
            self.tiles, self.song_tiles, self.tiles_px = collections.OrderedDict(), {}, px
        key = self.song_tiles.get(it["src"])
        hit = self.tiles.get(key) if key else None
        if hit is None:
            return None, None
        self.tiles.move_to_end(key)
        return hit

    def music_tile_next(self):
        """The next song whose cover the grid wants ready ((the song, the size)): one on the screen first, then the
        rows just under them. None: they all are, or the grid's not on the screen."""
        if not (self.active and self.view == "list" and self.music_grid()) or self.tiles is None:
            return None
        items, lay = self.tab_items(), self.music_layout()
        first = self.tops.get(self.tab, 0) * lay["cols"]
        for it in items[first:first + (lay["rows"] + GRID_AHEAD) * lay["cols"]]:
            key = self.song_tiles.get(it["src"], False)
            if key is False or (key is not None and key not in self.tiles):
                return it, self.tiles_px
        return None

    def music_tile_make(self, it, px):
        """A song's cover at the grid's size, got ready: one kept on disk from before, or made now and kept there
        (a folder's cover: one for all the songs in it)."""
        from PIL import Image, ImageOps
        from ..fine import scale
        src = it["src"]
        thumbs = os.path.join(CACHE_DIR, "thumbs")
        key = os.path.join(thumbs, cache_name(src, f"-m{px}.jpg"))   # (its own: a cover from inside its file)
        im = None
        try:
            if not os.path.exists(key):
                found = cover_file(src)
                if found is None:
                    self.song_tiles[src] = None
                    return
                if not found.startswith(covers_dir() + os.sep):      # (a picture in its folder: the folder's)
                    key = os.path.join(thumbs, cache_name(found, f"-m{px}.jpg"))
                if key not in self.tiles and not os.path.exists(key):
                    im = Image.open(found)
                    im.draft("RGB", (px * 2, px * 2))
                    im = ImageOps.fit(im.convert("RGB"), (px, px), Image.LANCZOS)
                    try:
                        os.makedirs(thumbs, exist_ok=True)
                        im.save(key, quality=88)
                    except OSError:                    # (nowhere to keep it: it's made again next time)
                        pass
            if key not in self.tiles:
                if im is None:
                    im = Image.open(key).convert("RGB")
                self.tiles[key] = (rounded(im, GRID_RADIUS * scale()), cover_colour(im))
                while len(self.tiles) > TILES_KEPT:
                    self.tiles.popitem(last=False)
            self.song_tiles[src] = key
        except Exception as ex:                        # (a picture that won't open: no cover)
            print(f"cover: {ex!r}", flush=True)
            self.song_tiles[src] = None

    def music_tile_loop(self):
        """Gets the grid's covers ready, the ones on the screen first, while the grid's up (and for a little after:
        the grid starts it again)."""
        idle = 0.0
        try:
            while self.active and idle < GRID_IDLE:
                want = None if self.proc_owns_screen() else self.music_tile_next()
                if want is None:
                    idle += 0.2
                    time.sleep(0.2)
                    continue
                idle = 0.0
                self.music_tile_make(*want)
                self.dirty = True
        finally:
            self.tiles_busy = False

    def render_music(self):
        """Music: a grid of its songs' covers, each with its name under it; the picked one a little bigger, with a
        glow in its cover's colour all round it; the one that's playing marked."""
        from PIL import Image as Plain
        from ..fine import made_fine, scale
        F = self.fonts
        img, d = self.canvas()
        items = self.tab_items()
        n = len(items)
        sel = max(0, min(self.sels.get(self.tab, 0), n - 1))
        self.header(img, d)
        lay = self.music_layout()
        cols, rows, side, s = lay["cols"], lay["rows"], lay["side"], scale()
        top, srow, total = self.tops.get(self.tab, 0), sel // cols, (n + cols - 1) // cols
        top = srow if srow < top else srow - rows + 1 if srow >= top + rows else top
        top = self.tops[self.tab] = max(min(top, total - rows), 0)
        playing = self.cur["key"] if self.proc and self.kind in LISTEN_KINDS and self.cur else None
        shown = [((top + r) * cols + c, lay["x"] + c * lay["dx"], lay["y"] + r * lay["dy"])
                 for r in range(rows) for c in range(cols) if (top + r) * cols + c < n]
        tiles = {i: self.music_tile(items[i], side * s) for i, _, _ in shown}
        big = side + 2 * GRID_RAISED
        for i, x, y in shown:                          # (the picked one's glow: under everything)
            if i == sel:
                made = getattr(self, "grid_glow", None)
                if made is None or made[0] != (big, s):
                    made = self.grid_glow = ((big, s), glow_mask(big * s, GRID_GLOW * s, GRID_RADIUS * s))
                at = (x - GRID_RAISED - GRID_GLOW, y - GRID_RAISED - GRID_GLOW)
                img.paste(made_fine(Plain.new("RGB", made[1].size, tiles[i][1] or ACCENT), s), at,
                          made_fine(made[1].point(lambda v: int(v * GRID_LIT)), s))
        half = (lay["dx"] - side) // 2
        for i, x, y in shown:
            it = items[i]
            self.tappable((x - half, y - 6, x + side + half, y + lay["dy"] - 6), "sel", "sels", self.tab, i)
            pic = tiles[i][0]
            if i == sel:                               # (a little bigger, about its own middle)
                x0, y0, w = x - GRID_RAISED, y - GRID_RAISED, big
                pic = None if pic is None else pic.resize((big * s, big * s), Plain.LANCZOS)
            else:
                x0, y0, w = x, y, side
            if pic is not None:
                pic = made_fine(pic, s)
                img.paste(pic, (x0, y0), pic)
            else:
                d.rounded_rectangle((x0, y0, x0 + w - 1, y0 + w - 1), radius=GRID_RADIUS, fill=ROW)
                self.cover_sign(d, x0 + w / 2, y0 + w / 2, "note")
            on = playing is not None and it["key"] == playing
            name = self.fit(d, ("♪ " if on else "") + it["title"], F["small_b"], side)
            d.text((x, y + side + 21), name, font=F["small_b"],     # (under the picked one's glow, not in it)
                   fill=ACCENT if on else TEXT if i == sel else BODY, anchor="lm")
        self.scrollbar(d, top, rows, total, lay["y"], lay["y"] + rows * lay["dy"] - GRID_WORDS)
        f = self.cover_finder
        self.footer(d, self.music_hints(self.list_hints()), right=f"Finding covers: {f.done} of {f.total}"
                    if f is not None and f.busy else f"{sel + 1} of {n}")
        self.fb.show(img)
        if not self.tiles_busy and self.music_tile_next() is not None:
            self.tiles_busy = True
            threading.Thread(target=self.music_tile_loop, daemon=True, name="covers").start()
