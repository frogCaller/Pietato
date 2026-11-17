"""Apps' little worlds: what they share (the Fish Tank: fishtank.py)."""
import random


# ---- Apps' little worlds to watch ---------------------------------------------------------------------
# Each sim runs in a box beside its numbers, or on the whole screen (SELECT, or START's Full screen). A
# pauses, X gives it a poke, Y starts it again, START has its options, B goes back to the list.
# fishtank.py has the Fish Tank.
SIM_FLOOR = (21, 27, 33)                      # the box
SIM_BOX = (12, 78, 452, 424)                  # ...on the GPi Case's screen (a wider one: the box is wider)
SIM_IN = 2                                    # pieces keep this far in from its wall
SIM_PANEL = (468, 78, 628, 424)               # the numbers, beside it
SIM_DIRTY = (SIM_BOX[0], SIM_BOX[1], SIM_PANEL[2], SIM_PANEL[3])   # what changes from one frame to the next
SIM_FPS, SIM_FPS_BIG = 20, 10                 # frames a second (a Pi Zero on a TV: fewer, each one scaled up)
SIM_SAMPLE = 0.2                              # seconds between a chart's points
SIM_FULL = ("full", "Full screen", ("Off", "On"), "Off")   # (the last row of every sim's START card)


def sim_hue(h, s=0.45, v=1.0):
    import colorsys
    return tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h % 1.0, s, v))


class Sim:
    """A little world in a box, w x h px. update moves it on, draw puts it on the screen (the box's
    top-left at x0, y0), poke is X, restart is Y. Its options - (key, label, choices, default) - are
    START's card; values holds what you picked."""
    key = ""
    blurb = ""
    poke_label = None               # X: what it does, or None
    options = ()
    restart_for = ()                # options it starts again for
    pale_defaults = {}              # options it starts with on a light page (Settings > Appearance > App pages)
                                    # instead, till you pick any of them: {key: choice}
    bare = False                    # drawn on the page itself, in the middle: no box, no numbers beside it
    paced = False                   # its picture changes now and then (frame_in says when), not frame by frame
    look_now = False                # what look() says is drawn the moment it changes (the numbers: 4 times a second)
    backdrop = SIM_FLOOR            # what's behind it on the whole screen

    def __init__(self, w, h, rng=None, values=None):
        self.w, self.h = w, h
        self.rng = rng or random.Random()
        self.values = {k: d for k, _, _, d in self.options}
        self.values.update(values or {})
        self.paused = False
        self.clock = self.sampled = 0.0
        self.history = []               # (seconds, counts...), for a chart
        self.started = {}               # the options it last started with (those it starts again for)

    def configure(self, values):
        """Your choices, put to use: True if it has to start again for them."""
        changed = {k for k, v in values.items() if self.values.get(k) != v}
        self.values.update(values)
        self.apply()
        return bool(changed & set(self.restart_for))

    def apply(self):
        pass

    def needs_restart(self):
        """An option it starts again for has changed since it last started."""
        return any(self.values.get(k) != self.started.get(k) for k in self.restart_for)

    def restart(self):
        self.clock = self.sampled = 0.0
        self.history = []
        self.started = {k: self.values.get(k) for k in self.restart_for}

    def refit(self, w, h):
        """The box changes size (full screen, and back)."""
        self.w, self.h = w, h
        self.restart()

    def relook(self):
        """The pages' look has changed (Settings > Appearance > App pages): pictures it kept in the page's colours,
        thrown away."""

    def update(self, dt):
        return None

    def frame_in(self, wall):
        """A paced sim: seconds until its picture next changes (wall: time.time())."""
        return None

    def poke(self):
        pass

    def draw(self, img, x0, y0):
        pass

    def stats(self):
        """(label, value) rows for beside the box."""
        return []

    def chart(self):
        """(history, colours, top) for a chart beside the box, or None."""
        return None

    def note(self):
        """(title, words) for a card at the foot of the box, or None."""
        return None

    def note_top(self):
        """The card goes at the top of the box instead (out of the way of something at the foot)."""
        return False

    def hints(self):
        """Its buttons along the bottom, if it has its own: [(button, what it does)], or None."""
        return None

    def look(self):
        """Something that changes what's beside the box besides its numbers (drawn again when it does), or
        None."""
        return None

    def sample(self, counts):
        self.history.append((self.clock, tuple(counts)))
        if len(self.history) > 400:              # a long run: every other point
            self.history = self.history[:-1:2] + self.history[-1:]
