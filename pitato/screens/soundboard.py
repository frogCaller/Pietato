"""Apps > Soundboard, in media mode (soundboard.py draws it, soundbank.py has its sounds and banks, soundplay.py plays
them). Its player's a process of its own, as you, started with the page and gone as you leave it. While the page is
up, your Soundboard folder and the banks' file are looked at every second, so a new sound is on its button without
anything being started again (and at once when the web page says it changed something); the sound goes where
Settings > Sound says, as it changes; and whether there's a microphone is known, so Record a sound is on START's card
only when there's one to record with. Your LEDs (Apps > LED backlight, an ESP32 board: screens/glow.py) are lit by its
sounds as they are by music: a pulse in the button's colour as each is heard, and that colour while it plays.

Its buttons: the d-pad's four, A, B, X and Y play what's on them; L and R go through the banks; START, tapped, has its
card (the bank, the volume, the loop's tempo and length, snapping to the beat, the click, the notes' scale, its reverb,
Record a sound), where A, B or START goes on; HOME goes back to Apps from anywhere on it (screens/sims.py's
sim_home). Recording a sound: A keeps it, B drops it; kept (its silence
trimmed, a file in your Soundboard folder), the next button pressed is the one it goes on (L and R: in another bank;
SELECT: hear it first; START: leave it where it is, record it again, or delete it).

The loop: SELECT starts recording a layer, and stops it; what's pressed meanwhile is played back round and round where
it was pressed (to the nearest sixteenth, unless snapping's off), over the layers before it, a quiet click on each beat
while it records. SELECT held drops the last layer (the one being recorded, if one is); START held clears the loop and
stops every sound. Its player plays the loop itself, each sound at its very frame (soundplay.py). The beat: a tempo,
and which beat's heard when, shared with your other Pietatos that have their Soundboard open (beatlink.py), so their
loops keep time with this one's. Notes: A, B, X or Y held, and the d-pad plays its sound up and down a scale (▲ a note
higher, ▼ lower, ▶ the same again, ◀ back to its own), the note on its tile; recording, they go in the loop."""
import json
import math
import os
import subprocess
import sys
import threading
import time
import urllib.parse

from .. import soundbank as B
from ..asyou import as_you, nice_now
from .. import beatlink
from ..beatlink import Clock
from ..config import home_dir, read_own_text, settings_file, write_setting
from ..glow import colour_of
from ..library import LIBRARY, VOLUME_STEP
from ..listen import mics
from ..screen import aplay_device, sound_place
from ..theme import ACCENT, BODY, co_mix, LINE, MUTED, ROW, TEXT
from ..util import home_folder
from .bounce import BOUNCE_HOW

PLAYER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "soundplay.py")
BOARD_NICE = -8                  # its player's priority: ahead of the menus (a late sound is heard)
BOARD_LOOK = 1.0                 # seconds between looks at whether your folder or the banks' file has changed
BOARD_DEEP = 5.0                 # ...and at each of your sounds (one changed where it is)
BOARD_ROUTE = 2.0                # ...at where the sound goes, and whether there's a microphone
BOARD_AGAIN = (1.0, 5)           # a player that stops is started again after this long, this many times running
BOARD_QUIET = 2.0                # seconds the sound card's let go of for something else that starts playing
BOARD_BEHIND = 256 << 10         # bytes waiting for a player that isn't taking them, before it's stopped (and started again)
BOARD_HEARD = (0.004, 0.032)     # seconds from a button to its sound being heard: a little (its player's next
                                 # chunk), and the sound card's buffer (this, till its player's said how long it is)
BOARD_HUE = 0.5                  # seconds between its colour, said to your LEDs while a sound plays
BOARD_HUE_ON = 0.3               # ...and this long after a button at least (its player says it's playing a moment on)
PAD_SAY = {"up": "Up", "down": "Down", "left": "Left", "right": "Right", "x": "X", "y": "Y", "a": "A", "b": "B"}
PAD_LIGHT = {"up": "Blue", "left": "Teal", "right": "Green", "down": "Purple", "x": "Pink", "y": "Yellow", "a": "Red",
             "b": "White"}       # each button's colour on your LEDs (glow.py's COLOURS): its own on the page
                                 # (soundboard.py's PAD_COLOUR), as an LED shows it
PAD_LIGHT_NONE = "Warm white"    # ...and a sound that's on no button of the bank that's up
BPM_RANGE = (40, 240)            # the loop's tempo: the slowest and fastest
BARS = (1, 2, 4)                 # how long a loop can be (bars of BAR beats)
BAR = 4
SNAP = 0.25                      # beats: what's pressed while recording goes to the nearest sixteenth
HOLD = 0.5                       # seconds SELECT or START is held for its other job (drop the last layer; clear it all)
NOTE_HOLD = 0.25                 # seconds A, B, X or Y is held before the d-pad plays its sound as notes (pressed
                                 # together sooner, as drums are, each plays its own)
LAYERS_MOST = 32                 # layers in a loop, at most
TAKE_MOST = 400                  # sounds in a layer, at most
SCALES = {"Major": (0, 2, 4, 5, 7, 9, 11), "Minor": (0, 2, 3, 5, 7, 8, 10), "Pentatonic": (0, 2, 4, 7, 9)}
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")   # (a sound's own note: C)
NOTE_PADS = ("a", "b", "x", "y")  # held, the d-pad plays its sound as notes
DPAD = ("up", "down", "left", "right")
BOARD_HOW = ("SELECT records a loop: held, it drops the last layer. START held clears it. A, B, X or Y held, the "
             "d-pad plays its sound as notes.")    # (START's card, under its title)


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
        self.buffer = None             # the sound card's buffer, as its player has it (seconds)
        self.hue = None                # your LEDs lit by its sounds: [their colour, when it was last said, since when]
        self.layers = []               # the loop: each layer one recording kept, [beats long, [(beat, sound, semitones,
                                       # not before this beat of the clock's)]]
        self.take = None               # ...the layer being recorded
        self.clock = None              # the beat (beatlink.py's Clock): a tempo, and when a beat's heard
        self.held = {}                 # buttons held down on its page: name -> when it went down
        self.held_done = set()         # ...those whose holding has done its job (SELECT: dropped; START: cleared)
        self.select_did = None         # what SELECT going down did: "start" (recording), "kept" (a layer), "stop"
        self.note_pad = None           # A, B, X or Y whose sound the d-pad's playing as notes, while it's held
        self.note = 0                  # ...the note it's on: steps of the scale from the sound's own
        self.loop_told = None          # what its player was last told of the loop
        self.link = None               # the beat shared with your others (beatlink.py), while its page is open
        self.link_at = 0.0             # ...when it's tried again, if it couldn't start
        self.peers, self.peers_at = [], 0.0   # your others' addresses, and when they're looked at again
        self.bounce = None             # Bounce (bounce.py's World: screens/bounce.py), while it's up
        self.bounce_lit = []           # ...when each of its walls was last hit
        self.bounce_at = 0.0           # ...when its balls were last moved on
        self.bounce_slots = {}         # ...its notes snapped to the tempo lately: (wall, eighth) -> its beat
        self.bounce_plan = {}          # ...its notes told ahead: (a ball, a wall) -> when it'll hit (the last few)
        self.bounce_levels = {}        # ...its sliders for its sound while it's up (bounce.py's LEVELS): 0 to 10
        self.bounce_sel = 0            # ...the slider ▲▼ have picked
        self.bounce_bpm = None         # ...the tempo its echo was told
        self.pitch = {}                # a sound -> its own note, as its player could tell (None: it hasn't one)

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
        b.buffer = b.hue = None
        proc.started = now
        threading.Thread(target=self.board_reader, args=(proc,), daemon=True, name="soundboard").start()
        self.board_route(now)
        if self.board_tell(do="volume", v=self.volume):
            b.volume = self.volume
        self.board_look(now, force=True)               # (its sounds as they are now, and its player told)
        b.loop_told = None
        if b.clock is not None:                        # (opened again: the beat of your others' wins, if they're
            b.clock = b.clock.fresh(now, self.board_me())   # playing already)
        self.board_loop_tell()                         # (the loop, if there is one: it goes on)
        if self.board_space():
            self.board_tell(do="space", v=self.board_space() / 10)
        self.bounce_told()                             # (Bounce, if it's up: its effects, its sound's own note)
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
        self.bounce_keep()
        proc, b.proc = b.proc, None
        if b.rec is not None:
            self.board_rec_over()
        b.placing = b.card = None
        b.pitch = {}
        b.held, b.held_done, b.select_did, b.note_pad = {}, set(), None, None
        if b.link is not None:
            b.link.close()
            b.link = None
        if b.take is not None:                         # (recording a layer: it's kept)
            self.board_commit()
        b.loop_told = None
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
            if b.bounce is not None and sid == self.bounce_sound_id() and sid not in b.pitch:
                self.board_tell(do="pitch", id=sid)    # (Bounce's sound: its own note, to play it in tune)
        elif what == "pitch" and isinstance(sid, str):
            m = said.get("midi")
            good = isinstance(m, (int, float)) and not isinstance(m, bool) and math.isfinite(m) and 20 <= m <= 110
            b.pitch[sid] = float(m) if good else None
            return
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
            ms = said.get("buffer")
            good = ok and isinstance(ms, (int, float)) and not isinstance(ms, bool) and 0 < ms < 1000
            b.buffer = ms / 1000.0 if good else None
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
        extra = self.bounce_sound_id() if b.bounce is not None else "Tones/"
        if not extra.startswith("Tones/") and extra not in {sid for sid, _ in sounds}:
            path = B.path_of(extra, folder)            # (Bounce's sound, on no button: wanted first)
            if path:
                sounds.insert(0, [extra, path])
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
        for name, down in list(b.held.items()):        # (SELECT or START held: their other job)
            if name in ("select", "start") and now - down >= HOLD and name not in b.held_done:
                b.held_done.add(name)
                if name == "select":
                    self.board_undo()
                else:
                    if self.sim_opts is not None and b.card is not None:
                        self.board_card_shut()         # (the card it opened as it went down: gone again)
                    self.board_clear()
        self.bounce_tick(now)                          # (Bounce, if it's up: its balls moved on, their notes played)
        if b.note_pad is None and b.placing is None and self.board_note_pad(now) is not None:
            b.note_pad = self.board_note_pad(now)      # (A, B, X or Y held a moment: its note on its tile, the d-pad's
            self.dirty = True                          #  notes its)
        self.board_link(now)
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
        if b.hue is not None:                          # (your LEDs: its sound's colour, while it plays)
            if not b.playing and now - b.hue[2] >= BOARD_HUE_ON:
                b.hue = None
            elif now - b.hue[1] >= BOARD_HUE:
                b.hue[1] = now
                self.glow_hue(b.hue[0])

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
        """The web page's Soundboard changed something: looked at now, not at the next look. Or the loop's tempo, its
        length, snapping or the click ("loop": {"bpm", "bars", "snap", "click"}, any of them), and how the loop is."""
        if isinstance(cmd.get("loop"), dict) or isinstance(cmd.get("bounce"), dict):   # (its Bounce: screens/bounce.py)
            if isinstance(cmd.get("loop"), dict):
                why = self.board_web_set(cmd["loop"])
            else:
                why = self.bounce_web(cmd["bounce"])
            if why:
                return {"error": why}
            return {"ok": True, "loop": self.board_web_loop(), "bounce": self.bounce_web_state()}
        b = getattr(self, "board", None)
        if b is not None:
            b.look_at = b.deep_at = 0.0
            b.quick = None
            if self.board_shown():
                self.wake()
        return {"ok": True, "open": bool(b is not None and b.proc is not None)}

    def board_web_set(self, loop):
        """(board_web's.) The loop's settings from the web page, all of them or none: why not, or None."""
        bpm, bars = loop.get("bpm"), loop.get("bars")
        if bpm is not None and (type(bpm) is not int or not BPM_RANGE[0] <= bpm <= BPM_RANGE[1]):
            return f"A tempo's {BPM_RANGE[0]} to {BPM_RANGE[1]} BPM"
        if bars is not None and (type(bars) is not int or bars not in BARS):
            return "A loop's " + ", ".join(str(n) for n in BARS[:-1]) + f" or {BARS[-1]} bars"
        if any(loop.get(k) not in (None, "On", "Off") for k in ("snap", "click")):
            return "Bad request"
        b = getattr(self, "board", None)
        if bpm is not None:
            if b is None:
                self.set_setting("board_bpm", str(bpm))
            elif round(self.board_clock().bpm) != bpm:
                self.board_tempo(bpm)                  # (here and on your others, from the beat it's at)
        for key, value in (("bars", None if bars is None else str(bars)), ("snap", loop.get("snap")),
                           ("click", loop.get("click"))):
            if value is not None:
                self.set_setting("board_" + key, value)
        if b is not None:
            self.board_loop_tell()
            self.dirty = True
        return None

    def board_web_loop(self):
        """How the loop is, for the web page (asked from its own thread: only looked at, never changed): its tempo,
        length, snapping and click, its layers, a layer being recorded, whether it's playing (the Soundboard open), your
        others in time with it (their names); and the tempos and lengths there can be."""
        b = getattr(self, "board", None)
        clock = b.clock if b is not None else None
        out = {"bpm": round(clock.bpm if clock is not None else self.board_bpm()), "bars": self.board_bars(),
               "snap": "Off" if self.setting("board_snap") == "Off" else "On",
               "click": "Off" if self.setting("board_click") == "Off" else "On",
               "layers": len(b.layers) if b is not None else 0, "rec": b is not None and b.take is not None,
               "open": b is not None and b.proc is not None and self.board_shown(), "with": [],
               "bpms": list(BPM_RANGE), "lengths": list(BARS)}
        link = b.link if b is not None else None
        if link is not None and out["open"]:
            near = set(link.with_whom(time.monotonic()))
            out["with"] = [name for u, name in self.saves_peers() if urllib.parse.urlsplit(u).hostname in near]
        return out

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
        elif b.take is not None:
            s.own_hints = many + [("SELECT", "Keep it"), ("START", "More"), ("HOME", "Back")]
        elif b.layers:
            s.own_hints = many + [("SELECT", "Add to the loop"), ("START", "More"), ("HOME", "Back")]
        else:
            s.own_hints = many + [("SELECT", "Record a loop"), ("START", "More"), ("HOME", "Back")]
        now = time.monotonic()
        if b.take is not None or b.layers:             # (the loop: recording or playing, where it is, how fast)
            c = self.board_clock()
            n = BAR * self.board_bars()
            at = self.board_beat(now) % n
            s.loop = {"rec": b.take is not None, "layers": len(b.layers), "bar": int(at // BAR) + 1,
                      "beat": int(at % BAR) + 1, "bpm": round(c.bpm), "bars": self.board_bars()}
            s.clock = (c.bpm, c.b0, c.t0)
        else:
            s.loop = s.clock = None
        s.held_note = (b.note_pad, self.board_note_name(b.note)) if b.note_pad is not None else None
        s.fps = self.sim_fps()
        self.bounce_page(s)                            # (Bounce, if it's up: its shape and balls, its buttons)

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
        now = time.monotonic()
        if self.board_sound(sid, pad):
            self.board_take_hit(sid, 0, now)
        if b.sound_ok is False and now - b.busy_said > 5:
            b.busy_said = now
            self.toast("No sound: " + self.board_trouble(), 3)

    def board_sound(self, sid, pad=None, semis=0):
        """A sound played (its player's told), and your LEDs lit by it (screens/glow.py's glow_flash): a pulse as it's
        heard (a moment on: what's mixed waits its turn, then the sound card's buffer), in its button's colour, kept
        while it plays (board_tick). semis: as a note, that many semitones from its own."""
        b = self.board
        if not self.board_tell(**({"do": "play", "id": sid, "semis": semis} if semis else {"do": "play", "id": sid})):
            return False
        if pad is None:
            bank = b.bank()
            pad = next((p for p, s in (bank["pads"] if bank is not None else {}).items() if s == sid), None)
        rgb = colour_of(PAD_LIGHT.get(pad, PAD_LIGHT_NONE))
        now = time.monotonic()
        late = BOARD_HEARD[0] + (b.buffer if b.buffer is not None else BOARD_HEARD[1])
        if self.glow_flash(rgb, now + late):
            b.hue = [rgb, now, now]
        return True

    def press_board(self, s, name, repeat):
        """Its buttons (not START's card: press_board_card). Every one is its own: none goes back, or on to the next
        app."""
        b = self.board_open()
        if b.bounce is not None and b.rec is None and b.placing is None:
            return self.press_bounce(name, repeat)     # (Bounce: its buttons, screens/bounce.py)
        if repeat:
            return None                                # (held down: once is once)
        if b.rec is not None:                          # recording: A keeps it, B drops it
            if name in ("a", "b") and not b.rec["ending"]:
                self.board_rec_stop(name == "a")
            return None
        now = time.monotonic()
        b.held[name] = now
        b.held_done.discard(name)
        if name in B.PADS:
            if b.placing is not None:
                self.board_place(name)
            elif name in DPAD and self.board_note_pad(now) is not None:
                self.board_note(self.board_note_pad(now), name, now)   # (A, B, X or Y held: its sound as a note)
            else:
                self.board_play(name)
                if name in NOTE_PADS:                  # (its notes start from its own; held a moment, its note's
                    if b.note_pad is not None:         #  shown at a look of board_tick's, a quarter second at most:
                        self.dirty = True              #  no frame of its own for it, drums played quickly)
                    b.note_pad, b.note = None, 0
        elif name in ("l", "r", "l2", "r2"):
            self.board_step(-1 if name in ("l", "l2") else 1)
        elif name == "select":
            if b.placing is not None:
                b.held.pop(name, None)
                self.board_sound(b.placing)
            else:
                self.board_loop_button(now)
        elif name == "start":                          # (its card; held, the card goes and the loop's cleared)
            b.card = "kept" if b.placing is not None else "more"
            self.sim_opts = 0
            self.sim_next = min(self.sim_next, now + HOLD)
            self.dirty = True
        return None

    def release_board(self, name):
        """A button let go of on its page (or with START's card up): no longer held; A, B, X or Y, no more notes."""
        b = getattr(self, "board", None)
        if b is None:
            return
        b.held.pop(name, None)
        b.held_done.discard(name)
        if name == b.note_pad:
            b.note_pad = None
            self.dirty = True

    # -- the loop -----------------------------------------------------------------------------------------------------
    def board_bars(self):
        try:
            n = int(self.setting("board_bars"))
        except (TypeError, ValueError):
            return BARS[1]
        return n if n in BARS else BARS[1]

    def board_scale(self):
        return SCALES.get(self.setting("board_scale")) or SCALES["Major"]

    def board_clock(self):
        """The beat: shared with your other Pietatos that have the Soundboard open, as it's heard here."""
        b = self.board
        if b.clock is None:
            b.clock = Clock.new(self.board_bpm(), time.monotonic(), self.board_me())
        return b.clock

    def board_bpm(self):
        """The tempo as it's set (START's card, the web page)."""
        try:
            bpm = float(self.setting("board_bpm"))
        except (TypeError, ValueError):
            bpm = 100.0
        return min(BPM_RANGE[1], max(BPM_RANGE[0], bpm)) if bpm == bpm else 100.0

    def board_me(self):
        """This Pietato's word for itself (the same as its saves')."""
        try:
            return self.saves_id()
        except Exception:
            return ""

    def board_link(self, now):
        """The beat shared with your other Pietatos that have the Soundboard open (Settings > Share with other
        Pietatos): theirs taken if it wins, this one's said to them."""
        b = self.board
        if self.setting("share") == "Off":
            if b.link is not None:
                b.link.close()
                b.link = None
            return
        if b.link is None:
            if now < b.link_at:
                return
            try:
                b.link = beatlink.Link(self.board_me(), beatlink.BEAT_HOST, beatlink.BEAT_PORT)
            except OSError as ex:                      # (something else has its port: on its own, for now)
                print(f"soundboard: no shared beat ({ex})", flush=True)
                b.link_at = now + 30.0
                return
        if now >= b.peers_at:
            b.peers_at = now + 1.0
            try:
                b.peers = [h for h in (urllib.parse.urlsplit(u).hostname for u, _ in self.saves_peers()) if h]
            except Exception as ex:
                print(f"soundboard: couldn't list your others ({ex!r})", flush=True)
                b.peers = []
        was = self.board_clock()
        got = b.link.tick(was, b.peers)
        if got is not was:
            b.clock = got
            self.board_loop_tell()
            self.dirty = True

    def board_beat(self, now):
        """The beat heard at that moment (counting from when the clock began: 3.5, half way through the fourth)."""
        return self.board_clock().beat(now)

    def board_loop_button(self, now):
        """SELECT: a layer starts recording, or the one recording stops (kept); held, it's dropped (board_undo)."""
        b = self.board
        if b.take is None:
            if len(b.layers) >= LAYERS_MOST:
                self.toast("That's as many layers as a loop can have", 3)
                b.held.pop("select", None)
                return
            b.take = [BAR * self.board_bars(), []]
            b.select_did = "start"
        else:
            b.select_did = "kept" if self.board_commit() else "stop"
        self.board_loop_tell()
        self.sim_next = min(self.sim_next, now + HOLD)   # (a look then: held, it drops the last layer)
        self.dirty = True

    def board_commit(self):
        """The layer being recorded, kept (if anything was played in it)."""
        b = self.board
        take, b.take = b.take, None
        if take is not None and take[1]:
            b.layers.append(take)
            return True
        return False

    def board_undo(self):
        """SELECT held: the last layer dropped (one just started recording, with it). One was recording: that one
        (nothing, if nothing was played in it)."""
        b = self.board
        if b.select_did == "start":
            b.take = None
        if b.layers and b.select_did != "stop":
            b.layers.pop()
            self.toast("The last layer's gone" if b.layers else "The loop's gone", 2)
        else:
            self.toast("Nothing to take back", 2)
        self.board_loop_tell()
        self.dirty = True

    def board_clear(self):
        """START held: the loop cleared, and every sound stopped."""
        b = self.board
        had = bool(b.layers or b.take)
        b.layers, b.take = [], None
        self.board_loop_tell()
        self.board_tell(do="stop")
        self.toast("Loop cleared" if had else "Stopped", 2)
        self.dirty = True

    def board_take_hit(self, sid, semis, now):
        """A sound played while a layer's recording: in it, where it was played (to the nearest sixteenth, snapping),
        and heard from the next time round (this time it was heard as it was played)."""
        b = self.board
        if b.take is None:
            return
        beats, hits = b.take
        beat = self.board_beat(now)
        p = beat % beats
        q = round(p / SNAP) * SNAP if self.setting("board_snap") != "Off" else p
        at = beat - p + q
        if q >= beats:
            q -= beats
        if len(hits) >= TAKE_MOST or any(abs(h[0] - q) < 1e-6 and h[1] == sid and h[2] == semis for h in hits):
            return
        hits.append((q, sid, semis, at + 0.001))
        self.board_loop_tell()

    def board_loop_tell(self):
        """Its player told the loop as it is now (its layers, the one recording, the beat, the click while recording),
        or that there's none. Only when that's changed."""
        b = getattr(self, "board", None)
        if b is None or b.proc is None:
            return
        layers = b.layers + ([b.take] if b.take is not None else [])
        hits = [[round(p, 5), sid, semis, round(after, 4), beats]
                for beats, hs in layers for p, sid, semis, after in hs]
        click = b.take is not None and self.setting("board_click") != "Off"
        what = {}
        if hits or click:
            c = self.board_clock()
            what = {"hits": hits, "beats": BAR * self.board_bars(), "bpm": c.bpm, "b0": c.b0, "t0": c.t0,
                    "click": click}
        key = json.dumps(what, sort_keys=True)
        if key != b.loop_told and self.board_tell(do="loop", **what):
            b.loop_told = key

    def board_tempo(self, bpm):
        """A new tempo (START's card, the web page): from the beat it's at, here and on your others."""
        b = self.board_open()
        bpm = min(BPM_RANGE[1], max(BPM_RANGE[0], int(round(bpm))))
        self.set_setting("board_bpm", str(bpm))
        b.clock = self.board_clock().retimed(bpm, time.monotonic(), self.board_me())
        if b.link is not None:
            b.link.say_now()                           # (your others: at once)
        self.board_loop_tell()
        self.dirty = True

    # -- notes --------------------------------------------------------------------------------------------------------
    def board_semis(self, step):
        """Semitones from a sound's own note, so many steps up (or down) its scale."""
        scale = self.board_scale()
        octave, i = divmod(step, len(scale))
        return 12 * octave + scale[i]

    def board_note_name(self, step):
        semis = self.board_semis(step)
        name = NOTE_NAMES[semis % 12]
        return ("Low " if semis < 0 else "High " if semis >= 12 else "") + name

    def board_note_pad(self, now):
        """Which button's sound the d-pad plays as notes: of A, B, X and Y, the one held that went down last, if it's
        been held a moment (NOTE_HOLD) and has a sound. None: the d-pad plays its own."""
        b = self.board
        held = [(at, p) for p, at in b.held.items() if p in NOTE_PADS]
        if not held:
            return None
        at, pad = max(held)
        bank = b.bank()
        sid = bank["pads"].get(pad) if bank is not None else None
        return pad if now - at >= NOTE_HOLD and sid and sid in b.ready else None

    def board_note(self, pad, way, now):
        """The d-pad, with A, B, X or Y held (pad): that button's sound, a note higher (▲) or lower (▼) up its scale,
        the same again (▶), or at its own (◀). An octave either way at most."""
        b = self.board
        bank = b.bank()
        sid = bank["pads"].get(pad) if bank is not None else None
        if not sid or sid not in b.ready:
            return
        b.note_pad = pad
        most = len(self.board_scale())
        if way == "up":
            b.note = min(most, b.note + 1)
        elif way == "down":
            b.note = max(-most, b.note - 1)
        elif way == "left":
            b.note = 0
        semis = self.board_semis(b.note)
        if self.board_sound(sid, pad, semis):
            self.board_take_hit(sid, semis, now)
        self.dirty = True

    # -- START's card ------------------------------------------------------------------------------------------------------
    def board_rows(self):
        """Its card's rows: (key, label, its value or None: A does it)."""
        b = self.board
        if b.card == "bounce":
            return self.bounce_rows()
        if b.card == "kept":
            at = B.where(b.banks, b.placing) if b.placing else None
            stay = f"Leave it on {PAD_SAY[at[1]]} in {b.banks[at[0]]['name']}" if at else "Leave it off the buttons"
            return [("stay", stay, None), ("again", "Record it again", None), ("delete", "Delete it", None)]
        bank = b.bank()
        bars = self.board_bars()
        rows = [("bank", "Bank", bank["name"] if bank is not None else ""), ("volume", "Volume", str(self.volume))]
        if b.mic is not None and b.proc is not None:
            rows.append(("rec", "Record a sound", None))   # (where it's always been: START, ▼▼, A records)
        rows += [("tempo", "Tempo", f"{round(self.board_clock().bpm)} BPM"),
                 ("bars", "Loop", f"{bars} bar" + ("s" if bars > 1 else "")),
                 ("snap", "Snap to the beat", "Off" if self.setting("board_snap") == "Off" else "On"),
                 ("click", "Click while recording", "Off" if self.setting("board_click") == "Off" else "On"),
                 ("scale", "Notes", self.setting("board_scale") if self.setting("board_scale") in SCALES else "Major"),
                 ("space", "Reverb", str(self.board_space()) if self.board_space() else "Off"),
                 ("bounce", "Bounce", None)]
        return rows

    def board_card_shut(self):
        self.board.card = None
        self.sim_close()

    def press_board_card(self, s, name, repeat):
        """START's card: ▲▼ pick a row, ◀▶ change it; A, B or START goes on with the Soundboard (HOME goes back to
        Apps). A recording's card: A does the row, B or START shuts it."""
        b = self.board_open()
        b.held.pop("start", None)                      # (anything pressed on the card: START wasn't being held)
        if b.card == "bounce":
            return self.press_bounce_card(name, repeat)
        rows = self.board_rows()
        sel = self.sim_opts % len(rows)
        key = rows[sel][0]
        if name in ("up", "down"):
            self.sim_opts = (sel + (1 if name == "down" else -1)) % len(rows)
        elif name in ("left", "right") and key == "volume":
            self.set_volume(VOLUME_STEP if name == "right" else -VOLUME_STEP)
        elif name in ("left", "right") and key == "tempo":
            self.board_tempo(self.board_clock().bpm + (1 if name == "right" else -1))
        elif name in ("left", "right") and key == "space" and b.card != "kept":
            self.board_set_space(self.board_space() + (1 if name == "right" else -1))
        elif repeat:
            return None
        elif name in ("left", "right") and key in ("bars", "snap", "click", "scale") and b.card != "kept":
            self.board_choose(key, 1 if name == "right" else -1)
        elif b.card == "kept":
            if name == "a":
                self.board_kept_do(key)
            elif name in ("b", "start"):
                self.board_card_shut()
            elif name == "select" and b.placing:
                self.board_sound(b.placing)
            else:
                return None
        elif name in ("left", "right") and key == "bank":
            self.board_step(1 if name == "right" else -1)
        elif name in ("l", "r", "l2", "r2"):
            self.board_step(-1 if name in ("l", "l2") else 1)
        elif name == "a" and key == "rec":
            self.board_card_shut()
            self.board_rec_start()
        elif name == "a" and key == "bounce":
            self.bounce_start(time.monotonic())
        elif name in ("a", "b", "start"):              # (B too: HOME's the way back to Apps, not B)
            self.board_card_shut()
        elif name == "select":
            self.board_tell(do="stop")
        else:
            return None
        self.dirty = True
        return None

    def board_space(self):
        """START's card's Reverb: how much of a room its own sounds are played in, 0 (none) to 10."""
        try:
            return max(0, min(10, int(self.setting("board_space"))))
        except (TypeError, ValueError):
            return 0

    def board_set_space(self, v):
        v = max(0, min(10, v))
        if v != self.board_space():
            self.set_setting("board_space", str(v))
        self.board_tell(do="space", v=v / 10)

    def board_choose(self, key, way):
        """START's card, ◀▶ on the loop's length, snapping, the click, the notes' scale: the next one."""
        choices = {"bars": [str(n) for n in BARS], "snap": ["On", "Off"], "click": ["On", "Off"],
                   "scale": list(SCALES)}[key]
        was = self.setting("board_" + key)
        i = choices.index(was) if was in choices else 0
        self.set_setting("board_" + key, choices[(i + way) % len(choices)])
        self.board_loop_tell()                         # (the click: only while recording)

    def board_card_hints(self):
        b = self.board_open()
        rows = self.board_rows()
        key, _, value = rows[self.sim_opts % len(rows)]
        if b.card == "kept":
            return [("▲▼", "Choose"), ("A", "OK"), ("SELECT", "Hear it"), ("B", "Not now")]
        if b.card == "bounce":
            return self.bounce_card_hints()
        if value is None:
            return [("▲▼", "Choose"), ("A", "Record" if key == "rec" else "Open"), ("START", "Done"),
                    ("HOME", "Back to Apps")]
        return [("▲▼", "Choose"), ("◀▶", "Change"), ("A", "Done"), ("HOME", "Back to Apps")]

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
        if b.card == "bounce":
            return self.rows_card("Bounce", BOUNCE_HOW, rows)
        return self.rows_card(LIBRARY[self.tab].get("title") or LIBRARY[self.tab]["name"], BOARD_HOW, rows)

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
        (bx0, by0, bx1, by1), _ = self.sim_box()
        fit = max(3, (by1 - by0 - top - 10) // rh)     # (more rows than fit: those round the one picked)
        first = min(max(0, sel - fit // 2), max(0, len(rows) - fit))
        shown = list(enumerate(rows))[first:first + fit]
        H = top + rh * len(shown) + 10
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((0, 0, W - 1, H - 1), radius=12, fill=ROW + (255,), outline=LINE + (255,))
        d.text((22, 30), title, font=F["head"], fill=TEXT, anchor="lm")
        y = 56
        for line in lede:
            d.text((22, y), line, font=F["small"], fill=MUTED, anchor="lm")
            y += 20
        y = top
        for i, (key, label, value) in shown:
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
        cx = W // 2                                    # (rows above or below the ones shown: a mark that says so)
        if first > 0:
            d.polygon([(cx - 6, top - 1), (cx + 6, top - 1), (cx, top - 7)], fill=MUTED)
        if first + fit < len(rows):
            d.polygon([(cx - 6, H - 9), (cx + 6, H - 9), (cx, H - 3)], fill=MUTED)
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
