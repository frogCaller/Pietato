"""A stream that comes in pieces (a channel of Plex's live TV, a Plex video), played with some of it in hand
(pitato/ahead.py): mplayer's own cache holds only the list of pieces, so a second's trouble on the network was a
second's freeze. First the lists, read: each piece's link made one of this machine's, known by where it comes in
the stream (not by its link, which some streams change each time); other lists of pieces too; a key's or a header
piece's link made whole and left; pieces that are parts of one file left; a list that only grew read from where it
was; its newest pieces kept back from the player, as many as when it's first seen, and shown after all once the
stream stops answering. Then a pretend stream on this machine: the pieces to come fetched before they're asked for,
one at a time; handed over at once, as the stream sent them; the list answered at once while the stream's dead, and
what's in hand played on; a piece on its way handed over as it comes; one that can't be had: the player's sent for
it; cookies given back; what the player's past let go of, and no more held than there's room for; a piece that
couldn't be fetched because the network was away a moment: tried again by itself; a stream that says no to every
piece: left to the player; a stream gone for good let go; what isn't a list, or can't be reached: its player told so at once; a stream in several versions:
only the one the player goes on with fetched ahead; a stream from elsewhere that points at this machine itself (a
piece's link, a piece that sends on, a name): nothing of this machine's fetched for it. Then media mode: a live channel's player given this machine's
address, and a Plex video's; a radio station's not; stopped, it's closed; one that won't play that way played as
before, and its like for a while (unless it won't play as before either: then it wasn't that). And, where mplayer
and FFmpeg are, the real thing: a made-up channel whose network dies for four seconds, watched as it plays: no
freeze; a stream that can't be opened from here: mplayer stops at once; and media mode starting mplayer its own
way: a channel plays from here, and one that's down is tried from here, then as before, then let go."""
import http.client, http.server, io, os, shutil, socket, socketserver, subprocess, sys, threading, time
from paths import SP, TESTS  # noqa: E402  (this test's folder of work; tests)
sys.path.insert(0, TESTS)
os.environ["PITATO_AHEAD"] = "1"                       # (the other tests look at what a player's given: off for them)
import pietato_all as g
import pitato.ahead as A

S = SP + "/t_ahead"
shutil.rmtree(S, ignore_errors=True)
os.makedirs(S)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def until(cond, secs=5.0):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return bool(cond())


# ---- a list, read ------------------------------------------------------------------------------------------------------
def reader():
    """(what a List reads with: its other lists and its pieces, numbered as they come.)"""
    lists, pieces = {}, {}

    def list_at(link):
        return f"l{lists.setdefault(link, len(lists) + 1)}.m3u8"

    def piece_at(key, link, ext):
        n = pieces.setdefault(key, [len(pieces), link])
        n[1] = link
        return n[0], f"p{n[0]}.{ext}"
    return lists, pieces, list_at, piece_at


BASE = "https://cdn.example/live/abc/v480/index.m3u8?sig=1"
LIVE = ("#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:6\n#EXT-X-MEDIA-SEQUENCE:120\n"
        "#EXTINF:6.006,\nseg120.ts\n#EXTINF:6.006,\nseg121.ts?x=1\n#EXT-X-DISCONTINUITY\n"
        "#EXTINF:4.5, an advert\nhttps://ads.example/a/640x360_800000?u=7\n#EXTINF:6.006,\n../v480/seg123.TS\n")
lists, pieces, list_at, piece_at = reader()
lst = A.List(BASE)
lst.take(LIVE, BASE, list_at, piece_at)
body = lst.body.decode().splitlines()
check(f"a live list read: each piece's link one of this machine's, numbered ({[x for x in body if not x.startswith('#')]}),"
      f" the rest of it as it was", [x for x in body if not x.startswith("#")] == ["p0.ts", "p1.ts", "p2.ts", "p3.ts"]
      and body[:4] == LIVE.splitlines()[:4] and "#EXT-X-DISCONTINUITY" in body and "#EXTINF:4.5, an advert" in body)
check(f"...each known by where it comes in the stream ({sorted(pieces)}), its own link whole ({pieces[(0, 122)][1]}, "
      f"{pieces[(0, 123)][1]})", sorted(pieces) == [(0, 120), (0, 121), (0, 122), (0, 123)]
      and pieces[(0, 120)][1] == "https://cdn.example/live/abc/v480/seg120.ts"
      and pieces[(0, 121)][1] == "https://cdn.example/live/abc/v480/seg121.ts?x=1"
      and pieces[(0, 122)][1] == "https://ads.example/a/640x360_800000?u=7"
      and pieces[(0, 123)][1] == "https://cdn.example/live/abc/v480/seg123.TS")
check(f"...how long each is, that it's still growing, and how often to look ({lst.pieces}, {lst.every()} s)",
      [d for _, d in lst.pieces] == [6.006, 6.006, 4.5, 6.006] and lst.live and not lst.master and lst.target == 6.0
      and lst.every() == 3.0)
NEXT = LIVE.replace("#EXT-X-MEDIA-SEQUENCE:120", "#EXT-X-MEDIA-SEQUENCE:121").replace("#EXTINF:6.006,\nseg120.ts\n", "") \
    .replace("seg121.ts?x=1", "seg121.ts?x=2") + "#EXTINF:6.006,\nseg124.ts\n"
lst.take(NEXT, BASE, list_at, piece_at)
check(f"the list moved on, a piece's link changed: the same pieces by the same numbers, and the new one "
      f"({[n for n, _ in lst.pieces]}; {pieces[(0, 121)][1][-3:]})", [n for n, _ in lst.pieces] == [1, 2, 3, 4]
      and pieces[(0, 121)][1].endswith("?x=2") and lst.at == {1: 0, 2: 1, 3: 2, 4: 3})

MASTER = ('#EXTM3U\n#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aac",NAME="English",URI="audio/en.m3u8"\n'
          '#EXT-X-STREAM-INF:BANDWIDTH=900000,RESOLUTION=640x360,AUDIO="aac"\nv360.m3u8?t=9\n'
          '#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080,AUDIO="aac"\nhttps://other.example/v1080.m3u8\n'
          '#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="English",URI="subs/en.m3u8"\n'
          '#EXT-X-I-FRAME-STREAM-INF:BANDWIDTH=80000,URI="iframes.m3u8"\n')
lists, pieces, list_at, piece_at = reader()
top = A.List(BASE)
top.take(MASTER, "https://cdn.example/x/master.m3u8", list_at, piece_at)
check(f"a list of lists: each of them one of this machine's too, the sound's as well ({sorted(lists.items(), key=lambda x: x[1])}); "
      f"the lists a player leaves alone (words, a quick look through) left, their links whole",
      top.master and not pieces and top.body.decode().splitlines()[1].endswith('URI="l1.m3u8"')
      and [x for x in top.body.decode().splitlines() if not x.startswith("#")] == ["l2.m3u8", "l3.m3u8"]
      and lists == {"https://cdn.example/x/audio/en.m3u8": 1, "https://cdn.example/x/v360.m3u8?t=9": 2,
                    "https://other.example/v1080.m3u8": 3}
      and top.body.decode().splitlines()[-2].endswith('URI="https://cdn.example/x/subs/en.m3u8"')
      and top.body.decode().splitlines()[-1].endswith('URI="https://cdn.example/x/iframes.m3u8"'))
KEYED = ('#EXTM3U\n#EXT-X-TARGETDURATION:4\n#EXT-X-MAP:URI="init.mp4"\n#EXT-X-KEY:METHOD=AES-128,URI="../keys/k1",IV=0x01\n'
         "#EXTINF:4.0,\nchunk_1\n#EXTINF:4.0,\nchunk_2.m4s\n#EXT-X-ENDLIST\n")
lists, pieces, list_at, piece_at = reader()
lst = A.List(BASE)
lst.take(KEYED, "https://cdn.example/x/y/index.m3u8", list_at, piece_at)
body = lst.body.decode().splitlines()
check(f"a key's link and a header piece's: made whole, and left for FFmpeg to fetch ({body[2]}; {body[3][:60]}); "
      f"pieces with no ending to their names take their kind's ({body[5]}, {body[7]}); a finished list known as one",
      body[2] == '#EXT-X-MAP:URI="https://cdn.example/x/y/init.mp4"'
      and body[3] == '#EXT-X-KEY:METHOD=AES-128,URI="https://cdn.example/x/keys/k1",IV=0x01'
      and body[5] == "p0.m4s" and body[7] == "p1.m4s" and not lst.live and lst.shown() == lst.body)
RANGED = ("#EXTM3U\n#EXT-X-TARGETDURATION:4\n#EXTINF:4.0,\n#EXT-X-BYTERANGE:1000@0\nall.ts\n"
          "#EXTINF:4.0,\n#EXT-X-BYTERANGE:1000@1000\nall.ts\n")
lists, pieces, list_at, piece_at = reader()
lst = A.List(BASE)
lst.take(RANGED, "https://cdn.example/x/index.m3u8", list_at, piece_at)
check("pieces that are parts of one file: their link whole, and left",
      not pieces and lst.pieces == [] and lst.body.decode().count("https://cdn.example/x/all.ts") == 2)

ends = [(A.ext_of(x, f), x.rsplit("/", 1)[-1]) for x, f in (
    ("https://c.example/a/seg1.ts?x=1", False), ("https://c.example/a/seg1.M2TS", False),
    ("https://c.example/a/640x360_800000", False), ("https://c.example/a/v.1/chunk", True),
    ("https://c.example/a/1.cmfv", True), ("https://c.example/a/1.m4s", False), ("https://c.example/a/1.aac", False),
    ("https://c.example/a/1.webvtt", False), ("https://c.example/a/1.php", False))]
check(f"what a piece's name ends in here: as the stream's, if FFmpeg takes that for a piece; else its kind's "
      f"({', '.join(f'{n} {e}' for e, n in ends)})",
      [e for e, _ in ends] == ["ts", "ts", "ts", "m4s", "m4s", "m4s", "aac", "webvtt", "ts"])

w = A.Wire()
for said in ("hdntl=exp~1; Path=/; Domain=.cdn.example; HttpOnly", "own=1; Path=/", "far=1; Domain=other.example",
             "wide=1; Domain=example"):
    w.cookie("video.cdn.example", said)
check(f"a cookie the stream hands out: back to its own site ({w.cookies('video.cdn.example')}), and to the others of "
      f"the wider one it names ({w.cookies('pieces.cdn.example')}); nowhere it had no say ({w.cookies('other.example')!r})",
      w.cookies("video.cdn.example") == "hdntl=exp~1; own=1; far=1; wide=1"
      and w.cookies("pieces.cdn.example") == "hdntl=exp~1" and w.cookies("other.example") == ""
      and w.cookies("cdn.example") == "hdntl=exp~1" and w.cookies("xcdn.example") == "")

# a list that only grows (a Plex video being made ready): read from where it was, the same as read whole
lists, pieces, list_at, piece_at = reader()
grow = A.List(BASE)
text = "#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXT-X-MEDIA-SEQUENCE:0\n"
read = []
for k in range(40):
    text += f"#EXTINF:2.0,\n{k:05d}.ts\n"
    if k % 7 == 3 or k == 39:
        if k == 39:
            text += "#EXT-X-ENDLIST\n"
        seen = len(grow.raw or "")
        grow.take(text, "http://10.0.0.5:32400/video/session/s1/base/index.m3u8", list_at, piece_at)
        read.append(len(text) - seen)
l2, p2, la2, pa2 = reader()
whole = A.List(BASE)
whole.take(text, "http://10.0.0.5:32400/video/session/s1/base/index.m3u8", la2, pa2)
check(f"a list that only grew: just what's new read each time ({read[:4]}... of {len(text)}), and it comes to the same "
      f"({len(grow.pieces)} pieces)", grow.body == whole.body and grow.pieces == whole.pieces and grow.ends == whole.ends
      and not grow.live and max(read[1:]) < 200 and len(grow.pieces) == 40
      and pieces[(0, 39)][1].endswith("/base/00039.ts"))

lists, pieces, list_at, piece_at = reader()
long = A.List(BASE)
long.take("#EXTM3U\n#EXT-X-TARGETDURATION:4\n" + "".join(f"#EXTINF:4.0,\n{k:05d}.ts\n" for k in range(900)),
          "http://10.0.0.5:32400/video/session/s1/base/index.m3u8", list_at, piece_at)
check(f"how often a growing list's looked at: twice in a piece's length ({grow.target / 2:.0f} s for two-second pieces"
      f"... no less than {A.LIST_LEAST:.0f}); one that's long ({len(long.raw) >> 10} KB), fetched whole each time: once "
      f"({long.every():.0f} s for four-second pieces)", (grow.every(), long.every(), len(long.pieces)) == (1.0, 4.0, 900))

# its newest pieces kept back from the player: as many as when it's first seen; shown once the stream's quiet
def shown(lst, **kw):
    return [x for x in lst.shown(**kw).decode().splitlines() if not x.startswith("#")]


def live_text(first, last, secs=6.0):
    return ("#EXTM3U\n#EXT-X-TARGETDURATION:6\n" + f"#EXT-X-MEDIA-SEQUENCE:{first}\n"
            + "".join(f"#EXTINF:{secs},\ns{k}.ts\n" for k in range(first, last + 1)))


lists, pieces, list_at, piece_at = reader()
lst = A.List(BASE)
lst.take(live_text(0, 7), BASE, list_at, piece_at)
first = shown(lst)
check(f"a live list of eight six-second pieces: the player's shown six, the newest twelve seconds kept back "
      f"({first[-1]}; held {lst.hold})", first == [f"p{k}.ts" for k in range(6)] and lst.hold == 2)
lst.take(live_text(1, 8), BASE, list_at, piece_at)
check(f"...as it moves on, so does what's shown ({shown(lst)[-1]})", shown(lst) == [f"p{k}.ts" for k in range(1, 7)])
got = shown(lst, stale=True, have=lambda n: n == 7)
check(f"...the stream not answering: the ones in hand shown after all, one of two here ({got[-1]}); never fewer after "
      f"({shown(lst)[-1]})", got[-1] == "p7.ts" and shown(lst)[-1] == "p7.ts" and len(shown(lst)) == 7)
lst.take(live_text(2, 9), BASE, list_at, piece_at)
check(f"...and answering again: kept back as before ({shown(lst)[-1]})", shown(lst)[-1] == "p7.ts"
      and (lst.take(live_text(3, 10), BASE, list_at, piece_at), shown(lst)[-1])[1] == "p8.ts")
lists, pieces, list_at, piece_at = reader()
short = A.List(BASE)
short.take(live_text(0, 1), BASE, list_at, piece_at)
some = [len(shown(short))]
for last in range(2, 9):
    short.take(live_text(0, last), BASE, list_at, piece_at)
    some.append(len(shown(short)))
check(f"a list that starts with too few to spare (a video only just being made ready): shown all of it, then and "
      f"after, so the player never waits for what's there ({some})", some == list(range(2, 10)) and short.hold == 0)
lists, pieces, list_at, piece_at = reader()
four = A.List(BASE)
four.take(live_text(0, 4), BASE, list_at, piece_at)
check(f"...one with five pieces: four shown (three back from the end is where a player starts, and one more behind "
      f"it), one kept back ({len(shown(four))})", len(shown(four)) == 4 and four.hold == 1)


# ---- a pretend stream on this machine ----------------------------------------------------------------------------------
SIZE = 60000


def piece(k):
    return bytes([k % 251]) * SIZE


class Stream:
    """A stream whose list goes from first to edge (the test moves them on); dead while it's told to be (nothing
    gets through); a piece slow, or not there; and a note of everything it's asked, and how much at once."""

    def __init__(self, host="127.0.0.1"):
        self.first, self.edge, self.ended, self.grows = 0, 9, False, False
        self.far, self.sends = {}, {}                  # a piece -> the link it's listed by; the link it sends on to
        self.cut = {}                                  # a piece -> how many times it's hung up on, with not a word
        self.dead, self.slow, self.missing, self.tokens = False, {}, set(), 0
        self.asks, self.cookies, self.busy, self.most = [], [], 0, 0   # (a piece: "seg5.ts"; of its other version: "alt5.ts")
        self.film = 0                                  # (bytes of its film sent)
        self.lock = threading.Lock()
        stream = self

        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def hold(self):
                while stream.dead:
                    time.sleep(0.02)

            def do_GET(self):
                name = self.path.split("?")[0].lstrip("/")
                piece = name.endswith(".ts") and name != "film.ts"
                with stream.lock:
                    stream.asks.append(name)
                    if piece:
                        stream.busy += 1
                        stream.most = max(stream.most, stream.busy)
                        stream.cookies.append(self.headers.get("Cookie"))
                try:
                    self.answer(name)
                finally:
                    if piece:
                        with stream.lock:
                            stream.busy -= 1

            def answer(self, name):
                self.hold()
                if name == "film.ts":                  # (not in pieces at all: a long one)
                    self.send_response(200)
                    self.send_header("Content-Type", "video/mp2t")
                    self.send_header("Content-Length", str(50 << 20))
                    self.end_headers()
                    try:
                        for _ in range(50 << 4):
                            self.wfile.write(b"G" + bytes(65535))
                            self.wfile.flush()
                            stream.film += 65536
                    except OSError:
                        pass
                    return
                if name.endswith(".m3u8"):
                    stream.tokens += 1
                    first = 0 if stream.grows else stream.first
                    stem = "alt" if name == "b.m3u8" else "seg"
                    body = ("#EXTM3U\n#EXT-X-TARGETDURATION:1\n" + f"#EXT-X-MEDIA-SEQUENCE:{first}\n" + "".join(
                        f"#EXTINF:1.0,\n{stream.far.get(k) or f'{stem}{k}.ts?t={stream.tokens}'}\n"
                        for k in range(first, stream.edge + 1))
                        + ("#EXT-X-ENDLIST\n" if stream.ended else "")).encode()
                    if name == "master.m3u8":          # (two versions of it)
                        body = ("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360\na.m3u8\n"
                                "#EXT-X-STREAM-INF:BANDWIDTH=3000000,RESOLUTION=1280x720\nb.m3u8\n").encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/vnd.apple.mpegurl")
                    self.send_header("Set-Cookie", "ticket=abc123; Path=/; HttpOnly")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                k = int(name[3:].split(".")[0])
                if stream.cut.get(k, 0) > 0:           # (as when the network's away: known at once)
                    stream.cut[k] -= 1
                    self.close_connection = True
                    return
                if k in stream.missing:
                    return self.send_error(404)
                if k in stream.sends:
                    self.send_response(302)
                    self.send_header("Location", stream.sends[k])
                    self.send_header("Content-Length", "0")
                    return self.end_headers()
                body = piece(k)
                self.send_response(200)
                self.send_header("Content-Type", "video/mp2t")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    for i in range(0, len(body), 20000):
                        self.hold()
                        self.wfile.write(body[i:i + 20000])
                        self.wfile.flush()
                        time.sleep(stream.slow.get(k, 0))
                except OSError:
                    pass

        class Srv(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True

            def handle_error(self, request, client_address):
                pass

        self.srv = Srv((host, 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.at = f"http://{host}:{self.srv.server_address[1]}"

    def asked(self, k):
        return self.asks.count(f"seg{k}.ts")

    def pieces(self, stem="seg"):
        """(The pieces it's been asked for, in order.)"""
        return [int(x[3:-3]) for x in list(self.asks) if x.startswith(stem) and x.endswith(".ts")]


def ask(link, wait=8.0, first=False):
    """What this machine's address gives, as the player asks it: (status, its headers, its body, seconds it took,
    seconds to its first bytes)."""
    u = A.urllib.parse.urlsplit(link)
    conn = http.client.HTTPConnection(u.netloc, timeout=wait)
    t = time.monotonic()
    conn.request("GET", u.path)
    r = conn.getresponse()
    head = r.read(1000)
    t1 = time.monotonic() - t
    body = head + r.read()
    conn.close()
    return r.status, dict(r.getheaders()), body, time.monotonic() - t, t1


def names(body):
    return [x for x in body.decode().splitlines() if x and not x.startswith("#")]


def sent(link):
    """What this machine's address says to the player, when it's not the thing itself: (status, where it's sent)."""
    u = A.urllib.parse.urlsplit(link)
    conn = http.client.HTTPConnection(u.netloc, timeout=5)
    conn.request("GET", u.path)
    r = conn.getresponse()
    r.read()
    conn.close()
    return r.status, r.getheader("Location") or ""


A.LIST_LEAST, A.HOLD_SECS = 0.2, 2.0                   # (a second to a piece here: looked at twice a second)
st = Stream()
before = threading.active_count()
a = A.Ahead(st.at + "/live.m3u8")
local = a.start()
check(f"a stream opened: the player's given this machine's address for it ({local})", local is not None
      and local.startswith("http://127.0.0.1:") and local.endswith("/l0.m3u8") and a.token in local)
here = local.rsplit("/", 1)[0]
took = until(lambda: all(st.asked(k) for k in range(5, 10)), 5)
check(f"the pieces to come, fetched before they're asked for: from three back from the end the player's shown, on "
      f"({st.pieces()}); one at a time ({st.most})", took and st.pieces() == [5, 6, 7, 8, 9] and st.most == 1)
status, heads, body, secs, _ = ask(local)
shown_now = names(body)
check(f"the list, as the player's given it: this machine's names, the newest two seconds kept back ({shown_now[-3:]}); "
      f"answered at once ({secs * 1000:.0f} ms)", status == 200 and shown_now == [f"p{k}.ts" for k in range(8)]
      and secs < 0.3)
until(lambda: a.pieces[5].done and a.pieces[9].done, 3)
status, heads, body, secs, _ = ask(f"{here}/p5.ts")
check(f"a piece in hand: handed over at once ({secs * 1000:.0f} ms), as the stream sent it, and the stream's not "
      f"asked again", status == 200 and body == piece(5) and secs < 0.3 and st.pieces() == [5, 6, 7, 8, 9]
      and heads.get("Content-Length") == str(SIZE))
check(f"the cookie the stream gave with its list: given back with each piece ({st.cookies[-1]})",
      st.cookies and all(c == "ticket=abc123" for c in st.cookies))
st.first, st.edge = 1, 10                              # (the stream moves on a piece)
took = until(lambda: st.asked(10) == 1, 4)
check("the stream moves on: its new piece fetched without being asked for, once", took and st.most == 1)
status, _, body, _, _ = ask(local)
check(f"...and the player's shown one more ({names(body)[-1]})", names(body) == [f"p{k}.ts" for k in range(1, 9)])

# the network dead: answered at once all the same, with what's in hand
until(lambda: a.pieces[10].done, 3)
held = sorted(a.begun)
ask(f"{here}/p6.ts")
st.dead = True
t = time.monotonic()
status, _, body, secs, _ = ask(local)
got = [ask(f"{here}/p{k}.ts") for k in (7, 8)]
check(f"the stream dead: the list answered at once ({secs * 1000:.0f} ms), and the pieces in hand "
      f"({max(x[3] for x in got) * 1000:.0f} ms)", status == 200 and secs < 0.3 and all(x[0] == 200 for x in got)
      and [x[2] for x in got] == [piece(7), piece(8)] and max(x[3] for x in got) < 0.3)
took = until(lambda: names(ask(local)[2])[-1] == "p10.ts", 5)
check(f"...and still dead a couple of seconds on: the ones kept back are shown ({names(ask(local)[2])[-2:]}), so it "
      f"plays on ({time.monotonic() - t:.1f} s)", took and ask(f"{here}/p10.ts")[2] == piece(10))
st.dead = False
st.first, st.edge = 3, 12
took = until(lambda: st.asked(11) and st.asked(12) and a.pieces[12].done, 5)
status, _, body, _, _ = ask(local)
check(f"alive again: what it missed fetched ({names(body)[-1]} shown: never fewer than before)", took
      and names(body)[-1] == "p10.ts" and names(body)[0] == "p3.ts")
took = until(lambda: sorted(a.begun) == [9, 10, 11, 12], 3)
check(f"what the player's past: let go of ({held} held when it was on the fifth; on the tenth, {sorted(a.begun)})",
      took and held == [5, 6, 7, 8, 9, 10] and len(a.pieces[6].data) == 0 and not a.pieces[6].started)
status, _, body, _, _ = ask(f"{here}/p2.ts")
check(f"...one that's gone from the list, asked for all the same (a player that's far behind): fetched then "
      f"({st.pieces()[-1]})", status == 200 and body == piece(2) and st.asked(2) == 1)

# a piece on its way; one that can't be had
st.slow[13] = 0.4
st.first, st.edge = 4, 13
until(lambda: st.asked(13) == 1, 4)
status, heads, body, secs, first = ask(f"{here}/p13.ts")
check(f"a piece that's still coming: handed over as it comes (its first bytes after {first * 1000:.0f} ms, all of it "
      f"after {secs * 1000:.0f}), whole", status == 200 and body == piece(13) and first < secs - 0.3
      and st.asked(13) == 1)
st.missing.add(14)
st.first, st.edge = 5, 14
until(lambda: st.asked(14) >= 1 and a.pieces[14].failed, 4)
u = A.urllib.parse.urlsplit(f"{here}/p14.ts")
conn = http.client.HTTPConnection(u.netloc, timeout=5)
conn.request("GET", u.path)
r = conn.getresponse()
r.read()
check(f"a piece the stream won't give: the player's sent to ask for it itself ({r.status}, {r.getheader('Location')})",
      r.status == 302 and (r.getheader("Location") or "").startswith(st.at + "/seg14.ts"))
conn.close()
st.missing.clear()
check("...nothing else of this machine's to be had there: another's token, a piece that never was",
      ask(local.replace(a.token, "x" * 12))[0] == 404 and ask(f"{here}/p999.ts")[0] == 404
      and ask(f"{here}/q1.ts")[0] == 404)

# closed; no more held than there's room for
a.close()
took = until(lambda: socket.socket().connect_ex(("127.0.0.1", int(local.split(":")[2].split("/")[0]))) != 0, 3)
gone = until(lambda: threading.active_count() <= before, 5)
check(f"closed (the player's stopped): its address is gone, and nothing of it's left running "
      f"({threading.active_count() - before} more threads than before it)", took and a.closed and gone)
A.AHEAD_BYTES = 3 * SIZE + 1000
st2 = Stream()
st2.edge = 29
b = A.Ahead(st2.at + "/live.m3u8")
b.start()
until(lambda: len(b.begun) >= 4, 3)
time.sleep(0.6)
check(f"no more held than there's room for (three pieces' worth, here): of the five to come, four fetched "
      f"({sorted(b.begun)}: one's on its way before it's known how big it is)", sorted(b.begun) == [25, 26, 27, 28]
      and st2.most == 1)
b.close()
A.AHEAD_BYTES = 24 << 20

# the network away for a moment, known at once (no waiting for an answer): tried again by itself
A.RETRY_AFTER = 0.3
st7 = Stream()
st7.cut[7] = 2
q = A.Ahead(st7.at + "/live.m3u8")
qh = q.start().rsplit("/", 1)[0]
took = until(lambda: len(q.pieces) > 9 and q.pieces[7].done and q.pieces[9].done, 5)
check(f"a piece that couldn't be fetched, known at once (the network away a moment): tried again by itself "
      f"({st7.asked(7)} asks of it: two hung up on, then it came), and in hand", took and st7.asked(7) == 3
      and ask(f"{qh}/p7.ts")[2] == piece(7) and st7.asked(7) == 3 and not q.off)
q.close()

# a stream that says no to every piece asked of it from here: its pieces are left to the player
st8 = Stream()
st8.missing = set(range(100))
w8 = A.Ahead(st8.at + "/live.m3u8")
wl = w8.start()
took = until(lambda: w8.off, 5)
time.sleep(0.5)
asked = st8.pieces()
code, to = sent(wl.rsplit("/", 1)[0] + "/p9.ts")
check(f"a stream that says no to each piece asked of it from here ({asked}, and none fetched): left to the player, "
      f"sent for its pieces at once ({code}); nothing more asked of it from here; its lists still from here "
      f"({ask(wl)[0]})", took and asked == [5, 6, 7, 8] and code == 302 and to.startswith(st8.at + "/seg9.ts")
      and st8.pieces() == asked and ask(wl)[0] == 200)
w8.close()
A.RETRY_AFTER = 3.0

# a stream gone for good; what isn't a list
A.LIST_WAIT, A.GONE_AFTER = 1.0, 3.0                   # (an answer waited for a second here, a stream let go after three)
st3 = Stream()
c = A.Ahead(st3.at + "/live.m3u8")
there = c.start()
until(c.opened.is_set, 3)
st3.dead = True
t = time.monotonic()
codes = []
while time.monotonic() - t < 7 and (not codes or codes[-1] == 200):
    codes.append(ask(there, wait=3)[0])
    time.sleep(0.25)
check(f"a stream gone quiet for good: answered for a while with what there was, then let go, so the player stops "
      f"({codes[0]}... then {codes[-1]} after {time.monotonic() - t:.1f} s)", codes[0] == 200 and codes[-1] == 504
      and 2.5 < time.monotonic() - t < 6.5)
c.close()
A.LIST_WAIT, A.GONE_AFTER = 8.0, 30.0
st3.dead = False
d = A.Ahead(st3.at + "/film.ts")
t = time.monotonic()
code = ask(d.start())[0]
secs = time.monotonic() - t
time.sleep(0.3)
check(f"a stream that isn't in pieces: its player's told there's none here ({code}: it stops, and is played as "
      f"before), found out from its first bytes ({secs:.2f} s; {st3.film >> 10} KB of its {50 << 10} sent)",
      code == 504 and not d.ok and secs < 1.0 and st3.film < 4 << 20)
d.close()
others = [A.Ahead("http://127.0.0.1:9/none.m3u8"), A.Ahead("not a link at all")]
codes = [ask(x.start())[0] for x in others]
check(f"one that isn't there at all, one that's no link: the same ({codes})", codes == [504, 504])
for x in others:
    x.close()

# a list that grows from its start (a Plex video being made ready), then ends
A.HOLD_SECS = 12.0
st4 = Stream()
st4.grows, st4.edge = True, 1
f = A.Ahead(st4.at + "/grow.m3u8")
fl = f.start()
fh = fl.rsplit("/", 1)[0]
seen = [len(names(ask(fl)[2]))]
ask(f"{fh}/p0.ts")                                     # (the player starts on its first piece)
for edge in range(2, 8):
    st4.edge = edge
    until(lambda: len(names(ask(fl)[2])) == edge + 1, 3)
    seen.append(len(names(ask(fl)[2])))
took = until(lambda: sorted(f.begun) == list(range(8)), 3)
check(f"a list that grows from its start: all of it shown as it comes ({seen}), its pieces fetched as they're made "
      f"({sorted(f.begun)})", seen == list(range(2, 9)) and took and st4.most == 1)
ask(f"{fh}/p6.ts")
st4.ended = True
st4.edge = 9
took = until(lambda: ask(fl)[2].decode().rstrip().endswith("#EXT-X-ENDLIST"), 4)
looks = st4.asks.count("grow.m3u8")
time.sleep(1.2)
check(f"...and ends: its end shown, and it's not looked at again ({st4.asks.count('grow.m3u8') - looks} more looks)",
      took and st4.asks.count("grow.m3u8") == looks and len(names(ask(fl)[2])) == 10)
f.close()

# a stream in several versions: the player looks at each, tries a piece of each, and goes on with one
A.HOLD_SECS = 2.0
st6 = Stream()
h = A.Ahead(st6.at + "/master.m3u8")
ml = h.start()
mh = ml.rsplit("/", 1)[0]
top = names(ask(ml)[2])
both = [names(ask(f"{mh}/{x}")[2]) for x in top]
time.sleep(0.5)
check(f"a stream in two versions: each of them a list here ({top}), its pieces here too ({both[0][-1]}, {both[1][-1]}); "
      f"none fetched yet ({st6.pieces() + st6.pieces('alt')})", top == ["l1.m3u8", "l2.m3u8"]
      and both[0] == [f"p{k}.ts" for k in range(8)] and both[1] == [f"p{k}.ts" for k in range(10, 18)]
      and st6.pieces() + st6.pieces("alt") == [] and st6.asks.count("master.m3u8") == 1)
got = [ask(f"{mh}/p5.ts")[2] == piece(5), ask(f"{mh}/p15.ts")[2] == piece(5)]
time.sleep(0.5)
check(f"...the player tries a piece of each: fetched as it asks ({st6.pieces()}, {st6.pieces('alt')}), and no more",
      all(got) and st6.pieces() == [5] and st6.pieces("alt") == [5])
ask(f"{mh}/p6.ts")
took = until(lambda: sorted(st6.pieces()) == [5, 6, 7, 8, 9], 4)
time.sleep(0.5)
check(f"...and goes on with one: that one's fetched ahead ({sorted(st6.pieces())}), the other's left "
      f"({st6.pieces('alt')})", took and sorted(st6.pieces()) == [5, 6, 7, 8, 9] and st6.pieces("alt") == [5]
      and st6.most <= 2)
h.close()

# a stream from elsewhere that points at this machine itself: nothing of this machine's is fetched for it
try:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.connect(("10.255.255.255", 1))               # (this machine's address on its network: run.py --offline
    ME = probe.getsockname()[0]                        #  gives it one of its own)
    probe.close()
except OSError:
    ME = None
if not ME or ME.startswith("127."):
    print("(no address here but 127.0.0.1: a stream from elsewhere isn't tried)")
else:
    own = Stream()                                     # (something of this machine's own, on 127.0.0.1)
    far = Stream(ME)                                   # (a stream from elsewhere)
    far.far[7] = own.at + "/seg7.ts"                   # (one of its pieces: a link to this machine itself)
    far.sends[8] = own.at + "/seg8.ts"                 # (another sends whoever asks for it on to it)
    x = A.Ahead(far.at + "/live.m3u8")
    xh = x.start().rsplit("/", 1)[0]
    took = until(lambda: far.asked(9) == 1 and x.pieces[9].done and x.pieces[8].failed, 5)
    codes = [ask(f"{xh}/p{k}.ts")[0] for k in (6, 7)]
    u = A.urllib.parse.urlsplit(f"{xh}/p8.ts")
    conn = http.client.HTTPConnection(u.netloc, timeout=5)
    conn.request("GET", u.path)
    r = conn.getresponse()
    r.read()
    codes.append((r.status, (r.getheader("Location") or "").startswith(far.at + "/seg8.ts")))
    conn.close()
    check(f"a stream from elsewhere ({ME}), one piece a link to this machine itself, one sending on to it: neither "
          f"fetched from here ({own.asks}); the first not to be had (the player's not sent there either), the second "
          f"asked of the stream itself, as before ({codes})", took and not x.home and own.asks == []
          and codes == [200, 404, (302, True)] and far.pieces()[:4] == [5, 6, 8, 9])
    x.close()
    real_gai = socket.getaddrinfo
    socket.getaddrinfo = lambda host, *a, **k: real_gai("127.0.0.1" if host == "rebind.test" else host, *a, **k)
    y = A.Ahead(f"http://rebind.test:{own.at.rsplit(':', 1)[1]}/live.m3u8")
    code = ask(y.start())[0]
    socket.getaddrinfo = real_gai
    check(f"a stream by a name that turns out to be this machine itself: not opened ({code}), nothing asked of it "
          f"({own.asks})", code == 504 and not y.ok and own.asks == [])
    y.close()
    z = A.Ahead(own.at + "/live.m3u8")
    code = ask(z.start())[0]
    check(f"...one that's here by its own address (a Plex server on this machine): opened as any other ({code})",
          code == 200 and z.home)
    z.close()
A.HOLD_SECS = 12.0

# ---- media mode: a live channel's player is given this machine's address ---------------------------------------------
HOME = S + "/home/u"
os.makedirs(HOME + "/Music")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
spawned = []


class Proc:
    def __init__(self):
        self.stdin, self.code, self.args, self.said = io.StringIO(), None, [], []

    def poll(self):
        return self.code

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.code = -9


def spawn(self, args, target):
    self.started = time.monotonic()
    self.proc = Proc()
    self.proc.args = list(args) + [target]
    spawned.append(target)


real_spawn = g.Media.spawn
g.Media.spawn = spawn
g.Plex.live_url = lambda self, key: key                 # (the version that suits the screen: the test's own stream)
m = g.Media()
m.active = True
m.render_wait = lambda *a, **k: None
st5 = Stream()
tv = [{"title": "Pretend TV", "kind": "live", "src": "plexlive:" + st5.at + "/live.m3u8", "key": "live:1"},
      {"title": "Pretend FM", "kind": "radio", "src": st5.at + "/live.m3u8", "key": "radio:1"},
      {"title": "Gone TV", "kind": "live", "src": "plexlive:http://127.0.0.1:9/live.m3u8", "key": "live:2"},
      {"title": "A film", "kind": "live", "src": "plexlive:" + st5.at + "/film.ts", "key": "live:3"}]
m.play(tv, 0)
mine = m.ahead
check(f"a live channel: the player's given this machine's address ({spawned[-1]})", mine is not None
      and spawned[-1] == "ffmpeg://" + mine.address and until(lambda: st5.asked(9) == 1, 4))
m.stop()
check("...stopped: closed", m.ahead is None and mine.closed)
m.play(tv, 1)
check(f"a radio station: as ever ({spawned[-1][:40]})", m.ahead is None and st5.at in spawned[-1])
m.play(tv, 2)
mine, count = m.ahead, len(spawned)
m.proc.code = 1                                        # (told there's none here, its player stops at once)
m.tick()
check(f"a channel that can't be opened that way: its player's started again with its own address, as before "
      f"({spawned[-1]})", mine is not None and spawned[count - 1] == "ffmpeg://" + mine.address and mine.closed
      and len(spawned) == count + 1 and spawned[-1] == "ffmpeg://http://127.0.0.1:9/live.m3u8" and m.ahead is None
      and "127.0.0.1:9" in m.ahead_not)
m.proc.code = 1
m.tick()
check("...and it won't play as before either (it's down): so it wasn't how it was played, and its like are played "
      "with some in hand again", len(spawned) == count + 1 and m.kind is None and "127.0.0.1:9" not in m.ahead_not)
m.play(tv, 3)
code = ask(m.ahead.address)[0]
check(f"one that isn't in pieces: its player's told there's none here ({code})", code == 504)
m.stop()
m.play(tv, 0)
mine, count = m.ahead, len(spawned)
m.proc.code = 1                                        # (it stops as soon as it's started)
m.tick()
check(f"a channel that won't play that way (its player stops at once): played again as before ({spawned[-1]}), and "
      f"closed", len(spawned) == count + 1 and spawned[-1] == "ffmpeg://" + st5.at + "/live.m3u8" and m.ahead is None
      and mine.closed and m.kind == "live")
m.stop()
m.play(tv, 0)
check("...and the next from there too, for a while", m.ahead is None and spawned[-1] == "ffmpeg://" + st5.at + "/live.m3u8")
m.ahead_not = {}
film = {"title": "A film", "kind": "plexvideo", "src": "123", "key": "plex:123", "dur": 600, "off": 0}
m.plex.stream_url = lambda key, offset, session: f"{st5.at}/video/start.m3u8?session={session}"
m.play([film], 0)
mine, count = m.ahead, len(spawned)
check(f"a Plex video: its player's given this machine's address too ({spawned[-1][:32]}...)", mine is not None
      and spawned[-1] == "ffmpeg://" + mine.address and m.kind == "plex")
m.proc.code = 1
m.tick()
check(f"...and one that won't play that way: again as before, a conversion of its own asked for ({spawned[-1][-22:]})",
      len(spawned) == count + 1 and spawned[-1].startswith(f"ffmpeg://{st5.at}/video/start.m3u8?session=")
      and spawned[-1] != "ffmpeg://" + mine.link and m.ahead is None and mine.closed and m.kind == "plex")
m.stop()
m.plex.stream_url = lambda key, offset, session: f"{st5.at}/Videos/123/stream.ts"
m.ahead_not = {}
m.play([film], 0)
check("a video that comes whole (Jellyfin's): as before", m.ahead is None and spawned[-1].endswith("/stream.ts"))
m.stop()
os.environ["PITATO_AHEAD"] = "0"
m.play(tv, 0)
check("turned off (PITATO_AHEAD=0, as the other tests have it): every stream as before", m.ahead is None
      and spawned[-1] == "ffmpeg://" + st5.at + "/live.m3u8")
os.environ["PITATO_AHEAD"] = "1"
m.stop()

# ---- the real thing: mplayer playing a made-up channel whose network dies for a while --------------------------------
if shutil.which("mplayer") is None or shutil.which("ffmpeg") is None:
    print("(no mplayer and FFmpeg here: the real thing isn't played)")
else:
    V = S + "/video"
    os.makedirs(V)
    made = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25", "-f", "lavfi",
         "-i", "sine=frequency=440:sample_rate=44100", "-t", "60", "-c:v", "libx264", "-preset", "ultrafast", "-b:v", "400k",
         "-g", "50", "-keyint_min", "50", "-sc_threshold", "0", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "64k",
         "-f", "hls", "-hls_time", "2", "-hls_list_size", "0", "-hls_segment_filename", V + "/seg%03d.ts", V + "/all.m3u8"],
        capture_output=True, text=True)
    count = len([n for n in os.listdir(V) if n.endswith(".ts")])
    if made.returncode != 0 or count < 25:
        print(f"(FFmpeg here couldn't make the channel: {made.stderr.strip()[-200:]})")
    else:
        class Channel:
            """A live channel of that video: six pieces listed, a new one every two seconds; dead from 8 s to 12 s."""

            def __init__(self, dead=(8.0, 12.0)):
                channel = self
                self.t0, self.dead = time.monotonic(), dead

                class H(http.server.BaseHTTPRequestHandler):
                    protocol_version = "HTTP/1.1"

                    def log_message(self, *a):
                        pass

                    def hold(self):
                        while channel.dead[0] <= time.monotonic() - channel.t0 < channel.dead[1]:
                            time.sleep(0.02)

                    def do_GET(self):
                        name = self.path.split("?")[0].lstrip("/")
                        self.hold()
                        if name.endswith(".m3u8"):
                            last = min(count - 1, 5 + int((time.monotonic() - channel.t0) / 2))
                            body = ("#EXTM3U\n#EXT-X-TARGETDURATION:2\n" + f"#EXT-X-MEDIA-SEQUENCE:{last - 5}\n" + "".join(
                                f"#EXTINF:2.0,\nseg{k:03d}.ts\n" for k in range(last - 5, last + 1))).encode()
                        else:
                            try:
                                body = open(V + "/" + name, "rb").read()
                            except OSError:
                                return self.send_error(404)
                        self.send_response(200)
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        try:
                            for i in range(0, len(body), 8192):   # (no faster than three times as fast as it plays)
                                self.hold()
                                self.wfile.write(body[i:i + 8192])
                                time.sleep(8192 / 180000)
                        except OSError:
                            pass

                class Srv(socketserver.ThreadingMixIn, http.server.HTTPServer):
                    daemon_threads = True

                    def handle_error(self, request, client_address):
                        pass
                self.srv = Srv(("127.0.0.1", 0), H)
                threading.Thread(target=self.srv.serve_forever, daemon=True).start()
                self.at = f"http://127.0.0.1:{self.srv.server_address[1]}/live.m3u8"

        def watched(through):
            """The channel played for 22 seconds: (seconds its picture stood still, in all; seconds it played)."""
            ch = Channel()
            ahead = A.Ahead(ch.at) if through else None
            ch.t0 = time.monotonic()
            link = (ahead.start() if ahead else None) or ch.at
            p = subprocess.Popen(["mplayer", "-slave", "-quiet", "-vo", "null", "-ao", "null", "-nolirc", "-framedrop",
                                  "-cache", "4096", "-cache-min", "5", "ffmpeg://" + link], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, errors="replace")
            said = []

            def read():
                for line in p.stdout:
                    if line.startswith("ANS_TIME_POSITION="):
                        try:
                            said.append((time.monotonic() - ch.t0, float(line.split("=")[1])))
                        except ValueError:
                            pass
            threading.Thread(target=read, daemon=True).start()
            while time.monotonic() - ch.t0 < 22 and p.poll() is None:
                try:
                    p.stdin.write("pausing_keep_force get_time_pos\n")
                    p.stdin.flush()
                except OSError:
                    break
                time.sleep(0.1)
            try:
                p.stdin.write("quit\n")
                p.stdin.flush()
                p.wait(timeout=3)
            except Exception:
                p.kill()
            if ahead:
                ahead.close()
            ch.srv.shutdown()
            moving = [(t, pos) for (t, pos), (_, nxt) in zip(said, said[1:]) if nxt > pos]
            if not moving:
                return None, 0.0
            start = moving[0][0]
            played = said[-1][1] - moving[0][1]
            return max(0.0, (said[-1][0] - start) - played), played

        gone = A.Ahead("http://127.0.0.1:9/none.m3u8")
        t = time.monotonic()
        subprocess.run(["mplayer", "-quiet", "-vo", "null", "-ao", "null", "-nolirc", "ffmpeg://" + gone.start()],
                       stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
        secs = time.monotonic() - t
        gone.close()
        check(f"the real thing, a stream that can't be opened from here: mplayer stops at once ({secs:.1f} s), in time "
              f"to be started again as before", secs < 4.0)
        A.LIST_LEAST, A.HOLD_SECS = 1.0, 12.0
        still, played = watched(True)
        check(f"the real thing (mplayer, a channel whose network's dead for 4 of its 22 seconds), with some in hand: "
              f"its picture never stands still ({still if still is None else round(still, 2)} s in all; {played:.1f} s "
              f"played)", still is not None and still < 1.0 and played > 18)
        plain, played = watched(False)
        print(f"(as it was before, on the same: its picture still for {plain if plain is None else round(plain, 2)} s "
              f"in all; {played:.1f} s played)")

        # media mode, starting mplayer its own way (with no screen or sound to play to, here)
        launched = []

        def spy(self, args, target):
            launched.append(target)
            return real_spawn(self, args, target)

        def ticks(secs, done=lambda: False):
            end = time.monotonic() + secs
            while time.monotonic() < end and not done():
                m.tick()
                time.sleep(0.1)
            return done()

        g.Media.spawn = spy
        m.video_args = lambda: ["mplayer", "-slave", "-quiet", "-nolirc", "-vo", "null", "-nosound"]
        m.ahead_not = {}
        ch = Channel(dead=(1e9, 1e9))
        real = [{"title": "Real TV", "kind": "live", "src": "plexlive:" + ch.at, "key": "live:9"}, tv[2]]
        m.play(real, 0)
        mine, p = m.ahead, m.proc
        ticks(7)
        check(f"media mode, mplayer started its own way: the channel plays from here ({mine.lists[0].asks} pieces "
              f"asked for in seven seconds, {len(mine.begun)} in hand)", p is m.proc and p.poll() is None
              and launched == ["ffmpeg://" + mine.address] and mine.lists[0].asks >= 2 and len(mine.begun) >= 2)
        m.stop()
        check("...stopped: mplayer's gone, and it's closed", until(lambda: p.poll() is not None, 5) and mine.closed
              and m.ahead is None)
        m.play(real, 1)
        mine = m.ahead
        over = ticks(15, lambda: m.kind is None)
        check(f"...a channel that's down: tried from here, then as before, then let go ({len(launched) - 1} goes)",
              over and launched[1:] == ["ffmpeg://" + mine.address, "ffmpeg://http://127.0.0.1:9/live.m3u8"]
              and m.ahead is None and "127.0.0.1:9" not in m.ahead_not)

print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}", flush=True)
os._exit(0)
