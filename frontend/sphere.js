// The agent orb: a holographic core (frontend/nova_interface). Particle rings orbit a glowing
// sphere over a pulsing platform, with a waveform below. Canvas 2D, additive light.

// Every parameter eases toward the target state, so no state change snaps. `orbit` scales the
// particle speed, `spin` the ring precession, `listen` / `talk` how much the mic or voice level
// drives the core and the waveform.
const STATES = {
  idle:      { orbit: 1.0, spin: 1.0, wave: 0.45, bright: 0.85, listen: 0, talk: 0 },
  listening: { orbit: 1.2, spin: 1.0, wave: 0.6,  bright: 1.0,  listen: 1, talk: 0 },
  thinking:  { orbit: 3.2, spin: 5.0, wave: 0.3,  bright: 1.0,  listen: 0, talk: 0 },
  speaking:  { orbit: 1.4, spin: 1.6, wave: 0.5,  bright: 1.0,  listen: 0, talk: 1 },
};
const EASE_RATE = 3.5; // per second; higher snaps faster
const EASE_RATE_IDLE = 1.6; // settling back to rest is slower, so a session end reads as calm
const PARAMS = Object.keys(STATES.idle);
const TICKS = 60; // the reference animation steps per frame at 60 fps; we step per second
const TRAIL = 0.35; // share of the last frame erased each frame: lower = longer trails
const HUE_CYAN = 195, HUE_VIOLET = 275;

function makeRings() {
  return Array.from({ length: 7 }, (_, i) => ({
    r: 0.18 + i * 0.045 + Math.random() * 0.04,
    tiltX: 0.25 + Math.random() * 0.45,
    rz: Math.random() * Math.PI,
    spin: (Math.random() - 0.5) * 0.004,
    hue: Math.random() < 0.5 ? HUE_CYAN : HUE_VIOLET,
  }));
}

function makeParticles(n, rings) {
  return Array.from({ length: n }, () => {
    const ring = rings[(Math.random() * rings.length) | 0];
    const off = (Math.random() + Math.random() + Math.random() - 1.5) * 0.018;
    return {
      ring, off,
      a: Math.random() * Math.PI * 2,
      s: 0.002 + Math.random() * 0.006,
      size: Math.random() * 1.3 + 0.4,
      color: `hsl(${Math.round(ring.hue + off * 300)},100%,70%)`,
    };
  });
}

function makeCore(n) {
  return Array.from({ length: n }, () => {
    const u = Math.random() * 2 - 1, t = Math.random() * Math.PI * 2, q = Math.sqrt(1 - u * u);
    return { x: q * Math.cos(t), y: u, z: q * Math.sin(t), r: 0.08 + Math.random() * 0.1 };
  });
}

// The core's hue follows depth (200 + z * 60); 21 buckets avoid a colour string per point.
const CORE_COLORS = Array.from({ length: 21 }, (_, i) => `hsl(${200 + (i / 10 - 1) * 60},100%,72%)`);

/** Mount the orb on `canvas`. Returns { setState(name), setLevel(0..1) }. */
export function createSphere(canvas) {
  const ctx = canvas.getContext('2d');
  const motionQuery = matchMedia('(prefers-reduced-motion: reduce)');
  let reduced = motionQuery.matches;

  // ponytail: particle count fixed by screen size at mount; tune here if a phone stutters.
  const small = Math.min(innerWidth, innerHeight) < 600;
  const rings = makeRings();
  const parts = makeParticles(small ? 2500 : 7000, rings);
  const core = makeCore(small ? 600 : 1500);

  const cur = { ...STATES.idle };
  let target = STATES.idle;
  let stateName = 'idle';
  let level = 0;
  let levelSmooth = 0;
  let T = 0; // reference ticks elapsed
  let W = 0, H = 0, dpr = 1;
  let raf = 0;
  let last = performance.now();

  function fit() {
    const r = canvas.getBoundingClientRect();
    dpr = Math.min(devicePixelRatio || 1, 2);
    W = r.width; H = r.height;
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    // A hidden canvas (display:none collapses it to 0x0) gets no frames at all.
    if (!W || !H) return stop();
    start();
    if (reduced) draw();
  }

  function step(dt) {
    const k = Math.min(1, dt * (stateName === 'idle' ? EASE_RATE_IDLE : EASE_RATE));
    for (const p of PARAMS) cur[p] += (target[p] - cur[p]) * k;
    levelSmooth += (level - levelSmooth) * Math.min(1, dt * (level > levelSmooth ? 18 : 6));

    const ticks = dt * TICKS * (reduced ? 0.15 : 1);
    T += ticks;
    for (const ring of rings) ring.rz += ring.spin * cur.spin * ticks;
    const orbit = cur.orbit * ticks;
    for (const p of parts) p.a += p.s * orbit;
  }

  function project(x, y, z, ring) {
    const c1 = Math.cos(ring.tiltX), s1 = Math.sin(ring.tiltX);
    let y2 = y * c1 - z * s1;
    const z2 = y * s1 + z * c1;
    const c2 = Math.cos(ring.rz), s2 = Math.sin(ring.rz);
    const x3 = x * c2 - y2 * s2;
    y2 = x * s2 + y2 * c2;
    return [x3, y2, z2];
  }

  function drawPlatform(cx, S) {
    for (let i = 0; i < 7; i++) {
      const pulse = i === 0 ? 0 : ((T * 0.004 + i / 6) % 1);
      const rx = S * (0.11 + pulse * 0.45), ry = S * (0.02 + pulse * 0.07);
      const n = Math.floor(rx * 2.2);
      ctx.globalAlpha = (i === 0 ? 0.9 : (1 - pulse) * 0.7) * cur.bright;
      ctx.fillStyle = `hsl(${195 + i * 12},100%,${i === 0 ? 80 : 65}%)`;
      for (let k = 0; k < n; k++) {
        const a = (k / n) * Math.PI * 2 + T * 0.003 * (i % 2 ? 1 : -1);
        const j = Math.abs((Math.sin(k * 12.9898 + i) * 43758.5453) % 1) * 3;
        ctx.fillRect(cx + Math.cos(a) * (rx + j), H * 0.8 + Math.sin(a) * (ry + j * 0.3), 1.6, 1.6);
      }
    }
  }

  function drawRings(cx, cy, S) {
    for (const p of parts) {
      const r = p.ring.r + p.off;
      const [x, y, z] = project(Math.cos(p.a) * r, p.off * 0.5, Math.sin(p.a) * r, p.ring);
      ctx.globalAlpha = Math.max(0.1, Math.min(1, 0.35 + (z + 0.4) * 0.9)) * cur.bright;
      ctx.fillStyle = p.color;
      ctx.fillRect(cx + x * S, cy + y * S, p.size, p.size);
    }
  }

  function drawCore(cx, cy, S, drive) {
    const rot = T * 0.006;
    const c = Math.cos(rot), s = Math.sin(rot);
    const swell = 1 + Math.sin(T * 0.03) * 0.05 + drive * 0.25;
    for (const q of core) {
      const x = q.x * c - q.z * s, z = q.x * s + q.z * c;
      const k = q.r * swell * S;
      ctx.globalAlpha = (0.25 + (z + 1) * 0.3) * cur.bright;
      ctx.fillStyle = CORE_COLORS[Math.round((z + 1) * 10)];
      ctx.fillRect(cx + x * k, cy + q.y * k, 1.4, 1.4);
    }
    const R = S * 0.12 * (1 + drive * 0.3);
    const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, R);
    g.addColorStop(0, `hsla(200,100%,75%,${0.35 + drive * 0.3})`);
    g.addColorStop(1, 'hsla(260,100%,50%,0)');
    ctx.globalAlpha = 1;
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.fill();
  }

  function drawWave(cx, S, drive) {
    const step = S * 0.0067, amp0 = S * 0.024, base = S * 0.0022;
    const gain = cur.wave + drive * 1.4;
    ctx.globalAlpha = 0.8;
    for (let i = -60; i <= 60; i++) {
      if (Math.abs(i) < 6) continue;
      const env = Math.exp(-((Math.abs(i) - 25) ** 2) / 200);
      const amp = (Math.sin(i * 0.4 + T * 0.15) * 0.5 + 0.5) * env * amp0 * gain + base;
      ctx.fillStyle = `hsl(${200 + Math.abs(i)},100%,65%)`;
      ctx.fillRect(cx + i * step, H * 0.905 - amp / 2, Math.max(1, step / 3), amp);
    }
  }

  function draw() {
    if (!W) return;
    // Fade the last frame toward transparent, not toward a colour, so the page glow shows through.
    ctx.globalCompositeOperation = 'destination-out';
    ctx.globalAlpha = 1;
    ctx.fillStyle = `rgba(0,0,0,${reduced ? 1 : TRAIL})`;
    ctx.fillRect(0, 0, W, H);
    ctx.globalCompositeOperation = 'lighter';

    const cx = W / 2, cy = H * 0.47, S = Math.min(W * 1.1, H * 1.5) * 0.8;
    // The mic level drives the core while listening; the voice level while speaking.
    const drive = levelSmooth * (cur.listen + cur.talk);
    drawPlatform(cx, S);
    drawRings(cx, cy, S);
    drawCore(cx, cy, S, drive);
    drawWave(cx, S, drive);
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
  start();

  return {
    setState(name) {
      if (!STATES[name]) return;
      stateName = name;
      target = STATES[name];
      if (name !== 'speaking' && name !== 'listening') level = 0;
    },
    setLevel(x) { level = Math.max(0, Math.min(1, Number(x) || 0)); },
  };
}
