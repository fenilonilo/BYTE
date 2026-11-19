// Run: node --test frontend/tests/session.test.mjs
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { createSession } from '../session.js';

function memoryStorage() {
  const m = new Map();
  return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, v), removeItem: (k) => m.delete(k) };
}

// A fake server: master "M", refresh tokens it knows, a call log.
function fakeServer() {
  let n = 0;
  const known = new Set();
  const calls = [];
  const post = async (path, body, bearer) => {
    calls.push(path);
    if (path === '/auth/login') {
      if (bearer !== 'M') return { status: 401, json: null };
      known.add('R');
      return { status: 200, json: { access_token: `A${++n}`, refresh_token: 'R', expires_in: 3600 } };
    }
    if (path === '/auth/refresh') {
      return known.has(body.refresh_token)
        ? { status: 200, json: { access_token: `A${++n}`, refresh_token: body.refresh_token, expires_in: 3600 } }
        : { status: 401, json: null };
    }
    if (path === '/auth/logout') { known.delete(body.refresh_token); return { status: 204, json: null }; }
    throw new Error(path);
  };
  return { post, calls, known };
}

const quiet = { schedule: () => 0, cancel: () => {} };

test('login keeps the refresh token on the device and the access token in memory', async () => {
  const storage = memoryStorage();
  const s = createSession({ storage, post: fakeServer().post, ...quiet });
  assert.equal(await s.login('wrong'), 401);
  assert.equal(s.signedIn(), false);
  assert.equal(await s.login('M'), 200);
  assert.equal(s.access(), 'A1');
  assert.equal(storage.getItem('byte.refresh'), 'R');
});

test('a new page with only the refresh token renews without the token screen', async () => {
  const server = fakeServer();
  server.known.add('R');
  const storage = memoryStorage();
  storage.setItem('byte.refresh', 'R');
  const s = createSession({ storage, post: server.post, ...quiet });
  assert.equal(s.signedIn(), true);
  assert.equal(s.access(), null);
  assert.equal(await s.renew(), true);
  assert.equal(s.access(), 'A1');
});

test('concurrent renewals share one request', async () => {
  const server = fakeServer();
  server.known.add('R');
  const storage = memoryStorage();
  storage.setItem('byte.refresh', 'R');
  const s = createSession({ storage, post: server.post, ...quiet });
  await Promise.all([s.renew(), s.renew(), s.renew()]);
  assert.equal(server.calls.filter((c) => c === '/auth/refresh').length, 1);
});

test('a revoked refresh token signs the device out', async () => {
  const storage = memoryStorage();
  storage.setItem('byte.refresh', 'gone');
  const s = createSession({ storage, post: fakeServer().post, ...quiet });
  assert.equal(await s.renew(), false);
  assert.equal(s.signedIn(), false);
  assert.equal(storage.getItem('byte.refresh'), null);
});

test('a network failure keeps the device signed in', async () => {
  const storage = memoryStorage();
  storage.setItem('byte.refresh', 'R');
  const post = async () => { throw new Error('offline'); };
  const s = createSession({ storage, post, ...quiet });
  await assert.rejects(s.renew());
  assert.equal(s.signedIn(), true);
});

test('renewal is scheduled ahead of expiry', async () => {
  const delays = [];
  const s = createSession({
    storage: memoryStorage(), post: fakeServer().post, schedule: (_, ms) => delays.push(ms), cancel: () => {},
  });
  await s.login('M');
  assert.deepEqual(delays, [3600 * 800]);
});

test('logout revokes on the server and forgets locally', async () => {
  const server = fakeServer();
  const storage = memoryStorage();
  const s = createSession({ storage, post: server.post, ...quiet });
  await s.login('M');
  await s.logout();
  assert.equal(s.signedIn(), false);
  assert.equal(server.known.has('R'), false);
});
