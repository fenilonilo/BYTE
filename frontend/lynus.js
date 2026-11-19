// Pure helpers for the Lynus chat. Run: node --test tests/web/lynus.test.mjs
// Lynus drives Claude Code on its own; the panel only shows it and talks to it.

/** What the panel sends Byte so Byte asks for the project and the task (Spec 5). */
export const HANDOFF = 'Quero passar uma tarefa para o Lynus.';

const PHASE = {
  off: 'livre', briefing: 'conversando', working: 'trabalhando',
  done: 'concluído', stopped: 'parado', failed: 'falhou',
};

export const isActive = (phase) => phase === 'briefing' || phase === 'working';

/** The chip next to the switch: "trabalhando · turno 3 · FinFlow". */
export function phaseText(view) {
  if (!view || view.phase === 'off') return '';
  const turn = view.phase === 'working' && view.turns ? ` · turno ${view.turns}` : '';
  return `${PHASE[view.phase] ?? view.phase}${turn}${view.project ? ` · ${view.project}` : ''}`;
}

const NOTE = {
  owner: { kind: 'me', who: 'você' },
  lynus: { kind: 'agent', who: 'lynus' },
  claude: { kind: 'claude', who: '→claude' },
  system: { kind: 'system', who: 'sys' },
};

/** How one note is drawn: the message class and the name in the left column. */
export const noteLook = (role) => NOTE[role] ?? NOTE.system;

/**
 * Who gets what the owner types, and which conversation is on screen.
 * `target` is the switch; `handoff` is true while Byte is still asking for project and task.
 */
export function route({ target, phase, handoff }) {
  const lynusShown = target === 'lynus' && !handoff && phase !== 'off';
  return {
    shown: lynusShown ? 'lynus' : 'byte',
    sendTo: lynusShown && isActive(phase) ? 'lynus' : 'byte',
  };
}

export const placeholder = ({ shown, sendTo }, handoff) => {
  if (handoff) return 'Diga ao Byte o projeto e a tarefa…';
  if (sendTo === 'lynus') return 'Escreva para o Lynus…';
  return shown === 'lynus' ? 'Lynus terminou. Escreva ao Byte para outra tarefa…' : 'Escreva para o Byte…';
};

/** Which animation Lynus's core plays for its phase. */
export function coreState(phase, thinking) {
  if (phase === 'failed') return 'failed';
  if (phase === 'done') return 'done';
  if (!isActive(phase)) return 'idle';
  if (thinking) return 'thinking';
  return phase === 'working' ? 'working' : 'talking';
}
