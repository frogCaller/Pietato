"""The Cookie (pitato/cookie.py: its rules; pitato/cookiepage.py: its page): media mode's part. Who got the last cookie
(the one to beat for the next) is kept here and told to your others in this one's beacon (straight to each of them,
every 20 seconds, with the group chat's), and what theirs say is looked at every few seconds: a later one than the one
known here is this one's word for it too. None yet: one of them gets the first, once two that play have heard each
other. The one that got the last not heard for an hour: the one that's waited longest, of those on, gets the next.

A throw for one: the one that wants a cookie sends its throw to the web page of the one to beat (POST /api/cookie,
from your network only: webui.py, control.py), which answers with its own and how it went; a win, and it's told as
the one that got a cookie from then on (the one it beat says so at once, to all of them). Their Bots play by
themselves, one of them about every ten minutes: not at night, not while this one's in a game or a video, and not
while the group chat's quiet. You play from its page (◀ rock, ▲ paper, ▶ scissors); on the one to beat, with its
page open, another's throw waits a few seconds for yours, and its Bot throws if you don't. The one that's just got
a cookie says so in the group chat. Everything it shows and says is of cookies got (and eaten), never of one taken:
"Den got a cookie", "I got a cookie!".

Each keeps how many throws in a row it's won (a tie changes nothing), and says so with its throw and its answer. One
that's just been beaten by another on its third win in a row or more may say, a few seconds on, that it must be
cheating: a line in the group chat (pitato/circle.py's "cheat"), which the accused and your others answer."""
import math
import random
import threading
import time
import uuid

from ..circle import NIGHT, ON_WITHIN
from ..config import clean_name
from ..cookie import (
    cookie_accuses, cookie_ago, cookie_beat, cookie_bot_throw, cookie_count, cookie_habit, cookie_heir, cookie_line,
    cookie_newer, cookie_night, cookie_rec, cookie_result, cookie_says, cookie_whose, COOKIE_KEPT, COOKIE_SUSPECT,
    COOKIE_THROW)
from ..cookiepage import COOKIE_STILL
from ..library import LIBRARY, SCREEN_KINDS
from ..savesync import post_json
from ..theme import accent_for, ACCENTS

COOKIE_TICK = 5.0             # seconds between its looks (who got the last cookie, whether its Bot's throw is due)
COOKIE_SETTLE = 60            # seconds after it starts before it gets the first cookie (your others' word comes
COOKIE_SETTLE_ANY = 300       # first): the one of them with the lowest id; after this long, whichever
COOKIE_GRACE = 120            # ...and before it gets the next, the one that got the last gone quiet
COOKIE_DROP = 3600            # the one that got the last cookie, not heard for this long: another gets the next
COOKIE_EVERY = (480, 720)     # seconds between their Bots' tries, all of them together (each waits as many times as
                              # long as there are of them trying)
COOKIE_FIRST = (60, 600)      # ...this one's first, after it starts
COOKIE_AGAIN = (20, 300)      # ...and after the night, or a game: not all of them at once
COOKIE_GAP = 15               # seconds between one Pietato's tries, at least (the rule of the one it plays; yours too)
COOKIE_ANSWER = 6             # seconds you have to throw, when another plays this one for a cookie
COOKIE_ASK_WAIT = 12          # seconds the one to beat has to answer a try (your throw there takes a few)
COOKIE_SHOW = 8               # seconds what's just happened stays at the top of its page
COOKIE_ACCUSE_WAIT = (4, 12)  # seconds after a throw before the one beaten says the winner's cheating
COOKIE_KEYS = {"left": "r", "up": "p", "right": "s"}   # its page's buttons: ◀ rock, ▲ paper, ▶ scissors


class CookieScreen:
    """The Cookie: who has it, their Bots' tries for it and yours, and its page (cookie_setup: media mode's start)."""

    def cookie_setup(self):
        self.cookie_lock = threading.RLock()   # the cookie as it's known here, and a try being answered
        self.cookie_rng = random.Random()
        self.cookie_up = time.monotonic()      # when this started (it waits a little before it gets the first, or
                                               # the next after one that's gone quiet)
        self.cookie_next = 0.0                 # when it next looks (monotonic)
        self.cookie_try_at = self.cookie_up + self.cookie_rng.uniform(*COOKIE_FIRST)   # ...and its Bot next tries
        self.cookie_held = False               # its Bot may not try just now (the night, a game)
        self.cookie_trying = ""                # a try's on its way to the holder: "you" (yours) or "bot" (its Bot's)
        self.cookie_tries = {}                 # another's id -> when it last tried for the one here (monotonic)
        self.cookie_ask = None                 # another's try, waiting for your throw: {"name", "until", "done",
                                               # "throw"}
        self.cookie_news = None                # what's just happened, for the top of its page: {"head", "sub",
                                               # "until", "again": your next throw's wait said after it}
        self.cookie_wait = 0.0                 # your next try: not before this (monotonic)
        self.cookie_deaf = False               # its holder didn't answer this one's last try (its web page's off):
                                               # heard or not, it's as good as gone, till it answers one
        st = self.state.get("cookie")
        st = st if isinstance(st, dict) else {}
        throws, seen = st.get("throws"), st.get("seen")
        kept = {"rec": cookie_rec(st.get("rec")), "had": cookie_count(st.get("had")) or 0,
                "throws": "".join(c for c in throws if c in COOKIE_THROW)[-COOKIE_KEPT:]
                if isinstance(throws, str) else "",
                "beat": st.get("beat") if st.get("beat") in COOKIE_THROW else "",
                "said": cookie_count(st.get("said")) or 0, "wins": cookie_count(st.get("wins"), 9999) or 0,
                "seen": float(seen) if isinstance(seen, (int, float)) and not isinstance(seen, bool)
                and math.isfinite(seen) and seen > 0 else 0.0}
        if cookie_whose(st.get("id")):
            kept["id"] = st["id"]
        self.state["cookie"] = kept            # {"id": this one's, "rec": the cookie as it's known here (or None),
                                               #  "had": how many times it had moved when it last got here, "throws":
                                               #  its Bot's last few, "beat": what last beat its Bot, "said": the
                                               #  cookie it last told the group chat it had (its n), "wins": the
                                               #  throws it's won in a row, "seen": when its holder was last heard}.
                                               #  Never changed in place: a new one each time (it's written down by
                                               #  other threads, as part of the state)

    # -- the cookie as it's known here -------------------------------------------------------------------------------
    def cookie_me(self, new=False):
        """This Pietato's id for the cookie: made once, and kept. new: another one, now (two of yours had the same: an
        SD card copied). If it had the cookie, it has it still, as its new self."""
        made = False
        with self.cookie_lock:
            st = self.state["cookie"]
            me = None if new else cookie_whose(st.get("id"))
            if me is None:
                me, made = uuid.uuid4().hex[:16], True
                rec, more = st.get("rec"), {}
                if rec is not None and rec["at"] == st.get("id"):
                    more = {"rec": dict(rec, n=rec["n"] + 1, at=me), "had": rec["n"] + 1, "said": rec["n"] + 1}
                self.state["cookie"] = dict(st, id=me, **more)
        if made:
            self.save_state()
        return me

    def cookie_here(self):
        """This one got the last cookie (with sharing off, it's out of it: no)."""
        st = getattr(self, "state", {}).get("cookie") or {}
        rec = st.get("rec")
        return bool(rec) and rec["at"] == st.get("id") and self.setting("share") != "Off"

    def cookie_keep(self, **changes):
        """Something of it kept (in the state: written down the next time that is)."""
        with self.cookie_lock:
            self.state["cookie"] = dict(self.state["cookie"], **changes)

    def cookie_beacon(self):
        """What this one's beacon says of the cookie, to your others."""
        me = self.cookie_me()
        st = self.state["cookie"]
        return cookie_says(me, st.get("rec"), st.get("had") or 0, st.get("throws") or "", st.get("wins") or 0)

    def cookie_heard(self):
        """Your other Pietatos as their beacons were last heard, for the cookie (none with sharing off)."""
        return self.pie.cookie_heard() if self.setting("share") != "Off" else []

    @staticmethod
    def cookie_on(heard, wall):
        """Of those, the ones that are on and play, each once (two addresses with one id: the one heard last):
        [{"id", "rec", "had", "throws", "url", "name", "accent"}]."""
        out = {}
        for h in sorted(heard, key=lambda h: h["seen"]):
            said = h["cookie"]
            if said is not None and wall - h["seen"] <= ON_WITHIN:
                out[said["id"]] = dict(said, url=h["url"], name=h["name"], accent=h["accent"])
        return list(out.values())

    def cookie_set(self, rec):
        """(Its lock held; any thread.) The cookie's somewhere new, as far as this one knows: kept, and written down.
        Come here: said in the group chat, once for each time it does."""
        st = self.state["cookie"]
        new = dict(st, rec=rec, seen=time.time())
        came = rec["at"] == st.get("id") and st.get("said", 0) < rec["n"]
        if rec["at"] == st.get("id"):
            new["had"] = rec["n"]
            new["said"] = max(st.get("said", 0), rec["n"])
        self.state["cookie"] = new
        self.cookie_deaf = False
        self.save_state()
        self.soon(lambda: self.cookie_moved(rec, came))
        self.wake()

    def cookie_moved(self, rec, came):
        """(Main loop.) The screen, with the cookie somewhere new: its page, and the small one on the bar. Come here:
        this one says so in the group chat (not while it's quiet)."""
        self.next_status = 0.0
        self.cookie_redraw()
        if came and self.setting("share") != "Off" and self.setting("group_talk") != "Off":
            try:
                c = self.circle
                c.add(c.new(cookie_line(rec, c.rng), topic="cookie", about=rec["from"] or None))
            except Exception as ex:
                print(f"the cookie: {ex!r}", flush=True)

    def cookie_fact(self):
        """A line on the cookies for their Bots' models (the group chat's): how they're got, and who got the last."""
        st = self.state["cookie"]
        rec = st.get("rec")
        if rec is None:
            return ""
        mine = rec["at"] == st.get("id")
        return ("Cookies: you all play each other at rock paper scissors, and whoever wins a throw gets a cookie (and "
                f"eats it). {'You' if mine else rec['name']} got the last one, and {'are' if mine else 'is'} the one "
                "to beat for the next")

    # -- the main loop -----------------------------------------------------------------------------------------------
    def cookie_tick(self, now):
        """(Media mode's main loop.) Its look, every few seconds."""
        if now < getattr(self, "cookie_next", math.inf):
            return
        self.cookie_next = now + COOKIE_TICK
        if self.setting("share") == "Off":
            return
        try:
            self.cookie_look(now)
        except Exception as ex:                        # (never the main loop's end)
            print(f"the cookie: {ex!r}", flush=True)

    def cookie_look(self, now):
        """Who got the last cookie, as your others say: a later one than this one knows of is this one's word for it
        too. None yet anywhere: this one gets the first, if it's the one to. The one that got the last not heard for
        an hour: this one gets the next, if it's the one to. That one on: this one's Bot plays it for one, when
        that's due."""
        wall = time.time()
        heard = self.cookie_heard()
        said = [h["cookie"] for h in heard if h["cookie"] is not None]
        with self.cookie_lock:
            if not said and self.state["cookie"].get("rec") is None:
                return                                 # (no other that plays, and no cookie: nothing to do)
            me = self.cookie_me()
            if any(s["id"] == me for s in said):       # (another of yours with this one's id: a new one here)
                me = self.cookie_me(new=True)
                self.soon(lambda: self.cookie_moved(None, False))
            mine = best = self.state["cookie"].get("rec")
            for s in said:
                if cookie_newer(s["rec"], best):
                    best = s["rec"]
            if best is not mine:
                self.cookie_set(best)
                mine = best
            peers = self.cookie_on(heard, wall)
            up = now - self.cookie_up
            if mine is None:
                if peers and (up >= COOKIE_SETTLE_ANY or (up >= COOKIE_SETTLE and me < min(p["id"] for p in peers))):
                    self.cookie_set({"n": 1, "at": me, "name": self.own_name(), "t": wall, "from": "", "how": "new",
                                     "you": False})
                return
            if mine["at"] == me:
                return
            st = self.state["cookie"]
            on = any(p["id"] == mine["at"] for p in peers)
            if on and not self.cookie_deaf:
                self.state["cookie"] = dict(st, seen=wall)
            else:                                      # (its holder's not heard, or doesn't answer: for an hour, and
                seen = min(st.get("seen") or 0.0, wall)   # the cookie's the one's that's waited longest)
                heir = cookie_heir([(me, st.get("had") or 0)]
                                   + [(p["id"], p["had"]) for p in peers if p["id"] != mine["at"]])
                if wall - seen >= COOKIE_DROP and up >= COOKIE_GRACE and heir == me:
                    self.cookie_set({"n": mine["n"] + 1, "at": me, "name": self.own_name(), "t": wall,
                                     "from": mine["name"], "how": "left", "you": False})
                    return
            if not on:
                return
            if not self.cookie_bots_may(wall):
                self.cookie_held = True
                return
            if self.cookie_held:                       # (the night's over, the game's ended: not all of them at once)
                self.cookie_held = False
                self.cookie_try_at = max(self.cookie_try_at, now + self.cookie_rng.uniform(*COOKIE_AGAIN))
            if now < self.cookie_try_at or self.cookie_trying:
                return
            self.cookie_try_at = now + self.cookie_rng.uniform(*COOKIE_EVERY) * max(1, len(peers))
        self.cookie_try()

    def cookie_bots_may(self, wall):
        """Its Bot may try for the cookie now: the group chat's not quiet, it's not the night, and this one's not in a
        game, a video or an update."""
        return (self.setting("group_talk") != "Off" and not cookie_night(time.localtime(wall).tm_hour, NIGHT)
                and self.game is None and not (self.proc and self.kind in SCREEN_KINDS) and self.view != "update")

    # -- a throw -----------------------------------------------------------------------------------------------------
    def cookie_bot(self):
        """Its Bot's throw: by its habit."""
        st = self.state["cookie"]
        return cookie_bot_throw(cookie_habit(self.cookie_me()), st.get("throws") or "", st.get("beat") or "",
                                self.cookie_rng)

    def cookie_threw(self, throw, beat=""):
        """Its Bot threw that: kept with its last few (your others show them). beat: what beat it, if it lost."""
        with self.cookie_lock:
            st = self.state["cookie"]
            self.state["cookie"] = dict(st, throws=((st.get("throws") or "") + throw)[-COOKIE_KEPT:],
                                        beat=beat or st.get("beat") or "")

    def cookie_streak(self, res):
        """A throw's gone res for this one ("won", "lost" or "tie"): how many it's won in a row now (a tie changes
        nothing)."""
        with self.cookie_lock:
            st = self.state["cookie"]
            wins = st.get("wins") or 0
            wins = wins + 1 if res == "won" else 0 if res == "lost" else wins
            self.state["cookie"] = dict(st, wins=wins)
        return wins

    def cookie_suspect(self, name, wins):
        """(Any thread.) Another's just beaten this one, its wins-th throw won in a row (a cookie for each). From its
        third, perhaps this one says it must be cheating (it isn't): in the group chat, a few seconds on, where the
        accused and your others answer (circle.py). Not while the group chat's quiet. True if it's to be said."""
        if (self.setting("share") == "Off" or self.setting("group_talk") == "Off"
                or not cookie_accuses(wins, self.cookie_rng)):
            return False
        self.circle.schedule(self.cookie_rng.uniform(*COOKIE_ACCUSE_WAIT), "cheat", {"about": name, "wins": wins})
        return True

    def cookie_say(self, head, sub, again=False):
        """What's just happened, at the top of its page for a few seconds."""
        self.cookie_news = {"head": head, "sub": sub, "until": time.monotonic() + COOKIE_SHOW, "again": again}
        self.cookie_redraw()

    def cookie_try(self, throw=None):
        """This one tries for the cookie: its Bot's throw, or yours (throw). Its holder's asked on a thread of its
        own: someone there may be given a few seconds for theirs. False: there's nobody to ask."""
        with self.cookie_lock:
            st = self.state["cookie"]
            rec, me = st.get("rec"), st.get("id")
            if rec is None or me is None or rec["at"] == me or self.cookie_trying:
                return False
            holder = next((p for p in self.cookie_on(self.cookie_heard(), time.time()) if p["id"] == rec["at"]),
                          None)
            if holder is None:
                return False
            you = throw is not None
            if not you:
                throw = self.cookie_bot()
            self.cookie_trying = "you" if you else "bot"
        self.cookie_redraw()
        body = {"id": me, "name": self.own_name(), "n": rec["n"], "throw": throw, "you": you,
                "wins": st.get("wins") or 0}
        url, name = holder["url"], holder["name"]

        def go():
            try:
                got = post_json(f"{url}/api/cookie", body, timeout=COOKIE_ASK_WAIT)
            except Exception as ex:
                print(f"the cookie: {name} didn't answer ({ex})", flush=True)
                got = None
            self.soon(lambda: self.cookie_tried(name, throw, you, got))
            self.wake()
        threading.Thread(target=go, daemon=True, name="cookie-try").start()
        return True

    def cookie_tried(self, name, throw, you, got):
        """(Main loop.) The holder's answer to this one's try: how it went, said at the top of its page; won, the
        cookie's this one's (it got it)."""
        now = time.monotonic()
        self.cookie_trying = ""
        res = got.get("got") if isinstance(got, dict) and got.get("ok") is True else None
        self.cookie_deaf = res is None                 # (no answer: its web page's off, as far as this one can tell)
        theirs = got.get("mine") if res else None
        new = cookie_rec(got.get("rec")) if res else None
        mine_w, my = COOKIE_THROW[throw], "your" if you else "this one's"
        if res in ("won", "lost", "tie") and theirs in COOKIE_THROW:
            if not you:
                self.cookie_threw(throw, theirs if res == "lost" else "")
            self.cookie_streak(res)
            if res == "lost":                          # (the one it played has won again: suspicious, after a few)
                self.cookie_suspect(name, cookie_count(got.get("wins"), 9999) or 0)
            self.cookie_wait = 0.0 if res == "won" else now + COOKIE_GAP
            if res == "won":
                with self.cookie_lock:
                    if (new is not None and new["at"] == self.cookie_me()
                            and cookie_newer(new, self.state["cookie"].get("rec"))):
                        self.cookie_set(new)
                self.cookie_say(f"{my.capitalize()} {mine_w} beat {name}'s {COOKIE_THROW[theirs]}",
                                f"{self.own_name()} got a cookie!")
            elif res == "lost":
                self.cookie_say(f"{name}'s {COOKIE_THROW[theirs]} beat {my} {mine_w}", f"{name} got another cookie.",
                                again=you)
            else:
                self.cookie_say(f"Both threw {mine_w}", "No cookie this time.", again=you)
        elif res == "wait":
            secs = got.get("wait")
            secs = secs if isinstance(secs, int) and not isinstance(secs, bool) and 0 < secs <= COOKIE_GAP else 3
            self.cookie_wait = now + secs
            if you:
                self.cookie_say("Too soon", f"{name} plays one throw every {COOKIE_GAP} seconds.", again=True)
        elif res == "gone":
            with self.cookie_lock:
                if cookie_newer(new, self.state["cookie"].get("rec")):
                    self.cookie_set(new)
            if you:
                self.cookie_say("Too late", "Another got a cookie a moment ago.")
        elif you:
            self.cookie_say(f"{name} didn't answer", "Try again in a moment.")
        self.cookie_redraw()

    def web_cookie(self, cmd):
        """POST /api/cookie (the control server's thread): another of yours tries for the cookie, with its throw. Not
        here (or not the one it means): told so, with the cookie as it's known here. One try from each every few
        seconds. Its page open here: you're given a few seconds to throw; else, or if you don't, its Bot does. Beaten,
        the cookie's the other's: all of yours are told at once. The answer: how it went for the one that tried
        ("won", "lost", "tie"), this one's throw, the cookie now, and how many throws in a row this one's won."""
        if self.setting("share") == "Off" or not self.saves_peers(str(cmd.get("from") or "")):
            return {"ok": False, "error": "Not one of yours"}
        who, throw = cookie_whose(cmd.get("id")), cmd.get("throw")
        if who is None or throw not in COOKIE_THROW:
            return {"ok": False, "error": "What's that?"}
        name = clean_name(cmd.get("name"), 40) or "A Pietato"
        now = time.monotonic()
        with self.cookie_lock:
            me = self.cookie_me()
            rec = self.state["cookie"].get("rec")
            if rec is None or rec["at"] != me or who == me or cmd.get("n") != rec["n"]:
                return {"ok": True, "got": "gone", "rec": rec}
            last = self.cookie_tries.get(who)
            if last is not None and now - last < COOKIE_GAP:
                return {"ok": True, "got": "wait", "wait": max(1, math.ceil(COOKIE_GAP - (now - last)))}
            if self.cookie_ask is not None:            # (another's try is waiting for your throw)
                return {"ok": True, "got": "wait", "wait": 3}
            if len(self.cookie_tries) > 32:
                self.cookie_tries.clear()
            self.cookie_tries[who] = now
            ask = None
            if self.cookie_shown():                    # (its page is open here: your throw)
                ask = self.cookie_ask = {"name": name, "until": now + COOKIE_ANSWER, "done": threading.Event(),
                                         "throw": None}
        if ask is not None:
            self.soon(self.cookie_redraw)
            self.wake()
            ask["done"].wait(COOKIE_ANSWER + 0.5)
        with self.cookie_lock:
            mine = None
            if ask is not None:
                self.cookie_ask, mine = None, ask["throw"]
            you = mine is not None
            rec = self.state["cookie"].get("rec")
            if rec is None or rec["at"] != me or cmd.get("n") != rec["n"]:   # (gone while you thought about it)
                self.soon(self.cookie_redraw)
                self.wake()
                return {"ok": True, "got": "gone", "rec": rec}
            if not you:
                mine = self.cookie_bot()
            res = cookie_result(throw, mine)
            if not you:
                self.cookie_threw(mine, throw if res == "won" else "")
            my, mine_w, theirs_w = "your" if you else "this one's", COOKIE_THROW[mine], COOKIE_THROW[throw]
            wins = self.cookie_streak({"won": "lost", "lost": "won"}.get(res, "tie"))
            if res == "won":
                self.cookie_set({"n": rec["n"] + 1, "at": who, "name": name, "t": time.time(),
                                 "from": self.own_name(), "how": throw + mine, "you": cmd.get("you") is True})
                self.cookie_suspect(name, (cookie_count(cmd.get("wins"), 9999) or 0) + 1)
                news = (f"{name}'s {theirs_w} beat {my} {mine_w}", f"{name} got a cookie.")
            elif res == "lost":
                news = (f"{my.capitalize()} {mine_w} beat {name}'s {theirs_w}",
                        f"{self.own_name()} got another cookie.")
            else:
                news = (f"Both threw {mine_w}", "No cookie this time.")
            rec = self.state["cookie"].get("rec")
        self.soon(lambda: self.cookie_say(*news))
        self.wake()
        if res == "won" and getattr(self, "sharing", False):   # (all of yours told now, not at its next beacon)
            threading.Thread(target=self.share_now, daemon=True, name="share-now").start()
        return {"ok": True, "got": res, "mine": mine, "rec": rec, "wins": wins}

    # -- Apps > The Cookie -------------------------------------------------------------------------------------------
    def cookie_tab(self):
        """This page is The Cookie's."""
        try:
            return self.tab_type() == "sim" and LIBRARY[self.tab].get("sim") == "cookie"
        except (AttributeError, IndexError, KeyError, TypeError):
            return False

    def cookie_shown(self):
        """Its page is on the screen, with someone likely at it."""
        return bool(self.active and not self.resting and self.view == "list" and self.cookie_tab()
                    and self.sim_opts is None)

    def cookie_redraw(self):
        """(Main loop.) The screen drawn again; its page, and its countdown's steps, from now."""
        self.dirty = True
        if self.cookie_tab():
            self.sim_next = 0.0

    def cookie_until(self):
        """(Its page's, asked each frame.) Seconds till its top next changes by itself: a countdown's next second,
        what's just happened having had its time; else a while (how long ago: by the minute)."""
        now = time.monotonic()
        ask, news = self.cookie_ask, self.cookie_news
        marks = []
        if ask is not None:
            left = ask["until"] - now
            marks.append(left - math.floor(left) if left > 0 else 0.25)
        if news is not None and now < news["until"]:
            marks.append(news["until"] - now)
        wait = self.cookie_wait - now
        if wait > 0:
            marks.append(wait - math.floor(wait) or 1.0)
        return max(0.05, min(marks)) if marks else COOKIE_STILL

    @staticmethod
    def cookie_story(rec, wall, here=True):
        """How the last cookie was got, in a line: at the top of the page of the one that got it (here), or a few
        words under its name on another's."""
        ago = cookie_ago(wall - rec["t"]) if 0 < rec["t"] <= wall + 300 else ""
        ago = " " + ago if ago else ""
        other, how = rec["from"], rec["how"]
        if cookie_beat(how) and other:
            if not here:
                return f"Beat {other}{ago}"
            return (f"{'You' if rec['you'] else 'Its Bot'} beat {other}{ago}, {COOKIE_THROW[how[0]]} over "
                    f"{COOKIE_THROW[how[1]]}.")
        if how == "left" and other:
            return f"After {other} went quiet{ago}" + ("." if here else "")
        if how == "new":
            return f"The first one{',' + ago if ago else ''}" + ("." if here else "")
        return ""

    def cookie_page(self, s):
        """(sim_game's.) Its page as things are now: the line at its top (another's try waiting for your throw, what's
        just happened, or where the cookie is), your Pietatos' rows, and its buttons."""
        now, wall = time.monotonic(), time.time()
        share = self.setting("share") != "Off"
        heard = self.cookie_heard()
        peers = sorted(self.cookie_on(heard, wall), key=lambda p: (p["name"].lower(), p["id"]))
        older = sorted(h["name"] for h in heard if h["cookie"] is None and h["full"] and wall - h["seen"] <= ON_WITHIN)
        st = self.state["cookie"]
        rec, me = st.get("rec"), st.get("id")
        here = rec is not None and rec["at"] == me
        holder = None if rec is None or here else next((p for p in peers if p["id"] == rec["at"]), None)
        ask, news = self.cookie_ask, self.cookie_news
        wait = max(0, math.ceil(self.cookie_wait - now))
        can = False
        if ask is not None:
            left = max(0, math.ceil(ask["until"] - now))
            head = f"{ask['name']} wants a cookie"
            sub = "Thrown." if ask["throw"] else f"Throw to win another. This one's Bot does in {left} s."
            can = not ask["throw"]
        elif news is not None and now < news["until"]:
            head, sub = news["head"], news["sub"]
            if news["again"] and holder is not None:
                sub += f" Again in {wait} s." if wait else " Throw again."
                can = True
        elif not share:
            head, sub = "Sharing is off", "Settings > Share with other Pietatos turns it on."
        elif rec is None and peers:
            head, sub = "No cookie yet", "One of your Pietatos gets the first in a minute or two."
        elif rec is None:
            head = "It needs two Pietatos"
            sub = ("Update your others, and they play." if older
                   else "They play each other for cookies. No other is on.")
        elif here:
            head, sub = f"{self.own_name()} got a cookie", self.cookie_story(rec, wall)
        elif holder is not None:
            head, can = f"{holder['name']} got a cookie", True
            sub = f"Throw again in {wait} s." if wait else "Beat it at rock paper scissors to win one."
        else:
            head, sub = f"{rec['name']} got a cookie", "It's off. After an hour off, another gets one."
        if self.cookie_trying and ask is None:           # (a try on its way: yours, or its Bot's)
            other = holder["name"] if holder else rec["name"] if rec else "it"
            sub, can = (f"Waiting for {other}…" if self.cookie_trying == "you"
                        else "This one's Bot is playing for one…"), False
        s.head, s.here, s.until = (head, sub), here, self.cookie_until
        hues = dict(ACCENTS)

        def hue(name):
            return accent_for(name) if name in hues else None
        def streak(wins, word=""):                     # (three wins in a row, or more: said under its name)
            if wins < COOKIE_SUSPECT:
                return word
            return f"{word}{', ' if word else ''}{wins} wins in a row"
        rows = []
        if share and (rec is not None or peers or older):
            rows.append((self.own_name(), streak(st.get("wins") or 0, "This one"), hue(self.setting("accent")),
                         st.get("throws") or "", here, True))
            if rec is not None and not here and holder is None:
                rows.append((rec["name"], "Off", None, "", True, False))
            for p in sorted(peers, key=lambda p: p["id"] != (rec or {}).get("at")):   # (the one that got the last,
                has = rec is not None and p["id"] == rec["at"]                        # first: how, under its name)
                word = streak(p["wins"], self.cookie_story(rec, wall, here=False) if has else "")
                rows.append((p["name"], word, hue(p["accent"]), p["throws"], has, True))
            rows += [(name, "Update it to play", None, "", False, True) for name in older]
        s.rows = rows
        s.own_hints = [("◀", "Rock"), ("▲", "Paper"), ("▶", "Scissors")] if can else [("B", "Back")]

    def press_cookie(self, s, name, repeat):
        """Its page's buttons: ◀ rock, ▲ paper, ▶ scissors. With the cookie here and another's try waiting: your
        throw for it. With the cookie on another that's on: your try for it. False: B, L and R (as any of Apps')."""
        if name in ("b", "l", "r"):
            return False
        throw = COOKIE_KEYS.get(name)
        if repeat or throw is None:
            return None
        ask = self.cookie_ask
        if ask is not None:
            if ask["throw"] is None:
                ask["throw"] = throw
                ask["done"].set()
                self.cookie_redraw()
            return None
        st = self.state["cookie"]
        rec = st.get("rec")
        now = time.monotonic()
        if self.setting("share") == "Off" or rec is None:
            return None
        if rec["at"] == st.get("id"):
            self.toast("The others have to beat this one next", 3)
        elif self.cookie_trying:
            pass
        elif now < self.cookie_wait:
            self.toast(f"Again in {math.ceil(self.cookie_wait - now)} s", 2)
        elif self.cookie_try(throw):
            self.cookie_say(f"You threw {COOKIE_THROW[throw]}", "")
        else:
            self.toast(f"{rec['name']} is off", 2)
        self.cookie_redraw()
        return None
