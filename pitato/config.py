"""Where your settings are: the static folder and its settings files, the saved state's settings,
and reading and writing settings files."""
import glob
import os
import re
import stat
import tempfile

from .theme import ACCENTS, LOOKS


CONTROL_PORT = 5480        # the web page (webui.py) works media mode through this, on this Pi only
WEB_PORT = 5432            # ...which is itself on this port
CONTROL_KEY = "/run/pitato/control-key"   # ...with this key, readable by you and root only
# passwords and tokens: never shown
WEB_PRIVATE = {"webui.txt", "homeassistant.txt", "plex.txt", "jellyfin.txt", "pihole.txt", "retroachievements.txt",
               "hotspot.txt"}


# ---- your settings files: the static folder ---------------------------------
def settings_dir():
    """Where your settings files are (radio.txt, bot.txt...): the static folder in the Pietato
    folder. The service is told where that is (setup.sh); run by hand, it's the one next to the
    code's own folder."""
    told = os.environ.get("PITATO_STATIC", "").strip()
    if told:
        return os.path.abspath(told)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")


STATIC = settings_dir()


def settings_file(name):
    """A settings file's path, in the static folder."""
    return os.path.join(STATIC, name)


def settings_glob(name):
    """...as the pattern the tabs read it by (a folder name with [ or * in it stays as it is)."""
    return glob.escape(settings_file(name))


WEB_PRIVATE_NAME = re.compile(r"[#.~]*(" + "|".join(map(re.escape, sorted(WEB_PRIVATE))) + ")")


def web_private(name):
    """A password or a token, or a copy of one an editor left (webui.txt.save, homeassistant.txt~,
    #plex.txt#), but not complex.txt."""
    return bool(WEB_PRIVATE_NAME.match((name or "").lower()))


# ---- settings: saved with the rest of the state ---------------------------------------
WALLPAPERS = ["Midnight", "Dusk", "Ocean", "Forest", "Aurora",      # Settings > Appearance > Background: the dark
              "Sunset", "Candy", "Lagoon", "Jungle", "Arcade",      # ones, as ever; strong colours; pale ones (the
              "Sky", "Peach", "Mint", "Lemon", "Bubblegum",         # home screen's words go dark over them); and
              "Rainbow", "Snow", "Space", "Black", "Picture"]       # the rest. How each looks: home.py's WALLS
SCREEN_MODES = ["Fit", "Full screen", "Stretch"]   # Settings > Screen > Video size; Y while a video plays
OLED_CHOICES = ["Off", "Music bars"]               # Settings > Screen > Waveshare 2.23 OLED (screens/oled.py)
ATTRACT_CHOICES = ["On", "Games only", "Off"]      # Settings > Bot > Attract mode: left idle, plugged in, the Bot gets
                                                   # bored and finds something to do (screens/attract.py)
SETTINGS = [   # Settings' first page: key, label, choices (None: opens a page of its own). (Where you are and the
               # temperature's units are Weather's: START there)
    ("wifi", "WiFi", None),
    ("bluetooth", "Bluetooth", None),     # your controllers, keyboards and the rest: find, pair, connect
    ("appearance", "Appearance", None),   # how the home screen and the apps look: a page of settings (SETTINGS_PAGES)
    ("display", "Screen", None),          # the screen's picture, and an OLED beside it: a page of settings too
    ("clock", "Clock", ["12-hour", "24-hour"]),
    ("battery", "Battery saver", ["Auto", "On", "Off"]),   # the screen dark after a few minutes with nothing happening
                                                         # (Auto: while it runs on its battery; screens/rest.py)
    ("sound", "Sound", None),
    ("pad", "Controller", None),
    ("pad_swap", "Swap A and B", ["Off", "On"]),   # on the controller in hand (kept with its buttons, not here)
    ("friend", "Bot", None),
    ("homeassistant", "Home Assistant", None),   # its address and token, for the TV Remote and Lights
    ("start", "At start-up", ["Home screen", "Terminal", "Game"]),   # (Game: the one you played last, where you
                                                                     # were: screens/games.py game_boot. Desktop too,
                                                                     # where there's one: screens/settings.py)
    ("start_song", "Random song at start-up", ["Off", "On"]),   # one of yours from ~/Music, as it starts
    ("share", "Share with other Pietatos", ["On", "Off"]),   # prices and the weather fetched once for them all, and
                                                            # a game carried on on another of them (savesync.py)
]
SETTINGS_PAGES = {   # Settings' pages of settings, each opened from its row on the first page: their rows, as above
    "appearance": [
        ("wallpaper", "Background", WALLPAPERS),
        ("home_style", "Home screen style", ["Bright", "Glass", "Cards"]),
        ("accent", "Accent colour", [a for a, _ in ACCENTS]),
        ("look", "App pages", list(LOOKS)),   # the pages inside the apps, dark (as ever) or light; the home screen
                                              # keeps its background (theme.py's set_look)
        ("app_full", "Full screen apps", ["Off", "On"]),   # the apps without the bars along the top and bottom
    ],
    "display": [                              # ("screen" is Video size's own key, as ever)
        ("screen", "Video size", SCREEN_MODES),
        ("resolution", "Resolution", None),   # a TV or monitor's: the sizes it takes (not there on the GPi Case)
        ("turn", "Rotate screen", ["Off", "90°", "180°", "270°"]),   # a screen on its side: the picture turned
                                                                    # clockwise (not there on the GPi Case's own)
        ("oled", "Waveshare 2.23 OLED", OLED_CHOICES),   # that OLED HAT on the Pi's pins: bars that move with your
                                                         # music (only on a Pi with its pins free: screens/oled.py)
    ],
}
SETTINGS_DEFAULT = {"wallpaper": "Midnight", "picture": "", "accent": "Blue", "look": "Dark", "clock": "12-hour",
                    "units": "°F", "start": "Home screen", "location": None,
                    "screen": "Fit", "sound": "Auto", "sim_full": "Off", "bot_mode": "chat",
                    "game_picture": "Fit", "start_song": "Off", "home_style": "Glass",
                    "ds_screens": "Left/Right", "ds_touch": "Right stick, R2", "app_full": "Off", "turn": "Off",
                    "sys_view": "Dashboard", "battery": "Auto", "share": "On", "attract": "On",
                    "hotspot": "Off",                 # (Settings > WiFi > Hotspot: on again at start-up, if it was)
                    "group_talk": "On", "group_eyes": "On",   # (Apps > Group chat: they talk among themselves; a USB
                                                              # camera notices you: screens/group.py)
                    "glow_on": "Off", "glow_colour": "Off", "glow_follow": "Any of yours", "glow_bright": "25%",
                    "glow_beat": "On", "glow_each": "The same beat", "glow_shape": "8x8 grid", "glow_turn": "0°",
                    "glow_mirror": "On",
                    "glow_wiring": "Rows", "glow_count": "60", "glow_start": "Bottom left", "glow_way": "Clockwise",
                    "glow_bottom": "Yes",             # (Apps > LED backlight: screens/glow.py)
                    "board_bpm": "100", "board_bars": "2", "board_snap": "On", "board_click": "On",
                    "board_scale": "Major", "board_space": "0",   # (Apps > Soundboard's loop, notes and space:
                                                                  #  screens/soundboard.py)
                    "bounce_sound": "Tones/Bell", "bounce_key": "C", "bounce_scale": "Pentatonic",
                    "bounce_shape": "Hexagon", "bounce_echo": "3", "bounce_snap": "Off", "bounce_spin": "0.30",
                    "bounce_speed": "0.80", "bounce_space": "4", "bounce_tone": "5",
                    "bounce_drone": "0",              # (...its Bounce: screens/bounce.py)
                    "oled": "Off"}
TURN_DEGREES = {"Off": 0, "90°": 90, "180°": 180, "270°": 270}   # Settings > Screen > Rotate screen's choices
HOME_STYLE_WAS = {"Original": "Bright", "Style 2": "Glass", "Style 3": "Glass", "Style 4": "Cards",   # (earlier names,
                  "Minimal": "Glass"}                                                               # and one gone)
SETTINGS_GONE = ("shrink", "widget")   # settings there were once (Big videos: they're made smaller whenever they
                                       # need it; On the home screen: the weather's there once there's a place)


STATE_FILE = "/var/lib/pitato/state.json"   # resume points, lengths, lists
CACHE_DIR = "/var/cache/pitato"             # thumbnails, converted documents
OLD_PLACES = (("/var/lib/gpi-keys", "/var/lib/pitato"), ("/var/cache/gpi-keys", "/var/cache/pitato"))


def move_old_places():
    """What it kept by the name it had before (gpi-media), where it keeps it now. setup.sh moves them; this is
    for a setup.sh that didn't get that far."""
    for old, new in OLD_PLACES:
        if os.path.isdir(old) and not os.path.exists(new):
            try:
                os.rename(old, new)
            except OSError:
                pass


def home_dir():
    homes = sorted(h for h in glob.glob("/home/*") if os.path.isdir(h))
    return homes[0] if homes else "/root"


def read_lines(patterns):
    for pattern in patterns:
        for fn in sorted(glob.glob(pattern)):
            try:
                yield from open(fn, errors="ignore").read().splitlines()
            except OSError:
                continue


def read_config(patterns):
    """'key = value' lines; lines starting with # are notes."""
    cfg = {}
    for line in read_lines(patterns):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            cfg[k.strip().lower()] = v.strip()
    return cfg


def clean_name(text, limit=40):
    """A name fit for a line of a settings file, and the screen: printable, on one line."""
    text = "".join(c if c.isprintable() else " " for c in str(text or ""))
    return " ".join(text.split())[:limit]


def read_own_text(path):
    """A settings file of yours, read in order to change it (this runs as root): only a plain
    file you could read yourself, so a link to somewhere private isn't copied into your folder."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with open(fd, errors="ignore") as f:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or \
                (st.st_uid != os.stat(home_dir()).st_uid and not st.st_mode & stat.S_IROTH):
            raise PermissionError(f"{os.path.basename(path)} isn't a file of yours")
        return f.read(1_000_000)


def write_setting(name, text, private=False):
    """A settings file in the static folder, written whole and owned by you: a new file swapped
    in, so a link left in its place is replaced rather than followed (this runs as root)."""
    st = os.stat(home_dir())
    if not os.path.isdir(STATIC):                     # not made yet: yours, like the rest (and only
        os.mkdir(STATIC)                              # in a Pietato folder that's there)
        os.chown(STATIC, st.st_uid, st.st_gid, follow_symlinks=False)
    fd, tmp = tempfile.mkstemp(dir=STATIC, prefix="." + name + ".")
    try:
        with os.fdopen(fd, "w") as f:
            os.fchown(f.fileno(), st.st_uid, st.st_gid)     # (the open file: a swapped name can't
            os.fchmod(f.fileno(), 0o600 if private else 0o644)   # point root anywhere else)
            f.write(text)
        os.replace(tmp, settings_file(name))
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return settings_file(name)


def read_own_bytes(path, limit):
    """A file of yours, read whole (this runs as root): only a plain file you could read yourself,
    no bigger than limit."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with open(fd, "rb") as f:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or \
                (st.st_uid != os.stat(home_dir()).st_uid and not st.st_mode & stat.S_IROTH):
            raise PermissionError(f"{os.path.basename(path)} isn't a file of yours")
        if st.st_size > limit:
            raise ValueError("That picture is too big")
        return f.read(limit + 1)


def edit_config(name, updates, head="", was="", limit=400, private=False):
    """'key = value' lines in a settings file changed or added; the rest kept. A file that isn't
    there yet starts from `was` (its earlier name), if that one is. Values: a line each, `limit`
    characters at most. private: a password's in it (for you to read, nobody else)."""
    path = settings_file(name)
    updates = {k: clean_name(v, limit) for k, v in updates.items()}
    try:
        lines = read_own_text(path).splitlines()
    except FileNotFoundError:
        try:
            lines = read_own_text(settings_file(was)).splitlines() if was else None
        except FileNotFoundError:
            lines = None
        if lines is not None:                          # its own header, rather than the old one's
            while lines and lines[0].lstrip().startswith("#"):
                lines.pop(0)
            lines = (head.rstrip("\n").split("\n") if head else []) + lines
        else:
            lines = head.rstrip("\n").split("\n") if head else []
    done, out = set(), []
    for line in lines:
        k, eq, _ = line.partition("=")
        key = k.strip().lower()
        if eq and not line.strip().startswith("#") and key in updates:
            if key not in done:
                out.append(f"{key} = {updates[key]}")
                done.add(key)
            continue
        out.append(line)
    out += [f"{k} = {v}" for k, v in updates.items() if k not in done]
    return write_setting(name, "\n".join(out).rstrip("\n") + "\n", private=private)
