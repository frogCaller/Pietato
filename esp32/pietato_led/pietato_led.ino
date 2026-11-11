/*
  Pietato LED: an ESP32's own light, lit by your Pietatos over WiFi.

  It pulses to the music one of them plays, takes the colours of a game, flashes red when you're hit and gold
  for an achievement. There's nothing to set up on the Pietatos: the board says it's there every couple of
  seconds, and whichever of them is playing lights it. As many boards as you like can do this at once.

  To put it on a board (an ESP32-S3 dev board, or any ESP32 with an RGB LED):
    1. In the Arduino IDE, pick your board (ESP32S3 Dev Module, say).
    2. Put your WiFi's name and password below (a 2.4 GHz one: an ESP32 doesn't do 5 GHz).
    3. Upload.
  The LED glows a dim amber while it looks for your WiFi, then green for a moment once it's on it, and goes
  dark till something plays. Apps > LED backlight on a Pietato shows how many boards it's found.

  If the LED never lights: set ONBOARD_PIN below to its pin (48 on most ESP32-S3 boards, 38 on some), and look
  for a pair of pads marked RGB beside it, which some boards need joined with a blob of solder.

  A strip or a ring of WS2812B LEDs instead of the board's own: set LED_COUNT to how many it has and STRIP_PIN
  to the pin its DIN is on, and install the FastLED library. All of its LEDs show the same colour.
*/
#include <WiFi.h>
#include <WiFiUdp.h>
#include <math.h>
#include <string.h>
#include "esp_timer.h"

// ---- yours to set -------------------------------------------------------------------------------------------
const char *WIFI_NAME = "your WiFi's name";
const char *WIFI_PASSWORD = "its password";

#define LED_COUNT 1          // 1: the board's own LED. More: a strip of WS2812B LEDs on STRIP_PIN (needs FastLED)
#define ONBOARD_PIN -1       // the board's own LED: -1 for where the board says it is, or its pin (48, or 38 on some)
#define STRIP_PIN 5          // a strip's DIN
#define BRIGHTNESS 90        // how bright it gets at most, 0 to 255
const uint8_t IDLE_COLOUR[3] = {0, 0, 0};   // its colour while nothing's playing (0, 0, 0: dark)

// ---- the rest -------------------------------------------------------------------------------------------------
#if LED_COUNT > 1
#include <FastLED.h>
CRGB leds[LED_COUNT];
#endif

const uint16_t GLOW_PORT = 5448;    // a Pietato's colours and beats come here (UDP)
const uint16_t LAMP_PORT = 5449;    // ...and this says it's there, to that port on every Pietato
const double HELLO_EVERY = 2.0;     // seconds between saying so
const double WIFI_AGAIN = 30.0;     // seconds looking for your WiFi before it's asked for again
const double SOURCE_HOLD = 2.5;     // seconds the Pietato it's following is kept, once it's quiet
const double KEEP = 1.5;            // seconds a colour is kept with no more of it, before its own colour again
const double FRAMES_APART = 5.0;    // a game's colours come 30 times a second, or with a lot of boards only now and
                                    // then: further apart than this, it's a game starting again
const double FRAME_TAU = 0.06, MUSIC_TAU = 0.18, IDLE_TAU = 0.5;   // seconds its colour takes to follow
const double MUSIC_BASE = 0.4;      // music's colour, between beats
const double BEAT_TAU = 0.12, BEAT_GAIN = 1.6;   // a beat: how fast it dies away, and how much brighter
const double HIT_SECS = 0.5, GOLD_SECS = 1.4;    // a hit's red, an achievement's gold: how long they take to go
const double LED_GAMMA = 2.2;       // an LED's brightness as it's seen
const double EVENT_KEEP = 3.0;      // seconds something that's happened is kept
const int EVENTS_MOST = 12;

enum { BEAT = 1, HIT = 2, CHEEVO = 3 };
struct LampEvent { double at; uint8_t kind; float strength; };

WiFiUDP udp;
bool listening = false;
double helloAt = -1e9;
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

void light(uint8_t r, uint8_t g, uint8_t b) {       // (the LED, or every LED of a strip, that colour)
  if (r == lit[0] && g == lit[1] && b == lit[2]) return;
  lit[0] = r; lit[1] = g; lit[2] = b;
#if LED_COUNT > 1
  fill_solid(leds, LED_COUNT, CRGB(r, g, b));
  FastLED.show();
#else
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

// A packet from a Pietato: "PG", a version, what it is (F: a picture's colours; E: something happening; M: music's
// colour), when it was sent by that one's clock, then the rest.
void take(const uint8_t *data, int n, IPAddress from, double now) {
  if (n < 12 || data[0] != 'P' || data[1] != 'G' || data[2] != 1) return;
  const char kind = (char)data[3];
  if (kind != 'F' && kind != 'E' && kind != 'M') return;
  const double sent = beDouble(data + 4);
  if (!aNumber(sent)) return;
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
    for (int k = 0; k < 3; k++) music[k] = rest[k];
    musicAt = now;
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
  } else if (kind == 'E' && left > 9) {
    const double at = beDouble(rest) + offset;      // (when it shows, by this one's clock)
    const float strength = rest[8] / 255.0f;
    const char *name = (const char *)rest + 9;
    const int len = left - 9;
    uint8_t what = 0;
    if (len == 4 && !memcmp(name, "beat", 4)) what = BEAT;
    else if (len == 3 && !memcmp(name, "hit", 3)) what = HIT;
    else if (len == 6 && !memcmp(name, "cheevo", 6)) what = CHEEVO;
    if (!what || !aNumber(at)) return;
    if (eventCount == EVENTS_MOST) {                // (full: the oldest goes)
      memmove(events, events + 1, sizeof(LampEvent) * (EVENTS_MOST - 1));
      eventCount--;
    }
    events[eventCount].at = at > now - 0.05 ? at : now - 0.05;
    events[eventCount].kind = what;
    events[eventCount].strength = strength;
    eventCount++;
  }
}

// Its colour now: the picture's, or music's between beats, or its own; a beat brighter, a hit red, an
// achievement gold, each dying away.
void draw(double now) {
  double dt = now - drawnAt;
  if (dt < 0) dt = 0;
  if (dt > 0.5) dt = 0.5;
  drawnAt = now;
  float goal[3];
  double tau;
  const double frameKeep = frameEvery * 3 + 0.5 > KEEP ? frameEvery * 3 + 0.5 : KEEP;
  if (now - frameAt < frameKeep) {                  // (a game's: from one to the next as smoothly as they come)
    for (int k = 0; k < 3; k++) goal[k] = frame[k];
    tau = frameEvery * 0.7 > FRAME_TAU ? frameEvery * 0.7 : FRAME_TAU;
  } else if (now - musicAt < KEEP) {
    for (int k = 0; k < 3; k++) goal[k] = music[k] * MUSIC_BASE;
    tau = MUSIC_TAU;
  } else {
    for (int k = 0; k < 3; k++) goal[k] = IDLE_COLOUR[k];
    tau = IDLE_TAU;
  }
  const float follow = 1.0f - (float)exp(-dt / tau);
  float out[3];
  for (int k = 0; k < 3; k++) { shown[k] += (goal[k] - shown[k]) * follow; out[k] = shown[k]; }
  int kept = 0;
  for (int i = 0; i < eventCount; i++) {
    const double age = now - events[i].at;
    if (age >= EVENT_KEEP) continue;                // (over: let go of)
    events[kept++] = events[i];
    if (age < 0) continue;                          // (not yet)
    const float s = events[i].strength;
    if (events[i].kind == BEAT) {
      const float p = s * (float)exp(-age / BEAT_TAU);
      for (int k = 0; k < 3; k++) out[k] = out[k] * (1 + BEAT_GAIN * p) + 60 * p;
    } else if (events[i].kind == HIT && age < HIT_SECS) {
      const float r = s * (float)pow(1 - age / HIT_SECS, 2);
      const float red[3] = {255, 0, 0};
      for (int k = 0; k < 3; k++) out[k] = out[k] * (1 - r) + red[k] * r;
    } else if (events[i].kind == CHEEVO && age < GOLD_SECS) {
      const float g = 1 - (float)(age / GOLD_SECS);
      const float gold[3] = {255, 180, 30};
      for (int k = 0; k < 3; k++) out[k] = out[k] * (1 - g) + gold[k] * g;
    }
  }
  eventCount = kept;
  uint8_t rgb[3];
  for (int k = 0; k < 3; k++) {
    float v = out[k] < 0 ? 0 : out[k] > 255 ? 255 : out[k];
    v = (float)pow(v / 255.0, LED_GAMMA) * BRIGHTNESS;   // (as it's seen: an LED's half is far brighter than half)
    rgb[k] = (uint8_t)(v + 0.5f);
  }
  light(rgb[0], rgb[1], rgb[2]);
}

// "I'm here", to every Pietato on your network: "PG", the version, L, this one's clock, its LEDs, its name.
void hello(double now) {
  uint8_t msg[12 + 2 + 24];
  msg[0] = 'P'; msg[1] = 'G'; msg[2] = 1; msg[3] = 'L';
  putBeDouble(msg + 4, now);
  msg[12] = (LED_COUNT >> 8) & 0xFF; msg[13] = LED_COUNT & 0xFF;
  uint8_t mac[6];
  WiFi.macAddress(mac);
  char name[24];
  const int len = snprintf(name, sizeof name, "ESP32 %02X%02X%02X", mac[3], mac[4], mac[5]);
  memcpy(msg + 14, name, len);
  const IPAddress ip = WiFi.localIP(), mask = WiFi.subnetMask();
  const IPAddress everyone(ip[0] | (uint8_t)~mask[0], ip[1] | (uint8_t)~mask[1], ip[2] | (uint8_t)~mask[2],
                           ip[3] | (uint8_t)~mask[3]);
  udp.beginPacket(everyone, LAMP_PORT);
  udp.write(msg, 14 + len);
  udp.endPacket();
}

void setup() {
#if LED_COUNT > 1
  FastLED.addLeds<WS2812B, STRIP_PIN, GRB>(leds, LED_COUNT);
#endif
  light(0, 0, 0);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);                             // (awake: a beat comes when it's sent, not a moment after)
  WiFi.begin(WIFI_NAME, WIFI_PASSWORD);
  askedAt = seconds();
}

void loop() {
  const double now = seconds();
  if (WiFi.status() != WL_CONNECTED) {              // (looking for your WiFi: a dim amber)
    if (listening) { listening = false; askedAt = now; }   // (just lost: the board looks for it itself, at first)
    if (now - askedAt >= WIFI_AGAIN) {              // (a while with no luck: asked for again)
      askedAt = now;
      WiFi.disconnect();
      WiFi.begin(WIFI_NAME, WIFI_PASSWORD);
    }
    light(10, 5, 0);
    delay(100);
    return;
  }
  if (!listening) {                                 // (on it: green for a moment, fading to its own colour)
    udp.begin(GLOW_PORT);
    listening = true;
    helloAt = -1e9;
    askedAt = now;
    shown[0] = 0; shown[1] = 140; shown[2] = 0;
    drawnAt = now;
    lit[0] = lit[1] = lit[2] = 1;
  }
  if (now - helloAt >= HELLO_EVERY) { helloAt = now; hello(now); }
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
