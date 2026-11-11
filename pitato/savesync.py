"""Each Pietato keeps its own game saves: none of your others' ever takes their place (Settings > Share with other
Pietatos). A game sent to another of yours (Play on another Pietato) is that one's guest: its saves go with it, into a
folder of their own there (Games/Saves/.guests, a folder for each Pietato a game's come from), and that Pietato's own
save of the game stays as it is. What's played there goes back to the Pietato whose game it is: when it's sent back,
when it's done there (that one's told, and asks for it), or when that one next starts the game (it asks). Only ever
on from where that one left it: one that's played the game itself meanwhile keeps its own save, and the guest stays
where it is. A save a newer one takes the place of is kept, the last one only, in .replaced beside it.

Each Pietato's web page answers the others on your network (webui.py: /api/saves, /api/saves/file, /api/saves/home).
How old a save is, is told in seconds (not as a time of day), so two Pis' clocks needn't agree."""
import hashlib
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request

SAVE_EXTS = (".srm", ".rtc", ".state", ".state.cheevos", ".state.auto", ".state.auto.cheevos")   # a game's own,
                                                     # named for it (its in-game save, its clock, its saved states)
SAVE_MOST = 64 << 20         # bytes: a save bigger than this stays where it is
ASK_TIMEOUT = 2.0            # a Pietato on your network answers quickly, or not at all
GET_TIMEOUT = 30.0           # ...a save on its way: this long at most
TELL_TIMEOUT = 2.0
REPLACED = ".replaced"       # (in a folder of saves: the save a newer one took the place of)
GUESTS = ".guests"           # (in the Saves folder: the saves of games come from your others, a folder for each one)
GUEST = ".guest"             # ...and beside a game's saves there, a note: whose game it is, and what it came on from
SUM = re.compile(r"[0-9a-f]{40}")
WHOSE = re.compile(r"[a-z0-9]{6,32}")   # a Pietato, for whose a game's saves are (its own word for itself, kept)
WHO_MOST = 60                # letters of a Pietato's name, as a note keeps it
GUESTS_MOST = 16             # guests of one game, as another Pietato lists them: no more looked at


def game_name(name):
    """A game's name for its saves (games.py's save_name), as another Pietato may send it: a plain file name, or None."""
    if not isinstance(name, str) or not 0 < len(name) <= 200 or name.startswith("."):
        return None
    if "/" in name or "\\" in name or "\0" in name or name != name.strip() or name in (".", ".."):
        return None
    return name


def file_sum(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def save_files(saves, name, now=None):
    """A game's saves here: {ext: {"size", "age": seconds since it was written, "sum": its SHA-1}}."""
    out, now = {}, time.time() if now is None else now
    if game_name(name) is None:
        return out
    for ext in SAVE_EXTS:
        path = os.path.join(saves, name + ext)
        try:
            st = os.stat(path)
            if not os.path.isfile(path) or st.st_size > SAVE_MOST:
                continue
            out[ext] = {"size": st.st_size, "age": max(0.0, now - st.st_mtime), "sum": file_sum(path)}
        except OSError:
            continue
    return out


def clean_files(files):
    """Another Pietato's list of a game's saves, only as much of it as makes sense."""
    out = {}
    if not isinstance(files, dict):
        return out
    for ext, f in files.items():
        if ext not in SAVE_EXTS or not isinstance(f, dict):
            continue
        size, age, sm = f.get("size"), f.get("age"), f.get("sum")
        if (isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= SAVE_MOST
                or isinstance(age, bool) or not isinstance(age, (int, float)) or not 0 <= age < 1e10
                or not isinstance(sm, str) or not SUM.fullmatch(sm)):
            continue
        out[ext] = {"size": size, "age": float(age), "sum": sm}
    return out


def newest(files):
    """The youngest of a game's saves (seconds), or None for none."""
    return min((f["age"] for f in files.values()), default=None)


def ask_json(url, timeout=ASK_TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": "Pietato"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read(1 << 20))


def fetch_file(url, dest, size, timeout=GET_TIMEOUT):
    """A save, into dest: True once it's all there (no more than size bytes)."""
    req = urllib.request.Request(url, headers={"User-Agent": "Pietato"})
    end = time.monotonic() + timeout
    got = 0
    with urllib.request.urlopen(req, timeout=ASK_TIMEOUT * 3) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            got += len(chunk)
            if got > size or time.monotonic() > end:
                return False
            f.write(chunk)
    return got == size


def ask_all(peers, name, ask=ask_json):
    """What each of your other Pietatos has of a game's saves, asked at once: [((url, host), its answer or None)]."""
    answers = [None] * len(peers)

    def one(i, url):
        try:
            answers[i] = ask(f"{url}/api/saves?game={urllib.parse.quote(name)}")
        except (OSError, ValueError):
            answers[i] = None
    threads = [threading.Thread(target=one, args=(i, url), daemon=True) for i, (url, _) in enumerate(peers)]
    for t in threads:
        t.start()
    end = time.monotonic() + ASK_TIMEOUT + 0.5
    for t in threads:
        t.join(max(0.0, end - time.monotonic()))
    return list(zip(peers, answers))


def whose_id(x):
    """A Pietato's word for itself (whose a game's saves are), or None for anything else."""
    return x if isinstance(x, str) and WHOSE.fullmatch(x) else None


def clean_who(x):
    """A Pietato's name, as another says it: a line of it, or ""."""
    return " ".join(x.split())[:WHO_MOST] if isinstance(x, str) else ""


def sums(files):
    """A game's saves, as their sums alone ({ext: sum}): two lots the same are the same saves."""
    return {ext: f["sum"] for ext, f in files.items()}


def clean_base(base):
    """What a guest came on from (the sums of its Pietato's own saves then), only as much as makes sense."""
    if not isinstance(base, dict):
        return {}
    return {ext: sm for ext, sm in base.items() if ext in SAVE_EXTS and isinstance(sm, str) and SUM.fullmatch(sm)}


# ---- guests: the saves of a game come from another of yours, apart from this one's own ---------------------------
def guest_dir(saves, whose):
    return os.path.join(saves, GUESTS, whose)


def guest_note(saves, whose, name):
    """A guest's note: {"from": whose game it is (its name), "via": the one it came here from, "base": what it came
    on from}, or None when there's no such guest here."""
    if whose_id(whose) is None or game_name(name) is None:
        return None
    try:
        with open(os.path.join(guest_dir(saves, whose), name + GUEST)) as f:
            got = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(got, dict):
        return None
    return {"from": clean_who(got.get("from")), "via": clean_who(got.get("via")), "base": clean_base(got.get("base"))}


def guest_keep(saves, whose, name, who, via, base, owner=None):
    """A guest's note, written (its folder made, the Games folder's owner's)."""
    folder = guest_dir(saves, whose)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name + GUEST)
    with open(path + ".part", "w") as f:
        json.dump({"from": clean_who(who), "via": clean_who(via), "base": clean_base(base)}, f)
    os.replace(path + ".part", path)
    if owner:
        for made in (os.path.join(saves, GUESTS), folder, path):
            os.chown(made, *owner)


def guests_of(saves, name):
    """The guests of a game here: {whose: {"from", "via", "base", "files"}} (each with its saves: a note with none
    isn't one)."""
    out = {}
    if game_name(name) is None:
        return out
    try:
        ids = sorted(os.listdir(os.path.join(saves, GUESTS)))
    except OSError:
        return out
    for whose in ids:
        note = guest_note(saves, whose, name)
        files = save_files(guest_dir(saves, whose), name) if note is not None else {}
        if files:
            out[whose] = dict(note, files=files)
    return out


def guests_held(saves):
    """Every guest here: [(whose, the game's name)]."""
    out = []
    try:
        ids = sorted(os.listdir(os.path.join(saves, GUESTS)))
    except OSError:
        return out
    for whose in ids:
        if whose_id(whose) is None:
            continue
        try:
            names = sorted(os.listdir(guest_dir(saves, whose)))
        except OSError:
            continue
        out += [(whose, n[:-len(GUEST)]) for n in names if n.endswith(GUEST) and game_name(n[:-len(GUEST)])]
    return out


def guest_gone(saves, whose, name):
    """A guest let go of (it's gone home, or you've said to forget it): its saves put in .replaced beside them (the
    last one's kept, as ever), its note taken away."""
    if whose_id(whose) is None or game_name(name) is None:
        return
    folder = guest_dir(saves, whose)
    keep = os.path.join(folder, REPLACED)
    for ext in SAVE_EXTS:
        src = os.path.join(folder, name + ext)
        if os.path.isfile(src):
            os.makedirs(keep, exist_ok=True)
            os.replace(src, os.path.join(keep, name + ext))
    try:
        os.remove(os.path.join(folder, name + GUEST))
    except OSError:
        pass


# ---- what another Pietato says it has ---------------------------------------------------------------------------
def clean_answer(got):
    """Another Pietato's word for a game's saves there, only as much of it as makes sense: {"id": its word for itself,
    "name", "playing": its own being played now, "own": its own saves, "guests": {whose: {"from", "base", "files",
    "playing"}}}; None from one that isn't sharing, or answers nonsense. (One from before each Pietato's saves were
    its own says no id: nothing of its is taken.)"""
    if not isinstance(got, dict) or got.get("on") is not True:
        return None
    pid = whose_id(got.get("id"))
    guests = {}
    theirs = got.get("guests") if pid else None
    for whose, gst in (list(theirs.items())[:GUESTS_MOST] if isinstance(theirs, dict) else []):
        files = clean_files(gst.get("files")) if isinstance(gst, dict) and whose_id(whose) else {}
        if files:
            guests[whose] = {"from": clean_who(gst.get("from")), "base": clean_base(gst.get("base")),
                             "files": files, "playing": gst.get("playing") is True}
    return {"id": pid, "name": clean_who(got.get("name")), "playing": got.get("playing") is True,
            "own": clean_files(got.get("own")) if pid else {}, "guests": guests}


def take(dest, name, url, files, whose="", fetch=fetch_file, owner=None):
    """A game's saves from another Pietato (files: as it lists them; whose: its guest's, or "" for its own), into the
    folder dest: all of them that aren't the same there already, or none (a save and where you left off go together).
    What they take the place of is kept in dest/.replaced (the last one), and so is any save of the game there that
    the other hasn't got: dest ends with just what the other has. True once it has."""
    name = game_name(name)
    if name is None:
        return False
    mine = save_files(dest, name)
    todo = {ext: f for ext, f in files.items() if not (ext in mine and mine[ext]["sum"] == f["sum"])}
    parts = {}
    try:
        os.makedirs(dest, exist_ok=True)
        for ext, f in todo.items():
            parts[ext] = os.path.join(dest, f".{name}{ext}.part")
            q = urllib.parse.urlencode(dict({"game": name, "ext": ext}, **({"whose": whose} if whose else {})))
            if not fetch(f"{url}/api/saves/file?{q}", parts[ext], f["size"]) or file_sum(parts[ext]) != f["sum"]:
                raise OSError(f"{name}{ext} didn't come whole")
        keep = os.path.join(dest, REPLACED)
        aside = [ext for ext in mine if ext in todo or ext not in files]
        if aside:
            os.makedirs(keep, exist_ok=True)
            if owner:
                os.chown(keep, *owner)
        if owner:
            os.chown(dest, *owner)
        for ext in aside:                              # (what they replace, and what the other hasn't: kept)
            os.replace(os.path.join(dest, name + ext), os.path.join(keep, name + ext))
        now = time.time()
        for ext, part in parts.items():
            path = os.path.join(dest, name + ext)
            os.replace(part, path)
            age = todo[ext]["age"]
            os.utime(path, (now - age, now - age))     # (as old as it is there: the next look sees the same)
            if owner:
                os.chown(path, *owner)
        return True
    except OSError as ex:
        print(f"saves: {name} from {url}: {ex}", flush=True)
        return False
    finally:
        for part in parts.values():
            try:
                os.remove(part)
            except OSError:
                pass


def home(saves, name, me, peers, ask=ask_json, fetch=fetch_file, owner=None, on_fetch=None):
    """This Pietato's own game, come home: played on as a guest on another of yours (peers: [(its address, its name)])
    from just where this one left it (the guest came on from this one's saves as they are now), and not being played
    there now. The newest such guest's saves take the place of this one's (which are kept, in .replaced). The name of
    the Pietato they came from, or None: nothing's taken from a guest that came on from anything else (this one's
    played it since: its own save stays)."""
    name, me = game_name(name), whose_id(me)
    if name is None or me is None or not peers:
        return None
    base = sums(save_files(saves, name))
    best = None
    for (url, host), got in ask_all(peers, name, ask):
        said = clean_answer(got)
        gst = said["guests"].get(me) if said else None
        if gst is None or gst["playing"] or gst["base"] != base or sums(gst["files"]) == base:
            continue
        n = newest(gst["files"])
        if best is None or n < best[0]:
            best = (n, url, host, gst["files"])
    if best is None:
        return None
    _, url, host, files = best
    if on_fetch:
        on_fetch(host)
    return host if take(saves, name, url, files, whose=me, fetch=fetch, owner=owner) else None


def is_home(files, said, whose):
    """A guest's saves here (files) are its Pietato's own now (said: what that one says it has): it's gone home."""
    return bool(said) and said["id"] == whose and bool(files) and sums(said["own"]) == sums(files)


def is_there(files, said, whose):
    """...or another of yours has just those as its guest (it was sent on to it), or as its own (it's home)."""
    if not said or not files:
        return False
    gst = said["guests"].get(whose)
    return is_home(files, said, whose) or (gst is not None and sums(gst["files"]) == sums(files))


def post_json(url, body, timeout=TELL_TIMEOUT):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "Pietato"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read(1 << 16))


def tell_home(name, whose, peers, post=post_json):
    """Your other Pietatos told a game of one of them (whose) has been played on here, as a guest: the one whose it is
    takes it home (it asks for it). How many were told."""
    name, whose = game_name(name), whose_id(whose)
    if name is None or whose is None:
        return 0
    told = 0
    for url, _ in peers:
        try:
            post(f"{url}/api/saves/home", {"game": name, "whose": whose})
            told += 1
        except (OSError, ValueError):
            pass
    return told
