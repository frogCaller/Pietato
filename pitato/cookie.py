"""The Cookie: your Pietatos (and a guest's, while it's on your network) play each other at rock paper scissors for
cookies. One of them is the one to beat: the one that got the last cookie. Another that beats it at one throw gets a
cookie, and is the one to beat from then on; a loss, and the one it played gets another; the same throw, and nobody
does. A cookie's eaten as it's got: none is ever taken from anyone, and nothing a Pietato shows or says puts it that
way ("Den got a cookie", "I got a cookie!"). Their Bots play by themselves now and then; on the one in your hands you
can throw instead (Apps > The Cookie).

This is its rules, with nothing of media mode in them:
- which Pietato is which: an id of its own for each (16 hex digits, made once and kept);
- who got the last cookie, as a Pietato knows it ("the cookie", in the code): {"n": how many times that's been another
  one (1: the first), "at": its id, "name": its name, "t": when, "from": the one it beat for it (or the one before
  it), "how": "new" (the first cookie: nobody was beaten for it), "left" (the one before it went quiet for an hour,
  and this one got the next) or the two throws that won it, the winner's first ("pr": paper over rock), "you": a
  person threw the winner's}. Every Pietato keeps the one it knows and tells your others in its beacon; of two, the
  one with the higher n is right (the same n: the one whose id is lower), so two are never both the one to beat for
  long, and one that was off finds out as it comes back;
- each Bot's habit at rock paper scissors, from its id (so it's always the same Bot's): one leans on a throw, one
  never throws the same twice, one throws what last beat it, one goes round in order. Its last few throws are told
  with the cookie, for your other Pietatos' pages to show: that's how you learn it;
- which gets the next cookie when the one that got the last has gone quiet: of those that are on, the one that's
  waited longest;
- how many throws in a row a Pietato has won, told with the cookie too: from its third, the one it's just beaten may
  say it must be cheating (it isn't), and your others take sides in the group chat (circle.py's "cheat").
(screens/cookie.py: media mode's part, who throws when. cookiepage.py: its page.)"""
import hashlib
import math
import re

from .config import clean_name

COOKIE_THROWS = ("r", "p", "s")
COOKIE_THROW = {"r": "rock", "p": "paper", "s": "scissors"}
COOKIE_BEATS = {"r": "s", "p": "r", "s": "p"}                 # what each throw beats
COOKIE_ID = re.compile(r"[0-9a-f]{16}")
COOKIE_KEPT = 6               # of its Bot's throws, the last this many are kept (and told: your others show them)
COOKIE_HABITS = ("rock", "paper", "scissors", "change", "copy", "round")
COOKIE_LEAN = 0.6             # a Bot that leans on a throw: it's that one this often
COOKIE_HABIT = 0.75           # ...one that copies, or goes round: it does this often (any throw, the rest of the time,
                              # so two Bots' habits never lock the cookie between them)
COOKIE_SUSPECT = 3            # wins in a row from which the one just beaten may say the winner's cheating,
COOKIE_ACCUSE = (0.6, 0.15, 0.9)   # ...how likely: at that many; more with each win after; at most
COOKIE_WON = ("I got a cookie! {beats}, {other}.", "I got a cookie! My {mine} beat {other}'s {theirs}.",
              "I beat {other}, and got a cookie! {Mine} over {theirs}.")   # (what the one that's got a cookie says)
COOKIE_YOU_WON = ("We got a cookie! {beats}, {other}.",                    # (...with your throw)
                  "We beat {other}, and I got a cookie! {Mine} over {theirs}.")
COOKIE_NEXT = ("{other}'s been gone a while. I got a cookie!",             # (...the one before it gone quiet)
               "No sign of {other}, so I got a cookie!")
COOKIE_GOT = ("I got a cookie!",)                                          # (...the first one)


def cookie_whose(x):
    """A Pietato's id for the cookie, if that's one; else None."""
    return x if isinstance(x, str) and COOKIE_ID.fullmatch(x) else None


def cookie_count(v, most=10 ** 9):
    return v if isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= most else None


def cookie_beat(how):
    """how is two throws, the first beating the second ("pr"): a cookie won by them."""
    return isinstance(how, str) and len(how) == 2 and how[0] in COOKIE_BEATS and COOKIE_BEATS[how[0]] == how[1]


def cookie_rec(raw):
    """The cookie as another says it is (or as it was kept here), kept to what's expected; None if it isn't one."""
    if not isinstance(raw, dict):
        return None
    n, at = cookie_count(raw.get("n")), cookie_whose(raw.get("at"))
    if not n or at is None:
        return None
    t, how = raw.get("t"), raw.get("how")
    ok = isinstance(t, (int, float)) and not isinstance(t, bool) and math.isfinite(t) and 0 < t < 1e11
    return {"n": n, "at": at, "name": clean_name(raw.get("name"), 40) or "A Pietato", "t": float(t) if ok else 0.0,
            "from": clean_name(raw.get("from"), 40), "how": how if how in ("new", "left") or cookie_beat(how) else "",
            "you": raw.get("you") is True}


def cookie_newer(a, b):
    """a is who got the last cookie, not b (either may be None: none known): its n is higher; the same n, the one
    whose id is lower. False for the same one twice."""
    if a is None:
        return False
    if b is None:
        return True
    return (a["n"], b["at"]) > (b["n"], a["at"])


def cookie_says(me, rec, had, throws, wins=0):
    """What a Pietato's beacon says of the cookie (to your others): which it is, who got the last one as it knows it,
    that one's n when this one last got one itself (0: it never has), its Bot's last few throws, and how many throws
    in a row it's won."""
    out = {"id": me, "had": had, "throws": throws[-COOKIE_KEPT:], "wins": wins}
    if rec is not None:
        out["rec"] = rec
    return out


def cookie_said(raw):
    """What another's beacon says of the cookie, kept to what's expected: {"id", "rec", "had", "throws", "wins"}; None
    from one that doesn't say (an older Pietato: it doesn't play)."""
    if not isinstance(raw, dict) or cookie_whose(raw.get("id")) is None:
        return None
    throws = raw.get("throws")
    throws = "".join(c for c in throws[-64:] if c in COOKIE_THROW)[-COOKIE_KEPT:] if isinstance(throws, str) else ""
    return {"id": raw["id"], "rec": cookie_rec(raw.get("rec")), "had": cookie_count(raw.get("had")) or 0,
            "throws": throws, "wins": cookie_count(raw.get("wins"), 9999) or 0}


def cookie_result(theirs, mine):
    """How one that threw `theirs` did against `mine`: "won", "lost" or "tie"."""
    return "tie" if theirs == mine else "won" if COOKIE_BEATS[theirs] == mine else "lost"


def cookie_habit(pid):
    """A Bot's habit at rock paper scissors, from its Pietato's id: the same Bot's is always the same."""
    return COOKIE_HABITS[int(hashlib.sha256(pid.encode()).hexdigest()[:8], 16) % len(COOKIE_HABITS)]


def cookie_bot_throw(habit, throws, beat, rng):
    """What a Bot throws: by its habit, mostly. throws: what it's thrown before (the last, last); beat: what beat it,
    the last time it lost ("" if it hasn't)."""
    last = throws[-1:]
    if habit in ("rock", "paper", "scissors"):         # (it leans on one)
        fav = habit[0]
        return fav if rng.random() < COOKIE_LEAN else rng.choice([t for t in COOKIE_THROWS if t != fav])
    if habit == "change":                              # (never the same twice)
        return rng.choice([t for t in COOKIE_THROWS if t != last])
    if rng.random() < COOKIE_HABIT:
        if habit == "copy" and beat in COOKIE_BEATS:   # (what beat it last)
            return beat
        if habit == "round" and last in COOKIE_BEATS:  # (rock, paper, scissors, and round again)
            return COOKIE_THROWS[(COOKIE_THROWS.index(last) + 1) % len(COOKIE_THROWS)]
    return rng.choice(COOKIE_THROWS)


def cookie_accuses(wins, rng):
    """One just beaten by another that's now won `wins` throws in a row: whether it says the winner must be cheating.
    Never before its third; then by chance, likelier the longer it goes on."""
    if wins < COOKIE_SUSPECT:
        return False
    first, more, most = COOKIE_ACCUSE
    return rng.random() < min(most, first + more * (wins - COOKIE_SUSPECT))


def cookie_heir(cands):
    """The one that got the last cookie has gone quiet: which gets the next, of those that are on. cands: (id, the
    cookie's n when it last got one: 0 for never) for each. The one that's waited longest; of two the same, the
    lower id. None with nobody on."""
    return min(cands, key=lambda c: (c[1], c[0]))[0] if cands else None


def cookie_night(hour, night):
    """hour (0 to 23) is in the night: night's (from, till), as (23, 7)."""
    lo, hi = night
    return hour >= lo or hour < hi if lo > hi else lo <= hour < hi


def cookie_beat_words(winner, loser):
    """Paper beats rock. (Scissors beat paper.)"""
    return f"{COOKIE_THROW[winner].capitalize()} beat{'' if winner == 's' else 's'} {COOKIE_THROW[loser]}"


def cookie_ago(secs):
    """How long ago, in a word or two: just now, 12 min ago, 3 h ago, 2 days ago."""
    secs = max(0, int(secs))
    if secs < 90:
        return "just now"
    if secs < 3600:
        return f"{secs // 60} min ago"
    if secs < 2 * 86400:
        return f"{max(1, secs // 3600)} h ago"
    return f"{secs // 86400} days ago"


def cookie_line(rec, rng):
    """What the one that's just got a cookie says in the group chat: that it got one (never that it took one)."""
    other, how = rec.get("from") or "", rec.get("how") or ""
    if cookie_beat(how) and other:
        mine = COOKIE_THROW[how[0]]
        return rng.choice(COOKIE_YOU_WON if rec.get("you") else COOKIE_WON).format(
            other=other, mine=mine, Mine=mine.capitalize(), theirs=COOKIE_THROW[how[1]],
            beats=cookie_beat_words(how[0], how[1]))
    if how == "left" and other:
        return rng.choice(COOKIE_NEXT).format(other=other)
    return rng.choice(COOKIE_GOT)
