"""Watching another Pietato's game, its parts on their own (pitato/netplay.py's Watchers and WatchLink; the emulator's
watch_frame and watch_host_frame), over real connections on this machine but with no emulator: a watcher comes, says
hello (with the key, and the same emulator and game: or it isn't let in), waits for the game, and gets it with each
frame's buttons from then on, a few frames at a time, the checks, and pauses; one that asks for the game again too often,
or stops taking what's sent, is let go of; the host's game over, each is told. Then the emulator's side of it: a watcher
waits till it has a few frames in hand, plays the host's buttons, catches up when it's behind, takes the game again
when it's out of step (or far behind), and ends when the host's gone; the host sends the game to the ones that come (and
to all, when one's out of step or its game's changed), and each frame's buttons, with a check now and then."""
import socket, sys, time
from paths import ROOT, TESTS  # noqa: E402  (the Pietato folder; tests)
sys.path.insert(0, TESTS); sys.path.insert(0, ROOT)
import pietato_all as g  # noqa: F401  (Pietato's modules, as the other tests have them)
import pitato.netplay as N
import pitato.emulator as E

ok_all = []
KEY = "k" * 22
ABOUT = {"v": 1, "core": "Genesis Plus GX 1.7.4", "game": "a" * 40, "who": "tv", "key": ""}


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def until(cond, secs=5.0):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


def watcher(port, key=KEY, about=None):
    link = N.WatchLink(N.join("127.0.0.1", port))
    until(lambda: link.hello is not None or link.gone is not None)
    link.say_hello(dict(about or ABOUT, key=key))
    return link


# ---- the host's side and a watcher's, over a real connection ------------------------------------------------------
host = N.Watchers(0, KEY, dict(ABOUT, watch=True))
one = watcher(host.port)
check(f"a watcher comes: the host says hello first ({one.hello})", one.hello == dict(ABOUT, watch=True))
check("...with the key, the same emulator and game: it waits for the game", until(lambda: len(host.ready()) == 1))
nokey = watcher(host.port, key="x" * 22)
other = watcher(host.port, about=dict(ABOUT, game="b" * 40))
check(f"...without the key, or with another copy of the game: not let in ({nokey.gone}, {other.gone})",
      until(lambda: nokey.gone is not None and other.gone is not None) and len(host.ready()) == 1)
host.state(1000, b"STATE" * 100)
check("the game, as it is at a frame's start: to it", until(lambda: one.states[:1] == [(1000, b"STATE" * 100)])
      and host.ready() == [] and host.tidy() == 1 and host.news() == [("watchjoined", "tv")])
for f in range(1000, 1010):
    host.frame(f, f & 0xFF, 0x80)
check(f"...then each frame's buttons, both players', a few at a time ({one.ahead(1000)} in hand)",
      until(lambda: one.ahead(1000) == 8) and one.take(1000) == (0xE8, 0x80) and one.take(1007) == (0xEF, 0x80))
host.check(1010, 0xDEADBEEF)
host.frame(1010, 1, 2)
host.flush()
check("...a check now and then (the sum of the game at a frame)", until(lambda: one.ahead(1010) == 1)
      and one.their_sum(1010) == 0xDEADBEEF)
host.pause(True)
check("...the host's menu up: said", until(lambda: one.paused))
host.pause(False)
check("...and gone", until(lambda: not one.paused))
one.ask_again()
check("out of step, it asks for the game again: the host hears it (once)", until(lambda: host.asked_again())
      and not host.asked_again())
for _ in range(N.WATCH_AGAINS[0] + 1):
    one.ask_again()
check(f"...asking again and again: let go of ({host.news()})", until(lambda: host.tidy() == 0))
two = watcher(host.port)
until(lambda: len(host.ready()) == 1)
host.state(2000, b"x")
check("another comes, and has the game", until(lambda: two.states[:1] == [(2000, b"x")]))
two.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
was = N.WATCH_QUEUED
N.WATCH_QUEUED = 1 << 16
host.state(2001, b"y" * (1 << 20))                     # (a big game, to one that isn't taking it)
N.WATCH_QUEUED = was
check("...one that stops taking what's sent: let go of", until(lambda: host.tidy() == 0))
three = watcher(host.port)
until(lambda: len(host.ready()) == 1)
host.state(3000, b"z")
until(lambda: three.states[:1] == [(3000, b"z")])
host.close()
check(f"the host's game over: each one watching's told ({three.gone})", until(lambda: three.gone == "it left"))


# ---- the emulator: watching ---------------------------------------------------------------------------------------------
class Core:
    def __init__(self):
        self.buttons, self.ram, self.loaded, self.ports = [0, 0, 0, 0], b"same", [], set()

    def unserialize(self, data):
        self.loaded.append(data)
        self.ram = b"same"
        return True

    def serialize(self):
        return b"GAME"

    def read_memory(self, kind):
        return self.ram if kind == E.SYSTEM_RAM else b""

    def plug(self, port):
        self.ports.add(port)


class Screen:
    def __init__(self):
        self.said = []

    def notice(self, lines):
        self.said.append(lines)

    def notice_now(self):
        pass


class Link:
    """A pretend host, for a watcher: frames' buttons, sums, states, a pause, as the test says."""
    def __init__(self):
        self.frames, self.sums, self.states, self.asked = {}, {}, [], 0
        self.paused, self.gone, self.closed = False, None, False

    def ahead(self, frame):
        return max([f for f in self.frames], default=frame - 1) - frame + 1

    def take(self, frame):
        return self.frames.pop(frame, None)

    def state_due(self, frame, now=False):
        if self.states and (now or self.states[-1][0] <= frame):
            got, self.states = self.states[-1], []
            return got
        return None

    def their_sum(self, frame):
        return self.sums.pop(frame, None)

    def ask_again(self):
        self.asked += 1

    def close(self):
        self.closed = True


def session():
    s = E.Session.__new__(E.Session)
    s.core, s.screen, s.said = Core(), Screen(), []
    s.say = lambda *words: s.said.append(" ".join(str(w) for w in words))
    s.frame, s.quit, s.watch_who = 100, False, "tv"
    s.watch, s.watch_hold = Link(), True
    return s


s = session()
w = s.watch
for f in range(100, 105):
    w.frames[f] = (f, 0)
check("a watcher: not with fewer than a few frames in hand (it waits)", s.watch_frame() is False and s.frame == 100)
for f in range(105, 100 + N.WATCH_AHEAD):
    w.frames[f] = (f, 7)
got = s.watch_frame()
check(f"...a few in hand: the host's buttons for the frame, both players' ({s.core.buttons[:2]})",
      got is True and s.core.buttons[:2] == [100, 0])
for f in range(101, 100 + N.WATCH_AHEAD):
    s.frame = f
    s.watch_frame()
s.frame = 100 + N.WATCH_AHEAD
check("...run dry: it waits for a few in hand again", s.watch_frame() is False and s.watch_hold)
for f in range(s.frame, s.frame + N.WATCH_HURRY + 5):
    w.frames[f] = (1, 1)
check("...far behind the host: it catches up (frames not drawn, nor waited for)", s.watch_frame() == "hurry")
s = session()
w = s.watch
s.frame = N.NET_CHECK * 3
for f in range(s.frame, s.frame + 20):
    w.frames[f] = (0, 0)
w.sums[s.frame] = N.game_sum(b"different")
s.watch_hold = False
s.watch_frame()
check(f"out of step (its sum isn't the host's): it asks for the host's game again, once ({w.asked})",
      w.asked == 1 and s.watch_asked)
s.frame += 1
s.watch_frame()
check("...not again while it waits for it", w.asked == 1)
w.states.append((s.frame + 500, b"FRESH"))
for f in range(s.frame + 500, s.frame + 520):
    w.frames[f] = (3, 3)
s.watch_frame()
check(f"...the host's game come: taken up at once, from its frame ({s.frame})", s.core.loaded == [b"FRESH"]
      and s.frame == N.NET_CHECK * 3 + 501 and not s.watch_asked)
s = session()
w = s.watch
s.watch_hold = False
for f in range(100, 130):
    w.frames[f] = (0, 0)
w.states.append((110, b"LATER"))
s.watch_frame()
check("in step, a game the host's sent for a frame ahead (another came, say): not yet", s.core.loaded == [])
for s.frame in range(101, 110):
    s.watch_frame()
s.frame = 110
s.watch_frame()
check("...taken up as it gets to that frame (nothing missed)", s.core.loaded == [b"LATER"] and s.frame == 110)
w.frames = {f: (0, 0) for f in range(s.frame, s.frame + N.WATCH_FAR + 10)}
s.watch_frame()
check("far, far behind: the host's game again instead", w.asked == 1 and s.watch_asked)
w.paused = True
w.frames = {}
s.watch_frame()
check(f"the host's menu up, nothing in hand: it says why ({s.screen.said[-1:]})",
      s.screen.said[-1:] == [["Paused on tv"]])
w.gone = "it left"
check(f"the host gone: so's this game, and it says why ({s.said})", s.watch_frame() is False and s.quit
      and s.said == ["watchgone it left"] and w.closed)


# ---- the emulator: watched ----------------------------------------------------------------------------------------------
class Watched:
    def __init__(self, waiting=1):
        self.waiting, self.again, self.sent, self.checks, self.frames, self.n = waiting, False, [], [], [], 0

    def tidy(self):
        return self.n

    def news(self):
        return []

    def ready(self):
        return [object()] * self.waiting

    def asked_again(self):
        got, self.again = self.again, False
        return got

    def state(self, frame, data):
        self.sent.append((frame, data))
        self.n += self.waiting
        self.waiting = 0

    def check(self, frame, total):
        self.checks.append(frame)

    def frame(self, frame, b0, b1):
        self.frames.append((frame, b0, b1))


s = session()
s.watch, s.net, s.watch_count, s.watch_fresh = None, None, 0, False
s.watchers = Watched()
s.frame = N.NET_CHECK * 2
s.core.buttons = [5, 6, 0, 0]
s.watch_host_frame()
check(f"the host: one come, it has the game as it is (and the host takes it up too: {s.core.loaded}), said",
      s.watchers.sent == [(N.NET_CHECK * 2, b"GAME")] and s.core.loaded == [b"GAME"] and s.said == ["watchers 1"])
check("...a check at this frame, and its buttons, both players'", s.watchers.checks == [N.NET_CHECK * 2]
      and s.watchers.frames == [(N.NET_CHECK * 2, 5, 6)])
s.frame += 1
s.watchers.again = True
s.watch_host_frame()
check("...one out of step: the game to all of them again", len(s.watchers.sent) == 2)
s.frame += 1
s.watch_fresh = True                                   # (a state loaded, or started over)
s.watch_host_frame()
check("...its game changed: to all of them again", len(s.watchers.sent) == 3 and not s.watch_fresh)
s.frame += 1
s.watch_host_frame()
check("...otherwise just the buttons", len(s.watchers.sent) == 3 and len(s.watchers.frames) == 4)
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
