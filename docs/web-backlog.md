# Web panel — backlog (from live testing, 2026-10-06)

## Spotify
Observed on the real setup (Tuya, ThinQ and Spotify adapters, panel with `--web`):

- `play_music` fails with `UnknownMusicDeviceError` and `control_music` with `MusicError` while the
  Connect device (`BatCaverna`) is asleep. `GET /me/player/devices` returns an empty list then.
  Waking it from the Spotify app fixes it. Not a panel bug.
- Todo:
  1. Panel message for that case: "<device> está offline. Abra o Spotify nele e tente de novo."
     instead of the raw error.
  2. Device picker in the Music section: list the online Connect devices
     (`MusicPort.devices()`), choose one, fall back to `BYTE_SPOTIFY_DEVICE`.
  3. Failure log gets a short category (`guard`, `offline`, `validation`, `upstream`), never content.
     `set_light` failing 2 s after a success looked like the 5 s guard but the log could not say.

## Still in memory (not Google yet)
Agenda and expenses use the in-memory adapters: they vanish on restart. Google Calendar / Sheets
adapters are a later spec.

## Done in this round
- Chat confirmed working with a real key (`chat.start` / `chat.done` ~1 s).
- Lights, climate, music (device awake) confirmed working from the panel.
