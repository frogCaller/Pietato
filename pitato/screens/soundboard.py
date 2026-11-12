"""Apps > Soundboard, in media mode (soundboard.py draws it, soundbank.py has its sounds and banks, soundplay.py plays
them). Its player's a process of its own, as you, started with the page and gone as you leave it. While the page is
up, your Soundboard folder and the banks' file are looked at every second, so a new sound is on its button without
anything being started again (and at once when the web page says it changed something); the sound goes where
Settings > Sound says, as it changes; and whether there's a microphone is known, so Record a sound is on START's card
only when there's one to record with.

Its buttons: the d-pad's four, A, B, X and Y play what's on them; L and R go through the banks; SELECT stops
everything; START has its card (the bank, the volume, Record a sound), where A or START goes on and B goes back to
Apps. Recording: A keeps it, B drops it; kept (its silence trimmed, a file in your Soundboard folder), the next button
pressed is the one it goes on (L and R: in another bank; SELECT: hear it first; START: leave it where it is, record it
again, or delete it)."""
import json
import os
import subprocess
import sys
import threading
import time

from .. import soundbank as B
from ..asyou import as_you, nice_now
from ..config import home_dir, read_own_text, settings_file, write_setting
from ..library import LIBRARY, VOLUME_STEP
from ..listen import mics
from ..screen import aplay_device, sound_place
from ..theme import ACCENT, BODY, co_mix, LINE, MUTED, ROW, TEXT
from ..util import home_folder

PLAYER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "soundplay.py")
BOARD_NICE = -8                  # its player's priority: ahead of the menus (a late sound is heard)
BOARD_LOOK = 1.0                 # seconds between looks at whether your folder or the banks' file has changed
BOARD_DEEP = 5.0                 # ...and at each of your sounds (one changed where it is)
BOARD_ROUTE = 2.0                # ...at where the sound goes, and whether there's a microphone
BOARD_AGAIN = (1.0, 5)           # a player that stops is started again after this long, this many times running
BOARD_QUIET = 2.0                # seconds the sound card's let go of for something else that starts playing
BOARD_BEHIND = 256 << 10         # bytes waiting for a player that isn't taking them, before it's stopped (and started again)
PAD_SAY = {"up": "Up", "down": "Down", "left": "Left", "right": "Right", "x": "X", "y": "Y", "a": "A", "b": "B"}


class Board:
    """The Soundboard while it's been opened: its player, the banks as they are, and what's going on."""

    def __init__(self):
        self.proc = None
        self.out = b""                 # what its player's to be told, not taken yet (its pipe full: seldom)
        self.banks, self.off = [], []
        self.at = 0                    # which bank's on the page
        self.ready, self.bad = {}, {}  # a sound -> its seconds; a sound -> why it can't be played
        self.playing = frozenset()     # the sounds heard now
        self.sound_ok, self.sound_why = None, ""   # the sound card: open (True), won't open (False), not known yet
        self.busy_said = -1e9
        self.device, self.volume, self.loaded = None, None, None   # what its player's been told
        self.quick, self.seen = None, None   # your folder and the banks' file as last looked at: by date, and whole
        self.look_at = self.deep_at = self.route_at = 0.0
        self.mic = None                # arecord's -D for the microphone there is, or None
        self.rec = None                # recording: {"secs", "level", "drawn", "ending"}
        self.ears = False              # the Bot was listening before it (and will again after)
        self.placing = None            # a sound just recorded, waiting for the button it goes on
        self.card = None               # START's card: "more", or "kept" (a recording's)
        self.rested = False            # the sound card's let go of (the Bot's talking)
        self.rest_till = 0.0
        self.start_at, self.stops = 0.0, 0
        self.gave_up = False

    def bank(self):
        return self.banks[self.at] if 0 <= self.at < len(self.banks) else None


class SoundboardScreen:
    """Apps > Soundboard: its player, its sounds as they change, its buttons, START's card, recording."""

    # -- where it is ------------------------------------------------------------------------------------------------------
    def board_tab(self):
        """This page is the Soundboard's."""
        try:
            return self.tab_type() == "sim" and LIBRARY[self.tab].get("sim") == "sound"
        except (AttributeError, IndexError, KeyError, TypeError):
            return False

    def board_shown(self):
        return bool(self.active and self.view == "list" and self.board_tab())

    def board_folder(self):
        """Your Soundboard folder (made the first time, yours)."""
        return home_folder(B.FOLDER)

    def board_open(self):
        """The Soundboard, as it is: made the first time its page is opened, its banks read."""
        b = getattr(self, "board", None)
        if b is None:
            b = self.board = Board()
        if not b.banks:
            self.board_look(time.monotonic(), force=True)
            want = self.setting("board_bank")
            b.at = next((i for i, bank in enumerate(b.banks) if bank["name"] == want), 0)
        return b

    # -- its player: a process of its own, as you -----------------------------------------------------------------------
    def board_start(self, now):
        b = self.board
        home = home_dir()
        pre, you = as_you(home)

        def ahead():
            try:
                os.nice(BOARD_NICE)
            except OSError:
                pass
        cmd = pre + [sys.executable, "-I", PLAYER, os.path.join(home, ".cache", "pitato", "soundboard")]
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd="/", bufsize=0,
                                    **(you or {"preexec_fn": ahead}))
            os.set_blocking(proc.stdin.fileno(), False)    # (media mode never waits on it: board_send)
        except OSError as ex:
            print(f"soundboard: its player wouldn't start ({ex})", flush=True)
            b.start_at, b.stops = now + BOARD_AGAIN[0], b.stops + 1
            return
        if you:
            nice_now(proc, BOARD_NICE)
        b.proc, b.out = proc, b""
        b.device = b.volume = b.loaded = None
        b.ready, b.bad, b.playing = {}, {}, frozenset()
        b.sound_ok, b.sound_why, b.rested = None, "", False
        proc.started = now
        threading.Thread(target=self.board_reader, args=(proc,), daemon=True, name="soundboard").start()
        self.board_route(now)
        if self.board_tell(do="volume", v=self.volume):
            b.volume = self.volume
        self.board_look(now, force=True)               # (its sounds as they are now, and its player told)
        if not self.voice.speaking:
            self.board_tell(do="warm")

    def board_tell(self, **what):
        """A line to its player. False: it isn't there (any more)."""
        b = getattr(self, "board", None)
        if b is None or b.proc is None:
            return False
        b.out += (json.dumps(what) + "\n").encode()
        return self.board_send()

    def board_send(self):
        """What its player's to be told, sent: at once, as a rule; if its pipe's full, as much as it takes now and the
        rest at the next tick (media mode never waits on it). One that takes nothing for long is stopped, and started
        again like one that stopped by itself. False: it isn't there (any more)."""
        b = self.board
        try:
            while b.out:
                n = os.write(b.proc.stdin.fileno(), b.out[:1 << 16])
                b.out = b.out[n:]
        except BlockingIOError:
            if len(b.out) > BOARD_BEHIND:
                print("soundboard: its player isn't listening: stopped", flush=True)
                b.out = b""
                try:
                    b.proc.kill()
                except OSError:
                    pass
                return False
        except (OSError, ValueError):
            b.out = b""
            return False
        return True

    def board_reader(self, proc):
        """(A thread of its own.) What its player says, passed to media mode's own thread a line at a time."""
        try:
            for line in proc.stdout:
                try:
                    said = json.loads(line)
                except ValueError:
                    continue
                if isinstance(said, dict):
                    self.soon(lambda said=said: self.board_said(proc, said))
                    self.wake()
        except (OSError, ValueError):
            pass
        self.soon(lambda: self.board_gone(proc))
        self.wake()

    def board_gone(self, proc):
        """Its player has stopped by itself: started again in a moment (a few times running, then left be)."""
        b = getattr(self, "board", None)
        if b is None or b.proc is not proc:
            return
        try:
            proc.wait(0.5)
        except (OSError, subprocess.TimeoutExpired):
            pass
        now = time.monotonic()
        print(f"soundboard: its player stopped (exit code {proc.returncode})", flush=True)
        b.proc = None
        b.stops = b.stops + 1 if now - getattr(proc, "started", now) < 30 else 1
        b.start_at = now + BOARD_AGAIN[0]
        b.ready, b.playing, b.sound_ok = {}, frozenset(), None
        if b.rec is not None:
            self.board_rec_over()
        if b.stops >= BOARD_AGAIN[1] and not b.gave_up:
            b.gave_up = True
            self.toast("The Soundboard can't play just now", 4)
        self.dirty = True

    def board_stop(self):
        """Leaving its page: its player quits (a recording under way is dropped), and the bank you were on is kept
        for next time."""
        b = getattr(self, "board", None)
        if b is None:
            return
        proc, b.proc = b.proc, None
        if b.rec is not None:
            self.board_rec_over()
        b.placing = b.card = None
        b.ready, b.bad, b.playing = {}, {}, frozenset()
        b.sound_ok, b.stops, b.gave_up, b.start_at = None, 0, False, 0.0
        bank = b.bank()
        if bank is not None and len(b.banks) > 1 and self.setting("board_bank") != bank["name"]:
            self.set_setting("board_bank", bank["name"])
        if proc is None:
            return
        b.out = b""
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
        threading.Thread(target=reap, daemon=True, name="soundboard-end").start()

    def board_said(self, proc, said):
        """(Media mode's own thread.) What its player said."""
        b = getattr(self, "board", None)
        if b is None or b.proc is not proc:
            return
        what, sid = said.get("is"), said.get("id")
        if what == "ready" and isinstance(sid, str):
            b.ready[sid] = said.get("secs") or 0
            b.bad.pop(sid, None)
            b.stops = 0
        elif what == "bad" and isinstance(sid, str):
            b.bad[sid] = str(said.get("why") or "")[:80]
            b.ready.pop(sid, None)
        elif what == "playing":
            b.playing = frozenset(s for s in said.get("ids") or () if isinstance(s, str))
        elif what == "sound":
            ok = said.get("ok") is True
            if ok != b.sound_ok:
                print("soundboard: " + (f"playing through a {said.get('buffer')} ms buffer" if ok else
                                        f"the sound won't open ({said.get('why')})"), flush=True)
            b.sound_ok, b.sound_why = ok, "" if ok else str(said.get("why") or "")
        elif what == "level" and b.rec is not None:
            now = time.monotonic()
            b.rec["secs"], b.rec["level"] = said.get("secs") or 0, said.get("peak") or 0
            if now - b.rec["drawn"] < 0.1:
                return                                 # (its meter: ten times a second is plenty)
            b.rec["drawn"] = now
        elif what == "recorded":
            self.board_recorded(said)
        else:
            return
        self.dirty = True

    # -- its sounds and banks, as they are now ----------------------------------------------------------------------------
    def board_look(self, now, force=False):
        """Your Soundboard folder and the banks' file, looked at: when either has changed (a file added, taken
        away or renamed; the web page's Soundboard), the banks are worked out again and its player's told. A new sound
        of yours goes on My sounds' first free button, and the file's written to say so."""
        b = self.board
        b.look_at = now + BOARD_LOOK
        path = settings_file(B.FILE)
        try:
            folder = self.board_folder()
            when = os.stat(folder).st_mtime_ns
        except OSError:
            return
        try:
            st = os.stat(path)
            filed = (st.st_mtime_ns, st.st_size)
        except OSError:
            filed = None
        quick = (when, filed)
        if not force and quick == b.quick and now < b.deep_at:
            return
        b.quick, b.deep_at = quick, now + BOARD_DEEP
        try:
            files = B.scan(folder)
        except OSError:
            return                                     # (it can't be read just now: as it was)
        text = None
        if filed is not None:
            try:
                text = read_own_text(path)
            except (OSError, ValueError):
                if b.banks:
                    return
        seen = (tuple(files), text)
        if seen == b.seen and not force:
            return
        had = {name for name, _, _ in b.seen[0]} if b.seen is not None and b.loaded is not None else None
        b.seen = seen
        was = b.bank()["name"] if b.bank() is not None else None
        banks, off, placed = B.arrange(text, [name for name, _, _ in files], B.starter_sounds())
        b.banks, b.off = banks, off
        if placed:
            self.board_keep()
        b.at = next((i for i, bank in enumerate(banks) if bank["name"] == was), min(b.at, len(banks) - 1))
        new = [name for name, _, _ in files if name not in had] if had is not None else []
        if new and b.rec is None and b.placing is None and self.sim_opts is None:
            at = B.where(banks, new[-1])               # (a file just put in the folder: where it is, shown and said)
            if at is not None:
                b.at = at[0]
                self.toast(f"{B.title(new[-1])} is on {PAD_SAY[at[1]]} in {banks[at[0]]['name']}", 3)
        self.board_load()
        self.dirty = True

    def board_keep(self):
        """The banks as they are, written to their file (yours)."""
        b = self.board
        try:
            text = B.dumps(b.banks, b.off)
            path = write_setting(B.FILE, text)
            st = os.stat(path)
        except OSError as ex:
            print(f"soundboard: couldn't keep its banks ({ex})", flush=True)
            return False
        if b.quick is not None:                        # (its own writing: not a change to look into)
            b.quick = (b.quick[0], (st.st_mtime_ns, st.st_size))
        if b.seen is not None:
            b.seen = (b.seen[0], text)
        return True

    def board_load(self):
        """Its player told which sounds there are: this bank's first, then the banks either side, and so on out."""
        b = self.board
        n = len(b.banks)
        if not n:
            return
        order = [b.at % n]
        for k in range(1, n):
            for i in ((b.at + k) % n, (b.at - k) % n):
                if i not in order:
                    order.append(i)
        folder = os.path.join(home_dir(), B.FOLDER)
        sounds = []
        for i in order:
            for pad in B.PADS:
                sid = b.banks[i]["pads"].get(pad)
                path = B.path_of(sid, folder) if sid else None
                if path:
                    sounds.append([sid, path])
        names = {sid for sid, _ in sounds}
        b.ready = {s: v for s, v in b.ready.items() if s in names}
        b.bad = {s: v for s, v in b.bad.items() if s in names}
        sig = (tuple(map(tuple, sounds)), b.seen[0] if b.seen else None)
        if b.proc is not None and sig != b.loaded and self.board_tell(do="load", sounds=sounds):
            b.loaded = sig

    def board_route(self, now):
        """Where the sound goes (Settings > Sound, Bluetooth headphones as they come and go), its volume, and whether
        there's a microphone to record with: its player told what's changed."""
        b = self.board
        b.route_at = now + BOARD_ROUTE
        device = aplay_device(None, sound_place(self.setting("sound"))[0])
        if device != b.device and self.board_tell(do="device", device=device):
            b.device = device
        mic = self.board_mic()
        if mic != b.mic:
            b.mic = mic
            self.dirty = True

    def board_mic(self):
        """arecord's -D for the microphone a sound's recorded with: the one picked for the Bot (Settings > Bot) if
        it's plugged in, else one you plugged in, else a webcam's. None: there's none (and no Record a sound)."""
        try:
            found = mics()
            picked = self.bot_mic_set()
            own = self.auto_mics(found)
        except Exception as ex:
            print(f"soundboard: couldn't look for a microphone ({ex!r})", flush=True)
            return None
        hit = (next((c for c in found if picked and c["id"] == picked), None) or (own[0] if own else None)
               or next((c for c in found if c["camera"] and c["usb"]), None))
        return hit["device"] if hit else None

    def board_tick(self, now):
        """Each tick: its player started with its page and stopped as it's left; its sounds, the sound's way out and
        the microphone looked at now and then; the sound card let go of while the Bot talks."""
        b = getattr(self, "board", None)
        shown = self.board_shown()
        if not shown:
            if b is not None and (b.proc is not None or b.rec is not None or b.placing is not None):
                self.board_stop()
            return
        b = self.board_open()
        if b.proc is None:
            if now < b.start_at or b.stops >= BOARD_AGAIN[1]:
                return
            self.board_start(now)
            if b.proc is None:
                return
        if b.out:
            self.board_send()
        if now >= b.look_at:
            self.board_look(now)
        if now >= b.route_at:
            self.board_route(now)
        if b.volume != self.volume and self.board_tell(do="volume", v=self.volume):
            b.volume = self.volume
        quiet = bool(self.voice.speaking) or now < b.rest_till
        if quiet != b.rested:                          # (the Bot's talking: it has the sound card, as a player would)
            b.rested = quiet
            self.board_tell(do="rest" if quiet else "warm")

    def board_quiet(self, secs=BOARD_QUIET):
        """Something else starts playing (the Bot's voice, a song): the sound card's let go of for it, at once."""
        b = getattr(self, "board", None)
        if b is None or b.proc is None:
            return
        b.rest_till = time.monotonic() + secs
        if not b.rested:
            b.rested = True
            self.board_tell(do="rest")

    def board_web(self, cmd):
        """The web page's Soundboard changed something: looked at now, not at the next look."""
        b = getattr(self, "board", None)
        if b is not None:
            b.look_at = b.deep_at = 0.0
            b.quick = None
            if self.board_shown():
                self.wake()
        return {"ok": True, "open": bool(b is not None and b.proc is not None)}

    # -- its page -------------------------------------------------------------------------------------------------------
    def board_page(self, s):
        """(sim_game's.) Its page as things are now: the bank, what's on each button and whether it's ready, the ones
        playing, and its buttons along the bottom."""
        b = self.board_open()
        bank = b.bank()
        pads = bank["pads"] if bank is not None else {}
        s.bank = (b.at, len(b.banks), bank["name"] if bank is not None else "")
        s.pads = {pad: (B.title(sid), "bad" if sid in b.bad else "ready" if sid in b.ready else "loading")
                  for pad, sid in pads.items() if sid}
        s.lit = frozenset(pad for pad, sid in pads.items() if sid and sid in b.playing)
        s.trouble = "" if b.sound_ok is not False else "No sound: " + self.board_trouble()
        s.rec = (b.rec["secs"], b.rec["level"]) if b.rec is not None else None
        if b.placing is not None:
            s.placing = (B.title(b.placing), next((pad for pad, sid in pads.items() if sid == b.placing), None))
        else:
            s.placing = None
        many = [("L R", "Bank")] if len(b.banks) > 1 else []
        if b.rec is not None:
            s.own_hints = [("A", "Keep it"), ("B", "Cancel")]
        elif b.placing is not None:
            s.own_hints = many + [("SELECT", "Hear it"), ("START", "More")]
        else:
            s.own_hints = many + [("SELECT", "Stop"), ("START", "Back, more")]

    def board_trouble(self):
        why = (self.board.sound_why or "").lower()
        return "something else has it" if "busy" in why else "it won't open"

    def board_step(self, way):
        """L or R: the bank before or after (round and round)."""
        b = self.board
        if len(b.banks) < 2:
            return
        b.at = (b.at + way) % len(b.banks)
        self.board_load()
        self.dirty = True

    def board_play(self, pad):
        b = self.board
        bank = b.bank()
        sid = bank["pads"].get(pad) if bank is not None else None
        if not sid:
            return
        if sid in b.bad:
            why = b.bad[sid] or "it can't be read"
            self.toast(f"{B.title(sid)} can't be played ({why})", 3)
            return
        if sid not in b.ready:
            return                                     # (not read yet, its name still dim: not played late)
        self.board_tell(do="play", id=sid)
        now = time.monotonic()
        if b.sound_ok is False and now - b.busy_said > 5:
            b.busy_said = now
            self.toast("No sound: " + self.board_trouble(), 3)

    def press_board(self, s, name, repeat):
        """Its buttons (not START's card: press_board_card). Every one is its own: none goes back, or on to the next
        app."""
        b = self.board_open()
        if repeat:
            return None                                # (held down: once is once)
        if b.rec is not None:                          # recording: A keeps it, B drops it
            if name in ("a", "b") and not b.rec["ending"]:
                self.board_rec_stop(name == "a")
            return None
        if name in B.PADS:
            if b.placing is not None:
                self.board_place(name)
            else:
                self.board_play(name)
        elif name in ("l", "r", "l2", "r2"):
            self.board_step(-1 if name in ("l", "l2") else 1)
        elif name == "select":
            if b.placing is not None:
                self.board_tell(do="play", id=b.placing)
            else:
                self.board_tell(do="stop")
        elif name == "start":
            b.card = "kept" if b.placing is not None else "more"
            self.sim_opts = 0
            self.dirty = True
        return None

    # -- START's card ------------------------------------------------------------------------------------------------------
    def board_rows(self):
        """Its card's rows: (key, label, its value or None: A does it)."""
        b = self.board
        if b.card == "kept":
            at = B.where(b.banks, b.placing) if b.placing else None
            stay = f"Leave it on {PAD_SAY[at[1]]} in {b.banks[at[0]]['name']}" if at else "Leave it off the buttons"
            return [("stay", stay, None), ("again", "Record it again", None), ("delete", "Delete it", None)]
        bank = b.bank()
        rows = [("bank", "Bank", bank["name"] if bank is not None else ""), ("volume", "Volume", str(self.volume))]
        if b.mic is not None and b.proc is not None:
            rows.append(("rec", "Record a sound", None))
        return rows

    def board_card_shut(self):
        self.board.card = None
        self.sim_close()

    def press_board_card(self, s, name, repeat):
        """START's card: ▲▼ pick a row, ◀▶ change it; A or START goes on with the Soundboard, B goes back to Apps
        (here, where it isn't a sound). A recording's card: A does the row, B or START shuts it."""
        b = self.board_open()
        rows = self.board_rows()
        sel = self.sim_opts % len(rows)
        key = rows[sel][0]
        if name in ("up", "down"):
            self.sim_opts = (sel + (1 if name == "down" else -1)) % len(rows)
        elif name in ("left", "right") and key == "volume":
            self.set_volume(VOLUME_STEP if name == "right" else -VOLUME_STEP)
        elif repeat:
            return None
        elif b.card == "kept":
            if name == "a":
                self.board_kept_do(key)
            elif name in ("b", "start"):
                self.board_card_shut()
            elif name == "select" and b.placing:
                self.board_tell(do="play", id=b.placing)
            else:
                return None
        elif name in ("left", "right") and key == "bank":
            self.board_step(1 if name == "right" else -1)
        elif name in ("l", "r", "l2", "r2"):
            self.board_step(-1 if name in ("l", "l2") else 1)
        elif name == "a" and key == "rec":
            self.board_card_shut()
            self.board_rec_start()
        elif name in ("a", "start"):
            self.board_card_shut()
        elif name == "select":
            self.board_tell(do="stop")
        elif name == "b":
            self.board_card_shut()
            return "pass"                              # (back to Apps, as B goes back anywhere else)
        else:
            return None
        self.dirty = True
        return None

    def board_card_hints(self):
        b = self.board_open()
        rows = self.board_rows()
        key, _, value = rows[self.sim_opts % len(rows)]
        if b.card == "kept":
            return [("▲▼", "Choose"), ("A", "OK"), ("SELECT", "Hear it"), ("B", "Not now")]
        if value is None:
            return [("▲▼", "Choose"), ("A", "Record"), ("START", "Done"), ("B", "Back to Apps")]
        return [("▲▼", "Choose"), ("◀▶", "Change"), ("A", "Done"), ("B", "Back to Apps")]

    def board_card_key(self):
        """What its card shows (drawn again when it changes)."""
        b = self.board_open()
        rows = self.board_rows()
        return ("opts", "sound", b.card, self.sim_opts % len(rows), tuple(rows), b.placing, self.sim_box(), ACCENT)

    def board_opts_card(self, s):
        """START on its page: the bank, the volume, and Record a sound when there's a microphone. Or a recording's:
        where it stays, again, or gone."""
        from ..fine import Image, ImageDraw
        b = self.board_open()
        rows = self.board_rows()
        if b.card == "kept":
            probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
            title = self.fit(probe, B.title(b.placing or ""), self.fonts["head"], 360)
            secs = b.ready.get(b.placing)
            return self.rows_card(title, [f"{secs:.1f} seconds long." if secs else "Your new sound."], rows, False)
        return self.rows_card(LIBRARY[self.tab].get("title") or LIBRARY[self.tab]["name"], s.blurb, rows)

    def rows_card(self, title, lede, rows, press_a=True):
        """A card of rows over a sim's page (the Soundboard's, the Band's): its title, a line or two (lede: words to
        wrap, or lines as they are), then each row (key, label, its value or None: A does it), the one picked lit."""
        from ..fine import Image, ImageDraw
        F = self.fonts
        sel = self.sim_opts % len(rows)
        W, rh = 404, 38
        probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        if isinstance(lede, str):
            lede = self.wrap(probe, lede, F["small"], W - 44, lines=3)
        top = 56 + 20 * len(lede) + 6
        H = top + rh * len(rows) + 10
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((0, 0, W - 1, H - 1), radius=12, fill=ROW + (255,), outline=LINE + (255,))
        d.text((22, 30), title, font=F["head"], fill=TEXT, anchor="lm")
        y = 56
        for line in lede:
            d.text((22, y), line, font=F["small"], fill=MUTED, anchor="lm")
            y += 20
        y = top
        for i, (key, label, value) in enumerate(rows):
            on, mid = i == sel, y + rh / 2 - 1
            if on:
                d.rounded_rectangle((10, y, W - 11, y + rh - 4), radius=8, fill=co_mix(ROW, TEXT, 0.07))
                d.rectangle((10, y + 9, 13, y + rh - 13), fill=ACCENT)
            x1, font = W - 24, F["small_b"] if on else F["small"]
            room = W - 60 if value is None else 150
            d.text((26, mid), self.fit(d, label, F["small"], room), font=F["small"], fill=TEXT if on else BODY,
                   anchor="lm")
            if value is not None:
                value = self.fit(d, value, font, 180)
                if on:
                    d.text((x1, mid), "▶", font=F["small"], fill=ACCENT, anchor="rm")
                    x1 -= 22
                d.text((x1, mid), value, font=font, fill=ACCENT if on else MUTED, anchor="rm")
                if on:
                    d.text((x1 - d.textlength(value, font=font) - 10, mid), "◀", font=F["small"], fill=ACCENT,
                           anchor="rm")
            elif on and press_a:
                d.text((x1, mid), "Press A", font=font, fill=ACCENT, anchor="rm")
            y += rh
        (bx0, by0, bx1, by1), _ = self.sim_box()
        return img, ((bx0 + bx1 - W) // 2, max(by0, (by0 + by1 - H) // 2))

    # -- a new sound, recorded -------------------------------------------------------------------------------------------
    def board_rec_start(self):
        """Record a sound: the Bot stops listening meanwhile (the microphone's one program's at a time), what's
        playing stops, and its player records."""
        b = self.board
        if b.proc is None or b.mic is None or b.rec is not None:
            return
        b.ears = bool(self.ears.on)
        if b.ears:
            self.ears.stop()
        b.placing = None
        if not self.board_tell(do="rec", mic=b.mic, folder=os.path.join(home_dir(), B.FOLDER)):
            self.board_rec_over()
            return
        b.rec = {"secs": 0.0, "level": 0.0, "drawn": 0.0, "ending": False}
        self.dirty = True

    def board_rec_stop(self, keep):
        b = self.board
        if b.rec is None:
            return
        b.rec["ending"] = True
        if not self.board_tell(do="rec_stop", keep=bool(keep)):
            self.board_rec_over()
        self.dirty = True

    def board_rec_over(self):
        """Recording's done with, one way or another: the Bot listens again, if it was."""
        b = self.board
        b.rec = None
        if b.ears:
            b.ears = False
            try:
                self.listen_now(quiet=True)
            except Exception as ex:
                print(f"soundboard: the Bot couldn't listen again ({ex!r})", flush=True)
        self.dirty = True

    def board_recorded(self, said):
        """Its player's done recording: kept (the file's name), and the next button pressed is where it goes; or not
        (nothing was heard, the microphone didn't answer, B)."""
        b = self.board
        self.board_rec_over()
        name, why = said.get("name"), said.get("why")
        if not isinstance(name, str) or B.sound_name(name) is None:
            if why == "quiet":
                self.toast("Nothing was heard", 3)
            elif why == "mic":
                print(f"soundboard: no recording ({said.get('said')})", flush=True)
                self.toast("The microphone didn't answer", 3)
            elif why == "file":
                why = said.get("said") or "the folder can't be written to"
                self.toast(f"It couldn't be kept ({why})", 4)
            return
        b.placing = name                               # (the page says what to do now)
        self.board_look(time.monotonic(), force=True)  # (it's a file in your folder now: on a button, like any new one)
        at = B.where(b.banks, name)
        if at is None and name not in b.off:
            b.placing = None                           # (gone already: nothing to put anywhere)
        elif at is not None and at[0] != b.at:
            b.at = at[0]
            self.board_load()

    def board_place(self, pad):
        """A button pressed for the sound just recorded: it goes on it (what was there, where this one was)."""
        b = self.board
        sid, b.placing = b.placing, None
        if B.where(b.banks, sid) != (b.at, pad):
            B.put(b.banks, b.off, sid, b.at, pad)
            self.board_keep()
            self.board_load()
        self.toast(f"{B.title(sid)} is on {PAD_SAY[pad]} in {b.banks[b.at]['name']}", 3)
        self.dirty = True

    def board_kept_do(self, key):
        """A recording's card: left where it is, recorded again, or deleted."""
        b = self.board
        sid = b.placing
        self.board_card_shut()
        if key == "stay" or not sid:
            b.placing = None
            return
        self.board_tell(do="stop")
        try:
            if B.sound_name(sid) and not B.is_starter(sid):
                os.remove(os.path.join(home_dir(), B.FOLDER, sid))
        except OSError as ex:
            self.toast(f"It couldn't be deleted ({ex.strerror or ex})", 3)
            return
        b.placing = None
        B.forget(b.banks, b.off, sid)
        self.board_look(time.monotonic(), force=True)
        if key == "again":
            self.board_rec_start()
        else:
            self.toast("Deleted", 2)
