"""Settings > TV backlight (pitato/glow.py): an 8x8 grid of WS2812B LEDs behind the TV, on this Pi's GPIO 10 (SPI),
lit by the games and music of whichever of your Pietatos it follows (this one too). And the other way: this one's games
and music lighting your grids, wherever they are. A game's colours come from its emulator (told where they go: glow
ADDRESS:PORT...); music's beats from its player, when one of your grids wants them: a song or a station then plays
through party mode's player (party.py: it knows when each bit of it is heard), on its own, as if it were a party."""
import secrets
import threading
import time
import urllib.parse

from ..config import SETTINGS_DEFAULT
from ..glow import (ANY, CONFIG_TXT, GLOW_PORT, GlowOut, Grid, PI_MODEL, spi_lines, SPI_DEV, Strip, THIS_ONE,
                    turn_spi_on)
from ..handheld import is_handheld
from ..library import LISTEN_KINDS
from ..party import PartyProc, RelayServer
from ..system import is_pc, read_file, run_out
from ..theme import ACCENTS

GLOW_ROWS = [("glow_on", "LED grid", ["Off", "On"]), ("glow_follow", "Follows", None),
             ("glow_bright", "Brightness", ["10%", "25%", "50%", "100%"]), ("glow_beat", "Pulse to music", ["On", "Off"]),
             ("glow_turn", "Turn", ["0°", "90°", "180°", "270°"]), ("glow_mirror", "Mirror", ["On", "Off"]),
             ("glow_wiring", "Wiring", ["Rows", "Zigzag"])]
GLOW_KEYS = tuple(k for k, _, _ in GLOW_ROWS)
GLOW_LOOK = 2.0              # seconds between looks for your grids (and where a game's colours go)
GLOW_MUSIC = 0.5             # seconds between music's colour, said to your grids (a beat between)
GLOW_LEAD = 0.8              # seconds from a song being started to its playing, on party mode's player
GLOW_SOON = 0.05             # ...and from A to its pausing there
GLOW_QUIET = 3.0             # seconds with no station on that player: the one passed through here let go of
NAMED_KEEP = 10.0            # seconds an address's name is kept (the grid asks it for every packet)


class GlowScreen:
    """Settings > TV backlight, the grid it lights, and this one's games and music lighting your grids."""
    glow_grid = None         # this Pi's LED grid, lit (glow.Grid)
    glow_out = None          # this one's music, to your grids (glow.GlowOut)
    glow_station = None      # a station on party mode's player, for its beat: {"token", "server", "relay", "song", "quiet"}
    glow_note = ""           # why the grid isn't lit ("" when it is, or it's off)
    glow_restart = False     # SPI turned on in config.txt: the Pi needs restarting
    glow_seen = glow_music_at = 0.0
    glow_to = ()             # your grids (and this one's): [(address, port)]
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
        if cur not in (ANY, THIS_ONE) and cur not in names:
            names.append(cur)
        return [ANY] + names + [THIS_ONE]

    def glow_rows(self):
        rows = [(k, label, self.glow_follow_choices() if k == "glow_follow" else choices) for k, label, choices in GLOW_ROWS]
        rows.append(("glow_test", "Show which way is up", None))
        if self.glow_restart:
            rows.append(("glow_reboot", "Restart the Pi now", None))
        return rows

    def glow_value(self, key):
        if key == "glow_follow":
            return self.glow_follows()
        if key in ("glow_test", "glow_reboot"):
            return ""
        return self.glow_setting(key) or ""

    def glow_status(self):
        """A few words on the grid, for its Settings page."""
        if self.glow_setting("glow_on") != "On":
            return "Wire its DIN to GPIO 10 (pin 19)"
        if self.glow_note:
            return self.glow_note
        g = self.glow_grid
        if g is None:
            return ""
        src = g.now_following()
        if src is None:
            return "Waiting for a game or music"
        return "Lit by " + (self.glow_named(src) or src)

    # -- Settings > TV backlight -------------------------------------------------------------------------------------
    def press_glow_settings(self, name, repeat, key, extra):
        if name == "b":
            self.set_page, self.set_sel = None, self.settings_root_index("glow")
        elif name in ("left", "right", "a") and not repeat and extra:
            cur = self.glow_value(key)
            i = extra.index(cur) if cur in extra else 0
            self.glow_pick(key, extra[(i + (-1 if name == "left" else 1)) % len(extra)])
        elif name == "a" and not repeat and key == "glow_test":
            self.glow_test()
        elif name == "a" and not repeat and key == "glow_reboot":
            self.system_do("reboot")
        self.dirty = True
        return None

    def glow_test(self):
        if self.glow_grid is None:
            self.toast("Turn the LED grid on first", 3)
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
    def glow_start(self):
        """The grid lit (Settings > TV backlight > LED grid: On), if it can be: the Pi's SPI turned on first (in
        config.txt: then a restart), if it isn't."""
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
        self.glow_apply()
        print(f"glow: the LED grid's on ({spi})", flush=True)

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
        """What this one's beacon says of its grid (to your others: so they light it), or None."""
        g = self.glow_grid
        if g is None:
            return None
        follow = self.glow_follows()
        return {"port": g.port, "follow": "" if follow == ANY else self.own_name() if follow == THIS_ONE else follow,
                "beat": self.glow_setting("glow_beat") != "Off"}

    # -- this one's games and music, lighting your grids -------------------------------------------------------------
    def glow_targets(self):
        """Your grids that are on (this one's too): [(address, port)]."""
        out = []
        if self.glow_grid is not None:
            out.append(("127.0.0.1", self.glow_grid.port))
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
        """One of your grids (this one's too) follows this one and pulses to its music: its music played on party mode's
        player, which knows when each beat's heard."""
        if self.glow_grid is not None and self.glow_setting("glow_beat") != "Off" \
                and self.glow_follows() in (ANY, THIS_ONE):
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
            if self.glow_out is not None:
                self.glow_out.aim(self.glow_to)

    def glow_game_tick(self, run, now):
        """(A game on.) Its emulator told where its colours go, when that changes."""
        self.glow_look(now)
        spec = " ".join(f"{h}:{p}" for h, p in self.glow_to) or "-"
        if spec != getattr(run, "glow_said", "-") and getattr(run, "state", "") in ("on", "paused") \
                and hasattr(run, "send"):
            if run.send(f"glow {spec}") is not False:
                run.glow_said = spec

    def glow_beat(self, t, strength):
        """(Party mode's player, as it plays.) A beat, heard at t (its clock: the leader's, in another's party)."""
        out = self.glow_out
        if out is None or not out.to:
            return
        if self.party is not None and not self.party.get("lead"):
            t -= self.party_clock() - time.monotonic()  # (the leader's clock, as this one's)
        out.event("beat", strength, at=t)

    def glow_tick(self, now):
        """(Media mode's main loop.) Music on party mode's player: its colour, now and then, to your grids (the beats
        go as they're found); a station passed through here: its song's name, and let go of once it's not played."""
        playing = isinstance(self.proc, PartyProc) and self.kind in LISTEN_KINDS
        if playing or self.glow_out is not None:
            self.glow_look(now)
        if playing and self.glow_to and not self.paused and now - self.glow_music_at >= GLOW_MUSIC:
            if self.glow_out is None:
                self.glow_out = GlowOut()
                self.glow_out.aim(self.glow_to)
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

    # -- the web page's Settings ---------------------------------------------------------------------------------------
    def web_glow_rows(self):
        """Settings > TV backlight, on the web page (a Pi that can have a grid)."""
        rows = [dict(key=k, label=label, kind="choice", value=self.glow_value(k), choices=list(choices))
                for k, label, choices in self.glow_rows() if choices]
        rows[0]["note"] = "WS2812B LEDs, 8 by 8: DIN to GPIO 10 (pin 19), and 5 V from a supply of their own."
        rows.append({"key": "glow_status", "label": "Now", "kind": "info", "value": self.glow_status()})
        rows.append({"key": "glow_test", "label": "Which way is up", "kind": "action", "button": "Show it",
                     "disabled": self.glow_grid is None})
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

