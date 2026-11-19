// Run: node --test tests/web/weather.test.mjs
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { CONDITION_WORD, chart, dayLabel, hourLabel, rangeBar } from '../../web/weather.js';

test('hourLabel reads the hour from the string, never the browser zone', () => {
  assert.equal(hourLabel('2026-10-23T23:00:00-03:00'), '23h');
  assert.equal(hourLabel('2026-10-24T00:00:00+01:00'), '00h');
  assert.equal(hourLabel('2026-10-24T07:00-03:00'), '07h');
});

test('dayLabel says hoje for the first day and the weekday after', () => {
  assert.equal(dayLabel('2026-10-23', '2026-10-23'), 'hoje');
  assert.equal(dayLabel('2026-10-24', '2026-10-23'), 'sáb');
  assert.equal(dayLabel('2026-10-25', '2026-10-23'), 'dom');
  assert.equal(dayLabel('2026-10-26', '2026-10-23'), 'seg');
});

test('rangeBar scales each day across the week span', () => {
  const days = [{ low: 17, high: 27 }, { low: 18, high: 31 }, { low: 20, high: 25 }];
  assert.deepEqual(rangeBar(days[0], days), { left: 0, right: 28.57 });
  assert.deepEqual(rangeBar(days[1], days), { left: 7.14, right: 0 });
});

test('rangeBar with a flat week does not divide by zero', () => {
  const days = [{ low: 20, high: 20 }, { low: 20, high: 20 }];
  assert.deepEqual(rangeBar(days[0], days), { left: 0, right: 0 });
});

test('chart lays 24 hours inside the box and labels the peak', () => {
  const hours = Array.from({ length: 24 }, (_, i) => ({
    time: `2026-10-23T${String(i).padStart(2, '0')}:00:00-03:00`,
    temperature: 20 + (i === 15 ? 9.4 : i % 5),
    rain_chance: (i * 9) % 100,
  }));
  const c = chart(hours, 320, 84);
  assert.equal(c.bars.length, 24);
  const pairs = c.line.split(' ');
  assert.equal(pairs.length, 24);
  for (const pair of pairs) {
    const [x, y] = pair.split(',').map(Number);
    assert.ok(x >= 0 && x <= 320, `x ${x}`);
    assert.ok(y >= 0 && y <= 84, `y ${y}`);
  }
  for (const b of c.bars) assert.ok(b.y >= 0 && b.y + b.h <= 84 + 1e-9);
  assert.equal(c.peak.label, '29°');
  assert.equal(c.peak.hour, '15h');
});

test('chart survives a flat temperature line', () => {
  const hours = Array.from({ length: 24 }, (_, i) => ({ time: `2026-10-23T${String(i).padStart(2, '0')}:00-03:00`, temperature: 22, rain_chance: 0 }));
  const c = chart(hours, 320, 84);
  assert.ok(c.line.split(' ').every((p) => !p.includes('NaN')));
});

test('every condition has a word', () => {
  for (const k of ['clear', 'partly_cloudy', 'cloudy', 'fog', 'drizzle', 'rain', 'storm']) assert.ok(CONDITION_WORD[k]);
});
