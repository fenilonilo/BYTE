// Run: node --test frontend/tests/server.test.mjs
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { apiBase, wsBase } from '../server.js';

const page = { origin: 'http://localhost:5500' };

test('the API and the sockets follow the chosen server', () => {
  assert.equal(apiBase('https://192.168.0.44', page), 'https://192.168.0.44/api/v1');
  assert.equal(wsBase('https://192.168.0.44', page), 'wss://192.168.0.44/api/v1');
  assert.equal(wsBase('http://127.0.0.1:8000', page), 'ws://127.0.0.1:8000/api/v1');
});

test('no server falls back to the page that served the panel', () => {
  assert.equal(apiBase('', page), 'http://localhost:5500/api/v1');
  assert.equal(wsBase('', page), 'ws://localhost:5500/api/v1');
});
