// Pure time helpers for the panel. Run: node --test tests/web/time.test.mjs

const pad = (n) => String(n).padStart(2, '0');

/** Time left until a reminder, read at a glance: "2d 4h", "3h 07m", "12:04", "agora". */
export function countdown(ms) {
  if (ms <= 0) return 'agora';
  const s = Math.ceil(ms / 1000);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${pad(m)}m`;
  return `${m}:${pad(s % 60)}`;
}

export const SOON_MS = 5 * 60_000;

/** 'due' once the time has come, 'soon' in the last five minutes, else ''. */
export const urgency = (ms) => (ms <= 0 ? 'due' : ms <= SOON_MS ? 'soon' : '');

/** Elapsed time as "1:02:03" (or "02:03" under an hour). */
export function elapsed(ms) {
  const s = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(s / 3600);
  return h ? `${h}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}` : `${pad(Math.floor(s / 60))}:${pad(s % 60)}`;
}
