"""Party mode keeping itself together (screens/party.py), with three Pietatos on this machine: the Den, the Kitchen and
the TV, each a process of its own (peer_pietato.py) at an address of its own, with a clock of its own (as Pis are, up
for different whiles) and a pretend sound card that takes one player at a time, as HDMI's does (party_kit.py). The Den
starts a party. The Kitchen, whose clock is 5,000 seconds from the Den's and whose first look at the Den's clock takes
a while, plays the first song all the same, and in step once it's looked. That song ends: the next starts by itself
and is heard on both (the one that's over has let go of each sound card). A song the Kitchen never hears of (its web
page deaf a while): the Den doesn't drop it, finds it behind at its next look, and tells it again, from where the song
is by then. The TV, turned on in the middle of the party: asked in, without anyone doing anything, and playing from
where the song is. The party paused, the TV turned off and on again: back in it, paused, and playing on with the
others. The Kitchen leaves (HOME's menu), its word to the Den lost: it isn't brought back. Then the Kitchen starts a
party of its own while the Den's is still going: the Den and the TV switch to it (the Den's own is over). And when
that one's over, the Den (Settings > Random song at start-up on) has its own song back, the one the party stopped:
not the party's. The party's songs come with their covers from the one that leads it."""
import json, os, shutil, socket, subprocess, sys, time
from paths import SP, TESTS  # noqa: E402  (this test's folder of work; tests)
sys.path.insert(0, TESTS)
from party_kit import apart, heard, ramp, sound_card

S = SP + "/t_party_joins"
shutil.rmtree(S, ignore_errors=True)
os.makedirs(S)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


sound_card(S + "/bin")


class Pie:
    """One of them: its process, and the test's word with it."""

    def __init__(self, name, addr, ahead, slow=None):
        self.name, self.home = name, f"{S}/{name.lower()}"
        self.log, self.sound = f"{S}/{name.lower()}.log", f"{S}/{name.lower()}-sound.log"
        for d in ("Music", "Videos", "Pictures", "Documents", "Games/Saves"):
            os.makedirs(f"{self.home}/{d}")
        with socket.socket() as s:                     # (a port that's free there: its web page's, each time it's on)
            s.bind((addr, 0))
            port = s.getsockname()[1]
        self.url = f"http://{addr}:{port}"
        self.env = dict(os.environ, PITATO_OWN_MUSIC="1", PITATO_ADDR=addr, PITATO_WEB_PORT=str(port),
                        PITATO_CLOCK_AHEAD=str(ahead), PITATO_PARTY_QUICK="2.5", FAKE_APLAY_LOG=self.sound,
                        FAKE_APLAY_ONE=f"{S}/{name.lower()}-card")   # (its sound card: one player at a time)
        if slow:
            self.env["PITATO_PING_SLOW"] = str(slow)
        self.proc = None

    def start(self, others):
        self.proc = subprocess.Popen([sys.executable, TESTS + "/peer_pietato.py", self.home, self.log, self.name,
                                      others[0].url, others[0].name], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=open(f"{S}/{self.name.lower()}.err", "a"), text=True, bufsize=1,
                                     env=self.env)
        line = self.proc.stdout.readline().split()
        if line[:1] != ["READY"] or line[1] != self.url:
            print(f"FAIL {self.name}'s Pietato didn't start", line)
            sys.exit(1)
        for o in others[1:]:
            self.do(f"peer {o.url} {o.name} too")
        self.do("set volume 100")                      # (as loud as it goes: each sample says where in the song it is)

    def do(self, text):
        self.proc.stdin.write(text + "\n")
        self.proc.stdin.flush()
        return self.proc.stdout.readline().strip()

    def state(self):
        return json.loads(self.do("state") or "{}")

    def said(self, key):
        """What it's logged under key, in order."""
        rows = [json.loads(x) for x in open(self.log).read().splitlines() if x.strip()]
        return [r[key] for r in rows if key in r]

    def menu(self, pick):
        """HOME on its Now playing, and a row of its menu picked."""
        self.do("mediahome")
        rows = self.state().get("media_menu") or []
        for _ in range(rows.index(pick) if pick in rows else 0):
            self.do("press down")
        self.do("press a")
        return rows

    def off(self):
        self.proc.kill()
        self.proc.wait()


def wait(secs, until):
    """until(), asked every so often for up to secs seconds: what it said last."""
    end = time.time() + secs
    while True:
        got = until()
        if got or time.time() > end:
            return got
        time.sleep(0.25)


def brief(st):
    return {k: st.get(k) for k in ("playing", "cur", "paused", "party")}


def on(pie, title, leader):
    """It's on that song, in that one's party: its state, or None."""
    st = pie.state()
    return st if (st.get("party") or {}).get("with") == leader and st.get("cur") == title \
        and st.get("playing") == "PartyProc" else None


def step(a, b, since, after):
    """How far apart two of them heard the same sound, from after seconds past since (ms: the mean, the most)."""
    got = apart(a.sound, b.sound, since, after=after)
    return (round(got[0], 1), round(got[1], 1)) if got[0] is not None else got


den, kitchen = Pie("Den", "127.0.0.2", 0), Pie("Kitchen", "127.0.0.3", 5000, slow=2.5)
tv = Pie("TV", "127.0.0.4", 200000)
SONGS = [f"{den.home}/Music/{name}.wav" for name in ("One", "Two", "Three")]
for k, path in enumerate(SONGS):
    ramp(path, 100 if k else 15, first=1000 * k)       # (each song's places its own: One 0 on, Two 1000 on...)
K1 = f"{kitchen.home}/Music/K1.wav"
ramp(K1, 100, first=5000)
from PIL import Image  # noqa: E402
Image.new("RGB", (400, 400), (40, 160, 90)).save(f"{den.home}/Music/cover.jpg")   # (the Den's songs' cover)
den.start([kitchen])
kitchen.start([den])
try:
    # ---- the first song, on one whose clock isn't found yet ---------------------------------------------------------
    den.do("set start_song On")                        # (Settings > Random song at start-up: its music comes back)
    den.do("play " + "|".join(SONGS))
    began = time.monotonic()
    rows = den.menu("party")
    st, theirs = den.state(), kitchen.state()
    check(f"the Den starts a party ({rows}): the Kitchen's in it ({brief(st)})", "party" in rows
          and (st.get("party") or {}).get("members") == ["Kitchen"] and st["playing"] == "PartyProc")
    check(f"...and on the song at once, its clock 5,000 seconds from the Den's and not looked at yet: set roughly, "
          f"by what the Den said ({brief(theirs)})", theirs.get("playing") == "PartyProc" and theirs.get("cur") == "One"
          and theirs["party"].get("rough") is True and abs(theirs["party"]["offset"] + 5000) < 1.0)
    theirs = wait(10, lambda: (lambda s: s if (s.get("party") or {}).get("rough") is False else None)(kitchen.state()))
    check(f"...then looked at: found ({theirs and theirs['party']['offset']})", bool(theirs)
          and abs(theirs["party"]["offset"] + 5000) < 0.01)
    time.sleep(max(0.0, began + 11.0 - time.monotonic()))
    got = step(den, kitchen, began, 8.0)
    check(f"...and from then on in step with the Den ({got} ms apart)", got[0] is not None and abs(got[0]) < 10)
    theirs = kitchen.state().get("cover")
    pic = Image.open(theirs).convert("RGB") if theirs and os.path.isfile(theirs) else None
    check(f"...with the song's cover from the Den, for its Now playing ({pic and pic.size}, "
          f"{pic and pic.getpixel((200, 200))})", pic is not None and pic.size == (400, 400)
          and all(abs(a - b) < 12 for a, b in zip(pic.getpixel((200, 200)), (40, 160, 90))))

    # ---- the song ends: the next, by itself --------------------------------------------------------------------------
    theirs = wait(20, lambda: on(kitchen, "Two", "Den"))
    since = time.monotonic()
    time.sleep(6.0)
    mine = [w for t, w, _ in heard(den.sound) if w is not None and t > since + 3.0]
    there = [w for t, w, _ in heard(kitchen.sound) if w is not None and t > since + 3.0]
    got = step(den, kitchen, since, 3.0)
    check(f"the song ends: the next starts by itself ({den.state()['cur']!r}), and it's heard on the Den "
          f"({len(mine)} bits of it, from {mine[:1]}) and the Kitchen ({len(there)}): each one's sound card takes one "
          f"player at a time, and the song that's over has let go of it", bool(theirs) and len(mine) > 200
          and len(there) > 200 and min(mine + there) >= 1000)
    check(f"...in step ({got} ms apart)", got[0] is not None and abs(got[0]) < 10)

    # ---- a song one of them never hears of ---------------------------------------------------------------------------
    kitchen.do("deaf 6")
    den.do("press r")
    time.sleep(1.0)
    st, theirs = den.state(), kitchen.state()
    check(f"the next song, the Kitchen's web page deaf to it: the Den's on it ({st['cur']!r}), the Kitchen isn't "
          f"({theirs['cur']!r})", st["cur"] == "Three" and theirs["cur"] == "Two")
    theirs = wait(25, lambda: on(kitchen, "Three", "Den"))
    since = time.monotonic()
    st = den.state()
    check(f"...the Den doesn't drop it ({st['party']['members']}): at its next look it finds it behind, and tells it "
          f"again ({theirs and brief(theirs)})", bool(theirs) and st["party"]["members"] == ["Kitchen"]
          and theirs["party"]["n"] == st["party"]["n"])
    time.sleep(6.0)
    got = step(den, kitchen, since, 3.0)
    there = [w for t, w, _ in heard(kitchen.sound) if w is not None and t > since + 3.0]
    check(f"...from where the song is by then, in step ({got} ms apart; the Kitchen at {there[:1]})",
          got[0] is not None and abs(got[0]) < 10 and bool(there) and there[0] > 2005)

    # ---- one turned on in the middle of the party --------------------------------------------------------------------
    tv.start([den, kitchen])
    for other in (den, kitchen):
        other.do(f"peer {tv.url} TV too")
    theirs = wait(25, lambda: on(tv, "Three", "Den"))
    since = time.monotonic()
    st = den.state()
    check(f"the TV, turned on in the middle of it: asked in, and on the party's song ({theirs and brief(theirs)}; the "
          f"Den: {st['party']['members']}, {den.said('toast')[-1:]})", bool(theirs)
          and st["party"]["members"] == ["Kitchen", "TV"] and "TV joined the party" in den.said("toast"))
    time.sleep(6.0)
    got, both = step(den, tv, since, 3.0), step(kitchen, tv, since, 3.0)
    check(f"...from where it is, in step with the Den ({got} ms apart) and the Kitchen ({both})",
          None not in (got[0], both[0]) and abs(got[0]) < 10 and abs(both[0]) < 10)

    # ---- paused; one turned off and on again -------------------------------------------------------------------------
    den.do("press a")
    time.sleep(1.5)
    check("A on the Den: all three paused", all(p.state()["paused"] for p in (den, kitchen, tv)))
    tv.off()
    time.sleep(1.0)
    tv.start([den, kitchen])
    theirs = wait(30, lambda: on(tv, "Three", "Den"))
    check(f"the TV turned off and on again: back in the party, by itself, and paused as the party is "
          f"({theirs and brief(theirs)})", bool(theirs) and theirs["paused"] is True)
    den.do("press a")
    since = time.monotonic()
    time.sleep(5.0)
    got, both = step(den, tv, since, 2.0), step(den, kitchen, since, 2.0)
    check(f"A on the Den: all three play on ({[p.state()['paused'] for p in (den, kitchen, tv)]}), in step (the TV "
          f"{got} ms from the Den, the Kitchen {both})", not any(p.state()["paused"] for p in (den, kitchen, tv))
          and None not in (got[0], both[0]) and abs(got[0]) < 10 and abs(both[0]) < 10)

    # ---- one that leaves isn't brought back --------------------------------------------------------------------------
    den.do("deaf 3")                                   # (its word that it's left never gets to the Den)
    kitchen.do("press start")                          # (its Now playing, from its home screen)
    rows = kitchen.menu("party")
    theirs = kitchen.state()
    check(f"the Kitchen leaves (HOME's menu: {rows}): its music stops ({brief(theirs)})", rows == ["back", "party"]
          and theirs["party"] is None and theirs["playing"] is None)
    time.sleep(12.0)
    st, theirs = den.state(), kitchen.state()
    check(f"...and though the Den never heard that it left, it isn't brought back (the Kitchen: {theirs['party']}; "
          f"the Den's party: {st['party']['members']})", theirs["party"] is None and theirs["playing"] is None
          and st["party"]["members"] == ["TV"])

    # ---- a new party, started on another of them: the rest switch to it ----------------------------------------------
    kitchen.do("play " + K1)
    rows = kitchen.menu("party")
    since = time.monotonic()
    mine, st, theirs = kitchen.state(), den.state(), tv.state()
    check(f"the Kitchen starts a party of its own, the Den's still going: both switch to it ({mine['party']}, "
          f"{kitchen.said('toast')[-1:]})", (mine.get("party") or {}).get("lead") is True
          and mine["party"]["members"] == ["Den", "TV"] and kitchen.said("toast")[-1] == "Party mode with Den and TV")
    st, theirs = wait(10, lambda: on(den, "K1", "Kitchen")), wait(10, lambda: on(tv, "K1", "Kitchen"))
    check(f"...the Den's own party is over: it's in the Kitchen's, on its song ({st and brief(st)}), and so is the TV "
          f"({theirs and brief(theirs)})", bool(st) and bool(theirs) and st["party"]["lead"] is False)
    time.sleep(max(0.0, since + 8.0 - time.monotonic()))
    got, both = step(kitchen, den, since, 5.0), step(kitchen, tv, since, 5.0)
    check(f"...all three in step (the Den {got} ms from the Kitchen, the TV {both})", None not in (got[0], both[0])
          and abs(got[0]) < 10 and abs(both[0]) < 10)

    # ---- the party over: what it stopped comes back, not its own songs -----------------------------------------------
    rows = kitchen.menu("party")
    time.sleep(5.0)
    st, theirs = den.state(), tv.state()
    played = den.said("play")
    check(f"the Kitchen ends it: the TV stops ({brief(theirs)}), and the Den, whose own music the party stopped, has "
          f"it back: its own song, not the party's ({brief(st)}, {played[-1:]})", theirs["party"] is None
          and theirs["playing"] is None and st["party"] is None and st["playing"] == "Proc" and st["cur"] == "Three"
          and played[-1] == SONGS[2])
finally:
    for p in (den, kitchen, tv):
        if p.proc is not None and p.proc.poll() is None:
            try:
                p.do("quit")
            except OSError:
                pass
            p.off()
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
