"""The AI player getting a game going, and playing on (pitato/instincts.py's PressOn, pitato/anygame.py), on pretend
games that start the way real ones do (tests/pretend_games.py): a title screen; logos first; a title screen that's
all movement; menus; a file to pick; pages of text; a name to put in; an arcade game's coin; a title screen only A
starts; a menu with CONTINUE first and nothing saved; then the game itself, where Start pauses it and a level's end
waits for a button. Each with pretend decision models of several kinds: one that isn't answering, one that knows what
to press, one that's slow to wake or slow each time, one sure it's being played, one that only ever waits, one that
keeps saying Start. All in the game's own time (a minute and a half of play takes a second or two, and comes out the
same each time). Checked: it gets to the game in good time by itself, whatever the model says or doesn't; then plays
on by instinct (levels done, road driven) or by the model's moves; the game's never left paused; a pick that comes
too late for its screen isn't made, nor Start in the middle of the game; what it presses first on each console; and
what it writes in its log."""
import os
import sys

from paths import ROOT

sys.path.insert(0, ROOT)
from pitato import instincts as I   # noqa: E402
from pretend_games import PLAYS, FairLevel, Flow, always, flows, knows, play, silent   # noqa: E402

ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def said(r, words):
    return r["io"].said(words)


def first(r, *buttons):
    """The first of these buttons it pressed, and when."""
    return next(((b, t) for t, b in r["presses"] if b in buttons), (None, None))


# ---- what it presses first, on each console -------------------------------------------------------------------------
bases = {s: I.PressOn(s).base for s in ("nes", "snes", "gba", "genesis", "sms", "n64", "ps1", "neogeo", "ngpc")}
check(f"what it presses to get a game going: Start, then what picks things on that console ({bases['nes']}, "
      f"{bases['snes']}, a PlayStation {bases['ps1']}); a Master System has no Start ({bases['sms']}); an arcade game "
      f"gets a coin first ({bases['neogeo']})", bases["nes"] == bases["gba"] == ("start", "a")
      and bases["snes"] == bases["genesis"] == ("start", "a", "b") and bases["ps1"] == ("start", "b", "a")
      and bases["n64"] == ("start", "b") and bases["sms"] == ("b", "a", "start")
      and bases["neogeo"] == ("select", "start", "b") and bases["ngpc"] == ("start", "b", "a"))

# ---- every start, with no model answering, and with one that knows --------------------------------------------------
STARTS = flows()
#        the start: seconds it may take (the most), and how far it's to get in a minute and a half (no model, a model)
WANT = {"a title screen, then the level": (6, 5000, 5000),
        "a logo, then a title screen that's all movement": (8, 1200, 1200),
        "logos, a title screen, a file to pick, text": (20, 5000, 5000),
        "a racing game's menus": (24, 2500, 2500),
        "an RPG's long start": (60, 0, 400),
        "an arcade game: a coin first": (12, 1200, 1200),
        "a title screen only A starts": (10, 5000, 5000),
        "CONTINUE first, with nothing saved": (22, 5000, 5000),
        "a game it doesn't know, text first": (26, 0, 400)}
check("the starts tried are the ones known here", set(WANT) == set(STARTS))
tries = {}
for name, make in STARTS.items():
    most, far0, far1 = WANT[name]
    for who, model, far in (("no model answering", silent, far0), ("a model that knows", knows(), far1)):
        r = tries[name, who] = play(make, model, 90.0)
        got = "never" if r["secs"] is None else f"{r['secs']:.1f} s"
        check(f"{name}, {who}: in the game after {got} (at most {most}), {r['far']:.0f} on from there ({r['levels']} "
              f"levels done; at least {far}); paused {r['paused_longest']:.1f} s at the longest; "
              f"{r['wrong']} wrong turns in its menus", r["secs"] is not None and r["secs"] <= most
              and r["far"] >= far and r["paused_longest"] <= 5 and r["wrong"] <= 1)

r = tries["a title screen, then the level", "no model answering"]
check(f"with no model: its log says so, and what it pressed and what came of it "
      f"({[e['event'] for e in r['io'].logged][2:5]})", said(r, "isn't answering") and said(r, "Start pressed: ")
      and said(r, "the game's going"))
check(f"...a level's end (its tally, standing still) got through, on to the next ({r['levels']} levels done)",
      r["levels"] >= 2)


def start_only():
    return "Super Mario Bros. (World)", "nes", Flow(FairLevel(), [], system="nes", tally=("start",))


r = play(start_only, silent, 90.0)
check(f"...a level's end that only Start gets past (what it plays with doesn't): the screen standing dead, it "
      f"presses what picks things, then Start, and on it goes ({r['levels']} levels done; paused "
      f"{r['paused_longest']:.1f} s at the longest)", r["levels"] >= 1 and not r["game"].paused
      and r["paused_longest"] <= 4 and first(r, "start")[1] > 20
      and said(r, "Start pressed, as the game waited: on it goes"))
r = tries["an arcade game: a coin first", "no model answering"]
coin, start = first(r, "select"), first(r, "start")
check(f"an arcade game: the coin goes in before Start ({coin}, {start})", coin[0] == "select" and start[0] == "start"
      and coin[1] < start[1])
r = tries["a title screen only A starts", "no model answering"]
start, a = first(r, "start"), first(r, "a")
check(f"a title screen only A starts: Start tried, nothing came of it, then A ({start}, {a})", start[1] < a[1]
      and said(r, "Start pressed: nothing came of it"))
r = tries["CONTINUE first, with nothing saved", "no model answering"]
down = first(r, "down")
check(f"CONTINUE first, with nothing saved: what picks things brought nothing, so the cursor's moved (Down, at "
      f"{down[1]} s) and that's picked; no wrong turn ({r['wrong']})", down[0] == "down" and down[1] < r["secs"]
      and r["wrong"] == 0)
r = tries["an RPG's long start", "no model answering"]
taps = [t for t, b in r["presses"] if b == "a" and t < r["secs"]]
check(f"an RPG's long start: sixteen pages of text and a name to put in, by itself ({len(taps)} presses of A)",
      len(taps) >= 16)
r = tries["an RPG's long start", "a model that knows"]
moves = [q for q in r["io"].asked if q["kind"] == "move"]
late = [q for q in moves if q["at"] > r["secs"] + 5]
looks = r["io"].looks
check(f"...then it's the model's game, a move at a time ({len(late)} picks asked once it's going), and it's looked "
      f"at less often ({looks} looks in a minute and a half)", len(late) >= 8 and looks < 700)

# ---- models that are slow, sure of themselves, or no help -----------------------------------------------------------
r = play(STARTS["a title screen, then the level"], knows(wake=25.0), 90.0)
check(f"a model that takes 25 seconds to wake: the game's going long before ({r['secs']:.1f} s), and well on "
      f"({r['far']:.0f}); its first pick, for a screen that's gone by then, isn't made (paused "
      f"{r['paused_longest']:.1f} s at the longest)", r["secs"] <= 6 and r["far"] >= 5000 and r["paused_longest"] <= 4
      and said(r, "came for a screen that's gone: not made"))
for name, most, far in (("a racing game's menus", 32, 2000), ("CONTINUE first, with nothing saved", 28, 5000)):
    r = play(STARTS[name], knows(latency=6.0), 90.0)
    check(f"a model that takes 6 seconds a pick, {name}: in the game after {r['secs']:.1f} s (at most {most}), "
          f"{r['far']:.0f} on", r["secs"] is not None and r["secs"] <= most and r["far"] >= far
          and r["paused_longest"] <= 4)
for name, most, far in (("a title screen, then the level", 6, 5000),
                        ("a logo, then a title screen that's all movement", 16, 1200),
                        ("a racing game's menus", 24, 2500), ("CONTINUE first, with nothing saved", 22, 5000)):
    r = play(STARTS[name], always(PLAYS), 90.0)
    check(f"a model sure it's being played from the first screen, {name}: in the game after {r['secs']:.1f} s (at "
          f"most {most}), {r['far']:.0f} on; paused {r['paused_longest']:.1f} s at the longest",
          r["secs"] is not None and r["secs"] <= most and r["far"] >= far and r["paused_longest"] <= 4)
for name, most, far in (("a title screen, then the level", 6, 5000), ("a racing game's menus", 24, 2500),
                        ("an RPG's long start", 70, 0)):
    r = play(STARTS[name], always("wait"), 90.0)
    check(f"a model that only ever says wait, {name}: in the game after {r['secs']:.1f} s (at most {most}), "
          f"{r['far']:.0f} on: got going, and played, by itself", r["secs"] is not None and r["secs"] <= most
          and r["far"] >= far and r["paused_longest"] <= 4)
r = play(STARTS["a title screen, then the level"], always("start"), 90.0)
check(f"a model that keeps saying Start: in the game after {r['secs']:.1f} s, {r['far']:.0f} on; Start in the "
      f"middle of the game isn't pressed for it (it would only pause it): paused {r['paused_longest']:.1f} s at the "
      f"longest", r["secs"] <= 6 and r["far"] >= 5000 and r["paused_longest"] <= 6
      and said(r, "would only pause the game, as it's going: not made"))

# ---- a game that's paused when it's turned on -----------------------------------------------------------------------


def paused_level():
    game = Flow(FairLevel(), [], system="nes")
    game.paused = True
    return "Super Mario Bros. (World)", "nes", game


r = play(paused_level, silent, 40.0)
check(f"a game that's paused when it's turned on (and looks just the same): Start, then it walks a moment, the "
      f"screen moves, and it plays on ({r['far']:.0f} on; paused {r['paused']:.1f} s in all)",
      not r["game"].paused and r["paused"] <= 8 and r["far"] >= 2000 and r["player"].presser.sure)

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
