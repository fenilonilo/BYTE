# Voice client

## What it is

`voice/` is a small daemon that runs on the machine with the microphone and speaker (an Ubuntu
Server laptop). It listens for the wake word "Ei Byte" locally with openWakeWord; nothing leaves the
machine while idle. After the wake word it opens `WS /live` on the Byte API, streams microphone
audio, and plays the agent's reply. The microphone is muted while the agent speaks (half-duplex,
no barge-in). Once the agent finishes a turn, the client closes the session after
`BYTE_VOICE_IDLE_SECONDS` of silence (before the first finished turn, the server's own 60 s idle
limit applies). A new wake word opens a new session. Design:
`docs/superpowers/specs/2026-10-05-voice-client-wake-word-design.md`.

Settings (env, `BYTE_` prefix): `BYTE_API_TOKEN` (same token as the server, at least 32 chars),
`BYTE_VOICE_WAKE_MODEL` (openWakeWord model name such as `hey_jarvis`, or a path to an `.onnx`),
`BYTE_VOICE_URL` (default `ws://127.0.0.1:8000/api/v1/live`), `BYTE_VOICE_THRESHOLD` (0.5),
`BYTE_VOICE_IDLE_SECONDS` (8), `BYTE_VOICE_SEGMENT` (`auto`), `BYTE_VOICE_INPUT_DEVICE`,
`BYTE_VOICE_OUTPUT_DEVICE`, `BYTE_VOICE_LOG_LEVEL`.

Known limitation: an utterance that starts after a turn and runs longer than the idle timeout is
cut. Raise `BYTE_VOICE_IDLE_SECONDS` if that happens.

## Install on Ubuntu Server

The API runs in Docker on the same host and listens on loopback; the voice client runs on the
host (not in Docker) so it can reach the sound card. Voice dependencies are not in the lock file
used by the Docker image.

```bash
sudo apt install libportaudio2 alsa-utils python3.12-venv git
sudo useradd --system --create-home --shell /usr/sbin/nologin byte
sudo usermod -aG audio byte
sudo git clone <your repository URL> /opt/byte
sudo chown -R byte:byte /opt/byte
cd /opt/byte
sudo -u byte python3.12 -m venv .venv
sudo -u byte .venv/bin/pip install -e ".[voice]"
sudo -u byte .venv/bin/pip install --no-deps openwakeword
sudo -u byte .venv/bin/pip install onnxruntime tqdm scikit-learn requests
sudo -u byte .venv/bin/python -c "import openwakeword; openwakeword.utils.download_models()"
```

openWakeWord is installed with `--no-deps` because its `tflite-runtime` dependency has no wheel
for Python 3.12/3.13 and is not needed with the onnx framework.

Put the settings in `/opt/byte/.env` (copy `.env.example`; at minimum `BYTE_API_TOKEN` and
`BYTE_VOICE_WAKE_MODEL`). The daemon reads this file itself from its working directory; the unit
does not inject it into the environment. Lock it down (it holds the API token; only its owner
should read it, and the `byte` user must own it), then install the service:

```bash
sudo chown byte:byte /opt/byte/.env
sudo chmod 600 /opt/byte/.env   # holds the API token: readable only by its owner
sudo cp deploy/byte-voice.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now byte-voice
journalctl -u byte-voice -f
```

## Choosing audio devices

```bash
arecord -l                       # capture devices
aplay -l                         # playback devices
.venv/bin/python -m sounddevice  # indexes and names as the client sees them
```

Set `BYTE_VOICE_INPUT_DEVICE` and `BYTE_VOICE_OUTPUT_DEVICE` to an index or a name. Built-in
codecs often cannot capture at 16 kHz on raw `hw:` devices. Use a `plughw:CARD=...,DEV=0` name
(or `default`) so ALSA converts the rate.

With the built-in mic and speaker, half-duplex means you cannot interrupt the agent while it
talks. A USB speakerphone or headset with hardware echo cancellation is the planned upgrade.

## Training the "Ei Byte" wake word (local)

The wake word is **"Ei Byte"** (two words fire far less on TV and conversation than "Byte"
alone). The trained model, `models/ei_byte.onnx`, is committed; this section is how it was made
and how to redo it.

**Why not the Colab notebook.** openWakeWord's notebook generates its clips with Piper TTS, whose
`piper-phonemize` package has no wheel for the Python 3.13 that Colab runs now, so the first cell
fails. It is also English-only. `train.py` can skip generation (`--generate_clips` is a separate
flag), so we feed it our own pt-BR clips and train locally.

Needs: an NVIDIA GPU (the first model took about 25 minutes on an RTX 4060 8 GB), about 30 GB of
free disk, the `uv`-managed Python 3.12, and internet for the datasets. Commands below are
for Git Bash; `<T>` is a training directory outside the repository, for example
`D:/Projetos/Byte/wakeword_train`.

### 1. Clips

```bash
pip install edge-tts soundfile sounddevice scipy numpy
python scripts/wakeword_clips.py          # ~900 synthetic pt-BR clips -> wakeword_data/ (30-60 min)
```

`wakeword_clips.py` uses Microsoft Edge TTS (online; only the phrases leave the machine) with the
three pt-BR voices, varying rate and pitch, plus near-miss negatives ("Ei Pedro", "bate aqui").
Edit `POSITIVE` there if you pronounce the name differently.

Then record **your own voice**; there are only three pt-BR voices, so these clips matter most. Each
command plays three low beeps, then a high beep before every take. Say the phrase right after it.
Takes with no clear speech are dropped and repeated.

```bash
python scripts/wakeword_record.py pos s1_normal 20     # normal voice, close to the mic
python scripts/wakeword_record.py pos s2_other 20      # the other pronunciation
python scripts/wakeword_record.py pos s3_far 20        # far from the mic, quieter
python scripts/wakeword_record.py pos s4_loud 20       # fast, louder, calling out
python scripts/wakeword_record.py neg s5_speech 90     # talk freely, TV on; never say the phrase
```

### 2. Training environment and data

```bash
T=D:/Projetos/Byte/wakeword_train; mkdir -p $T/data && cd $T
"$HOME/AppData/Roaming/uv/python/cpython-3.12.0-windows-x86_64-none/python.exe" -m venv venv
./venv/Scripts/python.exe -m pip install torch==2.5.0 torchaudio==2.5.0 \
    --index-url https://download.pytorch.org/whl/cu121
./venv/Scripts/python.exe -m pip install "numpy<2" "scipy==1.14.1" soundfile pyyaml tqdm requests \
    huggingface_hub datasets mutagen==1.47.0 torchinfo torchmetrics audiomentations \
    torch_audiomentations pronouncing onnx onnxruntime speechbrain acoustics
./venv/Scripts/python.exe -m pip install --no-deps openwakeword
B=https://huggingface.co/datasets/davidscripka/openwakeword_features/resolve/main
curl -L -o data/validation_set_features.npy $B/validation_set_features.npy             # 185 MB
curl -L -o data/acav100m.npy $B/openwakeword_features_ACAV100M_2000_hrs_16bit.npy      # 17 GB
curl -L -o data/esc50.zip https://github.com/karolpiczak/ESC-50/archive/master.zip     # 600 MB
curl -L -o base_config.yml \
    https://raw.githubusercontent.com/dscripka/openWakeWord/main/examples/custom_model.yml
```

`scipy` stays at 1.14.1: `acoustics` imports `scipy.special.sph_harm`, removed in scipy 1.17.
Python 3.12 and torch 2.5 are what openWakeWord's training code was written against.

### 3. Prepare and train

```bash
cd <repo>
$T/venv/Scripts/python.exe scripts/wakeword_train.py prepare $T
$T/venv/Scripts/python.exe scripts/wakeword_train.py train $T      # about 25 minutes
cp $T/ei_byte.onnx models/ei_byte.onnx
```

`prepare` splits the clips 85/15, removes identical TTS renders before the split, peak-normalises
your negatives, cuts them to 2 s, and writes each clip as several on-disk copies (your voice
counts 4x more): `train.py` makes one augmentation pass over the files, so `augmentation_rounds`
alone does nothing. `train` runs a patched copy of openWakeWord's `train.py` (written to
`<T>/train_patched.py`) with three Windows fixes: `num_workers=0` (the workers cannot pickle
lambdas under `spawn`), a `trim_mmap` that does not rewrite a file still memory-mapped, and no
tflite export (it needs tensorflow). The script stops if upstream `train.py` changed.

Set `BYTE_VOICE_WAKE_MODEL=models/ei_byte.onnx` (on the laptop: `/opt/byte/models/ei_byte.onnx`).

### 4. Check the model

Offline, on clips held out of training, the first model scored above 0.5 on 12/12 of the owner's
test takes and 41/44 synthetic ones, with 0/91 negatives above 0.5. Those clips come from the same
sessions as the training clips, so treat the result as optimistic. Live, on the microphone: every
phrase fired with scores of 0.8 to 0.95, and 60 seconds of normal speech gave no trigger (peak
0.10). Not yet measured: distance, a quiet voice, hours of TV, and near-miss words.

To retrain after more problems appear, record more clips with `wakeword_record.py` (it never
overwrites earlier takes) and run `prepare` and `train` again.

## Tuning

`BYTE_VOICE_THRESHOLD` (default 0.5): raise it if the wake word fires on TV or conversation,
lower it if it misses you. Keep a one-day tally of false triggers and misses before judging the
model.

## Troubleshooting

- "Invalid sample rate": the device cannot capture at 16 kHz. See the device notes above.
- `config error` at start: the message names the invalid settings. Fix them in `/opt/byte/.env`.
- No sound out: test with `aplay /usr/share/sounds/alsa/Front_Center.wav` as the `byte` user and
  confirm `id byte` lists the `audio` group.
- Service restarts in a loop: read `journalctl -u byte-voice`.

## Verify on the laptop

These checks have not been run on real hardware yet. Run them once before treating the voice
client as done:

1. Idle: with the service running and nobody speaking, it stays silent and opens no `/live`
   connection.
2. Wake and answer: say "Byte", ask something; the agent's spoken answer plays.
3. Mute while speaking: the microphone is not picked up while the agent talks (no self-trigger,
   no feedback loop).
4. Idle close: after the agent finishes and you stay silent, the session closes after about
   `BYTE_VOICE_IDLE_SECONDS` (8 s by default).
5. API restart recovery: restart the API container during a session; the client ends the
   session and a new wake word opens a fresh one.
6. Bad token: set a wrong `BYTE_API_TOKEN`; the client reports a clear authentication error in
   the journal, with no secrets in it.
7. Device error: if you get "Invalid sample rate", select a `plughw:` or `default` device as
   described above and confirm it then works.
