"""Train the "Ei Byte" wake word with openWakeWord from our own clips (no piper, no TTS step).

Run with the training venv (Python 3.12, torch 2.5 + CUDA, openwakeword), not the project venv:

    <train>/venv/Scripts/python.exe scripts/wakeword_train.py prepare <train_dir>
    <train>/venv/Scripts/python.exe scripts/wakeword_train.py train <train_dir>

`prepare` packages wakeword_data/ (see wakeword_clips.py and wakeword_record.py) plus the
RIR / background audio into <train_dir>; `train` augments, trains and writes <model>.onnx.
Expects <train_dir>/base_config.yml, data/validation_set_features.npy, data/acav100m.npy and
data/esc50.zip.
"""

from __future__ import annotations

import hashlib
import importlib
import io
import random
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import soundfile as sf
import yaml
from scipy.signal import resample_poly

if TYPE_CHECKING:
    from collections.abc import Callable

MODEL = "ei_byte"
RATE = 16_000
CLIPS = Path("wakeword_data")
REAL_WEIGHT = 4  # your voice counts four times: there are far fewer real clips than synthetic
COPIES = 4  # on-disk copies, each augmented differently: train.py makes one pass over the files
NEG_CHUNK = 32_000  # train.py cuts every clip to total_length (2 s here)
TEST_FRACTION = 0.15
TARGET_PEAK = 0.7
STEPS = 30_000
STUB = (
    "def generate_samples(*args, **kwargs):\n"
    "    raise RuntimeError('clips come from wakeword_data/')\n"
)
# openwakeword.data.trim_mmap rewrites a file its caller still has memory-mapped, which Windows
# refuses. It only drops blank rows at the end, and one pass over the clips leaves none.
TRIM_PATCH = """import openwakeword.data as _owwdata


def _trim_mmap(mmap_path):
    rows = np.load(mmap_path, mmap_mode="r")
    blank = 0
    while blank < rows.shape[0] and np.all(rows[-1 - blank] == 0):
        blank += 1
    if blank:
        print(f"warning: {blank} blank rows left in {mmap_path}")


_owwdata.trim_mmap = _trim_mmap


"""
MODULES = (
    "torch", "torchaudio", "torchinfo", "torchmetrics", "speechbrain", "audiomentations",
    "torch_audiomentations", "mutagen", "acoustics", "pronouncing", "onnx", "onnxruntime",
    "requests", "datasets", "soundfile", "yaml", "openwakeword",
)  # fmt: skip


def load16(source: str | Path | io.BytesIO) -> np.ndarray:
    audio, rate = sf.read(source, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    return resample_poly(audio, RATE, rate).astype("float32") if rate != RATE else audio


def write16(path: Path, audio: np.ndarray) -> None:
    sf.write(path, (np.clip(audio, -1, 1) * 32767).astype("<i2"), RATE, subtype="PCM_16")


def peak_normalised(audio: np.ndarray) -> np.ndarray:
    return audio / max(float(np.abs(audio).max()), 1e-6) * TARGET_PEAK


def split(files: list[Path], rng: random.Random) -> tuple[list[Path], list[Path]]:
    unique = {
        hashlib.sha1(f.read_bytes(), usedforsecurity=False).hexdigest(): f
        for f in sorted(files, reverse=True)
    }
    files = sorted(unique.values())  # identical TTS renders must not land in both train and test
    rng.shuffle(files)
    cut = max(1, int(len(files) * TEST_FRACTION))
    return files[cut:], files[:cut]


def put(
    files: list[Path], out: Path, *, weight: int = 1, normalise: bool = False, chunk: int = 0
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for f in files:
        audio = load16(f)
        audio = peak_normalised(audio) if normalise else audio
        parts = (
            [audio[i : i + chunk] for i in range(0, len(audio) - chunk + 1, chunk)]
            if chunk and len(audio) > chunk
            else [audio]
        )
        for j, part in enumerate(parts):
            for k in range(weight):
                write16(out / f"{f.stem}_{j}_{k}.wav", part)


def preflight() -> None:
    missing = []
    for name in MODULES:
        try:
            importlib.import_module(name)
        except ImportError:
            missing.append(name)
    if missing:
        raise SystemExit(f"missing in this venv: {', '.join(missing)}")


def fill_once(dest: Path, build: Callable[[Path], None]) -> None:
    """Build in a .tmp sibling and rename, so a crash never leaves a half-filled directory."""
    if dest.exists():
        return
    tmp = dest.with_name(dest.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    build(tmp)
    tmp.rename(dest)
    print(f"{dest.name}: {len(list(dest.glob('*.wav')))}")


def prepare(train: Path) -> None:
    preflight()
    rng = random.Random(0)  # noqa: S311 - reproducible split, not security
    base = train / MODEL
    if base.exists():
        shutil.rmtree(base)
    # (source, copies, peak-normalise, chunk). The first real negative clip holds the start beep.
    groups = {
        "positive": [
            (CLIPS / "synth_positive", COPIES, False, 0),
            (CLIPS / "real_positive", COPIES * REAL_WEIGHT, False, 0),
        ],
        "negative": [
            (CLIPS / "synth_negative", COPIES, False, 0),
            (CLIPS / "real_negative", COPIES * REAL_WEIGHT, True, NEG_CHUNK),
        ],
    }
    for kind, sources in groups.items():
        for src, weight, normalise, chunk in sources:
            files = list(src.glob("*.wav"))
            if src.name == "real_negative":
                files = [f for f in files if not f.stem.endswith("_000")]
            tr, te = split(files, rng)
            put(tr, base / f"{kind}_train", weight=weight, normalise=normalise, chunk=chunk)
            put(te, base / f"{kind}_test", normalise=normalise, chunk=chunk)
            print(f"{kind}: {src.name} -> {len(tr)} train x{weight}, {len(te)} test")
    (train / "piper_stub").mkdir(exist_ok=True)
    (train / "piper_stub" / "generate_samples.py").write_text(STUB, encoding="utf-8")
    prepare_background(train)
    write_config(train)


def prepare_background(train: Path) -> None:
    def rirs(out: Path) -> None:
        from huggingface_hub import snapshot_download  # noqa: PLC0415 - training venv only

        repo = snapshot_download(
            "davidscripka/MIT_environmental_impulse_responses",
            repo_type="dataset",
            allow_patterns=["16khz/*.wav"],
        )
        for f in sorted((Path(repo) / "16khz").glob("*.wav")):
            write16(out / f.name, load16(f))

    def esc50(out: Path) -> None:
        with zipfile.ZipFile(train / "data" / "esc50.zip") as z:
            for name in z.namelist():
                if name.endswith(".wav") and "/audio/" in name:
                    write16(out / Path(name).name, load16(io.BytesIO(z.read(name))))

    fill_once(train / "mit_rirs", rirs)
    fill_once(train / "background" / "esc50", esc50)


def write_config(train: Path) -> None:
    config = yaml.safe_load((train / "base_config.yml").read_text(encoding="utf-8"))
    n_pos = len(list((train / MODEL / "positive_train").glob("*.wav")))
    n_test = len(list((train / MODEL / "positive_test").glob("*.wav")))
    config.update(
        model_name=MODEL,
        target_phrase=["ei byte"],
        n_samples=n_pos,
        n_samples_val=n_test,
        piper_sample_generator_path=str(train / "piper_stub"),
        output_dir=str(train),
        rir_paths=[str(train / "mit_rirs")],
        background_paths=[str(train / "background" / "esc50")],
        background_paths_duplication_rate=[1],
        false_positive_validation_data_path=str(train / "data" / "validation_set_features.npy"),
        feature_data_files={"ACAV100M_sample": str(train / "data" / "acav100m.npy")},
        batch_n_per_class={"ACAV100M_sample": 1024, "adversarial_negative": 50, "positive": 50},
        augmentation_rounds=1,
        steps=STEPS,
    )
    (train / f"{MODEL}.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")


def patched_train_script(train: Path) -> Path:
    """train.py with the two things that break on Windows / without tensorflow switched off."""
    import openwakeword  # noqa: PLC0415 - only the training venv has it

    source = (Path(openwakeword.__file__).parent / "train.py").read_text(encoding="utf-8")
    # worker processes must pickle lambdas and a generator: impossible when spawned on Windows
    source, workers = re.subn(r"num_workers=n_cpus, prefetch_factor=\d+", "num_workers=0", source)
    # the tflite export needs tensorflow + onnx_tf, and runs after the .onnx is already written
    marker = "def convert_onnx_to_tflite(onnx_model_path, output_path):\n"
    if workers < 1 or marker not in source:
        raise SystemExit("train.py changed upstream: re-check the Windows patch")
    entry = "if __name__ == '__main__':"
    if entry not in source:
        raise SystemExit("train.py changed upstream: re-check the Windows patch")
    source = source.replace(marker, marker + "    return\n").replace(entry, TRIM_PATCH + entry, 1)
    patched = train / "train_patched.py"
    patched.write_text(source, encoding="utf-8")
    return patched


def train_model(train: Path) -> None:
    import openwakeword  # noqa: PLC0415 - only the training venv has it

    preflight()
    openwakeword.utils.download_models()
    script = patched_train_script(train)
    for flag in ("--augment_clips", "--train_model"):
        subprocess.run(  # noqa: S603 - our own interpreter and script
            [sys.executable, str(script), "--training_config", str(train / f"{MODEL}.yaml"), flag],
            cwd=train,
            check=True,
        )
    print(f"model: {train / (MODEL + '.onnx')}")


if __name__ == "__main__":
    command, directory = sys.argv[1], Path(sys.argv[2]).resolve()
    {"prepare": prepare, "train": train_model}[command](directory)
