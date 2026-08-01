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

    frame = cv2.flip(frame,1)

    h,w,_ = frame.shape


    rgb = cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)

    result = hands.process(rgb)


    points=[]


    if result.multi_hand_landmarks:

        for hand in result.multi_hand_landmarks:

            draw.draw_landmarks(
                frame,
                hand,
                mp_hands.HAND_CONNECTIONS
            )


            x=int(hand.landmark[9].x*w)
            y=int(hand.landmark[9].y*h)

            points.append((x,y))


    if len(points)==2:

        left = points[0]
        right = points[1]


        # calculate angle

        dx = right[0]-left[0]
        dy = right[1]-left[1]


        angle = math.degrees(
            math.atan2(dy,dx)
        )


        cv2.putText(
            frame,
            f"Steering Angle: {int(angle)}",
            (20,50),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0,255,0),
            2
        )


        if angle > 10:
            direction="RIGHT"

        elif angle < -10:
            direction="LEFT"

        else:
            direction="STRAIGHT"


        cv2.putText(
            frame,
            direction,
            (20,100),
            cv2.FONT_HERSHEY_SIMPLEX,
            2,
            (0,0,255),
            3
        )


    cv2.imshow(
        "DriveSense AI Steering",
        frame
    )


    if cv2.waitKey(1)==27:
        break


cap.release()
cv2.destroyAllWindows()