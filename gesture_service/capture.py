from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import cv2
from cv2.typing import MatLike
from mediapipe.python.solutions import drawing_utils as mp_drawing
from mediapipe.python.solutions import hands as mp_hands

from gesture_service.config import CameraSettings
from gesture_service.events import Vec3
from gesture_service.landmarks import HandLandmarks, Landmark, hand_center
from gesture_service.matcher import HandFrame
from gesture_service.motion import classify_motion
from gesture_service.pose import classify_pose

FrameCallback = Callable[[list[HandFrame], MatLike], None]  # second arg: annotated BGR frame


@dataclass
class _PrevHand:
    center: Vec3
    ts: float


def _to_hand_landmarks(mp_landmarks: object, label: str) -> HandLandmarks:
    pts = tuple(Landmark(lm.x, lm.y, lm.z) for lm in mp_landmarks.landmark)  # type: ignore[attr-defined]
    return HandLandmarks(points=pts, handedness="left" if label == "Left" else "right")


def run_capture_loop(
    on_frame: FrameCallback,
    settings: CameraSettings | None = None,
    stop: Callable[[], bool] = lambda: False,
) -> None:
    """Blocking camera loop. Runs in a background thread. Calls `on_frame` with
    the per-frame HandFrames and the annotated BGR image. Returns when `stop()`."""
    cfg = settings or CameraSettings()
    cap = cv2.VideoCapture(cfg.index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.height)

    hands = mp_hands.Hands(
        max_num_hands=2,
        model_complexity=1,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.5,
    )
    drawer = mp_drawing
    prev: dict[str, _PrevHand] = {}

    try:
        while not stop():
            ok, frame = cap.read()
            if not ok:
                continue
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result: Any = hands.process(rgb)  # dynamic NamedTuple fields
            now = time.monotonic()

            frames: list[HandFrame] = []
            if result.multi_hand_landmarks:
                handed = result.multi_handedness or []
                for i, lms in enumerate(result.multi_hand_landmarks):
                    label = handed[i].classification[0].label if i < len(handed) else "Right"
                    hand = _to_hand_landmarks(lms, label)
                    pose = classify_pose(hand)
                    c = hand_center(hand)
                    center = Vec3(c.x, c.y, c.z)
                    side = hand.handedness
                    p = prev.get(side)
                    dt = (now - p.ts) if p else 1e-3
                    motion = classify_motion(p.center if p else center, center, dt)
                    prev[side] = _PrevHand(center=center, ts=now)
                    frames.append(
                        HandFrame(pose=pose, center=center, motion=motion, handedness=side)
                    )
                    drawer.draw_landmarks(frame, lms, list(mp_hands.HAND_CONNECTIONS))

            on_frame(frames, frame)
    finally:
        cap.release()
        hands.close()
