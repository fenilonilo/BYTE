// The only module that talks to the network. Contract: docs/web-api-contract.md.
// `?mock=1` swaps fetch for an in-browser fake that implements the same routes.

const BASE = '/api/v1';
const TOKEN_KEY = 'byte.token';
export const MOCK = new URLSearchParams(location.search).get('mock') === '1';

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export const token = {
  get: () => { try { return sessionStorage.getItem(TOKEN_KEY); } catch { return null; } },
  set: (t) => { try { sessionStorage.setItem(TOKEN_KEY, t); } catch { /* private mode */ } },
  clear: () => { try { sessionStorage.removeItem(TOKEN_KEY); } catch { /* private mode */ } },
};

async function request(method, path, body) {
  const res = MOCK ? await mockRoute(method, path, body) : await send(method, path, body);
  if (res.status >= 400) {
    // FastAPI validation errors (422) carry a list of {msg}; domain errors carry a string.
    const d = res.json?.detail;
    const detail = typeof d === 'string' ? d : Array.isArray(d) ? d.map((e) => e.msg).join('; ') : null;
    throw new ApiError(res.status, detail || `Erro ${res.status}`);
  }
  return res.json;
}

async function send(method, path, body) {
  const headers = { Authorization: `Bearer ${token.get() || ''}` };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  let res;
  try {
    res = await fetch(BASE + path, {
      method, headers, body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'Sem conexão com o servidor.');
  }
  const json = await res.json().catch(() => null);
  return { status: res.status, json };
}

const q = (params) => '?' + new URLSearchParams(params).toString();
const seg = encodeURIComponent;

export const api = {
  state: () => request('GET', '/state'),
  lights: () => request('GET', '/lights'),
  setLight: (name, change) => request('PATCH', `/lights/${seg(name)}`, change),
  climates: () => request('GET', '/climate'),
  setClimate: (name, change) => request('PATCH', `/climate/${seg(name)}`, change),
  music: () => request('GET', '/music/state'),
  searchMusic: (query, kind) => request('GET', '/music/search' + q({ q: query, kind })),
  playlists: () => request('GET', '/music/playlists'),
  musicDevices: () => request('GET', '/music/devices'),
  selectMusicDevice: (name) => request('POST', '/music/device', { name }),
  play: (body) => request('POST', '/music/play', body),
  controlMusic: (change) => request('POST', '/music/control', change),
  events: (date) => request('GET', '/agenda' + q({ date })),
  createEvent: (event) => request('POST', '/agenda', event),
  deleteEvent: (id) => request('DELETE', `/agenda/${seg(id)}`),
  expenses: (year, month) => request('GET', '/finance/expenses' + q({ year, month })),
  addExpense: (expense) => request('POST', '/finance/expenses', expense),
  reminders: () => request('GET', '/reminders'),
  createReminder: (reminder) => request('POST', '/reminders', reminder),
  cancelReminder: (id) => request('DELETE', `/reminders/${seg(id)}`),
  confirm: (approve) => request('POST', '/confirm', { approve }),
  chat: (content, conversationId) => request('POST', '/messages', {
    content, client: 'panel', ...(conversationId ? { conversation_id: conversationId } : {}),
  }),
};

// ---------------------------------------------------------------------------
// Mock adapter. Mirrors the server's rules: one pending action, 60 s expiry,
// any other action drops it, lamp toggle guard, climate refuses changes when off.
// ---------------------------------------------------------------------------

const today = () => new Date().toLocaleDateString('sv-SE');
const ymd = (offsetDays) => {
  const d = new Date(); d.setDate(d.getDate() + offsetDays);
  return d.toLocaleDateString('sv-SE');
};
const monthDay = (d) => {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), Math.min(d, now.getDate())).toLocaleDateString('sv-SE');
};
const tz = () => {
  const m = -new Date().getTimezoneOffset();
  const s = m >= 0 ? '+' : '-';
  const a = Math.abs(m);
  return `${s}${String(Math.floor(a / 60)).padStart(2, '0')}:${String(a % 60).padStart(2, '0')}`;
};

const inMinutes = (m) => new Date(Date.now() + m * 60_000).toISOString();

const db = {
  lights: [
    { name: 'Sala', power: true, mode: 'white', brightness: 72, color_temperature: 28,
      color: { hue: 0, saturation: 0, brightness: 72 }, timer_seconds: 0, do_not_disturb: false },
    { name: 'Quarto', power: false, mode: 'white', brightness: 40, color_temperature: 10,
      color: { hue: 0, saturation: 0, brightness: 40 }, timer_seconds: 0, do_not_disturb: false },
    { name: 'Escritório', power: true, mode: 'colour', brightness: 64, color_temperature: 50,
      color: { hue: 34, saturation: 82, brightness: 64 }, timer_seconds: 0, do_not_disturb: false },
  ],
  climates: [
    { name: 'Ar do quarto', power: false, mode: 'cool', target_temperature: 23,
      current_temperature: 26.5, fan_speed: 'auto', swing: false, power_save: false,
      display_light: true, has_error: false },
  ],
  music: {
    playing: true, progress_ms: 84_000, duration_ms: 241_000, volume: 38, shuffle: false,
    repeat: 'off', device: 'Echo da sala',
    item: { uri: 'spotify:playlist:7xQm', name: 'Foco noturno', kind: 'playlist', artist: 'Byte' },
  },
  // `?mock=1&devices=0` starts with every Connect device asleep (the empty state).
  devices: new URLSearchParams(location.search).get('devices') === '0' ? [] : [
    { name: 'Echo da sala', active: true, volume: 38 },
    { name: 'BatCaverna', active: false, volume: 64 },
    { name: 'Notebook do Felipe', active: false, volume: null },
  ],
  defaultDevice: 'BatCaverna',
  catalog: [
    { uri: 'spotify:track:4aN1', name: 'Clair de Lune', kind: 'track', artist: 'Claude Debussy' },
    { uri: 'spotify:track:9kLe', name: 'Águas de Março', kind: 'track', artist: 'Elis Regina' },
    { uri: 'spotify:track:2bTr', name: 'Teardrop', kind: 'track', artist: 'Massive Attack' },
    { uri: 'spotify:album:5hZu', name: 'Clube da Esquina', kind: 'album', artist: 'Milton Nascimento' },
    { uri: 'spotify:artist:1mVp', name: 'Tim Maia', kind: 'artist', artist: 'Tim Maia' },
    { uri: 'spotify:playlist:3lof', name: 'Lo-fi para programar', kind: 'playlist', artist: 'Spotify' },
  ],
  playlists: [
    { uri: 'spotify:playlist:7xQm', name: 'Foco noturno', kind: 'playlist', artist: 'Byte' },
    { uri: 'spotify:playlist:0dmn', name: 'Domingo devagar', kind: 'playlist', artist: 'Felipe' },
    { uri: 'spotify:playlist:8trn', name: 'Treino 140 bpm', kind: 'playlist', artist: 'Felipe' },
  ],
  events: [
    { id: 'evt_7f3a', title: 'Dentista, Dra. Lívia Okada', start: `${today()}T09:30:00${tz()}`, duration_minutes: 45 },
    { id: 'evt_b21c', title: 'Revisão do contrato do apartamento', start: `${today()}T14:00:00${tz()}`, duration_minutes: 60 },
    { id: 'evt_c904', title: 'Futsal com o pessoal', start: `${today()}T19:15:00${tz()}`, duration_minutes: 90 },
    { id: 'evt_d55e', title: 'Pagar IPVA', start: `${ymd(1)}T10:00:00${tz()}`, duration_minutes: 15 },
  ],
  expenses: [
    { amount_cents: 31247, category: 'mercado', description: 'Compra do mês, Pão de Açúcar', date: monthDay(1) },
    { amount_cents: 18690, category: 'contas', description: 'Conta de luz', date: monthDay(2) },
    { amount_cents: 11999, category: 'contas', description: 'Internet fibra', date: monthDay(3) },
    { amount_cents: 5430, category: 'saúde', description: 'Farmácia', date: monthDay(5) },
    { amount_cents: 21864, category: 'transporte', description: 'Gasolina', date: monthDay(6) },
  ],
  // Due ones vanish 20 s after their time, as if the device had played them and acked.
  reminders: [
    { id: 'a1b2c3', text: 'Tomar o remédio', at: inMinutes(1.5), kind: 'lembrete' },
    { id: '9f8e7d', text: 'Tirar a roupa da máquina', at: inMinutes(38), kind: 'lembrete' },
    { id: 'd4e5f6', text: 'Acordar', at: `${ymd(1)}T07:00:00${tz()}`, kind: 'alarme' },
  ],
  pending: null,
  chatPending: null,
  lastToggle: {},
  seq: 1,
};
if (!db.devices.length) Object.assign(db.music, { device: null, playing: false });

const ok = (json) => ({ status: 200, json });
const fail = (status, detail) => ({ status, json: { detail } });
const done = (message) => ok({ status: 'done', message, pending_confirmation: null });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const clone = (x) => JSON.parse(JSON.stringify(x));

function ask(summary, run) {
  db.pending = { summary, run, expires: Date.now() + 60_000 };
  return ok({ status: 'pending_confirmation', message: summary, pending_confirmation: { summary } });
}
const livePending = () => (db.pending && db.pending.expires > Date.now() ? db.pending : null);

function describeLight(l) {
  return `${l.name}: ${l.power ? 'ligada' : 'desligada'}, brilho ${l.brightness}%`;
}

async function mockRoute(method, path, body) {
  await sleep(220 + Math.random() * 380);
  const [route, query] = path.split('?');
  const params = new URLSearchParams(query || '');
  const parts = route.split('/').filter(Boolean).map(decodeURIComponent);
  if ((token.get() || '').length < 32) return fail(401, 'Invalid token');
  if (method !== 'GET' && route !== '/confirm' && route !== '/messages') db.pending = null;

  const [head, sub] = parts;
  if (method === 'GET' && head === 'state') {
    const p = livePending();
    return ok({
      lights: clone(db.lights), climates: clone(db.climates), music: clone(db.music),
      pending_confirmation: p ? { summary: p.summary } : null, errors: [],
    });
  }
  if (head === 'lights') {
    if (method === 'GET') return ok({ lights: clone(db.lights) });
    const light = db.lights.find((l) => l.name === sub);
    if (!light) return fail(422, `luz desconhecida: ${sub}`);
    if ('power' in body) {
      const lastAt = db.lastToggle[light.name] || 0;
      if (Date.now() - lastAt < 5000) {
        return fail(422, 'aguarde alguns segundos antes de ligar ou desligar a mesma luz de novo');
      }
      db.lastToggle[light.name] = Date.now();
      light.power = body.power;
    }
    if ('brightness' in body) { light.brightness = body.brightness; light.mode = 'white'; light.power = true; }
    if ('hue' in body) { light.mode = 'colour'; light.color.hue = body.hue; light.power = true; }
    return done(describeLight(light));
  }
  if (head === 'climate') {
    if (method === 'GET') return ok({ climates: clone(db.climates) });
    const c = db.climates.find((x) => x.name === sub);
    if (!c) return fail(422, `ar-condicionado desconhecido: ${sub}`);
    const apply = () => {
      Object.assign(c, body);
      return `${c.name}: ${c.power ? 'ligado' : 'desligado'}, alvo ${c.target_temperature}°C`;
    };
    if ('power' in body) {
      return ask(`${body.power ? 'Ligar' : 'Desligar'} ${c.name}`, apply);
    }
    if (!c.power) return fail(422, 'o aparelho está desligado: ligue-o antes de ajustar');
    const t = body.target_temperature;
    if (t !== undefined && (t < 18 || t > 30 || (t * 2) % 1 !== 0)) {
      return fail(422, 'temperatura alvo deve ficar entre 18 e 30, de 0,5 em 0,5');
    }
    return done(apply());
  }
  if (head === 'music') {
    const m = db.music;
    if (method === 'GET' && sub === 'state') {
      if (m.playing) m.progress_ms += 4000;
      if (m.progress_ms >= m.duration_ms) nextTrack(m, m.progress_ms - m.duration_ms);
      return ok(clone(m));
    }
    if (method === 'GET' && sub === 'playlists') return ok({ items: clone(db.playlists) });
    if (method === 'GET' && sub === 'devices') return ok({ devices: clone(db.devices), default: db.defaultDevice });
    if (method === 'POST' && sub === 'device') {
      const target = db.devices.find((d) => d.name === body.name);
      if (!target) return fail(422, `Aparelho desconhecido: ${body.name}`);
      db.devices.forEach((d) => { d.active = d === target; });
      m.device = target.name;
      return done(`Reprodução movida para ${target.name}`);
    }
    if (method === 'GET' && sub === 'search') {
      const term = (params.get('q') || '').toLowerCase();
      const kind = params.get('kind') || 'track';
      const items = db.catalog.filter((i) => i.kind === kind &&
        (i.name.toLowerCase().includes(term) || i.artist.toLowerCase().includes(term)));
      return ok({ items: clone(items) });
    }
    if (method === 'POST' && sub === 'play') {
      if (body.uri) {
        const item = [...db.catalog, ...db.playlists].find((i) => i.uri === body.uri);
        if (!item) return fail(422, 'uri desconhecida: busque antes de tocar');
        m.item = clone(item); m.progress_ms = 0; m.duration_ms = 180_000 + (item.name.length * 7919) % 120_000;
      }
      m.playing = true;
      return done(`Tocando ${m.item?.name ?? ''}`.trim());
    }
    if (method === 'POST' && sub === 'control') {
      if ('paused' in body) m.playing = !body.paused;
      if ('volume' in body) m.volume = body.volume;
      if ('shuffle' in body) m.shuffle = body.shuffle;
      if ('repeat' in body) m.repeat = body.repeat;
      if (body.skip) { nextTrack(m, 0, body.skip === 'previous' ? -1 : 1); m.playing = true; }
      return done(m.playing ? 'Reproduzindo' : 'Pausado');
    }
  }
  if (head === 'agenda') {
    if (method === 'GET') {
      const date = params.get('date');
      const events = db.events.filter((e) => e.start.startsWith(date))
        .sort((a, b) => a.start.localeCompare(b.start));
      return ok({ events: clone(events) });
    }
    if (method === 'POST') {
      if (!body.title || !(body.duration_minutes > 0)) return fail(422, 'título e duração são obrigatórios');
      const e = { id: `evt_${(db.seq++).toString(16).padStart(4, '0')}`, ...body };
      db.events.push(e);
      return done(`Evento criado: ${e.title}`);
    }
    if (method === 'DELETE') {
      const e = db.events.find((x) => x.id === sub);
      if (!e) return fail(422, `evento desconhecido: ${sub}`);
      const when = new Date(e.start).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
      return ask(`Apagar o evento "${e.title}" (${when})`, () => {
        db.events = db.events.filter((x) => x.id !== sub);
        return `Evento apagado: ${e.title}`;
      });
    }
  }
  if (head === 'finance') {
    if (method === 'GET') {
      const prefix = `${params.get('year')}-${String(params.get('month')).padStart(2, '0')}`;
      const expenses = db.expenses.filter((e) => e.date.startsWith(prefix))
        .sort((a, b) => b.date.localeCompare(a.date));
      return ok({ expenses: clone(expenses), total_cents: expenses.reduce((s, e) => s + e.amount_cents, 0) });
    }
    if (!(body.amount_cents > 0)) return fail(422, 'valor deve ser positivo');
    const brl = (body.amount_cents / 100).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
    return ask(`Registrar ${brl} em ${body.category}: ${body.description}`, () => {
      db.expenses.push({ ...body });
      return `Gasto registrado: ${brl}`;
    });
  }
  if (head === 'reminders') {
    if (method === 'GET') {
      db.reminders = db.reminders.filter((r) => new Date(r.at).getTime() + 20_000 > Date.now());
      return ok({ reminders: clone(db.reminders) });
    }
    if (method === 'DELETE') {
      if (!db.reminders.some((r) => r.id === sub)) return fail(422, `Unknown reminder: '${sub}'`);
      db.reminders = db.reminders.filter((r) => r.id !== sub);
      return done(`${sub} cancelado`);
    }
    if (!['lembrete', 'alarme'].includes(body.kind)) return fail(422, 'kind inválido');
    if (new Date(body.at) <= Date.now()) return fail(422, 'esse horário já passou');
    const r = { id: (db.seq++ * 0x9e3779b1 >>> 0).toString(16).slice(0, 6), ...body };
    db.reminders.push(r);
    return done(`${r.kind} ${r.id} ${new Date(r.at).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })}`);
  }
  if (head === 'confirm') {
    const p = livePending();
    db.pending = null;
    if (!body.approve) return ok({ status: 'cancelled', message: 'Cancelado', pending_confirmation: null });
    if (!p) return fail(409, 'nada pendente para confirmar');
    return done(p.run());
  }
  if (head === 'messages') return mockChat(body);
  return fail(404, 'Not found');
}

// Loops through the track catalog, like a playlist on repeat.
function nextTrack(m, carryMs, step = 1) {
  const pool = db.catalog.filter((i) => i.kind === 'track');
  const at = pool.findIndex((i) => i.uri === m.item?.uri);
  const item = pool[(at + step + pool.length) % pool.length];
  m.item = clone(item);
  m.duration_ms = 180_000 + (item.name.length * 7919) % 120_000;
  m.progress_ms = Math.min(carryMs, m.duration_ms - 1);
}

function mockChat({ content, conversation_id: cid }) {
  const text = content.toLowerCase();
  const reply = (msg, pending = null) => ok({
    id: `msg_${db.seq++}`, role: 'assistant', content: msg,
    conversation_id: cid || 'web_mock', pending_confirmation: pending,
  });
  const p = db.chatPending;
  db.chatPending = null;
  if (p && /\b(sim|pode|confirmo|confirma|isso)\b/.test(text)) return reply(p.run());
  if (/\b(apag|delet|remov)\w*\b.*\b(evento|compromisso)/.test(text)) {
    const e = db.events.find((x) => x.start.startsWith(today()));
    if (!e) return reply('Não há eventos hoje para apagar.');
    db.chatPending = { run: () => { db.events = db.events.filter((x) => x !== e); return `Pronto, apaguei "${e.title}".`; } };
    return reply(`Posso apagar "${e.title}"? Confirme para eu seguir.`, { summary: `Apagar o evento "${e.title}"` });
  }
  if (/\b(luz|lâmpada|lampada)\b/.test(text)) {
    const on = !/\b(apag|deslig)/.test(text);
    const plain = (x) => x.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    const light = db.lights.find((l) => plain(text).includes(plain(l.name))) || db.lights[0];
    light.power = on;
    return reply(`${on ? 'Acendi' : 'Apaguei'} a luz ${light.name}.`);
  }
  if (/\b(gast|despes)/.test(text)) {
    const total = db.expenses.reduce((s, e) => s + e.amount_cents, 0) / 100;
    return reply(`Neste mês você gastou ${total.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}.`);
  }
  if (/\b(agenda|hoje|compromisso)/.test(text)) {
    const n = db.events.filter((e) => e.start.startsWith(today())).length;
    return reply(`Você tem ${n} compromisso${n === 1 ? '' : 's'} hoje.`);
  }
  return reply('Modo de demonstração: posso acender a luz, falar da agenda, dos gastos ou apagar um evento.');
}
