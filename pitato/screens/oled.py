"""Settings > Screen > Waveshare 2.23 OLED (pitato/oled.py): a Waveshare 2.23inch OLED HAT on this Pi's pins, showing
bars that move with your music. Only on a Pi with its pins free: one on a TV or monitor, not one in a GPi Case (its
screen has the pins), a PC or a handheld. The bars are the music player's sound: with the OLED on, a song or a station
plays through party mode's player (party.py: it knows when each bit of it is heard), on its own, as it does for an LED
backlight's beat (screens/glow.py), and is shown as it's heard. The HAT is on the Pi's SPI, and an LED backlight's
LEDs are wired to the same pin (GPIO 10): one of them at a time, so turning one on turns the other off. The first
time, the Pi's SPI is turned on in config.txt (if it isn't), and it's lit after a restart."""
import errno
import os
import time

from ..config import OLED_CHOICES, SETTINGS_PAGES
from ..glow import BLOCK, CONFIG_TXT, PI_MODEL, turn_spi_on
from ..handheld import is_handheld
from ..library import LISTEN_KINDS
from ..oled import OLED_SPI, OledBars, Screen, wires
from ..party import PartyProc
from ..system import is_pc, read_file

OLED_BARS = OLED_CHOICES[1]
OLED_LABEL = next(label for key, label, _ in SETTINGS_PAGES["display"] if key == "oled")   # (its row's name)
OLED_NOTES = {errno.EBUSY: "Its pins are in use", errno.ENODEV: "No GPIO here"}
RESTART = "Restart the Pi"   # its note, with SPI just turned on in config.txt


class OledScreen:
    """Settings > Screen > Waveshare 2.23 OLED, and the OLED it lights."""
    oled = None              # the OLED, lit (oled.OledBars)
    oled_note = ""           # why it isn't lit ("" when it is, or it's off)
    oled_restart = False     # SPI turned on in config.txt for it: the Pi needs restarting

    def oled_can(self):
        """An OLED HAT can go on this one: a Pi (not a PC or a handheld), and not in a GPi Case (its screen has the
        pins). As an LED grid can (screens/glow.py)."""
        return "Raspberry Pi" in read_file(PI_MODEL) and not is_pc() and not is_handheld() \
            and not getattr(self, "case", None)

    def oled_wanted(self):
        """The OLED's lit: music plays on party mode's player, which says when each bit of it is heard."""
        return self.oled is not None

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
            return
        leds = self.glow_setting("glow_on") == "On"
        if leds:
            self.glow_pick("glow_on", "Off")
        self.oled_start()
        if self.oled is not None:
            self.oled.hello()                          # (its bars up once: it's lit)
            self.oled_catch()
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
        self.oled = OledBars(screen)
        print(f"oled: the OLED's on ({spi})", flush=True)

    def oled_spi_on(self):
        """SPI turned on in config.txt, in the LED backlight's own part of it (glow.py: uninstall.sh takes it out),
        unless that's there already: True if it had to be put in."""
        path = next((p for p in getattr(self, "glow_configs", CONFIG_TXT) if read_file(p, None) is not None), None)
        if path is None or BLOCK[0] in read_file(path):
            return False
        return turn_spi_on(path, ["dtparam=spi=on"])

    def oled_stop(self):
        o, self.oled = self.oled, None
        if o is not None:
            o.close()
            print("oled: the OLED's off", flush=True)
        self.oled_note = ""

    def oled_heard(self, pcm, t, gain):
        """(Party mode's player, as it plays.) Sound, its first sample heard at t (its clock: the leader's, in another's
        party), as loud as the volume's made it (gain)."""
        o = self.oled
        if o is None:
            return
        if self.party is not None and not self.party.get("lead"):
            t -= self.party_clock() - time.monotonic()  # (the leader's clock, as this one's)
        o.heard(pcm, t, gain)

    def oled_catch(self):
        """The OLED's just been turned on, and music's playing on the plain player, which says nothing of its sound:
        moved to party mode's player, from where it is, after a moment's quiet."""
        p = self.proc
        plain = (p is not None and not isinstance(p, PartyProc) and self.kind in LISTEN_KINDS and p.poll() is None
                 and 0 <= self.qi < len(self.queue))
        if not plain or self.party is not None or self.paused:
            return
        pos = (self.pos or 0.0) if self.kind == "audio" else 0.0
        self.play(self.queue, self.qi, start=max(0.0, pos), show=False)

    def web_oled_row(self):
        """Its row in the web page's Settings (None where there can't be one)."""
        if not self.oled_can():
            return None
        row = dict(key="oled", label=OLED_LABEL, kind="choice", value=self.setting("oled") or "Off",
                   choices=list(OLED_CHOICES), note="The OLED HAT on the Pi's pins: bars that move with your music.")
        if self.oled_note:
            restart = self.oled_note == RESTART
            row.update(status="Restart the Pi to turn its SPI on" if restart else self.oled_note,
                       tone="" if restart else "bad")
        return row
