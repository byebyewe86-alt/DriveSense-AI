# 🚗 DriveSense AI - Virtual Steering Wheel

A computer vision-based **AI virtual steering system** that converts real-time hand movements into a virtual steering wheel controller using a webcam.

The project uses **MediaPipe Hand Tracking** and **OpenCV** to detect hand positions, calculate steering movement, and render a realistic virtual steering wheel between the user's hands.

---

# ✨ Features

- 🖐️ Real-time hand tracking using MediaPipe
- 🚗 Virtual steering wheel controlled by hand gestures
- 🔄 Realistic steering wheel rotation
- 📏 Dynamic wheel scaling based on hand distance
- 🎯 Smooth movement stabilization
- 🎥 Webcam-based real-time processing
- 🧠 Computer vision powered interaction
- 🎮 Contactless driving simulation

---

# 🛠️ Technologies Used

| Technology | Purpose |
|------------|---------|
| Python | Core programming language |
| OpenCV | Webcam processing and image manipulation |
| MediaPipe | Hand landmark detection |
| NumPy | Mathematical calculations |
| Computer Vision | Gesture-based control |

---

# 📂 Project Structure

```
DriveSense-AI/
│
├── virtual_steering.py        # Virtual steering wheel (simulation / vJoy)
├── drive.py                   # Steering + throttle/brake dashboard
├── gesture_car.py             # ⭐ Gestures -> real ESP32 RC car
├── car_link.py                # WiFi link to the ESP32 (background thread)
├── test_car.py                # Test the car with the keyboard, no camera
│
├── esp32/
│   ├── drivesense_car/
│   │   └── drivesense_car.ino # ESP32 firmware (Arduino IDE)
│   └── README.md              # Wiring + power notes
│
├── test.py                    # Environment testing script
│
├── assets/
│   └── steering_clean.png      # Transparent steering wheel image
│
├── requirements.txt           # Python dependencies
│
├── .gitignore                 # Ignored files
│
└── README.md                  # Project documentation
```

---

# ⚙️ Installation

## 1. Clone Repository

```bash
git clone https://github.com/yourusername/DriveSense-AI.git
```

Move into project directory:

```bash
cd DriveSense-AI
```

---

## 2. Create Virtual Environment

> **Use Python 3.10 – 3.12 (3.11 recommended).**
> MediaPipe has no wheels for Python 3.13/3.14, so the dependencies
> will not install there.

Create environment (using the Python 3.11 launcher):

```bash
py -3.11 -m venv .venv
```

Activate environment:

### Windows

```bash
.venv\Scripts\activate
```

---

## 3. Install Dependencies

Install required libraries:

```bash
pip install -r requirements.txt
```

or manually:

```bash
pip install mediapipe==0.10.21 numpy==1.26.4 opencv-contrib-python==4.11.0.86 protobuf==4.25.9
```

`pyvjoy==1.0.1` is optional — install it only if you want to control a
real game through vJoy.

---

# ▶️ Running the Project

Activate virtual environment:

```bash
.venv\Scripts\activate
```

Run the application:

```bash
python virtual_steering.py
```

Press:

```
ESC
```

to close the application.

---

# 🚙 Driving a Real RC Car (ESP32 + L298N)

Yes — **speed is gesture-controlled**. Your hand height is the accelerator and
brake pedal, and the tilt of your hands is the steering wheel. Nothing extra is
needed on the laptop beyond what is already installed (`socket` is built in).

## How the signal travels

```
 webcam  ->  MediaPipe hands  ->  gesture_car.py  ->  WiFi TCP  ->  ESP32
                                                      (30x per second)   |
                                                                         v
                                                                   L298N -> 4 motors
```

* The laptop works out `steer, throttle, brake` once per video frame and sends
  one short line over TCP: `-32,74,0`
* The ESP32 mixes that into a left-wheel speed and a right-wheel speed
  (skid steering) and drives the two L298N channels with PWM.
* If the laptop stops sending for 0.7 s, or the WiFi drops, the ESP32 stops the
  motors by itself. The car cannot run away.

## 1. Wire the car

| L298N | ESP32 / battery |
|---|---|
| `ENA` | GPIO 25 — left speed (PWM) |
| `IN1`, `IN2` | GPIO 26, GPIO 27 — left direction |
| `ENB` | GPIO 33 — right speed (PWM) |
| `IN3`, `IN4` | GPIO 32, GPIO 13 — right direction |
| `OUT1`/`OUT2` | the two **left** motors (in parallel) |
| `OUT3`/`OUT4` | the two **right** motors (in parallel) |
| `+12V` / `GND` | battery + / battery − |
| ESP32 `GND` | **must also go to L298N `GND`** |

**Remove the two jumper caps on ENA and ENB** — otherwise the ESP32's PWM does
nothing. Full notes, power advice and the "my car spins the wrong way" fixes
are in [`esp32/README.md`](esp32/README.md).

## 2. Flash the ESP32

Open `esp32/drivesense_car/drivesense_car.ino` in the Arduino IDE
(Board: **ESP32 Dev Module**), upload, then open the Serial Monitor at
**115200 baud**. You should see:

```
WiFi hotspot : DriveSense-Car
Password     : drivesense123
Car address  : 192.168.4.1
TCP port     : 5005
```

## 3. Connect the laptop

Join the **`DriveSense-Car`** WiFi on the laptop (password `drivesense123`).
There is no internet on that network — that is normal. If you would rather keep
your normal WiFi, set `USE_AP_MODE 0` in the sketch, fill in your router details,
and pass the ESP32's IP with `--host`.

## 4. Test the hardware first (no camera)

```bash
python test_car.py            # keys: W/S = speed, A/D = steer, SPACE = stop
python test_car.py --demo     # automatic forward / turn / reverse / stop
```

Put the car **on blocks** for this. If the wheels turn the wrong way or the car
turns backwards, flip `INVERT_LEFT` / `INVERT_RIGHT` / `INVERT_STEER` in the
sketch — no rewiring needed.

## 5. Drive with gestures

```bash
python gesture_car.py                 # ESP32 hotspot mode (default)
python gesture_car.py --host 192.168.1.42   # if the ESP32 is on your router
python gesture_car.py --preview       # no car, just look at the UI
python gesture_car.py --max-speed 40  # gentle, for the first run
```

| Gesture | Result |
|---|---|
| Hold both hands up like a wheel | arms the car |
| Tilt both hands left / right | steer left / right (differential) |
| Raise both hands | accelerate, up to `--max-speed` |
| Lower both hands | brake / reverse |
| Hands level at neutral height | coast to a stop |
| Drop your hands | car stops immediately |
| `C` | recalibrate the neutral height |
| `SPACE` | emergency stop (release hands, then grip again to re-arm) |
| `ESC` | quit |

The wheels are steered by **differential drive**: the outer wheels spin faster
than the inner ones, and at zero throttle the car can pivot on the spot. Set
`PIVOT_GAIN` to `0` in the sketch if you do not want pivoting.

## Tuning

| Where | Constant | What it does |
|---|---|---|
| sketch | `MAX_PWM` | top speed cap (start around 150) |
| sketch | `MIN_PWM` | pushes past the motors' dead zone |
| sketch | `TURN_GAIN` | how hard steering bites |
| sketch | `PIVOT_GAIN` | pivot strength at standstill |
| sketch | `WATCHDOG_MS` | auto-stop delay if the link dies |
| `gesture_car.py` | `MAX_STEER_ANGLE` | hand tilt for full lock (default 45°) |
| `gesture_car.py` | `THROTTLE_BRAKE_RANGE` | pixels of hand travel for full throttle |
| `gesture_car.py` | `HAND_SMOOTH` | higher = steadier but laggier |

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Car: no link" in the HUD | laptop is not on the `DriveSense-Car` WiFi, or wrong `--host` |
| Car connects but nothing moves | ENA/ENB jumpers still in place, or no common GND |
| One side spins backwards | flip that side's `INVERT_*` flag in the sketch |
| Wheels buzz but do not turn | raise `MIN_PWM` (or lower it if the car jumps at 1%) |
| Car stutters / stops while driving | laptop frame rate too low: raise `WATCHDOG_MS`, lower camera resolution |
| ESP32 reboots when driving | motor battery sagging: power the ESP32 separately |

---

# 🧠 How It Works

## 1. Hand Detection

MediaPipe detects hand landmarks from the webcam feed.

The system tracks stable grip points:

- Index finger base landmark
- Pinky finger base landmark

These points represent where the user holds the steering wheel.

---

## 2. Virtual Wheel Placement

The system calculates the midpoint between both hands.

This position becomes the center of the virtual steering wheel.

The distance between hands controls:

- Wheel size
- Wheel position

---

## 3. Steering Rotation

The angle between both hands determines steering direction.

Example:

```
Hands straight
      |
      🛞
      |
```

```
Hands rotated

     /
    🛞
```

The wheel rotates according to hand movement.

---

## 4. Stabilization

To create smooth driving:

- Position smoothing reduces shaking
- Rotation smoothing prevents sudden jumps
- Frame-by-frame tracking maintains stability

---

# 🎮 Controls

| User Action | Result |
|------------|--------|
| Move hands apart | Wheel increases size |
| Move hands closer | Wheel decreases size |
| Rotate hands | Steering wheel rotates |
| Move hands | Wheel follows position |

---

# 📸 Demo

The system creates a virtual driving experience:

```
        ✊                 ✊


              🛞


       Virtual Steering Control
```

The user can control the steering wheel without any physical controller.

---

# 🚀 Future Improvements

## Computer Vision Enhancements

- ✋ Hand occlusion so hands appear in front of wheel
- 🤖 Driver monitoring system
- 👁️ Eye tracking integration
- 🛣️ Lane detection

## Simulation Features

- 🚘 Vehicle simulator integration
- 🎮 Game controller support
- 🌐 Real-time dashboard interface
- 🔊 Voice-assisted driving controls

---

# 📦 Requirements

Python 3.10 – 3.12 (3.11 recommended).

```
mediapipe==0.10.21
numpy==1.26.4
opencv-contrib-python==4.11.0.86
protobuf==4.25.9
pyvjoy==1.0.1        # optional (vJoy game control)
```

> Only `opencv-contrib-python` is used — do **not** also install
> `opencv-python`, since both packages provide `cv2` and overwrite
> each other.

---

# 🔒 Git Ignore

The following files should not be uploaded:

```
.venv/
__pycache__/
*.pyc
```

Virtual environments contain large machine-specific files and should not be stored in GitHub.

---

# 🧪 Environment Test

Run:

```bash
python test.py
```

Expected output:

```
========================================
🚗 DriveSense AI - Environment Test
========================================

✅ OpenCV Version
✅ MediaPipe Version
✅ NumPy Version

✅ Camera detected successfully!

🎉 Environment is ready!
```

---

# 👩‍💻 Author

**Saanvi Patnaik**

B.Tech Computer Science Engineering  
Artificial Intelligence & Machine Learning

---

# 📜 License

This project is developed for educational purposes, computer vision experimentation, and AI-based interaction research.
