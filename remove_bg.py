import cv2
import numpy as np


img = cv2.imread(
    "assets/steering_wheel.png",
    cv2.IMREAD_UNCHANGED
)


if img is None:
    print("Image not found")
    exit()


# convert to HSV
hsv = cv2.cvtColor(
    img[:,:,:3],
    cv2.COLOR_BGR2HSV
)


# checkerboard is usually light grey/white
lower = np.array([0,0,180])
upper = np.array([180,80,255])


mask = cv2.inRange(
    hsv,
    lower,
    upper
)


# invert mask
alpha = 255 - mask


# keep original RGB
result = img[:,:,:3]


# add new alpha channel
result = np.dstack(
    (
        result,
        alpha
    )
)


cv2.imwrite(
    "assets/steering_clean.png",
    result
)


print("✅ Created steering_clean.png")
