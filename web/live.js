// Spoken conversation over WS /api/v1/live, the browser twin of voice/session.py.
// Protocol: docs/web-api-contract.md (Voice). Audio is PCM16 mono 24 kHz little-endian both ways.

import { ORT_URL, WAKE_THRESHOLD, createWake } from './wake.js';

export const LIVE_RATE = 24000;
const BUFFER_CHUNKS = 125; // 5 s of 40 ms chunks held until `ready` (voice/session.py buffer_seconds)

// ---- Session feel. Tune by ear on the owner's speakers.
// Close this long after Byte finished a turn (turn_done or ready, and playback drained) with no speech.
export const IDLE_SECONDS = 12;
export const IDLE_WARN_SECONDS = 3; // last stretch shows "encerrando…"; speaking cancels it
const CONNECT_HINT_MS = 600; // `ready` slower than this gets a visible hint instead of dead air
export const MIN_DWELL_SECONDS = 0.25; // a shown ouvindo/pensando/falando holds at least this long
const PLAYBACK_GAP_SECONDS = 0.25; // a gap between audio chunks shorter than this stays "falando"
const CHIME_GAIN = 0.045; // peak gain of the start/end chimes (0..1)
const CHIME_UP = [587.33, 880]; // D5 -> A5, rising: session open
const CHIME_DOWN = [880, 587.33]; // falling: session closed
const ECHO_TAIL_SECONDS = 0.3;
const THINKING_MAX_SECONDS = 8;
// ponytail: half-duplex like the laptop client (mic ignored while Byte talks, no barge-in);
// set true once the browser's echo cancellation proves good enough on the owner's speakers.
const BARGE_IN = false;
// Calibration knobs for the local end-of-speech guess (only drives the "pensando" state).
// Hysteresis: speech starts above ON and keeps going until the level drops below OFF.
export const SPEECH_ON_RMS = 0.03;
export const SPEECH_OFF_RMS = 0.015;
export const END_OF_SPEECH_SECONDS = 0.7;

const LIVE_STATES = new Set(['listening', 'thinking', 'speaking']);

/**
 * Hold each shown live state at least `min` seconds. `update(want, at)` returns the state to
 * show now, or null to keep the current one; call it again later (each frame) to catch up.
 * Entering or leaving a live state (off, wake, connecting) is never delayed.
 */
export function createDwell(min = MIN_DWELL_SECONDS) {
  let shown = null;
  let since = -Infinity;
  return {
    update(want, at) {
      if (want === shown) return null;
      if (LIVE_STATES.has(shown) && LIVE_STATES.has(want) && at - since < min) return null;
      shown = want;
      since = at;
      return want;
    },
  };
}

/**
 * Speech gate with hysteresis. `push(rms, at)` returns 'speech' for a voiced frame, 'end' once
 * after `hang` seconds of quiet that followed speech, else null.
 */
export function createSpeechGate(on = SPEECH_ON_RMS, off = SPEECH_OFF_RMS, hang = END_OF_SPEECH_SECONDS) {
  let active = false;
  let heard = false;
  let last = 0;
  return {
    push(level, at) {
      active = level > (active ? off : on);
      if (active) {
        heard = true;
        last = at;
        return 'speech';
      }
      if (heard && at - last > hang) {
        heard = false;
        return 'end';
      }
      return null;
    },
  };
}

/** Where the idle countdown stands after `quiet` seconds: 'quiet', 'warn' or 'end'. */
export function idlePhase(quiet, idle = IDLE_SECONDS, warn = IDLE_WARN_SECONDS) {
  if (quiet >= idle) return 'end';
  return quiet >= idle - warn ? 'warn' : 'quiet';
}

const SERVER_ERRORS = {
  model_unavailable: 'O modelo de voz não respondeu. Tente de novo em instantes.',
  session_limit: 'A conversa por voz atingiu o limite de tempo.',
  internal: 'O servidor falhou na conversa por voz.',
  bad_start: 'O servidor recusou o início da sessão de voz.',
  bad_segment: 'O servidor recusou o início da sessão de voz.',
};

export const serverErrorText = (code) => SERVER_ERRORS[code] || `Erro na conversa por voz (${code}).`;

/** pt-BR text for a socket close, or null when the close was a normal end. */
export function closeText(code, opened) {
  if (!opened) return 'Não consegui abrir a voz: token recusado ou servidor fora do ar.';
  if (code === 4000) return 'Outra sessão de voz assumiu (outro aparelho ou aba).';
  if (code === 1008) return 'O servidor recusou a sessão de voz (1008).';
  if (code === 1009) return 'Áudio grande demais para o servidor.';
  if (code === 1000 || code === 1005) return null;
  return 'A conexão de voz caiu.';
}

export function pcm16ToFloat(buffer) {
  const view = new DataView(buffer);
  const out = new Float32Array(buffer.byteLength >> 1);
  for (let i = 0; i < out.length; i++) out[i] = view.getInt16(i * 2, true) / 0x8000;
  return out;
}

export function rms(pcm) {
  let sum = 0;
  for (let i = 0; i < pcm.length; i++) sum += (pcm[i] / 0x8000) ** 2;
  return pcm.length ? Math.sqrt(sum / pcm.length) : 0;
}

/** Perceptual 0..1 level for the orb from an RMS in 0..1. */
export const levelOf = (r) => Math.min(1, Math.max(0, Math.sqrt(r) * 2.4 - 0.12));

function analyserLevel(analyser, scratch) {
  analyser.getFloatTimeDomainData(scratch);
  let sum = 0;
  for (const s of scratch) sum += s * s;
  return levelOf(Math.sqrt(sum / scratch.length));
}

function createPlayer(ctx, output) {
  let end = 0;
  let start = 0;
  const sources = new Set();
  return {
    play(buffer) {
      const samples = pcm16ToFloat(buffer);
      if (!samples.length) return;
      const audio = ctx.createBuffer(1, samples.length, LIVE_RATE);
      audio.copyToChannel(samples, 0);
      const src = ctx.createBufferSource();
      src.buffer = audio;
      src.connect(output);
      if (end <= ctx.currentTime) start = end = ctx.currentTime + 0.06; // a small lead absorbs jitter
      src.start(end);
      end += audio.duration;
      sources.add(src);
      src.onended = () => sources.delete(src);
    },
    busy: () => end > ctx.currentTime,
    /** Seconds of queued audio left; negative once drained (how long ago it ran out). */
    remaining: () => end - ctx.currentTime,
    /** Stop now; return the milliseconds of the current response already played. */
    clear() {
      const played = Math.max(0, Math.min(ctx.currentTime, end) - start);
      sources.forEach((s) => s.stop());
      sources.clear();
      end = 0;
      return Math.round(played * 1000);
    },
  };
}

function micErrorText(err) {
  if (err?.name === 'NotAllowedError' || err?.name === 'SecurityError') {
    return 'Permissão do microfone negada. Libere no cadeado da barra de endereço e tente de novo.';
  }
  if (err?.name === 'NotFoundError') return 'Nenhum microfone encontrado.';
  return 'Não consegui abrir o microfone.';
}

/**
 * Voice controller. States: off, wake (waiting for "Ei Byte"), connecting, listening, thinking,
 * speaking. Callbacks: onState(state), onLevel(0..1), onTranscript(role, text),
 * onNotice(text, isError), onConversation(id), onClosing(bool) (idle countdown running).
 */
export function createVoice({
  getToken, getConversationId, onState, onLevel, onTranscript, onNotice, onConversation, onClosing = () => {},
}) {
  let state = 'off';
  let wakeOn = false;
  let audio = null; // { ctx, stream, mic, worklet, micAnalyser, playAnalyser, player, scratch }
  let opening = null;
  let wake = null;
  let wakeQueue = Promise.resolve();
  let wakeInflight = 0;
  let ws = null;
  let pending = [];
  let raf = 0;
  const t = { cueUntil: 0, unmuteAt: 0, lastActivity: 0, thinkingSince: 0 };
  let gate = createSpeechGate();
  let idleArmed = false;
  let closing = false; // idle countdown in its last stretch
  let cued = false; // a start chime played, so the session owes an end chime
  let connectHint = 0;
  let hinted = false;
  let drainTimer = 0;
  let releaseTimer = 0;
  const dwell = createDwell();

  const now = () => audio?.ctx.currentTime ?? 0;
  const live = () => state === 'listening' || state === 'thinking' || state === 'speaking';

  function show() {
    const next = dwell.update(state, performance.now() / 1000);
    if (next) onState(next);
  }

  function set(next) {
    if (next === state) return;
    state = next;
    if (next === 'thinking') t.thinkingSince = now();
    if (next !== 'listening') setClosing(false);
    show();
  }

  function setClosing(on) {
    if (on === closing) return;
    closing = on;
    onClosing(on);
    onNotice(on ? 'encerrando… fale para continuar' : '');
  }

  async function openAudio() {
    if (audio) return audio;
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      throw new Error('O microfone só funciona em HTTPS ou em http://localhost / 127.0.0.1.');
    }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      });
    } catch (err) {
      throw new Error(micErrorText(err));
    }
    const ctx = new AudioContext();
    await ctx.audioWorklet.addModule(new URL('./mic-worklet.js', import.meta.url));
    const mic = ctx.createMediaStreamSource(stream);
    const micAnalyser = ctx.createAnalyser();
    const playAnalyser = ctx.createAnalyser();
    micAnalyser.fftSize = playAnalyser.fftSize = 1024;
    const worklet = new AudioWorkletNode(ctx, 'byte-mic', { numberOfInputs: 1, numberOfOutputs: 0 });
    worklet.port.onmessage = ({ data }) => (data.rate === LIVE_RATE ? onLiveChunk(data.pcm) : onWakeChunk(data.pcm));
    mic.connect(micAnalyser);
    mic.connect(worklet);
    playAnalyser.connect(ctx.destination);
    audio = {
      ctx, stream, mic, worklet, micAnalyser, playAnalyser,
      player: createPlayer(ctx, playAnalyser), scratch: new Float32Array(1024),
    };
    await ctx.resume();
    raf = requestAnimationFrame(tick);
    return audio;
  }

  function ensureAudio() {
    clearTimeout(releaseTimer); // a release waiting for the end chime must not kill a new session
    opening ??= openAudio().finally(() => { opening = null; });
    return opening;
  }

  function releaseAudio() {
    if (!audio) return;
    cancelAnimationFrame(raf);
    audio.stream.getTracks().forEach((track) => track.stop());
    audio.ctx.close();
    audio = null;
    onLevel(0);
  }

  // ------------------------------------------------------------ wake word

  async function loadWake() {
    if (wake) return wake;
    const ort = await import(ORT_URL);
    ort.env.wasm.numThreads = 1; // threads need cross-origin isolation, which the panel does not set
    wake = await createWake(ort, new URL('./models', import.meta.url).href);
    return wake;
  }

  function onWakeChunk(pcm) {
    if (state !== 'wake' || !wake) return;
    // ponytail: a device too slow for the models drops audio and starts over instead of lagging
    if (wakeInflight > 12) { wakeQueue = wakeQueue.then(() => wake.reset()); wakeInflight = 0; return; }
    wakeInflight++;
    wakeQueue = wakeQueue.then(async () => {
      const score = await wake.push(pcm);
      wakeInflight = Math.max(0, wakeInflight - 1);
      if (score > WAKE_THRESHOLD && state === 'wake') begin();
    }).catch(() => {});
  }

  async function setWake(on) {
    wakeOn = on;
    if (!on) {
      if (state === 'wake') { set('off'); releaseAudio(); }
      return true;
    }
    onNotice('Carregando o detector de “Ei Byte”…');
    const failure = await ensureAudio().then(
      () => loadWake().then(() => null, () => 'Não consegui carregar o detector de “Ei Byte” (sem internet para o onnxruntime?).'),
      (err) => err.message,
    );
    if (failure) {
      wakeOn = false;
      onNotice(failure, true);
      if (state === 'off') releaseAudio();
      return false;
    }
    if (!wakeOn) { // turned off while loading
      if (state === 'off') releaseAudio();
      return false;
    }
    wake.reset();
    if (state === 'off') set('wake');
    onNotice('Diga “Ei Byte”.');
    return true;
  }

  // ------------------------------------------------------------ session

  /** Two soft sine notes straight to the speakers (never into the worklet); returns seconds. */
  function chime(notes) {
    const { ctx } = audio;
    const at = ctx.currentTime + 0.01;
    notes.forEach((hz, i) => {
      const start = at + i * 0.11;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.frequency.value = hz;
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(CHIME_GAIN, start + 0.015);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.22);
      osc.connect(gain).connect(ctx.destination);
      osc.start(start);
      osc.stop(start + 0.24);
    });
    const length = 0.11 * (notes.length - 1) + 0.25;
    t.cueUntil = at + length + 0.05; // keep the chime out of what the server hears
    return length;
  }

  async function begin() {
    if (state !== 'off' && state !== 'wake') return;
    set('connecting');
    onNotice('');
    hinted = false;
    clearTimeout(connectHint);
    connectHint = setTimeout(() => {
      if (state !== 'connecting') return;
      hinted = true;
      onNotice(audio ? 'Conectando… pode ir falando, eu guardo o áudio.' : 'Abrindo o microfone…');
    }, CONNECT_HINT_MS);
    try {
      await ensureAudio();
    } catch (err) {
      clearTimeout(connectHint);
      set(wakeOn ? 'wake' : 'off');
      onNotice(err.message, true);
      return;
    }
    if (state !== 'connecting') { // stopped (sign-out) while the microphone was opening
      if (state === 'off') releaseAudio();
      return;
    }
    chime(CHIME_UP);
    cued = true;
    if (hinted) onNotice('Conectando… pode ir falando, eu guardo o áudio.');
    pending = [];
    gate = createSpeechGate();
    idleArmed = false;
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
    // Browsers cannot set Authorization on a WebSocket; the token rides as a subprotocol and the
    // server answers with the bare name "bearer". Never put it in the URL.
    let socket;
    try {
      socket = new WebSocket(`${scheme}://${location.host}/api/v1/live`, ['bearer', getToken() || '']);
    } catch { // SyntaxError: the token holds characters a subprotocol cannot carry
      return finish('O token tem caracteres que o WebSocket não aceita; gere um com secrets.token_urlsafe.');
    }
    socket.binaryType = 'arraybuffer';
    ws = socket;
    let opened = false;
    let serverError = null;
    socket.onopen = () => {
      opened = true;
      const id = getConversationId();
      // client 'panel': only the panel may open a project in its terminal
      socket.send(JSON.stringify({ type: 'start', segment: 'auto', client: 'panel', ...(id ? { conversation_id: id } : {}) }));
    };
    socket.onmessage = (e) => {
      if (ws !== socket) return;
      if (typeof e.data !== 'string') return onAudio(e.data);
      let event;
      try { event = JSON.parse(e.data); } catch { return; }
      if (event.type === 'error') serverError = event.code;
      onEvent(event);
    };
    socket.onclose = (e) => {
      if (ws !== socket) return;
      const text = serverError ? serverErrorText(serverError) : closeText(e.code, opened);
      finish(text);
    };
  }

  function onAudio(buffer) {
    if (!live()) return;
    t.lastActivity = now();
    idleArmed = false;
    audio.player.play(buffer);
    set('speaking');
  }

  function onEvent(event) {
    t.lastActivity = now();
    switch (event.type) {
      case 'ready':
        clearTimeout(connectHint);
        if (hinted) onNotice('');
        if (event.conversation_id) onConversation(event.conversation_id);
        for (const chunk of pending) ws.send(chunk);
        pending = [];
        idleArmed = true; // a false wake, or a press and silence, must not hold a provider session
        set('listening');
        break;
      case 'transcript':
        if (event.text) onTranscript(event.role, event.text);
        if (event.role === 'user') {
          idleArmed = false;
          if (state === 'listening') set('thinking');
        }
        break;
      case 'interrupt': {
        const played = audio.player.clear();
        ws.send(JSON.stringify({ type: 'played', audio_end_ms: played }));
        set('listening');
        break;
      }
      case 'turn_done':
        idleArmed = true;
        if (state === 'thinking') set('listening');
        break;
      default: // `error` and `closed` are followed by the server closing the socket
    }
  }

  function onLiveChunk(pcm) {
    const at = now();
    if (at < t.cueUntil) return;
    if (state === 'connecting') {
      pending.push(pcm.buffer);
      if (pending.length > BUFFER_CHUNKS) pending.shift();
      return;
    }
    if (!live() || ws?.readyState !== WebSocket.OPEN) return;
    // The idle clock only runs once Byte is done: playback drained and the echo tail passed.
    if (audio.player.busy() || at < t.unmuteAt) t.lastActivity = at;
    if (!BARGE_IN && (audio.player.busy() || at < t.unmuteAt)) {
      if (audio.player.busy()) t.unmuteAt = at + ECHO_TAIL_SECONDS;
      return;
    }
    const voiced = gate.push(rms(pcm), at);
    if (voiced === 'speech') t.lastActivity = at;
    else if (voiced === 'end' && state === 'listening') set('thinking');
    const phase = idleArmed && state === 'listening' ? idlePhase(at - t.lastActivity) : 'quiet';
    if (phase === 'end') return stop(false);
    setClosing(phase === 'warn');
    ws.send(pcm.buffer);
  }

  function tick() {
    raf = requestAnimationFrame(tick);
    const at = now();
    // A short gap between chunks is network jitter, not the end of the answer.
    if (state === 'speaking' && !drainTimer && audio.player.remaining() < -PLAYBACK_GAP_SECONDS) {
      t.unmuteAt = at + ECHO_TAIL_SECONDS;
      set('listening');
    }
    if (state === 'thinking' && at - t.thinkingSince > THINKING_MAX_SECONDS) set('listening');
    show(); // a state held back by the dwell catches up here
    const source = state === 'speaking' ? audio.playAnalyser : state === 'listening' || state === 'wake' ? audio.micAnalyser : null;
    onLevel(source ? analyserLevel(source, audio.scratch) : 0);
  }

  /**
   * The session is over (socket gone). Byte finishes the sentence it is saying unless `flush`
   * (the owner pressed Parar or signed out), then `settle` plays the end chime.
   */
  function finish(notice, flush = false) {
    ws = null;
    pending = [];
    clearTimeout(connectHint);
    clearTimeout(drainTimer);
    drainTimer = 0;
    setClosing(false);
    const left = !flush && audio ? audio.player.remaining() : 0;
    // setTimeout, not the rAF tick: a hidden tab gets no frames but must still close.
    if (left > 0) drainTimer = setTimeout(() => settle(notice), left * 1000 + 80);
    else settle(notice);
  }

  function settle(notice) {
    clearTimeout(drainTimer);
    drainTimer = 0;
    audio?.player.clear();
    const tail = cued && audio ? chime(CHIME_DOWN) : 0;
    cued = false;
    if (notice) onNotice(notice, true);
    if (wakeOn && wake && audio) {
      wakeQueue = wakeQueue.then(() => wake.reset());
      set('wake');
      if (!notice) onNotice('Diga “Ei Byte”.');
    } else {
      set('off');
      clearTimeout(releaseTimer);
      releaseTimer = setTimeout(releaseAudio, tail * 1000 + 50); // let the end chime ring out
    }
  }

  /** End the session from this side; `finish` runs now, not from a late onclose. */
  function stop(flush) {
    const socket = ws;
    ws = null;
    socket?.close(1000);
    finish(null, flush);
  }

  return {
    get state() { return state; },
    /** The talk button: start a session, or end the one running ("Parar" cuts Byte off now). */
    toggle() {
      if (state === 'off' || state === 'wake') return begin();
      if (state !== 'connecting' || ws) stop(true); // mid-ensureAudio there is nothing to stop yet
    },
    setWake,
    /** Sign-out: end everything and forget the microphone. */
    shutdown() {
      wakeOn = false;
      stop(true);
    },
  };
}
