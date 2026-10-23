// Run: node --test tests/web/time.test.mjs
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { countdown, elapsed, urgency } from '../../web/time.js';

test('countdown picks the coarsest useful unit', () => {
  assert.equal(countdown(0), 'agora');
  assert.equal(countdown(-5000), 'agora');
  assert.equal(countdown(400), '0:01'); // a partial second still counts as one left
  assert.equal(countdown(12 * 60_000 + 4000), '12:04');
  assert.equal(countdown(3 * 3600_000 + 7 * 60_000), '3h 07m');
  assert.equal(countdown(2 * 86400_000 + 4 * 3600_000), '2d 4h');
});

test('urgency turns soon in the last five minutes and due at zero', () => {
  assert.equal(urgency(6 * 60_000), '');
  assert.equal(urgency(5 * 60_000), 'soon');
  assert.equal(urgency(0), 'due');
});

test('elapsed shows hours only when there are any', () => {
  assert.equal(elapsed(63_000), '01:03');
  assert.equal(elapsed(3723_000), '1:02:03');
});
