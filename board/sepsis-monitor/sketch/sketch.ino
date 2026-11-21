// Sepsis monitor: STM32 side.
// Reads the Modulino Movement (LSM6DSOX at 0x6A) at 25 Hz into a ring buffer,
// polls Thermo / Light, and drives the Vibro. The Linux side pulls everything
// over the Arduino Bridge:
//   drain()  -> "t0,t1|ax,ay,az;ax,ay,az;..."   accel in milli-g, t in ms
//   env()    -> "temp_c,hum_pct,lux,ir"          (nan fields when absent)
//   vibe(ms,power) -> 1                          power 25..50 (Modulino levels)
//   status() -> "imu=1 thermo=1 light=1 vibro=1"
#include <Arduino_RouterBridge.h>
#include <Arduino_Modulino.h>
#include <Wire.h>

static const uint8_t IMU_ADDR = 0x6A;
static const uint32_t SAMPLE_PERIOD_MS = 40;  // 25 Hz
static const int BUF_N = 128;

struct Sample { int16_t x, y, z; };
static Sample buf[BUF_N];
static volatile int head = 0;   // next write slot
static volatile int tail = 0;   // next read slot
static volatile uint32_t tFirst = 0, tLast = 0;

static ModulinoThermo thermo;
static ModulinoLight light;
static ModulinoVibro vibro;
static bool okImu = false, okThermo = false, okLight = false, okVibro = false;

static float envTemp = NAN, envHum = NAN;
static int envLux = -1, envIr = -1;
static uint32_t lastEnv = 0;

static bool imuWrite(uint8_t reg, uint8_t val) {
  Wire1.beginTransmission(IMU_ADDR);
  Wire1.write(reg);
  Wire1.write(val);
  return Wire1.endTransmission() == 0;
}

static bool imuReadAccel(Sample &s) {
  Wire1.beginTransmission(IMU_ADDR);
  Wire1.write(0x28);  // OUTX_L_A
  if (Wire1.endTransmission(false) != 0) return false;
  if (Wire1.requestFrom(IMU_ADDR, (uint8_t)6) != 6) return false;
  int16_t v[3];
  for (int i = 0; i < 3; i++) {
    uint8_t lo = Wire1.read();
    uint8_t hi = Wire1.read();
    v[i] = (int16_t)((hi << 8) | lo);
  }
  // +-2 g: 0.061 mg per count -> milli-g
  s.x = (int16_t)(v[0] * 61L / 1000);
  s.y = (int16_t)(v[1] * 61L / 1000);
  s.z = (int16_t)(v[2] * 61L / 1000);
  return true;
}

String drain() {
  int t = tail, h = head;
  String out;
  out.reserve(1500);
  int n = (h - t + BUF_N) % BUF_N;
  if (n > 100) { t = (h - 100 + BUF_N) % BUF_N; n = 100; }
  out += String(tFirst) + "," + String(tLast) + "|";
  for (int i = 0; i < n; i++) {
    const Sample &s = buf[(t + i) % BUF_N];
    out += String(s.x) + "," + String(s.y) + "," + String(s.z) + ";";
  }
  tail = h;
  tFirst = tLast;
  return out;
}

String env() {
  String s = isnan(envTemp) ? "nan" : String(envTemp, 2);
  s += ",";
  s += isnan(envHum) ? "nan" : String(envHum, 1);
  s += "," + String(envLux) + "," + String(envIr);
  return s;
}

int vibe(int ms, int power) {
  if (!okVibro) return 0;
  if (ms < 1) ms = 1;
  if (ms > 5000) ms = 5000;
  if (power < 25) power = 25;
  if (power > 50) power = 50;
  vibro.on(ms, false, power);
  return 1;
}

String status() {
  return String("imu=") + (int)okImu + " thermo=" + (int)okThermo +
         " light=" + (int)okLight + " vibro=" + (int)okVibro;
}

void setup() {
  Modulino.begin();   // Wire1 on the UNO Q (Qwiic)
  okThermo = thermo.begin();
  okLight = light.begin();
  okVibro = vibro.begin();
  okImu = imuWrite(0x10, 0x30);   // CTRL1_XL: 52 Hz, +-2 g

  Bridge.begin();
  Bridge.provide("drain", drain);
  Bridge.provide("env", env);
  Bridge.provide("vibe", vibe);
  Bridge.provide("status", status);
}

void loop() {
  static uint32_t next = 0;
  uint32_t now = millis();
  if ((int32_t)(now - next) < 0) { delay(1); return; }
  next = now + SAMPLE_PERIOD_MS;

  if (okImu) {
    Sample s;
    if (imuReadAccel(s)) {
      if (head == tail && tFirst == 0) tFirst = now;
      buf[head] = s;
      head = (head + 1) % BUF_N;
      if (head == tail) tail = (tail + 1) % BUF_N;  // overwrite oldest
      tLast = now;
    }
  }

  if (now - lastEnv > 2000) {
    lastEnv = now;
    if (okThermo) { envTemp = thermo.getTemperature(); envHum = thermo.getHumidity(); }
    if (okLight && light.update()) { envLux = light.getLux(); envIr = light.getIR(); }
  }
}
