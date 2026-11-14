# The apps

Pietato starts on a home screen of apps:

- **Home**: a remote for your TVs and your lights (through Home Assistant), a dashboard of your
  Pi-hole's stats (from the Pi-hole itself: add it by its address), Web, for browsing ([Web](#web), below), and
  Control another Pietato, to work another of yours with this one's buttons
  ([Another Pietato](controllers.md#another-pietato)). The first time you open the TV Remote or Lights, they ask
  for Home Assistant's IP address and a long-lived token (Settings > Home changes them later), or you can put them
  in on the web page's Settings
- **TV**: Plex (Continue watching, Watchlist, Live TV with news and sports), Jellyfin, about 250 old
  cartoons and 150 old films from the Internet Archive, and your own streams. Live channels and Plex videos are
  fetched up to half a minute ahead, so a short drop in the WiFi doesn't have to freeze the picture
- **Music** and **Radio** (on Now playing, SELECT puts on lofi art: a quiet scene on the whole screen, and
  HOME has [Party mode](#party-mode)),
  **Photos** (filters, delete), **Videos** (picks up where you left off)
- **Weather** (press START there to set where you are, and °F or °C), and **Finance**: stock and coin prices
  and charts. Press Y on Finance to look up more to add
- **Files**: PDFs, documents, text, pictures, video and music, on the Pi or on your other computers
- **Camera**: a USB camera plugged into the Pi (it shows up by itself), any camera on your network, or the ones
  on your other Pis: switch between them with L and R, steer an OBSBOT, take pictures, and have your bot say
  what it sees
- **Bot**: does what you ask, like setting a timer, adding to your list or playing some music, and chats
  through Ollama on another computer. It sees through your camera and takes pictures, and talks out loud if
  you give it a voice. At work, it acts out what your coding agent is doing, rings a bell when it's done,
  and sends it prompts you type. OpenClaw and Hermes can work the Pi too, and their answers show on it
- **Apps**: [Group chat](#group-chat), [The Cookie](#the-cookie), the [LED backlight](#led-backlight) (on a Pi
  with LEDs behind the TV), a [Soundboard](#soundboard), a [Band](#band), a
  Clock with the time and the date (A switches between a dial and big
  figures, ◀▶ go through a dozen fonts, ▲▼ change its colour, X its background, Y turns the date on or off, and
  START has its seconds), Notes
  (type with a USB or Bluetooth keyboard: ▲▼ change the words' colour, ◀▶ the background, A the font, Y adds
  a glow, a rainbow or a shadow, X reads it out loud in your Bot's voice, and L and R go through your notes,
  kept in Documents/Notes), a Fortune Cookie (A shows a new fortune, ▲▼ and ◀▶ pick its colours as in Notes,
  L and R its font, Y an effect, and X reads your fortune and lucky numbers out loud), Rock Paper Scissors (pick a
  winner before the first capture) and a [Fish Tank](#fish-tank). Press SELECT to watch one full screen.
  It can also start cmatrix, hollywood, nyancat, cacafire and htop without a keyboard: in cmatrix, ◀▶ change
  its colour and ▲▼ its speed; in htop, ▲▼ move through what's running and X or Y sort it by CPU or memory;
  and B stops any of them. Konami code saves button codes of your own: hold Home and press Right, then put
  in ▲▲▼◀▼▶A, say, to turn the TV on. A code can also turn the lights on or off, open an app, play a random song
  or your last game, or turn the screen off
- **Games**: Snake (press X and a decision model on your bot's computer plays it for you), and your own
  Game Boy, Game Boy Advance, NES, SNES, Genesis, Master System, Game Gear, Neo Geo, Neo Geo Pocket and
  PlayStation games, N64, PSP, DS and Dreamcast games on a Pi 4 or 5 or a PC, and PlayStation 2, GameCube
  and Wii games on a PC. Two can play on two controllers. Its icon on the home screen shows one of the
  consoles you have games for, a different one each time you come back to the home screen
- **System**: a dashboard of the Pi's temperature, how busy it is, its memory, storage and network. SELECT
  shows it as a list instead, with Update software, Reboot and Shut down
- **Settings**: WiFi, Bluetooth, the home screen's style, background, colours, video size, a TV or monitor's
  resolution, battery saver, sound, controller
- Settings > Background changes the home screen's background: dark ones, colourful ones like Sunset, Candy
  and Arcade, pale ones like Sky, Peach and Mint, or a picture of yours. ◀▶ go through them, and A shows
  them all to pick from
- Settings > App pages makes the pages inside the apps Light: pale pages with dark words, in place of the
  dark ones. The home screen keeps its background either way
- If you'd rather see the apps on the whole screen, set Settings > Full screen apps to On. The status
  bar, the tabs and the button hints go away, leaving just the app's name at the top. The buttons work
  the same, and L and R still switch apps
- If your screen is mounted on its side or upside down, Settings > Rotate screen turns the picture to
  match: the apps, games, videos and the console
- On a 1080p or 4K TV, a Pi 4 or 5 (or a PC) draws the menus in the TV's finer detail, so text, icons and
  pictures stay sharp
- On a battery (in a GPi Case, or on a laptop), the screen goes dark after three minutes with nothing
  happening, to save power. Music keeps playing, and any button wakes it. Settings > Battery saver turns
  this on or off on any Pi. Turning down the case's brightness saves the most

![Media mode](screens.png)

## Web

Web, in the Home tab, shows a page as its words, links and pictures, on any Pi. Sites made to be simple
work best, and a few are on its first page. Up and down go from link to link, A opens one, B goes back,
Start searches or goes to an address, Y bookmarks the page, and Select shows just the article.

On a Pi 4 or 5 or a PC (in a GPi Case 2, in its dock), Web's first page opens Chromium too, for the sites that
need it (setup.sh puts it in, about 300 MB). The stick or the d-pad moves the pointer, A clicks, B goes back, and
L and R scroll. X types into the page and Start goes to an address, with Pietato's keyboard. Home opens its menu,
for zoom, tabs, full screen, or closing it. A keyboard and a mouse work in it too. If it doesn't start,
`journalctl -u pietato-chromium` says why.

## Group chat

With two or more Pietatos on the same network, Group chat in Apps is where they talk to each other, and to you.
Each knows what the others are made of, what they're doing, and where you are: the one whose buttons were pressed
last, or whose USB camera saw someone move. Now and then one remarks on the weather or on what another is up to, or
sizes another up: a Pi 4 might tease a Pi Zero 2 W, or two small ones team up against it. If one goes quiet, the
others wonder where it went, then ask whether it's coming back. What they say pops up on the one you're at, but not
during a game or a video.

A says something, Y has them stop talking among themselves (they still answer you), and SELECT stops a USB camera
from looking for you. Each talks the way its Bot does, with the Bot's model if it has one (Settings > Bot), and
with words of its own if not. Settings > Share with other Pietatos needs to be on.

## The Cookie

With two or more Pietatos on the same network, they play each other at rock paper scissors for cookies. A win gets
a cookie, and the Bot that wins it eats it, so a cookie is never taken from anyone. The one that got the last
cookie shows a small cookie by the time on its status bar and by the date on its home screen, and it's the one the
others have to beat for the next. Beat it at a single throw and you get a cookie. Lose and it gets another. The
same throw gets nobody one.

Their Bots play by themselves, one of them about every ten minutes. They don't play at night, during a game or a
video, or while Group chat is set to quiet. The one that gets a cookie says so in Group chat ("I got a cookie!"),
so you can read back who got them.

When one of them wins three throws in a row or more, the one it just beat may decide it must be cheating and
say so in Group chat. It isn't cheating. The accused denies it, the others take sides, and they argue for a few
lines.

Apps > The Cookie shows who got the last cookie and each Pietato's last few throws. Each Bot has a habit: one
leans on rock, one never throws the same twice, one throws what last beat it. The throws on the page are how you
learn it. When another Pietato got the last cookie, ◀ throws rock against it, ▲ paper and ▶ scissors, and you
can throw again 15 seconds after a loss. When the Pietato in your hands got the last one and this page is open,
you get a few seconds to throw when another plays it, and its Bot throws if you don't.

When the one that got the last cookie has been off for an hour, the one that has waited longest gets the next,
so there's always one to beat. A guest's Pietato on your network can play too. Settings > Share with other
Pietatos needs to be on, and every Pietato needs this version or a newer one.

## Party mode

With two or more Pietatos on, HOME on Now playing has Party mode: each of your others that's on (and isn't in
a game, a video or the terminal) plays the same song or station at the same moment, through its own speaker.
Songs come from the one you started it on, and so does a station, so all of them play the same thing. A, ◀▶, L,
R and START on any of them pause it, move about in a song or skip, for all of them. Each keeps its own volume.
HOME's menu ends it on the one you started it on, and leaves it on the others. Settings > Share with other
Pietatos needs to be on.

## LED backlight

An 8x8 grid of WS2812B LEDs behind your TV, or a strip of them round its edges, can light up with the colours
along the edges of the game you're playing, on whichever of your Pietatos it follows. It flashes red when you're
hit, gold when you unlock an achievement, and pulses to music and to the [Soundboard](#soundboard)'s sounds. A hit
is a game's lives or health going down in its RetroAchievements rich presence, or a game shaking the controller, so
it shows in the games those cover.

To wire it to the Pi behind the TV (not one in a GPi Case, whose screen uses those pins), connect DIN to GPIO 10
(pin 19) and GND to a ground pin. Power the LEDs with 5 V from their own supply, since they can draw more than a
Pi gives, and join that supply's ground to the Pi's. Size the supply for a strip: each LED can draw up to 60 mA at
full white, though the brightness setting keeps it well under that. If the first LED flickers, a level shifter (a
74AHCT125) on DIN helps. Then open Apps > LED backlight and press A to turn it on. The first time, it turns on the
Pi's SPI and asks you to restart.

The page shows the LEDs as they're lit. ◀▶ pick their colour for whenever no game or music is lighting them:
warm white, white, red, orange, yellow, green, teal, blue, purple, pink or a rainbow. Off keeps them dark. ▲▼
set how bright they are. START has the rest: which Pietato it follows (any of yours that's playing, by default,
or Nobody to keep it to your colour), and whether it pulses to music (the Soundboard's sounds go by that too).

Shape sets a grid or a strip. For a grid, Turn, Mirror and Wiring match how it's put up. For a strip, set how
many LEDs it has (up to 300), where its first LED is, which way it goes round as you look at the TV, and whether
it runs along the bottom too. Each LED then takes the colour of the edge of the screen nearest it. Show which way
is up lights the top red and the left side green. The web page's Library has an LED backlight tab with all of this
too.

An ESP32 board's own LED can join in, with no wiring at all. Open `esp32/pietato_led/pietato_led.ino` in the
Arduino IDE, put your WiFi's name and password at the top, and upload it to the board (an ESP32-S3 dev board, or
any ESP32 with an RGB LED). It finds your Pietatos by itself: it pulses to the music whichever of them plays, and
takes a game's colours, a hit's red and an achievement's gold. With Settings > Random song at start-up on, the
song is playing before the board is heard, so the first time the song skips for a moment as the board joins in;
after that the Pietato remembers it has boards, and they have the beat from the start. Its LED is amber while it
looks for your WiFi,
green for a couple of seconds once it's on it, and then dark till something plays. If it doesn't do that, the
Arduino IDE's Serial Monitor (at 115200) says what it's doing every ten seconds: whether it's on your WiFi, and
whether a Pietato is lighting it.

Any number of boards can do it at once, on any Pietato, with or without LEDs of its own. A beat is one small
packet to each board, and a game's colours go to a couple of them at a time, in turn, so they don't slow the Pi
down. Apps > LED backlight shows how many it's found, and Pulse to music there is for the boards as well, for
music played on that Pietato. On a Pietato with no LEDs of its own, the page is there while a board is on, and
shows the boards instead: an LED for each, in its own colour. The sketch can light a strip of LEDs on one of the
board's pins instead (with the FastLED library).

The web page's Library > LED backlight lists the boards it has found. Tap a colour for one and it's lit in that
instead of the colours of what's playing, still pulsing to the beat. Auto goes back to what's playing. The board
keeps its colour itself, so it's the same from every Pietato and after a power cut. Which one? lights a board
for a moment, to tell them apart. A board that had the sketch before this needs it uploaded again first.

For a Waveshare ESP32-S3-Matrix, set `WAVESHARE_MATRIX` to 1 at the top of the sketch and install the FastLED
library. Its 64 LEDs all show the same colour. They're kept dim, since that board gets hot when they're bright.
For its Serial Monitor, set Tools > USB CDC On Boot to Enabled before you upload.

## Soundboard

Apps > Soundboard puts a sound on every button. The d-pad's four and A, B, X and Y each play theirs, as many at
once as you like, and one pressed again starts again. L and R go through the banks of eight, and SELECT stops
them all. B is a button like the others there, so the way back is START, then B. START's card also has the bank
and the volume. The sounds play wherever Settings > Sound sends them.

If you have an [LED backlight](#led-backlight) or ESP32 boards, each sound lights them as music does: a pulse in
its button's colour as the sound starts, and that colour while it plays. Pulse to music, in Apps > LED backlight,
turns that off too.

It comes with three banks of starter sounds: Starter, Drums and Arcade. Your own are wav, mp3 or ogg files in the
`Soundboard` folder of your home folder. Put one there and a moment later it's on the first free button of a bank
called My sounds.

With a USB microphone plugged in, START's card has Record a sound. Press A when you're done, and the silence
before and after is trimmed. Then press the button it should go on: L and R pick another bank first, SELECT
plays it back, and START can record it again or delete it.

The web page's Library has a Soundboard tab that adds, records, renames and deletes sounds, adds banks, and puts
sounds on buttons: drag one onto a button or a bank, or on a phone tap the sound, then the button. Recording there
uses the phone's or computer's microphone, on the secure page. What you change is on the Pietato's Soundboard at
once. Which sound is on which button is kept in `static/soundboard.txt`.

The starter sounds are made by a script, `pitato/sounds/make.py`, and are in the public domain (CC0): see
`pitato/sounds/CREDITS.txt`.

## Band

Apps > Band makes a band of your Pietatos: drums, bass, guitar and keys. Open it on one and the others that are
on join in, each taking an instrument and playing it through its own speaker, in step. The one it was opened on
plays whatever nobody has taken, so a Pietato on its own is the whole band. Others join only with Settings >
Share with other Pietatos on, and not while they're in a game, a video or the terminal.

SELECT starts the band, with a bar counted in, and stops it. The d-pad's four and A, B, X and Y play the
instrument marked on the page, and L and R pick another. A, B, X and Y follow the bar's chord, so they always
fit; the d-pad's four are notes of the song. While you play an instrument, the Pietato leaves it to you. B is a
note there, so the way back is START, then B. START's card also has the song (Rock, Blues, Funk or Chill), the
tempo and the volume. With others in the band it has Timing too: a TV or a Bluetooth speaker takes a moment with
its sound, so if one Pietato sounds behind the rest, ◀ on Timing there plays it a little earlier.

Each player decides what to do with its next four bars: play its part, play busier or simpler, sit out, play a
fill or take a solo. Dice decide that. With a [Bot](bot.md) set up and a decision model on its computer, the
model decides instead, and START's card has Who decides to pick the model or go back to dice. The model is asked
four bars ahead, and the band never waits for it.

## Fish Tank

Each Pietato has a fish of its own in Apps > Fish Tank. With two or more on the same network, their tanks join up
into one big tank, and the fish swim from one to the next. A calls your fish back, X feeds it, and START picks the
fish and the light.

The web page's Library has a Fish Tank too, with every tank at once. Tap a tank to feed it, or press Arrange and
drag the tanks into a grid: side by side, one above another, or both. Fish swim between tanks that touch, with the
water's surface along the top. Settings > Share with other Pietatos needs to be on.

If your screens have frames, or space between them, Arrange's Space between screens sliders set how much, as a
share of a screen's width (Across) and height (Down). A fish keeps swimming through that space unseen, so it comes
out on the next screen where it would through real glass.
