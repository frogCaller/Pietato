"""Party mode (pitato/party.py), started from HOME's menu on Now playing: each of your other Pietatos that's on, and isn't
in a game, a video or the terminal, plays what this one plays, in step with it, through its own speaker. This one leads:
its songs, one after another, and its stations. A, ◀▶, L, R and START on any of them pause it, move about in a song or
skip, for all of them; HOME's menu on the leader ends it, and on another leaves it (it stops there). Each keeps its own
volume and sound (Settings > Sound). One that's in another party when this one's started switches to this one (a party
it was leading itself is over). While it goes on the leader looks at it every few seconds: one that's fallen behind (a
song or a pause that never got to it) is told again, from where the song is by then; one that's on and free (just
turned on, done with its game) is asked in, and plays from there too; one that's stopped answering is asked in again
when it's back; one that left stays out, till Join is picked on it (HOME's menu on Now playing has it, with Party
mode, while another of yours leads a party): the leader's asked to let it in. POST /api/party (webui.py) carries what
the leader says, and what the others ask."""
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse

from ..asyou import as_you
from ..config import home_dir
from ..coverfind import song_key
from ..library import LISTEN_KINDS
from ..party import (ClockServer, clock_offset, PARTY_LEAD, PARTY_PORT, PartyPlayer, PartyProc, probe, Relay,
                     RelayServer)
from .glow import GLOW_LEAD, GLOW_SOON
from ..screen import aplay_device, sound_place
from .. import savesync

PARTY_WAIT = 4.0             # seconds each of your others has to say it's in
PARTY_PING_EVERY = 30.0      # seconds between a follower's looks at the leader's clock (clocks drift apart)
PARTY_PING_SOON = 2.0        # ...while it only has it roughly (none of its looks has found it yet)
PARTY_GONE = 3.0             # seconds the leader's had no party music: the party's over
PARTY_SOON = 0.6             # seconds from a pause (or playing on) to its happening on all of them
PARTY_LOOK = 5.0             # seconds between the leader's looks at its party: who's behind, who else is on
PARTY_SAID = 4.0             # ...and none this soon after it's said something to all of them (still on its way)
PARTY_MISSES = 3             # times running one doesn't answer before it's out of the party (asked in again later)
PARTY_AGAIN = 30.0           # seconds before one that couldn't join (a game on it, say) is asked again; and between
                             # a station's starting again for one that's behind
PARTY_LOST = 60.0            # seconds without a word from its leader before one in a party takes it to be over
PARTY_ASKS = ("pause", "next", "back", "ahead", "behind")   # what another can ask the leader to do, for all of them
PATH = re.compile(r"/[A-Za-z0-9/_.?=&%-]{1,300}")
NOT_IN = "It isn't in that party"
LEFT = "It left that party"
OLD = "What's that?"         # (a Pietato from before the leader's looks, asked what it's on: left as it is)


def party_post(url, body, timeout=3.0):
    """Another Pietato's answer (a dict) to what's said of the party, or None when it doesn't answer."""
    try:
        got = savesync.post_json(url + "/api/party", body, timeout=timeout)
    except urllib.error.HTTPError as ex:               # (it answered: it doesn't know what's asked)
        return {"ok": False, "error": OLD} if ex.code == 400 else None
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) else None


def whole(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


class PartyScreen:
    """Party mode: leading one (this one's music, on all of yours, in step), or in another's."""
    party = None      # leading: {"lead": True, "token", "members": {url: name}, "clock", "server", "relay", "song",
                      # "n": its songs counted, "on": the one playing as it was said, "said": when all were last told
                      # something, "missed": {url: times running it hasn't answered}, "away": out of it for that,
                      # "left": out of their own accord, "plain": older ones, "asked": {url: not asked in before}};
                      # in another's: {"lead": False, "leader": url, "name", "token", "port", "offset", "rough",
                      # "pinged", "heard": when its leader last said anything, "n", "at": the song it was last told}
    party_quit = None  # the party it last left of its own accord (its key): not one it's asked back into

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

        def ask(url):                                  # (new: one in another party switches to this one)
            said[url] = party_post(url, {"kind": "start", "token": token, "port": PARTY_PORT, "new": True,
                                         "clock": time.monotonic()}, PARTY_WAIT)
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
        now = time.monotonic()
        self.party = {"lead": True, "token": token, "members": members, "clock": clock, "server": server,
                      "relay": None, "song": "", "since": now, "quiet": None, "n": 0, "on": None, "said": now,
                      "looked": now, "looking": 0, "missed": {}, "away": set(), "left": set(), "plain": set(),
                      "asked": {url: now + PARTY_AGAIN for url, _ in peers if url not in members and said.get(url)}}
        names = list(members.values())
        self.toast("Party mode with " + (names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]), 5)
        print(f"party: leading, with {', '.join(names)}", flush=True)
        self.party_said()
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
        if "web" in theirs:                            # (a song of this one's: its cover's asked for by these)
            item["name"], item["size"] = song_key(target)
        if p is not None:                              # (its number, and what was said of it: for one that's behind,
            p["n"] += 1                                #  or joins later)
            p["on"] = {"item": item, "src": theirs}
        self.party_tell({"kind": "play", "item": item, "src": theirs, "at": at, "pos": pos, "n": (p or {}).get("n")})
        self.party_proc(mine, at, pos, kind, it, True, title, artist, length)

    def party_tell(self, msg, only=None):
        """What the leader says (a song to play, a pause...), to each of yours in the party (only: just that one), on
        threads of their own, with its clock as it's said. One that doesn't answer is told once more."""
        p = self.party
        if not p or not p.get("lead"):
            return
        msg = dict(msg, token=p["token"])
        if only is None and msg["kind"] != "song":
            p["said"] = time.monotonic()

        def tell(url):
            got = None
            try:
                got = party_post(url, dict(msg, clock=time.monotonic())) or \
                    party_post(url, dict(msg, clock=time.monotonic()))
            finally:
                self.soon(lambda: self.party_heard(p, url, got))
        for url in ([only] if only else list(p["members"])):
            threading.Thread(target=tell, args=(url,), daemon=True, name="party-tell").start()

    def party_heard(self, p, url, got):
        """(The leader's main loop.) One in the party answered what it was told or asked (got), or didn't (None). A few
        times running, and it's out of the party for now; so is one that says it isn't in it (restarted, say). The
        leader's looks ask it in again."""
        if self.party is not p or url not in p["members"]:
            return
        if got is None:
            p["missed"][url] = p["missed"].get(url, 0) + 1
            if p["missed"][url] < PARTY_MISSES:
                return
        elif not (got.get("ok") is False and got.get("error") == NOT_IN):
            p["missed"].pop(url, None)
            return
        name = p["members"].pop(url)
        p["missed"].pop(url, None)
        p["asked"].pop(url, None)
        p["away"].add(url)
        print(f"party: {name} " + ("isn't answering" if got is None else "isn't in it any more"), flush=True)

    def party_look(self, now):
        """(The leader, every few seconds.) Each of yours in the party asked what it's on; each one that's on and isn't
        in it (and didn't leave it) asked in. On threads of their own: party_looked has what they say."""
        p = self.party
        p["looked"] = now
        n, paused = p["n"], self.proc.player.stop_at is not None
        for url, name in self.saves_peers():
            if url in p["members"]:
                if url in p["plain"]:
                    continue
                msg = {"kind": "look"}
            elif url in p["left"] or now < p["asked"].get(url, 0.0):
                continue
            else:
                p["asked"][url] = now + PARTY_AGAIN
                msg = {"kind": "start", "port": PARTY_PORT}
            self.party_reach(p, url, name, msg, n, paused, now)

    def party_reach(self, p, url, name, msg, n, paused, since):
        """(The leader.) One of yours asked what it's on, or asked in, on a thread of its own: party_looked has what
        it says. n, paused: what the party's on as it's asked; since: when."""
        p["looking"] += 1
        threading.Thread(target=self.party_look_at, args=(p, url, name, dict(msg, token=p["token"]), n, paused, since),
                         daemon=True, name="party-look").start()

    def party_look_at(self, p, url, name, msg, n, paused, since):
        """(A thread of its own.) One of yours asked what it's on, or asked in."""
        got = None
        try:
            got = party_post(url, dict(msg, clock=time.monotonic()), PARTY_WAIT if msg["kind"] == "start" else 3.0)
        finally:
            self.soon(lambda: self.party_looked(p, url, name, msg["kind"], got, n, paused, since))

    def party_looked(self, p, url, name, kind, got, n, paused, since):
        """(The leader's main loop.) What one of yours said to a look. In the party and not on its song, or not paused
        as it is: told again. Asked in, and it's in: said, and told what's on. One that says it left stays out; one
        that doesn't answer is asked again at the next look, one that can't join now a while later."""
        p["looking"] -= 1
        if self.party is not p:
            if kind == "start" and got is not None and got.get("ok") is True:   # (in, as the party ended: told so)
                threading.Thread(target=party_post, args=(url, {"kind": "stop", "token": p["token"]}), daemon=True,
                                 name="party-end").start()
            return
        if kind == "start":
            if got is None:                            # (not answering: asked again at the next look)
                p["asked"].pop(url, None)
                return
            if url in p["members"]:
                return
            if got.get("ok") is not True:
                if got.get("error") == LEFT:
                    p["left"].add(url)
                    p["away"].discard(url)
                return
            p["members"][url] = name
            p["away"].discard(url)
            p["asked"].pop(url, None)
            self.toast(f"{name} joined the party", 3)
            print(f"party: {name} joined", flush=True)
        else:
            self.party_heard(p, url, got)
            if got is None or url not in p["members"]:
                return
            if got.get("ok") is not True:
                if got.get("error") == OLD:
                    p["plain"].add(url)
                return
        if whole(got.get("n")) == n and bool(got.get("paused")) == paused:
            return                                     # (on the party's song, as the party is)
        if p["n"] == n and p["said"] <= since:         # (nothing's been said to all of them since it was asked)
            if kind != "start":
                print(f"party: {name} is behind: told again", flush=True)
            self.party_catch(url)

    def party_catch(self, url):
        """(The leader.) One of them told what the party's on, from where it is: a song from there, a moment from now
        (paused, if the party is). A station can't be joined in the middle (each plays the same bytes from the same
        one on): it starts again for all of them, once it plays (and not again for a while)."""
        p, proc = self.party, self.proc
        if not p or not p.get("lead") or not p.get("on") or not isinstance(proc, PartyProc) or proc.poll() is not None:
            return
        now = time.monotonic()
        paused = proc.player.stop_at is not None
        if self.kind == "radio":
            if not paused and now - p.get("again", 0.0) >= PARTY_AGAIN and 0 <= self.qi < len(self.queue or ()):
                p["again"] = now
                self.play(self.queue, self.qi, show=False)
            return
        at = now + PARTY_LEAD
        pos = proc.player.position(at)
        if proc.length and pos > proc.length - 1.0:    # (about over: the next song comes to all of them)
            return
        self.party_tell(dict(p["on"], kind="play", at=at, pos=pos, n=p["n"], paused=paused), only=url)

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

    def party_end(self, say=False, play_on=True):
        """Not leading a party any more: the others stop; this one's music plays on, on its own (play_on False: as it
        is for now, on the party's player: it's off to another party, whose song comes in a moment)."""
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
        self.party_said()
        if say:
            self.toast("Party mode's over", 3)
        if play_on and isinstance(self.proc, PartyProc) and self.queue and 0 <= self.qi < len(self.queue):
            pos = self.proc.player.position() if self.kind == "audio" else 0
            self.start_paused = bool(self.paused)       # (paused: still paused, on its own player)
            try:
                self.play(self.queue, self.qi, start=pos, show=False)   # (as ever: on its own player)
            finally:
                self.start_paused = False

    def party_said(self):
        """This one's beacon again, now: a party's begun here, or it's over (your others that aren't in it leave your
        lights to it while it's on: party_elsewhere)."""
        if getattr(self, "sharing", False):
            threading.Thread(target=self.share_now, daemon=True, name="party-said").start()

    def party_others(self):
        """Your other Pietatos leading a party now that this one isn't in (in a game when it began, say, or left to
        play something of its own): [(its address, its name)]. None while this one's in a party."""
        pie = getattr(self, "pie", None)
        if self.party is not None or pie is None:
            return []
        yours = dict(self.saves_peers())
        with pie.lock:
            on = [u for u, h in pie.heard.items() if u in yours and h.get("party")]
        return sorted((u, yours[u]) for u in on)

    def party_elsewhere(self):
        """There's a party on among your others that this one isn't in: the lights of your own on the network are
        the party's to light, not this one's music's."""
        return bool(self.party_others())

    def party_join(self, url, host):
        """Join, picked in HOME's menu on Now playing (there while another of yours leads a party): its leader's asked
        to let this one in. It asks this one in as it does any of yours, a moment later, and tells it what's on."""
        if self.party is not None:
            return
        why = self.party_busy()
        if why:
            self.toast(why, 3)
            return
        self.party_quit = None                         # (asked for: a party it left is one it's in again)
        self.toast(f"Joining {host}'s party…", 4)

        def ask():
            got = party_post(url, {"kind": "join"}, PARTY_WAIT)
            if got is None or got.get("ok") is not True:
                why = (got or {}).get("error") or f"{host} not responding"
                self.soon(lambda: self.toast(f"Couldn't join: {why}", 4))
        threading.Thread(target=ask, daemon=True, name="party-join").start()

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
                    rough = p.get("rough")
                    p["offset"], p["rtt"] = got
                    p["rough"], p["heard"] = False, time.monotonic()
                    proc = self.proc
                    if rough and self.party is p and isinstance(proc, PartyProc):
                        proc.player.snapped()          # (its song, begun by the rough clock: where this one says, now)
            finally:
                p["pinging"] = False
        threading.Thread(target=ping, daemon=True, name="party-ping").start()

    def party_led(self, p, cmd):
        """Something from its leader: it's there. With the leader's clock as it said it: this one's set by it, roughly
        (as late as that took to get here), till one of its own looks at the leader's clock has found it."""
        p["heard"] = time.monotonic()
        clock = cmd.get("clock")
        if p.get("offset") is None and isinstance(clock, (int, float)) and not isinstance(clock, bool):
            p["offset"], p["rough"] = clock - time.monotonic(), True

    def party_has(self, p):
        """What this one's on, for its leader: the number of the party's song it's playing (None: none of them), and
        whether it's paused."""
        proc = self.proc
        on = isinstance(proc, PartyProc) and not proc.lead
        return {"n": p.get("n") if on else None, "paused": bool(on and proc.player.stop_at is not None)}

    def party_leave(self, say=False, tell=True, mine=True):
        """Out of the party: the music stops here, and the leader's told. mine: of its own accord (it isn't asked back
        into that one); not mine (a game or a video on here now): it's asked in again, later."""
        p, self.party = self.party, None
        if not p or p.get("lead"):
            return
        if mine:
            self.party_quit = p["token"]
        if tell:
            said = {"kind": "leave", "token": p["token"], "back": not mine}
            threading.Thread(target=party_post, args=(p["leader"], said), daemon=True, name="party-leave").start()
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
                             clock=time.monotonic if lead else self.party_clock, pre=pre, you=you, on_beat=beat,
                             on_band=self.glow_band if beat is not None else None,   # (your boards, each its own beat)
                             on_sound=self.oled_heard)   # (an OLED screen's bars: screens/oled.py)
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
        if kind == "join":                             # (one of yours asks to be let into the party this one leads:
            if p is None or not p.get("lead"):         #  asked in as any is, now, whether or not it left before)
                return {"ok": False, "error": "There's no party here now"}
            p["left"].discard(url)
            if url not in p["members"]:
                now, proc = time.monotonic(), self.proc
                p["asked"][url] = now + PARTY_AGAIN
                paused = isinstance(proc, PartyProc) and proc.player.stop_at is not None
                self.party_reach(p, url, host, {"kind": "start", "port": PARTY_PORT}, p["n"], paused, now)
            return {"ok": True}
        if not isinstance(token, str) or not 16 <= len(token) <= 64:
            return {"ok": False, "error": "What party?"}
        if kind == "start":
            why = self.party_busy()
            if why:
                return {"ok": False, "error": why}
            port = cmd.get("port")
            if isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536:
                return {"ok": False, "error": "What's that?"}
            new = cmd.get("new") is True               # (just started, from HOME's menu there: not its leader's
                                                       #  look for more of yours to join)
            if p is not None and not p.get("lead") and p["leader"] == url and p["token"] == token:
                self.party_led(p, cmd)                 # (in it already: what it's on, for its leader)
                return dict(self.party_has(p), ok=True)
            if p is not None and (p.get("lead") or p["leader"] != url):
                if not new:
                    return {"ok": False, "error": "It's in another party"}
                if p.get("lead"):                      # (the newest party's the one: this one's own is over, and its
                    self.party_end(play_on=False)      #  others are asked into that one too)
                else:
                    self.party_leave()
            elif not new and token == self.party_quit:
                return {"ok": False, "error": LEFT}
            p = self.party = {"lead": False, "leader": url, "name": host, "token": token, "port": port, "offset": None,
                              "rough": None, "pinged": 0.0, "got": False, "heard": time.monotonic()}
            self.party_led(p, cmd)
            self.party_ping()
            self.stir()                                # (said on a screen that's resting, too)
            self.toast(f"Party mode with {host}", 4)
            print(f"party: in {host}'s", flush=True)
            return {"ok": True}
        if p is None or p.get("token") != token:
            return {"ok": False, "error": NOT_IN}
        if p.get("lead"):                              # (the leader: another of the party)
            if kind == "leave":                        # (of its own accord: it isn't asked back. For a game or a
                p["members"].pop(url, None)            #  video: it is, after)
                p["missed"].pop(url, None)
                if cmd.get("back") is True:
                    p["away"].add(url)
                    p["asked"][url] = time.monotonic() + PARTY_AGAIN
                else:
                    p["away"].discard(url)
                    p["left"].add(url)
                return {"ok": True}
            if url not in p["members"]:
                return {"ok": False, "error": NOT_IN}
            if kind == "ask" and cmd.get("what") in PARTY_ASKS:
                self.party_do(cmd["what"])
                return {"ok": True}
            return {"ok": False, "error": "What's that?"}
        if url != p["leader"]:
            return {"ok": False, "error": NOT_IN}
        self.party_led(p, cmd)
        at = cmd.get("at")
        if kind == "stop":
            self.party_leave(tell=False, mine=False)
            self.toast(f"{host}'s party is over", 3)
            return {"ok": True}
        if kind in ("play", "pause", "resume") and (isinstance(at, bool) or not isinstance(at, (int, float))
                                                    or abs(at - self.party_clock()) > 60):
            return {"ok": False, "error": "When?"}
        if kind == "play":
            if whole(cmd.get("n")) is not None and cmd["n"] == p.get("n") and at == p.get("at") \
                    and isinstance(self.proc, PartyProc):
                return {"ok": True}                    # (told twice: its answer the first time never got there)
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
            self.party_leave(mine=False)
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
        self.cover_bring(it, url, item.get("name"), item.get("size"))   # (the song's cover there, for Now playing)
        self.party_proc(where, at, float(pos), item["kind"], it, False, text("meta_title"), text("artist"), length)
        if cmd.get("paused") is True:                  # (a party that's paused: there, till it plays on)
            self.proc.player.pause_at(at)
            self.paused = True
        p = self.party
        p["got"] = True                                # (its music's on: something else on instead, and it's left)
        p["n"], p["at"] = whole(cmd.get("n")), at
        return {"ok": True}

    def web_party_look(self, cmd):
        """(The control server's thread: answered at once, whatever the main loop's at.) Its leader's look at the
        party: what this one's on, for the leader to tell it again if that's not what the party's on."""
        peers = self.saves_peers(str(cmd.get("from") or ""))
        p = self.party
        if not peers or p is None or p.get("lead") or p.get("token") != cmd.get("token") or peers[0][0] != p["leader"]:
            return {"ok": False, "error": NOT_IN}
        self.party_led(p, cmd)
        p["looks"] = True
        return dict(self.party_has(p), ok=True)

    def party_tick(self, now):
        """(Media mode's main loop.) Leading: the station's song, said to the others; a look at the party every few
        seconds (party_look); everyone's left it, or no party music here a while: it's over (ones that have only
        stopped answering are waited for). In another's: something else on here, or not a word from its leader for a
        long while: out of it; the leader's clock looked at again now and then."""
        p = self.party
        if p is None:
            return
        party_music = isinstance(self.proc, PartyProc)
        if p.get("lead"):
            if not p["members"] and not p["away"]:
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
            if not p["looking"] and now - p["looked"] >= PARTY_LOOK and now - p["said"] >= PARTY_SAID:
                self.party_look(now)
            return
        if p.get("got") and not party_music:          # (something else on here, or nothing: out of it. A game or a
            self.party_leave(mine=self.party_busy() is None)   # video: back in it after. Its own music: not)
            return
        if (p.get("looks") or not p.get("got")) and now - p["heard"] > PARTY_LOST:
            self.party_leave(tell=False, mine=False)   # (not a word from its leader for a long while, and it's one
            self.toast(f"Lost touch with {p['name']}'s party", 3)   # that would have said something: off, or out of
            return                                     #  reach. It's over here)
        if now - p.get("pinged", 0.0) > (PARTY_PING_EVERY if p.get("rough") is False else PARTY_PING_SOON):
            self.party_ping()
