"""The home screen: its grid of apps, and opening one."""
import random
import time

from ..theme import ACCENT, BG, BODY, co_mix, LINE, MUTED, ROW, TEXT
from ..library import LIBRARY, LISTEN_KINDS, NOW_POP_SECS
from ..home import (CARD, CARD_LINE, draw_bright_icon, draw_glyph, draw_icon, home_cols, HOME_ICONS, HOME_LABELS,
                    home_layout, mix, PALE_BOTTOM, PALE_CARD, PALE_CARD_LINE, PALE_GLYPH, PALE_TOP, tile_tint,
                    TILE_BOTTOM, TILE_TOP, wall_ink, wallpaper)
from ..weather import wx_icon_name, wx_words
from ..fine import made_fine, scale
from .draw import FOOT_NOTE

LABEL = (214, 219, 226)      # Glass: an app's name under its tile
DATE = (222, 226, 232)       # ...the date, and the weather in words
CARD_PICKED = (36, 42, 52)   # Cards: the picked card
KEY_RING = (150, 158, 170)   # ...a button's ring, along the bottom
INK = {    # the home screen's words over its background (home.py's WALLS say which): light, as ever (a dark one, a
           # picture of yours); white, with a soft shadow, over a strong colour; dark over a pale one. text: the time,
           # the app picked; date: the date and the weather in words; label: an app's name; body, muted: the smaller
           # words; note: the line about the app picked; key: a button along the bottom, and the letter on it; ring:
           # Cards' buttons; shade: how much darker than the background the shadow under the words is (None: none)
    "light": {"text": TEXT, "date": DATE, "label": LABEL, "body": BODY, "muted": MUTED, "note": FOOT_NOTE,
              "key": None, "key_text": TEXT, "ring": KEY_RING, "shade": None},
    "white": {"text": (255, 255, 255), "date": (248, 249, 251), "label": (248, 249, 251), "body": (242, 244, 248),
              "muted": (232, 236, 242), "note": (244, 246, 249), "key": (30, 34, 44), "key_text": (255, 255, 255),
              "ring": (244, 246, 249), "shade": 0.4},
    "dark": {"text": (20, 24, 32), "date": (38, 44, 56), "label": (30, 36, 46), "body": (52, 60, 74),
             "muted": (84, 92, 106), "note": (52, 60, 74), "key": (38, 44, 56), "key_text": (244, 246, 248),
             "ring": (70, 78, 92), "shade": None},
}


class HomeScreen:
    """The home screen: its grid of apps, and opening one."""

    # -- the home screen ------------------------------------------------------
    def home_apps(self):
        """(name, tab) for each icon. (Y goes to the terminal, so it has no icon.)"""
        return [(LIBRARY[i]["name"], i) for i in self.visible_tabs()]

    def playing_now(self):
        return bool(self.proc and self.kind in LISTEN_KINDS and self.cur)

    def pop_now(self):
        """What's playing pops up on the home screen for a few seconds (a song starts, the radio's song changes,
        you come back from the terminal); then the weather's back."""
        self.np_until = time.monotonic() + NOW_POP_SECS
        self.dirty = True

    def now_popped(self):
        return self.playing_now() and time.monotonic() < self.np_until

    def press_home(self, name, repeat):
        if not repeat and self.press_lobby(name):      # (X, SELECT, L, R: your others' games, to watch or join)
            return None
        apps = self.home_apps()
        n = len(apps)
        cols = self.home_columns(n)
        sel = self.home_sel
        if name in ("left", "right"):
            sel = (sel + (1 if name == "right" else -1)) % n
        elif name in ("up", "down"):                   # the nearest icon in the row above or below
            slots = home_layout(n, cols)
            r, c = slots[sel]
            row = [k for k, (rr, _) in enumerate(slots) if rr == r + (1 if name == "down" else -1)]
            if row:
                sel = min(row, key=lambda k: abs(slots[k][1] - c))
        elif name == "a" and not repeat:
            return self.open_app(apps[sel][1])
        elif name == "start" and not repeat and self.playing_now():
            self.view, self.now_from = "now", "home"
        elif name == "y" and not repeat:               # (here only: B is back everywhere else)
            return "exit"
        self.home_sel = sel
        self.dirty = True
        return None

    def open_app(self, i):
        self.tab = i
        self.view = "list"
        self.load_tab(i)
        self.dirty = True
        return None

    def go_home(self):
        """B from an app: back to the icons, with that app picked."""
        ttype = self.tab_type()
        if ttype == "camera":
            self.camera.stop()
        elif ttype == "finance":
            self.fin_stop()
            self.fin_close()
        elif ttype == "remote":
            self.hass.stop()
            self.remote_more = None
        elif ttype == "lights":
            self.lights_close()
        elif ttype == "pihole":
            self.pihole_close()
        self.confirm = (None, 0.0)
        self.picking = None
        self.friend_more = None
        self.coder_help = False
        self.bot_settings = False
        self.sim_close()
        self.set_page = "root"
        self.wx_menu = None
        self.ha_menu = None
        self.cam_menu = None
        self.games_q = None                            # (finding a game: not any more)
        self.games_dir = None                          # (the Games tab's folder: shut)
        if ttype == "radio" and self.radio_stack:
            self.radio_stack = []
            self.status[self.tab] = None
        for k in list(self.chan_stack):                # home: the Cartoons folders close
            self.chan_stack[k] = []
        apps = self.home_apps()
        self.home_sel = next((k for k, a in enumerate(apps) if a[1] == self.strip_tab()), self.home_sel)
        self.view = "home"
        self.dirty = True

    # -- its three looks (Settings > Home screen style) -------------------------
    #   Bright: bold, the time and the weather big, bright tiles with white glyphs, an accent ring round the app
    #           picked
    #   Glass: thin type, tiles of tinted glass with grey glyphs, the app picked lit and glowing
    #   Cards: dark cards, each with a coloured glyph and its name, an accent line by the time, the weather
    #          between thin lines
    # Over a pale background (Settings > Background: Sky, Peach...), the words go dark, Glass's tiles are light
    # glass with dark glyphs, and Cards' cards are white.
    HOME_X = 36                                      # Glass's margins, left and right
    TILE = 74                                        # Glass's tile
    HOME_TOP = 14                                    # the time's top (no status bar here)
    LABEL_DY = 15                                    # Glass: an app's name, this far under its tile (its middle)
    HOME_GEOMETRY = {    # a tile; the first row's top; a row (a tile and its name); its name's middle under it
        "Bright": (72, 116, 104, 14),
        "Glass": (74, 116, 105, 15),
        "Cards": (92, 112, 104, -16),            # (a card 92 high, as wide as fits; its name inside it, at the foot)
    }
    CARD_X, CARD_GAP, CARD_R, GLYPH = 22, 14, 20, 52   # Cards: its margins, the gap between cards, their corners'
                                                      # roundness, a glyph's size
    CARD_GAP_SHARE = 0.125                           # Cards: the gap between cards, at least this much of a card's
                                                      # width (and the rows' own gap): a wider screen's further apart
    CARD_WIDEST = 1.75                               # ...and a card never wider than this against its height
    CARDS_WIDE = 2.1                                 # a screen this many times wider than high (an ultrawide, 21:9):
    WIDE_CARDS = (118, 118, 26)                      # Cards in two rows (if 9 across do), taller: a card this high, the
                                                      # first row's top, the gap between the rows

    def home_style(self):
        style = self.setting("home_style")
        return style if style in self.HOME_GEOMETRY else "Glass"

    def home_geometry(self):
        """(a tile, the first row's top, a row, its name's middle under it). On a taller screen than the GPi
        Case's (a monitor's 540 lines), the rows lower down and further apart: the room shared out. Cards on an
        ultrawide: two rows of taller cards (cards_two_rows()), their glyph and name in the middle of them."""
        tile, top, row, dy = self.HOME_GEOMETRY[self.home_style()]
        if self.cards_two_rows():
            high, top, gap = self.WIDE_CARDS
            tile, row, dy = high, high + gap, dy - (high - tile) // 2
        extra = max(0, (self.fb.h if self.fb else 480) - 480)
        return tile, top + extra // 3, row + extra // 4, dy

    def cards_two_rows(self, n=None):
        """Cards on an ultrawide (21:9): its apps in two rows, as many across as that takes (up to 9), not three
        rows of cards drawn out wide."""
        if self.home_style() != "Cards" or not self.fb or self.fb.w < self.CARDS_WIDE * self.fb.h:
            return False
        return -(-(len(self.home_apps()) if n is None else n) // 2) <= 9

    def home_columns(self, n):
        """Icons across, for n of them: as home_cols() has it, or Cards' two rows on an ultrawide."""
        return -(-n // 2) if self.cards_two_rows(n) else home_cols(n)

    def home_icon(self, name, lit=False):
        style, s, pale = self.home_style(), scale(), self.home_pale()
        face = self.games_face() if name == "Games" else None
        key = (style, name, lit, s, face, pale and style != "Bright")
        if key not in self.icons:                      # (as finely as the screen's drawn: fine.py)
            size = self.home_geometry()[0]
            self.icons[key] = made_fine(draw_glyph(name, self.GLYPH * s, face=face, pale=pale) if style == "Cards" else
                                        draw_bright_icon(name, size * s, face=face) if style == "Bright" else
                                        draw_icon(name, size * s, lit=lit, fine=s, face=face, pale=pale))
        return self.icons[key]

    def games_face(self):
        """The console the Games icon shows now: one you have games for (None: you have none, and it's the
        controller, as ever)."""
        return getattr(self, "games_face_key", None)

    def games_face_next(self):
        """You've come to the home screen (not just had it drawn again): the Games icon moves on to the next console
        you have games for, in the Games list's order (the first time, any of them)."""
        have = self.games_systems()
        was = self.games_face()
        self.games_face_key = (have[(have.index(was) + 1) % len(have)] if was in have
                               else random.choice(have) if have else None)

    def home_wall(self):
        """The home screen's background, made again only when it changes."""
        s = scale()
        fields = getattr(self.fb, "fields", None)          # (a 16-bit screen: its few steps, dithered to)
        depth = tuple(ln for _, ln in fields) if getattr(self.fb, "bpp", 32) == 16 and fields else 8
        key = (self.setting("wallpaper"), self.setting("picture"), self.fb.w, self.fb.h, s, depth)
        if self.wall[0] != key:
            from PIL import Image
            pic = wallpaper(key[0], (self.fb.w * s, self.fb.h * s), key[1], depth)
            tones = pic.resize((1, self.TONES), Image.BOX)   # (its colour, about, from its top to its foot)
            self.wall_tones = [tones.getpixel((0, k)) for k in range(self.TONES)]
            self.wall = (key, made_fine(pic))
        return self.wall[1]

    TONES = 12                                       # how many of them, down it

    def home_tone(self, y):
        """The background's colour, about, this far down the screen."""
        tones = self.wall_tones or [(11, 14, 19)]
        return tones[max(0, min(len(tones) - 1, int(y * len(tones) / max(self.fb.h, 1))))]

    def home_ink(self):
        """The home screen's words over its background: light, as ever; white over a strong colour; dark over a
        pale one (INK)."""
        name = self.setting("wallpaper")
        return INK[wall_ink(name) if name != "Picture" or not self.setting("picture") else "light"]

    def home_pale(self):
        """A pale background: Glass's tiles are light glass over it, Cards' cards white."""
        return self.home_ink() is INK["dark"]

    def home_say(self, d, xy, text, font, fill, anchor="la", ink=None):
        """Words on the home screen's background. Over a strong colour: a soft shadow under them, the background's
        colour there made darker, so they read."""
        ink = ink or self.home_ink()
        if ink["shade"]:
            d.text((xy[0], xy[1] + 1), text, font=font, fill=mix(self.home_tone(xy[1]), (0, 0, 0), ink["shade"]),
                   anchor=anchor)
        d.text(xy, text, font=font, fill=fill, anchor=anchor)

    def home_line(self, ink=None, y=None):
        """A thin line on the background (along the bottom, unless y says): a little of its ink in its colour
        there. (A dark background's: as ever.)"""
        ink = ink or self.home_ink()
        tone = self.home_tone(self.fb.h - 1 if y is None else y)
        return LINE if max(tone) < 48 and ink is INK["light"] else mix(tone, ink["text"], 0.2)

    def home_accent(self, ink=None):
        """The accent colour, for what's drawn on the background: itself over a dark one, white over a strong
        colour, darker over a pale one (it's a light colour)."""
        ink = ink or self.home_ink()
        if ink is INK["light"]:
            return ACCENT
        return (255, 255, 255) if ink is INK["white"] else mix(ACCENT, (0, 0, 0), 0.45)

    def home_foot_ink(self, ink=None):
        """The colours for the buttons along the bottom (draw.py's footer), on the background."""
        ink = ink or self.home_ink()
        shadow = mix(self.home_tone(self.fb.h - 1), (0, 0, 0), ink["shade"]) if ink["shade"] else None
        return dict(ink, line=self.home_line(ink), shadow=shadow)

    def home_canvas(self):
        """A fresh copy of the home screen's background."""
        from ..fine import ImageDraw
        img = self.home_wall().copy()
        return img, ImageDraw.Draw(img)

    def home_pitch(self, cols):
        """How far apart the columns are."""
        W, style = self.fb.w, self.home_style()
        if style == "Bright":
            return (W - 20) / cols
        if style == "Cards":
            _, wide, gap = self.card_grid(cols)
            return wide + gap
        return (W - 2 * self.HOME_X - self.TILE) / max(cols - 1, 1)   # (the first tile on the left margin, the last
                                                                        # on the right: the time and weather's)

    def card_grid(self, cols):
        """Cards across the screen: (the first one's left, a card's width, the gap between them). As wide as fits,
        the gap at least CARD_GAP, the rows' own gap and CARD_GAP_SHARE of a card (the GPi Case's: 108 wide, 14
        apart; a TV's further apart, as its rows are); never wider than CARD_WIDEST of their height, the room left
        either side of them all."""
        tile, _, row, _ = self.home_geometry()
        room, gap = self.fb.w - 2 * self.CARD_X, max(self.CARD_GAP, row - tile)
        wide = (room - (cols - 1) * gap) / cols
        if self.CARD_GAP_SHARE * wide > gap:
            wide = room / (cols + (cols - 1) * self.CARD_GAP_SHARE)
            gap = self.CARD_GAP_SHARE * wide
        wide = min(wide, self.CARD_WIDEST * tile)
        return (self.fb.w - cols * wide - (cols - 1) * gap) / 2, wide, gap

    def card_box(self, k, slots, cols, first):
        """Where app k's tile is: (x0, y0, x1, y1)."""
        style = self.home_style()
        tile, top, row, _ = self.home_geometry()
        r, c = slots[k]
        pitch = self.home_pitch(cols)
        if style == "Bright":
            cx = 10 + (c + 0.5) * pitch
        else:
            cx = self.HOME_X + tile / 2 + c * pitch
        if style == "Cards":                          # (cards: as wide as fits, card_grid())
            left, wide, _ = self.card_grid(cols)
            x0 = left + c * pitch
            return x0, top + (r - first) * row, x0 + wide, top + (r - first) * row + tile
        x0, y0 = cx - tile / 2, top + (r - first) * row
        return x0, y0, x0 + tile, y0 + tile

    def home_rows_fit(self):
        tile, top, row, dy = self.home_geometry()
        return max(1, (self.fb.h - self.FOOTER - top - tile - 2 * max(dy, 0)) // row + 1)

    def home_glow(self, name, kind):
        """Glass: a soft light round a tile (the picked one: in its colour) or a shadow under it, made once. (A
        lighter shadow over a pale background.)"""
        from ..fine import Image, ImageDraw
        from PIL import ImageFilter
        face = self.games_face() if name == "Games" else None
        pale = self.home_pale()
        key = ("glow", name if kind == "glow" else None, kind, self.TILE, scale(), face, pale)
        if key not in self.icons:
            pad = 26 if pale else 14                   # (a pale background shows where it stops: further out)
            im = Image.new("RGBA", (self.TILE + 2 * pad, self.TILE + 2 * pad), (0, 0, 0, 0))
            colour = tile_tint(name, face) + (150,) if kind == "glow" else (0, 0, 0, 56 if pale else 120)
            ImageDraw.Draw(im).rounded_rectangle((pad, pad, pad + self.TILE, pad + self.TILE),
                                                 radius=int(self.TILE * 0.23), fill=colour)
            self.icons[key] = (im.filter(ImageFilter.GaussianBlur(7 if kind == "glow" else 5)), pad)
        return self.icons[key]

    def home_card(self, d, img, name, box, picked, pitch):
        """One app: its tile, and its name under it, the picked one marked as its look has it."""
        F, style, ink = self.fonts, self.home_style(), self.home_ink()
        x0, y0, x1, y1 = box
        dy = self.home_geometry()[3]
        room = pitch - 8
        if style == "Cards":                         # its glyph on the card, its name at the card's foot
            pale = self.home_pale()
            if picked:
                d.rounded_rectangle((x0 - 1, y0 - 1, x1 + 1, y1 + 1), radius=self.CARD_R + 1,
                                    fill=(255, 255, 255) if pale else CARD_PICKED,
                                    outline=self.home_accent(ink) if pale else ACCENT, width=2)
            glyph = self.home_icon(name)
            lift = (y1 - y0 - self.HOME_GEOMETRY["Cards"][0]) // 2   # (a taller card: its glyph lower, its name
            img.paste(glyph, (int((x0 + x1 - self.GLYPH) / 2), int(y0 + 11 + lift)), glyph)   # higher: in the middle)
            label = self.fit(d, HOME_LABELS.get(name, name), F["home4_label"], x1 - x0 - 6)
            d.text(((x0 + x1) / 2, y1 + dy), label, font=F["home4_label"],
                   fill=(ink["text"] if picked else ink["label"]) if pale else TEXT if picked else LABEL, anchor="mm")
            return
        if picked:                                     # (its name, as drawn on the grid unpicked: gone)
            cx, ly = (x0 + x1) / 2, y1 + dy
            strip = tuple(int(v) for v in (cx - pitch / 2, ly - 11, cx + pitch / 2, ly + 12))
            patch = self.wall[1].crop(strip)
            if style == "Glass":                       # (the tiles' shadows across it, as on the grid: none cut
                shade, pad = self.home_glow(None, "shadow")   # short where the name was, on a bright background)
                for bx, by in self.home_tiles:
                    at = (bx - pad - strip[0], by - pad + 3 - strip[1])
                    if -shade.size[0] < at[0] < patch.size[0] and -shade.size[1] < at[1] < patch.size[1]:
                        patch.paste(shade, at, shade)
            img.paste(patch, strip[:2])
        if style == "Bright":
            if picked:
                d.rounded_rectangle((x0 - 6, y0 - 6, x1 + 6, y1 + 6), radius=24, outline=self.home_accent(ink),
                                    width=3)
            tile = self.home_icon(name)
            img.paste(tile, (int(x0), int(y0)), tile)
            font = F["home1_label_b"] if picked and d.textlength(name, font=F["home1_label_b"]) <= room \
                else F["home_label"]
            label = self.fit(d, name, font, room)
            if ink is INK["light"]:                    # (a dark background: a shadow under its name, as ever)
                d.text(((x0 + x1) / 2 + 1, y1 + dy + 1), label, font=font, fill=(0, 0, 0), anchor="mm")
            self.home_say(d, ((x0 + x1) / 2, y1 + dy), label, font, ink["text"] if picked else ink["label"], "mm", ink)
            return
        if picked and style == "Glass":
            glow, pad = self.home_glow(name, "glow")
            img.paste(glow, (int(x0) - pad, int(y0) - pad), glow)
        tile = self.home_icon(name, picked)
        img.paste(tile, (int(x0), int(y0)), tile)
        font, fill = F["home_label"], (ink["text"] if picked else ink["label"])
        label = name if d.textlength(name, font=font) <= room else HOME_LABELS.get(name, name)
        self.home_say(d, ((x0 + x1) / 2, y1 + dy), self.fit(d, label, font, room), font, fill, "mm", ink)

    def home_grid(self, apps, cols, first, rows_fit):
        """The background with every tile on it, unpicked: kept until something about it changes."""
        from ..fine import ImageDraw
        style = self.home_style()
        key = (style, self.wall[0], tuple(a for a, _ in apps), cols, first, rows_fit, self.fb.w, self.fb.h,
               self.games_face())
        if self.home_base[0] != key:
            base = self.wall[1].copy()
            bd = ImageDraw.Draw(base)
            slots = home_layout(len(apps), cols)
            if style == "Glass":
                shade, pad = self.home_glow(None, "shadow")
            shown = [(name, self.card_box(k, slots, cols, first)) for k, (name, _) in enumerate(apps)
                     if first <= slots[k][0] < first + rows_fit]
            self.home_tiles = [(int(box[0]), int(box[1])) for _, box in shown]   # (where each one's drawn)
            if style == "Cards":                     # the cards, a little see-through (white ones, over a pale
                from ..fine import Image             # background)
                layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
                ld = ImageDraw.Draw(layer)
                pale = self.home_pale()
                for _, box in shown:
                    ld.rounded_rectangle(box, radius=self.CARD_R, fill=(PALE_CARD + (206,)) if pale else CARD + (232,),
                                         outline=(PALE_CARD_LINE if pale else CARD_LINE) + (255,))
                base = base.convert("RGBA")
                base.alpha_composite(layer)
                base = base.convert("RGB")
                bd = ImageDraw.Draw(base)
            for name, box in shown:
                if style == "Glass":
                    base.paste(shade, (int(box[0]) - pad, int(box[1]) - pad + 3), shade)
                self.home_card(bd, base, name, box, False, self.home_pitch(cols))
            self.home_base = (key, base)
        img = self.home_base[1].copy()
        return img, ImageDraw.Draw(img)

    def home_wx_icon(self, img, sky, size, at):
        """The sky's icon, on the background. Over a pale one, a soft shadow behind it: its cloud is as pale."""
        icon = self.wx_icon(sky, size, pale=False)
        if self.home_pale():
            from ..fine import Image
            from PIL import ImageFilter
            key = ("wx_shade", sky, size, scale())
            if key not in self.icons:
                pad = 6
                shade = Image.new("RGBA", (size + 2 * pad, size + 2 * pad), (0, 0, 0, 0))
                shade.paste(Image.new("RGBA", (size, size), (40, 50, 70, 120)), (pad, pad), icon)
                self.icons[key] = (shade.filter(ImageFilter.GaussianBlur(2.5)), pad)
            shade, pad = self.icons[key]
            img.paste(shade, (int(at[0]) - pad, int(at[1]) - pad + 1), shade)
        img.paste(icon, (int(at[0]), int(at[1])), icon)

    def home_widget(self, img, d):
        """The top right of the home screen when nothing is playing: the temperature and the sky, and under them
        the weather in words and today's high and low."""
        F, W, style, ink = self.fonts, self.fb.w, self.home_style(), self.home_ink()
        wx = self.weather.data
        if not wx or not self.setting("location"):
            return
        today = (wx.get("days") or [{}])[0]
        hi, lo = self.deg(today.get("hi")), self.deg(today.get("lo"))
        temp, sky = self.deg(wx.get("temp")), wx_icon_name(wx.get("code"), wx.get("is_day", True))
        words = wx_words(wx.get("code"))[0]
        say = self.home_say
        if style == "Cards":                         # between thin lines: the sky, now, today's high and low
            hilo = f"{hi} / {lo}"
            words = self.fit(d, words, F["home4_small"], 150)
            x_hilo = W - 22 - d.textlength(hilo, font=F["home4_date"])
            line2 = x_hilo - 16
            x_tc = line2 - 16 - max(d.textlength(temp, font=F["home4_temp"]),
                                    d.textlength(words, font=F["home4_small"]))
            x_icon = x_tc - 10 - 52
            line1 = x_icon - 16
            line = CARD_LINE if ink is INK["light"] else self.home_line(ink, 60)
            d.line((line1, 30, line1, 92), fill=line, width=1)
            self.home_wx_icon(img, sky, 52, (x_icon, 34))
            say(d, (x_tc, 26), temp, F["home4_temp"], ink["text"], "la", ink)
            say(d, (x_tc, 80), words, F["home4_small"], ink["body"], "lm", ink)
            d.line((line2, 30, line2, 92), fill=line, width=1)
            say(d, (x_hilo, 80), hilo, F["home4_date"], co_mix(self.home_accent(ink), ink["text"], 0.35), "lm", ink)
        elif style == "Bright":
            self.home_wx_icon(img, sky, 64, (W - 24 - 64, 16))
            say(d, (W - 24 - 64 - 10, 68), temp, F["home1_clock"], ink["text"], "rs", ink)
            line = f"{words}  ·  {hi} / {lo}"
            say(d, (W - 24, 96), self.fit(d, line, F["home1_date"], 300), F["home1_date"], ink["body"], "rs", ink)
        else:
            x1 = W - self.HOME_X
            self.home_wx_icon(img, sky, 52, (x1 - 52, 21))
            say(d, (x1 - 52 - 14, 66), temp, F["wx_temp"], ink["text"], "rs", ink)
            tail = f"  ·  {hi} / {lo}"
            words = self.fit(d, words, F["home_date"], 300 - d.textlength(tail, font=F["home_date"]))
            say(d, (x1, 95), words + tail, F["home_date"], ink["date"], "rs", ink)

    def hour_min(self, hhmm):
        try:
            t = time.strptime(hhmm, "%H:%M")
        except ValueError:
            return hhmm
        return time.strftime("%H:%M" if self.setting("clock") == "24-hour" else "%-I:%M %p", t)

    def home_clock(self, d):
        """The time, big, and the date under it."""
        F, style, ink = self.fonts, self.home_style(), self.home_ink()
        t = time.localtime()
        hm = self.clock_text(t, ampm=False)
        twelve = self.setting("clock") != "24-hour"
        date = time.strftime("%A, %B ", t) + str(t.tm_mday)
        say = self.home_say
        if style == "Cards":                         # an accent line beside it, a little calendar by the date
            top = self.HOME_TOP
            d.rounded_rectangle((16, top + 8, 20, top + 84), radius=2, fill=self.home_accent(ink))
            say(d, (31, top + 50), hm, F["home4_clock"], ink["text"], "ls", ink)
            if twelve:
                say(d, (31 + d.textlength(hm, font=F["home4_clock"]) + 9, top + 34), time.strftime("%p", t),
                    F["home4_date"], ink["text"], "ls", ink)
            cy = top + 72
            d.rounded_rectangle((33, cy - 6, 47, cy + 8), radius=3, outline=ink["body"], width=2)
            d.line((33, cy - 1, 47, cy - 1), fill=ink["body"], width=2)
            for x in (37, 43):
                d.line((x, cy - 9, x, cy - 4), fill=ink["body"], width=2)
            say(d, (57, cy + 1), date, F["home4_date"], ink["body"], "lm", ink)
        elif style == "Bright":
            say(d, (23, 68), hm, F["home1_clock"], ink["text"], "ls", ink)
            if twelve:
                say(d, (23 + d.textlength(hm, font=F["home1_clock"]) + 9, 50), time.strftime("%p", t),
                    F["home1_ampm"], ink["body"], "ls", ink)
            say(d, (25, 96), date, F["home1_date"], ink["body"], "ls", ink)
        else:
            x = self.HOME_X - 2                        # (the figures' own margin)
            say(d, (x, 66), hm, F["home_clock"], ink["text"], "ls", ink)
            if twelve:
                say(d, (x + d.textlength(hm, font=F["home_clock"]) + 9, 47), time.strftime("%p", t),
                    F["home_ampm"], ink["text"], "ls", ink)
            say(d, (self.HOME_X, 95), date, F["home_date"], ink["date"], "ls", ink)

    def home_playing(self, img, d):
        """What's playing, top right, for a few seconds."""
        it = self.cur
        radio = self.kind == "radio"
        title = it["title"] if radio else (self.meta.get("title") or it["title"])
        sub = (self.meta.get("song") or it.get("sub") or "") if radio else (it.get("sub") or "")
        head = "PAUSED" if self.paused else "ON THE RADIO" if radio else "NOW PLAYING"
        self.home_panel(img, d, head, title, sub, "Radio" if radio else "Music")

    def home_lobby(self, img, d, e, n):
        """Another of yours playing a game, top right (while nothing's popped up there): whose, which, and with whom;
        a tap on it watches it (or joins it, for one that can't be watched)."""
        head, title, sub = self.lobby_words(e, n)
        box = self.home_panel(img, d, head.upper(), title, sub, "Games")
        if e["watch"] or e["join"]:
            self.tappable(box, "keys", "x" if e["watch"] else "select")

    def home_panel(self, img, d, head, title, sub, tile):
        """A card top right (what's playing, another's game): a few words over its title, and a line under it, in a
        tile's colour (Music's, Radio's, Games'). Its box. (Over a pale background: a light one, its words dark.)"""
        from ..fine import Image, ImageDraw
        F, W, style, ink, pale = self.fonts, self.fb.w, self.home_style(), self.home_ink(), self.home_pale()
        if style in ("Bright", "Cards"):           # a card
            x0, x1, y0 = W - 296, W - 20, 18 if style == "Bright" else self.HOME_TOP + 8
            if pale:
                d.rounded_rectangle((x0, y0, x1, y0 + 78), radius=14 if style == "Bright" else 12, fill=PALE_CARD,
                                    outline=PALE_CARD_LINE)
            elif style == "Bright":
                d.rounded_rectangle((x0, y0, x1, y0 + 78), radius=14, fill=ROW)
            else:
                d.rounded_rectangle((x0, y0, x1, y0 + 78), radius=12, fill=CARD, outline=CARD_LINE)
            d.text((x0 + 18, y0 + 17), self.fit(d, head, F["key"], x1 - x0 - 36), font=F["key"],
                   fill=self.home_accent(ink) if pale else ACCENT, anchor="lm")
            d.text((x0 + 18, y0 + 42), self.fit(d, title, F["row_b"], x1 - x0 - 36), font=F["row_b"],
                   fill=ink["text"] if pale else TEXT, anchor="lm")
            if sub:
                d.text((x0 + 18, y0 + 63), self.fit(d, sub, F["small"], x1 - x0 - 36), font=F["small"],
                       fill=ink["body"] if pale else BODY, anchor="lm")
            return x0, y0, x1, y0 + 78
        x0, y0, x1, y1 = W - self.HOME_X - 280, 20, W - self.HOME_X, 98   # a panel like the tiles, in Music's or
        tint = tile_tint(tile)                                             # Radio's colour (or Games')
        key = ("panel", tint, x1 - x0, y1 - y0, pale)
        if key not in self.icons:
            w, h = int(x1 - x0), int(y1 - y0)
            grad = Image.linear_gradient("L").resize((w, h))
            foot, top, edge = mix(TILE_BOTTOM, tint, 0.2), mix(TILE_TOP, tint, 0.32), mix((66, 72, 84), tint, 0.5)
            if pale:                                   # (light glass, as the tiles are over it)
                foot, top = mix(PALE_BOTTOM, tint, 0.3), mix(PALE_TOP, tint, 0.12)
                edge = mix((255, 255, 255), tint, 0.45)
            panel = Image.composite(Image.new("RGBA", (w, h), foot + (255,)), Image.new("RGBA", (w, h), top + (255,)),
                                    grad)
            shape = Image.new("L", (w, h), 0)
            ImageDraw.Draw(shape).rounded_rectangle((0, 0, w - 1, h - 1), radius=16, fill=255)
            ImageDraw.Draw(panel).rounded_rectangle((0, 0, w - 1, h - 1), radius=16, outline=edge + (255,), width=1)
            panel.putalpha(shape)
            shade = None
            if pale:                                   # (a soft shadow under it, as the light tiles have)
                from PIL import ImageFilter
                shade = Image.new("RGBA", (w + 28, h + 28), (0, 0, 0, 0))
                ImageDraw.Draw(shade).rounded_rectangle((14, 14, 14 + w, 14 + h), radius=16, fill=(0, 0, 0, 56))
                shade = shade.filter(ImageFilter.GaussianBlur(5))
            self.icons[key] = (panel, shade)
        panel, shade = self.icons[key]
        if shade is not None:
            img.paste(shade, (int(x0) - 14, int(y0) - 14 + 3), shade)
        img.paste(panel, (int(x0), int(y0)), panel)
        room = x1 - x0 - 36
        d.text((x0 + 18, y0 + 19), self.fit(d, head, F["home_pop_head"], room), font=F["home_pop_head"],
               fill=mix(tint, PALE_GLYPH, 0.4) if pale else mix(tint, (255, 255, 255), 0.45), anchor="lm")
        d.text((x0 + 18, y0 + 42), self.fit(d, title, F["home_pop_title"], room), font=F["home_pop_title"],
               fill=ink["text"] if pale else TEXT, anchor="lm")
        if sub:
            d.text((x0 + 18, y0 + 62), self.fit(d, sub, F["home_pop_sub"], room), font=F["home_pop_sub"],
                   fill=ink["body"] if pale else DATE, anchor="lm")
        return x0, y0, x1, y1

    def home_footer4(self, d, hints, note):
        """Cards's buttons along the bottom: rings round the letters, thin lines between them, and the app's line on
        the right with three little slants before it."""
        F, W, H, ink = self.fonts, self.fb.w, self.fb.h, self.home_ink()
        light = ink is INK["light"]
        y, x = H - self.FOOTER // 2, 20
        say, small = self.home_say, F["home4_small"]
        for n, (k, label) in enumerate(hints):
            if n:
                d.line((x - 9, y - 9, x - 9, y + 9), fill=LINE if light else self.home_line(ink), width=1)
            x0, w = x, self.key_w(d, k)
            if len(k) == 1:
                d.ellipse((x, y - 11, x + w, y + 11), outline=ink["ring"], width=2)
            else:
                d.rounded_rectangle((x, y - 11, x + w, y + 11), radius=11, outline=ink["ring"], width=2)
            say(d, (x + w / 2, y), k, F["key"], ink["text"], "mm", ink)
            x += w + 7
            say(d, (x, y), label, small, ink["body"], "lm", ink)
            x += d.textlength(label, font=small) + 18
            self.tap_hint(x0 - 9, x - 9, H - self.FOOTER, H, k)
        if note and x + d.textlength(note, font=small) < W - 20:
            say(d, (W - 20, y), note, small, ink["muted"] if light else ink["body"], "rm", ink)
            if x + 34 + d.textlength(note, font=small) < W - 20:   # (a long line goes without them)
                mx = W - 20 - d.textlength(note, font=small) - 14
                for j in range(3):
                    sx = mx - (2 - j) * 9
                    d.polygon([(sx - 7, y + 4), (sx - 3, y - 4), (sx + 2, y - 4), (sx - 2, y + 4)],
                              fill=self.home_accent(ink))
        self.msg_pill(d)

    def render_home(self):
        F = self.fonts
        W, H = self.fb.w, self.fb.h
        style = self.home_style()
        apps = self.home_apps()
        n = len(apps)
        cols = self.home_columns(n)
        sel = self.home_sel % n
        rows_fit = self.home_rows_fit()
        first = max(0, min(sel // cols - rows_fit + 1, (n - 1) // cols - rows_fit + 1))
        self.home_wall()
        img, d = self.home_grid(apps, cols, first, rows_fit)

        self.home_clock(d)
        lobby = None if self.now_popped() else self.lobby_now()
        if self.now_popped():                          # what's playing, top right, for a few seconds
            self.home_playing(img, d)
        elif lobby is not None:                        # (another of yours playing a game: to watch, or join)
            self.home_lobby(img, d, *lobby)
        else:                                          # (the weather, once there's a place for it)
            self.home_widget(img, d)

        # the picked app, marked; a dot on what's playing
        slots = home_layout(n, cols)
        self.home_card(d, img, apps[sel][0], self.card_box(sel, slots, cols, first), True, self.home_pitch(cols))
        pitch, below = self.home_pitch(cols), max(self.home_geometry()[3], 0) + 12   # (each app: its tile and its name)
        for k in range(n):
            if first <= slots[k][0] < first + rows_fit:
                x0, y0, x1, y1 = self.card_box(k, slots, cols, first)
                cx = (x0 + x1) / 2
                self.tappable((min(x0, cx - pitch / 2 + 2), y0 - 8, max(x1, cx + pitch / 2 - 2), y1 + below),
                              "sel", "attr", "home_sel", k)
        playing = {"audio": "Music", "radio": "Radio"}.get(self.kind) if self.playing_now() else None
        for k, (name, _) in enumerate(apps):
            if name == playing and first <= slots[k][0] < first + rows_fit:
                x0, y0, x1, y1 = self.card_box(k, slots, cols, first)
                if style == "Bright":
                    d.ellipse((x1 - 13, y0 - 3, x1 + 5, y0 + 15), fill=BG)
                    d.ellipse((x1 - 10, y0, x1 + 2, y0 + 12), fill=ACCENT)
                elif style == "Cards":
                    d.ellipse((x1 - 22, y0 + 10, x1 - 10, y0 + 22), fill=ACCENT)
                else:
                    d.ellipse((x1 - 10, y0 - 4, x1 + 4, y0 + 10), fill=ACCENT, outline=BG, width=2)
        if (n - 1) // cols >= first + rows_fit:       # more below
            d.text((W / 2, H - self.FOOTER - 2), "▼", font=F["small"], fill=self.home_ink()["muted"], anchor="mm")

        hints = [("A", "Open")]
        if self.now_popped():                          # (START opens it any time; said while it's up)
            hints.append(("START", "Now playing"))
        hints += self.lobby_hints()                    # (X: watch another's game; SELECT: join it)
        hints.append(("Y", "Terminal"))
        name_sel, tab_sel = apps[sel]
        about = HOME_ICONS.get(name_sel, (None, ""))[1]
        if not about and tab_sel is not None:
            about = LIBRARY[tab_sel].get("about", "")
        if style == "Cards":
            self.home_footer4(d, hints, about)
        else:                                          # (straight on the background, in its ink)
            self.footer(d, hints, right=about, plain=True, ink=self.home_foot_ink())
        self.fb.show(img)
