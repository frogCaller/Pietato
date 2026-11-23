"""Settings > WiFi > Hotspot: a Pietato makes a WiFi network of its own, for your other Pietatos (a phone, an ESP32's
LEDs) when there's no WiFi around: off-road, say. NetworkManager makes it, on 2.4 GHz (all a Pi Zero 2 W and an ESP32
can join), and hands out the addresses (10.42.0.x). A Pi can't be on your WiFi while it makes one.

Its name and password are the same on all your Pietatos (hotspot.txt, in the static folder: a password, so the web
page never shows it or hands it out). Made up the first time they're needed, they go from one of yours to the others
while they're on the same network (Settings > Share with other Pietatos on): a Pietato's beacon says which it has (a
version, and a word for it), and one that has an older one asks for the newer one at that one's web page (from your
network only). Each keeps the hotspot as a network to join by itself, after your own (your WiFi comes first), so it
joins whichever of yours has it on. A hotspot that's on isn't changed under the Pietatos on it: a new name or
password is used the next time it's turned on."""
import json
import re
import secrets
import urllib.request

from .config import clean_name, edit_config, read_config, settings_glob
from .net import NoRedirect
from .system import nm, nm_fields, run_out

HOTSPOT_FILE = "hotspot.txt"
HOST = "Pietato hotspot"             # NetworkManager's name for it on the one making it...
JOIN = "Pietato hotspot (join)"      # ...and on each of yours, to join it by itself
JOIN_PRIORITY = -10                  # (after your own networks: theirs are 0)
NAME_MOST = 32                       # bytes: a WiFi's name, at most
PASS_LEAST, PASS_MOST = 8, 63        # a WiFi password's letters (WPA2's), at least and at most
LETTERS = "abcdefghjkmnpqrstuvwxyz23456789"   # a made-up name's and password's (none to mistake for another)
TAG = re.compile(r"([1-9][0-9]{0,8})\.([0-9a-f]{8})")   # what a beacon says it has: its version, and which
ASK_MOST = 4096                      # bytes: another's answer, at most
HEAD = ("# Your Pietatos' own WiFi, for away from yours (Settings > WiFi > Hotspot): its name and password, the same\n"
        "# on all of them. Change them there, or on the web page: your others get them while they're together.\n")


def made(n, upper=False):
    letters = LETTERS.upper() if upper else LETTERS
    return "".join(secrets.choice(letters) for _ in range(n))


def made_hotspot(name=None, password=None, before=None):
    """A hotspot, new: its name and password (made up where they're not given), its version one on from before's."""
    return {"name": name or "Pietato-" + made(4, upper=True),
            "password": password or "-".join(made(4) for _ in range(3)),
            "v": before["v"] + 1 if before else 1, "id": secrets.token_hex(4)}


def name_ok(name):
    """A name a WiFi can have, and a settings file keep as it is."""
    return isinstance(name, str) and clean_name(name, 64) == name and 0 < len(name.encode()) <= NAME_MOST


def password_ok(pw):
    """A password WPA2 takes (8 to 63 of the keyboard's letters), and a settings file keeps as it is."""
    return (isinstance(pw, str) and PASS_LEAST <= len(pw) <= PASS_MOST and all(32 <= ord(c) < 127 for c in pw)
            and clean_name(pw, 100) == pw)


def name_why(name):
    return "" if name_ok(name) else "A name of 1 to 32 letters, with no spaces at its ends"


def password_why(pw):
    if isinstance(pw, str) and len(pw) < PASS_LEAST:
        return "A WiFi password is 8 letters or more"
    return "" if password_ok(pw) else "8 to 63 of the keyboard's letters, with no spaces at its ends or two together"


def hotspot_clean(h):
    """A hotspot, as read or as another of yours says it: {"name", "password", "v", "id"}, or None."""
    if not isinstance(h, dict):
        return None
    v, hid = h.get("v"), h.get("id")
    if isinstance(v, str) and v.isdigit():
        v = int(v)
    if not (name_ok(h.get("name")) and password_ok(h.get("password")) and isinstance(v, int)
            and not isinstance(v, bool) and 0 < v < 10 ** 9 and isinstance(hid, str)
            and re.fullmatch(r"[0-9a-f]{8}", hid)):
        return None
    return {"name": h["name"], "password": h["password"], "v": v, "id": hid}


def read_hotspot():
    """Yours, as hotspot.txt has it, or None (none yet)."""
    cfg = read_config([settings_glob(HOTSPOT_FILE)])
    return hotspot_clean({"name": cfg.get("name"), "password": cfg.get("password"), "v": cfg.get("version"),
                          "id": cfg.get("id")})


def save_hotspot(h):
    edit_config(HOTSPOT_FILE, {"name": h["name"], "password": h["password"], "version": str(h["v"]), "id": h["id"]},
                head=HEAD, private=True)


def tag_of(h):
    """A beacon's word for a hotspot: its version, and which ("" for none)."""
    return f"{h['v']}.{h['id']}" if h else ""


def newer(tag, h):
    """A beacon's word (tag) is for a newer hotspot than h (or there's none here yet)."""
    m = TAG.fullmatch(tag) if isinstance(tag, str) else None
    return m is not None and (h is None or (int(m.group(1)), m.group(2)) > (h["v"], h["id"]))


# ---- NetworkManager --------------------------------------------------------------------------------------------------
def nm_said(err):
    """What NetworkManager said went wrong, shortly: its last line, without its "Error:" and its number."""
    line = (err or "").strip().split("\n")[-1].strip()
    line = re.sub(r"^(Error:\s*)?(Connection activation failed:\s*)?(\(\d+\)\s*)?", "", line).rstrip(".")
    return (line[:1].lower() + line[1:])[:70] or "it didn't say why"


def can_host(dev):
    """This Pi's WiFi can make a hotspot (NetworkManager says so; one that doesn't say: tried)."""
    ok, out, _ = nm(["-t", "-f", "WIFI-PROPERTIES.AP", "device", "show", dev], 10)
    return not ok or out.strip().rpartition(":")[2].strip().lower() != "no"


def hosting(dev):
    """The name of the hotspot this Pi's WiFi is making now, or "" (it's on a network, or none)."""
    info = run_out(["iw", "dev", dev, "info"])
    if not re.search(r"^\s*type AP\s*$", info, re.M):
        return ""
    m = re.search(r"^\s*ssid (.+)$", info, re.M)
    return m.group(1).strip() if m else "?"


def heard_near(name):
    """A hotspot of that name is on already, near here: another of yours has it on."""
    ok, out, _ = nm(["-t", "-f", "SSID", "device", "wifi", "list", "--rescan", "yes"], 30)
    if not ok:                                         # (scanned a moment ago: what it has)
        ok, out, _ = nm(["-t", "-f", "SSID", "device", "wifi", "list"], 20)
    return ok and any(nm_fields(line)[0] == name for line in out.splitlines())


def host_on(h, dev):
    """The hotspot made, here: (ok, what went wrong). Made afresh each time, as it is now: 2.4 GHz; WPA2 alone, and
    none of the protected frames a Pi's WiFi makes a mess of; the addresses handed out (NetworkManager's "shared");
    and a way out for what's said to everyone (255.255.255.255), as there's no other with no internet."""
    nm(["connection", "delete", "id", HOST], 15)
    ok, _, err = nm(["connection", "add", "type", "wifi", "ifname", dev, "con-name", HOST, "autoconnect", "no",
                     "ssid", h["name"], "802-11-wireless.mode", "ap", "802-11-wireless.band", "bg",
                     "ipv4.method", "shared", "ipv4.routes", "255.255.255.255/32", "ipv6.method", "ignore",
                     "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", h["password"], "wifi-sec.proto", "rsn",
                     "wifi-sec.pairwise", "ccmp", "wifi-sec.group", "ccmp", "wifi-sec.pmf", "disable"], 20)
    if not ok:
        return False, err
    return nm(["connection", "up", "id", HOST], 60)[::2]


def host_address(dev):
    """This Pi's address on the hotspot it's making (10.42.0.1, as NetworkManager has it), or ""."""
    m = re.search(r"\binet (\d+\.\d+\.\d+\.\d+)/", run_out(["ip", "-4", "-o", "addr", "show", "dev", dev]))
    return m.group(1) if m else ""


def host_off():
    """The hotspot here, off (NetworkManager joins your WiFi again by itself): (ok, what went wrong)."""
    ok, _, err = nm(["connection", "down", "id", HOST], 20)
    gone = "not an active connection" in err.lower() or "unknown connection" in err.lower()
    return ok or gone, "" if ok or gone else err


def join_keep(h, dev):
    """Your hotspot, kept as a network to join by itself, after your own and for as long as it's there: changed in
    place where it's kept already (one joined now stays joined, till that hotspot's turned off). (ok, what went
    wrong)."""
    ok, _, err = nm(["connection", "modify", "id", JOIN, "802-11-wireless.ssid", h["name"],
                     "wifi-sec.psk", h["password"]], 15)
    if ok:
        return True, ""
    return nm(["connection", "add", "type", "wifi", "ifname", dev, "con-name", JOIN, "autoconnect", "yes",
               "connection.autoconnect-priority", str(JOIN_PRIORITY), "connection.autoconnect-retries", "0",
               "ssid", h["name"], "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", h["password"]], 20)[::2]


def join_now():
    """Your hotspot, joined now (another of yours has it on): (ok, what went wrong)."""
    return nm(["connection", "up", "id", JOIN], 60)[::2]


# ---- from another of yours -------------------------------------------------------------------------------------------
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)   # (straight there: never elsewhere)


def ask_peer(url, timeout=5):
    """Another of yours' hotspot (its web page's /api/hotspot), or None: it isn't answering, sharing's off there, or it
    has none."""
    req = urllib.request.Request(url + "/api/hotspot", headers={"User-Agent": "Pietato"})
    try:
        with OPENER.open(req, timeout=timeout) as r:
            got = json.loads(r.read(ASK_MOST).decode())
    except (OSError, ValueError):
        return None
    return hotspot_clean(got.get("hotspot")) if isinstance(got, dict) else None
