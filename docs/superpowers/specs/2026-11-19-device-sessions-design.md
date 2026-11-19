# Spec 8 — Device sessions (sign in once per device)

## Intent

The panel runs on the owner's devices against one fixed server. Typing the API token on every
visit is friction, and keeping the master token in a browser is the wrong thing to store.
Each device signs in once with `BYTE_API_TOKEN` and keeps a revocable refresh token instead.

## Decided (owner, 2026-11-19)

- Server address is a constant in `frontend/config.js` (`https://192.168.0.44`); no field.
- `POST /api/v1/auth/login` — master token in `Authorization` → `{access_token, refresh_token,
  expires_in}`. Access: random, 1 h, kept only in memory (server and tab). Refresh: random,
  valid while used at least every 180 days, kept in the device's `localStorage`.
- `POST /api/v1/auth/refresh` `{refresh_token}` → new access token, same refresh token (no
  rotation: two tabs refreshing at once must not sign each other out). Unknown/idle → 401.
- `POST /api/v1/auth/logout` `{refresh_token}` → 204, grant revoked.
- Every HTTP route and WebSocket accepts the master token (ESP32, voice, scripts) or a valid
  access token. Master is checked first.
- Refresh grants persist as SHA-256 hashes only, in `data/devices.json` (JSON file behind
  `DeviceGrantStorePort`; Postgres later behind the same port). Access tokens live in memory;
  a restart makes the panel refresh once.
- Stdlib only (`secrets`, `hashlib`, `hmac`). No JWT. No users or passwords: one owner.

## Panel

`frontend/session.js` holds the flow: refresh before the first call when only a refresh token
exists, refresh once and retry on a 401, refresh ahead of expiry (80 % of `expires_in`) so
WebSockets reconnect with a live token, and drop to the token screen only when refresh fails.
Sign-out calls logout and forgets the refresh token.

## Not in scope

Refresh rotation, per-device names or a device list UI, multi-user.
