"""Instincts: how a person plays a kind of game without stopping to think, for the AI player (pitato/anygame.py) in
games where waiting a second or two for each press would lose: a race, a platformer's level, a fight, a shoot-'em-up.
Each looks at the game's screen many times a second and holds the buttons a player would. A racer holds the gas and
steers to keep on the road (the road's colour just ahead of the car, and where the road goes further on), and backs
up and turns when it's hit something. A platformer runs on and jumps when it's blocked, when the floor ahead drops
away, and now and then anyway, backing off for a run-up when a jump wasn't enough. A fighter goes at the other
fighter with a mix of attacks, blocks, jumps and special moves. A shooter keeps firing and weaves about. The decision
model (pitato/anygame.py) says which way: where the level goes, which side the other fighter's on.

And one that every game needs (PressOn): pressing Start, then A, to get a game going from its logos, title screen,
menus and text, and on again when it's waiting (a level's end, GAME OVER, paused), telling by what comes of each
press, with no model needed.

What kind of game it is, and what its buttons do, come from what your Bot's model knows of the game (pitato/coach.py);
until it's said, from the game's name; and the buttons from how most games on that console go."""
import math
import random
import re

import numpy as np

KINDS = ("racing", "platformer", "fighting", "shooter", "sports", "puzzle", "rpg", "adventure", "other")
LIVE = ("racing", "platformer", "fighting", "shooter")   # played by instinct, many times a second
SMALL = 96                   # pixels across the picture the instincts look at

# the kind of game, from its name: (a pattern in its name, lower case, the kind), the first that matches
TITLE_KINDS = (
    (r"mario kart|kart\b|racing|racer\b|\brace\b|rally|f-?zero|grand prix|\bgp\b|gran turismo|need for speed|"
     r"ridge racer|out ?run|road rash|rad racer|excitebike|motocross|\bmoto|top gear|wipe ?out|wave race|cruis.n|"
     r"micro machines|pro-am|pole position|burnout|nascar|\bindy|formula|\bf-?1\b|daytona|test drive|speed(?!y)|drift|"
     r"\bcart\b|\btoca\b|hang-?on|road fighter|super off road|stunt race|super monaco|colin mcrae|"
     r"destruction derby|jet moto|hydro thunder|san francisco rush|\brush 2049|sonic r\b|sonic drift|"
     r"rock n'? roll rac|power drive|lotus|chase h\.?q|rc de go|penny racers|mickey'?s speedway|"
     r"crazy taxi|18 wheeler|super sprint|turbo out|battle gear|initial d", "racing"),
    (r"dr\.? ?mario|tetris|puyo|columns|picross|puzzle|panel de pon|yoshi'?s cookie|wario'?s woods|klax|lemmings|"
     r"bust-a-move|zoop|mean bean|bejeweled|lumines|minesweeper|solitaire|chess|sudoku|sokoban|boxxle|"
     r"adventures of lolo|\blolo\b|kickle|mole mania|kwirk|pipe ?dream|\bqix\b|mahjong|shanghai|magical drop|"
     r"baku baku|kirby'?s (avalanche|star stacker)|pok[eé]mon puzzle|professor layton|mr\.? driller|"
     r"chu chu rocket|kuru kuru|polarium|meteos|hexic|othello|reversi|checkers|shogi", "puzzle"),
    (r"mario (tennis|golf|strikers)|tennis|golf|fifa|\bnba|\bnhl|\bnfl|madden|soccer|football|"
     r"baseball|basketball|hockey|bowling|\bhawk'?s (pro|under|american|downhill|project|proving)|skate|\bpga\b|olympic|track (&|and) field|tecmo bowl|"
     r"blades of steel|world cup|volleyball|pro evolution|winning eleven|international superstar|\biss\b|"
     r"sensible|kick off|california games|winter games|summer games|decathlon|\bbmx\b|\bpool\b|billiard|"
     r"snooker|darts|fishing|\bbass\b|rugby|cricket|ping pong|table tennis|\bpong\b|badminton|dodge ?ball|"
     r"lacrosse|\bmlb\b|\bncaa\b|bases loaded|r\.?b\.?i\.? baseball|ken griffey|double dribble|hoops|"
     r"\bslam\b|curling|hot shots|everybody'?s golf|virtua striker|world series", "sports"),
    (r"street fighter|mortal kombat|tekken|king of fighters|\bkof\b|fatal fury|samurai shodown|killer instinct|"
     r"smash bros|darkstalkers|soul ?(calibur|blade)|bloody roar|guilty gear|marvel vs|x-men vs|primal rage|"
     r"clay ?fighter|art of fighting|virtua fighter|dead or alive|toshinden|punch-out|dragon ball z|"
     r"power instinct|world heroes|eternal champions|bushido blade|rival schools|"
     r"streets of rage|bare knuckle|final fight|double dragon|golden axe(?! warrior)|turtles|\btmnt\b|battletoads|"
     r"river city|knights of the round|captain commando|cadillacs|punisher|alien vs\.? predator|"
     r"king of dragons|sengoku|burning fight|mutation nation|robo army|ninja combat|vendetta|bad dudes|"
     r"dragonninja|renegade|kung.?fu|karate|yie ar|wrestl|\bwwf\b|\bwwe\b|\bwcw\b|\becw\b|boxing|\bufc\b|"
     r"ready 2 rumble|fighters megamix|fighting vipers|last blade|garou|real bout|waku waku|breakers|kizuna|"
     r"savage reign|capcom vs|vs\.? capcom|pocket fighter|star gladiator|ehrgeiz|tobal|battle arena|"
     r"psychic force|power stone|\bjojo|weaponlord|shaq.?fu|time killers|pit-?fighter|fighter'?s history|"
     r"rise of the robots|ranma|yu yu hakusho|sailor moon|gundam wing|comix zone|splatterhouse|"
     r"dynasty warriors|guardian heroes|die hard arcade|fighting force|power rangers", "fighting"),
    (r"pok[eé]mon (pinball|snap|stadium|puzzle)|mario (party|paint)|party|pinball|spinball|dream course|"
     r"block ball|tilt .?n.? tumble", "other"),
    (r"pok[eé]mon|final fantasy|dragon (quest|warrior)|chrono|earthbound|mother\b|secret of mana|seiken|"
     r"breath of fire|lufia|phantasy star|golden sun|fire emblem|suikoden|star ocean|tales of|persona|"
     r"megami|paper mario|mario (&|and) luigi|mario rpg|xenogears|wild arms|kingdom hearts|legend of dragoon|"
     r"\bys\b|terranigma|illusion of gaia|shining force|advance wars|tactics|dragon slayer|"
     r"digimon|monster rancher|grandia|vagrant story|parasite eve|\bmana\b|soul blazer|7th saga|ogre battle|"
     r"langrisser|shining (in the|the holy|soul|wisdom|tears)|skies of arcadia|baldur|diablo|ultima|wizardry|"
     r"might (&|and) magic|riviera|summon night|robotrek|crystalis|\bsaga\b|romancing|legaia|valkyrie profile|"
     r"xenosaga|dark cloud|lunar[ :-]+(the )?(silver|eternal|legend)|arc the lad|azure dreams|"
     r"dragon ?view|eye of the beholder|lagoon|secret of the stars|inindo|uncharted waters|"
     r"harvest moon|rune factory|medabots|robopon|dokapon|sword of vermilion|beyond the beyond|\brpg\b", "rpg"),
    (r"gradius|r-type|\b194[2-5]\b|galaga|galaxian|space invaders|xevious|life force|salamander|parodius|"
     r"thunder ?force|star ?fox|raiden|tyrian|ikaruga|contra|probotector|metal slug|zanac|gun\.?smoke|twinbee|"
     r"darius|axelay|u\.?n\.? squadron|phalanx|asteroids|defender|robotron|smash tv|einhander|gunbird|"
     r"strikers 1945|b-wings|1943|sky ?shark|tiger-heli|shmup|shoot|"
     r"space harrier|after ?burner|panzer dragoon|star soldier|aleste|power strike|truxton|tatsujin|"
     r"fire shark|twin cobra|forgotten worlds|side arms|section z|scramble|zaxxon|centipede|millipede|"
     r"tempest|gyruss|time pilot|blazing lazers|gate of thunder|lords of thunder|soldier blade|air zonk|"
     r"cotton|radiant silvergun|m\.?u\.?s\.?h\.?a\b|steel empire|sub-?terrania|viewpoint|pulstar|blazing star|"
     r"last resort|aero fighters|sonic wings|twinkle star|ghost pilots|alpha mission|nam-?1975|cabal|"
     r"wild guns|sunset riders|gunstar|alien soldier|super c\b|operation c\b|ikari|jackal|guerrilla war|"
     r"heavy barrel|\bmercs\b|total carnage|sin (&|and) punishment|silpheed|galaxy force|vanguard|"
     r"bio-?hazard battle|super aleste|space megaforce|super r-type|macross|area 88|1941|19xx|giga wing|"
     r"dodonpachi|donpachi|batsugun|battle garegga|mars matrix|zero gunner|thunder cross|vic viper", "shooter"),
    (r"zelda|link'?s awakening|resident evil|silent hill|tomb raider|metal gear|monkey island|myst\b|"
     r"secret of evermore|alundra|beyond oasis|landstalker|okami|shadow of|"
     r"startropics|soul reaver|legacy of kain|shenmue|grim fandango|broken sword|discworld|sam (&|and) max|"
     r"day of the tentacle|maniac mansion|king'?s quest|space quest|shadowgate|deja vu|uninvited|snatcher|"
     r"policenauts|phoenix wright|ace attorney|harry potter|lord of the rings|indiana jones|dino crisis|"
     r"alone in the dark|clock tower|fear effect|syphon filter|medievil|\becco\b|little big adventure|"
     r"illusion of time|light crusader|story of thor|dark savior|brave fencer|threads of fate|"
     r"neutopia|golden axe warrior|crusader of centy|soleil|oracle of|minish|wind waker|majora|ocarina|"
     r"shrek (2|the third|forever)|lost vikings", "adventure"),   # (...and platformers that are puzzles: things to
                                            # carry, characters to switch between. Running and jumping alone gets
                                            # nowhere in them)
    (r"mario|sonic|mega ?man|rockman|kirby|castlevania|metroid|donkey kong|yoshi|wario ?land|adventure island|"
     r"bonk|crash bandicoot|spyro|banjo|rayman|jazz jackrabbit|earthworm jim|aladdin|lion king|ninja gaiden|"
     r"shinobi|kid icarus|ducktales|chip .?n.? dale|prince of persia|commander keen|pitfall|bubsy|gex\b|croc\b|"
     r"ghouls|ghosts|wonder boy|alex kidd|bubble bobble|mega man|cave story|shovel knight|celeste|vectorman|"
     r"rocket knight|kid chameleon|ristar|toejam|cool spot|kid kool|super meat boy|klonoa|tail concerto|"
     r"ape escape|pandemonium|jumping flash|blinx|mischief makers|conker|"
     r"shrek|tarzan|toy story|hercules|jungle book|pinocchio|pocahontas|mulan|bug'?s life|monsters,? inc|"
     r"finding nemo|incredibles|ice age|madagascar|lilo|stitch|peter pan|mickey|donald|goofy|quackshot|"
     r"magical quest|darkwing|tale ?spin|rescue rangers|duck ?tales|looney|bugs bunny|daffy|\btaz\b|tiny toon|"
     r"animaniacs|scooby|flintstones|jetsons|simpsons|\bbart\b|asterix|smurfs|tintin|garfield|felix the cat|"
     r"spongebob|rugrats|jimmy neutron|powerpuff|dexter'?s|spider-?man|batman|superman|x-men|wolverine|\bhulk\b|"
     r"turrican|strider|bionic commando|blaster master|little nemo|gargoyle'?s quest|demon'?s crest|actraiser|"
     r"sparkster|\bplok\b|\bzool\b|james pond|chuck rock|joe (&|and) mac|kid niki|karnov|rygar|shatterhand|"
     r"power blade|gimmick|little samson|kid dracula|goemon|mystical ninja|tomba|pac-?man world|pac-?in-?time|"
     r"oddworld|abe'?s|heart of darkness|flashback|another world|out of this world|blackthorne|boogerman|"
     r"aero the acro|dynamite headdy|pulseman|alisia dragoon|el viento|\bvalis\b|monster world|psycho fox|"
     r"land of illusion|castle of illusion|world of illusion|lucky dime|\btails\b|knuckles|glover|\bjak\b|"
     r"ratchet|sly (cooper|raccoon|2|3)|daxter|loco ?roco|megaman|speedy gonzales|super star wars|"
     r"empire strikes back|return of the jedi|hook\b|home alone|addams family|wayne'?s world|cool world|"
     r"james bond jr|rocketeer|robocop|terminator|alien ?(3|³)|predator|judge dredd|demolition man|"
     r"claymates|skyblazer|hagane|run saber|magic sword|black tiger|ghost'?n|maximo|"
     r"pac-?land|wardner|new zealand story|rainbow islands|snow bros|rod ?land|parasol stars|"
     r"super pitfall|jungle hunt|pooyan|circus charlie|mappy|kangaroo|popeye|ice climber|kung fu kid|"
     r"astro boy|lady sia|drill dozer|wario ?ware|scurge|ty the tasmanian|frogger'?s adventures|"
     r"crash (of the titans|nitro|twinsanity|bash|purple|n-tranced|the huge)|"
     r"spyro (the|2|orange|season)|rayman (advance|2|3|raving)", "platformer"),
)

# what a button's for, in a game: its role, and the words that say it
ROLE_WORDS = {
    "gas": r"accelerat|\bgas\b|throttle|\bdrive|go faster|speed up",
    "brake": r"\bbrake|revers|slow down",
    "jump": r"\bjump",
    "run": r"\brun\b|\bruns\b|\bdash|sprint",
    "attack": r"attack|punch|kick|\bhit\b|slash|strike|sword|whip|\bfight",
    "fire": r"\bfire|shoot|\bshot|laser|blast|\bgun\b",
}
# ...and which button it is in most games on each console, until it's known for this one (the attacks: several)
NINTENDO_ROLES = {"gas": "A", "brake": "B", "jump": "A", "run": "B", "attack": ("B", "A"), "fire": "B"}
SONY_ROLES = {"gas": "Cross", "brake": "Square", "jump": "Cross", "run": "",
              "attack": ("Square", "Triangle", "Cross", "Circle"), "fire": "Square"}
SEGA8_ROLES = {"gas": "1", "brake": "2", "jump": "2", "run": "", "attack": ("1", "2"), "fire": "1"}
ROLES = {
    "nes": NINTENDO_ROLES, "gb": NINTENDO_ROLES, "gbc": NINTENDO_ROLES,
    "gba": dict(NINTENDO_ROLES, attack=("B", "A", "L", "R")),
    "snes": {"gas": "B", "brake": "Y", "jump": "B", "run": "Y", "attack": ("Y", "X", "B", "A", "L", "R"), "fire": "Y"},
    "nds": {"gas": "A", "brake": "B", "jump": "B", "run": "Y", "attack": ("Y", "X", "B", "A"), "fire": "Y"},
    "genesis": {"gas": "B", "brake": "A", "jump": "C", "run": "", "attack": ("A", "B", "C"), "fire": "B"},
    "sms": SEGA8_ROLES, "gg": SEGA8_ROLES,
    "ngp": dict(NINTENDO_ROLES, run=""), "ngpc": dict(NINTENDO_ROLES, run=""),
    "neogeo": {"gas": "A", "brake": "B", "jump": "B", "run": "", "attack": ("A", "B", "C", "D"), "fire": "A"},
    "n64": {"gas": "A", "brake": "B", "jump": "A", "run": "", "attack": ("B", "A"), "fire": "A"},
    "ps1": SONY_ROLES, "psp": SONY_ROLES,
    "dc": {"gas": "R", "brake": "L", "jump": "A", "run": "", "attack": ("X", "A", "B", "Y"), "fire": "A"},
}
OPPOSITE = {"left": "right", "right": "left", "up": "down", "down": "up"}
PAD = {"Up": "up", "Down": "down", "Left": "left", "Right": "right"}   # (a role can be a direction: "Up: accelerate")


def guess_kind(title):
    """The kind of game, from its name (lower case, its tags gone): one of KINDS ("other" if nothing says)."""
    t = (title or "").lower()
    for pattern, kind in TITLE_KINDS:
        if re.search(pattern, t):
            return kind
    return "other"


def kind_of(words):
    """One of KINDS, from what a model said ("a 2D platformer", "Racing game"...); None if it's none of them."""
    w = (words or "").lower()
    if not w:
        return None
    for kind, pattern in (("racing", r"rac(e|ing)|kart|driving"), ("platformer", r"platform|side.?scroll|jump.?n"),
                          ("fighting", r"fight|beat.?em|brawl"), ("shooter", r"shoot|shmup|shot|bullet"),
                          ("sports", r"sport|football|soccer|golf|tennis|basketball|baseball|hockey"),
                          ("puzzle", r"puzzle|block|match"), ("rpg", r"rpg|role.?play"),
                          ("adventure", r"adventure|action.?adv|explor"), ("other", r"other")):
        if re.search(pattern, w):
            return kind
    return None


def label_spots(text, labels):
    """Where each button's named in some text: [(where, label)]. One-letter names count only as capitals (not
    "a" the word); longer ones (Start, Cross) either way."""
    spots = []
    for label in labels:
        flags = 0 if len(label) == 1 else re.I
        for m in re.finditer(r"(?<![\w-])%s(?![\w-])" % re.escape(label), text, flags):
            spots.append((m.start(), label))
    return spots


def parse_roles(text, labels):
    """What each role's button is, from words like "B: accelerate; A: use an item; L or R: hop" or "Press A to jump
    and B to run": {role: label} (the attacks: a tuple). Each word that says a role goes with the button named
    nearest it, in its part of the text (an attack with every button named there: "B and A kick")."""
    found = {}
    for clause in re.split(r"[;\n]|\.(?:\s|$)", text or ""):
        spots = label_spots(clause, labels)
        if not spots:
            continue
        for role, pattern in ROLE_WORDS.items():
            for m in re.finditer(pattern, clause, re.I):
                if role == "attack":
                    found.setdefault("attack", [])
                    found["attack"] += [b for _, b in sorted(spots) if b not in found["attack"]]
                else:
                    found.setdefault(role, min(spots, key=lambda s: abs(s[0] - m.start()))[1])
    if "attack" in found:
        found["attack"] = tuple(found["attack"])
    return found


def roles_for(system, labels, buttons_said=""):
    """{role: label} for a game: what's been said of its buttons, over how most games on its console go (only
    buttons it has); and "told": the roles that were said. A button said to shoot, with nothing said of running,
    isn't held to run (it's the shooting button: Mega Man's B)."""
    roles = dict(ROLES.get(system, NINTENDO_ROLES))
    said = {r: v for r, v in parse_roles(buttons_said, list(labels) + list(PAD)).items()
            if r in ("gas", "brake") or v not in PAD}                 # (only the gas and the brake a direction)
    roles.update(said)
    if "run" not in said and roles.get("run") and roles["run"] in (said.get("fire"),) + tuple(said.get("attack", ())):
        roles["run"] = ""
    have = set(labels) | set(PAD)
    out = {}
    for role, v in roles.items():
        if role == "attack":
            v = tuple(b for b in (v if isinstance(v, (tuple, list)) else (v,)) if b in have)
            out[role] = v or tuple(b for b in labels[:2])
        else:
            out[role] = v if v in have else ""
    out["told"] = tuple(sorted(said))
    return out


# ---- looking ----------------------------------------------------------------------------------------------------
def small(look, width=SMALL):
    """A look's picture, small, as an (h, w, 3) int16 array (made once per look)."""
    got = getattr(look, "_small", None)
    if got is not None and got.shape[1] == width:
        return got
    from PIL import Image
    im = look.im
    h = max(2, round(im.height * width / im.width))
    got = np.asarray(im.resize((width, h), Image.BILINEAR), dtype=np.int16)
    look._small = got
    return got


def grey(a):
    return a.mean(axis=2)


def shift(prev, cur, most, axis=1, errs=None):
    """How far the picture moved between two grey ones: (shift, how well it matched there, and with none). + when
    what's on it moved left (or up): the view moving right (or down). The middle rows only (not a score along the
    top). errs: a dict that's given how well it matched at each shift tried."""
    h = cur.shape[0]
    rows = slice(int(h * 0.15), int(h * 0.95))
    p, c = prev[rows], cur[rows]
    if axis == 0:
        p, c = p.T, c.T
    n = c.shape[1]
    best, best_err, zero_err = 0, None, None
    for s in range(-most, most + 1):
        if s >= 0:
            a, b = c[:, :n - s], p[:, s:]
        else:
            a, b = c[:, -s:], p[:, :n + s]
        err = float(np.abs(a - b).mean())
        if errs is not None:
            errs[s] = err
        if s == 0:
            zero_err = err
        if best_err is None or err < best_err - 1e-6 or (abs(err - best_err) <= 1e-6 and abs(s) < abs(best)):
            best, best_err = s, err
    return best, best_err, zero_err


def motion(prev, cur, most, axis=1):
    """How far the view moved between two grey pictures (as shift()), if that's clear: the picture matches itself
    moved that far much better than not moved at all; else 0."""
    s, err, err0 = shift(prev, cur, most, axis)
    return s if err < 0.85 * err0 else 0


def common_colour(a):
    """The most common colour in a picture (rgb), roughly: its pixels' colours in coarse bins, the fullest bin's
    mean; and how much its pixels vary."""
    px = a.reshape(-1, 3)
    q = px // 32
    keys = q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2]
    top = np.bincount(keys, minlength=512).argmax()
    sel = px[keys == top]
    return sel.mean(axis=0), float(sel.std(axis=0).mean())


def runs(row):
    """The runs of True in a row of booleans: [(start, end)] (end not in it)."""
    d = np.diff(np.concatenate(([0], row.astype(np.int8), [0])))
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def close_gaps(row, most):
    """A row of booleans with short runs of False between Trues made True (a car, or a line, on the road)."""
    out = row.copy()
    rs = runs(row)
    for (s0, e0), (s1, e1) in zip(rs, rs[1:]):
        if s1 - e0 <= most:
            out[e0:s1] = True
    return out


# ---- the instincts -------------------------------------------------------------------------------------------------
class Instinct:
    """Plays a kind of game for a moment at a time: tick(look, now) says what to hold for the next moment, as a few
    steps: [(buttons, sticks, seconds)], buttons by the emulator's names (libretro's), sticks {axis: -127 to 127}.
    way: which way to go ("right", "left"; where the level goes, or the other fighter is). stuck(): it's been told
    it's got nowhere for a while (try something else)."""

    TICK = 0.1

    def __init__(self, system, labels, roles, stick=False):
        self.system, self.labels, self.roles, self.stick = system, dict(labels, **PAD), roles, stick
        self.way = "right"
        self.prev = None                           # the last look's grey picture
        self.said = ""                             # what it's doing, in a few words (for the game's menu)

    def button(self, role):
        """A role's button, as the emulator takes it (or None)."""
        label = self.roles.get(role)
        return self.labels.get(label) if isinstance(label, str) and label else None

    def attacks(self):
        return [self.labels[b] for b in self.roles.get("attack", ()) if b in self.labels and b not in PAD] or \
            [v for k, v in self.labels.items() if k not in ("Start", "Select", "Pause") and k not in PAD][:2]

    def dirs(self, *ds):
        """Directions held: d-pad buttons, or the left stick pushed (a stick console's): (buttons, sticks)."""
        if not self.stick:
            return set(d for d in ds if d), {}
        sticks = {}
        for d in ds:
            if d in ("left", "right"):
                sticks["lx"] = -127 if d == "left" else 127
            elif d in ("up", "down"):
                sticks["ly"] = -127 if d == "up" else 127
        return set(), sticks

    def step(self, buttons=(), dirs=(), secs=None, steer=None):
        """One step: buttons and directions held for secs (a tick, unless said); steer pushes the stick partway
        (-1 to 1) on a stick console."""
        b, s = self.dirs(*dirs)
        b |= set(x for x in buttons if x)
        if steer is not None and self.stick:
            s["lx"] = int(max(-1.0, min(1.0, steer)) * 127)
        return (b, s, self.TICK if secs is None else secs)

    def tick(self, look, now):
        return [self.step()]

    def stuck(self, now):
        pass

    def moved(self, g):
        """How much the picture changed since the last look (0 to 255), and remember this one."""
        changed = float(np.abs(g - self.prev).mean()) if self.prev is not None and self.prev.shape == g.shape else 255.0
        self.prev = g
        return changed


class Racing(Instinct):
    """Holds the gas and steers toward the middle of the road: the road's colour learnt from just ahead of the car
    (the most common colour low in the middle of the driver's view), the road found in rows from the car out to the
    distance (gaps the size of a car, or a line, closed), and steered toward where its middle is, more by the rows
    further on (a bend's seen coming). A view that's stopped changing with the gas held means it's hit something:
    it backs up (the brake held), steering the other way, then goes on. On a split screen (a map or another view
    below), the view is the top part."""

    STILL = 1.2               # how little the view changes (of 255) when the car's not moving
    STILL_FOR = 1.5           # seconds of that, the gas held, after it's been moving: it's stuck
    MOVED_WITHIN = 5.0        # (moving this lately: not a race that's yet to start)
    BACK_FOR = 1.2            # seconds it backs up for
    LEARN_EVERY = 4.0         # seconds between looks at what colour the road is
    DEAD = 0.05               # the road's middle this near the car's (of half the view across): no steering
    GAIN = 2.5

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.colour, self.spread, self.learnt_at = None, 30.0, -1e9
        self.still_since, self.back_until, self.back_way = None, 0.0, "left"
        self.offset, self.moving_at = 0.0, -1e9

    def view(self, a):
        """The driver's view: the screen above a band across it that's all one dark colour with things above and
        below it (a split screen), else all of it."""
        h = a.shape[0]
        lo, hi = int(h * 0.35), int(h * 0.75)
        band = a[lo:hi]
        spread = band.std(axis=1).mean(axis=1)
        dark = band.mean(axis=(1, 2))
        for i in np.where((spread < 4) & (dark < 60))[0]:
            y = lo + i
            below = a[min(h - 1, y + max(2, h // 12)):]
            if a[:y].std() > 12 and below.size and below.std() > 12:
                return a[:y]
        return a

    def learn(self, v):
        """The road's colour: the most common colour low in the middle of the view (just ahead of the car and
        round it), if that looks like a road (not most of the view, or a sliver of it)."""
        h, w = v.shape[:2]
        colour, spread = common_colour(v[int(h * 0.62):int(h * 0.92), int(w * 0.28):int(w * 0.72)])
        share = float((np.abs(v - colour).sum(axis=2) < max(45.0, spread * 4)).mean())
        if 0.08 < share < 0.85 or self.colour is None:
            self.colour, self.spread = colour, spread

    def road(self, v):
        """Where the road's middle is, ahead: (how far off the middle of the view, -1 to 1: + to the right; how
        much of the view low down is road)."""
        h, w = v.shape[:2]
        mask = np.abs(v - self.colour).sum(axis=2) < max(45.0, self.spread * 4)
        top, bottom = int(h * 0.5), int(h * 0.94)
        total = weight = 0.0
        mid = w / 2
        for y in range(top, bottom, 2):
            row = close_gaps(mask[y], max(2, w // 4))
            rs = [(s, e) for s, e in runs(row) if e - s >= max(2, w // 12)]
            if not rs:
                continue
            s, e = min(rs, key=lambda r: 0 if r[0] <= mid < r[1] else min(abs(r[0] - mid), abs(r[1] - mid)))
            far = 1.0 - (y - top) / max(1, bottom - top)            # (rows further on count for more)
            wgt = 1.0 + 2.0 * far
            total += wgt * ((s + e) / 2 - mid) / mid
            weight += wgt
        share = float(mask[int(h * 0.7):bottom, int(w * 0.3):int(w * 0.7)].mean())
        return (total / weight if weight else 0.0), share

    def tick(self, look, now):
        a = small(look)
        v = self.view(a)
        changed = self.moved(grey(v))
        gas, brake = self.button("gas"), self.button("brake")
        if now < self.back_until:                  # backing up, steering the other way
            self.said = "Backing up"
            return [self.step((brake,), ("down" if not brake else None, self.back_way))]
        if now - self.learnt_at > self.LEARN_EVERY or self.colour is None:
            self.learn(v)
            self.learnt_at = now
        self.offset, share = self.road(v)
        if changed < self.STILL:
            self.still_since = self.still_since or now
            if now - self.still_since > self.STILL_FOR and self.still_since - self.moving_at < self.MOVED_WITHIN:
                self.stuck(now)
                return [self.step((brake,), ("down" if not brake else None, self.back_way))]
        else:
            self.still_since, self.moving_at = None, now
        o = self.offset
        self.said = "Driving"
        if abs(o) < self.DEAD:
            return [self.step((gas,))]
        way = "right" if o > 0 else "left"
        if self.stick:
            return [self.step((gas,), steer=o * self.GAIN)]
        duty = min(1.0, abs(o) * self.GAIN)
        held = round(self.TICK * duty, 3)
        steps = [self.step((gas,), (way,), held)]
        if held < self.TICK:
            steps.append(self.step((gas,), secs=round(self.TICK - held, 3)))
        return steps

    def stuck(self, now):
        """Hit something: back up a while, steering away from where the road was."""
        self.back_way = "left" if self.offset > 0 else "right"
        self.back_until = now + self.BACK_FOR
        self.still_since = None
        self.colour = None                         # (and look at the road again after)


class Platformer(Instinct):
    """Runs the way it's going (the run button held, if the game has one) and jumps: when it's held that way and the
    view's stopped moving (a wall, a pipe), longer each time; when the floor ahead drops away (the background's
    colour showing at the bottom of the screen ahead, where there's floor under it); when something's moving just
    ahead of it, low down, on its own (not as the view moves: an enemy coming); and now and then anyway. When
    jumping hasn't got it past something, it backs off for a run-up. In a game with a button to shoot or attack (said
    of it: not just how most games go), it presses that every so often too."""

    BLOCKED = 3               # looks in a row not moving on, holding that way: blocked
    FAR = 16                  # pixels (of its small picture) beyond where the view's been: new ground
    PAST = 32                 # ...and this much beyond that again, the decision model playing: that's past what
                              # stopped it (a third of the screen across)
    CUT = (0.5, 24, 0.5)      # the screen's changed altogether (another room, a life lost, a menu): this share of
                              # its small picture this much lighter or darker (of 255) than this many seconds
                              # before, with nothing scrolled by between
    HOP = (1.4, 3.0)          # seconds between hops, at random
    JUMPS = (0.30, 0.45, 0.6, 0.6)   # how long jumps are held, try by try (a longer press jumps higher)
    BACK_FOR = 0.5

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.jump_until = self.rest_until = self.back_until = 0.0
        self.next_hop = None
        self.blocked = self.tries = 0
        self.going = 0                             # looks in a row moving on
        self.scrolled = 0                          # ...and in all: a level that scrolls by as it's run through
        self.pos = 0.0                             # where the view is: how far it's scrolled by on balance (pixels
        self.lo = self.hi = 0.0                    # of its small picture: + to the right); the furthest it's been
        self.far_at = None                         # each way (the ground it's covered: back over it isn't getting
                                                   # anywhere, whichever way it's told the level goes); and when
                                                   # that last grew (pitato/anygame.py: no new ground for a long
        self.shots = 0                             # while, and the decision model's handed the game)
        self.goal = None                           # the decision model playing (hand): where's past what stopped
        self.cut, self.ref = False, None           # this (beyond the ground covered, either way); whether the
                                                   # screen's changed altogether since; and the look that's told by:
                                                   # (its grey picture, when, where the view was then)
        self.holding = None                        # the way it held last ("right", "left"), for scroll()
        self.drift = (None, 0.0)                   # ...the way the view last moved, and when
        self.ticked = None                         # when it last played a moment (tick)

    def gap_ahead(self, a):
        """The floor ahead drops away: low down in front, the background's colour (from high up the screen), where
        there's floor underneath."""
        h, w = a.shape[:2]
        sky, spread = common_colour(a[int(h * 0.12):int(h * 0.4)])
        low = a[int(h * 0.88):]
        like_sky = np.abs(low - sky).sum(axis=2) < max(30.0, spread * 4)
        if self.way == "right":
            under, ahead = like_sky[:, int(w * 0.36):int(w * 0.5)], like_sky[:, int(w * 0.52):int(w * 0.66)]
        else:
            under, ahead = like_sky[:, int(w * 0.5):int(w * 0.64)], like_sky[:, int(w * 0.34):int(w * 0.48)]
        if under.mean() > 0.3:                     # (no floor under it: it's in the air, or this isn't that game)
            return False
        cols = ahead.mean(axis=0) > 0.8
        return any(e - s >= max(2, w // 30) for s, e in runs(cols))

    def coming(self, prev, g, s):
        """Something moving on its own just ahead, low down: what's there unlike the last look, the view's own
        move (s) taken out."""
        h, w = g.shape
        was = np.roll(prev, -s, axis=1)            # (what was at x + s is at x now)
        cols = slice(int(w * 0.52), int(w * 0.68)) if self.way == "right" else slice(int(w * 0.32), int(w * 0.48))
        box = np.abs(g - was)[int(h * 0.55):int(h * 0.88), cols]
        return float((box > 40).mean()) > 0.02

    def shooter(self, run, jump):
        """Its shooting button, if it's been said to have one (and it's not running or jumping too)."""
        told = self.roles.get("told", ())
        b = self.button("fire") if "fire" in told else self.attacks()[0] if "attack" in told else None
        return b if b not in (run, jump) else None

    def tick(self, look, now):
        a = small(look)
        g = grey(a)
        prev = self.prev
        self.moved(g)
        run, jump = self.button("run"), self.button("jump")
        shoot = self.shooter(run, jump)
        self.shots += 1
        shoot = shoot if shoot and self.shots % 4 == 0 else None   # (pressed one moment in four: a new press each)
        back = OPPOSITE[self.way]
        if self.next_hop is None:
            self.next_hop = now + random.uniform(*self.HOP)
        if self.far_at is None:                               # (just begun, or its own to play again: no new
            self.far_at = now                                 #  ground is counted from now)
        elif self.ticked is not None and now - self.ticked > 1.0:
            self.far_at += now - self.ticked                  # (not its to play meanwhile, as the game was got going
        self.ticked = now                                     #  again: that's not time it got no further in)
        moving_on = False
        s = self.scroll(prev, g, now, self.holding)
        if now < self.back_until:
            self.said, self.holding = "Backing off for a run-up", back
            return [self.step((run,), (back,))]
        if s is not None:
            moving_on = (s if self.way == "right" else -s) >= 1
        self.going = self.going + 1 if moving_on else 0
        self.scrolled += moving_on
        jumping = now < self.jump_until
        if not jumping and now >= self.rest_until:
            self.blocked = 0 if moving_on else self.blocked + 1
            why = None
            if self.blocked >= self.BLOCKED:
                why = "blocked"
            elif self.gap_ahead(a):
                why = "gap"
            elif s is not None and self.coming(prev, g, s):
                why = "enemy"
            elif now >= self.next_hop:
                why = "hop"
            if why == "blocked" and self.tries >= len(self.JUMPS):
                self.tries, self.blocked = 1, 0     # (jumping hasn't done it: back off, for a run-up)
                self.back_until, self.holding = now + self.BACK_FOR, back
                return [self.step((run,), (back,))]
            if why:
                held = self.JUMPS[min(self.tries, len(self.JUMPS) - 1)] if why == "blocked" else \
                    0.6 if why == "gap" else 0.35 if why == "enemy" else random.uniform(0.2, 0.45)
                self.tries += why == "blocked"
                self.jump_until, self.rest_until = now + held, now + held + self.TICK
                self.next_hop = now + random.uniform(*self.HOP)
                jumping = True
                self.blocked = 0
                self.said = {"blocked": "Jumping over something", "gap": "Jumping a gap",
                             "enemy": "Jumping something coming", "hop": "Running"}[why]
        if self.going >= 10:
            self.tries = 0
        if not jumping:
            self.said = "Running"
        self.holding = self.way
        return [self.step((run, jump if jumping else None, shoot), (self.way,))]

    def stuck(self, now):
        """Got nowhere for a while: the other way for a few seconds (the level may go that way)."""
        self.back_until = now + 3.0

    def scroll(self, prev, g, now, held=None):
        """How far the view's moved since the last look, as motion() has it (pixels of its small picture: + when
        what's on it moved left; None with no look before this one), and counted into where the view is and the
        ground it's covered. For that count, scenery that repeats (a tiled floor under a plain sky) is told apart
        by the way it's going: of shifts that match about as well, the one the way that's held (held: "right",
        "left"; None: not known, so the way the view last moved)."""
        if prev is None or prev.shape != g.shape:
            return None
        errs = {}
        best, err, err0 = shift(prev, g, max(3, g.shape[1] // 10), errs=errs)
        s = best if err < 0.85 * err0 else 0
        by = s
        way = held or (self.drift[0] if now - self.drift[1] <= 0.5 else None)
        if s and way and (s > 0) != (way == "right"):
            alike = [t for t, e in errs.items() if t and (t > 0) == (way == "right") and e <= 1.2 * err + 0.05
                     and e < 0.85 * err0]
            if alike:
                by = min(alike, key=lambda t: (errs[t], abs(t)))
        if by:
            self.drift = ("right" if by > 0 else "left", now)
            self.pos += by
            if self.pos > self.hi + self.FAR:
                self.hi, self.far_at = self.pos, now
            elif self.pos < self.lo - self.FAR:
                self.lo, self.far_at = self.pos, now
        return s

    def hand(self):
        """The decision model plays from here, a move at a time (pitato/anygame.py: this covered no new ground),
        and watch() takes its looks meanwhile. Past what stopped this is PAST beyond the ground it's covered."""
        self.goal = (self.lo - self.FAR - self.PAST, self.hi + self.FAR + self.PAST)
        self.cut, self.ref = False, None

    def watch(self, look, now, held=None):
        """A look, while the decision model plays (held: the way its move holds, if it holds one): how far the
        level's scrolled by is counted on, and whether the screen's changed altogether (most of it unlike half a
        second before, with nothing scrolled by between: another room, a life lost, a menu)."""
        g = grey(small(look))
        prev, self.prev = self.prev, g
        self.scroll(prev, g, now, held)
        ref = self.ref
        if ref is None or ref[0].shape != g.shape:
            self.ref = (g, now, self.pos)
        elif now - ref[1] >= self.CUT[2]:
            share, by, _ = self.CUT
            if abs(self.pos - ref[2]) < 2 and float((np.abs(g - ref[0]) > by).mean()) >= share:
                self.cut = True
            self.ref = (g, now, self.pos)

    def past(self):
        """...and it's past what stopped this: the view's beyond all the ground this had covered."""
        return self.goal is not None and not self.goal[0] < self.pos < self.goal[1]

    def unhand(self):
        """Its own to play again: no new ground is counted from now."""
        self.goal = self.far_at = None


class Fighter(Instinct):
    """Goes at the other fighter (on the side it's told: right to start with, as player 1 starts on the left) with
    a mix of moves: stepping in, quick attacks, blocking (holding away), jumping in with an attack, and special
    moves (a quarter circle forward and a punch; forward, down, down-forward and a punch)."""

    def tick(self, look, now):
        self.moved(grey(small(look)))
        toward, away = self.way, OPPOSITE[self.way]
        hits = self.attacks()
        hit = random.choice(hits)
        punch = hits[0]
        r = random.random()
        if r < 0.25:
            self.said = "Moving in"
            return [self.step((), (toward,), 0.25)]
        if r < 0.6:
            self.said = "Attacking"
            return [self.step((hit,), secs=0.08), self.step(secs=0.06)]
        if r < 0.7:
            self.said = "Blocking"
            return [self.step((), (away,), 0.45)]
        if r < 0.8:
            self.said = "Jumping in"
            return [self.step((), ("up", toward), 0.12), self.step((hit,), secs=0.3)]
        self.said = "A special move"
        if r < 0.92:
            return [self.step((), ("down",), 0.05), self.step((), ("down", toward), 0.05),
                    self.step((), (toward,), 0.05), self.step((punch,), (toward,), 0.08), self.step(secs=0.05)]
        return [self.step((), (toward,), 0.05), self.step((), ("down",), 0.05),
                self.step((), ("down", toward), 0.05), self.step((punch,), ("down", toward), 0.08), self.step(secs=0.05)]

    def stuck(self, now):
        self.way = OPPOSITE[self.way]              # (maybe they're the other side now)


class Shooter(Instinct):
    """Keeps firing (pressed and let go each moment: most games fire again only for a new press) and weaves about:
    up and down when the game scrolls sideways, left and right when it scrolls up; now and then it holds still."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.across = self.along = 0.0             # how much it's scrolled sideways, and up or down
        self.move, self.move_until = None, 0.0

    def tick(self, look, now):
        g = grey(small(look))
        prev = self.prev
        self.moved(g)
        if prev is not None and prev.shape == g.shape:
            sx = motion(prev, g, 4, axis=1)
            sy = motion(prev, g, 4, axis=0)
            self.across = 0.9 * self.across + abs(sx)
            self.along = 0.9 * self.along + abs(sy)
        if now >= self.move_until:
            ways = ("left", "right") if self.along > 1.5 * self.across else ("up", "down")
            self.move = random.choice(ways + (None,))
            self.move_until = now + random.uniform(0.3, 0.9)
        fire = self.button("fire") or self.attacks()[0]
        self.said = "Shooting"
        half = round(self.TICK / 2, 3)
        return [self.step((fire,), (self.move,), half), self.step((), (self.move,), half)]

    def stuck(self, now):
        self.move_until = 0.0


INSTINCTS = {"racing": Racing, "platformer": Platformer, "fighting": Fighter, "shooter": Shooter}


# ---- pressing on: getting a game going, and getting on when it waits -------------------------------------------
# what picks things on each console (its Start comes first, but on a Master System: its Pause is on the console)
CONFIRM = {"snes": ("a", "b"), "genesis": ("a", "b"), "sms": ("b", "a"), "gg": ("b", "a"), "n64": ("b",),
           "ps1": ("b", "a"), "psp": ("b", "a"), "dc": ("b",), "neogeo": ("b",), "ngp": ("b", "a"),
           "ngpc": ("b", "a")}                       # (as the emulator names them: pitato/anygame.py's BUTTONS)
BACK = {"n64": "y", "ps1": "x", "psp": "x"}          # ...and what goes back, where that's not B: an N64's B, Triangle
COIN = {"neogeo": "select"}                          # an arcade game: a coin before Start does anything


class PressOn:
    """What a person does without thinking when a game's waiting for them: presses Start, then A, until it's going.
    Logos, a title screen, menus, a file to pick, a name to put in, pages of text, GAME OVER: it presses through them,
    whatever the decision model says or doesn't (the model can still press things itself, and move a menu's cursor:
    while it's getting somewhere that way, it's left to it).

    Each look (tick), it tells whether the screen's showing anything new (unlike every look of the last several
    seconds: PRESS START blinking isn't) and whether it's moving at all. While the game's yet to get going, it presses
    when nothing new's come for a second (the game's waiting), sooner after a press that worked (a page of text after
    another), and every few seconds anyway (a title screen can be all movement); it watches what comes of each press,
    and goes by that: the button that worked again, else the next one, in turn; when none does anything, twice over,
    the menu's cursor moved (Down, then picked), and in the end B. A press worked when it brought something new: not
    a screen it's pressed its way to before (into a menu's options and out again, round and round); and when most of
    its last presses brought nothing, though one in a few did, it's the cursor's turn too.

    A still screen may be the game itself, waiting to be played, and Start would only pause it. So before it presses
    anything on a still screen it hasn't tried, it walks a moment (the way the game goes; and back, if nothing moved:
    there may be a wall that way, and a menu's cursor ends where it was): a screen that moves along with that, and
    stops when it stops, is the game, and it's going (going). Start that stops a moving screen (dead, or all but)
    has paused the game: Start again, and it's going. Start that did nothing to be seen on a still screen may have
    paused the game, or let it go on (paused before, and looking just the same): it walks a moment again; a screen
    that moves now is the game, playing on, and one that doesn't gets Start once more, to leave it as it was. And
    when pressing has brought nothing many times over, or a few times with the screen moving all the while, or the
    model says it's being played and new things keep coming, or (an action game) the same button keeps bringing a
    little something new and never another screen (the gas, at the start of a race), it's taken for the game: on
    with it. Only taken for
    it, though (a title screen can be all movement, and play its own demo): so now and then it presses Start to
    see, less and less often. The screen stopping (paused) settles it: Start again, and it's sure. Another screen
    altogether: it wasn't going yet.

    Once it's going, it presses on when the screen's stopped dead for a couple of seconds (text, a level's end, GAME
    OVER, or the game paused): what picks things, then Start (and the walk after, as above). And when the screen's
    moving but nothing new's come for several seconds: what picks things. Less and less often, while that brings
    nothing. again(): it's got nowhere for a long while (a title screen once more, after a game over): from the
    top."""

    KEEP = 64                # looks kept, several seconds of them, to tell something new from what's just been seen
    BEEN = 32                # ...and the screens its presses were made on and led to, kept longer
    DIFF = 16                # a cell this much lighter or darker than another look's (of 255) is different there
    NEW = 0.02               # this share of a look's cells unlike every look kept: something new
    BIG = 0.25               # ...this much: another screen altogether
    SAME = 0.003             # less than this share changed since the look before: it didn't move
    LIVELY = 0.45            # seconds back its sense of how much the screen's moving goes
    IDLE = 1.0               # seconds with nothing new, getting it going: it's waiting for a press
    IDLE_AGAIN = 0.6         # ...after a press that worked (a page of text after another)
    FIRST = 2.5              # seconds in, its first press at the latest
    ANYWAY = 4.0             # seconds after a press that it presses again though the screen's moving
    ROLL = 1.5               # ...when that press brought another screen altogether
    WATCH = 1.3              # seconds it watches what came of a press, at most...
    SETTLED = 0.4            # ...or till what it brought has stood still this long
    PAUSED = 0.4             # seconds not moving, after Start on a moving screen: it paused the game...
    STILLER = 0.2            # ...or the screen moving this share of what it did, at most (PAUSE blinking on it)
    STILL = 0.3              # seconds not moving: the screen's standing still
    WALK = 0.5               # seconds it walks for, to see whether a still screen's the game...
    WALKING = 0.6            # ...it is, when the screen moved at this share of its looks meanwhile
    WALKS = 12               # ...tried at most this many times, getting it going
    GIVE_UP = 12             # presses in a row that brought nothing: it's the game itself, on with it
    MOVING = 5               # ...and presses with the screen moving all the while
    PLAYED = 2.0             # seconds of new things coming, the model saying it's being played: it is
    SAME_AGAIN = 3           # times running a button brought a little something new, in an action game: it is
    STOPS = 0.4              # seconds it stands after a walk that moved the screen: the game's stopped too (mostly)
    PROBE = 8.0              # seconds on, taken for the game but not sure, till Start's pressed to see (then twice
                             # as long, each time)
    REPEATS = 3              # on a moving screen, the button that worked, again, at most this many times running
    LATELY = 12              # its last presses, getting it going: when half of them brought nothing, the cursor's moved
    DEAD = 2.0               # seconds the screen's stood dead still, once it's going: it presses on
    IDLE_GOING = 6.0         # seconds with nothing new, the screen moving, before it presses on (an action game)
    IDLE_TURN = 4.0          # ...in a game played a move at a time
    REST_MOST = 30.0         # seconds between its tries, at most, while they bring nothing

    def __init__(self, system, live=False, fresh=True, log=None, stick=False):
        self.system, self.live, self.stick, self.log = system, live, stick, log or (lambda words: None)
        confirm = CONFIRM.get(system, ("a",))
        start = () if system == "sms" else ("start",)
        coin = (COIN[system],) if system in COIN else ()
        self.base = coin + start + confirm + (("start",) if system == "sms" else ())
        self.confirm = confirm[0]
        self.menu = ("down", self.confirm, "start", "down", self.confirm, "up", "up", self.confirm, "right",
                     self.confirm, BACK.get(system) or ("b" if "b" not in confirm else "a"), "left", self.confirm)
        self.going = not fresh                     # the game's going (past its title screen and its menus)...
        self.sure = not fresh                      # ...for sure (it moved as it was walked, or Start paused it)
        self.probes, self.probe_at = 0, 0.0        # (Start pressed to see, how often, and when next)
        self.rows = self.prev = self.been = None
        self.n = self.at = self.been_n = self.been_at = 0
        self.t0 = self.last_new = self.last_press = self.seen_at = None
        self.still = 0                             # looks in a row not moving...
        self.still_since = None                    # ...and since when
        self.lively, self.motion = 0.0, 0.0        # how often it's moved a lot lately (0 to 1), and how much of it
        self.stir = 0.0                            # ...and how often it's moved at all
        self.watch = None                          # what's being watched: a press, or a walk
        self.fails = self.moving_presses = self.repeats = self.walks = self.fruitless = 0
        self.lately, self.menu_at = [], 0          # whether each of its last presses worked; where the cursor's got to
        self.streak = 0                            # times running the same button's brought a little something new
        self.last = None                           # the last button pressed: (which, whether it worked, whether the
                                                   # screen was moving then)
        self.walked = False                        # this still screen's been walked on already
        self.played_since = None                   # since when it's moved on, the model saying it's being played
        self.pending = []                          # presses still to make, one after another
        self.rest_until = 0.0
        self.quiet = False                         # it's pressing on: nothing else held meanwhile
        self.pressed = []                          # (every button it's pressed)
        self.way = "right"                         # (the way the game goes: the way it walks)
        self.said = ""

    # -- looking -------------------------------------------------------------------------------------------------
    def novelty(self, rows, cells):
        if rows is None or not len(rows):
            return 1.0
        return float((np.abs(rows - cells) > self.DIFF).mean(axis=1).min())

    def see(self, look, now):
        """A look taken in: how much of it moved since the last one."""
        cells = look.cells.astype(np.int16)
        if self.rows is None or self.rows.shape[1] != cells.size:
            self.rows, self.n, self.at, self.prev = np.zeros((self.KEEP, cells.size), np.int16), 0, 0, None
            self.been, self.been_n, self.been_at = np.zeros((self.BEEN, cells.size), np.int16), 0, 0
        new = self.novelty(self.rows[:self.n], cells)
        moved = float((np.abs(cells - self.prev) > self.DIFF).mean()) if self.prev is not None else 1.0
        self.prev = cells
        self.rows[self.at] = cells
        self.at, self.n = (self.at + 1) % self.KEEP, min(self.n + 1, self.KEEP)
        if self.t0 is None:
            self.t0 = self.last_new = self.seen_at = now
            self.last_press = now - self.ANYWAY + self.FIRST
        elif new >= self.NEW:
            self.last_new = now
            self.fruitless = 0
            if new >= self.BIG and self.watch is None:   # (another screen altogether, by itself or by the model's
                self.walked, self.fails = False, 0       # doing: tried afresh)
        if moved < self.SAME:
            self.still += 1
            if self.still_since is None:
                self.still_since = now
        else:
            self.still, self.still_since = 0, None
        share = 1.0 - math.exp(-max(0.0, min(2.0, now - self.seen_at)) / self.LIVELY)
        self.seen_at = now
        self.lively += share * ((moved >= self.NEW) - self.lively)
        self.stir += share * ((moved >= self.SAME) - self.stir)
        self.motion += share * (moved - self.motion)
        return moved, cells

    def dead(self, now):
        """Seconds the screen's stood dead still."""
        return 0.0 if self.still_since is None or self.still < 2 else now - self.still_since

    def idle(self, now):
        """Seconds since the screen last showed something new."""
        return 0.0 if self.last_new is None else now - self.last_new

    def before(self):
        """What's been on the screen: the last looks, and the screens it's pressed on and to. The screen now's kept
        with those."""
        if self.prev is not None:
            self.been[self.been_at] = self.prev
            self.been_at, self.been_n = (self.been_at + 1) % self.BEEN, min(self.been_n + 1, self.BEEN)
        return np.concatenate((self.rows[:self.n], self.been[:self.been_n]))

    # -- pressing ------------------------------------------------------------------------------------------------
    def tap(self, what, now, watch=True):
        """A button pressed and let go (as steps), and watched."""
        self.pressed.append(what)
        self.last_press = now
        self.said = "Pressing " + ("the stick " if self.stick and what in OPPOSITE else "") + what.capitalize()
        if watch:
            self.watch = {"what": what, "at": now, "until": now + self.WATCH, "effect": 0.0, "lively": self.lively,
                          "stir": self.stir, "rate": self.motion, "after": 0.0, "n": 0,
                          "dead": self.dead(now) >= self.STILL,
                          "moves": 0, "before": self.before()}
        if self.stick and what in OPPOSITE:              # (a stick console's menus: the stick, not the d-pad)
            axis, v = ("lx", -127 if what == "left" else 127) if what in ("left", "right") else \
                ("ly", -127 if what == "up" else 127)
            return [(set(), {axis: v}, 0.12), (set(), {}, 0.06)]
        return [({what}, {}, 0.06), (set(), {}, 0.06)]

    def walk_step(self, way):
        if self.stick:
            return [(set(), {"lx": -127 if way == "left" else 127}, 0.1)]
        return [({way}, {}, 0.1)]

    def next_button(self):
        """What to press now, getting it going: the one that just worked again (on a moving screen it can't be sure
        the button did it: a few times running at most), else the next in turn; and when they've all done nothing
        twice over, a menu's cursor moved and picked."""
        what, ok, moving = self.last or (None, False, False)
        if ok and what in self.base and (not moving or self.repeats < self.REPEATS):
            self.repeats += 1
            return what
        self.repeats = 0
        rounds = 2 * len(self.base)
        if self.fails >= rounds or self.lately.count(False) >= self.LATELY // 2:
            self.menu_at += 1                            # (a menu with the wrong thing picked, most likely)
            return self.menu[(self.menu_at - 1) % len(self.menu)]
        if what in self.base:                            # (the one after the last, round and round)
            return self.base[(self.base.index(what) + 1) % len(self.base)]
        return self.base[0]

    def tick(self, look, now, says_play=False, helpless=True, way="right"):
        """A look: what to press now, as steps [(buttons, sticks, seconds)], or None (nothing: whoever plays goes on).
        says_play: the decision model says the game's being played (it's played by instinct meanwhile). helpless: the
        model isn't getting through this itself (it's not answering, or what it picks brings nothing new). way: the
        way the game goes (to walk a moment)."""
        if look is None:
            return None
        moved, cells = self.see(look, now)
        idle = self.idle(now)
        self.way = way
        w = self.watch
        if w is not None:
            w["effect"] = max(w["effect"], self.novelty(w["before"], cells))
            if w["what"] == "walk":                       # (walked a moment: does the screen move along with it,
                if now >= w["from"]:                     # look after look? even a little: someone walking, the view
                    w["looks"] += 1                      # not moving yet)
                    w["moved"] += moved >= self.SAME
                if now < w["until"] or (w["looks"] < 3 and now < w["until"] + 1.0):
                    return [(set(), {}, 0.1)] if w["stood"] else self.walk_step(w["way"])
                walking = w["looks"] >= 3 and w["moved"] >= self.WALKING * w["looks"]
                if w["stood"]:                           # (it moved as it was walked: and stopped as it stopped?)
                    self.watch = None
                    stopped = w["looks"] >= 3 and w["moved"] <= (1 - self.WALKING) * w["looks"]
                    if self.going:                       # (Start let a paused game go on)
                        self.log("...and it moves as it's walked: the game plays on")
                        self.fruitless, self.rest_until, self.sure = 0, now + 1.0, self.sure or stopped
                    elif stopped:
                        self.get_going("It moves as it's walked: the game's going", sure=True)
                    else:                                # (it may be moving by itself: not sure)
                        self.get_going("It moves as it's walked, and on: taken for the game")
                    return None
                if walking:                              # (let go: a moment to come to a stop, then watched)
                    w.update(stood=True, until=now + 0.2 + self.STOPS, looks=0, moved=0)
                    w["from"] = now + 0.2
                    return [(set(), {}, 0.1)]
                if not w["back"]:                        # (nothing moved: a wall that way, perhaps: and back)
                    w.update(way=OPPOSITE[w["way"]], back=True, until=now + self.WALK, looks=0, moved=0)
                    return self.walk_step(w["way"])
                self.watch = None
                if w.get("then"):                        # (Start changed nothing, and it doesn't move: Start once
                    return self.tap(w["then"], now, watch=False)   # more, to leave it as it was)
            else:
                w["moves"] += moved >= self.SAME
                if now - w["at"] >= 0.3:                 # (how much it's moving, once the press has sunk in)
                    w["after"], w["n"] = w["after"] + moved, w["n"] + 1
                paused = w["what"] == "start" and w["stir"] >= 0.5 and self.dead(now) >= self.PAUSED
                settled = w["effect"] >= self.NEW and self.dead(now) >= self.SETTLED and now - w["at"] >= 0.3
                if now < w["until"] and not paused and not settled:
                    return None
                self.watch = None
                got = self.came(w, now)
                if got is not None:
                    return got
        if self.pending:
            return self.tap(self.pending.pop(0), now, watch=not self.pending)
        self.quiet = False
        if self.going:
            if not helpless:
                return None
            stale = idle >= (self.IDLE_GOING if self.live else self.IDLE_TURN)
            if not self.sure and now >= self.probe_at and self.dead(now) < self.STILL and (self.lively >= 0.5 or stale):
                self.quiet, self.probes = True, self.probes + 1      # (taken for the game, the screen moving: Start,
                self.probe_at = now + self.PROBE * 2 ** self.probes  # to see whether it is)
                steps = self.tap("start", now)
                self.watch["probe"] = True
                return steps
            if now < self.rest_until:
                return None
            if self.dead(now) >= self.DEAD:              # (stopped dead: text, a level's end, GAME OVER, or paused:
                self.quiet = True                        # what picks things, then Start)
                self.pending = ["start"]
                return self.tap(self.confirm, now)
            if stale:                                    # (moving, but nothing new: what picks things, in passing)
                return self.tap(self.confirm, now)
            return None
        if self.fails >= self.GIVE_UP or self.moving_presses >= self.MOVING:
            self.get_going("Pressing on brings nothing more: it's the game, on with it")
            return None
        if says_play and self.lively >= 0.5 and idle < 0.5:   # (the model says it's being played, it's played by
            if self.played_since is None:                    # instinct, and new things keep coming: it is)
                self.played_since = now
            elif now - self.played_since >= self.PLAYED:
                self.get_going("It moves on as it's played: the game's going")
                return None
        else:
            self.played_since = None
        worked = bool(self.last and self.last[1])
        anyway = self.ROLL if self.last and self.last[1] == "big" else self.ANYWAY
        waiting = idle >= (self.IDLE_AGAIN if worked else self.IDLE)
        if says_play and self.dead(now) < self.STILL:    # (played by instinct, and moving: it's given a moment to
            waiting = False                              # show it's the game, before anything's pressed on it)
        due = waiting or (now - self.last_press >= anyway and (self.lively >= 0.5 or not self.pressed))
        if not due or not helpless or now - self.t0 < min(self.FIRST, 1.5):
            return None
        if waiting and self.dead(now) >= self.STILL and not self.walked and not says_play \
                and self.walks < self.WALKS:
            self.walked, self.walks = True, self.walks + 1   # (a screen standing still: is it the game, waiting to
            return self.walk(now)                            # be played? walked a moment, to see)
        return self.tap(self.next_button(), now)

    def came(self, w, now):
        """What came of a press, now it's been watched: steps (Start again), or None."""
        what, effect = w["what"], w["effect"]
        if self.prev is not None:                        # (the screen it led to: kept)
            self.been[self.been_at] = self.prev
            self.been_at, self.been_n = (self.been_at + 1) % self.BEEN, min(self.been_n + 1, self.BEEN)
        name = what.capitalize()
        moving = w["lively"] >= 0.5
        stiller = w["n"] >= 4 and w["rate"] >= 0.01 and w["after"] / w["n"] < self.STILLER * w["rate"]
        if what == "start" and effect < self.BIG and (w["stir"] >= 0.5 and self.dead(now) >= self.PAUSED
                                                      or moving and stiller):
            self.log("Start pressed: that paused the game. Start again, to play on")
            self.get_going(sure=True)
            return self.tap("start", now, watch=False)
        ok = effect >= self.NEW
        if self.going and w.get("probe"):                # (Start, to see whether it's the game: it didn't pause)
            if effect >= self.BIG:
                self.log("Start pressed, to see: another screen. It wasn't going yet")
                self.unsure(now)
                self.last = (what, "big", moving)
            else:
                self.log("Start pressed, to see: it didn't pause")
            return None
        if self.going:                                   # (pressing on, once it's going)
            if ok or (w["dead"] and w["moves"] >= 3):    # (something new, or a dead screen moving again: that did it)
                self.log(f"{name} pressed, as the game waited: on it goes")
                self.pending, self.fruitless = [], 0
                self.rest_until = now + 1.0
                return None
            if what == "start":
                self.log("Start pressed, as the game waited: nothing came of it")
                self.rest()
                if self.dead(now) >= self.STILL:         # (Start that left the screen dead may have paused it, or
                    return self.walk(now, then="start")  # let it go on: walked, to see)
                return None
            if not self.pending:
                self.log(f"{name} pressed, as the game waited: nothing came of it")
                self.rest()
            return None
        if moving and not (ok and effect >= self.BIG and self.dead(now) > 0):
            self.moving_presses += 1                     # (the screen moving all the while: it can't tell)
        else:
            self.moving_presses = 0
        self.lately = (self.lately + [ok])[-self.LATELY:]
        little = ok and effect < self.BIG and what != "start" and bool(self.last) and self.last[0] == what
        self.streak = self.streak + 1 if little else 0
        if ok:
            self.log(f"{name} pressed: " + ("another screen" if effect >= self.BIG else "something new"))
            self.fails = 0
            if effect >= self.BIG:
                self.walked = False
            self.last = (what, "big" if effect >= self.BIG else True, moving)
            if self.live and self.streak >= self.SAME_AGAIN:
                self.get_going(f"{name} keeps bringing a little something new: taken for the game")
            return None
        self.log(f"{name} pressed: nothing came of it")
        self.fails += 1
        if self.fails == 2:                              # (not a screen that takes Start or A: the game, perhaps,
            self.walked = False                          # after its text: walked once more, to see)
        self.last = (what, False, moving)
        if what == "start" and self.dead(now) >= self.STILL:   # (Start that did nothing may have paused a game
            if self.walks < self.WALKS:                        # that's standing still, or let it go on: walked, to
                self.walks += 1                                # see; then Start once more)
                return self.walk(now, then="start")
            return self.tap("start", now, watch=False)
        return None

    def walk(self, now, then=None):
        """Walking a moment, watched (then: what's pressed after, if the screen didn't move with it)."""
        self.said = "Trying the game"
        self.watch = {"what": "walk", "way": self.way, "back": False, "stood": False, "until": now + self.WALK,
                      "from": now, "effect": 0.0, "moved": 0, "looks": 0, "before": self.before(), "then": then}
        return self.walk_step(self.way)

    def rest(self):
        """Pressing on brought nothing, once it's going: longer till the next try, each time."""
        self.fruitless += 1
        self.rest_until = (self.last_press or 0.0) + min(self.REST_MOST, self.IDLE_TURN * self.fruitless)
        self.pending = []

    def get_going(self, why="", sure=False):
        if why:
            self.log(why)
        if not self.going:
            self.probes, self.probe_at = 0, (self.last_press or 0.0) + self.PROBE
        self.going, self.fails, self.moving_presses, self.pending = True, 0, 0, []
        self.fruitless, self.quiet, self.played_since, self.streak = 0, False, None, 0
        self.sure = self.sure or sure

    def unsure(self, now):
        """Not going after all: getting the game going, from the top."""
        self.going, self.sure, self.fails, self.moving_presses, self.last, self.pending = False, False, 0, 0, None, []
        self.repeats = self.walks = self.fruitless = self.menu_at = 0
        self.lately = []
        self.walked, self.rest_until, self.played_since = False, 0.0, None

    def again(self, now):
        """It's got nowhere for a long while: getting the game going, from the top (it's at that already, if it's
        yet to get going)."""
        if self.going:
            self.log("Nothing new for a long while: getting the game going again (back at a title screen?)")
            self.unsure(now)
