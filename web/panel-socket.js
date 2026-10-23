// The panel's push link (WS /api/v1/ws/panel). Run: node --test tests/web/panel-socket.test.mjs
// The server only says "something changed"; the panel reads the truth over HTTP.

const FIRST_DELAY = 1000;
const MAX_DELAY = 30_000;
const NO_RETRY = new Set([4000, 1008]); // replaced by another panel, or the token was refused

/** `open()` returns a WebSocket-like object. Returns `{close()}`. */
export function panelSocket({ open, onWeather, onOpen, setTimer = setTimeout, clearTimer = clearTimeout }) {
  let socket = null;
  let timer = null;
  let delay = FIRST_DELAY;
  let stopped = false;

  function connect() {
    timer = null;
    try {
      socket = open();
    } catch { // a token a subprotocol cannot carry: the voice path reports it already
      stopped = true;
      return;
    }
    socket.onopen = () => { delay = FIRST_DELAY; onOpen(); };
    socket.onmessage = (e) => {
      if (typeof e.data !== 'string') return;
      let message;
      try { message = JSON.parse(e.data); } catch { return; }
      if (message?.type === 'weather') onWeather();
    };
    socket.onclose = (e) => {
      if (stopped || NO_RETRY.has(e.code)) return;
      timer = setTimer(connect, delay);
      delay = Math.min(delay * 2, MAX_DELAY);
    };
  }

  connect();
  return {
    close() {
      stopped = true;
      if (timer !== null) clearTimer(timer);
      socket?.close();
    },
  };
}
