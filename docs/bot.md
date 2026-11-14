# The Bot

Type it, say it into a USB microphone, or send it from the web page, and the bot does what you ask
right away, even before you set up Ollama: "set a timer for 10 minutes", "start a focus session",
"wake me up at 7", "add milk to my list", "remind me at 5 to call mom", "take a note: the car's on
level 3", "play some jazz", "turn off the kitchen lights" or "open the weather". Timers and reminders
speak up when they're due (or chime, if it has no voice), and a timer's time left shows beside the
clock at the top of each app.

It plays your games too: "play a game" starts one of yours at random, and "play mario" (or "I want to
play shrek two") starts the one with that in its name. "Put on some cartoons", "watch a movie", "turn on a
channel" or "watch the news" puts something on (a channel comes from your streams, or from Plex if you're
signed in), and "next channel" changes it. "Show my camera roll", "show my newest picture" and "start a
slideshow" bring up your photos. "Rotate the camera" turns a camera's picture, and "turn the camera left"
turns a camera that can move. Tell it you're bored and it suggests a game or some cartoons, and "show me
something cool" puts on something from Apps, picked at random. "Check for updates", "restart" and
"shut down" ask first, and say yes to go ahead. With Ollama set up, ask any way you like: the bot knows
your games, music and streams by name, and starts what you asked for.

Press left on the Bot for Today: your list, timers, reminders and notes. A adds to your list, X ticks
a thing off, and SELECT twice takes it off. START starts a 25-minute focus timer, with a 5-minute
break after it. Its face blinks, looks around, and shows when it's listening, thinking or talking.
SELECT switches its chat page to just its face, big, in the middle of the screen, with no words, and
back. It still talks, and with a microphone it listens: press A and talk to it. Without one, A opens
the keyboard. On its face, up and down change its colour and left and right its background.

Make it your own in its Character, like a game's character creator: X > Edit Character on the Bot, or
first in its settings (START). Its name, its eyes (size, height, corners, spacing, eyelashes), its mouth,
its colours and its voice are each a row: ◀▶ changes it and its face shows it at once, A types its name,
L and R go through the parts, SELECT shows its other looks (happy, sorry, cool...), X makes up a look at
random, and Y twice puts its look back as it started. Its name is what you call it ("hey potato" for
Potato), and it knows it. How it talks gives it a personality: Friendly, Big brother, Butler, Pirate,
Coach, Robot or Calm. Settings > Bot keeps the rest: the computer with Ollama, the model, and how it listens.

START has its settings, right on the Bot, and B brings you back to it. They're also in Settings > Bot.

If you run [Ollama](https://ollama.com) on a computer on your network, set its address and a
model in Settings > Bot, or on the web page. On that computer Ollama has to listen on the
network (`OLLAMA_HOST=0.0.0.0`). The bot knows the time, the weather, your stocks and coins, and
what's playing. Ask it to take a picture and your camera takes one, into Photos and the conversation.

It also looks through your camera now and then and says what it sees, and looks at pictures you
send it: press X on the Bot page to pick one from Photos, or use the picture button on the web page
to send one from your phone. Press SELECT on the Camera tab, or Describe on the web page's Cameras,
and it says what that camera sees. It looks with the model you picked; if that model can't see
pictures, it tells you.

Left alone for five minutes while it's plugged in, it gets bored and finds something to do, something
else every minute or so: it plays one of your games, looks through your camera and says what it sees (a
camera that turns, like an OBSBOT, it turns to look around, then back), or puts up the weather, your
stocks and coins, one of Apps, a slideshow of your photos or how the Pi's doing. Each time, it says
something about it, on the screen and out loud between 8 in the morning and 10 at night. A or START keeps
what it's showing, and any other button takes you back to where you were. Settings > Attract mode turns
it off, or keeps it to games.

If that computer has a decision model (Ollama 0.35 or newer: `ollama pull nimble`), press X in
Snake and the model plays. Beside the board you see its decisions as it makes them: the snake's moves,
what it was told about each, and the one it picked. Pick which model in Snake's options (START), and
Slow if it can't keep up.

It can also play your games for you: in a game, open its menu with Home and press ▶ on AI player to
pick a decision model. Your buttons wait while it plays. It gets a game going by itself, the way you
would without thinking: Start, then A, through the logos, the title screen, menus and text (a coin
first in an arcade game), and again if it ends up back there after a game over. Racing games,
platformers, fighting games and shooters it then plays by instinct, many times a second: it holds the
gas and steers along the road, runs and jumps over gaps and enemies, attacks and blocks, or keeps
firing. The model says which way to go and helps with menus, but the game doesn't wait for it, and
it plays on when the model's slow or says nothing. It knows what kind of game many are from their
names; for the rest, your Bot's model says. In other games the model looks at the screen and picks
the next button to press, while the game goes on at its own speed. It does that in a platformer too,
where running and jumping has got it no further for half a minute (a ledge that wants a crate, a gate
with a switch): the model takes over there, a button at a time, until it's past.

It plays Pokémon Emerald (the English cartridge) best, as there it reads the game's memory too. It
knows the story (out of the truck, the clock, your rival, Professor Birch, and on badge by badge) and
walks there by itself. It battles, reads, answers, heals when your team's badly hurt and trains in
tall grass when it's too weak for the next Gym, though it can't shop, catch Pokémon or solve every
puzzle yet.

In other games, your Bot's model coaches it. The first time, it says what kind of game it is, what each
button does and how it's played well; then every so often, and whenever it gets stuck, it looks at the
screen and works out what to aim for. What it works out goes in `Games/Saves`, in a file ending in
`.ai-notes.txt`, for next time. You can add your own tips there, under Tips, and change its Kind: line
if it got the kind of game wrong. What it saw and picked goes there too, in a file ending in `.ai.log`.

It learns a little as it plays. When it was stuck and then got on, your Bot's model writes one line in
those notes on what did it, and when it's been stuck a long while, one on what it tried. The lines start
Learned:, and it's told them every time it plays that game after, so they add up from one game to the
next (it keeps the newest 24). They're its guesses from what it saw, so some will be wrong: change or
delete any of them. It can't tell a lost life or a finished level from the screen by itself, so it
learns little from those: only when the screen changes altogether while the model is working a
platformer out does it ask your Bot's model what happened.

If you pick a voice in its Character (Voice), it says its replies out loud with
[Piper](https://github.com/rhasspy/piper), which runs on the Pi. The first time, the Pi
downloads Piper (about 25 MB) and the voice (about 60 MB). The quick voices suit a Pi Zero
best. Press X and Say it again to hear the last reply again, or Say it out loud on the web page.
It doesn't talk over your music, unless you turn on Pauses music in its Character (Voice): then it
pauses your music or the radio while you talk to it and while it answers, and plays it on after.

If you plug a USB microphone into the Pi (one with a free USB port: in a GPi Case, only the GPi Case 2's
dock has one) or a PC, you can talk to it: say "hey potato" and what you want. It makes out what you say on
the Pi itself with [Vosk](https://alphacephei.com/vosk/), which it downloads the first time you plug one in
(about 45 MB). It listens while music plays or is paused: over music it only listens for its name, so
say "hey potato" and, once the music pauses or goes quieter, what you want. It doesn't listen while it's
talking, while you play a game, or while a video plays on a Pi Zero, 1, 2 or 3.
Renaming it in its Character changes what you say, or set any wake phrase in Settings > Bot. Or press X
on the Bot page and Talk to it instead. Set Settings > Bot > Listens to Off to stop it, or to On to have it
use a webcam's microphone or a PC's built-in one too.

## Claude Code

Press right on the Bot to go from chatting to work. At work it sits at a desk: it
reads when your coding agent reads, types when it writes code, waves when it needs you, and rings a
bell when it's done.

To connect Claude Code, run this on the computer it runs on:

```
curl -O http://<your Pi's IP address>:5432/coder_hooks.py
python3 coder_hooks.py <your Pi's IP address>
```

It adds hooks to Claude Code's settings that tell the Pi what Claude Code is doing. They run in
the background and do nothing when the Pi is off. `--remove` takes them out again.

The same script lets you send Claude Code prompts from the Pi. Start Claude Code like this:

```
claude --dangerously-load-development-channels server:pitato
```

Then press A at work, type a prompt, and press START. Claude Code gets it as if you had typed it.
When Claude Code asks to use a tool (to run a command, say), the question shows on the Pi too: A allows
it, B denies it, and X leaves it for the computer. Whichever answers first counts.
This uses Claude Code's channels, which are a research preview: Claude Code asks you to confirm
each time it starts, and it needs to be signed in with a Claude account or an Anthropic API key.
If channels aren't available to you yet, Claude Code says so when it starts.

- If your web page has a password, add `--password` and the password.
- Prompts and answers only come from the Pi itself. The web page's remote can't send them.
- If you only want the hooks, add `--no-prompts`.
- To have Claude Code use your Ollama models, start it with `ollama launch claude`
  ([Ollama's guide](https://docs.ollama.com/integrations/claude-code)). Prompts from the Pi
  need Claude Code signed in, though.
- Other agents and scripts can `POST /coder?pose=typing` (or `reading`, `thinking`, `done`...),
  and send a WAV to `POST /coder/say` to have it said out loud.

At work, A types a prompt, Y rings the bell, X turns its sounds off, and START shows these steps.

## OpenClaw and Hermes

If you run [OpenClaw](https://github.com/openclaw/openclaw) or
[Hermes Agent](https://github.com/NousResearch/hermes-agent) on a computer, you can connect it too, both
ways. Run this on the computer it runs on:

```
curl -O http://<your Pi's IP address>:5432/agent_link.py
python3 agent_link.py <your Pi's IP address>
```

It gives your agent a skill for your Pietato, in `~/.openclaw/skills` and `~/.hermes/skills` (whichever
you have). With it your agent can see the Pi's screen, press its buttons, open its apps and play your
music, videos and radio there: ask it "what's my Pietato playing?" or "put some jazz on the Pietato".
Hermes lists its skills when it starts, so restart it once.

To send your agent prompts from the Pi, keep this running on that computer:

```
python3 agent_link.py listen
```

Then press A at work, type a prompt, and press START. The Bot acts out that your agent is working, and
what it answers shows on a card: up and down move through a long answer, X reads it out loud, B closes
it, and SELECT shows it again. Your agent carries on the same conversation each time; `listen --new`
starts a new one.

`listen` hands your prompts to your agent through its own API on that computer, which has to be on:

- OpenClaw: set `gateway.http.endpoints.chatCompletions.enabled` to `true` in
  `~/.openclaw/openclaw.json`.
- Hermes: put `API_SERVER_ENABLED=true` and `API_SERVER_KEY=` with a key of 16 characters or more in
  `~/.hermes/.env`, then run `hermes gateway`.

A few more things:

- Your agent's API and its key stay on its computer: the script fetches your prompts from the Pi, and
  the Pi never reaches into the computer.
- The skill works the Pi the way the web page's remote does. Prompts, and answers to what Claude Code
  asks, only come from the Pi's own buttons: the skill can't send them.
- If your web page has a password, add `--password` and the password.
- With both agents on one computer, `listen --agent hermes` (or `openclaw`) picks one.
- With several Pietatos, set each one up the same way. The skill's commands and `listen` take `--on`
  and a Pietato's name.
- Keep one listener running for a Pietato, not two. With Claude Code's channel running for it too, a
  prompt goes to whichever of them asks for it first.
- Another agent that speaks OpenAI's chat API works with `listen --url`, `--key` and `--model`.
- `--remove` forgets your Pietato there and takes the skill out again.

START at work shows these steps too: left and right change between Claude Code's and these.
It was tried with OpenClaw 2026.9 and Hermes Agent 0.19: a later version of either may need something
different.
