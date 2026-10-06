# Voice client

## What it is

`voice/` is a small daemon that runs on the machine with the microphone and speaker (an Ubuntu
Server laptop). It listens for the wake word "Byte" locally with openWakeWord; nothing leaves the
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

## Training the "Byte" wake word

Use openWakeWord's automatic training notebook (in the openWakeWord repository, run on Colab;
the plan names it `notebooks/automatic_model_training.ipynb`, from memory). Check the
openWakeWord repository README for current notebook and API names before following these steps.

1. Set the target phrase to `byte`.
2. Also train and test spelling variants that match pt-BR pronunciation (for example `baiti`,
   `bait`) and compare them.
3. The notebook outputs an `.onnx` file. Copy it to `/opt/byte/models/byte.onnx` and set
   `BYTE_VOICE_WAKE_MODEL=/opt/byte/models/byte.onnx`.
4. Optional: record 20 to 30 real samples of your own voice and train a custom verifier model
   (see the openWakeWord README) to cut false triggers.

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
