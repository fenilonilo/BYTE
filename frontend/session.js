// Sign in once per device: the master token buys a refresh token kept on this device, which
// is traded for short access tokens kept only in memory. Run: node --test frontend/tests/session.test.mjs

const KEY = 'byte.refresh';

export function createSession({ storage, post, schedule = setTimeout, cancel = clearTimeout }) {
  let access = null;
  let timer = null;
  let inflight = null;

  const read = () => { try { return storage.getItem(KEY); } catch { return null; } };

  function keep(pair) {
    access = pair.access_token;
    try { storage.setItem(KEY, pair.refresh_token); } catch { /* private mode: this tab only */ }
    cancel(timer);
    // renew at 80 % of the lifetime so a reconnecting socket never offers a dead token
    timer = schedule(() => { renew().catch(() => {}); }, pair.expires_in * 800);
  }

  function forget() {
    access = null;
    cancel(timer);
    try { storage.removeItem(KEY); } catch { /* nothing kept */ }
  }

  async function login(master) {
    const res = await post('/auth/login', undefined, master);
    if (res.status === 200) keep(res.json);
    return res.status;
  }

  // true = a fresh access token; false = signed out. A network error throws and keeps the device.
  function renew() {
    inflight ??= (async () => {
      const refresh = read();
      if (!refresh) return false;
      const res = await post('/auth/refresh', { refresh_token: refresh });
      if (res.status === 200) { keep(res.json); return true; }
      if (res.status === 401 || res.status === 422) forget();
      return false;
    })().finally(() => { inflight = null; });
    return inflight;
  }

  async function logout() {
    const refresh = read();
    forget();
    if (refresh) await post('/auth/logout', { refresh_token: refresh }).catch(() => {});
  }

  return { access: () => access, signedIn: () => Boolean(access || read()), login, renew, logout };
}
