"""Watching another Pietato's game, end to end (pitato/netplay.py's watching; the emulator's watchhost and --watch): real
emulators (Genesis Plus GX, each with a pretend screen of its own) on this machine, as if on several. A tiny test game of
our own: blue, red while player 1 holds B, green while player 2 does, yellow for both (counting its rounds in its memory,
so two that aren't in step can tell). The host's game is opened to watch (with a key); a watcher takes it up as it is
and from then on runs it from the host's buttons alone: each B on the host shows on the watcher too, its own buttons do
nothing, and it keeps a few frames behind. A second one watches too; then a player 2 joins (playing together) and the
watchers see both players' buttons. The host's menu up: the watchers wait (and say why); the host's game changed (started
over): the watchers have it again, and stay in step. One with another copy of the game, or without the key: not let in.
The host leaving: the watchers' games end and say why. Nothing of the game's kept by the watchers."""
import os, shutil, sys, time
import numpy as np
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS); sys.path.insert(0, ROOT)
import pietato_all as g

S = SP + "/t_watch_game"
shutil.rmtree(S, ignore_errors=True)
H = S + "/home/u"
os.makedirs(H + "/Games/genesis")
os.makedirs(S + "/bin")
open(S + "/bin/aplay", "w").write('#!/bin/sh\nexec cat > /dev/null\n')
os.chmod(S + "/bin/aplay", 0o755)
os.environ["PATH"] = S + "/bin:" + os.environ["PATH"]
ROM = H + "/Games/genesis/Pitato Sega Count (World).md"
shutil.copy(SP + "/sega/Pitato Sega Count (World).md", ROM)
OTHER = H + "/Games/genesis/Pitato Sega Test (Other).md"   # (another copy of it: a byte at its end changed)
data = bytearray(open(ROM, "rb").read())
data[-1] ^= 0xFF
open(OTHER, "wb").write(bytes(data))
CORE = SP + "/sega/cores/genesis_plus_gx_libretro.so"
g.home_dir = lambda: H
W, HH = 640, 480
KEY = "k" * 22
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def start(name, watch="", net="", rom=ROM):
    """An emulator with a pretend screen of its own, and what it says on its errors kept (its log)."""
    fb = f"{S}/{name}.fb"
    open(fb, "wb").write(bytes(W * HH * 2))
    os.environ["PITATO_FB"] = f"{fb}:{W}x{HH}:16"
    log = open(f"{S}/{name}.log", "w")
    saved = os.dup(2)
    os.dup2(log.fileno(), 2)                           # (its errors into its log: the emulator's stderr is ours)
    try:
        run = g.GameRun({"path": rom, "title": "Pitato Sega Test", "system": "genesis"})
        run.start(CORE, sound="", volume=0, resume=False, cheevos=False, saves=f"{S}/{name}-saves", watch=watch,
                  net=net)
    finally:
        os.dup2(saved, 2)
        os.close(saved)
        log.close()
    run.fb, run.log = fb, f"{S}/{name}.log"
    return run


def colour(run):
    a = int(np.fromfile(run.fb, dtype="<u2").reshape(HH, W)[300, 320])
    r, gr, b = (((a >> 11) & 31) << 3, ((a >> 5) & 63) << 2, (a & 31) << 3)
    return {(True, False, False): "red", (False, True, False): "green", (False, False, True): "blue",
            (True, True, False): "yellow", (False, False, False): "black"}.get((r > 128, gr > 128, b > 128),
                                                                              str((r, gr, b)))


def until(cond, secs=6.0):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.03)
    return cond()


def all_of(runs, c, secs=6.0):
    """Each picture that colour (waited for): whether they are, and what they are."""
    ok = until(lambda: all(colour(r) == c for r in runs), secs)
    return ok, ", ".join(colour(r) for r in runs)


def news(run, what, secs=6.0, n=1):
    until(lambda: sum(1 for x in run.net_news if x[0] == what) >= n, secs)
    got = [x for x in run.net_news if x[0] == what]
    return got[n - 1] if len(got) >= n else None


def logged(run, words):
    try:
        return open(run.log).read().count(words)
    except OSError:
        return 0


host = start("host")
check("the host's game starts", host.wait_started(20))
what, rest = host.ask(f"watchhost 0 {KEY}", ("watchhost",), 5)
words = rest.split()
check(f"...opened to watch, with a key ({what} {rest})", what == "watchhost" and words[:1] == ["ok"]
      and len(words) > 1 and words[1].isdigit())
port = int(words[1])
SPEC = f"127.0.0.1:{port}:{KEY}"

# ---- not let in: another copy of the game, or without the key -----------------------------------------------------
wrong = start("other", watch=SPEC, rom=OTHER)
until(lambda: wrong.ended, 20)
check(f"another copy of the game: not let in, and it says why ({wrong.error})", wrong.ended
      and wrong.error == "Couldn't watch: its copy of the game isn't the same as this one's")
nokey = start("nokey", watch=f"127.0.0.1:{port}:{'x' * 22}")
until(lambda: nokey.ended, 20)
check(f"without the key: not let in ({nokey.error})", nokey.ended and nokey.error.startswith("Couldn't watch"))
check("...and the host plays on, watched by nobody", host.alive() and host.watchers == 0)

# ---- one watches ----------------------------------------------------------------------------------------------------
one = start("one", watch=SPEC)
check("one watches: its game starts, the host's as it is", one.wait_started(20) and one.state == "on")
check(f"...the host's told: one's come, one watching ({news(host, 'watchjoined')}, {news(host, 'watchers')})",
      news(host, "watchjoined") is not None and news(host, "watchers") == ("watchers", "1") and host.watchers == 1)
ok, now = all_of([host, one], "blue")
check(f"...both pictures: blue ({now})", ok)
t0 = time.monotonic()
host.press("b")
ok, now = all_of([host, one], "red")
lag = time.monotonic() - t0
check(f"the host's B: red on the host, and on the one watching ({now}, {lag:.2f} s)", ok and lag < 2)
host.release("b")
ok, now = all_of([host, one], "blue")
check(f"...let go: blue on both ({now})", ok)
one.press("b")
time.sleep(0.6)
check(f"the watcher's own B: nothing (the host's buttons alone play it: {colour(one)})", colour(one) == "blue"
      and colour(host) == "blue")
one.release("b")

# ---- another watches; a player 2 joins -------------------------------------------------------------------------------
two = start("two", watch=SPEC)
check("another watches too", two.wait_started(20) and news(host, "watchers", n=2) == ("watchers", "2"))
host.press("b")
ok, now = all_of([host, one, two], "red")
check(f"...the host's B: red on all three ({now})", ok)
host.release("b")
all_of([host, one, two], "blue")
what, rest = host.ask(f"nethost 0 {KEY} 127.0.0.1", ("nethost",), 5)
guest = start("guest", net=f"127.0.0.1:{rest.split()[1]}:{KEY}")
check("a player 2 joins (playing together)", guest.wait_started(20) and news(host, "netjoined") is not None)
ok, now = all_of([host, guest, one, two], "blue")
check(f"...all four pictures: blue ({now})", ok)
guest.press("b")
ok, now = all_of([host, guest, one, two], "green")
check(f"player 2's B: green on all four, the watchers too ({now})", ok)
host.press("b")
ok, now = all_of([host, guest, one, two], "yellow")
check(f"...and player 1's: yellow on all four ({now})", ok)
host.release("b")
guest.release("b")
ok, now = all_of([host, guest, one, two], "blue")
check(f"...both let go: blue on all four ({now})", ok)
time.sleep(4.5)                                        # (two checks of each game's memory, meanwhile)
check(f"...all in step all along ({logged(one, 'out of step')}, {logged(two, 'out of step')}, "
      f"{logged(guest, 'out of step')} out of step)", logged(one, "out of step") + logged(two, "out of step")
      + logged(guest, "out of step") == 0)
guest.quit()
check("player 2 leaves: the host plays on, still watched", news(host, "netleft") is not None and host.alive()
      and one.alive() and two.alive())

# ---- the host's menu up; its game changed --------------------------------------------------------------------------
before = np.fromfile(one.fb, dtype="<u2").copy()
check("the host's menu up (paused)", host.pause())
time.sleep(1.0)
after = np.fromfile(one.fb, dtype="<u2")
check(f"...the watchers wait, and say why ({int((after != before).sum())} pixels of a notice)",
      (after != before).sum() > 500 and colour(one) == "blue")
host.resume()
host.press("b")
ok, now = all_of([host, one, two], "red")
check(f"...back in the game: on all go ({now})", ok)
host.release("b")
all_of([host, one, two], "blue")
host.ask("reset", ("reset",), 3)                      # (its game started over: told to the watchers, as it is now)
time.sleep(0.5)
host.press("b")
ok, now = all_of([host, one, two], "red")
check(f"the host's game started over: the watchers have it again, in step ({now})", ok)
host.release("b")
all_of([host, one, two], "blue")
time.sleep(4.5)
check(f"...and stay in step ({logged(one, 'out of step')}, {logged(two, 'out of step')} out of step)",
      logged(one, "out of step") + logged(two, "out of step") == 0)

# ---- one stops watching; the host leaves ---------------------------------------------------------------------------
two.quit()
check(f"one stops watching: the host's told ({host.watchers} watching)", until(lambda: host.watchers == 1, 6))
host.quit()
check(f"the host leaves: the watcher's game ends, and it says why ({news(one, 'watchgone')})",
      until(lambda: one.ended, 10) and news(one, "watchgone") == ("watchgone", "it left"))
for run in (host, one, two, wrong, nokey):
    run.quit(3)
kept = [f for d in ("one-saves", "two-saves") for f in os.listdir(f"{S}/{d}")] if os.path.isdir(f"{S}/one-saves") else []
check(f"nothing of the game's kept by the ones that watched ({kept})", not kept)
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
