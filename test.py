import cv2
import mediapipe as mp
import numpy as np

print("=" * 40)
print("🚗 DriveSense AI - Environment Test")
print("=" * 40)

print(f"✅ OpenCV Version    : {cv2.__version__}")
print(f"✅ MediaPipe Version : {mp.__version__}")
print(f"✅ NumPy Version     : {np.__version__}")

# Camera Test
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("\n❌ Camera could not be opened.")
else:
    print("\n✅ Camera detected successfully!")

    while True:
        ret, frame = cap.read()

        if not ret:
            print("❌ Failed to capture frame.")
            break

        cv2.putText(
            frame,
            "DriveSense AI Camera Test",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2
        )

        cv2.imshow("Camera Test", frame)

        # Press ESC to exit
        if cv2.waitKey(1) == 27:
            break

    cap.release()
    cv2.destroyAllWindows()

print("\n🎉 Environment is ready!")