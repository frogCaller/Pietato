"""The tests' own runner (run.py): a test that fails is run once more, on its own, and has failed when it fails both
times. A copy of run.py with four pretend tests beside it: one that passes; one that fails its first go (leaving a
program of its own running and a file in its folder) and passes its second, which finds neither, and the fixtures
there again; one that fails every time; and one that ends badly without a word. What's said of each, how the run ends
(1: something failed), the logs (the first go's kept beside the second's), and GitHub's notes: an error for what
failed, a warning for what needed its second go, both in the run's summary with what each said. Just the two that
pass: 0 and ALL OK, the warning still there. --once: no second go."""
import os, re, shutil, signal, subprocess, sys
from paths import SP, TESTS  # noqa: E402  (this test's folder of work; tests)

T = SP + "/t_runner"
shutil.rmtree(T, ignore_errors=True)
os.makedirs(T + "/tests/fixtures")
for f in ("run.py", "paths.py"):
    shutil.copy(os.path.join(TESTS, f), T + "/tests/")
open(T + "/tests/fixtures/seed.txt", "w").write("seed\n")
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond)); print(("ok   " if cond else "FAIL ") + what, flush=True)


def pretend(name, body):
    open(f"{T}/tests/{name}.py", "w").write(body)


pretend("test_a_fine", 'print("ok   it is")\nprint("ALL OK")\n')
pretend("test_b_late", '''import os, subprocess, sys
mark, here = os.environ["RUNNER_T"] + "/late-went", os.environ["PIETATO_TEST_WORK"]
if not os.path.exists(mark):                       # its first go: late, and it leaves things behind
    open(mark, "w").write(str(subprocess.Popen(["sleep", "300"]).pid))
    open(here + "/left.txt", "w").write("x")
    print("ok   a thing that went well")
    print("FAIL late the first time")
    print("FAILED 1")
    sys.exit(0)
pid = int(open(mark).read())
try:
    gone = open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[0] == "Z"
except OSError:
    gone = True
ok = [gone, not os.path.exists(here + "/left.txt"), os.path.exists(here + "/seed.txt")]
said = ("what its first go left running: stopped", "its folder: a new one", "the fixtures: in it")
for what, cond in zip(said, ok):
    print(("ok   " if cond else "FAIL ") + what)
print("ALL OK" if all(ok) else "FAILED")
''')
pretend("test_c_never", 'print("FAIL never right")\nprint("FAILED 1")\n')
pretend("test_d_silent", 'import sys\nprint("starting")\nsys.exit(3)\n')


def run(tag, *args):
    """run.py on the pretend tests, as GitHub's machine has it: how it ended, what it printed, its summary, its
    logs' folder."""
    if os.path.exists(T + "/late-went"):
        try:
            os.kill(int(open(T + "/late-went").read()), signal.SIGKILL)   # (the last run's, if it's still there)
        except OSError:
            pass
        os.remove(T + "/late-went")
    env = dict(os.environ, RUNNER_T=T, GITHUB_ACTIONS="true", GITHUB_STEP_SUMMARY=f"{T}/summary-{tag}.md")
    r = subprocess.run([sys.executable, T + "/tests/run.py", "--work", f"{T}/work-{tag}", "--logs", f"{T}/logs-{tag}",
                        *args], env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
    try:
        summary = open(f"{T}/summary-{tag}.md", encoding="utf-8").read()
    except OSError:
        summary = ""
    return r.returncode, r.stdout.splitlines(), summary, f"{T}/logs-{tag}"


def has(lines, pattern):
    return any(re.fullmatch(pattern, l) for l in lines)


def where(lines, pattern):
    return next((i for i, l in enumerate(lines) if re.fullmatch(pattern, l)), -1)


# ---- all four: two fail both times -----------------------------------------------------------------------------------
rc, out, summary, logs = run("all")
print("\n".join("     | " + l for l in out))
check("a test that passes: said once", has(out, r"ok   test_a_fine \(\d+s\)")
      and not any("test_a_fine" in l for l in out if not l.startswith("ok ")))
a, b = where(out, r"again test_b_late \(2 FAIL, \d+s: once more, on its own\)"), where(
    out, r"ok   test_b_late \(\d+s, on its second go\)")
check("one that fails its first go and passes its second: said to be run once more, what it said shown, then ok",
      0 <= a < b and "     | FAIL late the first time" in out[a:b] and not has(out, r"FAIL test_b_late.*"))
check("...its second go started as its first was: nothing left running, a folder of its own again, the fixtures in it",
      "ALL OK" in open(logs + "/test_b_late.log").read() and "FAIL" not in open(logs + "/test_b_late.log").read())
check("...the first go's log kept beside it, and its folder as it left it",
      "FAIL late the first time" in open(logs + "/test_b_late.first.log").read()
      and os.path.exists(T + "/work-all/test_b_late.first/left.txt")
      and not os.path.exists(T + "/work-all/test_b_late/left.txt"))
a, b = where(out, r"again test_c_never \(2 FAIL, \d+s: once more, on its own\)"), where(
    out, r"FAIL test_c_never \(2 FAIL, \d+s\)")
check("one that fails every time: run once more, then failed", 0 <= a < b
      and os.path.exists(logs + "/test_c_never.first.log") and os.path.exists(logs + "/test_c_never.log"))
check("one that ends badly without a word: the same, with how it ended",
      0 <= where(out, r"again test_d_silent \(exit 3, \d+s: once more, on its own\)")
      < where(out, r"FAIL test_d_silent \(exit 3, \d+s\)"))
check(f"how the run ends: 1, what failed, and what needed its second go ({rc}, {out[-3:]})", rc == 1
      and has(out, r"2 of 4 failed \(\d+ min\): test_c_never test_d_silent")
      and "(1 passed on a second go: test_b_late)" in out and not has(out, r"ALL OK.*"))
check("GitHub's notes: an error for what failed, with why", "::error title=2 of 4 tests failed::"
      "test_c_never (2 FAIL: never right)%0Atest_d_silent (exit 3: starting)" in out)
check("...a warning for what needed its second go, with why",
      "::warning title=1 of 4 tests passed on their second go::test_b_late (2 FAIL: late the first time)" in out)
check("the run's summary: what failed, and what each said",
      "**2 of 4 tests failed**" in summary and "| `test_c_never` | 2 FAIL: never right |" in summary
      and "| `test_d_silent` | exit 3: starting |" in summary
      and "<code>test_c_never</code>: what it said</summary>" in summary)
check("...and what passed on a second go, with what it said the first time",
      "**1 passed on a second go**" in summary and "| `test_b_late` | 2 FAIL: late the first time |" in summary
      and "<code>test_b_late</code>: what it said the first time</summary>" in summary
      and summary.index("**1 passed on a second go**") > summary.index("| `test_d_silent`"))

# ---- the two that pass: a pass, the warning still there --------------------------------------------------------------
rc, out, summary, logs = run("pass", "test_a_fine", "test_b_late")
check(f"just the two that pass: 0 and ALL OK, the second go said ({rc}, {out[-3:]})", rc == 0
      and has(out, r"ALL OK: 2 tests \(\d+ min\)") and "(1 passed on a second go: test_b_late)" in out
      and has(out, r"ok   test_b_late \(\d+s, on its second go\)"))
check("...GitHub's notes: no error, the warning", not any(l.startswith("::error") for l in out)
      and "::warning title=1 of 2 tests passed on their second go::test_b_late (2 FAIL: late the first time)"
      in out)
check("...its summary: all passed, and which on a second go", summary.startswith("All 2 tests passed")
      and "**1 passed on a second go**" in summary and "tests failed" not in summary)
rc, out, summary, logs = run("fine", "test_a_fine")
check(f"one that passes, on its own: nothing about second goes ({out[-1:]})", rc == 0
      and not any("second go" in l or l.startswith("::") for l in out)
      and summary.strip().startswith("All 1 tests passed") and "second go" not in summary)

# ---- --once: no second go --------------------------------------------------------------------------------------------
rc, out, summary, logs = run("once", "--once", "test_a_fine", "test_b_late")
check(f"--once: no second go, it has failed ({rc}, {out[-1:]})", rc == 1
      and has(out, r"FAIL test_b_late \(2 FAIL, \d+s\)") and not any(l.startswith("again") for l in out)
      and has(out, r"1 of 2 failed \(\d+ min\): test_b_late")
      and not os.path.exists(logs + "/test_b_late.first.log"))
try:
    os.kill(int(open(T + "/late-went").read()), signal.SIGKILL)      # (what that one left running: this test's
except OSError:                                                      #  to stop)
    pass
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
