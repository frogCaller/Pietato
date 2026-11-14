#!/usr/bin/env python3
"""
agent_link.py - connects an agent on your computer (OpenClaw, Hermes) and your Pietato, both ways.

Run it on the computer your agent runs on, with your Pi's name or address:
    python3 agent_link.py gpi.local
That remembers your Pietato (in ~/.pietato) and gives your agent a skill for it, in ~/.openclaw/skills
and ~/.hermes/skills (whichever you have). With the skill your agent can see the Pietato's screen, press
its buttons, open its apps and play things on it: ask it to.

To talk to your agent from the Pietato, keep this running too:
    python3 agent_link.py listen
A on the Bot at work types a prompt. Your agent gets it through its own API on this computer, the Bot
acts out that it's working, and what it answers shows on the Pietato. Its API has to be on:
    OpenClaw   gateway.http.endpoints.chatCompletions.enabled: true   in ~/.openclaw/openclaw.json
    Hermes     API_SERVER_ENABLED=true and API_SERVER_KEY=<16 characters or more> in ~/.hermes/.env,
               then: hermes gateway
Anything else that speaks OpenAI's chat API works with --url, --key and --model.

    --password PW   your Pi's web page password, if it has one (kept in ~/.pietato/link.json)
    --name NAME     what to call this Pietato here, if you have several (its own name otherwise)
    --skills DIR    put the skill in this folder too (an agent that keeps its skills somewhere else)
    --new           with listen: a new conversation (your agent carries on the last one otherwise)
    --remove        forget your Pietatos and take the skill out again

What the skill runs (you can too):
    python3 agent_link.py status | screen [FILE] | press BUTTON... | open APP | home | files FOLDER [PATH]
                          | play FOLDER PATH | radio WORDS [--play N] | player DO | type TEXT [--enter]
                          | pose NAME | list            (--on NAME: which Pietato, with several)

The Pi hands this script out:  curl -O http://<your Pi's name>.local:5432/agent_link.py
"""
import argparse
import base64
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

PORT = 5432                            # the Pi's web page
KEPT = os.path.join("~", ".pietato")   # where your Pietatos are remembered, and this script's own copy
SKILL = "pietato"                      # the skill's name, and its folder's
SKILL_HOMES = (("OpenClaw", os.path.join("~", ".openclaw"), "skills"),     # where each agent keeps your skills
               ("Hermes", os.path.join("~", ".hermes"), "skills"))
BUTTONS = ("up", "down", "left", "right", "a", "b", "x", "y", "l", "r", "select", "start", "home", "l2", "r2")
FOLDERS = ("music", "videos", "pictures", "documents", "games")
PLAYER = ("pause", "stop", "next", "prev", "back", "forward", "louder", "quieter", "screen")
POSES = ("rest", "typing", "reading", "thinking", "talking", "done", "hello", "attention", "error", "shrug",
         "wake", "sleep")
COMMANDS = ("listen", "status", "screen", "press", "open", "home", "files", "play", "radio", "player", "type",
            "pose", "list")
WAIT = 20                              # seconds each request for prompts waits on the Pi for one
REPLY_MAX = 6000                       # characters of your agent's answer the Pi is sent (the rest: …)
QUIET_MOST = 900                       # seconds your agent can go without a word, mid-answer, before it's given up on
HISTORY = 12                           # turns kept for an API that doesn't keep the conversation itself
READS = ("read", "search", "browse", "browser", "web", "fetch", "list", "view", "find", "grep", "glob", "vision",
         "snapshot", "look", "session")   # a tool with one of these in its name: the Bot reads (else it types)
DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # (the Pi, and your agent, are on your network)


class Said(Exception):
    """Something to tell you, and stop."""


# ---- your Pietatos, as remembered here -----------------------------------------------------------------------------
def kept(*more):
    return os.path.join(os.path.expanduser(KEPT), *more)


def base_url(where):
    """gpi.local -> http://gpi.local:5432"""
    where = where.strip().rstrip("/")
    if "://" not in where:
        where = "http://" + where
    scheme, rest = where.split("://", 1)
    host = rest.split("/", 1)[0]
    if ":" not in host.rsplit("]", 1)[-1]:          # (no port given; an IPv6 address is in brackets)
        host += f":{PORT}"
    return f"{scheme}://{host}"


def load():
    try:
        with open(kept("link.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    pis = data.get("pietatos") if isinstance(data, dict) else None
    pis = {str(k): v for k, v in (pis or {}).items() if isinstance(v, dict) and isinstance(v.get("url"), str)}
    first = data.get("first") if isinstance(data, dict) else None
    talks = data.get("talks") if isinstance(data, dict) else None
    talks = {k: n for k, n in talks.items() if k in pis and type(n) is int and n > 0} if isinstance(talks, dict) else {}
    return {"pietatos": pis, "first": first if first in pis else next(iter(pis), None), "talks": talks}


def save(data):
    os.makedirs(kept(), exist_ok=True)
    path = kept("link.json")
    tmp = path + ".part"
    # (yours only to read: a web page's password may be in it)
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in data.items() if v or k != "talks"}, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def which_pi(data, name):
    """The Pietato a command is for: (its name, its address, its password)."""
    pis = data["pietatos"]
    if not pis:
        raise Said("No Pietato is set up yet. Run:  python3 agent_link.py <your Pi's name or address>")
    if name is None:
        name = data["first"]
    elif name not in pis:
        close = [k for k in pis if k.lower() == name.lower()]
        if not close:
            raise Said(f"There's no Pietato called {name} here. There's: " + ", ".join(pis))
        name = close[0]
    return name, pis[name]["url"], str(pis[name].get("password") or "")


# ---- asking a Pietato (its web page's own requests) ----------------------------------------------------------------
def ask(url, password, path, body=None, coder=False, timeout=30, raw=False):
    """A request to the Pietato's web page: its answer (JSON as a dict; raw: the bytes and their type). A Said
    with why not, when it doesn't answer or says no."""
    headers = {"X-Pitato-Page": "1"}
    data = None
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if password:                                    # (the Bot at work takes it as a token, the rest as a login)
        headers["Authorization"] = "Bearer " + password if coder else \
            "Basic " + base64.b64encode(b"agent:" + password.encode()).decode()
    req = urllib.request.Request(url + path, data=data, headers=headers, method="POST" if data is not None else "GET")
    try:
        with DIRECT.open(req, timeout=timeout) as resp:
            got, kind = resp.read(), resp.headers.get("Content-Type") or ""
    except urllib.error.HTTPError as ex:
        try:
            why = json.loads(ex.read())
            why = why.get("error") if isinstance(why, dict) else None
        except (ValueError, OSError):
            why = None                              # (a page of its own, not words for you)
        if ex.code == 401:
            why = "Its web page has a password. Set it up again with --password and the password"
        why = why or {403: "That isn't allowed", 404: "That isn't there", 413: "That's too much to send"}.get(ex.code)
        raise Said(f"The Pietato said no ({ex.code}): {why or 'no reason given'}")
    except (OSError, ValueError) as ex:
        raise Said(f"The Pietato at {url} isn't answering ({getattr(ex, 'reason', ex)}). Is it on?")
    if raw:
        return got, kind
    try:
        out = json.loads(got or b"{}")
    except ValueError:
        raise Said("The Pietato's answer made no sense")
    if isinstance(out, dict) and out.get("error"):
        raise Said(f"The Pietato said: {out['error']}")
    return out


# ---- the skill, and setting up -------------------------------------------------------------------------------------
def command_line():
    """How the skill runs this script: the Python that's running it now, and its kept copy."""
    return " ".join(('"%s"' % p if " " in p else p) for p in (sys.executable or "python3", kept("agent_link.py")))


# (what it's for, on one line: no colon in it, for the plainest reader of a SKILL.md's head; what matters first, as
# Hermes lists only the first 57 characters of it)
SKILL_SAYS = ("Play music, videos and radio on the user's Pietato, open its apps, see its screen and press its "
              "buttons. A Pietato is a Raspberry Pi handheld and media player.")
SKILL_BODY = """
# Pietato

The user has {has}. A Pietato is a Raspberry Pi in a handheld case (or on a TV) that plays the user's
music, videos, radio and games. This skill works it over their network, the way its own web remote does.

## When to use

The user asks to play, pause or stop something on {whose} Pietato, to change its volume, to open one of its
apps, or asks what it's showing or playing.

## Commands

Run them in the terminal. Each prints what happened, or why it couldn't.

    {cmd} status                what's on its screen, what's playing, the volume
    {cmd} screen [FILE.png]     saves a picture of its screen, and says where
    {cmd} press BUTTON...       presses buttons in order: up down left right a b x y l r start select
    {cmd} open APP              opens an app by its name on the home screen (Music, Videos, Radio, Games...)
    {cmd} home                  goes back to its home screen
    {cmd} files FOLDER [PATH]   lists the user's files: FOLDER is music, videos, pictures, documents or games
    {cmd} play FOLDER PATH      plays (or opens) one of those files on its screen
    {cmd} radio WORDS           finds radio stations by name; --play 1 plays the first found
    {cmd} player DO             pause, stop, next, prev, back, forward, louder or quieter
    {cmd} type TEXT             puts TEXT in the box that's open on its screen; --enter finishes it
    {cmd} pose NAME             what its Bot acts out at its desk: thinking, typing, reading, done, hello
{several}
## How to work it

1. Run `status` first. To see more, run `screen` and look at the picture it saves.
2. Use `open`, `play`, `radio` and `player` when they do the job. Press buttons for the rest.
3. A picks, B goes back, up and down move through a list, L and R change tab.
4. After a few presses, run `status` or `screen` again before pressing more.

## Don't

- Don't press home: on a handheld it leaves the menus for the terminal.
- Don't shut it down, restart it, update it or change its settings unless the user asked for exactly that.
- Don't delete anything on it.
"""


def skill_text(names):
    """The skill, as OpenClaw and Hermes both read one (a SKILL.md): what a Pietato is, and the commands for it,
    spelt out with where this script is kept here."""
    cmd, several = command_line(), len(names) > 1
    head = "\n".join(("---", f"name: {SKILL}", f"description: {SKILL_SAYS}", "version: 1.0.0",
                      'metadata: {"hermes": {"tags": ["pietato", "media", "raspberry-pi"], "category": "devices"}}',
                      "---"))
    more = f"    {cmd} list                  the Pietatos there are: add --on NAME to a command for one of them\n" \
        if several else ""
    return head + "\n" + SKILL_BODY.format(cmd=cmd, has="Pietatos: " + ", ".join(names) if several else "a Pietato",
                                           whose="a" if several else "their", several=more)


def skill_dirs(extra=()):
    """Where the skill goes: (whose, its folder) for each agent that's here, and any folder asked for."""
    out = []
    for who, home, sub in SKILL_HOMES:
        if os.path.isdir(os.path.expanduser(home)):
            out.append((who, os.path.join(os.path.expanduser(home), sub, SKILL)))
    out += [("your folder", os.path.join(os.path.abspath(os.path.expanduser(d)), SKILL)) for d in extra]
    return out


def put_skill(data, extra=()):
    """The skill written (again) for every agent here: what was written, in words."""
    text, lines = skill_text(sorted(data["pietatos"])), []
    head = text.split("\n# ", 1)[0]                 # (its name and what it's for: what an agent lists)
    for who, folder in skill_dirs(extra):
        path = os.path.join(folder, "SKILL.md")
        try:
            with open(path, encoding="utf-8") as f:
                listed = f.read().split("\n# ", 1)[0] == head
        except (OSError, ValueError):
            listed = False
        try:
            os.makedirs(folder, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            lines.append(f"{who} has the skill: {folder}")
            if who == "Hermes" and not listed:      # (OpenClaw notices a new skill by itself, Hermes as it starts)
                lines.append("  Hermes lists its skills when it starts: if it's running (hermes gateway), restart it.")
        except OSError as ex:
            lines.append(f"{who}'s skill couldn't be written ({ex})")
    return lines


def keep_copy():
    """This script, copied to where the skill runs it from."""
    here, there = os.path.abspath(__file__), kept("agent_link.py")
    os.makedirs(kept(), exist_ok=True)
    if os.path.realpath(here) != os.path.realpath(there):
        shutil.copyfile(here, there)
    return there


def set_up(args):
    url = base_url(args.what)
    password = args.password or ""
    try:
        info = ask(url, password, "/api/info", timeout=10)
    except Said as ex:
        raise Said(f"{ex}\nNothing was changed.")
    own = str(info.get("name") or "") if isinstance(info, dict) else ""
    name = (args.name or own or urllib.parse.urlsplit(url).hostname or "pietato").strip()
    data = load()
    for old in [k for k, v in data["pietatos"].items() if v.get("url") == url and k != name]:
        del data["pietatos"][old]                   # (the same one, called something else before)
    data["pietatos"][name] = {"url": url, "password": password}
    if data.get("first") not in data["pietatos"]:
        data["first"] = name
    save(data)
    keep_copy()
    print(f"{name} is set up ({url}).")
    wrote = put_skill(data, args.skills or ())
    for line in wrote:
        print(line)
    if not wrote:
        print("No OpenClaw or Hermes folder was found here (~/.openclaw, ~/.hermes), so no skill was written.")
        print("If your agent keeps its skills somewhere else, add:  --skills <that folder>")
    try:
        ask(url, password, "/coder?pose=hello", body=b"", coder=True, timeout=5)   # (the Bot waves, if it's at work)
    except Said:
        pass
    print()
    print("Your agent can work it now: ask it what your Pietato is playing.")
    print("To send your agent prompts from the Pietato (A on the Bot at work), keep this running:")
    print(f"    {command_line()} listen")


def remove(args):
    for who, folder in skill_dirs(args.skills or ()):
        if os.path.isfile(os.path.join(folder, "SKILL.md")):
            shutil.rmtree(folder, ignore_errors=True)
            print(f"{who}'s skill is gone: {folder}")
    if os.path.isdir(kept()):
        shutil.rmtree(kept(), ignore_errors=True)
        print("Your Pietatos are forgotten here.")


# ---- what the skill runs --------------------------------------------------------------------------------------------
def span(secs):
    secs = int(secs or 0)
    if secs >= 3600:
        return f"{secs // 3600}:{secs % 3600 // 60:02d}:{secs % 60:02d}"
    return f"{secs // 60}:{secs % 60:02d}"


def do_status(pi, args):
    name, url, pw = pi
    s = ask(url, pw, "/api/pi/state")
    if s.get("mode") != "media":
        print(f"{name} is in its terminal, not its menus. (open Home puts the menus back.)")
        return
    print(f"{name} is showing: {s.get('where') or s.get('view') or 'its menus'}")
    p = s.get("playing")
    if p:
        what = p.get("title") or "something"
        if p.get("song") and p.get("song") != what:
            what += f" ({p['song']})"
        if p.get("sub"):
            what += f", {p['sub']}"
        at = f" at {span(p.get('pos'))}" + (f" of {span(p.get('length'))}" if p.get("length") else "") \
            if p.get("kind") not in ("radio", "live") else ""
        print(f"Playing ({p.get('kind') or 'media'}{', paused' if p.get('paused') else ''}): {what}{at}")
    else:
        print("Nothing is playing.")
    print(f"Volume: {s.get('volume')}")
    if s.get("kb"):
        kb = s["kb"]
        print(f"A box to type in is open: {kb.get('title') or 'no title'} (in it now: {kb.get('text')!r})")
    if s.get("msg"):
        print(f"It says: {s['msg']}")


def do_screen(pi, args):
    name, url, pw = pi
    data, kind = ask(url, pw, "/api/pi/screen", raw=True, timeout=30)
    ext = ".jpg" if "jpeg" in kind else ".png"
    path = args.words[0] if args.words else kept(f"screen-{re.sub(r'[^A-Za-z0-9_-]+', '-', name)}{ext}")
    path = os.path.abspath(os.path.expanduser(path))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    print(f"{name}'s screen is saved as {path}")


def do_press(pi, args):
    name, url, pw = pi
    names = [w.lower() for w in args.words]
    bad = [w for w in names if w not in BUTTONS]
    if bad or not names:
        raise Said("press takes buttons: " + " ".join(BUTTONS))
    for k, button in enumerate(names):
        if k:
            time.sleep(0.25)                        # (as a thumb would: the screen keeps up)
        ask(url, pw, "/api/pi/press", {"button": button})
    print(f"Pressed {' '.join(names)} on {name}.")


def do_open(pi, args):
    name, url, pw = pi
    app = " ".join(args.words).strip()
    if not app:
        raise Said("open takes an app's name, as the home screen has it: Music, Videos, Radio, Games...")
    if app.lower() == "home":
        return do_home(pi, args)
    try:
        ask(url, pw, "/api/pi/open", {"app": app})
    except Said as ex:
        if "No such app" not in str(ex):
            raise
        cat = ask(url, pw, "/api/pi/catalog")
        apps = [a.get("name", "") for a in cat.get("apps", [])] + [t.get("name", "") for t in cat.get("tv", [])]
        match = [a for a in apps if a.lower() == app.lower()] or [a for a in apps if app.lower() in a.lower()]
        if len(match) != 1:
            raise Said(f"There's no app called {app}. There's: " + ", ".join(a for a in apps if a))
        app = match[0]
        ask(url, pw, "/api/pi/open", {"app": app})
    print(f"{name} is showing {app}.")


def do_home(pi, args):
    name, url, pw = pi
    ask(url, pw, "/api/pi/open", {"app": "", "home": True})
    print(f"{name} is on its home screen.")


def folder_of(words, what):
    if not words or words[0].lower() not in FOLDERS:
        raise Said(f"{what} takes a folder first: " + ", ".join(FOLDERS))
    return words[0].lower(), "/".join(w.strip("/") for w in words[1:] if w.strip("/"))


def do_files(pi, args):
    name, url, pw = pi
    folder, path = folder_of(args.words, "files")
    got = ask(url, pw, "/api/list?" + urllib.parse.urlencode({"folder": folder, "path": path}))
    rows = got.get("entries", [])
    print(f"{name}, {folder}{'/' + got.get('path') if got.get('path') else ''}: {len(rows)} there")
    for e in rows[:400]:
        print(("  [folder] " if e.get("dir") else "  ") + str(e.get("name")))
    if len(rows) > 400:
        print(f"  ...and {len(rows) - 400} more")


def do_play(pi, args):
    name, url, pw = pi
    folder, path = folder_of(args.words, "play")
    if not path:
        raise Said("play takes a folder and a file in it:  play music \"Some Album/01 A Song.mp3\"")
    ask(url, pw, "/api/pi/show", {"folder": folder, "path": path}, timeout=70)
    print(f"{name} is playing (or showing) {path}.")


def do_radio(pi, args):
    name, url, pw = pi
    words = " ".join(args.words).strip()
    if not words:
        raise Said("radio takes a station's name, or part of it")
    got = ask(url, pw, "/api/pi/radio?" + urllib.parse.urlencode({"q": words}), timeout=45)
    rows = [r for r in got.get("stations", []) if isinstance(r, list) and len(r) >= 3]
    if not rows:
        print(f"No station found for {words}.")
        return
    if args.play:
        if not 1 <= args.play <= len(rows):
            raise Said(f"--play takes 1 to {len(rows)}")
        r = rows[args.play - 1]
        item = {"src": r[2], "title": r[0], "sub": r[1], "kind": "radio", "uuid": r[3] if len(r) > 3 else ""}
        ask(url, pw, "/api/pi/play", {"items": [item], "index": 0, "where": "Radio"}, timeout=70)
        print(f"{name} is playing {r[0]}.")
        return
    for k, r in enumerate(rows[:20], 1):
        print(f"  {k}. {r[0]}" + (f" ({r[1]})" if r[1] else ""))
    print("Play one with:  radio " + words + " --play N")


def do_player(pi, args):
    name, url, pw = pi
    do = (args.words[0] if args.words else "").lower()
    if do not in PLAYER:
        raise Said("player takes one of: " + ", ".join(PLAYER))
    got = ask(url, pw, "/api/pi/player", {"do": do})
    print(f"{name}: volume {got['volume']}." if "volume" in got else f"{name}: {do}, done.")


def do_type(pi, args):
    name, url, pw = pi
    ask(url, pw, "/api/pi/type", {"text": " ".join(args.words), "enter": bool(args.enter)})
    print(f"Typed on {name}" + (", and finished." if args.enter else "."))


def do_pose(pi, args):
    name, url, pw = pi
    pose = (args.words[0] if args.words else "").lower()
    if pose not in POSES:
        raise Said("pose takes one of: " + ", ".join(POSES))
    ask(url, pw, "/coder?pose=" + pose, body=b"", coder=True)
    print(f"{name}'s Bot: {pose}.")


def do_list(data):
    for name, pi in sorted(data["pietatos"].items()):
        print(f"{name}  {pi['url']}" + ("  (the one used when you don't say)" if name == data["first"] else ""))
    if not data["pietatos"]:
        print("No Pietato is set up yet.")


DO = {"status": do_status, "screen": do_screen, "press": do_press, "open": do_open, "home": do_home,
      "files": do_files, "play": do_play, "radio": do_radio, "player": do_player, "type": do_type, "pose": do_pose}


# ---- your agent's own API, on this computer --------------------------------------------------------------------------
def env_file(path):
    """KEY=value lines of a .env file."""
    out = {}
    try:
        with open(os.path.expanduser(path), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k.replace("export ", "").strip()] = v.strip().strip("'\"")
    except OSError:
        pass
    return out


def openclaw_says(path):
    """A setting of OpenClaw's, as its own command has it ("" when it can't say, or won't: it doesn't show keys)."""
    exe = shutil.which("openclaw")
    if not exe:
        return ""
    try:
        got = subprocess.run([exe, "config", "get", path], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return ""
    if got.returncode != 0 or not got.stdout.strip():
        return ""
    said = got.stdout.strip().splitlines()[-1].strip().strip("'\"")
    return "" if "*" in said or "redacted" in said.lower() or " " in said else said


def openclaw_set(*keys):
    """A setting of OpenClaw's ("" when it has none): as ~/.openclaw/openclaw.json has it, or (when that isn't
    plain JSON: it may have comments) as its own command says."""
    try:
        with open(os.path.expanduser(os.path.join("~", ".openclaw", "openclaw.json")), encoding="utf-8") as f:
            node = json.load(f)
    except OSError:
        return ""
    except ValueError:
        return openclaw_says(".".join(keys))
    try:
        for k in keys:
            node = node[k]
    except (KeyError, TypeError, IndexError):
        return ""
    return str(node) if isinstance(node, (str, int)) and not isinstance(node, bool) else ""


def agents_here():
    """The agents this computer may have, as (which, its API's address, its key, the model to ask for)."""
    out = []
    env = env_file(os.path.join("~", ".hermes", ".env"))
    key = os.environ.get("API_SERVER_KEY") or env.get("API_SERVER_KEY") or ""
    if key or os.path.isdir(os.path.expanduser(os.path.join("~", ".hermes"))):
        port = os.environ.get("API_SERVER_PORT") or env.get("API_SERVER_PORT") or "8642"
        model = os.environ.get("API_SERVER_MODEL_NAME") or env.get("API_SERVER_MODEL_NAME") or "hermes-agent"
        out.append(("hermes", f"http://127.0.0.1:{port}", key, model))
    key = os.environ.get("OPENCLAW_GATEWAY_TOKEN") or openclaw_set("gateway", "auth", "token") \
        or os.environ.get("OPENCLAW_GATEWAY_PASSWORD") or openclaw_set("gateway", "auth", "password")
    if key or os.path.isdir(os.path.expanduser(os.path.join("~", ".openclaw"))):
        port = os.environ.get("OPENCLAW_GATEWAY_PORT") or openclaw_set("gateway", "port") or "18789"
        out.append(("openclaw", f"http://127.0.0.1:{port}", key, "openclaw/default"))
    return out


def api_get(url, key, path, timeout=6):
    req = urllib.request.Request(url + path, headers={"Authorization": "Bearer " + key} if key else {})
    with DIRECT.open(req, timeout=timeout) as resp:
        return json.loads(resp.read() or b"{}")


NAMES = {"hermes": "Hermes", "openclaw": "OpenClaw"}
HOW_ON = {
    "hermes": "Hermes's API isn't answering at {url}. In ~/.hermes/.env set API_SERVER_ENABLED=true and "
              "API_SERVER_KEY=<16 characters or more>, then run: hermes gateway",
    "openclaw": "OpenClaw's chat API isn't answering at {url}. In ~/.openclaw/openclaw.json set "
                "gateway.http.endpoints.chatCompletions.enabled to true, then restart its gateway",
}


def find_agent(args):
    """Your agent's API: (which, address, key, model). What --agent, --url, --key and --model say, and for the
    rest what this computer's OpenClaw or Hermes has set; of two that answer, the first asked for by --agent, or
    Hermes."""
    if args.url:
        url = args.url.rstrip("/")
        url = url[:-3] if url.endswith("/v1") else url
        return args.agent or "other", url, args.key or "", args.model or "default"
    found = [a for a in agents_here() if args.agent in (None, a[0])]
    if not found:
        raise Said("No OpenClaw or Hermes was found on this computer (~/.openclaw, ~/.hermes). For another agent, "
                   "say where its API is:  --url http://127.0.0.1:PORT --key KEY --model NAME")
    why = []
    for which, url, key, model in found:
        key, model = args.key or key, args.model or model
        try:
            api_get(url, key, "/v1/models")
            return which, url, key, model
        except urllib.error.HTTPError as ex:
            why.append(f"{NAMES[which]}'s API at {url} said no ({ex.code}): is its key right? (--key)"
                       if ex.code in (401, 403) else HOW_ON[which].format(url=url))
        except (OSError, ValueError):
            why.append(HOW_ON[which].format(url=url))
    raise Said("\n".join(why))


def tidy(text):
    """Your agent's answer, fit for a small screen: plain lines, no markdown marks, not too long."""
    text = re.sub(r"```[A-Za-z0-9_+-]*\n?", "", str(text or ""))
    text = re.sub(r"(\*\*|__|`)", "", text)
    text = re.sub(r"(?m)^[ \t]{0,3}#{1,6}[ \t]+", "", text)
    text = re.sub(r"(?m)^[ \t]*[-*][ \t]+", "- ", text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"\1 (\2)", text)
    text = "\n".join(line.rstrip() for line in text.replace("\r", "").split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text if len(text) <= REPLY_MAX else text[:REPLY_MAX - 1].rstrip() + "…"


class Talk:
    """A conversation with your agent through its chat API (OpenAI's shape). OpenClaw and Hermes keep the
    conversation themselves, told which one it is; anything else is sent the last few turns each time."""

    def __init__(self, which, url, key, model, thread):
        self.which, self.url, self.key, self.model, self.thread = which, url, key, model, thread
        self.turns = []

    def request(self, text, stream=True):
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream" if stream else "application/json"}
        if self.key:
            headers["Authorization"] = "Bearer " + self.key
        body = {"model": self.model, "stream": stream, "messages": [{"role": "user", "content": text}]}
        if self.which == "hermes":
            headers["X-Hermes-Session-Id"] = self.thread
        elif self.which == "openclaw":
            body["user"] = self.thread
        else:
            body["messages"] = self.turns[-2 * HISTORY:] + body["messages"]
        return urllib.request.Request(self.url + "/v1/chat/completions", data=json.dumps(body).encode(),
                                      headers=headers, method="POST")

    def say(self, text, doing=lambda pose: None):
        """Your words to it, and its answer. doing: told "typing" as its answer starts to come and "reading" or
        "typing" as it uses a tool (where it says so). A Said when it can't answer."""
        try:
            resp = DIRECT.open(self.request(text), timeout=QUIET_MOST)
        except urllib.error.HTTPError as ex:
            raise Said(self.refused(ex))
        except (OSError, ValueError) as ex:
            raise Said(f"Your agent's API at {self.url} isn't answering ({getattr(ex, 'reason', ex)})")
        try:
            with resp:
                if "event-stream" in (resp.headers.get("Content-Type") or ""):
                    answer = self.stream(resp, doing)
                else:
                    answer = self.whole(json.loads(resp.read() or b"{}"))
        except (OSError, ValueError) as ex:
            raise Said(f"Your agent stopped answering part-way ({getattr(ex, 'reason', ex)})")
        if self.which not in ("hermes", "openclaw"):
            self.turns += [{"role": "user", "content": text}, {"role": "assistant", "content": answer}]
        return answer

    def refused(self, ex):
        try:
            err = json.loads(ex.read() or b"{}").get("error")
            why = err.get("message") if isinstance(err, dict) else err
        except (ValueError, AttributeError, OSError):
            why = None
        if ex.code in (401, 403):
            return f"Your agent's API said no ({ex.code}): {why or 'is its key right?'}"
        if ex.code == 404 and self.which == "openclaw":
            return HOW_ON["openclaw"].format(url=self.url)
        return f"Your agent's API said no ({ex.code}): {why or 'no reason given'}"

    @staticmethod
    def whole(got):
        choice = (got.get("choices") or [{}])[0] if isinstance(got, dict) else {}
        text = (choice.get("message") or {}).get("content")
        if isinstance(text, list):
            text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
        if not text and isinstance(got, dict) and got.get("error"):
            err = got["error"]
            raise Said(f"Your agent said: {err.get('message') if isinstance(err, dict) else err}")
        return str(text or "")

    def stream(self, resp, doing):
        """Its answer as it comes (server-sent events): the words put together."""
        parts, event, writing = [], "", False
        for raw in resp:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if not line:
                event = ""
                continue
            if line.startswith(":"):                 # (a keepalive)
                continue
            if line.startswith("event:"):
                event = line[6:].strip()
                continue
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                got = json.loads(data)
            except ValueError:
                continue
            if not isinstance(got, dict):
                continue
            if event == "hermes.tool.progress":      # (Hermes says which tool it's using)
                if got.get("status", "running") == "running":
                    tool = str(got.get("tool") or "").lower()
                    doing("reading" if any(w in tool for w in READS) else "typing")
                    writing = False
                continue
            if got.get("error") and not got.get("choices"):
                err = got["error"]
                raise Said(f"Your agent said: {err.get('message') if isinstance(err, dict) else err}")
            for choice in got.get("choices") or []:
                piece = (choice.get("delta") or {}).get("content")
                if isinstance(piece, str) and piece:
                    parts.append(piece)
                    if not writing and piece.strip():
                        writing = True
                        doing("typing")
                if choice.get("finish_reason") == "error" and not parts:
                    raise Said("Your agent couldn't finish its answer")
        return "".join(parts)


def thread_of(data, name, new=False):
    """The name of the conversation your agent keeps for this Pietato: the same each time, so it carries on where
    it was; the next one when you ask for a new conversation (--new)."""
    n = data["talks"].get(name, 0)
    if new:
        n += 1
        data["talks"][name] = n
        save(data)
    tag = re.sub(r"[^A-Za-z0-9_.-]+", "-", f"pietato-{name}").strip("-")[:50] or "pietato"
    return tag + (f"-{n}" if n else "")


def listen(args):
    """Prompts typed on the Pietato (A on the Bot at work), handed to your agent; its answers, sent back."""
    data = load()
    name, url, pw = which_pi(data, args.on)
    which, api, key, model = find_agent(args)
    talk = Talk(which, api, key, model, thread_of(data, name, args.new))
    who = NAMES.get(which, "your agent")
    print(f"Listening: prompts typed on {name} (A on the Bot at work) go to {who} at {api}.", flush=True)
    if args.new:
        print("This is a new conversation.", flush=True)
    print("Ctrl-C stops it.", flush=True)

    def tell(path, body=b"", timeout=10):
        try:
            return ask(url, pw, path, body=body, coder=True, timeout=timeout)
        except Said as ex:
            print(f"  ({ex})", flush=True)
            return None

    todo = queue.Queue()

    def work():
        while True:
            text = todo.get()
            print(f"> {text}", flush=True)
            tell("/coder?pose=thinking")
            last = [None]

            def doing(pose):
                if pose != last[0]:
                    last[0] = pose
                    tell("/coder?pose=" + pose, timeout=5)
            try:
                answer = tidy(talk.say(text, doing)) or "(It answered with nothing.)"
                failed = False
            except Said as ex:
                answer, failed = str(ex), True
            except Exception as ex:                  # (whatever it was, the Pi is told, and this carries on)
                answer, failed = f"Something went wrong handing it to your agent ({type(ex).__name__})", True
            print(answer, flush=True)
            print(flush=True)
            tell("/coder?pose=" + ("error" if failed else "done"))
            tell("/coder/reply", {"text": answer, "failed": failed, "agent": who if which != "other" else ""})

    threading.Thread(target=work, daemon=True).start()
    tell("/coder?pose=hello")
    got, run, quiet = 0, "", 0.0
    while True:
        query = urllib.parse.urlencode({"wait": WAIT, "got": got, "run": run})
        try:
            r = ask(url, pw, "/coder/prompts?" + query, body=b"", coder=True, timeout=WAIT + 15)
        except Said as ex:
            if time.monotonic() - quiet > 60:        # (said once a minute, not each try)
                print(f"  ({ex})", flush=True)
                quiet = time.monotonic()
            time.sleep(3)
            continue
        if not isinstance(r, dict):
            time.sleep(1)
            continue
        if isinstance(r.get("run"), str) and r["run"] != run:
            run, got = r["run"], 0                   # (the Pi restarted: its prompts are numbered afresh)
        for p in r.get("prompts") or []:
            pid, text = p.get("id"), p.get("text")
            if type(pid) is int and pid > got and isinstance(text, str) and text.strip():
                got = pid
                todo.put(text.strip())
            elif type(pid) is int and pid > got:
                got = pid


# ---- the command line --------------------------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(prog="agent_link.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", nargs="?", help="your Pi's name or address (to set it up), or a command")
    ap.add_argument("words", nargs="*", help="what the command takes")
    ap.add_argument("--password", help="the Pi's web page password, if it has one")
    ap.add_argument("--name", help="what to call this Pietato here")
    ap.add_argument("--skills", action="append", metavar="DIR", help="put the skill in this folder too")
    ap.add_argument("--remove", action="store_true", help="forget your Pietatos and take the skill out")
    ap.add_argument("--on", metavar="NAME", help="which Pietato (with several)")
    ap.add_argument("--play", type=int, metavar="N", help="radio: play the Nth station found")
    ap.add_argument("--enter", action="store_true", help="type: finish what's typed")
    ap.add_argument("--agent", choices=("openclaw", "hermes"), help="listen: which agent, with both here")
    ap.add_argument("--new", action="store_true", help="listen: start a new conversation with your agent")
    ap.add_argument("--url", help="listen: an agent's API that isn't OpenClaw's or Hermes's (OpenAI's chat shape)")
    ap.add_argument("--key", help="listen: that API's key")
    ap.add_argument("--model", help="listen: the model's name to ask for")
    args = ap.parse_args(argv)
    try:
        if args.remove:
            return remove(args)
        if not args.what:
            ap.print_usage()
            raise Said("Give your Pi's name or address to set it up, or a command (see --help).")
        what = args.what.lower()
        if what == "listen":
            return listen(args)
        if what == "list":
            return do_list(load())
        if what in DO:
            return DO[what](which_pi(load(), args.on), args)
        if args.words:
            raise Said(f"{args.what} isn't a command. There's: " + ", ".join(COMMANDS))
        return set_up(args)
    except Said as ex:
        print(str(ex), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print()
        sys.exit(130)


if __name__ == "__main__":
    main()
