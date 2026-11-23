"""Settings > WiFi > Hotspot (pitato/hotspot.py has how it's done): turning it on and off, its page on the Pi (its name
and password, to read for a phone), the web page's rows for it, and the newer one another of yours has, taken."""
import ipaddress
import threading
import time

from ..theme import ACCENT, BODY, DONE, MUTED, TEXT, WARN
from ..config import WEB_PORT
from ..system import nm, wifi_dev
from ..hotspot import (NAME_MOST, PASS_MOST, ask_peer, can_host, heard_near, host_address, host_off, host_on, hosting,
                       join_keep, join_now, made_hotspot, name_why, newer, nm_said, password_why, read_hotspot,
                       save_hotspot, tag_of)

HOTSPOT_SETTLE = 8.0         # seconds after start-up before a hotspot left on is turned on again (NetworkManager's
                             # had a moment by then)
HOTSPOT_ASK_AGAIN = 600.0    # seconds before another of yours is asked for its hotspot again, when it didn't give it


class HotspotScreen:
    """Settings > WiFi > Hotspot."""

    def hotspot_init(self):
        self.hotspot_h = None        # yours: {"name", "password", "v", "id"} (None: not read yet; False: none yet)
        self.hotspot_st = {"busy": False, "status": None, "bad": False, "up": False, "addr": "", "asking": False,
                           "asked": {}}   # (addr: this Pi's address on it, for a phone's web page)
        self.hotspot_lock = threading.Lock()   # (kept one at a time...)
        self.hotspot_joins = threading.Lock()  # (...and kept as a network to join, the latest last)

    # -- yours, and whether it's on ------------------------------------------------------------------------------------
    def hotspot_get(self, make=False):
        """Your hotspot (its name and password, the same on all your Pietatos), or None: there's none yet. make: one
        made up now, if there's none."""
        if self.hotspot_h is None:
            self.hotspot_h = read_hotspot() or False   # (read once: it's only changed here)
        if not self.hotspot_h and make:
            self.hotspot_keep(made_hotspot())
        return self.hotspot_h or None

    def hotspot_keep(self, h):
        """A hotspot (new here, or newer from another of yours): kept, and kept as a network to join by itself (in the
        background: NetworkManager takes a moment)."""
        with self.hotspot_lock:
            self.hotspot_h = h
            try:
                save_hotspot(h)
            except OSError as ex:
                print(f"hotspot: couldn't keep it ({ex})", flush=True)
        threading.Thread(target=self.hotspot_joinable, daemon=True, name="hotspot-join").start()

    def hotspot_joinable(self):
        with self.hotspot_joins:                       # (the one kept last, whichever thread gets here first)
            h = self.hotspot_h
            ok, err = join_keep(h, wifi_dev()) if h else (True, "")
        if not ok:
            print(f"hotspot: couldn't keep it as a network to join ({err})", flush=True)

    def hotspot_on(self):
        """It's to be on here (Settings > WiFi > Hotspot), whether or not it's on yet."""
        return self.setting("hotspot") == "On"

    def hotspot_turn(self, on):
        """On or off (its page, the WiFi page, the web page): done in the background. False: it's busy already."""
        st = self.hotspot_st
        if st["busy"]:
            return False
        self.set_setting("hotspot", "On" if on else "Off")
        st["busy"], st["bad"], st["status"] = True, False, f"Turning the hotspot {'on' if on else 'off'}…"
        threading.Thread(target=self.hotspot_job, args=(on,), daemon=True, name="hotspot").start()
        self.dirty = True
        return True

    def hotspot_start(self):
        """At start-up: a hotspot left on, on again once NetworkManager's had a moment (or still on, from before
        Pietato was started again)."""
        if self.hotspot_on():
            self.hotspot_st["busy"], self.hotspot_st["status"] = True, "Turning the hotspot on…"
            threading.Thread(target=self.hotspot_job, args=(True, HOTSPOT_SETTLE), daemon=True,
                             name="hotspot").start()

    def hotspot_job(self, on, wait=0.0):
        st, dev = self.hotspot_st, wifi_dev()

        def failed(why):
            self.set_setting("hotspot", "Off")
            st["up"], st["bad"], st["status"] = False, True, f"Couldn't turn the hotspot on: {why}"
            self.toast(st["status"], 5)
        try:
            if wait:
                time.sleep(wait)
            if not on:
                ok, err = host_off()
                st["up"] = False
                st["status"], st["bad"] = (None, False) if ok else (f"Couldn't turn the hotspot off: {nm_said(err)}",
                                                                    True)
                self.toast("Hotspot off" if ok else st["status"], 3)
                if ok:
                    time.sleep(1)                      # (your WiFi's networks, looked for again: none meanwhile)
                    self.wifi_rescan()
                return
            h = self.hotspot_get(make=True)
            if hosting(dev):                           # (still on, from before Pietato was started again)
                st["up"], st["status"], st["addr"] = True, None, host_address(dev)
                return
            if not can_host(dev):
                return failed("this WiFi can't make one")
            ok, out, _ = nm(["radio", "wifi"], 10)
            if ok and out.strip() == "disabled":       # (WiFi off: on, for it)
                nm(["radio", "wifi", "on"], 15)
                self.wifi["radio"] = True
                time.sleep(2)
            if heard_near(h["name"]):                  # (another of yours has it on: that one's joined, not two made)
                self.set_setting("hotspot", "Off")
                join_keep(h, dev)
                ok, err = join_now()
                st["status"], st["bad"] = (None, False) if ok else (f"Couldn't join your hotspot: {nm_said(err)}",
                                                                    True)
                self.toast("Your hotspot's on already, on another of yours: joined it" if ok else st["status"], 5)
                return
            ok, err = host_on(h, dev)
            if not ok:
                return failed(nm_said(err))
            st["up"], st["status"], st["addr"] = True, None, host_address(dev)
            self.toast(f"Hotspot on: {h['name']}", 4)
        except Exception as ex:                        # (whatever nmcli does: said, and it's off)
            failed(f"{ex}"[:60])
        finally:
            st["busy"] = False
            self.wifi["ssid_t"] = 0.0
            self.dirty = True

    def hotspot_change(self, name=None, password=None):
        """A new name or password for it (its page, the web page): kept as a newer one, which your others take while
        they're on the same network. Not while it's on (the Pietatos on it would lose it). (ok, what's said)."""
        if self.hotspot_on() or self.hotspot_st["busy"]:
            return False, "Turn the hotspot off first, to change it"
        why = (name_why(name) if name is not None else "") or (password_why(password) if password is not None else "")
        if why:
            return False, why
        old = self.hotspot_get(make=True)
        name, password = name or old["name"], password or old["password"]
        if (name, password) == (old["name"], old["password"]):
            return True, "Saved"
        self.hotspot_keep(made_hotspot(name, password, before=old))
        return True, "Saved. Your other Pietatos get it over your WiFi"

    # -- your other Pietatos' ------------------------------------------------------------------------------------------
    def hotspot_tag(self):
        """What this one's beacon says of its hotspot, for your others to ask for it when theirs is older ("": none)."""
        return tag_of(self.hotspot_get())

    def hotspot_heard(self, ip, msg):
        """Another of yours' beacon (the one told straight to this one): its hotspot asked for, when it's newer than
        this one's. One question at a time; one that didn't give it isn't asked again for a while. True: asked."""
        tag = msg.get("hotspot")
        if self.setting("share") == "Off" or msg.get("id") == self.share_id or not newer(tag, self.hotspot_get()):
            return False
        port = msg.get("port")
        port = int(port) if isinstance(port, str) and port.isdigit() else port
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        if not (addr.is_private or addr.is_link_local) or isinstance(port, bool) or not isinstance(port, int) \
                or not 0 < port < 65536:
            return False
        url = f"http://[{ip}]:{port}" if addr.version == 6 else f"http://{ip}:{port}"
        st, now = self.hotspot_st, time.monotonic()
        if st["asking"] or now < st["asked"].get(url, 0.0):
            return False
        st["asking"], st["asked"][url] = True, now + HOTSPOT_ASK_AGAIN
        threading.Thread(target=self.hotspot_ask, args=(url,), daemon=True, name="hotspot-ask").start()
        return True

    def hotspot_ask(self, url):
        try:
            h = ask_peer(url)
            if h is not None and newer(tag_of(h), self.hotspot_get()):
                self.hotspot_keep(h)
                self.hotspot_st["asked"].pop(url, None)
                print(f"hotspot: {h['name']} (its version {h['v']}), from {url}", flush=True)
        except Exception as ex:
            print(f"hotspot: asking {url}: {ex!r}", flush=True)
        finally:
            self.hotspot_st["asking"] = False

    def web_hotspot(self):
        """GET /api/hotspot (from your network only: webui.py): its name and password, for another of yours (with
        Settings > Share with other Pietatos on). (The control server's thread.)"""
        h = self.hotspot_get()
        if self.setting("share") == "Off" or not h:
            return {"ok": False, "error": "Sharing is off" if h else "No hotspot yet"}
        return {"ok": True, "hotspot": dict(h)}

    # -- the web page --------------------------------------------------------------------------------------------------
    def web_hotspot_rows(self):
        """Settings > WiFi's rows for it: on or off, its name, and its password (never shown: only that it has one)."""
        h, st, on = self.hotspot_get(), self.hotspot_st, self.hotspot_on()
        status, tone = st["status"] or "", "busy" if st["busy"] else "bad" if st["bad"] else ""
        if not status and on and st["up"] and h:
            status, tone = f"On: {h['name']}", "ok"
        return [{"key": "hotspot", "label": "Hotspot", "kind": "choice", "value": "On" if on else "Off",
                 "choices": ["On", "Off"], "status": status, "tone": tone,
                 "note": "The Pi makes a WiFi of its own, for your other Pietatos when you're away from yours: they "
                         "join it by themselves. It's off your WiFi meanwhile."},
                {"key": "hs_name", "label": "Hotspot's name", "kind": "text", "value": h["name"] if h else "",
                 "max": NAME_MOST, "placeholder": "Made up the first time it's on"},
                {"key": "hs_password", "label": "Hotspot's password", "kind": "secret", "set": bool(h), "keep": True,
                 "max": PASS_MOST, "note": "The Pi's screen shows it, for a phone: Settings > WiFi > Hotspot."}]

    def web_set_hotspot(self, value, cmd):
        if value not in ("On", "Off"):
            return {"error": "That isn't one of its choices"}
        if (value == "On") == self.hotspot_on() and not self.hotspot_st["busy"]:
            return {"ok": True}
        if not self.hotspot_turn(value == "On"):
            return {"error": "One thing at a time. Try again in a moment"}
        return {"ok": True}

    def web_set_hs_name(self, value, cmd):
        if not isinstance(value, str):
            return {"error": "What's that?"}
        ok, said = self.hotspot_change(name=value.strip())
        return {"ok": True, "said": said} if ok else {"error": said}

    def web_set_hs_password(self, value, cmd):
        ok, said = self.hotspot_change(password=value) if isinstance(value, str) else (False, "What's that?")
        return {"ok": True, "said": said} if ok else {"error": said}

    # -- its page on the Pi: Settings > WiFi > Hotspot -----------------------------------------------------------------
    def hotspot_open(self):
        self.hotspot_get(make=True)                    # (its name and password, made up now if there are none: to read)
        self.set_page, self.set_sel = "hotspot", 0
        self.dirty = True

    def hotspot_rows(self):
        return [("hs_on", "Hotspot", ["On", "Off"]), ("hs_name", "Name", None), ("hs_pass", "Password", None)]

    def hotspot_value(self, key):
        h = self.hotspot_get()
        if key == "hs_on":
            return "On" if self.hotspot_on() else "Off"
        return (h["name"] if key == "hs_name" else h["password"]) if h else ""

    def hotspot_said(self, page=True):
        """How it is, and its colour: its page's top right (page), or the WiFi page's."""
        st, h = self.hotspot_st, self.hotspot_get()
        if st["status"]:
            return st["status"], WARN if st["bad"] else ACCENT
        on = self.hotspot_on()
        words = ("On" if on else "Off") if page else ("Hotspot on" if on else "Hotspot off")
        if on and st["up"] and h:
            return f"{words}: {h['name']}", DONE
        return words, ACCENT if on else MUTED

    def hotspot_note(self):
        """Its page's line at the bottom: your others on it (while it's on), or where a phone on it finds the web page,
        or what it's for."""
        st = self.hotspot_st
        if self.hotspot_on() and st["up"]:
            names = [p["name"] for p in self.pie.peer_rows(within=60)]
            if names:
                return "On it: " + ", ".join(names)
            if st["addr"]:
                return f"A phone on it finds the web page at {st['addr']}:{WEB_PORT}"
        return "Your other Pietatos join it by themselves, away from your WiFi"

    def hotspot_hints(self, key):
        if key == "hs_on":
            return [("◀▶", "On / off"), ("B", "Back")]
        return ([] if self.hotspot_on() else [("A", "Change")]) + [("B", "Back")]

    def hotspot_row(self, d, key, label, extra, mid, on, y, rh):
        F, W = self.fonts, self.fb.w
        d.text((30, mid), label, font=F["row"], fill=TEXT if on else BODY, anchor="lm")
        value = self.hotspot_value(key)
        x1 = W - 28
        if extra and on:
            d.text((x1, mid), "▶", font=F["small"], fill=ACCENT, anchor="rm")
            x1 -= 22
        shown = self.fit(d, value, F["row"], W - 260)
        d.text((x1, mid), shown, font=F["row"], fill=ACCENT if on or (key == "hs_on" and value == "On") else MUTED,
               anchor="rm")
        if extra and on:
            x0 = x1 - d.textlength(shown, font=F["row"])
            d.text((x0 - 10, mid), "◀", font=F["small"], fill=ACCENT, anchor="rm")
            self.tap_arrows(y, y + rh, x0 - 10, W - 28)

    def press_hotspot(self, name, repeat, key, extra):
        if repeat:
            return None
        if name == "b":
            self.set_page = "wifi"
            keys = [r[0] for r in self.settings_rows()]
            self.set_sel = keys.index("hotspot") if "hotspot" in keys else 0
        elif key == "hs_on" and name in ("left", "right", "a"):
            if not self.hotspot_turn(not self.hotspot_on()):
                self.toast("One thing at a time", 2)
        elif key in ("hs_name", "hs_pass") and name == "a":
            if self.hotspot_on() or self.hotspot_st["busy"]:
                self.toast("Turn the hotspot off first, to change it", 3)
            else:
                h = self.hotspot_get(make=True)
                if key == "hs_name":
                    self.open_keyboard("The hotspot's name", h["name"], lambda t: self.hotspot_typed(name=t),
                                       limit=NAME_MOST)
                else:
                    self.open_keyboard("Its password (8 letters or more)", h["password"],
                                       lambda t: self.hotspot_typed(password=t), strip=False, limit=PASS_MOST)
        self.dirty = True
        return None

    def hotspot_typed(self, name=None, password=None):
        self.toast(self.hotspot_change(name=name, password=password)[1], 4)
