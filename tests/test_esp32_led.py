"""An ESP32's own LED lit by your Pietatos (esp32/pietato_led, and glow.py's Lamps). The sketch itself, built here
with stand-ins for the board (its WiFi, its clock, its LED: what the LED's sent is noted) and run by its own loop:
looking for the WiFi it's a dim amber, and says nothing; on it, it says it's there every couple of seconds, to everyone
on its network, in words a Pietato takes (and only from your network: a light's listened for there, kept while it
keeps saying so). Lit by a Pietato's own packets (glow.py makes them): music's colour between beats, a beat at the
moment it's due by the sender's clock (not before), a game's colours (their blend), a hit's red, an achievement's
gold, dark again once it's quiet; nothing for a packet that isn't one; one Pietato followed at a time. A strip of LEDs
instead: all of them that colour. Then media mode: a light found is one of the places a game's colours and music's
beats go, and music's played for its beat while one's there (unless Pulse to music is off: Apps > LED backlight has
that, on a Pietato with no LEDs of its own too while a board's on); however many there are, a
game's pictures go to a couple of them at a time, in turn (a beat to all at once), and a board that gets them only now
and then keeps its colour between them."""
import json, os, shutil, socket, subprocess, sys, time
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
inline long long esp_timer_get_time() { return (long long)llround(NOW * 1e6); }
inline void delay(int ms) { NOW += ms / 1000.0; }
#define RGB_BUILTIN 97
#define WL_CONNECTED 3
#define WIFI_STA 1
struct IPAddress {
  uint8_t b[4];
  IPAddress() : b{0, 0, 0, 0} {}
  IPAddress(uint8_t a, uint8_t c, uint8_t d, uint8_t e) : b{a, c, d, e} {}
  uint8_t operator[](int i) const { return b[i]; }
  bool operator==(const IPAddress &o) const { return !memcmp(b, o.b, 4); }
};
struct WiFiClass {
  int status() { return ON_WIFI ? WL_CONNECTED : 6; }
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
open(S + "/board/FastLED.h", "w").write(r'''
#pragma once
#include "Arduino.h"
struct CRGB { uint8_t r = 0, g = 0, b = 0; CRGB() {} CRGB(uint8_t x, uint8_t y, uint8_t z) : r(x), g(y), b(z) {} };
enum { GRB = 1 };
struct WS2812B {};
extern CRGB *STRIP; extern int STRIP_N, STRIP_AT;
struct CFastLED {
  template <typename CHIP, int PIN, int ORDER> void addLeds(CRGB *leds, int n) { STRIP = leds; STRIP_N = n; STRIP_AT = PIN; }
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
# "wifi 0|1"
open(S + "/main.cpp", "w").write(r'''
#include "Arduino.h"
double NOW = 0; bool ON_WIFI = false; WiFiClass WiFi; std::deque<Packet> INBOX;
#ifdef WITH_STRIP
#include "FastLED.h"
CRGB *STRIP = nullptr; int STRIP_N = 0, STRIP_AT = 0; CFastLED FastLED;
#endif
#include "sketch.cpp"
int main() {
  setup();
  char line[8192];
  while (fgets(line, sizeof line, stdin)) {
    double t; int a, b, c, d, on; char hex[8000];
    if (sscanf(line, "t %lf", &t) == 1) { while (NOW < t) loop(); }
    else if (sscanf(line, "wifi %d", &on) == 1) ON_WIFI = on;
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


def build(name, strip=0, core="3,3,12"):
    """The sketch, built for the stand-in board (a strip of that many LEDs, if any; core: the version of the board's
    software): the program, or None. (A warning's an error: nothing the board's software says not to use.)"""
    src = open(SKETCH).read()
    if strip:
        assert "#define LED_COUNT 1 " in src
        src = src.replace("#define LED_COUNT 1 ", f"#define LED_COUNT {strip} ")
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


def run(prog, script):
    """Its loop, run through what the test says: what its LED was sent [(when, pin, r, g, b)] (a strip: [(when, pin,
    [its LEDs])]), what it sent [(when, to, port, bytes)], and when it began listening [(when, port)]. (ASKED: when
    it asked for the WiFi.)"""
    r = subprocess.run([prog], input="\n".join(script) + "\n", capture_output=True, text=True, timeout=60)
    leds, sent, begun, strip = [], [], [], []
    ASKED[:] = [float(line.split()[1]) for line in r.stdout.splitlines() if line.startswith("W ")]
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


ASKED = []


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
    hellos = [s for s in sent if s[2] == G.LAMP_PORT]
    gaps = [round(b[0] - a[0], 2) for a, b in zip(hellos, hellos[1:])]
    said = G.read_lamp(hellos[0][3]) if hellos else None
    check(f"...and says it's there every couple of seconds, to everyone on its network ({len(hellos)}, {gaps}, "
          f"{hellos[0][1] if hellos else None}): {said}", len(hellos) == 3 and all(1.95 <= x <= 2.1 for x in gaps)
          and hellos[0][1] == "10.0.0.255" and said == {"name": "ESP32 A1B2C3", "count": 1})
    joined = at(leds, 1.1)
    check(f"...its LED green for a moment, so you can tell ({joined}), then dark, with nothing playing "
          f"({at(leds, 6.9)})", joined is not None and joined[1] >= 8 and joined[0] == joined[2] == 0
          and at(leds, 6.9) == (0, 0, 0))
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
    leds, _, _, _ = run(prog, ["wifi 1", "t 1.0"] + [packet(PI, j) for j in junk] + ["t 2.0"])
    check(f"what isn't a Pietato's packet (or isn't right): nothing ({at(leds, 1.9)})", at(leds, 1.9) == (0, 0, 0))
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
        check(f"...all eight of its LEDs, music's colour ({last[2][:2]}, for {base}), on its pin ({last[1]})",
              len(last[2]) == 8 and len(set(last[2])) == 1 and near(last[2][0], base) and last[1] == 5)

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
      f"{page.says}; {led_app()!r}, {m.web_glow_now()['status']!r})",
      page.facts == [("ESP32 boards", "None"), ("Pulse to music", "On")]
      and page.says == ("No LEDs here", "They go on a Pi behind the TV") and led_app() is None
      and "ESP32" not in m.web_glow_now()["status"])
m.press_glow(page, "a", False)
check("...A there: nothing to turn on, and said", m.setting("glow_beat") == "On" and m.setting("glow_on") != "On")
check("media mode closing: not listened for any more", m.glow_lamps is None and m.glow_targets() == []
      and not m.glow_beats_wanted())
s.close()
print("ALL OK" if all(ok_all) else f"FAILED {ok_all.count(False)}")
