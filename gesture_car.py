"""
gesture_car.py - drive a real ESP32 + L298N RC car with hand gestures.

HOW TO DRIVE
------------
  * Hold both hands up like you are gripping a steering wheel.
      -> the car arms itself and starts listening to you.
  * Tilt both hands left / right   -> steering.
  * Raise both hands               -> throttle (forward), up to --max-speed.
  * Lower both hands               -> brake / reverse.
  * Hands level and neutral height -> car coasts to a stop.
  * Drop your hands                -> car stops immediately.

  C     recalibrate the neutral height (do this in your normal sitting pose)
  SPACE emergency stop (disarms; show both hands again to re-arm)
  ESC   quit

USAGE
-----
  python gesture_car.py                          # ESP32 in AP mode (default)
  python gesture_car.py --host 192.168.1.42      # ESP32 in STA mode
  python gesture_car.py --preview                # no car, just the on-screen UI
  python gesture_car.py --max-speed 40           # gentle first test
"""

import argparse
import math
import os
import sys

import cv2
import mediapipe as mp
import numpy as np

from car_link import CarLink, DEFAULT_HOST, DEFAULT_PORT

# ============================================================================
#  CONFIG
# ============================================================================

WHEEL_PATH = "assets/steering_clean.png"
WHEEL_Y_OFFSET = 60          # push the wheel a bit below screen centre

MAX_STEER_ANGLE = 45.0       # hand tilt (degrees) that means "full lock"
STEER_DEADZONE = 3.5         # degrees of wobble ignored around centre

THROTTLE_BRAKE_RANGE = 130   # pixels of hand raise/lower for 100% throttle/brake
NEUTRAL_BAND = 12            # pixels of dead zone around the neutral line

HAND_SMOOTH = 0.65           # 0 = raw/jittery, 1 = frozen. 0.6-0.75 feels good
VALUE_SMOOTH = 0.30          # how fast throttle/brake follow your hands

# Anything below 6% is snapped to 0. The ESP32 boosts tiny PWM values so the
# motors can actually turn, so a leftover 2% would make the car creep.
MIN_COMMAND = 0.06

MAX_LOST_FRAMES = 3          # frames of "no hands" tolerated before hard stop

CM_PER_PIXEL = 0.045         # rough only, used for the readout


# ============================================================================
#  MEDIAPIPE
# ============================================================================

mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

LANDMARK_STYLE = mp_drawing.DrawingSpec(color=(0, 0, 255), thickness=2, circle_radius=3)
CONNECTION_STYLE = mp_drawing.DrawingSpec(color=(255, 255, 255), thickness=1)


# ============================================================================
#  IMAGE HELPERS
# ============================================================================

def load_wheel(path):
    """Returns a BGRA steering-wheel image, or None if the asset is missing."""
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    if img.shape[2] == 3:
        b, g, r = cv2.split(img)
        a = np.full(b.shape, 255, dtype=b.dtype)
        img = cv2.merge((b, g, r, a))
    return cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)


def rotate_image(img, angle):
    h, w = img.shape[:2]
    matrix = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1)
    return cv2.warpAffine(
        img, matrix, (w, h),
        flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
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

    crop = overlay[oy1:oy2, ox1:ox2]
    alpha = crop[:, :, 3:4] / 255.0

    background[y1:y2, x1:x2, :3] = (
        alpha * crop[:, :, :3] + (1 - alpha) * background[y1:y2, x1:x2, :3]
    ).astype(background.dtype)
    return background


def draw_fallback_wheel(frame, center, size, angle):
    """Used only when assets/steering_clean.png is missing."""
    cv2.circle(frame, center, size // 2, (200, 200, 200), 10, cv2.LINE_AA)
    rad = math.radians(-angle)
    for spoke in (0, 120, 240):
        a = rad + math.radians(spoke)
        end = (
            int(center[0] + math.cos(a) * size * 0.45),
            int(center[1] + math.sin(a) * size * 0.45),
        )
        cv2.line(frame, center, end, (200, 200, 200), 8, cv2.LINE_AA)


def draw_panel(frame, x, y, w, h, alpha=0.55, color=(40, 40, 40)):
    overlay = frame.copy()
    cv2.rectangle(overlay, (x, y), (x + w, y + h), color, -1)
    cv2.rectangle(overlay, (x, y), (x + w, y + h), (90, 90, 90), 1)
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
    return frame


def draw_status_dot(frame, x, y, ok=True):
    color = (0, 210, 0) if ok else (0, 0, 220)
    cv2.circle(frame, (x, y), 4, color, -1, cv2.LINE_AA)


def draw_bar(frame, x, y, w, h, value, color):
    """Vertical fill bar, value 0..1, fills bottom-up."""
    cv2.rectangle(frame, (x, y), (x + w, y + h), (70, 70, 70), 1)
    fill_h = int(h * max(0.0, min(1.0, value)))
    if fill_h > 0:
        cv2.rectangle(frame, (x, y + h - fill_h), (x + w, y + h), color, -1)


def draw_steer_bar(frame, x, y, w, h, steer_pct, color):
    """Horizontal bar with a marker at -100 (left) .. +100 (right)."""
    cv2.rectangle(frame, (x, y), (x + w, y + h), (70, 70, 70), 1)
    cv2.line(frame, (x + w // 2, y), (x + w // 2, y + h), (110, 110, 110), 1)
    mx = int(x + w / 2 + (steer_pct / 100.0) * (w / 2 - 6))
    cv2.rectangle(frame, (mx - 5, y + 1), (mx + 5, y + h - 1), color, -1)
    cv2.putText(frame, "L", (x - 14, y + h - 2), cv2.FONT_HERSHEY_SIMPLEX,
                0.4, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(frame, "R", (x + w + 4, y + h - 2), cv2.FONT_HERSHEY_SIMPLEX,
                0.4, (200, 200, 200), 1, cv2.LINE_AA)


def steer_percent(angle_deg):
    """Smoothed hand tilt (degrees) -> -100..+100 steering command."""
    magnitude = abs(angle_deg)
    if magnitude < STEER_DEADZONE:
        return 0
    usable = MAX_STEER_ANGLE - STEER_DEADZONE
    value = (magnitude - STEER_DEADZONE) / usable * 100.0
    value = min(100.0, value)
    return int(value if angle_deg > 0 else -value)


def speed_targets(offset, span, max_speed_pct):
    """Hand-height offset (px, +up) -> (throttle 0..1, brake 0..1)."""
    if abs(offset) < NEUTRAL_BAND:
        return 0.0, 0.0
    scale = max(5, min(100, max_speed_pct)) / 100.0
    if offset > 0:
        return min(1.0, offset / span) * scale, 0.0
    return 0.0, min(1.0, -offset / span) * scale


# ============================================================================
#  ARGUMENTS
# ============================================================================

def parse_args():
    ap = argparse.ArgumentParser(description="Gesture-controlled ESP32 RC car")
    ap.add_argument("--host", default=DEFAULT_HOST,
                    help="ESP32 IP (192.168.4.1 in AP mode; check the Serial "
                         "Monitor in STA mode)")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--camera", type=int, default=0, help="webcam index")
    ap.add_argument("--preview", action="store_true",
                    help="do not talk to the car, just show the UI")
    ap.add_argument("--max-speed", type=int, default=70,
                    help="cap throttle at this percent (default 70)")
    return ap.parse_args()


# ============================================================================
#  MAIN
# ============================================================================

def main():
    args = parse_args()
    max_speed = max(5, min(100, args.max_speed))

    wheel_img = load_wheel(WHEEL_PATH)
    if wheel_img is None:
        print("Wheel image not found at '%s' - drawing a plain wheel instead."
              % os.path.abspath(WHEEL_PATH))

    link = None
    if args.preview:
        print("[mode] PREVIEW - nothing is sent to the car")
    else:
        link = CarLink(args.host, args.port)
        link.start()
        print("[mode] CAR  - target %s:%d (Ctrl+C / ESC to quit)"
              % (args.host, args.port))

    hands = mp_hands.Hands(
        max_num_hands=2,
        min_detection_confidence=0.6,
        min_tracking_confidence=0.6,
    )

    cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW if os.name == "nt" else 0)
    if not cap.isOpened():
        cap.release()
        cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print("Could not open webcam index %d." % args.camera)
        return 1

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    # ---- state ----
    previous_angle = 0.0
    previous_size = None
    neutral_y = None
    smooth_left = smooth_right = None
    throttle = 0.0
    brake = 0.0
    steer_pct = 0
    hands_detected = 0
    hand_distance_cm = 0.0
    lost_frames = 0
    armed = False
    require_regrip = False      # after an emergency stop, drop your hands first

    def emergency():
        nonlocal throttle, brake, steer_pct, armed, require_regrip
        throttle = brake = 0.0
        steer_pct = 0
        armed = False
        require_regrip = True
        if link is not None:
            link.send(0, 0, 0)
        print("[safe] emergency stop - release your hands to re-arm")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Frame grab failed - stopping.")
                break

            frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]

            result = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

            hands_detected = len(result.multi_hand_landmarks or [])
            for lms in (result.multi_hand_landmarks or []):
                mp_drawing.draw_landmarks(
                    frame, lms, mp_hands.HAND_CONNECTIONS,
                    LANDMARK_STYLE, CONNECTION_STYLE,
                )

            tracking = False

            if hands_detected < 2:
                require_regrip = False      # hands released -> re-arming allowed

            if hands_detected == 2:
                points = []
                for lms in result.multi_hand_landmarks:
                    lm = lms.landmark
                    gx = (lm[5].x + lm[17].x) / 2      # index base .. pinky base
                    gy = (lm[5].y + lm[17].y) / 2
                    points.append((gx * w, gy * h))

                points.sort(key=lambda p: p[0])
                raw_left, raw_right = points[0], points[1]

                if smooth_left is None:
                    smooth_left, smooth_right = raw_left, raw_right
                else:
                    smooth_left = (
                        HAND_SMOOTH * smooth_left[0] + (1 - HAND_SMOOTH) * raw_left[0],
                        HAND_SMOOTH * smooth_left[1] + (1 - HAND_SMOOTH) * raw_left[1],
                    )
                    smooth_right = (
                        HAND_SMOOTH * smooth_right[0] + (1 - HAND_SMOOTH) * raw_right[0],
                        HAND_SMOOTH * smooth_right[1] + (1 - HAND_SMOOTH) * raw_right[1],
                    )

                lost_frames = 0
                tracking = True
                if not require_regrip:
                    armed = True

            elif smooth_left is not None and lost_frames < MAX_LOST_FRAMES:
                lost_frames += 1
                tracking = True

            if tracking:
                x1, y1 = smooth_left
                x2, y2 = smooth_right

                center = (w // 2, h // 2 + WHEEL_Y_OFFSET)

                # ---------------- wheel size ----------------
                distance = math.hypot(x2 - x1, y2 - y1)
                hand_distance_cm = distance * CM_PER_PIXEL

                target_size = int(max(220, min(distance * 1.35, 430)))
                if previous_size is None:
                    previous_size = target_size
                size = int(0.8 * previous_size + 0.2 * target_size)
                previous_size = size

                # ---------------- steering ----------------
                angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
                diff = angle - previous_angle
                if diff > 180:
                    angle -= 360
                elif diff < -180:
                    angle += 360
                previous_angle = 0.78 * previous_angle + 0.22 * angle
                steer_pct = steer_percent(previous_angle)

                # ---------------- wheel drawing ----------------
                if wheel_img is not None:
                    wheel = cv2.resize(wheel_img, (size, size),
                                       interpolation=cv2.INTER_LANCZOS4)
                    wheel = rotate_image(wheel, -previous_angle)
                    frame = overlay_image(
                        frame, wheel, center[0] - size // 2, center[1] - size // 2)
                else:
                    draw_fallback_wheel(frame, center, size, previous_angle)

                # ---------------- throttle / brake ----------------
                avg_y = (y1 + y2) / 2
                if neutral_y is None:
                    neutral_y = avg_y          # auto-calibrate on first grip

                offset = neutral_y - avg_y     # positive = hands raised
                target_throttle, target_brake = speed_targets(
                    offset, THROTTLE_BRAKE_RANGE, max_speed)

                throttle += (target_throttle - throttle) * VALUE_SMOOTH
                brake += (target_brake - brake) * VALUE_SMOOTH

                cv2.line(frame, (0, int(neutral_y)), (w, int(neutral_y)),
                         (100, 100, 100), 1)

            else:
                # Hands gone: ramp everything to zero fast. A real car must not
                # keep rolling because the camera lost track of a hand.
                throttle *= 0.5
                brake *= 0.5
                steer_pct = int(steer_pct * 0.5)
                smooth_left = smooth_right = None
                previous_size = None
                if abs(steer_pct) <= 2:
                    steer_pct = 0

            if not armed:
                throttle = brake = 0.0
                steer_pct = 0

            if throttle < MIN_COMMAND:
                throttle = 0.0
            if brake < MIN_COMMAND:
                brake = 0.0

            if link is not None:
                link.send(steer_pct, throttle * 100.0, brake * 100.0)

            # ================================================================
            #  HUD
            # ================================================================
            frame = draw_panel(frame, 0, 0, w, 30, alpha=0.6, color=(20, 20, 20))
            cv2.putText(frame, "DriveSense AI  |  Gesture RC Car", (12, 21),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)

            # left: numbers
            frame = draw_panel(frame, 15, 40, 185, 118)
            cv2.putText(frame, "Steering", (28, 63), cv2.FONT_HERSHEY_SIMPLEX,
                        0.45, (200, 200, 200), 1, cv2.LINE_AA)
            cv2.putText(frame, "%+d %%" % steer_pct, (28, 95),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 230, 0), 2, cv2.LINE_AA)
            cv2.putText(frame, "Hand distance", (28, 118), cv2.FONT_HERSHEY_SIMPLEX,
                        0.42, (200, 200, 200), 1, cv2.LINE_AA)
            cv2.putText(frame, "%.1f cm" % hand_distance_cm, (28, 142),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 255), 2, cv2.LINE_AA)

            # right: link + arming status
            status_w = 195
            frame = draw_panel(frame, w - status_w - 15, 40, status_w, 92)
            sx = w - status_w
            cv2.putText(frame, "Status", (sx, 60), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (255, 255, 255), 1, cv2.LINE_AA)

            if link is None:
                link_ok, link_text = True, "Preview mode"
            elif link.connected:
                link_ok, link_text = True, "Car: linked"
            else:
                link_ok, link_text = False, "Car: " + link.status

            draw_status_dot(frame, sx + 4, 75, ok=link_ok)
            cv2.putText(frame, link_text, (sx + 14, 79), cv2.FONT_HERSHEY_SIMPLEX,
                        0.40, (220, 220, 220), 1, cv2.LINE_AA)

            draw_status_dot(frame, sx + 4, 94, ok=armed)
            cv2.putText(frame, "Armed" if armed else "Disarmed", (sx + 14, 98),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.40, (220, 220, 220), 1, cv2.LINE_AA)

            draw_status_dot(frame, sx + 4, 113, ok=(hands_detected == 2))
            cv2.putText(frame, "Hands: %d/2" % hands_detected, (sx + 14, 117),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.40, (220, 220, 220), 1, cv2.LINE_AA)

            # throttle / brake bars
            bar_h = 140
            bar_y = 150
            draw_bar(frame, w - 70, bar_y, 22, bar_h, throttle, (0, 200, 0))
            draw_bar(frame, w - 40, bar_y, 22, bar_h, brake, (0, 0, 220))
            cv2.putText(frame, "GAS", (w - 72, bar_y + bar_h + 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 200, 0), 1, cv2.LINE_AA)
            cv2.putText(frame, "BRK", (w - 44, bar_y + bar_h + 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 220), 1, cv2.LINE_AA)

            # steering bar
            draw_steer_bar(frame, w - 260, h - 34, 200, 14, steer_pct, (0, 220, 255))

            # controls panel
            ctrl_h = 118
            frame = draw_panel(frame, 15, h - ctrl_h - 15, 260, ctrl_h)
            cy = h - ctrl_h
            cv2.putText(frame, "Controls", (28, cy + 20), cv2.FONT_HERSHEY_SIMPLEX,
                        0.45, (255, 255, 255), 1, cv2.LINE_AA)
            lines = (
                "- Tilt hands to steer",
                "- Raise hands = forward",
                "- Lower hands = brake/reverse",
                "- C: neutral   SPACE: stop",
                "- ESC: quit",
            )
            for i, text in enumerate(lines):
                color = (0, 220, 0) if i >= 3 else (200, 200, 200)
                cv2.putText(frame, text, (28, cy + 40 + i * 16),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1, cv2.LINE_AA)

            if require_regrip:
                cv2.putText(frame, "Emergency stop - release your hands, then grip again",
                            (w // 2 - 250, h - 150), cv2.FONT_HERSHEY_SIMPLEX,
                            0.55, (0, 0, 220), 2, cv2.LINE_AA)
            elif not armed:
                cv2.putText(frame, "Show both hands to grip the wheel",
                            (w // 2 - 180, h - 150), cv2.FONT_HERSHEY_SIMPLEX,
                            0.6, (0, 165, 255), 2, cv2.LINE_AA)
            elif hands_detected < 2:
                cv2.putText(frame, "TRACKING LOST - car stopped",
                            (w // 2 - 150, h - 150), cv2.FONT_HERSHEY_SIMPLEX,
                            0.55, (0, 0, 220), 2, cv2.LINE_AA)

            cv2.imshow("DriveSense AI - RC Car", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == 27:                       # ESC
                break
            elif key == ord("c"):
                neutral_y = None                # recalibrate next grip
            elif key == 32:                     # SPACE = emergency stop
                emergency()

    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        if link is not None:
            link.send(0, 0, 0)
            link.stop()
        cap.release()
        cv2.destroyAllWindows()
        hands.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
