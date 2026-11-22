"""The Soundboard's beat, shared (Apps > Soundboard: screens/soundboard.py). Your Pietatos that have their Soundboard
open keep one tempo and one count of beats between them, so a loop on one keeps time with a loop on another. Each says,
once a second and at once when it changes, what its beat is to each of your others (Settings > Share with other
Pietatos: the ones heard lately), on BEAT_PORT; and sets its clock against each of theirs (a few pings now and then,
the quickest answer the nearest: NTP's way), so what another says of its beat, by its own clock, is known by this one's.
On its own, it's a beat of its own, as ever; one that joins or leaves changes nothing for the others.

Which beat wins: the one changed (a new tempo) more times; of two changed as often, the one set first (a Soundboard
just opened takes the beat of the ones playing already); of two set at once, the one whose Pietato's word for itself
comes first. The Pietato that set a beat goes on saying it: the others keep theirs in step with what it says."""
import collections
import json
import select
import socket
import threading
import time

BEAT_PORT = 5450                 # where each says its beat, and answers pings (UDP)
BEAT_HOST = ""                   # ...at every address of this Pi's (the tests' Pietatos share a machine: each at its
                                 # own)
SAY_EVERY = 1.0                  # seconds between saying its beat to each of the others
PING_EVERY = 10.0                # seconds between rounds of pings to another's clock
PING_AGAIN = 1.0                 # ...while none's been answered yet (its Soundboard isn't open, or it hasn't heard of
                                 # this one yet)
PINGS = 6                        # pings a round (one a look, the quickest answer kept)
PINGS_KEPT = 18                  # ...answers kept, of the rounds lately
PING_LOST = 1.0                  # seconds before a ping that's had no answer is forgotten
GONE = 5.0                       # seconds without a word from another: it's gone (or its Soundboard has closed)
SAME_SET = 0.05                  # seconds apart two beats can be set and be said to be set at once
IN_STEP = 0.002                  # beats out of step with the one that set it before this one's put right
KIND = "pietato-beat"


class Clock:
    """A beat: its tempo, and beat b0 heard at t0 (this machine's time.monotonic()): which beat's heard when follows.
    rev: how many times it's been changed by hand; set: when it was set (this machine's clock); who: the Pietato that
    set it (its word for itself)."""
    __slots__ = ("bpm", "b0", "t0", "rev", "set", "who")

    def __init__(self, bpm, b0, t0, rev=0, set_at=None, who=""):
        self.bpm, self.b0, self.t0 = float(bpm), float(b0), float(t0)
        self.rev, self.set, self.who = int(rev), float(t0 if set_at is None else set_at), str(who)

    @classmethod
    def new(cls, bpm, now, who=""):
        return cls(bpm, 0.0, now, 0, now, who)

    def beat(self, now):
        return self.b0 + (now - self.t0) * self.bpm / 60.0

    def at(self, beat):
        return self.t0 + (beat - self.b0) * 60.0 / self.bpm

    def retimed(self, bpm, now, who=None):
        """A new tempo from the beat it's at: changed once more."""
        return Clock(bpm, self.beat(now), now, self.rev + 1, now, self.who if who is None else who)

    def fresh(self, now, who):
        """The same beat, as if just set here (a Soundboard opened again: the ones playing already win)."""
        return Clock(self.bpm, self.beat(now), now, 0, now, who)

    def same(self, other):
        return other is not None and self.rev == other.rev and self.who == other.who

    def wins(self, other):
        """This beat over that one (see above)."""
        if other is None:
            return True
        if self.rev != other.rev:
            return self.rev > other.rev
        if abs(self.set - other.set) > SAME_SET:
            return self.set < other.set
        return self.who < other.who

    def said(self):
        return {"bpm": self.bpm, "b0": self.b0, "t0": self.t0, "rev": self.rev, "set": self.set, "who": self.who}

    @classmethod
    def heard(cls, m, off):
        """Another's beat, as it said it by its own clock, by this one's (off: its clock less this one's). None: it
        isn't one."""
        try:
            c = cls(m["bpm"], m["b0"], float(m["t0"]) - off, int(m["rev"]), float(m["set"]) - off, m["who"])
        except (KeyError, TypeError, ValueError):
            return None
        if not (20 <= c.bpm <= 300) or not isinstance(m["who"], str) or len(c.who) > 64 or c.rev < 0:
            return None
        if not all(v == v and abs(v) < 1e12 for v in (c.b0, c.t0, c.set)):
            return None
        return c


class Peer:
    __slots__ = ("pongs", "sent", "round_at", "left", "seen", "who")

    def __init__(self):
        self.pongs = collections.deque(maxlen=PINGS_KEPT)   # (round trip, its clock less this one's)
        self.sent = {}                 # pings sent and not answered yet: their time -> sent at
        self.round_at = 0.0            # when its next round of pings starts
        self.left = 0                  # ...pings left in this round
        self.seen = None               # when it last said anything
        self.who = ""

    def off(self):
        """Its clock less this one's (from the quickest answer), or None: not known yet."""
        return min(self.pongs)[1] if self.pongs else None


class Link:
    """This Pietato's end of the shared beat: a UDP socket of its own while the Soundboard's open, and a thread of its
    own that answers pings the moment they come (and notes when answers come), so each clock's set against the
    others' to a millisecond or so, however busy media mode is. What else comes waits for media mode's next look."""

    def __init__(self, who, host="", port=BEAT_PORT, clock=time.monotonic):
        self.who, self.port, self.clock = who, port, clock
        self.peers = {}                # address -> Peer
        self.say_at = 0.0
        self.said = []                 # others' beats as they came: (address, what it said, when)
        self.lock = threading.Lock()
        self.alive = True
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind((host, port))
        except OSError:
            self.sock.close()
            raise
        threading.Thread(target=self.listen, daemon=True, name="beatlink").start()

    def close(self):
        self.alive = False
        try:
            self.sock.close()
        except OSError:
            pass

    def send(self, addr, m):
        m["k"] = KIND
        try:
            self.sock.sendto(json.dumps(m, separators=(",", ":")).encode(), (addr, self.port))
        except OSError:
            pass                       # (its Soundboard isn't open, or it's gone: it'll say so by saying nothing)

    def listen(self):
        """(A thread of its own.) What comes: a ping answered at once, with when it came; an answer to one, the time
        it took and the other's clock against this one's noted; a beat, kept for media mode's next look."""
        while self.alive:
            try:
                ready, _, _ = select.select([self.sock], [], [], 0.5)
                if not ready:
                    continue
                data, (addr, _) = self.sock.recvfrom(2048)
            except (BlockingIOError, InterruptedError):
                continue
            except (OSError, ValueError):
                return                                 # (closed)
            got = self.clock()
            with self.lock:
                p = self.peers.get(addr)
            if p is None:
                continue                               # (not one of yours)
            try:
                m = json.loads(data)
            except ValueError:
                continue
            if not isinstance(m, dict) or m.get("k") != KIND:
                continue
            if "ping" in m:
                self.send(addr, {"pong": m["ping"], "at": got})
            elif "pong" in m:
                at = m.get("at")
                with self.lock:
                    sent = p.sent.pop(m["pong"], None) if isinstance(m["pong"], float) else None
                    if sent is not None and isinstance(at, (int, float)) and not isinstance(at, bool):
                        p.pongs.append((got - sent, at - (sent + got) / 2))
            elif "bpm" in m:
                with self.lock:
                    self.said.append((addr, m, got))
                    del self.said[:-64]

    def say_now(self):
        self.say_at = 0.0

    def with_whom(self, now):
        """The others whose beat is this one's (their Soundboards open, heard lately): [their addresses]."""
        with self.lock:
            return sorted(a for a, p in self.peers.items() if p.seen is not None and now - p.seen < GONE)

    def tick(self, clock, addrs):
        """Each look (a few a second): what the others have said, pings sent, this one's beat said. addrs: your
        others' addresses (no others: none, and nothing's said). The beat as it is now: another's, if theirs wins (or
        this one's, kept in step with the one that set it), else the one given."""
        now = self.clock()
        addrs = set(addrs)
        with self.lock:
            for addr in [a for a in self.peers if a not in addrs]:
                del self.peers[addr]
            for addr in addrs:
                if addr not in self.peers:
                    self.peers[addr] = Peer()
            said, self.said = self.said, []
            offs = {addr: p.off() for addr, p in self.peers.items()}
        for addr, m, got in said:
            p = self.peers.get(addr)
            if p is None:
                continue
            p.seen, p.who = got, str(m.get("me") or "")[:64]
            theirs = Clock.heard(m, offs[addr]) if offs.get(addr) is not None else None
            if theirs is None:
                continue
            if theirs.wins(clock) and not theirs.same(clock):
                clock = theirs
            elif (theirs.same(clock) and m.get("me") == clock.who and m.get("me") != self.who
                    and abs(theirs.beat(now) - clock.beat(now)) > IN_STEP):
                clock = theirs                         # (the one that set it says where it is: in step with it)
        for addr, p in self.peers.items():             # its clock against each of theirs, now and then
            with self.lock:
                for t in [t for t, at in p.sent.items() if now - at > PING_LOST]:
                    del p.sent[t]
            if now >= p.round_at:
                p.round_at, p.left = now + (PING_EVERY if p.pongs else PING_AGAIN), PINGS
            if p.left:
                p.left -= 1
                t = self.clock()
                with self.lock:
                    p.sent[t] = t
                self.send(addr, {"ping": t})
        if now >= self.say_at and self.peers:
            self.say_at = now + SAY_EVERY
            said = dict(clock.said(), me=self.who)
            for addr in self.peers:
                self.send(addr, dict(said))
        return clock
