"""What the AI player learns by playing, and a platformer its instincts can't get through (pitato/coach.py's Learned:
lines, pitato/anygame.py). The notes' own words for it: a line it's learned made plain (and nothing kept of "None"),
two that say the same, a new one added after the last (one it has already moved there, not said twice; the oldest
gone past the most it keeps; your tips, your # lines and its other lines as they were). The coach, your Bot's model
on a pretend Ollama: told what's happened, it's asked for a line to remember with its next look (and only then),
told where the player was stuck as it saw it; the line's kept in the notes beside the game's saves, told to it
every time after, read by the next game's coach, and by one with no model; a line you change or take out is yours.
The player, on pretend games in their own time (tests/pretend_games.py): stuck a long while, the coach is told what
it's tried; stuck and then on again (three moves running that brought something new), which moves did it; moving
about without either, nothing; what's been learned goes with each of the decision model's picks. And a platformer
with a gate across it that only a button opens: by instinct it gets no further for half a minute, so the decision
model's handed it, a move at a time, opens the gate and walks on, and once the level's scrolled by further than it
ever had, its instincts have it back (sooner at the next gate); the coach is told how it got past; a model that
gets it no further in two dozen moves hands it back too (the coach told what was tried, twice at most); the screen
changing altogether hands it back as well (the coach told that, and the moves before it: it can't tell a life lost
from a new room); what its buttons do, said meanwhile, is taken up once its instincts have the game; a model that
isn't answering is never handed it, nor is a game of one screen, nor one its instincts get through (a floor that
repeats under a plain sky and all)."""
import json, os, shutil, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import numpy as np
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, ROOT)
from PIL import Image
from pitato import anygame as AG, coach as C, gameai as A, instincts as I
from pretend_games import Level, Room, play_on, silent as silent_model

S = SP + "/t_learned"
shutil.rmtree(S, ignore_errors=True)
SAVES = S + "/Games/Saves"
os.makedirs(SAVES)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


# ---- the notes' own words for it -----------------------------------------------------------------------------------
CRATE = "At the high ledge, B picks up the crate: carry it to the ledge to climb up."
made = C.lesson_of("  **Learned:** " + CRATE.replace(": ", ":\n"))
check(f"a line it's learned, made plain: one line, no Learned: in front, no markdown ({made!r})", made == CRATE)
check("...nothing worth keeping: nothing kept", [C.lesson_of(x) for x in (
    "", None, "None", "none.", "N/A", "Nothing", "Nothing worth keeping.", "nothing new here", "Jump", "Press A")] == [""] * 10)
long = C.lesson_of("The lever by the gate opens it " + "and so on " * 40)
check(f"...a long one: cut short, at a word ({len(long)} characters)", len(long) <= C.LEARNED_LONG + 1 and long.endswith("…")
      and not long[:-1].endswith(" "))
check("two that say the same, in other words' order: the same; two that don't: not", C.same_lesson(
    "Press B to pick up the crate, then carry it to the ledge.", "Carry the crate to the ledge: press B to pick it up then.")
    and not C.same_lesson(CRATE, "At the gate, the lever opens it: press X beside it.") and not C.same_lesson("", ""))
MINE = ("# my notes\nTips: R switches character.\nKind: adventure\nLearned: Donkey kicks doors open with B.\n"
        "Controls: A jumps.\nlearned:   The red switch is under the bridge.  \nStay off the spikes.\nGoal: Find the key\n")
check(f"a notes file's Learned: lines, in order ({C.notes_learned(MINE)}); not tips ({C.notes_parts(MINE)[0]!r})",
      C.notes_learned(MINE) == ["Donkey kicks doors open with B.", "The red switch is under the bridge."]
      and C.notes_parts(MINE) == ("R switches character.\nStay off the spikes.", {"Kind": "adventure", "Controls": "A jumps.",
                                                                                   "Goal": "Find the key"}))
got = C.notes_learning(MINE, CRATE)
check("a new one: after the last of them, every other line as it was", got == MINE.replace(
    "learned:   The red switch is under the bridge.  \n", "learned:   The red switch is under the bridge.  \nLearned: "
    + CRATE + "\n"))
again = C.notes_learning(got, "donkey kicks doors open with b")
check(f"one it has already (in other letters): moved to the end as it was written, not said twice "
      f"({C.notes_learned(again)})", C.notes_learned(again) == ["The red switch is under the bridge.", CRATE,
                                                                "Donkey kicks doors open with B."]
      and again.count("Donkey") == 1 and "# my notes\nTips: R switches character.\nKind: adventure\nControls: A jumps.\n" in again)
many = MINE
for k in range(C.LEARNED_MOST + 5):
    many = C.notes_learning(many, f"Lever {k}a opens gate {k}b on floor {k}c.")
kept = C.notes_learned(many)
check(f"more than it keeps ({C.LEARNED_MOST}): the oldest go ({len(kept)}: {kept[0]!r} to {kept[-1]!r}); your lines all there",
      len(kept) == C.LEARNED_MOST and kept[0].startswith("Lever 5a ") and kept[-1].startswith(f"Lever {C.LEARNED_MOST + 4}a ")
      and "Donkey" not in many and "# my notes\nTips: R switches character.\nKind: adventure\nControls: A jumps.\n" in many
      and "Stay off the spikes.\nGoal: Find the key\n" in many)
check("no file yet, or one with none of them: at its end", C.notes_learning("Tips: x\n", CRATE) == f"Tips: x\nLearned: {CRATE}\n"
      and C.notes_learning("", CRATE) == f"Learned: {CRATE}\n")
check(f"its answer's shape: a line to remember only when it's asked for ({C.schema(learned=True)['required']})",
      "learned" not in C.SCHEMA["properties"] and "learned" not in C.CARD_SCHEMA["properties"]
      and C.schema(learned=True)["required"] == ["screen", "goal", "plan", "controls", "learned"]
      and C.schema(True, True)["required"][-1] == "learned" and C.schema(True, True)["properties"]["kind"]["enum"] == list(C.KINDS))
check("a new notes file's heading says they're its own, and yours to change", "Learned: lines" in C.NOTES_HEAD
      and all(line.startswith("#") for line in C.NOTES_HEAD.splitlines()))


# ---- the coach, your Bot's model on a pretend Ollama -----------------------------------------------------------------
class Fake:
    said, lock = [], threading.Lock()
    answer = {"screen": "A brick ledge, too high to jump onto, with a crate beside you.", "goal": "Get onto the ledge",
              "plan": "Walk left to the crate and press B.", "controls": "A jumps.", "kind": "adventure",
              "buttons": "A: jump; B: pick up", "how": "Use what's around you."}


class Ollama(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        with Fake.lock:
            Fake.said.append(body)
        if body.get("model") == "broken":
            code, obj = 500, {"error": "llama runner process has terminated"}
        else:
            code, obj = 200, {"response": json.dumps(Fake.answer), "done": True}
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


srv = ThreadingHTTPServer(("127.0.0.1", 0), Ollama)
threading.Thread(target=srv.serve_forever, daemon=True).start()
SERVER = f"127.0.0.1:{srv.server_address[1]}"
NOTES = SAVES + "/Shrek 2.ai-notes.txt"
GBA = "A, B, L, R, Start, Select and the d-pad (Up, Down, Left, Right)"
look = A.Look(Image.new("RGB", (240, 160), (40, 90, 160)))
QUIET = {"moves": ["Right, held a second: something new"], "stale": 0, "stuck": False, "mostly": "", "off": [],
         "untried": [], "note": ""}
STUCK = {"moves": ["Right and A together: nothing new"] * 8, "stale": 8, "stuck": True,
         "mostly": "A (on its own and on the move)", "off": [], "untried": ["B", "L", "R", "Select"], "note": ""}
GOT_ON = ("It was stuck: 16 of its moves brought nothing new, mostly A (on its own and on the move). Then it got on. "
          "Its last moves, oldest first: Press B: nothing new; Left, held a second: something new.")
logged = []
co = C.Coach(SERVER, "gemma", NOTES, log=logged.append)
co.game, co.system, co.buttons = "Shrek 2", "Game Boy Advance", GBA
co.think(look, STUCK)
q = Fake.said[-1]
check("the coach, nothing told it yet: no line to remember asked for (what it knows of the game is, the first time)",
      q["format"] == C.CARD_SCHEMA and C.ASK_LEARNED not in q["prompt"] and "Since you last looked" not in q["prompt"]
      and "Learned by playing" not in q["prompt"] and co.learned == [] and not C.notes_learned(open(NOTES).read())
      and "carry things or switch between characters" in q["prompt"])
co.tell(GOT_ON)
check("told what's happened: it looks again soon", co.nudged and co.events == [GOT_ON])
Fake.answer = dict(Fake.answer, screen="A grassy path past the ledge.", goal="Go on to the castle", learned=CRATE)
co.think(look, QUIET)
q = Fake.said[-1]
check("...and with that look it's asked for a line to remember, told what happened and where the player was stuck, as "
      "it saw it then", q["format"] == C.schema(learned=True) and q["prompt"].endswith(C.ASK + C.ASK_LEARNED)
      and f"Since you last looked:\n- {GOT_ON}\nWhere it was stuck, as you saw it then: A brick ledge, too high to jump "
          "onto, with a crate beside you." in q["prompt"] and q["options"]["num_predict"] == 700)
txt = open(NOTES).read()
check(f"...its line, kept in the notes beside the game's saves, after its other lines ({txt.splitlines()[-1]!r}), and "
      f"in its log", txt.endswith(f"Goal: Go on to the castle\nLearned: {CRATE}\n") and co.learned == [CRATE]
      and co.events == [] and logged.count({"event": f"Learned: {CRATE}"}) == 1
      and co.advice["goal"] == "Go on to the castle")
Fake.answer = dict(Fake.answer, learned="The path past the ledge leads on to a castle with a moat.")
co.think(look, QUIET)
q = Fake.said[-1]
check("its next look, nothing new told it: what it's learned is told to it, to go by; no line asked for, and one it "
      "says anyway isn't kept", f"Learned by playing it before (go by these):\n- {CRATE}" in q["prompt"]
      and q["format"] == C.SCHEMA and C.ASK_LEARNED not in q["prompt"] and co.learned == [CRATE]
      and "Where it was stuck" not in q["prompt"])
co.tell("It was stuck: 8 of its moves brought nothing new. Then it got on. Its last moves, oldest first: Press B: "
        "something new.")
Fake.answer = dict(Fake.answer, learned="at the high ledge b picks up the crate, carry it to the ledge to climb up")
co.think(look, QUIET)
check(f"the same thing learned again: not said twice, in its notes or its log ({co.learned})", co.learned == [CRATE]
      and open(NOTES).read().count("\nLearned:") == 1 and co.events == []
      and sum(str(e.get("event")).startswith("Learned:") for e in logged) == 1)
co.tell("It's been stuck a long while: 24 moves with nothing new. It's pressed no button. Not yet: L, R, Select.")
Fake.answer = dict(Fake.answer, learned="None")
co.think(look, STUCK)
check("nothing worth keeping, it says: nothing kept; what it was told is done with", co.learned == [CRATE]
      and co.events == [] and "Since you last looked:\n- It's been stuck a long while" in Fake.said[-1]["prompt"])
co.tell("It was stuck: 8 of its moves brought nothing new. Then it got on. Its last moves, oldest first: Press L: "
        "something new.")
co.model = "broken"
ok = co.think(look, QUIET)
co.model = "gemma"
check("its model couldn't answer: what it was told is kept for its next look", not ok and len(co.events) == 1)
Fake.answer = dict(Fake.answer, learned="L switches to Donkey, who kicks the wooden door open with B.")
co.think(look, QUIET)
check(f"...and learned then ({co.learned[-1]!r})", co.learned == [CRATE, "L switches to Donkey, who kicks the wooden "
                                                                    "door open with B."] and co.events == [])
for k in range(5):
    co.tell(f"thing {k}")
check(f"told more than it keeps till it looks ({C.EVENTS_MOST}): the newest", co.events == ["thing 2", "thing 3", "thing 4"])
with co.lock:
    co.events = []
nxt = C.Coach(SERVER, "gemma", NOTES)
plain = C.Coach(SERVER, "", NOTES)
check(f"the next game's coach reads them ({len(nxt.learned)}), and one with no model too (the decision model's told "
      f"them all the same)", nxt.learned == co.learned and plain.learned == co.learned and plain.lessons() == co.learned
      and plain.lessons(70) == co.learned[-1:] and plain.lessons(10) == [])
time.sleep(0.05)
txt = open(NOTES).read()
open(NOTES, "w").write(txt.replace(CRATE, "At the high ledge, B picks up the crate. Drop it by the ledge and jump from it.")
                       .replace("Learned: L switches to Donkey, who kicks the wooden door open with B.\n", "")
                       + "Hold R to see the map.\n")
co.read_notes()
check(f"one you change, one you take out, a tip you add after them: yours ({co.learned}; {co.tips!r})",
      co.learned == ["At the high ledge, B picks up the crate. Drop it by the ledge and jump from it."]
      and co.tips == "Hold R to see the map.")
co.tell("It was stuck: 8 of its moves brought nothing new. Then it got on. Its last moves, oldest first: Press Select: "
        "something new.")
Fake.answer = dict(Fake.answer, learned="Select shows the map of the swamp.")
co.think(look, QUIET)
txt = open(NOTES).read()
check("...and its next one goes after its last, before your tip", txt.endswith(
    "Learned: At the high ledge, B picks up the crate. Drop it by the ledge and jump from it.\n"
    "Learned: Select shows the map of the swamp.\nHold R to see the map.\n") and co.tips == "Hold R to see the map.")
new = C.Coach(SERVER, "gemma", SAVES + "/New.ai-notes.txt")
new.game, new.system, new.buttons = "New", "Game Boy Advance", GBA
new.tell(GOT_ON)
Fake.answer = dict(Fake.answer, learned=CRATE)
new.think(look, QUIET)
txt = open(SAVES + "/New.ai-notes.txt").read()
check("a game with no notes yet: its heading, a place for your tips, its own lines, then what it learned",
      txt.startswith(C.NOTES_HEAD + "Tips: \nKind: adventure\n") and txt.endswith(f"\nLearned: {CRATE}\n"))


# ---- the player: what it tells the coach ------------------------------------------------------------------------------
class Told:
    """A coach that notes what it's told (and has learned something already, or not). buttons: what it says the
    game's buttons do, once the player's instincts have handed the game over."""

    def __init__(self, learned=(), buttons=""):
        self.advice, self.tips, self.told, self.seen, self.nudges, self.learned = None, "", [], [], 0, list(learned)
        self.buttons, self.says_buttons = "", buttons

    def start(self, *a):
        pass

    def see(self, look, story):
        self.seen.append(story)
        if story.get("note"):
            self.buttons = self.says_buttons

    def nudge(self):
        self.nudges += 1

    def tell(self, words):
        self.told.append(words)

    def controls(self):
        return ""

    def card(self):
        return {"kind": "", "buttons": self.buttons, "how": ""}

    def lessons(self, most=None):
        return list(self.learned)


class BoxRoom(Room):
    """The room, with a door shut beside you: nothing you press moves you, till B opens it."""

    def __init__(self):
        super().__init__()
        self.open = False

    def step(self):
        if "b" in self.held:
            self.open = True
        if not self.open:
            self.frames += 1
            return
        super().step()

    def frame(self):
        img = np.asarray(super().frame()).copy()
        if not self.open:
            img[52:172, 148:188] = (150, 80, 20)
        return Image.fromarray(img)


def boxed(most):
    """A decision model that walks at the door this way and that, till it's done so `most` times; then B, and on."""
    n = [0]

    def model(game, choices, fallback):
        n[0] += 1
        if not game.open and n[0] <= most:
            ways = [k for k in ("right_held", "up_held", "left_held", "down_held") if k in choices]
            return ways[n[0] % len(ways)], "model", 0.5
        return ("right_held" if game.open else "b"), "model", 0.5
    return model


QUEST = ("Zorblax Quest (USA)", "gba")                 # (a game it doesn't know the kind of: a move at a time)
coach = Told(["B opens doors."])
room = BoxRoom()
io, p = play_on(room, *QUEST, boxed(26), 90.0, resumed=True, coach=coach)
stuck = [e["event"] for e in io.logged if str(e.get("event")).startswith("Stuck")]
check(f"a game played a move at a time, the player shut in: stuck, and again ({stuck[:3]})",
      stuck[:3] == [f"Stuck: {8 * k} moves with nothing new" for k in (1, 2, 3)])
check(f"...a long while ({AG.LONG_STUCK} times over): the coach is told what it's tried, once ({coach.told[:1]})",
      len(coach.told) >= 1 and coach.told[0] == "It's been stuck a long while: 24 moves with nothing new. It's pressed no "
      "button. Not yet: A, B, L, R, Select." and sum(t.startswith("It's been stuck") for t in coach.told) == 1)
check(f"...then B opens the door and it walks on, three moves running that brought something new: told how it got on "
      f"({coach.told[1:2]})", room.open and len(coach.told) == 2 and coach.told[1].startswith(
          "It was stuck: 24 of its moves brought nothing new. Then it got on. Its last moves, oldest first: ")
      and coach.told[1].endswith("Press B: something new; Right, held a second: something new; Right, held a second: "
                                 "something new.") and io.said("It was stuck: 24 of its moves"))
asked = [q for q in io.asked if q["kind"] == "move"]
check(f"what's been learned goes with each of the decision model's picks ({asked[-1]['state'].get('learned by playing it before')})",
      all(q["state"].get("learned by playing it before") == ["B opens doors."] for q in asked) and len(asked) > 20)
check("...and with no coach, or one that's learned nothing: not a word of it",
      "learned by playing it before" not in AG.AnyGame({"title": "x", "system": "gba"}, io).state(None)
      and "learned by playing it before" not in AG.AnyGame({"title": "x", "system": "gba"}, io, Told()).state(None))


def wander(first):
    """A decision model that walks up and back down, over and over (nothing new after the first time), for its first
    so many picks; then: back a step, on a step (seen before), on another (new), a little further each time."""
    n = [0]

    def model(game, choices, fallback):
        n[0] += 1
        if n[0] <= first:
            return ("up_held" if game.y >= 300 else "down_held"), "model", 0.5
        return ("left_held", "right_held", "right_held")[(n[0] - first - 1) % 3], "model", 0.5
    return model


coach = Told()
room = Room()
io, p = play_on(room, *QUEST, wander(14), 58.0, resumed=True, coach=coach)
came = [q["state"].get("you did last, oldest first", [""])[-1].rsplit(": ", 1)[-1] for q in io.asked]
runs = max(len(r) for r in "".join("n" if c == "something new" else " " for c in came).split(" "))
check(f"stuck once, then moving about (a step back, two on: something new every third move or so, never three running: "
      f"{came.count('something new')} of {len(came)}, {runs} running at most): it's not told it got on, and that it "
      f"was stuck is let go of ({coach.told})", coach.told == [] and io.said("Stuck: 8 moves") and runs < AG.GOT_ON
      and came.count("something new") >= 8 and p.episode is None and not io.said("Stuck: 16 moves"))


# ---- a platformer its instincts can't get through ---------------------------------------------------------------------
class GatedLevel(Level):
    """The platformer, with nothing in the way but gates too tall to jump (the tiles they're at): X, beside one,
    opens it. Things in the sky tell one place from another. Start pauses it, and Start again plays on. black: Select
    turns the screen black for so many frames, and puts you back at the start (a life lost, as real games show it)."""

    def __init__(self, gates=(40,), black=0):
        super().__init__()
        self.pipes, self.pits, self.enemies = {g: 9 for g in gates}, [], []
        self.opened, self.paused, self.was_start, self.black, self.dark, self.lost = [], False, False, black, 0, 0

    def step(self):
        start = "start" in self.held
        if start and not self.was_start:
            self.paused = not self.paused
        self.was_start = start
        if self.paused:
            self.frames += 1
            return
        if self.dark:
            self.dark -= 1
            self.frames += 1
            return
        if self.black and "select" in self.held:
            self.dark, self.lost, self.x = self.black, self.lost + 1, 3 * 16.0
            return
        if "x" in self.held:
            for g in sorted(self.pipes):
                if 0 < g * 16 - self.x < 48:
                    del self.pipes[g]
                    self.opened.append((g, self.frames / 60.0))
        super().step()

    def frame(self):
        if self.dark:
            return Image.fromarray(np.zeros((self.H, self.W, 3), np.uint8))
        img = np.asarray(super().frame()).copy()
        cam = max(0.0, self.x - 112)
        for sx in range(self.W):
            tx = int((sx + cam) // 16)
            if tx % 4 == 2:
                y0 = 30 + tx * 37 % 40
                img[y0:y0 + 30, sx] = (40 + tx * 53 % 200, 40 + tx * 97 % 200, 40 + tx * 29 % 200)
        return Image.fromarray(img)


def shut(game):
    return [g for g in game.pipes if 0 < g * 16 - game.x < 48]


def helper(game, choices, fallback):
    """Says to play on by instinct; handed the game, walks up to what's in the way, opens it (X) and walks on."""
    if "go_right" in choices:
        return "go_right", "model", 0.6
    return ("x" if shut(game) else "right_held"), "model", 0.8


def fumbler(game, choices, fallback):
    """...or tries this and that, none of which opens anything."""
    if "go_right" in choices:
        return "go_right", "model", 0.6
    fumbler.n += 1
    ways = [k for k in ("up", "down", "left", "right", "wait") if k in choices]
    return ways[fumbler.n % len(ways)], "model", 0.8


def flipper(game, choices, fallback):
    """...or, once it's stopped at something, keeps changing its mind about which way the level goes (handed the
    game, it does as helper does)."""
    if "go_right" not in choices:
        return helper(game, choices, fallback)
    flipper.at_it = flipper.at_it or game.x > 600
    flipper.n += flipper.at_it
    return ("go_left" if flipper.n % 2 else "go_right"), "model", 0.6


def loser(game, choices, fallback):
    """...or presses Select, which here loses a life."""
    if "go_right" in choices:
        return "go_right", "model", 0.6
    return ("select" if not game.lost else "right_held"), "model", 0.8


def events(io, words):
    return [(e["t"], e["event"]) for e in io.logged if words in str(e.get("event"))]


OVER, BACK = "By instinct it's got nowhere for", "played by instinct again"
MARIO = ("Super Mario World (USA)", "snes")            # (a platformer, by its name: the level's buttons are a SNES's)
coach = Told()
lvl = GatedLevel((40, 100))
io, p = play_on(lvl, *MARIO, helper, 110.0, resumed=True, coach=coach)
over, back = events(io, OVER), events(io, BACK)
secs = [int(e.split(" for ")[1].split()[0]) for _, e in over]
check(f"a platformer with a gate across it that only X opens: by instinct it gets no further, and after half a minute "
      f"the decision model's handed it ({over[:1]})", len(over) >= 1 and 30 <= secs[0] <= 32 and 30 <= over[0][0] <= 40
      and over[0][1].endswith("the decision model plays it a move at a time from here, till it's past"))
handed = [q for q in io.asked if q["kind"] == "move" and over[0][0] - 0.1 <= q["at"] <= back[0][0] + 0.1] \
    if over and back else []
picks = [q["pick"] for q in handed]
check(f"...a move at a time, told why ({len(handed)} picks: {picks})", 2 <= len(handed) <= 6 and "x" in picks
      and set(picks) <= {"x", "right_held"} and "Pick the next thing to press" in handed[0]["says"]
      and all("go_right" not in q["choices"] and AG.HANDED_NOTE in q["state"].get("note", "") for q in handed))
check(f"...it opens the gate ({lvl.opened[:1]}) and walks on; the level's scrolled by further than it ever had, and "
      f"its instincts have it again ({back[:1]})", len(lvl.opened) >= 1 and lvl.opened[0][0] == 40 and len(back) >= 1
      and back[0][1] == "It's got past: played by instinct again" and back[0][0] - over[0][0] < 12)
check(f"...the coach is told how it got past, for a line to remember ({coach.told[:1]})", len(coach.told) >= 1
      and coach.told[0].startswith(f"It was stuck: playing by itself (running and jumping), it got nowhere for {secs[0]} "
                                   "seconds. Then, a move at a time, it got past. Its last moves, oldest first: ")
      and "Press X: something new; Right, held a second: something new" in coach.told[0]
      and coach.told[0].endswith("Right, held a second: something new."))
note = [s for s in coach.seen if s.get("note")]
check("...and told meanwhile that the player's pressing one thing at a time, as it says", note and note[0]["note"] == AG.HANDED
      and not coach.seen[0].get("note"))
check(f"the next gate: handed over sooner ({secs[1:2]} seconds), opened, and on ({lvl.best / 16:.0f} tiles in all)",
      len(over) == 2 and 15 <= secs[1] <= 17 and [g for g, _ in lvl.opened] == [40, 100] and len(back) == 2
      and lvl.best / 16 > 130 and not p.thinking and len(coach.told) == 2)

coach = Told(buttons="B: jump; Y: run; X: opens gates")
lvl = GatedLevel((40, 100))
io, p = play_on(lvl, *MARIO, helper, 85.0, resumed=True, coach=coach)
back, made = events(io, BACK), events(io, "Its buttons, as it plays")
check(f"what its buttons do, said while the model has the game: the instinct that's watching how far it gets is kept, "
      f"and made again once it has the game back ({[t for t, _ in made]}, back at {[t for t, _ in back]})",
      len(back) == 2 and len(made) == 2 and back[0][0] <= made[1][0] <= back[0][0] + 0.5
      and [g for g, _ in lvl.opened] == [40, 100] and io.asked[-1]["state"].get("its buttons") == coach.says_buttons
      and "its buttons" not in io.asked[0]["state"])

fumbler.n = 0
coach = Told()
lvl = GatedLevel()
io, p = play_on(lvl, *MARIO, fumbler, 175.0, resumed=True, coach=coach)
over, back = events(io, OVER), events(io, BACK)
check(f"a model that gets it no further: after {AG.HANDED_MOST} moves its instincts have another go ({back[:1]}), and "
      f"the coach is told what was tried ({coach.told[:1]})", len(back) >= 1
      and back[0][1] == "The decision model's got it no further either (24 moves): played by instinct again"
      and len(coach.told) >= 1 and coach.told[0].startswith(
          "It's been stuck a long while: playing by itself (running and jumping) it got nowhere for 3")
      and coach.told[0].endswith(" seconds, and then 24 moves, one at a time, got it no further. It's pressed no button. "
                                 "Not yet: A, B, X, Y, L, R, Select.") and not lvl.opened)
check(f"...then the model again, sooner ({[e for _, e in over[1:2]]}), and its instincts once more ({len(back)} times "
      f"in all); what was tried is told twice at most, till it's got on ({len(coach.told)})", len(over) >= 3
      and len(back) >= 3 and (" for 15 " in over[1][1] or " for 16 " in over[1][1])
      and (" for 10 " in over[2][1] or " for 11 " in over[2][1]) and len(coach.told) == AG.LONG_TELLS == 2)

flipper.n, flipper.at_it = 0, False
coach = Told()
lvl = GatedLevel()
io, p = play_on(lvl, *MARIO, flipper, 60.0, resumed=True, coach=coach)
over = events(io, OVER)
ways = [q["pick"] for q in io.asked if q["kind"] == "live" and q["at"] < (over[0][0] if over else 60)]
check(f"a model that sends it back and forth at the gate ({ways.count('go_left')} times left, {ways.count('go_right')} "
      f"right): back over ground it's covered isn't getting anywhere, so it's handed over all the same ({over[:1]}), "
      f"and the gate's opened ({lvl.opened[:1]})", ways.count("go_left") >= 8 and len(over) >= 1
      and 30 <= int(over[0][1].split(" for ")[1].split()[0]) <= 34 and over[0][0] <= 45
      and [g for g, _ in lvl.opened] == [40])

coach = Told()
lvl = GatedLevel(black=50)
io, p = play_on(lvl, *MARIO, loser, 60.0, resumed=True, coach=coach)
over, back = events(io, OVER), events(io, BACK)
check(f"a life lost while the model has it (the screen black, then the level's start): its instincts have it again "
      f"({back[:1]})", lvl.lost == 1 and len(back) >= 1 and 0 < back[0][0] - over[0][0] < 6
      and back[0][1] == "The screen's changed altogether: played by instinct again")
check(f"...what that was, it can't tell: the coach is told the screen changed altogether, and after which moves, to "
      f"make of its own look what there is to learn ({coach.told})", len(coach.told) == 1 and coach.told[0].startswith(
          "It was stuck: playing by itself (running and jumping), it got nowhere for 3")
      and " seconds. Then, as it pressed one thing at a time, the screen changed altogether: another room, a life lost "
          "or a menu (the picture shows which). Its last moves, oldest first: Press Select: " in coach.told[0])

coach = Told()
lvl = GatedLevel()
io, p = play_on(lvl, *MARIO, silent_model, 80.0, resumed=True, coach=coach)
check(f"a model that isn't answering: never handed it (its instincts play on at the gate: tile {lvl.best / 16:.0f})",
      not events(io, OVER) and not p.thinking and 35 < lvl.best / 16 < 40 and coach.told == [])

coach = Told()
lvl = GatedLevel((6,))                                 # (shut in at the start: the screen never scrolls)
io, p = play_on(lvl, *MARIO, helper, 80.0, resumed=True, coach=coach)
check(f"a game of one screen (nothing's scrolled by: {p.instinct.scrolled} looks): left to its instincts",
      not events(io, OVER) and p.instinct.scrolled < AG.SCROLLED and not lvl.opened)

lvl = Level()
io, p = play_on(lvl, *MARIO, helper, 90.0, resumed=True, coach=Told())
check(f"the level its instincts get through (pipes, pits, enemies): never handed over (tile {lvl.best / 16:.0f} of "
      f"{lvl.length}, {lvl.deaths} times back to a checkpoint)", not events(io, OVER) and lvl.best / 16 >= 100)
check(f"what kind of game, from its name: Shrek 2 and The Lost Vikings aren't run and jump "
      f"({I.guess_kind('shrek 2')}, {I.guess_kind('the lost vikings')}); Shrek's kart game still races "
      f"({I.guess_kind('shrek swamp kart speedway')})", I.guess_kind("shrek 2") == "adventure"
      and I.guess_kind("the lost vikings") == "adventure" and I.guess_kind("shrek swamp kart speedway") == "racing"
      and I.guess_kind("super mario world") == "platformer")

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
