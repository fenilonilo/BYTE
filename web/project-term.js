// The project terminal: a real `claude` running on the server, shown with xterm.js.
// The process belongs to the server; this view only attaches to it (WS /api/v1/ws/terminal).

const REPLACED = 4000; // another panel took the terminal: do not fight it
const UNAVAILABLE = 1008; // no claude / pty on this server

export const paneView = (project) => (project
  ? { mode: 'xterm', title: `byte@casa: ~/${project}` }
  : { mode: 'log', title: 'byte@casa: ~' });

export const clampBackoff = (ms) => Math.min(Math.max(ms * 2, 1000), 30_000);

// The panel palette (style.css :root) mapped onto the 16 ANSI colours, so claude's output reads
// as part of the panel instead of a stock VS Code terminal.
const THEME = {
  background: '#0d0c0a',
  foreground: '#ebe5d9',
  cursor: '#e3a548',
  cursorAccent: '#0d0c0a',
  selectionBackground: 'rgba(227, 165, 72, 0.28)',
  black: '#23201b',
  red: '#e2826a',
  green: '#9cc3a2',
  yellow: '#e3a548',
  blue: '#8fa8c8',
  magenta: '#c49bb8',
  cyan: '#8cbfb8',
  white: '#d6cfc2',
  brightBlack: '#6f685d',
  brightRed: '#eb9b86',
  brightGreen: '#b4d4b8',
  brightYellow: '#ecb460',
  brightBlue: '#a9bed8',
  brightMagenta: '#d4b2ca',
  brightCyan: '#a7d0ca',
  brightWhite: '#f5f0e6',
};
const FONT = '"Geist Mono", ui-monospace, "Cascadia Mono", Consolas, monospace';

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
      fontFamily: FONT,
      fontSize: matchMedia('(max-width: 559px)').matches ? 12 : 13,
      fontWeightBold: 600,
      scrollback: 5000,
      theme: THEME,
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

  // xterm measures its cell once: open it with the web font in, not the fallback.
  document.fonts.load(`13px ${FONT}`).finally(connect);
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
