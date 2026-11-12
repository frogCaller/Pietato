"""How things look: the colours (with the accent you pick in Settings, and the pages inside the apps dark or light),
the fonts, and mixing colours."""
import os
import sys


ACCENTS = [("Blue", (96, 170, 228)), ("Teal", (64, 196, 180)), ("Green", (110, 200, 120)),
           ("Purple", (160, 130, 230)), ("Pink", (232, 120, 170)), ("Red", (236, 100, 100)),
           ("Gold", (230, 190, 80)), ("White", (228, 232, 238))]
ACCENTS_LIGHT = {"Blue": (32, 108, 190), "Teal": (12, 132, 120), "Green": (38, 138, 60),   # ...as they are on a light
                 "Purple": (112, 80, 204), "Pink": (198, 56, 122), "Red": (202, 56, 56),   # page: darker, to read
                 "Gold": (160, 112, 8), "White": (58, 64, 78)}                             # against it (White: grey)
LOOKS = ("Dark", "Light")        # Settings > App pages: the pages inside the apps (the home screen keeps its own)
OWN_LOOK = ("home", "screens.home")   # the modules that draw the home screen: its background's colours, whatever
                                      # the pages' are
LOOK = ["Dark"]                  # the look now


def look():
    """The pages' look now: "Dark" or "Light"."""
    return LOOK[0]


def accent_for(name, look_name=None):
    """An accent colour by its name, as it is on the pages now (look_name: on a dark page, or a light one)."""
    if (look_name or LOOK[0]) == "Light":
        return ACCENTS_LIGHT.get(name, ACCENTS_LIGHT[ACCENTS[0][0]])
    return dict(ACCENTS).get(name, ACCENTS[0][1])


def on_dark(key):
    """A colour by the name the modules draw with ("TEXT", "BODY"... "ACCENT"), as a dark page has it, whatever the
    pages are now: for words on something that's dark anyway (Now playing's art, a photo, the black before a video)."""
    return accent_for(ACCENT_NAME[0], "Dark") if key == "ACCENT" else PALETTES["Dark"][key]


def _modules():
    """(a module of Pietato's, whether it keeps the home screen's colours) for each that's loaded."""
    package = __name__.split(".")[0]
    for mod in list(sys.modules.values()):
        name = getattr(mod, "__name__", "")
        if name.split(".")[0] == package:
            yield mod, name.split(".", 1)[-1] in OWN_LOOK


def set_accent(name):
    """The accent colour everything draws with: changed in each module that draws with it (each
    keeps its own name for it). On a light page it's a darker one of its kind (the home screen: as ever)."""
    colour = accent_for(name)
    for mod, own in _modules():
        if "ACCENT" in vars(mod):
            mod.ACCENT = accent_for(name, "Dark") if own else colour
    BADGE["dir"] = colour
    ACCENT_NAME[0] = name


def set_look(name):
    """The pages inside the apps, dark (as ever) or light: their colours changed in each module that draws with them
    (as the accent is), but for the home screen's, which has its background's. Pictures drawn before are for whoever
    kept them to throw away (media mode: look_changed)."""
    name = name if name in PALETTES else "Dark"
    LOOK[0] = name
    known = {key: {p[key] for p in PALETTES.values()} for key in PALETTES["Dark"]}
    for mod, own in _modules():
        had = vars(mod)
        for key, colour in PALETTES["Dark" if own else name].items():
            if had.get(key) in known[key]:             # (its own LINE or ROW, something else altogether: left)
                setattr(mod, key, colour)
    BADGE.update(BADGES[name])
    set_accent(ACCENT_NAME[0])


FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_MONO_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"


def bundled_font(name, instead):
    """A typeface that comes with Pietato, in its static/fonts folder (where setup.sh puts the code, or the
    Pietato folder itself); the system's `instead` if it isn't there."""
    for static in (os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static"),
                   os.environ.get("PITATO_STATIC", "").strip()):
        path = os.path.join(static, "fonts", name) if static else ""
        if path and os.path.isfile(path):
            return path
    return instead


# the home screen's: Inter (thin, for the time and the temperature). Its OpenType (CFF) files, laid out simply
# (draw.py), draw several times quicker than its TrueType ones on a Pi.
FONT_THIN = bundled_font("InterDisplay-Light.otf", FONT)
FONT_UI = bundled_font("Inter-Regular.otf", FONT)
FONT_UI_BOLD = bundled_font("Inter-SemiBold.otf", FONT_BOLD)

# typefaces to pick from, in Notes and the Clock (static/fonts, free: their OFL.txt): the name each goes by, its file,
# and how big it's set beside Inter for its small letters to look as big (a pixel font: its own sizes, notes.py's)
TYPEFACES = (("Clean", "Inter-Regular.otf", 1.0), ("Thin", "InterDisplay-Light.otf", 1.0),
             ("Bold", "Inter-SemiBold.otf", 1.0), ("Handwriting", "Caveat-Variable.ttf", 1.45),
             ("Typewriter", "CourierPrime-Regular.ttf", 1.2), ("Pixel", "PressStart2P-Regular.ttf", 0.62),
             ("Terminal", "VT323-Regular.ttf", 1.35), ("Comic", "ComicNeue-Regular.ttf", 1.1),
             ("Script", "Pacifico-Regular.ttf", 1.1), ("Future", "Orbitron-Variable.ttf", 0.92),
             ("Retro", "Righteous-Regular.ttf", 1.05), ("Poster", "BebasNeue-Regular.ttf", 1.2),
             ("Neon", "Monoton-Regular.ttf", 1.0))


def typeface(name):
    """A typeface by the name it goes by: (its file, how big it's set beside Inter). One that isn't there (an older
    fonts folder): DejaVu Sans, as big."""
    for n, f, k in TYPEFACES:
        if n == name:
            path = bundled_font(f, "")
            return (path, k) if path else (FONT, 1.0)
    return FONT_UI, 1.0


# PiE-ink's colour-screen palette
PI_BG, PI_FG, PI_DIM, PI_ACCENT = (0, 0, 0), (255, 255, 255), (150, 150, 150), (98, 210, 255)
PI_UP, PI_DOWN = (0, 255, 0), (255, 80, 80)


# colours: calm dark theme for a small screen
BG     = (16, 19, 23)
ROW    = (31, 37, 46)
TEXT   = (236, 239, 243)
BODY   = (176, 184, 196)
MUTED  = (104, 112, 125)
LINE   = (40, 46, 55)
ACCENT = (96, 170, 228)
DONE   = (122, 186, 150)
WARN   = (230, 120, 120)
KEY_FILL = (62, 68, 79)      # a button, in the hints along the bottom
KEY_TEXT = (236, 239, 243)   # ...the letter on it
PILL = (31, 37, 46)          # a notice (toast) over a page
PILL_TEXT = (236, 239, 243)  # ...its words
PHOTO_BG = (6, 7, 9)
BADGE = {  # file type label colours in the Files tab
    "dir": ACCENT, "image": DONE, "video": (110, 196, 196), "audio": (170, 146, 222),
    "pdf": (224, 122, 128), "doc": (124, 152, 232), "text": BODY, "other": MUTED,
}
# ...and a light one (Settings > App pages): a pale page, white rows and cards on it, dark words. Each colour by the
# name the modules draw with (set_look changes them there)
PALETTES = {
    "Dark": {"BG": BG, "ROW": ROW, "TEXT": TEXT, "BODY": BODY, "MUTED": MUTED, "LINE": LINE, "DONE": DONE,
             "WARN": WARN, "KEY_FILL": KEY_FILL, "KEY_TEXT": KEY_TEXT, "PILL": PILL, "PILL_TEXT": PILL_TEXT,
             "WWW_UNDERLINE": (58, 92, 124),           # (a link's line under it, in Web's pages: screens/www.py)
             "PI_BG": PI_BG, "PI_FG": PI_FG, "PI_DIM": PI_DIM, "PI_ACCENT": PI_ACCENT, "PI_UP": PI_UP,
             "PI_DOWN": PI_DOWN, "PH_AXIS": (58, 65, 76), "PH_REST": (78, 86, 98)},   # (PH_: the dashboards' greys,
    "Light": {"BG": (236, 239, 244), "ROW": (255, 255, 255), "TEXT": (20, 24, 31), "BODY": (64, 72, 86),
              "MUTED": (116, 124, 138), "LINE": (210, 215, 224), "DONE": (34, 136, 94), "WARN": (200, 58, 58),
              "KEY_FILL": (58, 64, 78), "KEY_TEXT": (246, 247, 249), "PILL": (44, 50, 62),   # (a notice: dark on a
              "PILL_TEXT": (246, 247, 249), "WWW_UNDERLINE": (150, 182, 216),              #  light page, to stand out)
              "PI_BG": (255, 255, 255), "PI_FG": (16, 18, 22), "PI_DIM": (112, 116, 124), "PI_ACCENT": (0, 118, 178),
              "PI_UP": (0, 146, 62), "PI_DOWN": (204, 44, 44), "PH_AXIS": (208, 213, 222),       # screens/pihole.py)
              "PH_REST": (170, 177, 188)},
}
BADGES = {
    "Dark": {"image": DONE, "video": (110, 196, 196), "audio": (170, 146, 222), "pdf": (224, 122, 128),
             "doc": (124, 152, 232), "text": BODY, "other": MUTED},
    "Light": {"image": PALETTES["Light"]["DONE"], "video": (14, 128, 128), "audio": (108, 82, 190),
              "pdf": (194, 62, 72), "doc": (58, 94, 200), "text": PALETTES["Light"]["BODY"],
              "other": PALETTES["Light"]["MUTED"]},
}
ACCENT_NAME = [ACCENTS[0][0]]    # the accent picked, by name (set_accent)


def co_ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def co_mix(c1, c2, f):
    return tuple(int(round(a + (b - a) * f)) for a, b in zip(c1, c2))
