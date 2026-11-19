// Run: node --test tests/web/lynus.test.mjs
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { coreState, isActive, noteLook, phaseText, placeholder, route } from '../../web/lynus.js';

test('only briefing and working are active', () => {
  assert.equal(isActive('briefing'), true);
  assert.equal(isActive('working'), true);
  for (const p of ['off', 'done', 'stopped', 'failed']) assert.equal(isActive(p), false);
});

test('phaseText names the phase, the turn while working, and the project', () => {
  assert.equal(phaseText({ phase: 'off', turns: 0, project: null }), '');
  assert.equal(phaseText({ phase: 'briefing', turns: 0, project: 'Byte' }), 'conversando · Byte');
  assert.equal(phaseText({ phase: 'working', turns: 3, project: 'Byte' }), 'trabalhando · turno 3 · Byte');
  assert.equal(phaseText({ phase: 'done', turns: 9, project: 'Byte' }), 'concluído · Byte');
  assert.equal(phaseText(null), '');
});

test('noteLook maps roles to message styles', () => {
  assert.deepEqual(noteLook('owner'), { kind: 'me', who: 'você' });
  assert.deepEqual(noteLook('claude'), { kind: 'claude', who: '→claude' });
  assert.deepEqual(noteLook('weird'), { kind: 'system', who: 'sys' });
});

test('route: Byte does the intake, then the chat belongs to Lynus while active', () => {
  assert.deepEqual(route({ target: 'byte', phase: 'working', handoff: false }), { shown: 'byte', sendTo: 'byte' });
  assert.deepEqual(route({ target: 'lynus', phase: 'off', handoff: true }), { shown: 'byte', sendTo: 'byte' });
  assert.deepEqual(route({ target: 'lynus', phase: 'briefing', handoff: false }), { shown: 'lynus', sendTo: 'lynus' });
  assert.deepEqual(route({ target: 'lynus', phase: 'done', handoff: false }), { shown: 'lynus', sendTo: 'byte' });
});

test('placeholder tells the owner who is listening', () => {
  assert.equal(placeholder({ shown: 'byte', sendTo: 'byte' }, true), 'Diga ao Byte o projeto e a tarefa…');
  assert.equal(placeholder({ shown: 'lynus', sendTo: 'lynus' }, false), 'Escreva para o Lynus…');
  assert.equal(placeholder({ shown: 'byte', sendTo: 'byte' }, false), 'Escreva para o Byte…');
});

test('coreState follows the phase, and thinking wins while active', () => {
  assert.equal(coreState('off', false), 'idle');
  assert.equal(coreState('briefing', false), 'talking');
  assert.equal(coreState('briefing', true), 'thinking');
  assert.equal(coreState('working', false), 'working');
  assert.equal(coreState('done', true), 'done');
  assert.equal(coreState('failed', false), 'failed');
  assert.equal(coreState('stopped', false), 'idle');
});
