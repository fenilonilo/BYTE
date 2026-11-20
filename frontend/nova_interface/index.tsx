import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef } from "react";
import { Home, Cpu, LayoutGrid, Brain, Settings, Activity, Wifi, House, BarChart3, Globe } from "lucide-react";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "IAGO — Núcleo Holográfico de IA" },
      { name: "description", content: "Animação de núcleo holográfico futurista do assistente virtual IAGO." },
      { property: "og:title", content: "IAGO — Núcleo Holográfico de IA" },
      { property: "og:description", content: "Animação de núcleo holográfico futurista do assistente virtual IAGO." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

function useHolo(ref: React.RefObject<HTMLCanvasElement | null>) {
  useEffect(() => {
    const c = ref.current!;
    const ctx = c.getContext("2d")!;
    let w = 0, h = 0, raf = 0;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const resize = () => { w = c.clientWidth; h = c.clientHeight; c.width = w * dpr; c.height = h * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0); };
    resize(); window.addEventListener("resize", resize);

    // orbit rings: each has tilt (rx), rotation (rz), radius
    const rings = Array.from({ length: 7 }, (_, i) => ({
      r: 0.18 + i * 0.045 + Math.random() * 0.04,
      tiltX: 0.25 + Math.random() * 0.45,
      rz: Math.random() * Math.PI,
      spin: (Math.random() - 0.5) * 0.004,
      hue: Math.random() < 0.5 ? 195 : 275,
    }));
    const parts = Array.from({ length: 9000 }, () => {
      const ring = rings[(Math.random() * rings.length) | 0]!;
      return { ring, a: Math.random() * Math.PI * 2, s: 0.002 + Math.random() * 0.006, off: (Math.random() + Math.random() + Math.random() - 1.5) * 0.018, size: Math.random() * 1.3 + 0.4 };
    });
    const sphere = Array.from({ length: 1500 }, () => {
      const u = Math.random() * 2 - 1, t = Math.random() * Math.PI * 2;
      return { x: Math.sqrt(1 - u * u) * Math.cos(t), y: u, z: Math.sqrt(1 - u * u) * Math.sin(t), r: 0.08 + Math.random() * 0.1 };
    });
    const project = (x: number, y: number, z: number, ring: (typeof rings)[0]) => {
      const cy = Math.cos(ring.tiltX), sy = Math.sin(ring.tiltX);
      let y2 = y * cy - z * sy; const z2 = y * sy + z * cy;
      const cz = Math.cos(ring.rz), sz = Math.sin(ring.rz);
      const x3 = x * cz - y2 * sz; y2 = x * sz + y2 * cz;
      return [x3, y2, z2] as [number, number, number];
    };
    let t = 0;
    const draw = () => {
      t += 1;
      ctx.globalCompositeOperation = "source-over";
      ctx.fillStyle = "rgba(4,6,18,0.35)"; ctx.fillRect(0, 0, w, h);
      ctx.globalCompositeOperation = "lighter";
      const cx = w / 2, cy = h * 0.47, S = Math.min(w * 1.1, h * 1.5) * 0.8;
      // base platform (particles only)
      for (let i = 0; i < 7; i++) {
        const pulse = i === 0 ? 0 : ((t * 0.004 + i / 6) % 1);
        const rx = S * (0.11 + pulse * 0.45), ry = S * (0.02 + pulse * 0.07);
        const al = i === 0 ? 0.9 : (1 - pulse) * 0.7;
        const n = Math.floor(rx * 2.2);
        for (let k = 0; k < n; k++) {
          const a = (k / n) * Math.PI * 2 + t * 0.003 * (i % 2 ? 1 : -1);
          const j = Math.abs((Math.sin(k * 12.9898 + i) * 43758.5453) % 1) * 3;
          ctx.fillStyle = `hsla(${195 + i * 12},100%,${i === 0 ? 80 : 65}%,${al})`;
          ctx.fillRect(cx + Math.cos(a) * (rx + j), h * 0.8 + Math.sin(a) * (ry + j * 0.3), 1.6, 1.6);
        }
      }
      // ring lines
      for (const ring of rings) {
        ring.rz += ring.spin;
      }
      // particles
      for (const p of parts) {
        p.a += p.s;
        const r = p.ring.r + p.off;
        const [x, y, z] = project(Math.cos(p.a) * r, p.off * 0.5, Math.sin(p.a) * r, p.ring);
        const alpha = 0.35 + (z + 0.4) * 0.9;
        ctx.fillStyle = `hsla(${p.ring.hue + p.off * 300},100%,70%,${Math.max(0.1, Math.min(1, alpha))})`;
        ctx.fillRect(cx + x * S, cy + y * S, p.size, p.size);
      }
      // core sphere
      const rot = t * 0.006;
      for (const s of sphere) {
        const x = s.x * Math.cos(rot) - s.z * Math.sin(rot), z = s.x * Math.sin(rot) + s.z * Math.cos(rot);
        const k = s.r * (1 + Math.sin(t * 0.03) * 0.05);
        ctx.fillStyle = `hsla(${200 + z * 60},100%,72%,${0.25 + (z + 1) * 0.3})`;
        ctx.fillRect(cx + x * k * S, cy + s.y * k * S, 1.4, 1.4);
      }
      const cg = ctx.createRadialGradient(cx, cy, 0, cx, cy, S * 0.12);
      cg.addColorStop(0, "hsla(200,100%,75%,0.35)"); cg.addColorStop(1, "hsla(260,100%,50%,0)");
      ctx.fillStyle = cg; ctx.beginPath(); ctx.arc(cx, cy, S * 0.12, 0, Math.PI * 2); ctx.fill();
      // waveform
      for (let i = -60; i <= 60; i++) {
        if (Math.abs(i) < 6) continue;
        const amp = (Math.sin(i * 0.4 + t * 0.15) * 0.5 + 0.5) * Math.exp(-((Math.abs(i) - 25) ** 2) / 200) * 22 + 2;
        ctx.fillStyle = `hsla(${200 + Math.abs(i)},100%,65%,0.8)`;
        ctx.fillRect(cx + i * 6, h * 0.905 - amp / 2, 2, amp);
      }
      raf = requestAnimationFrame(draw);
    };
    draw();
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", resize); };
  }, [ref]);
}

function Index() {
  const ref = useRef<HTMLCanvasElement>(null);
  useHolo(ref);
  const nav = [[Home, "Início"], [Cpu, "Dispositivos"], [LayoutGrid, "Aplicativos"], [Brain, "Memória"], [Settings, "Configurações"]] as const;
  const acts = [[Wifi, "Spotify", "Tocando agora"], [House, "Casa Inteligente", "Tudo funcionando"], [BarChart3, "Análise de Dados", "Processando..."], [Globe, "Navegação", "Pronta para ajudar"]] as const;
  return (
    <main className="holo">
      <canvas ref={ref} />
      <div className="holo-panel holo-brand"><h1>IAGO</h1><p>ASSISTENTE VIRTUAL</p></div>
      <div className="holo-panel holo-online"><span className="holo-dot" />ONLINE</div>
      <nav className="holo-panel holo-nav">
        {nav.map(([I, l], i) => <a key={l} className={i === 0 ? "active" : ""}><I size={20} />{l}</a>)}
      </nav>
      <aside className="holo-panel holo-act">
        <h3><Activity size={18} />Atividades</h3>
        <ul>
          {acts.map(([I, t, s], i) => (
            <li key={t}><I size={22} /><div>{t}<small>{s}</small></div>
              {i === 0 && <span className="holo-bars">{Array.from({ length: 6 }, (_, k) => <i key={k} style={{ animationDelay: `${k * 0.12}s` }} />)}</span>}
            </li>
          ))}
        </ul>
      </aside>
      <div className="holo-foot">∿ Sempre ao seu lado</div>
      <div className="holo-mic"><div className="holo-mic-orb" />Escutando...</div>
      <div className="holo-stripes">{Array.from({ length: 8 }, (_, k) => <i key={k} style={{ animationDelay: `${k * 0.1}s` }} />)}</div>
    </main>
  );
}
