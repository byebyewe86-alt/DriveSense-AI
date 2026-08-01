import cv2
import mediapipe as mp
import numpy as np
import math
import os


# =========================================================
#  CONFIG
# =========================================================

WHEEL_PATH = "assets/steering_clean.png"
WHEEL_Y_OFFSET = 60          # shift wheel center down/up on screen
CM_PER_PIXEL = 0.045         # rough calibration for the "Hand Distance" readout

THROTTLE_BRAKE_RANGE = 140   # pixels of hand-raise/lower needed to reach 100% throttle/brake
MAX_STEER_ANGLE = 90         # degrees of hand-tilt that maps to full-lock steering

# Set this to True once vJoy + pyvjoy are installed to actually drive a real game.
USE_VJOY = False


# =========================================================
#  MEDIAPIPE
# =========================================================

mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

hands = mp_hands.Hands(
    max_num_hands=2,
    min_detection_confidence=0.6,
    min_tracking_confidence=0.6
)

LANDMARK_STYLE = mp_drawing.DrawingSpec(color=(0, 0, 255), thickness=2, circle_radius=3)
CONNECTION_STYLE = mp_drawing.DrawingSpec(color=(255, 255, 255), thickness=1)


# =========================================================
#  LOAD WHEEL IMAGE
# =========================================================

wheel_img = cv2.imread(WHEEL_PATH, cv2.IMREAD_UNCHANGED)

if wheel_img is None:
    print(f"Wheel image not found at '{os.path.abspath(WHEEL_PATH)}'")
    print("Make sure the 'assets' folder sits next to this script.")
    exit()

if wheel_img.shape[2] == 3:
    b, g, r = cv2.split(wheel_img)
    a = np.full(b.shape, 255, dtype=b.dtype)
    wheel_img = cv2.merge((b, g, r, a))

wheel_img = cv2.resize(wheel_img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
print("Wheel loaded:", wheel_img.shape)


# =========================================================
#  OPTIONAL: vJoy hookup (real game control)
# =========================================================

vjoy_device = None
if USE_VJOY:
    try:
        import pyvjoy
        vjoy_device = pyvjoy.VJoyDevice(1)
        print("vJoy device connected.")
    except Exception as e:
        print("Could not connect to vJoy:", e)
        print("Install the vJoy driver + 'pip install pyvjoy', enable device #1.")
        USE_VJOY = False


def send_controls(steer_angle, throttle, brake):
    """
    steer_angle : degrees, -MAX_STEER_ANGLE..+MAX_STEER_ANGLE
    throttle    : 0..1
    brake       : 0..1
    Pushes these onto vJoy's X (steering), Y (throttle) and Z (brake) axes.
    In your game's control-binding menu, bind:
        Steering -> vJoy X axis
        Throttle -> vJoy Y axis
        Brake    -> vJoy Z axis
    """
    if vjoy_device is None:
        return

    clamped = max(-MAX_STEER_ANGLE, min(MAX_STEER_ANGLE, steer_angle))
    steer_norm = (clamped + MAX_STEER_ANGLE) / (2 * MAX_STEER_ANGLE)  # 0..1

    vjoy_device.set_axis(pyvjoy.HID_USAGE_X, int(steer_norm * 32768))
    vjoy_device.set_axis(pyvjoy.HID_USAGE_Y, int(max(0, min(1, throttle)) * 32768))
    vjoy_device.set_axis(pyvjoy.HID_USAGE_Z, int(max(0, min(1, brake)) * 32768))


# =========================================================
#  IMAGE HELPERS
# =========================================================

def rotate_image(img, angle):
    h, w = img.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1)
    return cv2.warpAffine(
        img, matrix, (w, h),
        flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0)
    )


def overlay_image(background, overlay, x, y):
    bh, bw = background.shape[:2]
    oh, ow = overlay.shape[:2]

    x1, y1 = max(x, 0), max(y, 0)
    x2, y2 = min(x + ow, bw), min(y + oh, bh)

    if x1 >= x2 or y1 >= y2:
        return background

    ox1, oy1 = x1 - x, y1 - y
    ox2, oy2 = ox1 + (x2 - x1), oy1 + (y2 - y1)

    overlay_crop = overlay[oy1:oy2, ox1:ox2]
    alpha = overlay_crop[:, :, 3] / 255.0

    for c in range(3):
        background[y1:y2, x1:x2, c] = (
            alpha * overlay_crop[:, :, c]
            + (1 - alpha) * background[y1:y2, x1:x2, c]
        )

    return background


def draw_panel(frame, x, y, w, h, alpha=0.55, color=(40, 40, 40)):
    overlay = frame.copy()
    cv2.rectangle(overlay, (x, y), (x + w, y + h), color, -1)
    cv2.rectangle(overlay, (x, y), (x + w, y + h), (90, 90, 90), 1)
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
    return frame


def draw_status_dot(frame, x, y, ok=True):
    color = (0, 220, 0) if ok else (0, 0, 220)
    cv2.circle(frame, (x, y), 4, color, -1, cv2.LINE_AA)


def draw_bar(frame, x, y, w, h, value, color):
    """Vertical fill bar, value 0..1, fills bottom-up."""
    cv2.rectangle(frame, (x, y), (x + w, y + h), (70, 70, 70), 1)
    fill_h = int(h * max(0, min(1, value)))
    cv2.rectangle(frame, (x, y + h - fill_h), (x + w, y + h), color, -1)


# =========================================================
#  CAMERA LOOP
# =========================================================

previous_angle = 0.0
previous_size = None
neutral_y = None          # calibrated resting hand height for throttle/brake
throttle_smooth = 0.0
brake_smooth = 0.0

cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("Could not open webcam (index 0). Check camera permissions / index.")
    exit()

while True:

    success, frame = cap.read()
    if not success:
        print("Frame grab failed, stopping.")
        break

    frame = cv2.flip(frame, 1)
    h, w, _ = frame.shape

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    result = hands.process(rgb)

    hands_detected = 0
    hand_distance_cm = 0.0
    steering_angle_display = int(previous_angle)

    if result.multi_hand_landmarks:
        hands_detected = len(result.multi_hand_landmarks)
        for hand_lms in result.multi_hand_landmarks:
            mp_drawing.draw_landmarks(
                frame, hand_lms, mp_hands.HAND_CONNECTIONS,
                LANDMARK_STYLE, CONNECTION_STYLE
            )

    if result.multi_hand_landmarks and hands_detected == 2:

        hand_points = []
        for hand_lms in result.multi_hand_landmarks:
            lm = hand_lms.landmark
            gx = (lm[5].x + lm[17].x) / 2
            gy = (lm[5].y + lm[17].y) / 2
            hand_points.append((int(gx * w), int(gy * h)))

        hand_points.sort(key=lambda p: p[0])
        x1, y1 = hand_points[0]
        x2, y2 = hand_points[1]

        # ---------------- CENTER (fixed) ----------------
        center_x = w // 2
        center_y = h // 2 + WHEEL_Y_OFFSET

        # ---------------- SIZE ----------------
        distance = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        hand_distance_cm = distance * CM_PER_PIXEL

        target_size = int(distance * 1.35)
        target_size = max(220, min(target_size, 430))

        if previous_size is None:
            previous_size = target_size
        size = int(0.8 * previous_size + 0.2 * target_size)
        previous_size = size

        wheel = cv2.resize(wheel_img, (size, size), interpolation=cv2.INTER_LANCZOS4)

        # ---------------- ROTATION ----------------
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
        diff = angle - previous_angle
        if diff > 180:
            angle -= 360
        elif diff < -180:
            angle += 360
        previous_angle = 0.85 * previous_angle + 0.15 * angle
        steering_angle_display = int(previous_angle)

        wheel = rotate_image(wheel, -previous_angle)

        x = center_x - size // 2
        y = center_y - size // 2
        frame = overlay_image(frame, wheel, x, y)

        # ---------------- THROTTLE / BRAKE ----------------
        avg_y = (y1 + y2) / 2

        if neutral_y is None:
            neutral_y = avg_y   # auto-calibrate on first detection

        offset = neutral_y - avg_y   # positive = hands raised, negative = hands lowered

        target_throttle = max(0.0, min(1.0, offset / THROTTLE_BRAKE_RANGE)) if offset > 0 else 0.0
        target_brake = max(0.0, min(1.0, -offset / THROTTLE_BRAKE_RANGE)) if offset < 0 else 0.0

        throttle_smooth = 0.7 * throttle_smooth + 0.3 * target_throttle
        brake_smooth = 0.7 * brake_smooth + 0.3 * target_brake

        if USE_VJOY:
            send_controls(previous_angle, throttle_smooth, brake_smooth)

        # neutral-line guide for feedback
        cv2.line(frame, (0, int(neutral_y)), (w, int(neutral_y)), (100, 100, 100), 1)

    else:
        throttle_smooth *= 0.85
        brake_smooth *= 0.85

    # =====================================================
    #  DASHBOARD UI
    # =====================================================

    frame = draw_panel(frame, 0, 0, w, 30, alpha=0.6, color=(20, 20, 20))
    cv2.putText(frame, "DriveSense AI", (12, 21),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)

    # --- top-left: steering angle / hand distance ---
    frame = draw_panel(frame, 15, 40, 175, 110)
    cv2.putText(frame, "Steering Angle", (28, 65),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(frame, f"{steering_angle_display}", (28, 100),
                cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 230, 0), 2, cv2.LINE_AA)
    cv2.putText(frame, "Hand Distance", (28, 122),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(frame, f"{hand_distance_cm:.1f} cm", (28, 142),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 255), 2, cv2.LINE_AA)

    # --- top-right: status panel ---
    status_w = 175
    frame = draw_panel(frame, w - status_w - 15, 40, status_w, 90)
    sx = w - status_w
    cv2.putText(frame, "Status", (sx, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    draw_status_dot(frame, sx + 4, 75, ok=(hands_detected == 2))
    cv2.putText(frame, f"Hands Detected: {hands_detected}", (sx + 14, 79),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (220, 220, 220), 1, cv2.LINE_AA)
    draw_status_dot(frame, sx + 4, 92, ok=(hands_detected == 2))
    cv2.putText(frame, f"Tracking: {'OK' if hands_detected == 2 else 'WAIT'}", (sx + 14, 96),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (220, 220, 220), 1, cv2.LINE_AA)
    draw_status_dot(frame, sx + 4, 109, ok=USE_VJOY)
    cv2.putText(frame, f"Mode: {'Game' if USE_VJOY else 'Preview'}", (sx + 14, 113),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (220, 220, 220), 1, cv2.LINE_AA)

    # --- right-middle: throttle / brake bars ---
    bar_h = 140
    bar_y = 150
    draw_bar(frame, w - 70, bar_y, 22, bar_h, throttle_smooth, (0, 200, 0))
    draw_bar(frame, w - 40, bar_y, 22, bar_h, brake_smooth, (0, 0, 220))
    cv2.putText(frame, "GAS", (w - 72, bar_y + bar_h + 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 200, 0), 1, cv2.LINE_AA)
    cv2.putText(frame, "BRK", (w - 44, bar_y + bar_h + 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 220), 1, cv2.LINE_AA)

    # --- bottom-left: controls panel ---
    ctrl_h = 110
    frame = draw_panel(frame, 15, h - ctrl_h - 15, 250, ctrl_h)
    cy = h - ctrl_h
    cv2.putText(frame, "Controls", (28, cy + 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(frame, "- Tilt hands to steer", (28, cy + 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(frame, "- Raise hands to accelerate", (28, cy + 58),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(frame, "- Lower hands to brake", (28, cy + 76),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(frame, "- C: recalibrate neutral   ESC: quit", (28, cy + 94),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 220, 0), 1, cv2.LINE_AA)

    if hands_detected < 2:
        cv2.putText(frame, "Show both hands to grip the wheel",
                    (w // 2 - 190, h - 25), cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, (0, 165, 255), 2, cv2.LINE_AA)

    cv2.imshow("DriveSense AI", frame)

    key = cv2.waitKey(1) & 0xFF
    if key == 27:  # ESC
        break
    elif key == ord('c'):
        # will re-calibrate neutral_y next time both hands are seen
        neutral_y = None

cap.release()
cv2.destroyAllWindows()