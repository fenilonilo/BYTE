# Marcelo UI v2 — Design Spec

**Data:** 2026-05-27  
**Status:** Aprovado  
**Branch alvo:** `feat/ui-v2-svelte`

---

## Contexto

Rewrite completo da interface do assistente Marcelo. Substituir `Animacao_Marcelo/` (vanilla HTML/JS) por aplicação Svelte 5 + Vite moderna. Backend FastAPI existente não muda — apenas o frontend é reescrito.

### Objetivos

1. Interface futurista e moderna com overlays glass sobre canvas de partículas
2. Partículas Three.js + webcam MediaPipe continuam dominando o centro da tela
3. Sistema de gestos expandido: 6 gestos bimanais novos + 3 gestos unimanais novos
4. Painel de projetos minimalista lendo `D:\Projetos\Projetos_Marcelo`
5. Chat overlay glass com streaming, STT/TTS integrados
6. Stack tipada (TypeScript), modular, escalável

---

## Stack

| Camada | Tecnologia | Justificativa |
|--------|-----------|---------------|
| Framework UI | **Svelte 5** (Runes) | Compila pra vanilla JS, zero virtual DOM, zero overhead em eventos de alta frequência (gestos 60fps) |
| Build | **Vite** | HMR instantâneo, ES modules nativos, bundle otimizado |
| Estilos | **UnoCSS** | Utility-first sem runtime, purgado automaticamente |
| 3D / Partículas | **Three.js** (módulo puro) | Mantido igual — roda em loop `requestAnimationFrame` próprio, Svelte não interfere |
| Gestos | **MediaPipe Hands** (módulo puro) | Mantido — callback direto ao gesture engine |
| Áudio | **Web Audio API** (módulo puro) | Mantido — `AudioContext` compartilhado |
| Comunicação | **WebSocket** nativo | Streaming de resposta do backend |
| Ícones | **lucide-svelte** | SVG inline, sem font, tree-shakeable |
| Tipagem | **TypeScript strict** | Todos os módulos `.ts` / `.svelte` com `lang="ts"` |

---

## Estrutura de Arquivos

```
Animacao_Marcelo/          ← mantido intacto como backup/referência
marcelo-ui/                ← novo diretório, rewrite completo
├── index.html
├── vite.config.ts
├── tsconfig.json
├── package.json
├── uno.config.ts
└── src/
    ├── main.ts                    ← entry point, monta App.svelte
    ├── App.svelte                 ← shell raiz: canvas + todos os overlays
    ├── lib/
    │   ├── particle-engine.ts     ← Three.js scene (reescrito em TS, lógica igual)
    │   ├── gesture-engine.ts      ← MediaPipe + máquina de estados bimanual (novo)
    │   ├── audio-analyzer.ts      ← Web Audio, TS port do original
    │   └── ws-client.ts           ← WebSocket client tipado
    ├── stores/
    │   ├── gesture.svelte.ts      ← $state: GestureState (duas trilhas independentes)
    │   ├── chat.svelte.ts         ← $state: mensagens, streaming, preview
    │   └── projects.svelte.ts     ← $state: lista projetos + polling
    └── components/
        ├── ParticleCanvas.svelte     ← monta canvas, chama particle-engine
        ├── ChatOverlay.svelte        ← painel chat glass, canto inferior esquerdo
        ├── ProjectsOverlay.svelte    ← painel projetos minimalista, canto inferior direito
        ├── GestureHUD.svelte         ← badge gesto ativo, topo centro
        ├── WebcamView.svelte         ← feed webcam, canto superior direito
        └── StatusBadge.svelte        ← estado idle/listening/thinking/speaking
```

---

## Layout

Todos os elementos usam `position: fixed`. Z-index definido por camada:

| Camada | z-index | Elemento |
|--------|---------|----------|
| Canvas partículas | 0 | `ParticleCanvas` — `inset: 0` |
| Webcam | 10 | `WebcamView` — `top: 16px; right: 16px; width: 120px` |
| Overlays | 20 | `ChatOverlay`, `ProjectsOverlay` |
| HUD | 30 | `GestureHUD`, `StatusBadge` |

### Posicionamento dos Overlays

```
┌─────────────────────────────────────────────┐
│  [GestureHUD / StatusBadge]    [WebcamView] │
│              centro-topo          dir-topo  │
│                                             │
│                                             │
│          [ParticleCanvas — full]            │
│                                             │
│                                             │
│  [ChatOverlay]          [ProjectsOverlay]   │
│   esq-baixo               dir-baixo        │
└─────────────────────────────────────────────┘
```

### Glass System

Todos os overlays seguem o mesmo padrão visual:

```css
background: rgba(6, 10, 15, 0.75);
backdrop-filter: blur(12px);
border: 1px solid rgba(255, 255, 255, 0.08);
border-radius: 12px;
```

---

## Paleta de Cores

```
fundo:        #060a0f
azul:         rgba(99, 179, 255, *)      → partículas, chat assistente, pinch
violeta:      rgba(150, 80, 255, *)      → usuário, repel, effects
verde:        rgba(150, 255, 180, *)     → projetos, status online
âmbar:        rgba(255, 200, 80, *)      → thinking, explosão, alerta
vermelho:     rgba(255, 100, 80, *)      → fist burst, erro
gelo:         rgba(150, 220, 255, *)     → freeze state
```

### Tipografia

- UI geral: `Inter` (400, 500)
- Labels, status, badges: `JetBrains Mono` (400) — letter-spacing: 1-2px, uppercase

---

## Gesture Engine

### Modelo de Dados

```typescript
type HandGesture = 'none' | 'open' | 'pinch' | 'fist' | 'point' | 'idle'

interface HandState {
  gesture: HandGesture
  worldPos: Vector3
  velocity: Vector3
  age: number           // ms no gesto atual
}

interface BimanualPattern {
  active: boolean
  pattern: BimanualGesture | null
  phase: string         // depende do padrão
  progress: number      // 0..1
}

interface GestureState {
  left: HandState
  right: HandState
  bimanual: BimanualPattern
}
```

### Gestos Bimanais

Detectados verificando combinação dos estados das duas mãos simultaneamente. Processados em paralelo — mão "livre" continua emitindo eventos unimanais durante padrão bimanual.

| Gesto | Condição de entrada | Fase | Trigger de disparo |
|-------|--------------------|----|-------------------|
| `prayer-explosion` | ambas `open`, distância normalizada entre palmas < 0.08 (coords MediaPipe 0..1) | `contact` → `release` → `blast` | velocidade de afastamento > 0.8 unidades/s |
| `implosion` | ambas `open`, longe → aproximando, vel < 0.3 unidades/s | `approach` → `vortex` | distância normalizada < 0.15 |
| `orbit` | uma `pinch` estável + outra qualquer circulando ao redor (ângulo varia > 180°) | `anchor` → `orbit` | mão âncora pinch por > 500ms |
| `freeze` | ambas `fist` com delta de tempo < 300ms | `instant` | detecção imediata |
| `dual-pinch` | ambas `pinch` simultaneamente | `sustained` | enquanto mantiver |
| `portal` | fingertips de ambas as mãos formam círculo (12 pontos em elipse) | `forming` → `sustained` | confiança > 0.75 |

### Gestos Unimanais

| Gesto | Condição | Efeito partículas |
|-------|----------|-------------------|
| `pinch` | polegar + indicador < 6cm | centro gravitacional — atrai partículas (existente) |
| `fist` | todos dedos dobrados | burst local raio ~20% tela (existente) |
| `open` | todos dedos estendidos | repulsão ao redor da mão (existente) |
| `point` | indicador estendido, outros dobrados | feixe direcional — partículas seguem ponta |
| `swipe` | mão `open` com velocidade horizontal > 1.5 m/s | onda de pressão lateral |
| `breathe` | mão `open` imóvel por > 1000ms (vel < 0.05 m/s) | modo respiração — expansão rítmica |

---

## Efeitos de Partículas — Novos Métodos

Adicionados ao `particle-engine.ts`:

```typescript
// Bimanais
shockwave(origin: Vector3, radius: number, force: number): void
// onda de choque radial — prayer-explosion — bloom flash branco 400ms

vortex(target: Vector3, strength: number): void
// partículas colapsam em espiral — implosion

orbitAnchor(anchor: Vector3, radius: number): void
// partículas orbitam ponto fixo — orbit gesture

crystallize(durationMs: number): void
// partículas param, cor → gelo, desfaz após duração — freeze

splitField(pointA: Vector3, pointB: Vector3): void
// dois centros gravitacionais — dual-pinch

portalRing(center: Vector3, ringRadius: number): void
// partículas em órbita ao redor de anel — portal

// Unimanais novos
directionalBeam(tip: Vector3, direction: Vector3): void
// feixe direcional — point gesture

lateralWave(origin: Vector3, directionSign: number, speed: number): void
// onda lateral — swipe

breathePulse(center: Vector3): void
// pulsação rítmica — breathe gesture
```

Métodos existentes mantidos sem mudança:
- `applyHandForce(worldPos, gesture, velocity)`
- `setState(state)` — idle/listening/thinking/speaking
- `setAmplitude(value)`

---

## Chat Overlay

### Estrutura

```svelte
<!-- ChatOverlay.svelte — Svelte 5 Runes syntax -->
<script lang="ts">
  import { chat } from '../stores/chat.svelte'
  let collapsed = $state(false)
</script>

<div class="overlay chat-overlay" class:collapsed={collapsed}>
  <header onclick={() => collapsed = !collapsed}>
    <span>💬 chat</span>
    <StatusBadge />
  </header>

  {#if !collapsed}
    <div class="transcript" bind:this={scrollEl}>
      {#each chat.messages as msg}
        <ChatMessage {msg} />
      {/each}
      {#if chat.interim}
        <InterimMessage text={chat.interim} />
      {/if}
    </div>

    {#if chat.preview}
      <PreviewCard
        text={chat.preview}
        onapprove={approvePreview}
        oncancel={cancelPreview}
      />
    {/if}

    <InputDock />
  {/if}
</div>
```

### Store `chat.svelte.ts`

```typescript
export const chat = $state({
  messages: Message[],
  interim: string | null,      // STT em tempo real
  preview: string | null,      // Claude Code preview
  streaming: boolean,
  connected: boolean,
})
```

### Comportamento

- Auto-scroll para última mensagem durante streaming
- Mensagem `assistant` aparece palavra por palavra (chunk events)
- `interim` aparece em itálico semi-transparente, substitui por mensagem real ao confirmar
- Preview card bloqueia input até approve/cancel
- Colapsável: clique no header → minimiza pra badge de ícone (40×40px)

---

## Projects Overlay

### Backend — Novo Endpoint

```python
# app/api/router.py — adicionar
GET /api/v1/projects
→ [{ name: str, mtime: float, path: str }]  # ordenado por mtime desc
```

Implementação: `os.scandir(settings.workspace_path)`, retorna apenas diretórios, `mtime` do item.

### Frontend

```typescript
// stores/projects.svelte.ts
export const projects = $state({
  items: ProjectItem[],
  loading: boolean,
})

// polling a cada 30s
```

### Componente

```
[● byte-agent          hoje    ]
[● landing-usados      2d      ]
[○ dashboard-v2        5d      ]
[○ api-gateway         12d     ]
[○ crm-interno         3sem    ]
[  + 6 projetos...             ]
```

- Dot: verde (#96ff64, glow) = modificado hoje; âmbar = < 7d; cinza = antigo
- Clique no item → chama `open_dev_environment(path)` → abre terminal no diretório
- "+" expandir mostra todos
- Colapsável igual ao chat overlay

---

## GestureHUD

Badge no topo centro. Mostra gesto ativo com ícone + nome. Desaparece 1.5s após gesto terminar (fade out).

```
Estado idle:     [sem badge]
Gesto ativo:     [🙏 EXPLOSÃO]   [❄️ CONGELAR]   [☝️ APONTAR]
Bimanual:        badge âmbar com ícone duplo
```

Durante `crystallize`: toda a interface recebe overlay sutil de gelo (filter: hue-rotate + saturate) por 3s.

---

## WebSocket — Tipos (sem mudança de protocolo)

```typescript
// Mensagens enviadas
{ type: 'message', message: string, session_id: string }
{ type: 'approve_send' }
{ type: 'cancel_send' }

// Mensagens recebidas
{ type: 'chunk', text: string }
{ type: 'preview', text: string }
{ type: 'done', text: string }
```

---

## API Backend — Mudanças Necessárias

Apenas uma adição. Todo o resto do backend FastAPI é mantido sem alteração.

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/api/v1/projects` | GET | **NOVO** — lista projetos da workspace |

---

## Animações e Transições CSS

```css
/* Overlays entram/saem */
.overlay { transition: opacity 200ms ease, transform 200ms ease; }

/* Collapse */
.overlay.collapsed { transform: scale(0.95); opacity: 0.8; }

/* Mensagens novas no chat */
.message { animation: slideIn 150ms ease; }

/* GestureHUD badge */
.gesture-badge { animation: fadeIn 100ms ease; }
.gesture-badge.exiting { animation: fadeOut 300ms ease forwards; }

/* Freeze overlay */
.freeze-overlay { animation: iceIn 400ms ease; filter: hue-rotate(180deg) saturate(0.3); }
```

---

## Requisitos Não-Funcionais

- **60fps** — Three.js loop nunca bloqueado por Svelte. Stores apenas notificam, nunca bloqueiam `requestAnimationFrame`
- **Latência gesture → visual < 16ms** — gesture engine processa no mesmo frame do MediaPipe callback
- **Bundle < 500KB** (gzipped) excluindo Three.js e MediaPipe (carregados separados)
- **Sem flash branco** no carregamento — fundo `#060a0f` no `index.html` antes do JS iniciar
- **Graceful degradation** sem webcam: desativa gesture engine, mantém chat/TTS/texto

---

## Fora de Escopo (v2)

- Múltiplos usuários / sessões
- Persistência de histórico de chat no frontend (backend já guarda)
- Tema claro
- Mobile / touch

---

## Critérios de Conclusão

- [ ] `marcelo-ui/` roda com `vite dev` e conecta ao backend FastAPI existente
- [ ] Todos os 6 gestos bimanais detectados e com efeito visual
- [ ] Todos os 3 gestos unimanais novos + 3 existentes funcionando
- [ ] Chat overlay: streaming, STT, TTS, preview card
- [ ] Projects overlay: lista correta de `D:\Projetos\Projetos_Marcelo`, dot recência correto
- [ ] Layout glass overlay sobre canvas full-screen
- [ ] `tsc --noEmit` passa sem erros
- [ ] Vite build sem warnings críticos
