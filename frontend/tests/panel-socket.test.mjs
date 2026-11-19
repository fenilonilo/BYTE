// Run: node --test tests/web/panel-socket.test.mjs
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { panelSocket } from '../../web/panel-socket.js';

class FakeSocket {
  constructor() { this.closed = false; }
  close() { this.closed = true; }
}

function harness() {
  const sockets = [];
  const timers = [];
  const seen = { weather: 0, lynus: 0, open: 0 };
  const handle = panelSocket({
    open: () => { const s = new FakeSocket(); sockets.push(s); return s; },
    onWeather: () => seen.weather++,
    onLynus: () => seen.lynus++,
    onOpen: () => seen.open++,
    setTimer: (fn, ms) => { timers.push({ fn, ms }); return timers.length; },
    clearTimer: () => {},
  });
  return { handle, sockets, timers, seen, last: () => sockets[sockets.length - 1] };
}

test('open and weather messages reach the callbacks; junk is ignored', () => {
  const h = harness();
  h.last().onopen();
  assert.equal(h.seen.open, 1);
  h.last().onmessage({ data: '{"type":"weather"}' });
  h.last().onmessage({ data: 'not json' });
  h.last().onmessage({ data: '{"type":"other"}' });
  h.last().onmessage({ data: new ArrayBuffer(2) });
  assert.equal(h.seen.weather, 1);
  h.last().onmessage({ data: '{"type":"lynus"}' });
  assert.equal(h.seen.lynus, 1);
  assert.equal(h.seen.weather, 1);
});

test('a dropped link reconnects with growing backoff, reset on open', () => {
  const h = harness();
  h.last().onclose({ code: 1006 });
  assert.equal(h.timers.at(-1).ms, 1000);
  h.timers.at(-1).fn();
  assert.equal(h.sockets.length, 2);
  h.last().onclose({ code: 1006 });
  assert.equal(h.timers.at(-1).ms, 2000);
  h.timers.at(-1).fn();
  h.last().onopen();
  h.last().onclose({ code: 1006 });
  assert.equal(h.timers.at(-1).ms, 1000);
});

test('backoff is capped at 30 s', () => {
  const h = harness();
  for (let i = 0; i < 10; i++) { h.last().onclose({ code: 1006 }); h.timers.at(-1).fn(); }
  assert.equal(h.timers.at(-1).ms, 30000);
});

test('replaced (4000) or refused (1008) does not reconnect', () => {
  for (const code of [4000, 1008]) {
    const h = harness();
    h.last().onclose({ code });
    assert.equal(h.timers.length, 0, `code ${code}`);
  }
});

test('close() stops for good', () => {
  const h = harness();
  h.handle.close();
  assert.ok(h.last().closed);
  h.last().onclose({ code: 1000 });
  assert.equal(h.timers.length, 0);
});

test('an open() that throws (bad token characters) does not loop', () => {
  let calls = 0;
  const timers = [];
  panelSocket({ open: () => { calls++; throw new SyntaxError('bad'); }, onWeather() {}, onOpen() {}, setTimer: (fn, ms) => timers.push(ms), clearTimer() {} });
  assert.equal(calls, 1);
  assert.equal(timers.length, 0);
});
