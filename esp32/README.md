# ESP32 RC car firmware

`drivesense_car/drivesense_car.ino` — Arduino sketch for the car.

## What it does

1. Creates a WiFi hotspot **`DriveSense-Car`** (password `drivesense123`).
2. Listens on **TCP port 5005**.
3. The laptop sends one line per video frame: `steer,throttle,brake`
   (e.g. `-32,74,0`).
4. The ESP32 mixes that into a left and a right wheel speed (skid steering)
   and drives the two L298N channels.
5. **Watchdog:** if no valid packet arrives for 700 ms, or the laptop
   disconnects, the motors stop. The car cannot run away.

## Wiring — 2 gear motors + one L298N

| L298N | Goes to | Notes |
|---|---|---|
| `+12V` | Battery **+** | 7.4 V – 11.1 V (2S/3S Li-ion, or 6×AA) |
| `GND` | Battery **−** | **Also** connect this to an ESP32 GND pin |
| `+5V` | — | leave alone (unless you power the ESP32 from it, see below) |
| `ENA` | **GPIO 25** | left side speed (PWM) |
| `IN1` | **GPIO 26** | left side direction |
| `IN2` | **GPIO 27** | left side direction |
| `ENB` | **GPIO 33** | right side speed (PWM) |
| `IN3` | **GPIO 32** | right side direction |
| `IN4` | **GPIO 13** | right side direction |
| `OUT1` / `OUT2` | both **left** motors | wire the two left motors in parallel |
| `OUT3` / `OUT4` | both **right** motors | wire the two right motors in parallel |

**Remove the two small jumper caps on ENA and ENB.** They tie the enable pins
permanently high, and then the ESP32's PWM signal does nothing.

### Power — read this once, it saves an ESP32

- **Motors on the L298N battery, ESP32 on its own 5 V** (USB power bank, or a
  5 V buck converter from the same battery). This is the reliable option.
- The ESP32 GND and the L298N GND **must be connected together**, otherwise
  the PWM/direction signals have no reference and the car behaves randomly.
- Do **not** feed 5 V into the ESP32's `VIN`/`5V` pin at the same time as USB.
- Cheap 4WD chassis motors draw 1–2 A each when stalled. If the ESP32 reboots
  when the car starts moving, the supply is sagging — use a separate battery
  for the ESP32 or add a big capacitor across the L298N supply.

## Uploading

1. Arduino IDE → **Boards Manager** → install *esp32* by Espressif.
2. Open `drivesense_car.ino`.
3. Tools → Board → **ESP32 Dev Module**, Port → your COM port.
4. Upload. Open **Serial Monitor at 115200 baud** — it prints the IP address,
   which should be `192.168.4.1` in AP mode.

## Before you drive

- Flip `INVERT_LEFT` / `INVERT_RIGHT` / `INVERT_STEER` in the sketch if a wheel
  spins backwards or steering feels mirrored. No rewiring needed.
- Start with `MAX_PWM = 150` for the first test run, raise it later.
- Put the car **on blocks** (wheels off the ground) for the very first test.
