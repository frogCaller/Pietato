"""Party mode (pitato/party.py), started from HOME's menu on Now playing: each of your other Pietatos that's on, and isn't
in a game, a video or the terminal, plays what this one plays, in step with it, through its own speaker. This one leads:
its songs, one after another, and its stations. A, ◀▶, L, R and START on any of them pause it, move about in a song or
skip, for all of them; HOME's menu on the leader ends it, and on another leaves it (it stops there). Each keeps its own
volume and sound (Settings > Sound). POST /api/party (webui.py) carries what the leader says, and what the others ask."""
import os
import re
import secrets
import threading
import time
import urllib.parse

from ..asyou import as_you
from ..config import home_dir
from ..library import LISTEN_KINDS
from ..party import (ClockServer, clock_offset, PARTY_LEAD, PARTY_PORT, PartyPlayer, PartyProc, probe, Relay,
                     RelayServer)
from .glow import GLOW_LEAD, GLOW_SOON
from ..screen import aplay_device, sound_place
from .. import savesync

PARTY_WAIT = 4.0             # seconds each of your others has to say it's in
PARTY_PING_EVERY = 30.0      # seconds between a follower's looks at the leader's clock (clocks drift apart)
PARTY_GONE = 3.0             # seconds the leader's had no party music: the party's over
PARTY_SOON = 0.6             # seconds from a pause (or playing on) to its happening on all of them
PARTY_ASKS = ("pause", "next", "back", "ahead", "behind")   # what another can ask the leader to do, for all of them
PATH = re.compile(r"/[A-Za-z0-9/_.?=&%-]{1,300}")


def party_post(url, body, timeout=3.0):
    """Another Pietato's answer (a dict) to what's said of the party, or None when it doesn't answer."""
    try:
        got = savesync.post_json(url + "/api/party", body, timeout=timeout)
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) else None


class PartyScreen:
    """Party mode: leading one (this one's music, on all of yours, in step), or in another's."""
    party = None      # leading: {"lead": True, "token", "members": {url: name}, "clock", "server", "relay", "song"};
                      # in another's: {"lead": False, "leader": url, "name", "token", "port", "offset", "pinged"}

    def party_on(self):
        return self.party is not None

    def party_leading(self):
        return self.party is not None and self.party.get("lead") is True

    def party_label(self):
        """Its row in HOME's menu on Now playing: what it does now, or None (nobody to have a party with)."""
        if self.party_leading():
            return "End party mode"
        if self.party_on():
            return "Leave the party"
        return "Party mode" if self.kind in LISTEN_KINDS and self.saves_peers() else None

    def party_job(self):
        """Its row picked: party mode started, ended, or left."""
        if self.party_leading():
            self.party_end(say=True)
        elif self.party_on():
            self.party_leave(say=True)
        else:
            self.party_start()

    # -- leading one ------------------------------------------------------------------------------------------------
    def party_start(self):
        """Your others that are on asked to join; then what's playing here starts again on all of them at once, in
        step, from where it is."""
        if self.kind not in LISTEN_KINDS or not self.cur or not self.proc:
            self.toast("Play some music first", 3)
            return
        peers = self.saves_peers()
        if not peers:
            self.toast("None of your other Pietatos is on", 3)
            return
        token = secrets.token_urlsafe(16)
        try:
            clock, server = ClockServer(token), RelayServer(token)
        except OSError as ex:
            print(f"party: couldn't start ({ex})", flush=True)
            self.toast("Couldn't start party mode", 4)
            return
        self.toast("Asking your other Pietatos…", 5)
        self.flush()
        said = {}

        def ask(url):
            said[url] = party_post(url, {"kind": "start", "token": token, "port": PARTY_PORT}, PARTY_WAIT)
        jobs = [threading.Thread(target=ask, args=(url,), daemon=True) for url, _ in peers]
        for j in jobs:
            j.start()
        for j in jobs:
            j.join(PARTY_WAIT + 0.5)
        members = {url: host for url, host in peers if (said.get(url) or {}).get("ok")}
        if not members:
            clock.close()
            server.close()
            why = next((s.get("error") for s in said.values() if s and s.get("error")), "")
            self.toast(f"None of them could join{': ' + why if why and len(peers) == 1 else ''}", 4)
            return
        self.party = {"lead": True, "token": token, "members": members, "clock": clock, "server": server,
                      "relay": None, "song": "", "since": time.monotonic(), "quiet": None}
        names = list(members.values())
        self.toast("Party mode with " + (names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]), 5)
        print(f"party: leading, with {', '.join(names)}", flush=True)
        pos = (self.pos or 0) if self.kind == "audio" else 0
        self.play(self.queue, self.qi, start=max(0, pos), show=False)   # (on all of them: play() comes back here)

    def party_play(self, it, kind, target, start):
        """(play(), leading a party.) It, here and on each of yours at once: a moment from now, from where it is, each
        taking it from here (a song: from this one's web page; a station: passed on from this one, byte for byte, or
        each its own if it can't be). Not in a party, but an LED grid wants its beat (screens/glow.py): just here, on
        the same player (a station passed through here all the same: for its song's names)."""
        p = self.party
        at = time.monotonic() + (PARTY_LEAD if p is not None else GLOW_LEAD)
        pos = max(0.0, float(start or 0)) if kind == "audio" else 0.0
        title = artist = ""
        length = None
        if kind == "radio":
            st = p if p is not None else self.glow_station_for()
            relay = st["relay"]
            if relay is None or relay.url != target or relay.gone is not None:
                if relay is not None:
                    relay.close()
                relay = st["relay"] = Relay(target)
                st["server"].relay = relay
                st["song"] = ""
            port = st["server"].port
            if relay.ready(3.0):
                path = f"/station?token={st['token']}&from={relay.start_byte()}"
                mine, theirs = f"http://127.0.0.1:{port}{path}", {"port": port, "path": path}
            else:                                      # (it can't be passed on: each takes it, all at once)
                print(f"party: {it['title']} can't be passed on ({relay.gone}): each takes it", flush=True)
                relay.close()
                st["relay"] = st["server"].relay = None
                mine, theirs = target, {"url": target}
        elif os.path.isfile(target):
            title, artist, length = probe(target)
            mine = target                              # (the others: from this one's web page, where they know it is)
            theirs = {"web": "/api/handoff/file?token=" + self.handoff_keys().issue(target)} if p is not None else {}
        else:                                          # (one from the web, the Internet Archive's: each takes it there)
            mine, theirs = target, {"url": target}
        item = {"kind": kind, "title": it["title"], "sub": it.get("sub") or "", "meta_title": title,
                "artist": artist, "length": length}
        self.party_tell({"kind": "play", "item": item, "src": theirs, "at": at, "pos": pos})
        self.party_proc(mine, at, pos, kind, it, True, title, artist, length)

    def party_tell(self, msg):
        """What the leader says (a song to play, a pause...), to each of yours in the party, on threads of their own:
        one that doesn't answer has left it."""
        p = self.party
        if not p or not p.get("lead"):
            return
        msg = dict(msg, token=p["token"])

        def tell(url):
            if party_post(url, msg) is None:
                gone = p["members"].pop(url, None)
                if gone:
                    print(f"party: {gone} didn't answer: it's left", flush=True)
        for url in list(p["members"]):
            threading.Thread(target=tell, args=(url,), daemon=True, name="party-tell").start()

    def party_pause(self):
        """A, leading: all of them pause (or play on) together, a moment from now."""
        got = self.party_toggle()
        if got is not None:
            self.paused = got
            self.dirty = True

    def party_toggle(self):
        """The player paused, or played on, a moment from now (all of them, leading a party): True if it's paused now,
        False if it plays on, None if it isn't party mode's player. (Whether it's shown paused: the caller's.)"""
        proc = self.proc
        if not isinstance(proc, PartyProc):
            return None
        at = time.monotonic() + (PARTY_SOON if self.party_leading() else GLOW_SOON)
        if proc.player.stop_at is not None:
            proc.player.resume_at(at)
            self.party_tell({"kind": "resume", "at": at})
            return False
        proc.player.pause_at(at)
        self.party_tell({"kind": "pause", "at": at})
        return True

    def party_control(self, what, arg):
        """(Party mode's player, told "pause" or "seek" as mplayer is: the web page's remote, the Bot.) Done here, and on
        all of them in a party (in another's: the leader's asked)."""
        if what == "pause":
            if self.party_on() and not self.party_leading():
                self.party_ask("pause")
            else:
                self.party_toggle()
        elif what == "seek" and self.kind == "audio" and isinstance(self.proc, PartyProc):
            step, how = arg
            if self.party_on() and not self.party_leading():
                self.party_ask("ahead" if step >= 0 else "behind")
                return
            here = self.proc.player.position()
            length = self.proc.length
            to = here + step if how == 0 else (length or 0) * step / 100 if how == 1 else step
            self.play(self.queue, self.qi, start=max(0.0, to), show=False)

    def party_seek(self, d):
        """◀▶ in a song, leading: all of them from a little further on (or back), together."""
        proc = self.proc
        if not isinstance(proc, PartyProc) or self.kind != "audio":
            return
        self.play(self.queue, self.qi, start=max(0.0, proc.player.position() + d), show=False)

    def party_end(self, say=False):
        """Not leading a party any more: the others stop; this one's music plays on, on its own."""
        p, self.party = self.party, None
        if not p or not p.get("lead"):
            return
        for url in list(p["members"]):
            threading.Thread(target=party_post, args=(url, {"kind": "stop", "token": p["token"]}), daemon=True,
                             name="party-end").start()
        for x in (p.get("relay"), p.get("clock"), p.get("server")):
            if x is not None:
                x.close()
        print("party: over", flush=True)
        if say:
            self.toast("Party mode's over", 3)
        if isinstance(self.proc, PartyProc) and self.queue and 0 <= self.qi < len(self.queue):
            pos = self.proc.player.position() if self.kind == "audio" else 0
            self.start_paused = bool(self.paused)       # (paused: still paused, on its own player)
            try:
                self.play(self.queue, self.qi, start=pos, show=False)   # (as ever: on its own player)
            finally:
                self.start_paused = False

    # -- in another's -----------------------------------------------------------------------------------------------
    def party_busy(self):
        """Why this one can't join a party now, or None."""
        if self.view == "update":
            return "It's updating itself"
        if self.game is not None and not getattr(self.game, "attract", False):
            return "It's playing a game"
        if self.proc and self.kind not in LISTEN_KINDS and self.proc.poll() is None:
            return "It's playing a video"
        if not self.active:
            return "It's in the terminal"
        return None

    def party_clock(self):
        """The leader's clock (this one's, with the offset its pings found)."""
        p = self.party
        return time.monotonic() + ((p or {}).get("offset") or 0.0)

    def party_ping(self):
        """The leader's clock against this one's, found again (on a thread of its own)."""
        p = self.party
        if not p or p.get("lead") or p.get("pinging"):
            return
        p["pinging"], p["pinged"] = True, time.monotonic()

        def ping():
            try:
                got = clock_offset(urllib.parse.urlsplit(p["leader"]).hostname, p["port"], p["token"])
                if got is not None:
                    p["offset"], p["rtt"] = got
            finally:
                p["pinging"] = False
        threading.Thread(target=ping, daemon=True, name="party-ping").start()

    def party_leave(self, say=False, tell=True):
        """Out of the party: the music stops here, and the leader's told."""
        p, self.party = self.party, None
        if not p or p.get("lead"):
            return
        if tell:
            threading.Thread(target=party_post, args=(p["leader"], {"kind": "leave", "token": p["token"]}),
                             daemon=True, name="party-leave").start()
        if isinstance(self.proc, PartyProc):
            self.stop()
            if self.view == "now":
                self.view = "home"
        if say:
            self.toast(f"Left {p['name']}'s party", 3)
        print(f"party: out of {p['name']}'s", flush=True)

    def party_ask(self, what):
        """A, ◀▶, L, R or START, in another's party: the leader's asked to do it, for all of them."""
        p = self.party
        threading.Thread(target=party_post, args=(p["leader"], {"kind": "ask", "what": what, "token": p["token"]}),
                         daemon=True, name="party-ask").start()

    def party_press(self, name):
        """A button on Now playing in a party: True if it's the party's (the same on all of them)."""
        if not self.party_on() or not isinstance(self.proc, PartyProc):
            return False
        what = {"a": "pause", "r": "next", "start": "next", "l": "back"}.get(name)
        if name in ("left", "right"):
            what = None if self.kind != "audio" else "behind" if name == "left" else "ahead"
            if self.kind == "radio":
                what = "back" if name == "left" else "next"
        if what is None:
            return False
        if self.party_leading():
            self.party_do(what)
        else:
            self.party_ask(what)
        self.dirty = True
        return True

    def party_do(self, what):
        """(The leader.) What one of them asked (or its own button): for all of them."""
        if what == "pause":
            self.party_pause()
        elif what in ("next", "back"):
            self.skip(1 if what == "next" else -1)
        elif what in ("ahead", "behind"):
            self.party_seek(10 if what == "ahead" else -10)

    def party_proc(self, src, at, pos, kind, it, lead, title="", artist="", length=None):
        """It, played here in step (src: a file or a web address; at: the leader's clock; pos: from where in it), as
        media mode's player (PartyProc): Now playing shows it, the volume's this one's own."""
        if not lead:
            self.stop()                                # (the song before it: the leader's already stopped its own)
        place = sound_place(self.setting("sound"))
        pre, you = as_you(home_dir())
        beat = self.glow_beat if self.glow_beats_wanted() else None   # (an LED grid pulsing to it: screens/glow.py)
        player = PartyPlayer(src, at, pos=pos, device=aplay_device(None, place[0]), volume=self.volume,
                             clock=time.monotonic if lead else self.party_clock, pre=pre, you=you, on_beat=beat)
        proc = PartyProc(player, title=title, artist=artist, length=length, lead=lead, control=self.party_control)
        if not lead:
            self.queue, self.qi = [it], 0
            self.pop_now()
        self.kind, self.cur, self.pos, self.paused = kind, it, pos, False
        self.meta = {k: v for k, v in (("title", title), ("artist", artist), ("length", length)) if v}
        self.proc, self.started = proc, time.monotonic()
        self.next_query = time.monotonic() + 1
        self.sound_used, self.sound_look = place, time.monotonic() + 2.0
        self.muted = self.settling = False
        self.voice.stop(unload=True)                   # (the player has the sound)
        threading.Thread(target=self.reader, args=(proc,), daemon=True).start()
        self.dirty = True

    # -- what's said of it (POST /api/party: the control server's, on the main loop) ------------------------------------
    def web_party(self, cmd):
        """From another of yours: the leader asking this one to join its party, then what to play, when it pauses...;
        or (to the leader) another in the party asking it to pause or skip, or saying it's left."""
        peers = self.saves_peers(str(cmd.get("from") or ""))
        if not peers:
            return {"ok": False, "error": "Not one of your Pietatos"}
        url, host = peers[0]
        kind, token, p = cmd.get("kind"), cmd.get("token"), self.party
        if not isinstance(token, str) or not 16 <= len(token) <= 64:
            return {"ok": False, "error": "What party?"}
        if kind == "start":
            why = self.party_busy()
            if why:
                return {"ok": False, "error": why}
            if p is not None and (p.get("lead") or p.get("leader") != url):
                return {"ok": False, "error": "It's in another party"}
            port = cmd.get("port")
            if isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536:
                return {"ok": False, "error": "What's that?"}
            self.party = {"lead": False, "leader": url, "name": host, "token": token, "port": port, "offset": None,
                          "pinged": 0.0, "got": False}
            self.party_ping()
            self.toast(f"Party mode with {host}", 4)
            print(f"party: in {host}'s", flush=True)
            return {"ok": True}
        if p is None or p.get("token") != token:
            return {"ok": False, "error": "It isn't in that party"}
        if p.get("lead"):                              # (the leader: another of the party)
            if url not in p["members"]:
                return {"ok": False, "error": "It isn't in that party"}
            if kind == "leave":
                p["members"].pop(url, None)
                return {"ok": True}
            if kind == "ask" and cmd.get("what") in PARTY_ASKS:
                self.party_do(cmd["what"])
                return {"ok": True}
            return {"ok": False, "error": "What's that?"}
        if url != p["leader"]:
            return {"ok": False, "error": "It isn't in that party"}
        at = cmd.get("at")
        if kind == "stop":
            self.party_leave(tell=False)
            self.toast(f"{host}'s party is over", 3)
            return {"ok": True}
        if kind in ("play", "pause", "resume") and (isinstance(at, bool) or not isinstance(at, (int, float))
                                                    or abs(at - self.party_clock()) > 60):
            return {"ok": False, "error": "When?"}
        if kind == "play":
            return self.party_take(cmd, url, at)
        proc = self.proc if isinstance(self.proc, PartyProc) else None
        if kind == "pause" and proc is not None:
            proc.player.pause_at(at)
            self.paused = True
        elif kind == "resume" and proc is not None:
            proc.player.resume_at(at)
            self.paused = False
        elif kind == "song" and isinstance(cmd.get("song"), str):
            self.meta["song"] = cmd["song"][:200]
        self.dirty = True
        return {"ok": True}

    def party_take(self, cmd, url, at):
        """(In another's party.) A song or a station to play: from where (the leader's, or the station's own web
        address), from where in it, at when. A game or a video on here now: out of the party instead."""
        why = self.party_busy()
        if why:
            self.party_leave()
            return {"ok": False, "error": why}
        item, src, pos = cmd.get("item"), cmd.get("src"), cmd.get("pos")
        if not isinstance(item, dict) or item.get("kind") not in ("audio", "radio") or not isinstance(src, dict) \
                or isinstance(pos, bool) or not isinstance(pos, (int, float)) or not 0 <= pos < 86400:
            return {"ok": False, "error": "What's that?"}
        port, path, station, web = src.get("port"), src.get("path"), src.get("url"), src.get("web")
        if isinstance(station, str) and re.fullmatch(r"https?://[^\s]{1,1000}", station):
            where = station                            # (a station that can't be passed on: its own address)
        elif isinstance(web, str) and PATH.fullmatch(web):
            where = url + web                          # (a song: from the leader's web page)
        elif isinstance(port, int) and not isinstance(port, bool) and 0 < port < 65536 and isinstance(path, str) \
                and PATH.fullmatch(path):
            where = f"http://{urllib.parse.urlsplit(url).hostname}:{port}{path}"   # (a station it passes on)
        else:
            return {"ok": False, "error": "From where?"}

        def text(k, most=200):
            v = item.get(k)
            return v[:most] if isinstance(v, str) else ""
        length = item.get("length")
        length = float(length) if isinstance(length, (int, float)) and not isinstance(length, bool) and 0 < length < 86400 \
            else None
        it = {"key": f"party:{url}:{text('title')}", "kind": item["kind"], "title": text("title") or "Party",
              "sub": text("sub"), "src": "party:" + url}
        self.party_proc(where, at, float(pos), item["kind"], it, False, text("meta_title"), text("artist"), length)
        self.party["got"] = True                       # (its music's on: something else on instead, and it's left)
        return {"ok": True}

    def party_tick(self, now):
        """(Media mode's main loop.) Leading: the station's song, said to the others; nobody left in the party, or no
        party music here a while: it's over. In another's: something else on here, out of it; the leader's clock
        looked at again now and then."""
        p = self.party
        if p is None:
            return
        party_music = isinstance(self.proc, PartyProc)
        if p.get("lead"):
            if not p["members"]:
                self.party_end()
                self.toast("Your other Pietatos left the party", 3)
                return
            if not party_music:
                p["quiet"] = p.get("quiet") or now
                if now - p["quiet"] > PARTY_GONE:
                    self.party_end()
                return
            p["quiet"] = None
            relay = p.get("relay")
            if relay is not None and relay.song and relay.song != p.get("song"):
                p["song"] = relay.song
                self.meta["song"] = relay.song
                self.party_tell({"kind": "song", "song": relay.song})
                self.dirty = True
            return
        if p.get("got") and not party_music:          # (something else on here, or nothing: out of it)
            self.party_leave()
            return
        if now - p.get("pinged", 0.0) > PARTY_PING_EVERY:
            self.party_ping()
