"""Settings > WiFi > Hotspot (pitato/hotspot.py, screens/hotspot.py): a WiFi of its own, for your other Pietatos away
from yours. Its name and password: made up the first time they're needed (Pietato-K7MP, and three fours of letters
that can't be mistaken for each other), kept in hotspot.txt (only for you to read, and never shown or handed out by
the web page), changed on its page or the web page (a newer version each time; refused while it's on, and when WPA2
or a settings file wouldn't take them). Turned on: NetworkManager makes it, on 2.4 GHz, with WPA2 alone, the addresses
handed out and a way out for what's said to everyone; the WiFi page has no networks to join meanwhile, the status bar
says Hotspot, and it's on again at start-up (or still on, from before Pietato was started again). Not made when this
WiFi can't, nor when another of yours has it on already (that one's joined); turned off with the WiFi. Each of yours
keeps it as a network to join by itself, after your own WiFi and for as long as it's there, changed in place. Passed
between them: a beacon told straight to each says which it has, and one with an older one (or none) asks the one
with the newer one for it, at its web page (from your network only: another of yours, its own process here); once a
question at a time, a Pietato that didn't give it not asked again for a while, nothing asked with sharing off, nor of
an address outside your network, nor of one that sends it elsewhere. On the web page, Settings > WiFi has it (its
password only as there being one), and the networks go while it's on. The Fish Tank's and an ESP32's parts of this are
test_fishtank's and test_esp32_led's."""
import http.server, json, os, re, shutil, socket, stat, subprocess, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, SP); sys.path.insert(0, TESTS); sys.path.insert(0, ROOT)
import pietato_all as g
from PIL import Image

S = SP + "/t_hotspot"
shutil.rmtree(S, ignore_errors=True)
H, DEN = S + "/gpi", S + "/den"
for h in (H, DEN):
    for d in ("Music", "Videos", "Pictures", "Documents"):
        os.makedirs(f"{h}/{d}")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PADS_FILE = S + "/pads.json"
g.COMPUTERS_FILE = S + "/computers.json"; g.NET_ROOT = S + "/net"
open(g.STATE_FILE, "w").write('{"settings": {}}')
g.home_dir = lambda: H
import gk_static; gk_static.use_home(g, H)
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "1", "returncode": 0, "stderr": ""})()
g.list_devices = lambda: []
socket.gethostname = lambda: "gpi"
os.makedirs(SP + "/out", exist_ok=True)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


def until(cond, sec=8):
    t = time.monotonic()
    while not cond() and time.monotonic() - t < sec:
        time.sleep(0.05)
    return cond()


# ---- the module itself -----------------------------------------------------------------------------------------------
made = g.made_hotspot()
check(f"made up: a name like Pietato-K7MP, a password of three fours of letters, version 1 ({made['name']}, "
      f"{made['password']})", re.fullmatch(r"Pietato-[A-HJ-NP-Z2-9]{4}", made["name"])
      and re.fullmatch(r"[a-hj-km-np-z2-9]{4}-[a-hj-km-np-z2-9]{4}-[a-hj-km-np-z2-9]{4}", made["password"])
      and made["v"] == 1 and re.fullmatch(r"[0-9a-f]{8}", made["id"]) and g.name_ok(made["name"])
      and g.password_ok(made["password"]))
check("...another each time", len({g.made_hotspot()["password"] for _ in range(20)}) == 20)
nxt = g.made_hotspot("Trail", "trail-mix-99", before=made)
check(f"...one changed: the next version ({nxt['v']})", nxt["v"] == 2 and nxt["name"] == "Trail"
      and nxt["id"] != made["id"])
check("names a WiFi can have, and a settings file keep", g.name_ok("Pietato-K7MP") and g.name_ok("Rig 2")
      and g.name_ok("Café ☕") and not g.name_ok("") and not g.name_ok(" Rig") and not g.name_ok("Rig  2")
      and not g.name_ok("x" * 33) and not g.name_ok("ééééééééééééééééé") and not g.name_ok("a\tb") and not g.name_ok(5))
check("passwords WPA2 takes", g.password_ok("12345678") and g.password_ok("x" * 63) and g.password_ok("a b#c=d!")
      and not g.password_ok("1234567") and not g.password_ok("x" * 64) and not g.password_ok("pässword1")
      and not g.password_ok(" leading1") and not g.password_ok("two  gaps") and not g.password_ok(None))
check(f"...said why not ({g.password_why('short')!r}, {g.name_why(' x')!r})",
      g.password_why("short") == "A WiFi password is 8 letters or more" and "letters" in g.password_why("two  gaps")
      and g.password_why("12345678") == "" and "32" in g.name_why(" x"))
check("which is newer: the version, then its word; none here yet, any", g.newer("2.00000000", made)
      and not g.newer(g.tag_of(made), made) and g.newer("1.ffffffff", dict(made, id="0fffffff"))
      and not g.newer("1.00000000", dict(made, id="0fffffff")) and g.newer("1.00000000", None)
      and not any(g.newer(t, None) for t in ("", "0.12345678", "2.1234567", "2.ABCDEF12", "x", None, 3, "2.123456789")))
check("...what another says, kept to what makes sense", g.hotspot_clean(dict(made, v="3"))["v"] == 3
      and g.hotspot_clean(dict(made, v=True)) is None and g.hotspot_clean(dict(made, password="short")) is None
      and g.hotspot_clean(dict(made, id="nothex12")) is None and g.hotspot_clean([made]) is None)

# ---- a pretend NetworkManager ----------------------------------------------------------------------------------------
NM = {"profiles": {"HomeNet": {"ssid": "HomeNet"}}, "active": "HomeNet", "radio": True, "ap": "yes",
      "air": ["HomeNet", "Cafe"], "fail_up": "", "hosting": ""}
nmlog = []
HOST, JOIN = g.HOST, g.JOIN


def fake_nm(args, timeout=20):
    nmlog.append(list(args))
    p = NM["profiles"]
    if args[:2] == ["radio", "wifi"]:
        if len(args) == 3:
            NM["radio"] = args[2] == "on"
            if not NM["radio"]:
                NM["active"], NM["hosting"] = None, ""
            return True, "", ""
        return True, "enabled\n" if NM["radio"] else "disabled\n", ""
    if args[:3] == ["-t", "-f", "WIFI-PROPERTIES.AP"]:
        return True, f"WIFI-PROPERTIES.AP:{NM['ap']}\n", ""
    if "wifi" in args and "list" in args:
        if args[2] == "SSID":
            return True, "".join(s.replace(":", "\\:") + "\n" for s in NM["air"]), ""
        return True, "".join(f"{'*' if s == NM['active'] else ' '}:{s}:70:WPA2\n" for s in NM["air"]), ""
    if args[-2:] == ["connection", "show"]:
        return True, "".join(f"{n}:802-11-wireless\n" for n in p), ""
    if args[:2] == ["-g", "802-11-wireless.ssid"]:
        return True, p[args[-1]]["ssid"] + "\n", ""
    if args[:3] == ["connection", "delete", "id"]:
        p.pop(args[3], None)
        return True, "", ""
    if args[:2] == ["connection", "add"]:
        kv = dict(zip(args[2::2], args[3::2]))
        p[kv["con-name"]] = dict(kv)
        return True, f"Connection '{kv['con-name']}' successfully added.\n", ""
    if args[:3] == ["connection", "modify", "id"]:
        if args[3] not in p:
            return False, "", f"Error: unknown connection '{args[3]}'."
        kv = dict(zip(args[4::2], args[5::2]))
        p[args[3]].update(kv)
        p[args[3]]["ssid"] = kv.get("802-11-wireless.ssid", p[args[3]]["ssid"])
        return True, "", ""
    if args[:3] == ["connection", "up", "id"]:
        prof = p.get(args[3])
        if NM["fail_up"] or prof is None:
            return False, "", NM["fail_up"] or f"Error: unknown connection '{args[3]}'."
        if prof.get("802-11-wireless.mode") == "ap":
            time.sleep(0.3)                            # (a moment, as it takes one)
            NM["hosting"], NM["active"] = prof["ssid"], None
        else:
            NM["hosting"], NM["active"] = "", args[3]
        return True, "Connection successfully activated\n", ""
    if args[:3] == ["connection", "down", "id"]:
        if NM["hosting"] and args[3] == HOST:
            NM["hosting"], NM["active"] = "", "HomeNet"
            return True, "", ""
        return False, "", f"Error: '{args[3]}' is not an active connection."
    return False, "", "unexpected " + " ".join(args)


def fake_run_out(cmd, timeout=3):
    if cmd[:2] == ["iw", "dev"] and cmd[3:] == ["info"]:
        return (f"Interface wlan0\n\tifindex 3\n\tssid {NM['hosting']}\n\ttype AP\n\twiphy 0\n" if NM["hosting"]
                else "Interface wlan0\n\tifindex 3\n\ttype managed\n")
    if cmd[:2] == ["iw", "dev"] and cmd[3:] == ["link"]:
        a = NM["active"]
        return (f"Connected to aa:bb:cc:dd:ee:ff (on wlan0)\n\tSSID: {NM['profiles'][a]['ssid']}\n" if a
                else "Not connected.")
    if cmd[:4] == ["ip", "-4", "-o", "addr"]:
        ip = "10.42.0.1/24 brd 10.42.0.255" if NM["hosting"] else "192.168.1.40/24 brd 192.168.1.255"
        return f"3: wlan0    inet {ip} scope global dynamic noprefixroute wlan0\\       valid_lft forever"
    return ""


g.nm = fake_nm
g.run_out = fake_run_out
g.wifi_dev = lambda: "wlan0"
g.HOTSPOT_SETTLE = 0.0


def since(n):
    return nmlog[n:]


# ---- this one --------------------------------------------------------------------------------------------------------
class FB:
    w, h = 640, 480; real_w, real_h = 640, 480; last = None
    def show(self, img): FB.last = img.copy()
    def show_part(self, img, box): FB.last = img.copy()
    def blank_outside(self, box): pass
    def invalidate(self): pass
    def close(self): pass


g.Framebuffer = FB
shots = {}


def snap(name):
    m.dirty = True; m.flush(); shots[name] = FB.last


def idle(sec=8):
    return until(lambda: not m.hotspot_st["busy"] and not m.wifi["busy"], sec)


def rows():
    return [r[0] for r in m.settings_rows()]


m = g.Media(); m.enter()
control = g.Control()
server = g.serve_control(m, control, port=0, key="k" * 32)
m.home_sel = [a[0] for a in m.home_apps()].index("Settings"); m.press("a")
root = rows()
check(f"Settings: WiFi, and no hotspot of its own on its first page ({root[:3]})", root[0] == "wifi"
      and "hotspot" not in root)
m.set_sel = 0; m.press("a")
idle()
check(f"Settings > WiFi: the switch, then the hotspot, then the networks; the first of them picked ({rows()}, "
      f"{m.set_sel})", rows()[:4] == ["radio", "hotspot", "net", "net"] and rows()[-1] == "other" and m.set_sel == 2)
snap("wifi")
check("...no hotspot yet: none made just for that", not os.path.exists(H + "/hotspot.txt") and m.hotspot_get() is None)
m.set_sel = 1; m.press("a")
h = m.hotspot_get()
check(f"A on it: its own page, its name and password made up now, to read ({m.set_page}, {rows()}, {h and h['name']})",
      m.set_page == "hotspot" and rows() == ["hs_on", "hs_name", "hs_pass"] and h and h["v"] == 1
      and m.hotspot_value("hs_name") == h["name"] and m.hotspot_value("hs_pass") == h["password"]
      and m.hotspot_value("hs_on") == "Off")
kept = open(H + "/hotspot.txt").read()
mode = stat.S_IMODE(os.stat(H + "/hotspot.txt").st_mode)
check(f"...kept in hotspot.txt, for you alone to read ({oct(mode)})", f"name = {h['name']}" in kept
      and f"password = {h['password']}" in kept and "version = 1" in kept and not mode & 0o077
      and g.read_hotspot() == h)
check("...and kept as a network to join by itself, after your own and as long as it's there", until(
    lambda: JOIN in NM["profiles"]) and NM["profiles"][JOIN].get("connection.autoconnect-priority") == "-10"
      and NM["profiles"][JOIN].get("connection.autoconnect-retries") == "0"
      and NM["profiles"][JOIN].get("autoconnect") == "yes" and NM["profiles"][JOIN]["ssid"] == h["name"]
      and NM["profiles"][JOIN].get("wifi-sec.psk") == h["password"])
snap("hotspot_off")

# its name and password, changed
m.set_sel = 1; m.press("a")
check(f"A on its name: the keyboard, with it in ({m.view}, {m.kb and m.kb['title']})", m.view == "keys"
      and m.kb["text"] == h["name"])
m.kb["done"]("Trail Rig"); m.view = "list"
h2 = m.hotspot_get()
check(f"...a new one: kept, the next version, and said ({h2['name']}, {h2['v']}, {m.msg!r})", h2["name"] == "Trail Rig"
      and h2["v"] == 2 and h2["password"] == h["password"] and "Saved" in m.msg and "name = Trail Rig" in
      open(H + "/hotspot.txt").read())
check("...the network to join, changed in place", until(lambda: NM["profiles"][JOIN]["ssid"] == "Trail Rig")
      and ["connection", "modify", "id", JOIN] == next(a[:4] for a in reversed(nmlog)
                                                       if a[:2] == ["connection", "modify"]))
m.set_sel = 2; m.press("a")
m.kb["done"]("short"); m.view = "list"
check(f"its password: too short, said, and not taken ({m.msg!r})", m.msg == "A WiFi password is 8 letters or more"
      and m.hotspot_get() == h2)
m.press("a")
check("...the keyboard keeps what you type as it is (spaces too)", m.kb["strip"] is False)
m.kb["done"]("sand dune 42"); m.view = "list"
h3 = m.hotspot_get()
check(f"...one it takes: the next version ({h3['v']})", h3["password"] == "sand dune 42" and h3["v"] == 3
      and until(lambda: NM["profiles"][JOIN].get("wifi-sec.psk") == "sand dune 42"))

# on
n = len(nmlog)
m.set_sel = 0; m.press("right")
check(f"◀▶: on, at once, and it says so while it's made ({m.setting('hotspot')}, {m.hotspot_st['status']!r})",
      m.setting("hotspot") == "On" and m.hotspot_st["busy"] and "Turning the hotspot on" in m.hotspot_st["status"])
idle()
add = next((a for a in since(n) if a[:2] == ["connection", "add"]), [])
kv = dict(zip(add[2::2], add[3::2]))
check(f"...NetworkManager makes it: on 2.4 GHz, WPA2 alone, the addresses handed out, a way out for what's said to "
      f"everyone, not on by itself at start ({kv})", kv.get("802-11-wireless.mode") == "ap"
      and kv.get("802-11-wireless.band") == "bg" and kv.get("ipv4.method") == "shared"
      and kv.get("ipv4.routes") == "255.255.255.255/32" and kv.get("autoconnect") == "no"
      and kv.get("ssid") == "Trail Rig" and kv.get("wifi-sec.psk") == "sand dune 42"
      and kv.get("wifi-sec.key-mgmt") == "wpa-psk" and kv.get("wifi-sec.proto") == "rsn"
      and kv.get("wifi-sec.pmf") == "disable" and kv.get("con-name") == HOST and kv.get("ifname") == "wlan0")
check(f"...made afresh, then turned on ({[a[:3] for a in since(n) if a[0] == 'connection']})",
      [a[:4] for a in since(n) if a[:2] in (["connection", "delete"], ["connection", "up"])]
      == [["connection", "delete", "id", HOST], ["connection", "up", "id", HOST]])
check(f"...on: said, here and on its page ({m.msg!r}, {m.hotspot_said()})", m.hotspot_st["up"]
      and NM["hosting"] == "Trail Rig" and m.msg == "Hotspot on: Trail Rig"
      and m.hotspot_said()[0] == "On: Trail Rig" and m.hotspot_st["status"] is None)
check(f"...a phone on it: where the web page is ({m.hotspot_note()!r})",
      m.hotspot_note() == "A phone on it finds the web page at 10.42.0.1:5432")
snap("hotspot_on")
m.press("b")
check(f"B: the WiFi page, on its row; no networks to join while it's on ({rows()}, {m.set_sel})",
      m.set_page == "wifi" and rows() == ["radio", "hotspot"] and m.set_sel == 1
      and m.hotspot_said(page=False)[0] == "Hotspot on: Trail Rig")
snap("wifi_hotspot")
n = len(nmlog)
m.press("x")
check(f"...X looks for none ({m.msg!r})", not [a for a in since(n) if "list" in a] and "hotspot off" in m.msg)
check("...the status bar: Hotspot, not No WiFi", m.status_signature()[2] is True)
m.press("a"); m.set_sel = 1; m.press("a")
check(f"its name, while it's on: not changed under the Pietatos on it ({m.msg!r})", m.view != "keys"
      and "off first" in m.msg)
check(f"...nor from the web page ({m.web_settings_do({'cmd': 'settings', 'key': 'hs_name', 'value': 'Other'})})",
      "off first" in m.web_settings_do({"cmd": "settings", "key": "hs_name", "value": "Other"}).get("error", "")
      and m.hotspot_get() == h3)

# the web page
secs = {s["id"]: s for s in m.web_settings()["sections"]}
wifi = {r["key"]: r for r in secs["wifi"]["rows"]}
check(f"the web page's Settings > WiFi: it, its name and its password ({list(wifi)})",
      list(wifi) == ["wifi", "hotspot", "hs_name", "hs_password"])
check(f"...on: says so, and no networks to join meanwhile ({wifi['wifi']['hosting']}, {wifi['hotspot']['status']})",
      wifi["wifi"]["hosting"] == "Trail Rig" and wifi["wifi"]["nets"] == [] and wifi["wifi"]["here"] == ""
      and wifi["hotspot"]["value"] == "On" and wifi["hotspot"]["status"] == "On: Trail Rig"
      and wifi["hotspot"]["tone"] == "ok")
check("...its password: only that there's one, and it can't be taken off", wifi["hs_password"]["set"] is True
      and wifi["hs_password"]["keep"] is True and wifi["hs_password"]["kind"] == "secret"
      and "sand dune 42" not in json.dumps(m.web_settings()) and wifi["hs_name"]["value"] == "Trail Rig")
said = m.web_settings_do({"cmd": "settings", "key": "wifi", "value": {"do": "connect", "ssid": "Cafe"}})
check(f"...a network joined from there while it's on: refused ({said})", "hotspot off" in said.get("error", ""))

# off
m.press("b")
n = len(nmlog)
m.set_sel = 1; m.press("left")
idle()
check(f"◀▶ on the WiFi page: off ({[a[:4] for a in since(n) if a[0] == 'connection']}, {m.msg!r})",
      m.setting("hotspot") == "Off" and not m.hotspot_st["up"] and ["connection", "down", "id", HOST] in since(n)
      and NM["active"] == "HomeNet" and m.msg in ("Hotspot off", ""))
check(f"...your networks again, looked for afresh ({rows()[:3]})", until(lambda: "net" in rows())
      and [a for a in since(n) if "list" in a])

# at start-up
m.set_setting("hotspot", "On")
n = len(nmlog)
m.hotspot_start()
idle()
check("left on: on again at start-up", m.hotspot_st["up"] and NM["hosting"] == "Trail Rig"
      and ["connection", "up", "id", HOST] in since(n))
m.hotspot_st["up"] = False
n = len(nmlog)
m.hotspot_start()
idle()
check("...still on, from before Pietato was started again: left as it is", m.hotspot_st["up"]
      and not [a for a in since(n) if a[:2] in (["connection", "add"], ["connection", "up"])])
m.set_sel = 0; m.press("a")                        # (WiFi off: no hotspot either)
idle()
check(f"WiFi off: the hotspot's off too ({m.setting('hotspot')})", not m.wifi["radio"] and m.setting("hotspot") == "Off"
      and not m.hotspot_st["up"])
m.press("a")
idle()
NM["hosting"] = ""

# when it isn't made
NM["ap"] = "no"
m.hotspot_turn(True)
idle()
check(f"this WiFi can't make one: off, and said ({m.hotspot_st['status']!r})", m.setting("hotspot") == "Off"
      and m.hotspot_st["bad"] and m.hotspot_st["status"] == "Couldn't turn the hotspot on: this WiFi can't make one"
      and m.hotspot_said()[0] == m.hotspot_st["status"])
row = next(r for s in m.web_settings()["sections"] for r in s["rows"] if r["key"] == "hotspot")
check(f"...the web page says so too ({row['status']}, {row['tone']})", row["tone"] == "bad"
      and "can't" in row["status"])
NM["ap"] = "yes"
NM["fail_up"] = "Error: Connection activation failed: (10) The device could not be readied for configuration."
m.hotspot_turn(True)
idle()
check(f"...NetworkManager couldn't: off, and why, shortly ({m.hotspot_st['status']!r})", m.setting("hotspot") == "Off"
      and m.hotspot_st["status"] == "Couldn't turn the hotspot on: the device could not be readied for configuration"
      and not m.hotspot_st["up"])
NM["fail_up"] = ""
NM["air"].append("Trail Rig")
n = len(nmlog)
m.hotspot_turn(True)
idle()
check(f"another of yours has it on already: that one joined, not a second made ({m.msg!r})",
      m.setting("hotspot") == "Off" and not m.hotspot_st["up"] and ["connection", "up", "id", JOIN] in since(n)
      and not [a for a in since(n) if a[:2] == ["connection", "add"] and HOST in a] and "joined it" in m.msg
      and NM["active"] == JOIN)
NM["air"].remove("Trail Rig"); NM["active"] = "HomeNet"
said = m.web_settings_do({"cmd": "settings", "key": "hotspot", "value": "Sometimes"})
check(f"the web page: on or off, nothing else ({said})", "error" in said)
said = m.web_settings_do({"cmd": "settings", "key": "hs_password", "value": "dust-devil-7"})
check(f"...its password, changed there ({said}, {m.hotspot_get()['v']})", said.get("ok")
      and m.hotspot_get()["password"] == "dust-devil-7" and m.hotspot_get()["v"] == 4)
said = m.web_settings_do({"cmd": "settings", "key": "hs_name", "value": "  Trail Rig 2 "})
check(f"...its name ({said}, {m.hotspot_get()['name']})", said.get("ok") and m.hotspot_get()["name"] == "Trail Rig 2"
      and m.hotspot_get()["v"] == 5)
said = m.web_settings_do({"cmd": "settings", "key": "hs_password", "value": "naïve-pass"})
check(f"...one WPA2 won't take: refused ({said})", "error" in said and m.hotspot_get()["v"] == 5)

# ---- your other Pietatos ---------------------------------------------------------------------------------------------
mine = m.hotspot_get()
full, everyone = m.share_beacon(m.own_name(), full=True), m.share_beacon(m.own_name())
check(f"its beacon told straight to each of yours says which it has ({full.get('hotspot')}); the one to everyone, "
      f"nothing", full.get("hotspot") == f"5.{mine['id']}" and "hotspot" not in everyone)
check("...asked, it gives it", m.web_hotspot() == {"ok": True, "hotspot": mine})
m.set_setting("share", "Off")
check(f"...not with sharing off ({m.web_hotspot()})", m.web_hotspot()["ok"] is False
      and not m.hotspot_heard("10.0.0.8", {"pietato": 1, "id": "x", "port": 5432, "hotspot": "99.12345678"}))
m.set_setting("share", "On")

import logging; logging.getLogger("werkzeug").setLevel(logging.ERROR)
sys.path.append(ROOT + "/pitato")
import webui
webui.HOME = H; webui.STATIC = H + "/.pietato/static"; os.makedirs(webui.STATIC, exist_ok=True)
open(S + "/control-key", "w").write("k" * 32)
webui.STATE_FILE = g.STATE_FILE
webui.CONTROL = ("127.0.0.1", server.server_address[1]); webui.CONTROL_KEY = S + "/control-key"
client = webui.app.test_client()
near = client.get("/api/hotspot", base_url="http://10.0.0.30:5432", environ_base={"REMOTE_ADDR": "10.0.0.31"})
check(f"its web page: another of yours on your network asks, and has it ({near.status_code})", near.status_code == 200
      and g.hotspot_clean(near.get_json().get("hotspot")) == mine)
far = client.get("/api/hotspot", base_url="http://10.0.0.30:5432", environ_base={"REMOTE_ADDR": "8.8.8.8"})
check(f"...nothing from outside your network ({far.status_code})", far.status_code == 403)
open(webui.STATIC + "/webui.txt", "w").write("password = sesame\n")
near = client.get("/api/hotspot", base_url="http://10.0.0.30:5432", environ_base={"REMOTE_ADDR": "10.0.0.31"})
check(f"...the page's password isn't asked of yours for it, as for the rest they ask each other ({near.status_code})",
      near.status_code == 200)
os.remove(webui.STATIC + "/webui.txt")
got = client.get("/api/file?folder=home&path=hotspot.txt", headers={"X-Pitato-Page": "1"})
check(f"...hotspot.txt never shown or handed out there ({got.status_code})", got.status_code == 403
      and webui.private("hotspot.txt") and g.web_private("hotspot.txt") and g.web_private("hotspot.txt~"))

# the den's Pietato, with a newer one of its own
open(DEN + "/hotspot.txt", "w").write("name = Den Rig\npassword = den-pass-77\nversion = 7\nid = abcdef01\n")
LOG = S + "/den.log"
den = subprocess.Popen([sys.executable, TESTS + "/peer_pietato.py", DEN, LOG, "den", "http://127.0.0.1:9", "gpi"],
                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
ready = den.stdout.readline().split()
DEN_URL = ready[1] if ready[:1] == ["READY"] else ""
check(f"the den's Pietato is up ({DEN_URL})", DEN_URL.startswith("http://127.0.0.1:"))


def ask_den(line):
    den.stdin.write(line + "\n"); den.stdin.flush()
    return den.stdout.readline().strip()


beacon = json.loads(ask_den("beacon"))
check(f"its beacon says it has version 7 ({beacon.get('hotspot')})", beacon.get("hotspot") == "7.abcdef01")
n = len(nmlog)
check("heard here: asked for it", m.hotspot_heard("127.0.0.1", beacon))
check(f"...taken: kept, and the network to join changed in place ({m.hotspot_get() and m.hotspot_get()['name']})",
      until(lambda: (m.hotspot_get() or {}).get("v") == 7) and m.hotspot_get()["name"] == "Den Rig"
      and m.hotspot_get()["password"] == "den-pass-77" and "version = 7" in open(H + "/hotspot.txt").read()
      and until(lambda: NM["profiles"][JOIN]["ssid"] == "Den Rig")
      and NM["profiles"][JOIN].get("wifi-sec.psk") == "den-pass-77")
check("...its beacon said again: nothing asked (it's this one's too now)", until(lambda: not m.hotspot_st["asking"])
      and not m.hotspot_heard("127.0.0.1", beacon) and full != m.share_beacon(m.own_name(), full=True)
      and m.share_beacon(m.own_name(), full=True)["hotspot"] == "7.abcdef01")
check("...an older one heard: nothing asked", not m.hotspot_heard("127.0.0.1", dict(beacon, hotspot="6.ffffffff")))
check("...this one's own beacon: nothing", not m.hotspot_heard("127.0.0.1", dict(beacon, hotspot="9.00000000",
                                                                                  id=m.share_id)))
check("...from outside your network: nothing", not m.hotspot_heard("8.8.8.8", dict(beacon, hotspot="9.00000000")))
check("...a port that isn't one: nothing", not m.hotspot_heard("127.0.0.1", dict(beacon, hotspot="9.00000000",
                                                                                 port=70000)))
check("...the den, with its sharing off: it gives none", ask_den("set share Off") and g.ask_peer(DEN_URL) is None)
ask_den("set share On")


class Elsewhere(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(302)
        self.send_header("Location", DEN_URL + "/api/hotspot")
        self.end_headers()

    def log_message(self, *a):
        pass


away = http.server.HTTPServer(("127.0.0.1", 0), Elsewhere)
threading.Thread(target=away.serve_forever, daemon=True).start()
check("...one that sends the question elsewhere: not followed", g.ask_peer(f"http://127.0.0.1:{away.server_port}")
      is None and g.ask_peer(DEN_URL) is not None)
gone = dict(beacon, hotspot="9.00000000", port=9)
check("...one that doesn't answer: asked once", m.hotspot_heard("127.0.0.1", gone)
      and until(lambda: not m.hotspot_st["asking"]) and m.hotspot_get()["v"] == 7)
check(f"...and not again for a while ({m.hotspot_st['asked'].get('http://127.0.0.1:9', 0) - time.monotonic():.0f} s)",
      not m.hotspot_heard("127.0.0.1", gone)
      and m.hotspot_st["asked"]["http://127.0.0.1:9"] - time.monotonic() > 500)
m.hotspot_st["asking"] = True
check("...one question at a time", not m.hotspot_heard("127.0.0.1", dict(beacon, hotspot="10.00000000")))
m.hotspot_st["asking"] = False
ask_den("quit")
den.wait(10)
away.shutdown()

# ---- the web page, in a browser --------------------------------------------------------------------------------------
from werkzeug.serving import make_server
web = make_server("127.0.0.1", 0, webui.app, threaded=True)
threading.Thread(target=web.serve_forever, daemon=True).start()
from playwright.async_api import async_playwright
import asyncio


async def browse():
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        pg = await b.new_page(viewport={"width": 1100, "height": 1400})

        async def wifi_now(name):
            await pg.goto("about:blank")               # (the page afresh)
            await pg.goto(f"http://127.0.0.1:{web.server_port}/#settings")
            await pg.wait_for_selector('#set-wifi .set-row[data-key="hs_password"]', timeout=10000)
            await pg.locator("#set-wifi").screenshot(path=SP + f"/out/hotspot_web_{name}.png")
            sec = pg.locator("#set-wifi")
            return {"text": await sec.inner_text(), "nets": await sec.locator("ul.nets li").count(),
                    "take_off": await sec.locator('.set-row[data-key="hs_password"] button',
                                                  has_text="Take it off").count(),
                    "on": await sec.locator('.set-row[data-key="hotspot"] button[aria-pressed="true"]').inner_text()}
        m.hotspot_turn(True)
        idle()
        on = await wifi_now("on")
        m.hotspot_turn(False)
        idle()
        until(lambda: m.wifi["nets"])
        off = await wifi_now("off")
        await b.close()
        return on, off


on, off = asyncio.run(browse())
check(f"in a browser: on, the WiFi row says it's making its own, with no networks to join ({on['on']}, "
      f"{on['nets']} networks)", on["on"] == "On" and "Making its own WiFi: Den Rig" in on["text"] and on["nets"] == 0)
check(f"...its password: only that it has one, and no Take it off ({on['take_off']})", on["take_off"] == 0
      and "den-pass-77" not in on["text"] and "Saved" in on["text"])
check(f"...off: your networks again ({off['on']}, {off['nets']} networks)", off["on"] == "Off" and off["nets"] == 2
      and "Making its own" not in off["text"])
web.shutdown()

# the pages, to look at
W_, H_ = 640, 480
order = ["wifi", "hotspot_off", "hotspot_on", "wifi_hotspot"]
out = Image.new("RGB", (W_ * 2 + 10, (H_ + 10) * 2 - 10), (80, 80, 80))
for k, name in enumerate(order):
    if shots.get(name) is not None:
        out.paste(shots[name], ((k % 2) * (W_ + 10), (k // 2) * (H_ + 10)))
out.save(SP + "/out/hotspot_pages.png")

docs = open(ROOT + "/docs/apps.md").read()
check("the docs: its part, and hotspot.txt among the settings files", "\n## Hotspot\n" in docs
      and "`hotspot.txt`" in open(ROOT + "/docs/settings.md").read()
      and "HOTSPOT_NAME" in open(ROOT + "/esp32/README.md").read())
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
