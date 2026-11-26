"""Settings > Screen > Waveshare 2.23 OLED (pitato/oled.py): a Waveshare 2.23inch OLED HAT on this Pi's pins, showing
bars that move with your music. Only on a Pi with its pins free: one on a TV or monitor, or with no screen at all
(the web page's Settings has it then), not one in a GPi Case (its screen has the pins), a PC or a handheld. The bars
are the music player's sound: with the OLED on, a song or a station plays through party mode's player (party.py: it
knows when each bit of it is heard), on its own, as it does for an LED backlight's beat (screens/glow.py), and is
shown as it's heard. The HAT is on the Pi's SPI, and an LED backlight's LEDs are wired to the same pin (GPIO 10): one
of them at a time, so turning one on turns the other off. The first time, the Pi's SPI is turned on in config.txt (if
it isn't), and it's lit after a restart.
Another of your Pietatos' music moves its bars too, while this Pi plays none of its own, as an LED backlight follows
whichever of yours is playing: its beacon says its OLED's lit (oled_beacon), each of your others then plays its music
on party mode's player and sends its bars here as they're heard there (oled.py's BarsOut, BarsIn).
With no music for a while, it shows something (Settings > Screen > OLED with no music): the time, the weather here
(the Weather app's, while it isn't too old: else the time), a smiley face, all three in turn, or nothing."""
import errno
import os
import time
import urllib.parse

from ..config import OLED_CHOICES, OLED_QUIET, SETTINGS_PAGES
from ..glow import BLOCK, CONFIG_TXT, PI_MODEL, turn_spi_on
from ..handheld import is_handheld
from ..library import LISTEN_KINDS
from ..oled import (BarsIn, BarsOut, DRIFT_FACE, DRIFT_SECS, DRIFT_TIME, DRIFT_WX, OLED_PORT, OLED_SPI, OledBars,
                    Screen, drift, picture_rows, quiet_face, quiet_time, quiet_weather, wires)
from ..party import PartyProc
from ..system import is_pc, read_file
from ..weather import wx_icon_name, wx_words

OLED_BARS = OLED_CHOICES[1]
OLED_LOOK = 2.0              # seconds between looks for your others' OLEDs (where this one's bars go)
OLED_CATCH = 60.0            # seconds into a song that it's still moved to party mode's player, when one turns up
OLED_OUT_QUIET = 10.0        # seconds with no music for them: its bars' sender is let go of
OLED_LABEL = next(label for key, label, _ in SETTINGS_PAGES["display"] if key == "oled")   # (its row's name)
OLED_NOTES = {errno.EBUSY: "Its pins are in use", errno.ENODEV: "No GPIO here"}
RESTART = "Restart the Pi"   # its note, with SPI just turned on in config.txt
QUIET_TURN = 15.0            # All three: each of them this many seconds
QUIET_WX_OLD = 3 * 3600      # seconds old the weather's shown at most (older: the time instead)


class OledScreen:
    """Settings > Screen > Waveshare 2.23 OLED, and the OLED it lights."""
    oled = None              # the OLED, lit (oled.OledBars)
    oled_note = ""           # why it isn't lit ("" when it is, or it's off)
    oled_restart = False     # SPI turned on in config.txt for it: the Pi needs restarting
    oled_in = None           # your others' music, as bars, taken for it (oled.BarsIn)
    oled_out = None          # this one's music, as bars, to your others' OLEDs (oled.BarsOut)
    oled_to = ()             # ...where they are: [(address, port)]
    oled_seen = 0.0          # ...and when they were last looked for
    oled_quiet_key = None    # what it showed last with no music (quiet), and its rows
    oled_quiet_rows = None
    oled_quiet_said = False  # (what went wrong drawing it: said once)

    def oled_can(self):
        """An OLED HAT can go on this one: a Pi (not a PC or a handheld), and not in a GPi Case (its screen has the
        pins). As an LED grid can (screens/glow.py)."""
        return "Raspberry Pi" in read_file(PI_MODEL) and not is_pc() and not is_handheld() \
            and not getattr(self, "case", None)

    def oled_wanted(self):
        """The OLED's lit, or one of your others' is: music plays on party mode's player, which says when each bit of
        it is heard (for the bars here, or sent there)."""
        return self.oled is not None or bool(self.oled_peers())

    # -- another of your Pietatos' music, on this one's OLED; and this one's, on theirs -------------------------------
    def oled_beacon(self):
        """What this one's beacon says of its OLED (to your others: so their music's bars come here), or None."""
        i = self.oled_in
        return {"port": i.port} if self.oled is not None and i is not None else None

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
        The weather, for this one's OLED with no music: fetched again when it's due."""
        if now - self.oled_seen < OLED_LOOK:
            return
        self.oled_seen = now
        if self.oled is not None and self.setting("oled_quiet") in ("Weather", "All three"):
            self.weather.refresh()                     # (only does anything when it's due)
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
        return self.oled_note or self.setting("oled") or "Off"

    def oled_pick(self, value):
        """Settings > Screen > Waveshare 2.23 OLED picked, here or on the web page. On: an LED backlight on this Pi's
        own pin goes off (the same pin), its bars come up once (so you can tell it's lit), and music that's playing is
        shown from where it is."""
        self.set_setting("oled", value)
        if value != OLED_BARS:
            self.oled_stop()
            self.share_news()                          # (your others hear it's off now, not in 20 seconds)
            return
        leds = self.glow_setting("glow_on") == "On"
        if leds:
            self.glow_pick("glow_on", "Off")
        self.oled_start()
        if self.oled is not None:
            self.oled.hello()                          # (its bars up once: it's lit)
            self.oled_catch()
            self.share_news()                          # (...and your others hear of it now: their music's its too)
            if leds:
                self.toast("The LED backlight is off: the OLED uses its pin", 4)
        elif self.oled_note == RESTART:
            self.toast("Restart the Pi to turn its SPI on for the OLED", 5)
        elif self.oled_note:
            self.toast(f"The OLED can't be lit: {self.oled_note[0].lower()}{self.oled_note[1:]}", 5)

    def oled_start(self):
        """The OLED lit (Settings > Screen > Waveshare 2.23 OLED: Music bars), if it can be. The Pi's SPI not on:
        turned on in config.txt, for the next start."""
        if self.oled is not None or self.setting("oled") != OLED_BARS or not self.oled_can():
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
                screen = Screen(w)
            except OSError:
                w.close()
                raise
        except OSError as ex:
            self.oled_note = OLED_NOTES.get(ex.errno) or ex.strerror or "It didn't start"
            print(f"oled: not lit: {ex}", flush=True)
            return
        self.oled = OledBars(screen, quiet=self.oled_quiet)
        print(f"oled: the OLED's on ({spi})", flush=True)
        try:                                           # (your others' music, as bars: taken from them, for it)
            self.oled_in = BarsIn(self.oled.told, self.glow_named, port=getattr(self, "oled_port", OLED_PORT))
        except OSError as ex:
            print(f"oled: your others' music can't be taken for it ({ex})", flush=True)

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
        o, out = self.oled, self.oled_out
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

    # -- with no music: the time, the weather, a face ---------------------------------------------------------------
    def oled_quiet(self, now):
        """(The OLED's thread, with no music for a while.) Its picture (Settings > Screen > OLED with no music), as the
        screen's rows: the time, the weather (the time instead, while there's none here that isn't too old), a smiley
        face, or each in turn; moved a little each minute. None: nothing (dark). Drawn only as it changes."""
        try:
            pick = self.setting("oled_quiet") or OLED_QUIET[0]
            if pick not in OLED_QUIET[:-1]:
                return None
            wall = getattr(self, "oled_wall", time.time)()   # (the tests' own clock)
            wx = self.oled_weather(wall)
            if pick == "All three":
                turn = ["Time"] + (["Weather"] if wx else []) + ["Smiley"]
                pick = turn[int(wall // QUIET_TURN) % len(turn)]
            if pick == "Weather" and not wx:
                pick = "Time"
            slot = int(wall // DRIFT_SECS)
            if pick == "Time":
                t = time.localtime(wall)
                ampm = "" if self.setting("clock") == "24-hour" else time.strftime("%p", t)
                key = ("time", self.clock_text(t, ampm=False), ampm, drift(slot, DRIFT_TIME))
            elif pick == "Weather":
                key = ("weather",) + wx + (drift(slot, DRIFT_WX),)
            else:
                key = ("face", drift(slot, DRIFT_FACE))
            if key != self.oled_quiet_key:
                img = (quiet_time(key[1], key[2], at=key[3]) if pick == "Time" else
                       quiet_weather(*key[1:4], at=key[4]) if pick == "Weather" else quiet_face(at=key[1]))
                self.oled_quiet_rows, self.oled_quiet_key = picture_rows(img), key
            return self.oled_quiet_rows
        except Exception as ex:                        # (a font missing, say: dark, as before; said once)
            if not self.oled_quiet_said:
                self.oled_quiet_said = True
                print(f"oled: its picture with no music: {ex!r}", flush=True)
            return None

    def oled_weather(self, wall):
        """The weather here for it: (how warm, its words, its picture's name), or None (none, or too old)."""
        w = getattr(self, "weather", None)
        wx = w.data if w is not None else None
        if not wx or wx.get("temp") is None or wall - w.t > QUIET_WX_OLD:
            return None
        return self.deg(wx["temp"]), wx_words(wx.get("code"))[0], wx_icon_name(wx.get("code"), wx.get("is_day", True))

    def web_oled_row(self):
        """Its row in the web page's Settings (None where there can't be one)."""
        if not self.oled_can():
            return None
        row = dict(key="oled", label=OLED_LABEL, kind="choice", value=self.setting("oled") or "Off",
                   choices=list(OLED_CHOICES),
                   note="The OLED HAT on the Pi's pins: bars that move with the music, this Pi's or another of yours'.")
        if self.oled_note:
            restart = self.oled_note == RESTART
            row.update(status="Restart the Pi to turn its SPI on" if restart else self.oled_note,
                       tone="" if restart else "bad")
        return row
