"""Apps > LED backlight (pitato/glow.py): an 8x8 grid of WS2812B LEDs behind the TV (or a strip of them round its
edges), on this Pi's GPIO 10 (SPI), lit by the games and music of whichever of your Pietatos it follows (this one too),
and in a colour of your own the rest of the time (its page: a picture of the LEDs as they're lit, backlight.py; the
web page's Library has it too). And the other way: this one's games and music lighting your grids, wherever they are,
and the ESP32 boards on your network (esp32/pietato_led: found by themselves; the web page lists them, and gives each
a colour of its own, which the board keeps). A game's colours come from its emulator
(told where they go: glow ADDRESS:PORT...); music's beats from its player, when one of your grids or boards wants them:
a song or a station then plays through party mode's player (party.py: it knows when each bit of it is heard), on its
own, as if it were a party."""
import re
import secrets
import threading
import time
import urllib.parse

from ..config import SETTINGS_DEFAULT
from ..glow import (ANY, colour_of, COLOURS, CONFIG_TXT, GLOW_PORT, GlowOut, Grid, LAMP_PORT, Lamps, NOBODY, PI_MODEL,
                    spi_lines, SPI_DEV, STARTS, Strip, STRIP_LEAST, STRIP_MOST, strip_points, target_words,
                    THIS_ONE, turn_spi_on)
from ..handheld import is_handheld
from ..library import LISTEN_KINDS
from ..party import PartyProc, RelayServer
from ..screen import web_late
from ..system import is_pc, read_file, run_out
from ..theme import ACCENT, ACCENTS, BODY, co_mix, LINE, MUTED, ROW, TEXT

GLOW_BRIGHT = ["10%", "25%", "50%", "100%"]
GLOW_SHAPES = ["8x8 grid", "Strip"]
GLOW_COUNTS = [str(n) for n in range(STRIP_LEAST, STRIP_MOST + 1)]
GLOW_ROWS = [("glow_on", "LEDs", ["Off", "On"]), ("glow_colour", "Colour", [n for n, _ in COLOURS]),
             ("glow_bright", "Brightness", GLOW_BRIGHT), ("glow_follow", "Follows", None),
             ("glow_beat", "Pulse to music", ["On", "Off"]), ("glow_shape", "Shape", GLOW_SHAPES),
             ("glow_turn", "Turn", ["0°", "90°", "180°", "270°"]), ("glow_mirror", "Mirror", ["On", "Off"]),
             ("glow_wiring", "Wiring", ["Rows", "Zigzag"]),
             ("glow_count", "LEDs on it", GLOW_COUNTS), ("glow_start", "Starts at", list(STARTS)),
             ("glow_way", "Goes", ["Clockwise", "Anticlockwise"]), ("glow_bottom", "Along the bottom", ["Yes", "No"])]
GLOW_KEYS = tuple(k for k, _, _ in GLOW_ROWS)
GLOW_GRID_ONLY = ("glow_turn", "glow_mirror", "glow_wiring")
GLOW_STRIP_ONLY = ("glow_count", "glow_start", "glow_way", "glow_bottom")
GLOW_CARD = ("glow_follow", "glow_beat", "glow_shape") + GLOW_GRID_ONLY + GLOW_STRIP_ONLY + ("glow_test",
                                                                                             "glow_reboot")
                             # START's card on its page (its buttons do the rest: on, its colour, how bright)
GLOW_SWATCH = {"Off": "linear-gradient(135deg, #23272e 44%, #8b95a3 44% 56%, #23272e 56%)",
               "Rainbow": "conic-gradient(#ff3b30, #ffcc00, #34c759, #00c7be, #007aff, #af52de, #ff2d55, #ff3b30)"}
                             # (the web page's swatches for what isn't one colour)
LAMP_COLOURS = [(n, "#%02x%02x%02x" % c) for n, c in COLOURS if isinstance(c, tuple)]
                             # an ESP32 board's own colour, on the web page: these, or any other
GLOW_LOOK = 2.0              # seconds between looks for your grids (and where a game's colours go)
GLOW_MUSIC = 0.5             # seconds between music's colour, said to your grids (a beat between)
GLOW_LEAD = 0.8              # seconds from a song being started to its playing, on party mode's player
GLOW_SOON = 0.05             # ...and from A to its pausing there
GLOW_QUIET = 3.0             # seconds with no station on that player: the one passed through here let go of
NAMED_KEEP = 10.0            # seconds an address's name is kept (the grid asks it for every packet)


class GlowScreen:
    """Apps > LED backlight, the grid it lights, and this one's games and music lighting your grids."""
    glow_grid = None         # this Pi's LED grid, lit (glow.Grid)
    glow_lamps = None        # lights of your own on the network, found (an ESP32's LED: glow.Lamps)
    glow_out = None          # this one's music, to your grids (glow.GlowOut)
    glow_station = None      # a station on party mode's player, for its beat: {"token", "server", "relay", "song", "quiet"}
    glow_note = ""           # why the grid isn't lit ("" when it is, or it's off)
    glow_restart = False     # SPI turned on in config.txt: the Pi needs restarting
    glow_seen = glow_music_at = 0.0
    glow_to = ()             # your grids (and this one's), and the lights of your own: [(address, port)]
    glow_to_lamps = ()       # ...the lights among them
    glow_names = None        # address -> (name, when looked up)

    # -- what it is --------------------------------------------------------------------------------------------------
    def glow_can(self):
        """A grid can go on this one: a Pi (not a PC or a handheld), and not in a GPi Case (its screen has the pins)."""
        return "Raspberry Pi" in read_file(PI_MODEL) and not is_pc() and not is_handheld() \
            and not getattr(self, "case", None)

    def glow_setting(self, key):
        v = self.setting(key)
        return v if v is not None else SETTINGS_DEFAULT.get(key)

    def glow_follows(self):
        """Who the grid follows now: ANY, THIS_ONE, or one of yours by name (one that's not on now: still its name)."""
        return self.glow_setting("glow_follow") or ANY

    def glow_follow_choices(self):
        names = [h for _, h in self.saves_peers()]
        cur = self.glow_follows()
        if cur not in (ANY, THIS_ONE, NOBODY) and cur not in names:
            names.append(cur)
        return [ANY] + names + [THIS_ONE, NOBODY]

    def glow_colour_name(self):
        """Its own colour's name (Off: dark, with nothing lighting it)."""
        name = self.glow_setting("glow_colour")
        return name if any(name == n for n, _ in COLOURS) else "Off"

    def glow_strip(self):
        """It's a strip round the TV (not the grid)."""
        return self.glow_setting("glow_shape") == "Strip"

    def glow_rows(self):
        skip = GLOW_GRID_ONLY if self.glow_strip() else GLOW_STRIP_ONLY   # (a grid's turn and wiring, or a strip's)
        rows = [(k, label, self.glow_follow_choices() if k == "glow_follow" else choices)
                for k, label, choices in GLOW_ROWS if k not in skip]
        rows.append(("glow_test", "Show which way is up", None))
        if self.glow_restart:
            rows.append(("glow_reboot", "Restart the Pi now", None))
        return rows

    def glow_value(self, key):
        if key == "glow_follow":
            return self.glow_follows()
        if key == "glow_colour":
            return self.glow_colour_name()
        if key == "glow_count":
            return str(self.glow_count())
        if key in ("glow_test", "glow_reboot"):
            return ""
        return self.glow_setting(key) or ""

    def glow_status(self):
        """A few words on the grid (the web page's Library has them)."""
        if self.glow_setting("glow_on") != "On":
            return "Off. Wire its DIN to GPIO 10 (pin 19)"
        if self.glow_note:
            return self.glow_note
        g = self.glow_grid
        if g is None:
            return ""
        src = g.now_following()
        if src is not None:
            return "Lit by " + (self.glow_named(src) or src)
        colour = self.glow_colour_name()
        if self.glow_follows() == NOBODY:
            return "Dark: no colour picked" if colour == "Off" else colour
        return "Waiting for a game or music" if colour == "Off" else colour + ", till a game or music comes on"

    def glow_lit_by(self):
        """What's lighting the grid now, in a word or two (beside its picture)."""
        g = self.glow_grid
        src = g.now_following() if g is not None else None
        if src is not None:
            return self.glow_named(src) or src
        return "Your colour" if g is not None and self.glow_colour_name() != "Off" else "Nothing"

    def glow_shade(self):
        """How bright its picture is drawn, for how bright the LEDs are (their light, as the eye sees it)."""
        try:
            bright = int((self.glow_setting("glow_bright") or "25%").rstrip("%")) / 100
        except ValueError:
            bright = 0.25
        return max(0.35, bright ** 0.45)

    # -- Apps > LED backlight -----------------------------------------------------------------------------------------
    def glow_page(self, s):
        """(sim_game's.) Its page as things are now: the grid for its picture, how bright, what's beside it, what it
        says at the foot of the picture, and its buttons."""
        on = self.glow_setting("glow_on") == "On"

        def short(v):
            return v if len(v) <= 13 else v[:12].rstrip() + "…"
        boards = len(self.lamps_on())                  # (ESP32 boards on your network, lit along with it)
        s.plain = not self.glow_can()
        s.blurb = "Your ESP32 boards' LEDs, lit by this Pietato's games and music." if s.plain else type(s).blurb
        if s.plain:                                    # (a GPi Case, a PC: no LEDs of its own. Just the boards, then)
            beat = self.glow_setting("glow_beat") != "Off"
            s.grid, s.points = None, None
            lamps = self.glow_lamps                    # (its picture: an LED for each, in its own colour)
            s.lamps = [(b["name"], b["leds"], b["colour"]) for b in (lamps.boards() if lamps is not None else [])]
            s.facts = [("ESP32 boards", str(boards) if boards else "None"),
                       ("Pulse to music", "On" if beat else "Off")]
            s.says = ("No LEDs here", "They go on a Pi behind the TV") if not boards else (
                "1 ESP32 board" if boards == 1 else f"{boards} ESP32 boards",
                "Lit by this Pietato's games and music" if beat else "Lit by this Pietato's games")
            s.own_hints = [("A", "Pulse off" if beat else "Pulse on")] if boards else [("B", "Back")]
            return
        s.grid, s.shade, s.points = self.glow_grid, self.glow_shade(), self.glow_points()
        s.facts = [("LEDs", "On" if on else "Off"),
                   ("Shape", f"Strip of {self.glow_count()}" if self.glow_strip() else "8x8 grid"),
                   ("Colour", self.glow_colour_name()), ("Brightness", self.glow_setting("glow_bright") or "25%"),
                   ("Follows", short(self.glow_follows())), ("Lit by", short(self.glow_lit_by()))]
        if boards:
            s.facts.append(("ESP32 boards", str(boards)))
        if not on:
            s.says = ("The LEDs are off", "A turns them on")
        elif self.glow_grid is None and self.glow_restart:
            s.says = ("Restart the Pi", "To light them: START, then Restart the Pi now")
        elif self.glow_grid is None:
            s.says = ("The LEDs can't light", self.glow_note or "Its SPI isn't there")
        else:
            s.says = None
        s.own_hints = [("A", "Turn off" if on else "Turn on"), ("◀▶", "Colour"), ("▲▼", "Brightness"),
                       ("START", "More")]

    def glow_points(self):
        """A strip's LEDs, where each is round the TV (for its picture, lit or not), or None: the grid."""
        if not self.glow_strip():
            return None
        want = (self.glow_count(), self.glow_setting("glow_start") or "Bottom left",
                self.glow_setting("glow_way") != "Anticlockwise", self.glow_setting("glow_bottom") != "No")
        got = getattr(self, "glow_points_at", None)
        if got is None or got[0] != want:
            got = self.glow_points_at = (want, strip_points(*want))
        return got[1]

    def press_glow(self, s, name, repeat):
        """Its page's buttons: A turns the LEDs on or off, ◀▶ go through its colours, ▲▼ make it brighter or dimmer
        (START has the rest). False: not one of these (as any sim's: screens/sims.py). On a Pietato with no LEDs of
        its own, A is your ESP32 boards' pulse to music, on or off, and that's all."""
        if not self.glow_can():
            if name in ("b", "l", "r"):
                return False
            if name == "a" and not repeat:
                if self.lamps_on():
                    new = "Off" if self.glow_setting("glow_beat") != "Off" else "On"
                    self.glow_pick("glow_beat", new)
                    self.toast(f"Pulse to music: {new.lower()}", 2)
                else:
                    self.toast("The LED backlight goes on a Pi behind the TV", 3)
                self.dirty = True
            return None
        if name not in ("a", "left", "right", "up", "down"):
            return False
        if repeat:
            return None
        if name == "a":
            self.glow_pick("glow_on", "Off" if self.glow_setting("glow_on") == "On" else "On")
            if self.glow_setting("glow_on") != "On":
                self.toast("LEDs off", 2)
            elif self.glow_grid is not None:
                self.toast("LEDs on", 2)
        elif name in ("left", "right"):
            names = [n for n, _ in COLOURS]
            new = names[(names.index(self.glow_colour_name()) + (1 if name == "right" else -1)) % len(names)]
            self.glow_pick("glow_colour", new)
            self.toast(f"Colour: {new}", 2)
        else:
            cur = self.glow_setting("glow_bright")
            i = GLOW_BRIGHT.index(cur) if cur in GLOW_BRIGHT else 1
            j = max(0, min(len(GLOW_BRIGHT) - 1, i + (1 if name == "up" else -1)))
            if j != i:
                self.glow_pick("glow_bright", GLOW_BRIGHT[j])
            self.toast(f"Brightness: {GLOW_BRIGHT[j]}", 2)
        self.dirty = True
        return None

    def glow_card_rows(self):
        """START's card on its page: (key, label, choices; None: A does it)."""
        return [r for r in self.glow_rows() if r[0] in GLOW_CARD]

    def press_glow_opts(self, s, name, repeat):
        """START's card: ▲▼ pick a row, ◀▶ change it, A shows which way is up (or restarts the Pi), B closes it."""
        rows = self.glow_card_rows()
        sel = self.sim_opts % len(rows)
        key, _, choices = rows[sel]
        if name in ("l", "r"):
            return "pass"                              # (switching apps closes it)
        if name in ("up", "down"):
            self.sim_opts = (sel + (1 if name == "down" else -1)) % len(rows)
        elif name in ("left", "right") and key == "glow_count":   # (held: five at a time)
            step = (5 if repeat else 1) * (1 if name == "right" else -1)
            n = max(STRIP_LEAST, min(STRIP_MOST, self.glow_count() + step))
            if n != self.glow_count():
                self.glow_pick(key, str(n))
        elif name in ("left", "right") and choices:
            if not repeat:
                cur = self.glow_value(key)
                i = choices.index(cur) if cur in choices else 0
                self.glow_pick(key, choices[(i + (1 if name == "right" else -1)) % len(choices)])
        elif name == "a" and key == "glow_test":
            if not repeat:
                self.glow_test()
        elif name == "a" and key == "glow_reboot":
            if not repeat:
                self.system_do("reboot")
        elif name in ("a", "b", "start"):
            if not repeat:
                self.sim_close()
        else:
            return None
        self.dirty = True
        return None

    def glow_card_hints(self):
        rows = self.glow_card_rows()
        key = rows[self.sim_opts % len(rows)][0]
        if key in ("glow_test", "glow_reboot"):
            return [("▲▼", "Choose"), ("A", "Show" if key == "glow_test" else "Restart"), ("B", "Done")]
        return [("▲▼", "Choose"), ("◀▶", "Change"), ("B", "Done")]

    def glow_card_key(self):
        """What START's card shows (drawn again when it changes)."""
        rows = self.glow_card_rows()
        return ("opts", "glow", self.sim_opts % len(rows), tuple((k, self.glow_value(k)) for k, _, _ in rows),
                self.sim_box(), self.sim_full(), ACCENT)

    def glow_opts_card(self, s):
        """START on its page: who it follows, pulsing to music, how it's put up and wired, which way is up (and a
        restart, once SPI's been turned on for it). Rows a little closer than other apps' cards: there are more."""
        from ..fine import Image, ImageDraw
        F = self.fonts
        rows = self.glow_card_rows()
        sel = self.sim_opts % len(rows)
        (bx0, by0, bx1, by1), _ = self.sim_box()
        if self.sim_full():
            by1 -= self.FOOTER                         # (the buttons show along the bottom meanwhile)
        W, top, rh = 404, 54, 36
        fit = max(3, min(len(rows), (by1 - by0 - top - 10) // rh))   # (more than fit: the ones round the picked one)
        first = max(0, min(sel - fit // 2, len(rows) - fit))
        H = top + rh * fit + 10
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((0, 0, W - 1, H - 1), radius=12, fill=ROW + (255,), outline=LINE + (255,))
        d.text((22, 29), "LED backlight", font=F["head"], fill=TEXT, anchor="lm")
        if fit < len(rows):                            # (more above or below: which way)
            d.text((W - 24, 29), ("▲ " if first else "") + ("▼" if first + fit < len(rows) else ""), font=F["small"],
                   fill=MUTED, anchor="rm")
        y = top
        for i, (key, label, choices) in list(enumerate(rows))[first:first + fit]:
            on, mid = i == sel, y + rh / 2
            if on:
                d.rounded_rectangle((10, y + 1, W - 11, y + rh - 1), radius=8, fill=co_mix(ROW, TEXT, 0.07))
                d.rectangle((10, y + 9, 13, y + rh - 9), fill=ACCENT)
            d.text((26, mid), label, font=F["small"], fill=TEXT if on else BODY, anchor="lm")
            x1, font = W - 24, F["small_b"] if on else F["small"]
            if choices:
                value = self.fit(d, str(self.glow_value(key)), font, 170)
                if on:
                    d.text((x1, mid), "▶", font=F["small"], fill=ACCENT, anchor="rm")
                    x1 -= 22
                d.text((x1, mid), value, font=font, fill=ACCENT if on else MUTED, anchor="rm")
                if on:
                    d.text((x1 - d.textlength(value, font=font) - 10, mid), "◀", font=F["small"], fill=ACCENT,
                           anchor="rm")
            elif on:
                d.text((x1, mid), "Press A", font=font, fill=ACCENT, anchor="rm")
            y += rh
        return img, ((bx0 + bx1 - W) // 2, max(by0, (by0 + by1 - H) // 2))

    def glow_test(self):
        if self.glow_grid is None:
            self.toast("Turn the LEDs on first", 3)
            return False
        self.glow_grid.test()
        self.toast("Red's the top, green's the left side", 4)
        return True

    def glow_pick(self, key, value):
        self.set_setting(key, value)
        if key == "glow_on":
            if value == "On":
                self.glow_start()
            else:
                self.glow_stop()
        else:
            self.glow_apply()
        self.share_news()                              # (your others: what it wants of them, now)
        self.glow_seen = 0.0

    # -- the grid ----------------------------------------------------------------------------------------------------
    def lamps_start(self):
        """Lights of your own on the network (an ESP32's LED) listened for, from here on: on any Pietato, with or
        without a grid of its own."""
        if self.glow_lamps is None:
            try:
                self.glow_lamps = Lamps(getattr(self, "lamps_port", LAMP_PORT))
            except OSError as ex:
                print(f"glow: lights on the network aren't listened for ({ex})", flush=True)

    def lamps_stop(self):
        lamps, self.glow_lamps = self.glow_lamps, None
        if lamps is not None:
            lamps.close()

    def lamps_on(self):
        """The lights there now: [(address, name, its LEDs)]."""
        return self.glow_lamps.on() if self.glow_lamps is not None else []

    def lamps_note(self):
        """How many of them, in a few words ("" for none)."""
        n = len(self.lamps_on())
        return "" if not n else "1 ESP32 board found" if n == 1 else f"{n} ESP32 boards found"

    def glow_shown(self):
        """The web page's Library has an LED backlight: a Pi that can have LEDs of its own, or any Pietato that's found
        an ESP32 board (since it started: so it doesn't come and go with them)."""
        lamps = self.glow_lamps
        return bool(lamps is not None and lamps.ever) or self.glow_can()

    def web_lamps(self):
        """The ESP32 boards there now, for the web page: each one's name, its LEDs, and its own colour ("#rrggbb"; ""
        for none: it takes what's playing; None for a board with the older sketch, which can't keep one)."""
        lamps = self.glow_lamps
        return [{"ip": b["ip"], "name": b["name"], "leds": b["leds"],
                 "colour": None if not b["keeps"] else "#%02x%02x%02x" % b["colour"] if b["colour"] else ""}
                for b in (lamps.boards() if lamps is not None else [])]

    def web_set_glow_lamp(self, value, cmd):
        """(The web page.) One of the ESP32 boards there now (its address), given a colour of its own ("#rrggbb"; "":
        none, so it takes what's playing); or just lit a moment, so you can tell which one it is (find)."""
        lamps = self.glow_lamps
        ip = value.get("ip") if isinstance(value, dict) else None
        board = next((b for b in (lamps.boards() if lamps is not None else []) if b["ip"] == ip), None)
        if board is None:
            return {"error": "That board isn't on now"}
        if not board["keeps"]:
            return {"error": "It needs the newer sketch first (esp32/pietato_led)"}
        port = getattr(self, "lamp_port", GLOW_PORT)   # (where a board takes its colours: the tests' own)
        if value.get("find") is True:                  # (the colour it has, told it again: it shows it a moment)
            if not lamps.set_colour(ip, board["colour"], port):
                return {"error": "It couldn't be told"}
            return {"ok": True, "said": f"{board['name']} lights up for a moment"}
        colour = value.get("colour")
        if not isinstance(colour, str) or not re.fullmatch(r"(#[0-9a-fA-F]{6})?", colour):
            return {"error": "That isn't a colour"}
        rgb = tuple(int(colour[k:k + 2], 16) for k in (1, 3, 5)) if colour else None
        if not lamps.set_colour(ip, rgb, port):
            return {"error": "It couldn't be told"}
        return {"ok": True}

    def glow_start(self):
        """The grid lit (Apps > LED backlight: on), if it can be: the Pi's SPI turned on first (in config.txt: then a
        restart), if it isn't."""
        if self.glow_grid is not None or self.glow_setting("glow_on") != "On" or not self.glow_can():
            return
        self.glow_note = ""
        spi = getattr(self, "glow_spi", SPI_DEV)
        try:
            self.glow_restart = self.glow_spi_on() or self.glow_restart
        except OSError as ex:
            print(f"glow: couldn't turn SPI on in config.txt ({ex})", flush=True)
        try:
            strip = Strip(spi)
        except OSError as ex:
            self.glow_note = "Restart the Pi to turn SPI on" if self.glow_restart else f"No SPI here ({ex.strerror})"
            print(f"glow: no LEDs: {ex}", flush=True)
            return
        try:
            self.glow_grid = Grid(strip, self.glow_named, port=getattr(self, "glow_port", GLOW_PORT))
        except OSError as ex:
            strip.close()
            self.glow_note = f"Its port's taken ({ex.strerror})"
            print(f"glow: no grid: {ex}", flush=True)
            return
        self.glow_shape_now = None                     # (a strip's shape, set on it: none yet)
        self.glow_apply()
        print(f"glow: the LEDs are on ({spi})", flush=True)

    def glow_spi_on(self):
        """The grid's lines in config.txt (SPI on, the core clock steady): True if they had to be put in."""
        path = next((p for p in getattr(self, "glow_configs", CONFIG_TXT) if read_file(p, None) is not None), None)
        if path is None:
            return False
        lines = spi_lines(read_file(PI_MODEL), run_out(["vcgencmd", "get_config", "core_freq"]))
        return turn_spi_on(path, lines)

    def glow_stop(self):
        g, self.glow_grid = self.glow_grid, None
        if g is not None:
            g.close()
            print("glow: the LED grid's off", flush=True)
        self.glow_note = ""

    def glow_apply(self):
        """The grid's settings, as they are now."""
        g = self.glow_grid
        if g is None:
            return
        g.bright = int((self.glow_setting("glow_bright") or "25%").rstrip("%")) / 100
        g.turn = int((self.glow_setting("glow_turn") or "0°").rstrip("°"))
        g.mirror = self.glow_setting("glow_mirror") == "On"
        g.zigzag = self.glow_setting("glow_wiring") == "Zigzag"
        g.beat = self.glow_setting("glow_beat") != "Off"
        g.follow = self.glow_follows()
        g.colour = colour_of(self.glow_colour_name())
        if self.glow_strip():
            want = (self.glow_count(), self.glow_setting("glow_start") or "Bottom left",
                    self.glow_setting("glow_way") != "Anticlockwise", self.glow_setting("glow_bottom") != "No")
            if getattr(self, "glow_shape_now", None) != want:
                g.set_strip(*want)
                self.glow_shape_now = want
        elif g.on_strip is not None:
            g.set_grid()
            self.glow_shape_now = None

    def glow_count(self):
        """A strip's LEDs."""
        try:
            return max(STRIP_LEAST, min(STRIP_MOST, int(self.glow_setting("glow_count") or 60)))
        except ValueError:
            return 60

    def glow_named(self, ip):
        """(The grid's listener.) Who's at an address: THIS_ONE (this Pi), one of yours (by name, as Settings shows
        them), or None: not one of yours."""
        if ip.startswith("127.") or ip == "::1":
            return THIS_ONE
        names = self.glow_names
        if names is None:
            names = self.glow_names = {}
        got = names.get(ip)
        now = time.monotonic()
        if got is None or now - got[1] > NAMED_KEEP:
            peers = self.saves_peers(ip)
            got = names[ip] = (peers[0][1] if peers else None, now)
        return got[0]

    def glow_beacon(self):
        """What this one's beacon says of its grid (to your others: so they light it), or None (following nobody: just
        its own colour, so nothing's said)."""
        g = self.glow_grid
        follow = self.glow_follows()
        if g is None or follow == NOBODY:
            return None
        return {"port": g.port, "follow": "" if follow == ANY else self.own_name() if follow == THIS_ONE else follow,
                "beat": self.glow_setting("glow_beat") != "Off"}

    # -- this one's games and music, lighting your grids -------------------------------------------------------------
    def glow_targets(self):
        """Your grids that are on (this one's too), and the lights of your own on the network: [(address, port)]."""
        out = []
        if self.glow_grid is not None and self.glow_follows() != NOBODY:
            out.append(("127.0.0.1", self.glow_grid.port))
        out += [(ip, GLOW_PORT) for ip, _, _ in self.lamps_on()]
        pie = getattr(self, "pie", None)
        if pie is None or self.setting("share") == "Off":
            return out
        names = dict(self.saves_peers())
        with pie.lock:
            for url, h in pie.heard.items():
                g = h.get("glow")
                if url in names and g:
                    host = urllib.parse.urlsplit(url).hostname
                    if host:
                        out.append((host, g["port"]))
        return out

    def glow_beats_wanted(self):
        """One of your grids (this one's too) follows this one and pulses to its music, or a light of your own's on the
        network (unless Pulse to music is off here): its music played on party mode's player, which knows when each
        beat's heard."""
        beat = self.glow_setting("glow_beat") != "Off"
        if self.glow_grid is not None and beat and self.glow_follows() in (ANY, THIS_ONE):
            return True
        if beat and self.lamps_on():
            return True
        pie = getattr(self, "pie", None)
        if pie is None or self.setting("share") == "Off":
            return False
        me = self.own_name()
        names = dict(self.saves_peers())
        with pie.lock:
            grids = [h.get("glow") for u, h in pie.heard.items() if u in names and h.get("glow")]
        return any(g["beat"] and (g["follow"] in ("", me) or g["follow"].startswith(me + " (")) for g in grids)

    def glow_look(self, now):
        if now - self.glow_seen >= GLOW_LOOK:
            self.glow_seen = now
            self.glow_to = self.glow_targets()
            self.glow_to_lamps = frozenset((ip, GLOW_PORT) for ip, _, _ in self.lamps_on())
            if self.glow_out is not None:
                self.glow_out.aim(self.glow_to, self.glow_to_lamps)

    def glow_game_tick(self, run, now):
        """(A game on.) Its emulator told where its colours go, when that changes."""
        self.glow_look(now)
        say = target_words(self.glow_to, self.glow_to_lamps)   # (the lights marked: a picture to a few at a time)
        if say != getattr(run, "glow_said", "-") and getattr(run, "state", "") in ("on", "paused") \
                and hasattr(run, "send"):
            if run.send(f"glow {say}") is not False:
                run.glow_said = say

    def glow_beat(self, t, strength):
        """(Party mode's player, as it plays.) A beat, heard at t (its clock: the leader's, in another's party)."""
        out = self.glow_out
        if out is None or not out.to:
            return
        if self.party is not None and not self.party.get("lead"):
            t -= self.party_clock() - time.monotonic()  # (the leader's clock, as this one's)
        out.event("beat", strength, at=t, lamps=self.glow_setting("glow_beat") != "Off")   # (a grid: its own say)

    def glow_tick(self, now):
        """(Media mode's main loop.) Music on party mode's player: its colour, now and then, to your grids (the beats
        go as they're found); a station passed through here: its song's name, and let go of once it's not played."""
        playing = isinstance(self.proc, PartyProc) and self.kind in LISTEN_KINDS
        if playing or self.glow_out is not None:
            self.glow_look(now)
        if playing and getattr(self.proc, "player", None) is not None:   # (its sound on the web page, Sound here: its
            used = getattr(self, "sound_used", None) or ("",)           #  beats as that one's listener hears them)
            self.proc.player.late = web_late() if used[0] == "web" else 0.0
        if playing and self.glow_to and not self.paused and now - self.glow_music_at >= GLOW_MUSIC:
            if self.glow_out is None:
                self.glow_out = GlowOut()
                self.glow_out.aim(self.glow_to, self.glow_to_lamps)
            self.glow_music_at = now
            self.glow_out.music(dict(ACCENTS).get(self.setting("accent"), ACCENTS[0][1]))
        st = self.glow_station
        if st is not None:
            relay = st.get("relay")
            if playing and self.kind == "radio" and relay is not None:
                st["quiet"] = None
                if relay.song and relay.song != st["song"]:
                    st["song"] = self.meta["song"] = relay.song
                    self.dirty = True
            else:
                st["quiet"] = st.get("quiet") or now
                if now - st["quiet"] > GLOW_QUIET:
                    self.glow_station_end()

    def glow_station_for(self):
        """A station on party mode's player, on its own: passed through here (glow.py's beat, and its song's names),
        as a party's leader passes one on."""
        st = self.glow_station
        if st is None:
            token = secrets.token_urlsafe(16)
            st = self.glow_station = {"token": token, "server": RelayServer(token, port=0), "relay": None, "song": "",
                                      "quiet": None}
        return st

    def glow_station_end(self):
        st, self.glow_station = self.glow_station, None
        if st is not None:
            for x in (st.get("relay"), st.get("server")):
                if x is not None:
                    threading.Thread(target=x.close, daemon=True).start()

    # -- the web page's Library ----------------------------------------------------------------------------------------
    def web_glow_rows(self):
        """Library > LED backlight's settings, on the web page (a Pi that can have a grid): as Settings rows are. On a
        Pietato with no LEDs of its own: just your ESP32 boards' pulse to music, while one's on."""
        if not self.glow_can():
            if not self.lamps_on():
                return []
            return [dict(key="glow_beat", label="Pulse to music", kind="choice", value=self.glow_value("glow_beat"),
                         choices=["On", "Off"], note="Your ESP32 boards, to this Pietato's music.")]
        rows = [dict(key=k, label=label, kind="choice", value=self.glow_value(k), choices=list(choices))
                if k != "glow_count" else dict(key=k, label=label, kind="count", value=self.glow_count(),
                                               min=STRIP_LEAST, max=STRIP_MOST)
                for k, label, choices in self.glow_rows() if choices]
        rows[0]["note"] = ("WS2812B LEDs, an 8 by 8 grid or a strip: DIN to GPIO 10 (pin 19), and 5 V from a supply "
                           "of their own.")
        rows[1]["colours"] = {n: GLOW_SWATCH.get(n) or "#%02x%02x%02x" % c for n, c in COLOURS}
        rows[1]["note"] = "With no game or music lighting it."
        for r in rows:
            if r["key"] == "glow_way":
                r["note"] = "As you look at the TV."
        rows.append({"key": "glow_test", "label": "Which way is up", "kind": "action", "button": "Show it",
                     "note": "Its top lights red, its left side green.", "disabled": self.glow_grid is None})
        if self.glow_restart:
            rows.append({"key": "glow_reboot", "label": "", "kind": "action", "button": "Restart the Pi",
                         "confirm": "The Pi restarts, with SPI on for the LEDs."})
        return rows

    def web_set_glow_test(self, value, cmd):
        return {"ok": True, "said": "Red's the top, green's the left side"} if self.glow_test() else \
            {"error": "Turn the LED grid on first"}

    def web_set_glow_reboot(self, value, cmd):
        if not self.glow_restart:
            return {"error": "It doesn't need restarting"}
        self.soon(lambda: self.system_do("reboot"))
        return {"ok": True, "said": "Restarting"}

    def web_glow(self):
        """(The web page's thread: it only reads, and tries again if the main loop changed something under it.)"""
        for _ in range(3):
            try:
                return self.web_glow_now()
            except (RuntimeError, IndexError, KeyError, AttributeError, TypeError):
                time.sleep(0.02)
        return self.web_glow_now()

    def web_glow_now(self):
        """Library > LED backlight: the LEDs as they're lit now (as they're seen from in front, each "#rrggbb", row by
        row; None while they're off), what's lighting them, and its settings."""
        g = self.glow_grid
        points = self.glow_points()                  # (a strip: where its LEDs are round the TV; the grid: None)
        if points is not None and g is not None and g.lit() is not None and len(g.lit()[0]) == len(points):
            pic = g.lit()[1]
        else:
            pic = g.picture() if g is not None and points is None else None
        leds = None
        if pic is not None:
            px = (pic.reshape(-1, 3) * self.glow_shade()).clip(0, 255).round().astype(int)
            leds = ["#%02x%02x%02x" % tuple(c) for c in px.tolist()]
        status, boards = self.glow_status(), self.lamps_note()
        if not self.glow_can():                        # (no LEDs of its own: just the boards)
            status = boards
        elif boards and not self.glow_note:
            status = f"{status}. {boards}" if status else boards
        return {"can": self.glow_can(), "on": g is not None, "leds": leds, "status": status,
                "warn": bool(self.glow_note), "rows": self.web_glow_rows(),
                "strip": None if points is None else points.round(4).tolist(),
                "boards": self.web_lamps(), "colours": [list(c) for c in LAMP_COLOURS]}
