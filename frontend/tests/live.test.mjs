// Pure pieces of the browser voice client. Run: node --test tests/web/live.test.mjs
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { Resampler, floatToPcm16 } from '../../web/mic-worklet.js';
import {
  IDLE_SECONDS, IDLE_WARN_SECONDS, closeText, createDwell, createSpeechGate, idlePhase, pcm16ToFloat, rms,
} from '../../web/live.js';

const sine = (rate, hz, seconds) => Float32Array.from({ length: rate * seconds }, (_, i) => 0.5 * Math.sin((2 * Math.PI * hz * i) / rate));

function zeroCrossings(pcm) {
  let n = 0;
  for (let i = 1; i < pcm.length; i++) if ((pcm[i - 1] < 0) !== (pcm[i] < 0)) n++;
  return n;
}

test('48 kHz to 24 kHz keeps the length ratio, the pitch and the level', () => {
  const out = new Resampler(48000, 24000).push(sine(48000, 440, 1));
  assert.equal(out.length, 24000);
  assert.ok(Math.abs(zeroCrossings(out) - 880) <= 2);
  assert.ok(Math.abs(rms(out) - 0.5 / Math.SQRT2) < 0.01);
});

test('fractional ratios (44.1 kHz to 16 kHz) stay exact across blocks', () => {
  const r = new Resampler(44100, 16000);
  const input = sine(44100, 300, 2);
  let total = 0;
  for (let i = 0; i < input.length; i += 128) total += r.push(input.subarray(i, i + 128)).length;
  assert.ok(Math.abs(total - 32000) <= 1);
});

test('the box filter attenuates content above the new Nyquist', () => {
  const low = rms(new Resampler(48000, 16000).push(sine(48000, 1000, 1)));
  const high = rms(new Resampler(48000, 16000).push(sine(48000, 15000, 1)));
  assert.ok(high < low / 2, `15 kHz leaked: ${high} vs ${low}`);
});

test('PCM16 encoding clips and round-trips little-endian', () => {
  assert.deepEqual([...floatToPcm16([2, -2, 0, 0.5])], [32767, -32768, 0, 16383]);
  const bytes = new Uint8Array([0x00, 0x80, 0xff, 0x7f, 0x01]); // -32768, 32767, a stray odd byte
  const back = pcm16ToFloat(bytes.buffer);
  assert.equal(back.length, 2);
  assert.equal(back[0], -1);
  assert.ok(back[1] > 0.999);
});

test('close codes map to pt-BR messages, a normal close to none', () => {
  assert.match(closeText(4000, true), /Outra sessão/);
  assert.match(closeText(1006, false), /token recusado/);
  assert.match(closeText(1008, true), /1008/);
  assert.equal(closeText(1000, true), null);
  assert.match(closeText(1006, true), /caiu/);
});

test('a shown live state holds for the dwell, then catches up to the latest wish', () => {
  const d = createDwell(0.25);
  assert.equal(d.update('connecting', 0), 'connecting');
  assert.equal(d.update('listening', 0.01), 'listening'); // leaving connecting is never held
  assert.equal(d.update('thinking', 0.1), null); // too soon after listening
  assert.equal(d.update('speaking', 0.2), null);
  assert.equal(d.update('speaking', 0.26), 'speaking'); // the blip through thinking never showed
  assert.equal(d.update('listening', 0.3), null);
  assert.equal(d.update('speaking', 0.4), null); // wish went back before the dwell: no flicker
  assert.equal(d.update('off', 0.41), 'off'); // ending is immediate
});

test('the speech gate has hysteresis and reports the end of speech once', () => {
  const g = createSpeechGate(0.03, 0.015, 0.7);
  assert.equal(g.push(0.02, 0), null); // below ON: not speech yet
  assert.equal(g.push(0.04, 0.1), 'speech');
  assert.equal(g.push(0.02, 0.2), 'speech'); // between OFF and ON keeps going
  assert.equal(g.push(0.01, 0.3), null); // dropped below OFF
  assert.equal(g.push(0.02, 0.4), null); // needs ON again to restart
  assert.equal(g.push(0.0, 0.95), 'end');
  assert.equal(g.push(0.0, 2), null);
});

test('the idle countdown warns in its last seconds and ends at the limit', () => {
  assert.equal(IDLE_SECONDS, 12);
  assert.equal(idlePhase(0), 'quiet');
  assert.equal(idlePhase(IDLE_SECONDS - IDLE_WARN_SECONDS - 0.01), 'quiet');
  assert.equal(idlePhase(IDLE_SECONDS - IDLE_WARN_SECONDS), 'warn');
  assert.equal(idlePhase(IDLE_SECONDS - 0.01), 'warn');
  assert.equal(idlePhase(IDLE_SECONDS), 'end');
});
