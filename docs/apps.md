# The apps

Pietato starts on a home screen of apps:

- **Home**: a remote for your TVs and your lights (through Home Assistant), a dashboard of your
  Pi-hole's stats (from the Pi-hole itself: add it by its address), Web, for browsing ([Web](#web), below), and
  Control another Pietato, to work another of yours with this one's buttons
  ([Another Pietato](controllers.md#another-pietato)). The first time you open the TV Remote or Lights, they ask
  for Home Assistant's IP address and a long-lived token (Settings > Home Assistant changes them later), or you
  can put them in on the web page's Settings
- **TV**: Plex (Continue watching, Watchlist, Live TV with news and sports), Jellyfin, about 250 old
  cartoons and 150 old films from the Internet Archive, and your own streams. Live channels and Plex videos are
  fetched up to half a minute ahead, so a short drop in the WiFi doesn't have to freeze the picture
- **Music** and **Radio**. Music is a grid of your songs' covers; going right from the last song takes you back
  to the first. Now playing shows the cover big, with a soft glow in its colour. On a Pi 4 or 5 or a PC, bars
  beside it move with the music, a station's too, on a battery as well (where there's room under the name).
  A song's cover is a `cover.jpg` or `folder.jpg` in its folder, or the picture inside its
  file. For songs with neither, press Y on Music. Covers your other Pietatos have for the same songs (the same
  file name and size) are copied from them. The rest are looked up in the iTunes Store's search, then on
  [MusicBrainz](https://musicbrainz.org) and the Cover Art Archive (free, no account), by the song's name and
  who it's by: from its tags, or a file name like `Song - Artist.mp3` or `Artist - Song.mp3`. Only those names
  are sent, and the covers are kept on the Pi. On Now playing, Y goes round playing in order, shuffled, and
  the one song on repeat; SELECT puts on lofi art (a quiet scene on the whole screen), then on a Pi 4 or 5 or a
  PC Game beat (a dancer throwing glowing notes at glowing balls, all to the beat), and HOME has
  [Party mode](#party-mode), **Photos** (filters, delete), **Videos** (picks up where you left off)
- **Weather** (press START there to set where you are, and °F or °C), and **Finance**: stock and coin prices
  and charts. Press Y on Finance to look up more to add
- **Files**: PDFs, documents, text, pictures, video and music, on the Pi or on your other computers
- **Camera**: a USB camera plugged into the Pi, or a Raspberry Pi camera module on its ribbon (it shows up by
  itself, and on your other Pietatos under On your network), any camera on your network, or the ones on your other
  Pis: switch between them with L and R, steer an OBSBOT, take pictures, and have your bot say what it sees
- **Bot**: does what you ask, like setting a timer, adding to your list or playing some music, and chats
  through Ollama on another computer. It sees through your camera and takes pictures, and talks out loud if
  you give it a voice
- **Apps**: [Group chat](#group-chat), a [Sequencer](#sequencer), a [Band](#band), a
  Clock with the time and the date (A switches between a dial and big
  figures, ◀▶ go through a dozen fonts, ▲▼ change its colour, X its background, Y turns the date on or off, and
  START has its seconds) and a [Fish Tank](#fish-tank). Press SELECT to watch one full screen.
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
- **Settings**: WiFi (with a [Hotspot](#hotspot) for away from home), Bluetooth, the clock, battery saver, sound
  and controller, plus two pages that A opens and B closes. Appearance has the home screen's background and
  style, the accent color (one of eight, or Custom: your own, from its red, green and blue sliders), the apps'
  pages and full screen apps. Screen has the video size, a TV or monitor's
  resolution, turning the picture and what an OLED or e-ink HAT shows
- Settings > Appearance > Background changes the home screen's background: dark ones, colourful ones like
  Sunset, Candy and Arcade, pale ones like Sky, Peach and Mint, or a picture of yours. ◀▶ go through them, and
  A shows them all to pick from
- Settings > Appearance > App pages makes the pages inside the apps Light: pale pages with dark words, in
  place of the dark ones. The home screen keeps its background either way
- If you'd rather see the apps on the whole screen, set Settings > Appearance > Full screen apps to On. The
  status bar, the tabs and the button hints go away, leaving just the app's name at the top. The buttons work
  the same, and L and R still switch apps
- If your screen is mounted on its side or upside down, Settings > Screen > Rotate screen turns the picture
  to match: the apps, games, videos and the console
- With a Waveshare 2.23inch OLED HAT on the Pi's pins, Settings > Screen > Waveshare 2.23 OLED shows bars that
  move with your music, the time, the weather, prices or the Bot's face ([OLED screen](#oled-screen))
- With a Waveshare 2.13inch e-Paper HAT there instead, Settings > Screen > Waveshare 2.13 e-ink shows the time,
  the weather, prices and the Bot's face on paper ([E-ink screen](#e-ink-screen))
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

## Party mode

With two or more Pietatos on, HOME on Now playing has Party mode: each of your others that's on (and isn't in
a game, a video or the terminal) plays the same song or station at the same moment, through its own speaker.
Songs come from the one you started it on, and so does a station, so all of them play the same thing. A, ◀▶, L,
R and START on any of them pause it, move about in a song or skip, for all of them. Each keeps its own volume.
HOME's menu ends it on the one you started it on, and leaves it on the others. Settings > Share with other
Pietatos needs to be on.

One that's turned on later, or comes out of a game or a video, joins by itself within a few seconds and plays
from where the song is (a station starts again for all of them). One that missed a song is put right the same
way. One you took out with Leave the party stays out; to bring it back, play something on it and pick Join in
HOME's menu on Now playing, which has it while a party is going. Starting Party mode on another Pietato moves
them all to that one's party.

A Pietato in the party with a camera plugged into it is the party's bouncer. When its camera sees someone come
in, after nobody had moved for a while, it says what a bouncer at the door would in the [Group chat](#group-chat)
("Hold it. Are you on the list?"), no more than once every five minutes, and the others may answer. That pops up
on its screen like any line of theirs. These are words of their own: the Bot's model isn't asked. Y in Group
chat keeps them quiet, and SELECT there stops the camera looking.

## Hotspot

Away from your WiFi (off-road, say), one Pietato can make a WiFi of its own for the others: Settings > WiFi >
Hotspot, then ◀▶ to turn it on. Your other Pietatos join it by themselves, and Party mode, Group chat, the Fish
Tank, your cameras and the rest work as they do at home. Your own WiFi comes first, so once you turn the hotspot
off, they go back to it.

Its name and password are on that page, made up the first time you open it. A changes them while it's off.
They're the same on all your Pietatos, which pass them to each other while they're on your WiFi together, so do
that once before you leave (Settings > Share with other Pietatos needs to be on). A phone or a laptop joins with
the name and password shown there, and while it's on, the page says where a phone finds the web page. For an
ESP32's LEDs, put them in its sketch as well ([esp32](../esp32/README.md)).

The one making it isn't on your WiFi meanwhile, so it has no internet unless it has a cable. It stays on until
you turn it off, even through a restart. It's on 2.4 GHz, the only WiFi a Pi Zero 2 W and an ESP32 can join. The
web page's Settings > WiFi has it too.

## LED backlight

An 8x8 grid of WS2812B LEDs behind your TV, or a strip of them round its edges, can light up with the colours
along the edges of the game you're playing, on whichever of your Pietatos it follows. It flashes red when you're
hit, gold when you unlock an achievement, and pulses to music and to the [Soundboard](#sequencer)'s sounds. A hit
is a game's lives or health going down in its RetroAchievements rich presence, or a game shaking the controller, so
it shows in the games those cover.

To wire it to the Pi behind the TV (not one in a GPi Case, whose screen uses those pins), connect DIN to GPIO 10
(pin 19) and GND to a ground pin. Power the LEDs with 5 V from their own supply, since they can draw more than a
Pi gives, and join that supply's ground to the Pi's. Size the supply for a strip: each LED can draw up to 60 mA at
full white, though the brightness setting keeps it well under that. If the first LED flickers, a level shifter (a
74AHCT125) on DIN helps. Then open the web page's Library > LED backlight and set LEDs to On. The first time, it
turns on the Pi's SPI and asks you to restart.

That tab shows the LEDs as they're lit. Colour is theirs for whenever no game or music is lighting them: warm
white, white, red, orange, yellow, green, teal, blue, purple, pink or a rainbow. Off keeps them dark. Brightness
sets how bright they are, Follows which Pietato it follows (any of yours that's playing, by default, or Nobody to
keep it to your colour), and Pulse to music whether it pulses to music (the Soundboard's sounds go by that too).

Shape sets a grid or a strip. For a grid, Turn, Mirror and Wiring match how it's put up. For a strip, set how
many LEDs it has (up to 300), where its first LED is, which way it goes round as you look at the TV, and whether
it runs along the bottom too. Each LED then takes the colour of the edge of the screen nearest it. Which way is
up lights the top red and the left side green.

An ESP32 board's own LED can join in, with no wiring at all. Open `esp32/pietato_led/pietato_led.ino` in the
Arduino IDE, put your WiFi's name and password at the top, and upload it to the board (an ESP32-S3 dev board, or
any ESP32 with an RGB LED). [esp32/README.md](../esp32/README.md) has the steps, for this and for a strip or a
matrix board. It finds your Pietatos by itself: it pulses to the music whichever of them plays, and
takes a game's colours, a hit's red and an achievement's gold. While one of them leads a
[party](#party-mode), the boards pulse to the party's music: a Pietato that isn't in the party leaves them to
it. With Settings > Random song at start-up on, the
song is playing before the board is heard, so the first time the song skips for a moment as the board joins in;
after that the Pietato remembers it has boards, and they have the beat from the start. Its LED is amber while it
looks for your WiFi,
green for a couple of seconds once it's on it, and then dark till something plays. If it doesn't do that, the
Arduino IDE's Serial Monitor (at 115200) says what it's doing every ten seconds: whether it's on your WiFi, and
whether a Pietato is lighting it.

Any number of boards can do it at once, on any Pietato, with or without LEDs of its own. A beat is one small
packet to each board, and a game's colours go to a couple of them at a time, in turn, so they don't slow the Pi
down. The web page's LED backlight lists the boards it's found, and Pulse to music there is for the boards as well,
for music played on that Pietato. On a Pietato with no LEDs of its own, that tab is there once a board is found,
with just the boards and their settings.

The sketch can light a strip of WS2812B LEDs on one of the board's pins instead (with the FastLED library): set
`LED_COUNT` and `STRIP_PIN` at the top of it. Set `ONBOARD_PIN` to the pin of the board's own LED as well (48 on
most ESP32-S3 boards) and that lights with the strip. A long strip needs a 5 V supply of its own. However bright
you set it, it never takes more power than a white at the sketch's `BRIGHTNESS` does: allow about 2 A for every
100 LEDs at 90, and 6 A at 255. Raise `BRIGHTNESS` only as far as your supply and its wires can give.

With two or more boards, each can follow a different beat instead of all pulsing to the kick drum. Set ESP32
boards to Different beats on the web page's LED backlight. One board then follows the kick, the next the snare
and claps, the next the hi-hats, and round again, in the order of their names. The web page shows which follows
which. These are low, middle
and high parts of the sound rather than instruments, so a voice or a guitar can move the snare's board too. It's
set on each Pietato, for the music that one plays, and the boards' sketch stays as it is.

The web page's Library > LED backlight lists the boards it has found. Tap a colour for one and it's lit in that
instead of the colours of what's playing, still pulsing to the beat. Auto goes back to what's playing. The board
keeps its colour itself, so it's the same from every Pietato and after a power cut. Which one? lights a board
for a moment, to tell them apart. Each board has a Brightness slider too: it lights for a moment as you drag, so
you can see, and keeps where you leave it the same way. It starts at `BRIGHTNESS` in the sketch.

With music, a board can make its colours itself. Beside Auto, Per beat is a new colour on every beat, and Slow
goes round all the colours in about a minute. A board with a strip has Effect too: Pulse brightens the whole
strip on each beat, and Shoot sends each beat down the strip as a few bright LEDs. With Shoot and Per beat
together, each beat leaves the strip in its colour as it passes. Pick one with nothing playing and the board
shows you with a few beats of its own. The board does all of this itself from the beats it's already sent, so
it's no more work for the Pi, and it keeps what you pick. Boards on Per beat turn the same colours together. A
board that had the sketch before this needs it uploaded again first.

A Waveshare ESP32-S3-Matrix (an 8x8 square of LEDs on the board) has a sketch of its own instead:
`esp32/pietato_matrix/pietato_matrix.ino`. In the Arduino IDE, pick ESP32S3 Dev Module, set Tools > USB CDC On
Boot to Enabled, install the FastLED library, and upload it. The board makes a WiFi hotspot of its own, called
Pietato Matrix (its name and password are at the top of the sketch). Join that and open
`http://10.20.30.40:8000` for the board's page. Under Connection there, Join Wi-Fi puts the board on your WiFi
too. Your Pietatos then find it like any other board, and its page is at `http://matrix.local:8000` as well.

Its page picks what it shows: a liquid that pours as you tilt the board, fire, scrolling text, a picture you
paint, a few animations, and Music, which sends a ring out from the middle on each beat and shows a game's
colours while one's on. With Beat on, the other modes move with the music too. The BOOT button steps through
them. A Pietato's web page lists the board with the rest: its colour there is its Music colour, and its
Brightness slider is the board's own. Keep it dim, since that board gets hot when its LEDs are bright.

## OLED screen

A [Waveshare 2.23inch OLED HAT](https://www.waveshare.com/wiki/2.23inch_OLED_HAT) on the Pi can show bars that
move with your music, the time, the weather, prices or the Bot's face. Press the HAT onto the Pi's pins, wired as
it comes (SPI), and pick what it shows with ◀▶ on Settings > Screen > Waveshare 2.23 OLED. The first time, it
turns on the Pi's SPI if it isn't on, and asks you to restart.

- **Music bars**: bars that move with the music. While nothing plays, it shows the time.
- **Time**, **Weather**, **Prices**, **Face**: that one, whether music is playing or not. The weather is the
  Weather app's, for where you set it. Prices are your Finance app's stocks and coins, one at a time. The face
  is the Bot's, as its Character has it, and it blinks and looks around.
- **Each in turn**: the time, the weather, each price and the face, one after another.

A picture is a little dimmer than the bars, and moves a little each minute so it doesn't wear in.

While it's on, **OLED upside down** shows under it. It turns the picture round, for a Pi that sits the other way
up.

The setting is there on a Pi, with a TV on HDMI or with no screen at all (turn it on in the web page's Settings
then). It isn't on a Pi in a GPi Case, whose screen uses those pins, or on a PC or a handheld. The HAT uses the
pin an [LED backlight](#led-backlight)'s LEDs are wired to, so turning one on turns the other off. An
[e-ink HAT](#e-ink-screen) goes on the same pins, so that's one or the other too. ESP32 boards' LEDs work
alongside it.

About the bars:

- They follow songs and radio stations. Videos, games, the Sequencer app and the Band don't move them.
- When its own Pi isn't playing, they follow whichever of your other Pietatos is, as an LED backlight does. Both
  need Settings > Share with other Pietatos on. A song that was already playing when the OLED's Pi came on may
  not show: the next one does.
- They're the same at any volume.
- With the bars picked, music takes a moment longer to start: it plays through the player that knows when each
  sound is heard, as it does for an LED backlight's beat.

## E-ink screen

A [Waveshare 2.13inch e-Paper HAT](https://www.waveshare.com/wiki/2.13inch_e-Paper_HAT_Manual) on the Pi can show
the time, the weather, prices and the Bot's face on paper, which needs no light of its own. Press the HAT onto the
Pi's pins, and pick what it shows with ◀▶ on Settings > Screen > Waveshare 2.13 e-ink. The first time, it turns on
the Pi's SPI if it isn't on, and asks you to restart. It's for the V4 panel, the one sold now (it says so on a
label on its back). An older V3 isn't supported.

- **Everything**: the date and the weather along the top, the Bot's face and the time in the middle, and along
  the bottom the song that's playing, or two of your prices when nothing is.
- **Time**, **Weather**, **Prices**, **Face**: that one, on all of the paper. Weather has today's high and low and
  the next three days. Prices are your Finance app's stocks and coins, four at a time.
- **Each in turn**: those four, a minute each.

While it's on, **E-ink upside down** shows under it. It turns the picture round, for a Pi that sits the other way
up.

Paper is slow. What it shows changes about once a minute, and it flashes black and white now and then to clean
itself up: when you pick something, and every so often after that. Set to Off, it goes white first, since
whatever is left on paper stays there with the power off.

The setting is there on a Pi, with a TV on HDMI or with no screen at all (use the web page's Settings then). It
isn't on a Pi in a GPi Case, or on a PC or a handheld. The HAT uses the same pins as the [OLED HAT](#oled-screen),
and the pin an [LED backlight](#led-backlight)'s LEDs are wired to, so it's one of the three at a time: turning
one on turns the others off.

## Sequencer

Apps > Sequencer has three pages: the Sequencer, Bounce and the Soundboard. It opens on the Sequencer. R goes on
to the next (the Sequencer, then Bounce, then the Soundboard, round the three) and L goes back. The name of the page
you're on is at the top left. HOME goes back to Apps from any of them, and it opens again on the page you left.

The Sequencer is a grid of four sounds, a kick, a snare, a hi-hat and a lead, across the sixteen
steps of a bar. A cell that's on plays its row's sound as the bar comes round to it, at its tempo. The
d-pad moves from cell to cell, A turns one on or off, and B starts the tune and stops it. Each of the lead's cells
has a note, shown on it, and X changes it. On a drum's row, X changes the row's sound to another of your
Soundboard's. Y changes the tune a little, a few cells and a few notes, as often as you like, and SELECT changes
the scale. The cells that are on are lit in your accent colour, the steps are numbered over the grid, and the
column that's playing is lit. Along the top are four buttons: Tempo, Key, Scale and Lead (the lead's sound). A
narrow screen shows just what each is set to. Press ▲ from the top row to reach them, ◀▶ to go from one to the next, and A to change it;
tapping one does the same. Under the grid, bars show the sound as it plays, low notes at the left.

The first tune a Pietato has is made from its name, so each of yours starts with its own. START's card there has
the tempo, the volume, the key and scale (Bounce's too, so the two sound right together), the lead's sound, A new
tune and Clear all. The tune plays on under the Soundboard's buttons and under Bounce, in time with a loop you
record there, and holding START on the buttons' page stops it with the rest. It's kept for next time.

Bounce is a shape turning slowly, with balls bouncing inside it, both in your accent colour.
Each wall is a note of a scale, so whatever's hit sounds right together, and a ball that hits a wall plays its note
and lights it up. A ball that hits a wall straight on plays louder than one that only grazes it, and you hear it
from the side it hits. A adds a ball and B takes one away (up to 8). X changes the sound, Y the scale (major,
minor, pentatonic or blues) and SELECT the key, so what you hear is a button away.

Its sliders are on the right: ▲▼ pick one and ◀▶ move it, and the line under them says what the one picked does.
Spin turns the shape either way, Speed is how fast the balls go, Reverb puts the notes in a room or a big hall, Echo
plays each note again, from side to side, in time with the tempo, Tone makes them darker (◀) or brighter (▶), and
Drone holds a soft note in the key under them. START pauses it, and its card has the shape (a triangle, a square,
a pentagon or a hexagon: more sides, more notes), the sound (a bell, a marimba, a kalimba, glass, a pluck, a pad,
or any sound on your Soundboard, played at each wall's note), the key, the scale and Snap to the tempo (each note
on the loop's beat). Your LEDs, if you have them, flash in the same colour.

The Soundboard puts a sound on every button. The buttons are in your accent colour, like the Sequencer's cells,
and turn lighter while their sound plays. The d-pad's four and A, B, X and Y each play theirs, as many at
once as you like, and one pressed again starts again. SELECT goes through the banks of eight, and holding START
stops them all. B is a button like the others there, so HOME is the way back. On this page,
the bank is at the top right. START's card also has the bank, the volume, the loop's settings and Reverb, which plays the sounds in a room or a hall. The
sounds play wherever Settings > Sound sends them.

START's card records a loop. Record a loop is its first row, so it's START, then A. Play some buttons, then
press START and A again (the row says Stop recording now): what you played goes round and round, each hit moved
to the nearest sixteenth note. Add to the loop, in the same place, records another layer on top of it. Drop the
last layer, at the end of the card (START, ▲, A), takes the last one back, and holding START clears the loop.
While you record, a quiet click counts the beats. The card also has the tempo, the loop's length (1, 2 or 4
bars), Snap to the beat and Click while recording. The loop plays while the Sequencer app is open, and it's still
there when you come back to it.

Hold A, B, X or Y for a moment and the d-pad plays that button's sound as notes: ▲ a note higher, ▼ a note lower,
▶ the same note again and ◀ the sound's own. The note shows on the button, and notes go into a loop like any
other sound. They follow a scale, Major, Minor or Pentatonic (Notes, on START's card), up to an octave either way.
Buttons pressed together quickly, as drums are, each play their own sound.

With Settings > Share with other Pietatos on, your Pietatos that have the Sequencer app open share one tempo and one
beat, so their loops keep time together. A new tempo on one of them goes to all of them, and one that opens the
Sequencer app takes the beat of the ones already playing. A Pietato on its own keeps its own beat, and one leaving
changes nothing for the others.

If you have an [LED backlight](#led-backlight) or ESP32 boards, each sound lights them as music does: a pulse in
a colour of its button's own (each button has one for the LEDs) as the sound starts, and that colour while it
plays. Pulse to music, on the web page's LED
backlight, turns that off too.

It comes with four banks of starter sounds: Starter, Drums, Arcade and Calm. Calm is the soft one: a kalimba, a
marimba, a bell, a glass, a plucked string, a pad, a singing bowl and wind chimes, all in one key, so any of them
sound right together. A bank that comes with an update is added to yours by itself, once, and the Soundboard says
so; delete it and it stays away. Your own are wav, mp3 or ogg files in the `Soundboard` folder of your home folder.
Put one there and a moment later it's on the first free button of a bank called My sounds.

With a USB microphone plugged in, START's card has Record a sound. Press A when you're done, and the silence
before and after is trimmed. Then press the button it should go on: L and R pick another bank first, SELECT
plays it back, and START can record it again or delete it.

The web page's Library has a Soundboard tab that adds, records, renames and deletes sounds, adds banks, and puts
sounds on buttons: drag one onto a button or a bank, or on a phone tap the sound, then the button. Recording there
uses the phone's or computer's microphone, on the secure page. The tab also shows the loop, with its tempo,
length, snapping and click to change. What you change is on the Pietato's Soundboard at once. Which sound is on
which button is kept in `static/soundboard.txt`.

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
note there, so HOME is the way back (START, then B, works too). START's card also has the song (Rock, Blues, Funk
or Chill), the tempo and the volume. With others in the band it has Timing too: a TV or a Bluetooth speaker takes a
moment with its sound, so if one Pietato sounds behind the rest, ◀ on Timing there plays it a little earlier.

Each player decides what to do with its next four bars: play its part, play busier or simpler, sit out, play a
fill or take a solo. Dice decide that. With a [Bot](bot.md) set up and a decision model on its computer, the
model decides instead, and START's card has Who decides to pick the model or go back to dice. The model is asked
four bars ahead, and the band never waits for it.

## Fish Tank

Each Pietato has a fish of its own in Apps > Fish Tank. With two or more on the same network, their tanks join up
into one big tank, and the fish swim from one to the next. A calls your fish back, X feeds it, and START picks the
fish and the light.

When you open it, the names of the tanks next door show at the edges they're through for a few seconds, then go.

The web page's Library has a Fish Tank too, with every tank at once. Tap a tank to feed it, or press Arrange and
drag the tanks into a grid: side by side, one above another, or both. Fish swim between tanks that touch, with the
water's surface along the top. Settings > Share with other Pietatos needs to be on.

If your screens have frames, or space between them, Arrange's Space between screens sliders set how much, as a
share of a screen's width (Across) and height (Down). A fish keeps swimming through that space unseen, so it comes
out on the next screen where it would through real glass.
