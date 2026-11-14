"""The AI player's coach (pitato/anygame.py): your Bot's model (Settings > Bot) knows a lot of games, and uses what
it knows. The first time, it says what it knows of this one: what kind of game it is (a racing game, a platformer,
fighting, a shooter, sports, a puzzle, an RPG, an adventure), what each button does in it, and how a good player
plays it, so the player plays it that way (a racer drives by instinct, many times a second: pitato/instincts.py).
Then now and then it looks at the game's screen and works out what's going on, what to aim for and how to get there,
and the decision model picks each move, following that. The coach thinks on a thread of its own, so the game never
waits for it: every so often, and soon after the player gets stuck (its moves keep bringing nothing new), when it's
told what the player's been doing and asked for something different.

What it works out about a game is kept for next time, in a notes file beside the game's saves (Games/Saves/
<game>.ai-notes.txt), with a place for tips of yours: the controls, what to aim for, how to get past a part. Its own
lines in it are the first that start Kind:, Buttons:, How:, Controls: and Goal:, and it keeps those up to date (a
Kind: line you write, it goes by: racing, platformer, fighting, shooter, sports, puzzle, rpg, adventure or other);
every other line is yours, left just as it is (and all but # lines are tips, Tips: in front or not). It's read again
whenever it's changed, so tips added while the game's played count straight away, and they're read even with no Bot
model (the decision model's told them, and what was worked out before).

And what it learns by playing is kept there too, a line each that starts Learned:. The player tells it what's
happened (tell(): it was stuck and has got on, and with which moves; it's been stuck a long while, and what it
tried; or the screen changed altogether under its moves), and with its next look it's asked for one sentence to
remember: what got it on, and where, or what didn't work or went wrong there. A new one goes after the last; one it
has already (or nearly) isn't said twice, and it's asked not to say one again; LEARNED_MOST are kept (the oldest go).
They're told to it, and to the decision model, every time after: so what it found out in one game it knows in the
next. They're its own lines, but yours to change or take out. (They're a model's guesses at what it saw: the player
tells it only what it can tell by itself, and whether a life was lost or a level done isn't among that.)"""
import json
import os
import re
import tempfile
import threading
import time

from .bot import FRIEND_THINK, CantSee, OllamaError, cant_see, ollama_call
from .instincts import KINDS, kind_of

EVERY = 40.0                 # seconds between its looks while the player gets on
GAP = 12.0                   # ...and at least this long after its last, when the player's stuck
FIRST_TIMEOUT = 150.0        # seconds its first answer may take (its model wakes up on the other computer)
TIMEOUT = 90.0               # ...and the rest
RESTS = (60.0, 300.0)        # seconds it rests after it couldn't answer; after FAILS_LONG in a row, the longer
FAILS_LONG = 3
SAYS_MOST = 400              # characters of each thing it says, at most
TIPS_MOST = 1500             # characters of your tips it's told
NOTES_MOST = 1 << 20         # bytes of the notes file, at most, it reads (a bigger one it reads the start of, and
                             # leaves as it is)
OWN = ("Kind", "Buttons", "How", "Controls", "Goal")   # its own lines in the notes, in the order it adds them
OWN_LINE = re.compile(r"\s*(kind|buttons|how|controls|goal)\s*:\s?(.*)$", re.I)   # their starts
LEARNED = re.compile(r"\s*learned\s*:\s?(.*)$", re.I)    # ...and what it's learned by playing: a line each
LEARNED_MOST = 24            # of those kept (the oldest go)
LEARNED_LONG = 160           # characters of one, at most
LEARNED_TOLD = 2400          # characters of them it's told (the newest that fit: all of them, as a rule)
LEARNED_SAME = 0.75          # two of them are the same when this share of their words is
NOTHING = re.compile(r"(none|nothing|n/?a|no|empty|not applicable|unknown|nothing (new|to|worth)\b.*)\W*", re.I)
EVENTS_MOST = 3              # things the player's told it have happened, kept till it's looked (the oldest go)
FIELDS = ("screen", "goal", "plan", "controls")
CARD = ("kind", "buttons", "how")             # what it knows of the game (asked once: kept in the notes)


def schema(card=False, learned=False):
    """The shape its answer's asked for in: what to do; with what it knows of the game (card); with a line to
    remember (learned)."""
    keys = (CARD if card else ()) + FIELDS + (("learned",) if learned else ())
    props = {k: {"type": "string"} for k in keys}
    if card:
        props["kind"] = {"type": "string", "enum": list(KINDS)}
    return {"type": "object", "properties": props, "required": list(keys)}


SCHEMA, CARD_SCHEMA = schema(), schema(card=True)
ROLE = ("You coach a player that is playing {game} on the {system}. You know video games, and very likely this one: "
        "use what you know of it (what kind of game it is, what each button does in it, what the goal is, and how "
        "good players play it) along with what you see on its screen. The player can't plan ahead or remember much. "
        "In an action game (racing, a platformer, fighting, a shooter) it plays by instinct, many times a second: it "
        "drives, runs and jumps, fights or shoots by itself, and you say when that's what to do and which way to go. "
        "Otherwise, every second or two it presses one thing, following what you tell it: a button, a direction for "
        "a moment or held a second, a direction with one of the first two buttons (a jump or an attack on the "
        "move), or nothing. Now and then you look at the game's screen and work out what's going on, what to aim "
        "for and how to get there; when the player's stuck, think of something different to try. Reply with JSON "
        "only.")
ASK = ('Reply with JSON: "screen": what\'s on the screen, in a sentence. "goal": what to aim for right now, in a few '
       'words. "plan": the next few things to do, in a sentence or two, naming the buttons and directions to press. '
       '"controls": what\'s known about this game\'s controls so far, in a sentence (keep what\'s still true).')
ASK_CARD = (' And what you know of this game: "kind": what kind of game it is, one of ' + ", ".join(KINDS) + ' '
            '(a platformer only if running and jumping alone gets you through it: one where you have to work things '
            'out, carry things or switch between characters to get on is an adventure). '
            '"buttons": what each of its buttons does in this game, as Button: what it does, separated by '
            'semicolons, with the button names above (A, B, Cross...). "how": how a good player plays it, in a '
            'sentence or two.')
STUCK_SAYS = (" Think of what a person would try instead: a button it hasn't used (one may pick things up, use them "
              "or throw them), going another way, or doing something with what's around it.")
ASK_LEARNED = (' "learned": one short sentence to remember the next time this game\'s played, from what\'s just '
               'happened: what got it on (which button or move) and where (by what\'s on the screen there), or what '
               'didn\'t work or went wrong there. "" if there\'s nothing worth keeping, or it\'s been learned '
               'already.')
NOTES_HEAD = ("# The AI player's notes on this game: it reads them each time it plays. The Kind:, Buttons:, How:,\n"
              "# Controls: and Goal: lines are its own, kept up to date as it works things out (change Kind: if it's\n"
              "# wrong), and so are the Learned: lines: what it's found out by playing, one a line (change one, or\n"
              "# take it out, if it's wrong). The rest is yours: write tips anywhere (the controls, what to aim for,\n"
              "# how to get past a part where it's stuck) and it leaves them as they are.\n")


def flat(text):
    """Text on one line: its spaces and line breaks each one space."""
    return " ".join(str(text or "").split())


def tidy(value):
    """Something it said, made plain: one line, no markdown or quotes round it, at most SAYS_MOST characters, and
    only characters that can be written out (a stray half of one, from a model's \\ud83c, becomes a ?)."""
    if isinstance(value, (list, tuple)):
        value = " ".join(str(v) for v in value)
    elif not isinstance(value, str):
        value = "" if value is None else str(value)
    value = value.encode("utf-8", "replace").decode("utf-8")
    for junk in ("**", "`", "__"):
        value = value.replace(junk, "")
    value = flat(value).strip("\"'“”‘’ ")
    if len(value) > SAYS_MOST:
        value = value[:SAYS_MOST].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return value


def salvage(text):
    """What can be read of JSON cut short (an answer that ran out of room): the fields whose values started."""
    got = {}
    for k in FIELDS + CARD + ("learned",):
        m = re.search(r'"%s"\s*:\s*"((?:[^"\\]|\\.)*)' % k, text, re.I)
        if m:
            raw = m.group(1).rstrip("\\")
            try:
                got[k] = json.loads('"' + raw + '"')
            except ValueError:
                got[k] = raw
    return got


def answer(text):
    """(its answer's JSON: a dict, a string, something else, or None; the text with any reasoning taken out). JSON
    among other words is found; JSON cut short gives what's there of it."""
    text = FRIEND_THINK.sub(" ", text or "")
    text = re.sub(r"^\s*<think>.*", "", text, flags=re.S | re.I).strip()
    found = re.search(r"\{.*\}", text, re.S)
    for candidate in (text, found.group(0) if found else ""):
        try:
            return json.loads(candidate), text
        except ValueError:
            continue
    if "{" in text:
        return salvage(text[text.index("{"):]) or None, text
    return None, text


def parse(text):
    """Its answer: {"screen", "goal", "plan", "controls"}, or None when it said nothing to go by. JSON, as asked
    (or JSON among other words, or JSON cut short: what's there of it); words alone, or a string of them, are taken
    as the plan."""
    got, text = answer(text)
    if got is None and "{" in text:                    # (JSON it couldn't finish, with nothing in it to go by)
        return None
    if isinstance(got, str):
        text, got = got, None
    if isinstance(got, dict):
        low = {str(k).strip().lower(): v for k, v in got.items()}
        out = {k: tidy(low.get(k)) for k in FIELDS}
        return out if out["goal"] or out["plan"] else None
    if got is not None:
        return None
    words = tidy(re.sub(r"[#*>{}\[\]]", " ", text))
    return {"screen": "", "goal": "", "plan": words, "controls": ""} if words else None


def parse_card(text):
    """What it said it knows of the game, in its answer: {"kind" (one of KINDS), "buttons", "how"}, those it said;
    {} if none."""
    got, _ = answer(text)
    if not isinstance(got, dict):
        return {}
    low = {str(k).strip().lower(): v for k, v in got.items()}
    out = {k: tidy(low.get(k)) for k in CARD}
    out["kind"] = kind_of(out["kind"]) or ""
    return {k: v for k, v in out.items() if v}


def lesson_of(value):
    """A line it's learned, made plain: one line, no Learned: in front, at most LEARNED_LONG characters; "" for
    nothing worth keeping (no words, a word or two, or it says there's nothing)."""
    words = re.sub(r"^\s*learned\s*:\s*", "", tidy(value), flags=re.I)
    if len(words.split()) < 3 or NOTHING.fullmatch(words):
        return ""
    if len(words) > LEARNED_LONG:
        words = words[:LEARNED_LONG].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return words


def parse_learned(text):
    """What it said it's learned, in its answer: a line (lesson_of), or ""."""
    got, _ = answer(text)
    if not isinstance(got, dict):
        return ""
    return lesson_of({str(k).strip().lower(): v for k, v in got.items()}.get("learned"))


def same_lesson(a, b):
    """Two lines it's learned say the same: their words alike (LEARNED_SAME of them, whatever their order)."""
    x, y = (set(re.findall(r"[a-z0-9']+", s.lower())) for s in (a, b))
    return bool(x and y) and len(x & y) / len(x | y) >= LEARNED_SAME


def notes_learned(text):
    """What it's learned by playing, from a notes file: its Learned: lines' words, in order (the oldest first)."""
    out = []
    for line in text.splitlines():
        m = None if line.lstrip().startswith("#") else LEARNED.match(line)
        if m and m.group(1).strip():
            out.append(flat(m.group(1)))
    return out


def notes_learning(text, lesson):
    """A notes file's text with a line it's learned added: after its last Learned: line (or at the end); one it has
    already, or nearly, is moved there as it was written, not said twice; over LEARNED_MOST of them, the oldest
    go. Every other line just as it was."""
    lines = text.splitlines()
    mine = [i for i, line in enumerate(lines) if not line.lstrip().startswith("#") and LEARNED.match(line)]
    had = {i: LEARNED.match(lines[i]).group(1).strip() for i in mine}
    again = [i for i in mine if had[i] and same_lesson(had[i], lesson)]
    new = lines[again[-1]] if again else f"Learned: {lesson}"
    gone = set(again) | {i for i in mine if not had[i]}
    kept = [i for i in mine if i not in gone]
    gone |= set(kept[:max(0, len(kept) + 1 - LEARNED_MOST)])
    at = mine[-1] if mine else len(lines) - 1          # (it goes after this line)
    out = []
    for i, line in enumerate(lines):
        if i not in gone:
            out.append(line)
        if i == at:
            out.append(new)
    if not lines:
        out.append(new)
    return "\n".join(out) + "\n"


def readable(text):
    """A notes file's text as read to write back (any bytes that weren't UTF-8 kept as they were), made plain to
    read (those a ?)."""
    return text.encode("utf-8", "surrogateescape").decode("utf-8", "replace")


def notes_parts(text):
    """(your tips, {"Kind", "Buttons", "How", "Controls", "Goal"} worked out before, those there) from a notes file:
    its own lines (the first that starts each), and every other line but # lines a tip (Tips: in front or not; not
    its Learned: lines)."""
    tips, own = [], {}
    for line in text.splitlines():
        if line.lstrip().startswith("#") or LEARNED.match(line):   # (what it's learned: notes_learned has those)
            continue
        m = OWN_LINE.match(line)
        if m and m.group(1).capitalize() not in own:
            own[m.group(1).capitalize()] = m.group(2).strip()
            continue
        m = re.match(r"\s*tips\s*:\s?(.*)$", line, re.I)
        tips.append((m.group(1) if m else line).rstrip())
    return "\n".join(tips).strip(), {k: v for k, v in own.items() if v}


def notes_with(text, own):
    """A notes file's text with its own lines saying what's in own ({"Kind", "Buttons", "How", "Controls", "Goal"}:
    those with something to say): in place of the first line that starts each (or added at the end), every other
    line just as it was. None (no file yet): a new one, its heading, a Tips line for yours, and them."""
    own = {k: v for k, v in own.items() if v}
    if text is None:
        return NOTES_HEAD + "Tips: \n" + "".join(f"{k}: {own[k]}\n" for k in OWN if k in own)
    lines, done = text.splitlines(), set()
    for i, line in enumerate(lines):
        m = None if line.lstrip().startswith("#") else OWN_LINE.match(line)
        key = m.group(1).capitalize() if m else None
        if key and key not in done:
            done.add(key)
            if key in own:
                lines[i] = f"{key}: {own[key]}"
    lines += [f"{k}: {own[k]}" for k in OWN if k in own and k not in done]
    return "\n".join(lines) + "\n"


class Coach:
    """Your Bot's model, coaching the AI player: start() it with the game's name, system and controls; see() what the
    player's seen and done as it goes; nudge() when it's stuck; tell() it what's happened that's worth learning
    from; stop(). advice: {"screen", "goal", "plan", "controls"} once it's said (None till then); tips: yours;
    controls(): what's known about the controls, now or from before; card(): what's known of the game (its kind,
    what its buttons do, how it's played well); lessons(): what it's learned by playing it. With no model, it only
    reads the notes (your tips, what was worked out before, and what was learned)."""

    def __init__(self, server, model, notes_path, log=lambda entry: None, paused=lambda: False):
        self.server, self.model, self.notes_path = server, (model or "").strip(), notes_path
        self.log, self.paused = log, paused
        self.game = self.system = self.buttons = ""
        self.advice, self.advised_at = None, 0.0
        self.tips, self.known = "", {}
        self.learned = []                     # what it's learned by playing, the oldest first (the notes' Learned:)
        self.events = []                      # what the player's told it has happened, till it's looked
        self.stuck_screen = ""                # what it saw where the player was last stuck
        self.said_card = {}                   # what it said of the game (kept in the notes too, if they can be)
        self.notes_seen = None                # the notes file's (mtime, size) when read: read again when they change
        self.notes_failed = False
        self.blind = False                    # its model was shown the screen and can't look at pictures
        self.fails = 0
        self.nudged = False
        self.latest = None                    # (the Look, the player's story): what it thinks about next
        self.lock = threading.Lock()
        self.stopping = threading.Event()
        self.thread = None
        self.read_notes()

    # -- the player's side ---------------------------------------------------------------------------------------
    def start(self, game, system, buttons):
        self.game, self.system, self.buttons = game, system, buttons
        if self.model and self.server and self.thread is None:
            self.thread = threading.Thread(target=self.main, daemon=True, name="game-coach")
            self.thread.start()

    def see(self, look, story):
        """The player's latest look (None: it couldn't see this time, so the last one's kept) and how it's going."""
        self.latest = (look if look is not None or self.latest is None else self.latest[0], story)
        self.read_notes()

    def nudge(self):
        """The player's stuck: think again soon (GAP after the last time, at the soonest)."""
        self.nudged = True

    def tell(self, words):
        """Something's happened that's worth learning from (the player was stuck and has got on, and how; or it's
        been stuck a long while): kept till its next look, which comes soon, and asks for a line to remember."""
        with self.lock:
            self.events = (self.events + [flat(words)])[-EVENTS_MOST:]
        self.nudged = True

    def lessons(self, most=None):
        """What it's learned by playing this game, the oldest first; most: only the newest that fit in so many
        characters."""
        out = list(self.learned)
        while most is not None and out and sum(len(x) + 2 for x in out) > most:
            out.pop(0)
        return out

    def stop(self):
        self.stopping.set()

    def controls(self):
        """What's known about the game's controls: what it said last, or what was worked out before."""
        said = (self.advice or {}).get("controls")
        return said or flat(self.known.get("Controls", ""))

    def card(self):
        """What's known of the game, from the notes (what it said of it, the first time; or a Kind: line of yours):
        {"kind": one of KINDS, or "" if it's not known, "buttons": what each does, "how": how it's played well}."""
        known, said = self.known, self.said_card
        return {"kind": kind_of(known.get("Kind")) or said.get("kind", ""),
                "buttons": flat(known.get("Buttons", "")) or said.get("buttons", ""),
                "how": flat(known.get("How", "")) or said.get("how", "")}

    # -- thinking --------------------------------------------------------------------------------------------------
    def main(self):
        last, rest_until = None, 0.0
        while not self.stopping.is_set():
            now = time.monotonic()
            due = (self.latest is not None and now >= rest_until and not self.paused()
                   and (last is None or now - last >= EVERY or (self.nudged and now - last >= GAP)))
            if not due:
                self.stopping.wait(0.25)
                continue
            self.nudged = False
            look, story = self.latest
            try:
                ok = self.think(look, story, first=last is None)
            except Exception as ex:                    # (never stops for good: it says why, and rests)
                self.log({"kind": "coach", "error": repr(ex)[:300]})
                ok = False
            last = time.monotonic()
            if ok:
                self.fails, rest_until = 0, 0.0
            else:
                self.fails += 1
                rest_until = last + RESTS[1 if self.fails >= FAILS_LONG else 0]

    def think(self, look, story, first=False):
        """Looks at the screen and says what to do (and, while it's not known, what it knows of the game): True once
        it has (it's kept, logged and noted for next time)."""
        self.read_notes()
        sees = look is not None and not self.blind
        timeout = FIRST_TIMEOUT if first else TIMEOUT
        card = not self.card()["kind"]             # (what kind of game it is: asked till it's known)
        with self.lock:
            events = list(self.events)             # (what's happened: a line to remember is asked for with it)
        t0 = time.monotonic()
        try:
            try:
                text = self.ask(self.prompt(story, sees, card, events), [look.data] if sees else None, timeout, card,
                                bool(events))
            except CantSee:
                self.blind, sees = True, False
                self.log({"event": f"{self.model} can't look at pictures: it coaches without seeing the screen"})
                text = self.ask(self.prompt(story, False, card, events), None, timeout, card, bool(events))
        except Exception as ex:                    # (it says why in the log; the player plays on)
            if self.stopping.is_set():
                return True
            self.log({"kind": "coach", "error": str(ex) or repr(ex), "ms": round((time.monotonic() - t0) * 1000)})
            return False
        if self.stopping.is_set():                 # (stopped while it thought: the answer's not wanted now)
            return True
        ms = round((time.monotonic() - t0) * 1000)
        advice = parse(text)
        if advice is None:
            self.log({"kind": "coach", "error": f"{self.model} didn't say what to do", "said": flat(text)[:300] or None,
                      "ms": ms})
            return False
        self.advice, self.advised_at = advice, time.monotonic()
        said = parse_card(text) if card else {}
        self.said_card.update(said)
        if said.get("kind"):
            self.log({"event": f"{self.model} says it's a {said['kind']} game", "buttons": said.get("buttons"),
                      "how": said.get("how")})
        lesson = parse_learned(text) if events else ""
        with self.lock:                            # (told of those: done with, whatever it made of them)
            self.events = [e for e in self.events if e not in events]
        if events:
            self.stuck_screen = ""
        if (story.get("stuck") or story.get("note")) and advice.get("screen"):
            self.stuck_screen = advice["screen"]   # (where it's stuck, as it's seen: told with what comes of it)
        new = bool(lesson) and not any(same_lesson(x, lesson) for x in self.learned)
        self.write_notes(advice, said, lesson)
        if new:                                    # (one it had already isn't said twice, there or in its log)
            self.log({"event": f"Learned: {lesson}"})
        self.log(dict({"kind": "coach"}, **{k: v or None for k, v in advice.items()},
                      saw="x".join(map(str, look.size)) if sees else None, stuck=story.get("stale") if
                      story.get("stuck") else None, ms=ms))
        return True

    def prompt(self, story, sees, card=False, events=()):
        """What it's asked: the game, your tips, what was worked out before, what it's learned by playing and what it
        said last, the player's last moves and what came of each, and whether it's stuck (and, card: what it knows
        of the game; events: what's happened since it last looked, for a line to remember)."""
        lines = [f"The game: {self.game}, on the {self.system}. Its buttons: {self.buttons}."]
        if self.tips:
            lines.append(f"Tips from the person whose game it is (trust these): {self.tips}")
        before = " ".join(f"{k}: {flat(self.known[k])}" for k in OWN if self.known.get(k))
        if before:
            lines.append(f"Worked out in earlier games: {before}")
        if self.learned:
            lines.append("Learned by playing it before (go by these):\n"
                         + "\n".join(f"- {x}" for x in self.lessons(LEARNED_TOLD)))
        if self.advice:
            ago = max(0, round(time.monotonic() - self.advised_at))
            lines.append(f"What you said {ago} seconds ago: goal: {self.advice['goal'] or '-'}; plan: "
                         f"{self.advice['plan'] or '-'}")
        if story.get("moves"):
            lines.append("The player's last moves, oldest first, and what came of each:\n"
                         + "\n".join(f"- {m}" for m in story["moves"]))
        if story.get("note"):                          # (handed the game by its instincts, which got nowhere)
            lines.append(story["note"])
        if story.get("stuck"):
            said = story.get("stuck_words") or (
                (f"It's stuck: its last {story.get('stale')} moves got it nowhere (the screen keeps looking as it "
                 "has before)") + (f", doing mostly {story['mostly']}" if story.get("mostly") else "") + ".")
            if story.get("off"):
                said += " Off its list for now: " + ", ".join(story["off"]) + "."
            if story.get("untried"):
                said += " Buttons it hasn't tried here: " + ", ".join(story["untried"]) + "."
            lines.append(said + STUCK_SAYS)
        if events:
            lines.append("Since you last looked:\n" + "\n".join(f"- {e}" for e in events))
            if self.stuck_screen:
                lines.append(f"Where it was stuck, as you saw it then: {self.stuck_screen}")
        lines.append("The attached picture is the game's screen right now." if sees else
                     "You can't see the screen this time: go by the game and what's said here.")
        lines.append(ASK + (ASK_CARD if card else "") + (ASK_LEARNED if events else ""))
        return "\n".join(lines)

    def ask(self, prompt, images, timeout, card=False, learned=False):
        """Its model's answer (text): asked for JSON in the shape wanted (card: with what it knows of the game;
        learned: with a line to remember), with no reasoning first; an older Ollama or a model that doesn't do one of
        those is asked again without it. CantSee: shown a picture, it can't look."""
        body = {"model": self.model, "system": ROLE.format(game=self.game, system=self.system), "prompt": prompt,
                "stream": False, "think": False, "format": schema(card, learned), "keep_alive": "30m",
                "options": {"temperature": 0.5, "num_predict": (800 if card else 600) + (100 if learned else 0)}}
        if images:
            body["images"] = list(images)
        while True:
            try:
                got = ollama_call(self.server, "/api/generate", body, timeout)
            except OllamaError as e:
                low = (e.detail or "").lower()
                if e.code == 404:
                    raise ValueError(f"That computer doesn't have {self.model}")
                if cant_see(e, images):
                    raise CantSee(self.model)
                if e.code == 400 and "think" in low and "think" in body:
                    body.pop("think")
                    continue
                if e.code == 400 and "format" in low and "format" in body:
                    body.pop("format")
                    continue
                raise ValueError(f"{self.model} couldn't answer: {e.detail}")
            return got.get("response") or ""

    # -- the notes file ----------------------------------------------------------------------------------------------
    def read_notes(self):
        """Your tips, what was worked out before (its own lines: Kind, Buttons, How, Controls, Goal) and what it's
        learned by playing (its Learned: lines), from the notes file: read again when it's changed."""
        with self.lock:
            try:
                st = os.stat(self.notes_path)
            except (OSError, TypeError, ValueError):
                if self.notes_seen is not None:
                    self.tips, self.known, self.learned, self.notes_seen = "", {}, [], None
                return
            sig = (st.st_mtime_ns, st.st_size)
            if sig == self.notes_seen:
                return
            try:
                with open(self.notes_path, encoding="utf-8", errors="replace") as f:
                    text = f.read(NOTES_MOST)
            except OSError:
                return
            tips, self.known = notes_parts(text)
            self.tips = flat(tips)[:TIPS_MOST]
            self.learned = notes_learned(text)
            self.notes_seen = sig

    def write_notes(self, advice, card=None, lesson=""):
        """What it's worked out (the controls, its goal; and what it said of the game: its kind, its buttons, how
        it's played) into its own lines of the notes file, for next time: the file read afresh first, and every
        other line in it (yours) left just as it is. What it said of the game goes in only where the file hasn't a
        line for it already (one there, yours or its own, stays as it is). Written under a name of its own, then put
        in place; owned like the Saves folder, so it's yours to edit. A file too big to read whole is left as it is.
        Your tips, and the file's own lines, are taken as it now is. lesson: a line it's learned by playing, added
        to its Learned: lines (notes_learning)."""
        said = dict(card or {}, controls=advice.get("controls"), goal=advice.get("goal"))
        with self.lock:
            folder = os.path.dirname(self.notes_path)
            tmp = None
            try:
                try:
                    if os.path.getsize(self.notes_path) > NOTES_MOST:
                        return
                    with open(self.notes_path, encoding="utf-8", errors="surrogateescape") as f:
                        text = f.read()
                except FileNotFoundError:
                    text = None
                fresh = notes_parts(readable(text))[1] if text else {}
                own = {k: (fresh.get(k) or said.get(k.lower())) if k in ("Kind", "Buttons", "How")
                       else (said.get(k.lower()) or fresh.get(k)) for k in OWN}
                new = notes_with(text, {k: v or "" for k, v in own.items()})
                if lesson:
                    new = notes_learning(new, lesson)
                if new == text:
                    return
                st = os.stat(folder)
                fd, tmp = tempfile.mkstemp(prefix="." + os.path.basename(self.notes_path) + ".", suffix=".part",
                                           dir=folder)
                with os.fdopen(fd, "w", encoding="utf-8", errors="surrogateescape") as f:
                    f.write(new)
                try:
                    os.chown(tmp, st.st_uid, st.st_gid)
                except OSError:
                    pass
                os.chmod(tmp, 0o644)
                os.replace(tmp, self.notes_path)
                tmp = None
                st = os.stat(self.notes_path)
                self.notes_seen = (st.st_mtime_ns, st.st_size)
                tips, self.known = notes_parts(readable(new))
                self.tips = flat(tips)[:TIPS_MOST]
                self.learned = notes_learned(readable(new))
            except (OSError, ValueError) as ex:
                if not self.notes_failed:
                    self.notes_failed = True
                    self.log({"event": f"Couldn't keep its notes on the game ({ex})"})
            finally:
                if tmp is not None:
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
