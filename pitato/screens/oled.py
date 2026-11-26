"""Settings > Screen > Waveshare 2.23 OLED (pitato/oled.py): a Waveshare 2.23inch OLED HAT on this Pi's pins, showing
what that one row's set to: bars that move with your music, the time, the weather, your prices, the Bot's face, or
each of those four in turn. Only on a Pi with its pins free: one on a TV or monitor, or with no screen at all
(the web page's Settings has it then), not one in a GPi Case (its screen has the pins), a PC or a handheld. The bars
are the music player's sound: with them picked, a song or a station plays through party mode's player (party.py: it
knows when each bit of it is heard), on its own, as it does for an LED backlight's beat (screens/glow.py), and is
shown as it's heard. The HAT is on the Pi's SPI, and an LED backlight's LEDs are wired to the same pin (GPIO 10): one
of them at a time, so turning one on turns the other off. The first time, the Pi's SPI is turned on in config.txt (if
it isn't), and it's lit after a restart.
Another of your Pietatos' music moves its bars too, while this Pi plays none of its own, as an LED backlight follows
whichever of yours is playing: its beacon says its OLED's lit (oled_beacon), each of your others then plays its music
on party mode's player and sends its bars here as they're heard there (oled.py's BarsOut, BarsIn).
A picture stays up whatever plays: the time, the weather here (the Weather app's, while it isn't too old: else the
time), your stocks' and coins' prices (the Finance app's, one at a time; fetched every few minutes for it, the prices
alone, while the Finance tab isn't open), or the Bot's face (as its Character has it: it blinks and glances about).
With the bars picked and no music for a while, it shows the time, so it isn't left dark.
One more row while it's on (or the e-ink is: screens/eink.py): upside down, for a Pi that sits the other way up.
The one setting (HAT_FLIP) turns whichever of the two is on."""
import errno
import os
import threading
import time
import urllib.parse

from ..config import EINK_CHOICES, OLED_CHOICES, SETTINGS_PAGES
from ..crypto import price_text
from ..face import face_shape, face_state, face_wait
from ..glow import BLOCK, CONFIG_TXT, PI_MODEL, turn_spi_on
from ..handheld import is_handheld
from ..library import LISTEN_KINDS
from ..oled import (BarsIn, BarsOut, DRIFT_SECS, DRIFT_TIME, DRIFT_WX, OLED_PORT, OLED_SPI, OledBars, Screen, drift,
                    face_drift, picture_rows, quiet_face, quiet_price, quiet_time, quiet_weather, wires)
from ..party import PartyProc
from ..stocks import money
from ..system import is_pc, read_file
from ..weather import wx_icon_name, wx_words

OLED_BARS = OLED_CHOICES[1]
OLED_PICTURES = tuple(OLED_CHOICES[2:])   # a picture in place of its bars, whatever plays: Time to Face...
OLED_TURN = OLED_CHOICES[-1]              # ...and Each in turn
OLED_SETTLE = 2.0            # seconds its bars are picked for before music that's playing is moved to party mode's
                             # player for them (not as the row's gone past them, on the way to another)
OLED_LOOK = 2.0              # seconds between looks for your others' OLEDs (where this one's bars go)
OLED_CATCH = 60.0            # seconds into a song that it's still moved to party mode's player, when one turns up
OLED_OUT_QUIET = 10.0        # seconds with no music for them: its bars' sender is let go of
OLED_LABEL = next(label for key, label, _ in SETTINGS_PAGES["display"] if key == "oled")   # (its row's name)
OLED_NOTES = {errno.EBUSY: "Its pins are in use", errno.ENODEV: "No GPIO here"}
RESTART = "Restart the Pi"   # its note, with SPI just turned on in config.txt
HAT_FLIP = "hat_flip"        # Settings > Screen's row under the two HATs' own: the one that's on, upside down
QUIET_TURN = 15.0            # Each in turn: each of them this many seconds (the prices: PRICE_SECS each)
QUIET_WX_OLD = 3 * 3600      # seconds old the weather's shown at most (older: the time instead), and a price
PRICE_SECS = 5.0             # Prices: each this many seconds
PRICES_EVERY = 300.0         # seconds between fetching them for it (a stock's market shut: PRICES_SHUT)
PRICES_SHUT = 600.0


class OledScreen:
    """Settings > Screen > Waveshare 2.23 OLED, and the OLED it lights."""
    oled = None              # the OLED, lit (oled.OledBars): its bars, or a picture
    oled_note = ""           # why it isn't lit ("" when it is, or it's off)
    oled_restart = False     # SPI turned on in config.txt for it: the Pi needs restarting
    oled_in = None           # your others' music, as bars, taken for it (oled.BarsIn)
    oled_out = None          # this one's music, as bars, to your others' OLEDs (oled.BarsOut)
    oled_to = ()             # ...where they are: [(address, port)]
    oled_seen = 0.0          # ...and when they were last looked for
    oled_quiet_key = None    # the picture it showed last, and its rows
    oled_quiet_rows = None
    oled_quiet_said = False  # (what went wrong drawing it: said once)
    oled_catch_at = 0.0      # its bars just picked: when music that's playing is moved over for them (0: not)
    oled_prices_at = 0.0     # when its prices were last fetched, for it (and it's at it)
    oled_prices_busy = False

    def oled_can(self):
        """An OLED HAT can go on this one: a Pi (not a PC or a handheld), and not in a GPi Case (its screen has the
        pins). As an LED grid can (screens/glow.py)."""
        return "Raspberry Pi" in read_file(PI_MODEL) and not is_pc() and not is_handheld() \
            and not getattr(self, "case", None)

    def oled_shows(self):
        """What it's set to show (Settings > Screen > Waveshare 2.23 OLED): one of its choices."""
        v = self.setting("oled")
        return v if v in OLED_CHOICES else OLED_CHOICES[0]

    def hat_on(self):
        """Which of the two HATs is on: "OLED", "E-ink", or "" (neither: no row for which way up it is)."""
        if not self.oled_can():
            return ""
        if self.oled_shows() != OLED_CHOICES[0]:
            return "OLED"
        return "E-ink" if self.eink_shows() != EINK_CHOICES[0] else ""

    def hat_flip(self):
        """The OLED or the e-ink, whichever's on, shows its picture upside down: a Pi that sits the other way up."""
        return self.setting(HAT_FLIP) == "On"

    def hat_flip_label(self):
        """Its row's name: which of the two it turns just now."""
        return f"{self.hat_on() or 'OLED or e-ink'} upside down"

    def hat_flip_pick(self, value):
        """Upside down or not, picked (here or on the web page): kept, and whichever's on drawn that way up from
        now."""
        self.set_setting(HAT_FLIP, value)
        o = self.oled
        if o is not None:
            o.turn(self.hat_flip())
        self.eink_turned()                             # (the e-ink, if that's the one that's on: screens/eink.py)

    def oled_bars(self):
        """It's lit, and set to its bars."""
        return self.oled is not None and self.oled_shows() == OLED_BARS

    def oled_wanted(self):
        """The OLED's showing its bars, or one of your others' is: music plays on party mode's player, which says when
        each bit of it is heard (for the bars here, or sent there)."""
        return self.oled_bars() or bool(self.oled_peers())

    # -- another of your Pietatos' music, on this one's OLED; and this one's, on theirs -------------------------------
    def oled_beacon(self):
        """What this one's beacon says of its OLED (to your others: so their music's bars come here), or None (it's
        off, or showing a picture)."""
        i = self.oled_in
        return {"port": i.port} if self.oled_bars() and i is not None else None

    def oled_peers(self):
        """Your other Pietatos with an OLED lit, as their beacons say: [(address, port)]. None with sharing off."""
        pie = getattr(self, "pie", None)
        if pie is None or self.setting("share") == "Off":
            return []
        names = dict(self.saves_peers())
        out = []
        with pie.lock:
            for url, h in pie.heard.items():
                o = h.get("oled")
                if url in names and o:
                    host = urllib.parse.urlsplit(url).hostname
                    if host:
                        out.append((host, o["port"]))
        return out

    def oled_tick(self, now):
        """(Media mode's main loop: every couple of seconds.) Your others' OLEDs, looked for: this one's music on
        party mode's player has its bars sent to them (till there's been none for a while). One's just turned up, and
        a song's only just begun on the plain player (which says nothing of its sound): moved over, from where it is.
        The weather and your prices, while this one's OLED shows them: fetched again when they're due."""
        if self.oled_catch_at and now >= self.oled_catch_at:   # (its bars picked, and still: the music's moved over)
            self.oled_catch_at = 0.0
            if self.oled_bars():
                self.oled_catch()
        if now - self.oled_seen < OLED_LOOK:
            return
        self.oled_seen = now
        if self.oled is not None and self.oled_shows() in ("Weather", OLED_TURN):
            self.weather.refresh()                     # (only does anything when it's due)
        if self.oled is not None and self.oled_shows() in ("Prices", OLED_TURN):
            self.oled_prices_due()
        was, to = self.oled_to, tuple(self.oled_peers())
        self.oled_to = to
        out = self.oled_out
        if to and isinstance(self.proc, PartyProc) and self.kind in LISTEN_KINDS:
            if out is None:
                out = self.oled_out = BarsOut()
            out.aim(to)
        elif out is not None:
            out.aim(to)
            if not to or now - out.fed > OLED_OUT_QUIET:
                self.oled_out_stop()
        if to and not was and now - (self.started or 0.0) <= OLED_CATCH:
            self.oled_catch()

    def oled_out_stop(self):
        out, self.oled_out = self.oled_out, None
        if out is not None:
            out.close()

    def oled_value(self):
        """Its row in Settings: what it's set to, or why it's dark when it should be lit."""
        return self.oled_note or self.oled_shows()

    def oled_pick(self, value):
        """Settings > Screen > Waveshare 2.23 OLED picked, here or on the web page: what it shows from now, whatever
        plays. On (from Off): an LED backlight on this Pi's own pin goes off (the same pin). Its bars: they come up
        once (so you can tell it's lit), and music that's playing is shown from where it is, once the row's stayed on
        them a moment. A picture: shown at once."""
        was_bars = self.oled_bars()
        self.set_setting("oled", value)
        self.oled_catch_at = 0.0
        if self.oled_shows() == OLED_CHOICES[0]:
            self.oled_stop()
            self.share_news()                          # (your others hear it's off now, not in 20 seconds)
            return
        leds = self.glow_setting("glow_on") == "On"
        if leds:
            self.glow_pick("glow_on", "Off")
        ink = self.eink_drop()                         # (an e-Paper HAT goes on the same pins: let go of)
        self.oled_start()
        if self.oled is not None:
            self.oled_listen()                         # (your others' music, as bars: taken for its bars alone)
            if self.oled_bars():
                self.oled.hello()                      # (its bars up once: it's lit)
                self.oled_catch_at = time.monotonic() + OLED_SETTLE
            self.oled.poke()                           # (a picture: shown now)
            if was_bars != self.oled_bars():
                self.share_news()                      # (...and your others hear of it now: their music's its too)
            if leds:
                self.toast("The LED backlight is off: the OLED uses its pin", 4)
            elif ink:
                self.toast("The e-ink is off: the OLED uses its pins", 4)
        elif self.oled_note == RESTART:
            self.toast("Restart the Pi to turn its SPI on for the OLED", 5)
        elif self.oled_note:
            self.toast(f"The OLED can't be lit: {self.oled_note[0].lower()}{self.oled_note[1:]}", 5)

    def oled_listen(self):
        """Your others' music, as bars: taken for this one's OLED while it shows its bars, and not while it shows a
        picture."""
        if self.oled_bars() and self.oled_in is None:
            try:
                self.oled_in = BarsIn(self.oled.told, self.glow_named, port=getattr(self, "oled_port", OLED_PORT))
            except OSError as ex:
                print(f"oled: your others' music can't be taken for it ({ex})", flush=True)
        elif not self.oled_bars() and self.oled_in is not None:
            i, self.oled_in = self.oled_in, None
            i.close()

    def oled_start(self):
        """The OLED lit (Settings > Screen > Waveshare 2.23 OLED: anything but Off), if it can be. The Pi's SPI not
        on: turned on in config.txt, for the next start."""
        if self.oled is not None or self.oled_shows() == OLED_CHOICES[0] or not self.oled_can():
            return
        self.oled_note = ""
        if self.glow_setting("glow_on") == "On":       # (both set, somehow: the LEDs keep the pin)
            self.oled_note = "The LED backlight has its pin"
            return
        spi = getattr(self, "oled_spi", OLED_SPI)
        if not os.path.exists(spi):
            try:
                self.oled_restart = self.oled_spi_on() or self.oled_restart
            except OSError as ex:
                print(f"oled: couldn't turn SPI on in config.txt ({ex})", flush=True)
            self.oled_note = RESTART if self.oled_restart or self.glow_restart else "No SPI here"
            print(f"oled: not lit: no {spi}", flush=True)
            return
        try:
            w = getattr(self, "oled_wires", wires)(spi)    # (the tests' own wires)
            try:
                screen = Screen(w, flip=self.hat_flip())
            except OSError:
                w.close()
                raise
        except OSError as ex:
            self.oled_note = OLED_NOTES.get(ex.errno) or ex.strerror or "It didn't start"
            print(f"oled: not lit: {ex}", flush=True)
            return
        self.oled = OledBars(screen, picture=self.oled_picture)
        print(f"oled: the OLED's on ({spi})", flush=True)
        self.oled_listen()                             # (your others' music, as bars: taken from them, for its bars)

    def oled_spi_on(self):
        """SPI turned on in config.txt, in the LED backlight's own part of it (glow.py: uninstall.sh takes it out),
        unless that's there already: True if it had to be put in."""
        path = next((p for p in getattr(self, "glow_configs", CONFIG_TXT) if read_file(p, None) is not None), None)
        if path is None or BLOCK[0] in read_file(path):
            return False
        return turn_spi_on(path, ["dtparam=spi=on"])

    def oled_stop(self):
        i, self.oled_in = self.oled_in, None
        if i is not None:
            i.close()
        o, self.oled = self.oled, None
        if o is not None:
            o.close()
            print("oled: the OLED's off", flush=True)
        self.oled_note = ""

    def oled_heard(self, pcm, t, gain):
        """(Party mode's player, as it plays.) Sound, its first sample heard at t (its clock: the leader's, in another's
        party), as loud as the volume's made it (gain)."""
        o, out = self.oled if self.oled_bars() else None, self.oled_out   # (showing a picture: no bars to move)
        if o is None and out is None:
            return
        if self.party is not None and not self.party.get("lead"):
            t -= self.party_clock() - time.monotonic()  # (the leader's clock, as this one's)
        if o is not None:
            o.heard(pcm, t, gain)
        if out is not None:                            # (...and for your others' OLEDs)
            out.heard(pcm, t, gain)

    def oled_catch(self):
        """The OLED's just been turned on (or one of your others' has turned up), and music's playing on the plain
        player, which says nothing of its sound: moved to party mode's player, from where it is, after a moment's
        quiet."""
        p = self.proc
        plain = (p is not None and not isinstance(p, PartyProc) and self.kind in LISTEN_KINDS and p.poll() is None
                 and 0 <= self.qi < len(self.queue))
        if not plain or self.party is not None or self.paused:
            return
        pos = (self.pos or 0.0) if self.kind == "audio" else 0.0
        self.play(self.queue, self.qi, start=max(0.0, pos), show=False)

    # -- a picture in place of its bars: the time, the weather, prices, the Bot's face -------------------------------
    def oled_picture(self, now, quiet=True):
        """(The OLED's thread.) The picture it shows now in place of its bars, as the screen's rows, and how soon to
        ask again: (rows, seconds: None for a quarter of a second), or None for its bars. What Settings > Screen >
        Waveshare 2.23 OLED is set to, whatever plays: the time, the weather or your prices (the time instead, while
        there are none here that aren't too old), the Bot's face, or each in turn. Set to its bars: the time, once
        there's been no music for a while (quiet). Moved a little each minute, and drawn only as it changes."""
        try:
            pick = self.oled_shows()
            if pick == OLED_BARS:
                if not quiet:
                    return None
                pick = "Time"                          # (no music for a while: not left dark)
            elif pick not in OLED_PICTURES:
                return None
            wall = getattr(self, "oled_wall", time.time)()   # (the tests' own clock)
            wx, prices = self.oled_weather(wall), self.oled_prices(wall)
            at = wall % (len(prices) * PRICE_SECS) if prices else 0.0
            if pick == OLED_TURN:                      # (each for its while: the prices one at a time, all of them)
                turn = ([("Time", QUIET_TURN)] + ([("Weather", QUIET_TURN)] if wx else [])
                        + ([("Prices", len(prices) * PRICE_SECS)] if prices else []) + [("Face", QUIET_TURN)])
                at = wall % sum(secs for _, secs in turn)
                for pick, secs in turn:
                    if at < secs:
                        break
                    at -= secs
            if (pick == "Weather" and not wx) or (pick == "Prices" and not prices):
                pick = "Time"
            slot, wait = int(wall // DRIFT_SECS), None
            if pick == "Time":
                t = time.localtime(wall)
                ampm = "" if self.setting("clock") == "24-hour" else time.strftime("%p", t)
                key = ("time", self.clock_text(t, ampm=False), ampm, drift(slot, DRIFT_TIME))
            elif pick == "Weather":
                key = ("weather",) + wx + (drift(slot, DRIFT_WX),)
            elif pick == "Prices":
                key = ("price",) + prices[int(at // PRICE_SECS) % len(prices)] + (drift(slot, DRIFT_WX),)
            else:                                      # (the Bot's face, as it looks now: a blink, a glance)
                shape, lashes = self.oled_face()
                opened, (gx, gy), _, _ = face_state("idle", now)
                key = ("face", tuple(sorted(shape.items())), lashes, round(opened, 2), round(gx, 2), round(gy, 2),
                       face_drift(slot, shape, lashes))
                wait = face_wait("idle", now)
            if key != self.oled_quiet_key:
                img = (quiet_time(key[1], key[2], at=key[3]) if pick == "Time" else
                       quiet_weather(*key[1:4], at=key[4]) if pick == "Weather" else
                       quiet_price(*key[1:4], at=key[4]) if pick == "Prices" else
                       quiet_face(shape, lashes, now, at=key[6]))
                self.oled_quiet_rows, self.oled_quiet_key = picture_rows(img), key
            return self.oled_quiet_rows, wait
        except Exception as ex:                        # (a font missing, say: its bars, as before; said once)
            if not self.oled_quiet_said:
                self.oled_quiet_said = True
                print(f"oled: its picture: {ex!r}", flush=True)
            return None

    def oled_face(self):
        """The Bot's face, as its Character has it: (its eyes' and mouth's shape, whether it has eyelashes)."""
        try:
            return self.bot_shape(), bool(self.bot_lashes())
        except Exception:                              # (bot.txt as it can't be read: as it's always looked)
            return face_shape(), False

    def oled_prices(self, wall):
        """Your stocks' and coins' prices for it (the Finance app's): [(ticker, price, how far it's moved today in
        percent: None when that isn't known)], each as fetched last, while that isn't too old."""
        out = []
        for src, mine, key, change, said in ((self.stocks, self.stocks.stocks, "symbol", "change_1d", None),
                                             (self.crypto, self.crypto.coins, "id", "change_24h", price_text)):
            for one in mine:
                e = src.quotes.get(one[key]) or {}
                q = e.get("d") or {}
                if q.get("price") is None or wall - e.get("t", 0) > QUIET_WX_OLD:
                    continue
                price = said(q["price"]) if said else money(q["price"], q.get("currency") or "USD", q.get("kind", ""))
                moved = q.get(change)
                out.append((one.get("symbol") or q.get("symbol") or one[key],
                            price, round(moved, 2) if isinstance(moved, (int, float)) and moved == moved else None))
        return out

    def oled_prices_due(self):
        """(Media mode's main loop, while its OLED shows them.) Your stocks' and coins' prices, fetched again every
        few minutes (PRICES_EVERY; a stock's while its market's shut, PRICES_SHUT): the prices alone, not their
        charts, on a thread of their own. Not while the Finance tab's open (it's fetching them itself)."""
        now = time.time()
        if self.oled_prices_busy or self.stocks.running or self.crypto.running or now - self.oled_prices_at < 60:
            return
        self.oled_prices_at, self.oled_prices_busy = now, True
        self.fin_load()                                # (your stocks and coins, as finance.txt has them now)
        threading.Thread(target=self.oled_prices_fetch, daemon=True, name="oled-prices").start()

    def oled_prices_fetch(self):
        try:
            for src, ids in ((self.stocks, self.stocks.symbols()), (self.crypto, self.crypto.ids())):
                got = False
                for i in ids:
                    if self.stocks.running or self.crypto.running:
                        return                         # (the Finance tab's open now: it fetches them)
                    e = src.quotes.get(i) or {}
                    every = PRICES_EVERY
                    if src is self.stocks and src.ttl(("quote", i)) > 60:
                        every = PRICES_SHUT            # (its market's shut: its price won't change much)
                    if time.time() - e.get("t", 0) < every - 30 or time.time() - e.get("tried", 0) < 60:
                        continue
                    job = ("quote", i)
                    try:
                        if not (src.from_peer(job, every) if src is self.stocks else src.from_pie(job, every)):
                            src.fetch_quote(i)
                        got = True
                    except Exception:                  # (no WiFi, say: the old price kept, tried again later)
                        with src.lock:
                            src.quotes[i] = dict(src.quotes.get(i) or {}, tried=time.time())
                if got:
                    src.save_cache()
        finally:
            self.oled_prices_busy = False

    def oled_weather(self, wall):
        """The weather here for it: (how warm, its words, its picture's name), or None (none, or too old)."""
        w = getattr(self, "weather", None)
        wx = w.data if w is not None else None
        if not wx or wx.get("temp") is None or wall - w.t > QUIET_WX_OLD:
            return None
        return self.deg(wx["temp"]), wx_words(wx.get("code"))[0], wx_icon_name(wx.get("code"), wx.get("is_day", True))

    def web_flip_row(self, choices):
        """Upside down's row in the web page's Settings (there while the OLED or the e-ink is on)."""
        return dict(key=HAT_FLIP, label=self.hat_flip_label(), kind="choice", value="On" if self.hat_flip() else "Off",
                    choices=list(choices), note="Turns its picture round, for a Pi that sits the other way up.")

    def web_oled_row(self):
        """Its row in the web page's Settings (None where there can't be one)."""
        if not self.oled_can():
            return None
        row = dict(key="oled", label=OLED_LABEL, kind="choice", value=self.oled_shows(),
                   choices=list(OLED_CHOICES),
                   note="The OLED HAT on the Pi's pins, and what it shows: bars that move with the music (this Pi's "
                        "or another of yours'), the time, the weather, your Finance prices, the Bot's face, or each "
                        "of those four in turn.")
        if self.oled_note:
            restart = self.oled_note == RESTART
            row.update(status="Restart the Pi to turn its SPI on" if restart else self.oled_note,
                       tone="" if restart else "bad")
        return row
