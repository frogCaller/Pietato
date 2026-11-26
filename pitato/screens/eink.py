"""Settings > Screen > Waveshare 2.13 e-ink (pitato/eink.py): a Waveshare 2.13inch e-Paper HAT on this Pi's pins,
showing what that one row's set to: everything at once (the date and the weather along the top, the Bot's face and
the time, and along the bottom the song that's playing, or your prices), the time, the weather, your prices, the
Bot's face, or each of those four in turn. Only on a Pi with its pins free, as the OLED is (screens/oled.py: one on a
TV or monitor, or with no screen at all), and never with it: the two HATs go on the same pins, and an LED backlight's
LEDs are wired to the pin its pictures are sent on, so turning one of the three on turns the others off.
One more row while it's on: upside down, for a Pi that sits the other way up (the OLED's too: screens/oled.py's
HAT_FLIP). The first time, the Pi's SPI is turned on in config.txt (if it isn't), and it's lit after a restart.
Paper's slow, and it wears a little each time it's redrawn: what it shows changes once a minute at most (the time
does), and as a song changes. Set to Off (and as Pietato goes), it's made white first: what's left on paper stays
there for good."""
import errno
import os
import time

from ..config import EINK_CHOICES, OLED_CHOICES, SETTINGS_PAGES
from ..eink import (EINK_SPI, PRICE_ROWS, EINK_SETTLE, Paper, PaperShow, ink_all, ink_face_page, ink_prices,
                    ink_time, ink_weather, paper_wires)
from ..library import LISTEN_KINDS
from ..weather import wx_icon_name, wx_words
from .oled import RESTART

EINK_OFF, EINK_ALL, EINK_TURN = EINK_CHOICES[0], EINK_CHOICES[1], EINK_CHOICES[-1]
EINK_LABEL = next(label for key, label, _ in SETTINGS_PAGES["display"] if key == "eink")   # (its row's name)
EINK_NOTES = {errno.EBUSY: "Its pins are in use", errno.ENODEV: "No GPIO here"}
EINK_LOOKS = ("idle", "happy", "sad", "cool", "curious")   # the Bot's looks that last a while (the rest, what it's
                                                           # doing this second, are gone before paper's caught up)
EINK_LOOK = 2.0              # seconds between looks at what it should show (a song's changed, say)
EINK_TICK = 2.0              # ...and between looks at whether its weather and prices are due
EINK_OLD = 3 * 3600          # seconds old the weather's shown at most (older: the time instead)
DROP_WAIT = 3.0              # seconds it's waited for, let go of for another HAT
GONE_WAIT = 5.0              # ...and as Pietato goes (it's made white first: a couple of seconds)


class EinkScreen:
    """Settings > Screen > Waveshare 2.13 e-ink, and the paper it draws on."""
    eink = None              # the paper, shown what it should show (eink.PaperShow)
    eink_note = ""           # why it isn't ("" when it is, or it's off)
    eink_restart = False     # SPI turned on in config.txt for it: the Pi needs restarting
    eink_key = None          # the picture it showed last, and what it was made from
    eink_img = None
    eink_said = False        # (what went wrong drawing it: said once)
    eink_seen = 0.0          # when its weather and prices were last looked at
    eink_noted = ""          # what its row last said was wrong (the panel's stopped answering, say)

    def eink_can(self):
        """An e-Paper HAT can go on this one: where an OLED HAT can (a Pi with its pins free)."""
        return self.oled_can()

    def eink_shows(self):
        """What it's set to show (Settings > Screen > Waveshare 2.13 e-ink): one of its choices."""
        v = self.setting("eink")
        return v if v in EINK_CHOICES else EINK_OFF

    def eink_lit(self):
        """It's on (and not on its way off)."""
        e = self.eink
        return e is not None and not e.going()

    def eink_value(self):
        """Its row in Settings: what it's set to, or why it's blank when it shouldn't be."""
        e = self.eink
        return self.eink_note or (e.note if e is not None and not e.going() else "") or self.eink_shows()

    def eink_pick(self, value):
        """Settings > Screen > Waveshare 2.13 e-ink picked, here or on the web page: what it shows from now. On: an
        OLED HAT's turned off, and an LED backlight on this Pi's own pin (the same pins), and that's said. Off: white
        and off, once the row's stayed there a moment (not as it's gone past, on the way to another)."""
        self.set_setting("eink", value)
        e = self.eink
        if self.eink_shows() == EINK_OFF:
            if e is not None:
                e.off()
            self.eink_note = ""
            return
        said = ""
        if self.oled_shows() != OLED_CHOICES[0]:
            self.oled_pick(OLED_CHOICES[0])
            said = "The OLED is off: the e-ink uses its pins"
        if self.glow_setting("glow_on") == "On":
            self.glow_pick("glow_on", "Off")
            said = "The LED backlight is off: the e-ink uses its pin"
        self.eink_start()
        if self.eink is not None:
            if said:
                self.toast(said, 4)
        elif self.eink_note == RESTART:
            self.toast("Restart the Pi to turn its SPI on for the e-ink", 5)
        elif self.eink_note:
            self.toast(f"The e-ink can't be used: {self.eink_note[0].lower()}{self.eink_note[1:]}", 5)

    def eink_turned(self):
        """(screens/oled.py's hat_flip_pick.) Upside down or not, picked: the paper drawn afresh, that way up."""
        e = self.eink
        if e is not None and not e.going():
            e.turn(self.hat_flip(), settle=EINK_SETTLE)

    def eink_start(self):
        """The paper drawn on (Settings > Screen > Waveshare 2.13 e-ink: anything but Off), if it can be. The Pi's SPI
        not on: turned on in config.txt, for the next start."""
        if self.eink_shows() == EINK_OFF or not self.eink_can():
            return
        e = self.eink
        if e is not None:
            if e.on():                                 # (there already, or on its way off: it carries on, afresh)
                return
            e.close(wait=DROP_WAIT)                    # (off, this moment: its pins are let go of before they're had)
        self.eink, self.eink_note, self.eink_key = None, "", None
        if self.glow_setting("glow_on") == "On":       # (both set, somehow: the LEDs keep the pin)
            self.eink_note = "The LED backlight has its pin"
            return
        if self.oled_shows() != OLED_CHOICES[0]:       # (...or the OLED its pins)
            self.eink_note = "The OLED has its pins"
            return
        spi = getattr(self, "eink_spi", EINK_SPI)
        if not os.path.exists(spi):
            try:
                self.eink_restart = self.oled_spi_on() or self.eink_restart
            except OSError as ex:
                print(f"eink: couldn't turn SPI on in config.txt ({ex})", flush=True)
            restart = self.eink_restart or self.oled_restart or self.glow_restart
            self.eink_note = RESTART if restart else "No SPI here"
            print(f"eink: not on: no {spi}", flush=True)
            return
        try:
            w = getattr(self, "eink_wires", paper_wires)(spi)   # (the tests' own wires)
            try:
                paper = Paper(w)
            except OSError:
                w.close()
                raise
        except OSError as ex:
            self.eink_note = EINK_NOTES.get(ex.errno) or ex.strerror or "It didn't start"
            print(f"eink: not on: {ex}", flush=True)
            return
        self.eink = PaperShow(paper, self.eink_picture, flip=self.hat_flip())
        print(f"eink: the e-ink's on ({spi})", flush=True)

    def eink_stop(self, wait=None):
        """White, asleep and let go of, now (Pietato's going). wait: seconds it's waited for."""
        e = self.eink
        if e is not None:
            e.close(clear=True, wait=wait)

    def eink_gone(self, secs=GONE_WAIT):
        """(As Pietato goes, eink_stop a moment ago.) Waited for, a few seconds at most."""
        e, self.eink = self.eink, None
        if e is not None:
            e.close(clear=True, wait=secs)

    def eink_drop(self):
        """Let go of at once, as it is, and set to Off: an OLED HAT or the LEDs are to have its pins. True: it was
        on."""
        was = self.eink_shows() != EINK_OFF
        if was:
            self.set_setting("eink", EINK_OFF)
        e, self.eink = self.eink, None
        if e is not None:
            e.close(clear=False, wait=DROP_WAIT)
        self.eink_note = ""
        return was

    def eink_tick(self, now):
        """(Media mode's main loop.) The weather and your prices, while the paper shows them: fetched again when
        they're due (as for the OLED: screens/oled.py). And its row in Settings, as what it says changes."""
        if now - self.eink_seen < EINK_TICK:
            return
        self.eink_seen = now
        note = self.eink_value()
        if note != self.eink_noted:                    # (it's stopped answering, or it's started again: its row says
            self.eink_noted, self.dirty = note, True   # so, if that's the page that's up)
        if not self.eink_lit():
            return
        pick = self.eink_shows()
        if pick in (EINK_ALL, "Weather", EINK_TURN):
            self.weather.refresh()                     # (only does anything when it's due)
        if pick in (EINK_ALL, "Prices", EINK_TURN):
            self.oled_prices_due()

    # -- what it shows -----------------------------------------------------------------------------------------------
    def eink_weather(self, wall):
        """The weather here for it: (how warm, its words, its picture's name, today's high, today's low, the next
        three days: ((its name, its picture's name, its high, its low), ...)), or None (none, or too old)."""
        w = getattr(self, "weather", None)
        wx = w.data if w is not None else None
        if not wx or wx.get("temp") is None or wall - w.t > EINK_OLD:
            return None
        days = [d for d in wx.get("days") or [] if isinstance(d, dict)]
        today = time.strftime("%Y-%m-%d", time.localtime(wall))
        at = next((k for k, d in enumerate(days) if d.get("date") == today), 0)   # (by its date: it may be a day old)
        now = days[at] if at < len(days) else {}
        coming = []
        for day in days[at + 1:at + 4]:
            try:
                name = time.strftime("%a", time.strptime(day["date"], "%Y-%m-%d"))
            except (KeyError, TypeError, ValueError):
                continue
            coming.append((name, wx_icon_name(day.get("code"), True), self.deg(day.get("hi")),
                           self.deg(day.get("lo"))))
        return (self.deg(wx["temp"]), wx_words(wx.get("code"))[0],
                wx_icon_name(wx.get("code"), wx.get("is_day", True)),
                self.deg(now["hi"]) if now.get("hi") is not None else "",
                self.deg(now["lo"]) if now.get("lo") is not None else "", tuple(coming))

    def eink_song(self):
        """The song that's playing (the station's, on the radio), as the status bar names it, or ""."""
        if self.proc and self.kind in LISTEN_KINDS and self.cur:
            return str(self.meta.get("song") or self.meta.get("title") or self.cur.get("title") or "")
        return ""

    def eink_look(self):
        """How the Bot's face looks on paper: how it felt about what it last said (for a while), or its everyday
        look. Not what it's doing this second."""
        try:
            look = self.face_look()
        except Exception:                              # (the Bot not there yet: as it's always looked)
            return "idle"
        return look if look in EINK_LOOKS else "idle"

    def eink_picture(self, now):
        """(The e-ink's thread.) What it shows now: (the picture, seconds till it's asked again, what kind of picture
        it is), or None (nothing). As Settings > Screen > Waveshare 2.13 e-ink is set: everything at once, the time,
        the weather or your prices (the time instead, while there are none here that aren't too old), the Bot's
        face, or each of those four in turn, a minute each. Drawn only as it changes."""
        try:
            pick = self.eink_shows()
            if pick == EINK_OFF:
                return None
            wall = getattr(self, "eink_wall", time.time)()   # (the tests' own clock)
            t = time.localtime(wall)
            minute = int(wall // 60)
            wx, prices = self.eink_weather(wall), self.oled_prices(wall)
            pages = -(-len(prices) // PRICE_ROWS)      # (your prices, PRICE_ROWS at a time: a minute each)
            page = minute % pages if pages else 0
            if pick == EINK_TURN:
                turn = ([("Time", 0)] + ([("Weather", 0)] if wx else []) + [("Prices", k) for k in range(pages)]
                        + [("Face", 0)])
                pick, page = turn[minute % len(turn)]
            if (pick == "Weather" and not wx) or (pick == "Prices" and not prices):
                pick = "Time"
            ampm = "" if self.setting("clock") == "24-hour" else time.strftime("%p", t)
            clock = self.clock_text(t, ampm=False)
            shape, lashes = self.oled_face()
            face = (self.eink_look(), tuple(sorted(shape.items())), lashes)
            if pick == EINK_ALL:
                song = self.eink_song()
                if song:
                    foot = ("song", song)
                elif prices:                           # (two at a time, on by one each minute: all of them, in turn)
                    foot = ("prices", tuple(prices[(minute + k) % len(prices)] for k in range(min(2, len(prices)))))
                elif wx:
                    foot = ("words", wx[1] + (f", high {wx[3]}" if wx[3] else "") + (f" low {wx[4]}" if wx[4] else ""))
                else:
                    foot = None
                key = ("all", clock, ampm, time.strftime("%a, %b ", t) + str(t.tm_mday), wx and (wx[0], wx[2]), face,
                       foot)
            elif pick == "Time":
                key = ("time", clock, ampm, time.strftime("%A, %B ", t) + str(t.tm_mday))
            elif pick == "Weather":
                key = ("weather",) + wx
            elif pick == "Prices":
                key = ("prices", tuple(prices[page * PRICE_ROWS:(page + 1) * PRICE_ROWS]))
            else:
                key = ("face",) + face
            if key != self.eink_key:
                self.eink_img = (ink_all(*key[1:5], face=(face[0], shape, lashes), foot=key[6]) if key[0] == "all"
                                 else ink_time(*key[1:]) if key[0] == "time"
                                 else ink_weather(*key[1:]) if key[0] == "weather"
                                 else ink_prices(key[1]) if key[0] == "prices"
                                 else ink_face_page(face[0], shape, lashes))
                self.eink_key = key
            return self.eink_img, min(EINK_LOOK, 60.05 - wall % 60), key[0]
        except Exception as ex:                        # (a font missing, say: left as it is; said once)
            if not self.eink_said:
                self.eink_said = True
                print(f"eink: its picture: {ex!r}", flush=True)
            return None

    # -- the web page's Settings ------------------------------------------------------------------------------------
    def web_eink_row(self):
        """Its row in the web page's Settings (None where there can't be one)."""
        if not self.eink_can():
            return None
        row = dict(key="eink", label=EINK_LABEL, kind="choice", value=self.eink_shows(), choices=list(EINK_CHOICES),
                   note="The e-Paper HAT on the Pi's pins, and what it shows: everything at once (the date, the "
                        "weather, the time, and the song that's playing or your Finance prices), or the time, the "
                        "weather, your prices, the Bot's face, or each of those four in turn.")
        e = self.eink
        why = self.eink_note or (e.note if e is not None and not e.going() else "")
        if why:
            restart = why == RESTART
            row.update(status="Restart the Pi to turn its SPI on" if restart else why, tone="" if restart else "bad")
        return row
