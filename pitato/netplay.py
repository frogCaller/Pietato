"""Two players on two Pietatos, one game: the emulators keep in step, frame by frame (lockstep). One (the host, player 1)
is already playing; the other (player 2) joins it over your network, starts from the host's game as it is at that
moment (its save state), and from then on each frame runs on both only once both players' buttons for it are there.
Each sends its buttons a few frames ahead (the delay), so on your network neither waits. The same start and the same
buttons make the same game on both; now and then they check (a sum of the game's own memory), and one that's got out
of step takes the host's state again. Pausing on one pauses both; one leaving says so to the other.

Watching: any number of your other Pietatos run the game along with the one playing it, on their own screens, sharp, with
no video sent: the host's game as it is once (its state), then both players' buttons for each frame, a few frames at a
time (a kilobyte or so a second, however many are watching). A watcher plays them a few frames behind, so a slow moment
on your network doesn't show; the same checks keep it in step (out of step: the host's game again, for all of them).

A message: its kind (a byte), its length (4 bytes), then what it says. pitato/emulator.py runs it (--net, nethost; --watch,
watchhost)."""
import collections
import json
import socket
import struct
import sys
import threading
import time
import zlib

NET_PORT = 5442              # the host's game listens for the other one here
NET_DELAY = 3                # frames each side's buttons are sent ahead (50 ms: your network's well within that)
NET_WAIT = 6.0               # seconds without the other's buttons before it's taken to have gone
NET_CHECK = 120              # frames between checks that both games are the same (every two seconds)
NET_KEEP = 900               # frames of buttons kept (to play again from a state taken a moment ago)
NET_STATE_MOST = 64 << 20    # bytes: a game's state, at most
NET_HELLO_WAIT = 10.0        # seconds the two have to say hello
WATCH_PORT = 5444            # a game's watchers join it here (any number of them)
WATCH_BATCH = 4              # frames of both players' buttons sent to the watchers at a time
WATCH_AHEAD = 8              # frames a watcher has in hand before it plays them (a slow moment on the network: unseen)
WATCH_HURRY = 40             # ...and more than this: it's fallen behind, and catches up (frames not drawn)
WATCH_FAR = 900              # ...and more than this: it takes the host's game as it is now instead
WATCH_MOST = 8               # watchers at once, at most
WATCH_QUEUED = 8 << 20       # bytes waiting to go to a watcher, at most (one that's stopped taking them is let go)
WATCH_AGAINS = (5, 60.0)     # times a watcher may ask for the game again in so many seconds (more: it's let go)
HEADER = struct.Struct(">cI")
MSG_HELLO, MSG_STATE, MSG_BUTTONS, MSG_CHECK = b"H", b"S", b"I", b"C"   # (a message's kind)
MSG_AGAIN, MSG_PAUSE, MSG_RESUME, MSG_BYE = b"X", b"P", b"R", b"B"
MSG_FRAMES = b"F"            # (watching: frames' buttons, both players', from the first one's number on)
FRAME = struct.Struct(">HH")


class Gone(Exception):
    """The other Pietato's game has gone (it said so, or it stopped answering)."""


def game_sum(data):
    """A sum of a game's state, to tell whether two are the same."""
    return zlib.crc32(data) & 0xFFFFFFFF if data else 0


class Link:
    """This game's side of two keeping in step: what it sends, and what the other has sent (read on a thread of its
    own as it comes)."""

    def __init__(self, sock, host, delay=NET_DELAY):
        self.sock = sock
        self.host = host                              # player 1 (its game is the one they play), or player 2
        self.delay = delay
        self.sock.settimeout(None)
        try:
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        self.cond = threading.Condition()
        self.mine, self.theirs = {}, {}               # frame -> buttons (this one's, the other's)
        self.sums = {}                                # frame -> the other's sum of its game then
        self.states = []                              # (frame, state) the host's sent (to start from, or again)
        self.again = None                             # (the host) the frame the other asked to start again from
        self.paused = False                           # the other's menu is up
        self.start = 0                                # the frame the two started together at
        self.gone = None                              # why the other's gone (None: it's there)
        self.hello = None                             # what the other said it is
        self.sending = threading.Lock()
        self.reader = threading.Thread(target=self.read, daemon=True, name="netplay")
        self.reader.start()

    # -- sending ------------------------------------------------------------------------------------------------
    def send(self, kind, data=b""):
        try:
            with self.sending:
                self.sock.sendall(HEADER.pack(kind, len(data)) + data)
            return True
        except OSError as ex:
            self.lost(f"it stopped answering ({ex.strerror or ex})")
            return False

    def say_hello(self, about):
        self.send(MSG_HELLO, json.dumps(about).encode())

    def send_state(self, frame, data):
        self.send(MSG_STATE, struct.pack(">I", frame) + data)

    def send_sum(self, frame, total):
        self.send(MSG_CHECK, struct.pack(">II", frame, total))

    def ask_again(self, frame):
        self.send(MSG_AGAIN, struct.pack(">I", frame))

    def pause(self, on):
        self.send(MSG_PAUSE if on else MSG_RESUME)

    def bye(self):
        self.send(MSG_BYE)
        self.close()

    # -- reading ------------------------------------------------------------------------------------------------
    def read_exactly(self, n):
        out = bytearray()
        while len(out) < n:
            chunk = self.sock.recv(min(1 << 20, n - len(out)))
            if not chunk:
                raise Gone("it's gone")
            out += chunk
        return bytes(out)

    def read(self):
        try:
            while True:
                kind, n = HEADER.unpack(self.read_exactly(HEADER.size))
                if n > NET_STATE_MOST + 16:
                    raise Gone("it said something too big")
                data = self.read_exactly(n)
                with self.cond:
                    if kind == MSG_BUTTONS and n == 8:
                        frame, held = struct.unpack(">II", data)
                        self.theirs[frame] = held
                    elif kind == MSG_HELLO:
                        self.hello = json.loads(data.decode())
                    elif kind == MSG_STATE and n >= 4:
                        self.states.append((struct.unpack(">I", data[:4])[0], data[4:]))
                    elif kind == MSG_CHECK and n == 8:
                        frame, total = struct.unpack(">II", data)
                        self.sums[frame] = total
                    elif kind == MSG_AGAIN and n == 4:
                        self.again = struct.unpack(">I", data)[0]
                    elif kind == MSG_PAUSE:
                        self.paused = True
                    elif kind == MSG_RESUME:
                        self.paused = False
                    elif kind == MSG_BYE:
                        raise Gone("it left")
                    self.cond.notify_all()
        except (Gone, OSError, ValueError, struct.error) as ex:
            self.lost(str(ex) if isinstance(ex, Gone) else "it stopped answering")

    def lost(self, why):
        with self.cond:
            if self.gone is None:
                self.gone = why
            self.cond.notify_all()

    def wait_for(self, what, timeout):
        """Waits (up to timeout seconds) till what() is true; it's what() then. Gone, if the other's gone."""
        end = time.monotonic() + timeout
        with self.cond:
            while True:
                got = what()
                if got or self.gone is not None:
                    break
                left = end - time.monotonic()
                if left <= 0:
                    break
                self.cond.wait(left)
            if not got and self.gone is not None:
                raise Gone(self.gone)
            return got

    def other(self, timeout=NET_HELLO_WAIT):
        """What the other said it is (its hello)."""
        got = self.wait_for(lambda: self.hello, timeout)
        if not got:
            raise Gone("it didn't say hello")
        return got

    def first_state(self, timeout=NET_HELLO_WAIT):
        """(the frame, the state) the host's game was at as this one joined it."""
        got = self.wait_for(lambda: self.states[:1], timeout)
        if not got:
            raise Gone("its game didn't come")
        with self.cond:
            return self.states.pop(0)

    def new_state(self):
        """A state the host's sent again (the two had got out of step): (frame, state), or None."""
        with self.cond:
            return self.states.pop(0) if self.states else None

    def asked_again(self):
        with self.cond:
            frame, self.again = self.again, None
            return frame

    # -- a frame ------------------------------------------------------------------------------------------------
    def begin(self, frame):
        """The two start together at this frame (nobody's pressed anything for the first few)."""
        self.start = frame

    def fill(self, frame, held):
        """This one's buttons for the frames from this one on that it hasn't sent yet (it's jumped ahead, to the
        host's state), so the other isn't left waiting for them."""
        for f in range(frame, frame + self.delay + 1):
            if f not in self.mine:
                self.mine[f] = held
                self.send(MSG_BUTTONS, struct.pack(">II", f, held))

    def buttons(self, frame, held, timeout=NET_WAIT):
        """This frame's buttons for both: this one's (held now) go to the other for frame + delay, and the other's
        for this frame are waited for. (player 1's, player 2's). Gone if the other's gone (at once, even with its
        buttons for the next few frames here) or never sent them. None: the other's menu is up (no frame now)."""
        with self.cond:
            if self.gone is not None:
                raise Gone(self.gone)
        ahead = frame + self.delay
        if ahead not in self.mine:
            self.mine[ahead] = held
            self.send(MSG_BUTTONS, struct.pack(">II", ahead, held))
        with self.cond:
            if self.paused:
                return None                             # (its menu's up: both wait, at once)
        if frame < self.start + self.delay:            # (the first few: nobody's pressed anything yet)
            theirs, mine = 0, 0
        else:
            got = self.wait_for(lambda: frame in self.theirs or self.paused, timeout)
            if not got:
                raise Gone("it stopped answering")
            with self.cond:
                if frame not in self.theirs:
                    return None                         # (paused there)
                theirs = self.theirs[frame]
            mine = self.mine.get(frame, 0)
        if frame % 64 == 0:                            # (the old ones go)
            for d in (self.mine, self.theirs):
                for f in [f for f in d if f < frame - NET_KEEP]:
                    del d[f]
        return (mine, theirs) if self.host else (theirs, mine)

    def their_sum(self, frame):
        with self.cond:
            return self.sums.pop(frame, None)

    def close(self):
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


class Listener:
    """The host's game, waiting for the other to join (polled between frames: it never holds a frame up)."""

    def __init__(self, port, key, allow=None):
        self.key, self.allow = key, allow
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("", port))
        self.sock.listen(1)
        self.sock.setblocking(False)
        self.port = self.sock.getsockname()[1]

    def take(self):
        """The other's connection, once it's come (from the address allowed, if one's said), or None."""
        try:
            conn, addr = self.sock.accept()
        except (BlockingIOError, OSError):
            return None
        if self.allow and addr[0] != self.allow:
            conn.close()
            return None
        conn.setblocking(True)
        return conn

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def join(addr, port, timeout=NET_HELLO_WAIT):
    """The host's game, joined: the connection."""
    return socket.create_connection((addr, port), timeout=timeout)


# ---- watching -------------------------------------------------------------------------------------------------------
def message(kind, data=b""):
    return HEADER.pack(kind, len(data)) + data


def read_message(sock, most=NET_STATE_MOST + 16):
    """One message from sock: (its kind, what it says). Gone when the other end's gone."""
    head = read_exactly(sock, HEADER.size)
    kind, n = HEADER.unpack(head)
    if n > most:
        raise Gone("it said something too big")
    return kind, read_exactly(sock, n)


def keep_alive(sock):
    """A connection that's quietly gone (the other Pi switched off, its WiFi down) found out in seconds, not minutes:
    asked after when nothing's come for a while, and given up on when what's sent isn't taken."""
    for level, opt, value in ((socket.SOL_SOCKET, "SO_KEEPALIVE", 1), (socket.IPPROTO_TCP, "TCP_KEEPIDLE", 10),
                              (socket.IPPROTO_TCP, "TCP_KEEPINTVL", 5), (socket.IPPROTO_TCP, "TCP_KEEPCNT", 3),
                              (socket.IPPROTO_TCP, "TCP_USER_TIMEOUT", 20000)):
        try:
            sock.setsockopt(level, getattr(socket, opt), value)
        except (AttributeError, OSError):
            pass


def read_exactly(sock, n):
    out = bytearray()
    while len(out) < n:
        chunk = sock.recv(min(1 << 20, n - len(out)))
        if not chunk:
            raise Gone("it's gone")
        out += chunk
    return bytes(out)


class Watcher:
    """One of your Pietatos watching this game (the host's side): what goes to it goes on a thread of its own, so a slow
    one never holds a frame up; and what it asks (the game again: it's out of step) is read on another."""

    def __init__(self, sock, who):
        self.sock, self.who = sock, who
        self.cond = threading.Condition()
        self.out, self.queued = collections.deque(), 0
        self.live = False                             # it has the game: the frames go to it
        self.again = False                            # it's asked for the game again (out of step)
        self.agains = []                              # ...when (one that keeps asking is let go)
        self.gone = None                              # why it's gone (None: it's there)
        threading.Thread(target=self.write, daemon=True, name="watcher-out").start()
        threading.Thread(target=self.read, daemon=True, name="watcher-in").start()

    def send(self, data):
        with self.cond:
            if self.gone is not None:
                return
            if self.queued + len(data) > WATCH_QUEUED:
                self.lost("it stopped taking the game")
                return
            self.out.append(data)
            self.queued += len(data)
            self.cond.notify_all()

    def write(self):
        while True:
            with self.cond:
                while not self.out and self.gone is None:
                    self.cond.wait()
                if self.gone is not None and not self.out:
                    break
                data = self.out.popleft()
                self.queued -= len(data)
            try:
                self.sock.sendall(data)
            except OSError:
                self.lost("it stopped answering")
                break
        self.close()

    def read(self):
        try:
            while True:
                kind, data = read_message(self.sock, 64)
                if kind == MSG_AGAIN:
                    now = time.monotonic()
                    with self.cond:
                        self.agains = [t for t in self.agains if now - t < WATCH_AGAINS[1]] + [now]
                        if len(self.agains) > WATCH_AGAINS[0]:
                            raise Gone("it keeps getting out of step")
                        self.again = True
                elif kind == MSG_BYE:
                    raise Gone("it stopped watching")
        except (Gone, OSError, ValueError, struct.error) as ex:
            self.lost(str(ex) if isinstance(ex, Gone) else "it stopped answering")

    def lost(self, why, drop=True):
        """It's gone (why). drop: what's waiting for it isn't sent, and the connection's closed now (so nothing's left
        waiting on it)."""
        with self.cond:
            if self.gone is None:
                self.gone = why
            if drop:
                self.out.clear()
                self.queued = 0
            self.cond.notify_all()
        if drop:
            self.close()

    def bye(self):
        """This game's over (or not watched any more): it's told, once what's waiting has gone."""
        self.send(message(MSG_BYE))
        self.lost("the game ended", drop=False)

    def close(self):
        for how in (lambda: self.sock.shutdown(socket.SHUT_RDWR), self.sock.close):
            try:
                how()
            except OSError:
                pass


class Watchers:
    """The host's game, watched (polled between frames: nothing here ever holds a frame up). New ones come in on a
    thread of their own: each says hello (it's one of yours: the key; the same emulator and game), then waits for the
    game, which the host sends at the start of a frame (ready). Then each frame's buttons go to all of them, a few frames
    at a time, and now and then a sum of the game (the frame's), to check by."""

    def __init__(self, port, key, about):
        self.key, self.about = key, about
        self.lock = threading.Lock()
        self.all, self.waiting = [], []               # watchers: the ones with the game; the ones waiting for it
        self.batch, self.first = [], None             # buttons not sent yet, and the frame they start at
        self.said = []                                # (watcher, why) come or gone, for media mode
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("", port))
        self.sock.listen(WATCH_MOST)
        self.port = self.sock.getsockname()[1]
        self.closed = False
        threading.Thread(target=self.accept, daemon=True, name="watchers").start()

    def accept(self):
        while not self.closed:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                if self.closed:
                    break
                time.sleep(0.2)
                continue
            threading.Thread(target=self.welcome, args=(conn,), daemon=True, name="watcher-hello").start()

    def welcome(self, conn):
        """A new one: it says it's one of yours, with the same emulator and game; then it waits for the game."""
        try:
            conn.settimeout(NET_HELLO_WAIT)
            try:
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass
            keep_alive(conn)
            conn.sendall(message(MSG_HELLO, json.dumps(self.about).encode()))
            kind, data = read_message(conn, 4096)
            other = json.loads(data.decode()) if kind == MSG_HELLO else {}
            if not isinstance(other, dict) or other.get("key") != self.key:
                raise Gone("it didn't give the key")
            if other.get("core") != self.about.get("core") or other.get("game") != self.about.get("game"):
                raise Gone("its emulator or its game isn't the same")
            with self.lock:
                if self.closed or len(self.all) + len(self.waiting) >= WATCH_MOST:
                    raise Gone("too many watching")
                conn.settimeout(None)
                w = Watcher(conn, str(other.get("who") or "")[:40])
                self.waiting.append(w)
        except (Gone, OSError, ValueError, struct.error) as ex:
            print(f"game: one didn't start watching ({ex})", file=sys.stderr, flush=True)
            try:
                conn.close()
            except OSError:
                pass

    def ready(self):
        """Watchers waiting for the game (it goes to them at the start of this frame), or []."""
        with self.lock:
            return list(self.waiting)

    def asked_again(self):
        """One out of step has asked for the game again (it goes to all of them, then)."""
        with self.lock:
            out = False
            for w in self.all:
                with w.cond:
                    if w.again:
                        w.again, out = False, True
            return out

    def state(self, frame, data):
        """The game as it is at the start of this frame, to every watcher (the ones waiting for it, and the ones with it:
        it's what the host's game is now, to the last detail)."""
        self.flush()
        msg = message(MSG_STATE, struct.pack(">I", frame) + data)
        with self.lock:
            for w in self.waiting:
                w.live = True
                self.all.append(w)
                self.said.append(("watchjoined", w.who))
            self.waiting = []
            for w in self.all:
                w.send(msg)

    def frame(self, frame, b0, b1):
        """This frame's buttons (both players'), on their way with the next few."""
        if self.first is None or frame != self.first + len(self.batch):
            self.flush()
            self.first = frame
        self.batch.append(FRAME.pack(b0 & 0xFFFF, b1 & 0xFFFF))
        if len(self.batch) >= WATCH_BATCH:
            self.flush()

    def flush(self):
        if self.batch:
            self.send_all(message(MSG_FRAMES, struct.pack(">I", self.first) + b"".join(self.batch)))
        self.batch, self.first = [], None

    def check(self, frame, total):
        self.flush()
        self.send_all(message(MSG_CHECK, struct.pack(">II", frame, total)))

    def pause(self, on):
        self.flush()
        self.send_all(message(MSG_PAUSE if on else MSG_RESUME))

    def send_all(self, data):
        with self.lock:
            for w in self.all:
                w.send(data)

    def tidy(self):
        """The ones that have gone, let go (said, for media mode). How many are watching."""
        with self.lock:
            for w in [w for w in self.all + self.waiting if w.gone is not None]:
                (self.all if w in self.all else self.waiting).remove(w)
                self.said.append(("watchleft", w.who))
            return len(self.all)

    def news(self):
        with self.lock:
            out, self.said = self.said, []
            return out

    def close(self):
        """Not watched any more (the game's over): each told."""
        self.closed = True
        self.flush()
        try:
            self.sock.close()
        except OSError:
            pass
        with self.lock:
            for w in self.all + self.waiting:
                w.bye()
            self.all, self.waiting = [], []


class WatchLink:
    """Watching another's game (the watcher's side): what it sends, read on a thread of its own as it comes."""

    def __init__(self, sock):
        self.sock = sock
        self.sock.settimeout(None)
        try:
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        keep_alive(self.sock)                         # (the host's Pi switched off while its menu's up: found out)
        self.cond = threading.Condition()
        self.frames = {}                              # frame -> (player 1's buttons, player 2's)
        self.last = -1                                # the latest frame whose buttons have come
        self.sums = {}                                # frame -> the host's sum of its game then
        self.states = []                              # (frame, state) the host's sent
        self.paused = False                           # its menu is up
        self.hello = None
        self.gone = None
        threading.Thread(target=self.read, daemon=True, name="watching").start()

    def read(self):
        try:
            while True:
                kind, data = read_message(self.sock)
                with self.cond:
                    if kind == MSG_FRAMES and len(data) >= 4 and (len(data) - 4) % FRAME.size == 0:
                        first = struct.unpack(">I", data[:4])[0]
                        for k in range((len(data) - 4) // FRAME.size):
                            self.frames[first + k] = FRAME.unpack_from(data, 4 + k * FRAME.size)
                        self.last = max(self.last, first + (len(data) - 4) // FRAME.size - 1)
                    elif kind == MSG_STATE and len(data) >= 4:
                        self.states.append((struct.unpack(">I", data[:4])[0], data[4:]))
                        self.states = self.states[-2:]        # (the newest two, at most: an older one's no use)
                    elif kind == MSG_CHECK and len(data) == 8:
                        frame, total = struct.unpack(">II", data)
                        self.sums[frame] = total
                    elif kind == MSG_HELLO:
                        self.hello = json.loads(data.decode())
                    elif kind == MSG_PAUSE:
                        self.paused = True
                    elif kind == MSG_RESUME:
                        self.paused = False
                    elif kind == MSG_BYE:
                        raise Gone("it left")
                    self.cond.notify_all()
        except (Gone, OSError, ValueError, struct.error) as ex:
            with self.cond:
                if self.gone is None:
                    self.gone = str(ex) if isinstance(ex, Gone) else "it stopped answering"
                self.cond.notify_all()

    def wait_for(self, what, timeout):
        end = time.monotonic() + timeout
        with self.cond:
            while True:
                got = what()
                if got or self.gone is not None:
                    break
                left = end - time.monotonic()
                if left <= 0:
                    break
                self.cond.wait(left)
            if not got and self.gone is not None:
                raise Gone(self.gone)
            return got

    def say_hello(self, about):
        self.send(MSG_HELLO, json.dumps(about).encode())

    def send(self, kind, data=b""):
        try:
            self.sock.sendall(message(kind, data))
            return True
        except OSError:
            return False

    def ask_again(self):
        self.send(MSG_AGAIN)

    def take(self, frame):
        """This frame's buttons (player 1's, player 2's), and the ones before it let go; None: not here yet."""
        with self.cond:
            got = self.frames.pop(frame, None)
            if frame % 64 == 0:
                for f in [f for f in self.frames if f < frame]:
                    del self.frames[f]
                for f in [f for f in self.sums if f < frame - 10 * NET_CHECK]:
                    del self.sums[f]
            return got

    def ahead(self, frame):
        """Frames whose buttons are here, from this one on."""
        with self.cond:
            return self.last - frame + 1

    def state_due(self, frame, now=False):
        """The newest state the host's sent, if it's for this frame or one before it (or now: whatever its frame):
        (frame, state), or None."""
        with self.cond:
            if self.states and (now or self.states[-1][0] <= frame):
                got = self.states[-1]
                self.states = []
                return got
            return None

    def their_sum(self, frame):
        with self.cond:
            return self.sums.pop(frame, None)

    def bye(self):
        self.send(MSG_BYE)
        self.close()

    def close(self):
        for how in (lambda: self.sock.shutdown(socket.SHUT_RDWR), self.sock.close):
            try:
                how()
            except OSError:
                pass
