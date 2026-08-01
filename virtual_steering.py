import cv2
import mediapipe as mp
import math

cap = cv2.VideoCapture(0)

mp_hands = mp.solutions.hands
hands = mp_hands.Hands(
    max_num_hands=2,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7
)

draw = mp.solutions.drawing_utils

while True:
    success, frame = cap.read()

    if not success:
        break

    frame = cv2.flip(frame, 1)
    h, w, _ = frame.shape

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    result = hands.process(rgb)

    points = []

    if result.multi_hand_landmarks:

        for hand in result.multi_hand_landmarks:

            draw.draw_landmarks(frame, hand, mp_hands.HAND_CONNECTIONS)

            # Palm center (landmark 9)
            cx = int(hand.landmark[9].x * w)
            cy = int(hand.landmark[9].y * h)

            points.append((cx, cy))

            cv2.circle(frame, (cx, cy), 10, (0,255,0), -1)

        if len(points) == 2:

            p1 = points[0]
            p2 = points[1]

            cv2.line(frame, p1, p2, (255,0,0), 4)

            center = (
                (p1[0]+p2[0])//2,
                (p1[1]+p2[1])//2
            )

            radius = int(math.dist(p1,p2)/2)

            cv2.circle(frame, center, radius, (0,255,255), 3)

    cv2.imshow("DriveSense AI", frame)

    if cv2.waitKey(1)==27:
        break

cap.release()
cv2.destroyAllWindows()