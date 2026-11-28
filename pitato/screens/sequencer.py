"""The Soundboard's Sequencer (sequencer.py: the tune, and its page): its buttons, its tune kept with the settings, its
cells told to the Soundboard's player as part of the loop (so each is heard at its very moment, in time with a loop
recorded there, with Bounce, and with your other Pietatos' Soundboards), its card (START), and the sound's bars, as
its player says them. One of the Soundboard's three pages (L and R go round them: screens/soundboard.py's
board_cycle): B on its page starts it and stops it. It goes on playing when you leave it for the Soundboard's buttons
(or Bounce), so they can be played over it, and START held there (which clears the loop) stops it too."""
import random
import time

from .. import bounce as BN
from .. import sequencer as SQ
from .. import soundbank as B
from ..library import VOLUME_STEP
from ..theme import ACCENT

SEQ_HOW = ("A: a cell on or off. X: its note (a drum's: its sound). Y changes the tune a little. SELECT: the scale. L "
           "and R: the Soundboard and Bounce.")
SEQ_ALWAYS = -1e12               # the beat a cell's heard from: any (a loop's layer waits for its next time round)
DPAD = ("up", "down", "left", "right")


class SequencerScreen:
    """The Soundboard's Sequencer: a mode of its page."""

    # -- its tune ------------------------------------------------------------------------------------------------------
    def seq_tune(self):
        """Its tune: [its grid, the lead's notes] (sequencer.py), as it was kept; the first time, made from this
        Pietato's name."""
        b = self.board
        if b.seq is None:
            got = SQ.loads(self.setting("seq_tune"))
            if got is None:
                got = SQ.born(SQ.seed_of(self.own_name()))
            b.seq = [got[0], got[1]]
        return b.seq

    def seq_keep(self):
        """Its tune kept with the settings (as its page is left, not at each cell)."""
        b = getattr(self, "board", None)
        if b is None or b.seq is None:
            return
        text = SQ.dumps(*b.seq)
        if self.setting("seq_tune") != text:
            self.set_setting("seq_tune", text)

    def seq_sounds(self):
        """Each row's sound: the three drums' (any sound of the Soundboard's), and the lead's (one of the player's
        own, as Bounce has them). One that's gone since (a file of yours taken away), or isn't of its row's kind:
        the one its row starts with. (Asked for each frame: worked out again when the setting or your sounds have
        changed.)"""
        b = self.board
        text = str(self.setting("seq_sounds") or "")
        had = b.seq_rows
        if had is not None and had[0] == text and had[1] is b.seen:
            return list(had[2])
        kept = text.split("|")
        yours = {name for name, _, _ in b.seen[0]} if b.seen is not None else None   # (None: not looked at yet)
        starters = getattr(self, "seq_starters", None)
        if starters is None:
            starters = self.seq_starters = frozenset(B.starter_sounds())
        out = []
        for r in range(SQ.ROWS):
            sid = kept[r] if r < len(kept) else ""
            if r == SQ.LEAD_ROW:
                out.append(sid if sid.startswith("Tones/") and sid[6:] in BN.TONES else SQ.LEAD)
            elif B.is_starter(sid):
                out.append(sid if sid in starters else SQ.DRUMS[r])
            else:
                there = B.sound_name(sid) is not None and (yours is None or sid in yours)
                out.append(sid if there else SQ.DRUMS[r])
        b.seq_rows = (text, b.seen, out)
        return list(out)

    def seq_set_sound(self, row, sid):
        sounds = self.seq_sounds()
        sounds[row] = sid
        self.set_setting("seq_sounds", "|".join(sounds))
        self.board_load()                              # (one that's on no button: its player has it too)
        self.seq_told()
        self.board_loop_tell()

    def seq_choices(self):
        """The sounds a drum's row can have: the Sequencer's own three, then every sound on the Soundboard's buttons,
        bank by bank."""
        out = list(SQ.DRUMS)
        for bank in self.board.banks:
            for pad in B.PADS:
                sid = bank["pads"].get(pad)
                if sid and sid not in out:
                    out.append(sid)
        return out

    @staticmethod
    def seq_sound_name(sid):
        return sid.split("/", 1)[1] if sid.startswith("Tones/") else B.title(sid)

    def seq_key(self):
        """Its key and scale: Bounce's (one key for the Soundboard's tunes)."""
        return self.bounce_get("key"), self.bounce_get("scale")

    def seq_hits(self):
        """Its cells as the loop has them, while it's playing: [[beat, sound, semitones, from which beat (any), a
        bar's beats, how loud]] (soundplay.py's loop_from)."""
        b = getattr(self, "board", None)
        if b is None or not b.seq_on or b.seq is None:
            return []
        key, scale = self.seq_key()
        return [[beat, sid, semis, SEQ_ALWAYS, SQ.BAR, gain]
                for beat, sid, semis, gain in SQ.hits(b.seq[0], b.seq[1], self.seq_sounds(), key, scale)]

    def seq_extra(self):
        """Its rows' sounds that its player needs (the drums': the lead's is made by the player itself), while it's up
        or playing."""
        b = self.board
        if not (b.seq_up or b.seq_on):
            return []
        return self.seq_sounds()[:SQ.LEAD_ROW]

    # -- its page up, and left -----------------------------------------------------------------------------------------
    def seq_start(self, now):
        """L or R on to it (board_cycle): its grid on the page (its tune playing or not, as it was: B starts it)."""
        b = self.board
        if b.bounce is not None:
            self.bounce_leave()
        self.seq_tune()
        b.seq_up = True
        b.card = None
        self.sim_close()
        self.board_load()
        self.seq_told()
        self.board_loop_tell()
        self.seq_going()

    def seq_leave(self):
        """L or R on to another page: its page is left (the Soundboard's buttons again, or Bounce). Its tune plays
        on, if it was. (HOME leaves the Soundboard altogether, its page up for the next time: sims.py's sim_home.)"""
        b = self.board
        self.seq_keep()
        b.seq_up = False
        b.card = None
        self.sim_close()
        self.board_tell(do="bars", on=False)
        b.bars = None
        self.dirty = True

    def seq_told(self):
        """Its player told what the Sequencer wants of it: the sound's bars while its page is up, and the lead's
        sound made ready (it takes a moment, the first time)."""
        b = self.board
        if b.proc is None or not (b.seq_up or b.seq_on):
            return
        self.board_tell(do="tone", id=self.seq_sounds()[SQ.LEAD_ROW])
        if b.seq_up:
            self.board_tell(do="bars", on=True)

    def seq_going(self):
        """Its page as it is now, and drawn frame by frame from now (it may have been still)."""
        if self.board_shown():
            self.sim_game()
            self.sim_next = 0.0
        self.dirty = True

    def seq_changed(self):
        """A cell, a note or a sound changed: its player told the loop as it is now."""
        self.board_loop_tell()
        self.dirty = True

    # -- its buttons ---------------------------------------------------------------------------------------------------
    def press_seq(self, name, repeat):
        """◀▶▲▼ move from cell to cell (held: on and on; round the edges), and on to its buttons on its line, over
        the grid (▲ from its first row, ▼ round from its last; ◀▶ there: from one to the next); A a cell on or off,
        or a button's next; B stops it, or starts it; X a drum's next sound, or a lead cell's next note; Y changes a
        little of the tune; SELECT the scale; L and R the Soundboard's page before and after; START its card."""
        b = self.board
        grid, notes = self.seq_tune()
        rows = SQ.ROWS + 1                             # (its buttons too: over the grid, ▼ round from its last row)
        r, c = b.seq_at
        if name in DPAD:
            if name in ("up", "down"):
                r = (r + (1 if name == "down" else -1)) % rows
            elif r == SQ.ROWS:                         # (its buttons: one for each beat's four)
                c = (c + (4 if name == "right" else -4)) % SQ.STEPS
            else:
                c = (c + (1 if name == "right" else -1)) % SQ.STEPS
            b.seq_at = (r, c)
        elif repeat:
            return None
        elif name in ("l", "r", "l2", "r2"):
            self.board_cycle(-1 if name in ("l", "l2") else 1)
        elif r == SQ.ROWS and name in ("a", "x"):      # (one of its buttons: A, its next; X, nothing there)
            if name == "a":
                self.seq_knob(c // 4)
        elif name == "a":
            grid[r][c] = not grid[r][c]
            if grid[r][c]:
                self.seq_hear(r, c)
            self.seq_changed()
        elif name == "b":
            self.seq_play(not b.seq_on)
        elif name == "x":
            if r == SQ.LEAD_ROW:                       # (a lead's cell: its next note, round and round; on, if off)
                if grid[r][c]:
                    notes[c] = (notes[c] + 1) % SQ.NOTES
                grid[r][c] = True
                self.seq_hear(r, c)
                self.seq_changed()
            else:
                choices = self.seq_choices()
                was = self.seq_sounds()[r]
                sid = choices[(choices.index(was) + 1) % len(choices)] if was in choices else choices[0]
                self.seq_set_sound(r, sid)
                self.toast(self.seq_sound_name(sid), 1.5)
                if not b.seq_on:
                    self.board_sound(sid, gain=SQ.GAINS[r])
        elif name == "y":
            self.seq_swap(SQ.mutated(grid, notes, getattr(self, "seq_rng", None) or random.Random()))
        elif name == "select":
            self.bounce_choose("scale", 1)
            self.seq_changed()
        elif name == "start":
            self.seq_keep()
            b.card = "seq"
            self.sim_opts = 0
        else:
            return None
        self.dirty = True
        return None

    def seq_tap(self, r, c):
        """A cell tapped, or one of its buttons (the web page's picture of this screen): moved to, and A does the
        rest."""
        b = getattr(self, "board", None)
        if b is None or not b.seq_up or b.bounce is not None or b.rec is not None or b.placing is not None:
            return []
        if not (type(r) is int and type(c) is int and 0 <= c < SQ.STEPS and 0 <= r <= SQ.ROWS):
            return []
        b.seq_at = (r, c)
        self.dirty = True
        return ["a"]

    def seq_knob(self, k):
        """A on one of its buttons (SQ.KNOBS): the tempo, the key, the scale or the lead's sound, the next one
        (round and round); the lead's heard at the key's own note, the tune stopped."""
        b = self.board
        name = SQ.KNOBS[k]
        if name == "Tempo":
            bpm = round(self.board_clock().bpm)
            self.board_tempo(next((t for t in SQ.TEMPOS if t > bpm), SQ.TEMPOS[0]))
        elif name in ("Key", "Scale"):
            self.bounce_choose(name.lower(), 1)
            self.seq_changed()
        else:
            tones = [f"Tones/{t}" for t in BN.TONES]
            was = self.seq_sounds()[SQ.LEAD_ROW]
            sid = tones[(tones.index(was) + 1) % len(tones)] if was in tones else tones[0]
            self.seq_set_sound(SQ.LEAD_ROW, sid)
        if name in ("Key", "Lead") and not b.seq_on:
            self.board_sound(self.seq_sounds()[SQ.LEAD_ROW], semis=SQ.note_of(0, *self.seq_key()) - BN.TONE_ROOT,
                             gain=SQ.GAINS[SQ.LEAD_ROW])

    def seq_hear(self, r, c):
        """A cell just turned on, or its note changed: heard now as it is in the tune, while the tune's stopped
        (playing, it's heard as the bar comes round to it)."""
        b = self.board
        if b.seq_on:
            return
        semis = 0
        if r == SQ.LEAD_ROW:
            semis = SQ.note_of(b.seq[1][c], *self.seq_key()) - BN.TONE_ROOT
        self.board_sound(self.seq_sounds()[r], semis=semis, gain=SQ.GAINS[r])

    def seq_play(self, on):
        """It's started, or stopped (its cells in the loop, or out of it)."""
        b = self.board
        b.seq_on = bool(on)
        self.seq_keep()
        if on:
            self.seq_told()
        self.board_loop_tell()
        self.seq_going()

    def seq_swap(self, tune):
        """Its tune replaced (changed a little, a new one, cleared)."""
        self.board.seq = [tune[0], tune[1]]
        self.seq_changed()

    # -- its card ------------------------------------------------------------------------------------------------------
    def seq_rows(self):
        """Its card: (key, label, value or None: A does it)."""
        key, scale = self.seq_key()
        return [("tempo", "Tempo", f"{round(self.board_clock().bpm)} BPM"), ("volume", "Volume", str(self.volume)),
                ("key", "Key", key), ("scale", "Scale", scale),
                ("lead", "Lead", self.seq_sound_name(self.seq_sounds()[SQ.LEAD_ROW])),
                ("new", "A new tune", None), ("clear", "Clear all", None)]

    def press_seq_card(self, name, repeat):
        """Its card: ▲▼ a row, ◀▶ change it; A does a row that does something; START or B, on with it."""
        b = self.board
        rows = self.seq_rows()
        sel = self.sim_opts % len(rows)
        key = rows[sel][0]
        way = 1 if name == "right" else -1
        if name in ("up", "down"):
            self.sim_opts = (sel + (1 if name == "down" else -1)) % len(rows)
        elif name in ("left", "right") and key == "tempo":
            self.board_tempo(self.board_clock().bpm + way)
        elif name in ("left", "right") and key == "volume":
            self.set_volume(way * VOLUME_STEP)
        elif repeat:
            return None
        elif name in ("left", "right") and key in ("key", "scale"):
            self.bounce_choose(key, way)
            self.seq_changed()
        elif name in ("left", "right") and key == "lead":
            tones = [f"Tones/{t}" for t in BN.TONES]
            self.seq_set_sound(SQ.LEAD_ROW, tones[(tones.index(self.seq_sounds()[SQ.LEAD_ROW]) + way) % len(tones)])
        elif name == "a" and key == "new":
            rng = getattr(self, "seq_rng", None) or random.Random()
            self.seq_swap(SQ.born(rng.getrandbits(32)))
            self.toast("A new tune", 2)
        elif name == "a" and key == "clear":
            self.seq_swap(([[False] * SQ.STEPS for _ in range(SQ.ROWS)], list(b.seq[1])))
            self.toast("Cleared", 2)
        elif name in ("a", "b", "start"):
            b.card = None
            self.sim_close()
            self.seq_going()
        else:
            return None
        self.dirty = True
        return None

    def seq_card_hints(self):
        rows = self.seq_rows()
        if rows[self.sim_opts % len(rows)][2] is None:
            return [("▲▼", "Choose"), ("A", "Do it"), ("START", "Play on")]
        return [("▲▼", "Choose"), ("◀▶", "Change"), ("START", "Play on")]

    # -- its page, and the sound's bars --------------------------------------------------------------------------------
    @staticmethod
    def seq_levels(said):
        """What its player said of the sound, low notes first: each bar 0 to 1 (None: it's said nothing of the kind)."""
        v = said.get("v")
        if not isinstance(v, list):
            return None
        return [max(0.0, min(1.0, x / 99.0)) if isinstance(x, (int, float)) and not isinstance(x, bool) and x == x
                else 0.0 for x in v[:SQ.BARS]]

    def seq_heard(self, proc, said):
        """(Its player's reader's own thread.) The sound's bars, 20 times a second: kept for its page's next frame,
        which is all there is to do while the page is being drawn frame by frame anyway. False: it isn't (no sound
        till now), so media mode's own thread hears of them, and draws it from now (seq_said)."""
        b = getattr(self, "board", None)
        if b is None or b.proc is not proc or not b.seq_up:
            return True                                # (nobody's looking: dropped)
        levels = self.seq_levels(said)
        was = b.bars
        now = time.monotonic()
        if levels is None or was is None or now - was[0] >= SQ.BARS_KEPT:
            return False
        b.bars = (now, levels)
        return True

    def seq_said(self, said):
        """(board_said's.) Its player's bars after silence, with its page still: drawn again from now."""
        b = self.board
        levels = self.seq_levels(said)
        if levels is None or not b.seq_up:
            return
        b.bars = (time.monotonic(), levels)
        if self.board_shown() and self.sim_opts is None:
            self.sim_next = 0.0
            self.dirty = True

    def seq_page(self, s):
        """(board_page's.) What the page draws of it, as it is now (None: it's not up)."""
        b = self.board
        if not b.seq_up:
            s.seq = None
            return
        grid, notes = self.seq_tune()
        key, scale = self.seq_key()
        c = self.board_clock()
        sounds = self.seq_sounds()
        root = BN.root_of(key)
        s.seq = {"grid": tuple(tuple(row) for row in grid),
                 "names": tuple(BN.note_name(SQ.note_of(n, key, scale)) for n in notes),
                 "high": tuple(SQ.note_of(n, key, scale) - root >= 12 for n in notes),   # (the octave above: a dot)
                 "rows": [self.seq_sound_name(sid) for sid in sounds], "key": key, "scale": scale,
                 "bpm": round(c.bpm), "playing": b.seq_on, "clock": (c.bpm, c.b0, c.t0), "cursor": b.seq_at,
                 "colour": ACCENT, "bars": b.bars, "paused": b.card == "seq"}
        if b.seq_at[0] == SQ.ROWS:                     # (one of its buttons)
            s.own_hints = [("A", "Change"), ("B", "Stop" if b.seq_on else "Play"), ("Y", "Mutate"),
                           ("START", "More"), ("HOME", "Back")]
            return
        s.own_hints = [("A", "On/off"), ("B", "Stop" if b.seq_on else "Play"),
                       ("X", "Note" if b.seq_at[0] == SQ.LEAD_ROW else "Sound"), ("Y", "Mutate"), ("START", "More"),
                       ("HOME", "Back")]
