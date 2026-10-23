// Run: node --test tests/web/project-term.test.mjs
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { clampBackoff, paneView } from '../../web/project-term.js';

test('no open project shows the activity log', () => {
  assert.deepEqual(paneView(null), { mode: 'log', title: 'byte@casa: ~' });
});

test('an open project shows the xterm view under its name', () => {
  assert.deepEqual(paneView('FinFlow'), { mode: 'xterm', title: 'byte@casa: ~/FinFlow' });
});

test('reconnect backoff doubles from 1 s and stops at 30 s', () => {
  assert.equal(clampBackoff(0), 1000);
  assert.equal(clampBackoff(1000), 2000);
  assert.equal(clampBackoff(20_000), 30_000);
  assert.equal(clampBackoff(30_000), 30_000);
});
