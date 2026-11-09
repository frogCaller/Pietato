"""TV backlight, end to end with a real emulator (Genesis Plus GX, with a pretend screen): a tiny test game of our own
that's blue, and red while player 1 holds B. Told where its colours go (glow ADDRESS:PORT, as media mode tells it), the
emulator sends the edges of each picture over UDP, 30 a second at most: blue; B held, red; let go, blue again. Told
nowhere: nothing more. And an LED grid (glow.py's, its LEDs a plain file) lit by them, over real UDP."""
import os, shutil, socket, sys, time
import numpy as np
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS); sys.path.insert(0, ROOT)
import pietato_all as g
import pitato.glow as G

S = SP + "/t_glow_game"
shutil.rmtree(S, ignore_errors=True)
H = S + "/home/u"
os.makedirs(H + "/Games/genesis")
os.makedirs(S + "/bin")
open(S + "/bin/aplay", "w").write('#!/bin/sh\nexec cat > /dev/null\n')
os.chmod(S + "/bin/aplay", 0o755)
os.environ["PATH"] = S + "/bin:" + os.environ["PATH"]
ROM = H + "/Games/genesis/Pitato Sega Count (World).md"
shutil.copy(SP + "/sega/Pitato Sega Count (World).md", ROM)
CORE = SP + "/sega/cores/genesis_plus_gx_libretro.so"
g.home_dir = lambda: H
W, HH = 640, 480
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


def until(cond, secs=6.0):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.03)
    return cond()


fb = f"{S}/game.fb"
open(fb, "wb").write(bytes(W * HH * 2))
os.environ["PITATO_FB"] = f"{fb}:{W}x{HH}:16"
log = open(f"{S}/game.log", "w")
saved = os.dup(2)
os.dup2(log.fileno(), 2)
try:
    run = g.GameRun({"path": ROM, "title": "Pitato Sega Count", "system": "genesis"})
    run.start(CORE, sound="", volume=0, resume=False, cheevos=False, saves=f"{S}/saves")
finally:
    os.dup2(saved, 2)
    os.close(saved)
    log.close()
check("the game starts", run.wait_started(20))

ear = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
ear.bind(("127.0.0.1", 0))
ear.settimeout(0.2)


def heard(secs=0.5):
    """The packets that came in a while: [packet]."""
    end = time.monotonic() + secs
    out = []
    while time.monotonic() < end:
        try:
            p = G.read_packet(ear.recv(4096))
        except OSError:
            continue
        if p is not None:
            out.append(p)
    return out


def looks(p):
    c = p["colours"].mean(axis=(0, 1))
    return "red" if c[0] > 120 and c[2] < 80 else "blue" if c[2] > 120 and c[0] < 80 else str(c.round().tolist())


check("no grids told of: nothing sent", heard(0.5) == [])
run.send(f"glow 127.0.0.1:{ear.getsockname()[1]}")
pk = heard(1.0)
rate = len(pk)
check(f"told where its colours go: each picture's edges, 30 a second at most ({rate} in a second)", 20 <= rate <= 32
      and all(p["kind"] == "frame" and p["colours"].shape == (8, 8, 3) for p in pk))
check(f"...blue, as the game is ({looks(pk[-1]) if pk else None})", pk and looks(pk[-1]) == "blue")
run.press("b")
check("B held: red", until(lambda: (lambda got: bool(got) and looks(got[-1]) == "red")(heard(0.2)), 4))
run.release("b")
check("...let go: blue again", until(lambda: (lambda got: bool(got) and looks(got[-1]) == "blue")(heard(0.2)), 4))

# an LED grid lit by it, over real UDP
OUT = S + "/spi"
open(OUT, "wb").close()
grid = G.Grid(G.Strip(OUT), lambda ip: G.THIS_ONE if ip.startswith("127.") else None, port=0)
grid.bright, grid.mirror = 1.0, False
run.send(f"glow 127.0.0.1:{grid.port}")


def lit():
    data = open(OUT, "rb").read()
    n = 8 * 8 * 3 * 3
    if len(data) < n + len(G.RESET):
        return None
    grb = np.frombuffer(G.from_spi(data[-(n + len(G.RESET)):-len(G.RESET)]), dtype=np.uint8).reshape(8, 8, 3)
    return grb[..., [1, 0, 2]]


check("an LED grid lit by it: blue", until(lambda: lit() is not None and lit()[0, 3, 2] > 150 and lit()[0, 3, 0] < 60))
run.press("b")
check("...B held: red", until(lambda: lit()[0, 3, 0] > 150 and lit()[0, 3, 2] < 60, 4))
run.release("b")
run.send("glow -")
time.sleep(0.2)
heard(0.1)
check("told nowhere: nothing more sent; the grid goes dark", heard(0.5) == []
      and until(lambda: lit().max() < 10, G.FADE_AFTER + 4 * G.FADE_TAU + 2))
grid.close()
run.quit(3)
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
