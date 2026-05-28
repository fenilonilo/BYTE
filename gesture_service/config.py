from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Thresholds:
    pinch_dist: float = 0.06  # normalized thumb-index distance
    swipe_speed: float = 0.8  # normalized units/sec, horizontal
    hold_speed: float = 0.15  # normalized units/sec, below = hold
    orbit_move_speed: float = 0.4  # free-hand speed for orbit
    portal_near: float = 0.15  # min inter-hand distance for portal
    portal_far: float = 0.6  # max inter-hand distance for portal
    portal_y_tol: float = 0.12  # max vertical offset between hands
    instant_cooldown_s: float = 1.0  # min seconds between same instant gesture


@dataclass(frozen=True, slots=True)
class CameraSettings:
    index: int = 0
    width: int = 640
    height: int = 480


@dataclass(frozen=True, slots=True)
class ServiceSettings:
    backend_ingest_url: str = "ws://127.0.0.1:8000/ws/gesture-ingest"
    reconnect_seconds: float = 2.0
