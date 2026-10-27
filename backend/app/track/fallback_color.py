import cv2
import numpy as np
from numpy.typing import NDArray

from app.schemas import ObjectSpec
from app.track.geometry import Detection


def segment_color(image: NDArray[np.uint8], obj: ObjectSpec) -> Detection:
    if obj.hsv_lower is None or obj.hsv_upper is None:
        raise ValueError("HSV fallback requires explicit per-object color calibration")
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(obj.hsv_lower), np.array(obj.hsv_upper)) > 0
    # Calibration gives geometry, not a calibrated probability. Kept conservative.
    return Detection(mask if mask.any() else None, 0.8 if mask.any() else 0, obj.obj_class)
