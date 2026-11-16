"""Covers for the songs that have none (Y on Music). First your other Pietatos that are on are asked: the same song
there (the same file name, the same size) with a cover has it copied here, which is quick, and a cover one of yours
found needn't be found again. The rest are looked up on the internet, going by a song's tags (who it's by, the record
it's on, its name) or, for a song with no tags, by its file's name ("Song - Artist" or "Artist - Song": either way
round). The iTunes Store's search is asked first: it knows nearly every song, and its answer says where the record's
picture is. For what it doesn't have, MusicBrainz says which record a song is on, and the Cover Art Archive has that
record's front cover. All three are free and ask for no account; the Store asks for no more than twenty questions a
minute, MusicBrainz for one a second and to be told who's asking. Only a likely match is taken (the song's name, or
who it's by, is the answer's), and from MusicBrainz never a compilation's cover. What's found is kept with the
covers got out of songs' files (cover.py looks there): one picture for each record, its songs sharing it."""
import collections
import io
import json
import os
import re
import shutil
import subprocess
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

from .cover import cover_at_hand, cover_file, COVER_SIDE, found_file
from .savesync import post_json

MB_URL = "https://musicbrainz.org/ws/2/{what}?query={query}&fmt=json&limit=5"
ART_URL = "https://coverartarchive.org/release-group/{mbid}/front-500"
SHOP_URL = "https://itunes.apple.com/search?term={words}&media=music&entity={what}&limit=10"
SHOP_ART = "100x100bb", "600x600bb"   # the size in a picture's address there, and the size asked for instead
SHOP_MOST, SHOP_SPAN = 18, 60.0  # questions the Store's asked in any minute (it asks for no more than twenty)
SHOP_BUSY = 30.0                 # ...and seconds it's left alone when it says that's too many all the same
MB_GAP = 1.1                     # seconds between questions to MusicBrainz
SURE = 90                        # how sure of a match MusicBrainz must be (its score, out of 100)
TRIES = 3                        # records tried for a song's cover, the likeliest first
MISS_KEPT = 30 * 86400           # seconds before a song nothing was found for is asked about again
MISS = ".miss"                   # ...which a file of this kind, by where its cover would be, says
TAGS_WAIT, NET_WAIT = 10, 20     # seconds ffprobe may take over a song's tags, and an answer from the internet
NET_GIVES_UP = 3                 # questions in a row with no answer: it stops (the WiFi's down)
PEER_ASKED = 100                 # songs one of your Pietatos is asked about at a time (and answers about, at most)
PEER_WAIT = 20                   # seconds it has to say
TRACK_NO = re.compile(r"^\s*(?:\d{1,3}\s*[-._)]+|0\d(?=\s))\s*")   # "03 ", "3. ", "12 - " before a song's name
EXTRA = re.compile(r"\s*[(\[][^)\]]*[)\]]")                        # (Official Video), [Lyrics] and the like
ALSO = re.compile(r"\s+(?:feat|ft|featuring)\b\.?\s.*$", re.I)       # " feat. Somebody Else", and all after it
SPECIAL = re.compile(r'([+\-&|!(){}\[\]^"~*?:\\/])')               # what a search takes as its own


def agent():
    """Who's asking, as MusicBrainz wants to be told: Pietato, and where it lives."""
    from .update import REPO_MOVED
    return {"User-Agent": f"Pietato/1.0 ( https://github.com/{next(iter(REPO_MOVED.values()))} )"}


def fetch(url, timeout=NET_WAIT):
    with urllib.request.urlopen(urllib.request.Request(url, headers=agent()), timeout=timeout) as r:
        return r.read(8_000_000)


def song_tags(path, run=None):
    """What a song's tags say of who it's by, the record it's on and its name ({"artist", "album", "title"}, each ""
    where they don't), as ffprobe reads them."""
    run = run or subprocess.run
    tags = {}
    try:
        out = run(["ffprobe", "-v", "error", "-show_entries", "format_tags:stream_tags", "-of", "json", path],
                  stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=TAGS_WAIT)
        data = json.loads(out.stdout or b"{}")
        for part in [data.get("format") or {}] + list(data.get("streams") or []):
            for k, v in (part.get("tags") or {}).items():
                tags.setdefault(k.lower(), str(v).strip())
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        pass
    return {"artist": tags.get("artist") or tags.get("album_artist") or "", "album": tags.get("album") or "",
            "title": tags.get("title") or ""}


def from_name(path):
    """The two sides of a song's file's name ("Artist - Song", or "Song - Artist": which is which isn't known), a
    track number before them left off. A name that isn't two: ("", the name)."""
    stem = TRACK_NO.sub("", os.path.splitext(os.path.basename(path))[0].replace("_", " "))
    artist, dash, title = stem.partition(" - ")
    if dash and artist.strip() and title.strip():
        return artist.strip(), title.strip()
    return "", stem.strip()


def wanted(path, run=None):
    """What to ask about a song: (who it's by, the record it's on, its name, either), from its tags, and from its
    file's name what they don't say: the side of it that isn't what a tag says. either: both are from the file's
    name, and may be the other way round."""
    tags = song_tags(path, run)
    one, two = from_name(path)
    artist, title = tags["artist"], tags["title"]
    if artist and not title:
        title = one if one and same(two, artist) else two
    elif title and not artist:
        artist = two if one and same(one, title) else one
    elif not artist:
        artist, title = one, two
    return artist, tags["album"], title, bool(one) and not tags["artist"] and not tags["title"]


def bare(text):
    """A name without what's been added to it: what's in brackets, and who else is on it (" feat. Somebody")."""
    text = str(text)
    return ALSO.sub("", EXTRA.sub("", text)).strip() or text.strip()


def plain(text):
    """A name with nothing in it to trip a comparison: small letters and numbers only, what's added to it left
    out."""
    text = unicodedata.normalize("NFKD", bare(text).lower())
    return "".join(c for c in text if c.isalnum())


def same(a, b):
    """Two names are one: the same once plain ("Nevermind" and "Nevermind (Remastered)" are), or one most of the
    other, if it's long enough to be sure of ("Queen" isn't "Queen II")."""
    a, b = sorted((plain(a), plain(b)), key=len)
    return bool(a) and (a == b or (len(a) >= 8 and len(a) >= 0.6 * len(b) and a in b))


def said(text):
    """A name as a search for just it takes it: in quotes, what's special to the search made plain."""
    return '"' + SPECIAL.sub(r"\\\1", bare(text)) + '"'


def by(item, artist):
    """One of MusicBrainz's answers is credited to this artist."""
    return any(same(c.get("name") or (c.get("artist") or {}).get("name") or "", artist)
               for c in item.get("artist-credit") or [] if isinstance(c, dict))


def records(artist, album, title, ask):
    """The records a song's cover might be on, the likeliest first (MusicBrainz's ids for them, TRIES at most): the
    one its tags name, by that artist; else the ones a song of that name by that artist is on, a record of the
    artist's own before a single. Nothing sure: none. ask(what, query): MusicBrainz's answer, as it's read."""
    out = []
    if artist and album:
        got = ask("release-group", f"releasegroup:{said(album)} AND artist:{said(artist)}")
        out = [g["id"] for g in got.get("release-groups") or []
               if g.get("id") and int(g.get("score") or 0) >= SURE and same(g.get("title", ""), album)
               and by(g, artist)]
    if not out and artist and title:
        got = ask("recording", f"recording:{said(title)} AND artist:{said(artist)}")
        ranked = []
        for r in got.get("recordings") or []:
            if int(r.get("score") or 0) < SURE or not same(r.get("title", ""), title) or not by(r, artist):
                continue
            for rel in r.get("releases") or []:
                g = rel.get("release-group") or {}
                kind = g.get("primary-type")
                if g.get("id") and kind in ("Album", "Single", "EP") and not g.get("secondary-types"):
                    ranked.append((0 if kind == "Album" else 1, len(ranked), g["id"]))   # (not a compilation's,
        out = [mbid for _, _, mbid in sorted(ranked)]                                  #  a soundtrack's, a live one's)
    return list(dict.fromkeys(out))[:TRIES]


def art_at(item):
    """Where the picture of one of the Store's answers is, at the size a cover's kept, or None: it has none."""
    url = item.get("artworkUrl100")
    return url.replace(*SHOP_ART) if isinstance(url, str) and url.startswith("https://") else None


def shop_art(artist, album, title, either, ask):
    """Where a song's cover is in the iTunes Store (a picture's address), or None: nothing there is likely it. The
    record its tags name, by that artist before anyone (a compilation is by nobody in particular); else a song: that
    name by that artist first, then that name by somebody (who it's by, spelt another way), then another of that
    artist's. either: its name and who it's by may be the other way round. ask(what, words): the Store's answers
    (a list), as it's read."""
    if artist and album:
        got = [g for g in ask("album", f"{bare(artist)} {bare(album)}")
               if art_at(g) and same(g.get("collectionName") or "", album)]
        got.sort(key=lambda g: not same(g.get("artistName") or "", artist))
        if got:
            return art_at(got[0])
    best = None
    if artist and title:
        for r in ask("song", f"{bare(artist)} {bare(title)}"):
            who, name = r.get("artistName") or "", r.get("trackName") or ""
            for by_, called in ((artist, title), (title, artist))[:2 if either else 1]:
                rank = 0 if same(who, by_) and same(name, called) else 1 if same(name, called) else 2
                if (rank < 2 or same(who, by_)) and art_at(r) and (best is None or rank < best[0]):
                    best = (rank, art_at(r))
    return best[1] if best else None


def keep(data, out):
    """A picture from the internet, kept as a song's cover (a JPEG, COVER_SIDE a side at most): a file that isn't a
    picture isn't (ValueError, OSError)."""
    from PIL import Image
    im = Image.open(io.BytesIO(data))
    im.load()
    im = im.convert("RGB")
    im.thumbnail((COVER_SIDE, COVER_SIDE))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    im.save(out + ".part", "JPEG", quality=90)
    os.replace(out + ".part", out)


def song_key(path):
    """What says a song here and one on another Pietato are the same song: its file's name, and its size."""
    try:
        return [os.path.basename(path), os.path.getsize(path)]
    except OSError:
        return [os.path.basename(path), -1]


def cover_bytes(path):
    """A cover as it's sent to another Pietato: a JPEG, COVER_SIDE a side at most."""
    from PIL import Image
    im = Image.open(path)
    im.draft("RGB", (COVER_SIDE, COVER_SIDE))
    im = im.convert("RGB")
    im.thumbnail((COVER_SIDE, COVER_SIDE))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=90)
    return out.getvalue()


def covers_had(songs, mine):
    """(One of yours asks.) Which of the songs it lists ([[file name, size]]) this one has a cover to hand for:
    their numbers in its list. mine: this one's songs, {(name in small letters, size): path}."""
    have = []
    for i, key in enumerate(songs[:PEER_ASKED]):
        if isinstance(key, (list, tuple)) and len(key) == 2 and isinstance(key[0], str):
            path = mine.get((key[0].lower(), key[1]))
            if path and cover_at_hand(path):
                have.append(i)
    return have


def missed(path, now=None):
    """Nothing was found for this song lately: it isn't asked about again yet."""
    try:
        return (time.time() if now is None else now) - os.path.getmtime(found_file(path)[:-4] + MISS) < MISS_KEPT
    except OSError:
        return False


class CoverFinder:
    """Finds covers for the songs that have none, a song at a time, on a thread of its own (as the games' pictures
    are found). on_change(): it's got somewhere; on_found(song): that song has a cover now. note: what it says when
    it's done (taken once)."""

    def __init__(self, fetch=fetch, run=None, pause=time.sleep, clock=time.monotonic, peers=None, post=post_json):
        self.fetch, self.run_ffprobe, self.pause, self.clock = fetch, run, pause, clock
        self.peers, self.post = peers or (lambda: []), post   # (your other Pietatos that are on: [(address, name)])
        self.busy = False
        self.done = self.total = self.found = self.shared = 0
        self.note = ""
        self.last = {}                                 # when each place was asked something, the last few times
        self.on_change = lambda: None
        self.on_found = lambda path: None
        self.known = lambda path: False                # (a song known to have a cover: not looked at again)

    def start(self, songs, thread=True):
        """False if it's busy already, or there are no songs."""
        songs = list(songs)
        if self.busy or not songs:
            return False
        self.busy, self.done, self.total, self.found, self.shared, self.note = True, 0, len(songs), 0, 0, ""
        if thread:
            threading.Thread(target=self.run, args=(songs,), daemon=True, name="cover-finder").start()
        else:
            self.run(songs)
        return True

    def asked(self, who, most, span, url, busy, wait):
        """One of the places covers are looked up, asked: never more than most times in any span seconds, and told
        that's too many all the same (one of busy's answers), once more, wait seconds later. What it said, as it's
        read ({}: not an answer)."""
        times = self.last.setdefault(who, collections.deque(maxlen=most))
        for again in (True, False):
            if len(times) == most:
                self.pause(max(0.0, span - (self.clock() - times[0])))
            times.append(self.clock())
            try:
                got = json.loads(self.fetch(url))
                return got if isinstance(got, dict) else {}
            except urllib.error.HTTPError as ex:
                if ex.code not in busy or not again:
                    raise
                self.pause(wait)
        return {}

    def ask(self, what, query):
        """MusicBrainz, asked."""
        return self.asked("mb", 1, MB_GAP, MB_URL.format(what=what, query=urllib.parse.quote(query)), (503,), 2.0)

    def shop(self, what, words):
        """The iTunes Store's search, asked: its answers."""
        url = SHOP_URL.format(what=what, words=urllib.parse.quote(words))
        got = self.asked("shop", SHOP_MOST, SHOP_SPAN, url, (403, 429), SHOP_BUSY).get("results")
        return [r for r in got if isinstance(r, dict)] if isinstance(got, list) else []

    def front(self, mbid):
        """A record's front cover from the Cover Art Archive (a picture's bytes), or None: it has none there."""
        try:
            return self.fetch(ART_URL.format(mbid=mbid))
        except urllib.error.HTTPError as ex:
            if ex.code in (400, 404):
                return None
            raise

    def from_shop(self, artist, album, title, out, either):
        """A song's cover from the iTunes Store, kept at out: whether it has one."""
        url = shop_art(artist, album, title, either, self.shop)
        if not url:
            return False
        try:
            keep(self.fetch(url), out)
            return True
        except urllib.error.HTTPError as ex:
            if ex.code not in (400, 403, 404):         # (the picture isn't there after all)
                raise
        except (OSError, ValueError):                  # (...or isn't a picture)
            pass
        return False

    def from_archive(self, artist, album, title, out, either):
        """...and from the Cover Art Archive, going by what MusicBrainz says."""
        for by_, called in ((artist, title), (title, artist))[:2 if either else 1]:
            for mbid in records(by_, album, called, self.ask):
                data = self.front(mbid)
                if data:
                    try:
                        keep(data, out)
                        return True
                    except (OSError, ValueError):      # (not a picture after all: the next record's)
                        continue
        return False

    def look(self, artist, album, title, out, either=False):
        """A cover for a song, looked for and kept at out: whether one was found. A place that didn't answer, and
        nothing from the other: its error (the song isn't put down as having none)."""
        failed = None
        for place in (self.from_shop, self.from_archive):
            try:
                if place(artist, album, title, out, either):
                    return True
            except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as ex:
                print(f"covers: {place.__name__[5:]}: no answer ({ex!r})", flush=True)
                failed = failed or ex
        if failed:
            raise failed
        return False

    def got(self, path):
        self.found += 1
        self.done += 1
        self.on_found(path)
        self.on_change()

    def from_peers(self, todo):
        """Your other Pietatos, asked for the covers of these songs: what they have is copied here. The songs still
        without one."""
        try:
            peers = list(self.peers())
        except Exception as ex:
            print(f"covers: your others aren't known ({ex!r})", flush=True)
            peers = []
        for url, name in peers:
            if not todo:
                break
            keys, have = [song_key(p) for p in todo], set()
            try:
                for i in range(0, len(keys), PEER_ASKED):
                    said = self.post(f"{url}/api/covers", {"songs": keys[i:i + PEER_ASKED]}, timeout=PEER_WAIT)
                    have |= {i + k for k in (said.get("have") or []) if isinstance(k, int) and 0 <= k < PEER_ASKED}
            except Exception as ex:                    # (it isn't answering, or it's an older one: the next)
                print(f"covers: {name} wasn't asked ({ex!r})", flush=True)
                continue
            left = []
            for k, path in enumerate(todo):
                ok = False
                if k in have:
                    try:
                        q = urllib.parse.urlencode({"name": keys[k][0], "size": keys[k][1]})
                        keep(self.fetch(f"{url}/api/covers/file?{q}"), found_file(path))
                        ok = True
                    except Exception as ex:
                        print(f"covers: {name}'s for {keys[k][0]} didn't come ({ex!r})", flush=True)
                if ok:
                    self.shared += 1
                    self.got(path)
                else:
                    left.append(path)
            todo = left
        return todo

    def run(self, songs):
        asked, lost, reached = {}, 0, False            # (what's been asked this time: where its cover is, or None)
        offline = False                                # (nothing answered at all, the last time one didn't)
        try:
            todo = []
            for path in songs:                         # (the ones with none: looked into once, the first time)
                if self.known(path) or cover_file(path):
                    self.done += 1
                    self.on_change()
                else:
                    todo.append(path)
            for path in self.from_peers(todo):
                try:
                    if missed(path):
                        continue
                    artist, album, title, either = wanted(path, self.run_ffprobe)
                    key = (plain(artist), plain(album), "" if album else plain(title))
                    out = found_file(path)
                    if not key[0] or not (key[1] or key[2]):
                        got = None                     # (nothing to go by: who it's by isn't said anywhere)
                    elif key in asked:
                        got = asked[key]
                    else:
                        got = asked[key] = out if self.look(artist, album, title, out, either) else None
                        reached, lost = True, 0
                    if got and got != out:             # (another song of the same record: the same picture)
                        try:
                            os.link(got, out)
                        except OSError:
                            shutil.copyfile(got, out)
                    if got:
                        self.found += 1
                        self.on_found(path)
                    else:
                        os.makedirs(os.path.dirname(out), exist_ok=True)
                        open(out[:-4] + MISS, "w").close()
                except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as ex:
                    print(f"covers: no answer about {os.path.basename(path)} ({ex!r})", flush=True)
                    lost += 1
                    offline = not isinstance(ex, (urllib.error.HTTPError, ValueError))
                    if lost >= NET_GIVES_UP:
                        break
                except OSError as ex:                  # (nowhere to keep it, or the song's gone)
                    print(f"covers: {os.path.basename(path)}: {ex!r}", flush=True)
                finally:
                    self.done += 1
                    self.on_change()
            if self.found:
                self.note = f"Found covers for {self.found} song{'s' if self.found != 1 else ''}" + (
                    f", {self.shared} from your other Pietatos" if self.shared else "")
            elif lost and not reached:
                self.note = "Couldn't look covers up. " + ("Check the WiFi" if offline else "Try again in a minute")
            else:
                self.note = "No covers found for these songs"
        except Exception as ex:                        # (never leaves it stuck on "busy")
            print(f"covers: finding them: {ex!r}", flush=True)
            self.note = "Couldn't find covers just now"
        finally:
            self.busy = False
            self.on_change()
