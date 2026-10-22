// The panel's terminal: an activity log (voice, actions, alerts) plus a few local commands.
// Nothing here talks to the network; commands are handlers supplied by app.js.

const MAX_LINES = 400;
const hms = () => new Date().toLocaleTimeString('pt-BR');

/**
 * `commands` maps a name to {help, run(args, term)}. `run` may return a string or a promise of one.
 * `log(tag, text, kind)` kinds: '' | 'error' | 'voice' | 'alert' | 'cmd'.
 */
export function createTerminal({ out, form, input, commands }) {
  const history = [];
  let at = 0;

  function log(tag, text, kind = '') {
    const line = document.createElement('p');
    line.className = `tl ${kind}`;
    const time = document.createElement('span');
    time.className = 'tt';
    time.textContent = hms();
    const label = document.createElement('span');
    label.className = 'tg';
    label.textContent = tag;
    const body = document.createElement('span');
    body.className = 'tb';
    body.textContent = text;
    line.append(time, label, body);
    // Follow new lines only when the owner has not scrolled up to read.
    const stick = out.scrollHeight - out.scrollTop - out.clientHeight < 40;
    out.append(line);
    while (out.childElementCount > MAX_LINES) out.firstElementChild.remove();
    if (stick) out.scrollTop = out.scrollHeight;
  }

  const clear = () => out.replaceChildren();

  async function exec(raw) {
    const [name, ...args] = raw.trim().split(/\s+/);
    log('$', raw.trim(), 'cmd');
    if (name === 'clear' || name === 'cls') return clear();
    if (name === 'help' || name === 'ajuda') {
      const width = Math.max(...Object.keys(commands).map((k) => k.length), 5);
      for (const [k, c] of Object.entries({ help: { help: 'esta lista' }, clear: { help: 'limpa a tela' }, ...commands })) {
        log('', `${k.padEnd(width)}  ${c.help}`);
      }
      return;
    }
    const cmd = commands[name.toLowerCase()];
    if (!cmd) return log('sh', `comando desconhecido: ${name}. Digite help.`, 'error');
    try {
      const res = await cmd.run(args);
      if (res) res.split('\n').forEach((l) => log('', l));
    } catch (err) {
      log(name, err.message || String(err), 'error');
    }
  }

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const raw = input.value;
    input.value = '';
    if (!raw.trim()) return;
    if (history[history.length - 1] !== raw) history.push(raw);
    at = history.length;
    exec(raw);
  });
  input.addEventListener('keydown', (e) => {
    if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;
    e.preventDefault();
    at = Math.max(0, Math.min(history.length, at + (e.key === 'ArrowUp' ? -1 : 1)));
    input.value = history[at] ?? '';
  });
  // Clicking anywhere in the log focuses the prompt, like a real console (unless selecting text).
  out.addEventListener('click', () => { if (!getSelection()?.toString()) input.focus({ preventScroll: true }); });

  return { log, clear, wipe: () => { clear(); history.length = 0; at = 0; input.value = ''; } };
}
