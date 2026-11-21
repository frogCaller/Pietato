"""The bot talks when your music's paused. ("hey potato, play a song", "hey potato, stop the music", then "hey potato,
tell me a joke": it answered on the screen and said nothing.) Asked to stop, the music's paused, and a paused player
keeps the sound card: so the bot said nothing while one was there, unless Pauses music was on. With Pauses music off,
as it comes: music that's paused is put by while it talks and is back after, paused, where it was; "play" plays it on;
"play" or "stop" said before it's back is kept; a timer's up is said over it; its voice is loaded ahead for it. As
before: nothing said over music that's playing (a chime for a timer), over a video, or by itself (a remark); and a
party's music is left alone, paused or not, Pauses music on or off (it's the others' too: the leader's player stopped
ends the party). On party mode's player (your music's on it when an LED board or an OLED wants its beat): the sound
card let go of while it talks, the song back paused and silent, played on from the same place; and a paused party
that ends leaves it paused there too."""
import collections, glob, os, shutil, sys, threading, time, wave
import numpy as np
from paths import SP, TESTS  # noqa: E402  (this test's folder of work; the tests' own)
S = SP + "/t_paused_talk"
shutil.rmtree(S, ignore_errors=True)
HOME = S + "/home/u"
CARD = S + "/card"                                 # (what each pretend sound card was given to play)
for d in (HOME + "/Music", S + "/bin", CARD):
    os.makedirs(d)
open(S + "/bin/aplay", "w").write('''#!/usr/bin/env python3
import os, sys, time
args = sys.argv[1:]
if "-t" not in args:
    sys.exit(0)
rate = int(args[args.index("-r") + 1]) if "-r" in args else 48000
inp, start, played = sys.stdin.buffer, None, 0
with open(os.path.join(os.environ["FAKE_CARD"], f"{time.time():.3f}-{os.getpid()}.raw"), "wb", buffering=0) as out:
    while True:
        data = inp.read(rate // 100 * 4)
        if not data:
            break
        out.write(data)
        start = start or time.monotonic()
        played += len(data) // 4
        wait = start + played / rate - time.monotonic()
        if wait > 0:
            time.sleep(wait)
''')
os.chmod(S + "/bin/aplay", 0o755)
os.environ["PATH"] = S + "/bin:" + os.environ["PATH"]
os.environ["FAKE_CARD"] = CARD
sys.path.insert(0, TESTS)
import pietato_all as g
import pitato.assist as AS
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def wait(cond, secs):
    end = time.monotonic() + secs
    while time.monotonic() < end and not cond():
        time.sleep(0.02)
    return bool(cond())


def card_heard():
    """What the newest pretend sound card's been given so far: how many samples, and the loudest of them."""
    a = np.fromfile(sorted(glob.glob(CARD + "/*.raw"))[-1], dtype="<i2")
    return len(a) // 2, int(np.abs(a.astype(int)).max()) if len(a) else 0


g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.FRIEND_LOG = S + "/friend.json"; g.FRIEND_PICS = S + "/bot-pictures"
g.home_dir = lambda: HOME
for t in g.LIBRARY:
    for key in ("files", "dirs"):
        if key in t:
            t[key] = [x.replace("/home/*", HOME) for x in t[key]]
import gk_static; gk_static.use_home(g, HOME)
for n in ("So What.mp3", "Blue in Green.mp3", "All Blues.mp3"):
    open(f"{HOME}/Music/{n}", "wb").write(b"\0" * 100)
RATE = 8000                                           # (a song that's really one: a minute of a tone, for party mode's
tone = np.sin(np.arange(60 * RATE) * 2 * np.pi * 330 / RATE) * 9000   # player, which decodes it)
with wave.open(f"{HOME}/Music/Tone.wav", "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
    w.writeframes(tone.astype("<i2").tobytes())
spawned = []


class Player:
    def __init__(self, args, target):
        self.args, self.target, self.lines, self.dead = args, target, [], False
        self.stdin, self.said = self, collections.deque(maxlen=50)

    def write(self, s):
        self.lines.append(s.strip())

    def flush(self):
        pass

    def poll(self):
        return 0 if self.dead else None

    def wait(self, timeout=None):
        self.dead = True
        return 0

    def kill(self):
        self.dead = True


def fake_spawn(self, args, target):
    self.started = time.monotonic()
    paused = self.start_paused
    self.muted = self.settling = False
    self.proc = Player(args, target)
    spawned.append((os.path.basename(target), args[args.index("-ss") + 1] if "-ss" in args else None, paused))
    if paused:
        self.muted = self.settling = self.paused = True
        self.settle_play, self.settle_ask, self.pause_said = False, 0.0, None


g.Media.spawn = fake_spawn
spoken, chimes, warmed = [], [], []


class FB:
    w, h = 640, 480
    last = None

    def show(self, img):
        FB.last = img.copy()

    def close(self):
        pass


g.Framebuffer = FB
m = g.Media()
m.enter()


def fake_say(text, vid, device="", volume=100):
    spoken.append(text)
    m.voice.speaking = True
    return True, ""


m.voice.say = fake_say
m.voice.chime = lambda device="", volume=100: chimes.append(1) or True
m.voice.warm = lambda vid: warmed.append(vid)
m.ears.start = lambda *a, **k: None                   # (no microphone here: its state's set as it would be)
BOT = "server = 127.0.0.1:9\nmodel = llama3.2:3b\nvoice = en_US-lessac-medium\nspeak = on\n"


def bot_txt(extra=""):
    open(HOME + "/bot.txt", "w").write(BOT + extra)
    m.friend.load(m.friend_files())


bot_txt()
mi = m.music_tab()
m.load_tab(mi)
songs = [it for it in m.tab_items(mi) if it.get("kind") == "audio"]
BLUE = next(i for i, it in enumerate(songs) if it["title"].startswith("Blue in Green"))
TONE = next(i for i, it in enumerate(songs) if it["title"].startswith("Tone"))
JOKE = "Why did the potato cross the road? It saw a fork up ahead."


def play_music(pos=61):
    m.play(songs, BLUE, start=0, show=False)
    m.pos, m.paused = pos, False


def ears(state):
    m.ears.state = state
    m.ears_tick()


def done_talking():
    m.voice.speaking = False


def answers(text):
    """Its model's answer, as it comes: from its own thread; then media mode's next tick."""
    t = threading.Thread(target=m.bot_replied, args=(text,))
    t.start(); t.join()
    m.tick()


clock = [time.monotonic()]


def hold_ticks():
    """A tick, then the music's hold looked at as time goes by (a pretend clock, always on)."""
    m.tick()
    for _ in range(2):
        clock[0] = max(clock[0], time.monotonic()) + g.HOLD_AFTER + 0.1
        m.music_hold_tick(clock[0])


# ---- what was reported: a joke, a song, "stop the music", a joke -----------------------------------------------------
check("Pauses music: off, as it comes; no LED board or OLED: your music's on mplayer",
      not m.bot_pauses_music() and not m.glow_beats_wanted() and not m.oled_wanted())
answers(JOKE)
check(f"nothing playing: its answer's said, as before ({spoken})", spoken == [JOKE] and m.proc is None)
done_talking()
spoken.clear()
play_music()
p = m.proc
answers("It's half past nine.")
check(f"music playing: its answer isn't said over it, as before ({spoken})", not spoken and m.proc is p and not p.dead
      and not m.bot_can_talk())
check("\"stop the music\": something it does itself", m.bot_heard("stop the music") is None
      and m.friend.log[-1]["text"] == "Paused.")
check(f"...the music's paused, its player still there ({p.lines[-1:]})",
      m.paused and m.proc is p and not p.dead and p.lines[-1] == "pause" and m.music_held is None and not spoken)
warmed.clear()
m.bot_warm()
check(f"paused: nothing in the way of its talking, and its voice is loaded ahead ({warmed})",
      m.bot_can_talk() and warmed == ["en_US-lessac-medium"])
t = threading.Thread(target=m.bot_replied, args=(JOKE,))
t.start(); t.join()
check("a joke, asked for now: its answer, from its own thread, left for media mode's", not spoken and m.proc is p)
m.tick()
check(f"...then said out loud: the paused song put by for it, as the player has the sound card ({spoken}, {p.dead})",
      spoken == [JOKE] and p.dead and m.proc is None and m.music_held and m.music_held["paused"])
hold_ticks()
check("...not back while it talks", m.proc is None and len(spawned) == 1)
done_talking()
hold_ticks()
p2 = m.proc
check(f"...done talking: the song's back, paused, where it was: 61 s in ({spawned[-1]})",
      p2 is not None and spawned[-1] == ("Blue in Green.mp3", "61", True) and m.paused and m.kind == "audio"
      and m.cur is songs[BLUE] and m.music_held is None and len(spawned) == 2)
check("...silent till it plays on (as a player started paused is)", m.muted and "pause" not in p2.lines)
m.bot_heard("play")
check(f"\"play\": the same song plays on, not another ({p2.lines[-2:]})", not m.paused and m.proc is p2 and not m.muted
      and len(spawned) == 2 and p2.lines[-1] == "get_property pause" and "volume" in p2.lines[-2])

# ---- "play", or "stop", said before the song's back ------------------------------------------------------------------
m.settling = False                                     # (it's long since playing)
m.pos = 75
spoken.clear()
m.bot_heard("pause")
answers("It's sunny, and 21 degrees.")
check(f"paused again, and another answer: said ({spoken})", spoken == ["It's sunny, and 21 degrees."]
      and m.proc is None)
done_talking()
ears("listening")                                     # (the wake phrase, as soon as it's done)
hold_ticks()
check("the wake phrase heard before the song's back: it waits", m.proc is None and m.music_held is not None)
m.bot_heard("play")
ears("waiting")
check(f"...\"play\": kept for when it's back, nothing else started ({m.friend.log[-1]['text']!r})",
      m.proc is None and m.music_held is not None and not m.music_held["paused"] and len(spawned) == 2
      and m.friend.log[-1]["text"] == "Playing again.")
hold_ticks()
check(f"...then the same song, playing, from where it was: 75 s in ({spawned[-1]})",
      spawned[-1] == ("Blue in Green.mp3", "75", False) and not m.paused and m.cur is songs[BLUE] and len(spawned) == 3)
p3 = m.proc
m.pos = 90
m.bot_heard("stop the music")
spoken.clear()
answers("Here's a long story. " * 8)
check("paused, and a long answer: being said", m.voice.speaking and m.proc is None and len(spoken) == 1)
out = m.assist_media(AS.parse("stop"))
check(f"\"stop\", typed while it talks: it stops talking, and the song's still to come back ({out!r})",
      out == "" and not m.voice.speaking and m.music_held is not None and m.music_held["paused"])
hold_ticks()
check(f"...back, paused ({spawned[-1]})", spawned[-1] == ("Blue in Green.mp3", "90", True) and m.paused
      and m.music_held is None and p3.dead and len(spawned) == 4)

# ---- a timer's up; two answers running -------------------------------------------------------------------------------
spoken.clear(); chimes.clear()
m.pos = 90                                             # (where mplayer says it is: where it was started from)
m.assist_announce("timer", {"label": "pasta", "until": time.time()})
check(f"a timer's up, the music paused: said, not chimed ({spoken}, {chimes})",
      len(spoken) == 1 and "pasta" in spoken[0] and not chimes and m.proc is None and m.music_held["paused"])
m.say_aloud("And the oven's still on.")
check("...and something else said straight after: the song still put by", len(spoken) == 2 and m.proc is None
      and m.music_held is not None)
done_talking()
hold_ticks()
check(f"...back paused after them both, once, and no further back than it was ({spawned[-1]})",
      spawned[-1] == ("Blue in Green.mp3", "90", True) and m.paused and len(spawned) == 5)
m.stop()

# ---- as before -------------------------------------------------------------------------------------------------------
spoken.clear(); chimes.clear()
play_music(30)
p = m.proc
n = len(spawned)
m.assist_announce("timer", {"label": "pasta", "until": time.time()})
check(f"a timer's up over music that's playing: a chime, the music playing on, as before ({chimes})",
      chimes and not spoken and m.proc is p and not p.dead and not m.paused)
ok, why = m.say_aloud("Hello")
check(f"...and Say it again over it: not now ({why})", not ok and "playing" in why and m.proc is p and not p.dead)
m.cmd("pause"); m.paused = True                        # (A on Now playing)
m.friend.log.append({"who": "friend", "kind": "remark", "t": time.time(), "text": "Nice tune."})
answers("Nice tune.")
check(f"paused, and something it says by itself: not said, the song left where it is ({spoken})",
      not spoken and m.proc is p and not p.dead and m.music_held is None and len(spawned) == n)
m.friend.log.append({"who": "friend", "kind": "chat", "t": time.time(), "text": "Sure."})
m.stop()
film = Player([], "film.mp4")
m.proc, m.kind, m.paused = film, "video", True
ok, why = m.say_aloud("Hi")
check(f"a video, paused: not said over it ({why})", not ok and not spoken and m.proc is film and not film.dead
      and not m.bot_can_talk())
m.proc, m.kind, m.paused = None, None, False

# a party's music: the others' too
play_music(40)
p = m.proc
m.cmd("pause"); m.paused = True
for name, extra in (("off", ""), ("on", "pause_music = on\n")):
    bot_txt(extra)
    for lead in (True, False):
        m.party = {"lead": lead, "token": "k" * 22, "members": {}}
        ok, why = m.say_aloud("Hi")
        check(f"{'leading a party' if lead else 'in a party'}, its music paused, Pauses music {name}: not said, the "
              f"party's player left alone ({why})", not ok and not spoken and m.proc is p and not p.dead
              and m.music_held is None and not m.bot_can_talk())
        m.party = None
bot_txt()
m.stop()

# ---- Pauses music on: as it was, and "stop" said while it talks ------------------------------------------------------
bot_txt("pause_music = on\n")
spoken.clear()
play_music(50)
p = m.proc
ears("listening")
check("Pauses music on: the wake phrase heard, the music paused, as before", m.paused and m.proc is p and m.music_held)
answers("It's half past nine.")
ears("waiting")
check("...its answer said, the music stopped for it", spoken == ["It's half past nine."] and m.proc is None
      and not m.music_held["paused"])
done_talking()
hold_ticks()
check(f"...and on again after, where it was, as before ({spawned[-1]})",
      spawned[-1] == ("Blue in Green.mp3", "47", False) and not m.paused)
m.pos = 55
ears("listening")
answers("Here's a long story. " * 8)
ears("waiting")
out = m.assist_media(AS.parse("stop"))
hold_ticks()
check(f"...\"stop\", typed while it talks: quiet, the song back paused, not gone ({spawned[-1]})",
      out == "" and not m.voice.speaking and spawned[-1] == ("Blue in Green.mp3", "52", True) and m.paused
      and m.music_held is None)
m.stop()
bot_txt()

# ---- party mode's player (an LED board wants the beat): no party -----------------------------------------------------
beat = [True]
m.glow_beats_wanted = lambda: beat[0]
spoken.clear()
n = len(spawned)
m.play(songs, TONE, start=12, show=False)
first = m.proc
check(f"an LED board wants its beat: your music's on party mode's player ({type(first).__name__})",
      type(first).__name__ == "PartyProc" and m.party is None and len(spawned) == n)
check("...playing", wait(lambda: first.player.position() > 12.5, 10) and not m.paused)
m.bot_heard("stop the music")
check("\"stop the music\": paused", wait(lambda: first.player.paused(), 3) and m.paused and m.proc is first)
was = first.player.position()
m.next_query = 0
m.tick()
check(f"...there ({was:.2f} s)", wait(lambda: abs((m.pos or 0) - was) < 0.06, 3) and was > 12.5)
card = first.player.aplay
check("...its player still has the sound card, as a paused one does", card is not None and card.poll() is None)
answers(JOKE)
check(f"a joke: said, the player stopped for it and the sound card let go of ({spoken})",
      spoken == [JOKE] and m.proc is None and first.player.closed and card.poll() is not None
      and m.music_held["paused"])
hold_ticks()
check("...not back while it talks", m.proc is None)
done_talking()
hold_ticks()
second = m.proc
check(f"...done talking: back on party mode's player, paused, where it was "
      f"({getattr(getattr(second, 'player', None), 'pos0', None)})",
      type(second).__name__ == "PartyProc" and second is not first and m.paused and m.cur is songs[TONE]
      and m.kind == "audio" and abs(second.player.pos0 - was) < 0.06 and len(spawned) == n)
time.sleep(g.GLOW_LEAD + 1.2)                          # (past when it would have played)
got, loud = card_heard()
check(f"...paused there, and silent (its sound card given {got} samples, the loudest {loud})",
      second.player.paused() and got > 20000 and loud == 0 and abs(second.player.position() - was) < 0.06
      and second.poll() is None)
m.bot_heard("play")
on = wait(lambda: second.player.position() > was + 0.5, 6)
now_at = second.player.position()
check("\"play\": it plays on", on and not m.paused and not second.player.paused() and m.proc is second)
got, loud = card_heard()
check(f"...from the same place, and heard ({now_at:.2f} s, the loudest sample {loud})",
      now_at < was + 3 and loud > 1000)

# a paused party that's over: still paused, on its own
m.party_toggle(); m.paused = True
check("paused again (A)", wait(lambda: second.player.paused(), 3))
there = second.player.position()
m.party = {"lead": True, "token": "k" * 22, "members": {}}
m.party_end()
third = m.proc
time.sleep(g.GLOW_LEAD + 0.6)
check(f"a paused party that's over: its song still paused, on its own, where it was ({third.player.position():.2f} s)",
      m.party is None and third is not second and type(third).__name__ == "PartyProc" and m.paused
      and third.player.paused() and abs(third.player.position() - there) < 0.05)
m.stop()
beat[0] = False
check("stopped: the last sound card's let go of", third.player.closed and m.proc is None)
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
