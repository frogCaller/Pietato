"""setup.sh where the system starts in a desktop and it isn't a PC: the real setup.sh, start to end, in a mount
namespace (setupspin/full/inner.sh). A board of another make (an Orange Pi Zero 2W: 64-bit ARM, its own system with a
desktop, no config.txt): set up for a screen on HDMI, with no question about a GPi Case (Zero's in its name, but the
cases take a Raspberry Pi's alone) and no config.txt made; and it starts in the terminal now, with Pietato, as a PC
does (its desktop would cover Pietato on the screen): said, with setup.sh's note of it left, so stop.sh puts the
desktop back. And Pietato's in the desktop's menu, to come back from it: an entry that stops the desktop and starts
Pietato, as root through pkexec, which whoever's at the desktop may do (its polkit action); none without a desktop.
Without a desktop (no display manager, though its start-up target's the graphical one, as Debian's is till it's told
otherwise): the target left be, nothing said. An update: the target left as you have it. A Raspberry Pi whose system
has a desktop (Raspberry Pi OS with desktop): as the board."""
import os, re, shutil, subprocess
import xml.etree.ElementTree as ET
from paths import SP, ROOT  # noqa: E402  (this test's folder of work; the Pietato folder)
F = SP + "/setupspin/full"
ROOT = os.environ.get("PITATO_ROOT", ROOT)
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


shutil.rmtree(F + "/repo", ignore_errors=True)
shutil.copytree(ROOT, F + "/repo", symlinks=True, ignore=shutil.ignore_patterns(".git", "__pycache__"))
BOARD, PI3 = SP + "/out/board.model", SP + "/out/pi3.model"   # (as /proc/device-tree/model says each)
open(BOARD, "w").write("OrangePi Zero2W\0")
open(PI3, "w").write("Raspberry Pi 3 Model B Plus Rev 1.3\0")
IN_PIETATO = "starts in Pietato now, not the desktop (System > Desktop starts the desktop)"
AT_THE_END = "starts in Pietato. System > Desktop starts the desktop, and restarting comes back to Pietato."


def run(model, desktop, update=False, after=None):
    """setup.sh on model, its start-up target the graphical one; desktop: with a display manager to start one."""
    for f in ("hold.log", "stub.log"):
        if os.path.exists(f"{F}/{f}"):
            os.remove(f"{F}/{f}")
    env = dict(os.environ, HOLD_LOG=F + "/hold.log", STUB_LOG=F + "/stub.log", PITATO_MODEL_FILE=model, SETUP_GIT="1",
               SETUP_STDIN="/dev/null" if update else SP + "/setupspin/pc_answers.txt",   # (no services; no reboot)
               STUB_DEFAULT_TARGET="graphical.target",
               SETUP_ARGS="--update" if update else "--plain" if model == BOARD else "--no-gpi")
    if model == BOARD:                                 # (no config.txt; a 64-bit ARM system, as imagebin's dpkg says)
        env.update(PC_MODE="1", EXTRA_BIN=f"{SP}/setupspin/pcbin:{SP}/setupspin/imagebin")
    if desktop:
        env["DESKTOP_DM"] = "1"
    if after:
        env["AFTER"] = after
    env.pop("GIT_TERMINAL_PROMPT", None)
    p = subprocess.run(["unshare", "-m", "bash", F + "/inner.sh"], env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=1800)
    out = p.stdout + p.stderr
    stub = open(F + "/stub.log").read().splitlines() if os.path.exists(F + "/stub.log") else []
    return out, stub


def report(out, key):
    m = re.search(rf"^{re.escape(key)}: (.*)$", out, re.M)
    return m.group(1) if m else None


# ---- a board of another make, its system with a desktop ----
out, stub = run(BOARD, desktop=True, after="stop.sh")
open(SP + "/out/setup_board_desktop.out", "w").write(out)
lines = out.splitlines()
check(f"a board of another make: set up for a screen on HDMI (exit {report(out, 'SETUP EXIT')})",
      "Setting up for a screen on HDMI (OrangePi Zero2W). Plug in any USB or Bluetooth game controller." in lines
      and report(out, "SETUP EXIT") == "0")
check("...Zero in its name: no question about a GPi Case all the same (the cases take a Raspberry Pi's alone)",
      "Is this Pi in a RetroFlag" not in out and "GPi Case" not in out)
check(f"...no config.txt made, no GPi Case overlays ({report(out, 'CONFIG')}, {report(out, 'GPI OVERLAY')}), and "
      f"the PlayStation emulator built as for any computer ({report(out, 'PCSX')})",
      report(out, "CONFIG") == "[]" and report(out, "GPI OVERLAY") == "[]"
      and report(out, "PCSX") == "[platform=unix ]")
setup_part = stub[:stub.index("### stop.sh")] if "### stop.sh" in stub else stub
check("its system starts in a desktop: it starts in the terminal now, with Pietato, and says so",
      "systemctl set-default multi-user.target" in setup_part and "==> This Pi " + IN_PIETATO in lines)
check(f"...its note of that left ({report(out, 'VARLIB')}), and at the end how the desktop and Pietato go",
      "was-graphical" in (report(out, "VARLIB") or "").split() and "This Pi " + AT_THE_END in lines)
BACK = "/usr/local/bin/pietato-back"
menu, entry, does = (report(out, k) or "" for k in ("MENU", "MENU ENTRY", "MENU DOES"))
check(f"Pietato in the desktop's menu, to come back from the desktop: its entry runs what stops the desktop and starts "
      f"Pietato (and the console's sign-in, for its terminal), as root ({entry})",
      menu.split() == ["[" + BACK, "/usr/local/share/applications/pietato.desktop",
                       "/usr/share/polkit-1/actions/org.pietato.back.policy", "]"]
      and "|Name=Pietato|" in entry and f"|Exec=pkexec {BACK}|" in entry and "|Type=Application|" in entry
      and '|exec systemd-run --no-block --collect --unit=pietato-back sh -c \\|  "systemctl stop display-manager; '
          'systemctl start getty@tty1; systemctl start pitato"|' in does)
try:
    act = ET.fromstring((report(out, "MENU MAY") or "")[1:-1].replace("|", "\n")).find("action")
    may = (act.get("id"), act.findtext("defaults/allow_active"), act.findtext("defaults/allow_any"),
           act.find("annotate").get("key"), act.findtext("annotate"))
except (ET.ParseError, AttributeError) as ex:
    may = repr(ex)
check(f"...which whoever's at the desktop may do, with no password, and nobody else without one ({may})",
      may == ("org.pietato.back", "yes", "auth_admin", "org.freedesktop.policykit.exec.path", BACK))
stop_part = stub[stub.index("### stop.sh"):] if "### stop.sh" in stub else []
check("...stop.sh after: it starts in its desktop again, and the desktop's started",
      "systemctl set-default graphical.target" in stop_part and "The computer starts in its desktop again." in lines
      and "systemctl --no-block start display-manager" in stop_part)

# ---- the same board, no desktop ----
out, stub = run(BOARD, desktop=False)
open(SP + "/out/setup_board_plain.out", "w").write(out)
check(f"no desktop (no display manager): the start-up target left be, nothing said about one (exit "
      f"{report(out, 'SETUP EXIT')})",
      report(out, "SETUP EXIT") == "0" and not any("set-default" in s for s in stub) and "System > Desktop" not in out
      and "was-graphical" not in (report(out, "VARLIB") or "").split())
check(f"...and nothing in a menu ({report(out, 'MENU')})", report(out, "MENU") == "[]")

# ---- an update, with the desktop ----
out, stub = run(BOARD, desktop=True, update=True)
open(SP + "/out/setup_board_update.out", "w").write(out)
check(f"an update: no questions, and the start-up target left as you have it (exit {report(out, 'SETUP EXIT')})",
      report(out, "SETUP EXIT") == "0" and not any("set-default" in s for s in stub)
      and "[Y/n]" not in out and "[y/N]" not in out)

# ---- a Raspberry Pi whose system has a desktop ----
out, stub = run(PI3, desktop=True)
open(SP + "/out/setup_pi_desktop.out", "w").write(out)
lines = out.splitlines()
check(f"a Raspberry Pi whose system starts in a desktop: in Pietato now there too (exit {report(out, 'SETUP EXIT')})",
      report(out, "SETUP EXIT") == "0" and "systemctl set-default multi-user.target" in stub
      and "==> This Pi " + IN_PIETATO in lines and "This Pi " + AT_THE_END in lines
      and "was-graphical" in (report(out, "VARLIB") or "").split())
print("ALL OK" if all(ok_all) else f"{ok_all.count(False)} FAILED")
