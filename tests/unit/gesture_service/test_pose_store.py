from __future__ import annotations

from gesture_service.pose_store import PoseStore


def test_save_and_load_roundtrip(tmp_path) -> None:
    path = tmp_path / "poses.json"
    store = PoseStore(path)
    store.add_sample("wave_hand", (0.1, 0.2, 0.3))
    store.add_sample("wave_hand", (0.11, 0.21, 0.31))
    store.persist()

    reloaded = PoseStore(path)
    reloaded.load()
    samples = reloaded.samples()
    assert len(samples) == 2
    assert all(label == "wave_hand" for label, _ in samples)
