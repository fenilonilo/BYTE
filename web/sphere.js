// The agent orb: '0' and '1' glyphs on a rotating Fibonacci sphere, drawn with Canvas 2D.

// Every parameter eases toward the target state, including `listen` / `talk` (how much the mic
// swell and the speaking rings apply) and `breath` (breathing rate), so no state change snaps.
const STATES = {
  idle:      { spin: 0.14, radius: 1.0,  flip: 0.04, jitter: 0.0,  pulse: 0.012, bright: 0.85, listen: 0, talk: 0, breath: 1.1 },
  listening: { spin: 0.22, radius: 0.86, flip: 0.10, jitter: 0.0,  pulse: 0.045, bright: 1.0,  listen: 1, talk: 0, breath: 4.2 },
  thinking:  { spin: 0.95, radius: 0.97, flip: 2.60, jitter: 0.03, pulse: 0.0,   bright: 0.95, listen: 0, talk: 0, breath: 1.1 },
  speaking:  { spin: 0.30, radius: 1.0,  flip: 0.30, jitter: 0.0,  pulse: 0.0,   bright: 1.0,  listen: 0, talk: 1, breath: 1.1 },
};
const EASE_RATE = 3.5; // per second; higher snaps faster
const EASE_RATE_IDLE = 1.6; // settling back to rest is slower, so a session end reads as calm
const PARAMS = Object.keys(STATES.idle);
const GOLDEN = Math.PI * (3 - Math.sqrt(5));
const SPRITE_PX = 48;
const PERSPECTIVE = 3.2;

function sprite(char, color, font) {
  const c = document.createElement('canvas');
  c.width = c.height = SPRITE_PX;
  const g = c.getContext('2d');
  g.fillStyle = color;
  g.font = `500 ${SPRITE_PX * 0.78}px ${font}`;
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.fillText(char, SPRITE_PX / 2, SPRITE_PX / 2 + SPRITE_PX * 0.04);
  return c;
}

function fibonacci(n) {
  const pts = [];
  for (let i = 0; i < n; i++) {
    // A little jitter breaks the visible spiral stripes of a perfect Fibonacci lattice.
    const y = Math.max(-1, Math.min(1, 1 - (i / (n - 1)) * 2 + (Math.random() - 0.5) * 0.6 / n));
    const r = Math.sqrt(1 - y * y);
    const th = i * GOLDEN + (Math.random() - 0.5) * 0.35;
    pts.push({
      x: Math.cos(th) * r, y, z: Math.sin(th) * r,
      bit: Math.random() < 0.5 ? 0 : 1,
      flash: 0,
      seed: Math.random() * Math.PI * 2,
    });
  }
  return pts;
}

/** Mount the orb on `canvas`. Returns { setState(name), setLevel(0..1) }. */
export function createSphere(canvas) {
  const ctx = canvas.getContext('2d');
  const motionQuery = matchMedia('(prefers-reduced-motion: reduce)');
  let reduced = motionQuery.matches;

  const small = Math.min(innerWidth, innerHeight) < 600;
  const pts = fibonacci(small ? 240 : 720);
  const order = pts.map((_, i) => i);
  const depth = new Float32Array(pts.length);
  const sx = new Float32Array(pts.length);
  const sy = new Float32Array(pts.length);
  const ss = new Float32Array(pts.length);
  const wave = new Float32Array(pts.length);
  const lit = new Float32Array(pts.length);
  const front = new Uint8Array(pts.length);

  const cur = { ...STATES.idle };
  let target = STATES.idle;
  let stateName = 'idle';
  let level = 0;
  let levelSmooth = 0;
  let angle = 0;
  let wavePhase = 0;
  let breathPhase = 0;
  let tiltX = 0, tiltY = 0, aimX = 0, aimY = 0;
  let W = 0, H = 0, dpr = 1;
  let sprites = null;
  let raf = 0;
  let last = performance.now();

  function buildSprites() {
    const css = getComputedStyle(document.documentElement);
    const fg = css.getPropertyValue('--fg').trim() || '#e9e3d7';
    const accent = css.getPropertyValue('--accent').trim() || '#e2a24a';
    const font = css.getPropertyValue('--mono').trim() || 'monospace';
    sprites = {
      fg: [sprite('0', fg, font), sprite('1', fg, font)],
      accent: [sprite('0', accent, font), sprite('1', accent, font)],
    };
  }

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
    if (reduced) draw(performance.now() / 1000, 0);
  }

  function step(t, dt) {
    const k = Math.min(1, dt * (stateName === 'idle' ? EASE_RATE_IDLE : EASE_RATE));
    for (const p of PARAMS) cur[p] += (target[p] - cur[p]) * k;
    levelSmooth += (level - levelSmooth) * Math.min(1, dt * (level > levelSmooth ? 18 : 6));

    const motion = reduced ? 0.15 : 1;
    angle += dt * cur.spin * motion;
    breathPhase += dt * cur.breath; // integrated, so a rate change never jumps the phase
    wavePhase += dt * (5 + levelSmooth * 7) * motion;
    tiltX += ((reduced ? 0 : aimX) - tiltX) * Math.min(1, dt * 2.5);
    tiltY += ((reduced ? 0 : aimY) - tiltY) * Math.min(1, dt * 2.5);

    const flipChance = cur.flip * dt * (reduced ? 0.1 : 1);
    for (const p of pts) {
      if (Math.random() < flipChance) { p.bit ^= 1; p.flash = 1; }
      p.flash *= Math.pow(0.02, dt);
    }
  }

  function draw(t) {
    if (!W || !sprites) return;
    ctx.clearRect(0, 0, W, H);
    const cx = W / 2, cy = H / 2;
    // 0.40 leaves room for the speaking bulge, jitter and perspective without clipping.
    const R = Math.min(W, H) * 0.40;
    const speak = cur.talk * (0.2 + levelSmooth * 0.8);
    // While listening the orb swells with the microphone level.
    const breathe = 1 + Math.sin(breathPhase) * cur.pulse + cur.listen * levelSmooth * 0.14;
    const rotY = angle + tiltY;
    const rotX = 0.32 + tiltX;
    const cY = Math.cos(rotY), sY = Math.sin(rotY), cX = Math.cos(rotX), sX = Math.sin(rotX);
    const glyphBase = Math.max(5, R * 0.062);
    // 6px on a full-size orb; a small orb (gate, phones) keeps more of its rim.
    const minGlyph = small ? Math.max(Math.min(6, glyphBase * 0.8), glyphBase * 0.55) : Math.min(6, glyphBase * 0.8);

    for (let i = 0; i < pts.length; i++) {
      const p = pts[i];
      const x = p.x * cY + p.z * sY;
      const z = -p.x * sY + p.z * cY;
      const y2 = p.y * cX - z * sX;
      const z2 = p.y * sX + z * cX;
      // Rings around the view axis read as a wave radiating from the centre of the orb.
      wave[i] = speak ? speak * Math.pow(Math.max(0, Math.sin(Math.acos(Math.min(1, Math.max(-1, z2))) * 3 - wavePhase)), 6) : 0;
      let d = cur.radius * breathe + wave[i] * 0.08;
      if (cur.jitter) d += Math.sin(t * 9 + p.seed * 7) * cur.jitter;
      const f = PERSPECTIVE / (PERSPECTIVE - z2 * d);
      sx[i] = cx + x * R * d * f;
      sy[i] = cy + y2 * R * d * f;
      depth[i] = (z2 + 1) / 2;
      // Key light from the upper left gives the ball volume.
      lit[i] = 0.35 + 0.65 * Math.max(0, -0.4 * x - 0.5 * y2 + 0.77 * z2);
      front[i] = z2 >= 0 ? 1 : 0;
      ss[i] = glyphBase * (0.45 + depth[i] * 0.85) * f;
    }
    order.sort((a, b) => depth[a] - depth[b]);

    for (const i of order) {
      const p = pts[i];
      const dz = depth[i];
      if (ss[i] < minGlyph) continue; // rim glyphs this small only add mush
      const s = front[i] ? ss[i] : ss[i] * 0.8;
      let alpha = (0.06 + Math.pow(dz, 1.6) * 0.9) * cur.bright * lit[i];
      if (!front[i]) alpha = Math.min(alpha * 0.35, 0.14);
      ctx.globalAlpha = alpha;
      ctx.drawImage(sprites.fg[p.bit], sx[i] - s / 2, sy[i] - s / 2, s, s);
      const hot = Math.max(p.flash, wave[i] * 1.4);
      if (hot > 0.05) {
        ctx.globalAlpha = Math.min(1, hot) * alpha;
        ctx.drawImage(sprites.accent[p.bit], sx[i] - s / 2, sy[i] - s / 2, s, s);
      }
    }
    ctx.globalAlpha = 1;
  }

  function frame(now) {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    step(now / 1000, dt);
    draw(now / 1000);
    raf = requestAnimationFrame(frame);
  }

  function start() {
    if (raf || document.hidden || !W || !H) return;
    last = performance.now();
    raf = requestAnimationFrame(frame);
  }
  function stop() { cancelAnimationFrame(raf); raf = 0; }

  addEventListener('pointermove', (e) => {
    aimY = ((e.clientX / innerWidth) - 0.5) * 0.5;
    aimX = ((e.clientY / innerHeight) - 0.5) * 0.35;
  }, { passive: true });
  document.addEventListener('visibilitychange', () => (document.hidden ? stop() : start()));
  motionQuery.addEventListener('change', (e) => { reduced = e.matches; });
  new ResizeObserver(fit).observe(canvas);

  buildSprites();
  document.fonts?.ready.then(buildSprites);
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
