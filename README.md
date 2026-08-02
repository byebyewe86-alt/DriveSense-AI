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
├── virtual_steering.py        # Main virtual steering application
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

Create environment:

```bash
python -m venv .venv
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
pip install opencv-python mediapipe numpy
```

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

```
opencv-python
mediapipe==0.10.21
numpy==1.26.4
```

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
