# ESP32 boards

An ESP32 board can light up with your Pietatos over WiFi. It pulses to the music one of them plays, takes a
game's colours, and flashes red for a hit and gold for an achievement. There's nothing to set up on the
Pietatos: a board says it's there, and whichever Pietato is playing lights it. Any number of boards can join in.

There are two sketches here. Use the one for your board:

- [`pietato_led`](pietato_led/pietato_led.ino): an ESP32 with an RGB LED on it (an ESP32-S3 dev board, say), or
  one with a strip of WS2812B LEDs wired to it.
- [`pietato_matrix`](pietato_matrix/pietato_matrix.ino): a Waveshare ESP32-S3-Matrix, the board with an 8x8
  square of LEDs.

## What you need

- The [Arduino IDE](https://www.arduino.cc/en/software), with the esp32 boards added: Tools > Board > Boards
  Manager, search for esp32, and install the one by Espressif Systems. If it isn't listed,
  [Espressif's guide](https://docs.espressif.com/projects/arduino-esp32/en/latest/installing.html) has the link
  to add.
- The FastLED library, for a strip or the matrix: Tools > Manage Libraries, search for FastLED.
- A 2.4 GHz WiFi, the one your Pietatos are on. An ESP32 can't join a 5 GHz one.

## A board's own LED, or a strip: `pietato_led`

1. Open `pietato_led/pietato_led.ino` in the Arduino IDE.
2. Put your WiFi's name and password in `WIFI_NAME` and `WIFI_PASSWORD`, at the top.
3. Pick your board under Tools > Board (ESP32S3 Dev Module for an ESP32-S3 dev board), and its port.
4. Upload.

The LED is amber while it looks for your WiFi, green for a couple of seconds once it's on it, then dark until
something plays on a Pietato.

To take it away from home too, put your Pietatos' [hotspot](../docs/apps.md#hotspot) in `HOTSPOT_NAME` and
`HOTSPOT_PASSWORD` (Settings > WiFi > Hotspot on a Pietato shows them). With no WiFi found, the board looks for
your WiFi and the hotspot in turn, half a minute each.

For a strip, set these at the top as well, before you upload:

- `LED_COUNT`: how many LEDs the strip has.
- `STRIP_PIN`: the pin its DIN wire is on (5, unless you change it).
- `ONBOARD_PIN`: the pin of the board's own LED, if you want that lit too (48 on most ESP32-S3 boards).

Wire the strip's DIN to that pin and its GND to the board's GND. A long strip needs a 5 V supply of its own,
with the supply's GND joined to the board's as well. However bright you set it, the strip never takes more
power than a white at the sketch's `BRIGHTNESS` does: allow about 2 A for every 100 LEDs at 90, and 6 A at 255.

If it doesn't work:

- Open Tools > Serial Monitor, at 115200. Every ten seconds the board says what it's doing.
- Amber and nothing more: it can't get on your WiFi. Check the name and password, and that it's a 2.4 GHz one.
- The board's own LED never lights: set `ONBOARD_PIN` to its pin (48 on most ESP32-S3 boards, 38 on some).
  Some boards also need the pair of pads marked RGB beside it joined with a blob of solder.

## A Waveshare ESP32-S3-Matrix: `pietato_matrix`

1. Open `pietato_matrix/pietato_matrix.ino` in the Arduino IDE.
2. Pick ESP32S3 Dev Module under Tools > Board, and set Tools > USB CDC On Boot to Enabled.
3. Upload.
4. The board makes a WiFi hotspot of its own, called Pietato Matrix. Join it from your phone or computer (its
   password is `AP_PASS`, at the top of the sketch) and open `http://10.20.30.40:8000`.
5. On that page, under Connection, tap Join Wi-Fi and pick your own WiFi. Your Pietatos find the board from
   then on, and its page is at `http://matrix.local:8000` too.

For away from home, put your Pietatos' [hotspot](../docs/apps.md#hotspot) in `HOTSPOT_SSID` and `HOTSPOT_PASS`
at the top of the sketch before you upload. With no WiFi found, the board tries your WiFi and the hotspot in turn,
a minute each.

Its page picks what the board shows: a liquid that pours as you tilt it, fire, scrolling text, a picture you
paint, a few animations, and Music, which follows your Pietatos. The BOOT button steps through them. Keep the
brightness low: that board gets hot when its LEDs are bright.

## On a Pietato

The web page's Library > LED backlight lists the boards it has found. You can give each one a colour and set
how bright it is there, and a `pietato_led` board has effects for music too.
[LED backlight](../docs/apps.md#led-backlight) in the docs has the rest.

After you update Pietato, a `pietato_led` board may need its sketch uploaded again. The web page says so
beside that board.

If you share your copy of a sketch, take your WiFi's name and password out of it first.
