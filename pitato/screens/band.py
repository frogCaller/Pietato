"""Apps > Band, in media mode (bandstage.py draws it, band.py has the music, bandplay.py plays it). Any Pietato can
start a band: opened here, this one asks your others that are on (and aren't in a game, a video or the terminal) to
join. Each that does takes an instrument, sets its clock against this one's (party.py's way) and plays its own part
through its own speaker, a bar or so ahead of when it's heard, so nothing's sent in time with the music: only the song,
its tempo and when it started, and now and then what each is doing. This one plays whatever nobody's taken (all four,
on its own). POST /api/band (webui.py) carries what's said between them.

Each player decides what it does with its next four bars: dice, or a decision model on your bot's computer (asked on a
thread of its own, four bars ahead; an answer that's late isn't waited for). Its buttons: the d-pad's four, A, B, X
and Y play your instrument (the Pietato leaves it to you while you do), L and R pick it, SELECT starts and stops the
band, START has its card (the song, the tempo, your instrument, the volume, who decides; with others in the band,
Timing: this one's sound a little earlier or later, for a TV that's slow with it), where B goes back to Apps."""
import json
import math
import os
import random
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse
from collections import deque

from .. import band as B
from .. import savesync
from .. import soundbank
from ..asyou import as_you, nice_now
from ..bot import ollama_decide, ollama_deciders
from ..config import home_dir
from ..library import LIBRARY, LISTEN_KINDS, VOLUME_STEP
from ..party import ClockServer, clock_offset
from ..screen import aplay_device, sound_place
from .soundboard import BOARD_AGAIN, BOARD_BEHIND, BOARD_NICE, BOARD_QUIET, BOARD_ROUTE

PLAYER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bandplay.py")
BAND_PORT = 5447                 # the clock of the one that started it (UDP)
BAND_AHEAD = 1.2                 # seconds before a bar starts that its notes are with the player
BAND_LEAD = 1.4                  # seconds from SELECT to the first tap of the count-in (each of yours is ready by then)
BAND_WAIT = 4.0                  # seconds each of your others has to say whether it's in
BAND_ASK_EVERY = 30.0            # seconds between asking the ones that aren't
BAND_LEFT = 300.0                # ...and one whose own buttons took it out isn't asked again for this long
BAND_PING_EVERY = 30.0           # seconds between looks at the clock of the one that started it
BAND_SAY_EVERY = 2.0             # seconds between words to the others, at least
BAND_SAY_ANYWAY = 12.0           # ...and at most (the others know it's still there)
BAND_GONE = 45.0                 # seconds without a word from the one that started it: it's gone
BAND_YOURS = 2                   # bars after your last note that your instrument's still yours
BAND_LIT = 0.14                  # seconds a button's tile stays lit
BAND_MODELS_FRESH = 60.0         # seconds a list of the decision models is good for
BAND_PICK_WAIT = (60.0, 8.0)     # seconds a model's pick may take: its first (it wakes up), and after
BAND_EARLY = (250, 10)           # ms this one's sound can be played early or late (START's card: Timing), and a step
DICE = "Dice"


def band_post(url, body, timeout=3.0):
    """Another Pietato's answer (a dict) to what's said of the band, or None when it doesn't answer."""
    try:
        got = savesync.post_json(url + "/api/band", body, timeout=timeout)
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) else None


class Brain:
    """A decision model on your bot's computer, asked on a thread of its own (one question at a time: which models
    there are, or a player's pick), so the band never waits for it."""

    def __init__(self):
        self.cv = threading.Condition()
        self.job = None                 # ("models", server) or ("pick", server, model, state, says, choices, tag, wait)
        self.done = []                  # what came back: (kind, tag, answer, ms, error)
        self.thread = None

    def busy(self):
        with self.cv:
            return self.job is not None

    def ask(self, job):
        with self.cv:
            if self.job is not None:
                return False
            self.job = job
            self.cv.notify()
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self.run, daemon=True, name="band-brain")
            self.thread.start()
        return True

    def take(self):
        with self.cv:
            out, self.done = self.done, []
        return out

    def run(self):
        while True:
            with self.cv:
                while self.job is None:
                    self.cv.wait()
                job = self.job
            t0 = time.monotonic()
            try:
                if job[0] == "models":
                    out = ("models", job[1], ollama_deciders(job[1]), 0.0, "")
                else:
                    _, server, model, state, says, choices, tag, wait = job
                    pick, _ = ollama_decide(server, model, state, says, choices, wait)
                    out = ("pick", tag, pick, (time.monotonic() - t0) * 1000, "")
            except Exception as ex:                    # (it says why; the band plays on regardless)
                out = (job[0], job[6] if job[0] == "pick" else job[1], None, 0.0, str(ex) or repr(ex))
            with self.cv:
                self.done.append(out)
                self.job = None


class Gig:
    """The Band while its page is up: its player, the band as it is, and what's going on."""

    def __init__(self):
        self.proc, self.out = None, b""                # its player, and what it's to be told that it hasn't taken yet
        self.ready, self.bad = {}, {}
        self.sound_ok, self.sound_why, self.busy_said = None, "", -1e9
        self.device = self.volume = self.loaded = None
        self.place = ""                 # where its sound goes (Settings > Sound: a card, "bluetooth"; "": its own)
        self.rested, self.rest_till, self.route_at = False, 0.0, 0.0
        self.start_at, self.stops, self.gave_up = 0.0, 0, False
        self.lead = True                # this one started it (False: it's in another's)
        self.token = secrets.token_urlsafe(16)
        self.clock = None               # this one's clock, for the others (leading)
        self.leader, self.leader_name, self.port = None, "", BAND_PORT    # the one that started it (in another's)
        self.offset, self.pinged, self.pinging = None, 0.0, False         # ...its clock less this one's
        self.heard = 0.0                # ...when it last said something
        self.planned = False            # ...and that it has (the plan: till then this one says nothing of itself)
        self.members = {}               # leading: each of yours in it, address -> {"name", "seat", "does", "you"}
        self.asked, self.left = {}, {}  # ...when each of your others was last asked in; when one took itself out
        self.plan = None                # {"n", "song", "bpm", "t0", "seed", "on"}: t0 by the clock of the one leading
        self.n = 0
        self.mine = B.SEATS             # the instruments this one plays
        self.my = "keys"                # ...and the one your buttons play
        self.who = {}                   # instrument -> who has it (a name; "": this one)
        self.does = {}                  # instrument -> what it's doing, as last heard of the others' (do, by)
        self.sent = None                # (the plan's number, {instrument: the next bar of it to give the player})
        self.picks = {}                 # (instrument, section) -> (what it does, who says: Dice, a model)
        self.wanted = {}                # (instrument, section) -> when a model was asked
        self.models, self.models_for, self.models_at = [], "", -1e9
        self.model_woke, self.failed = False, -1e9   # (a model's answered once: it's awake; when one last couldn't)
        self.hits = deque()             # when you pressed its buttons, lately
        self.yours_till = 0.0           # till when your instrument's yours (this one doesn't play it meanwhile)
        self.person = None              # another's person playing: (instrument, how busily)
        self.lit = {}                   # button -> till when its tile's lit
        self.card = None                # START's card
        self.say_at, self.say_now = 0.0, False
        self.peers_at = 0.0
        self.was = None                 # asked in by another: where this one was before (view, tab)
        self.crash = set()              # sections that start with a crash (the fill before them)


class BandScreen:
    """Apps > Band: its player, the others in it, its buttons, START's card."""

    # -- where it is ------------------------------------------------------------------------------------------------------
    def band_tab(self):
        try:
            return self.tab_type() == "sim" and LIBRARY[self.tab].get("sim") == "band"
        except (AttributeError, IndexError, KeyError, TypeError):
            return False

    def band_shown(self):
        return bool(self.active and self.view == "list" and self.band_tab())

    def band_index(self):
        return next(k for k, t in enumerate(LIBRARY) if t.get("sim") == "band")

    def band_open(self):
        """The band, as it is: made the first time its page is opened (this one's own, till it's in another's)."""
        g = getattr(self, "gig", None)
        if g is None:
            g = self.gig = Gig()
            seat = self.setting("band_seat")
            g.my = seat if seat in B.SEATS else "keys"
            g.plan = self.band_plan(g, on=False)
            g.who = dict.fromkeys(B.SEATS, "")
        return g

    def band_song(self):
        return B.song(self.setting("band_song"))

    def band_bpm(self, song):
        v = self.setting("band_bpm_" + song["key"])
        return v if isinstance(v, int) and not isinstance(v, bool) and B.BPM[0] <= v <= B.BPM[1] else song["bpm"]

    def band_plan(self, g, on):
        """A plan of this one's own: the song and tempo as they're set, starting (on) a moment from now with a bar
        counted in."""
        song = self.band_song()
        bpm = self.band_bpm(song)
        g.n += 1
        g.picks, g.wanted, g.crash, g.sent = {}, {}, set(), None
        return {"n": g.n, "song": song["key"], "bpm": bpm, "seed": random.randrange(1 << 16), "on": bool(on),
                "t0": time.monotonic() + BAND_LEAD + B.BEATS * 60.0 / bpm}

    def band_clock(self):
        """The clock of the one that started it (this one's own, leading)."""
        g = self.gig
        return time.monotonic() + (0.0 if g.lead else g.offset or 0.0)

    def band_synced(self):
        g = self.gig
        return g.lead or g.offset is not None

    def band_bar(self, now=None):
        """(the bar it's on now, counted from the song's first: -1 while it's counted in; the beat in it, 0 to 3; a
        bar's seconds), or None when it isn't playing here."""
        g = self.gig
        p = g.plan
        if not p or not p["on"] or not self.band_synced():
            return None
        beat = 60.0 / p["bpm"]
        beats = ((now if now is not None else self.band_clock()) - p["t0"]) / beat
        return int(math.floor(beats / B.BEATS)), int(math.floor(beats % B.BEATS)), beat * B.BEATS

    # -- its player: a process of its own, as you (as the Soundboard's is) -----------------------------------------------
    def band_start(self, now):
        g = self.gig
        home = home_dir()
        pre, you = as_you(home)

        def ahead():
            try:
                os.nice(BOARD_NICE)
            except OSError:
                pass
        cmd = pre + [sys.executable, "-I", PLAYER, os.path.join(home, ".cache", "pitato", "band")]
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd="/", bufsize=0,
                                    **(you or {"preexec_fn": ahead}))
            os.set_blocking(proc.stdin.fileno(), False)    # (media mode never waits on it: band_send)
        except OSError as ex:
            print(f"band: its player wouldn't start ({ex})", flush=True)
            g.start_at, g.stops = now + BOARD_AGAIN[0], g.stops + 1
            return
        if you:
            nice_now(proc, BOARD_NICE)
        g.proc, g.out = proc, b""
        g.device = g.volume = g.loaded = None
        g.ready, g.bad = {}, {}
        g.sound_ok, g.sound_why, g.rested, g.sent = None, "", False, None
        proc.started = now
        threading.Thread(target=self.band_reader, args=(proc,), daemon=True, name="band").start()
        self.band_route(now)
        if self.band_tell(do="volume", v=self.volume):
            g.volume = self.volume
        self.band_load()
        if not self.voice.speaking:
            self.band_tell(do="warm")

    def band_tell(self, **what):
        """A line to its player. False: it isn't there (any more)."""
        g = getattr(self, "gig", None)
        if g is None or g.proc is None:
            return False
        g.out += (json.dumps(what) + "\n").encode()
        return self.band_send()

    def band_send(self):
        """What its player's to be told, sent: at once, as a rule; what its pipe can't take now, at the next tick. One
        that takes nothing for long is stopped (and started again). False: it isn't there (any more)."""
        g = self.gig
        try:
            while g.out:
                n = os.write(g.proc.stdin.fileno(), g.out[:1 << 16])
                g.out = g.out[n:]
        except BlockingIOError:
            if len(g.out) > BOARD_BEHIND:
                print("band: its player isn't listening: stopped", flush=True)
                g.out = b""
                try:
                    g.proc.kill()
                except OSError:
                    pass
                return False
        except (OSError, ValueError, AttributeError):
            g.out = b""
            return False
        return True

    def band_reader(self, proc):
        """(A thread of its own.) What its player says, passed to media mode's own thread a line at a time."""
        try:
            for line in proc.stdout:
                try:
                    said = json.loads(line)
                except ValueError:
                    continue
                if isinstance(said, dict):
                    self.soon(lambda said=said: self.band_said(proc, said))
                    self.wake()
        except (OSError, ValueError):
            pass
        self.soon(lambda: self.band_gone(proc))
        self.wake()

    def band_said(self, proc, said):
        g = getattr(self, "gig", None)
        if g is None or g.proc is not proc:
            return
        what, sid = said.get("is"), said.get("id")
        if what == "ready" and isinstance(sid, str):
            g.ready[sid] = True
            g.bad.pop(sid, None)
            g.stops = 0
        elif what == "bad" and isinstance(sid, str):
            g.bad[sid] = str(said.get("why") or "")[:80]
        elif what == "sound":
            ok = said.get("ok") is True
            if ok != g.sound_ok:
                print("band: " + (f"playing through a {said.get('buffer')} ms buffer" if ok else
                                  f"the sound won't open ({said.get('why')})"), flush=True)
            g.sound_ok, g.sound_why = ok, "" if ok else str(said.get("why") or "")
        else:
            return
        self.dirty = True

    def band_gone(self, proc):
        """Its player has stopped by itself: started again in a moment (a few times running, then left be)."""
        g = getattr(self, "gig", None)
        if g is None or g.proc is not proc:
            return
        try:
            proc.wait(0.5)
        except (OSError, subprocess.TimeoutExpired):
            pass
        now = time.monotonic()
        print(f"band: its player stopped (exit code {proc.returncode})", flush=True)
        g.proc = None
        g.stops = g.stops + 1 if now - getattr(proc, "started", now) < 30 else 1
        g.start_at = now + BOARD_AGAIN[0]
        g.ready, g.sound_ok = {}, None
        if g.stops >= BOARD_AGAIN[1] and not g.gave_up:
            g.gave_up = True
            self.toast("The band can't play just now", 4)
        self.dirty = True

    def band_player_stop(self):
        g = self.gig
        proc, g.proc = g.proc, None
        g.ready, g.bad, g.sound_ok = {}, {}, None
        g.stops, g.gave_up, g.start_at, g.out = 0, False, 0.0, b""
        if proc is None:
            return
        try:
            os.write(proc.stdin.fileno(), b'{"do": "quit"}\n')
        except (OSError, ValueError):
            pass
        try:
            proc.stdin.close()                         # (its end of the pipe closed: it goes, told or not)
        except (OSError, ValueError):
            pass

        def reap():
            try:
                proc.wait(1.5)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    proc.kill()
                    proc.wait(3)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            try:
                proc.stdout.close()
            except (OSError, ValueError):
                pass
        threading.Thread(target=reap, daemon=True, name="band-end").start()

    def band_route(self, now):
        """Where the sound goes (Settings > Sound), as it changes: its player told."""
        g = self.gig
        g.route_at = now + BOARD_ROUTE
        g.place = sound_place(self.setting("sound"))[0]
        device = aplay_device(None, g.place)
        if device != g.device and self.band_tell(do="device", device=device):
            g.device = device

    def band_load(self):
        """Its player told which sounds there are to play: this one's instruments' for the song, and your own's."""
        g = self.gig
        song = B.song(g.plan["song"])
        sounds = [list(s) for s in B.sounds(song, g.mine, g.my, soundbank.starter_dir())]
        names = {s[0] for s in sounds}
        g.ready = {s: v for s, v in g.ready.items() if s in names}
        sig = tuple(map(tuple, sounds))
        if g.proc is not None and sig != g.loaded and self.band_tell(do="load", sounds=sounds):
            g.loaded = sig

    def band_quiet(self, secs=BOARD_QUIET):
        """Something else starts playing (the Bot's voice): the sound card's let go of for it, at once."""
        g = getattr(self, "gig", None)
        if g is None or g.proc is None:
            return
        g.rest_till = time.monotonic() + secs
        if not g.rested:
            g.rested, g.sent = True, None
            self.band_tell(do="rest")

    # -- each tick ----------------------------------------------------------------------------------------------------------
    def band_tick(self, now):
        g = getattr(self, "gig", None)
        if not self.band_shown():
            if g is not None:
                self.band_over()
            return
        g = self.band_open()
        if g.proc is None:
            if now >= g.start_at and g.stops < BOARD_AGAIN[1]:
                self.band_start(now)
        if g.proc is not None:
            if g.out:
                self.band_send()
            if now >= g.route_at:
                self.band_route(now)
            if g.volume != self.volume and self.band_tell(do="volume", v=self.volume):
                g.volume = self.volume
            quiet = bool(self.voice.speaking) or now < g.rest_till
            if quiet != g.rested:
                g.rested, g.sent = quiet, None
                self.band_tell(do="rest" if quiet else "warm")
        if g.lead:
            self.band_lead_tick(now)
        else:
            self.band_in_tick(now)
        g = getattr(self, "gig", None)
        if g is None:
            return
        self.band_models(now)
        self.band_decide(now)
        if g.proc is not None and not g.rested:
            self.band_schedule(now)
        if g.say_now or now - g.say_at >= BAND_SAY_ANYWAY:
            self.band_say(now)
        if g.lit and min(g.lit.values()) <= now:
            g.lit = {pad: t for pad, t in g.lit.items() if t > now}
            self.dirty = True

    def band_over(self, tell=True):
        """Its page left: leading, the band's over for all of them; in another's, this one's out of it (tell: and
        says so). Its player quits."""
        g = self.gig
        if g.lead:
            for url in list(g.members):
                threading.Thread(target=band_post, args=(url, {"kind": "stop", "token": g.token}), daemon=True,
                                 name="band-end").start()
            if g.clock:
                g.clock.close()
        elif g.leader and tell:
            threading.Thread(target=band_post, args=(g.leader, {"kind": "leave", "token": g.token}), daemon=True,
                             name="band-leave").start()
        self.band_player_stop()
        self.gig = None

    # -- playing: each bar's notes with its player before it starts ------------------------------------------------------
    def band_level(self, g):
        """How loud this one plays each instrument: all four through one speaker, each has to leave the others room."""
        return 0.9 / math.sqrt(max(1, len(g.mine)))

    def band_early(self, g):
        """Seconds ahead of the beat this one plays (behind it: less than 0), as START's card has it for where its
        sound goes now. A TV or Bluetooth headphones take a moment with the sound, and how long isn't something
        they say: with others in the band, it's set by ear."""
        v = self.setting("band_early_" + (g.place or "own"))
        return v / 1000.0 if isinstance(v, int) and not isinstance(v, bool) and abs(v) <= BAND_EARLY[0] else 0.0

    def band_yours(self, g, now=None):
        """You're playing your instrument (this one leaves it to you)."""
        return (time.monotonic() if now is None else now) < g.yours_till

    def band_pick(self, g, seat, section):
        """What a player of this one's does with a section: what's been decided, or the dice now."""
        got = g.picks.get((seat, section))
        if got is None:
            others = {s: d[0] for s, d in g.does.items() if s != seat}
            others.update({s: g.picks[(s, section)][0] for s in g.mine if s != seat and (s, section) in g.picks})
            person = g.my if self.band_yours(g) else g.person[0] if g.person else None
            got = g.picks[(seat, section)] = (B.dice(g.plan["seed"], seat, section, others, person), DICE)
        return got

    def band_schedule(self, now):
        """The bars about to start, given to its player: each of this one's instruments its own, so one that's just
        become this one's (or yours no longer) comes in at its next bar and nothing's played twice."""
        g = self.gig
        at = self.band_bar()
        if at is None:
            return
        p = g.plan
        cur, _, bar_secs = at
        if g.sent is None or g.sent[0] != p["n"]:
            g.sent = (p["n"], {})
        nexts = g.sent[1]
        clock = self.band_clock() + self.band_early(g)
        song, beat = B.song(p["song"]), bar_secs / B.BEATS
        local = p["t0"] - (clock - time.monotonic())   # (the song's first beat, by this one's own clock)
        level, notes = self.band_level(g), []
        for seat in g.mine:
            nxt = nexts.get(seat, max(-1, cur))
            while p["t0"] + nxt * bar_secs - clock <= BAND_AHEAD:
                if p["t0"] + nxt * bar_secs - clock >= 0.12 and not (seat == g.my and self.band_yours(g, now)):
                    for when, sid, gain, lane, long in self.band_part(g, song, seat, nxt):   # (a bar that's already
                        notes.append([round(local + (nxt * B.BEATS + when) * beat, 5), sid,    # on isn't played
                                      round(gain * level, 3), lane, round(long * beat, 4), seat])   # from its middle)
                nxt += 1
            nexts[seat] = nxt
        for seat in [x for x in nexts if x not in g.mine]:
            del nexts[seat]
        if notes:
            for k in range(0, len(notes), 120):
                self.band_tell(do="at", notes=notes[k:k + 120])
        if nexts:
            done = min(nexts.values()) // B.SECTION - 2
            for key in [k for k in g.picks if k[1] < done]:
                del g.picks[key]
            for key in [k for k in g.wanted if k[1] < done]:
                del g.wanted[key]

    def band_part(self, g, song, seat, n):
        """A bar of one of this one's instruments, as it plays it: the count-in (the drums'), then the song's part
        at the level its player picked for the section."""
        if n < 0:
            return B.count_in(song) if seat == "drums" and n == -1 else []
        section = n // B.SECTION
        do, _ = self.band_pick(g, seat, section)
        level, solo, fill = B.played(B.form(g.plan["seed"], section)[seat], do)
        last = n % B.SECTION == B.SECTION - 1
        if seat == "drums" and fill and last:
            g.crash.add(section + 1)
        crash = seat == "drums" and n % B.SECTION == 0 and section in g.crash
        return B.bar(song, seat, n, level, solo, fill and last, crash, g.plan["seed"])

    # -- who decides: dice, or a decision model on your bot's computer ---------------------------------------------------
    def band_decider(self, g):
        """The decision model that picks for this one's players ("": the dice do)."""
        want = self.setting("band_decides")
        if want == DICE or not g.models:
            return ""
        return want if want in g.models else g.models[0]

    def band_models(self, now):
        """Which decision models your bot's computer has, asked now and then; and what came back (those, or a
        player's pick), taken."""
        g = self.gig
        brain = self.band_brain
        for kind, tag, answer, ms, error in brain.take():
            if kind == "models":
                g.models, g.models_for = list(answer or []), tag
                self.dirty = True
            elif kind == "pick" and tag[0] == (g.token, g.n):
                seat, section, model = tag[1:4]
                if answer not in B.SEAT_CHOICES[seat]:
                    print(f"band: no pick for the {seat} ({error or answer})", flush=True)
                    g.failed = now                     # (not asked again for a while: the dice do it meanwhile)
                    continue
                g.model_woke = True
                if g.sent is not None and g.sent[1].get(seat, -1) > section * B.SECTION:
                    continue                           # (it came too late: those bars are with the player already)
                changed = g.picks.get((seat, section), ("",))[0] != answer
                g.picks[(seat, section)] = (answer, model)
                if changed:
                    g.say_now = True
                    self.dirty = True
        if now - g.models_at > BAND_MODELS_FRESH and not brain.busy():
            g.models_at = now
            server = self.snake_server()
            if not server:
                g.models = []
            else:
                brain.ask(("models", server))

    def band_decide(self, now):
        """A model asked what each of this one's players does with the section after this one (one at a time): the
        dice's pick stands till it answers, and for good if it's late."""
        g = self.gig
        model = self.band_decider(g)
        at = self.band_bar()
        if not model or at is None or self.band_brain.busy() or now - g.failed < BAND_MODELS_FRESH:
            return
        section = max(0, at[0] // B.SECTION + (1 if at[0] >= 0 else 0))
        p = g.plan
        for seat in g.mine:
            if (seat, section) in g.wanted or (seat == g.my and self.band_yours(g, now)):
                continue
            self.band_pick(g, seat, section)           # (the dice's, meanwhile)
            before, run = g.picks.get((seat, section - 1)), 0
            while before and g.picks.get((seat, section - 1 - run), ("",))[0] == before[0]:
                run += 1
            others = {s: d[0] for s, d in g.does.items() if s != seat}
            others.update({s: g.picks[(s, section)][0] for s in g.mine if s != seat and (s, section) in g.picks})
            person = (g.my, self.band_busy_now(g, now)) if self.band_yours(g, now) else g.person
            state, says, choices = B.ask(B.song(p["song"]), p["bpm"], seat, section, p["seed"],
                                         (before[0], run) if before else None, others, person)
            wait = BAND_PICK_WAIT[1 if g.model_woke else 0]
            if self.band_brain.ask(("pick", self.snake_server(), model, state, says, choices,
                                    ((g.token, g.n), seat, section, model), wait)):
                g.wanted[(seat, section)] = now
            return

    def band_busy_now(self, g, now):
        """How busily you're playing: 1 to 3, by your notes in the last couple of bars."""
        while g.hits and g.hits[0] < now - 6.0:
            g.hits.popleft()
        return 1 if len(g.hits) < 6 else 2 if len(g.hits) < 16 else 3

    # -- leading: asking the others in, giving out the instruments, telling them the plan ------------------------------
    def band_lead_tick(self, now):
        g = self.gig
        if g.clock is None:
            try:
                g.clock = ClockServer(g.token, BAND_PORT)
            except OSError as ex:
                print(f"band: no clock for the others ({ex}): on its own", flush=True)
                g.clock = False
        if not g.clock or now < g.peers_at:
            return
        g.peers_at = now + 1.0
        for url, name in self.saves_peers():
            if url in g.members or now - g.asked.get(url, -1e9) < BAND_ASK_EVERY \
                    or now - g.left.get(url, -1e9) < BAND_LEFT:
                continue
            g.asked[url] = now
            threading.Thread(target=self.band_ask_in, args=(g, url, name), daemon=True, name="band-ask").start()

    def band_ask_in(self, g, url, name):
        """(A thread of its own.) One of your others asked into this one's band."""
        got = band_post(url, {"kind": "start", "token": g.token, "port": BAND_PORT, "members": len(g.members)},
                        BAND_WAIT)
        self.soon(lambda: self.band_asked_in(g, url, name, got))
        self.wake()

    def band_asked_in(self, g, url, name, got):
        if getattr(self, "gig", None) is not g or not g.lead or not isinstance(got, dict):
            return
        if got.get("ok"):
            self.band_member(g, url, name, got.get("want"))
            return
        theirs = got.get("band")                       # (it has a band of its own, with others in it: into that one)
        if isinstance(theirs, dict) and not g.members and isinstance(theirs.get("token"), str):
            self.band_join(url, name, theirs["token"], BAND_PORT, tell=True)

    def band_member(self, g, url, name, want):
        """One of yours is in: it has the instrument it wants, if no other of them has it (else the next free)."""
        new = url not in g.members
        m = g.members.setdefault(url, {"name": name, "seat": None, "does": {}, "you": 0})
        taken = {x["seat"] for u, x in g.members.items() if u != url}
        order = list(B.SEATS)
        if want in order:
            order = order[order.index(want):] + order[:order.index(want)]
        m["seat"] = next((s for s in order if s not in taken), None)
        self.band_seats(g)
        if new and m["seat"]:
            self.toast(f"{name} is on {B.SEAT_NAME[m['seat']].lower()}", 3)
        g.say_now = True
        self.dirty = True

    def band_seats(self, g):
        """Who has which instrument, worked out again (leading): each of the others its own, this one the rest."""
        held = {m["seat"]: m["name"] for m in g.members.values() if m["seat"]}
        mine = tuple(s for s in B.SEATS if s not in held)
        g.who = {s: held.get(s, "") for s in B.SEATS}
        g.does = {s: d for s, d in g.does.items() if s not in mine}
        if mine != g.mine:
            for s in [x for x in g.mine if x not in mine]:
                self.band_tell(do="clear", whose=s)    # (another has it now: this one's part on it stops)
            g.mine = mine
            self.band_load()

    def band_drop(self, g, url, why=""):
        m = g.members.pop(url, None)
        if m is None:
            return
        print(f"band: {m['name']} is out{': ' + why if why else ''}", flush=True)
        self.toast(f"{m['name']} left the band", 3)
        self.band_seats(g)                             # (its instrument's this one's again, from its next bar)
        g.say_now = True
        self.dirty = True

    def band_say(self, now):
        """What the others are told: leading, each of them the plan, its instrument, and what everyone's doing; in
        another's, the one leading what this one's doing."""
        g = self.gig
        if now - g.say_at < BAND_SAY_EVERY:
            return
        g.say_at, g.say_now = now, False
        at = self.band_bar()
        section = max(0, at[0] // B.SECTION) if at else 0
        does = {s: list(self.band_pick(g, s, section)) for s in g.mine}
        if g.my in g.mine and self.band_yours(g, now):
            does[g.my] = ["follow", "you"]
        you = [g.my, self.band_busy_now(g, now)] if self.band_yours(g, now) else None
        if not g.lead:
            if g.leader and g.planned:
                msg = {"kind": "status", "token": g.token, "does": does, "you": you}
                threading.Thread(target=self.band_tell_leader, args=(g, msg), daemon=True, name="band-say").start()
            return
        every = dict(does)
        for m in g.members.values():
            if m["seat"] and isinstance(m["does"].get(m["seat"]), list):
                every[m["seat"]] = m["does"][m["seat"]]
        g.does = {s: tuple(d) for s, d in every.items() if s not in g.mine}
        theirs = next((m["you"] for m in g.members.values() if m["you"]), None)
        g.person = tuple(theirs) if theirs else None
        person = you or theirs
        for url, m in list(g.members.items()):
            msg = {"kind": "plan", "token": g.token, "plan": g.plan, "seat": m["seat"] or "", "who": self.band_names(g),
                   "does": every, "person": person}
            threading.Thread(target=self.band_tell_member, args=(g, url, msg), daemon=True, name="band-say").start()

    def band_names(self, g):
        own = self.own_name()
        return {s: g.who.get(s) or own for s in B.SEATS}

    def band_tell_member(self, g, url, msg):
        got = band_post(url, msg)
        if got is None or (got.get("ok") is False and got.get("error") == "It isn't in that band"):
            why = "it didn't answer" if got is None else "it's left"
            self.soon(lambda: getattr(self, "gig", None) is g and self.band_drop(g, url, why))
            self.wake()

    def band_tell_leader(self, g, msg):
        got = band_post(g.leader, msg)
        if got is not None and g.planned and got.get("ok") is False and got.get("error") == "It isn't in that band":
            self.soon(lambda: getattr(self, "gig", None) is g and self.band_alone("left out"))
            self.wake()

    # -- in another's ---------------------------------------------------------------------------------------------------
    def band_busy(self):
        """Why this one can't join a band now, or None."""
        why = self.party_busy()
        if why:
            return why
        if self.party_on():
            return "It's in a party"
        if self.prog is not None or self.chromium_shown() or self.view not in ("home", "list", "now"):
            return "It's busy"
        return None

    def band_join(self, url, name, token, port, tell=False):
        """Into another's band: its page up (where this one was is kept, to go back to), its clock set against the
        other's; tell: the other's told this one's in (it wasn't the one that asked)."""
        g = getattr(self, "gig", None)
        if g is not None and g.lead:
            for u in list(g.members):
                threading.Thread(target=band_post, args=(u, {"kind": "stop", "token": g.token}), daemon=True).start()
            if g.clock:
                g.clock.close()
            g.clock, g.members = None, {}
        if not self.band_shown():
            was = (self.view, self.tab)
            if self.sim_opts is not None:
                self.sim_close()
            if self.proc and self.kind in LISTEN_KINDS:
                self.stop()                            # (its own music: the band's instead)
            self.open_app(self.band_index())
            g = self.band_open()
            g.was = was
        g = self.band_open()
        g.lead, g.leader, g.leader_name, g.token, g.port = False, url, name, token, port
        g.offset, g.pinged, g.heard, g.planned = None, 0.0, time.monotonic(), False
        g.plan = dict(g.plan, on=False)
        g.mine, g.sent, g.does, g.person = (), None, {}, None
        g.who = dict.fromkeys(B.SEATS, name)
        self.band_tell(do="clear")
        self.band_ping()
        self.toast(f"In {name}'s band", 3)
        print(f"band: in {name}'s", flush=True)
        if tell:
            threading.Thread(target=band_post, args=(url, {"kind": "join", "token": token, "want": g.my}),
                             daemon=True, name="band-join").start()
        self.dirty = True

    def band_ping(self):
        """The clock of the one that started it against this one's, found again (on a thread of its own)."""
        g = self.gig
        if g.lead or g.pinging or not g.leader:
            return
        g.pinging, g.pinged = True, time.monotonic()

        def ping():
            try:
                got = clock_offset(urllib.parse.urlsplit(g.leader).hostname, g.port, g.token)
            finally:
                g.pinging = False
            self.soon(lambda: self.band_pinged(g, got))
            self.wake()
        threading.Thread(target=ping, daemon=True, name="band-ping").start()

    def band_pinged(self, g, got):
        if getattr(self, "gig", None) is not g or got is None or g.lead:
            return
        was, g.offset = g.offset, got[0]
        if was is not None and abs(got[0] - was) > 0.004:
            self.band_tell(do="clear")                 # (its clock was out: what's with the player, again in step)
            g.sent = None
        self.dirty = True

    def band_in_tick(self, now):
        g = self.gig
        if now - g.pinged > (BAND_PING_EVERY if g.offset is not None else 2.0):
            self.band_ping()
        if now - g.heard > BAND_GONE:
            self.band_alone(f"{g.leader_name} went quiet")

    def band_alone(self, why=""):
        """Out of another's band (it's over, or gone): back where this one was before it was asked in, or on its own
        here."""
        g = self.gig
        name = g.leader_name
        print(f"band: out of {name}'s{': ' + why if why else ''}", flush=True)
        self.band_tell(do="clear")
        was = g.was
        if was is not None and self.band_shown():
            self.band_over(tell=False)
            if was[0] == "list" and was[1] != self.band_index():
                self.open_app(was[1])
            else:
                self.go_home()
            return
        g.lead, g.leader, g.leader_name, g.offset = True, None, "", None
        g.token = secrets.token_urlsafe(16)
        g.mine, g.does, g.person, g.members = B.SEATS, {}, None, {}
        g.who = dict.fromkeys(B.SEATS, "")
        g.plan = self.band_plan(g, on=False)
        g.asked = {}
        self.band_load()
        self.dirty = True

    # -- what's said of it (POST /api/band: the control server's, on the main loop) ------------------------------------
    def web_band(self, cmd):
        """From another of yours: asking this one into its band, then the plan (the song, when it started, this
        one's instrument, what the others are doing), or that it's over; or, to the one leading, another saying what
        it's doing, asking for an instrument, for the band to start or stop, or that it's left."""
        peers = self.saves_peers(str(cmd.get("from") or ""))
        if not peers:
            return {"ok": False, "error": "Not one of your Pietatos"}
        url, host = peers[0]
        kind, token = cmd.get("kind"), cmd.get("token")
        if not isinstance(token, str) or not 16 <= len(token) <= 64:
            return {"ok": False, "error": "What band?"}
        g = getattr(self, "gig", None)
        if kind == "start":
            why = self.band_busy()
            if why:
                return {"ok": False, "error": why}
            if g is not None and not g.lead:
                if g.leader == url and g.token == token:
                    return {"ok": True, "want": g.my}
                return {"ok": False, "error": "It's in another band"}
            if g is not None and (g.members or (not cmd.get("members") and g.token < token)):
                return {"ok": False, "error": "It has a band of its own", "band": {"token": g.token}}
            self.band_join(url, host, token, BAND_PORT)
            return {"ok": True, "want": self.gig.my}
        if g is None:
            return {"ok": False, "error": "It isn't in that band"}
        if g.lead:
            if g.token != token:
                return {"ok": False, "error": "It isn't in that band"}
            if kind == "join":
                self.band_member(g, url, host, cmd.get("want"))
                return {"ok": True}
            m = g.members.get(url)
            if m is None:
                return {"ok": False, "error": "It isn't in that band"}
            if kind == "leave":
                g.left[url] = time.monotonic()
                self.band_drop(g, url, "it left")
            elif kind == "seat":
                self.band_member(g, url, host, cmd.get("want"))
            elif kind == "status":
                does, you = cmd.get("does"), cmd.get("you")
                if isinstance(does, dict):
                    m["does"] = {s: d[:2] for s, d in does.items() if s in B.SEATS and isinstance(d, list)
                                 and len(d) >= 2 and d[0] in B.CHOICES and isinstance(d[1], str)}
                ok = isinstance(you, list) and len(you) == 2 and you[0] in B.SEATS and you[1] in (1, 2, 3)
                m["you"] = you if ok else None
                g.say_now = True
                self.dirty = True
            elif kind == "ask" and cmd.get("what") == "toggle":
                self.band_toggle()
            else:
                return {"ok": False, "error": "What's that?"}
            return {"ok": True}
        if url != g.leader or token != g.token:
            return {"ok": False, "error": "It isn't in that band"}
        g.heard = time.monotonic()
        if kind == "stop":
            self.toast(f"{host}'s band is over", 3)
            self.band_alone("it's over")
            return {"ok": True}
        if kind != "plan":
            return {"ok": False, "error": "What's that?"}
        return self.band_take(g, cmd)

    def band_take(self, g, cmd):
        """(In another's band.) The plan, this one's instrument, who has which, and what they're doing."""
        p, seat = cmd.get("plan"), cmd.get("seat")
        if not isinstance(p, dict) or seat not in B.SEATS + ("",):
            return {"ok": False, "error": "What's that?"}
        n, bpm, t0, seed = p.get("n"), p.get("bpm"), p.get("t0"), p.get("seed")
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in (n, bpm, seed)) \
                or not B.BPM[0] <= bpm <= B.BPM[1] or isinstance(t0, bool) or not isinstance(t0, (int, float)) \
                or not math.isfinite(t0) or not isinstance(p.get("song"), str) or not 0 <= seed < 1 << 31:
            return {"ok": False, "error": "What plan?"}
        new = {"n": n, "song": B.song(p["song"])["key"], "bpm": bpm, "t0": float(t0), "seed": seed, "on": p.get("on") is True}
        was, mine = g.plan, (seat,) if seat else ()
        g.planned = True
        fresh = (was["n"], was["t0"], was["bpm"], was["song"], was["on"], was["seed"]) != \
            (new["n"], new["t0"], new["bpm"], new["song"], new["on"], new["seed"])
        if fresh or mine != g.mine:
            if fresh:
                g.picks, g.wanted, g.crash = {}, {}, set()
                self.band_tell(do="clear")
                if new["on"] and not was["on"] and self.proc and self.kind in LISTEN_KINDS:
                    self.stop()                        # (its own music: the band's instead)
            else:
                for s in g.mine:
                    if s not in mine:
                        self.band_tell(do="clear", whose=s)
            g.n = n
            g.plan, g.mine = new, mine
            if fresh:
                g.sent = None
            self.band_load()
            g.say_now = True
        who, does, person = cmd.get("who"), cmd.get("does"), cmd.get("person")
        if isinstance(who, dict):
            g.who = {s: str(who.get(s) or "")[:40] for s in B.SEATS}
        if isinstance(does, dict):
            g.does = {s: (d[0], d[1][:40]) for s, d in does.items() if s in B.SEATS and s not in mine
                      and isinstance(d, list) and len(d) >= 2 and d[0] in B.CHOICES and isinstance(d[1], str)}
        ok = isinstance(person, list) and len(person) == 2 and person[0] in B.SEATS and person[1] in (1, 2, 3)
        g.person = tuple(person) if ok else None
        self.dirty = True
        return {"ok": True}

    # -- its page -------------------------------------------------------------------------------------------------------
    def band_chords(self, g):
        """(the chord of the bar it's on, the next bar's), as its page and your buttons have them."""
        chart = B.song(g.plan["song"])["chart"]
        at = self.band_bar()
        n = max(0, at[0]) if at else 0
        return chart[n % len(chart)], chart[(n + 1) % len(chart)]

    def band_page(self, s):
        """(sim_game's.) Its page as things are now: who's on what, the chord and the beat, your buttons."""
        g = self.band_open()
        now = time.monotonic()
        p = g.plan
        song = B.song(p["song"])
        at = self.band_bar()
        section = max(0, at[0] // B.SECTION) if at else 0
        own, yours = self.own_name(), self.band_yours(g, now)
        alone = g.lead and not g.members
        seats = []
        for seat in B.SEATS:
            mine = seat in g.mine
            do, by = self.band_pick(g, seat, section) if mine else g.does.get(seat, ("follow", ""))
            level = 0
            if at is not None and at[0] >= 0:
                level, solo, _ = B.played(B.form(p["seed"], section)[seat], do)
                level = 3 if solo else level
            you = mine and seat == g.my and yours
            who = "You" if you else g.who.get(seat) or (own if alone is False else "")   # (on its own: no names)
            doing = B.DO_SAYS.get(do, "") if at is not None and at[0] >= 0 and not you and by != "you" else ""
            seats.append((seat, B.SEAT_NAME[seat], who, doing, 0 if you else level, seat == g.my))
        s.seats = seats
        chord, then = self.band_chords(g)
        s.now = (chord, then, at[1] if at is not None and at[0] >= 0 and g.proc is not None else None)
        if g.gave_up:
            words = "The band can't play just now"
        elif at is not None and at[0] < 0:
            words = "Counting in…"
        elif not g.lead and g.offset is None:
            words = f"Getting in step with {g.leader_name}…"
        elif not g.lead:
            words = f"{g.leader_name} starts it (or SELECT here)"
        elif g.proc is not None and g.loaded and len(g.ready) < len(g.loaded) and not g.bad:
            words = "Tuning up…"
        else:
            words = "SELECT starts the band"
        s.song = (song["name"], p["bpm"], words)
        pads = B.pads(song, g.my, chord)
        s.pads = {pad: (v[0], "ready" if v[1] in g.ready else "bad" if v[1] in g.bad else "loading")
                  for pad, v in pads.items()}
        s.lit = frozenset(pad for pad, t in g.lit.items() if t > now)
        s.bank = (0, 1, "")
        s.trouble = "" if g.sound_ok is not False else "No sound: " + (
            "something else has it" if "busy" in (g.sound_why or "").lower() else "it won't open")
        s.own_hints = [("L R", "Instrument"), ("SELECT", "Stop" if p["on"] else "Start"), ("START", "Back, more")]

        def until():
            at = self.band_bar()
            if at is None:
                return 30.0
            beat = at[2] / B.BEATS
            return max(0.02, beat - ((self.band_clock() - self.gig.plan["t0"]) % beat) + 0.01)
        s.until = until if p["on"] else None

    # -- its buttons ------------------------------------------------------------------------------------------------------
    def band_hit(self, pad):
        """One of your instrument's buttons: its sound, now; and the instrument's yours for a couple of bars (this
        one's own part on it stops)."""
        g = self.gig
        now = time.monotonic()
        song = B.song(g.plan["song"])
        label, sid, gain, lane, long = B.pads(song, g.my, self.band_chords(g)[0])[pad]
        if sid in g.ready:
            self.band_tell(do="play", id=sid, gain=round(gain * max(0.7, self.band_level(g)), 3), lane=lane,
                           secs=0, whose="you")
            if g.sound_ok is False and now - g.busy_said > 5:
                g.busy_said = now
                self.toast("No sound: " + ("something else has it" if "busy" in (g.sound_why or "").lower()
                                           else "it won't open"), 3)
        g.hits.append(now)
        was = self.band_yours(g, now)
        g.yours_till = now + BAND_YOURS * B.BEATS * 60.0 / g.plan["bpm"]
        if not was:
            if g.my in g.mine:
                self.band_tell(do="clear", whose=g.my)
            g.say_now = True
        g.lit[pad] = now + BAND_LIT
        self.dirty = True

    def band_seat_step(self, way):
        """L or R: the instrument your buttons play, the one before or after. In another's band, this one asks for
        it too (and has it, if none of the others does)."""
        g = self.gig
        g.my = B.SEATS[(B.SEATS.index(g.my) + way) % len(B.SEATS)]
        g.yours_till, g.lit = 0.0, {}
        g.hits.clear()
        self.set_setting("band_seat", g.my)
        self.band_load()
        if not g.lead and g.leader:
            threading.Thread(target=band_post, args=(g.leader, {"kind": "seat", "token": g.token, "want": g.my}),
                             daemon=True, name="band-seat").start()
        g.say_now = True
        self.dirty = True

    def band_toggle(self):
        """SELECT: the band starts (a bar counted in), or stops. In another's: the one leading is asked."""
        g = self.gig
        if not g.lead:
            if g.leader:
                threading.Thread(target=band_post, args=(g.leader, {"kind": "ask", "what": "toggle", "token": g.token}),
                                 daemon=True, name="band-ask").start()
            return
        on = not g.plan["on"]
        if on and self.proc and self.kind in LISTEN_KINDS:
            self.stop()                                # (the music that was playing: the band's instead)
        g.plan = self.band_plan(g, on)
        self.band_tell(do="clear")
        self.band_load()
        g.say_now, g.say_at = True, 0.0
        self.dirty = True

    def band_replan(self):
        """Another song (leading): from the top, a bar counted in, if it was playing."""
        g = self.gig
        g.plan = self.band_plan(g, g.plan["on"])
        self.band_tell(do="clear")
        self.band_load()
        g.say_now, g.say_at = True, 0.0
        self.dirty = True

    def band_retime(self, bpm):
        """Faster or slower (leading): from where the song is, at its next bar."""
        g = self.gig
        p = g.plan
        clock = self.band_clock()
        beats = (clock - p["t0"]) * p["bpm"] / 60.0
        g.n += 1
        g.plan = dict(p, n=g.n, bpm=bpm, t0=clock - beats * 60.0 / bpm)
        g.sent, g.wanted = None, {}
        self.band_tell(do="clear")
        g.say_now, g.say_at = True, 0.0
        self.dirty = True

    def press_band(self, s, name, repeat):
        """Its buttons (not START's card: press_band_card). Every one is its own: none goes back, or on to the next
        app."""
        g = self.band_open()
        if repeat:
            return None
        if name in B.PADS:
            self.band_hit(name)
        elif name in ("l", "r", "l2", "r2"):
            self.band_seat_step(-1 if name in ("l", "l2") else 1)
        elif name == "select":
            self.band_toggle()
        elif name == "start":
            g.card = "more"
            self.sim_opts = 0
            self.dirty = True
        return None

    # -- START's card ------------------------------------------------------------------------------------------------------
    def band_rows(self):
        g = self.gig
        song = B.song(g.plan["song"])
        rows = []
        if g.lead:
            rows += [("song", "Song", song["name"]), ("tempo", "Tempo", str(g.plan["bpm"]))]
        rows += [("seat", "Your instrument", B.SEAT_NAME[g.my]), ("volume", "Volume", str(self.volume))]
        if g.members or not g.lead:                    # (with others: this one's sound against theirs)
            ms = int(round(self.band_early(g) * 1000))
            rows.append(("early", "Timing", f"{abs(ms)} ms {'early' if ms > 0 else 'late'}" if ms else "0 ms"))
        if g.models:
            rows.append(("decides", "Who decides", self.band_decider(g) or DICE))
        return rows

    def band_card_shut(self):
        self.gig.card = None
        self.sim_close()

    def press_band_card(self, s, name, repeat):
        """START's card: ▲▼ pick a row, ◀▶ change it; A or START goes on with the band, B goes back to Apps (here,
        where it isn't a sound); SELECT starts and stops it."""
        g = self.band_open()
        rows = self.band_rows()
        sel = self.sim_opts % len(rows)
        key = rows[sel][0]
        way = 1 if name == "right" else -1
        if name in ("up", "down"):
            self.sim_opts = (sel + (1 if name == "down" else -1)) % len(rows)
        elif name in ("left", "right") and key == "volume":
            self.set_volume(VOLUME_STEP * way)
        elif name in ("left", "right") and key == "tempo":
            bpm = max(B.BPM[0], min(B.BPM[1], g.plan["bpm"] + 4 * way))
            if bpm != g.plan["bpm"]:
                self.set_setting("band_bpm_" + g.plan["song"], bpm)
                self.band_retime(bpm)
        elif name in ("left", "right") and key == "early":   # (◀: earlier. Its next bars have it)
            ms = int(round(self.band_early(g) * 1000)) - BAND_EARLY[1] * way
            self.set_setting("band_early_" + (g.place or "own"), max(-BAND_EARLY[0], min(BAND_EARLY[0], ms)))
        elif repeat:
            return None
        elif name in ("left", "right") and key == "song":
            keys = [x["key"] for x in B.SONGS]
            self.set_setting("band_song", keys[(keys.index(g.plan["song"]) + way) % len(keys)])
            self.band_replan()
        elif name in ("left", "right") and key == "seat":
            self.band_seat_step(way)
        elif name in ("left", "right") and key == "decides":
            ways = [DICE] + list(g.models)
            now = self.band_decider(g) or DICE
            self.set_setting("band_decides", ways[(ways.index(now) + way) % len(ways)])
            g.wanted = {}
        elif name in ("l", "r", "l2", "r2"):
            self.band_seat_step(-1 if name in ("l", "l2") else 1)
        elif name in ("a", "start"):
            self.band_card_shut()
        elif name == "select":
            self.band_toggle()
        elif name == "b":
            self.band_card_shut()
            return "pass"                              # (back to Apps, as B goes back anywhere else)
        else:
            return None
        self.dirty = True
        return None

    def band_card_hints(self):
        g = self.band_open()
        return [("▲▼", "Choose"), ("◀▶", "Change"), ("A", "Done"),
                ("B", "Back to Apps" if g.lead else "Leave the band")]

    def band_card_key(self):
        g = self.band_open()
        rows = self.band_rows()
        return ("opts", "band", g.card, self.sim_opts % len(rows), tuple(rows), g.lead, self.sim_box())

    def band_opts_card(self, s):
        g = self.band_open()
        names = [m["name"] for m in g.members.values()]
        if not g.lead:
            lede = f"In {g.leader_name}'s band. It has the song and the tempo."
        elif names:
            lede = "With " + (names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]) + "."
        else:
            lede = s.blurb
        return self.rows_card(LIBRARY[self.tab].get("title") or LIBRARY[self.tab]["name"], lede, self.band_rows(), False)
