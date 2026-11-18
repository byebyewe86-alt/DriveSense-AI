"""
test_car.py - test the ESP32 + L298N car WITHOUT the camera.

Do this before you try gestures. It sends the same packets gesture_car.py
sends, so if the car drives correctly here, the hardware is good and any
problem left is only the gesture mapping.

    python test_car.py                     # keys, ESP32 in AP mode
    python test_car.py --host 192.168.1.42 # ESP32 in STA mode
    python test_car.py --demo              # automatic forward/left/right/stop

KEYS (click the window first so it has focus)
    W / S   forward / reverse   (hold to go faster)
    A / D   steer left / right
    SPACE   everything to zero
    R       reset steering to centre
    Q       quit (sends zero automatically)
"""

import argparse
import sys
import time

import cv2
import numpy as np

from car_link import CarLink, DEFAULT_HOST, DEFAULT_PORT

PACKET_HZ = 30
STEP = 8


def draw(screen, throttle, brake, steer, link):
    screen[:] = (30, 30, 30)

    if link is None:
        state, color = "PREVIEW (nothing sent)", (180, 180, 180)
    elif link.connected:
        state, color = "LINKED  %s:%d" % (link.host, link.port), (0, 220, 0)
    else:
        state, color = "NO LINK  (%s)" % link.status, (0, 0, 230)

    cv2.putText(screen, "DriveSense car test", (14, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(screen, state, (14, 52), cv2.FONT_HERSHEY_SIMPLEX,
                0.48, color, 1, cv2.LINE_AA)

    cv2.putText(screen, "GAS   %3d%%" % throttle, (14, 86),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 210, 0), 1, cv2.LINE_AA)
    cv2.putText(screen, "BRAKE %3d%%" % brake, (14, 108),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 220), 1, cv2.LINE_AA)
    cv2.putText(screen, "STEER %+4d" % steer, (14, 130),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 255), 1, cv2.LINE_AA)

    # steering bar
    x, y, w, h = 14, 142, 220, 12
    cv2.rectangle(screen, (x, y), (x + w, y + h), (80, 80, 80), 1)
    cv2.line(screen, (x + w // 2, y), (x + w // 2, y + h), (110, 110, 110), 1)
    mx = int(x + w / 2 + (steer / 100.0) * (w / 2 - 6))
    cv2.rectangle(screen, (mx - 5, y + 1), (mx + 5, y + h - 1), (0, 220, 255), -1)

    cv2.putText(screen, "W/S speed   A/D steer   SPACE stop   R centre   Q quit",
                (14, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200, 200, 200), 1, cv2.LINE_AA)


def main():
    ap = argparse.ArgumentParser(description="Manual test of the ESP32 RC car")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--preview", action="store_true", help="no network")
    ap.add_argument("--demo", action="store_true", help="run a scripted sequence")
    args = ap.parse_args()

    link = None if args.preview else CarLink(args.host, args.port)

    throttle = brake = 0
    steer = 0

    if args.demo:
        if link is None:
            print("--demo needs the car; drop --preview.")
            return 1
        link.start()
        print("Waiting for the car...")
        for _ in range(150):
            if link.connected:
                break
            time.sleep(0.1)
        if not link.connected:
            print("Never connected. Join the 'DriveSense-Car' WiFi first.")
            link.stop()
            return 1

        # (seconds, steer, throttle, brake, label)
        script = [
            (0.6,   0, 0,  0, "neutral"),
            (1.5,   0, 35, 0, "forward 35%"),
            (1.5,  60, 35, 0, "turn right"),
            (1.5, -60, 35, 0, "turn left"),
            (1.0,   0, 60, 0, "forward 60%"),
            (0.8,   0, 0, 35, "reverse"),
            (0.8,   0, 0,  0, "stop"),
        ]
        try:
            for seconds, s, t, b, label in script:
                print("  %-14s steer=%+4d gas=%3d rev=%3d" % (label, s, t, b))
                end = time.time() + seconds
                while time.time() < end:
                    link.send(s, t, b)
                    time.sleep(1.0 / PACKET_HZ)
        finally:
            link.send(0, 0, 0)
            time.sleep(0.3)
            link.stop()
        print("Demo finished. Car stopped.")
        return 0

    if link is not None:
        link.start()

    screen = np.zeros((200, 380, 3), dtype=np.uint8)

    try:
        while True:
            if link is not None:
                link.send(steer, throttle, brake)

            draw(screen, throttle, brake, steer, link)
            cv2.imshow("DriveSense car test", screen)

            key = cv2.waitKey(int(1000 / PACKET_HZ)) & 0xFF
            if key in (ord("q"), 27):
                break
            elif key == ord("w"):
                throttle = min(100, throttle + STEP)
                brake = 0
            elif key == ord("s"):
                brake = min(100, brake + STEP)
                throttle = 0
            elif key == ord("a"):
                steer = max(-100, steer - 15)
            elif key == ord("d"):
                steer = min(100, steer + 15)
            elif key == ord("r"):
                steer = 0
            elif key == 32:
                throttle = brake = 0
                steer = 0
    except KeyboardInterrupt:
        pass
    finally:
        if link is not None:
            link.send(0, 0, 0)
            time.sleep(0.2)
            link.stop()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    sys.exit(main())
