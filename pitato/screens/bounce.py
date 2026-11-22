"""The Soundboard's Bounce (bounce.py: the shape and its balls): its buttons, its notes to the Soundboard's player, its
card (START: paused, and its sound, key, scale, echo and snapping), and what the web page asks of it. Opened from
the Soundboard's own card (START, then Bounce); its player and its beat are the Soundboard's (screens/soundboard.py),
so a loop playing goes on under it, and its notes can keep time with the loop."""
import math
import time

from .. import bounce as BN
from .. import soundbank as B

BOUNCE_AHEAD = 0.12              # seconds the balls are looked ahead at, each look (more than between two of them): a
                                 # note's told its player before its ball gets there, and it's heard as it does
BOUNCE_LATE = 0.05               # ...just after it does (enough for the sound card to have it in time, too little to
                                 # notice)
BOUNCE_GRID = 0.5                # beats: its notes snapped to the tempo go to the next eighth
BOUNCE_GAIN = 0.8                # how loud its notes are, of a sound as it is
BOUNCE_STEP_MOST = 0.25          # seconds of the balls moved on at most at a look (media mode busy: they don't jump)
BOUNCE_HOW = "A adds a ball and B takes one away. ◀▶ turn the shape, ▲▼ speed the balls up, L and R change the shape."
ECHO_BEATS = 0.75                # its echo: a dotted eighth of the tempo after each note


class BounceScreen:
    """The Soundboard's Bounce: a mode of its page."""

    # -- its settings --------------------------------------------------------------------------------------------------
    def bounce_get(self, key):
        v = self.setting("bounce_" + key)
        choices = {"key": BN.KEYS, "scale": tuple(BN.SCALES), "shape": tuple(dict(BN.SHAPES)), "echo": ("On", "Off"),
                   "snap": ("On", "Off")}.get(key)
        if choices is not None and v not in choices:
            v = {"key": "C", "scale": "Pentatonic", "shape": "Hexagon", "echo": "On", "snap": "Off"}[key]
        return v

    def bounce_number(self, key, low, high, default):
        try:
            v = float(self.setting("bounce_" + key))
        except (TypeError, ValueError):
            return default
        return min(high, max(low, v)) if math.isfinite(v) else default

    def bounce_sound_id(self):
        """The sound its balls play: one of its own (Tones/...) or one of the Soundboard's."""
        sid = self.setting("bounce_sound")
        return sid if isinstance(sid, str) and sid else "Tones/Bell"

    def bounce_sounds(self):
        """The sounds the card goes through: its own, then the bank's that's up (in its buttons' order)."""
        b = self.board
        bank = b.bank()
        own = [f"Tones/{t}" for t in BN.TONES]
        theirs = [bank["pads"][p] for p in B.PADS if bank is not None and bank["pads"].get(p)]
        return own + [sid for sid in theirs if sid not in own]

    @staticmethod
    def bounce_sound_name(sid):
        return sid.split("/", 1)[1] if sid.startswith("Tones/") else B.title(sid)

    # -- in and out ----------------------------------------------------------------------------------------------------
    def bounce_start(self, now):
        """START's card, Bounce: the shape in the middle of the page, a few balls in it."""
        b = self.board
        b.bounce = BN.World(BN.shape_sides(self.bounce_get("shape")), self.bounce_number("spin", -BN.SPIN_MOST,
                            BN.SPIN_MOST, 0.3), self.bounce_number("speed", *BN.SPEEDS, 0.8))
        for _ in range(BN.BALLS_FIRST):
            b.bounce.add()
        b.bounce_lit = [0.0] * b.bounce.sides
        b.bounce_at, b.bounce_slots, b.bounce_plan = now, {}, {}
        b.card = None
        self.sim_close()
        self.bounce_told()
        self.bounce_going()

    def bounce_leave(self):
        """Its card's Leave Bounce: the Soundboard's buttons again."""
        b = self.board
        self.bounce_keep()
        b.bounce = None
        b.card = None
        self.sim_close()
        self.board_tell(do="echo", on=False)
        self.dirty = True

    def bounce_keep(self):
        """How fast it turns and the balls go, kept for next time (as it's left, not each press)."""
        w = getattr(self.board, "bounce", None)
        if w is not None:
            for key, v in (("spin", w.spin), ("speed", w.speed)):
                if self.setting("bounce_" + key) != f"{v:.2f}":
                    self.set_setting("bounce_" + key, f"{v:.2f}")

    def bounce_told(self):
        """Its player told what Bounce wants of it: its echo (a dotted eighth of the tempo), and the sound's own note
        (one of the Soundboard's: as near as the player can tell, asked once)."""
        b = self.board
        if b.bounce is None or b.proc is None:
            return
        bpm = self.board_clock().bpm
        self.board_tell(do="echo", on=self.bounce_get("echo") == "On", secs=round(ECHO_BEATS * 60.0 / bpm, 4))
        sid = self.bounce_sound_id()
        if not sid.startswith("Tones/") and sid in b.ready and sid not in b.pitch:
            self.board_tell(do="pitch", id=sid)

    # -- its buttons ---------------------------------------------------------------------------------------------------
    def press_bounce(self, name, repeat):
        """A a ball more, B one fewer; ◀▶ how fast it turns (and which way), ▲▼ how fast the balls go (both held: on
        and on); L and R the shape; SELECT the scale; START its card (paused)."""
        b = self.board
        w = b.bounce
        if name in ("left", "right"):
            w.spin = round(max(-BN.SPIN_MOST, min(BN.SPIN_MOST, w.spin + (BN.SPIN_STEP if name == "left" else
                                                                         -BN.SPIN_STEP))), 2)
        elif name in ("up", "down"):
            w.speed = round(max(BN.SPEEDS[0], min(BN.SPEEDS[1], w.speed + (BN.SPEED_STEP if name == "up" else
                                                                          -BN.SPEED_STEP))), 2)
        elif repeat:
            return None
        elif name == "a":
            if not w.add():
                self.toast(f"That's as many balls as there can be ({BN.BALLS_MOST})", 2)
        elif name == "b":
            w.drop()
        elif name in ("l", "r", "l2", "r2"):
            self.bounce_shape(-1 if name in ("l", "l2") else 1)
        elif name == "select":
            self.bounce_choose("scale", 1)
        elif name == "start":
            b.card = "bounce"
            self.sim_opts = 0
        else:
            return None
        self.dirty = True
        return None

    def bounce_shape(self, way):
        b = self.board
        names = [n for n, _ in BN.SHAPES]
        name = names[(names.index(self.bounce_get("shape")) + way) % len(names)]
        self.set_setting("bounce_shape", name)
        if b.bounce is not None:
            b.bounce.reshape(BN.shape_sides(name))
            b.bounce_lit = [0.0] * b.bounce.sides

    def bounce_choose(self, key, way):
        """The next key, scale, echo or snapping (◀▶ on its card; SELECT: the scale)."""
        choices = {"key": BN.KEYS, "scale": tuple(BN.SCALES), "echo": ("On", "Off"), "snap": ("On", "Off")}[key]
        was = self.bounce_get(key)
        self.set_setting("bounce_" + key, choices[(choices.index(was) + way) % len(choices)])
        if key == "echo":
            self.bounce_told()

    def bounce_sound_step(self, way):
        sounds = self.bounce_sounds()
        sid = self.bounce_sound_id()
        i = sounds.index(sid) if sid in sounds else (-1 if way > 0 else 0)
        self.bounce_set_sound(sounds[(i + way) % len(sounds)])

    def bounce_set_sound(self, sid):
        self.set_setting("bounce_sound", sid)
        self.board_load()                              # (one that's on no button: its player has it too)
        self.bounce_told()

    def bounce_rows(self):
        """Its card: (key, label, value or None: A does it)."""
        return [("sound", "Sound", self.bounce_sound_name(self.bounce_sound_id())),
                ("key", "Key", self.bounce_get("key")), ("scale", "Scale", self.bounce_get("scale")),
                ("echo", "Echo", self.bounce_get("echo")), ("snap", "Snap to the tempo", self.bounce_get("snap")),
                ("leave", "Leave Bounce", None)]

    def press_bounce_card(self, name, repeat):
        """Its card: ▲▼ a row, ◀▶ change it; A on Leave Bounce leaves it; START or B, on with it."""
        rows = self.bounce_rows()
        sel = self.sim_opts % len(rows)
        key = rows[sel][0]
        if name in ("up", "down"):
            self.sim_opts = (sel + (1 if name == "down" else -1)) % len(rows)
        elif repeat:
            return None
        elif name in ("left", "right") and key == "sound":
            self.bounce_sound_step(1 if name == "right" else -1)
        elif name in ("left", "right") and key in ("key", "scale", "echo", "snap"):
            self.bounce_choose(key, 1 if name == "right" else -1)
        elif name == "a" and key == "leave":
            self.bounce_leave()
        elif name in ("a", "b", "start"):
            self.board.card = None
            self.sim_close()
            self.board.bounce_at = time.monotonic()    # (the balls go on from where they were)
            self.bounce_going()
        else:
            return None
        self.dirty = True
        return None

    def bounce_going(self):
        """It's playing again (or for the first time): its page as it is now, and drawn frame by frame from now (its
        page said it was paused, and wasn't to be drawn again for a while)."""
        if self.board_shown():
            self.sim_game()
            self.sim_next = 0.0
        self.dirty = True

    def bounce_card_hints(self):
        rows = self.bounce_rows()
        if rows[self.sim_opts % len(rows)][2] is None:
            return [("▲▼", "Choose"), ("A", "Leave Bounce"), ("START", "Play on")]
        return [("▲▼", "Choose"), ("◀▶", "Change"), ("START", "Play on")]

    # -- the balls, as time goes by ------------------------------------------------------------------------------------
    def bounce_tick(self, now):
        """(board_tick's, its page up.) The balls moved on, a wall hit lit; and a look ahead: a ball that's going to
        hit a wall before the next look, its note told its player now, heard as it hits."""
        b = self.board
        w = b.bounce
        if w is None:
            return
        if b.card is not None or b.proc is None:       # (its card up: paused)
            b.bounce_at = now
            return
        dt = min(BOUNCE_STEP_MOST, max(0.0, now - b.bounce_at))
        b.bounce_at = now
        for k, t, ball in w.step(dt) if dt > 0 else ():
            when = now - (w.t - t)
            self.bounce_light(k, when)
            if not self.bounce_planned(ball, k, when):     # (not seen coming: a ball just added, the shape turned)
                self.bounce_note(k, when, ball)
        for k, t, ball in w.clone().step(BOUNCE_AHEAD):    # (what's coming: its notes told now, to be heard on time)
            when = now + (t - w.t)
            if not self.bounce_planned(ball, k, when):
                self.bounce_note(k, when, ball)
        for key in [key for key, ts in b.bounce_plan.items() if ts[-1] < now - 1.0]:
            del b.bounce_plan[key]

    def bounce_planned(self, ball, k, when):
        """That ball's note off that wall's been told already (looking ahead), for about then."""
        return any(abs(t - when) < 0.03 for t in self.board.bounce_plan.get((ball, k), ()))

    def bounce_light(self, k, when):
        b = self.board
        if k < len(b.bounce_lit):
            b.bounce_lit[k] = when

    def bounce_note(self, k, when, ball=None):
        """A ball off wall k (when: time.monotonic(), to come or just gone): its note, heard BOUNCE_LATE after it
        (snapping: at the next eighth of the tempo; once, for each wall and eighth)."""
        b = self.board
        if ball is not None:
            plan = b.bounce_plan.setdefault((ball, k), [])
            plan.append(when)
            del plan[:-4]
        key, scale = self.bounce_get("key"), self.bounce_get("scale")
        sid = self.bounce_sound_id()
        own = BN.TONE_ROOT if sid.startswith("Tones/") else b.pitch.get(sid)
        semis = BN.note_semis(BN.wall_note(k, key, scale), own, key)
        while semis > 24:
            semis -= 12
        while semis < -24:
            semis += 12
        at = when + BOUNCE_LATE
        if self.bounce_get("snap") == "On":
            c = self.board_clock()
            beat = math.ceil(c.beat(at) / BOUNCE_GRID - 1e-6) * BOUNCE_GRID
            slot = (k, round(beat / BOUNCE_GRID))
            if slot in b.bounce_slots:
                return
            b.bounce_slots[slot] = beat
            if len(b.bounce_slots) > 64:
                b.bounce_slots = dict(list(b.bounce_slots.items())[-32:])
            at = c.at(beat)
        self.board_tell(do="note", id=sid, semis=round(semis, 3), gain=BOUNCE_GAIN, at=round(at, 4))
        self.glow_flash(BN.wall_colour(BN.wall_note(k, key, scale)), at)   # (your LEDs, if there are: as it's heard)

    # -- its page ------------------------------------------------------------------------------------------------------
    def bounce_page(self, s):
        """(board_page's.) What the page draws of it, as it is now (None: it's not up)."""
        b = self.board
        w = b.bounce
        if w is None:
            s.bounce = None
            return
        key, scale = self.bounce_get("key"), self.bounce_get("scale")
        notes = [BN.wall_note(k, key, scale) for k in range(w.sides)]
        lit = (b.bounce_lit + [0.0] * w.sides)[:w.sides]
        s.bounce = {"corners": w.corners(), "balls": [(x, y) for _, x, y, _, _ in w.balls], "lit": lit,
                    "colours": [BN.wall_colour(n) for n in notes], "paused": b.card == "bounce",
                    "shape": self.bounce_get("shape"), "key": key, "scale": scale, "count": len(w.balls),
                    "sound": self.bounce_sound_name(self.bounce_sound_id())}
        s.own_hints = [("A B", "Balls"), ("◀▶▲▼", "Spin, speed"), ("L R", "Shape"), ("SELECT", "Scale"),
                       ("START", "Pause")]

    # -- the web page --------------------------------------------------------------------------------------------------
    def bounce_web_state(self):
        """What the web page shows of it (asked from its own thread: only looked at)."""
        b = getattr(self, "board", None)
        w = b.bounce if b is not None else None
        bank = b.bank() if b is not None else None
        own = [{"id": f"Tones/{t}", "name": t} for t in BN.TONES]
        sounds = own + [{"id": sid, "name": B.title(sid)} for sid in
                        dict.fromkeys(bk["pads"][p] for bk in (b.banks if b is not None else []) for p in B.PADS
                                      if bk["pads"].get(p))]
        return {"on": w is not None, "paused": w is not None and b.card == "bounce",
                "balls": len(w.balls) if w is not None else 0, "most": BN.BALLS_MOST,
                "spin": w.spin if w is not None else self.bounce_number("spin", -BN.SPIN_MOST, BN.SPIN_MOST, 0.3),
                "speed": w.speed if w is not None else self.bounce_number("speed", *BN.SPEEDS, 0.8),
                "spins": [-BN.SPIN_MOST, BN.SPIN_MOST, BN.SPIN_STEP], "speeds": list(BN.SPEEDS) + [BN.SPEED_STEP],
                "shape": self.bounce_get("shape"), "shapes": [n for n, _ in BN.SHAPES],
                "key": self.bounce_get("key"), "keys": list(BN.KEYS),
                "scale": self.bounce_get("scale"), "scales": list(BN.SCALES),
                "echo": self.bounce_get("echo"), "snap": self.bounce_get("snap"),
                "sound": self.bounce_sound_id(), "sounds": sounds, "open": bool(b is not None and b.proc is not None
                                                                              and self.board_shown()),
                "bank": bank["name"] if bank is not None else ""}

    def bounce_web(self, want):
        """The web page's Bounce: started or left, paused or not, balls added or taken away, how fast, the shape, key,
        scale, sound, echo and snapping, any of them. Why not, or None."""
        b = self.board_open()
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)   # noqa: E731
        checks = {"shape": tuple(dict(BN.SHAPES)), "key": BN.KEYS, "scale": tuple(BN.SCALES), "echo": ("On", "Off"),
                  "snap": ("On", "Off")}
        for k, choices in checks.items():
            if k in want and want[k] not in choices:
                return "Bad request"
        for k in ("spin", "speed"):
            if k in want and not num(want[k]):
                return "Bad request"
        if "balls" in want and not (type(want["balls"]) is int and 0 <= want["balls"] <= BN.BALLS_MOST):
            return f"Up to {BN.BALLS_MOST} balls"
        if "sound" in want and not (isinstance(want["sound"], str) and (want["sound"] in
                                    {f"Tones/{t}" for t in BN.TONES} or B.where(b.banks, want["sound"]) is not None)):
            return "There's no such sound on the Soundboard"
        now = time.monotonic()
        if want.get("on") is True and b.bounce is None:
            if not self.board_shown():
                return "Open the Soundboard on the Pi first"
            self.bounce_start(now)
        elif want.get("on") is False and b.bounce is not None:
            self.bounce_leave()
        for k in ("key", "scale", "echo", "snap"):
            if k in want and want[k] != self.bounce_get(k):
                self.set_setting("bounce_" + k, want[k])
                if k == "echo":
                    self.bounce_told()
        if "shape" in want and want["shape"] != self.bounce_get("shape"):
            names = [n for n, _ in BN.SHAPES]
            self.bounce_shape(names.index(want["shape"]) - names.index(self.bounce_get("shape")))
        if "sound" in want and want["sound"] != self.bounce_sound_id():
            self.bounce_set_sound(want["sound"])
        w = b.bounce
        for k, (low, high) in (("spin", (-BN.SPIN_MOST, BN.SPIN_MOST)), ("speed", BN.SPEEDS)):
            if k in want:
                v = round(min(high, max(low, float(want[k]))), 2)
                if w is not None:
                    setattr(w, k, v)
                self.set_setting("bounce_" + k, f"{v:.2f}")
        if w is not None and "balls" in want:
            while len(w.balls) < want["balls"] and w.add():
                pass
            while len(w.balls) > want["balls"] and w.drop():
                pass
        if w is not None and "paused" in want:
            if want["paused"] is True and b.card is None:
                b.card = "bounce"
                self.sim_opts = 0
            elif want["paused"] is False and b.card == "bounce":
                b.card = None
                self.sim_close()
                b.bounce_at = now
                self.bounce_going()
        self.dirty = True
        return None
