"""An ESP32's own LED lit by your Pietatos (esp32/pietato_led, and glow.py's Lamps). The sketch itself, built here
with stand-ins for the board (its WiFi, its clock, its LED: what the LED's sent is noted) and run by its own loop:
looking for the WiFi it's a dim amber, and says nothing; on it, it says it's there every couple of seconds, to everyone
on its network, in words a Pietato takes (and only from your network: a light's listened for there, kept while it
keeps saying so). Lit by a Pietato's own packets (glow.py makes them): music's colour between beats, a beat at the
moment it's due by the sender's clock (not before), a game's colours (their blend), a hit's red, an achievement's
gold, dark again once it's quiet; nothing for a packet that isn't one; one Pietato followed at a time. A strip of LEDs
instead: all of them that colour. Then media mode: a light found is one of the places a game's colours and music's
beats go, and music's played for its beat while one's there (unless Pulse to music is off: Apps > LED backlight has
that, on a Pietato with no LEDs of its own too while a board's on); the song at start-up, which begins before the
network's up and any board's heard (moved to that player once one is, and on it from the start the next time, the
boards remembered); however many there are, a
game's pictures go to a couple of them at a time, in turn (a beat to all at once), and a board that gets them only now
and then keeps its colour between them. A colour of its own: told it by a Pietato (the web page's LED backlight), it
shows it a moment, says it back at once, keeps it through a power cut (written only when it changes), and is lit in
it whatever's playing (music's beats on it, a hit's red over it); told none, it takes what's playing again; a Pietato
reads what it says of itself, lists the boards by name with their colours, and tells only one that's there and keeps
one. A Waveshare ESP32-S3-Matrix: its 64 LEDs on pin 14, red first, set up the way such a board is known to work
(FastLED's WS2812, and nothing asked of FastLED but to send each colour as it is), dim, and never more than 300 mA
(the sketch's own sum: a white's dimmed to fit). FastLED read before the sketch's own settings (it has a BRIGHTNESS
of its own), and a strip told again every half second. On your WiFi it's green for a second and a half, and the
Serial Monitor is told how it is every ten seconds and when that changes (what it lights, whether it's on your
WiFi and why not, which Pietato is lighting it, its own colour): a line a second at most, none with no one
listening. Its page in Apps on a Pietato with no LEDs of its own: your boards drawn in its box, an LED each, and
never full screen (it would be a black one)."""
import asyncio, json, logging, os, shutil, socket, subprocess, sys, threading, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
sys.path.insert(0, TESTS)
import numpy as np
import pietato_all as g
import pitato.glow as G

S = SP + "/t_esp32"
shutil.rmtree(S, ignore_errors=True)
os.makedirs(S + "/board")
ok_all = []


def check(what, cond):
    ok_all.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + what, flush=True)


SKETCH = ROOT + "/esp32/pietato_led/pietato_led.ino"
# the board, as far as the sketch uses it: its clock (which goes on only as the sketch waits), its WiFi and UDP
# (packets in from a list, packets out noted), and its LED (each colour it's sent noted)
open(S + "/board/Arduino.h", "w").write(r'''
#pragma once
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <deque>
#include <string>
#include <vector>
extern double NOW;
extern bool ON_WIFI;
extern int WHY_NOT;                 // (what its WiFi says of itself while it isn't on one: 6, looking; 1, none of
                                    //  that name; 4, the password wasn't taken)
inline long long esp_timer_get_time() { return (long long)llround(NOW * 1e6); }
inline void delay(int ms) { NOW += ms / 1000.0; }
#define RGB_BUILTIN 97
#define WL_NO_SSID_AVAIL 1
#define WL_CONNECTED 3
#define WL_CONNECT_FAILED 4
#define WIFI_STA 1
struct SerialClass {                // (the Serial Monitor: each line it's sent noted, if one's listening)
  bool there = true;
  void begin(unsigned long speed) { printf("SB %lu\n", speed); }
  explicit operator bool() const { return there; }
  void println(const char *s) { printf("# %.4f %s\n", NOW, s); }
};
extern SerialClass Serial;
struct IPAddress {
  uint8_t b[4];
  IPAddress() : b{0, 0, 0, 0} {}
  IPAddress(uint8_t a, uint8_t c, uint8_t d, uint8_t e) : b{a, c, d, e} {}
  uint8_t operator[](int i) const { return b[i]; }
  bool operator==(const IPAddress &o) const { return !memcmp(b, o.b, 4); }
};
struct WiFiClass {
  int status() { return ON_WIFI ? WL_CONNECTED : WHY_NOT; }
  void mode(int) {}
  void setSleep(bool) {}
  void begin(const char *name, const char *) { printf("W %.4f %s\n", NOW, name); }
  void disconnect() {}
  IPAddress localIP() { return IPAddress(10, 0, 0, 77); }
  IPAddress subnetMask() { return IPAddress(255, 255, 255, 0); }
  void macAddress(uint8_t *m) { const uint8_t mac[6] = {0x24, 0x6F, 0x28, 0xA1, 0xB2, 0xC3}; memcpy(m, mac, 6); }
};
extern WiFiClass WiFi;
struct Packet { IPAddress from; std::vector<uint8_t> data; };
extern std::deque<Packet> INBOX;
struct WiFiUDP {
  Packet cur; IPAddress to; uint16_t port = 0; std::vector<uint8_t> out; int begun = 0;
  int begin(uint16_t p) { begun = p; printf("B %.4f %d\n", NOW, p); return 1; }
  int parsePacket() { if (INBOX.empty()) return 0; cur = INBOX.front(); INBOX.pop_front(); return (int)cur.data.size(); }
  int read(uint8_t *buf, size_t n) { size_t k = cur.data.size() < n ? cur.data.size() : n; memcpy(buf, cur.data.data(), k); return (int)k; }
  IPAddress remoteIP() { return cur.from; }
  int beginPacket(IPAddress ip, uint16_t p) { to = ip; port = p; out.clear(); return 1; }
  size_t write(const uint8_t *buf, size_t n) { out.insert(out.end(), buf, buf + n); return n; }
  int endPacket() {
    printf("S %.4f %d.%d.%d.%d %d ", NOW, to[0], to[1], to[2], to[3], port);
    for (uint8_t c : out) printf("%02x", c);
    printf("\n");
    return 1;
  }
};
// the board's software's version, as its own esp_arduino_version.h says it
#define ESP_ARDUINO_VERSION_MAJOR CORE_MAJOR
#define ESP_ARDUINO_VERSION_MINOR CORE_MINOR
#define ESP_ARDUINO_VERSION_PATCH CORE_PATCH
#define ESP_ARDUINO_VERSION_VAL(major, minor, patch) ((major << 16) | (minor << 8) | (patch))
#define ESP_ARDUINO_VERSION ESP_ARDUINO_VERSION_VAL(ESP_ARDUINO_VERSION_MAJOR, ESP_ARDUINO_VERSION_MINOR, ESP_ARDUINO_VERSION_PATCH)
#if ESP_ARDUINO_VERSION >= ESP_ARDUINO_VERSION_VAL(3, 0, 5)   // (from 3.0.5 on: its LED lit by this name, the old one
inline void rgbLedWrite(uint8_t pin, uint8_t r, uint8_t g, uint8_t b) { printf("L %.4f %d %d %d %d\n", NOW, pin, r, g, b); }
[[deprecated("Use rgbLedWrite() instead.")]]                  //  still there, but not to be used)
inline void neopixelWrite(uint8_t pin, uint8_t r, uint8_t g, uint8_t b) { printf("OLD\n"); }
#else                                                         // (before: by this one alone)
inline void neopixelWrite(uint8_t pin, uint8_t r, uint8_t g, uint8_t b) { printf("L %.4f %d %d %d %d\n", NOW, pin, r, g, b); }
#endif
''')
for name in ("WiFi.h", "WiFiUdp.h", "esp_timer.h"):
    open(f"{S}/board/{name}", "w").write('#include "Arduino.h"\n')
# what the board keeps through a power cut: a file here (KEPT says which), so the next run of it has it; each time
# it's written is noted
open(S + "/board/Preferences.h", "w").write(r'''
#pragma once
#include "Arduino.h"
#include <cstdlib>
struct Preferences {
  bool begin(const char *name, bool readOnly = false) { return true; }
  void end() {}
  uint32_t getUInt(const char *key, uint32_t fallback = 0) {
    const char *path = getenv("KEPT");
    FILE *f = path ? fopen(path, "r") : nullptr;
    if (!f) return fallback;
    unsigned v = fallback;
    if (fscanf(f, "%u", &v) != 1) v = fallback;
    fclose(f);
    return v;
  }
  size_t putUInt(const char *key, uint32_t v) {
    printf("K %.4f %u\n", NOW, (unsigned)v);
    const char *path = getenv("KEPT");
    FILE *f = path ? fopen(path, "w") : nullptr;
    if (f) { fprintf(f, "%u", (unsigned)v); fclose(f); }
    return 4;
  }
};
''')
# FastLED, as far as the sketch uses it. The real one has names of its own that are the sketch's settings' too (its
# ClearFlags has a BRIGHTNESS, since 3.10): it's to be read before any of them is set, or it won't build at all
open(S + "/board/FastLED.h", "w").write(r'''
#pragma once
#if defined(BRIGHTNESS) || defined(LED_COUNT) || defined(STRIP_PIN) || defined(ONBOARD_PIN) || defined(MOST_MILLIAMPS)
#error "FastLED.h is to be read before the sketch's own settings: it has names of its own like theirs"
#endif
#if defined(MATRIX_BRIGHTNESS) || defined(MATRIX_ORDER) || defined(STRIP_ORDER)
#error "FastLED.h is to be read before the sketch's own settings: it has names of its own like theirs"
#endif
#include "Arduino.h"
struct CRGB { uint8_t r = 0, g = 0, b = 0; CRGB() {} CRGB(uint8_t x, uint8_t y, uint8_t z) : r(x), g(y), b(z) {} };
enum { GRB = 1, RGB = 2 };
enum class ClearFlags : uint32_t { NONE = 0, CHANNELS = 1 << 0, POWER_SETTINGS = 1 << 1, BRIGHTNESS = 1 << 2 };
struct WS2812 { static const char *name() { return "WS2812"; } };
struct WS2812B { static const char *name() { return "WS2812B"; } };
extern CRGB *STRIP; extern int STRIP_N, STRIP_AT;
struct CFastLED {
  template <typename CHIP, int PIN, int ORDER> void addLeds(CRGB *leds, int n) {
    STRIP = leds; STRIP_N = n; STRIP_AT = PIN;
    printf("A %d %d %s %s\n", PIN, n, ORDER == RGB ? "RGB" : "GRB", CHIP::name());
  }
  void setMaxPowerInVoltsAndMilliamps(int volts, int ma) { printf("P %d %d\n", volts, ma); }
  void setBrightness(uint8_t scale) { printf("R %d\n", scale); }
  void setDither(uint8_t mode) { printf("D %d\n", mode); }
  void show() {
    printf("F %.4f %d", NOW, STRIP_AT);
    for (int i = 0; i < STRIP_N; i++) printf(" %d,%d,%d", STRIP[i].r, STRIP[i].g, STRIP[i].b);
    printf("\n");
  }
};
extern CFastLED FastLED;
inline void fill_solid(CRGB *leds, int n, CRGB c) { for (int i = 0; i < n; i++) leds[i] = c; }
''')
# the test's word with it, a line at a time: "t SECONDS" (its loop, till then), "p ADDRESS HEX" (a packet for it),
# "wifi 0|1", "why N" (what its WiFi says while it isn't on one), "monitor 0|1" (a Serial Monitor listening, or not)
open(S + "/main.cpp", "w").write(r'''
#include "Arduino.h"
double NOW = 0; bool ON_WIFI = false; int WHY_NOT = 6; WiFiClass WiFi; std::deque<Packet> INBOX; SerialClass Serial;
#include "sketch.cpp"
#ifdef WITH_STRIP                  // (FastLED's own things: after the sketch, which reads FastLED.h where it must)
CRGB *STRIP = nullptr; int STRIP_N = 0, STRIP_AT = 0; CFastLED FastLED;
#endif
int main() {
  setup();
  char line[8192];
  while (fgets(line, sizeof line, stdin)) {
    double t; int a, b, c, d, on; char hex[8000];
    if (sscanf(line, "t %lf", &t) == 1) { while (NOW < t) loop(); }
    else if (sscanf(line, "wifi %d", &on) == 1) ON_WIFI = on;
    else if (sscanf(line, "why %d", &on) == 1) WHY_NOT = on;
    else if (sscanf(line, "monitor %d", &on) == 1) Serial.there = on;
    else if (sscanf(line, "p %d.%d.%d.%d %7999s", &a, &b, &c, &d, hex) == 5) {
      Packet p; p.from = IPAddress(a, b, c, d);
      for (size_t i = 0; i + 1 < strlen(hex); i += 2) { unsigned v; sscanf(hex + i, "%2x", &v); p.data.push_back((uint8_t)v); }
      INBOX.push_back(p);
    }
  }
  return 0;
}
''')
if shutil.which("g++") is None:
    print("(no g++ here: the sketch isn't built; the Pi's side is still looked at)")
    BOARD = None
else:
    BOARD = True


def build(name, strip=0, core="3,3,12", matrix=False):
    """The sketch, built for the stand-in board (a strip of that many LEDs, if any; matrix: a Waveshare
    ESP32-S3-Matrix; core: the version of the board's software): the program, or None. (A warning's an error:
    nothing the board's software says not to use.)"""
    src = open(SKETCH).read()
    if strip:
        assert "#define LED_COUNT 1 " in src
        src = src.replace("#define LED_COUNT 1 ", f"#define LED_COUNT {strip} ")
    if matrix:
        assert "#define WAVESHARE_MATRIX 0 " in src
        src = src.replace("#define WAVESHARE_MATRIX 0 ", "#define WAVESHARE_MATRIX 1 ")
        strip = 64
    open(S + "/sketch.cpp", "w").write(src)
    out = f"{S}/{name}"
    major, minor, patch = core.split(",")
    r = subprocess.run(["g++", "-std=c++17", "-O1", "-Wall", "-Werror", "-Wno-unused", "-I", S + "/board",
                        f"-DCORE_MAJOR={major}", f"-DCORE_MINOR={minor}", f"-DCORE_PATCH={patch}"]
                       + (["-DWITH_STRIP"] if strip else []) + ["-o", out, S + "/main.cpp"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-3000:])
        return None
    return out


def run(prog, script, kept=None):
    """Its loop, run through what the test says: what its LED was sent [(when, pin, r, g, b)] (a strip: [(when, pin,
    [its LEDs])]), what it sent [(when, to, port, bytes)], and when it began listening [(when, port)]. (ASKED: when
    it asked for the WiFi. kept: the file it keeps things in through a power cut, if it's to: KEPT has when each
    was written, and what; SET_UP how a strip was set up: its pin, its LEDs, their order and kind (and a limit asked
    of FastLED, if one was); BRIGHT and DITHER what FastLED was told of its brightness and its dithering; SAID
    what it told the Serial Monitor [(when, the line)], and MONITOR the speed it began that at.)"""
    env = dict(os.environ)
    env.pop("KEPT", None)
    if kept:
        env["KEPT"] = kept
    r = subprocess.run([prog], input="\n".join(script) + "\n", capture_output=True, text=True, timeout=60, env=env)
    leds, sent, begun, strip = [], [], [], []
    ASKED[:] = [float(line.split()[1]) for line in r.stdout.splitlines() if line.startswith("W ")]
    KEPT[:] = [(float(w[1]), int(w[2])) for w in (x.split() for x in r.stdout.splitlines()) if w and w[0] == "K"]
    SET_UP[:] = [w[1:] for w in (x.split() for x in r.stdout.splitlines()) if w and w[0] in ("A", "P")]
    DITHER[:] = [int(w[1]) for w in (x.split() for x in r.stdout.splitlines()) if w and w[0] == "D"]
    BRIGHT[:] = [int(w[1]) for w in (x.split() for x in r.stdout.splitlines()) if w and w[0] == "R"]
    SAID[:] = [(float(x.split()[1]), x.split(None, 2)[2]) for x in r.stdout.splitlines() if x.startswith("# ")]
    MONITOR[:] = [int(x.split()[1]) for x in r.stdout.splitlines() if x.startswith("SB ")]
    for line in r.stdout.splitlines():
        w = line.split()
        if w[0] == "L":
            leds.append((float(w[1]), int(w[2]), int(w[3]), int(w[4]), int(w[5])))
        elif w[0] == "S":
            sent.append((float(w[1]), w[2], int(w[3]), bytes.fromhex(w[4])))
        elif w[0] == "B":
            begun.append((float(w[1]), int(w[2])))
        elif w[0] == "F":
            strip.append((float(w[1]), int(w[2]), [tuple(int(v) for v in led.split(",")) for led in w[3:]]))
    return leds, sent, begun, strip


ASKED, KEPT, SET_UP, DITHER, BRIGHT, SAID, MONITOR = [], [], [], [], [], [], []


def at(leds, t):
    """Its LED's colour at t: what it was last sent by then."""
    got = [x[2:] for x in leds if x[0] <= t + 1e-9]
    return got[-1] if got else None


def seen(rgb, bright=90):
    """A colour as the LED's sent it: as it's seen, and no brighter than it's set."""
    return tuple(int(round((max(0.0, min(255.0, v)) / 255.0) ** 2.2 * bright)) for v in rgb)


def near(a, b, by=2):
    return a is not None and all(abs(x - y) <= by for x, y in zip(a, b))


AHEAD = 5000.0                                        # (the Pietato's clock, ahead of the board's by this)
PI, PI2 = "10.0.0.5", "10.0.0.9"


def packet(ip, data):
    return f"p {ip} {data.hex()}"


if BOARD:
    prog = build("led")
    check("the sketch builds for a board (its own LED)", prog is not None)
if BOARD and prog:
    # ---- looking for the WiFi, then on it ---------------------------------------------------------------------------
    leds, sent, begun, _ = run(prog, ["t 1.0", "wifi 1", "t 7.0"])
    check(f"looking for the WiFi: a dim amber, said once, and nothing sent ({leds[:2]})",
          leds[0][2:] == (0, 0, 0) and leds[1][2:] == (10, 5, 0) and not [s for s in sent if s[0] < 1.0])
    check(f"...its own LED, where the board says it is ({leds[0][1]})", leds[0][1] == 97)
    check(f"on it: it listens where a Pietato's colours come ({begun})", [b[1] for b in begun] == [G.GLOW_PORT])
    hellos = [s for s in sent if s[2] == G.LAMP_PORT and s[3][3:4] == b"L"]
    gaps = [round(b[0] - a[0], 2) for a, b in zip(hellos, hellos[1:])]
    said = G.read_lamp(hellos[0][3]) if hellos else None
    check(f"...and says it's there every couple of seconds, to everyone on its network ({len(hellos)}, {gaps}, "
          f"{hellos[0][1] if hellos else None}): {said}", len(hellos) == 3 and all(1.95 <= x <= 2.1 for x in gaps)
          and hellos[0][1] == "10.0.0.255" and said == {"name": "ESP32 A1B2C3", "count": 1})
    joined, still = at(leds, 1.1), at(leds, 2.45)
    check(f"...its LED green for a second and a half, so you can't miss it ({joined}, still {still}), then fading "
          f"({at(leds, 2.9)}) to dark, with nothing playing ({at(leds, 4.5)}, {at(leds, 6.9)})",
          joined == still == seen((0, 140, 0)) and 0 < at(leds, 2.9)[1] < joined[1] and at(leds, 2.9)[0] == 0
          and at(leds, 4.5) == at(leds, 6.9) == (0, 0, 0))
    said = list(SAID)
    check(f"the Serial Monitor (begun at {MONITOR}): told at once that it's looking for the WiFi, by name, and what "
          f"it lights ({said[:1]})", MONITOR == [115200] and len(said) >= 1 and said[0][0] < 0.2
          and said[0][1] == 'Pietato LED (the board\'s own LED): looking for the WiFi "your WiFi\'s name"')
    check(f"...and once it's on it: its address, the name your Pietatos list it by, and that it's dark till something "
          f"plays ({said[1:2]})", len(said) >= 2 and 1.0 <= said[1][0] <= 2.1 and said[1][1] ==
          'Pietato LED (the board\'s own LED): on your WiFi as 10.0.0.77, "ESP32 A1B2C3" to your Pietatos; '
          'dark till something plays on a Pietato')
    _, _, _, _ = run(prog, ["t 25.0", "why 1", "t 35.0", "why 4", "t 45.0", "wifi 1", "t 71.0",
                            packet(PI, G.music_packet((96, 170, 228), 71.0 + AHEAD)), "t 73.0",
                            packet(PI, G.colour_packet((255, 136, 0), 73.0 + AHEAD)), "t 95.0", "wifi 0", "t 97.0"])
    said = list(SAID)
    gaps = [round(b[0] - a[0], 1) for a, b in zip(said, said[1:])]
    check(f"...told how it is every ten seconds, changed or not ({gaps[:6]})", gaps[:4] == [10.0, 10.0, 10.0, 10.0]
          and all(1.0 <= x <= 10.1 for x in gaps))
    check(f"...no WiFi of that name: said so ({said[3][1][-70:]!r}); the password not taken: that ({said[4][1][-45:]!r})",
          said[2][1].endswith('"your WiFi\'s name"') and said[3][1].endswith(
              "There's none of that name here (an ESP32 only sees 2.4 GHz ones)")
          and said[4][1].endswith("It's there, but the password wasn't taken"))
    lit = [x for x in said if "lit by" in x[1]]
    check(f"...a Pietato lighting it: said within a second or so, with that one's address ({lit[:1]})", lit and
          71.0 <= lit[0][0] <= 72.1 and lit[0][1].endswith("lit by the Pietato at 10.0.0.5"))
    own = [x for x in said if "its own colour" in x[1] and x[0] < 95.0]
    check(f"...a colour of its own: that too ({own[:1]}), and with nothing playing ({own[-1:]})", own
          and 73.0 <= own[0][0] <= 74.1 and own[0][1].endswith("lit by the Pietato at 10.0.0.5, in its own colour "
                                                                "(#ff8800)") and own[-1][1].endswith(
              "dark till something plays on a Pietato (then in its own colour, #ff8800)"))
    check(f"...the WiFi gone: said ({said[-1]})", 95.0 <= said[-1][0] <= 96.2 and "looking for the WiFi" in said[-1][1])
    flood = ["wifi 1", "t 3.0"]                        # (a colour being picked: forty of them, in a second)
    for k in range(1, 41):
        flood += [f"t {3.0 + k * 0.025:.3f}", packet(PI, G.colour_packet((k, 0, 200), 3.0 + AHEAD))]
    run(prog, flood + ["t 5.5"])
    lines = [x for x in SAID if 3.0 <= x[0] <= 5.5]
    check(f"...a colour being picked (forty in a second): a line a second at most ({[round(x[0], 2) for x in lines]}), "
          f"the last with the one it ended on ({lines[-1][1][-10:] if lines else None})", 2 <= len(lines) <= 3
          and all(b[0] - a[0] >= 0.99 for a, b in zip(lines, lines[1:])) and lines[-1][1].endswith("#2800c8)"))
    leds_quiet, sent_quiet, _, _ = run(prog, ["monitor 0", "t 1.0", "wifi 1", "t 7.0"])
    check(f"...nothing listening: nothing's said ({SAID}), and it does as it does ({leds_quiet[:2]})", SAID == []
          and leds_quiet == leds and [x[1:] for x in sent_quiet] == [x[1:] for x in sent])
    leds, sent, _, _ = run(prog, ["t 100.0", "wifi 1", "t 300.0", "wifi 0", "t 420.0"])
    asked = list(ASKED)
    check(f"no WiFi yet: asked for again every half minute, and no oftener ({asked[:5]})",
          len(asked) >= 4 and all(30 * k <= t <= 30 * k + 0.5 for k, t in enumerate(asked[:4]))
          and not [t for t in asked if 100.5 < t < 300])
    check(f"...lost later: the board's left to look for it at first, then it's asked for again ({asked[4:]})",
          len(asked) >= 5 and 329.5 <= asked[4] <= 331 and at(leds, 301.0) == (10, 5, 0))
    for core in ("2,0,17", "3,0,4", "3,0,5"):          # (its LED's lit by another name, before 3.0.5)
        old = build("led_" + core.replace(",", "_"), core=core)
        got = run(old, ["t 1.0", "wifi 1", "t 3.0"])[0] if old else []
        check(f"the board's software, version {core.replace(',', '.')}: built for that too, and its LED lit "
              f"({got[:2]})", old is not None and [x[2:] for x in got[:2]] == [(0, 0, 0), (10, 5, 0)])

    # ---- music: its colour, and a beat when it's due ---------------------------------------------------------------
    BLUE = (96, 170, 228)
    script = ["wifi 1", "t 1.0"]
    for k in range(12):                                # (its colour said every half second, as media mode does)
        t = 1.0 + k * 0.5
        script += [f"t {t}", packet(PI, G.music_packet(BLUE, t + AHEAD))]
        if k == 4:                                     # (a beat, due 0.3 s from now by the Pietato's clock)
            script.append(packet(PI, G.event_packet("beat", 1.0, t + 0.3 + AHEAD, t + AHEAD)))
    script.append("t 9.5")
    leds, sent, _, _ = run(prog, script)
    base = seen([v * 0.4 for v in BLUE])
    check(f"music playing: its colour, dimmer, between beats ({at(leds, 2.9)}, for {base})", near(at(leds, 2.9), base))
    check(f"...a beat on its way (due in a moment): not yet ({at(leds, 3.28)})", near(at(leds, 3.28), base))
    peak = at(leds, 3.31)
    check(f"...at the moment it's due: brighter ({peak})", peak is not None and sum(peak) > sum(base) * 1.8)
    check(f"...and it dies away ({at(leds, 3.45)}, then {at(leds, 3.95)})",
          sum(base) < sum(at(leds, 3.45)) < sum(peak) and near(at(leds, 3.95), base))
    check(f"...the music stopped: dark again ({at(leds, 9.4)})", at(leds, 9.4) == (0, 0, 0))
    RED = (255, 0, 0)                                  # (a Soundboard's sound: its colour, and a beat with it)
    leds, _, _, _ = run(prog, ["wifi 1", "t 5.0", packet(PI, G.music_packet(RED, 5.0 + AHEAD)),
                               packet(PI, G.event_packet("beat", 1.0, 5.0 + AHEAD, 5.0 + AHEAD)), "t 5.02", "t 5.6",
                               "t 9.0"])
    first, glow = at(leds, 5.02), at(leds, 5.6)
    check(f"a beat that comes with music's first colour (a Soundboard's sound, the LED dark till then): as bright as "
          f"any, at once, in that colour ({first}); then the colour while it's kept ({glow}), and dark again "
          f"({at(leds, 8.9)})", first is not None and first[0] >= 40 and first[1] < first[0] / 4
          and near(glow, seen([v * 0.4 for v in RED])) and at(leds, 8.9) == (0, 0, 0))

    # ---- a game: its colours, a hit, an achievement ----------------------------------------------------------------
    colours = np.zeros((8, 8, 3), dtype=np.uint8)
    colours[:, :4] = (200, 40, 0)
    colours[:, 4:] = (0, 40, 200)
    script = ["wifi 1", "t 1.0"]
    for k in range(60):                                # (30 pictures a second, two seconds)
        t = 1.0 + k / 30
        script += [f"t {t:.4f}", packet(PI, G.frame_packet(colours, t + AHEAD))]
        if k == 30:
            script.append(packet(PI, G.event_packet("hit", 1.0, t + AHEAD, t + AHEAD)))
    script += ["t 3.2", packet(PI, G.frame_packet(colours, 3.2 + AHEAD)),
               packet(PI, G.event_packet("cheevo", 1.0, 3.2 + AHEAD, 3.2 + AHEAD)), "t 3.25", "t 9.5"]
    leds, _, _, _ = run(prog, script)
    blend = seen((100, 40, 100))
    check(f"a game: the blend of its picture's edges ({at(leds, 1.9)}, for {blend})", near(at(leds, 1.9), blend))
    hit = at(leds, 2.02)
    check(f"...a hit: red ({hit})", hit is not None and hit[0] > 60 and hit[1] < 6 and hit[2] < 10)
    check(f"...and back ({at(leds, 2.9)})", near(at(leds, 2.9), blend))
    gold = at(leds, 3.23)
    check(f"...an achievement: gold ({gold})", gold is not None and gold[0] > 60 and gold[0] > gold[1] > gold[2])
    check(f"...the game over: dark ({at(leds, 9.4)})", at(leds, 9.4) == (0, 0, 0))
    # (a lot of boards: each gets a picture only now and then. Three a second here, then one)
    red, blue = np.zeros((8, 8, 3), dtype=np.uint8), np.zeros((8, 8, 3), dtype=np.uint8)
    red[:], blue[:] = (200, 40, 0), (0, 40, 200)
    script, t = ["wifi 1", "t 5.0"], 5.0
    while t < 9.0:
        script += [f"t {t:.4f}", packet(PI, G.frame_packet(red, t + AHEAD))]
        t += 1 / 3
    while t < 20.0:
        script += [f"t {t:.4f}", packet(PI, G.frame_packet(blue if t > 14 else red, t + AHEAD))]
        t += 1.07
    last = t - 1.07
    script.append(f"t {last + 12:.4f}")
    leds, _, _, _ = run(prog, script)
    lows = [min(sum(at(leds, 6.0 + k * 0.05)) for k in range(60)), min(sum(at(leds, 10.0 + k * 0.05)) for k in range(70))]
    check(f"a game's pictures only now and then (three a second, then one): its colour kept between them, not "
          f"flickering ({lows}, for {sum(seen((200, 40, 0)))})", min(lows) >= sum(seen((200, 40, 0))) - 3)
    turned = [at(leds, 14.3 + k * 0.25) for k in range(16)]
    check(f"...its colour changing: from one to the other smoothly, a step at a time ({turned[::3]})",
          all(a[0] >= b[0] and a[2] <= b[2] for a, b in zip(turned, turned[1:])) and near(turned[-1], seen((0, 40, 200)))
          and len({x[2:] for x in leds if 14.3 < x[0] < 18.3}) > 20)
    check(f"...and the game over: kept a little longer than it was between them, then dark "
          f"({at(leds, last + 3.0)}, {at(leds, last + 11.0)})", near(at(leds, last + 3.0), seen((0, 40, 200)))
          and at(leds, last + 11.0) == (0, 0, 0))

    # ---- what isn't a Pietato's packet; one Pietato at a time -------------------------------------------------------
    good = G.music_packet((255, 0, 0), 1.0 + AHEAD)
    junk = [b"", b"PG", b"XX" + good[2:], good[:2] + b"\x02" + good[3:], good[:3] + b"Q" + good[4:], good[:-1],
            good + b"x", G.event_packet("beat", 1.0, 1.0 + AHEAD, 1.0 + AHEAD)[:14],
            G.HEAD.pack(G.MAGIC, G.VERSION, b"E", 1.0 + AHEAD) + G.EVENT.pack(1.0 + AHEAD, 255) + b"boom",
            G.HEAD.pack(G.MAGIC, G.VERSION, b"M", float("nan")) + bytes(3),
            G.HEAD.pack(G.MAGIC, G.VERSION, b"F", 1.0 + AHEAD) + bytes((0, 0)), G.lamp_packet("x", 1, 1.0 + AHEAD)]
    leds, _, _, _ = run(prog, ["wifi 1", "t 4.0"] + [packet(PI, j) for j in junk] + ["t 5.0"])
    check(f"what isn't a Pietato's packet (or isn't right): nothing ({at(leds, 4.9)}), and nothing said of one "
          f"lighting it ({[x[1][-45:] for x in SAID if x[0] > 4.0]})", at(leds, 4.9) == (0, 0, 0)
          and not [x for x in SAID if "lit by" in x[1]])
    script = ["wifi 1", "t 1.0"]
    for k in range(8):
        t = 1.0 + k * 0.5
        script += [f"t {t}", packet(PI, G.music_packet((255, 0, 0), t + AHEAD)),
                   packet(PI2, G.music_packet((0, 0, 255), t - 77.0))]
    for k in range(8, 16):                             # (the first stops; the second plays on)
        t = 1.0 + k * 0.5
        script += [f"t {t}", packet(PI2, G.music_packet((0, 0, 255), t - 77.0))]
    script.append("t 9.0")
    leds, _, _, _ = run(prog, script)
    first, later = at(leds, 4.4), at(leds, 8.9)
    check(f"two Pietatos playing: the one it's following, till that's quiet; then the other ({first}, {later})",
          first is not None and first[0] > 5 and first[2] == 0 and later is not None and later[2] > 5
          and later[0] == 0)

    # ---- a strip instead ---------------------------------------------------------------------------------------------
    strip = build("strip", strip=8)
    check("the sketch builds for a strip of LEDs (FastLED)", strip is not None)
    if strip:
        _, _, _, shows = run(strip, ["wifi 1", "t 1.0", packet(PI, G.music_packet(BLUE, 1.0 + AHEAD)), "t 1.4",
                                     packet(PI, G.music_packet(BLUE, 1.4 + AHEAD)), "t 2.2"])
        last = shows[-1] if shows else (0, 0, [(0, 0, 0)])   # (as it's lit by then: sent when it changes)
        check(f"...all eight of its LEDs, music's colour ({last[2][:2]}, for {base}), on its pin ({last[1]}), green "
              f"first as such strips take it ({SET_UP}), each colour as it is: FastLED isn't to dim it or dither it "
              f"({BRIGHT}, {DITHER})", len(last[2]) == 8 and len(set(last[2])) == 1 and near(last[2][0], base)
              and last[1] == 5 and SET_UP == [["5", "8", "GRB", "WS2812"]] and BRIGHT == [255] and DITHER == [0])
        check(f"...and the Serial Monitor's told it's a strip ({SAID[0][1][:44] if SAID else None})", SAID
              and SAID[0][1].startswith("Pietato LED (a strip, 8 LEDs on pin 5): "))
        _, _, _, shows = run(strip, ["wifi 1", "t 3.0", packet(PI, G.colour_packet((255, 255, 255), 3.0 + AHEAD)),
                                     "t 4.5"])
        check(f"...a white: as bright as the sketch's set to ({shows[-1][2][:1]}): a strip has its own supply",
              shows[-1][2][0] == (90, 90, 90))
        _, _, _, shows = run(strip, ["wifi 1", "t 9.0"])
        dark = [x[0] for x in shows if x[0] > 4.0 and set(x[2]) == {(0, 0, 0)}]
        gaps = [round(b - a, 2) for a, b in zip(dark, dark[1:])]
        check(f"...told again every half second, changed or not (a telling can go astray, with the WiFi busy): "
              f"{len(dark)} times in five seconds of dark ({sorted(set(gaps))})", 9 <= len(dark) <= 11
              and all(0.5 <= g <= 0.52 for g in gaps))

    # ---- a Waveshare ESP32-S3-Matrix: 64 LEDs on pin 14, red first, dim, and no more than 300 mA -------------------------
    matrix = build("matrix", matrix=True)
    check("the sketch builds for a Waveshare ESP32-S3-Matrix (FastLED)", matrix is not None)
    if matrix:
        _, sent, _, shows = run(matrix, ["wifi 1", "t 1.0", packet(PI, G.music_packet(BLUE, 1.0 + AHEAD)), "t 1.4",
                                         packet(PI, G.music_packet(BLUE, 1.4 + AHEAD)), "t 2.2"])
        last = shows[-1] if shows else (0, 0, [(0, 0, 0)])
        dim = seen([v * 0.4 for v in BLUE], 40)
        said = next((G.read_lamp(x[3]) for x in sent if x[3][3:4] == b"L"), None)
        check(f"...its 64 LEDs on pin 14, red first, set up as a board of them is known to work ({SET_UP}, FastLED's "
              f"own brightness {BRIGHT}, its dithering {DITHER}); all of them music's colour, dim ({last[2][:1]}, for "
              f"{dim}: the board gets hot otherwise); and it says it has 64 ({said})",
              SET_UP == [["14", "64", "RGB", "WS2812"]] and BRIGHT == [255] and DITHER == [0] and len(last[2]) == 64
              and len(set(last[2])) == 1 and near(last[2][0], dim, 1) and last[1] == 14
              and said == {"name": "ESP32 A1B2C3", "count": 64})
        check(f"...and the Serial Monitor's told it's the matrix ({SAID[0][1][:58] if SAID else None})", SAID
              and SAID[0][1].startswith("Pietato LED (a Waveshare matrix, 64 LEDs on pin 14): "))

        def takes(leds):                               # (mA, as FastLED reckons a WS2812 at 5 V: the board 25, a dark
            return 25 + sum(1 + (16 * r + 11 * g + 15 * b) / 255 for r, g, b in leds)   # LED 1, and each colour)

        script = ["t 1.0", "wifi 1", "t 4.0"]
        for k, rgb in enumerate(((255, 255, 255), (255, 0, 0), (255, 255, 0), (0, 0, 255))):
            script += [packet(PI, G.colour_packet(rgb, 4.0 + AHEAD)), f"t {6.0 + k * 3:.1f}"]   # (shown a moment)
        _, _, _, shows = run(matrix, script)
        most = max(takes(x[2]) for x in shows)
        white, red, yellow, blue = ([x[2][0] for x in shows if x[0] < t][-1] for t in (5.9, 7.9, 10.9, 13.9))
        check(f"...never more than 300 mA between them, whatever it's asked for ({most:.0f} mA at the most, in "
              f"{len(shows)} tellings): a white's dimmed to fit ({white}), and a yellow ({yellow}); a red and a "
              f"blue aren't ({red}, {blue})", 290 <= most <= 300 and white in ((19, 19, 19), (20, 20, 20))
              and red == (40, 0, 0) and blue == (0, 0, 40) and yellow[0] == yellow[1] and 28 <= yellow[0] <= 32
              and yellow[2] == 0 and all(len(set(x[2])) == 1 for x in shows))
        amber = [x for x in shows if x[0] < 1.0]
        check(f"...looking for the WiFi: all 64 a dim amber, at once ({amber[1][0] if len(amber) > 1 else None} s: "
              f"{amber[1][2][:1] if len(amber) > 1 else None}), and told again every half second "
              f"({len(amber)} tellings in the first second)", len(amber) >= 3 and set(amber[0][2]) == {(0, 0, 0)}
              and amber[1][0] <= 0.01 and set(amber[1][2]) == {(10, 5, 0)} and 3 <= len(amber) <= 4)

    # ---- a colour of its own: told it, shown a moment, kept, and what it's lit in whatever's playing ----------------------
    def states(sent):
        return [(x[0], G.read_state(x[3])) for x in sent if x[2] == G.LAMP_PORT and x[3][3:4] == b"S"]

    NVS = S + "/kept"
    RED, GREEN = (255, 0, 0), (0, 200, 60)
    leds, sent, _, _ = run(prog, ["wifi 1", "t 3.0", packet(PI, G.colour_packet(RED, 3.0 + AHEAD)), "t 9.0"], NVS)
    said = states(sent)
    check(f"how it is, said with each hello: it keeps a colour of its own, and has none yet ({said[:1]})",
          len(said) >= 2 and said[0][1] == {"keeps": True, "colour": None})
    check(f"told a colour of its own, with nothing playing: it shows it a moment ({at(leds, 3.6)}, for "
          f"{seen(RED)}), then goes dark again ({at(leds, 8.9)})", near(at(leds, 3.6), seen(RED))
          and at(leds, 8.9) == (0, 0, 0))
    back = [x for x in said if 3.0 <= x[0] <= 3.1]
    check(f"...says it back at once ({back[:1]})", len(back) == 1 and back[0][1] == {"keeps": True, "colour": RED})
    check(f"...and keeps it, once it's stood a second: written once ({KEPT})", len(KEPT) == 1
          and 4.0 <= KEPT[0][0] <= 4.1 and KEPT[0][1] == 0x01FF0000)
    script = ["wifi 1", "t 1.0"]                       # (after a power cut: the same board, started again)
    for k in range(12):
        t = 1.0 + k * 0.5
        script += [f"t {t}", packet(PI, G.music_packet(BLUE, t + AHEAD))]
        if k == 4:
            script.append(packet(PI, G.event_packet("beat", 1.0, t + 0.3 + AHEAD, t + AHEAD)))
        if k == 8:                                     # (the same colour again, from another of yours: which one is it?)
            script.append(packet(PI2, G.colour_packet(RED, 7.0)))
    script.append("t 9.5")
    leds, sent, _, _ = run(prog, script, NVS)
    said, own = states(sent), seen([v * 0.4 for v in RED])
    check(f"after a power cut: it still has it ({said[:1]})", said and said[0][1] == {"keeps": True, "colour": RED})
    check(f"...music playing: lit in its own colour, not music's ({at(leds, 2.9)}, for {own})", near(at(leds, 2.9), own))
    peak = at(leds, 3.31)
    check(f"...a beat: brighter, in its colour ({peak})", peak is not None and sum(peak) > sum(own) * 1.8
          and peak[0] > peak[2])
    check(f"...told the same colour again (which one is it?): shown bright a moment ({at(leds, 5.6)}), then as it "
          f"was ({at(leds, 7.6)}); nothing written ({KEPT})", near(at(leds, 5.6), seen(RED)) and near(at(leds, 7.6), own)
          and KEPT == [])
    script = ["wifi 1", "t 1.0", packet(PI, G.colour_packet(GREEN, 1.0 + AHEAD)), "t 1.5"]
    for k in range(60):                                # (a game: 30 pictures a second, two seconds)
        t = 1.5 + k / 30
        script += [f"t {t:.4f}", packet(PI, G.frame_packet(colours, t + AHEAD))]
        if k == 30:
            script.append(packet(PI, G.event_packet("hit", 1.0, t + AHEAD, t + AHEAD)))
    script.append("t 9.5")
    leds, _, _, _ = run(prog, script, S + "/kept2")
    hit = at(leds, 2.52)
    check(f"a game: its own colour, not the picture's ({at(leds, 4.0)}, for {seen(GREEN)}); a hit's red over it "
          f"({hit}); dark once it's over ({at(leds, 9.4)})", near(at(leds, 4.0), seen(GREEN)) and hit is not None
          and hit[0] > 60 and hit[1] < 6 and at(leds, 9.4) == (0, 0, 0))
    script = ["wifi 1", "t 1.0", packet(PI, G.colour_packet(None, 1.0 + AHEAD)), "t 4.0"]
    for k in range(6):
        t = 4.0 + k * 0.5
        script += [f"t {t}", packet(PI, G.music_packet(BLUE, t + AHEAD))]
    script.append("t 9.5")
    leds, sent, _, _ = run(prog, script, NVS)
    said = states(sent)
    check(f"told to have none: white a moment, so you can tell which it is ({at(leds, 1.6)}); said back "
          f"({said[1:2]}), kept ({KEPT}); and it takes what's playing again ({at(leds, 5.9)}, for {base})",
          near(at(leds, 1.6), seen((160, 160, 160))) and [x[1]["colour"] for x in said[:2]] == [RED, None]
          and [k[1] for k in KEPT] == [0] and near(at(leds, 5.9), base))
    good = G.colour_packet(RED, 1.0 + AHEAD)
    junk = [good[:-1], good + b"x", good[:12] + b"\x02" + good[13:],
            G.HEAD.pack(G.MAGIC, G.VERSION, b"C", float("nan")) + good[12:]]
    leds, sent, _, _ = run(prog, ["wifi 1", "t 4.0"] + [packet(PI, j) for j in junk] + ["t 6.0"], S + "/kept3")
    check(f"a colour that isn't said right: nothing ({at(leds, 4.9)}, {KEPT})", at(leds, 4.9) == (0, 0, 0)
          and KEPT == [] and all(x[1]["colour"] is None for x in states(sent)))
    flood = ["wifi 1", "t 3.0"]                        # (a colour being picked: forty of them, in a second)
    for k in range(1, 41):
        flood += [f"t {3.0 + k * 0.025:.3f}", packet(PI, G.colour_packet((k, 0, 200), 3.0 + AHEAD))]
    leds, sent, _, _ = run(prog, flood + ["t 7.0"], S + "/kept4")
    back = [x for x in states(sent) if 3.0 <= x[0] < 4.5]
    gaps = [round(b[0] - a[0], 2) for a, b in zip(back, back[1:])]
    check(f"a colour being picked, forty of them in a second: said back four times a second at most ({gaps}), the "
          f"last of them the one it's left at ({back[-1][1] if back else None}); followed as it goes "
          f"({at(leds, 3.6)}, then {at(leds, 4.4)}); and kept once, as it was left ({KEPT})",
          3 <= len(back) <= 6 and min(gaps) >= 0.25 and back[-1][1]["colour"] == (40, 0, 200)
          and at(leds, 3.6)[2] > 40 and near(at(leds, 4.4), seen((40, 0, 200)))
          and len(KEPT) == 1 and 5.0 <= KEPT[0][0] <= 5.1 and KEPT[0][1] == 0x012800C8)
    cut = ["wifi 1", "t 3.0", packet(PI, G.colour_packet(RED, 3.0 + AHEAD)), "t 3.5"]
    run(prog, cut, S + "/kept5")                       # (the power cut half a second after it's told)
    wrote = list(KEPT)
    _, sent, _, _ = run(prog, ["wifi 1", "t 1.0"], S + "/kept5")
    check(f"the power cut before it's stood a second: not kept ({wrote}), and it comes back with none "
          f"({states(sent)[:1]})", wrote == [] and states(sent)[0][1] == {"keeps": True, "colour": None})

# ---- the Pi's side: a light listened for, found, kept while it says it's there ----------------------------------------
check("what a light says: taken as it is, and nothing else is",
      G.read_lamp(G.lamp_packet("ESP32 A1B2C3", 1, 5.0)) == {"name": "ESP32 A1B2C3", "count": 1}
      and G.read_lamp(G.lamp_packet("", 300, 5.0)) == {"name": "light", "count": 300}
      and G.read_lamp(G.music_packet((1, 2, 3), 5.0)) is None and G.read_lamp(b"") is None
      and G.read_lamp(G.lamp_packet("x", 1, 5.0)[:13]) is None
      and G.read_lamp(G.lamp_packet("x", 1, 5.0) + b"y" * 30) is None
      and G.read_lamp(b"XX" + G.lamp_packet("x", 1, 5.0)[2:]) is None)
T = [100.0]
lamps = G.Lamps(port=0, clock=lambda: T[0])
check("no lights yet", lamps.on() == [])
check("one says it's there, from your network: found", lamps.take(G.lamp_packet("ESP32 A1B2C3", 1, 1.0), "10.0.0.77", T[0])
      and lamps.on() == [("10.0.0.77", "ESP32 A1B2C3", 1)])
check("...one from somewhere else: not", not lamps.take(G.lamp_packet("far", 1, 1.0), "8.8.8.8", T[0])
      and not lamps.take(G.lamp_packet("odd", 1, 1.0), "not an address", T[0]) and len(lamps.on()) == 1)
check("...nor anything that isn't a light's word", not lamps.take(G.music_packet((1, 2, 3), 1.0), "10.0.0.78", T[0])
      and len(lamps.on()) == 1)
T[0] += 6.0
lamps.take(G.lamp_packet("second", 8, 1.0), "10.0.0.80", T[0])
check(f"...another: both ({lamps.on()})", lamps.on() == [("10.0.0.77", "ESP32 A1B2C3", 1), ("10.0.0.80", "second", 8)])
T[0] += 3.0
check(f"...the first gone quiet: just the second ({lamps.on()})", lamps.on() == [("10.0.0.80", "second", 8)])
for k in range(G.LAMPS_MOST + 10):
    lamps.take(G.lamp_packet(f"n{k}", 1, 1.0), f"10.0.1.{k}", T[0])
check(f"...no more of them than {G.LAMPS_MOST} ({len(lamps.on())})", len(lamps.on()) == G.LAMPS_MOST)
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
T[0] += 60.0
s.sendto(G.lamp_packet("over the air", 1, 1.0), ("127.0.0.1", lamps.port))
for _ in range(50):
    if lamps.on():
        break
    time.sleep(0.05)
check(f"...heard over the network itself ({lamps.on()})", lamps.on() == [("127.0.0.1", "over the air", 1)])
lamps.close()

# ---- a light's own colour, on the Pi's side: what it says of itself read, and one told it ---------------------------
check("how a light says it is: read as it is, and nothing else is",
      G.read_state(G.state_packet((1, 2, 3), 5.0)) == {"keeps": True, "colour": (1, 2, 3)}
      and G.read_state(G.state_packet(None, 5.0)) == {"keeps": True, "colour": None}
      and G.read_state(G.state_packet(None, 5.0, can=0)) == {"keeps": False, "colour": None}
      and G.read_state(G.lamp_packet("x", 1, 5.0)) is None and G.read_state(G.state_packet(None, 5.0) + b"x") is None
      and G.read_state(b"") is None and G.read_state(G.state_packet(None, float("nan"))) is None
      and G.read_lamp(G.state_packet(None, 5.0)) is None)
check("a light told its colour: 1 and the colour (kept to what a colour can be), or 0 for none",
      G.colour_packet((255, 0, 128), 5.0)[12:] == bytes((1, 255, 0, 128)) and G.colour_packet(None, 5.0)[12:] == bytes(4)
      and G.colour_packet((300, -5, 1.9), 5.0)[12:] == bytes((1, 255, 0, 1))
      and G.read_packet(G.colour_packet((1, 2, 3), 5.0)) is None)
T = [100.0]
lamps = G.Lamps(port=0, clock=lambda: T[0])
board = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
board.bind(("127.0.0.1", 0))
board.setblocking(False)
BPORT = board.getsockname()[1]


def told():
    """What the stand-in board's been sent, since the last look."""
    time.sleep(0.2)
    got = []
    while True:
        try:
            got.append(board.recv(4096))
        except BlockingIOError:
            return got


check("how one is, before it's said it's there: not taken", not lamps.take(G.state_packet(None, 1.0), "127.0.0.1", T[0])
      and lamps.boards() == [] and not lamps.ever)
lamps.take(G.lamp_packet("ESP32 B", 64, 1.0), "127.0.0.1", T[0])
lamps.take(G.lamp_packet("ESP32 a", 1, 1.0), "10.0.0.80", T[0])
check(f"the boards, by name; ones that haven't said how they are (the older sketch) keep no colour, and aren't told "
      f"one ({lamps.boards()})", lamps.boards() == [
          {"ip": "10.0.0.80", "name": "ESP32 a", "leds": 1, "keeps": False, "colour": None},
          {"ip": "127.0.0.1", "name": "ESP32 B", "leds": 64, "keeps": False, "colour": None}]
      and not lamps.set_colour("127.0.0.1", (1, 2, 3), BPORT) and told() == [] and lamps.ever)
check("...one says how it is: it keeps one", lamps.take(G.state_packet(None, 1.0), "127.0.0.1", T[0])
      and lamps.boards()[1]["keeps"] and lamps.boards()[1]["colour"] is None and not lamps.boards()[0]["keeps"])
ok, got = lamps.set_colour("127.0.0.1", (255, 0, 128), BPORT), told()
check(f"told a colour: said twice (a packet can go astray), where it listens ({len(got)}); shown as that at once",
      ok and got == [G.colour_packet((255, 0, 128), T[0])] * 2 and lamps.boards()[1]["colour"] == (255, 0, 128))
lamps.take(G.state_packet((9, 9, 9), 1.0), "127.0.0.1", T[0])
check("...what it says back is what's shown", lamps.boards()[1]["colour"] == (9, 9, 9))
ok, got = lamps.set_colour("127.0.0.1", None, BPORT), told()
check("...told to have none", ok and got == [G.colour_packet(None, T[0])] * 2 and lamps.boards()[1]["colour"] is None)
check("...one that isn't there, or how one elsewhere is: not told, not taken",
      not lamps.set_colour("10.0.0.99", (1, 2, 3), BPORT) and not lamps.take(G.state_packet(None, 1.0), "8.8.8.8", T[0])
      and told() == [])
T[0] += 9.0
check("...gone quiet: off the list, and how it was forgotten", lamps.boards() == [] and lamps.states == {})
lamps.close()

# ---- a lot of them: a game's pictures to a couple at a time, in turn; a beat to every one at once --------------------
words = G.target_words([("127.0.0.1", 5448), ("10.0.0.70", 5448), ("10.0.0.9", 6000)], {("10.0.0.70", 5448)}).split()
check(f"where a game's colours go, as media mode says it: a light of your own marked ({words})",
      words == ["127.0.0.1:5448", "+10.0.0.70:5448", "10.0.0.9:6000"]
      and G.targets(words) == [("127.0.0.1", 5448), ("10.0.0.70", 5448), ("10.0.0.9", 6000)]
      and G.lamp_targets(words) == [("10.0.0.70", 5448)] and G.target_words([]) == "-" and G.targets(["-"]) == []
      and G.lamp_targets(["+bad", "+x:99999", "10.0.0.7:5448"]) == [])
ends = []
for _ in range(6):
    k = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    k.bind(("127.0.0.1", 0))
    k.setblocking(False)
    ends.append(k)
addrs = [("127.0.0.1", k.getsockname()[1]) for k in ends]


def came():
    """How many packets have come to each, since the last look."""
    time.sleep(0.2)
    counts = []
    for k in ends:
        n = 0
        while True:
            try:
                k.recv(4096)
            except BlockingIOError:
                break
            n += 1
        counts.append(n)
    return counts


out = G.GlowOut()
out.aim(addrs, addrs[1:])                              # (a grid, and five lights of your own)
pic = np.zeros((8, 8, 3), dtype=np.uint8)
for _ in range(30):
    out.frame(pic)
counts = came()
check(f"a second of a game's pictures, to a grid and five lights: the grid gets every one, the lights "
      f"{G.LAMPS_EACH} at a time, in turn ({counts})", counts == [30] + [30 * G.LAMPS_EACH // 5] * 5)
out.event("beat", 1.0)
out.music((1, 2, 3))
check("...a beat, and music's colour: every one of them, at once", came() == [2] * 6)
out.event("beat", 1.0, lamps=False)
check("...a beat that's not for the lights (Pulse to music off, where it's played): just the grid",
      came() == [1, 0, 0, 0, 0, 0])
out.aim(addrs[:3], addrs[1:3])
for _ in range(10):
    out.frame(pic)
counts = came()
check(f"...just two lights: every picture to each ({counts})", counts == [10, 10, 10, 0, 0, 0])
out.aim(addrs[:2] + addrs[3:], addrs[3:])              # (three of them now, and another grid)
for _ in range(9):
    out.frame(pic)
counts = came()
check(f"...the lights changed while it plays: still in turn ({counts})", counts == [9, 9, 0, 6, 6, 6])
out.aim(addrs[:1])
out.frame(pic)
check("...none: the grid, as ever", came() == [1, 0, 0, 0, 0, 0])
out.close()
for k in ends:
    k.close()

# ---- media mode: a light's one of the places colours and beats go ----------------------------------------------------
HOME = S + "/home/u"
os.makedirs(HOME + "/Music")
g.STATE_FILE = S + "/state.json"; g.CACHE_DIR = S + "/cache"; g.PLEX_FILE = S + "/plex.json"
g.home_dir = lambda: HOME
g.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "", "returncode": 0, "stderr": ""})()
m = g.Media()
m.lamps_port = 0
check("media mode, with no lights about: nowhere for colours to go, music as ever",
      m.glow_targets() == [] and not m.glow_beats_wanted() and m.lamps_on() == [])
m.lamps_start()
m.lamps_start()
check("...listening for them (once)", m.glow_lamps is not None and m.glow_lamps.port > 0)
s.sendto(G.lamp_packet("ESP32 A1B2C3", 1, 1.0), ("127.0.0.1", m.glow_lamps.port))
for _ in range(50):
    if m.lamps_on():
        break
    time.sleep(0.05)
check(f"a light says it's there: one of the places a game's colours and music's beats go ({m.glow_targets()})",
      m.glow_targets() == [("127.0.0.1", G.GLOW_PORT)])
# the web page's LED backlight: the boards, and a colour for each
check("no board found yet: the web page's Library has no LED backlight on a Pietato with no LEDs of its own; one "
      "found: it has, from then on", not g.Media.glow_shown(type("M", (), {"glow_lamps": None, "glow_can": lambda s: False})())
      and m.glow_shown() and not m.glow_can())
now = m.web_glow_now()
check(f"...it lists the board ({now['boards']}), with the colours it can be given ({len(now['colours'])}) and the "
      f"boards' pulse to music ({[r['key'] for r in now['rows']]}); {now['status']!r}",
      now["boards"] == [{"ip": "127.0.0.1", "name": "ESP32 A1B2C3", "leds": 1, "colour": None}]
      and now["colours"][:3] == [["Warm white", "#ffc26e"], ["White", "#ffffff"], ["Red", "#ff0000"]]
      and len(now["colours"]) == 10 and [r["key"] for r in now["rows"]] == ["glow_beat"]
      and now["status"] == "1 ESP32 board found" and not now["can"])
r = m.web_settings_do({"key": "glow_lamp", "value": {"ip": "127.0.0.1", "colour": "#ff0000"}})
check(f"...a board with the older sketch: no colour to give it, and said ({r})", "newer sketch" in r.get("error", ""))
s.sendto(G.state_packet(None, 1.0), ("127.0.0.1", m.glow_lamps.port))
for _ in range(50):
    if m.web_lamps()[0]["colour"] == "":
        break
    time.sleep(0.05)
check(f"...one that keeps a colour, with none yet ({m.web_lamps()})", m.web_lamps()[0]["colour"] == "")
m.lamp_port = BPORT
told()
r = m.web_settings_do({"key": "glow_lamp", "value": {"ip": "127.0.0.1", "colour": "#ff0000"}})
got = told()
check(f"...given one on the web page: the board's told ({len(got)} packets: {r}); shown as that "
      f"({m.web_lamps()[0]['colour']})", r == {"ok": True} and len(got) == 2
      and got[0][12:] == bytes((1, 255, 0, 0)) and m.web_lamps()[0]["colour"] == "#ff0000")
r = m.web_settings_do({"key": "glow_lamp", "value": {"ip": "127.0.0.1", "colour": "#12ABef"}})
got = told()
check(f"...any other colour ({r})", r == {"ok": True} and got[0][12:] == bytes((1, 0x12, 0xAB, 0xEF))
      and m.web_lamps()[0]["colour"] == "#12abef")
r = m.web_settings_do({"key": "glow_lamp", "value": {"ip": "127.0.0.1", "find": True}})
got = told()
check(f"...Which one?: told the colour it has again, so it shows it a moment ({r})",
      r == {"ok": True, "said": "ESP32 A1B2C3 lights up for a moment"} and got[0][12:] == bytes((1, 0x12, 0xAB, 0xEF)))
r = m.web_settings_do({"key": "glow_lamp", "value": {"ip": "127.0.0.1", "colour": ""}})
got = told()
check(f"...what's playing again ({r})", r == {"ok": True} and got[0][12:] == bytes(4)
      and m.web_lamps()[0]["colour"] == "")
bad = [m.web_settings_do({"key": "glow_lamp", "value": v}) for v in (
    {"ip": "10.9.9.9", "colour": "#ff0000"}, {"ip": "127.0.0.1", "colour": "red"}, {"ip": "127.0.0.1", "colour": "#12345"},
    {"ip": "127.0.0.1", "colour": 5}, {"ip": "127.0.0.1"}, "127.0.0.1", None, {"colour": "#ff0000"})]
check(f"...a board that isn't there, or what isn't a colour: said, and nothing sent ({[b.get('error') for b in bad][:3]})",
      all("error" in b for b in bad) and told() == [])
r = m.web_settings_do({"key": "glow_beat", "value": "Off"})
check(f"...the boards' pulse to music, off from the web page too ({r})", r.get("ok") and m.setting("glow_beat") == "Off"
      and m.web_glow_now()["rows"][0]["value"] == "Off")
m.web_settings_do({"key": "glow_beat", "value": "On"})
del m.lamp_port
m.glow_lamps.take(G.lamp_packet("ESP32 A1B2C3", 1, 1.0), "127.0.0.1", m.glow_lamps.clock())   # (still there)
check("...and music's played for its beat (on party mode's player) while it's there", m.glow_beats_wanted())


class Run:
    state, ended, game = "on", False, {"path": "/x", "title": "x", "system": "nes"}

    def __init__(self):
        self.sent = []

    def send(self, line):
        self.sent.append(line)
        return True


game = Run()
m.glow_game_tick(game, time.monotonic() + 10)
m.glow_game_tick(game, time.monotonic() + 20)
check(f"a game: its emulator told where its colours go, the light marked as one ({game.sent})",
      game.sent == [f"glow +127.0.0.1:{G.GLOW_PORT}"])


class Out:
    """(Where this one's music goes, noted.)"""
    to = (("127.0.0.1", G.GLOW_PORT),)

    def __init__(self):
        self.said = []

    def event(self, name, strength=1.0, at=None, lamps=True):
        self.said.append((name, lamps))

    def aim(self, to, lamps=()):
        self.to = tuple(to)

    def close(self):
        pass


m.glow_out = Out()
m.glow_beat(time.monotonic(), 1.0)
check(f"...a beat found in it: to the light too ({m.glow_out.said})", m.glow_out.said == [("beat", True)])
m.glow_pick("glow_beat", "Off")
check("...unless Pulse to music is off here (Apps > LED backlight > START): it still gets a game's colours",
      not m.glow_beats_wanted() and m.glow_targets() == [("127.0.0.1", G.GLOW_PORT)])
m.glow_beat(time.monotonic(), 1.0)
check(f"...and a beat found for another's grid then: not to the light ({m.glow_out.said[-1]})",
      m.glow_out.said[-1] == ("beat", False))
m.glow_pick("glow_beat", "On")
check("...and on again: its beat again", m.glow_beats_wanted())
m.glow_out = None
APPS = next(k for k, t in enumerate(g.LIBRARY) if t["name"] == "Apps")


def led_app():
    """Apps' LED backlight, as its list has it now: what it says under its name, or None when it's not there."""
    m.load_tab(APPS)
    return next((it.get("sub") for it in m.items[APPS] if it["title"] == "LED backlight"), None)


page = type("P", (), {"blurb": "x"})()
m.glow_page(page)
check(f"a Pietato with no LEDs of its own (this one), a board on: Apps has LED backlight, for the boards "
      f"({led_app()!r}), and its page is theirs ({page.facts}; {page.says}; {page.own_hints})",
      not m.glow_can() and led_app() == "Your ESP32 boards' LEDs" and page.plain
      and page.facts == [("ESP32 boards", "1"), ("Pulse to music", "On")]
      and page.says == ("1 ESP32 board", "Lit by this Pietato's games and music")
      and page.own_hints == [("A", "Pulse off")])
m.glow_lamps.take(G.lamp_packet("another", 1, 1.0), "10.0.0.81", m.glow_lamps.clock())
m.press_glow(page, "a", False)
m.glow_page(page)
check(f"...A: their pulse to music off (music as ever again), and said ({page.facts}; {page.says}; {page.own_hints})",
      m.setting("glow_beat") == "Off" and not m.glow_beats_wanted()
      and page.facts == [("ESP32 boards", "2"), ("Pulse to music", "Off")]
      and page.says == ("2 ESP32 boards", "Lit by this Pietato's games") and page.own_hints == [("A", "Pulse on")])
for name in ("start", "left", "up", "select", "x"):
    m.press_glow(page, name, False)
check("...its other buttons: nothing (there's no card of LEDs to set here), B goes back as ever",
      m.sim_opts is None and m.setting("glow_beat") == "Off" and m.setting("glow_on") != "On"
      and m.press_glow(page, "b", False) is False)
m.press_glow(page, "a", False)
check("...A again: on", m.setting("glow_beat") == "On" and m.glow_beats_wanted())

# ---- the song at start-up (Settings > Random song at start-up): playing before the network's up -----------------------
import wave
os.makedirs(S + "/bin", exist_ok=True)
open(S + "/bin/aplay", "w").write('''#!/usr/bin/env python3
import sys, time
args = sys.argv[1:]
rate = int(args[args.index("-r") + 1]) if "-r" in args else 48000
inp, start, played = sys.stdin.buffer, None, 0
while True:
    data = inp.read(rate // 100 * 4)
    if not data:
        break
    start = start or time.monotonic()
    played += len(data) // 4
    wait = start + played / rate - time.monotonic()
    if wait > 0:
        time.sleep(wait)
''')
os.chmod(S + "/bin/aplay", 0o755)
os.environ["PATH"] = S + "/bin:" + os.environ["PATH"]
for t in g.LIBRARY:
    if "dirs" in t:
        t["dirs"] = [x.replace("/home/*", HOME) for x in t["dirs"]]
RATE = 48000
tt = np.arange(RATE * 14) / RATE
sig = 0.05 * np.sin(2 * np.pi * 440 * tt) + 0.02 * np.random.default_rng(1).standard_normal(len(tt))
for kick in np.arange(0.5, 14, 0.5):                   # (a kick drum twice a second)
    on = (tt >= kick) & (tt < kick + 0.25)
    x = tt[on] - kick
    sig[on] += 0.6 * np.sin(2 * np.pi * (60 + 40 * np.exp(-x * 30)) * x) * np.exp(-x * 12)
KICKS = HOME + "/Music/Kicks.wav"
with wave.open(KICKS, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE)
    w.writeframes((np.stack([sig, sig], -1) * 0.8 * 32767).astype("<i2").tobytes())
spawned = []


class Plain:
    """(The plain player, mplayer: started, as far as media mode knows.)"""

    def __init__(self):
        self.stdin = open(os.devnull, "w")
        self.stdout, self.stderr = iter(()), iter(())
        self.returncode = None

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = 0
        return 0

    def kill(self):
        self.returncode = -9


def spawn(self, args, target):
    self.started = time.monotonic()
    self.proc = Plain()
    spawned.append(target)


g.PlayerScreen.spawn = spawn


class Lights:
    """(Where a Pietato's colours and beats go, noted: what GlowOut sends.)"""

    def __init__(self):
        self.to, self.said = (), []

    def aim(self, to, lamps=()):
        self.to = tuple(to)

    def music(self, rgb):
        self.said.append("colour")

    def event(self, name, strength=1.0, at=None, lamps=True):
        self.said.append(name if lamps else name + ", not for the boards")

    def close(self):
        pass


def board_says(mm, there=True):
    """A board says it's there, to that Pietato (or it's not been heard: the network's still coming up)."""
    with mm.glow_lamps.lock:
        mm.glow_lamps.heard.clear()
    if there:
        mm.glow_lamps.take(G.lamp_packet("ESP32 A1B2C3", 1, 1.0), "127.0.0.1", mm.glow_lamps.clock())
    mm.glow_seen = mm.glow_mind_at = 0.0


def goes(mm, secs):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        mm.glow_tick(time.monotonic())
        time.sleep(0.02)


def player(mm):
    return type(mm.proc).__name__


board_says(m, False)
m.state["glow"].clear()
m.glow_net_seen = False
m.random_song()
check(f"the song at start-up, no board heard yet (the network's still coming up) and none remembered: on the plain "
      f"player, which finds no beats ({player(m)})", player(m) == "Plain" and spawned == [KICKS] and m.queue_random
      and not m.glow_beats_wanted())
m.pos = 3.2                                            # (where the plain player says it's got to)
board_says(m)
m.glow_tick(time.monotonic())
check(f"...a board says it's there a few seconds in: the song's moved to the player that finds its beats, from "
      f"where it was ({player(m)}, {getattr(getattr(m.proc, 'player', None), 'pos0', None)} s in), your queue as it "
      f"was", player(m) == "PartyProc" and spawned == [KICKS] and abs(m.proc.player.pos0 - 3.2) < 0.01
      and m.queue_random and m.queue[m.qi]["src"] == KICKS and m.proc.player.beats is not None)
check(f"...and that there are boards is kept for the next start-up ({json.load(open(g.STATE_FILE)).get('glow')})",
      m.state["glow"] == {"lights": True} and json.load(open(g.STATE_FILE)).get("glow") == {"lights": True})
lights = m.glow_out = Lights()
m.glow_seen = 0.0
goes(m, 3.0)
check(f"...the board has its beats from then on ({lights.said.count('beat')} in three seconds, and its colour)",
      lights.said.count("beat") >= 3 and "colour" in lights.said and lights.to == (("127.0.0.1", G.GLOW_PORT),))
m.stop()
m.glow_out = None
board_says(m, False)
m.play([g.item(KICKS, "Kicks", "audio", KICKS)], 0, show=False)
m.started -= g.GLOW_CATCH + 1                          # (a minute and more ago)
board_says(m)
m.glow_tick(time.monotonic())
check(f"a song well under way when a board turns up: left as it is, on the plain player (the next has its beats) "
      f"({player(m)})", player(m) == "Plain" and spawned == [KICKS, KICKS])
m.stop()
board_says(m, False)
m.play([g.item(KICKS, "Kicks", "audio", KICKS)], 0, show=False)
m.party_play = lambda it, kind, target, start: spawn(m, [], target)   # (it can't be played there, whyever)
board_says(m)
for _ in range(3):
    m.glow_mind_at = 0.0
    m.glow_tick(time.monotonic())
del m.party_play
check(f"...one that can't be moved: tried once, not again and again ({len(spawned)} started in all)",
      player(m) == "Plain" and len(spawned) == 4)
m.stop()
m2 = g.Media()                                         # (started again: what it kept is read)
m2.lamps_port = 0
m2.lamps_start()
lights = m2.glow_out = Lights()
m2.random_song()
check(f"started again, the boards remembered: the song at start-up is on the player that finds its beats from the "
      f"start, before any board's heard ({player(m2)})", m2.glow_expected() and player(m2) == "PartyProc"
      and len(spawned) == 4 and m2.proc.player.beats is not None and m2.queue_random and not m2.glow_early)
goes(m2, 1.5)
quiet = list(lights.said)
board_says(m2)
goes(m2, 3.0)
check(f"...nothing's sent while none is heard ({quiet}); once one says it's there, it has the song's beats, with no "
      f"break in the song ({lights.said.count('beat')} in three seconds)", quiet == []
      and lights.said.count("beat") >= 3 and "colour" in lights.said and player(m2) == "PartyProc" and len(spawned) == 4)
m2.stop()
board_says(m2, False)
m2.glow_net_seen, m2.glow_since = False, time.monotonic() - g.GLOW_FORGET - 1   # (on five minutes, and no board)
m2.glow_tick(time.monotonic())
m2.random_song()
check(f"a start with none of them for five minutes: taken to be gone, and the song at start-up is on the plain "
      f"player again ({player(m2)}, {json.load(open(g.STATE_FILE)).get('glow')})", player(m2) == "Plain"
      and m2.state["glow"] == {"lights": False} and json.load(open(g.STATE_FILE)).get("glow") == {"lights": False})
m2.stop()
m2.state["glow"]["lights"] = True
m2.set_setting("glow_beat", "Off")
m2.random_song()
check(f"...and with Pulse to music off, they're not waited for ({player(m2)})", not m2.glow_expected()
      and player(m2) == "Plain")
m2.stop()
m2.lamps_stop()
m.save_state()                                         # (the first one's again, as the rest of this goes by it)
board_says(m)
m.glow_lamps.take(G.lamp_packet("another", 1, 1.0), "10.0.0.81", m.glow_lamps.clock())

# ---- the web page, in a real browser: Library > LED backlight lists the boards, a colour for each --------------------


class Board(threading.Thread):
    """A stand-in board at an address of this machine's own (127.0.0.x), doing as the sketch does: it says it's there
    and how it is every second, keeps the colour it's told (told: each one, in turn; a Pietato says each twice, and
    that's once here) and says it back. (old: the older sketch, which says only that it's there.)"""

    def __init__(self, ip, port, name, leds, to, old=False, colour=None):
        super().__init__(daemon=True)
        self.name_, self.leds, self.to, self.old, self.colour = name, leds, to, old, colour
        self.told, self.done, self.last = [], False, None
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((ip, port))
        self.sock.settimeout(0.05)
        self.ip, self.port = self.sock.getsockname()

    def say(self):
        self.sock.sendto(G.lamp_packet(self.name_, self.leds, time.monotonic()), self.to)
        if not self.old:
            self.sock.sendto(G.state_packet(self.colour, time.monotonic()), self.to)

    def run(self):
        said = 0.0
        while not self.done:
            if time.monotonic() - said >= 1.0:
                said = time.monotonic()
                self.say()
            try:
                data = self.sock.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if len(data) == 16 and data[:4] == b"PG\x01C" and data[12] <= 1 and not self.old:
                self.colour = tuple(data[13:16]) if data[12] else None
                if data != self.last:                  # (each is said twice: the same packet again)
                    self.told.append(self.colour)
                self.last = None if data == self.last else data
                self.say()
        self.sock.close()


class FB:
    w, h = 640, 480
    last = None
    def show(self, img): FB.last = img.copy()
    def show_part(self, img, box): FB.last = img.copy()
    def invalidate(self): pass
    def close(self): pass


class UI:
    def write(self, *a): pass
    def syn(self): pass


def until(cond, secs):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return bool(cond())


logging.getLogger("werkzeug").setLevel(logging.ERROR)
from werkzeug.serving import make_server
m.load_fonts(); m.fb = FB(); m.active = True

# ---- its page in Apps, drawn (a Pietato with no LEDs of its own): your boards in its box, never a black screen --------
at = m.glow_lamps.clock()
for name, ip, colour in (("ESP32 A1B2C3", "127.0.0.1", (255, 0, 0)), ("ESP32 77AA01", "10.0.0.82", None)):
    m.glow_lamps.take(G.lamp_packet(name, 64 if colour else 1, 1.0), ip, at)
    m.glow_lamps.take(G.state_packet(colour, 1.0), ip, at)
m.glow_lamps.take(G.lamp_packet("another", 1, 1.0), "10.0.0.81", at)   # (one with the older sketch)


def drawn():
    """The LED backlight's page as it's drawn on the screen now: (its sim, the picture as numbers)."""
    m.web_tab("LED backlight")
    sim = m.sim_game()
    m.dirty = True
    m.flush()
    return sim, np.asarray(FB.last.convert("RGB")).astype(int)


def about(pic, colour, by=40):
    """How many of a picture's pixels are about that colour."""
    return int((np.abs(pic - np.array(colour)).max(axis=2) <= by).sum())


m.set_setting("sim_full", "Off")
sim, pic = drawn()
check(f"its page, drawn: in its box, your boards, by name ({sim.lamps}), an LED each: one lit in its own colour "
      f"({about(pic, (255, 0, 0))} red pixels), the others dark ({about(pic, (40, 44, 51), 3)})",
      sim.plain and (sim.w, sim.h) != (640, 480)
      and sim.lamps == [("another", 1, None), ("ESP32 77AA01", 1, None), ("ESP32 A1B2C3", 64, (255, 0, 0))]
      and about(pic, (255, 0, 0)) > 250 and about(pic, (40, 44, 51), 3) > 600)
FB.last.convert("RGB").save(S + "/boards_page.png")
m.set_setting("sim_full", "On")                        # (SELECT on any sim: full screen, kept for every one of them)
sim, full = drawn()
bright = int((full.max(axis=2) > 150).sum())
check(f"...with Full screen on: this page in its box all the same, not a black screen (it has nothing to fill one "
      f"with): {bright} bright pixels, {about(full, (255, 0, 0))} red", not m.sim_full()
      and (sim.w, sim.h) != (640, 480) and bright > 1500 and about(full, (255, 0, 0)) == about(pic, (255, 0, 0)))
m.web_tab("Fish Tank")
kept = m.sim_full()
m.glow_can = lambda: True
m.web_tab("LED backlight")
check("...the other sims full screen as ever, and a Pi's own LEDs' page too", kept and m.sim_full())
del m.glow_can
m.set_setting("sim_full", "Off")
m.glow_lamps.take(G.lamp_packet("x", 1, 1.0), "10.0.0.83", at)
for k in range(30):                                    # (a lot of boards: no room for names, just their LEDs)
    m.glow_lamps.take(G.lamp_packet(f"ESP32 {k:06X}", 1, 1.0), f"10.0.2.{k}", at)
    m.glow_lamps.take(G.state_packet((0, 0, 255) if k % 2 else None, 1.0), f"10.0.2.{k}", at)
sim, many = drawn()
check(f"...a lot of boards (34): an LED each still ({about(many, (0, 0, 255))} blue pixels for 15 of them)",
      len(sim.lamps) == 34 and about(many, (0, 0, 255)) > 15 * 60)
FB.last.convert("RGB").save(S + "/boards_page_many.png")
with m.glow_lamps.lock:
    m.glow_lamps.heard.clear()
    m.glow_lamps.states.clear()
for k in range(4):                                     # (names as long as a board's can be: cut to fit under its LED)
    m.glow_lamps.take(G.lamp_packet(f"A light with a long name{k}"[-24:], 300, 1.0), f"10.0.3.{k}", at)
    m.glow_lamps.take(G.state_packet((0, 255, 0), 1.0), f"10.0.3.{k}", at)
sim, long = drawn()
cut = sorted((v[1], k[0]) for k, v in sim.tags.items() if k[0].endswith("…"))
check(f"...names as long as they can be: cut to fit under their LEDs ({cut[:1]}, in {sim.w / 4:.0f} pixels each), "
      f"each lit ({about(long, (0, 255, 0))} green pixels)", len(sim.lamps) == 4 and cut
      and cut[0][0] <= sim.w / 4 - 4 and about(long, (0, 255, 0)) > 4 * 250)
g.list_devices = lambda: []                            # (no controllers here)
control = g.Control()
server = g.serve_control(m, control, port=0, key="k" * 32)
done = threading.Event()
main = threading.Thread(target=lambda: g.run(UI(), m, control, stop=done.is_set), daemon=True)
main.start()
sys.path.append(ROOT + "/pitato")
import webui
webui.HOME = HOME; webui.STATIC = S + "/static"; os.makedirs(webui.STATIC + "/fonts")
for f in os.listdir(ROOT + "/static/fonts"):
    shutil.copy(ROOT + "/static/fonts/" + f, webui.STATIC + "/fonts/")
webui.FONTS_DIR = webui.STATIC + "/fonts"
open(S + "/control-key", "w").write("k" * 32)
webui.STATE_FILE = g.STATE_FILE; webui.NET_ROOT = g.NET_ROOT
webui.CONTROL = ("127.0.0.1", server.server_address[1]); webui.CONTROL_KEY = S + "/control-key"
web = make_server("127.0.0.1", 0, webui.app, threaded=True)
threading.Thread(target=web.serve_forever, daemon=True).start()
with m.glow_lamps.lock:                                # (a Pietato that's found no board yet)
    m.glow_lamps.heard.clear()
    m.glow_lamps.states.clear()
    m.glow_lamps.ever = False
to = ("127.0.0.1", m.glow_lamps.port)
one = Board("127.0.0.2", 0, "ESP32 0A11CE", 1, to)
two = Board("127.0.0.3", one.port, "ESP32 B0B0B0", 64, to, colour=dict(G.COLOURS)["Purple"])
old = Board("127.0.0.4", one.port, "ESP32 C0FFEE", 1, to, old=True)
m.lamp_port = one.port
from playwright.async_api import async_playwright
ROW = ".set-row[data-key='lamp:127.0.0.2']"
LOOK = """(() => {
  const rows = [...document.querySelectorAll('.gl-lamps .set-row[data-key^="lamp:"]')];
  const shown = (x) => !!x && getComputedStyle(x).display !== 'none';
  return {rows: rows.map((r) => [r.querySelector('.set-l b').textContent, r.querySelector('.gl-meta span').textContent,
                                 r.querySelectorAll('.swatch').length, r.querySelectorAll('.gl-find').length,
                                 [...r.querySelectorAll('.swatch[aria-pressed="true"]')].map((x) => x.getAttribute('aria-label') || x.textContent),
                                 r.querySelector('.swatch.any.on') ? r.querySelector('.swatch.any').style.getPropertyValue('--c') : '',
                                 r.querySelector('.set-c > .set-note') ? r.querySelector('.set-c > .set-note').textContent : '']),
          names: rows.length ? [...rows[0].querySelectorAll('.swatch')].map((x) => x.getAttribute('aria-label') || x.title) : [],
          head: document.querySelector('.gl-lamps header h2') ? document.querySelector('.gl-lamps header h2').textContent : '',
          note: document.querySelector('.gl-lamps .note b') ? document.querySelector('.gl-lamps .note b').textContent : '',
          board: shown(document.querySelector('.gl-board')), sub: document.querySelector('.content-h .src').textContent,
          set: [...document.querySelectorAll('.gl-set .set-row')].filter(shown).map((r) => r.dataset.key),
          more: [...document.querySelectorAll('.gl-lamps .set-row:not([data-key^="lamp:"])')].map((r) => r.dataset.key),
          under: (() => {                        // (the boards' list: under the picture of the LEDs, beside the settings)
            const a = document.querySelector('.gl-board').getBoundingClientRect();
            const c = document.querySelector('.gl-lamps').getBoundingClientRect();
            const e = document.querySelector('.gl-set').getBoundingClientRect();
            return c.top >= a.bottom && c.right <= e.left && Math.abs(c.left - a.left) < 2;
          })(),
          text: document.querySelector('#content').innerText};
})()"""


async def browse():
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        pg = await b.new_page(viewport={"width": 1180, "height": 900})
        oops = []
        pg.on("pageerror", lambda e: oops.append(str(e)))
        await pg.goto(f"http://127.0.0.1:{web.server_port}/#library")
        await pg.wait_for_selector(".ltab", timeout=10000)
        tabs = await pg.eval_on_selector_all(".ltab", "bs => bs.map((b) => b.textContent)")
        check(f"the page, on a Pietato with no LEDs of its own that's found no board: no LED backlight in its Library "
              f"({len(tabs)} tabs)", tabs and "LED backlight" not in tabs)
        for x in (one, two, old):
            x.start()
        await pg.wait_for_selector(".ltab:has-text('LED backlight')", timeout=8000)
        check("...boards found: it's there, without the page being loaded again", True)
        await pg.click(".ltab:has-text('LED backlight')")
        await pg.wait_for_function("document.querySelectorAll('.gl-lamps .set-row[data-key^=lamp]').length === 3",
                                   timeout=8000)
        got = await pg.evaluate(LOOK)
        check(f"...its page: the boards, by name, and how many LEDs each has ({[r[:2] for r in got['rows']]}); no "
              f"picture of LEDs behind a TV, nor anything about there being none ({got['sub']!r})",
              [r[:2] for r in got["rows"]] == [["ESP32 0A11CE", "1 LED"], ["ESP32 B0B0B0", "64 LEDs"],
                                               ["ESP32 C0FFEE", "1 LED"]]
              and not got["board"] and got["head"] == "ESP32 boards" and "No LEDs here" not in got["text"]
              and got["sub"] == "3 ESP32 boards found")
        check(f"...a colour for each: what's playing (Auto), the colours by name, or any other ({got['names']}); and "
              f"a way to tell which is which", got["names"] == ["The colours of what's playing"]
              + [n for n, c in G.COLOURS if isinstance(c, tuple)] + ["Another colour"]
              and got["rows"][0][2:4] == [12, 1] and got["rows"][1][2:4] == [12, 1])
        check(f"...as each is: one taking what's playing ({got['rows'][0][4]}), one with a colour of its own "
              f"({got['rows'][1][4]}); one with the older sketch has none to give, and it's said why "
              f"({got['rows'][2][6]!r})", got["rows"][0][4] == ["Auto"] and got["rows"][1][4] == ["Purple"]
              and got["rows"][2][2:4] == [0, 0] and "newer sketch" in got["rows"][2][6])
        check(f"...and their pulse to music, with them ({got['more']})", got["more"] == ["glow_beat"]
              and got["set"] == [])
        await pg.screenshot(path=S + "/boards_web.png")
        await pg.click(f"{ROW} .swatch[aria-label='Red']")
        pressed = await pg.eval_on_selector_all(f"{ROW} .swatch[aria-pressed='true']", "xs => xs.map((x) => x.title)")
        took = await asyncio.to_thread(until, lambda: one.told == [(255, 0, 0)], 5)
        check(f"a colour tapped: pressed at once ({pressed}), and that board's told it, no other ({one.told}, "
              f"{two.told})", pressed == ["Red"] and took and two.told == [] and old.told == [])
        await asyncio.sleep(4.0)                       # (the page asks again, and the board's said how it is)
        got = await pg.evaluate(LOOK)
        check(f"...and it stays, as the board says it is ({got['rows'][0][4]}; {m.web_lamps()[0]['colour']})",
              got["rows"][0][4] == ["Red"] and m.web_lamps()[0]["colour"] == "#ff0000")
        await pg.click(f"{ROW} .gl-find")
        took = await asyncio.to_thread(until, lambda: one.told == [(255, 0, 0)] * 2, 5)
        await pg.wait_for_function("document.querySelector('#toast').textContent.includes('lights up')", timeout=5000)
        said = await pg.inner_text("#toast")
        check(f"Which one?: told its colour again, so it lights a moment, and said ({said!r})", took
              and said == "ESP32 0A11CE lights up for a moment")
        await pg.evaluate("""(row) => {                // (the browser's own picker: dragged through a few, left at one)
          const inp = document.querySelector(row + ' .swatch.any input');
          for (const v of ['#101010', '#202020', '#303030', '#12abef']) {
            inp.value = v;
            inp.dispatchEvent(new Event('input', {bubbles: true}));
          }
          inp.dispatchEvent(new Event('change', {bubbles: true}));
        }""", ROW)
        took = await asyncio.to_thread(until, lambda: one.told[-1] == (0x12, 0xAB, 0xEF), 5)
        await asyncio.sleep(0.5)
        got = await pg.evaluate(LOOK)
        check(f"any other colour, from the browser's picker: the board follows as it's dragged, one told at a time, "
              f"and is left at the last ({one.told[2:]}); the picker's swatch lit in it ({got['rows'][0][5]}), no "
              f"other pressed", took and 2 <= len(one.told[2:]) <= 4 and one.told[2] == (0x10, 0x10, 0x10)
              and got["rows"][0][5] == "#12abef" and got["rows"][0][4] == [])
        await pg.click(f"{ROW} .swatch.auto")
        took = await asyncio.to_thread(until, lambda: one.told[-1] is None, 5)
        check(f"Auto: told to have none, so it takes what's playing again ({one.told[-1:]})", took)
        await pg.click(".gl-lamps .set-row[data-key='glow_beat'] .seg button:has-text('Off')")
        took = await asyncio.to_thread(until, lambda: m.setting("glow_beat") == "Off", 5)
        check("their pulse to music, off from here", took and not m.glow_beats_wanted())
        await pg.click(".gl-lamps .set-row[data-key='glow_beat'] .seg button:has-text('On')")
        await asyncio.to_thread(until, lambda: m.setting("glow_beat") == "On", 5)
        await pg.set_viewport_size({"width": 390, "height": 844})
        await asyncio.sleep(0.4)
        wide = await pg.evaluate("document.documentElement.scrollWidth")
        check(f"on a phone: nothing wider than it ({wide})", wide <= 390)
        await pg.screenshot(path=S + "/boards_web_phone.png", full_page=True)
        await pg.set_viewport_size({"width": 1180, "height": 900})
        m.glow_can = lambda: True                      # (a Pi that can have LEDs of its own: the boards under them)
        await pg.wait_for_function("getComputedStyle(document.querySelector('.gl-board')).display !== 'none'",
                                   timeout=8000)
        await pg.wait_for_selector(".gl-set .set-row[data-key='glow_on']", timeout=8000)
        got = await pg.evaluate(LOOK)
        check(f"a Pi with LEDs of its own: its picture and settings as ever ({got['set'][:3]}), the boards under "
              f"the picture ({len(got['rows'])}), their pulse to music the LEDs' own ({got['more']})", got["board"]
              and got["set"][:2] == ["glow_on", "glow_colour"] and "glow_beat" in got["set"] and got["more"] == []
              and len(got["rows"]) == 3 and got["under"] and got["sub"].endswith("3 ESP32 boards found"))
        await pg.screenshot(path=S + "/boards_web_pi.png", full_page=True)
        for x in (one, two, old):                      # (the boards unplugged)
            x.done = True
        with m.glow_lamps.lock:
            m.glow_lamps.heard.clear()
        await pg.wait_for_function("document.querySelector('.gl-lamps').hidden", timeout=8000)
        check("...the boards gone: nothing about them there", True)
        del m.glow_can
        await pg.wait_for_function("!!document.querySelector('.gl-lamps .note')", timeout=8000)
        got = await pg.evaluate(LOOK)
        await pg.reload()
        await pg.wait_for_selector(".ltab", timeout=10000)
        tabs = await pg.eval_on_selector_all(".ltab", "bs => bs.map((b) => b.textContent)")
        check(f"a Pietato with no LEDs of its own, its boards gone: said ({got['note']!r}; {got['sub']!r}), no "
              f"settings left ({got['set']}), and its Library keeps the LED backlight for when they're back",
              got["note"] == "No ESP32 boards on now" and got["sub"] == "" and got["set"] == []
              and not got["rows"] and "LED backlight" in tabs)
        check(f"no errors on the page ({oops})", not oops)
        await b.close()


asyncio.run(browse())
done.set()
main.join(5)
web.shutdown()
del m.lamp_port
m.glow_lamps.take(G.lamp_packet("ESP32 A1B2C3", 1, 1.0), "127.0.0.1", m.glow_lamps.clock())
m.glow_lamps.take(G.lamp_packet("another", 1, 1.0), "10.0.0.81", m.glow_lamps.clock())
m.glow_can = lambda: True                              # (one that can have LEDs: its own page, the boards a line of it)
m.glow_page(page)
now = m.web_glow_now()
check(f"a Pi with LEDs of its own: its page says how many boards it's found ({page.facts[-1]}), and the web page's "
      f"({now['status']!r})", not page.plain and page.facts[-1] == ("ESP32 boards", "2") and len(page.facts) == 7
      and now["status"].endswith("2 ESP32 boards found") and page.own_hints[0][0] == "A"
      and page.own_hints[-1] == ("START", "More"))
del m.glow_can
m.lamps_stop()
m.glow_page(page)
check(f"the boards gone: nothing about them on a Pi's page, and no LED backlight in Apps here ({page.facts}; "
      f"{page.says}; {led_app()!r})",
      page.facts == [("ESP32 boards", "None"), ("Pulse to music", "On")]
      and page.says == ("No LEDs here", "They go on a Pi behind the TV") and led_app() is None
      and m.web_glow_now()["status"] == "" and m.web_glow_now()["boards"] == []
      and m.web_glow_now()["rows"] == [] and not m.glow_shown())
m.press_glow(page, "a", False)
check("...A there: nothing to turn on, and said", m.setting("glow_beat") == "On" and m.setting("glow_on") != "On")
check("media mode closing: not listened for any more", m.glow_lamps is None and m.glow_targets() == []
      and not m.glow_beats_wanted())
s.close()
board.close()
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
