"""Covers for the songs that have none, found on the internet (Y on Music). MusicBrainz says which record a song is on,
going by its tags (the artist and the album; or the artist and the song's name) or, for a song with no tags, by its
file's name ("Artist - Title"); the Cover Art Archive has that record's front cover. Both are free and ask for no
account. MusicBrainz asks for no more than one question a second, and to be told who's asking. Only a sure match is
taken (a wrong cover is worse than none), and a compilation's cover isn't. What's found is kept with the covers got out
of songs' files (cover.py looks there): one picture for each record, its songs sharing it."""
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

from .cover import cover_file, COVER_SIDE, found_file

MB_URL = "https://musicbrainz.org/ws/2/{what}?query={query}&fmt=json&limit=5"
ART_URL = "https://coverartarchive.org/release-group/{mbid}/front-500"
MB_GAP = 1.1                     # seconds between questions to MusicBrainz
SURE = 90                        # how sure of a match MusicBrainz must be (its score, out of 100)
TRIES = 3                        # records tried for a song's cover, the likeliest first
MISS_KEPT = 30 * 86400           # seconds before a song nothing was found for is asked about again
TAGS_WAIT, NET_WAIT = 10, 20     # seconds ffprobe may take over a song's tags, and an answer from the internet
NET_GIVES_UP = 3                 # questions in a row with no answer: it stops (the WiFi's down)
TRACK_NO = re.compile(r"^\s*(?:\d{1,3}\s*[-._)]+|0\d(?=\s))\s*")   # "03 ", "3. ", "12 - " before a song's name
EXTRA = re.compile(r"\s*[(\[][^)\]]*[)\]]")                        # (Official Video), [Lyrics] and the like
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
    """Who a song's by and what it's called, going by its file's name: "Artist - Title", a track number before it
    left off. A name that doesn't say who: ("", the name)."""
    stem = TRACK_NO.sub("", os.path.splitext(os.path.basename(path))[0].replace("_", " "))
    artist, dash, title = stem.partition(" - ")
    if dash and artist.strip() and title.strip():
        return artist.strip(), title.strip()
    return "", stem.strip()


def wanted(path, run=None):
    """What to ask about a song: (who it's by, the record it's on, its name), from its tags, and from its file's
    name what they don't say."""
    tags = song_tags(path, run)
    artist, title = from_name(path)
    return tags["artist"] or artist, tags["album"], tags["title"] or title


def plain(text):
    """A name with nothing in it to trip a comparison: small letters and numbers only, what's in brackets left out."""
    text = unicodedata.normalize("NFKD", EXTRA.sub("", str(text).lower()))
    return "".join(c for c in text if c.isalnum())


def same(a, b):
    """Two names are one: the same once plain ("Nevermind" and "Nevermind (Remastered)" are), or one most of the
    other, if it's long enough to be sure of ("Queen" isn't "Queen II")."""
    a, b = sorted((plain(a), plain(b)), key=len)
    return bool(a) and (a == b or (len(a) >= 8 and len(a) >= 0.6 * len(b) and a in b))


def said(text):
    """A name as a search for just it takes it: in quotes, what's special to the search made plain."""
    return '"' + SPECIAL.sub(r"\\\1", EXTRA.sub("", text).strip() or text) + '"'


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


def missed(path, now=None):
    """Nothing was found for this song lately: it isn't asked about again yet."""
    try:
        return (time.time() if now is None else now) - os.path.getmtime(found_file(path)[:-4] + ".none") < MISS_KEPT
    except OSError:
        return False


class CoverFinder:
    """Finds covers for the songs that have none, a song at a time, on a thread of its own (as the games' pictures
    are found). on_change(): it's got somewhere; on_found(song): that song has a cover now. note: what it says when
    it's done (taken once)."""

    def __init__(self, fetch=fetch, run=None, pause=time.sleep, clock=time.monotonic):
        self.fetch, self.run_ffprobe, self.pause, self.clock = fetch, run, pause, clock
        self.busy = False
        self.done = self.total = self.found = 0
        self.note = ""
        self.asked_at = None                           # when MusicBrainz was last asked something
        self.on_change = lambda: None
        self.on_found = lambda path: None

    def start(self, songs, thread=True):
        """False if it's busy already, or there are no songs."""
        songs = list(songs)
        if self.busy or not songs:
            return False
        self.busy, self.done, self.total, self.found, self.note = True, 0, len(songs), 0, ""
        if thread:
            threading.Thread(target=self.run, args=(songs,), daemon=True, name="cover-finder").start()
        else:
            self.run(songs)
        return True

    def ask(self, what, query):
        """MusicBrainz, asked (never more than once in MB_GAP seconds; told to slow down: once more, a little
        later)."""
        url = MB_URL.format(what=what, query=urllib.parse.quote(query))
        for again in (True, False):
            if self.asked_at is not None:
                self.pause(max(0.0, MB_GAP - (self.clock() - self.asked_at)))
            self.asked_at = self.clock()
            try:
                got = json.loads(self.fetch(url))
                return got if isinstance(got, dict) else {}
            except urllib.error.HTTPError as ex:
                if ex.code != 503 or not again:
                    raise
                self.pause(2.0)
        return {}

    def front(self, mbid):
        """A record's front cover from the Cover Art Archive (a picture's bytes), or None: it has none there."""
        try:
            return self.fetch(ART_URL.format(mbid=mbid))
        except urllib.error.HTTPError as ex:
            if ex.code in (400, 404):
                return None
            raise

    def look(self, artist, album, title, out):
        """A cover for a song, looked for and kept at out: whether one was found."""
        for mbid in records(artist, album, title, self.ask):
            data = self.front(mbid)
            if data:
                try:
                    keep(data, out)
                    return True
                except (OSError, ValueError):          # (not a picture after all: the next record's)
                    continue
        return False

    def run(self, songs):
        asked, lost, reached = {}, 0, False            # (what's been asked this time: where its cover is, or None)
        try:
            for path in songs:
                try:
                    if cover_file(path) or missed(path):
                        continue
                    artist, album, title = wanted(path, self.run_ffprobe)
                    key = (plain(artist), plain(album), "" if album else plain(title))
                    out = found_file(path)
                    if not key[0] or not (key[1] or key[2]):
                        got = None                     # (nothing to go by: who it's by isn't said anywhere)
                    elif key in asked:
                        got = asked[key]
                    else:
                        got = asked[key] = out if self.look(artist, album, title, out) else None
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
                        open(out[:-4] + ".none", "w").close()
                except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as ex:
                    print(f"covers: no answer about {os.path.basename(path)} ({ex!r})", flush=True)
                    lost += 1
                    if lost >= NET_GIVES_UP:
                        break
                except OSError as ex:                  # (nowhere to keep it, or the song's gone)
                    print(f"covers: {os.path.basename(path)}: {ex!r}", flush=True)
                finally:
                    self.done += 1
                    self.on_change()
            if self.found:
                self.note = f"Found covers for {self.found} song{'s' if self.found != 1 else ''}"
            elif lost and not reached:
                self.note = "Couldn't reach MusicBrainz. Check the WiFi"
            else:
                self.note = "No covers found for these songs"
        except Exception as ex:                        # (never leaves it stuck on "busy")
            print(f"covers: finding them: {ex!r}", flush=True)
            self.note = "Couldn't find covers just now"
        finally:
            self.busy = False
            self.on_change()
