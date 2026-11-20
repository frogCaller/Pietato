// ============================================================
//  ESP32-S3-Matrix  8×8 LED Matrix Controller
//  Fluid, fire, music from your Pietatos, text, paint and
//  animations, all run from a page built into the sketch.
//
//  Web page:  join Wi-Fi "Pietato Matrix" (password 12345678),
//             then open http://10.20.30.40:8000
//
//  Music:     on the page, Connection > Join Wi-Fi, pick your
//             Wi-Fi. Your Pietatos find the board there by
//             themselves and it pulses to whatever they play
//             (Library > LED backlight on a Pietato lists it).
//
//  BOOT button:  tap        = next mode
//                double-tap = next colour preset (fluid / fire)
//                hold ~1 s  = jump to fluid
//
//  Arduino IDE: board "ESP32S3 Dev Module", USB CDC On Boot: Enabled
//  Library: FastLED.
// ============================================================

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <WebServer.h>
#include <ESPmDNS.h>
#include <Wire.h>
#include <Preferences.h>
#include <FastLED.h>
#include <math.h>
#include "esp_timer.h"

// ── Hardware ─────────────────────────────────────────────────
#define LED_PIN   14
#define NUM_LEDS  64
#define GRID_W     8
#define GRID_H     8
static const int SDA_PIN = 11;    // QMI8658 accelerometer
static const int SCL_PIN = 12;
static const int BTN_PIN = 0;     // BOOT button

// ── Wi-Fi ────────────────────────────────────────────────────
// The board always runs its own hotspot for the page. It can also join
// your Wi-Fi (set from the page, or here) so your Pietatos can find it.
const char* AP_SSID   = "Pietato Matrix";
const char* AP_PASS   = "12345678";
const char* WIFI_SSID = "";        // your Wi-Fi, if you'd rather set it here than on the page
const char* WIFI_PASS = "";
static const char *HOSTNAME = "matrix";              // http://matrix.local:8000 on your Wi-Fi
static const int WEB_PORT = 8000;
static const IPAddress BOARD_IP(10, 20, 30, 40);     // the hotspot's address
static const IPAddress SUBNET_MASK(255, 255, 255, 0);

// ── Modes (numbers match the old /pattern?n= values) ─────────
enum {
  P_PAINT, P_RAINBOW, P_HYPNO, P_RINGS, P_FIRE, P_SPARKLE,
  P_PLASMA, P_RAIN, P_HEART, P_BOUNCE, P_TEXT, P_FLUID, P_MUSIC, NUM_PATTERNS
};
static const uint16_t INTERVALS[NUM_PATTERNS] = {0, 35, 18, 30, 45, 40, 55, 45, 30, 22, 0, 0, 0};

// ── Settings (saved in flash) ────────────────────────────────
// New fields go at the end, so settings saved by an older version still load.
struct Settings {
  uint8_t  version;
  uint8_t  pattern;
  uint8_t  brightness;   // 1-100, top LED level (same scale as the old code)
  uint8_t  rotation;     // quarter turns; 2 = the old XY() layout
  uint8_t  tiltFlip;     // 1 = mirror the tilt
  uint8_t  fill;         // fluid amount, % of the matrix
  uint8_t  thick;        // fluid thickness 0-100
  uint8_t  fireHeight;   // 0-100
  uint8_t  textSpeed;    // 1-100
  uint32_t fluidColor, foamColor, fireColor, fireHot, textColor, paintColor;
  char     text[64];
  uint8_t  grid[GRID_H][GRID_W][3];   // paint canvas
  // v4
  uint8_t  speed;        // animation speed 1-100 (50 = as before)
  uint8_t  pulse;        // 1 = react to Pietato's beats
  uint8_t  musicOwnOn;   // 1 = Music mode in its own colour, not Pietato's
  uint32_t musicOwn;
};
static const uint8_t SETTINGS_VERSION = 4;
Settings S;

static void defaultSettings() {
  memset(&S, 0, sizeof(S));
  S.version = SETTINGS_VERSION;
  S.pattern = 11;   // fluid
  S.brightness = 20;
  S.rotation = 2;
  S.fill = 20;
  S.thick = 20;
  S.fireHeight = 56;
  S.textSpeed = 70;
  S.fluidColor = 0x0038FF;  S.foamColor = 0x8CF2FF;
  S.fireColor  = 0xFF1000;  S.fireHot   = 0xFF6000;   // = the old fire's red/orange
  S.textColor  = 0x0030FF;
  S.paintColor = 0xFF0040;
  strcpy(S.text, "HELLO");
  S.speed = 50;
  S.pulse = 1;
  S.musicOwnOn = 0;
  S.musicOwn = 0x5A7BFF;
}

struct Preset { uint32_t a, b; };
static const Preset FLUID_PRESETS[] = {
  {0x0038FF, 0x8CF2FF}, {0xFF1000, 0xFFC010}, {0x18FF05, 0xD8FF60}, {0x8C00FF, 0xFF70E6}, {0xFF8C00, 0xFFFF99},
};
static const Preset FIRE_PRESETS[] = {
  {0xFF1000, 0xFF6000}, {0x0020FF, 0x40C0FF}, {0x10FF00, 0xC0FF40}, {0x8000FF, 0xFF40FF}, {0xFF0030, 0xFF9060},
};
static const int NUM_PRESETS = 5;
static int presetIndex = 0;

// ── Globals ──────────────────────────────────────────────────
CRGB leds[NUM_LEDS];
WebServer server(WEB_PORT);
Preferences prefs;
WiFiUDP udp;

static float   fb[GRID_H][GRID_W][3];       // frame being drawn, 0..1, screen layout
static float   smoothFb[GRID_H][GRID_W][3];
static float   ditherErr[GRID_H][GRID_W][3];
static uint8_t shown[GRID_H][GRID_W][3];    // for the web preview

static bool     savePending = false;
static uint32_t saveAt = 0;
static void markChanged() { savePending = true; saveAt = millis() + 3000; }

static double nowSec() { return esp_timer_get_time() / 1e6; }
static float frand(float lo, float hi) { return lo + (hi - lo) * (random(0, 10000) / 10000.0f); }

static void hexToRGB(uint32_t c, float out[3]) {
  out[0] = ((c >> 16) & 255) / 255.0f;
  out[1] = ((c >> 8) & 255) / 255.0f;
  out[2] = (c & 255) / 255.0f;
}

// ── Drawing helpers (screen coordinates, 0,0 = top-left) ─────
static void clearFb() { memset(fb, 0, sizeof(fb)); }

static void setPix(int x, int y, const CRGB &c) {
  if (x < 0 || x >= GRID_W || y < 0 || y >= GRID_H) return;
  fb[y][x][0] = c.r / 255.0f;
  fb[y][x][1] = c.g / 255.0f;
  fb[y][x][2] = c.b / 255.0f;
}

static void setPixF(int x, int y, const float c[3], float a = 1.0f) {
  if (x < 0 || x >= GRID_W || y < 0 || y >= GRID_H) return;
  for (int i = 0; i < 3; i++) fb[y][x][i] = c[i] * a;
}

static void addPixF(int x, int y, const float c[3], float a) {
  if (x < 0 || x >= GRID_W || y < 0 || y >= GRID_H || a <= 0) return;
  for (int i = 0; i < 3; i++) { fb[y][x][i] += c[i] * a; if (fb[y][x][i] > 1) fb[y][x][i] = 1; }
}

static void fadeAll(uint8_t amount) {
  float k = 1.0f - amount / 256.0f;
  for (int y = 0; y < GRID_H; y++) for (int x = 0; x < GRID_W; x++) for (int i = 0; i < 3; i++) fb[y][x][i] *= k;
}

static CRGB hsv(uint8_t h, uint8_t s, uint8_t v) {
  CRGB c;
  hsv2rgb_rainbow(CHSV(h, s, v), c);
  return c;
}

// ── Rotation ─────────────────────────────────────────────────
// Everything is drawn in screen coordinates, then turned S.rotation
// quarter-turns on the way to the LEDs (LED 0 = top-left with the USB
// edge at the top, rows run left to right). rotation 2 = the old XY().
static void toRaw(int x, int y, int &rx, int &ry) {
  for (int r = 0; r < (S.rotation & 3); r++) { int t = x; x = GRID_W - 1 - y; y = t; }
  rx = x; ry = y;
}

// ── QMI8658 accelerometer (minimal driver) ───────────────────
static uint8_t qmiAddr = 0;

static bool qmiWrite(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(qmiAddr);
  Wire.write(reg);
  Wire.write(val);
  return Wire.endTransmission() == 0;
}

static bool qmiRead(uint8_t reg, uint8_t *buf, uint8_t n) {
  Wire.beginTransmission(qmiAddr);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom((int)qmiAddr, (int)n) != n) return false;
  for (uint8_t i = 0; i < n; i++) buf[i] = Wire.read();
  return true;
}

static bool qmiBegin() {
  const uint8_t addrs[] = { 0x6B, 0x6A };
  for (uint8_t a : addrs) {
    qmiAddr = a;
    uint8_t id = 0;
    if (qmiRead(0x00, &id, 1) && id == 0x05) {
      qmiWrite(0x60, 0xB0);  // soft reset
      delay(30);
      qmiWrite(0x02, 0x40);  // auto-increment
      qmiWrite(0x03, 0x15);  // accel +-4 g, ~250 Hz
      qmiWrite(0x08, 0x01);  // accel on
      delay(10);
      return true;
    }
  }
  qmiAddr = 0;
  return false;
}

static bool qmiReadAccel(float &ax, float &ay) {
  uint8_t b[4];
  if (!qmiRead(0x35, b, 4)) return false;
  ax = (int16_t)(b[0] | (b[1] << 8)) / 8192.0f;
  ay = (int16_t)(b[2] | (b[3] << 8)) / 8192.0f;
  return true;
}

// Gravity on the screen, px/s^2
static const float GRAVITY = 80.0f;
static float gravX = 0, gravY = GRAVITY;
static bool  imuOk = false;
static float fax = 0, fay = 0;

static void updateGravity() {
  float ax, ay;
  if (imuOk && qmiReadAccel(ax, ay)) {
    fax += (ax - fax) * 0.5f;
    fay += (ay - fay) * 0.5f;
  } else if (!imuOk) {
    float t = millis() * 0.0006f;           // no sensor: slowly turning demo gravity
    fax = sinf(t) * 0.8f;
    fay = cosf(t) * 0.8f;
  }
  // gravity in LED layout (sensor +X points at the USB edge)
  float gx = -fay * GRAVITY, gy = fax * GRAVITY;
  // into screen layout (undo the display rotation)
  for (int r = 0; r < (S.rotation & 3); r++) { float t = gx; gx = gy; gy = -t; }
  if (S.tiltFlip) gx = -gx;
  float gmax = 3.0f * GRAVITY;
  gravX = fmaxf(-gmax, fminf(gmax, gx));
  gravY = fmaxf(-gmax, fminf(gmax, gy));
}

// ============================================================
//  PATTERNS
// ============================================================

// ── 0: Paint ─────────────────────────────────────────────────
static void drawPaint() {
  for (int y = 0; y < GRID_H; y++)
    for (int x = 0; x < GRID_W; x++)
      setPix(x, y, CRGB(S.grid[y][x][0], S.grid[y][x][1], S.grid[y][x][2]));
}

// ── 1: Rainbow ───────────────────────────────────────────────
static uint8_t hueOff = 0;
static void tickRainbow() {
  hueOff += 2;
  for (int y = 0; y < GRID_H; y++)
    for (int x = 0; x < GRID_W; x++)
      setPix(x, y, hsv(hueOff + x * 8 + y * 4, 255, 255));
}

// ── 2: Hypno ─────────────────────────────────────────────────
static void tickHypno() {
  static uint8_t t = 0;
  t++;
  for (int y = 0; y < GRID_H; y++) {
    for (int x = 0; x < GRID_W; x++) {
      float dx = x - 3.5f, dy = y - 3.5f;
      float angle = atan2f(dy, dx) * 40;
      uint8_t v = sin8((uint8_t)(int)(angle + t * 6 + sqrtf(dx * dx + dy * dy) * 35));
      setPix(x, y, hsv(t * 3 + v, 255, v > 100 ? 255 : 80));
    }
  }
}

// ── 3: Pulse rings ───────────────────────────────────────────
static void tickPulseRings() {
  static uint8_t t = 0;
  t++;
  for (int y = 0; y < GRID_H; y++) {
    for (int x = 0; x < GRID_W; x++) {
      float dx = x - 3.5f, dy = y - 3.5f;
      uint8_t v = sin8((uint8_t)(int)(sqrtf(dx * dx + dy * dy) * 45 - t * 12));
      setPix(x, y, hsv(180 + t * 2, 255, v > 80 ? v : 30));
    }
  }
}

// ── 4: Fire (the old algorithm, colours from the settings) ───
static uint8_t heat[GRID_H][GRID_W];   // row 0 = bottom

static void fireColorFor(uint8_t h, float out[3]) {
  float base[3], hot[3];
  hexToRGB(S.fireColor, base);
  hexToRGB(S.fireHot, hot);
  if (h < 80) {                          // dark embers
    for (int i = 0; i < 3; i++) out[i] = base[i] * h / 255.0f;
    return;
  }
  float t = (h < 160) ? (h - 80) / 80.0f * 0.30f : 0.55f + (h - 160) / 95.0f * 0.45f;
  if (t > 1) t = 1;
  for (int i = 0; i < 3; i++) out[i] = base[i] + (hot[i] - base[i]) * t;
}

static void tickFire() {
  const uint8_t COOLING = 80 - S.fireHeight / 2;   // 56 -> 52, the old value
  const uint8_t SPARKING = 130;
  for (int y = 0; y < GRID_H; y++) for (int x = 0; x < GRID_W; x++) {
    uint8_t c = random8(COOLING / 2, COOLING);
    heat[y][x] = (heat[y][x] > c) ? heat[y][x] - c : 0;
  }
  for (int y = GRID_H - 1; y >= 1; y--) for (int x = 0; x < GRID_W; x++) {
    uint16_t s = heat[y - 1][x] * 2 + heat[y - 1][(x + GRID_W - 1) % GRID_W] + heat[y - 1][(x + 1) % GRID_W];
    heat[y][x] = s / 4;
  }
  for (int x = 0; x < GRID_W; x++) if (random8() < SPARKING) heat[0][x] = qadd8(heat[0][x], random8(160, 255));

  float c[3];
  for (int y = 0; y < GRID_H; y++) for (int x = 0; x < GRID_W; x++) {
    fireColorFor(heat[y][x], c);
    setPixF(x, GRID_H - 1 - y, c);
  }
}

// ── 5: Sparkle ───────────────────────────────────────────────
static void tickSparkle() {
  fadeAll(40);
  for (int i = 0; i < 4; i++)
    setPix(random8(GRID_W), random8(GRID_H), hsv(random8(), 200 + random8(55), 180 + random8(75)));
}

// ── 6: Plasma ────────────────────────────────────────────────
static void tickPlasma() {
  static uint8_t t = 0;
  t++;
  for (int y = 0; y < GRID_H; y++)
    for (int x = 0; x < GRID_W; x++) {
      int val = sin8(t * 2 + x * 20) + sin8(t * 3 + y * 25);
      setPix(x, y, hsv(val + t * 2, 255, 255));
    }
}

// ── 7: Matrix rain (now real falling drops with trails) ──────
static float dropY[GRID_W], dropV[GRID_W];
static void resetRain() {
  for (int x = 0; x < GRID_W; x++) { dropY[x] = -frand(0, 8); dropV[x] = frand(0.25f, 0.6f); }
}
static void tickRain() {
  fadeAll(70);
  for (int x = 0; x < GRID_W; x++) {
    dropY[x] += dropV[x];
    if (dropY[x] > GRID_H + 1) { dropY[x] = -frand(0, 6); dropV[x] = frand(0.25f, 0.6f); }
    int y = (int)floorf(dropY[x]);
    if (y >= 0 && y < GRID_H) setPix(x, y, hsv(96, 200, 255));
  }
}

// ── 8: Heart ─────────────────────────────────────────────────
static void tickHeart() {
  static uint8_t beat = 0; static int8_t dir = 1;
  beat += dir * 10; if (beat >= 240) dir = -1; if (beat <= 50) dir = 1;
  static const uint8_t h[8][8] = {
    {0,0,0,0,0,0,0,0},{0,1,1,0,0,1,1,0},{1,1,1,1,1,1,1,1},{1,1,1,1,1,1,1,1},
    {0,1,1,1,1,1,1,0},{0,0,1,1,1,1,0,0},{0,0,0,1,1,0,0,0},{0,0,0,0,0,0,0,0}};
  clearFb();
  CRGB hc = hsv(245, 220, beat);
  for (int y = 0; y < 8; y++) for (int x = 0; x < 8; x++) if (h[y][x]) setPix(x, y, hc);
}

// ── 9: Bounce (smooth: the ball moves between pixels) ────────
static float ballX = 2, ballY = 2, ballVX = 0.23f, ballVY = 0.18f;
static void tickBounce() {
  fadeAll(80);
  ballX += ballVX; ballY += ballVY;
  if (ballX <= 0) { ballX = 0; ballVX = -ballVX; } if (ballX >= GRID_W - 1) { ballX = GRID_W - 1; ballVX = -ballVX; }
  if (ballY <= 0) { ballY = 0; ballVY = -ballVY; } if (ballY >= GRID_H - 1) { ballY = GRID_H - 1; ballVY = -ballVY; }
  static const float col[3] = {0, 80 / 255.0f, 1};
  int ix = (int)floorf(ballX), iy = (int)floorf(ballY);
  float tx = ballX - ix, ty = ballY - iy;
  addPixF(ix,     iy,     col, (1 - tx) * (1 - ty));
  addPixF(ix + 1, iy,     col, tx * (1 - ty));
  addPixF(ix,     iy + 1, col, (1 - tx) * ty);
  addPixF(ix + 1, iy + 1, col, tx * ty);
}

// ── 10: Scrolling text ───────────────────────────────────────
const uint8_t font[95][5] PROGMEM = {
  {0x00,0x00,0x00,0x00,0x00},{0x00,0x00,0x5F,0x00,0x00},{0x00,0x07,0x00,0x07,0x00},{0x14,0x7F,0x14,0x7F,0x14}, //  !"#
  {0x24,0x2A,0x7F,0x2A,0x12},{0x23,0x13,0x08,0x64,0x62},{0x36,0x49,0x55,0x22,0x50},{0x00,0x05,0x03,0x00,0x00}, // $%&'
  {0x00,0x1C,0x22,0x41,0x00},{0x00,0x41,0x22,0x1C,0x00},{0x14,0x08,0x3E,0x08,0x14},{0x08,0x08,0x3E,0x08,0x08}, // ()*+
  {0x00,0x50,0x30,0x00,0x00},{0x08,0x08,0x08,0x08,0x08},{0x00,0x60,0x60,0x00,0x00},{0x20,0x10,0x08,0x04,0x02}, // ,-./
  {0x3E,0x51,0x49,0x45,0x3E},{0x00,0x42,0x7F,0x40,0x00},{0x42,0x61,0x51,0x49,0x46},{0x21,0x41,0x45,0x4B,0x31}, // 0123
  {0x18,0x14,0x12,0x7F,0x10},{0x27,0x45,0x45,0x45,0x39},{0x3C,0x4A,0x49,0x49,0x30},{0x01,0x71,0x09,0x05,0x03}, // 4567
  {0x36,0x49,0x49,0x49,0x36},{0x06,0x49,0x49,0x29,0x1E},{0x00,0x36,0x36,0x00,0x00},{0x00,0x56,0x36,0x00,0x00}, // 89:;
  {0x08,0x14,0x22,0x41,0x00},{0x14,0x14,0x14,0x14,0x14},{0x00,0x41,0x22,0x14,0x08},{0x02,0x01,0x51,0x09,0x06}, // <=>?
  {0x32,0x49,0x79,0x41,0x3E},{0x7E,0x11,0x11,0x11,0x7E},{0x7F,0x49,0x49,0x49,0x36},{0x3E,0x41,0x41,0x41,0x22}, // @ABC
  {0x7F,0x41,0x41,0x22,0x1C},{0x7F,0x49,0x49,0x49,0x41},{0x7F,0x09,0x09,0x09,0x01},{0x3E,0x41,0x49,0x49,0x7A}, // DEFG
  {0x7F,0x08,0x08,0x08,0x7F},{0x00,0x41,0x7F,0x41,0x00},{0x20,0x40,0x41,0x3F,0x01},{0x7F,0x08,0x14,0x22,0x41}, // HIJK
  {0x7F,0x40,0x40,0x40,0x40},{0x7F,0x02,0x0C,0x02,0x7F},{0x7F,0x04,0x08,0x10,0x7F},{0x3E,0x41,0x41,0x41,0x3E}, // LMNO
  {0x7F,0x09,0x09,0x09,0x06},{0x3E,0x41,0x51,0x21,0x5E},{0x7F,0x09,0x19,0x29,0x46},{0x46,0x49,0x49,0x49,0x31}, // PQRS
  {0x01,0x01,0x7F,0x01,0x01},{0x3F,0x40,0x40,0x40,0x3F},{0x1F,0x20,0x40,0x20,0x1F},{0x3F,0x40,0x38,0x40,0x3F}, // TUVW
  {0x63,0x14,0x08,0x14,0x63},{0x07,0x08,0x70,0x08,0x07},{0x61,0x51,0x49,0x45,0x43},{0x00,0x7F,0x41,0x41,0x00}, // XYZ[
  {0x02,0x04,0x08,0x10,0x20},{0x00,0x41,0x41,0x7F,0x00},{0x04,0x02,0x01,0x02,0x04},{0x40,0x40,0x40,0x40,0x40}, // \]^_
  {0x00,0x01,0x02,0x04,0x00},{0x20,0x54,0x54,0x54,0x78},{0x7F,0x48,0x44,0x44,0x38},{0x38,0x44,0x44,0x44,0x20}, // `abc
  {0x38,0x44,0x44,0x48,0x7F},{0x38,0x54,0x54,0x54,0x18},{0x08,0x7E,0x09,0x01,0x02},{0x0C,0x52,0x52,0x52,0x3E}, // defg
  {0x7F,0x08,0x04,0x04,0x78},{0x00,0x44,0x7D,0x40,0x00},{0x20,0x40,0x44,0x3D,0x00},{0x7F,0x10,0x28,0x44,0x00}, // hijk
  {0x00,0x41,0x7F,0x40,0x00},{0x7C,0x04,0x18,0x04,0x78},{0x7C,0x08,0x04,0x04,0x78},{0x38,0x44,0x44,0x44,0x38}, // lmno
  {0x7C,0x14,0x14,0x14,0x08},{0x08,0x14,0x14,0x18,0x7C},{0x7C,0x08,0x04,0x04,0x08},{0x48,0x54,0x54,0x54,0x20}, // pqrs
  {0x04,0x3F,0x44,0x40,0x00},{0x3C,0x40,0x40,0x20,0x7C},{0x1C,0x20,0x40,0x20,0x1C},{0x3C,0x40,0x30,0x40,0x3C}, // tuvw
  {0x44,0x28,0x10,0x28,0x44},{0x0C,0x50,0x50,0x50,0x3C},{0x44,0x64,0x54,0x4C,0x44},{0x00,0x08,0x36,0x41,0x00}, // xyz{
  {0x00,0x00,0x7F,0x00,0x00},{0x00,0x41,0x36,0x08,0x00},{0x02,0x01,0x02,0x04,0x02},                            // |}~
};

static int textOffset = GRID_W;
static uint32_t textLast = 0;

static void tickScrollText() {
  uint32_t stepMs = 260 - (uint32_t)S.textSpeed * 23 / 10;   // speed 70 -> ~100 ms, like before
  if (millis() - textLast < stepMs) return;
  textLast = millis();

  clearFb();
  float col[3];
  hexToRGB(S.textColor, col);
  int len = strlen(S.text);
  for (int i = 0; i < len; i++) {
    char ch = S.text[i];
    const uint8_t *letter = font[(ch >= 32 && ch <= 126) ? ch - 32 : 0];
    for (int c = 0; c < 5; c++) {
      int x = textOffset + i * 6 + c;
      if (x < 0 || x >= GRID_W) continue;
      uint8_t bits = pgm_read_byte(&letter[c]);
      for (int row = 0; row < 7; row++)
        if (bits & (1 << row)) setPixF(x, row + 1, col);   // bit 0 = top of the letter
    }
  }
  textOffset--;
  if (textOffset < -len * 6) textOffset = GRID_W;
}

// ── 11: Fluid ────────────────────────────────────────────────
// Many particles smaller than a pixel, with sub-pixel positions.
// Overlaps are pushed apart, a soft pressure levels the surface and
// a little viscosity makes them move together like a liquid.
static const int   MAX_PARTICLES = 200;
static const float PD   = 0.6f;    // particle diameter (pixels)
static const float PR   = 0.85f;   // pressure radius
static const float VR   = 1.0f;    // viscosity radius
static const float NR   = 1.05f;   // neighbour search radius
static const float PER_PIXEL = 2.8f;   // particles per pixel when settled
static const float FULL_DENS = 2.0f;   // density that lights a pixel fully
static const float PRESSURE  = 300.0f;
static const float STEP = 1.0f / 240.0f;

static float px[MAX_PARTICLES], py[MAX_PARTICLES];
static float vx[MAX_PARTICLES], vy[MAX_PARTICLES];
static float ox_[MAX_PARTICLES], oy_[MAX_PARTICLES];
static int   numParticles = 0;

static const int MAX_PAIRS = 2400;
static uint8_t pairA[MAX_PAIRS], pairB[MAX_PAIRS];
static int numPairs = 0;
static int16_t cellHead[GRID_W * GRID_H], cellNext[MAX_PARTICLES];

static int targetParticles() {
  int n = (int)(S.fill / 100.0f * GRID_W * GRID_H * PER_PIXEL + 0.5f);
  return n < 4 ? 4 : (n > MAX_PARTICLES ? MAX_PARTICLES : n);
}

static void spawnParticle(int i, bool settled) {
  if (settled) {   // stack against the low side so a reset starts calm
    float gx = gravX, gy = gravY, g = sqrtf(gx * gx + gy * gy);
    if (g < 1) { gx = 0; gy = 1; g = 1; }
    gx /= g; gy /= g;
    int row = i / 13, col = i % 13;
    float along = 3.7f - row * 0.52f, side = (col - 6) * 0.55f + (row & 1) * 0.27f;
    px[i] = 4.0f + gx * along - gy * side;
    py[i] = 4.0f + gy * along + gx * side;
  } else {
    px[i] = frand(0.5f, 7.5f);
    py[i] = frand(0.5f, 7.5f);
  }
  px[i] = fmaxf(0.3f, fminf(7.7f, px[i] + frand(-0.05f, 0.05f)));
  py[i] = fmaxf(0.3f, fminf(7.7f, py[i] + frand(-0.05f, 0.05f)));
  vx[i] = vy[i] = 0;
}

static void resetFluid() {
  numParticles = targetParticles();
  for (int i = 0; i < numParticles; i++) spawnParticle(i, true);
}

static void syncParticleCount() {
  int n = targetParticles();
  for (int i = numParticles; i < n; i++) spawnParticle(i, false);
  numParticles = n;
}

static void splash() {
  for (int i = 0; i < numParticles; i++) {
    vx[i] += frand(-25, 25) - gravX * 0.25f;
    vy[i] += frand(-25, 25) - gravY * 0.25f;
  }
}

static void buildPairs() {
  for (int k = 0; k < GRID_W * GRID_H; k++) cellHead[k] = -1;
  for (int i = 0; i < numParticles; i++) {
    int cx = (int)px[i], cy = (int)py[i];
    cx = cx < 0 ? 0 : (cx > GRID_W - 1 ? GRID_W - 1 : cx);
    cy = cy < 0 ? 0 : (cy > GRID_H - 1 ? GRID_H - 1 : cy);
    int c = cy * GRID_W + cx;
    cellNext[i] = cellHead[c];
    cellHead[c] = i;
  }
  numPairs = 0;
  const float nr2 = NR * NR;
  for (int i = 0; i < numParticles; i++) {
    int cx = (int)px[i], cy = (int)py[i];
    for (int y = cy - 1; y <= cy + 1; y++) {
      if (y < 0 || y >= GRID_H) continue;
      for (int x = cx - 1; x <= cx + 1; x++) {
        if (x < 0 || x >= GRID_W) continue;
        for (int j = cellHead[y * GRID_W + x]; j >= 0; j = cellNext[j]) {
          if (j <= i) continue;
          float dx = px[j] - px[i], dy = py[j] - py[i];
          if (dx * dx + dy * dy < nr2 && numPairs < MAX_PAIRS) {
            pairA[numPairs] = i;
            pairB[numPairs] = j;
            numPairs++;
          }
        }
      }
    }
  }
}

static void fluidStep(float gx, float gy, float dt) {
  const int n = numParticles;
  const float LO = PD * 0.5f, HI = 8.0f - PD * 0.5f;
  const float viscosity = 0.02f + S.thick / 100.0f * 0.25f;
  const float damping = 0.999f - S.thick / 100.0f * 0.004f;
  const float MAXV = 60.0f;

  buildPairs();

  // 1. soft pressure (scales with gravity, so lying flat it stays put)
  float gs = sqrtf(gx * gx + gy * gy) / GRAVITY;
  if (gs > 1.0f) gs = 1.0f;
  float pressure = PRESSURE * gs;
  if (pressure > 1.0f) {
    for (int k = 0; k < numPairs; k++) {
      int i = pairA[k], j = pairB[k];
      float dx = px[j] - px[i], dy = py[j] - py[i];
      float d2 = dx * dx + dy * dy;
      if (d2 >= PR * PR || d2 < 1e-8f) continue;
      float d = sqrtf(d2);
      float f = pressure * (1.0f - d / PR) * dt / d;
      vx[i] -= dx * f;  vy[i] -= dy * f;
      vx[j] += dx * f;  vy[j] += dy * f;
    }
  }

  // 2. gravity, predict
  for (int i = 0; i < n; i++) {
    vx[i] = (vx[i] + gx * dt) * damping;
    vy[i] = (vy[i] + gy * dt) * damping;
    ox_[i] = px[i];  oy_[i] = py[i];
    px[i] += vx[i] * dt;
    py[i] += vy[i] * dt;
  }

  // 3. push overlaps apart, keep inside the walls
  const float D2 = PD * PD;
  for (int iter = 0; iter < 4; iter++) {
    for (int k = 0; k < numPairs; k++) {
      int i = pairA[k], j = pairB[k];
      float dx = px[j] - px[i], dy = py[j] - py[i];
      float d2 = dx * dx + dy * dy;
      if (d2 >= D2) continue;
      if (d2 < 1e-8f) { dx = frand(-0.01f, 0.01f); dy = frand(-0.01f, 0.01f); d2 = dx * dx + dy * dy + 1e-8f; }
      float d = sqrtf(d2);
      float c = (PD - d) * 0.5f / d;
      px[i] -= dx * c;  py[i] -= dy * c;
      px[j] += dx * c;  py[j] += dy * c;
    }
    for (int i = 0; i < n; i++) {
      px[i] = fmaxf(LO, fminf(HI, px[i]));
      py[i] = fmaxf(LO, fminf(HI, py[i]));
    }
  }

  // 4. velocity from actual movement
  float inv = 1.0f / dt;
  for (int i = 0; i < n; i++) {
    vx[i] = (px[i] - ox_[i]) * inv;
    vy[i] = (py[i] - oy_[i]) * inv;
  }

  // 5. viscosity
  for (int k = 0; k < numPairs; k++) {
    int i = pairA[k], j = pairB[k];
    float dx = px[j] - px[i], dy = py[j] - py[i];
    float d2 = dx * dx + dy * dy;
    if (d2 >= VR * VR) continue;
    float w = (1.0f - sqrtf(d2) / VR) * viscosity;
    float dvx = (vx[j] - vx[i]) * w, dvy = (vy[j] - vy[i]) * w;
    vx[i] += dvx; vy[i] += dvy;
    vx[j] -= dvx; vy[j] -= dvy;
  }
  for (int i = 0; i < n; i++) {
    float s2 = vx[i] * vx[i] + vy[i] * vy[i];
    if (s2 > MAXV * MAXV) { float k = MAXV / sqrtf(s2); vx[i] *= k; vy[i] *= k; }
  }
}

static float dens[GRID_H][GRID_W], speedSum[GRID_H][GRID_W];

static void addLight(int x, int y, float w, float spd) {
  if (x < 0 || x >= GRID_W || y < 0 || y >= GRID_H || w <= 0) return;
  dens[y][x] += w;
  speedSum[y][x] += w * spd;
}

static void drawFluid() {
  memset(dens, 0, sizeof(dens));
  memset(speedSum, 0, sizeof(speedSum));
  for (int i = 0; i < numParticles; i++) {
    float fx = px[i] - 0.5f, fy = py[i] - 0.5f;
    int ix = (int)floorf(fx), iy = (int)floorf(fy);
    float tx = fx - ix, ty = fy - iy;
    float spd = sqrtf(vx[i] * vx[i] + vy[i] * vy[i]);
    addLight(ix,     iy,     (1 - tx) * (1 - ty), spd);
    addLight(ix + 1, iy,     tx       * (1 - ty), spd);
    addLight(ix,     iy + 1, (1 - tx) * ty,       spd);
    addLight(ix + 1, iy + 1, tx       * ty,       spd);
  }
  float deep[3], foam[3];
  hexToRGB(S.fluidColor, deep);
  hexToRGB(S.foamColor, foam);
  for (int y = 0; y < GRID_H; y++) {
    for (int x = 0; x < GRID_W; x++) {
      float a = dens[y][x] / FULL_DENS;
      if (a > 1.0f) a = 1.0f;
      float f = 0;
      if (dens[y][x] > 0.001f) { f = (speedSum[y][x] / dens[y][x]) / 25.0f; if (f > 1) f = 1; }
      a = a * a * (3.0f - 2.0f * a) * 0.8f + a * 0.2f;   // soft edge
      for (int c = 0; c < 3; c++) fb[y][x][c] = (deep[c] + (foam[c] - deep[c]) * f) * a;
    }
  }
}


// ============================================================
//  PIETATO MUSIC SYNC
//  The same UDP protocol as Pietato's esp32/pietato_led sketch:
//  the board says "I'm here" to port 5449 every couple of seconds,
//  and your Pietatos send it music colours, beats, a game's colours,
//  hits and achievements on port 5448.
// ============================================================
static const uint16_t GLOW_PORT = 5448;
static const uint16_t LAMP_PORT = 5449;
static const double HELLO_EVERY = 2.0, SAY_BACK = 0.25, SOURCE_HOLD = 2.5;
static const double MUSIC_KEEP = 1.5;        // seconds music counts as playing after its last colour or beat
static const double BEAT_TAU = 0.12;         // a beat dies away this fast (s)
static const double HIT_SECS = 0.5, GOLD_SECS = 1.4;
enum { EV_BEAT = 1, EV_HIT = 2, EV_CHEEVO = 3 };
struct BeatEvent { double at; uint8_t kind; float strength; bool fired; };

static bool      udpOn = false;
static double    helloAt = -1e9;
static bool      helloOwed = false;
static IPAddress pSource;
static bool      pFollowing = false;
static double    pOffset = 0, pHeardAt = -1e9;
static double    musicAt = -1e9, frameAt = -1e9, frameEvery = 0, beatAt = -1e9;
static float     musicRGB[3] = {90, 123, 255};
static uint8_t   gameRGB[GRID_H][GRID_W][3];
static BeatEvent events[16];
static int       eventCount = 0;
static float     beatPulse = 0, hitAmt = 0, goldAmt = 0;

static double beDouble(const uint8_t *p) {   // 8 bytes, biggest first, as Pietato sends a number
  uint64_t v = 0;
  for (int i = 0; i < 8; i++) v = (v << 8) | p[i];
  double d;
  memcpy(&d, &v, sizeof d);
  return d;
}

static void putBeDouble(uint8_t *p, double d) {
  uint64_t v;
  memcpy(&v, &d, sizeof v);
  for (int i = 7; i >= 0; i--) { p[i] = v & 0xFF; v >>= 8; }
}

static bool isNum(double v) { return v == v && v - v == 0; }

static bool musicPlaying(double now) { return now - musicAt < MUSIC_KEEP || now - beatAt < MUSIC_KEEP; }
static bool gamePlaying(double now) {
  double keep = frameEvery * 3 + 0.5;
  return now - frameAt < (keep > MUSIC_KEEP ? keep : MUSIC_KEEP);
}
static bool pietatoHeard(double now) { return now - pHeardAt < 10.0; }

static int boardName(char *name, size_t room) {   // "ESP32 Matrix A1B2C3"
  uint8_t mac[6];
  WiFi.macAddress(mac);
  return snprintf(name, room, "ESP32 Matrix %02X%02X%02X", mac[3], mac[4], mac[5]);
}

static uint8_t brightTo255() { return (uint8_t)((S.brightness * 255 + 50) / 100); }

// "I'm here": L (LEDs, name), then B (brightness 0-255), then S (keeps a colour and a brightness, 3, and is a
// sketch of its own, 8: a Pietato's page won't suggest the pietato_led sketch for it; has a colour; it)
static void sayHello(double now) {
  uint8_t msg[12 + 2 + 24];
  msg[0] = 'P'; msg[1] = 'G'; msg[2] = 1; msg[3] = 'L';
  putBeDouble(msg + 4, now);
  msg[12] = 0; msg[13] = NUM_LEDS;
  char name[24];
  int len = boardName(name, sizeof name);
  memcpy(msg + 14, name, len);
  IPAddress ip = WiFi.localIP(), mask = WiFi.subnetMask();
  IPAddress everyone(ip[0] | (uint8_t)~mask[0], ip[1] | (uint8_t)~mask[1], ip[2] | (uint8_t)~mask[2], ip[3] | (uint8_t)~mask[3]);
  udp.beginPacket(everyone, LAMP_PORT); udp.write(msg, 14 + len); udp.endPacket();
  msg[3] = 'B';
  msg[12] = brightTo255();
  udp.beginPacket(everyone, LAMP_PORT); udp.write(msg, 13); udp.endPacket();
  msg[3] = 'S';
  msg[12] = 3 | 8; msg[13] = S.musicOwnOn ? 1 : 0;
  msg[14] = (S.musicOwn >> 16) & 255; msg[15] = (S.musicOwn >> 8) & 255; msg[16] = S.musicOwn & 255;
  udp.beginPacket(everyone, LAMP_PORT); udp.write(msg, 17); udp.endPacket();
}

static void addEvent(double at, uint8_t kind, float strength, double now) {
  if (eventCount == 16) { memmove(events, events + 1, sizeof(BeatEvent) * 15); eventCount--; }
  events[eventCount].at = at > now - 0.05 ? at : now - 0.05;
  events[eventCount].kind = kind;
  events[eventCount].strength = strength;
  events[eventCount].fired = false;
  eventCount++;
}

static void takePacket(const uint8_t *data, int n, IPAddress from, double now) {
  if (n < 12 || data[0] != 'P' || data[1] != 'G' || data[2] != 1) return;
  const char kind = (char)data[3];
  const double sent = beDouble(data + 4);
  if (!isNum(sent)) return;
  const uint8_t *rest = data + 12;
  const int left = n - 12;

  if (kind == 'B') {                 // a Pietato's page set the brightness (0-255)
    if (left != 1) return;
    int b = (rest[0] * 100 + 127) / 255;
    S.brightness = b < 1 ? 1 : (b > 100 ? 100 : b);
    markChanged();
    helloOwed = true;
    return;
  }
  if (kind == 'C') {                 // ...or a colour of its own (1 + colour, or 0: none)
    if (left != 4 || rest[0] > 1) return;
    S.musicOwnOn = rest[0];
    if (rest[0]) S.musicOwn = ((uint32_t)rest[1] << 16) | ((uint32_t)rest[2] << 8) | rest[3];
    markChanged();
    helloOwed = true;
    return;
  }
  if (kind != 'M' && kind != 'F' && kind != 'E') return;

  const double off = now - sent;     // follow one Pietato at a time; its clock against ours
  if (!pFollowing || !(from == pSource)) {
    if (pFollowing && now - pHeardAt < SOURCE_HOLD) return;
    pSource = from; pFollowing = true; pOffset = off; eventCount = 0;
  } else {
    pOffset += 0.0001 * (now - pHeardAt);
    if (off < pOffset || off > pOffset + 5.0) pOffset = off;
  }
  pHeardAt = now;

  if (kind == 'M' && left == 3) {
    for (int k = 0; k < 3; k++) musicRGB[k] = rest[k];
    musicAt = now;
  } else if (kind == 'F' && left >= 2) {      // a game's picture edges, as a grid of colours
    int w = rest[0], h = rest[1];
    if (w < 1 || h < 1 || left < 2 + w * h * 3) return;
    for (int y = 0; y < GRID_H; y++)
      for (int x = 0; x < GRID_W; x++) {
        const uint8_t *c = rest + 2 + ((y * h / GRID_H) * w + (x * w / GRID_W)) * 3;
        memcpy(gameRGB[y][x], c, 3);
      }
    double gap = now - frameAt;
    frameEvery = gap >= 5.0 ? 0 : frameEvery > 0 ? (frameEvery + gap) / 2 : gap;
    frameAt = now;
  } else if (kind == 'E' && left > 9) {
    double at = beDouble(rest) + pOffset;     // when it's heard, by our clock
    float strength = rest[8] / 255.0f;
    const char *name = (const char *)rest + 9;
    int len = left - 9;
    uint8_t what = 0;
    if (len == 4 && !memcmp(name, "beat", 4)) what = EV_BEAT;
    else if (len == 3 && !memcmp(name, "hit", 3)) what = EV_HIT;
    else if (len == 6 && !memcmp(name, "cheevo", 6)) what = EV_CHEEVO;
    if (what && isNum(at)) addEvent(at, what, strength, now);
  }
}

static void networkTick(double now) {
  if (!udpOn) return;
  if (WiFi.status() == WL_CONNECTED &&
      (now - helloAt >= HELLO_EVERY || (helloOwed && now - helloAt >= SAY_BACK))) {
    helloAt = now; helloOwed = false;
    sayHello(now);
  }
  static uint8_t data[1500];
  for (int tries = 0; tries < 16; tries++) {
    int size = udp.parsePacket();
    if (size <= 0) break;
    int n = udp.read(data, sizeof data);
    if (n > 0) takePacket(data, n, udp.remoteIP(), nowSec());
  }
}

// ── What a beat does to each mode ────────────────────────────
// the liquid jumps with the beat (against gravity; lying flat, it sloshes)
static void spawnKick(float s) {
  float g = sqrtf(gravX * gravX + gravY * gravY);
  float kick = 6.0f + 14.0f * s;
  for (int i = 0; i < numParticles; i++) {
    float r = frand(0.6f, 1.2f);
    if (g > 10) {
      vx[i] += -gravX / g * kick * r + frand(-3, 3);
      vy[i] += -gravY / g * kick * r + frand(-3, 3);
    } else {
      vx[i] += frand(-kick, kick) * 0.6f;
      vy[i] += frand(-kick, kick) * 0.6f;
    }
  }
}

static void onBeat(float s) {
  beatAt = nowSec();
  if (!S.pulse && S.pattern != P_MUSIC) return;
  switch (S.pattern) {
    case P_FLUID: spawnKick(s); break;
    case P_FIRE:                                  // a flare from the bottom
      for (int x = 0; x < GRID_W; x++) {
        heat[0][x] = qadd8(heat[0][x], 90 + (uint8_t)(140 * s));
        heat[1][x] = qadd8(heat[1][x], 50 + (uint8_t)(100 * s));
      }
      break;
    case P_SPARKLE:
      for (int i = 0; i < 3 + (int)(5 * s); i++)
        setPix(random8(GRID_W), random8(GRID_H), hsv(random8(), 200, 255));
      break;
    case P_BOUNCE: {
      float k = 1.0f + 0.8f * s;
      ballVX *= k; ballVY *= k;
      float sp = sqrtf(ballVX * ballVX + ballVY * ballVY);
      if (sp > 0.6f) { ballVX *= 0.6f / sp; ballVY *= 0.6f / sp; }
      break;
    }
    default: break;
  }
}

static void beatTick(double now) {
  float p = 0, hit = 0, gold = 0;
  int kept = 0;
  for (int i = 0; i < eventCount; i++) {
    double age = now - events[i].at;
    if (age >= 3.0) continue;
    events[kept++] = events[i];
    BeatEvent &e = events[kept - 1];
    if (age < 0) continue;
    if (e.kind == EV_BEAT) {
      if (!e.fired) { e.fired = true; onBeat(e.strength); }
      p += e.strength * expf(-(float)(age / BEAT_TAU));
    } else if (e.kind == EV_HIT && age < HIT_SECS) {
      float r = e.strength * powf(1 - (float)(age / HIT_SECS), 2);
      if (r > hit) hit = r;
    } else if (e.kind == EV_CHEEVO && age < GOLD_SECS) {
      float g = 1 - (float)(age / GOLD_SECS);
      if (g > gold) gold = g;
    }
  }
  eventCount = kept;
  beatPulse = p;
  hitAmt = hit;
  goldAmt = gold;
}

// ── 8: Heart, with music ─────────────────────────────────────
// Each beat thumps it: the full heart, bright, then back to a smaller,
// dimmer one till the next. (No music: the old steady rhythm.)
static void drawHeartToBeat() {
  static const uint8_t big[8][8] = {
    {0,0,0,0,0,0,0,0},{0,1,1,0,0,1,1,0},{1,1,1,1,1,1,1,1},{1,1,1,1,1,1,1,1},
    {0,1,1,1,1,1,1,0},{0,0,1,1,1,1,0,0},{0,0,0,1,1,0,0,0},{0,0,0,0,0,0,0,0}};
  static const uint8_t small[8][8] = {
    {0,0,0,0,0,0,0,0},{0,0,0,0,0,0,0,0},{0,1,1,0,0,1,1,0},{0,1,1,1,1,1,1,0},
    {0,0,1,1,1,1,0,0},{0,0,0,1,1,0,0,0},{0,0,0,0,0,0,0,0},{0,0,0,0,0,0,0,0}};
  float p = fminf(1.0f, beatPulse * 1.3f);
  const uint8_t (*shape)[8] = p > 0.35f ? big : small;
  CRGB hc = hsv(245, 220, (uint8_t)(70 + 185 * p));
  clearFb();
  for (int y = 0; y < 8; y++) for (int x = 0; x < 8; x++) if (shape[y][x]) setPix(x, y, hc);
}

// ── 12: Music ────────────────────────────────────────────────
// A game playing on a Pietato: its picture's edge colours. Music: dark,
// with a ring in its colour going out from the middle on each beat.
static float musicShown[3] = {0, 0, 0};
static double musicDrawnAt = 0;

static void drawMusic(double now) {
  double dt = now - musicDrawnAt;
  dt = dt < 0 ? 0 : (dt > 0.2 ? 0.2 : dt);
  musicDrawnAt = now;

  if (gamePlaying(now)) {
    float k = 1.0f - expf(-(float)dt / 0.06f);
    for (int y = 0; y < GRID_H; y++) for (int x = 0; x < GRID_W; x++) for (int c = 0; c < 3; c++)
      fb[y][x][c] += (gameRGB[y][x][c] / 255.0f - fb[y][x][c]) * k;
    return;
  }

  bool playing = musicPlaying(now);
  float target[3];
  if (S.musicOwnOn) hexToRGB(S.musicOwn, target);
  else if (playing) for (int c = 0; c < 3; c++) target[c] = musicRGB[c] / 255.0f;
  else hexToRGB(S.musicOwn, target);
  float k = 1.0f - expf(-(float)dt / 0.18f);
  for (int c = 0; c < 3; c++) musicShown[c] += (target[c] - musicShown[c]) * k;

  for (int y = 0; y < GRID_H; y++) {
    for (int x = 0; x < GRID_W; x++) {
      float dx = x - 3.5f, dy = y - 3.5f, d = sqrtf(dx * dx + dy * dy);
      // dark between beats, so the rings stand out. Nothing playing: just the middle four, dimly
      float v = (!playing && d < 1.0f) ? 0.12f : 0.0f;
      float ring = 0;
      for (int i = 0; i < eventCount; i++) {
        if (events[i].kind != EV_BEAT) continue;
        float age = (float)(now - events[i].at);
        if (age < 0 || age > 1.2f) continue;
        float r = 0.7f + age * 9.0f;     // starts on the middle four, right on the beat
        float w = events[i].strength * expf(-age / 0.45f);
        float t = 1.0f - fabsf(d - r) / 1.1f;
        if (t > 0) ring += w * t;
      }
      ring += beatPulse * 0.6f * fmaxf(0.0f, 1.0f - d / 2.5f);
      if (ring > 1) ring = 1;
      v += ring;
      if (v > 1) v = 1;
      for (int c = 0; c < 3; c++) {
        float col = musicShown[c] + (1.0f - musicShown[c]) * 0.25f * ring;   // rings a little lighter
        fb[y][x][c] = col * v;
      }
    }
  }
}

// ── Mode switching ───────────────────────────────────────────
static uint32_t patternTimer = 0;

static void startPattern(int n) {
  S.pattern = n < 0 ? 0 : (n >= NUM_PATTERNS ? NUM_PATTERNS - 1 : n);
  patternTimer = 0;
  hueOff = 0;
  memset(heat, 0, sizeof(heat));
  textOffset = GRID_W;
  textLast = 0;
  resetRain();
  clearFb();
  markChanged();
}

static void tickPattern() {
  switch (S.pattern) {
    case P_PAINT:   drawPaint();      break;
    case P_RAINBOW: tickRainbow();    break;
    case P_HYPNO:   tickHypno();      break;
    case P_RINGS:   tickPulseRings(); break;
    case P_FIRE:    tickFire();       break;
    case P_SPARKLE: tickSparkle();    break;
    case P_PLASMA:  tickPlasma();     break;
    case P_RAIN:    tickRain();       break;
    case P_HEART:   tickHeart();      break;
    case P_BOUNCE:  tickBounce();     break;
    case P_TEXT:    tickScrollText(); break;
  }
}

// How long between animation steps, with the Speed setting (50 = as before)
static uint32_t intervalFor(int p) {
  float k = powf(2.0f, (S.speed - 50) / 25.0f);
  float ms = INTERVALS[p] / k;
  return ms < 8 ? 8 : (uint32_t)ms;
}

// ── Output: rotate, smooth, beat, brightness, dither, show ───
static void showFrame(double now) {
  const float keep = (S.pattern == P_FLUID) ? 0.45f : 0.0f;   // temporal smoothing for the fluid
  float gain = 1.0f;
  if (S.pulse && S.pattern != P_MUSIC && !(S.pattern == P_HEART) && musicPlaying(now)) {
    float p = fminf(1.0f, beatPulse * 1.3f);
    gain = (S.pattern == P_FLUID || S.pattern == P_FIRE) ? 0.7f + 0.3f * p : 0.35f + 0.65f * p;
  }
  const float hit = S.pulse || S.pattern == P_MUSIC ? hitAmt : 0;
  const float gold = S.pulse || S.pattern == P_MUSIC ? goldAmt : 0;
  static const float RED[3] = {1, 0, 0}, GOLD[3] = {1, 0.7f, 0.12f};
  const float bright = S.brightness;
  for (int y = 0; y < GRID_H; y++) {
    for (int x = 0; x < GRID_W; x++) {
      uint8_t out[3];
      for (int c = 0; c < 3; c++) {
        float s = smoothFb[y][x][c] * keep + fb[y][x][c] * (1 - keep);
        smoothFb[y][x][c] = s;
        s *= gain;
        if (hit > 0) s = s * (1 - hit) + RED[c] * hit;
        if (gold > 0) s = s * (1 - gold) + GOLD[c] * gold;
        shown[y][x][c] = (uint8_t)(fminf(1.0f, s) * 255 + 0.5f);
        float v = s * bright + ditherErr[y][x][c];
        int q = (int)(v + 0.5f);
        q = q < 0 ? 0 : (q > 255 ? 255 : q);
        ditherErr[y][x][c] = v - q;
        out[c] = q;
      }
      int rx, ry;
      toRaw(x, y, rx, ry);
      leds[ry * GRID_W + rx] = CRGB(out[0], out[1], out[2]);
    }
  }
  FastLED.show();
}

// ============================================================
//  WEB PAGE
// ============================================================
static const char PAGE[] PROGMEM = R"HTML(<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<meta name="theme-color" content="#0c0e11">
<title>Matrix</title>
<style>
:root{--bg:#0c0e11;--card:#14171c;--raise:#1d2128;--line:rgba(255,255,255,.07);--text:#eef0f3;--dim:#8c94a0;--faint:#59616c;--acc:#8ab4ff;--ok:#5fd99a}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html{touch-action:manipulation;background:var(--bg);-webkit-text-size-adjust:100%}
body{margin:0;color:var(--text);font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:radial-gradient(900px 500px at 15% -10%,rgba(138,180,255,.07),transparent 70%),var(--bg);min-height:100vh}
button{font:inherit;color:inherit;border:0;background:none;padding:0;cursor:pointer;-webkit-user-select:none;user-select:none;touch-action:manipulation}
label{touch-action:manipulation}
svg{width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;flex:none}
header{max-width:1200px;margin:0 auto;padding:18px 20px 2px;display:flex;align-items:center;justify-content:space-between;gap:12px}
.brand{display:flex;align-items:center;gap:10px;font-weight:650;font-size:18px}
.logo{width:20px;height:20px;display:grid;grid-template-columns:repeat(3,1fr);gap:2px}
.logo i{border-radius:2px;background:var(--acc)}
.logo i:nth-child(odd){opacity:.35}
.pill{display:flex;align-items:center;gap:8px;padding:7px 12px;border-radius:99px;background:var(--card);border:1px solid var(--line);color:var(--dim);font-size:13px;min-width:0}
.pill span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dot{width:8px;height:8px;border-radius:50%;background:var(--faint);flex:none}
.dot.on{background:var(--ok)}
main{max-width:1200px;margin:0 auto;padding:12px 20px 48px;display:flex;flex-direction:column;gap:16px}
.col{display:contents}
@media(min-width:960px){main{display:grid;grid-template-columns:400px minmax(0,1fr);gap:20px;align-items:start}.col{display:flex;flex-direction:column;gap:20px}}
#cPreview{order:1}#cModes{order:2}#cPanel{order:3}#cBeat{order:4}#cConn{order:5}
.card{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:18px;min-width:0}
h2{margin:0;font-size:17px;font-weight:620}
.sub{color:var(--dim);font-size:13.5px;margin:3px 0 0}
.head{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:16px}
.device{background:#050607;border-radius:22px;padding:14px;box-shadow:inset 0 0 0 1px rgba(255,255,255,.05)}
#grid{display:grid;grid-template-columns:repeat(8,1fr);gap:7px;aspect-ratio:1;touch-action:none}
#grid div{border-radius:30%;background:#121418}
#grid.paint{cursor:crosshair}
.bar{display:flex;align-items:center;gap:12px;margin-top:16px;color:var(--dim)}
.bar output{width:40px;text-align:right;font-size:13.5px;font-variant-numeric:tabular-nums}
.icon-btn{width:44px;height:44px;border-radius:13px;background:var(--raise);display:grid;place-items:center;color:var(--text);flex:none}
.icon-btn:active,.btn:active,.tile:active,.presets button:active,.palette button:active{transform:scale(.96)}
.ctl{margin-top:20px}
.lab{display:flex;justify-content:space-between;align-items:baseline;font-size:14px;color:var(--dim);margin-bottom:2px}
.lab output{color:var(--text);font-variant-numeric:tabular-nums}
input[type=range]{-webkit-appearance:none;appearance:none;width:100%;height:32px;background:none;margin:0;--p:50%;--c:var(--acc);cursor:pointer}
input[type=range]:focus{outline:none}
input[type=range]::-webkit-slider-runnable-track{height:8px;border-radius:99px;background:linear-gradient(90deg,var(--c) 0 var(--p),#2b3038 var(--p) 100%)}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:26px;height:26px;margin-top:-9px;border-radius:50%;background:#fff;box-shadow:0 1px 6px rgba(0,0,0,.5),0 0 0 6px rgba(255,255,255,.05)}
input[type=range]::-moz-range-track{height:8px;border-radius:99px;background:#2b3038}
input[type=range]::-moz-range-progress{height:8px;border-radius:99px;background:var(--c)}
input[type=range]::-moz-range-thumb{width:26px;height:26px;border:0;border-radius:50%;background:#fff;box-shadow:0 1px 6px rgba(0,0,0,.5)}
.bar input[type=range]{flex:1}
.feat{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
.more{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:6px;margin-top:10px}
.more .tile{padding:4px;gap:5px;border-radius:14px}
.more .tile span{font-size:11px;text-align:center;text-overflow:clip;padding:0 0 2px}
@media(min-width:600px){.more{gap:10px}.more .tile{padding:6px;gap:7px;border-radius:16px}.more .tile span{font-size:12.5px;text-align:left;padding:0 3px 3px}}
.tile{display:flex;flex-direction:column;gap:7px;text-align:left;padding:6px;border-radius:16px;background:var(--raise);border:1.5px solid transparent;min-width:0}
.tile .th{aspect-ratio:1;border-radius:11px;background:#0a0b0d;display:grid;place-items:center;overflow:hidden;font-weight:700;font-size:19px;position:relative}
.feat .tile .th{aspect-ratio:16/10}
.tile span{font-size:12px;line-height:1.25;padding:0 3px 3px;color:var(--dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.feat .tile span{font-size:14.5px;color:var(--text);font-weight:600;padding:0 4px 4px}
.tile small{display:block;font-size:12px;color:var(--dim);font-weight:400;overflow:hidden;text-overflow:ellipsis}
.tile.on{border-color:var(--acc);background:#1f2736}
.tile.on span{color:var(--text)}
.tile canvas{position:absolute;inset:14%;width:72%;height:72%;image-rendering:pixelated;border-radius:4px}
.stack{display:grid;grid-template-columns:minmax(0,1fr)}
.panel{min-width:0;display:none}
.panel.on{display:block}
@media(min-width:960px){.panel{display:block;grid-area:1/1;visibility:hidden}.panel.on{visibility:visible}}
.chips{display:flex;gap:10px;flex-wrap:wrap}
.chip{position:relative;display:flex;align-items:center;gap:10px;padding:7px 16px 7px 7px;border-radius:14px;background:var(--raise);font-size:14.5px;cursor:pointer}
.chip i{width:32px;height:32px;border-radius:10px;box-shadow:inset 0 0 0 1px rgba(255,255,255,.15)}
.chip input{position:absolute;inset:0;width:100%;height:100%;opacity:0;cursor:pointer;border:0;padding:0}
.presets{display:flex;gap:12px;flex-wrap:wrap;margin-top:14px}
.presets button{width:36px;height:36px;border-radius:50%;box-shadow:inset 0 0 0 1px rgba(255,255,255,.15)}
.presets button.on,.palette button.on{box-shadow:0 0 0 2px var(--card),0 0 0 4px var(--acc)}
.btns{display:flex;gap:10px;margin-top:20px}
.btn{flex:1;display:flex;align-items:center;justify-content:center;gap:8px;height:48px;border-radius:14px;background:var(--raise);font-weight:560}
.btn.pri{background:var(--acc);color:#0b1220}
.row{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-top:20px}
.row .t{font-size:14.5px}
.row .t small{display:block;color:var(--dim);font-size:13px}
.sw{position:relative;width:52px;height:32px;flex:none}
.sw input{position:absolute;opacity:0;inset:0;width:100%;height:100%;margin:0;cursor:pointer;z-index:1}
.sw span{position:absolute;inset:0;border-radius:99px;background:#2b3038;transition:background .15s}
.sw span:after{content:"";position:absolute;left:3px;top:3px;width:26px;height:26px;border-radius:50%;background:#fff;transition:transform .15s}
.sw input:checked+span{background:var(--acc)}
.sw input:checked+span:after{transform:translateX(20px)}
.seg{display:flex;background:var(--raise);border-radius:13px;padding:3px;gap:3px}
.seg button{flex:1;height:40px;border-radius:10px;color:var(--dim);font-weight:560}
.seg button.on{background:#2e3540;color:var(--text)}
.text-in{display:flex;gap:10px}
input[type=text],input[type=password],select{flex:1;min-width:0;font:inherit;font-size:16px;color:var(--text);background:var(--raise);border:1px solid transparent;border-radius:14px;padding:12px 14px;outline:none;-webkit-appearance:none;appearance:none}
input[type=text]:focus,input[type=password]:focus,select:focus{border-color:var(--acc)}
.palette{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-top:16px}
@media(min-width:600px){.palette{grid-template-columns:repeat(12,minmax(0,1fr));gap:8px}}
.palette button,.palette label{aspect-ratio:1;border-radius:12px;box-shadow:inset 0 0 0 1px rgba(255,255,255,.12);position:relative;cursor:pointer}
.palette label{background:conic-gradient(#ff3b3b,#ffd23b,#3bff6b,#3bd8ff,#6b5bff,#ff3bd8,#ff3b3b)}
.palette label input{position:absolute;inset:0;opacity:0;width:100%;height:100%;border:0;padding:0;cursor:pointer}
.status{display:flex;gap:12px;align-items:center;padding:13px 14px;background:var(--raise);border-radius:14px;font-size:14.5px}
.status small{display:block;color:var(--dim);font-size:13px}
.kv{display:flex;justify-content:space-between;gap:12px;padding:12px 0;border-top:1px solid var(--line);font-size:14.5px}
.kv:first-of-type{border-top:0;padding-top:0}
.kv span:first-child{color:var(--dim)}
.kv span:last-child{text-align:right;overflow-wrap:anywhere}
#wifiForm{display:none;flex-direction:column;gap:10px;margin-top:14px}
#wifiForm.open{display:flex}
.note{color:var(--dim);font-size:13px;margin:12px 0 0}
#hot{color:#e8b86a}
</style></head><body>
<header>
 <div class="brand"><div class="logo"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>Matrix</div>
 <div class="pill"><b class="dot" id="netDot"></b><span id="netTxt">Hotspot</span></div>
</header>
<main>
<div class="col">
 <section class="card" id="cPreview">
  <div class="device"><div id="grid"></div></div>
  <div class="bar">
   <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
   <input type="range" data-k="brightness" min="1" max="100" aria-label="Brightness">
   <output id="brightOut"></output>
   <button class="icon-btn" id="rot" title="Rotate the picture" aria-label="Rotate"><svg viewBox="0 0 24 24"><path d="M20 12a8 8 0 1 1-2.3-5.7"/><path d="M20 4v5h-5"/></svg></button>
  </div>
  <p class="note" id="hot" hidden>Above 50 the board gets hot.</p>
 </section>
 <section class="card" id="cBeat">
  <div class="head"><div><h2>Beat</h2><p class="sub">Every mode reacts to the music on your Pietatos.</p></div>
   <label class="sw"><input type="checkbox" data-k="pulse" aria-label="React to the beat"><span></span></label></div>
  <div class="status"><b class="dot" data-beatdot></b><div data-beattxt></div></div>
 </section>
 <section class="card" id="cConn">
  <div class="head"><div><h2>Connection</h2></div></div>
  <div class="kv"><span>Hotspot</span><span id="apTxt"></span></div>
  <div class="kv"><span>Your Wi-Fi</span><span id="wifiTxt"></span></div>
  <div class="btns" style="margin-top:6px"><button class="btn" id="wifiOpen">Join Wi-Fi</button></div>
  <div id="wifiForm">
   <div class="text-in"><select id="ssidSel" aria-label="Networks"><option value="">Pick a network</option></select><button class="icon-btn" id="scan" title="Find networks" aria-label="Find networks"><svg viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 3v6h-6"/></svg></button></div>
   <input type="text" id="ssid" placeholder="Network name" autocomplete="off" autocapitalize="off" spellcheck="false">
   <input type="password" id="pass" placeholder="Password">
   <div class="btns" style="margin-top:0"><button class="btn" id="forget">Forget</button><button class="btn pri" id="join">Connect</button></div>
   <p class="note">The hotspot stays on, so this page keeps working while the board joins.</p>
  </div>
 </section>
</div>
<div class="col">
 <section class="card" id="cModes">
  <div class="feat" id="feat"></div>
  <div class="more" id="more"></div>
 </section>
 <section class="card" id="cPanel"><div class="stack">

  <div class="panel" data-p="11">
   <div class="head"><div><h2>Fluid</h2><p class="sub">Tilt the board to pour it. Shake it to splash.</p></div></div>
   <div class="chips"><label class="chip"><i></i>Liquid<input type="color" data-k="fluidColor"></label><label class="chip"><i></i>Foam<input type="color" data-k="foamColor"></label></div>
   <div class="presets" data-set="fluid"></div>
   <div class="ctl"><div class="lab"><span>Amount</span><output data-for="fill"></output></div><input type="range" data-k="fill" min="5" max="60" data-fmt="pct"></div>
   <div class="ctl"><div class="lab"><span>Thickness</span><output data-for="thick"></output></div><input type="range" data-k="thick" min="0" max="100" data-fmt="thick"></div>
   <div class="btns"><button class="btn" data-act="splash">Splash</button><button class="btn" data-act="reset">Settle</button></div>
   <div class="row"><div class="t">Mirror the tilt<small>Turn on if tilting left pours to the right</small></div><label class="sw"><input type="checkbox" data-k="tiltFlip"><span></span></label></div>
  </div>

  <div class="panel" data-p="4">
   <div class="head"><div><h2>Fire</h2><p class="sub">Flames rising from the bottom edge.</p></div></div>
   <div class="chips"><label class="chip"><i></i>Flame<input type="color" data-k="fireColor"></label><label class="chip"><i></i>Hot core<input type="color" data-k="fireHot"></label></div>
   <div class="presets" data-set="fire"></div>
   <div class="ctl"><div class="lab"><span>Height</span><output data-for="fireHeight"></output></div><input type="range" data-k="fireHeight" min="0" max="100" data-fmt="pct"></div>
  </div>

  <div class="panel" data-p="12">
   <div class="head"><div><h2>Music</h2><p class="sub">Rings out from the middle on every beat, and shows a game's colours while one's on.</p></div></div>
   <div class="status"><b class="dot" data-beatdot></b><div data-beattxt></div></div>
   <div class="row"><div class="t">My own colour<small>Instead of the colours Pietato sends</small></div><label class="sw"><input type="checkbox" data-k="musicOwnOn"><span></span></label></div>
   <div class="chips" style="margin-top:14px"><label class="chip"><i></i>Colour<input type="color" data-k="musicOwn"></label></div>
  </div>

  <div class="panel" data-p="10">
   <div class="head"><div><h2>Text</h2><p class="sub">Scrolls a message across the matrix.</p></div></div>
   <div class="text-in"><input type="text" id="msg" maxlength="60" placeholder="Type a message" enterkeyhint="send"><button class="btn pri" id="sendText" style="flex:none;padding:0 22px">Show</button></div>
   <div class="chips" style="margin-top:16px"><label class="chip"><i></i>Colour<input type="color" data-k="textColor"></label></div>
   <div class="presets" data-set="text"></div>
   <div class="ctl"><div class="lab"><span>Speed</span><output data-for="textSpeed"></output></div><input type="range" data-k="textSpeed" min="1" max="100" data-fmt="speed"></div>
  </div>

  <div class="panel" data-p="0">
   <div class="head"><div><h2>Paint</h2><p class="sub">Draw on the preview with your finger.</p></div></div>
   <div class="seg" id="tool"><button data-tool="draw" class="on">Draw</button><button data-tool="erase">Erase</button></div>
   <div class="palette" id="palette"></div>
   <div class="btns"><button class="btn" id="fillBtn">Fill all</button><button class="btn" id="clearBtn">Clear</button></div>
  </div>

  <div class="panel" data-p="1 2 3 5 6 7 8 9">
   <div class="head"><div><h2 id="animName"></h2><p class="sub" id="animSub"></p></div></div>
   <div class="ctl"><div class="lab"><span>Speed</span><output data-for="speed"></output></div><input type="range" data-k="speed" min="1" max="100" data-fmt="speed"></div>
  </div>

 </div></section>
</div>
</main>
<script>
const $=id=>document.getElementById(id),Q=(s,r=document)=>[...r.querySelectorAll(s)];
const MODES=[{p:11,n:"Fluid",c:"Tilt to pour"},{p:4,n:"Fire",c:"Any colour"},{p:12,n:"Music",c:"With Pietato"},
 {p:10,n:"Text"},{p:0,n:"Paint"},{p:1,n:"Rainbow"},{p:6,n:"Plasma"},{p:2,n:"Hypno"},
 {p:3,n:"Rings"},{p:5,n:"Sparkle"},{p:7,n:"Rain"},{p:8,n:"Heart"},{p:9,n:"Bounce"}];
const ABOUT={1:"A rainbow drifting across.",2:"A turning spiral.",3:"Rings pulsing out from the middle.",5:"Random twinkles.",
 6:"Slow waves of colour.",7:"Green drops falling.",8:"A beating heart. While Pietato plays music, it beats with the song.",9:"A ball bouncing off the walls."};
const SETS={fluid:[["#0038ff","#8cf2ff"],["#ff1000","#ffc010"],["#18ff05","#d8ff60"],["#8c00ff","#ff70e6"],["#ff8c00","#ffff99"]],
 fire:[["#ff1000","#ff6000"],["#0020ff","#40c0ff"],["#10ff00","#c0ff40"],["#8000ff","#ff40ff"],["#ff0030","#ff9060"]],
 text:[["#0030ff"],["#ffffff"],["#ff2050"],["#20ff60"],["#ffc020"],["#c040ff"]]};
const KEYS={fluid:["fluidColor","foamColor"],fire:["fireColor","fireHot"],text:["textColor"]};
const PALETTE=["#ffffff","#ff2040","#ff7a00","#ffd400","#40ff40","#00e0c0","#0090ff","#3040ff","#a040ff","#ff40c0","#804020"];
const HEART="url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath fill='%23ff2d55' d='M12 21s-7.5-4.6-9.5-9.2C1.2 8.6 3.2 5 6.6 5c2 0 3.4 1.1 4.4 2.5C12 6.1 13.4 5 15.4 5c3.4 0 5.4 3.6 4.1 6.8C19.5 16.4 12 21 12 21z'/%3E%3C/svg%3E\") center/58% no-repeat,#0a0b0d";
let st={},touched={},tool="draw",cells=[],deb={};
const get=u=>fetch(u).catch(()=>{});
function later(k,u){clearTimeout(deb[k]);deb[k]=setTimeout(()=>get(u),70)}
function send(k,v){later(k,k=="brightness"?"/brightness?v="+v:"/config?"+k+"="+encodeURIComponent(v))}
const fresh=k=>Date.now()-(touched[k]||0)<1800;
function fmt(f,v){v=+v;return f=="pct"?v+"%":f=="thick"?(v<20?"Water":v<45?"Light":v<70?"Thick":"Syrup"):f=="speed"?(v<20?"Very slow":v<40?"Slow":v<61?"Normal":v<81?"Fast":"Very fast"):v}
function fillRange(r){r.style.setProperty("--p",(r.value-r.min)/(r.max-r.min)*100+"%")}
function hexOk(c){return /^#[0-9a-f]{6}$/i.test(c||"")?c.toLowerCase():"#000000"}

// preview
for(let i=0;i<64;i++){const d=document.createElement("div");d.dataset.i=i;$("grid").appendChild(d);cells.push(d)}
// mode tiles
MODES.forEach((m,i)=>{const b=document.createElement("button");b.className="tile";b.dataset.p=m.p;
 b.innerHTML='<div class="th"></div><span>'+m.n+(m.c?"<small>"+m.c+"</small>":"")+"</span>";
 if(m.p==0){const c=document.createElement("canvas");c.width=c.height=8;b.firstChild.appendChild(c)}
 b.onclick=()=>setMode(m.p);(i<3?$("feat"):$("more")).appendChild(b)});
function setMode(p){st.pattern=p;touched.pattern=Date.now();render();get("/pattern?n="+p)}
function thumb(p){const s=st,mc=s.musicOwnOn?s.musicOwn:"#8ab4ff";switch(p){
 case 11:return"linear-gradient(180deg,#0a0b0d 0 46%,"+s.foamColor+" 46% 53%,"+s.fluidColor+" 53%)";
 case 4:return"radial-gradient(85% 95% at 50% 118%,"+s.fireHot+" 0 28%,"+s.fireColor+" 52%,#0a0b0d 82%)";
 case 12:return"radial-gradient(circle,"+mc+" 0 7%,transparent 8% 20%,"+mc+"aa 21% 25%,transparent 26% 38%,"+mc+"55 39% 43%,transparent 44%),#0a0b0d";
 case 1:return"linear-gradient(135deg,#ff3b3b,#ffb02e,#f4ff3b,#3bff6b,#3bd8ff,#5b5bff,#d93bff)";
 case 6:return"radial-gradient(circle at 25% 30%,#ff3dbb,transparent 55%),radial-gradient(circle at 75% 70%,#3dc5ff,transparent 55%),radial-gradient(circle at 70% 18%,#7cff3d,transparent 45%),#2a1a5c";
 case 2:return"repeating-conic-gradient(from 0deg,#ff3d7f 0 20deg,#3d7bff 20deg 40deg,#7a3dff 40deg 60deg)";
 case 3:return"repeating-radial-gradient(circle,#7a5cff 0 4px,#140c2e 4px 11px)";
 case 5:return"radial-gradient(circle at 22% 30%,#fff 0 5%,transparent 7%),radial-gradient(circle at 72% 25%,#ff5ad1 0 6%,transparent 8%),radial-gradient(circle at 55% 70%,#5ad1ff 0 5%,transparent 7%),radial-gradient(circle at 25% 76%,#ffe15a 0 4%,transparent 6%),#0a0b0d";
 case 7:return"linear-gradient(180deg,transparent 20%,#3dff7a) 18% 0/11% 62% no-repeat,linear-gradient(180deg,transparent 20%,#3dff7a) 50% 30%/11% 50% no-repeat,linear-gradient(180deg,transparent 20%,#3dff7a) 82% 90%/11% 70% no-repeat,#04120a";
 case 8:return HEART;
 case 9:return"radial-gradient(circle at 64% 40%,#2d6bff 0 12%,transparent 13%),radial-gradient(circle at 47% 54%,#2d6bff66 0 9%,transparent 10%),radial-gradient(circle at 32% 66%,#2d6bff2a 0 7%,transparent 8%),#0a0b0d";
 default:return"#0a0b0d"}}
function drawTiles(){Q(".tile").forEach(t=>{const p=+t.dataset.p,th=t.firstChild;t.classList.toggle("on",p==st.pattern);
  if(p==10){th.textContent="Aa";th.style.color=st.textColor;th.style.background="#0a0b0d"}
  else if(p==0){const c=th.firstChild.getContext("2d");(st.grid||[]).forEach((row,y)=>row.forEach((v,x)=>{c.fillStyle="rgb("+v.r+","+v.g+","+v.b+")";c.fillRect(x,y,1,1)}))}
  else th.style.background=thumb(p)})}
// presets
Q(".presets").forEach(el=>{const set=el.dataset.set;SETS[set].forEach(pair=>{const b=document.createElement("button");
 b.style.background=pair.length>1?"radial-gradient(circle at 35% 35%,"+pair[1]+","+pair[0]+" 72%)":pair[0];b.dataset.v=pair.join();
 b.onclick=()=>{const keys=KEYS[set];let q=[];keys.forEach((k,i)=>{st[k]=pair[i];touched[k]=Date.now();q.push(k+"="+encodeURIComponent(pair[i]))});render();get("/config?"+q.join("&"))};
 el.appendChild(b)})});
// paint palette
PALETTE.forEach(c=>{const b=document.createElement("button");b.style.background=c;b.dataset.c=c;b.onclick=()=>pickPaint(c);$("palette").appendChild(b)});
{const l=document.createElement("label");l.title="Any colour";l.innerHTML='<input type="color" id="paintAny">';$("palette").appendChild(l);
 l.firstChild.addEventListener("input",e=>pickPaint(e.target.value))}
function pickPaint(c){st.paintColor=c;touched.paintColor=Date.now();setTool("draw");render();send("paintColor",c)}
function setTool(t){tool=t;Q("#tool button").forEach(b=>b.classList.toggle("on",b.dataset.tool==t))}
Q("#tool button").forEach(b=>b.onclick=()=>setTool(b.dataset.tool));
const rgbOf=h=>[1,3,5].map(i=>parseInt(h.substr(i,2),16));
$("fillBtn").onclick=()=>{const c=rgbOf(hexOk(st.paintColor));get("/fill?r="+c[0]+"&g="+c[1]+"&b="+c[2]).then(poll)};
$("clearBtn").onclick=()=>get("/clear").then(poll);
let drawing=false,lastCell=-1;
function paintAt(e){if(st.pattern!=0)return;const t=document.elementFromPoint(e.clientX,e.clientY);
 if(!t||t.dataset.i===undefined)return;const i=+t.dataset.i;if(i===lastCell)return;lastCell=i;
 const col=tool=="erase"?"#000000":hexOk(st.paintColor),c=rgbOf(col);t.style.background=col;
 get("/set?x="+(i%8)+"&y="+(i>>3)+"&r="+c[0]+"&g="+c[1]+"&b="+c[2])}
$("grid").addEventListener("pointerdown",e=>{drawing=true;lastCell=-1;paintAt(e)});
$("grid").addEventListener("pointermove",e=>{if(drawing)paintAt(e)});
addEventListener("pointerup",()=>{if(drawing){drawing=false;setTimeout(poll,400)}});
// generic controls
Q("input[type=range][data-k]").forEach(r=>r.addEventListener("input",()=>{const k=r.dataset.k;st[k]=+r.value;touched[k]=Date.now();fillRange(r);outs();send(k,r.value);if(k=="brightness")$("hot").hidden=r.value<=50}));
Q("input[type=color][data-k]").forEach(c=>c.addEventListener("input",()=>{const k=c.dataset.k;st[k]=c.value;touched[k]=Date.now();render();send(k,c.value)}));
Q("input[type=checkbox][data-k]").forEach(c=>c.addEventListener("change",()=>{const k=c.dataset.k;st[k]=c.checked?1:0;touched[k]=Date.now();render();send(k,st[k])}));
Q("[data-act]").forEach(b=>b.onclick=()=>get("/config?"+b.dataset.act+"=1"));
$("rot").onclick=()=>get("/config?rot=1").then(poll);
$("sendText").onclick=()=>{st.pattern=10;touched.pattern=Date.now();render();get("/settext?msg="+encodeURIComponent($("msg").value))};
$("msg").addEventListener("keydown",e=>{if(e.key=="Enter"){e.preventDefault();$("sendText").onclick();$("msg").blur()}});
$("msg").addEventListener("input",()=>touched.text=Date.now());
// wi-fi
$("wifiOpen").onclick=()=>{const f=$("wifiForm"),o=!f.classList.contains("open");f.classList.toggle("open",o);$("wifiOpen").textContent=o?"Close":"Join Wi-Fi";if(o&&$("ssidSel").options.length<2)scan()};
$("ssidSel").onchange=e=>{if(e.target.value){$("ssid").value=e.target.value;$("pass").focus()}};
$("scan").onclick=scan;
async function scan(){const s=$("ssidSel");s.options[0].text="Looking for networks…";await get("/scan?start=1");
 for(let i=0;i<20;i++){await new Promise(r=>setTimeout(r,700));try{const j=await (await fetch("/scan")).json();
  if(!j.scanning){s.length=1;s.options[0].text=j.nets.length?"Pick a network":"No networks found";
   j.nets.forEach(n=>{const o=document.createElement("option");o.value=n.ssid;o.text=n.ssid+(n.lock?"  🔒":"");s.add(o)});return}}catch(e){}}
 s.options[0].text="Pick a network"}
$("join").onclick=()=>{const n=$("ssid").value.trim();if(!n){$("ssid").focus();return}
 get("/wifi?ssid="+encodeURIComponent(n)+"&pass="+encodeURIComponent($("pass").value)).then(()=>{$("pass").value="";$("wifiOpen").onclick();setTimeout(poll,500)})};
$("forget").onclick=()=>get("/wifi?forget=1").then(()=>{$("ssid").value="";$("pass").value="";setTimeout(poll,300)});

function outs(){Q("output[data-for]").forEach(o=>{const r=document.querySelector('input[data-k="'+o.dataset.for+'"]');o.textContent=fmt(r.dataset.fmt,r.value)});
 $("brightOut").textContent=document.querySelector('input[data-k="brightness"]').value}
function beatText(){const w=st.wifi||{},b=st.pietato||{};
 if(!w.joined)return[false,w.ssid?"Joining "+w.ssid+"…":"Not on your Wi-Fi yet",w.ssid?"If this takes long, check the password under Connection.":"Your Pietatos find the board on your Wi-Fi. Join it under Connection."];
 if(b.game)return[true,"Showing a game from Pietato",b.ip];
 if(b.playing)return[true,"Following Pietato's music",b.ip+(st.pulse?"":" · beat effects off")];
 if(b.heard)return[true,"Pietato's quiet",b.ip];
 return[false,"Waiting for a Pietato to play","On your Wi-Fi as "+w.ip]}
function render(){
 Q("[data-k]").forEach(el=>{const k=el.dataset.k;if(st[k]===undefined||fresh(k))return;
  if(el.type=="checkbox")el.checked=!!st[k];else if(el.type=="color")el.value=hexOk(st[k]);else{el.value=st[k];fillRange(el)}});
 Q(".chip").forEach(c=>{const i=c.querySelector("input");c.querySelector("i").style.background=hexOk(st[i.dataset.k])});
 Q(".presets").forEach(el=>{const keys=KEYS[el.dataset.set],cur=keys.map(k=>hexOk(st[k])).join();Q("button",el).forEach(b=>b.classList.toggle("on",b.dataset.v==cur))});
 Q("#palette button").forEach(b=>b.classList.toggle("on",b.dataset.c==hexOk(st.paintColor)));
 if(!fresh("text")&&document.activeElement!==$("msg")&&st.text!==undefined)$("msg").value=st.text;
 Q(".panel").forEach(p=>p.classList.toggle("on",p.dataset.p.split(" ").includes(String(st.pattern))));
 const m=MODES.find(m=>m.p==st.pattern);if(ABOUT[st.pattern]){$("animName").textContent=m.n;$("animSub").textContent=ABOUT[st.pattern]}
 $("grid").classList.toggle("paint",st.pattern==0);
 drawTiles();outs();$("hot").hidden=(st.brightness||0)<=50;
 const [on,t,s]=beatText();Q("[data-beatdot]").forEach(d=>d.classList.toggle("on",on));
 Q("[data-beattxt]").forEach(d=>d.innerHTML=t+(s?"<small>"+s+"</small>":""));
 const w=st.wifi||{},port=st.port||8000;
 $("netDot").classList.toggle("on",!!w.joined);
 $("netTxt").textContent=w.joined?w.ssid+" · "+w.ip+":"+port:"Hotspot · "+(st.ap?st.ap.ip:"")+":"+port;
 if(st.ap)$("apTxt").textContent=st.ap.ssid+" · "+st.ap.ip+":"+port;
 $("wifiTxt").textContent=w.joined?w.ssid+" · "+w.ip+":"+port:w.ssid?"Joining "+w.ssid+"…":"Not set up";
 if(!$("wifiForm").classList.contains("open")&&w.ssid&&!$("ssid").value)$("ssid").value=w.ssid}
async function poll(){try{const s=await (await fetch("/state")).json();
 for(const k in s)if(!fresh(k))st[k]=s[k];render()}catch(e){}}
async function frame(){try{const h=await (await fetch("/frame")).text();
 if(!drawing)for(let i=0;i<64;i++){const r=parseInt(h.substr(i*6,2),16),g=parseInt(h.substr(i*6+2,2),16),b=parseInt(h.substr(i*6+4,2),16),
  a=Math.max(r,g,b)/255,cell=cells[i];
  cell.style.background=a<.02?"#121418":"rgb("+r+","+g+","+b+")";
  cell.style.boxShadow=a<.02?"none":"0 0 "+(4+12*a).toFixed(1)+"px rgba("+r+","+g+","+b+","+(.55*a).toFixed(2)+")"}}catch(e){}
 setTimeout(frame,100)}
poll();setInterval(poll,2000);frame();
</script></body></html>)HTML";

static String hexColor(uint32_t c) {
  char b[8];
  snprintf(b, sizeof(b), "#%06X", (unsigned)(c & 0xFFFFFF));
  return String(b);
}

static uint32_t parseColor(const String &s) {
  String t = s;
  if (t.startsWith("#")) t = t.substring(1);
  return strtoul(t.c_str(), nullptr, 16) & 0xFFFFFF;
}

static int clampi(long v, int lo, int hi) { return v < lo ? lo : (v > hi ? hi : (int)v); }

static void jsonText(String &s, const char *p) {   // a JSON string, quotes included
  s += '"';
  for (; *p; p++) {
    if (*p == '"' || *p == '\\') { s += '\\'; s += *p; }
    else if ((uint8_t)*p >= 32) s += *p;
  }
  s += '"';
}

// ── Wi-Fi (your network, set from the page) ──────────────────
static String homeSsid, homePass;
static uint32_t joinAt = 0;

static void joinHome() {
  WiFi.disconnect();
  if (homeSsid.length()) WiFi.begin(homeSsid.c_str(), homePass.c_str());
  joinAt = millis();
}

static void wifiTick() {   // not joined: try again every minute
  if (homeSsid.length() && WiFi.status() != WL_CONNECTED && millis() - joinAt > 60000) joinHome();
}

static String buildState() {
  double now = nowSec();
  String s;
  s.reserve(2600);
  s = "{\"brightness\":"; s += S.brightness;
  s += ",\"pattern\":";    s += S.pattern;
  s += ",\"rotation\":";   s += S.rotation;
  s += ",\"tiltFlip\":";   s += S.tiltFlip;
  s += ",\"fill\":";       s += S.fill;
  s += ",\"thick\":";      s += S.thick;
  s += ",\"fireHeight\":"; s += S.fireHeight;
  s += ",\"textSpeed\":";  s += S.textSpeed;
  s += ",\"speed\":";      s += S.speed;
  s += ",\"pulse\":";      s += S.pulse;
  s += ",\"musicOwnOn\":"; s += S.musicOwnOn;
  s += ",\"fluidColor\":\""; s += hexColor(S.fluidColor);
  s += "\",\"foamColor\":\""; s += hexColor(S.foamColor);
  s += "\",\"fireColor\":\""; s += hexColor(S.fireColor);
  s += "\",\"fireHot\":\"";   s += hexColor(S.fireHot);
  s += "\",\"textColor\":\""; s += hexColor(S.textColor);
  s += "\",\"paintColor\":\""; s += hexColor(S.paintColor);
  s += "\",\"musicOwn\":\"";  s += hexColor(S.musicOwn);
  s += "\",\"text\":";        jsonText(s, S.text);
  s += ",\"port\":";          s += WEB_PORT;
  s += ",\"ap\":{\"ssid\":";  jsonText(s, AP_SSID);
  s += ",\"ip\":\"";          s += WiFi.softAPIP().toString();
  s += "\"},\"wifi\":{\"ssid\":"; jsonText(s, homeSsid.c_str());
  bool joined = WiFi.status() == WL_CONNECTED;
  s += ",\"joined\":";        s += joined ? "true" : "false";
  s += ",\"ip\":\"";          if (joined) s += WiFi.localIP().toString();
  s += "\"},\"pietato\":{\"heard\":"; s += pietatoHeard(now) ? "true" : "false";
  s += ",\"playing\":";       s += musicPlaying(now) ? "true" : "false";
  s += ",\"game\":";          s += gamePlaying(now) ? "true" : "false";
  s += ",\"ip\":\"";          if (pFollowing) s += pSource.toString();
  s += "\"},\"grid\":[";
  for (int y = 0; y < GRID_H; y++) {
    s += '[';
    for (int x = 0; x < GRID_W; x++) {
      s += "{\"r\":"; s += S.grid[y][x][0]; s += ",\"g\":"; s += S.grid[y][x][1]; s += ",\"b\":"; s += S.grid[y][x][2]; s += '}';
      if (x < GRID_W - 1) s += ',';
    }
    s += ']';
    if (y < GRID_H - 1) s += ',';
  }
  s += "]}";
  return s;
}

// ── Old endpoints (kept, so anything that used them still works) ──
void handleRoot() { server.send(200, "text/html; charset=utf-8", PAGE); }

void handleSet() {
  int x = server.arg("x").toInt(), y = server.arg("y").toInt();
  if (x < 0 || x >= GRID_W || y < 0 || y >= GRID_H) { server.send(400, "text/plain", "BAD_XY"); return; }
  S.grid[y][x][0] = server.arg("r").toInt();
  S.grid[y][x][1] = server.arg("g").toInt();
  S.grid[y][x][2] = server.arg("b").toInt();
  markChanged();
  server.send(200, "text/plain", "OK");
}

void handleFill() {
  uint8_t r = server.arg("r").toInt(), g = server.arg("g").toInt(), b = server.arg("b").toInt();
  for (int y = 0; y < GRID_H; y++) for (int x = 0; x < GRID_W; x++) { S.grid[y][x][0] = r; S.grid[y][x][1] = g; S.grid[y][x][2] = b; }
  markChanged();
  server.send(200, "text/plain", "OK");
}

void handleClear() {
  memset(S.grid, 0, sizeof(S.grid));
  markChanged();
  server.send(200, "text/plain", "OK");
}

void handleBrightness() {
  S.brightness = clampi(server.arg("v").toInt(), 1, 100);
  helloOwed = true;      // tell your Pietatos too
  markChanged();
  server.send(200, "text/plain", "OK");
}

void handlePattern() {
  startPattern(server.arg("n").toInt());
  server.send(200, "text/plain", "OK");
}

void handleState() { server.send(200, "application/json", buildState()); }

void handleLoadFrame() {
  for (int y = 0; y < GRID_H; y++) for (int x = 0; x < GRID_W; x++) {
    String rk = "r" + String(y) + "_" + String(x), gk = "g" + String(y) + "_" + String(x), bk = "b" + String(y) + "_" + String(x);
    if (server.hasArg(rk)) S.grid[y][x][0] = server.arg(rk).toInt();
    if (server.hasArg(gk)) S.grid[y][x][1] = server.arg(gk).toInt();
    if (server.hasArg(bk)) S.grid[y][x][2] = server.arg(bk).toInt();
  }
  startPattern(P_PAINT);
  server.send(200, "text/plain", "OK");
}

void handleSetText() {
  if (server.hasArg("msg")) {
    String m = server.arg("msg");
    strncpy(S.text, m.c_str(), sizeof(S.text) - 1);
    S.text[sizeof(S.text) - 1] = 0;
    Serial.print("[/settext] "); Serial.println(S.text);
  }
  startPattern(P_TEXT);
  server.send(200, "text/plain", "OK");
}

void handleStop() {
  startPattern(P_PAINT);
  server.send(200, "text/plain", "STOPPED");
}

// ── New endpoints ────────────────────────────────────────────
void handleConfig() {
  bool fillChanged = false;
  for (int i = 0; i < server.args(); i++) {
    String k = server.argName(i), v = server.arg(i);
    if      (k == "rot")        S.rotation = (S.rotation + (v.toInt() < 0 ? 3 : 1)) & 3;
    else if (k == "tiltFlip")   S.tiltFlip = v.toInt() ? 1 : 0;
    else if (k == "fill")     { S.fill = clampi(v.toInt(), 5, 60); fillChanged = true; }
    else if (k == "thick")      S.thick = clampi(v.toInt(), 0, 100);
    else if (k == "fireHeight") S.fireHeight = clampi(v.toInt(), 0, 100);
    else if (k == "textSpeed")  S.textSpeed = clampi(v.toInt(), 1, 100);
    else if (k == "speed")      S.speed = clampi(v.toInt(), 1, 100);
    else if (k == "pulse")      S.pulse = v.toInt() ? 1 : 0;
    else if (k == "musicOwnOn") { S.musicOwnOn = v.toInt() ? 1 : 0; helloOwed = true; }
    else if (k == "musicOwn")   { S.musicOwn = parseColor(v); helloOwed = true; }
    else if (k == "fluidColor") S.fluidColor = parseColor(v);
    else if (k == "foamColor")  S.foamColor = parseColor(v);
    else if (k == "fireColor")  S.fireColor = parseColor(v);
    else if (k == "fireHot")    S.fireHot = parseColor(v);
    else if (k == "textColor")  S.textColor = parseColor(v);
    else if (k == "paintColor") S.paintColor = parseColor(v);
    else if (k == "splash")     splash();
    else if (k == "reset")      resetFluid();
  }
  if (fillChanged) syncParticleCount();
  markChanged();
  server.send(200, "text/plain", "OK");
}

void handleFrame() {
  static char buf[GRID_W * GRID_H * 6 + 1];
  static const char *hx = "0123456789abcdef";
  int k = 0;
  for (int y = 0; y < GRID_H; y++)
    for (int x = 0; x < GRID_W; x++)
      for (int c = 0; c < 3; c++) {
        buf[k++] = hx[shown[y][x][c] >> 4];
        buf[k++] = hx[shown[y][x][c] & 15];
      }
  buf[k] = 0;
  server.send(200, "text/plain", buf);
}

void handleWifi() {
  if (server.hasArg("forget")) {
    homeSsid = ""; homePass = "";
  } else {
    homeSsid = server.arg("ssid");
    homePass = server.arg("pass");
    homeSsid.trim();
  }
  prefs.putString("ssid", homeSsid);
  prefs.putString("pass", homePass);
  joinHome();
  server.send(200, "text/plain", "OK");
}

void handleScan() {
  if (server.hasArg("start")) {
    WiFi.scanDelete();
    WiFi.scanNetworks(true);
    server.send(200, "application/json", "{\"scanning\":true}");
    return;
  }
  int n = WiFi.scanComplete();
  if (n == WIFI_SCAN_RUNNING) { server.send(200, "application/json", "{\"scanning\":true}"); return; }
  String s = "{\"scanning\":false,\"nets\":[";
  int added = 0;
  for (int i = 0; i < n && added < 20; i++) {
    String name = WiFi.SSID(i);
    if (!name.length()) continue;
    bool dup = false;                                  // (the strongest of each name only; they come strongest first)
    for (int j = 0; j < i; j++) if (WiFi.SSID(j) == name) { dup = true; break; }
    if (dup) continue;
    if (added++) s += ',';
    s += "{\"ssid\":"; jsonText(s, name.c_str());
    s += ",\"rssi\":"; s += WiFi.RSSI(i);
    s += ",\"lock\":"; s += WiFi.encryptionType(i) == WIFI_AUTH_OPEN ? "false" : "true";
    s += '}';
  }
  s += "]}";
  server.send(200, "application/json", s);
}

static void startNetwork() {
  WiFi.mode(WIFI_AP_STA);
  WiFi.setSleep(false);                 // awake: a beat comes when it's sent
  WiFi.setHostname(HOSTNAME);
  WiFi.softAP(AP_SSID, AP_PASS);
  delay(100);
  WiFi.softAPConfig(BOARD_IP, BOARD_IP, SUBNET_MASK);

  homeSsid = prefs.getString("ssid", WIFI_SSID);
  homePass = prefs.getString("pass", WIFI_PASS);
  joinHome();

  Serial.print("Hotspot \""); Serial.print(AP_SSID); Serial.print("\": open http://");
  Serial.print(WiFi.softAPIP().toString());
  Serial.printf(":%d\n", WEB_PORT);
  if (homeSsid.length()) { Serial.print("Joining your Wi-Fi: "); Serial.println(homeSsid.c_str()); }

  if (MDNS.begin(HOSTNAME)) MDNS.addService("http", "tcp", WEB_PORT);
  udpOn = udp.begin(GLOW_PORT);

  server.on("/",           handleRoot);
  server.on("/set",        handleSet);
  server.on("/fill",       handleFill);
  server.on("/clear",      handleClear);
  server.on("/brightness", handleBrightness);
  server.on("/pattern",    handlePattern);
  server.on("/state",      handleState);
  server.on("/loadframe",  handleLoadFrame);
  server.on("/settext",    handleSetText);
  server.on("/stop",       handleStop);
  server.on("/config",     handleConfig);
  server.on("/frame",      handleFrame);
  server.on("/wifi",       handleWifi);
  server.on("/scan",       handleScan);
  server.begin();
}

// ── Settings storage ─────────────────────────────────────────
static void loadSettings() {
  defaultSettings();
  prefs.begin("matrix", false);
  size_t len = prefs.getBytesLength("s");
  if (len >= 2 && len <= sizeof(Settings)) {
    Settings tmp = S;                    // older versions saved a shorter struct: the rest keeps its defaults
    if (prefs.getBytes("s", &tmp, len) == len && tmp.version >= 3 && tmp.version <= SETTINGS_VERSION) {
      S = tmp;
      S.version = SETTINGS_VERSION;
    }
  }
  S.text[sizeof(S.text) - 1] = 0;
  if (S.pattern >= NUM_PATTERNS) S.pattern = P_FLUID;
  if (S.speed < 1 || S.speed > 100) S.speed = 50;
}

static void saveSettings() {
  prefs.putBytes("s", &S, sizeof(S));
  savePending = false;
}

// ── BOOT button ──────────────────────────────────────────────
static void nextPreset() {
  presetIndex = (presetIndex + 1) % NUM_PRESETS;
  if (S.pattern == P_FIRE) {
    S.fireColor = FIRE_PRESETS[presetIndex].a;
    S.fireHot   = FIRE_PRESETS[presetIndex].b;
  } else {
    S.fluidColor = FLUID_PRESETS[presetIndex].a;
    S.foamColor  = FLUID_PRESETS[presetIndex].b;
  }
  markChanged();
}

static void handleButton() {
  static bool wasDown = false, longDone = false, tapPending = false;
  static uint32_t downAt = 0, upAt = 0;
  bool down = digitalRead(BTN_PIN) == LOW;
  uint32_t now = millis();

  if (down && !wasDown) {
    downAt = now;
    longDone = false;
    if (tapPending && now - upAt < 350) {      // double-tap
      tapPending = false;
      longDone = true;
      nextPreset();
    }
  }
  if (down && !longDone && now - downAt > 900) {   // hold
    longDone = true;
    tapPending = false;
    startPattern(P_FLUID);
  }
  if (!down && wasDown && !longDone && now - downAt > 30) { tapPending = true; upAt = now; }
  if (tapPending && !down && now - upAt >= 350) {  // single tap
    tapPending = false;
    startPattern((S.pattern + 1) % NUM_PATTERNS);
  }
  wasDown = down;
}

// ── Setup / loop ─────────────────────────────────────────────
static uint32_t lastMicros = 0;
static float fluidAcc = 0;

void setup() {
  Serial.begin(115200);
  pinMode(BTN_PIN, INPUT_PULLUP);

  FastLED.addLeds<WS2812, LED_PIN, RGB>(leds, NUM_LEDS);
  FastLED.setBrightness(255);          // brightness is applied (with dithering) in showFrame()
  FastLED.setDither(DISABLE_DITHER);
  FastLED.clear();
  FastLED.show();

  loadSettings();

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(400000);
  imuOk = qmiBegin();
  Serial.println(imuOk ? "QMI8658 found" : "QMI8658 not found - fluid runs on demo gravity");

  randomSeed(micros());
  updateGravity();
  resetFluid();
  resetRain();
  startNetwork();
  savePending = false;
  lastMicros = micros();
}

void loop() {
  server.handleClient();
  handleButton();
  wifiTick();

  double now = nowSec();
  networkTick(now);
  beatTick(now);

  uint32_t nowUs = micros();
  float dt = (nowUs - lastMicros) * 1e-6f;
  lastMicros = nowUs;
  if (dt > 0.05f) dt = 0.05f;

  if (S.pattern == P_FLUID) {
    updateGravity();
    fluidAcc += dt;
    int steps = 0;
    while (fluidAcc >= STEP && steps < 12) { fluidStep(gravX, gravY, STEP); fluidAcc -= STEP; steps++; }
    if (steps == 12) fluidAcc = 0;
    drawFluid();
  } else if (S.pattern == P_MUSIC) {
    fluidAcc = 0;
    drawMusic(now);
  } else if (S.pattern == P_HEART && S.pulse && musicPlaying(now)) {
    fluidAcc = 0;
    drawHeartToBeat();
  } else {
    fluidAcc = 0;
    uint32_t ms = millis();
    if (ms - patternTimer >= intervalFor(S.pattern)) {
      patternTimer = ms;
      tickPattern();
    }
  }

  showFrame(now);

  if (savePending && (int32_t)(millis() - saveAt) >= 0) saveSettings();
}
