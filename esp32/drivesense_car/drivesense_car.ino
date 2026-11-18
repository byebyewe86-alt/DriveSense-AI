/* ============================================================================
   DriveSense AI  -  ESP32 RC-car receiver
   ============================================================================

   WHAT THIS DOES
   -------------
   The ESP32 joins / creates a WiFi network and listens on TCP port 5005.
   The laptop (gesture_car.py) sends one short line per video frame:

         steer , throttle , brake \\n          e.g.  "-32,74,0\\n"

     steer      -100 .. +100    (negative = left, positive = right)
     throttle      0 .. +100    (forward power)
     brake         0 .. +100    (reverse / braking power)

   The ESP32 turns that into left/right wheel speeds (skid steering, like a
   tank) and drives the two L298N channels.

   SAFETY: if no valid packet arrives for WATCHDOG_MS the motors stop. If the
   laptop closes the connection, the motors stop. There is no way for the car
   to keep driving after the link dies.

   WIRING (see esp32/README.md for the table + power notes)
   -------------------------------------------------------
     L298N ENA <- GPIO25      IN1 <- GPIO26      IN2 <- GPIO27   (left side)
     L298N ENB <- GPIO33      IN3 <- GPIO32      IN4 <- GPIO13   (right side)
     Battery +  -> L298N +12V      Battery -  -> L298N GND  AND  ESP32 GND
     L298N OUT1/OUT2 -> the two LEFT motors      OUT3/OUT4 -> the two RIGHT motors

   BOARD SETTINGS (Arduino IDE)
   ----------------------------
     Board            : "ESP32 Dev Module" (or your exact board)
     Upload Speed     : 921600 (drop to 115200 if uploads fail)
     Partition Scheme : Default
     Remove the two little ENA / ENB jumper caps on the L298N board!
   ============================================================================ */

#include <WiFi.h>

/* ---------------------------------------------------------------------------
   1. WHICH NETWORK?
   ---------------------------------------------------------------------------
   AP mode  (default, easiest): the ESP32 makes its own WiFi hotspot called
            "DriveSense-Car". Connect the laptop to it, then the laptop talks
            to 192.168.4.1. No router, works anywhere. The laptop will lose
            normal internet while connected - that is expected.

   STA mode : the ESP32 and the laptop both join your home WiFi / phone
              hotspot. More range, but you must put the ESP32's IP into the
              Python script. Set USE_AP_MODE to 0 and fill in STA_* below.
   --------------------------------------------------------------------------- */

#define USE_AP_MODE 1

static const char *AP_SSID = "DriveSense-Car";
static const char *AP_PASS = "drivesense123";   // must be >= 8 characters

static const char *STA_SSID = "YOUR_WIFI_NAME";
static const char *STA_PASS = "YOUR_WIFI_PASSWORD";

static const uint16_t TCP_PORT = 5005;

/* ---------------------------------------------------------------------------
   2. L298N WIRING  (all pins below can output PWM)
   --------------------------------------------------------------------------- */

static const int ENA = 25, IN1 = 26, IN2 = 27;   // left  side
static const int ENB = 33, IN3 = 32, IN4 = 13;   // right side

/* If a side spins the wrong way, flip its flag instead of rewiring. */
static const bool INVERT_LEFT  = false;
static const bool INVERT_RIGHT = false;

/* If turning feels mirrored, flip this instead of rewiring. */
static const bool INVERT_STEER = false;

/* Onboard blue LED - blinks fast while no laptop is connected, solid when
   the laptop is driving the car. */
static const int STATUS_LED = 2;

/* ---------------------------------------------------------------------------
   3. TUNING
   --------------------------------------------------------------------------- */

/* Top speed cap, 0-255. Start LOW (150) while testing on the floor. */
static const int MAX_PWM = 210;

/* Small motors buzz but do not move below ~40/255. This floor makes the
   very first bit of throttle actually move the car. */
static const int MIN_PWM = 45;

/* How much of the throttle range steering can steal, in percent. */
static const int TURN_GAIN  = 90;

/* Steering strength when throttle and brake are both 0, so the car can
   pivot on the spot. Lower this if pivoting is too violent. */
static const int PIVOT_GAIN = 55;

/* Stop the motors if nothing arrives for this long. Must stay well above the
   laptop's frame time (a slow laptop can take ~150 ms per frame). */
static const unsigned long WATCHDOG_MS = 700;

/* ---------------------------------------------------------------------------
   Internals
   --------------------------------------------------------------------------- */

WiFiServer server(TCP_PORT);
WiFiClient client;

String rxLine;
unsigned long lastPacketMs = 0;
bool watchdogTripped = true;
bool linkUp = false;

int clampInt(int v, int lo, int hi) {
  return v < lo ? lo : (v > hi ? hi : v);
}

void stopCar() {
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);
  analogWrite(ENA, 0);
  analogWrite(ENB, 0);
}

/* speed: -255 .. +255  (sign = direction) */
void setWheel(int pwmPin, int inA, int inB, int speed, bool invert) {
  if (invert) speed = -speed;
  speed = clampInt(speed, -255, 255);

  if (speed == 0) {
    digitalWrite(inA, LOW);
    digitalWrite(inB, LOW);
    analogWrite(pwmPin, 0);
    return;
  }

  if (speed > 0) {
    digitalWrite(inA, HIGH);
    digitalWrite(inB, LOW);
  } else {
    digitalWrite(inA, LOW);
    digitalWrite(inB, HIGH);
    speed = -speed;
  }

  /* Deadband compensation: 1..255  ->  MIN_PWM..MAX_PWM */
  int pwm = map(speed, 1, 255, MIN_PWM, MAX_PWM);
  analogWrite(pwmPin, clampInt(pwm, 0, 255));
}

/* The whole car in one function.
   steer>0 = turn right  =>  left wheels faster than right wheels. */
void drive(int steer, int throttle, int brake) {
  steer    = clampInt(steer, -100, 100);
  throttle = clampInt(throttle, 0, 100);
  brake    = clampInt(brake, 0, 100);

  if (INVERT_STEER) steer = -steer;

  int base = clampInt(throttle - brake, -100, 100);   // forward/reverse

  int gain = (base == 0) ? PIVOT_GAIN : TURN_GAIN;
  int turn = (steer * gain) / 100;

  int leftPct  = clampInt(base + turn, -100, 100);
  int rightPct = clampInt(base - turn, -100, 100);

  setWheel(ENA, IN1, IN2, leftPct  * 255 / 100, INVERT_LEFT);
  setWheel(ENB, IN3, IN4, rightPct * 255 / 100, INVERT_RIGHT);
}

/* "STEER,THROTTLE,BRAKE"  ->  true if the line was valid */
bool parsePacket(const String &line, int &steer, int &throttle, int &brake) {
  if (sscanf(line.c_str(), "%d,%d,%d", &steer, &throttle, &brake) != 3) {
    return false;
  }
  if (steer < -100 || steer > 100) return false;
  if (throttle < 0 || throttle > 100) return false;
  if (brake < 0 || brake > 100) return false;
  return true;
}

void handleLine(const String &line) {
  if (line.length() == 0) return;

  if (line.equalsIgnoreCase("STOP")) {
    stopCar();
    watchdogTripped = true;
    Serial.println("< STOP");
    return;
  }
  if (line.equalsIgnoreCase("PING")) {
    client.println("PONG");
    return;
  }

  int steer, throttle, brake;
  if (!parsePacket(line, steer, throttle, brake)) {
    Serial.print("< bad packet: ");
    Serial.println(line);
    return;
  }

  drive(steer, throttle, brake);
  lastPacketMs = millis();
  watchdogTripped = false;
}

void acceptClient() {
  WiFiClient newClient = server.available();
  if (!newClient.connected()) return;

  if (client.connected()) {
    client.stop();               // only one controller at a time
  }

  client = newClient;
  client.setNoDelay(true);
  rxLine = "";
  lastPacketMs = millis();
  watchdogTripped = false;
  linkUp = true;

  Serial.print("Controller connected from ");
  Serial.println(client.remoteIP());
  client.println("DS-READY");
}

void readClient() {
  if (!linkUp) return;

  if (!client.connected()) {
    client.stop();
    linkUp = false;
    stopCar();
    watchdogTripped = true;
    Serial.println("Controller disconnected -> motors stopped");
    return;
  }

  while (client.available()) {
    char c = client.read();
    if (c == '\n') {
      handleLine(rxLine);
      rxLine = "";
    } else if (c != '\r') {
      if (rxLine.length() < 63) {
        rxLine += c;
      } else {
        rxLine = "";             // runaway line, drop it
      }
    }
  }
}

void checkWatchdog() {
  if (!watchdogTripped && millis() - lastPacketMs > WATCHDOG_MS) {
    stopCar();
    watchdogTripped = true;
    Serial.println("! watchdog -> motors stopped");
  }
}

void updateLed() {
  if (linkUp && !watchdogTripped) {
    digitalWrite(STATUS_LED, HIGH);                        // solid = live
  } else {
    digitalWrite(STATUS_LED, (int)((millis() / 150) % 2));  // fast blink = waiting
  }
}

/* --------------------------------------------------------------------------- */

void setup() {
  Serial.begin(115200);
  delay(200);

  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  pinMode(ENA, OUTPUT);
  pinMode(ENB, OUTPUT);
  pinMode(STATUS_LED, OUTPUT);

  stopCar();

  Serial.println();
  Serial.println("===============================");
  Serial.println(" DriveSense AI - ESP32 car");
  Serial.println("===============================");

#if USE_AP_MODE
  WiFi.mode(WIFI_AP);
  WiFi.softAP(AP_SSID, AP_PASS);
  delay(300);
  Serial.print("WiFi hotspot : ");
  Serial.println(AP_SSID);
  Serial.print("Password     : ");
  Serial.println(AP_PASS);
  Serial.print("Car address  : ");
  Serial.println(WiFi.softAPIP());
#else
  WiFi.mode(WIFI_STA);
  WiFi.begin(STA_SSID, STA_PASS);
  Serial.print("Joining WiFi ");
  Serial.print(STA_SSID);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(400);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("Car address  : ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("Could not join WiFi - running standalone (car will not move)");
  }
#endif

  server.begin();
  server.setNoDelay(true);
  Serial.print("TCP port     : ");
  Serial.println(TCP_PORT);
  Serial.println("Waiting for the laptop...");
}

void loop() {
  acceptClient();
  readClient();
  checkWatchdog();
  updateLed();
}
