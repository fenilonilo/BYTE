// Lynus's core: a holographic neural cloud. An organic body of light points with tendrils
// reaching out, every point wired to its nearest neighbours, impulses hopping through the
// wiring, all drawn with additive light. Canvas 2D, same contract as the Byte orb (sphere.js).

// Every parameter eases toward the target state, so a phase change never snaps.
const STATES = {
  idle:     { spin: 0.05, signals: 4,  bright: 0.75, breath: 0.6, flicker: 0.02, hue: 0 },
  talking:  { spin: 0.09, signals: 14, bright: 0.92, breath: 1.0, flicker: 0.03, hue: 0 },
  thinking: { spin: 0.20, signals: 55, bright: 1.08, breath: 1.8, flicker: 0.06, hue: 0 },
  working:  { spin: 0.13, signals: 32, bright: 1.00, breath: 1.3, flicker: 0.04, hue: 0 },
  done:     { spin: 0.04, signals: 3,  bright: 0.80, breath: 0.5, flicker: 0.01, hue: 1 },
  failed:   { spin: 0.02, signals: 0,  bright: 0.50, breath: 0.3, flicker: 0.12, hue: 2 },
};
const PARAMS = Object.keys(STATES.idle);
const EASE_RATE = 2.2;
const PERSPECTIVE = 3.0;
const TINTS = [[63, 216, 255], [140, 230, 170], [235, 120, 96]]; // cyan, done green, failed red
const NEIGHBOURS = 3;
const LINK_REACH = 0.3;
const BUCKETS = 6;
const SPRITE = 32;

const rand = (a, b) => a + Math.random() * (b - a);

function unitVector() {
  const z = rand(-1, 1), t = rand(0, Math.PI * 2), r = Math.sqrt(1 - z * z);
  return [Math.cos(t) * r, Math.sin(t) * r, z];
}

// An organic outline: a few random lobes push the surface in and out.
function shaper() {
  const lobes = Array.from({ length: 6 }, () => [rand(-2.4, 2.4), rand(-2.4, 2.4), rand(-2.4, 2.4), rand(0, 7)]);
  return ([x, y, z]) => 1 + 0.5 * lobes.reduce((s, [a, b, c, p]) => s + Math.sin(a * x + b * y + c * z + p), 0) / lobes.length;
}

function cloud(n, shape) {
  const pts = [];
  const add = (x, y, z, kind) => pts.push({ x, y, z, kind, seed: rand(0, Math.PI * 2) });
  // The body: denser toward the centre, like a mind lit from inside.
  for (let i = 0; i < n * 0.62; i++) {
    const d = unitVector();
    const r = Math.pow(Math.random(), 0.55) * 0.78 * shape(d);
    add(d[0] * r, d[1] * r, d[2] * r, 0);
  }
  // Tendrils: thin streams curling out of the body.
  const tendrils = 14;
  const per = Math.floor((n * 0.38) / tendrils);
  for (let k = 0; k < tendrils; k++) {
    const d = unitVector();
    const axis = unitVector();
    const twist = rand(0.6, 1.6) * (Math.random() < 0.5 ? -1 : 1);
    for (let i = 0; i < per; i++) {
      const s = i / per;
      const a = s * twist;
      // Rodrigues rotation of d around axis by a: the stream bends as it leaves the body.
      const c = Math.cos(a), sn = Math.sin(a), dot = d[0] * axis[0] + d[1] * axis[1] + d[2] * axis[2];
      const v = [0, 1, 2].map((j) => d[j] * c + (axis[(j + 1) % 3] * d[(j + 2) % 3] - axis[(j + 2) % 3] * d[(j + 1) % 3]) * sn + axis[j] * dot * (1 - c));
      const r = (0.45 + s * 0.5) * shape(d);
      const j = 0.03 + s * 0.05;
      add(v[0] * r + rand(-j, j), v[1] * r + rand(-j, j), v[2] * r + rand(-j, j), 1);
    }
  }
  return pts;
}

// Fine dust filling the volume: no wiring, it only gives the cloud its density.
function dust(n, shape) {
  return Array.from({ length: n }, () => {
    const d = unitVector();
    const r = Math.pow(Math.random(), 0.8) * 0.85 * shape(d);
    return { x: d[0] * r, y: d[1] * r, z: d[2] * r, seed: rand(0, Math.PI * 2) };
  });
}

// The random lobes and tendrils pull the mass to one side: move the centroid onto the spin
// axis so the cloud sits centred in its column at every angle.
function centre(pts, motes) {
  const c = [0, 0, 0];
  for (const p of pts) { c[0] += p.x; c[1] += p.y; c[2] += p.z; }
  for (const p of [...pts, ...motes]) {
    p.x -= c[0] / pts.length; p.y -= c[1] / pts.length; p.z -= c[2] / pts.length;
  }
}

function wire(pts) {
  const near = pts.map(() => []);
  const edges = [];
  const seen = new Set();
  for (let i = 0; i < pts.length; i++) {
    const best = [];
    for (let j = 0; j < pts.length; j++) {
      if (i === j) continue;
      const dx = pts[i].x - pts[j].x, dy = pts[i].y - pts[j].y, dz = pts[i].z - pts[j].z;
      const d = dx * dx + dy * dy + dz * dz;
      if (d > LINK_REACH * LINK_REACH) continue;
      best.push([d, j]);
    }
    best.sort((a, b) => a[0] - b[0]);
    for (const [, j] of best.slice(0, NEIGHBOURS)) {
      near[i].push(j);
      near[j].push(i);
      const key = i < j ? i * 100000 + j : j * 100000 + i;
      if (!seen.has(key)) { seen.add(key); edges.push([i, j]); }
    }
  }
  return { near, edges };
}

function glowSprite([r, g, b]) {
  const c = document.createElement('canvas');
  c.width = c.height = SPRITE;
  const x = c.getContext('2d');
  const grad = x.createRadialGradient(SPRITE / 2, SPRITE / 2, 0, SPRITE / 2, SPRITE / 2, SPRITE / 2);
  grad.addColorStop(0, 'rgba(255,255,255,1)');
  grad.addColorStop(0.18, `rgba(${r},${g},${b},0.9)`);
  grad.addColorStop(0.5, `rgba(${r},${g},${b},0.18)`);
  grad.addColorStop(1, `rgba(${r},${g},${b},0)`);
  x.fillStyle = grad;
  x.fillRect(0, 0, SPRITE, SPRITE);
  return c;
}

/** Mount the core on `canvas`. Returns { setState(name) }. */
export function createLynusCore(canvas) {
  const ctx = canvas.getContext('2d');
  const motionQuery = matchMedia('(prefers-reduced-motion: reduce)');
  let reduced = motionQuery.matches;
  const small = Math.min(innerWidth, innerHeight) < 600;
  const shape = shaper(); // body, tendrils and dust share one outline
  const pts = cloud(small ? 700 : 1600, shape);
  const motes = dust(small ? 1000 : 2600, shape);
  centre(pts, motes);
  const bloom = document.createElement('canvas');
  const bctx = bloom.getContext('2d');
  const { near, edges } = wire(pts);
  const n = pts.length;
  const sx = new Float32Array(n), sy = new Float32Array(n), depth = new Float32Array(n);
  const flash = new Float32Array(n);
  const spread = new Float32Array(n);
  const sprites = TINTS.map(glowSprite);
  const paths = Array.from({ length: BUCKETS }, () => new Path2D());
  let signals = [];
  const cur = { ...STATES.idle };
  let target = STATES.idle;
  let angle = 0, time = 0, spawn = 0, offX = 0;
  let W = 0, H = 0, raf = 0, last = performance.now();

  function fit() {
    const r = canvas.getBoundingClientRect();
    const dpr = Math.min(devicePixelRatio || 1, 2);
    W = r.width; H = r.height;
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    bloom.width = Math.max(1, Math.round(W / 2));
    bloom.height = Math.max(1, Math.round(H / 2));
    if (!W || !H) return stop(); // hidden: no frames at all
    start();
  }

  function step(dt) {
    const k = Math.min(1, dt * EASE_RATE);
    for (const p of PARAMS) cur[p] += (target[p] - cur[p]) * k;
    const motion = reduced ? 0.15 : 1;
    time += dt * motion;
    angle += dt * cur.spin * motion;
    for (let i = 0; i < n; i++) flash[i] *= Math.pow(0.015, dt);

    // Impulses: born on a random point, hop neighbour to neighbour, light each one they reach.
    spawn += dt * cur.signals * (reduced ? 0.1 : 1);
    while (spawn >= 1) {
      spawn -= 1;
      const at = (Math.random() * n) | 0;
      if (near[at].length) signals.push({ from: at, to: near[at][(Math.random() * near[at].length) | 0], t: 0, hops: 4 + ((Math.random() * 8) | 0) });
    }
    for (const s of signals) {
      s.t += dt * 7;
      if (s.t < 1) continue;
      flash[s.to] = 1;
      s.hops -= 1;
      const next = near[s.to].filter((j) => j !== s.from);
      if (!next.length || s.hops <= 0) { s.dead = true; continue; }
      s.from = s.to;
      s.to = next[(Math.random() * next.length) | 0];
      s.t = 0;
    }
    signals = signals.filter((s) => !s.dead);
  }

  function draw() {
    if (!W) return;
    ctx.globalCompositeOperation = 'source-over';
    ctx.clearRect(0, 0, W, H);
    ctx.globalCompositeOperation = 'lighter'; // light adds up: the hologram look
    const cy = H / 2;
    const R = Math.min(W, H) * 0.4;
    const tint = TINTS[Math.round(cur.hue)];
    const sprite = sprites[Math.round(cur.hue)];
    const flick = 1 - cur.flicker * Math.random();
    const bright = cur.bright * flick;
    const rotY = angle, rotX = 0.3 + Math.sin(time * 0.21) * 0.15;
    const cY = Math.cos(rotY), sY = Math.sin(rotY), cX = Math.cos(rotX), sX = Math.sin(rotX);

    for (let i = 0; i < n; i++) {
      const p = pts[i];
      const b = 1 + Math.sin(time * 1.3 + p.seed) * 0.025 * cur.breath;
      const x = (p.x * cY + p.z * sY) * b;
      const z0 = (-p.x * sY + p.z * cY) * b;
      const y = p.y * b * cX - z0 * sX;
      const z = p.y * b * sX + z0 * cX;
      const f = PERSPECTIVE / (PERSPECTIVE - z);
      sx[i] = x * R * f;
      sy[i] = cy + y * R * f;
      depth[i] = Math.min(1, Math.max(0, (z + 1.3) / 2.6));
    }
    // Keep the outline centred in the column at every angle: as the cloud turns, lobes and
    // tendrils swing out to one side. The 5th..95th percentile ignores a lone tendril; eased,
    // so it never jumps.
    spread.set(sx);
    spread.sort();
    const mid = (spread[(n * 0.05) | 0] + spread[(n * 0.95) | 0]) / 2;
    offX += (-mid - offX) * 0.08;
    const cx = W / 2 + offX;
    for (let i = 0; i < n; i++) sx[i] += cx;

    // The hot centre the whole cloud seems lit from.
    const core = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 0.9);
    core.addColorStop(0, `rgba(220,250,255,${0.22 * bright})`);
    core.addColorStop(0.25, `rgba(${tint},${0.12 * bright})`);
    core.addColorStop(1, `rgba(${tint},0)`);
    ctx.fillStyle = core;
    ctx.fillRect(cx - R, cy - R, R * 2, R * 2);

    // Filaments, bucketed by brightness so the whole web is a handful of strokes.
    for (let b = 0; b < BUCKETS; b++) paths[b] = new Path2D();
    for (const [a, c] of edges) {
      const lit = (depth[a] + depth[c]) / 2 + (flash[a] + flash[c]) * 0.6;
      const b = Math.min(BUCKETS - 1, (lit * (BUCKETS - 1)) | 0);
      paths[b].moveTo(sx[a], sy[a]);
      paths[b].lineTo(sx[c], sy[c]);
    }
    for (let b = 0; b < BUCKETS; b++) {
      const level = b / (BUCKETS - 1);
      ctx.lineWidth = 0.8;
      ctx.strokeStyle = `rgba(${tint},${(0.06 + level * 0.5) * bright})`;
      ctx.stroke(paths[b]);
      if (level < 0.6) continue;
      ctx.lineWidth = 3; // a soft halo round the brightest strands
      ctx.strokeStyle = `rgba(${tint},${level * 0.1 * bright})`;
      ctx.stroke(paths[b]);
    }

    // Dust: one-pixel motes, fainter at the back.
    ctx.fillStyle = `rgb(${tint})`;
    for (const m of motes) {
      const b = 1 + Math.sin(time * 1.1 + m.seed) * 0.03 * cur.breath;
      const x = (m.x * cY + m.z * sY) * b;
      const z0 = (-m.x * sY + m.z * cY) * b;
      const y = m.y * b * cX - z0 * sX;
      const z = m.y * b * sX + z0 * cX;
      const f = PERSPECTIVE / (PERSPECTIVE - z);
      ctx.globalAlpha = (0.12 + (z + 1) * 0.22) * bright;
      ctx.fillRect(cx + x * R * f, cy + y * R * f, 1.2, 1.2);
    }

    // Points of light: nearer ones bigger and brighter, flashed ones burn white.
    for (let i = 0; i < n; i++) {
      const d = depth[i];
      const s = (pts[i].kind ? 3.2 : 4.2) * (0.5 + d) + flash[i] * 9;
      ctx.globalAlpha = Math.min(1, (0.12 + d * 0.55 + flash[i]) * bright);
      ctx.drawImage(sprite, sx[i] - s / 2, sy[i] - s / 2, s, s);
    }

    // Impulses in flight: a white-hot head and a streak behind it.
    ctx.lineWidth = 1.4;
    ctx.strokeStyle = 'rgba(230,252,255,0.9)';
    ctx.globalAlpha = Math.min(1, bright);
    for (const sg of signals) {
      const hx = sx[sg.from] + (sx[sg.to] - sx[sg.from]) * sg.t;
      const hy = sy[sg.from] + (sy[sg.to] - sy[sg.from]) * sg.t;
      ctx.beginPath(); ctx.moveTo(sx[sg.from], sy[sg.from]); ctx.lineTo(hx, hy); ctx.stroke();
      ctx.drawImage(sprite, hx - 7, hy - 7, 14, 14);
    }
    // Bloom: a blurred half-size copy of the frame added back on top.
    bctx.clearRect(0, 0, bloom.width, bloom.height);
    bctx.filter = 'blur(6px)';
    bctx.drawImage(canvas, 0, 0, bloom.width, bloom.height);
    bctx.filter = 'none';
    ctx.globalAlpha = 0.85;
    ctx.drawImage(bloom, 0, 0, W, H);
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = 'source-over';
  }

  function frame(now) {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    step(dt);
    draw();
    raf = requestAnimationFrame(frame);
  }

  function start() {
    if (raf || document.hidden || !W || !H) return;
    last = performance.now();
    raf = requestAnimationFrame(frame);
  }
  function stop() { cancelAnimationFrame(raf); raf = 0; }

  document.addEventListener('visibilitychange', () => (document.hidden ? stop() : start()));
  motionQuery.addEventListener('change', (e) => { reduced = e.matches; });
  new ResizeObserver(fit).observe(canvas);
  fit();

  return {
    setState(name) {
      if (STATES[name]) target = STATES[name];
    },
  };
}
