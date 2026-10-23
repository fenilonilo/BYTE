// The project terminal: a real `claude` running on the server, shown with xterm.js.
// The process belongs to the server; this view only attaches to it (WS /api/v1/ws/terminal).

const REPLACED = 4000; // another panel took the terminal: do not fight it
const UNAVAILABLE = 1008; // no claude / pty on this server

export const paneView = (project) => (project
  ? { mode: 'xterm', title: `byte@casa: ~/${project}` }
  : { mode: 'log', title: 'byte@casa: ~' });

export const clampBackoff = (ms) => Math.min(Math.max(ms * 2, 1000), 30_000);

/**
 * Keeps one socket open while the panel is unlocked. `onState(project|null)` fires on every
 * open, close or exit. Returns `{ close() }`. xterm.js and its fit addon are UMD globals.
 */
export function connectProjectTerm({ getToken, el, onState }) {
  const encoder = new TextEncoder();
  let ws = null;
  let term = null;
  let fit = null;
  let backoff = 0;
  let timer = null;
  let closed = false;

  const sendSize = () => {
    if (!term || ws?.readyState !== WebSocket.OPEN || el.hidden) return;
    fit.fit();
    ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
  };

  function ensureTerm() {
    if (term) return;
    term = new globalThis.Terminal({
      cursorBlink: true,
      fontFamily: '"Geist Mono", ui-monospace, monospace',
      fontSize: 13,
      scrollback: 5000,
      theme: { background: '#00000000' },
      allowTransparency: true,
    });
    fit = new globalThis.FitAddon.FitAddon();
    term.loadAddon(fit);
    term.open(el);
    term.onData((d) => { if (ws?.readyState === WebSocket.OPEN) ws.send(encoder.encode(d)); });
    new ResizeObserver(sendSize).observe(el);
  }

  function connect() {
    if (closed) return;
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
    let socket;
    try {
      socket = new WebSocket(`${scheme}://${location.host}/api/v1/ws/terminal`, ['bearer', getToken() || '']);
    } catch { return; } // a token a subprotocol cannot carry: the voice path reports it already
    socket.binaryType = 'arraybuffer';
    ws = socket;
    socket.onopen = () => { backoff = 0; };
    socket.onmessage = (e) => {
      if (typeof e.data !== 'string') return term?.write(new Uint8Array(e.data));
      let msg;
      try { msg = JSON.parse(e.data); } catch { return; }
      if (msg.type !== 'state') return;
      if (msg.project) {
        ensureTerm();
        term.reset(); // the scrollback replay that follows redraws the screen
      }
      onState(msg.project ?? null);
      if (msg.project) requestAnimationFrame(sendSize); // after the pane became visible
    };
    socket.onclose = (e) => {
      if (ws !== socket) return;
      ws = null;
      if (closed || e.code === REPLACED || e.code === UNAVAILABLE) return;
      backoff = clampBackoff(backoff);
      timer = setTimeout(connect, backoff);
    };
  }

  connect();
  return {
    focus: () => term?.focus(),
    close() {
      closed = true;
      clearTimeout(timer);
      ws?.close();
      ws = null;
      term?.dispose();
      term = null;
    },
  };
}
