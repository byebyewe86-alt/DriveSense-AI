import cv2
import mediapipe as mp
import numpy as np
import math
import os


# ================= MEDIA PIPE =================

mp_hands = mp.solutions.hands

hands = mp_hands.Hands(
    max_num_hands=2,
    min_detection_confidence=0.6,   # lowered a bit -> hands get picked up faster/more reliably
    min_tracking_confidence=0.6
)


# ================= LOAD WHEEL =================

WHEEL_PATH = "assets/steering_clean.png"

wheel_img = cv2.imread(WHEEL_PATH, cv2.IMREAD_UNCHANGED)

if wheel_img is None:
    print(f"❌ Wheel image not found at '{os.path.abspath(WHEEL_PATH)}'")
    print("   Make sure the 'assets' folder sits next to this script.")
    exit()

# If the PNG has no alpha channel (3 channels only), the old code would
# crash the first time it tried to read overlay[:,:,3]. Give it a full
# opaque alpha channel instead so it always has 4 channels (BGRA).
if wheel_img.shape[2] == 3:
    b, g, r = cv2.split(wheel_img)
    a = np.full(b.shape, 255, dtype=b.dtype)
    wheel_img = cv2.merge((b, g, r, a))

print("✅ Wheel loaded:", wheel_img.shape)

# upscale image quality
wheel_img = cv2.resize(wheel_img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)


# ================= VARIABLES =================

previous_angle = 0.0
previous_size = None

# The wheel now stays locked to a fixed spot on screen instead of
# following your hands around — set this to wherever you want the
# wheel's center to sit (tweak WHEEL_Y_OFFSET if you want it lower/higher).
WHEEL_Y_OFFSET = 60


# ================= FUNCTIONS =================

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
    """
    Alpha-blend `overlay` onto `background` at (x, y).
    Clips instead of bailing out completely when the wheel is
    partially off-screen, which is what was making it 'disappear'.
    """
    bh, bw = background.shape[:2]
    oh, ow = overlay.shape[:2]

    # Compute the region of the overlay that is actually on-screen
    x1, y1 = max(x, 0), max(y, 0)
    x2, y2 = min(x + ow, bw), min(y + oh, bh)

    if x1 >= x2 or y1 >= y2:
        # Fully off-screen, nothing to draw
        return background

    # Corresponding region inside the overlay image
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


# ================= CAMERA =================

cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("❌ Could not open webcam (index 0). Check camera permissions / index.")
    exit()

while True:

    success, frame = cap.read()
    if not success:
        print("⚠️  Frame grab failed, stopping.")
        break

    frame = cv2.flip(frame, 1)
    h, w, _ = frame.shape

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    result = hands.process(rgb)

    if result.multi_hand_landmarks and len(result.multi_hand_landmarks) == 2:

        hand_points = []

        for hand in result.multi_hand_landmarks:
            lm = hand.landmark

            # Grip point: between index base (5) and pinky base (17)
            gx = (lm[5].x + lm[17].x) / 2
            gy = (lm[5].y + lm[17].y) / 2

            hand_points.append((int(gx * w), int(gy * h)))

        # MediaPipe does NOT guarantee hand order stays consistent frame
        # to frame — your left/right hand can swap positions in this list,
        # which flips x1,y1/x2,y2 and made the wheel rotation randomly
        # reverse. Sorting by x-position (leftmost hand first) fixes that.
        hand_points.sort(key=lambda p: p[0])

        x1, y1 = hand_points[0]
        x2, y2 = hand_points[1]

        # ---------------- CENTER (fixed, no drift) ----------------

        center_x = w // 2
        center_y = h // 2 + WHEEL_Y_OFFSET

        # ---------------- SIZE ----------------

        distance = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        target_size = int(distance * 1.35)
        target_size = max(220, min(target_size, 430))

        if previous_size is None:
            previous_size = target_size

        # smooth size too, so the wheel doesn't jump/flicker in scale
        size = int(0.8 * previous_size + 0.2 * target_size)
        previous_size = size

        wheel = cv2.resize(wheel_img, (size, size), interpolation=cv2.INTER_LANCZOS4)

        # ---------------- ROTATION ----------------

        angle = math.degrees(math.atan2(y2 - y1, x2 - x1))

        # keep the smoothed angle continuous across the +/-180 wrap
        diff = angle - previous_angle
        if diff > 180:
            angle -= 360
        elif diff < -180:
            angle += 360

        previous_angle = 0.85 * previous_angle + 0.15 * angle

        wheel = rotate_image(wheel, -previous_angle)

        # position (top-left corner for the overlay)
        x = center_x - size // 2
        y = center_y - size // 2

        frame = overlay_image(frame, wheel, x, y)

        cv2.putText(
            frame, f"Steering Angle: {int(previous_angle)}",
            (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2
        )

    else:
        cv2.putText(
            frame, "Show both hands to grip the wheel",
            (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 165, 255), 2
        )

    cv2.putText(
        frame, "DriveSense AI",
        (30, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2
    )

    cv2.imshow("DriveSense AI", frame)

    if cv2.waitKey(1) == 27:
        break

cap.release()
cv2.destroyAllWindows()