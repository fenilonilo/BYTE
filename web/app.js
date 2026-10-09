import { api, MOCK, token } from './api.js';
import { IDLE_WARN_SECONDS, createVoice } from './live.js';
import { createSphere } from './sphere.js';

const $ = (sel, root = document) => root.querySelector(sel);
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === false || v == null) continue;
    if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'class') el.className = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  el.append(...children.flat().filter((c) => c != null && c !== false));
  return el;
}
const svg = (d, solid = false) => {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  s.setAttribute('viewBox', '0 0 16 16');
  s.setAttribute('aria-hidden', 'true');
  s.innerHTML = solid ? `<path d="${d}" fill="currentColor" stroke="none"/>` : `<path d="${d}"/>`;
  return s;
};
const ICON = {
  play: 'M4.5 2.8v10.4L13 8z', pause: 'M4 3h3v10H4zM9 3h3v10H9z',
  next: 'M3.5 3v10L10 8zM11 3h1.6v10H11z', prev: 'M12.5 3v10L6 8zM3.4 3H5v10H3.4z',
  shuffle: 'M2 4.5h2.5c3 0 4 7 7 7H14M2 11.5h2.5c1.2 0 2-1 2.7-2.3M9 6.6C9.6 5.4 10.3 4.5 11.5 4.5H14M12.5 3 14 4.5 12.5 6M12.5 10 14 11.5 12.5 13',
  trash: 'M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 8.5h5.8l.6-8.5',
  minus: 'M3.5 8h9', plus: 'M3.5 8h9M8 3.5v9',
};

const MODES = { cool: 'frio', dry: 'seco', fan: 'ventilar', auto: 'auto' };
const FANS = { auto: 'auto', low: 'baixa', mid: 'média', high: 'alta', nature: 'natural' };
const KINDS = { track: 'faixa', album: 'álbum', playlist: 'playlist', artist: 'artista' };
const AGENT_LABEL = { idle: 'em espera', listening: 'ouvindo', thinking: 'pensando', speaking: 'falando' };

const brl = (cents) => (cents / 100).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
const localDate = (d = new Date()) => d.toLocaleDateString('sv-SE');
const mmss = (ms) => {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
};
const tzOffset = () => {
  const m = -new Date().getTimezoneOffset();
  const a = Math.abs(m);
  return `${m >= 0 ? '+' : '-'}${String(Math.floor(a / 60)).padStart(2, '0')}:${String(a % 60).padStart(2, '0')}`;
};
const temp = (t) => t.toLocaleString('pt-BR', { minimumFractionDigits: t % 1 ? 1 : 0, maximumFractionDigits: 1 });

const state = { lights: null, climates: null, music: null, devices: null, conversationId: null };
let sphere = null;
let busy = 0;
let speaking = 0;
let timers = [];
let voiceState = 'off';

// ---------------------------------------------------------------- agent state

// Connecting already buffers the mic, so the orb eases straight into listening (no frantic detour).
const VOICE_AGENT = { connecting: 'listening', listening: 'listening', thinking: 'thinking', speaking: 'speaking' };

function setAgent(name) {
  // A live voice session owns the orb; chat activity shows only outside it.
  const effective = VOICE_AGENT[voiceState] || (speaking > 0 ? 'speaking' : busy > 0 ? 'thinking' : name);
  document.body.dataset.agent = effective;
  $('#agent-state').textContent = voiceState === 'connecting' ? 'conectando' : AGENT_LABEL[effective];
  sphere?.setState(effective);
}
function idleOrListening() {
  const input = $('#chat-input');
  setAgent(document.activeElement === input && input.value.trim() ? 'listening' : 'idle');
}
async function withAgent(promise) {
  busy++;
  setAgent('thinking');
  try { return await promise; } finally { busy--; idleOrListening(); }
}

// ---------------------------------------------------------------- feedback

// The server describes climate state with enum values and dot decimals; show them in pt-BR.
const climateText = (text) => text
  .replace(/\bmodo (cool|dry|fan|auto)\b/g, (_, m) => `modo ${MODES[m]}`)
  .replace(/\bventilador (auto|low|mid|high|nature)\b/g, (_, f) => `ventilador ${FANS[f]}`)
  .replace(/\d+\.\d+/g, (n) => Number(n).toLocaleString('pt-BR'));

const noteTimers = {};
function note(section, text, isError = false) {
  const el = $(`[data-note="${section}"]`);
  if (!el) return;
  el.textContent = section === 'climate' ? climateText(text) : text;
  el.classList.toggle('error', isError);
  clearTimeout(noteTimers[section]);
  if (!isError) noteTimers[section] = setTimeout(() => { el.textContent = ''; }, 6000);
}

function handleError(section, err) {
  if (err.status === 401) {
    if (!token.get()) return; // already signed out; a late reply must not blame the token
    return signOut('Token recusado. Entre de novo.');
  }
  const msg = err.status === 504
    ? `Sem resposta do aparelho: estado desconhecido. Relendo antes de tentar de novo.`
    : err.status >= 500 ? 'O servidor falhou ao executar. Tente de novo em instantes.'
    : err.message;
  note(section, msg, true);
  // An offline or unknown Connect device usually means the device list moved on.
  if (section === 'music' && (err.status === 422 || err.status === 504)) loadDevices();
}

const skeleton = () => h('div', { class: 'skeleton', 'aria-hidden': 'true' }, h('span'), h('span'), h('span'));
const empty = (title, hint) => h('div', { class: 'empty-state' }, h('strong', {}, title), hint);
const sectionError = (text, retry) => h('div', { class: 'section-error', role: 'alert' },
  h('span', {}, text), h('button', { class: 'btn small', type: 'button', onclick: retry }, 'Tentar de novo'));

// Re-rendering destroys focused controls, so background refreshes skip a section in use.
const inUse = (el) => el.contains(document.activeElement) && document.activeElement !== el;

// ---------------------------------------------------------------- confirmation

let pendingExpiry = 0;
function clearPending(root) {
  root.querySelectorAll('.pending').forEach((p) => p.remove());
}

/** Show an inline Confirm/Cancel strip. Nothing runs until the owner presses Confirm. */
function showPending(summary, host, { onConfirm, onCancel, before = null }) {
  const scope = host.closest('.transcript, .console') || host;
  clearPending(scope);
  const node = $('#tpl-pending').content.firstElementChild.cloneNode(true);
  node.setAttribute('role', 'group');
  node.setAttribute('aria-label', `Confirmação pendente: ${summary}`);
  node.tabIndex = -1;
  $('.summary', node).textContent = summary;
  const yes = $('[data-confirm]', node);
  const no = $('[data-cancel]', node);
  yes.addEventListener('click', async () => {
    yes.disabled = no.disabled = true;
    yes.setAttribute('aria-busy', 'true');
    await onConfirm();
    node.remove();
  });
  no.addEventListener('click', () => { node.remove(); onCancel(); });
  host.insertBefore(node, before);
  node.focus({ preventScroll: true });
  node.scrollIntoView({ block: 'nearest', behavior: reducedMotion.matches ? 'auto' : 'smooth' });
  return node;
}

function showPanelPending(summary, section, onDone) {
  const sec = section ? $(`#sec-${section}`) : $('#global-pending');
  const node = showPending(summary, sec, {
    before: section ? $('.note', sec) : null,
    onConfirm: async () => {
      try {
        const res = await withAgent(api.confirm(true));
        note(section || 'lights', res.message);
        onDone?.();
      } catch (err) {
        if (err.status === 409) note(section || 'lights', 'A confirmação expirou. Peça de novo.', true);
        else handleError(section || 'lights', err);
      }
      refreshAll(section);
      if (!section) { loadAgenda(true); loadFinance(true); } // restored after a reload: owner unknown
    },
    onCancel: () => {
      api.confirm(false).catch(() => {});
      note(section || 'lights', 'Cancelado. Nada foi executado.');
    },
  });
  clearTimeout(pendingExpiry);
  pendingExpiry = setTimeout(() => {
    if (!node.isConnected) return;
    node.remove();
    note(section || 'lights', 'A confirmação expirou sem resposta. Nada foi executado.');
  }, 60_000);
}

async function runAction(section, call, onDone) {
  clearPending($('#console')); // the server drops a pending action on any new request
  try {
    const res = await withAgent(call());
    if (res.status === 'pending_confirmation') {
      showPanelPending(res.pending_confirmation?.summary || res.message, section, onDone);
      return;
    }
    note(section, res.message);
    onDone?.();
  } catch (err) {
    handleError(section, err);
  }
  await refreshAll(section);
}

// ---------------------------------------------------------------- lights

function swatchColor(l) {
  if (!l.power) return 'transparent';
  if (l.mode === 'colour') return `hsl(${l.color.hue} ${Math.max(35, l.color.saturation)}% 58%)`;
  return `color-mix(in oklab, #dfe7ff ${l.color_temperature}%, #ffc27a)`;
}
function lightMeta(l) {
  if (!l.power) return 'desligada';
  if (l.mode === 'colour') return `cor, matiz ${l.color.hue}°, brilho ${l.color.brightness}%`;
  if (l.mode === 'scene') return 'cena';
  if (l.mode === 'music') return 'ritmo da música';
  return `branco, temperatura ${l.color_temperature}`;
}
function rangeFill(input, out, suffix = '%') {
  input.style.setProperty('--fill', `${((input.value - input.min) / (input.max - input.min)) * 100}%`);
  if (out) out.textContent = `${input.value}${suffix}`;
}

function lightRow(l) {
  const level = l.mode === 'colour' ? l.color.brightness : l.brightness;
  const out = h('output', { class: 'row-meta' });
  const range = h('input', {
    type: 'range', min: 1, max: 100, value: level, 'aria-label': `Brilho de ${l.name}`,
    oninput: () => rangeFill(range, out),
    onchange: () => {
      const b = Number(range.value);
      const change = l.mode === 'colour'
        ? { hue: l.color.hue, saturation: l.color.saturation, brightness: b }
        : { brightness: b };
      runAction('lights', () => api.setLight(l.name, change));
    },
  });
  rangeFill(range, out);
  const swatch = h('span', { class: 'swatch', 'aria-hidden': 'true' });
  swatch.style.background = swatchColor(l);
  if (l.power) swatch.style.boxShadow = `0 0 10px ${swatchColor(l)}`;
  return h('li', { class: `light${l.power ? ' on' : ''}` },
    swatch,
    h('div', {}, h('div', { class: 'row-title' }, l.name), h('div', { class: 'row-meta' }, lightMeta(l))),
    h('button', {
      class: 'toggle', type: 'button', 'aria-pressed': String(l.power),
      'aria-label': `${l.name}: ${l.power ? 'ligada' : 'desligada'}. Alternar`,
      onclick: () => runAction('lights', () => api.setLight(l.name, { power: !l.power })),
    }, l.power ? 'ligada' : 'desligada'),
    h('div', { class: 'dim' }, h('span', { class: 'label' }, 'brilho'), range, out),
  );
}

function renderLights() {
  const list = $('#lights-list');
  if (state.lights === null) return list.replaceChildren(sectionError('Luzes indisponíveis agora.', () => refreshAll('lights')));
  if (!state.lights.length) return list.replaceChildren(empty('Nenhuma luz configurada.', 'Adicione as lâmpadas na configuração do servidor.'));
  list.replaceChildren(...state.lights.map(lightRow));
}

// ---------------------------------------------------------------- climate

const tempDebounce = {};
// The mono comma is as wide as a digit; a tighter sans comma keeps "23,5" reading as one number.
const tempParts = (t) => {
  const [int, dec] = temp(t).split(',');
  return dec ? [int, h('span', { class: 'dec' }, ','), dec] : [int];
};
function climateBlock(c) {
  const off = !c.power;
  const tempEl = h('span', {}, tempParts(c.target_temperature));
  let target = c.target_temperature;
  const nudge = (delta) => {
    target = Math.min(30, Math.max(18, Math.round(target + delta)));
    tempEl.replaceChildren(...tempParts(target));
    clearTimeout(tempDebounce[c.name]);
    tempDebounce[c.name] = setTimeout(() => {
      delete tempDebounce[c.name];
      runAction('climate', () => api.setClimate(c.name, { target_temperature: target }));
    }, 1500); // one command after the owner stops clicking
  };
  const seg = h('div', { class: 'segmented', role: 'group', 'aria-label': `Modo de ${c.name}` },
    Object.entries(MODES).map(([value, label]) => h('button', {
      type: 'button', 'aria-pressed': String(c.mode === value), disabled: off,
      onclick: () => c.mode !== value && runAction('climate', () => api.setClimate(c.name, { mode: value })),
    }, label)));
  const fanId = `fan-${c.name.replace(/\W+/g, '-')}`;
  const fan = h('select', {
    id: fanId, disabled: off,
    onchange: () => runAction('climate', () => api.setClimate(c.name, { fan_speed: fan.value })),
  }, Object.entries(FANS).map(([v, label]) => h('option', { value: v, selected: v === c.fan_speed }, label)));
  const flag = (key, label) => h('button', {
    class: 'toggle', type: 'button', 'aria-pressed': String(c[key]), disabled: off,
    onclick: () => runAction('climate', () => api.setClimate(c.name, { [key]: !c[key] })),
  }, label);

  return h('div', { class: `climate${off ? ' off' : ''}` },
    h('div', { class: 'climate-top' },
      h('div', { class: 'row-title' }, c.name),
      h('button', {
        class: 'toggle', type: 'button', 'aria-pressed': String(c.power),
        'aria-label': `${c.name}: ${c.power ? 'ligado' : 'desligado'}. Alternar (pede confirmação)`,
        onclick: () => runAction('climate', () => api.setClimate(c.name, { power: !c.power })),
      }, c.power ? 'ligado' : 'desligado')),
    c.has_error ? h('p', { class: 'warn', role: 'alert' }, 'O aparelho está reportando erro.') : null,
    h('div', { class: 'climate-dial' },
      h('div', { class: 'temp', 'aria-live': 'polite' }, h('span', { class: 'sr-only' }, 'alvo '), tempEl, h('small', {}, '°C')),
      h('div', { class: 'stepper' },
        h('button', { class: 'icon-btn big', type: 'button', disabled: off, 'aria-label': 'Diminuir um grau', onclick: () => nudge(-1) }, svg(ICON.minus)),
        h('button', { class: 'icon-btn big', type: 'button', disabled: off, 'aria-label': 'Aumentar um grau', onclick: () => nudge(1) }, svg(ICON.plus))),
      h('div', { class: 'ambient' }, h('span', { class: 'label' }, 'ambiente'), h('strong', {}, `${temp(c.current_temperature)}°C`))),
    off ? h('p', { class: 'help' }, 'Desligado. Ligue para ajustar modo e temperatura.') : null,
    h('div', { class: 'climate-opts' },
      seg,
      h('div', { class: 'field' }, h('label', { for: fanId }, 'ventilador'), fan),
      flag('swing', 'oscilar'), flag('power_save', 'economia')),
  );
}

function renderClimate() {
  const box = $('#climate-list');
  if (state.climates === null) return box.replaceChildren(sectionError('Ar-condicionado indisponível agora.', () => refreshAll('climate')));
  if (!state.climates.length) return box.replaceChildren(empty('Nenhum ar-condicionado configurado.', 'Configure o LG ThinQ no servidor.'));
  box.replaceChildren(...state.climates.map(climateBlock));
}

// ---------------------------------------------------------------- music

function renderMusic() {
  const box = $('#music-now');
  const m = state.music;
  if (m === null) return box.replaceChildren(sectionError('Spotify indisponível agora.', () => refreshAll('music')));
  const item = m.item;
  const out = h('output', { class: 'row-meta' });
  const vol = h('input', {
    type: 'range', min: 0, max: 100, value: m.volume, 'aria-label': 'Volume',
    oninput: () => rangeFill(vol, out, ''),
    onchange: () => runAction('music', () => api.controlMusic({ volume: Number(vol.value) })),
  });
  rangeFill(vol, out, '');
  const ctl = (label, icon, body, extra = {}) => h('button', {
    class: 'icon-btn', type: 'button', 'aria-label': label,
    onclick: () => runAction('music', () => (body ? api.controlMusic(body) : api.play({}))), ...extra,
  }, svg(icon, true));
  const ratio = m.duration_ms ? Math.min(1, m.progress_ms / m.duration_ms) : 0;
  // The polled playback state is fresher than the device list: move the "active" mark with it.
  const listed = state.devices?.devices?.find((x) => x.name === m.device);
  if (listed) state.devices.devices.forEach((x) => { x.active = x === listed; });
  renderDevices();
  box.replaceChildren(
    item
      ? h('div', {}, h('p', { class: 'now-title' }, item.name), h('p', { class: 'now-artist' }, [item.artist, KINDS[item.kind]].filter(Boolean).join(' · ')))
      : empty('Nada tocando.', 'Toque para retomar ou escolha algo na busca.'),
    h('div', { class: 'progress', 'aria-hidden': 'true' }, h('span', { id: 'music-bar', style: `transform:scaleX(${ratio})` })),
    h('div', { class: 'progress-times' }, h('span', { id: 'music-pos' }, mmss(m.progress_ms)), h('span', {}, mmss(m.duration_ms))),
    h('div', { class: 'transport' },
      ctl('Faixa anterior', ICON.prev, { skip: 'previous' }),
      h('button', {
        class: 'icon-btn big', type: 'button', 'aria-label': m.playing ? 'Pausar' : 'Tocar',
        onclick: () => runAction('music', () => (m.playing ? api.controlMusic({ paused: true }) : api.play({}))),
      }, svg(m.playing ? ICON.pause : ICON.play, true)),
      ctl('Próxima faixa', ICON.next, { skip: 'next' }),
      h('span', { class: 'grow' }),
      h('button', {
        class: 'icon-btn', type: 'button', 'aria-label': 'Modo aleatório', 'aria-pressed': String(m.shuffle),
        onclick: () => runAction('music', () => api.controlMusic({ shuffle: !m.shuffle })),
      }, svg(ICON.shuffle))),
    h('div', { class: 'volume' }, h('span', { class: 'label' }, 'volume'), vol, out),
  );
}

// Spotify Connect devices: `state.devices` is {devices, default} | {error} | null (not loaded).
const NO_DEVICES = 'Nenhum dispositivo online. Abra o Spotify no BatCaverna (Chromecast) e toque Atualizar.';
let devicesAt = 0;

async function loadDevices() {
  devicesAt = Date.now();
  if (!state.devices) $('#music-devices').replaceChildren(h('span', { class: 'row-meta' }, 'procurando aparelhos…'));
  const btn = $('#devices-refresh');
  btn.setAttribute('aria-busy', 'true');
  try {
    state.devices = await api.musicDevices();
  } catch (err) {
    if (err.status === 401) return handleError('music', err);
    state.devices = { error: err.status >= 500 || !err.status ? 'Não consegui listar os aparelhos do Spotify.' : err.message };
  } finally {
    btn.removeAttribute('aria-busy');
  }
  if (token.get()) renderDevices(true); // a reply landing after sign-out must not repaint names
}

function renderDevices(force = false) {
  const box = $('#music-devices');
  const d = state.devices;
  if (!d || (!force && inUse(box))) return;
  const hadFocus = box.contains(document.activeElement);
  if (d.error) return box.replaceChildren(h('span', { class: 'devices-msg error' }, d.error));
  if (!d.devices.length) return box.replaceChildren(h('span', { class: 'devices-msg' }, NO_DEVICES));
  const current = d.devices.find((x) => x.active) || null;
  const select = h('select', {
    id: 'music-device', 'aria-labelledby': 'devices-label',
    onchange: () => runAction('music', () => api.selectMusicDevice(select.value), loadDevices),
  },
  current ? null : h('option', { value: '', selected: true, disabled: true }, 'escolher aparelho'),
  d.devices.map((x) => h('option', { value: x.name, selected: x === current },
    x.name === d.default ? `${x.name} · padrão` : x.name)));
  const defaultOffline = d.default && !d.devices.some((x) => x.name === d.default);
  const meta = [
    current ? (current.volume == null ? 'ativo' : `ativo · vol ${current.volume}`) : 'nenhum ativo',
    defaultOffline ? `padrão ${d.default} offline` : null,
  ].filter(Boolean).join(' · ');
  box.replaceChildren(select, h('span', { class: 'row-meta dev-status' },
    h('span', { class: `dev-led${current ? ' on' : ''}`, 'aria-hidden': 'true' }), meta));
  if (hadFocus) select.focus();
}

function tickMusic() {
  const m = state.music;
  if (!m?.playing || !m.duration_ms) return;
  m.progress_ms = Math.min(m.duration_ms, m.progress_ms + 1000);
  const bar = $('#music-bar');
  if (bar) bar.style.transform = `scaleX(${m.progress_ms / m.duration_ms})`;
  const pos = $('#music-pos');
  if (pos) pos.textContent = mmss(m.progress_ms);
}

async function loadResults(fetcher, emptyText) {
  const list = $('#music-results');
  list.replaceChildren(h('li', {}, skeleton()));
  try {
    const { items } = await withAgent(fetcher());
    if (!items.length) return list.replaceChildren(h('li', {}, empty(emptyText, 'Tente outro termo ou outro tipo.')));
    list.replaceChildren(...items.map((it) => h('li', {},
      h('div', { style: 'min-width:0' }, h('div', { class: 'row-title' }, it.name),
        h('div', { class: 'row-meta' }, [it.artist, KINDS[it.kind]].filter(Boolean).join(' · '))),
      h('button', {
        class: 'btn small', type: 'button', 'aria-label': `Tocar ${it.name}`,
        onclick: () => runAction('music', () => api.play({ uri: it.uri })),
      }, 'Tocar'))));
  } catch (err) {
    list.replaceChildren();
    handleError('music', err);
  }
}

// ---------------------------------------------------------------- agenda

function eventRow(e) {
  const start = new Date(e.start);
  const end = new Date(start.getTime() + e.duration_minutes * 60_000);
  const hm = (d) => d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  return h('li', { class: 'event' },
    h('time', { datetime: e.start }, hm(start)),
    h('div', { style: 'min-width:0' }, h('div', { class: 'row-title' }, e.title),
      h('div', { class: 'row-meta' }, `${e.duration_minutes} min · até ${hm(end)}`)),
    h('button', {
      class: 'icon-btn', type: 'button', 'aria-label': `Apagar ${e.title} (pede confirmação)`,
      onclick: () => runAction('agenda', () => api.deleteEvent(e.id)),
    }, svg(ICON.trash)));
}

async function loadAgenda(quiet = false) {
  const list = $('#agenda-list');
  const date = $('#agenda-date').value;
  if (quiet && inUse(list)) return;
  if (!quiet) list.replaceChildren(h('li', {}, skeleton()));
  try {
    const { events } = await api.events(date);
    const label = date === localDate() ? 'hoje' : new Date(`${date}T12:00`).toLocaleDateString('pt-BR', { day: 'numeric', month: 'long' });
    list.replaceChildren(...(events.length ? events.map(eventRow)
      : [h('li', {}, empty(`Nada marcado para ${label}.`, 'Crie um evento abaixo ou peça ao Byte.'))]));
  } catch (err) {
    if (err.status === 401) return handleError('agenda', err);
    list.replaceChildren(h('li', {}, sectionError('Não consegui ler a agenda.', () => loadAgenda())));
  }
}

function shiftDay(delta) {
  const input = $('#agenda-date');
  const d = new Date(`${input.value}T12:00`);
  d.setDate(d.getDate() + delta);
  input.value = localDate(d);
  loadAgenda();
}

// ---------------------------------------------------------------- finance

function parseCents(raw) {
  let s = raw.replace(/[R$\s]/g, '');
  if (s.includes(',')) s = s.replace(/\./g, '').replace(',', '.');
  if (!/^\d+(\.\d{1,2})?$/.test(s)) return NaN;
  return Math.round(parseFloat(s) * 100);
}

async function loadFinance(quiet = false) {
  const list = $('#finance-list');
  const [year, month] = $('#finance-month').value.split('-').map(Number);
  if (quiet && inUse(list)) return;
  if (!quiet) list.replaceChildren(h('li', {}, skeleton()));
  try {
    const { expenses, total_cents: total } = await api.expenses(year, month);
    $('#finance-total').textContent = brl(total);
    $('#ex-cats').replaceChildren(...[...new Set(expenses.map((e) => e.category))].map((c) => h('option', { value: c })));
    const monthName = new Date(year, month - 1, 1).toLocaleDateString('pt-BR', { month: 'long' });
    list.replaceChildren(...(expenses.length ? expenses.map((e) => h('li', { class: 'expense' },
      h('span', { class: 'day' }, e.date.slice(8, 10) + '/' + e.date.slice(5, 7)),
      h('div', { style: 'min-width:0' }, h('div', { class: 'row-title' }, e.description), h('div', { class: 'row-meta' }, e.category)),
      h('span', { class: 'amount' }, brl(e.amount_cents))))
      : [h('li', {}, empty(`Nenhum gasto em ${monthName}.`, 'Registre um abaixo; ele vai para a planilha depois da confirmação.'))]));
  } catch (err) {
    if (err.status === 401) return handleError('finance', err);
    $('#finance-total').textContent = '—';
    list.replaceChildren(h('li', {}, sectionError('Não consegui ler a planilha.', () => loadFinance())));
  }
}

// ---------------------------------------------------------------- refresh

const RENDER = { lights: renderLights, climate: renderClimate, music: renderMusic };
const BOX = { lights: '#lights-list', climate: '#climate-list', music: '#music-now' };

async function refreshAll(section, quiet = false) {
  if (section === 'agenda') return loadAgenda(quiet);
  if (section === 'finance') return loadFinance(quiet);
  try {
    const s = await api.state();
    applyState(s, quiet);
  } catch (err) {
    if (err.status === 401) return handleError(section || 'lights', err);
    if (!quiet) note(section || 'lights', 'Não consegui ler o estado da casa.', true);
  }
}

function applyState(s, quiet) {
  const map = { lights: s.lights, climate: s.climates, music: s.music };
  for (const [key, value] of Object.entries(map)) {
    const nudging = key === 'climate' && Object.keys(tempDebounce).length > 0;
    if (quiet && (inUse($(BOX[key])) || nudging)) continue;
    state[key === 'climate' ? 'climates' : key] = value;
    RENDER[key]();
  }
  for (const failed of s.errors || []) note(failed === 'climates' ? 'climate' : failed, `${failed}: leitura falhou.`, true);
}

// ---------------------------------------------------------------- chat

function addMsg(kind, text) {
  const box = $('#transcript');
  $('.t-empty', box)?.remove();
  const who = { me: 'você', agent: 'byte', error: 'erro', system: 'sys' }[kind];
  const body = h('span', { class: 'body' }, text);
  const msg = h('p', { class: `msg ${kind}` }, h('span', { class: 'who' }, who), body);
  box.append(msg);
  box.scrollTop = box.scrollHeight;
  return body;
}

// Drives the sphere's speaking wave from the rhythm of the text being typed out.
async function speak(text) {
  const body = addMsg('agent', '');
  if (reducedMotion.matches) { body.textContent = text; return; }
  speaking++;
  setAgent('speaking');
  const caret = h('span', { class: 'caret', 'aria-hidden': 'true' });
  body.append(caret);
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    caret.before(ch);
    sphere?.setLevel(/[aeiouáéíóúâêôãõ]/i.test(ch) ? 0.75 + Math.random() * 0.25 : /\s/.test(ch) ? 0.1 : 0.45);
    await new Promise((r) => setTimeout(r, /[.,;:!?]/.test(ch) ? 140 : 22));
    $('#transcript').scrollTop = $('#transcript').scrollHeight;
  }
  caret.remove();
  speaking--;
  if (!speaking) sphere?.setLevel(0);
  idleOrListening();
}

async function sendChat(text) {
  const box = $('#transcript');
  clearPending(box); // any new utterance drops the agent's pending action
  addMsg('me', text);
  try {
    const res = await withAgent(api.chat(text, state.conversationId));
    state.conversationId = res.conversation_id;
    await speak(res.content);
    if (res.pending_confirmation) {
      showPending(res.pending_confirmation.summary, box, {
        onConfirm: () => sendChat('sim'),
        onCancel: () => addMsg('system', 'Cancelado. Nada foi executado.'),
      });
      box.scrollTop = box.scrollHeight;
    }
    refreshAll(null, true);
  } catch (err) {
    if (err.status === 401) {
      if (!token.get()) return;
      return signOut('Token recusado. Entre de novo.');
    }
    addMsg('error', err.status === 502 ? 'O modelo não respondeu. Tente de novo.' : err.message);
  }
}

// ---------------------------------------------------------------- voice

const WAKE_KEY = 'byte.wake';
const TALK_WORD = { off: 'Falar', wake: 'Falar', connecting: 'Conectando', listening: 'Ouvindo', thinking: 'Pensando', speaking: 'Falando' };
const storedWake = {
  get: () => { try { return localStorage.getItem(WAKE_KEY) === '1'; } catch { return false; } },
  set: (on) => { try { localStorage.setItem(WAKE_KEY, on ? '1' : '0'); } catch { /* private mode */ } },
};

function voiceNote(text, isError = false) {
  const el = $('#voice-note');
  el.textContent = text;
  el.classList.toggle('error', isError);
}

const voice = createVoice({
  getToken: () => token.get(),
  getConversationId: () => state.conversationId,
  onConversation: (id) => { state.conversationId = id; },
  onLevel: (x) => sphere?.setLevel(x),
  onNotice: voiceNote,
  onClosing: (on) => {
    $('#voice').style.setProperty('--closing', `${IDLE_WARN_SECONDS}s`);
    $('#voice').toggleAttribute('data-closing', on);
  },
  onTranscript: (role, text) => {
    if (role === 'user') clearPending($('#transcript')); // a spoken utterance drops it server-side too
    addMsg(role === 'user' ? 'me' : 'agent', text);
  },
  onState: (next) => {
    const wasLive = Boolean(VOICE_AGENT[voiceState]);
    voiceState = next;
    $('#voice').dataset.voice = next;
    $('#talk-word').textContent = TALK_WORD[next];
    $('#talk').setAttribute('aria-label', VOICE_AGENT[next] ? `${TALK_WORD[next]}. Parar a conversa por voz` : 'Falar com o Byte');
    if (wasLive && !VOICE_AGENT[next]) refreshAll(null, true); // tools may have changed the house
    idleOrListening();
  },
});

function setWakeUi(on) {
  $('#wake-toggle').setAttribute('aria-pressed', String(on));
}

async function toggleWake() {
  const on = $('#wake-toggle').getAttribute('aria-pressed') !== 'true';
  setWakeUi(on);
  storedWake.set(on);
  if (!on) voiceNote('');
  const ok = await voice.setWake(on);
  if (on && !ok) { setWakeUi(false); storedWake.set(false); }
}

// Audio may only start after a user gesture, so a remembered "escuta ativa" waits for the first one.
function armStoredWake() {
  if (!storedWake.get()) return;
  voiceNote('Escuta ativa: toque em qualquer lugar da página para ligar o microfone.');
  const go = (e) => {
    removeEventListener('pointerdown', go, true);
    removeEventListener('keydown', go, true);
    if (e.target.closest?.('#wake-toggle') || !token.get()) return; // its own click decides
    setWakeUi(true);
    voice.setWake(true).then((ok) => { if (!ok) setWakeUi(false); });
  };
  addEventListener('pointerdown', go, true);
  addEventListener('keydown', go, true);
}

// ---------------------------------------------------------------- session

let gateSphere = null;
function showGate(message = '') {
  $('#app').hidden = true;
  $('#gate').hidden = false;
  gateSphere ??= createSphere($('#gate-orb'));
  $('#gate-error').textContent = message;
  $('#gate-token').setAttribute('aria-invalid', String(Boolean(message)));
  $('#gate-token').focus();
}

// Nothing the owner saw may stay in the DOM after signing out.
function wipePanel() {
  Object.assign(state, { lights: null, climates: null, music: null, devices: null, conversationId: null });
  devicesAt = 0;
  $('#music-devices').replaceChildren();
  $('#transcript').replaceChildren(h('p', { class: 't-empty' }, 'Escreva para o Byte. Ações destrutivas sempre pedem confirmação aqui.'));
  [...Object.values(BOX), '#agenda-list', '#finance-list'].forEach((sel) => $(sel).replaceChildren());
  $('#music-results').replaceChildren(h('li', {}, h('div', { class: 'empty-state' }, 'Busque uma faixa ou abra suas playlists.')));
  $('#finance-total').textContent = '—';
  $('#ex-cats').replaceChildren();
  $('#chat-input').value = '';
  document.querySelectorAll('.pending').forEach((p) => p.remove());
  document.querySelectorAll('.note').forEach((n) => { n.textContent = ''; });
}

function signOut(message = '') {
  token.clear();
  voice.shutdown();
  setWakeUi(false);
  voiceNote('');
  timers.forEach(clearInterval);
  timers = [];
  clearTimeout(pendingExpiry);
  wipePanel();
  showGate(message);
}

async function signIn(e) {
  e.preventDefault();
  const input = $('#gate-token');
  const value = input.value.trim();
  if (value.length < 32) return showGate('O token precisa ter pelo menos 32 caracteres.');
  const btn = $('button[type="submit"]', e.currentTarget);
  btn.setAttribute('aria-busy', 'true');
  btn.disabled = true;
  token.set(value);
  try {
    const s = await api.state();
    input.value = '';
    enter(s);
  } catch (err) {
    token.clear();
    showGate(err.status === 401 ? 'Token recusado pelo servidor.' : err.message);
  } finally {
    btn.removeAttribute('aria-busy');
    btn.disabled = false;
  }
}

function enter(initial) {
  $('#gate').hidden = true;
  $('#app').hidden = false;
  if (!sphere) sphere = createSphere($('#orb'));
  setAgent('idle');
  applyState(initial, false);
  if (initial.pending_confirmation) showPanelPending(initial.pending_confirmation.summary, null);
  loadAgenda();
  loadFinance();
  armStoredWake();
  timers.push(
    setInterval(() => { $('#clock').textContent = new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }); }, 1000),
    setInterval(tickMusic, 1000),
    // ponytail: polling every 20 s; switch to /ws/notifications pushes once it exists.
    setInterval(() => { if (!document.hidden && busy === 0) refreshAll(null, true); }, 20_000),
  );
}

// ---------------------------------------------------------------- wiring

// Marks the section nav link whose section sits in the upper band of the viewport.
function trackSections() {
  const links = [...document.querySelectorAll('.index a')];
  const seen = new Set();
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) (e.isIntersecting ? seen.add(e.target.id) : seen.delete(e.target.id));
    const current = links.find((a) => seen.has(a.hash.slice(1)));
    if (!current) return;
    links.forEach((a) => (a === current ? a.setAttribute('aria-current', 'location') : a.removeAttribute('aria-current')));
  }, { rootMargin: '-110px 0px -55% 0px' });
  links.forEach((a) => io.observe($(a.hash)));
}

// Connect devices come and go (a Chromecast sleeps), so the list reloads whenever Música comes
// into view, at most every 15 s.
function watchMusicSection() {
  new IntersectionObserver(([e]) => {
    if (e.isIntersecting && token.get() && Date.now() - devicesAt > 15_000) loadDevices();
  }).observe($('#sec-music'));
}

function wire() {
  trackSections();
  watchMusicSection();
  $('#devices-refresh').addEventListener('click', loadDevices);
  $('#gate-form').addEventListener('submit', signIn);
  $('#logout').addEventListener('click', () => signOut());

  document.querySelectorAll('[data-refresh]').forEach((b) => b.addEventListener('click', () => {
    const key = b.dataset.refresh;
    const box = $(BOX[key]);
    box.replaceChildren(box.tagName === 'UL' ? h('li', {}, skeleton()) : skeleton());
    refreshAll(key);
    if (key === 'music') loadDevices();
  }));

  const chatInput = $('#chat-input');
  $('#chat-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const text = chatInput.value.trim();
    if (!text) return;
    chatInput.value = '';
    sendChat(text);
  });
  $('#talk').addEventListener('click', () => voice.toggle());
  $('#wake-toggle').addEventListener('click', toggleWake);
  chatInput.addEventListener('input', idleOrListening);
  chatInput.addEventListener('blur', idleOrListening);

  $('#music-search').addEventListener('submit', (e) => {
    e.preventDefault();
    const q = $('#music-q').value.trim();
    if (q) loadResults(() => api.searchMusic(q, $('#music-kind').value), `Nada encontrado para "${q}".`);
  });
  $('#music-playlists').addEventListener('click', () => loadResults(api.playlists, 'Você ainda não tem playlists.'));

  $('#agenda-date').value = localDate();
  $('#agenda-date').addEventListener('change', () => loadAgenda());
  $('#day-prev').addEventListener('click', () => shiftDay(-1));
  $('#day-next').addEventListener('click', () => shiftDay(1));
  $('#event-form').addEventListener('submit', submitEvent);

  const now = new Date();
  $('#finance-month').value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  $('#finance-month').addEventListener('change', () => loadFinance());
  $('#ex-date').value = localDate();
  $('#expense-form').addEventListener('submit', submitExpense);
}

function formError(form, fields, message) {
  form.querySelectorAll('input').forEach((i) => i.removeAttribute('aria-invalid'));
  fields.forEach((f) => f.setAttribute('aria-invalid', 'true'));
  $('[data-form-error]', form).textContent = message;
  fields[0]?.focus();
  return Boolean(message);
}

function submitEvent(e) {
  e.preventDefault();
  const form = e.currentTarget;
  const title = $('#ev-title');
  const time = $('#ev-time');
  const dur = $('#ev-dur');
  const bad = [!title.value.trim() && title, !time.value && time, !(Number(dur.value) > 0) && dur].filter(Boolean);
  if (formError(form, bad, bad.length ? 'Preencha título, início e uma duração maior que zero.' : '')) return;
  const date = $('#agenda-date').value;
  runAction('agenda', () => api.createEvent({
    title: title.value.trim(), start: `${date}T${time.value}:00${tzOffset()}`, duration_minutes: Number(dur.value),
  }), () => { title.value = ''; });
}

function submitExpense(e) {
  e.preventDefault();
  const form = e.currentTarget;
  const amount = $('#ex-amount');
  const cat = $('#ex-cat');
  const desc = $('#ex-desc');
  const date = $('#ex-date');
  const cents = parseCents(amount.value);
  const bad = [!(cents > 0) && amount, !cat.value.trim() && cat, !date.value && date, !desc.value.trim() && desc].filter(Boolean);
  if (formError(form, bad, bad.length ? 'Confira o valor (ex.: 54,30), a categoria, a data e a descrição.' : '')) return;
  runAction('finance', () => api.addExpense({
    amount_cents: cents, category: cat.value.trim(), description: desc.value.trim(), date: date.value,
  }), () => { amount.value = ''; desc.value = ''; });
}

// ---------------------------------------------------------------- boot

wire();
if (MOCK) document.querySelectorAll('.mock-only').forEach((el) => { el.hidden = false; });
if (token.get()) {
  $('#app').hidden = false;
  Object.values(BOX).forEach((sel) => $(sel).replaceChildren(skeleton()));
  api.state().then(enter).catch((err) => signOut(err.status === 401 ? 'Sessão expirada. Entre de novo.' : err.message));
} else {
  showGate();
}
