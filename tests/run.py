#!/usr/bin/env python3
"""Pietato's tests, one after another, each in a folder of its own: run as root, from anywhere.

    sudo python3 tests/run.py                  the ones that need nothing but this folder (what GitHub runs)
    sudo python3 tests/run.py test_sims ...    just these
    sudo python3 tests/run.py --offline        ...with no network but this machine's own (as GitHub runs them:
                                               the same on any machine, the internet or not)
    sudo python3 tests/run.py --all            every test: the ones that need big files too (emulators built,
                                               game files, voices...), taken from PIETATO_TEST_ASSETS
    python3 tests/run.py --list                which is which

A test passes when it ends with ALL OK, says FAIL nowhere and exits cleanly. Its output is kept in the logs folder
(--logs, or a new one in /tmp); a failing one's last lines are shown too. --shard 2/4 runs every fourth test from the
second, to split the run across machines.

A test that fails is run once more, on its own, and has failed when it fails both times. The tests start real programs
and wait for them, and a busy machine makes one late now and then: that doesn't come twice running, and something
broken fails every time. Which ones needed their second go is said at the end (on GitHub, on the run's page too), with
what each said the first time (its log kept as test_name.first.log, its folder beside the second go's). --once: no
second go."""
import argparse
import fcntl
import glob
import os
import signal
import struct
import subprocess
import sys
import tempfile
import time

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
sys.path.insert(0, TESTS)

# Tests that need more than this folder and what GitHub's machine has: big files (in PIETATO_TEST_ASSETS: game files
# and emulators built, voices...), servers, or the internet
ROMS = "test game files (roms)"
LOCAL = {
    "test_anygame": ROMS, "test_coach": ROMS, "test_gameai": ROMS, "test_turn": ROMS,
    "test_retro": "test game files (roms, art, ps1)",
    "test_cheevos_game": "rcheevos built, and a game with achievements (cheevos_test, ra)",
    "test_dc": "Flycast built, and the Dreamcast test program and discs (setupdc, dctest, dcdat)",
    "test_discs": "PlayStation test discs (ps1, art)",
    "test_pcgames": "PlayStation test discs and emulators (ps1, cores)",
    "test_game_fill": "the N64 emulator built (n64)",
    "test_n64": "the N64 emulator built, and test games (n64, peterlemon)",
    "test_nds": "melonDS built, and a DS test game (setupds, nds)",
    "test_neogeo": "the Neo Geo Pocket emulator, and test games (ng)",
    "test_psp": "PPSSPP built, and PSP test discs (setuppsp, psp, ps1, art)",
    "test_sega": "Genesis test games (sega, ps1), and a web browser (Playwright's Chromium)",
    "test_two": "Genesis test games (sega)",
    "test_netplay_game": "Genesis test games (sega)",
    "test_watch_game": "Genesis test games (sega)",
    "test_glow_game": "Genesis test games (sega)",
    "test_link_cable": "gambatte built (gambatte)",
    "test_here_game": "EmulatorJS and its Game Boy core, as npm has them (ejs), and a web browser (Playwright's Chromium)",
    "test_hooks_rename": "a copy of Pietato from before its rename (gpi-media.before_rename), and Claude Code",
    "test_listen": "Vosk and its model (vosk_whl, vosk_model_npm, listen_t)",
    "test_listen_ui": "Vosk and its model (vosk_whl, vosk_model_npm, listen_t)",
    "test_music_talk": "Vosk and its model, and recordings to hear (vosk_whl, vosk_model_npm, listen_t, wakeexp)",
    "test_voice": "Piper and a voice (piper_dl)",
    "test_probe": "sound files of known lengths (t_lengths)",
    "test_shrink": "videos to shrink (vids, vids_long)",
    "test_shrink_parts": "videos in parts (t_parts_src)",
    "test_tv_stops": "PyAV, and the HDMI sound test's own build (pyav, hdmialsa)",
    "test_computers": "SSH and Samba servers here (openssh-server, samba, sshfs, smbclient)",
    "test_web_computers": "SSH and Samba servers here (openssh-server, samba, sshfs, smbclient)",
    "test_nyancat": "the internet (setup.sh fetches libcaca's aafire.c), with nyancat and libcaca-dev",
    "test_pie_e2e": "a PiE-ink running here (its pretend panel, on port 5062)",
    "test_pihole": "Pi-hole's engine (pihole-FTL) running here, on port 80",
}
TIMEOUT = 900
TIMEOUTS = {"test_setup_pc": 2400, "test_setup_full": 2400, "test_setup_gpi2": 2400, "test_stop_uninstall": 2400,
            "test_setup_debian": 2400, "test_setup_working": 1200, "test_setup_image": 1200, "test_setup_wizard": 2400}
HELPERS = ("_child",)                     # (run by other tests, not on their own)


def all_tests():
    names = []
    for path in sorted(glob.glob(os.path.join(TESTS, "test_*.py")) + glob.glob(os.path.join(TESTS, "test_*.sh"))):
        name = os.path.splitext(os.path.basename(path))[0]
        if not name.endswith(HELPERS):
            names.append((name, path))
    return names


KDGETMODE, KDSETMODE, VT_GETSTATE, VT_ACTIVATE = 0x4B3B, 0x4B3A, 0x5603, 0x5606


def consoles():
    """This machine's consoles: which is in front, and the first twelve's modes (text or graphics). None: none."""
    try:
        fd = os.open("/dev/tty0", os.O_RDWR | os.O_NOCTTY)
        try:
            front = struct.unpack("HHH", fcntl.ioctl(fd, VT_GETSTATE, bytes(6)))[0]
        finally:
            os.close(fd)
    except OSError:
        return None
    modes = {}
    for n in range(1, 13):
        try:
            fd = os.open(f"/dev/tty{n}", os.O_RDWR | os.O_NOCTTY)
            try:
                modes[n] = struct.unpack("i", fcntl.ioctl(fd, KDGETMODE, bytes(4)))[0]
            finally:
                os.close(fd)
        except OSError:
            pass
    return front, modes


def consoles_back(was):
    """The consoles as they were before a test, if it left them otherwise (one in graphics mode in front, say, and
    no other could come in front after it): what was put back."""
    now = consoles()
    if was is None or now is None or now == was:
        return []
    back = []
    for n, mode in was[1].items():
        if now[1].get(n, mode) != mode:
            try:
                fd = os.open(f"/dev/tty{n}", os.O_RDWR | os.O_NOCTTY)
                try:
                    fcntl.ioctl(fd, KDSETMODE, mode)
                finally:
                    os.close(fd)
                back.append(f"console {n}'s {'graphics' if mode else 'text'} mode")
            except OSError:
                pass
    if now[0] != was[0]:
        try:
            fd = os.open("/dev/tty0", os.O_RDWR | os.O_NOCTTY)
            try:
                fcntl.ioctl(fd, VT_ACTIVATE, was[0])
                for _ in range(20):                    # (a moment at most: never waiting for ever)
                    if struct.unpack("HHH", fcntl.ioctl(fd, VT_GETSTATE, bytes(6)))[0] == was[0]:
                        break
                    time.sleep(0.05)
            finally:
                os.close(fd)
            back.append(f"console {was[0]} in front")
        except OSError:
            pass
    return back


def has_evdev(python):
    return subprocess.run([python, "-c", "import evdev"], capture_output=True).returncode == 0


def run_one(name, path, base, logs, python, extra_path):
    import paths                                 # (its own folder isn't made: PIETATO_TEST_WORK is set, below)
    work = paths.make_work(os.path.join(base, name))
    env = dict(os.environ, PIETATO_TEST_WORK=work, PITATO_ROOT=ROOT, PYTHONDONTWRITEBYTECODE="1",
               PYTHONUNBUFFERED="1",           # (all a test prints in its log, ALL OK too, though it ends in os._exit)
               PYTHONPATH=os.pathsep.join(p for p in (extra_path, os.environ.get("PYTHONPATH", "")) if p))
    cmd = ["bash", path] if path.endswith(".sh") else [python, path]
    t0 = time.time()
    log = os.path.join(logs, name + ".log")
    was = consoles()
    with open(log, "w") as out:
        try:
            rc = subprocess.run(cmd, cwd=work, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                                timeout=TIMEOUTS.get(name, TIMEOUT)).returncode
        except subprocess.TimeoutExpired:
            rc = "timeout"
        back = consoles_back(was)
        if back:
            out.write(f"(run.py: this machine's consoles put back as they were: {', '.join(back)})\n")
    text = open(log, errors="replace").read()
    lines = text.splitlines()
    fails = [l for l in lines if l.startswith("FAIL")]
    ok = rc == 0 and not fails and any("ALL OK" in l for l in lines[-5:])
    return ok, rc, fails, lines, time.time() - t0


def left_behind(work):
    """What a test started and left running (each has the test's own folder in its environment), stopped: its second
    go starts as its first did, with no server of the first's still on its port. How many there were."""
    mark, n = f"PIETATO_TEST_WORK={work}".encode(), 0
    for pid in os.listdir("/proc"):
        if not pid.isdigit() or int(pid) == os.getpid():
            continue
        try:
            with open(f"/proc/{pid}/environ", "rb") as f:
                if mark not in f.read().split(b"\0"):
                    continue
            os.kill(int(pid), signal.SIGKILL)
            n += 1
        except OSError:                              # (gone already, or not ours to look at)
            pass
    if n:
        time.sleep(0.5)                              # (and gone, their ports with them)
    return n


def what_said(rc, fails, lines):
    """A failed test's why, in a few words, and what to show of it (its FAIL lines, or how it ended)."""
    why = f"exit {rc}" if rc != 0 else (f"{len(fails)} FAIL" if fails else "no ALL OK")
    said = fails[0][5:] if fails else next((x for x in reversed(lines)
                                            if x.strip() and not x.startswith("(run.py")), "")
    seen = [l[:300] for l in fails[:20]]             # (for GitHub's summary: what failed, or how it ended)
    if rc != 0 or not fails:
        seen += [l[:300] for l in lines[-25:]]
    return why, f"{why}: {said.strip()[:160]}", seen


def github_note(failed, again, total, mins):
    """On GitHub's machine: what failed and why, in a note on the run's own page and in its summary (where they're
    seen without signing in, as the logs aren't); and which passed only on their second go, the same way (a warning:
    the run's still a pass). GitHub's own variables say it's there: tests.yml hands them on (sudo leaves them
    behind)."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return

    def note(kind, title, rows):
        said, left = [], 3500                    # (a note holds only so much: the rest are in the summary)
        for name, why, _ in rows:
            line = f"{name} ({why})"[:240]
            if len(line) > left:
                said.append(f"...and {len(rows) - len(said)} more: in this run's summary")
                break
            said.append(line)
            left -= len(line) + 1
        text = "\n".join(said).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::{kind} title={title}::{text}", flush=True)
    if failed:
        note("error", f"{len(failed)} of {total} tests failed", failed)
    if again:
        note("warning", f"{len(again)} of {total} tests passed on their second go", again)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return

    def plain(text):
        return text.replace("&", "&amp;").replace("<", "&lt;").replace("|", "&#124;").replace("`", "'")
    lines = [f"**{len(failed)} of {total} tests failed** ({mins:.0f} min)", "", "| Test | Why |", "| --- | --- |"] \
        if failed else [f"All {total} tests passed ({mins:.0f} min)"]
    for name, why, _ in failed:
        lines.append(f"| `{name}` | {plain(why)} |")
    if again:
        lines += ["", f"**{len(again)} passed on a second go** (failed the first time, then passed when run again on "
                  "its own: most likely the machine was busy, but worth a look if the same one keeps turning up)", "",
                  "| Test | Why, the first time |", "| --- | --- |"]
        lines += [f"| `{name}` | {plain(why)} |" for name, why, _ in again]
    for rows, when in ((failed, ""), (again, " the first time")):   # (and what each said: its FAIL lines, or its last)
        for name, _, seen in rows:
            lines += ["", f"<details><summary><code>{name}</code>: what it said{when}</summary>", "", "~~~text"]
            lines += [l.replace("~~~", "---") for l in seen] + ["~~~", "", "</details>"]
    try:
        with open(path, "a", encoding="utf-8") as out:
            out.write("\n".join(lines) + "\n")
    except OSError:
        pass


def main():
    ap = argparse.ArgumentParser(description="Pietato's tests")
    ap.add_argument("names", nargs="*", help="tests to run (test_sims...): all of them if none")
    ap.add_argument("--all", action="store_true", help="the ones that need big files too")
    ap.add_argument("--list", action="store_true", help="list the tests, and what the local ones need")
    ap.add_argument("--logs", help="where the logs go (a new folder in /tmp if not given)")
    ap.add_argument("--work", help="where the tests' folders go (a new folder in /tmp if not given)")
    ap.add_argument("--shard", help="I/N: this machine's share of the run")
    ap.add_argument("--python", default=sys.executable, help="the Python to run them with")
    ap.add_argument("--offline", action="store_true", help="no network but this machine's own (needs root)")
    ap.add_argument("--once", action="store_true", help="no second go for a test that fails")
    a = ap.parse_args()
    if a.offline and not os.environ.get("PIETATO_OFFLINE"):
        # a network of its own: this machine (127.0.0.1, and 10.99.0.1 as its address "on the network", where what
        # it broadcasts comes back to it), and nowhere else, at once (not waiting to find out)
        net = ("ip link set lo up && ip addr add 10.99.0.1/32 dev lo && "
               "ip route add 10.255.255.255/32 dev lo src 10.99.0.1 && "
               "ip route add 255.255.255.255/32 dev lo src 10.99.0.1 && ip route add unreachable default")
        args = [sys.executable, os.path.abspath(__file__)] + sys.argv[1:]
        os.environ["PIETATO_OFFLINE"] = "1"
        os.execvp("unshare", ["unshare", "-n", "sh", "-c", net + ' && exec "$@"', "sh"] + args)
    tests = all_tests()
    if a.list:
        for name, _ in tests:
            print(f"{name:28} {('local: needs ' + LOCAL[name]) if name in LOCAL else 'everywhere'}")
        return 0
    if a.names:
        known = dict(tests)
        missing = [n for n in a.names if n not in known]
        if missing:
            print("No such test:", " ".join(missing))
            return 2
        tests = [(n, known[n]) for n in a.names]
    elif not a.all:
        tests = [(n, p) for n, p in tests if n not in LOCAL]
    if a.shard:
        i, n = (int(x) for x in a.shard.split("/"))
        tests = tests[i - 1::n]
    if os.geteuid() != 0:
        print("(Not root: some tests need it, as on a Pi. Run it with sudo.)")
    extra = "" if has_evdev(a.python) else os.path.join(TESTS, "stub")    # (no evdev here: the stand-in)
    base = a.work or tempfile.mkdtemp(prefix="pietato-tests-")
    os.environ["PIETATO_TEST_WORK"] = base       # (for paths.py, here: each test gets a folder of its own)
    logs = a.logs or os.path.join(base, "logs")
    os.makedirs(logs, exist_ok=True)
    print(f"{len(tests)} tests, with {a.python} ({'evdev' if not extra else 'evdev stand-in'}); logs in {logs}",
          flush=True)
    failed, again = [], []                       # (name, why, what it said): failed; passed on its second go
    t_all = time.time()
    for name, path in tests:
        ok, rc, fails, lines, secs = run_one(name, path, base, logs, a.python, extra)
        if ok:
            print(f"ok   {name} ({secs:.0f}s)", flush=True)
            continue
        why, told, seen = what_said(rc, fails, lines)
        if not a.once:                               # once more, on its own, started as the first was
            print(f"again {name} ({why}, {secs:.0f}s: once more, on its own)", flush=True)
            for line in lines[-25:]:
                print("     | " + line[:200], flush=True)
            os.replace(os.path.join(logs, name + ".log"), os.path.join(logs, name + ".first.log"))
            left_behind(os.path.join(base, name))
            try:                                     # (its folder put aside, not emptied: a test may have left
                os.rename(os.path.join(base, name), os.path.join(base, name + ".first"))   # something mounted in it)
            except OSError:
                pass
            first = (name, told, seen)
            ok, rc, fails, lines, secs = run_one(name, path, base, logs, a.python, extra)
            if ok:
                again.append(first)
                print(f"ok   {name} ({secs:.0f}s, on its second go)", flush=True)
                continue
            why, told, seen = what_said(rc, fails, lines)
        failed.append((name, told, seen))
        print(f"FAIL {name} ({why}, {secs:.0f}s)", flush=True)
        for line in lines[-25:]:
            print("     | " + line[:200], flush=True)
    mins = (time.time() - t_all) / 60
    github_note(failed, again, len(tests), mins)
    if again:
        print(f"\n({len(again)} passed on a second go: {' '.join(f[0] for f in again)})")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed ({mins:.0f} min): {' '.join(f[0] for f in failed)}")
        return 1
    print(f"\nALL OK: {len(tests)} tests ({mins:.0f} min)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
