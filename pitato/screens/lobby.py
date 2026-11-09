"""What everyone's playing: your other Pietatos' games, on the home screen, from what each one's beacon says it's playing
(media.py's share_beacon: lobby_mine). X watches one (its game runs here too, from its buttons alone: sharp, and next to
no network used: netplay.py's watching); SELECT joins it as player 2 (screens/together.py's playing together, asked for
from here); L and R go through them. The one playing is asked (POST /api/together: watch, or join): it opens its game to
this one (watchhost, nethost) and says where, with a key and which game it is; the game's copied over first if this one
hasn't got it. A game watched here: its menu is Back, Volume, Picture and Stop watching, and nothing of it is kept."""
import os
import secrets
import shutil
import threading
import time
import urllib.parse

from ..config import CACHE_DIR
from ..games import find_core, find_games, GAME_SYSTEMS, GameRun, games_dir, save_name, SAVES_FOLDER, system
from ..handoff import (clean_ident, copy_game, copy_place, GAME_COPY_MOST, game_ident, HANDOFF_GO, local_game,
                       not_sent, TOKEN)
from ..netplay import NET_PORT, WATCH_PORT
from ..screen import aplay_device, screen_turn, sound_place
from .handoff import ONE_FILE
from .together import gone_words, NET_SYSTEMS, together_post

WATCH_SYSTEMS = ("gb", "gbc", "gba", "nes", "snes", "genesis", "sms", "gg", "ngp", "ngpc", "neogeo")   # (its emulator
                              # plays the same game from the same buttons, every time: watched by running it here too)
LOBBY_WITHIN = 90.0           # seconds since another's beacon said what it's playing: it still is


class LobbyScreen:
    """Your other Pietatos' games on the home screen, to watch or to join; this one's, watched by them."""

    # -- this one's game, as your others' lobbies have it ------------------------------------------------------------
    def lobby_mine(self):
        """What this one's playing, for your others' home screens (its beacon): None while it isn't (or it's watching
        another's game, or it's player 2 in another's: that one says so)."""
        run = self.game
        if run is None or run.ended or getattr(run, "attract", False) or run.state not in ("on", "paused") \
                or self.watching_of(run):
            return None
        g = run.game
        t = self.together_of(run)
        if t is not None and (t.get("link") or not t.get("host")):
            return None
        n = getattr(run, "watchers", 0)
        return {"title": (g.get("title") or "")[:60], "system": g.get("system") or "",
                "watch": g.get("system") in WATCH_SYSTEMS, "join": g.get("system") in NET_SYSTEMS and t is None,
                "with": t["with"] if t is not None else "",    # (player 2's, or coming)
                "watchers": n if isinstance(n, int) and not isinstance(n, bool) else 0}

    def lobby_asked(self, kind, url, host):
        """POST /api/together, watch or join (another of yours, from its home screen): this one's game opened to it (to
        watch: to any of yours with the key; to join as player 2: to it alone), and which game it is, with where and
        the key (and a key to copy the game, if it's small enough to). Or why not."""
        run, mine = self.game, self.lobby_mine()
        if mine is None:
            return {"ok": False, "error": "It isn't playing a game now"}
        if kind == "watch" and not mine["watch"]:
            return {"ok": False, "error": "That game can't be watched"}
        if kind == "join" and not mine["join"]:
            return {"ok": False, "error": "It's playing with someone already" if mine["with"] or self.together_of(run)
                    else "That game is one player's"}
        g = run.game
        try:
            ident = game_ident(g["path"], games_dir(), g["system"], g["title"], save_name(g["path"]))
        except OSError:
            return {"ok": False, "error": "Couldn't read the game"}
        if kind == "watch":
            port, key = getattr(run, "watch_port", None), getattr(run, "watch_key", None)
            if port is None:
                key = secrets.token_urlsafe(16)
                what, rest = run.ask(f"watchhost {WATCH_PORT} {key}", ("watchhost",), 3)
                words = rest.split()
                if what != "watchhost" or words[:1] != ["ok"] or len(words) < 2 or not words[1].isdigit():
                    print(f"lobby: couldn't open the game to watch ({rest})", flush=True)
                    return {"ok": False, "error": "Its game couldn't be opened to watch"}
                port = run.watch_port = int(words[1])
                run.watch_key = key
            run.watch_who = (getattr(run, "watch_who", None) or []) + [host]   # (said by name as it comes)
        else:
            key = secrets.token_urlsafe(16)
            what, rest = run.ask(f"nethost {NET_PORT} {key} {urllib.parse.urlsplit(url).hostname}", ("nethost",), 3)
            words = rest.split()
            if what != "nethost" or words[:1] != ["ok"] or len(words) < 2 or not words[1].isdigit():
                print(f"lobby: couldn't open the game to {host} ({rest})", flush=True)
                return {"ok": False, "error": "Its game couldn't be opened to join"}
            port = int(words[1])
            run.together = {"with": host, "url": url, "host": True, "link": False, "state": "coming",
                            "since": time.monotonic()}
            run.send(f"notice {host} is joining as player 2")
            self.share_news()                          # (your others' lobbies: not one to join any more)
        copy = ident["size"] <= GAME_COPY_MOST and not g["path"].lower().endswith(ONE_FILE)
        print(f"lobby: {host} {'watches' if kind == 'watch' else 'joins'} {g['title']}", flush=True)
        return {"ok": True, "ident": ident, "port": port, "key": key,
                "file": self.handoff_keys().issue(g["path"]) if copy else ""}

    def watched_tick(self, run):
        """This one's game, watched: who's come said on its picture, and your others' lobbies told how many watch."""
        news = getattr(run, "net_news", None)
        if not news:
            return
        keep = []
        for what, rest in news:
            if what == "watchjoined":
                waiting = getattr(run, "watch_who", None) or []
                who = waiting.pop(0) if waiting else ""
                run.send(f"notice {who or 'One of your Pietatos'} is watching")
            elif what == "watchers":
                self.share_news()
            elif what != "watchleft":
                keep.append((what, rest))
        news[:] = keep

    # -- your others' games, on the home screen ----------------------------------------------------------------------
    def lobby_entries(self):
        """Your other Pietatos playing a game now: [{"url", "host", "title", "system", "watch", "join", "with",
        "watchers"}], by name."""
        pie = getattr(self, "pie", None)
        if pie is None or self.setting("share") == "Off":
            return []
        names = dict(self.saves_peers())               # (as they're shown: two of a name told apart)
        now = time.time()
        with pie.lock:
            rows = [(u, dict(h)) for u, h in pie.heard.items()
                    if h.get("peer") and h.get("game") and now - h.get("seen", 0) <= LOBBY_WITHIN and u in names]
        return sorted((dict(h["game"], url=u, host=names[u]) for u, h in rows), key=lambda e: (e["host"].lower(), e["url"]))

    def lobby_now(self):
        """The one shown on the home screen (L and R go through them), or None."""
        entries = self.lobby_entries()
        if not entries:
            return None
        return entries[getattr(self, "lobby_pick", 0) % len(entries)], len(entries)

    def lobby_words(self, e, n):
        """The home screen's card for it: (its first line, the game, the line under it)."""
        known = next((s for s in GAME_SYSTEMS if s[0] == e["system"]), None)
        bits = [known[2].split(" / ")[0] if known else e["system"].upper()]   # (Genesis / Mega Drive: Genesis)
        if e["with"]:
            bits.append(f"with {e['with']}")
        if e["watchers"]:
            bits.append(f"{e['watchers']} watching")
        return f"{e['host']} is playing", e["title"], "  ·  ".join(bits)

    def lobby_hints(self):
        """The home screen's buttons for it: X to watch, SELECT to join (as each can be)."""
        got = self.lobby_now()
        if got is None or self.now_popped():
            return []
        e, n = got
        return ([("X", "Watch")] if e["watch"] else []) + ([("SELECT", "Join")] if e["join"] else []) \
            + ([("L R", "Others")] if n > 1 else [])

    def press_lobby(self, name):
        """X, SELECT, L or R on the home screen, for your others' games: True if it was one of theirs."""
        got = self.lobby_now()
        if got is None or name not in ("x", "select", "l", "r"):
            return False
        e, n = got
        if name in ("l", "r"):
            self.lobby_pick = (getattr(self, "lobby_pick", 0) + (1 if name == "r" else -1)) % n
            self.dirty = True
            return True
        kind = "watch" if name == "x" else "join"
        if not e[kind]:
            self.toast("That game can't be watched" if kind == "watch" else
                       f"{e['host']} is playing with someone already" if e["with"] else "That game is one player's", 3)
            return True
        self.lobby_go(kind, e)
        return True

    def lobby_go(self, kind, e):
        """Watch it, or join it as player 2: the one playing it asked; then its game, opened here (copied over first,
        if this one hasn't got it)."""
        url, host = e["url"], e["host"]
        if not self.saves_peers(urllib.parse.urlsplit(url).hostname):
            self.toast(f"{host} isn't on now", 3)
            return
        self.toast(f"Asking {host}…", 4)
        self.flush()                                   # (said before it waits for the answer)
        said = together_post(url, {"kind": kind}, HANDOFF_GO)
        if said is None:
            self.toast(f"{host} not responding", 4)
            return
        if not said.get("ok"):
            self.toast(not_sent(host, said), 5)
            return
        ident, port, key, file = clean_ident(said.get("ident")), said.get("port"), said.get("key"), said.get("file") or ""
        if (ident is None or isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536
                or not isinstance(key, str) or not TOKEN.fullmatch(key) or not isinstance(file, str)
                or (file and not TOKEN.fullmatch(file))):
            self.toast(f"{host} said something odd", 4)
            return
        why = self.handoff_game_cant(ident["system"])
        if why:
            self.toast(why, 5)
            return
        spec = f"{urllib.parse.urlsplit(url).hostname}:{port}:{key}"
        mine = local_game(games_dir(), ident, [g["path"] for g in find_games() if g["system"] == ident["system"]],
                          save_name)
        g = {"path": mine, "title": ident["title"], "system": ident["system"]}
        if mine is not None:
            self.lobby_start(kind, g, host, url, spec)
            return
        dest = copy_place(games_dir(), ident)          # (it hasn't got it: from the other, first)
        if dest is None:
            self.toast("This Pietato has another game by that name", 4)
            return
        if not file:
            self.toast(f"This Pietato doesn't have {ident['title']}. Put it in its Games folder too", 5)
            return
        owner = self.saves_owner()
        self.toast(f"Copying {ident['title']} from {host}…", 5)

        def copy():
            try:
                copy_game(f"{url}/api/handoff/file?token={file}", dest, ident, owner)
            except OSError as ex:
                print(f"lobby: {ident['title']} from {host}: {ex}", flush=True)
                self.soon_jobs.append(lambda: self.toast(f"Couldn't copy {ident['title']} from {host}", 5))
            else:
                g["path"] = dest
                self.soon_jobs.append(lambda: self.lobby_start(kind, g, host, url, spec) if self.game is None else None)
            self.wake()
        threading.Thread(target=copy, daemon=True, name="lobby-game").start()

    def lobby_start(self, kind, g, host, url, spec):
        if kind == "join":
            return self.together_start(g, False, host, url, net=spec)
        return self.watch_start(g, host, url, spec)

    # -- watching another's game ------------------------------------------------------------------------------------
    def watching_of(self, run=None):
        """Whose game this one's watching ({"with": its name, "url"}), or None (one of its own: or none)."""
        run = self.game if run is None else run
        w = getattr(run, "watching", None) if run is not None else None
        return w if isinstance(w, dict) else None

    def watch_start(self, g, who, url, spec):
        """Another's game, watched here: this one's emulator runs it too, from its state and then its buttons (nothing
        of it kept here: a folder of its own for its saves, emptied first)."""
        core = find_core(g["system"])
        if not core:
            self.toast(f"This Pietato can't play {system(g['system'])[2]} games", 4)
            return None
        folder = os.path.join(CACHE_DIR, "watch", SAVES_FOLDER)
        shutil.rmtree(folder, ignore_errors=True)
        os.makedirs(folder, exist_ok=True)
        hints = [("HOME", "Its menu")]
        self.stop()                                    # (music, a video: the game has the speaker)
        self.view = "game"
        self.render_curtain(g["title"], f"Watching {who}'s game…", hints=hints)
        run = GameRun(g, on_change=self.game_changed)
        run.watching = {"with": who, "url": url}
        place = sound_place(self.setting("sound"))
        try:
            turn = screen_turn()
            run.start(core, sound=aplay_device(None, place[0]), volume=self.volume,
                      picture=self.game_picture(g["system"]), resume=False, cheevos=False, saves=folder, watch=spec,
                      **({"turn": turn} if turn else {}))
        except OSError as ex:
            print(f"lobby: couldn't start {g['path']}: {ex}", flush=True)
            self.view = "home"
            self.toast("Couldn't start the game", 4)
            return None
        self.game, self.game_menu, self.game_sound = run, None, place
        self.game_since = time.monotonic()
        self.stick_sent = {}
        self.ds_dirs = set()
        self.game_players = {}
        print(f"lobby: watching {g['title']} on {who}", flush=True)
        return run

    def watch_tick(self, run):
        """A game watched here: the one playing it ended it (or stopped answering): so does this one, saying so."""
        while run.net_news:
            what, why = run.net_news.pop(0)
            if what == "watchgone":
                run.error = gone_words(run.watching["with"], why)

    def watch_note(self):
        """What a game's menu says under its title while it's watched here, or ""."""
        w = self.watching_of()
        return f"Watching {w['with']}'s game" if w else ""
