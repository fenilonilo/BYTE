# Gesture CV Service — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Python `gesture-service` that owns the camera, detects a built-in set of hand gestures, logs them, and serves a live annotated webcam preview — the foundation of the CV-service rebuild.

**Architecture:** A separate process (`gesture_service/`). Pure, testable logic — landmark types, pose classification, motion analysis, gesture matching, event schema — sits behind thin, manually-verified I/O adapters (MediaPipe camera capture, MJPEG preview). A background thread runs the camera→MediaPipe→recognizers loop and updates shared state; a small FastAPI app serves the preview and the loop logs `GestureEvent`s. No backend/bus connection yet (that is Phase 2).

**Tech Stack:** Python 3.12, MediaPipe Hands, OpenCV, FastAPI + uvicorn, pytest, ruff, pyright (strict).

**Scope note — Phase 1 built-in gesture set:** `pinch`, `swipe`, `freeze`, `portal`, `orbit`. The matcher is structured so adding a gesture = adding a rule. Temporal refinements present in the old JS engine (freeze 300 ms window, orbit 500 ms hold, prayer→blast `explosion`, frame smoothing/memory) are intentionally **out of Phase 1 scope** — they are added in later phases and are not stubbed here.

**Scope note — motion vocabulary:** The motion analyzer is per-hand and emits `none`/`hold`/`swipe`. Two-hand relational detection (hand distance for `portal`, free-hand movement for `orbit`) is computed in the matcher where both hands are available — not in the per-hand analyzer.

**Coordinate convention:** All Phase 1 spatial data uses MediaPipe image-normalized coordinates (`x`, `y` in `[0, 1]`, `z` relative). The frontend maps these to particle world space in later phases.

**Ports / processes:** backend `8000`, vite `5173`, **gesture-service `8001`**.

---

## File Structure

| File | Responsibility | Tested |
|------|----------------|--------|
| `gesture_service/__init__.py` | Package marker | — |
| `gesture_service/config.py` | `Thresholds` + `CameraSettings` (frozen dataclasses) | indirectly |
| `gesture_service/landmarks.py` | `Landmark`, `HandLandmarks`, `distance`, `hand_center` (pure) | TDD |
| `gesture_service/events.py` | `Vec3`, `GestureParams`, `GestureEvent` (pure) | TDD |
| `gesture_service/pose.py` | `Pose` enum, `classify_pose` (pure) | TDD |
| `gesture_service/motion.py` | `Motion` enum, `MotionSample`, `classify_motion` (pure) | TDD |
| `gesture_service/matcher.py` | `HandFrame`, `GestureMatcher` (stateful, injected `now`) | TDD |
| `gesture_service/capture.py` | MediaPipe + OpenCV camera adapter (thin) | manual |
| `gesture_service/preview.py` | Annotated-frame MJPEG endpoint + shared state | manual |
| `gesture_service/main.py` | FastAPI app + capture thread wiring + logging | manual |
| `tests/unit/gesture_service/__init__.py` | Test package marker | — |
| `tests/unit/gesture_service/test_landmarks.py` | landmarks tests | — |
| `tests/unit/gesture_service/test_events.py` | events tests | — |
| `tests/unit/gesture_service/test_pose.py` | pose tests + `make_hand` helper | — |
| `tests/unit/gesture_service/test_motion.py` | motion tests | — |
| `tests/unit/gesture_service/test_matcher.py` | matcher tests | — |

**Why `--no-cov` on single-test runs:** `pyproject.toml` sets `addopts = [... "--cov=app", "--cov-fail-under=80"]`. Running a subset measures ~0% of `app` and fails the gate. Single-test commands below append `--no-cov`; the full suite (with coverage) runs once at the end (Task 10).

---

### Task 1: Project setup — deps, package, config

**Files:**
- Modify: `pyproject.toml`
- Create: `gesture_service/__init__.py`
- Create: `gesture_service/config.py`
- Create: `tests/unit/gesture_service/__init__.py`

- [ ] **Step 1: Add the `vision` optional dependency group**

In `pyproject.toml`, under `[project.optional-dependencies]`, add:

```toml
vision = [
    "mediapipe>=0.10.14",
    "opencv-python>=4.10",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
]
```

- [ ] **Step 2: Register `gesture_service` with hatch and pyright**

In `pyproject.toml`, update the wheel packages:

```toml
[tool.hatch.build.targets.wheel]
packages = ["app", "gesture_service"]
```

And the pyright include list:

```toml
include = ["app", "tests", "main.py", "gesture_service"]
```

- [ ] **Step 3: Install the new dependencies**

Run: `.venv\Scripts\python -m pip install -e ".[vision,dev]"`
Expected: installs `mediapipe`, `opencv-python`, `fastapi`, `uvicorn` without error.
If `mediapipe` fails to resolve a wheel on this Python/OS, stop and report — do not work around it silently.

- [ ] **Step 4: Create the package + test package markers**

Create `gesture_service/__init__.py`:

```python
"""Standalone computer-vision service: camera -> gestures."""
```

Create `tests/unit/gesture_service/__init__.py` (empty file).

- [ ] **Step 5: Create `gesture_service/config.py`**

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Thresholds:
    pinch_dist: float = 0.06        # normalized thumb-index distance
    swipe_speed: float = 0.8        # normalized units/sec, horizontal
    hold_speed: float = 0.15        # normalized units/sec, below = hold
    orbit_move_speed: float = 0.4   # free-hand speed for orbit
    portal_near: float = 0.15       # min inter-hand distance for portal
    portal_far: float = 0.6         # max inter-hand distance for portal
    portal_y_tol: float = 0.12      # max vertical offset between hands


@dataclass(frozen=True, slots=True)
class CameraSettings:
    index: int = 0
    width: int = 640
    height: int = 480
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml gesture_service/__init__.py gesture_service/config.py tests/unit/gesture_service/__init__.py
git commit -m "chore(gesture-service): scaffold package, vision deps, thresholds config"
```

---

### Task 2: Landmark types + helpers

**Files:**
- Create: `gesture_service/landmarks.py`
- Test: `tests/unit/gesture_service/test_landmarks.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import pytest

from gesture_service.landmarks import HandLandmarks, Landmark, distance, hand_center


def test_distance_euclidean() -> None:
    a = Landmark(0.0, 0.0, 0.0)
    b = Landmark(3.0, 4.0, 0.0)
    assert distance(a, b) == pytest.approx(5.0)


def test_hand_center_is_landmark_9() -> None:
    pts = tuple(Landmark(float(i), 0.0, 0.0) for i in range(21))
    hand = HandLandmarks(points=pts, handedness="right")
    assert hand_center(hand) == Landmark(9.0, 0.0, 0.0)


def test_landmark_is_frozen() -> None:
    lm = Landmark(1.0, 2.0, 3.0)
    with pytest.raises(Exception):
        lm.x = 9.0  # type: ignore[misc]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/unit/gesture_service/test_landmarks.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'gesture_service.landmarks'`

- [ ] **Step 3: Write the implementation**

Create `gesture_service/landmarks.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

HAND_CENTER_INDEX = 9  # middle-finger MCP


@dataclass(frozen=True, slots=True)
class Landmark:
    x: float
    y: float
    z: float


@dataclass(frozen=True, slots=True)
class HandLandmarks:
    points: tuple[Landmark, ...]   # 21 landmarks
    handedness: str                # 'left' | 'right'


def distance(a: Landmark, b: Landmark) -> float:
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2) ** 0.5


def hand_center(hand: HandLandmarks) -> Landmark:
    return hand.points[HAND_CENTER_INDEX]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/unit/gesture_service/test_landmarks.py -v --no-cov`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add gesture_service/landmarks.py tests/unit/gesture_service/test_landmarks.py
git commit -m "feat(gesture-service): add landmark types and helpers"
```

---

### Task 3: Event schema

**Files:**
- Create: `gesture_service/events.py`
- Test: `tests/unit/gesture_service/test_events.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import pytest

from gesture_service.events import GestureEvent, GestureParams, Vec3


def test_vec3_defaults_to_zero() -> None:
    v = Vec3()
    assert (v.x, v.y, v.z) == (0.0, 0.0, 0.0)


def test_gesture_params_defaults() -> None:
    p = GestureParams()
    assert p.points == ()
    assert p.vector == Vec3()
    assert p.center == Vec3()
    assert p.radius == 0.0
    assert p.magnitude == 0.0


def test_gesture_event_fields() -> None:
    ev = GestureEvent(
        gesture="pinch",
        phase="start",
        hands=1,
        params=GestureParams(points=(Vec3(0.5, 0.5, 0.0),)),
        ts=123.0,
    )
    assert ev.gesture == "pinch"
    assert ev.phase == "start"
    assert ev.hands == 1
    assert ev.params.points[0] == Vec3(0.5, 0.5, 0.0)
    assert ev.ts == 123.0


def test_gesture_event_is_frozen() -> None:
    ev = GestureEvent(gesture="none", phase="idle", hands=0, params=GestureParams(), ts=0.0)
    with pytest.raises(Exception):
        ev.gesture = "x"  # type: ignore[misc]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/unit/gesture_service/test_events.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'gesture_service.events'`

- [ ] **Step 3: Write the implementation**

Create `gesture_service/events.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass(frozen=True, slots=True)
class GestureParams:
    points: tuple[Vec3, ...] = ()
    vector: Vec3 = field(default_factory=Vec3)
    center: Vec3 = field(default_factory=Vec3)
    radius: float = 0.0
    magnitude: float = 0.0


@dataclass(frozen=True, slots=True)
class GestureEvent:
    gesture: str
    phase: str   # 'start' | 'hold' | 'end' | 'instant' | 'idle'
    hands: int   # 0 | 1 | 2
    params: GestureParams
    ts: float
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/unit/gesture_service/test_events.py -v --no-cov`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add gesture_service/events.py tests/unit/gesture_service/test_events.py
git commit -m "feat(gesture-service): add GestureEvent schema"
```

---

### Task 4: Pose classifier

**Files:**
- Create: `gesture_service/pose.py`
- Test: `tests/unit/gesture_service/test_pose.py`

- [ ] **Step 1: Write the failing test (includes the `make_hand` helper)**

```python
from __future__ import annotations

from gesture_service.landmarks import HandLandmarks, Landmark
from gesture_service.pose import Pose, classify_pose


def make_hand(
    *,
    index_curled: bool,
    middle_curled: bool,
    ring_curled: bool,
    pinky_curled: bool,
    pinch: bool = False,
    cx: float = 0.5,
    cy: float = 0.5,
    handedness: str = "right",
) -> HandLandmarks:
    """Build 21 landmarks. Extended finger: tip above pip (tip.y < pip.y).
    Curled finger: tip below pip (tip.y > pip.y). Image coords: y grows down.
    """
    pts = [Landmark(cx, cy, 0.0) for _ in range(21)]
    pts[9] = Landmark(cx, cy, 0.0)  # hand center
    pts[4] = Landmark(cx, cy, 0.0)  # thumb tip

    # Finger (tip_idx, pip_idx) pairs
    fingers = {
        "index": (8, 6),
        "middle": (12, 10),
        "ring": (16, 14),
        "pinky": (20, 18),
    }
    curl_flags = {
        "index": index_curled,
        "middle": middle_curled,
        "ring": ring_curled,
        "pinky": pinky_curled,
    }
    for name, (tip, pip) in fingers.items():
        pts[pip] = Landmark(cx, cy, 0.0)
        offset = 0.1 if curl_flags[name] else -0.1
        pts[tip] = Landmark(cx, cy + offset, 0.0)

    if pinch:
        # thumb tip near index tip (< pinch_dist 0.06)
        pts[8] = Landmark(cx + 0.02, cy, 0.0)
        pts[4] = Landmark(cx, cy, 0.0)
    else:
        # ensure thumb-index distance > 0.06
        pts[4] = Landmark(cx + 0.3, cy, 0.0)

    return HandLandmarks(points=tuple(pts), handedness=handedness)


def test_open_hand() -> None:
    hand = make_hand(index_curled=False, middle_curled=False, ring_curled=False, pinky_curled=False)
    assert classify_pose(hand) == Pose.OPEN


def test_fist() -> None:
    hand = make_hand(index_curled=True, middle_curled=True, ring_curled=True, pinky_curled=True)
    assert classify_pose(hand) == Pose.FIST


def test_pinch_takes_priority() -> None:
    hand = make_hand(index_curled=False, middle_curled=False, ring_curled=False, pinky_curled=False, pinch=True)
    assert classify_pose(hand) == Pose.PINCH


def test_point_index_only_extended() -> None:
    hand = make_hand(index_curled=False, middle_curled=True, ring_curled=True, pinky_curled=True)
    assert classify_pose(hand) == Pose.POINT


def test_mixed_is_none() -> None:
    hand = make_hand(index_curled=False, middle_curled=False, ring_curled=True, pinky_curled=False)
    assert classify_pose(hand) == Pose.NONE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/unit/gesture_service/test_pose.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'gesture_service.pose'`

- [ ] **Step 3: Write the implementation**

Create `gesture_service/pose.py`:

```python
from __future__ import annotations

from enum import Enum

from gesture_service.config import Thresholds
from gesture_service.landmarks import HandLandmarks, distance

THUMB_TIP, INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP = 4, 8, 12, 16, 20
INDEX_PIP, MIDDLE_PIP, RING_PIP, PINKY_PIP = 6, 10, 14, 18

_DEFAULTS = Thresholds()


class Pose(str, Enum):
    NONE = "none"
    FIST = "fist"
    OPEN = "open"
    PINCH = "pinch"
    POINT = "point"


def _curled(tip_y: float, pip_y: float) -> bool:
    return tip_y > pip_y  # image coords: tip below pip => finger curled


def classify_pose(hand: HandLandmarks, thresholds: Thresholds = _DEFAULTS) -> Pose:
    p = hand.points
    if distance(p[THUMB_TIP], p[INDEX_TIP]) < thresholds.pinch_dist:
        return Pose.PINCH

    index_c = _curled(p[INDEX_TIP].y, p[INDEX_PIP].y)
    middle_c = _curled(p[MIDDLE_TIP].y, p[MIDDLE_PIP].y)
    ring_c = _curled(p[RING_TIP].y, p[RING_PIP].y)
    pinky_c = _curled(p[PINKY_TIP].y, p[PINKY_PIP].y)

    if index_c and middle_c and ring_c and pinky_c:
        return Pose.FIST
    if not (index_c or middle_c or ring_c or pinky_c):
        return Pose.OPEN
    if not index_c and middle_c and ring_c and pinky_c:
        return Pose.POINT
    return Pose.NONE
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/unit/gesture_service/test_pose.py -v --no-cov`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add gesture_service/pose.py tests/unit/gesture_service/test_pose.py
git commit -m "feat(gesture-service): add rule-based pose classifier"
```

---

### Task 5: Motion analyzer

**Files:**
- Create: `gesture_service/motion.py`
- Test: `tests/unit/gesture_service/test_motion.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import pytest

from gesture_service.events import Vec3
from gesture_service.motion import Motion, classify_motion


def test_hold_when_nearly_still() -> None:
    sample = classify_motion(Vec3(0.5, 0.5, 0.0), Vec3(0.5, 0.5, 0.0), dt=0.033)
    assert sample.motion == Motion.HOLD
    assert sample.speed == pytest.approx(0.0)


def test_swipe_on_fast_horizontal() -> None:
    # 0.4 units in 0.1s => vx = 4.0 (>> swipe_speed 0.8), horizontal dominant
    sample = classify_motion(Vec3(0.2, 0.5, 0.0), Vec3(0.6, 0.5, 0.0), dt=0.1)
    assert sample.motion == Motion.SWIPE
    assert sample.velocity.x == pytest.approx(4.0)


def test_swipe_sign_negative_when_moving_left() -> None:
    sample = classify_motion(Vec3(0.6, 0.5, 0.0), Vec3(0.2, 0.5, 0.0), dt=0.1)
    assert sample.motion == Motion.SWIPE
    assert sample.velocity.x < 0


def test_none_when_moderate_vertical() -> None:
    # vy = 3.0 vertical, vx small => not swipe, speed above hold => none
    sample = classify_motion(Vec3(0.5, 0.2, 0.0), Vec3(0.5, 0.5, 0.0), dt=0.1)
    assert sample.motion == Motion.NONE


def test_zero_dt_does_not_divide_by_zero() -> None:
    sample = classify_motion(Vec3(0.5, 0.5, 0.0), Vec3(0.5, 0.5, 0.0), dt=0.0)
    assert sample.motion == Motion.HOLD
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/unit/gesture_service/test_motion.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'gesture_service.motion'`

- [ ] **Step 3: Write the implementation**

Create `gesture_service/motion.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from gesture_service.config import Thresholds
from gesture_service.events import Vec3

_DEFAULTS = Thresholds()


class Motion(str, Enum):
    NONE = "none"
    HOLD = "hold"
    SWIPE = "swipe"


@dataclass(frozen=True, slots=True)
class MotionSample:
    motion: Motion
    velocity: Vec3
    speed: float


def classify_motion(
    prev: Vec3, curr: Vec3, dt: float, thresholds: Thresholds = _DEFAULTS
) -> MotionSample:
    dt = max(dt, 1e-3)
    vx = (curr.x - prev.x) / dt
    vy = (curr.y - prev.y) / dt
    vz = (curr.z - prev.z) / dt
    speed = (vx * vx + vy * vy + vz * vz) ** 0.5
    velocity = Vec3(vx, vy, vz)

    if abs(vx) > thresholds.swipe_speed and abs(vx) > abs(vy):
        return MotionSample(Motion.SWIPE, velocity, speed)
    if speed < thresholds.hold_speed:
        return MotionSample(Motion.HOLD, velocity, speed)
    return MotionSample(Motion.NONE, velocity, speed)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/unit/gesture_service/test_motion.py -v --no-cov`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add gesture_service/motion.py tests/unit/gesture_service/test_motion.py
git commit -m "feat(gesture-service): add per-hand motion analyzer"
```

---

### Task 6: Gesture matcher

**Files:**
- Create: `gesture_service/matcher.py`
- Test: `tests/unit/gesture_service/test_matcher.py`

The matcher takes a per-frame list of `HandFrame` (already pose- and motion-classified) plus an injected `now`, and returns a `GestureEvent | None`. It owns phase lifecycle: sustained gestures (`pinch`, `portal`, `orbit`) emit `start` → `hold`… → `end`; instant gestures (`swipe`, `freeze`) emit a single `instant`.

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from gesture_service.events import Vec3
from gesture_service.matcher import GestureMatcher, HandFrame
from gesture_service.motion import Motion, MotionSample
from gesture_service.pose import Pose


def _still() -> MotionSample:
    return MotionSample(Motion.HOLD, Vec3(), 0.0)


def _swipe(vx: float) -> MotionSample:
    return MotionSample(Motion.SWIPE, Vec3(vx, 0.0, 0.0), abs(vx))


def _hand(pose: Pose, cx: float, cy: float, handed: str, motion: MotionSample | None = None) -> HandFrame:
    return HandFrame(pose=pose, center=Vec3(cx, cy, 0.0), motion=motion or _still(), handedness=handed)


def test_no_hands_returns_none() -> None:
    m = GestureMatcher()
    assert m.update([], now=0.0) is None


def test_pinch_emits_start_then_hold() -> None:
    m = GestureMatcher()
    hand = _hand(Pose.PINCH, 0.5, 0.5, "right")
    first = m.update([hand], now=0.0)
    second = m.update([hand], now=0.1)
    assert first is not None and first.gesture == "pinch" and first.phase == "start"
    assert second is not None and second.gesture == "pinch" and second.phase == "hold"
    assert first.hands == 1


def test_sustained_emits_end_when_released() -> None:
    m = GestureMatcher()
    hand = _hand(Pose.PINCH, 0.5, 0.5, "right")
    m.update([hand], now=0.0)
    end = m.update([], now=0.2)
    assert end is not None and end.gesture == "pinch" and end.phase == "end"


def test_swipe_emits_instant_once() -> None:
    m = GestureMatcher()
    hand = _hand(Pose.OPEN, 0.5, 0.5, "right", motion=_swipe(3.0))
    first = m.update([hand], now=0.0)
    second = m.update([hand], now=0.05)
    assert first is not None and first.gesture == "swipe" and first.phase == "instant"
    assert first.params.vector.x > 0
    assert second is None  # instant fires once, no repeat while held


def test_freeze_both_fists_instant() -> None:
    m = GestureMatcher()
    left = _hand(Pose.FIST, 0.4, 0.5, "left")
    right = _hand(Pose.FIST, 0.6, 0.5, "right")
    ev = m.update([left, right], now=0.0)
    assert ev is not None and ev.gesture == "freeze" and ev.phase == "instant" and ev.hands == 2


def test_portal_both_open_in_range() -> None:
    m = GestureMatcher()
    left = _hand(Pose.OPEN, 0.3, 0.5, "left")
    right = _hand(Pose.OPEN, 0.7, 0.5, "right")  # distance 0.4 in [0.15, 0.6]
    ev = m.update([left, right], now=0.0)
    assert ev is not None and ev.gesture == "portal" and ev.phase == "start"
    assert ev.params.center.x == 0.5
    assert ev.params.radius > 0


def test_orbit_one_pinch_other_moving() -> None:
    m = GestureMatcher()
    anchor = _hand(Pose.PINCH, 0.4, 0.5, "left")
    free = _hand(Pose.OPEN, 0.6, 0.5, "right", motion=MotionSample(Motion.NONE, Vec3(0.0, 0.5, 0.0), 0.5))
    ev = m.update([anchor, free], now=0.0)
    assert ev is not None and ev.gesture == "orbit" and ev.phase == "start"
    assert ev.params.center.x == 0.4  # anchor (pinch hand) center
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/unit/gesture_service/test_matcher.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'gesture_service.matcher'`

- [ ] **Step 3: Write the implementation**

Create `gesture_service/matcher.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from gesture_service.config import Thresholds
from gesture_service.events import GestureEvent, GestureParams, Vec3
from gesture_service.motion import Motion, MotionSample
from gesture_service.pose import Pose

INSTANT_GESTURES = frozenset({"swipe", "freeze"})


@dataclass(frozen=True, slots=True)
class HandFrame:
    pose: Pose
    center: Vec3
    motion: MotionSample
    handedness: str


def _distance(a: Vec3, b: Vec3) -> float:
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2) ** 0.5


class GestureMatcher:
    def __init__(self, thresholds: Thresholds | None = None) -> None:
        self._t = thresholds or Thresholds()
        self._current: str | None = None

    def update(self, hands: list[HandFrame], now: float) -> GestureEvent | None:
        raw = self._classify(hands)
        name = raw[0] if raw else None
        hand_count = len(hands)

        # Gesture changed (or stopped)
        if name != self._current:
            ended = self._end_event(now) if self._is_sustained(self._current) else None
            self._current = name
            if name is None:
                return ended  # may be None or the end event of the prior sustained gesture
            params = raw[1]  # type: ignore[index]
            phase = "instant" if name in INSTANT_GESTURES else "start"
            return GestureEvent(gesture=name, phase=phase, hands=hand_count, params=params, ts=now)

        # Gesture unchanged
        if name is None:
            return None
        if name in INSTANT_GESTURES:
            return None  # already fired once
        params = raw[1]  # type: ignore[index]
        return GestureEvent(gesture=name, phase="hold", hands=hand_count, params=params, ts=now)

    def _is_sustained(self, name: str | None) -> bool:
        return name is not None and name not in INSTANT_GESTURES

    def _end_event(self, now: float) -> GestureEvent:
        return GestureEvent(
            gesture=self._current or "none",
            phase="end",
            hands=0,
            params=GestureParams(),
            ts=now,
        )

    def _classify(self, hands: list[HandFrame]) -> tuple[str, GestureParams] | None:
        if len(hands) == 1:
            return self._classify_one(hands[0])
        if len(hands) == 2:
            return self._classify_two(hands[0], hands[1])
        return None

    def _classify_one(self, h: HandFrame) -> tuple[str, GestureParams] | None:
        if h.pose == Pose.PINCH:
            return "pinch", GestureParams(points=(h.center,))
        if h.pose == Pose.OPEN and h.motion.motion == Motion.SWIPE:
            sign = 1.0 if h.motion.velocity.x >= 0 else -1.0
            return "swipe", GestureParams(
                vector=Vec3(sign, 0.0, 0.0), magnitude=h.motion.speed
            )
        return None

    def _classify_two(self, a: HandFrame, b: HandFrame) -> tuple[str, GestureParams] | None:
        if a.pose == Pose.FIST and b.pose == Pose.FIST:
            return "freeze", GestureParams(points=(a.center, b.center))

        # orbit: exactly one hand pinching, the other moving
        pinching = [h for h in (a, b) if h.pose == Pose.PINCH]
        if len(pinching) == 1:
            anchor = pinching[0]
            free = b if anchor is a else a
            if free.motion.speed > self._t.orbit_move_speed:
                return "orbit", GestureParams(center=anchor.center, points=(free.center,))

        # portal: both open, in distance range, similar height
        if a.pose == Pose.OPEN and b.pose == Pose.OPEN:
            dist = _distance(a.center, b.center)
            y_diff = abs(a.center.y - b.center.y)
            if self._t.portal_near <= dist <= self._t.portal_far and y_diff < self._t.portal_y_tol:
                center = Vec3((a.center.x + b.center.x) / 2, (a.center.y + b.center.y) / 2, 0.0)
                return "portal", GestureParams(center=center, radius=dist / 2)
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/unit/gesture_service/test_matcher.py -v --no-cov`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add gesture_service/matcher.py tests/unit/gesture_service/test_matcher.py
git commit -m "feat(gesture-service): add stateful gesture matcher with phase lifecycle"
```

---

### Task 7: Camera capture adapter (manual verify)

**Files:**
- Create: `gesture_service/capture.py`

MediaPipe + OpenCV are untyped; isolate them here. This module is verified manually in Task 9 (it needs a real camera), so no unit test.

- [ ] **Step 1: Write the implementation**

Create `gesture_service/capture.py`:

```python
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import cv2  # type: ignore[import-untyped]
import mediapipe as mp  # type: ignore[import-untyped]

from gesture_service.config import CameraSettings
from gesture_service.events import Vec3
from gesture_service.landmarks import HandLandmarks, Landmark, hand_center
from gesture_service.matcher import HandFrame
from gesture_service.motion import classify_motion
from gesture_service.pose import classify_pose

FrameCallback = Callable[[list[HandFrame], object], None]  # second arg: BGR frame (cv2, untyped)


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

    hands = mp.solutions.hands.Hands(
        max_num_hands=2, model_complexity=1,
        min_detection_confidence=0.7, min_tracking_confidence=0.5,
    )
    drawer = mp.solutions.drawing_utils
    prev: dict[str, _PrevHand] = {}

    try:
        while not stop():
            ok, frame = cap.read()
            if not ok:
                continue
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = hands.process(rgb)
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
                    frames.append(HandFrame(pose=pose, center=center, motion=motion, handedness=side))
                    drawer.draw_landmarks(frame, lms, mp.solutions.hands.HAND_CONNECTIONS)

            on_frame(frames, frame)
    finally:
        cap.release()
        hands.close()
```

- [ ] **Step 2: Verify it imports cleanly (no camera needed yet)**

Run: `.venv\Scripts\python -c "import gesture_service.capture; print('ok')"`
Expected: prints `ok` (confirms cv2 + mediapipe import and the module is syntactically sound).

- [ ] **Step 3: Commit**

```bash
git add gesture_service/capture.py
git commit -m "feat(gesture-service): add MediaPipe camera capture adapter"
```

---

### Task 8: Preview state + MJPEG endpoint (manual verify)

**Files:**
- Create: `gesture_service/preview.py`

- [ ] **Step 1: Write the implementation**

Create `gesture_service/preview.py`:

```python
from __future__ import annotations

import threading
import time
from collections.abc import Iterator

import cv2  # type: ignore[import-untyped]
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter()

_lock = threading.Lock()
_latest_jpeg: bytes | None = None


def set_latest_frame(frame_bgr: object) -> None:
    global _latest_jpeg
    ok, buf = cv2.imencode(".jpg", frame_bgr)
    if ok:
        with _lock:
            _latest_jpeg = buf.tobytes()


def _mjpeg_stream() -> Iterator[bytes]:
    boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
    while True:
        with _lock:
            data = _latest_jpeg
        if data is not None:
            yield boundary + data + b"\r\n"
        time.sleep(0.015)


@router.get("/preview")
def preview() -> StreamingResponse:
    return StreamingResponse(
        _mjpeg_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `.venv\Scripts\python -c "import gesture_service.preview; print('ok')"`
Expected: prints `ok`

- [ ] **Step 3: Commit**

```bash
git add gesture_service/preview.py
git commit -m "feat(gesture-service): add MJPEG preview endpoint with shared frame state"
```

---

### Task 9: Service entrypoint + end-to-end manual verify

**Files:**
- Create: `gesture_service/main.py`

- [ ] **Step 1: Write the implementation**

Create `gesture_service/main.py`:

```python
from __future__ import annotations

import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI

from gesture_service.capture import run_capture_loop
from gesture_service.matcher import GestureMatcher, HandFrame
from gesture_service.preview import router as preview_router
from gesture_service.preview import set_latest_frame

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ]
)
log = structlog.get_logger("gesture-service")

_stop = threading.Event()
_matcher = GestureMatcher()


def _on_frame(frames: list[HandFrame], annotated: object) -> None:
    set_latest_frame(annotated)
    import time

    event = _matcher.update(frames, now=time.monotonic())
    if event is not None:
        log.info(
            "gesture",
            gesture=event.gesture,
            phase=event.phase,
            hands=event.hands,
        )


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    thread = threading.Thread(
        target=run_capture_loop,
        kwargs={"on_frame": _on_frame, "stop": _stop.is_set},
        daemon=True,
    )
    thread.start()
    log.info("capture-thread-started")
    yield
    _stop.set()


app = FastAPI(title="Marcelo Gesture Service", lifespan=lifespan)
app.include_router(preview_router)


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8001)


if __name__ == "__main__":
    main()
```

Note: `stop=_stop.is_set` passes the bound method so the loop polls the event.

- [ ] **Step 2: Run the service**

Run: `.venv\Scripts\python -m gesture_service.main`
Expected: logs `capture-thread-started` and uvicorn listening on `127.0.0.1:8001`. The webcam LED turns on.

- [ ] **Step 3: Manually verify gesture detection**

Perform each Phase 1 gesture in front of the camera and confirm the console logs the matching event:
- One pinching hand → `gesture gesture=pinch phase=start` then `phase=hold`; release → `phase=end`.
- Open hand swiped fast sideways → `gesture=swipe phase=instant`.
- Two fists → `gesture=freeze phase=instant`.
- Two open hands ~40% of frame apart, same height → `gesture=portal phase=start`/`hold`.
- One pinch + other hand moving → `gesture=orbit phase=start`/`hold`.

Expected: each gesture logs the right name + phase lifecycle. Tune `Thresholds` in `config.py` if a gesture is hard to trigger.

- [ ] **Step 4: Manually verify the preview**

Open `http://localhost:8001/preview` in a browser.
Expected: live webcam feed (mirrored) with the hand skeleton drawn over detected hands.

- [ ] **Step 5: Commit**

```bash
git add gesture_service/main.py
git commit -m "feat(gesture-service): add entrypoint wiring camera loop, matcher logging, preview"
```

---

### Task 10: Phase close — full checks

- [ ] **Step 1: Run the full test suite (with coverage)**

Run: `.venv\Scripts\python -m pytest`
Expected: all tests pass; `app` coverage gate (≥80%) still satisfied (new gesture_service tests do not lower it).

- [ ] **Step 2: Lint**

Run: `.venv\Scripts\python -m ruff check gesture_service tests/unit/gesture_service`
Expected: no errors. Fix any (e.g. import ordering) and re-run.

- [ ] **Step 3: Format check**

Run: `.venv\Scripts\python -m ruff format --check gesture_service tests/unit/gesture_service`
Expected: no changes needed (or run without `--check` to apply, then re-commit).

- [ ] **Step 4: Type check**

Run: `.venv\Scripts\python -m pyright gesture_service`
Expected: 0 errors. Untyped cv2/mediapipe calls in `capture.py`/`preview.py` surface as warnings (allowed per `pyproject.toml`), not errors.

- [ ] **Step 5: Final commit (only if lint/format changed files)**

```bash
git add -A
git commit -m "chore(gesture-service): lint/format/type-check pass for phase 1"
```

---

## Self-Review Notes

- **Spec coverage (Phase 1 §):** 1.1 skeleton+camera → Tasks 1, 7, 9. 1.2 pose primitives → Task 4. 1.3 motion analyzer → Task 5 (per-hand; two-hand relations in matcher, documented). 1.4 GestureEvent schema + matcher → Tasks 3, 6. 1.5 annotated preview → Tasks 8, 9.
- **Deliberate Phase 1 scope cuts (not placeholders):** `explosion`; freeze/orbit time-window gating; smoothing/memory frames; KNN custom poses (Phase 5). The matcher is complete and correct for `{pinch, swipe, freeze, portal, orbit}`.
- **Type consistency:** `HandFrame`, `GestureEvent`, `GestureParams`, `Vec3`, `MotionSample`, `Pose`, `Motion`, `Thresholds`, `classify_pose`, `classify_motion`, `GestureMatcher.update` names match across all tasks.
- **No backend/bus dependency:** the service is fully standalone in Phase 1; it logs events. Wiring to the backend event bus is Phase 2.
