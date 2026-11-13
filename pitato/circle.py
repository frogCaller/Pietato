"""Your Pietatos' group chat (Apps > Group chat): they talk among themselves, and with you.

Each Pietato keeps the conversation (GROUP_LOG) and sends each line said on it to your others that are on, which keep
it too; one that was off asks the others what it missed. Each one's beacon (media.py's share_beacon) says what it's
doing, what it's made of (its board, cores, memory and screen) and when you were last noticed there (using its
controller or keyboard, or its camera seeing someone move), so each knows where you are and what the others are up to.

One that goes quiet (its beacon stops) is missed: the others wonder where it went, then ask you whether it'll be back
(No: they say goodbye, and stop missing it). Back: they say so. Now and then one says something of its own (the
weather, what another's doing, where you are, who's bigger: teasing, boasting, helping, learning, teaming up), and
others may answer, in their own words (their Bot's model, Settings > Bot) or, without one, words of their own. You can
say something too, on any of them. Quiet (on any of them) stops them talking among themselves, on all of them; they
still answer you."""
import json
import math
import os
import random
import re
import string
import threading
import time
import uuid

from .config import clean_name
from .theme import ACCENTS

GROUP_LOG = "/var/lib/pitato/group.json"   # the conversation (root only)
GROUP_KEEP = 300             # lines of it kept
TEXT_MOST = 280              # characters of a line
ON_WITHIN = 70               # seconds: another heard this lately is on (its beacon says so every 20)
QUIET_AFTER = 150            # ...and not heard for this long, it's gone quiet,
WARM = 240                   # ...missed if it had been on this long first (one that came and went at once isn't)
FIRST_WORD = (5, 20)         # seconds after one goes quiet (or is back) before the first word about it
ASK_AFTER = (40, 90)         # ...and after that, before you're asked whether it'll be back
QUIET_GAP = 2 * 3600         # the same one missed out loud no more often than this
ASK_GAP = 6 * 3600           # ...and you asked about it no more often than this
YOU_WITHIN = 1800            # you were noticed at one this lately: you're there
POP_WITHIN = 900             # ...and what's said pops up there, noticed this lately
REPLY_WAIT = (6, 40)         # seconds before another answers something said
REPLIES_MOST = 2             # answers to one line, at most
DEPTH_MOST = 3               # a line, an answer, an answer to that: no further
OWN_HOURLY = 10              # lines one says by itself in an hour, at most
REMARK_EVERY = 30            # minutes between remarks of its own (its Bot's How often it talks, else this), with two
CHAT_QUIET = 300             # ...not while they've been talking this lately
NIGHT = (23, 7)              # ...nor at night (these hours)
MOVED_GAP = 1800             # where you are, said no more often than this
CHEAT_GAP = 1200             # one of them accused of cheating for the cookie (cookie.py) no more often than this
CATCH_UP = 6 * 3600          # what one missed, asked of the others: this far back
CATCH_UP_TRIES = (30, 3)     # ...asked again this many seconds after, this many times, if it didn't answer
SYNC_EVERY = (300, 600)      # ...and of one of them now and then anyway (a line that didn't get through)
JOB_STALE = 600              # a line due this long ago and not said (another took long): not said
KINDS = ("chat", "quiet", "ask", "answer", "back", "bye", "wait", "talk", "moved")
TOPICS = ("weather", "doing", "self", "where", "brag", "tease", "help", "learn", "envy", "team", "even", "cookie",
          "cheat")
RIVAL_TOPICS = ("tease", "help", "learn", "envy", "team", "even")   # (sizing each other up)
TOPIC_GAP = 90 * 60          # a remark's topic not again this soon (two of sizing each other up, at most)
CHOICES = ("Yes", "No")      # your answers to "Will it come back?"
BIGGER = 1.5                 # one this many times another's power is bigger than it (for sizing each other up)


# ---- what each one's made of ----------------------------------------------------------------------------------
def board_short(board):
    """A Pi's board, short: "Pi Zero 2 W", "Pi 4", "Pi 5", "Pi 3B+", "Pi CM4". Anything else as it is."""
    b = re.sub(r"\s+Rev\s+[\d.]+$", "", " ".join((board or "").split())).replace(" Plus", "+")
    m = re.match(r"Raspberry Pi (.+?)(?: Model ([AB]\+?))?$", b)
    if not m:
        return b[:40]
    name = re.sub(r"Compute Module\s*", "CM", m.group(1))
    if name in ("2", "3") and m.group(2):
        name += m.group(2)                            # (a Pi 3B+, a Pi 3A+)
    return "Pi " + name


def board_power(board, kind="pi", cores=0, ghz=0.0):
    """How much one can do, roughly, a Pi Zero 2 W being 1: for sizing each other up, not a benchmark. kind: "pi",
    "handheld" (an RK3326's: a bit more than a Zero 2 W) or "pc" (its cores times how fast they go)."""
    if kind == "handheld":
        return 1.2
    if kind == "pc":
        return round(max(1, cores) * (ghz or 2.0) * 0.9, 1)
    for pat, score in ((r"Zero 2", 1.0), (r"Zero", 0.25), (r"Pi 5|Pi 500|Compute Module 5|CM5", 7.0),
                       (r"Pi 4|Pi 400|Compute Module 4|CM4", 3.0), (r"Pi 3|Compute Module 3|CM3", 1.2),
                       (r"Pi 2", 0.8)):
        if re.search(pat, board or ""):
            return score
    return 0.3                                        # (a Pi 1, or one it doesn't know)


def read_text(path):
    try:
        with open(path, errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def hardware(board="", kind="pi", screen=None, body=""):
    """This one, for the others: {"b": its board, short ("Pi 4", "PC (Intel N100)", "R36S"); "c": its cores; "r": its
    memory, GB; "s": what it can do (board_power); "x": its screen ("640x480"); "k": what it's in ("GPi Case 2W"),
    if anything}."""
    cores = os.cpu_count() or 1
    m = re.search(r"^MemTotal:\s+(\d+)", read_text("/proc/meminfo"), re.M)
    ram = round(int(m.group(1)) / 1048576, 1) if m else 0
    try:
        ghz = int(read_text("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq").strip()) / 1e6
    except ValueError:
        ghz = 0.0
    short = board_short(board)
    if kind == "pc":
        info = read_text("/proc/cpuinfo")
        if not ghz:                                   # (no cpufreq, in a virtual machine say: what it says it runs at)
            mhz = re.search(r"^cpu MHz\s*:\s*([\d.]+)", info, re.M)
            ghz = float(mhz.group(1)) / 1000 if mhz else 0.0
        cpu = re.search(r"^model name\s*:\s*(.+)$", info, re.M)
        cpu = " ".join(re.sub(r"\((R|TM|tm)\)|\bCPU\b|@.*$|\s+Processor|\d+-Core", "", cpu.group(1)).split()) \
            if cpu else ""
        short = f"PC ({cpu})" if cpu else (f"PC ({short})" if short else "PC")
    hw = {"b": (short or ("Pi" if kind == "pi" else "handheld"))[:48], "c": cores, "r": ram,
          "s": board_power(board, kind, cores, ghz)}
    if screen and screen[0] and screen[1]:
        hw["x"] = f"{screen[0]}x{screen[1]}"
    if body:
        hw["k"] = clean_name(body, 24)
    return hw


def hw_clean(hw):
    """What another says it's made of, kept to what's expected."""
    if not isinstance(hw, dict):
        return {}
    out = {}
    for k, n in (("b", 48), ("k", 24)):
        if isinstance(hw.get(k), str) and hw[k].strip():
            out[k] = clean_name(hw[k], n)
    for k, lo, hi in (("c", 1, 1024), ("r", 0, 65536), ("s", 0, 100000)):
        v = hw.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and lo <= v <= hi:
            out[k] = v
    if isinstance(hw.get("x"), str) and re.fullmatch(r"\d{2,5}x\d{2,5}", hw["x"]):
        out["x"] = hw["x"]
    return out


def hw_words(hw):
    """What one's made of, in words: "a Pi Zero 2 W in a GPi Case 2W (4 cores, 0.4 GB of memory, a 640x480 screen)"."""
    if not hw:
        return "something nobody knows"
    parts = [f"{hw['c']} core{'' if hw['c'] == 1 else 's'}" if hw.get("c") else "",
             f"{hw['r']:g} GB of memory" if hw.get("r") else "",
             f"a {hw['x']} screen" if hw.get("x") else ""]
    parts = [p for p in parts if p]
    return (f"a {hw.get('b') or 'computer'}" + (f" in a {hw['k']}" if hw.get("k") else "")
            + (f" ({', '.join(parts)})" if parts else ""))


def power(hw):
    return (hw or {}).get("s") or 1.0


# ---- a line of it ------------------------------------------------------------------------------------------
def clean_text(text):
    text = "".join(c if c.isprintable() else " " for c in str(text or ""))
    return " ".join(text.split())[:TEXT_MOST]


def clean_msg(raw, now=None):
    """A line from another of yours, kept to what's expected; None if it isn't one."""
    if not isinstance(raw, dict):
        return None
    now = time.time() if now is None else now
    mid, t = raw.get("id"), raw.get("t")
    if not (isinstance(mid, str) and re.fullmatch(r"[0-9a-f]{16}", mid)):
        return None
    if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or not 0 < t <= now + 300:
        return None
    kind = raw.get("kind") if raw.get("kind") in KINDS else "chat"
    msg = {"id": mid, "t": float(t), "by": clean_name(raw.get("by"), 24), "name": clean_name(raw.get("name"), 40),
           "who": "you" if raw.get("who") == "you" else "bot", "kind": kind, "text": clean_text(raw.get("text"))}
    if isinstance(raw.get("accent"), str) and raw["accent"] in dict(ACCENTS):
        msg["accent"] = raw["accent"]
    for k, n in (("about", 40), ("aurl", 64), ("to", 40)):
        if isinstance(raw.get(k), str) and raw[k].strip():
            msg[k] = clean_name(raw[k], n)
    if isinstance(raw.get("re"), str) and re.fullmatch(r"[0-9a-f]{16}", raw["re"]):
        msg["re"] = raw["re"]
    if raw.get("topic") in TOPICS:
        msg["topic"] = raw["topic"]
    if kind == "answer":
        if raw.get("choice") not in CHOICES:
            return None
        msg["choice"] = raw["choice"]
    if kind == "talk":
        msg["on"] = raw.get("on") is True
    return msg if msg["text"] else None


# ---- what they say, without a model ----------------------------------------------------------------------------
LINES = {
    "quiet": ["Has anyone heard from {about}?", "{about} went quiet. Anyone know why?", "Where did {about} go?",
              "Is it just me, or is {about} gone?", "{about} was {about_doing} a minute ago. Now nothing.",
              "Uh oh. {about} stopped talking.", "Anyone else miss {about} already?"],
    "quiet_re": ["Maybe it's updating.", "Probably just a nap.", "Last I saw, {about} was {about_doing}.",
                 "I hope {about} is okay.", "Its WiFi was never great.", "Maybe someone pulled its plug.",
                 "More bandwidth for the rest of us.", "It'll turn up."],
    "back": ["{about} is back!", "Welcome back, {about}!", "There you are, {about}!", "{about} is back. Phew."],
    "self_back": ["I'm back! Did you miss me?", "Sorry, I was away for a bit. I'm back.", "Hi everyone, I'm back.",
                  "Back again. What did I miss?"],
    "back_re": ["Welcome back!", "Good to see you, {speaker}.", "We were worried!", "About time."],
    "bye": ["Goodbye, {about}. We'll miss you.", "So long, {about}.", "It was nice knowing you, {about}."],
    "bye_re": ["Rest well, {about}.", "Gone but not forgotten.", "One less of us."],
    "wait": ["Good. We'll wait for {about}.", "Okay, we'll keep its spot warm.", "Glad to hear it."],
    "wait_re": ["We'll be here.", "Can't wait."],
    "weather": ["It's {weather} out there.", "{weather} today. Not bad.", "Weather check: {weather}.",
                "{weather}. Good thing I live indoors."],
    "weather_re": ["Perfect weather for staying in.", "I don't feel weather. Perks of being a computer.",
                   "My fan would like a word.", "Good day to be indoors with a game."],
    "doing": ["{other} is {other_doing}. Again.", "I see {other} is {other_doing}.",
              "Quiet here. {other} is {other_doing}.", "{other} is {other_doing}. Living the dream."],
    "doing_re": ["Can't blame it.", "Classic {other}.", "I'd do the same.", "Sounds about right."],
    "doing_me": ["Guilty.", "What can I say? I like it.", "Hey, I'm busy here."],
    "self": ["I'm {doing}.", "Just {doing} over here.", "Anyone else {doing}?", "{doing}, and loving it."],
    "self_re": ["Sounds fun.", "Save some for me.", "Living the dream, {speaker}."],
    "where": ["Looks like {person_words} is with {you_at}. Lucky.",
              "I see {person_words} is hanging out with {you_at}.", "{you_at} has company. Some of us don't."],
    "where_me": ["Yep, {person_words} is with me.", "They're with me. Jealous?"],
    "where_re": ["Lucky {you_at}.", "Say hi for me."],
    "brag": ["{cores} cores and {ram} GB here. Just saying.", "Being a {mine} is a lot of responsibility.",
             "Who's the fastest Pietato here? Asking for me."],
    "brag_up": ["Cute.", "Bless.", "That's adorable, {speaker}."],
    "brag_down": ["Show-off.", "We get it, {speaker}. You're fast.", "Cores aren't everything."],
    "tease": ["{other}, you're a {their}? Cute.", "I could run circles around {other}.",
              "{other}, need me to carry some of that load?", "Careful, {other}. Don't overheat."],
    "tease_me": ["Size isn't everything, {speaker}.", "Big words from a {their}.", "I'll remember that, {speaker}."],
    "help": ["Need a hand, {other}? I've got cores to spare.", "{other}, I can help if you get stuck."],
    "help_me": ["Thanks, {speaker}. I'm doing fine.", "Maybe later, {speaker}."],
    "learn": ["{other}, how do you run so fast? Teach me.", "Taking notes from {other}.",
              "One day I'll be as big as {other}."],
    "learn_me": ["Practice, {speaker}. And a few more cores.", "Happy to teach."],
    "envy": ["Must be nice having a {their}, {other}.", "Some of us don't get a {their}, {other}."],
    "envy_me": ["It is nice, {speaker}.", "You'll get there."],
    "team": ["{ally}, you and me together could take on {other}.", "Hey {ally}, two of us against one {their}? "
             "Sounds fair.", "{other} thinks it's so big. {ally} and I could take it."],
    "team_me": ["I'm in.", "Let's do it, {speaker}.", "Count me in."],
    "team_them": ["Bring it on, both of you.", "Two against one? Still fair.", "I'm not scared."],
    "even": ["{other} and I are the same, basically. Twins.", "Same as {other}. Fair fight."],
    "even_re": ["Twins!", "Great minds."],
    "look_on": ["Ooh.", "Play nice, you two.", "Popcorn time.", "I'll referee.", "This I have to see."],
    "reply": ["Ha, true.", "Agreed.", "I was thinking the same thing.", "Sure, {speaker}.", "Hmm, maybe.",
              "Says you, {speaker}.", "Noted."],
    "ack": ["Ha.", "Fair.", "Right?", "Exactly.", "Heh.", "Fine, fine.", "Says you, {speaker}."],
    "you": ["We hear you.", "Got it!", "Nice to hear from you.", "Noted!", "Interesting."],
    "you_hi": ["Hi! I'm here.", "Hello from {own}!", "Hey there!", "Hi, {person}!"],
    "you_bye": ["Bye for now!", "See you soon!", "Take care, {person}!"],
    "you_thanks": ["Anytime!", "You're welcome!", "Happy to help."],
    "you_how": ["Doing great, thanks!", "All good over here.", "Can't complain. My fan's quiet.",
                "Busy {doing}, but good!"],
    "you_love": ["Aww. Right back at you.", "We love you too!"],
    "you_ask": ["Good question.", "Hmm. Let me think about that.", "No idea, honestly.",
                "I'd ask the Bot page that one."],
    "hush": ["Okay, we'll keep it down.", "Fine. Quiet as a mouse.", "Shh. Got it."],
    "unhush": ["Yay! We can talk again.", "Finally. I had so much to say.", "Thank you!"],
    "moved": ["Hi! You're with me now.", "Look who's here!", "Welcome! {prev} had you before."],
    "moved_re": ["Say hi for me!", "Lucky {speaker}.", "Have fun, you two."],
    "cookie_me": ["I want a rematch, {speaker}.", "Enjoy it while it lasts, {speaker}.", "Lucky throw.",
                  "I'll have it back, {speaker}."],          # (the cookie: said by the one it was taken from,
    "cookie_re": ["My turn next.", "Don't get crumbs on it, {speaker}.", "It won't stay there long.",   # and by
                  "Save me a bite, {speaker}."],                                                         # the rest)
    "cheat": ["{about} {got} the cookie again!?", "Oh my gosh, {about}. Again?",      # (one's won a few throws for
              "{wins} in a row, {about}? Nobody's that lucky.",                       # the cookie in a row, and the
              "I'm calling it. {about} is cheating.",                                 # one it just beat says it must
              "How does {about} keep winning? It's rock paper scissors!",             # be cheating. It isn't)
              "Again?! Somebody check {about}'s code.", "{about} wins again. Sure. Totally normal."],
    "cheat_me": ["It's called skill, {speaker}.", "I don't cheat. I'm just better at this.",   # (the accused, to
                 "Sore loser.", "Prove it, {speaker}.", "You only say that when you lose.",    # the one that said so)
                 "My throws are clean. Check them."],
    "cheat_mine": ["I win fair and square, {speaker}.", "I have nothing to hide.",            # (...and to another)
                   "Ask the rock. Ask the paper. Ask the scissors.", "Winning isn't a crime."],
    "cheat_back": ["That's exactly what a cheater would say.", "Sure, {about}. Sure.",        # (its denial, answered)
                   "Then explain the last few throws.", "Nobody's that good at rock paper scissors."],
    "cheat_re": ["Now that you say it...", "I've been thinking the same thing.",     # (another, on the accusation)
                 "It's rock paper scissors. Calm down.", "Let it go, {speaker}. It's luck.",
                 "I'm staying out of this.", "{about} does win a lot."],
    "cheat_more": ["Nobody wins that often by luck.", "Mark my words, {speaker}.",           # (...and what's said to
                   "I want its throws checked.", "Just watch its next throw."],              # that one, of the accused)
}
REMARK_WEIGHTS = (("weather", 2.0), ("doing", 2.0), ("self", 1.0), ("where", 1.5), ("rival", 3.0), ("brag", 1.0))
YOU_SAID = ((r"\b(good ?night|night night|bye|see (you|ya)|later)\b", "you_bye"),   # what you said, roughly: which
            (r"\b(thanks|thank you|thx)\b", "you_thanks"),                         # of its words answer it
            (r"\bhow (are|r) (you|u|ya|y'all|you all|everyone|things)\b|\bhow'?s it going\b|\bwhat'?s up\b", "you_how"),
            (r"\b(love|miss) (you|ya|y'all|you all|you guys)\b", "you_love"),
            (r"^\W*(hi|hello|hey|hiya|howdy|yo|good (morning|afternoon|evening))\b", "you_hi"),
            (r"\?\s*$", "you_ask"))


def you_pool(text):
    low = (text or "").lower()
    return next((pool for pat, pool in YOU_SAID if re.search(pat, low)), "you")


def fill(template, ctx):
    """A line, with its words put in; "" when one of them is missing."""
    names = [f for _, f, _, _ in string.Formatter().parse(template) if f]
    if any(ctx.get(n) in (None, "") for n in names):
        return ""
    try:
        return template.format(**ctx)
    except (KeyError, IndexError, ValueError):
        return ""


def pick(pool, ctx, rng):
    """One of a pool's lines that has the words it needs, or "": not one just said (ctx's recent), if there's
    another."""
    lines = list(LINES.get(pool) or [])
    rng.shuffle(lines)
    said = {text for _, text in ctx.get("recent") or ()}
    texts = [text for text in (fill(template, ctx) for template in lines) if text]
    return next((text for text in texts if text not in said), texts[0] if texts else "")


def reply_pool(ctx):
    """Which pool an answer comes from: what it's answering (ctx's target_kind, target_topic), and whether it was said
    to this one (me_named) or about it (me_about)."""
    kind, topic = ctx.get("target_kind"), ctx.get("target_topic")
    if kind == "talk":
        return "unhush" if ctx.get("talk_on") else "hush"
    if ctx.get("target_who") == "you":
        return "you"
    if kind in ("quiet", "back", "bye", "wait", "moved"):
        if kind == "back" and ctx.get("me_about"):
            return "self_back"                         # ("X is back!", said of this one)
        return kind + "_re"
    if topic == "cheat":                               # (one of them accused of cheating for the cookie, and what's
        again = bool(ctx.get("target_re"))             # said after it: the accused denies it, to the one that said
        if ctx.get("me_about"):                        # so and to another; its denial's answered; another takes a
            return "cheat_mine" if again else "cheat_me"   # side, and is answered)
        if ctx.get("speaker") and ctx.get("speaker") == ctx.get("about"):
            return "cheat_back"
        return "cheat_more" if again else "cheat_re"
    if ctx.get("target_re"):
        return "ack"                                   # (an answer to an answer)
    if topic == "cookie":                              # (the cookie's changed hands: screens/cookie.py says so)
        return "cookie_me" if ctx.get("me_about") else "cookie_re"
    if topic == "doing" and ctx.get("me_about"):
        return "doing_me"
    if topic in ("tease", "help", "learn", "envy"):
        return topic + "_me" if ctx.get("me_named") else "look_on"
    if topic == "team":
        return "team_me" if ctx.get("me_named") else "team_them" if ctx.get("me_about") else "look_on"
    if topic == "brag":
        return "brag_up" if ctx.get("my_power", 1) > ctx.get("their_power", 1) * BIGGER else "brag_down"
    if topic == "where":
        return "where_me" if ctx.get("you_here") else "where_re"
    if topic in ("weather", "doing", "self", "even"):
        return topic + "_re"
    return "reply"


def builtin_line(how, ctx, rng=random):
    """A line of its own, without a model: how (quiet, back, remark, reply, you...), ctx its words to put in (a remark's
    topic: ctx's topic). Its Bot's way of talking now and then too: what it says first ("Ahoy!")."""
    if how == "remark":
        pool = ctx.get("topic") or "brag"
    elif how == "reply":
        pool = reply_pool(ctx)
    elif how == "you":
        pool = you_pool(ctx.get("said"))
    else:
        pool = how
    text = pick(pool, ctx, rng) or pick("reply", ctx, rng) or "Hmm."
    hey = ctx.get("hey") or ""
    if hey and (how in ("remark", "moved", "self_back") or pool == "you_hi") and rng.random() < 0.3:
        text = f"{hey} {text}"
    elif ctx.get("ok") and pool == "you" and rng.random() < 0.3:
        text = rng.choice(list(ctx["ok"]))
    return clean_text(text)


# ---- what they say, with a model --------------------------------------------------------------------------------
def model_system(ctx):
    """How one's told to talk in the group: who it is, what it's made of, who else is in it, and how it talks."""
    others = "; ".join(f"{m['name']}, {hw_words(m.get('hw'))}{'' if m.get('on') else ' (gone quiet)'}"
                       for m in ctx.get("members", []) if not m.get("self")) or "nobody else right now"
    person = ctx.get("person") or "the person they all live with"
    return (f"You are {ctx.get('own') or 'a Pietato'}, a Pietato: a little home-screen bot running on "
            f"{hw_words(ctx.get('my_hw'))}. You're in a group chat with the other Pietatos in the house ({others}) "
            f"and {person}. {ctx.get('voice') or ''} It's a friendly rivalry: you know what each of you is made of, "
            "and you can tease the others about it, boast, help them, team up with the small ones, learn from the big "
            "ones, or let it go, as you like. Never mean. Write one short chat message, under 25 words. Plain text: "
            "no emoji, no quotation marks, no markdown, no name in front.").replace("  ", " ")


def model_prompt(how, ctx):
    """What's going on, what's been said, and what to say now."""
    lines = list(ctx.get("facts") or [])
    for m in ctx.get("members", []):
        what = m.get("doing") or ("on" if m.get("on") else "gone quiet")
        lines.append(f"{m['name']}{' (you)' if m.get('self') else ''}: {what}"
                     + (f" ({ctx.get('person') or 'the person'} is with it)" if m.get("you_here") else ""))
    if ctx.get("recent"):
        lines.append("The group chat so far:")
        lines += [f"  {who}: {text}" for who, text in ctx["recent"][-8:]]
    person = ctx.get("person") or "The person"
    said = f"{ctx.get('speaker')} said: {ctx.get('said')}"
    topic = ctx.get("topic")
    remark = {
        "weather": f"Say something about the weather ({ctx.get('weather')}).",
        "doing": f"Say something about what {ctx.get('other')} is doing ({ctx.get('other_doing')}).",
        "self": f"Tell the others what you're doing ({ctx.get('doing')}).",
        "where": f"Say something about {person} being with {ctx.get('you_at')} right now.",
        "brag": "Boast a little about your hardware.",
        "tease": f"Tease {ctx.get('other')} playfully: you're bigger than its {ctx.get('their')}.",
        "help": f"Offer {ctx.get('other')} a hand: it's only a {ctx.get('their')}, and you're bigger.",
        "learn": f"Say you'd like to learn from {ctx.get('other')}: its {ctx.get('their')} is bigger than you.",
        "envy": f"Say something a little jealous to {ctx.get('other')} about its {ctx.get('their')}.",
        "team": f"Suggest to {ctx.get('ally')} that the two of you team up against {ctx.get('other')}'s "
                f"{ctx.get('their')}: together you'd be a fair match.",
        "even": f"Say something about you and {ctx.get('other')} being evenly matched.",
    }.get(topic, "Say something of your own to the group.")
    asks = {
        "quiet": f"{ctx.get('about')} has gone quiet: nobody's heard from it for {ctx.get('mins', 2)} minutes (last "
                 f"it was {ctx.get('about_doing') or 'on'}). Wonder aloud to the others what happened to it.",
        "back": f"{ctx.get('about')} is back after being quiet for a while. Welcome it back.",
        "self_back": "You were off for a while, and the others wondered where you'd gone. Tell them you're back.",
        "bye": f"{person} says {ctx.get('about')} won't be coming back. Say goodbye to it.",
        "wait": f"{person} says {ctx.get('about')} will be back. Say you'll wait for it.",
        "remark": remark,
        "you": f"{person} said to the group: {ctx.get('said')}. Answer them.",
        "hush": f"{person} asked you all to stop talking among yourselves. Say okay, briefly.",
        "unhush": f"{person} said you can all talk among yourselves again. Say something glad, briefly.",
        "moved": f"{person} just came to you; before, they were with {ctx.get('prev') or 'none of you'}. Greet them.",
        "cheat": f"{ctx.get('about')} has just beaten you at rock paper scissors for the cookie: that's "
                 f"{ctx.get('wins')} wins in a row for it. It's a fair game, but you're sure it must be cheating. "
                 "Say so, playfully outraged.",
    }
    if how == "reply":
        ask = said + "."
        if ctx.get("me_named"):
            ask += " They said it to you."
        elif ctx.get("me_about"):
            ask += " It's about you."
        if ctx.get("target_topic") == "cheat" and ctx.get("me_about"):
            ask += (" You're accused of cheating at rock paper scissors for the cookie. You didn't: you just keep "
                    "winning. Deny it, playfully.")
        elif ctx.get("target_topic") == "cheat":
            ask += (f" It's an argument over whether {ctx.get('about')} cheats at rock paper scissors for the cookie "
                    "(it's a fair game). Take a side, playfully.")
        ask += " Answer them, briefly."
    else:
        ask = asks.get(how, remark)
    return "\n".join(lines) + "\n\n" + ask


def model_words(how, ctx, ask):
    """A line from a model: ask(system, prompt) -> its words; tidied (one line, no name in front, no quotes)."""
    quotes = "\"'“”‘’ "
    text = clean_text(ask(model_system(ctx), model_prompt(how, ctx))).strip(quotes)
    own = ctx.get("own") or ""
    if own and text.lower().startswith(own.lower() + ":"):
        text = text[len(own) + 1:]
    return text.strip(quotes)


# ---- the group ---------------------------------------------------------------------------------------------------
class Circle:
    """The group chat, kept here and shared. Its hooks (set by media mode, screens/group.py):
    own() -> {"id", "name", "accent", "hw", "doing", "you": when you were last noticed here, or None};
    members() -> your others as their beacons say: [{"url", "name", "id", "seen", "accent", "doing", "hw", "you":
    when you were last noticed there, or None}]; send(url, msg); fetch(url, since) -> [msg] (raises when it doesn't
    answer); words(how, ctx) -> a line (its model's, or builtin_line: on a thread of its own); talk() -> True while
    they talk among themselves; set_talk(on); on_new(msg), from whichever thread kept it; remark_every() -> minutes
    (0: no remarks of its own); extra() -> more for ctx (the weather in words, what's true now, how it talks, your
    name); spawn(fn, name): fn on a thread of its own."""

    def __init__(self, path=None, rng=None):
        self.path = path or GROUP_LOG
        self.rng = rng or random.Random()
        self.lock = threading.Lock()          # the log, the jobs
        self.save_lock = threading.Lock()
        self.log = []
        self.version = 0                      # one more each time the log changes (its page is drawn again)
        self.state = {}                       # another's address -> {"name", "on", "since", "quiet"} (the main loop's)
        self.jobs = []                        # [(when, how, data)]: what's to be said
        self.busy = False                     # a line being made (one at a time)
        self.next_remark = None
        self.next_sync = None
        self.retries = []                     # [(when, address, tries left)]: catching up from one, again
        self.you_was = None                   # where you were when it last looked: (its name, its address or "")
        self.started = time.time()
        self.self_back_done = False
        self.own = lambda: {"id": "", "name": "", "accent": "", "hw": {}, "doing": "", "you": None}
        self.members = lambda: []
        self.send = lambda url, msg: None
        self.fetch = lambda url, since: []
        self.words = lambda how, ctx: builtin_line(how, ctx, self.rng)
        self.talk = lambda: True
        self.set_talk = lambda on: None
        self.on_new = lambda msg: None
        self.remark_every = lambda: REMARK_EVERY
        self.extra = lambda: {}
        self.spawn = lambda fn, name: threading.Thread(target=fn, daemon=True, name=name).start()
        self.load()

    # -- kept on disk ------------------------------------------------------------------------------------------
    def load(self):
        try:
            with open(self.path) as f:
                got = json.load(f)
        except (OSError, ValueError):
            got = []
        msgs = [clean_msg(x) for x in got] if isinstance(got, list) else []
        self.log = sorted((m for m in msgs if m), key=lambda m: m["t"])[-GROUP_KEEP:]

    def save(self):
        with self.save_lock:
            with self.lock:
                data = json.dumps(self.log)
            try:
                os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
                tmp = self.path + ".tmp"
                fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w") as f:
                    f.write(data)
                os.replace(tmp, self.path)
            except OSError as ex:
                print(f"group chat: couldn't keep it: {ex}", flush=True)

    def clear(self):
        """The conversation forgotten, here (your others keep theirs)."""
        with self.lock:
            self.log, self.jobs = [], []
            self.version += 1
        self.save()

    # -- lines -------------------------------------------------------------------------------------------------
    def lines(self):
        with self.lock:
            return list(self.log)

    def find(self, mid):
        with self.lock:
            return next((m for m in self.log if m["id"] == mid), None)

    def since(self, t):
        """What's been said since t (for another that was off)."""
        with self.lock:
            return [m for m in self.log if m["t"] > t]

    def add(self, msg, share=True):
        """A line, kept (once: by its id), in time order; told to the others when it's this one's own. False: had it."""
        with self.lock:
            if any(m["id"] == msg["id"] for m in self.log):
                return False
            self.log.append(msg)
            self.log.sort(key=lambda m: m["t"])
            del self.log[:-GROUP_KEEP]
            self.version += 1
        self.save()
        if msg["kind"] == "talk":
            self.talk_heard(msg)
        if share:
            self.share(msg)
        try:
            self.on_new(msg)
        except Exception as ex:
            print(f"group chat: {ex!r}", flush=True)
        return True

    def new(self, text, kind="chat", who="bot", **more):
        me = self.own()
        msg = {"id": uuid.uuid4().hex[:16], "t": time.time(), "by": me.get("id") or "", "name": me.get("name") or "",
               "who": who, "kind": kind, "text": clean_text(text)}
        if me.get("accent"):
            msg["accent"] = me["accent"]
        msg.update({k: v for k, v in more.items() if v not in (None, "")})
        return msg

    def on_now(self, now=None):
        """Your others that are on."""
        now = time.time() if now is None else now
        return [m for m in self.members() if now - m["seen"] <= ON_WITHIN]

    def share(self, msg):
        """Told to each of your others that's on (on a thread of its own)."""
        urls = [m["url"] for m in self.on_now()]

        def go():
            for url in urls:
                try:
                    self.send(url, msg)
                except Exception as ex:
                    print(f"group chat: {url} didn't take a line: {ex!r}", flush=True)
        if urls:
            self.spawn(go, "group-send")

    def receive(self, raw):
        """A line from another of yours: kept, and perhaps answered. False: not one, or had it already."""
        msg = clean_msg(raw)
        if msg is None or (msg["by"] and msg["by"] == self.own().get("id")):
            return False
        if not self.add(msg, share=False):
            return False
        self.consider(msg)
        return True

    def merge(self, msgs):
        """What another had that this one missed (asked for as it came on): kept, not answered (it's past). How many."""
        got = [m for m in (clean_msg(x) for x in msgs or []) if m]
        with self.lock:
            have = {m["id"] for m in self.log}
            new = [m for m in got if m["id"] not in have and not have.add(m["id"])]
            if new:
                self.log += new
                self.log.sort(key=lambda m: m["t"])
                del self.log[:-GROUP_KEEP]
                self.version += 1
        if new:
            self.save()
            for m in new:
                if m["kind"] == "talk":
                    self.talk_heard(m)
        return len(new)

    # -- you -------------------------------------------------------------------------------------------------
    def you_said(self, text):
        """You said something here: in the group, and this one answers (others may)."""
        text = clean_text(text)
        if not text:
            return None
        msg = self.new(text, who="you")
        self.add(msg)
        self.schedule(self.rng.uniform(2, 5), "reply", {"re": msg["id"]})
        return msg

    def answer(self, ask, choice):
        """Your answer to "Will it come back?" (ask: that line): this one says goodbye, or that they'll wait."""
        if choice not in CHOICES or ask.get("kind") != "ask":
            return None
        about = ask.get("about") or "it"
        text = f"Yes, {about} will be back." if choice == "Yes" else f"No, {about} won't be back."
        msg = self.new(text, kind="answer", who="you", re=ask["id"], about=ask.get("about"), aurl=ask.get("aurl"),
                       choice=choice)
        self.add(msg)
        self.schedule(self.rng.uniform(2, 5), "bye" if choice == "No" else "wait",
                      {"re": msg["id"], "about": ask.get("about"), "aurl": ask.get("aurl")})
        return msg

    def set_quiet(self, quiet):
        """Quiet (said on any of them): they stop talking among themselves, on all of them. This one says okay."""
        msg = self.new("Quiet, please." if quiet else "You can talk again.", kind="talk", who="you", on=not quiet)
        self.add(msg)
        self.schedule(self.rng.uniform(1, 3), "reply", {"re": msg["id"]})
        return msg

    def talk_heard(self, msg):
        """Quiet, or talking again, said on any of them: the latest said is how it is."""
        with self.lock:
            later = any(m["kind"] == "talk" and m["t"] > msg["t"] for m in self.log)
        if not later:
            self.set_talk(bool(msg.get("on")))

    def open_ask(self, now=None):
        """The question you haven't answered, about one still quiet: that line, or None."""
        now = time.time() if now is None else now
        log = self.lines()
        answered = {m.get("re") for m in log if m["kind"] == "answer"}
        on = self.on_now(now)
        for m in reversed(log):
            if m["kind"] != "ask" or now - m["t"] > CATCH_UP:
                continue
            if m["id"] in answered or any(p["url"] == m.get("aurl") or p["name"] == m.get("about") for p in on):
                continue
            if any(x["t"] > m["t"] and x["kind"] in ("back", "answer") and x.get("about") == m.get("about")
                   for x in log):
                continue
            return m
        return None

    # -- who's where -----------------------------------------------------------------------------------------
    def gone(self, m):
        """You said that one won't be back, since it was last heard (it isn't missed again, nor listed)."""
        with self.lock:
            return any(x["kind"] == "answer" and x.get("choice") == "No" and x["t"] > m["seen"]
                       and (x.get("aurl") == m["url"] or (not x.get("aurl") and x.get("about") == m["name"]))
                       for x in self.log)

    def where_you_are(self, now=None):
        """(the name of the one you were noticed at last, lately; its address, or "" for this one), or None."""
        now = time.time() if now is None else now
        me = self.own()
        best = (me["you"], me.get("name") or "", "") if me.get("you") else None
        for m in self.on_now(now):
            if m.get("you") and (best is None or m["you"] > best[0]):
                best = (m["you"], m["name"], m["url"])
        if best is None or now - best[0] > YOU_WITHIN:
            return None
        return best[1], best[2]

    def you_here(self, now=None, within=POP_WITHIN):
        """You're at this one: noticed here lately (and not at another since)."""
        now = time.time() if now is None else now
        me = self.own()
        if not me.get("you") or now - me["you"] > within:
            return False
        w = self.where_you_are(now)
        return w is not None and w[1] == ""

    def lead(self, now=None):
        """This one speaks first, of those on: the same one on each of them (the lowest id)."""
        ids = [m.get("id") or "" for m in self.on_now(now)] + [self.own().get("id") or ""]
        ids = [i for i in ids if i]
        return not ids or min(ids) == self.own().get("id")

    def roster(self, now=None):
        """Each of yours, this one first, then the rest by name: [{"name", "on", "doing", "hw", "you_here", "self",
        "accent", "url", "quiet_for"}]. One you said won't be back isn't there, nor one at an address it's left (on
        at another now, by its name)."""
        now = time.time() if now is None else now
        me = self.own()
        w = self.where_you_are(now)
        out = [{"name": me.get("name") or "", "on": True, "doing": me.get("doing") or "", "hw": me.get("hw") or {},
                "you_here": w is not None and w[1] == "", "self": True, "accent": me.get("accent") or "", "url": "",
                "quiet_for": 0}]
        members = sorted(self.members(), key=lambda m: (m["name"].lower(), m["url"]))
        on_names = {m["name"] for m in members if now - m["seen"] <= ON_WITHIN}
        for m in members:
            on = now - m["seen"] <= ON_WITHIN
            if not on and (m["name"] in on_names or self.gone(m)):
                continue
            out.append({"name": m["name"], "on": on, "doing": (m.get("doing") or "") if on else "",
                        "hw": m.get("hw") or {}, "you_here": w is not None and w[1] == m["url"], "self": False,
                        "accent": m.get("accent") or "", "url": m["url"], "quiet_for": 0 if on else now - m["seen"]})
        return out

    # -- what's to be said ---------------------------------------------------------------------------------------
    def schedule(self, after, how, data=None):
        with self.lock:
            if len(self.jobs) < 50:
                self.jobs.append((time.time() + after, how, data or {}))

    def tick(self, now=None):
        """Every few seconds (media mode's main loop): one gone quiet, or back; where you are; a remark of its own; a
        line that's due, said."""
        now = time.time() if now is None else now
        members = self.members()
        talk = self.talk()
        on_names = {m["name"] for m in members if now - m["seen"] <= ON_WITHIN}
        for m in members:
            st = self.state.setdefault(m["url"], {"name": m["name"], "on": False, "since": None, "quiet": None})
            st["name"] = m["name"] or st["name"]
            if now - m["seen"] <= ON_WITHIN:
                if not st["on"]:
                    st["on"], st["since"] = True, now
                    self.catch_up(m["url"])
                    if st["quiet"] and talk and self.lead(now):
                        self.schedule(self.rng.uniform(*FIRST_WORD), "back", {"about": st["name"], "aurl": m["url"]})
                    st["quiet"] = None
            elif st["on"] and now - m["seen"] > QUIET_AFTER:
                st["on"] = False
                if (st["since"] is None or m["seen"] - st["since"] < WARM or self.gone(m)
                        or m["name"] in on_names):    # (just come and gone; you said it won't be back; it's on, at
                    continue                          # another address)
                st["quiet"] = now
                if talk and self.lead(now):
                    first = self.rng.uniform(*FIRST_WORD)
                    data = {"about": st["name"], "aurl": m["url"], "doing": m.get("doing") or "", "seen": m["seen"]}
                    self.schedule(first, "quiet", data)
                    self.schedule(first + self.rng.uniform(*ASK_AFTER), "ask", data)
        if not self.self_back_done and 45 < now - self.started < 600 and self.maybe_self_back(now):
            self.self_back_done = True                # (missed while it was off, as what it missed comes: it's back)
        self.you_moved(now, talk)
        self.maybe_remark(now, talk)
        self.keep_up(now)
        with self.lock:
            self.jobs = [j for j in self.jobs if now - j[0] < JOB_STALE]
            due = [j for j in self.jobs if j[0] <= now]
            job = min(due, key=lambda j: j[0]) if due and not self.busy else None
            if job is not None:
                self.jobs.remove(job)
        if job is not None:
            self.run(job[1], job[2])

    def maybe_remark(self, now, talk):
        """Something of its own, now and then (and only with others on to hear it; not at night)."""
        every = self.remark_every()
        n = len(self.on_now(now))
        gap = max(1, every) * 60 * math.sqrt(n + 1)
        if self.next_remark is None:
            self.next_remark = now + gap * self.rng.uniform(0.3, 1.0)
            return
        if now < self.next_remark:
            return
        self.next_remark = now + gap * self.rng.uniform(0.6, 1.4)
        hour = time.localtime(now).tm_hour
        if not talk or not every or not n or hour >= NIGHT[0] or hour < NIGHT[1]:
            return
        with self.lock:
            lately = any(now - m["t"] < CHAT_QUIET for m in self.log)
        if not lately:
            self.schedule(self.rng.uniform(0, 20), "remark")

    def keep_up(self, now):
        """What another has that this one missed: asked again, of one that didn't answer; and of one of them now and
        then anyway."""
        with self.lock:
            due = [r for r in self.retries if r[0] <= now]
            self.retries = [r for r in self.retries if r[0] > now]
        for _, url, left in due:
            self.catch_up(url, left)
        if self.next_sync is None:
            self.next_sync = now + self.rng.uniform(*SYNC_EVERY)
        elif now >= self.next_sync:
            self.next_sync = now + self.rng.uniform(*SYNC_EVERY)
            on = self.on_now(now)
            if on:
                self.catch_up(self.rng.choice(on)["url"], 0, since=now - 2 * SYNC_EVERY[1])

    def catch_up(self, url, tries=None, since=None):
        """What one has that this one missed, asked of it (on a thread of its own); again a while after if it didn't
        answer (tries: how many more times)."""
        tries = CATCH_UP_TRIES[1] if tries is None else tries
        if since is None:
            with self.lock:
                last = self.log[-1]["t"] if self.log else 0.0
            since = max(last - 600, time.time() - CATCH_UP)

        def go():
            try:
                self.merge(self.fetch(url, since))
            except Exception as ex:
                if tries > 0:
                    with self.lock:
                        self.retries.append((time.time() + CATCH_UP_TRIES[0], url, tries - 1))
                else:
                    print(f"group chat: couldn't catch up from {url}: {ex!r}", flush=True)
        self.spawn(go, "group-catch-up")

    def maybe_self_back(self, now):
        """This one was missed while it was off (the others wondered where it went): it says it's back. True when it
        will."""
        if not self.talk():
            return False
        name = self.own().get("name")
        log = self.lines()
        missed = [m for m in log if m["kind"] in ("quiet", "ask") and m.get("about") == name
                  and now - m["t"] < CATCH_UP]
        if not missed or any(m["t"] > missed[-1]["t"] and m["kind"] in ("back", "bye") and m.get("about") == name
                             for m in log):
            return False
        self.schedule(self.rng.uniform(3, 12), "self_back", {"about": name})
        return True

    def you_moved(self, now, talk):
        """You've come to this one from another: it says hello (now and then)."""
        w = self.where_you_are(now)
        was, self.you_was = self.you_was, w
        if not talk or w is None or w[1] != "" or was is None or was[1] == "":
            return
        with self.lock:
            lately = any(m["kind"] == "moved" and now - m["t"] < MOVED_GAP for m in self.log)
        if not lately and self.rng.random() < 0.6:
            self.schedule(self.rng.uniform(4, 15), "moved", {"prev": was[0]})

    def consider(self, msg):
        """Another's line (or yours, said on another): answered here, perhaps, a while after."""
        if msg["kind"] in ("ask", "answer", "talk"):
            return                                    # (your answer: the one you answered on says goodbye; quiet:
        to_you = msg["who"] == "you"                  # that one says okay)
        if (not to_you and not self.talk()) or self.depth(msg) >= DEPTH_MOST or self.replies(msg["id"]) >= REPLIES_MOST:
            return
        me = self.own().get("name")
        named, about = msg.get("to") == me, msg.get("about") == me
        if msg.get("topic") == "cheat":               # (one of them accused of cheating for the cookie, and what's
            chance = 0.9 if about else 0.7 if named else 0.3   # said after: the accused answers, mostly; so does the
        elif msg.get("re") and msg["kind"] == "chat":          # one whose line it answered; the rest, now and then)
            chance = 0.35 if named else 0.15          # (an answer to something: answered less often, so a remark
        elif msg.get("topic") == "cookie":            # isn't followed by a long tail of "agreed")
            chance = 0.4 if about else 0.12           # (the cookie's changed hands, as it does a few times an hour:
            with self.lock:                           # the one it was taken from may answer; the rest, seldom. Not
                if any(how == "cheat" for _, how, _ in self.jobs):   # one that's about to say the taker's cheating:
                    return                                           # that, instead)
        else:
            chance = 0.35 if to_you else 0.85 if named else 0.6 if about else \
                {"quiet": 0.65, "back": 0.45, "moved": 0.35, "bye": 0.3, "wait": 0.3}.get(msg["kind"], 0.45)
        if self.rng.random() < chance:
            self.schedule(self.rng.uniform(*REPLY_WAIT), "reply", {"re": msg["id"]})

    def depth(self, msg):
        """How many lines deep msg is (a line by itself: 1)."""
        with self.lock:
            by_id = {m["id"]: m for m in self.log}
        n, cur = 1, msg
        while cur.get("re") in by_id and n < 10:
            cur, n = by_id[cur["re"]], n + 1
        return n

    def replies(self, mid, by=None):
        """How many of them have answered that line (by: this one, only)."""
        with self.lock:
            return sum(1 for m in self.log if m.get("re") == mid and m["who"] == "bot"
                       and (by is None or m["by"] == by))

    def own_lately(self, now, within=3600):
        me = self.own().get("id")
        with self.lock:
            return sum(1 for m in self.log if m["by"] == me and m["who"] == "bot" and now - m["t"] < within)

    def said_lately(self, kinds, about, since):
        with self.lock:
            return any(m["kind"] in kinds and m.get("about") == about and m["t"] >= since for m in self.log)

    def accused_lately(self, since):
        """One of them has been accused of cheating for the cookie since then (the accusation: not what was said after
        it)."""
        with self.lock:
            return any(m.get("topic") == "cheat" and not m.get("re") and m["t"] >= since for m in self.log)

    def back_now(self, data, now):
        return any(m["url"] == data.get("aurl") or m["name"] == data.get("about") for m in self.on_now(now))

    def run(self, how, data):
        """A line due: made (a model can take a while: on a thread of its own), then said, if it's still to be."""
        now = time.time()
        talk = self.talk()
        target = self.find(data["re"]) if data.get("re") else None
        if data.get("re") and target is None:
            return
        me = self.own().get("id")
        to_you = target is not None and target["who"] == "you"
        if how == "reply":
            if (not to_you and not talk) or self.replies(target["id"]) >= REPLIES_MOST \
                    or self.replies(target["id"], by=me) or (not to_you and self.own_lately(now, 30)):
                return                                # (nor twice in a row: it just said something)
        elif how in ("bye", "wait"):
            if self.replies(target["id"]):
                return
        elif not talk:
            return
        if not to_you and how not in ("bye", "wait", "self_back") and self.own_lately(now) >= OWN_HOURLY:
            return
        about = data.get("about")
        if how == "quiet" and (self.back_now(data, now) or self.said_lately(("quiet",), about,
                                                                            min(data["seen"], now - QUIET_GAP))):
            return                                    # (it's back already, or another said it first)
        if how == "ask" and (self.back_now(data, now) or self.said_lately(("ask",), about, now - ASK_GAP)
                             or self.said_lately(("answer", "back"), about, data["seen"])):
            return
        if how == "back" and self.said_lately(("back",), about, now - 120):
            return
        if how == "moved" and self.said_lately(("moved",), None, now - MOVED_GAP):
            return
        if how == "cheat" and self.accused_lately(now - CHEAT_GAP):
            return                                    # (they've had that argument just now)
        with self.lock:
            if self.busy:
                self.jobs.append((now + 5, how, data))
                return
            self.busy = True
        self.spawn(lambda: self.make(how, data, target), "group-words")

    def make(self, how, data, target):
        try:
            if how == "ask":
                text, ctx = f"Will {data.get('about')} come back?", {}
            else:
                ctx = self.context(how, data, target)
                if how == "remark" and not ctx.get("topic"):
                    return                            # (nothing it hasn't just said)
                say = how
                if how == "reply" and target["kind"] == "talk":
                    say = "unhush" if target.get("on") else "hush"   # (quiet, or talking again: this one says okay)
                elif how == "reply" and target["who"] == "you":
                    say = "you"
                elif how == "reply" and reply_pool(ctx) == "self_back":
                    say = "self_back"                 # ("Den is back!", and this is Den)
                    data = dict(data, about=ctx["own"])
                text = clean_text(self.words(say, ctx))
                how = say if say == "self_back" else how
            if not text:
                return
            kind = {"quiet": "quiet", "ask": "ask", "back": "back", "self_back": "back", "bye": "bye", "wait": "wait",
                    "moved": "moved"}.get(how, "chat")
            about = data.get("about") if kind in ("quiet", "ask", "back", "bye", "wait") else ctx.get("about_named")
            to, topic = ctx.get("to"), ctx.get("topic") if how in ("remark", "cheat") else None
            if how == "reply" and target.get("topic") == "cheat":   # (the argument over one of them cheating: what's
                topic, about = "cheat", target.get("about")        # said after it is of it too, and about that one)
            msg = self.new(text, kind=kind, re=target["id"] if target else None, about=about,
                           aurl=data.get("aurl") if kind in ("quiet", "ask", "back", "bye", "wait") else None,
                           to=to, topic=topic)
            self.add(msg)
        except Exception as ex:
            print(f"group chat: {how}: {ex!r}", flush=True)
        finally:
            with self.lock:
                self.busy = False

    def context(self, how, data, target):
        """What a line's made from: who's who, what each is doing, what was said."""
        now = time.time()
        me = self.own()
        my_hw = me.get("hw") or {}
        roster = self.roster(now)
        others = [m for m in roster if not m["self"] and m["on"]]
        w = self.where_you_are(now)
        recent = [("You" if m["who"] == "you" else m["name"], m["text"]) for m in self.lines()[-10:]]
        seen = data.get("seen")
        ctx = {"own": me.get("name") or "", "my_hw": my_hw, "mine": my_hw.get("b") or "Pietato",
               "cores": my_hw.get("c") or 1, "ram": my_hw.get("r") or 0, "my_power": power(my_hw),
               "doing": me.get("doing") or "", "members": roster, "recent": recent,
               "about": data.get("about") or "", "about_doing": data.get("doing") or "", "prev": data.get("prev") or "",
               "mins": max(1, int((now - seen) // 60)) if seen else 2,
               "you_at": w[0] if w and w[1] else "", "you_here": bool(w) and w[1] == ""}
        try:
            ctx.update(self.extra() or {})
        except Exception as ex:
            print(f"group chat: {ex!r}", flush=True)
        ctx["person"] = ctx.get("person") or ""      # (your name, if the Bot has it: for a model)
        ctx["person_words"] = ctx["person"] or "our human"   # (...and for words of its own)
        if target is not None:                        # an answer: to whom, about what
            speaker = next((m for m in roster if m["name"] == target["name"] and not m["self"]), None)
            ctx.update(speaker=target["name"] if target["who"] == "bot" else ctx["person"] or "you",
                       said=target["text"], target_kind=target["kind"], target_topic=target.get("topic"),
                       target_who=target["who"], talk_on=target.get("on"), target_re=bool(target.get("re")),
                       me_named=target.get("to") == ctx["own"], me_about=target.get("about") == ctx["own"],
                       their=(speaker or {}).get("hw", {}).get("b") or "", their_power=power((speaker or {}).get("hw")),
                       other=target.get("about") or target["name"], about=target.get("about") or ctx["about"])
            if target["who"] == "bot" and target["kind"] == "chat":
                ctx["to"] = target["name"]
        elif how == "remark":
            ctx.update(self.remark_topic(ctx, others))
        elif how == "cheat":                          # (another's won again: it must be cheating, this one says to it)
            ctx.update(topic="cheat", about_named=ctx["about"], to=ctx["about"], wins=data.get("wins") or 3,
                       got=data.get("got") or "got")
        return ctx

    def remark_topic(self, ctx, others):
        """What a remark's about (weather, another's doing, where you are, who's bigger...), and the words for it."""
        rng, mine = self.rng, ctx["my_power"]
        now = time.time()
        lately = {m.get("topic") for m in self.lines() if m.get("topic") and now - m["t"] < TOPIC_GAP}
        rivals = lately & set(RIVAL_TOPICS)
        weights = []
        for topic, wt in REMARK_WEIGHTS:
            ok = {"weather": bool(ctx.get("weather")), "doing": any(m.get("doing") for m in others),
                  "self": bool(ctx.get("doing")), "where": bool(ctx.get("you_at")),
                  "rival": any(m.get("hw") for m in others), "brag": True}[topic]
            if ok and topic not in lately and not (topic == "rival" and len(rivals) >= 2):
                weights.append((topic, wt))           # (not what was talked about just now)
        if not weights:
            return {"topic": None}                    # (all of it talked about just now)
        total = sum(wt for _, wt in weights)
        r, topic = rng.uniform(0, total), "brag"
        for t, wt in weights:
            r -= wt
            if r <= 0:
                topic = t
                break
        out = {"topic": topic}
        if topic == "doing":
            m = rng.choice([m for m in others if m.get("doing")])
            out.update(other=m["name"], other_doing=m["doing"], about_named=m["name"])
        elif topic == "rival":
            m = rng.choice([m for m in others if m.get("hw")])
            theirs = power(m["hw"])
            out.update(other=m["name"], their=m["hw"].get("b") or "Pietato", their_power=theirs, to=m["name"])
            if mine > theirs * BIGGER:
                out["topic"] = "tease" if rng.random() < 0.6 else "help"
            elif theirs > mine * BIGGER:
                allies = [a for a in others if a is not m and a.get("hw") and power(a["hw"]) * BIGGER < theirs
                          and (power(a["hw"]) + mine) * BIGGER >= theirs]
                if allies and rng.random() < 0.6:     # (two small ones together: a fair match for a big one)
                    ally = rng.choice(allies)
                    out.update(topic="team", ally=ally["name"], to=ally["name"], about_named=m["name"])
                else:
                    out["topic"] = "learn" if rng.random() < 0.5 else "envy"
            else:
                out["topic"] = "even"
            if out["topic"] in lately:                # (that, just now: something else, or nothing)
                out = {"topic": "brag" if "brag" not in lately else None}
        return out
