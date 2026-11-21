/*
  Pietato LED: an ESP32's own light, lit by your Pietatos over WiFi.

  It pulses to the music one of them plays (and to its Soundboard's sounds), takes the colours of a game, flashes
  red when you're hit and gold for an achievement. There's nothing to set up on the Pietatos: the board says it's
  there every couple of seconds, and whichever of them is playing lights it. As many boards as you like can do this
  at once.

  To put it on a board (an ESP32-S3 dev board, or any ESP32 with an RGB LED):
    1. In the Arduino IDE, pick your board (ESP32S3 Dev Module, say).
    2. Put your WiFi's name and password below (a 2.4 GHz one: an ESP32 doesn't do 5 GHz).
    3. Upload.
  The LED glows a dim amber while it looks for your WiFi, then green for a couple of seconds once it's on it,
  and goes dark till something plays on a Pietato (music, or a game). A Pietato's web page lists the boards
  it's found (Library > LED backlight), and you can give each a colour of its own there: the board keeps it,
  and pulses in it whatever's playing. How bright it is is set there too (it starts at BRIGHTNESS below), and
  kept the same way. Which one? there lights a board for a moment. And with music it can do more than pulse,
  chosen there as well: its colour a new one on each beat (Per beat) or one that changes slowly (Slow), and on
  a strip, each beat shot down it instead of the whole of it pulsing (Shoot).

  If it doesn't do that, the Serial Monitor says what it's doing, every ten seconds (Tools > Serial Monitor, at
  115200). Amber and no further: it can't get on your WiFi (its name or password, or it's too far away).

  If the LED never lights: set ONBOARD_PIN below to its pin (48 on most ESP32-S3 boards, 38 on some), and look
  for a pair of pads marked RGB beside it, which some boards need joined with a blob of solder.

  A strip or a ring of WS2812B LEDs instead of the board's own: set LED_COUNT to how many it has and STRIP_PIN
  to the pin its DIN is on, and install the FastLED library. All of its LEDs show the same colour, but for the
  beats shot down it if you choose that. For the board's own LED lit with them, give ONBOARD_PIN its pin too.
  A long strip needs a power supply of its own: however bright it's set, it never takes more from it than a
  white at BRIGHTNESS does (allow 2 A for every 100 LEDs at 90, and 6 A at 255), so raise BRIGHTNESS only as far
  as your supply and its wires can give.

  A Waveshare ESP32-S3-Matrix (an 8x8 square of LEDs) has a sketch of its own, not this one: esp32/pietato_matrix.
*/
#include <WiFi.h>
#include <WiFiUdp.h>
#include <Preferences.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "esp_timer.h"

// ---- yours to set -------------------------------------------------------------------------------------------
const char *WIFI_NAME = "your WiFi's name";
const char *WIFI_PASSWORD = "its password";

#define LED_COUNT 1          // 1: the board's own LED. More: a strip of WS2812B LEDs on STRIP_PIN (needs FastLED)

#if LED_COUNT > 1                       // (FastLED, read here, before the names below: it has a BRIGHTNESS of its
#pragma push_macro("LED_COUNT")         //  own, and may come to have more of them)
#undef LED_COUNT
#include <FastLED.h>
#pragma pop_macro("LED_COUNT")
#endif

#define ONBOARD_PIN -1       // the board's own LED: -1 for where the board says it is, or its pin (48, or 38 on some).
                             // With a strip: lit as well, if its pin's given here (-1: just the strip)
#define STRIP_PIN 5          // a strip's DIN
#define BRIGHTNESS 90        // how bright it is, 0 to 255, to start with (a Pietato's web page can change it). A
                             // strip never takes more power than a white at this, however bright it's set
const uint8_t IDLE_COLOUR[3] = {0, 0, 0};   // its colour while nothing's playing (0, 0, 0: dark)

// ---- the rest -------------------------------------------------------------------------------------------------
#define STRIP_ORDER GRB             // (a strip: green first; and never more power than a white at BRIGHTNESS takes,
                                    //  however bright it's set)
#define MOST_MILLIAMPS (BOARD_MA + (long)DARK_MA * LED_COUNT \
                        + (long)BRIGHTNESS * (RED_MA + GREEN_MA + BLUE_MA) * LED_COUNT / 255)
#if LED_COUNT > 1
CRGB leds[LED_COUNT];
#endif
#if LED_COUNT > 1 && ONBOARD_PIN >= 0 && ONBOARD_PIN != STRIP_PIN
#define BOARD_LED_TOO 1             // (a strip, and the board's own LED given its pin: lit with it, the same colour)
CRGB boardLed[1];
#endif

const uint16_t GLOW_PORT = 5448;    // a Pietato's colours and beats come here (UDP)
const uint16_t LAMP_PORT = 5449;    // ...and this says it's there, to that port on every Pietato
const double HELLO_EVERY = 2.0;     // seconds between saying so
const double SAY_BACK = 0.25;       // ...or sooner, its colour just set: but never less than this apart
const double WIFI_AGAIN = 30.0;     // seconds looking for your WiFi before it's asked for again
const double SOURCE_HOLD = 2.5;     // seconds the Pietato it's following is kept, once it's quiet
const double KEEP = 1.5;            // seconds a colour is kept with no more of it, before it's as with nothing playing
const double FRAMES_APART = 5.0;    // a game's colours come 30 times a second, or with a lot of boards only now and
                                    // then: further apart than this, it's a game starting again
const double FRAME_TAU = 0.06, MUSIC_TAU = 0.18, IDLE_TAU = 0.5;   // seconds its colour takes to follow
const double MUSIC_BASE = 0.4;      // music's colour, between beats
const double BEAT_TAU = 0.12, BEAT_GAIN = 1.6;   // a beat: how fast it dies away, and how much brighter
const double HIT_SECS = 0.5, GOLD_SECS = 1.4;    // a hit's red, an achievement's gold: how long they take to go
const double LED_GAMMA = 2.2;       // an LED's brightness as it's seen
const double EVENT_KEEP = 3.0;      // seconds something that's happened is kept
const int EVENTS_MOST = 12;
const double STRIP_AGAIN = 0.5;     // seconds between tellings of a strip's LEDs what they already show
const double SHOW_SECS = 2.0;       // seconds it shows its colour, when that's set (or it's asked which one it is)
const double SHOW_TAU = 0.08;
const double JOINED_SECS = 1.5;     // seconds it's green, once it's on your WiFi (then it fades)
const float JOINED[3] = {0, 140, 0};
const double SAY_EVERY = 10.0;      // seconds between a line for the Serial Monitor, of how it is
const double SAY_SOON = 1.0;        // ...or this, something having changed
const double QUIET = 10.0;          // seconds with nothing from a Pietato: the next is one beginning to light it
const int RED_MA = 16, GREEN_MA = 11, BLUE_MA = 15;   // mA: an LED's red, green and blue, each at its brightest
const int BOARD_MA = 25, DARK_MA = 1;                 // ...the board itself, and an LED that's dark
const double KEEP_AFTER = 1.0;      // seconds its colour has stood before it's kept (not each step of one being picked)
const float SHOW_PLAIN[3] = {160, 160, 160};   // ...a board with no colour of its own: white
const double COLOURS_ROUND = 60.0;  // seconds music's colour takes to go all the way round, when it changes slowly
const double TRY_SECS = 2.6;        // seconds an effect's shown for, set with nothing playing: a few beats of its own
#if LED_COUNT > 1                   // A beat shot down a strip: along its LEDs, all the way in SHOT_SECS (a long
const float SHOT_WAY = (float)LED_COUNT;            // strip: two seconds), a few LEDs long (SHOT_TAIL), fading behind
const float SHOT_SECS = SHOT_WAY < 36 ? 0.6f : SHOT_WAY > 120 ? 2.0f : SHOT_WAY / 60;
const float SHOT_TAIL = SHOT_WAY < 50 ? 2.5f : SHOT_WAY > 320 ? 16.0f : SHOT_WAY / 20;
#endif

enum { BEAT = 1, HIT = 2, CHEEVO = 3 };
enum { KEEP_COLOUR = 1, KEEP_BRIGHT = 2, KEEP_EFFECT = 4 };   // (what's still to be kept: any of them)
enum { SHOOT = 1, HUES_BEAT = 2, HUES_SLOW = 4 };   // how it shows music, added up: a beat's shot down a strip (not
                                    // the whole of it pulsing); its colour's a new one each beat, or changes slowly
struct LampEvent { double at; uint8_t kind; float strength; float hue; };   // (hue: a beat's own colour, HUES_BEAT)

WiFiUDP udp;
bool listening = false;
double helloAt = -1e9;
bool owed = false;                  // (it's to say how it is, as soon as it may)
double askedAt = 0;                 // when your WiFi was last asked for
IPAddress source;                   // the Pietato it's following
bool following = false;
double offset = 0;                  // its clock, less that one's (the quickest packet's: nearest the truth)
double heardAt = -1e9;              // when that one was last heard
double frameAt = -1e9, musicAt = -1e9;
double frameEvery = 0;              // seconds between a game's colours, lately (0: the first of them)
float frame[3] = {0, 0, 0}, music[3] = {0, 0, 0};
float shown[3] = {0, 0, 0};
LampEvent events[EVENTS_MOST];
int eventCount = 0;
double drawnAt = 0;
uint8_t lit[3] = {1, 1, 1};         // (what the LED was last sent: sent again only when it changes)
bool ownOn = false;                 // a colour of its own (a Pietato's web page sets it): lit in that, whatever's
uint8_t own[3] = {0, 0, 0};         // playing. Kept through a power cut
uint8_t ownBright = BRIGHTNESS;     // ...and how bright it is, 0 to 255: set there too, and kept the same way
uint8_t ownEffect = 0;              // ...and how it shows music (SHOOT, HUES_BEAT or HUES_SLOW, added up): the same
double showUntil = -1e9;            // its colour's shown till then, when either's just been set
double tryUntil = -1e9;             // ...and an effect, set with nothing playing, with beats of its own till then
uint8_t toKeep = 0;                 // ...and what's still to be kept (KEEP_COLOUR, KEEP_BRIGHT, KEEP_EFFECT), at keepAt
double keepAt = 0;
float beatHue = 0, hueNow = 0;      // a colour each beat: the last beat's that's been taken in, and the last one's
double hueAt = -1e9;                // to come due (when, here), as an angle round the colours
float musicLevel = 0;               // how far music's colour has come in, 0 to 1
#if LED_COUNT > 1
float leftHue = -1;                 // ...and the one the last shot to get there left a strip's far end in (-1: none
                                    // has yet)
bool eachLit = false;               // (a strip's LEDs were last told one by one: they're not all the colour lit[] has)
float seenAs[256];                  // (an LED's brightness as it's seen, for each it can be asked for: worked out once)
#endif
Preferences store;
double joinedAt = -1e9;             // when it got on your WiFi
double litAt = -1e9;                // when a Pietato last lit it (a packet of its taken in), and which one
IPAddress litFrom;
double saidAt = -1e9;               // when the Serial Monitor was last told how it is
bool toSay = false;                 // ...and it's to be told again soon: something's changed

double seconds() { return esp_timer_get_time() / 1e6; }

bool aNumber(double v) { return v == v && v - v == 0; }   // (not one that's no number at all, or endless)

double beDouble(const uint8_t *p) {                 // (eight bytes, the biggest first, as a Pietato sends a number)
  uint64_t v = 0;
  for (int i = 0; i < 8; i++) v = (v << 8) | p[i];
  double d;
  memcpy(&d, &v, sizeof d);
  return d;
}

void putBeDouble(uint8_t *p, double d) {
  uint64_t v;
  memcpy(&v, &d, sizeof v);
  for (int i = 7; i >= 0; i--) { p[i] = v & 0xFF; v >>= 8; }
}

void keepColour() {                                 // (its own colour, kept: written only when it's changed)
  store.begin("pietato", false);
  store.putUInt("colour", ownOn ? (0x01000000u | ((uint32_t)own[0] << 16) | ((uint32_t)own[1] << 8) | own[2]) : 0);
  store.end();
}

void keepBright() {                                 // (...and its brightness, with the BRIGHTNESS it was set from)
  store.begin("pietato", false);
  store.putUInt("bright", 0x01000000u | ((uint32_t)(uint8_t)BRIGHTNESS << 8) | ownBright);
  store.end();
}

void keepEffect() {                                 // (...and how it shows music)
  store.begin("pietato", false);
  store.putUInt("effect", 0x01000000u | ownEffect);
  store.end();
}

bool anEffect(uint32_t v) {                         // (one it has: not both of the two its colour can be, and on a
  if (v > 5) return false;                          //  board with the one LED, nothing shot)
  return LED_COUNT > 1 || !(v & SHOOT);
}

void readKept() {                                   // (...and as they were kept. Its brightness, if BRIGHTNESS has been
  store.begin("pietato", false);                    //  changed in the sketch since: the sketch's, then)
  const uint32_t v = store.getUInt("colour", 0);
  const uint32_t b = store.getUInt("bright", 0);
  const uint32_t x = store.getUInt("effect", 0);
  store.end();
  ownOn = (v >> 24) == 1;
  own[0] = (v >> 16) & 0xFF; own[1] = (v >> 8) & 0xFF; own[2] = v & 0xFF;
  if ((b >> 24) == 1 && ((b >> 8) & 0xFF) == (uint32_t)(uint8_t)BRIGHTNESS) ownBright = b & 0xFF;
  if ((x >> 24) == 1 && anEffect(x & 0xFFFFFF)) ownEffect = x & 0xFF;
  if (ownOn) ownEffect &= SHOOT;                    // (a colour of its own: not colours of its own making as well)
}

void hueColour(float angle, float *rgb) {           // (an angle round the colours, 0 to 360: its red, green and blue,
  const float h = angle / 60.0f;                    //  at their fullest)
  const int part = (int)h % 6;
  const float up = (h - (int)h) * 255.0f, down = 255.0f - up;
  const float six[6][3] = {{255, up, 0}, {down, 255, 0}, {0, 255, up}, {0, down, 255}, {up, 0, 255}, {255, 0, down}};
  for (int k = 0; k < 3; k++) rgb[k] = six[part][k];
}

// A beat's own colour (HUES_BEAT), from when it is by the Pietato's clock: so every board that hears that beat turns
// the same colour. Never one close to the beat's before (a board that missed that one is with the rest again in a
// beat or two).
float hueOf(double there) {
  float h = (float)fmod(floor(there * 20.0) * 137.508, 360.0);
  if (!(h >= 0)) h = 0;
  float apart = (float)fabs(h - beatHue);
  if (apart > 180) apart = 360 - apart;
  if (apart < 60) h = (float)fmod(h + 150.0, 360.0);
  return h;
}

// Music's colour, when it's the effect's and not what's playing or the board's own: the last beat's (HUES_BEAT), or
// one that goes slowly round (HUES_SLOW: by the Pietato's clock too, so every board's the same). False: it's neither.
bool effectHue(double now, float *rgb) {
  if (ownEffect & HUES_BEAT) { hueColour(hueNow, rgb); return true; }
  if (!(ownEffect & HUES_SLOW)) return false;
  float h = (float)fmod((following ? now - offset : now) * (360.0 / COLOURS_ROUND), 360.0);
  if (!(h >= 0)) h = 0;
  hueColour(h, rgb);
  return true;
}

// Something that's happened, to show at its time (at, by this board's clock; there: by the Pietato's): the oldest
// goes, if there's no room.
void addEvent(double at, uint8_t kind, float strength, double there, double now) {
  if (eventCount == EVENTS_MOST) {
    memmove(events, events + 1, sizeof(LampEvent) * (EVENTS_MOST - 1));
    eventCount--;
  }
  events[eventCount].at = at > now - 0.05 ? at : now - 0.05;
  events[eventCount].kind = kind;
  events[eventCount].strength = strength;
  events[eventCount].hue = kind == BEAT ? (beatHue = hueOf(there)) : 0;
  eventCount++;
}

int boardName(char *name, size_t room) {            // ("ESP32 A1B2C3": the end of its address, as a Pietato lists it)
  uint8_t mac[6];
  WiFi.macAddress(mac);
  return snprintf(name, room, "ESP32 %02X%02X%02X", mac[3], mac[4], mac[5]);
}

// How it is, in a line for the Serial Monitor (115200): what it lights, whether it's on your WiFi, and whether a
// Pietato's lighting it. Said every ten seconds, and when that changes; never waited for.
void sayHowItIs(double now) {
  if (!Serial) return;
  char what[96], line[448];
#if defined(BOARD_LED_TOO)
  snprintf(what, sizeof what, "a strip, %d LEDs on pin %d, and the board's own LED on pin %d", LED_COUNT, STRIP_PIN,
           ONBOARD_PIN);
#elif LED_COUNT > 1
  snprintf(what, sizeof what, "a strip, %d LEDs on pin %d", LED_COUNT, STRIP_PIN);
#elif ONBOARD_PIN >= 0
  snprintf(what, sizeof what, "the board's own LED, on pin %d", ONBOARD_PIN);
#else
  snprintf(what, sizeof what, "the board's own LED");
#endif
  const int status = WiFi.status();
  if (status != WL_CONNECTED) {
    snprintf(line, sizeof line, "Pietato LED (%s): looking for the WiFi \"%s\"%s", what, WIFI_NAME,
             status == WL_NO_SSID_AVAIL ? ". There's none of that name here (an ESP32 only sees 2.4 GHz ones)"
             : status == WL_CONNECT_FAILED ? ". It's there, but the password wasn't taken" : "");
  } else {
    char name[24], colour[48] = "", dim[48] = "", fx[80] = "", by[64] = "dark till something plays on a Pietato";
    boardName(name, sizeof name);
    const IPAddress ip = WiFi.localIP();
    const bool byOne = now - litAt < SOURCE_HOLD;
    if (byOne) {
      snprintf(by, sizeof by, "lit by the Pietato at %d.%d.%d.%d", litFrom[0], litFrom[1], litFrom[2], litFrom[3]);
    }
    if (ownOn && byOne) snprintf(colour, sizeof colour, ", in its own colour (#%02x%02x%02x)", own[0], own[1], own[2]);
    else if (ownOn) snprintf(colour, sizeof colour, " (then in its own colour, #%02x%02x%02x)", own[0], own[1], own[2]);
    if (ownBright != (uint8_t)BRIGHTNESS) {         // (set on a Pietato's web page: said, as 0 is why it's dark)
      snprintf(dim, sizeof dim, "; its brightness set to %d of 255", ownBright);
    }
    if (ownEffect) {                                // (...and how it shows music, when that's more than pulsing)
      const char *hues = ownEffect & HUES_BEAT ? " in a new colour each beat"
                         : ownEffect & HUES_SLOW ? " in colours that change slowly" : "";
      snprintf(fx, sizeof fx, "; with music, %s%s", ownEffect & SHOOT ? "beats shoot down it" : "it pulses", hues);
    }
    snprintf(line, sizeof line, "Pietato LED (%s): on your WiFi as %d.%d.%d.%d, \"%s\" to your Pietatos; %s%s%s%s",
             what, ip[0], ip[1], ip[2], ip[3], name, by, colour, dim, fx);
  }
  Serial.println(line);
}

void light(uint8_t r, uint8_t g, uint8_t b) {       // (the LED, or every LED of a strip, that colour)
#if LED_COUNT > 1
  static double toldAt = -1e9;                      // (a strip's told again now and then, changed or not: with the
  const double now = seconds();                     //  WiFi busy a telling can go astray, and wouldn't be put right)
  {                                                 // (a colour that would take more than MOST_MILLIAMPS between
    const long takes = ((long)r * RED_MA + (long)g * GREEN_MA + (long)b * BLUE_MA) * LED_COUNT / 255;   // them is
    const long room = MOST_MILLIAMPS - BOARD_MA - (long)DARK_MA * LED_COUNT;                //  dimmed to fit: a
    if (takes > 0 && takes > room) {                                                        //  white, mostly)
      const long fits = room > 0 ? room : 0;
      r = (uint8_t)(r * fits / takes); g = (uint8_t)(g * fits / takes); b = (uint8_t)(b * fits / takes);
    }
  }
  if (!eachLit && r == lit[0] && g == lit[1] && b == lit[2] && now - toldAt < STRIP_AGAIN) return;
  toldAt = now;
  eachLit = false;
  lit[0] = r; lit[1] = g; lit[2] = b;
  for (int i = 0; i < LED_COUNT; i++) leds[i] = CRGB(r, g, b);
#ifdef BOARD_LED_TOO
  boardLed[0] = CRGB(r, g, b);
#endif
  FastLED.show();
#else
  if (r == lit[0] && g == lit[1] && b == lit[2]) return;
  lit[0] = r; lit[1] = g; lit[2] = b;
  #if ONBOARD_PIN >= 0
  const int pin = ONBOARD_PIN;
  #elif defined(RGB_BUILTIN)
  const int pin = RGB_BUILTIN;
  #else
  const int pin = 48;
  #endif
  #if defined(ESP_ARDUINO_VERSION) && ESP_ARDUINO_VERSION >= ESP_ARDUINO_VERSION_VAL(3, 0, 5)
  rgbLedWrite(pin, r, g, b);                        // (what the board's software calls it, from 3.0.5 on)
  #else
  neopixelWrite(pin, r, g, b);                      // (...and what it called it before)
  #endif
#endif
}

#if LED_COUNT > 1
// A strip with its beats shot down it (SHOOT): each LED its own colour. under: what all of it would be with no beat
// (as it is before it's dimmed for the LEDs); a beat is a few LEDs of what it brightens (lift) at its brightest, on
// their way from the first LED to the last, fading behind. With a colour each beat (HUES_BEAT) a shot's the colour of
// its beat, and leaves the LEDs it has passed in it: so with music (playing: it's what's lit now) an LED's the colour
// of the last shot to pass it, each new colour wiped along it. A hit's red and an achievement's gold lie over all of it
// (through, wash: what's left of the rest, and what's added). The board's own LED, beside a strip, pulses as ever
// (board: its colour). Never more power than light() lets a strip take. False: nothing's on its way and it's all the
// one colour, which is light()'s to show.
bool shots(double now, bool playing, const float *under, const float *lift, float through, const float *wash,
           const uint8_t *board) {
  struct Shot { float head, hue, its[3], peak[3]; };
  Shot shot[EVENTS_MOST];                           // (the newest first)
  int count = 0;
  bool flying = false;
  const bool each = ownEffect & HUES_BEAT;
  for (int i = eventCount - 1; i >= 0; i--) {
    if (events[i].kind != BEAT || events[i].at > now) continue;
    Shot &s = shot[count++];
    s.head = (float)(now - events[i].at) * (SHOT_WAY / SHOT_SECS);
    s.hue = events[i].hue;
    if (s.head < SHOT_WAY + SHOT_TAIL) flying = true;
    float full[3] = {0, 0, 0};
    if (each) hueColour(s.hue, full);
    for (int k = 0; k < 3; k++) {
      s.its[k] = each ? full[k] * (float)MUSIC_BASE : lift[k];
      const float v = s.its[k] * (1 + (float)BEAT_GAIN * events[i].strength) + 60 * events[i].strength;
      s.peak[k] = v > 255 ? 255 : v;
    }
  }
  if (!flying && !(each && musicLevel > 0.004f)) return false;
  float rest[3], ahead[3] = {0, 0, 0};              // (rest: what's lit but music, as music's colour comes and goes.
  for (int k = 0; k < 3; k++) rest[k] = each ? playing ? 0 : under[k] * (1 - musicLevel) : under[k];
  if (each) {                                       //  ahead: where no shot it knows of has been, as the last to get
    for (int j = 0; j < count; j++) if (shot[j].head >= SHOT_WAY) { leftHue = shot[j].hue; break; }   // there left it)
    hueColour(leftHue >= 0 ? leftHue : hueNow, ahead);
    for (int k = 0; k < 3; k++) ahead[k] *= (float)MUSIC_BASE;
  }
  long takes = 0;
  uint32_t sum = 2166136261u;                       // (what's told, as a number: told again only when it's changed)
  for (int p = 0; p < (int)SHOT_WAY; p++) {
    float c[3] = {rest[0], rest[1], rest[2]};
    if (each) {
      const float *left = ahead;                    // (the last to pass this LED: its colour)
      for (int j = 0; j < count; j++) if (shot[j].head >= p) { left = shot[j].its; break; }
      for (int k = 0; k < 3; k++) c[k] += left[k] * musicLevel;
    }
    for (int j = 0; j < count; j++) {
      const float d = shot[j].head - p;             // (how far behind a shot's first LED this one is)
      if (d <= -1 || d >= SHOT_TAIL) continue;
      const float w = d < 0 ? 1 + d : (1 - d / SHOT_TAIL) * (1 - d / SHOT_TAIL);
      for (int k = 0; k < 3; k++) c[k] += (shot[j].peak[k] - c[k]) * w;
    }
    uint8_t rgb[3];
    for (int k = 0; k < 3; k++) {
      float v = c[k] * through + wash[k];
      v = v < 0 ? 0 : v > 255 ? 255 : v;
      rgb[k] = (uint8_t)(seenAs[(uint8_t)(v + 0.5f)] * ownBright + 0.5f);
      sum = (sum ^ rgb[k]) * 16777619u;
    }
    leds[p] = CRGB(rgb[0], rgb[1], rgb[2]);
    takes += (long)rgb[0] * RED_MA + (long)rgb[1] * GREEN_MA + (long)rgb[2] * BLUE_MA;
  }
  {                                                 // (more than a strip's to take: all of it dimmed to fit)
    takes /= 255;
    const long room = MOST_MILLIAMPS - BOARD_MA - (long)DARK_MA * LED_COUNT;
    if (takes > 0 && takes > room) {
      const long fits = room > 0 ? room : 0;
      for (int i = 0; i < LED_COUNT; i++) {
        leds[i] = CRGB((uint8_t)(leds[i].r * fits / takes), (uint8_t)(leds[i].g * fits / takes),
                       (uint8_t)(leds[i].b * fits / takes));
      }
    }
  }
  for (int k = 0; k < 3; k++) sum = (sum ^ board[k]) * 16777619u;
  static double toldAt = -1e9;
  static uint32_t toldSum = 0;
  if (eachLit && sum == toldSum && now - toldAt < STRIP_AGAIN) return true;
  toldAt = now;
  toldSum = sum;
  eachLit = true;
#ifdef BOARD_LED_TOO
  boardLed[0] = CRGB(board[0], board[1], board[2]);
#endif
  FastLED.show();
  return true;
}
#endif

void litBy(double now) {                            // (a packet of a Pietato's taken in: that one's lighting it.
  if (now - litAt > QUIET || !(litFrom == source)) toSay = true;   // The Serial Monitor's told, when one begins to)
  litAt = now;
  litFrom = source;
}

// A packet from a Pietato: "PG", a version, what it is (F: a picture's colours; E: something happening; M: music's
// colour; C: this board's own colour; B: how bright it's to be; X: how it's to show music), when it was sent by that
// one's clock, then the rest.
void take(const uint8_t *data, int n, IPAddress from, double now) {
  if (n < 12 || data[0] != 'P' || data[1] != 'G' || data[2] != 1) return;
  const char kind = (char)data[3];
  if (kind != 'F' && kind != 'E' && kind != 'M' && kind != 'C' && kind != 'B' && kind != 'X') return;
  const double sent = beDouble(data + 4);
  if (!aNumber(sent)) return;
  if (kind == 'X') {                                // (how it's to show music: SHOOT, HUES_BEAT or HUES_SLOW, added up.
    if (n != 13 || !anEffect(data[12])) return;     // From any of your Pietatos, as its colour is: said back, and kept
    if (data[12] != ownEffect) {                    // once it's stood a second. With nothing playing it's shown with
      ownEffect = data[12];                         // a few beats of its own, so you can see)
      toKeep |= KEEP_EFFECT;
      keepAt = now + KEEP_AFTER;
    }
    if (ownOn && (ownEffect & (HUES_BEAT | HUES_SLOW))) {   // (colours of its own making: it has those in place of
      ownOn = false;                                //  a colour of its own, not as well)
      own[0] = own[1] = own[2] = 0;
      toKeep |= KEEP_COLOUR;
      keepAt = now + KEEP_AFTER;
    }
    showUntil = -1e9;
    if (now - musicAt >= KEEP && now - frameAt >= KEEP) {
      eventCount = 0;                               // (told again, as each thing is said twice: from the start, not
      tryUntil = now + TRY_SECS;                    //  twice over. Shot down a strip: till the last has got there)
#if LED_COUNT > 1
      if (ownEffect & SHOOT) tryUntil += SHOT_SECS;
#endif
      for (int k = 0; k < 4; k++) addEvent(now + 0.1 + k * 0.6, BEAT, 1.0f, now + k, now);
    }
    owed = true;
    toSay = true;
    return;
  }
  if (kind == 'B') {                                // (how bright it's to be, 0 to 255. From any of your Pietatos, as
    if (n != 13) return;                            // its colour is: that's shown a moment so you can see, it's said
    if (data[12] != ownBright) {                    // back, and kept once it's stood a second)
      ownBright = data[12];
      toKeep |= KEEP_BRIGHT;
      keepAt = now + KEEP_AFTER;
    }
    showUntil = now + SHOW_SECS;
    owed = true;
    toSay = true;
    return;
  }
  if (kind == 'C') {                                // (its own colour: 1 and the colour, or 0 for none. From any
    if (n != 16 || data[12] > 1) return;            // of your Pietatos, whichever it's following: shown a moment,
    const bool on = data[12] == 1;                  // said back, and kept once it's stood a second)
    const uint8_t none[3] = {0, 0, 0};
    const uint8_t *rgb = on ? data + 13 : none;
    if (on != ownOn || memcmp(own, rgb, 3)) {
      ownOn = on;
      memcpy(own, rgb, 3);
      toKeep |= KEEP_COLOUR;
      keepAt = now + KEEP_AFTER;
    }
    if (on && (ownEffect & (HUES_BEAT | HUES_SLOW))) {   // (a colour of its own: music's in that again, not in
      ownEffect &= SHOOT;                           //  colours of its own making)
      toKeep |= KEEP_EFFECT;
      keepAt = now + KEEP_AFTER;
    }
    showUntil = now + SHOW_SECS;
    owed = true;
    toSay = true;
    return;
  }
  const double off = now - sent;
  if (!following || !(from == source)) {
    if (following && now - heardAt < SOURCE_HOLD) return;   // (another's being followed: still playing)
    source = from; following = true; offset = off; eventCount = 0;
  } else {
    offset += 0.0001 * (now - heardAt);             // (the two clocks drift apart a little: the quickest lately)
    if (off < offset || off > offset + 5.0) offset = off;
  }
  heardAt = now;
  const uint8_t *rest = data + 12;
  const int left = n - 12;
  if (kind == 'M' && left == 3) {
    if (now - musicAt >= KEEP) {                    // (music beginning. A colour each beat: the one it begins in is
      float h = (float)fmod(sent * (360.0 / COLOURS_ROUND), 360.0);   // from when that is by the Pietato's clock,
      if (!(h >= 0)) h = 0;                         //  and each beat's goes on from it: so all your boards begin
      hueNow = beatHue = h;                         //  alike, whatever each showed before)
#if LED_COUNT > 1
      leftHue = -1;
#endif
    }
    for (int k = 0; k < 3; k++) music[k] = rest[k];
    musicAt = now;
    litBy(now);
  } else if (kind == 'F' && left >= 2) {            // (a picture's edges, as a grid of colours: their blend)
    const int count = rest[0] * rest[1];
    const int have = (left - 2) / 3 < count ? (left - 2) / 3 : count;
    if (have < 1) return;
    uint32_t sum[3] = {0, 0, 0};
    for (int i = 0; i < have; i++) for (int k = 0; k < 3; k++) sum[k] += rest[2 + i * 3 + k];
    for (int k = 0; k < 3; k++) frame[k] = (float)sum[k] / have;
    const double gap = now - frameAt;                // (how often they come)
    frameEvery = gap >= FRAMES_APART ? 0 : frameEvery > 0 ? (frameEvery + gap) / 2 : gap;
    frameAt = now;
    litBy(now);
  } else if (kind == 'E' && left > 9) {
    const double there = beDouble(rest);            // (when it is, by the Pietato's clock)
    const double at = there + offset;               // (...and so when it shows, by this one's)
    const float strength = rest[8] / 255.0f;
    const char *name = (const char *)rest + 9;
    const int len = left - 9;
    uint8_t what = 0;
    if (len == 4 && !memcmp(name, "beat", 4)) what = BEAT;
    else if (len == 3 && !memcmp(name, "hit", 3)) what = HIT;
    else if (len == 6 && !memcmp(name, "cheevo", 6)) what = CHEEVO;
    if (!what || !aNumber(at)) return;
    addEvent(at, what, strength, there, now);
    litBy(now);
  }
}

// Its colour now: the picture's, or music's between beats (its own colour instead of either, if it has one), or
// dark (green first, just on your WiFi); a beat brighter, a hit red, an achievement gold, each dying away. Music's
// colour can be the effect's instead (a new one each beat, or one that changes slowly), and on a strip a beat can be
// shot down it, where the whole of it grew brighter (shots()).
void draw(double now) {
  double dt = now - drawnAt;
  if (dt < 0) dt = 0;
  if (dt > 0.5) dt = 0.5;
  drawnAt = now;
  bool turned = false;                              // (a colour each beat: a beat's just come due, and it's that one's)
  if (ownEffect & HUES_BEAT) {
    for (int i = 0; i < eventCount; i++) {
      if (events[i].kind != BEAT || events[i].at > now || events[i].at <= hueAt) continue;
#if LED_COUNT > 1
      if (leftHue < 0) leftHue = hueNow;            // (a strip no shot's got to the end of yet: as it was, till then)
#endif
      hueAt = events[i].at;
      hueNow = events[i].hue;
      turned = true;
    }
  }
  float goal[3];
  double tau;
  bool coming = false;                              // (music's colour: its goal is what a beat brightens)
  const double frameKeep = frameEvery * 3 + 0.5 > KEEP ? frameEvery * 3 + 0.5 : KEEP;
  if (now < showUntil) {                            // (its colour just set, or which one it is asked: shown)
    for (int k = 0; k < 3; k++) goal[k] = ownOn ? own[k] : SHOW_PLAIN[k];
    tau = SHOW_TAU;
  } else if (now - frameAt < frameKeep) {           // (a game's: from one to the next as smoothly as they come)
    for (int k = 0; k < 3; k++) goal[k] = ownOn ? own[k] : frame[k];
    tau = frameEvery * 0.7 > FRAME_TAU ? frameEvery * 0.7 : FRAME_TAU;
  } else if (now - musicAt < KEEP || now < tryUntil) {   // (music; or an effect being tried, with nothing playing:
    float hue[3];                                   //  white then, if the board has no colour)
    const bool hued = effectHue(now, hue);
    for (int k = 0; k < 3; k++) {
      goal[k] = (hued ? hue[k] : ownOn ? own[k] : now - musicAt < KEEP ? music[k] : SHOW_PLAIN[k]) * MUSIC_BASE;
    }
    tau = MUSIC_TAU;
    coming = true;
  } else if (now - joinedAt < JOINED_SECS) {        // (just on your WiFi: green, so you can tell)
    for (int k = 0; k < 3; k++) goal[k] = JOINED[k];
    tau = SHOW_TAU;
  } else {
    for (int k = 0; k < 3; k++) goal[k] = IDLE_COLOUR[k];
    tau = IDLE_TAU;
  }
  const float follow = 1.0f - (float)exp(-dt / tau);
  musicLevel += ((coming ? 1.0f : 0.0f) - musicLevel) * follow;
  float out[3], lift[3];                            // (lift: what a beat brightens. Music's colour as it will be
  for (int k = 0; k < 3; k++) {                     // once it's come in, so a beat that comes with the first of it,
    if (turned && coming) shown[k] = goal[k];       // a Soundboard's sound, is as bright as any. A new colour for a
    shown[k] += (goal[k] - shown[k]) * follow;      // beat: at once, on the beat)
    out[k] = shown[k];
    lift[k] = coming && goal[k] > shown[k] ? goal[k] : shown[k];
  }
  float through = 1, wash[3] = {0, 0, 0};           // (a hit's red and an achievement's gold, as they lie over a strip
  int kept = 0;                                     //  lit LED by LED: what's left of its colour, and what's added)
  for (int i = 0; i < eventCount; i++) {
    const double age = now - events[i].at;
    if (age >= EVENT_KEEP) continue;                // (over: let go of)
    events[kept++] = events[i];
    if (age < 0) continue;                          // (not yet)
    const float s = events[i].strength;
    if (events[i].kind == BEAT) {
      const float p = s * (float)exp(-age / BEAT_TAU);
      for (int k = 0; k < 3; k++) out[k] = out[k] + lift[k] * BEAT_GAIN * p + 60 * p;
    } else if (events[i].kind == HIT && age < HIT_SECS) {
      const float r = s * (float)pow(1 - age / HIT_SECS, 2);
      const float red[3] = {255, 0, 0};
      for (int k = 0; k < 3; k++) out[k] = out[k] * (1 - r) + red[k] * r;
      for (int k = 0; k < 3; k++) wash[k] = wash[k] * (1 - r) + red[k] * r;
      through *= 1 - r;
    } else if (events[i].kind == CHEEVO && age < GOLD_SECS) {
      const float g = 1 - (float)(age / GOLD_SECS);
      const float gold[3] = {255, 180, 30};
      for (int k = 0; k < 3; k++) out[k] = out[k] * (1 - g) + gold[k] * g;
      for (int k = 0; k < 3; k++) wash[k] = wash[k] * (1 - g) + gold[k] * g;
      through *= 1 - g;
    }
  }
  eventCount = kept;
  uint8_t rgb[3];
  for (int k = 0; k < 3; k++) {
    float v = out[k] < 0 ? 0 : out[k] > 255 ? 255 : out[k];
    v = (float)pow(v / 255.0, LED_GAMMA) * ownBright;   // (as it's seen: an LED's half is far brighter than half)
    rgb[k] = (uint8_t)(v + 0.5f);
  }
#if LED_COUNT > 1
  if ((ownEffect & SHOOT) && shots(now, coming, shown, lift, through, wash, rgb)) return;
#endif
  light(rgb[0], rgb[1], rgb[2]);
}

// "I'm here", to every Pietato on your network: "PG", the version, L, this one's clock, its LEDs, its name. Then
// how bright it is (B: 0 to 255), how it shows music (X: SHOOT, HUES_BEAT or HUES_SLOW, added up), and how it is
// (S): 7 (it keeps a colour of its own, 1, a brightness, 2, and how it shows music, 4), whether it has a colour (1
// or 0), and the colour.
void hello(double now) {
  uint8_t msg[12 + 2 + 24];
  msg[0] = 'P'; msg[1] = 'G'; msg[2] = 1; msg[3] = 'L';
  putBeDouble(msg + 4, now);
  msg[12] = (LED_COUNT >> 8) & 0xFF; msg[13] = LED_COUNT & 0xFF;
  char name[24];
  const int len = boardName(name, sizeof name);
  memcpy(msg + 14, name, len);
  const IPAddress ip = WiFi.localIP(), mask = WiFi.subnetMask();
  const IPAddress everyone(ip[0] | (uint8_t)~mask[0], ip[1] | (uint8_t)~mask[1], ip[2] | (uint8_t)~mask[2],
                           ip[3] | (uint8_t)~mask[3]);
  udp.beginPacket(everyone, LAMP_PORT);
  udp.write(msg, 14 + len);
  udp.endPacket();
  msg[3] = 'B';
  msg[12] = ownBright;
  udp.beginPacket(everyone, LAMP_PORT);
  udp.write(msg, 13);
  udp.endPacket();
  msg[3] = 'X';
  msg[12] = ownEffect;
  udp.beginPacket(everyone, LAMP_PORT);
  udp.write(msg, 13);
  udp.endPacket();
  msg[3] = 'S';
  msg[12] = 7; msg[13] = ownOn ? 1 : 0;
  memcpy(msg + 14, own, 3);
  udp.beginPacket(everyone, LAMP_PORT);
  udp.write(msg, 17);
  udp.endPacket();
}

void setup() {
  Serial.begin(115200);
#if LED_COUNT > 1                                   // (set up as a board with them is known to take it. Each colour
  FastLED.addLeds<WS2812, STRIP_PIN, STRIP_ORDER>(leds, LED_COUNT);   // goes out as light() gives it, dimmed there:
#ifdef BOARD_LED_TOO                                //  FastLED isn't to dim it, or to make it flicker between two
  FastLED.addLeds<WS2812, ONBOARD_PIN, GRB>(boardLed, 1);   // levels, which it does to a colour sent often. The board's
#endif                                              //  own LED, with a strip: green first, as such are, and set up
  FastLED.setBrightness(255);                       //  before FastLED's told not to, which it says only to the
  FastLED.setDither(0);                             //  LEDs it has by then)
  for (int i = 0; i < 256; i++) seenAs[i] = (float)pow(i / 255.0, LED_GAMMA);
#endif
  readKept();
  light(0, 0, 0);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);                             // (awake: a beat comes when it's sent, not a moment after)
  WiFi.begin(WIFI_NAME, WIFI_PASSWORD);
  askedAt = seconds();
}

void loop() {
  const double now = seconds();
  if (now - saidAt >= SAY_EVERY || (toSay && now - saidAt >= SAY_SOON)) {   // (the Serial Monitor: how it is)
    saidAt = now; toSay = false;
    sayHowItIs(now);
  }
  if (WiFi.status() != WL_CONNECTED) {              // (looking for your WiFi: a dim amber)
    if (listening) { listening = false; askedAt = now; toSay = true; }   // (just lost: the board looks itself, at first)
    if (now - askedAt >= WIFI_AGAIN) {              // (a while with no luck: asked for again)
      askedAt = now;
      WiFi.disconnect();
      WiFi.begin(WIFI_NAME, WIFI_PASSWORD);
    }
    light(10, 5, 0);
    delay(100);
    return;
  }
  if (!listening) {                                 // (on it: green for a moment, then what's playing, or dark)
    udp.begin(GLOW_PORT);
    listening = true;
    helloAt = -1e9;
    askedAt = now;
    for (int k = 0; k < 3; k++) shown[k] = JOINED[k];
    joinedAt = now;
    drawnAt = now;
    lit[0] = lit[1] = lit[2] = 1;
    toSay = true;
  }
  if (now - helloAt >= HELLO_EVERY || (owed && now - helloAt >= SAY_BACK)) { helloAt = now; owed = false; hello(now); }
  if (toKeep && now >= keepAt) {
    if (toKeep & KEEP_COLOUR) keepColour();
    if (toKeep & KEEP_BRIGHT) keepBright();
    if (toKeep & KEEP_EFFECT) keepEffect();
    toKeep = 0;
  }
  static uint8_t data[1500];
  for (int tries = 0; tries < 16; tries++) {        // (what's come since the last look)
    const int size = udp.parsePacket();
    if (size <= 0) break;
    const int n = udp.read(data, sizeof data);
    if (n > 0) take(data, n, udp.remoteIP(), seconds());
  }
  draw(seconds());
  delay(5);
}
