"""A stream that comes in pieces (HLS: a channel of Plex's live TV, a film from your Plex server), played with some
of it in hand.

mplayer plays these through FFmpeg, which fetches each piece as it's played and asks for the list of pieces again
every few seconds, all in the player's own time: mplayer's cache holds only the list. So whenever the network
stands still for a second or two (WiFi does), so does the picture.

Ahead stands between the player and the stream, on this machine (127.0.0.1): the player's given its address in
place of the stream's. It fetches the pieces to come before they're asked for, and hands them over at once; and it
answers for the list at once too, with the last one it had, looking for the next by itself. A stall shorter than
what it holds isn't seen at all. What it doesn't follow (a piece that's part of a bigger file, a key, a header piece)
it leaves as it is, for FFmpeg to fetch itself; a piece it can't fetch, FFmpeg's sent for; and a stream it can't
open at all (it's opened as the player starts, in no one's way), the player's told so at once: it stops, and the
stream's played as before (screens/player.py's ahead_gave_up). A stream that's gone quiet for good is let go, so the
player stops as it would have."""
import http.client
import http.server
import re
import secrets
import socketserver
import threading
import time
import urllib.parse

from .net import cam_check_peer, cam_names_pi
from .util import UA

AHEAD_SECS = 30.0            # seconds of the stream beyond where the player is, kept in hand (as far as there is)
AHEAD_BYTES = 24 << 20       # ...and no more than this of it
HOLD_SECS = 12.0             # a growing list's newest pieces, this many seconds of them, aren't shown to the player
                             # yet: it plays that much further back from the end, with them in hand already. (As many
                             # as that is when the list's first seen, and so many from then on: a list that starts
                             # with too few to spare shows them all, or the player would have to wait for them)
HOLD_LEAST = 4               # ...but it's always shown this many pieces, or all there are (a player starts three from
                             # the end, and one more is room behind it: the oldest goes off a live list as it's played)
PIECE_MOST = 12 << 20        # a piece bigger than this isn't kept: the player fetches it itself
LIST_LEAST, LIST_MOST = 1.0, 6.0     # seconds between looks at a list that's still growing: half a piece's length,
                                     # within these
LIST_LONG = 16 << 10                 # ...a whole piece's length, for a list longer than this (fetched whole each time)
LIST_WAIT, PIECE_WAIT = 8.0, 20.0    # seconds an answer may take
PIECE_LONGEST = 120.0        # ...and a piece, to come whole
FIRST_WAIT = 20.0            # ...and the very first, as it's opened (a server getting a video ready takes its time)
LIST_IDLE = 20.0             # a list the player hasn't asked for in this long isn't looked at (it's paused, or gone)
GONE_AFTER = 30.0            # seconds a growing list has had no answer: the stream's let go
LIST_BYTES = 4 << 20         # a list is never longer than this
URGENT_MOST = 3              # pieces fetched at once because the player's waiting for them (more: it fetches its own)
RETRY_SOON = 2.0             # a piece that couldn't be fetched, and that was known this soon: the network's away (no
RETRY_AFTER = 3.0            # ...waiting for an answer), and it's tried again after this long, RETRY_MOST times; one
RETRY_MOST = 10              # the stream said no to: once more (some list a piece a moment before they have it)
NOES_MOST = 4                # pieces the stream's said no to, with none fetched yet: its pieces aren't to be had from
                             # here at all, and the player fetches them itself from then on
TAKE = 16 << 10              # a piece is taken from the stream, and is the player's, this much at a time
EXTS = ("ts", "m4s", "mp4", "m4v", "m4a", "mov", "aac", "mp3", "ac3", "eac3", "vtt", "webvtt", "mpg", "mpeg")
                             # what a piece's address here may end in: the kinds FFmpeg takes a piece to be, by
                             # its name (it turns down the rest, since its 2025 fixes: tv.py)
URI = re.compile(r'URI="([^"]*)"')
HOPS = (301, 302, 303, 307, 308)
BOM = b"\xef\xbb\xbf"


class No(OSError):
    """(What the stream, or its link, says no to: not the network being away.)"""


def names_here(link):
    """Whether a link's to this machine itself (localhost, 127.0.0.1, its own name)."""
    try:
        return cam_names_pi(urllib.parse.urlsplit(link).hostname)
    except ValueError:
        return False


class Plain(http.client.HTTPConnection):
    """(A name that turns out to be this machine itself isn't fetched from: net.py's cam_check_peer.)"""

    def connect(self):
        super().connect()
        cam_check_peer(self.sock, self.host)


class Secure(http.client.HTTPSConnection):
    def connect(self):
        super().connect()
        cam_check_peer(self.sock, self.host)


class Wire:
    """Connections kept open to wherever the stream comes from, for one thread's use: asking again is no new
    handshake (on a Pi Zero each of those is a good part of a second's work). A stream from elsewhere may send us
    on to anywhere but this machine itself (home: it's here, and may): its own services are its own, as with a
    camera (net.py)."""

    def __init__(self, agent=None, jar=None, home=True):
        self.conns, self.home = {}, home
        self.agent = (agent or UA).get("User-Agent", "pietato")
        self.jar = {} if jar is None else jar          # site -> {a cookie's name: what it is}: some streams hand one
                                                       # out with the list, and want it back with each piece

    def get(self, link, wait):
        """(where it really came from, its answer). The answer's to be read to its end (or the wire closed)."""
        for _ in range(6):
            u = urllib.parse.urlsplit(link)
            if u.scheme not in ("http", "https") or not u.netloc:
                raise No("not a link")
            if not self.home and cam_names_pi(u.hostname):
                raise No("this machine itself")
            key = (u.scheme, u.netloc)
            path = (u.path or "/") + ("?" + u.query if u.query else "")
            resp = None
            for again in (False, True):
                conn = self.conns.pop(key, None)
                if conn is None:
                    conn = (Secure if u.scheme == "https" else Plain)(u.netloc, timeout=wait)
                try:
                    conn.timeout = wait
                    if conn.sock is not None:
                        conn.sock.settimeout(wait)
                    heads = {"User-Agent": self.agent, "Accept": "*/*"}
                    mine = self.cookies(u.hostname)
                    if mine:
                        heads["Cookie"] = mine
                    conn.request("GET", path, headers=heads)
                    resp = conn.getresponse()
                    self.conns[key] = conn
                    for said in resp.headers.get_all("Set-Cookie") or ():
                        self.cookie(u.hostname, said)
                    break
                except (http.client.HTTPException, OSError):
                    conn.close()                       # (one kept open may have been shut at the other end: once more)
                    if again:
                        raise
            if resp.status in HOPS and resp.getheader("Location"):
                resp.read(1 << 16)
                if not resp.isclosed():                # (more to it than a few words: that connection's let go)
                    self.drop(link)
                link = urllib.parse.urljoin(link, resp.getheader("Location"))
                continue
            return link, resp
        raise No("sent on too many times")

    def cookie(self, host, said):
        """A cookie the stream hands out: kept for its own site, or for the wider one it names (its pieces often
        come from another site of the same name's)."""
        first, _, rest = said.partition(";")
        name, _, what = first.partition("=")
        host, site = (host or "").lower(), None
        for part in rest.split(";"):
            k, _, v = part.partition("=")
            if k.strip().lower() == "domain":
                site = v.strip().lstrip(".").lower()
        if not site or "." not in site or not (host == site or host.endswith("." + site)):
            site = host                                # (none named, or one that isn't its to name)
        name = name.strip()
        if name and (name in self.jar.get(site, ()) or sum(len(v) for v in list(self.jar.values())) < 32):
            self.jar.setdefault(site, {})[name] = what.strip()

    def cookies(self, host):
        """The cookies to send a site: its own, and those kept for the wider sites it's part of."""
        host = (host or "").lower()
        mine = {}
        for site, kept in sorted(list(self.jar.items()), key=lambda x: len(x[0])):
            if host == site or host.endswith("." + site):
                mine.update(kept)
        return "; ".join(f"{k}={v}" for k, v in mine.items())

    def drop(self, link):
        """(An answer that wasn't read to its end: its connection's no use again.)"""
        u = urllib.parse.urlsplit(link)
        conn = self.conns.pop((u.scheme, u.netloc), None)
        if conn is not None:
            conn.close()

    def close(self):
        for conn in self.conns.values():
            conn.close()
        self.conns = {}


def joined(base, link):
    """A link in a list, made whole (as it is, if it's no link at all: one bad line isn't the end of the list)."""
    try:
        return urllib.parse.urljoin(base, link)
    except ValueError:
        return link


def ext_of(link, fmp4=False):
    """What a piece's own address ends in here: as the stream's does, if that's a kind FFmpeg knows (EXTS), or what
    its kind of stream has (so one whose links end in nothing it knows isn't turned down for them, played from
    here)."""
    try:
        name = urllib.parse.urlsplit(link).path.rsplit("/", 1)[-1]
    except ValueError:
        name = ""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return ext if ext in EXTS else "m4s" if fmp4 else "ts"


class List:
    """A list of pieces (or of other lists), as the stream has it and as the player's given it."""

    def __init__(self, link, number=0):
        self.link, self.number = link, number    # the stream's own address for it; which of ours it is
        self.raw = None                  # as it came, last
        self.body = b""                  # as the player's given it
        self.pieces = []                 # [(piece's number, its seconds)], in order
        self.at = {}                     # piece's number -> where it is in that
        self.ends = []                   # where each piece's line ends, in body
        self.master, self.live, self.target, self.ranged, self.fmp4 = False, True, 6.0, False, False
        self.next, self.secs, self.seq, self.whole = None, 0.0, None, True   # (reading it: what comes next)
        self.got_at = self.asked_at = self.tried_at = 0.0
        self.failing = None              # when it first couldn't be had, since it last could
        self.cursor = None               # the last piece the player asked for
        self.asks = 0                    # how many it's asked for, one after another
        self.shown_to = None             # the last piece the player's been shown
        self.hold = None                 # how many of its newest pieces it isn't shown (settled when it's first seen)
        self.lock = threading.Lock()     # (held while it's read anew, and while it's looked at for what to show)

    def every(self):
        """Seconds between looks at it, while it grows."""
        secs = self.target if len(self.raw or "") > LIST_LONG else self.target / 2
        return min(max(secs, LIST_LEAST), LIST_MOST)

    def take(self, text, base, list_at, piece_at):
        """Read anew (base: where it really came from). One that only grew since last time: just what's new. A piece
        is known by where it comes in the stream (the list's count of them), whatever its link is this time: some
        streams give the same piece a new link each time they're asked."""
        more = (self.raw is not None and self.whole and self.live and not self.master
                and len(text) >= len(self.raw) and text.startswith(self.raw))
        if more:
            new, pieces, at, ends, size = text[len(self.raw):], self.pieces, self.at, self.ends, len(self.body)
        else:
            new, pieces, at, ends, size = text, [], {}, [], 0
            self.master, self.live, self.ranged, self.fmp4 = False, True, False, False
            self.next, self.secs, self.seq = None, 0.0, None
        self.whole = False                             # (till it's read to its end: a reading cut short isn't built on)
        out = []
        for line in new.splitlines():
            line = line.strip()
            mine = False
            if line.startswith("#"):
                if line.startswith("#EXT-X-STREAM-INF"):
                    self.next, self.master = "list", True
                elif line.startswith("#EXTINF"):
                    self.next = "piece"
                    try:
                        self.secs = float(line[8:].split(",")[0])
                    except ValueError:
                        self.secs = self.target
                elif line.startswith("#EXT-X-BYTERANGE"):
                    self.ranged = True                 # (pieces that are parts of one file: FFmpeg's to fetch)
                elif line.startswith("#EXT-X-ENDLIST"):
                    self.live = False
                elif line.startswith("#EXT-X-MEDIA-SEQUENCE") and self.seq is None:
                    try:
                        self.seq = int(line.split(":", 1)[1])
                    except ValueError:
                        pass
                elif line.startswith("#EXT-X-TARGETDURATION"):
                    try:
                        self.target = max(0.5, float(line.split(":", 1)[1]))
                    except ValueError:
                        pass
                elif line.startswith("#EXT-X-MAP"):
                    self.fmp4 = True
                if 'URI="' in line:                    # (a key, a header piece: its link made whole, fetched as it is;
                    other = line.startswith("#EXT-X-MEDIA:") and ("TYPE=AUDIO" in line or "TYPE=VIDEO" in line)
                    line = URI.sub(lambda m: 'URI="%s"' % (     # the stream's sound or picture, in a list apart: ours)
                        list_at(joined(base, m.group(1))) if other else joined(base, m.group(1))), line)
            elif line:
                link = joined(base, line)
                if self.next == "list":
                    line = list_at(link)
                elif self.next == "piece":
                    self.seq = 0 if self.seq is None else self.seq
                    if self.ranged:
                        line = link
                    else:
                        number, line = piece_at((self.number, self.seq), link, ext_of(link, self.fmp4))
                        at[number] = len(pieces)
                        pieces.append((number, self.secs))
                        mine = True
                    self.seq += 1
                else:
                    line = link
                self.next = None
            line = (line + "\n").encode()
            out.append(line)
            size += len(line)
            if mine:
                ends.append(size)
        self.pieces, self.at, self.ends = pieces, at, ends
        self.body = (self.body if more else b"") + b"".join(out)
        self.raw = text
        self.whole = text.endswith("\n") and self.next is None

    def shown(self, stale=False, have=lambda number: False):
        """The list as the player's given it. One that's still growing: without its newest pieces (HOLD_SECS of
        them), which are fetched all the same: so it plays that much further back from the end of the stream, with
        that much more in hand. While the stream isn't answering (stale), those in hand are shown after all (have:
        whether a piece is): that's what they were kept for. Never fewer than it's been shown already."""
        body, pieces, ends, at = self.body, self.pieces, self.ends, self.at
        if not self.live or self.master or len(ends) != len(pieces) or not pieces:
            return body
        if self.hold is None:
            held, secs = 0, 0.0
            while len(pieces) - held > HOLD_LEAST and secs + pieces[-1 - held][1] <= HOLD_SECS:
                secs += pieces[-1 - held][1]
                held += 1
            self.hold = held
        held = min(self.hold, max(0, len(pieces) - HOLD_LEAST))
        last = max(len(pieces) - 1 - held, at.get(self.shown_to, -1))
        while stale and last + 1 < len(pieces) and have(pieces[last + 1][0]):
            last += 1
        self.shown_to = pieces[last][0]
        return body[:ends[last]]


class Piece:
    """A piece of the stream: fetched (or being fetched) and handed to the player, as far as it's come."""

    def __init__(self, link, ext):
        self.link, self.ext = link, ext
        self.cond = threading.Condition()
        self.readers = 0
        self.clear()

    def clear(self):
        self.data = bytearray()
        self.size = None                 # how long it'll be, once that's said
        self.kind = None
        self.started = self.known = self.done = self.failed = False
        self.said_no = self.soon = False   # it failed: the stream said no; it was known at once (the network's away)
        self.failed_at, self.tries = 0.0, 0


class Ahead:
    """One stream, played from here. start(): the address the player's given in place of its own (None: there's none
    to give, and it's played as before). close(): the player's stopped."""

    def __init__(self, link, agent=None, clock=time.monotonic):
        self.link, self.agent, self.clock = link, agent, clock
        self.home = names_here(link)                   # (a stream on this machine itself: a Plex server here)
        self.token = secrets.token_urlsafe(9)
        self.lock = threading.RLock()
        self.planning = threading.Lock()               # (one plan at a time: plan())
        self.lists, self.list_no = [], {}              # List by number; link -> number
        self.pieces, self.piece_no = [], {}            # Piece by number; (its list, where it comes in it) -> number
        self.begun = set()                             # the pieces fetched, or being fetched
        self.queue = []                                # pieces to fetch next, in order
        self.urgent = 0
        self.fetched = self.noes = 0                   # pieces fetched; pieces the stream's said no to
        self.off = False                               # its pieces aren't to be had from here: only its lists are
        self.closed = False
        self.more, self.stop = threading.Event(), threading.Event()
        self.jar = {}                                  # (cookies, for every wire of it)
        self.server = None
        self.address = None
        self.opened, self.ok = threading.Event(), False    # the stream's been opened (or couldn't be); and was

    # -- its lists and pieces, by number ---------------------------------------------------------------------------
    def list_at(self, link):
        with self.lock:
            n = self.list_no.get(link)
            if n is None:
                n = self.list_no[link] = len(self.lists)
                self.lists.append(List(link, n))
        return f"l{n}.m3u8"

    def piece_at(self, key, link, ext):
        with self.lock:
            n = self.piece_no.get(key)
            if n is None:
                n = self.piece_no[key] = len(self.pieces)
                self.pieces.append(Piece(link, ext))
            elif not self.pieces[n].started:
                self.pieces[n].link = link             # (its link this time)
        return n, f"p{n}.{self.pieces[n].ext}"

    # -- starting and stopping -------------------------------------------------------------------------------------
    def start(self):
        """The address, at once: the stream's opened meanwhile (open), and the player's answered once it is."""
        try:
            self.server = Server(("127.0.0.1", 0), handler(self))
        except OSError:
            return None
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True).start()
        self.list_at(self.link)
        self.lists[0].asked_at = self.clock()
        threading.Thread(target=self.open, daemon=True).start()
        self.address = f"http://127.0.0.1:{self.server.server_address[1]}/{self.token}/l0.m3u8"
        return self.address

    def open(self):
        """The stream's list fetched for the first time, as the player starts: by the time it asks, there's often a
        piece on its way already. It couldn't be (or it's no list): the player's told so when it asks, and stops."""
        wire = Wire(self.agent, self.jar, self.home)
        try:
            self.ok = self.look(self.lists[0], wire, FIRST_WAIT)
            if self.ok and not self.closed:
                threading.Thread(target=self.keep_lists, daemon=True).start()
                threading.Thread(target=self.keep_pieces, daemon=True).start()
        finally:
            wire.close()
            self.opened.set()

    def close(self):
        self.closed = True
        self.more.set()
        self.stop.set()
        self.opened.set()
        server, self.server = self.server, None
        if server is not None:
            threading.Thread(target=lambda: (server.shutdown(), server.server_close()), daemon=True).start()
        with self.lock:
            pieces = list(self.pieces)
        for p in pieces:
            with p.cond:
                p.cond.notify_all()

    # -- the lists -------------------------------------------------------------------------------------------------
    def look(self, lst, wire, wait=None):
        """A list fetched from the stream, and read. False: it couldn't be had, or isn't one (a stream that's not in
        pieces is known by its first few bytes, and no more of it's taken)."""
        now = self.clock()
        lst.tried_at = now
        try:
            base, resp = wire.get(lst.link, LIST_WAIT if wait is None else wait)
            try:
                data = resp.read(16) if resp.status == 200 else b""
                if data.lstrip(BOM + b" \r\n")[:7] == b"#EXTM3U":
                    data += resp.read(LIST_BYTES + 1)
                else:
                    data = b""
            finally:
                if not resp.isclosed():                # (not read to its end: that connection's no use again)
                    wire.drop(base)
            text = data.decode("utf-8", "replace").lstrip("\ufeff")
            if not text.lstrip().startswith("#EXTM3U") or len(data) > LIST_BYTES:
                raise OSError("not a list")
            with lst.lock:
                lst.take(text, base, self.list_at, self.piece_at)
                lst.got_at, lst.failing = self.clock(), None
        except Exception as ex:
            if not isinstance(ex, (http.client.HTTPException, OSError, ValueError)):
                print(f"ahead: a list that couldn't be read ({ex!r})", flush=True)
            if lst.failing is None:
                lst.failing = now
            return False
        self.plan()
        return True

    def keep_lists(self):
        """Each list that's still growing looked at again as often as it grows, while the player's asking for it."""
        wire, tidied = Wire(self.agent, self.jar, self.home), self.clock()
        while not self.closed:
            now = self.clock()
            with self.lock:
                lists = list(self.lists)
            try:
                for lst in lists:
                    if self.closed:
                        break
                    if (lst.raw is not None and lst.live and not lst.master and now - lst.asked_at <= LIST_IDLE
                            and now - lst.tried_at >= lst.every()):
                        self.look(lst, wire)
                if now - tidied >= 5.0:                # (a player that's stopped asking: what was held is let go)
                    tidied = now
                    self.plan()
            except Exception as ex:                    # (never the end of the looking)
                print(f"ahead: {ex!r}", flush=True)
                self.stop.wait(1.0)
            self.stop.wait(0.2)
        wire.close()

    # -- the pieces ------------------------------------------------------------------------------------------------
    def plan(self):
        """What to fetch next, and what to let go of: for each list the player's on, the pieces from where it is
        (a growing list it hasn't started on: from a little back from its end, where a player starts) for
        AHEAD_SECS on, within AHEAD_BYTES in all. (With several lists of pieces, only those it's gone on from the
        first piece it took: it tries a piece of every version of a stream before it settles on one.)"""
        with self.planning:
            now = self.clock()
            with self.lock:
                lists = list(self.lists)
            several = sum(1 for lst in lists if not lst.master) > 1
            keep, want = set(), []
            for lst in lists:
                if lst.master or now - lst.asked_at > LIST_IDLE or (several and lst.asks < 2) or self.off:
                    continue
                with lst.lock:                         # (as it is now, all of a piece)
                    pieces, where = lst.pieces, lst.at
                    if not pieces:
                        continue
                    at = where.get(lst.cursor) if lst.cursor is not None else None
                    if at is not None:
                        start = at
                    elif lst.live and lst.cursor is None:  # (not started on: three back from the end it's shown)
                        seen = where.get(lst.shown_to, len(pieces) - 1) + 1 if lst.shown_to is not None \
                            else lst.shown().count(b"\n#EXTINF")
                        start = max(0, seen - 3)
                    else:
                        start = 0
                    ahead = pieces[max(0, start - 1):start + 400]
                secs = 0.0
                for k, (number, d) in enumerate(ahead):
                    keep.add(number)
                    if k == 0 and start > 0:           # (the one before: asked for again, now and then)
                        continue
                    want.append((secs, number))
                    secs += d
                    if secs >= AHEAD_SECS:
                        break
            want.sort()                                # (the soonest needed first, whichever list it's of)
            with self.lock:
                held = sum(len(self.pieces[n].data) for n in keep)
                self.queue = []
                for _, n in want:
                    p = self.pieces[n]
                    again = RETRY_MOST if p.soon and not p.said_no else 1 if p.said_no else 0
                    if p.failed and p.tries < again and p.readers == 0 and now - p.failed_at >= RETRY_AFTER:
                        tries = p.tries + 1            # (the network was away, most likely: once more)
                        self.begun.discard(n)
                        with p.cond:
                            p.clear()
                            p.tries = tries
                    if not p.started and held + sum(self.pieces[q].size or (1 << 20) for q in self.queue) < AHEAD_BYTES:
                        self.queue.append(n)
                for n in list(self.begun):             # (what the player's past: let go of)
                    p = self.pieces[n]
                    if n not in keep and p.readers == 0 and (p.done or p.failed):
                        self.begun.discard(n)
                        with p.cond:
                            p.clear()
        self.more.set()

    def keep_pieces(self):
        """The pieces to come, fetched one after another."""
        wire = Wire(self.agent, self.jar, self.home)
        while not self.closed:
            with self.lock:
                p = None
                while self.queue and p is None:
                    n = self.queue.pop(0)
                    if not self.pieces[n].started:
                        p = self.pieces[n]
                        p.started = True
                        self.begun.add(n)
            if p is None:
                self.more.wait(0.5)
                self.more.clear()
                continue
            try:
                self.fetch(p, wire)
            except Exception as ex:                    # (never the end of the fetching)
                print(f"ahead: {ex!r}", flush=True)
                self.stop.wait(1.0)
        wire.close()

    def fetch(self, p, wire):
        """A piece fetched: what's come of it is the player's as it comes."""
        base, began = p.link, self.clock()
        try:
            base, resp = wire.get(p.link, PIECE_WAIT)
            size = resp.getheader("Content-Length")
            size = int(size) if size and size.isdigit() else None
            if resp.status != 200 or (size or 0) > PIECE_MOST:
                wire.drop(base)
                raise No("not to be had here")
            with p.cond:
                p.size, p.kind, p.known = size, resp.getheader("Content-Type"), True
                p.cond.notify_all()
            while not self.closed:
                chunk = resp.read(TAKE)
                if not chunk:
                    break
                with p.cond:
                    p.data += chunk
                    p.cond.notify_all()
                if len(p.data) > PIECE_MOST:
                    raise No("too big to hold")
                if self.clock() > began + PIECE_LONGEST:
                    raise OSError("too long in coming")
            if self.closed or (size is not None and len(p.data) != size):
                raise OSError("cut short")
            with p.cond:
                p.done = True
                p.cond.notify_all()
            self.fetched += 1
        except Exception as ex:                        # (whatever went wrong: it isn't to be had here, for now)
            try:
                wire.drop(base)
            except ValueError:
                pass
            now = self.clock()
            with p.cond:
                p.failed, p.said_no, p.soon, p.failed_at = True, isinstance(ex, No), now - began < RETRY_SOON, now
                p.cond.notify_all()
            if p.said_no and not self.closed:
                self.noes += 1
                if not self.fetched and self.noes >= NOES_MOST and not self.off:
                    self.off = True
                    print("ahead: this stream's pieces aren't to be had from here: its player fetches them itself",
                          flush=True)
        self.plan()

    def urgently(self, n, p):
        """A piece the player's asking for that isn't on its way: fetched now, on a wire of its own."""
        def go():
            wire = Wire(self.agent, self.jar, self.home)
            try:
                self.fetch(p, wire)
            finally:
                wire.close()
                with self.lock:
                    self.urgent -= 1
        with self.lock:
            if p.started:
                return True
            if self.urgent >= URGENT_MOST:
                return False
            self.urgent += 1
            p.started = True
            self.begun.add(n)
        threading.Thread(target=go, daemon=True).start()
        return True

    # -- the player's asking ---------------------------------------------------------------------------------------
    def asked_list(self, n):
        """The list as the player's given it (bytes), or None: there's none to give (the stream's gone, or couldn't
        be opened)."""
        self.opened.wait(3 * FIRST_WAIT)               # (still being opened: the player waits, as it would have)
        with self.lock:
            lst = self.lists[n] if 0 <= n < len(self.lists) else None
        if lst is None or not self.ok or self.closed:
            return None
        now = self.clock()
        idle, lst.asked_at = now - lst.asked_at, now
        if lst.raw is None or (lst.live and not lst.master and idle > LIST_IDLE):
            wire = Wire(self.agent, self.jar, self.home)   # (its first time; or back after a pause: as it is now)
            ok = self.look(lst, wire)
            wire.close()
            if not ok and lst.raw is None:
                return None
        if lst.live and lst.failing is not None and now - lst.failing > GONE_AFTER:
            return None                                # (no word of it in a long while: the player's to stop)
        return self.show(lst)

    def show(self, lst):
        """A list as the player's given it now (List.shown): with what's in hand, once the stream's stopped answering
        (no new list in twice as long as it's looked for, and a second)."""
        stale = self.clock() - lst.got_at > 2 * lst.every() + 1.0
        with lst.lock:
            return lst.shown(stale, lambda n: self.pieces[n].done)

    def asked_piece(self, n):
        """The piece the player's asking for (on its way by now), or None: FFmpeg's to fetch it itself."""
        with self.lock:
            p = self.pieces[n] if 0 <= n < len(self.pieces) else None
            if p is None or self.off:
                return None
            for lst in self.lists:
                if n in lst.at and lst.cursor != n:
                    lst.cursor, lst.asks = n, lst.asks + 1
            if p.failed and p.readers == 0:            # (it couldn't be fetched before: once more, now it's wanted)
                tries = p.tries
                self.begun.discard(n)
                with p.cond:
                    p.clear()
                    p.tries = tries
            p.readers += 1
        if not p.started and not self.urgently(n, p):
            with self.lock:
                p.readers -= 1
            return None
        self.plan()
        return p

    def done_with(self, p):
        with self.lock:
            p.readers -= 1


def handler(ahead):
    class Asked(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def do_GET(self):
            parts = self.path.split("?")[0].strip("/").split("/")
            name = parts[1] if len(parts) == 2 and secrets.compare_digest(parts[0], ahead.token) else ""
            number = name[1:].split(".")[0]
            if not number.isdigit() or name[:1] not in "lp" or ahead.closed:
                return self.send_error(404)
            if name[0] == "l":
                body = ahead.asked_list(int(number))
                if body is None:
                    return self.send_error(504)
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.apple.mpegurl")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            p = ahead.asked_piece(int(number))
            if p is None:
                with ahead.lock:
                    link = ahead.pieces[int(number)].link if int(number) < len(ahead.pieces) else None
                return self.elsewhere(link)
            try:
                self.give(p)
            finally:
                ahead.done_with(p)

        def elsewhere(self, link):
            if not link or (names_here(link) and not ahead.home):
                return self.send_error(404)            # (nor is the player sent to this machine's own)
            self.send_response(302)
            self.send_header("Location", link)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def give(self, p):
            until = time.monotonic() + PIECE_WAIT
            with p.cond:                               # (how long it is, said first: once the stream's said)
                while not (p.known or p.done or p.failed) and not ahead.closed and time.monotonic() < until:
                    p.cond.wait(0.5)
                known, failed, size = p.known or p.done, p.failed, p.size
                if p.done:
                    size = len(p.data)
            if not known or (failed and not p.data):
                return self.elsewhere(p.link)          # (it can't be had here: FFmpeg's sent for it)
            self.send_response(200)
            self.send_header("Content-Type", p.kind or "video/mp2t")
            if size is not None:
                self.send_header("Content-Length", str(size))
            else:
                self.send_header("Connection", "close")
                self.close_connection = True
            self.end_headers()
            sent = 0
            while not ahead.closed:
                with p.cond:
                    while len(p.data) == sent and not (p.done or p.failed) and not ahead.closed:
                        p.cond.wait(0.5)
                    chunk, over = bytes(p.data[sent:sent + (256 << 10)]), p.done or p.failed
                if chunk:
                    self.wfile.write(chunk)
                    sent += len(chunk)
                elif over:
                    break
            if size is not None and sent != size:
                self.close_connection = True           # (cut short: said by ending there)
    return Asked


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        pass                                           # (the player hung up: nothing to say)
