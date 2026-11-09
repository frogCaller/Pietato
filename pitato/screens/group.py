"""Apps > Group chat: your Pietatos talking among themselves, and with you (pitato/circle.py keeps the conversation and
decides who says what, and when); a line said popping up on the one you're at; and where you are, for the others: its
controller or keyboard pressed, or its camera seeing someone move."""
import collections
import io
import math
import threading
import time
import urllib.error

from ..theme import ACCENT, ACCENTS, BG, BODY, LINE, MUTED, ROW, TEXT
from ..library import LIBRARY, SCREEN_KINDS
from ..circle import CATCH_UP, CHOICES, Circle, GROUP_KEEP, builtin_line, hardware, model_words
from ..bot import FRIEND_STYLES, friend_command, ollama_generate
from ..savesync import ask_json, post_json
from ..screen import pi_model
from ..system import is_pc, pc_name
from ..handheld import is_handheld, name as handheld_name
from ..weather import place_text, wx_words

GROUP_TICK = 2.0             # seconds between the group's looks (who's gone quiet, what's due to be said)
GROUP_POP = (7.0, 12.0)      # seconds a line pops up for (a question: the longer)
GROUP_POPS = 3               # lines waiting to pop up, at most
GROUP_POP_STALE = 90         # ...and one that's waited this long isn't shown
GROUP_MODEL_WAIT = 60        # seconds its Bot's model has to answer before its own words are used instead
GROUP_SEND_WAIT = 5          # seconds another of yours has to take a line (or say what this one missed)
GROUP_TIME_GAP = 1800        # a gap this long in the conversation: the time it went on at, between
EYES_EVERY = 4               # seconds between its camera's looks for someone moving
EYES_IDLE = 30               # ...and between looks for whether it can (a camera plugged in, nothing else using it)
EYES_MOVED = (24, 0.03)      # someone moved: this share of the camera's picture changed by this much (of 255)
NOTICED_TELL = 120           # you, noticed here after this long away: your others told at once (not in 20 seconds)
GROUP_OLDER = 3600           # one of yours without the group chat (not updated yet): not asked again for this long
CASES = {"2w": "GPi Case 2W", "2": "GPi Case 2"}   # what a Pi's in (media.case), for the others


def eyes_small(jpeg):
    """A camera's picture, tiny and grey (decoded at an eighth of its size: next to no work)."""
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(jpeg))
        im.draft("L", (80, 60))
        return im.convert("L").resize((32, 24))
    except Exception:
        return None


def eyes_moved(a, b, most=EYES_MOVED):
    """Enough of the picture changed between a and b (both from eyes_small) for someone to have moved."""
    from PIL import ImageChops
    if a.size != b.size:
        return False
    hist = ImageChops.difference(a, b).histogram()
    return sum(hist[most[0]:]) >= most[1] * a.size[0] * a.size[1]


class GroupScreen:
    """Apps > Group chat, its pop-ups, and noticing you (group_setup makes the group: media mode's start)."""

    def group_setup(self):
        self.you_at = None           # when you were last noticed here (a button, a key; its camera): by the clock
        self.circle = c = Circle()
        c.own = self.group_own
        c.members = self.group_members
        c.send = self.group_send
        c.fetch = self.group_fetch
        c.words = self.group_words
        c.talk = lambda: self.setting("group_talk") != "Off"
        c.set_talk = self.group_set_talk
        c.on_new = self.group_new
        c.remark_every = lambda: self.friend.chatter()
        c.extra = self.group_extra
        self.group_next = 0.0        # when the group next looks (monotonic)
        self.group_pops = collections.deque()   # [(when it came, a line)]: to pop up, one after another
        self.group_pop = None        # ...the one up now: {"msg", "until"}
        self.group_scroll = 0        # how far back the page is scrolled (pixels)
        self.group_choice = 0        # Yes or No, picked under the question
        self.group_wraps = {}        # (a line's id, how wide) -> its words as they're wrapped, and its bubble's width
        self.group_drawn = None      # what the page showed, last it was drawn (group_signature)
        self.group_hw = (0.0, None)  # what it's made of, looked at then
        self.group_without = {}      # another of yours without the group chat (an older one) -> not asked till then
        self.eyes = None             # its camera looking for someone moving: the thread
        self.eyes_looking = False    # ...looking now

    # -- the group's hooks ---------------------------------------------------------------------------------------
    def group_own(self):
        return {"id": self.share_id, "name": self.own_name(), "accent": self.setting("accent") or "",
                "hw": self.group_hardware(), "doing": self.group_doing(), "you": self.you_at}

    def group_hardware(self):
        """What it's made of (circle.hardware), looked at again every minute (the screen changes, on a dock)."""
        at, hw = self.group_hw
        now = time.monotonic()
        if hw is None or now - at > 60:
            if is_handheld():
                board, kind = handheld_name(), "handheld"
            elif is_pc():
                board, kind = pc_name(), "pc"
            else:
                board, kind = pi_model(), "pi"
            fb = self.fb
            screen = (getattr(fb, "real_w", 0), getattr(fb, "real_h", 0)) if fb is not None else None
            hw = hardware(board, kind, screen, CASES.get(getattr(self, "case", None), ""))
            self.group_hw = (now, hw)
        return hw

    def group_doing(self):
        """What it's doing, in a few words, for your others ("playing Tetris", "on the home screen")."""
        try:
            if self.view == "update":
                return "updating itself"
            if self.resting:
                return "resting"
            run = self.game
            if run is not None and not run.ended:
                title = (run.game.get("title") or "")[:40]
                if self.attract_on():
                    return f"playing {title} by itself" if title else "playing a game by itself"
                watching = self.watching_of(run)
                if watching:                           # (another's game, watched here: screens/lobby.py)
                    return f"watching {watching['with']} play {title}" if title else f"watching {watching['with']} play"
                return f"playing {title}" if title else "playing a game"
            if self.proc and self.cur:
                title = (self.cur.get("title") or "")[:40]
                if self.kind == "radio":
                    return "playing the radio"
                if self.kind == "live":
                    return "watching TV"
                if self.kind == "audio":
                    return f"playing {title}" if title else "playing music"
                return f"watching {title}" if title else "watching a video"
            if self.prog is not None:
                return f"showing {self.prog_name}"
            if self.chromium is not None:
                return "on the web"
            if not self.active:
                return "in the terminal"
            if self.view == "home":
                return "on the home screen"
            if self.view in ("photo", "pdf", "text"):
                return {"photo": "showing a picture", "pdf": "showing a PDF", "text": "showing some text"}[self.view]
            if self.view == "list":
                tab = LIBRARY[self.tab]
                ttype = tab.get("type")
                if ttype == "chat":
                    return "in the group chat"
                if ttype == "friend":
                    return "chatting with its Bot"
                if ttype == "sim":
                    return f"showing {tab['name']}"
                return f"on {tab['name']}"
        except Exception:
            pass
        return "on"

    def group_members(self):
        return self.pie.group_members() if self.setting("share") != "Off" else []

    def group_older(self, url, ex):
        """Another of yours without the group chat (an older Pietato: its web page hasn't /api/group, or asks for its
        password for it): not asked again for a while. True when that's why it didn't answer."""
        if isinstance(ex, urllib.error.HTTPError) and ex.code in (401, 404):
            self.group_without[url] = time.monotonic() + GROUP_OLDER
            return True
        return False

    def group_send(self, url, msg):
        if self.group_without.get(url, 0) > time.monotonic():
            return
        try:
            got = post_json(f"{url}/api/group", {"msg": msg}, timeout=GROUP_SEND_WAIT)
        except urllib.error.HTTPError as ex:
            if self.group_older(url, ex):
                return
            raise
        if not isinstance(got, dict) or not got.get("ok"):
            raise ValueError((got or {}).get("error") if isinstance(got, dict) else "no answer")

    def group_fetch(self, url, since):
        if self.group_without.get(url, 0) > time.monotonic():
            return []
        try:
            got = ask_json(f"{url}/api/group?since={since:.3f}", timeout=GROUP_SEND_WAIT)
        except urllib.error.HTTPError as ex:
            if self.group_older(url, ex):
                return []
            raise
        if not isinstance(got, dict) or not got.get("ok") or not isinstance(got.get("msgs"), list):
            raise ValueError((got or {}).get("error") if isinstance(got, dict) else "no answer")
        return got["msgs"]

    def group_words(self, how, ctx):
        """A line: its Bot's model's (Settings > Bot), or its own words when there's none, or it doesn't answer."""
        fr = self.friend
        if not fr.conf:
            fr.load(self.friend_files())
        if fr.ready():
            server, model = fr.server, fr.model
            try:
                text = model_words(how, ctx, lambda system, prompt: ollama_generate(server, model, system, prompt,
                                                                                     timeout=GROUP_MODEL_WAIT))
                text = friend_command(text)[1].strip()    # (asking for something done: not here)
                if text:
                    return text
            except Exception as ex:
                print(f"group chat: the Bot's model didn't answer ({ex}): its own words", flush=True)
        return builtin_line(how, ctx, self.circle.rng)

    def group_extra(self):
        """What its words are made from, beside the group's: the weather, what's true now, how its Bot talks, your
        name (the Bot's)."""
        fr = self.friend
        style = fr.style()
        own = (fr.conf.get("persona") or "").strip()
        voice = own[:400] if own else next((s[2] for s in FRIEND_STYLES if s[0] == style["key"]), "")
        out = {"person": fr.name, "voice": voice, "hey": style["hey"], "ok": style["ok"]}
        facts = [f"Time: {time.strftime('%A')} {self.clock_text()}"]
        w = self.weather.data if self.weather is not None else None
        try:
            if w and w.get("temp") is not None:
                out["weather"] = f"{round(w['temp'])}°{w.get('units') or 'F'} and {wx_words(w.get('code'))[0].lower()}"
                facts.append(f"Weather now: {out['weather']}")
        except (KeyError, TypeError, ValueError):
            pass
        loc = self.setting("location")
        if loc:
            facts.append(f"Where you all are: {place_text(loc)}")
        out["facts"] = facts
        return out

    def group_set_talk(self, on):
        """Quiet, or talking again, said on one of them (perhaps another): kept as this one's setting too."""
        value = "On" if on else "Off"
        if self.setting("group_talk") != value:
            self.soon(lambda: self.set_setting("group_talk", value))
            self.wake()

    def group_new(self, msg):
        """(Any thread.) A line come: on the page, or popping up."""
        self.soon(lambda: self.group_heard(msg))
        self.wake()

    # -- you, here ---------------------------------------------------------------------------------------------------
    def you_noticed(self):
        """You're at this one: a button or a key pressed here, or its camera saw someone move. Your others told at
        once if you hadn't been noticed here for a while (its beacon says so every 20 seconds anyway)."""
        now = time.time()
        was, self.you_at = self.you_at, now
        if (was is None or now - was > NOTICED_TELL) and getattr(self, "sharing", False):
            threading.Thread(target=self.share_now, daemon=True, name="share-now").start()

    def eyes_start(self):
        """Its camera (a USB one, plugged in) watching for someone moving, while it may (eyes_ok)."""
        if self.eyes is None:
            self.eyes = threading.Thread(target=self.eyes_loop, daemon=True, name="group-eyes")
            self.eyes.start()

    def eyes_ok(self):
        """Its camera may look now: Group chat's camera on (SELECT there), sharing on, and nothing on that wants the
        Pi to itself (a game, a video, Chromium, cmatrix and the rest, an update)."""
        return (self.setting("group_eyes") != "Off" and self.setting("share") != "Off" and self.game is None
                and not (self.proc and self.kind in SCREEN_KINDS) and self.prog is None and self.chromium is None
                and self.view != "update")

    def eyes_loop(self):
        prev, seq = None, None
        while True:
            wait = EYES_IDLE
            try:
                cams = self.camera.own.look() if self.eyes_ok() else []
                got = self.camera.own.pick(f"/usb/{cams[0]['id']}/") if cams else None
                if got is not None:
                    jpeg, n = got[0].frame(timeout=3)
                    if jpeg and n != seq:
                        seq = n
                        small = eyes_small(jpeg)
                        if small is not None and prev is not None and eyes_moved(prev, small):
                            self.you_noticed()
                        prev = small
                    wait = EYES_EVERY
                else:
                    prev = None
            except Exception as ex:
                print(f"group chat: its camera couldn't look: {ex!r}", flush=True)
                prev = None
            self.eyes_looking = wait == EYES_EVERY
            time.sleep(wait)

    # -- the main loop -----------------------------------------------------------------------------------------------
    def group_tick(self, now):
        """(Media mode's main loop.) The group's look, every few seconds; a line popped up has had its time."""
        if now >= self.group_next:
            self.group_next = now + GROUP_TICK
            try:
                self.circle.tick()
            except Exception as ex:
                print(f"group chat: {ex!r}", flush=True)
            if self.on_group_page() and self.group_drawn != self.group_signature():
                self.dirty = True                     # (who's on, what they're doing: the page again)
        pop = self.group_pop
        if pop is not None and (now >= pop["until"] or not self.group_pop_ok()):
            self.group_pop = None
            self.dirty = True
            if not self.group_pop_ok():
                self.group_pops.clear()
        if self.group_pop is None and self.group_pops:
            self.group_pop_next(now)

    def group_pop_ok(self):
        """A line can pop up here: you're here, and nothing's on the whole screen (a game, a video...)."""
        return (self.active and not self.resting and self.game is None and not (self.proc and self.kind in SCREEN_KINDS)
                and self.prog is None and self.chromium is None and self.view not in ("keys", "update", "game")
                and not self.on_group_page() and self.circle.you_here())

    def group_heard(self, msg):
        """(Main loop.) A line come: the page drawn again, or it pops up (one of theirs, where you are)."""
        if self.on_group_page():
            self.dirty = True
            return
        if msg["who"] == "you" or msg["kind"] == "talk" or not self.group_pop_ok():
            return
        self.group_pops.append((time.monotonic(), msg))
        while len(self.group_pops) > GROUP_POPS:
            self.group_pops.popleft()
        if self.group_pop is None:
            self.group_pop_next(time.monotonic())

    def group_pop_next(self, now):
        while self.group_pops:
            came, msg = self.group_pops.popleft()
            if now - came <= GROUP_POP_STALE:
                secs = GROUP_POP[1] if msg["kind"] == "ask" else GROUP_POP[0]
                self.group_pop = {"msg": msg, "until": now + secs}
                self.dirty = True
                return

    def group_shown(self):
        """The line popped up now (its id), or None: for a page that's drawn bit by bit (a sim) to know it changed."""
        pop = getattr(self, "group_pop", None)
        return pop["msg"]["id"] if pop else None

    def group_bubble(self, d, low=False):
        """A line popped up, along the foot of the page: who said it, in its colour, and what (a question: where to
        answer it). True when it's drawn."""
        pop = getattr(self, "group_pop", None)
        if not pop:
            return False
        msg = pop["msg"]
        F, W, H = self.fonts, self.fb.w, self.fb.h
        text = msg["text"] + ("  Answer in Apps > Group chat." if msg["kind"] == "ask" else "")
        lines = self.wrap(d, text, F["small"], W - 24 - 32, 3)
        y1 = H - 10 if low or self.full_app() else H - self.FOOTER - 10
        y0 = y1 - (18 + 22 + 21 * len(lines))
        col = dict(ACCENTS).get(msg.get("accent")) or ACCENT
        d.rounded_rectangle((12, y0, W - 12, y1), radius=14, fill=BG, outline=LINE)
        d.ellipse((26, y0 + 14, 36, y0 + 24), fill=col)
        d.text((44, y0 + 19), self.fit(d, msg["name"] or "A Pietato", F["small_b"], W - 80), font=F["small_b"],
               fill=col, anchor="lm")
        y = y0 + 34
        for line in lines:
            d.text((26, y), line, font=F["small"], fill=TEXT, anchor="la")
            y += 21
        return True

    # -- the page ------------------------------------------------------------------------------------------------
    def on_group_page(self):
        return self.active and self.view == "list" and self.tab_type() == "chat"

    def group_opened(self):
        self.group_scroll, self.group_choice = 0, 0

    def group_signature(self):
        """What the page shows, roughly: drawn again when it changes."""
        c = self.circle
        return (c.version, c.talk(), tuple((m["name"], m["on"], m["doing"], m["you_here"]) for m in c.roster()),
                self.setting("group_eyes"), self.eyes_looking)

    def group_say(self, text):
        if text and text.strip():
            self.you_noticed()
            self.circle.you_said(text)
            self.group_scroll = 0
            self.dirty = True

    def press_group(self, name, repeat):
        if name in ("l", "r", "b"):
            return "pass"
        c = self.circle
        if name in ("up", "down"):
            self.group_scroll = max(0, self.group_scroll + (72 if name == "up" else -72))
            self.dirty = True
            return None
        if repeat:
            return None
        ask = c.open_ask()
        if name in ("left", "right") and ask is not None:
            self.group_choice = 0 if name == "left" else 1
        elif name == "a" and ask is not None:
            c.answer(ask, CHOICES[self.group_choice])
            self.group_scroll, self.group_choice = 0, 0
        elif name in ("a", "x"):
            self.open_keyboard("Say something to your Pietatos", "", self.group_say, limit=200)
        elif name == "y":
            quiet = c.talk()
            self.set_setting("group_talk", "Off" if quiet else "On")
            c.set_quiet(quiet)
            self.group_scroll = 0
            self.toast("They stay quiet now, and still answer you" if quiet else
                       "They talk among themselves again", 3)
        elif name == "select":
            off = self.setting("group_eyes") != "Off"
            self.set_setting("group_eyes", "Off" if off else "On")
            self.toast("Its camera doesn't look for you now" if off else
                       "Its camera looks for someone moving: you, here", 3)
        self.dirty = True
        return None

    def group_quiet_words(self, secs):
        mins = int(secs // 60)
        return ("quiet " + (f"{mins} min" if mins < 60 else f"{mins // 60} h" if mins < 1440 else
                            f"{mins // 1440} d"))

    def render_group(self):
        from ..fine import Image, ImageDraw
        F = self.fonts
        c = self.circle
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        self.header(img, d)
        top, bottom = self.LIST_TOP + 4, H - self.FOOTER - 10
        sharing = self.setting("share") != "Off"
        roster = c.roster()
        talk = c.talk()
        self.group_drawn = self.group_signature()

        # who's in it, on a card on the left: this one first. Each: its name (YOU: you're with it), what it is, and
        # what it's doing (or how long it's been quiet)
        cx0, cx1 = 16, 16 + int(max(190, min(320, W * 0.28)))
        d.rounded_rectangle((cx0, top, cx1, bottom), radius=18, fill=ROW)
        y, room, tw = top + 12, bottom - 44, cx1 - cx0 - 46
        for k, m in enumerate(roster):
            if y + 52 > room:
                d.text((cx0 + 32, y + 8), f"and {len(roster) - k} more", font=F["label"], fill=MUTED, anchor="lm")
                break
            col = dict(ACCENTS).get(m["accent"]) or (ACCENT if m["self"] else MUTED)
            box = (cx0 + 14, y + 4, cx0 + 25, y + 15)
            if m["on"]:
                d.ellipse(box, fill=col)
            else:
                d.ellipse(box, outline=col, width=2)
            here = 40 if m["you_here"] else 0
            d.text((cx0 + 32, y + 10), self.fit(d, m["name"] or "This one", F["small_b"], tw - here),
                   font=F["small_b"], fill=TEXT if m["on"] else MUTED, anchor="lm")
            if here:                                  # (you're with it)
                d.rounded_rectangle((cx1 - 52, y + 2, cx1 - 14, y + 18), radius=8, fill=col)
                d.text((cx1 - 33, y + 10), "YOU", font=F["badge"], fill=BG, anchor="mm")
            board = (m["hw"] or {}).get("b") or "A Pietato"
            what = "This one" if m["self"] else m["doing"] if m["on"] else \
                self.group_quiet_words(m.get("quiet_for") or 0)
            d.text((cx0 + 32, y + 28), self.fit(d, board, F["label"], tw), font=F["label"], fill=MUTED, anchor="lm")
            d.text((cx0 + 32, y + 45), self.fit(d, what or "", F["label"], tw), font=F["label"],
                   fill=BODY if m["on"] and not m["self"] else MUTED, anchor="lm")
            y += 62
        if not sharing:
            note, tone = "Sharing is off: Settings", MUTED
        elif len(roster) == 1:
            note, tone = "Your others show up here", MUTED
        else:
            note, tone = ("Talking: on" if talk else "Talking: off"), (ACCENT if talk else MUTED)
        d.text(((cx0 + cx1) / 2, bottom - 20), note, font=F["label"], fill=tone, anchor="mm")

        # the conversation on the right, the newest at the bottom
        x0, x1 = cx1 + 14, W - 16
        pw, ph = x1 - x0, bottom - top - (44 if self.msg else 0)
        panel = Image.new("RGB", (pw, ph), BG)
        pd = ImageDraw.Draw(panel)
        ask = c.open_ask()
        lines = c.lines()
        bubbles = self.group_bubbles(pd, lines, pw, ask)
        total = sum(b["h"] + 10 for b in bubbles)
        self.group_scroll = max(0, min(self.group_scroll, total - ph))
        y = ph + self.group_scroll
        for b in reversed(bubbles):
            y -= b["h"]
            if y + b["h"] < 0:
                break
            if y < ph:
                self.draw_group_bubble(pd, b, y, pw)
            y -= 10
        if not lines:
            pd.text((pw / 2, ph / 2 - 14), "Nothing said yet", font=F["big"], fill=TEXT, anchor="mm")
            pd.text((pw / 2, ph / 2 + 18), "A to say something. Your others join in", font=F["small"], fill=MUTED,
                    anchor="mm")
        img.paste(panel, (x0, top))
        if self.group_scroll:
            d.text((x0 + pw / 2, top + ph - 4), "▼", font=F["small"], fill=MUTED, anchor="mb")
        if ask is not None:
            hints = [("◀▶", "Yes or No"), ("A", "Answer"), ("X", "Say something")]
        else:
            hints = [("A", "Say something")]
        hints += [("Y", "Quiet" if talk else "Let them talk")]
        if self.camera.own.found:                     # (a USB camera plugged in: it can look for you)
            hints.append(("SELECT", "Camera off" if self.setting("group_eyes") != "Off" else "Camera on"))
        hints += [("▲▼", "Scroll"), ("B", "Home")]
        self.footer(d, self.hints_room(hints, keep=("A", "Y", "◀▶", "B")))
        self.fb.show(img)

    def group_bubbles(self, pd, lines, pw, ask):
        """Each line as it's drawn, oldest first: [{"kind": "line"/"note"/"time", "who", "name", "colour", "lines",
        "w", "h", "chips"}]; the time between them where the conversation stopped a while."""
        F = self.fonts
        maxw = int(pw * 0.84)
        me = self.own_name()
        out, last = [], None
        for m in lines:
            if last is None or m["t"] - last >= GROUP_TIME_GAP:
                t = time.localtime(m["t"])
                day = "" if time.strftime("%Y%m%d", t) == time.strftime("%Y%m%d") else time.strftime("%a ", t)
                out.append({"kind": "time", "text": day + self.clock_text(t), "h": 18})
            last = m["t"]
            if m["kind"] == "talk":
                where = "" if m["name"] == me else f" on {m['name']}"
                out.append({"kind": "note", "h": 18, "text": ("You asked them to be quiet" if not m.get("on") else
                                                              "You let them talk again") + where})
                continue
            key = (m["id"], pw)
            got = self.group_wraps.get(key)
            if got is None:
                wrapped = self.wrap(pd, m["text"], F["chat"], maxw - 28, lines=12)
                w = max([pd.textlength(ln, font=F["chat"]) + 28 for ln in wrapped] + [60])
                got = self.group_wraps[key] = (wrapped, int(w))
                if len(self.group_wraps) > 2 * GROUP_KEEP:
                    self.group_wraps.clear()
            wrapped, w = got
            mine = m["who"] == "you"
            label = (m["name"] or "A Pietato") if not mine else ("" if m["name"] == me else f"You, on {m['name']}")
            if label:
                w = max(w, int(pd.textlength(label, font=F["small_b"])) + 28)
            h = 14 + (20 if label else 0) + 24 * len(wrapped)
            chips = ask is not None and m["id"] == ask["id"]
            out.append({"kind": "line", "who": m["who"], "name": label, "lines": wrapped, "w": min(w, maxw),
                        "h": h + (38 if chips else 0), "body": h, "chips": chips,
                        "colour": dict(ACCENTS).get(m.get("accent")) or ACCENT})
        return out

    def draw_group_bubble(self, pd, b, y, pw):
        F = self.fonts
        if b["kind"] in ("time", "note"):
            pd.text((pw / 2, y + b["h"] / 2), b["text"], font=F["label"], fill=MUTED, anchor="mm")
            return
        mine = b["who"] == "you"
        x0 = pw - b["w"] if mine else 0
        fill = tuple(int(a * 0.32 + c * 0.68) for a, c in zip(ACCENT, ROW)) if mine else ROW
        pd.rounded_rectangle((x0, y, x0 + b["w"], y + b["body"]), radius=14, fill=fill)
        ty = y + 7
        if b["name"]:
            pd.text((x0 + 14, ty + 10), b["name"], font=F["small_b"], fill=BODY if mine else b["colour"], anchor="lm")
            ty += 20
        for k, line in enumerate(b["lines"]):
            pd.text((x0 + 14, ty + k * 24 + 12), line, font=F["chat"], fill=TEXT, anchor="lm")
        if b["chips"]:                                # (the question you haven't answered: Yes or No)
            cy = y + b["body"] + 8
            for k, word in enumerate(CHOICES):
                cx = x0 + k * 84
                lit = k == self.group_choice
                pd.rounded_rectangle((cx, cy, cx + 74, cy + 28), radius=14, fill=ACCENT if lit else ROW,
                                     outline=None if lit else LINE)
                pd.text((cx + 37, cy + 14), word, font=F["small_b"], fill=BG if lit else TEXT, anchor="mm")

    # -- your other Pietatos (the control server's thread) -----------------------------------------------------------
    def web_group(self, cmd):
        """POST /api/group: a line said on another of yours, kept here (and perhaps answered)."""
        if self.setting("share") == "Off" or not self.saves_peers(str(cmd.get("from") or "")):
            return {"ok": False, "error": "Not one of yours"}
        return {"ok": True, "new": self.circle.receive(cmd.get("msg"))}

    def web_group_since(self, since, addr):
        """GET /api/group: what's been said since then, for another of yours that was off."""
        if self.setting("share") == "Off" or not self.saves_peers(str(addr or "")):
            return {"ok": False, "error": "Not one of yours"}
        try:
            t = float(since)
        except (TypeError, ValueError):
            t = 0.0
        if not math.isfinite(t):
            t = 0.0
        return {"ok": True, "msgs": self.circle.since(max(t, time.time() - CATCH_UP))[-GROUP_KEEP:]}

    # -- the web page's Settings --------------------------------------------------------------------------------------
    def web_set_group_talk(self, value, cmd):
        if value not in ("On", "Off"):
            return {"error": "That isn't one of its choices"}
        if (value == "On") != self.circle.talk():
            self.set_setting("group_talk", value)
            self.circle.set_quiet(value == "Off")
        return {"ok": True}

    def web_set_group_eyes(self, value, cmd):
        if value not in ("On", "Off"):
            return {"error": "That isn't one of its choices"}
        self.set_setting("group_eyes", value)
        return {"ok": True}
