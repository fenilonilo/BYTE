# Gesture CV Service — Phase 6: Config UI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. **Prerequisite: Phase 5 complete.**

**Goal:** A no-code UI to create gestures: a list screen plus a 3-step wizard — **record pose** (server-side capture, live preview), **compose** (pose + hands + motion, live-tested via `/current`), **bind** (effect + action + params, saved through the Phase 5 API).

**Architecture:** A `config-api.ts` client talks to the backend CRUD API (`/api/v1/gestures`) and the gesture-service capture/test endpoints. A `config.svelte.ts` store holds the definition list and wizard draft. Components: `GestureList`, `WizardRecord`, `WizardCompose`, `WizardBind`, and a `ConfigOverlay` container toggled from `App.svelte`. Because the browser has no landmarks (CV is server-side), pose recording is driven by a **server-side record session** on the gesture-service.

**Tech Stack:** Svelte 5 (runes), TypeScript.

**Catalogs (stable, hardcoded in the UI):** effects = the Phase 3 `FORCE_MODE` keys; actions = `none`, `swap_model`, `open_project`.

---

## File Structure

| File | Responsibility | Verify |
|------|----------------|--------|
| `marcelo-ui/src/lib/config-api.ts` | REST + service client, types | manual |
| `marcelo-ui/src/stores/config.svelte.ts` | definition list + wizard draft | manual |
| `marcelo-ui/src/components/config/ConfigOverlay.svelte` | container + step switch | manual |
| `marcelo-ui/src/components/config/GestureList.svelte` | list, edit/test/delete, + New | manual |
| `marcelo-ui/src/components/config/WizardRecord.svelte` | step 1: record pose | manual |
| `marcelo-ui/src/components/config/WizardCompose.svelte` | step 2: compose + live test | manual |
| `marcelo-ui/src/components/config/WizardBind.svelte` | step 3: bind + save | manual |
| `marcelo-ui/src/components/App.svelte` (modify) | gear toggle + mount overlay | manual |
| `gesture_service/main.py` (modify) | record-session state + capture hook | manual |
| `gesture_service/config_api.py` (modify) | `/poses/{label}/record` + status | manual |

---

### Task 1: Server-side pose record session

**Files:**
- Modify: `gesture_service/main.py`
- Modify: `gesture_service/config_api.py`

The browser cannot compute feature vectors (no landmarks client-side). The service records them from its own stream. This supersedes Phase 5's vector-upload `/poses/{label}` for UI use (that endpoint stays valid for programmatic/test use).

- [ ] **Step 1: Add a record-session to main.py**

In `gesture_service/main.py`, add:

```python
from gesture_service.features import feature_vector

_record = {"active": False, "label": "", "remaining": 0}


def _record_start(label: str, frames: int) -> None:
    _record["label"] = label
    _record["remaining"] = frames
    _record["active"] = True


def _record_status() -> dict[str, object]:
    return {"active": _record["active"], "remaining": _record["remaining"]}
```

In the capture callback `_on_frame`, after building `frames`, feed the recorder from the first detected hand. The callback receives `HandFrame`s, but feature recording needs the raw `HandLandmarks`. **Change `capture.py` to also pass the raw hands** (see Step 2), then here:

```python
def _on_frame(frames, raw_hands, annotated):  # signature updated in Step 2
    set_latest_frame(annotated)
    if _record["active"] and raw_hands:
        vec = feature_vector(raw_hands[0])
        _pose_store.add_sample(str(_record["label"]), vec)
        _record["remaining"] = int(_record["remaining"]) - 1
        if int(_record["remaining"]) <= 0:
            _record["active"] = False
            _pose_store.persist()
            _rebuild_knn()
    import time
    event = _matcher.update(frames, now=time.monotonic())
    if event is not None:
        _latest_gesture["gesture"] = event.gesture
        _latest_gesture["phase"] = event.phase
        _publisher.publish(event)
```

- [ ] **Step 2: Pass raw landmarks through the capture callback**

In `gesture_service/capture.py`, change `FrameCallback` and the call site to also yield the raw `HandLandmarks` list:

```python
FrameCallback = Callable[[list[HandFrame], list[HandLandmarks], object], None]
```

Collect `raw_hands: list[HandLandmarks]` alongside `frames` in the loop and call `on_frame(frames, raw_hands, frame)`.

- [ ] **Step 3: Add record endpoints to config_api.py**

Extend `build_router` signature to accept `record_start` and `record_status` callables, and add:

```python
    @router.post("/poses/{label}/record")
    def record(label: str, frames: int = 15) -> dict[str, bool]:
        record_start(label, frames)
        return {"ok": True}

    @router.get("/poses/record/status")
    def record_status() -> dict[str, object]:
        return record_status_fn()
```

Wire the new callables where `build_router(...)` is called in `main.py`.

- [ ] **Step 4: Manual verify**

Start the service. Run:
`.venv\Scripts\python -c "import httpx; print(httpx.post('http://127.0.0.1:8001/poses/wave_hand/record?frames=15').json())"`
Hold a pose; poll `http://127.0.0.1:8001/poses/record/status`.
Expected: `remaining` counts down to 0; `data/gesture_poses.json` gains samples; KNN rebuilds.

- [ ] **Step 5: Commit**

```bash
git add gesture_service/main.py gesture_service/config_api.py gesture_service/capture.py
git commit -m "feat(gesture-service): server-side pose record session for the config UI"
```

---

### Task 2: Frontend config API client

**Files:**
- Create: `marcelo-ui/src/lib/config-api.ts`

- [ ] **Step 1: Write the client**

```typescript
export interface PoseSpec { shape: string; hands: number }
export interface MotionSpec { type: string; params: Record<string, unknown> }
export interface BindingSpec { effect: string; action: string | null; action_params: Record<string, unknown> }
export interface GestureDefinition {
  id: string
  name: string
  pose: PoseSpec
  motion: MotionSpec
  binding: BindingSpec
}

const BACKEND = '/api/v1'
const SERVICE = 'http://localhost:8001'

export async function listGestures(): Promise<GestureDefinition[]> {
  const r = await fetch(`${BACKEND}/gestures`)
  return r.ok ? (await r.json() as GestureDefinition[]) : []
}

export async function saveGesture(def: GestureDefinition): Promise<void> {
  await fetch(`${BACKEND}/gestures/${encodeURIComponent(def.id)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(def),
  })
}

export async function deleteGesture(id: string): Promise<void> {
  await fetch(`${BACKEND}/gestures/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

export async function startRecording(label: string, frames = 15): Promise<void> {
  await fetch(`${SERVICE}/poses/${encodeURIComponent(label)}/record?frames=${frames}`, { method: 'POST' })
}

export async function recordStatus(): Promise<{ active: boolean; remaining: number }> {
  const r = await fetch(`${SERVICE}/poses/record/status`)
  return r.ok ? await r.json() : { active: false, remaining: 0 }
}

export async function currentGesture(): Promise<{ gesture: string; phase: string }> {
  const r = await fetch(`${SERVICE}/current`)
  return r.ok ? await r.json() : { gesture: 'none', phase: 'idle' }
}

export const EFFECTS = [
  'none', 'attract', 'repel', 'freeze', 'shockwave',
  'vortex', 'orbit', 'portal', 'beam', 'wave', 'breathe',
] as const

export const ACTIONS = ['none', 'swap_model', 'open_project'] as const
export const BUILTIN_POSES = ['fist', 'open', 'pinch', 'point'] as const
export const MOTIONS = ['none', 'hold', 'swipe', 'circle', 'approach'] as const
```

- [ ] **Step 2: Verify types**

Run: `cd marcelo-ui && npx svelte-check --tsconfig ./tsconfig.json`
Expected: 0 errors (file compiles; unused until imported).

- [ ] **Step 3: Commit**

```bash
git add marcelo-ui/src/lib/config-api.ts
git commit -m "feat(ui): add gesture config API client"
```

---

### Task 3: Config store (list + wizard draft)

**Files:**
- Create: `marcelo-ui/src/stores/config.svelte.ts`

- [ ] **Step 1: Write the store**

```typescript
import type { GestureDefinition } from '../lib/config-api'
import { listGestures } from '../lib/config-api'

type Screen = 'list' | 'record' | 'compose' | 'bind'

function emptyDraft(): GestureDefinition {
  return {
    id: '',
    name: '',
    pose: { shape: 'fist', hands: 1 },
    motion: { type: 'hold', params: {} },
    binding: { effect: 'none', action: null, action_params: {} },
  }
}

export const configState = $state({
  open: false,
  screen: 'list' as Screen,
  items: [] as GestureDefinition[],
  draft: emptyDraft(),
})

export async function refreshList(): Promise<void> {
  configState.items = await listGestures()
}

export function openConfig(): void {
  configState.open = true
  configState.screen = 'list'
  void refreshList()
}

export function closeConfig(): void {
  configState.open = false
}

export function newGesture(): void {
  configState.draft = emptyDraft()
  configState.screen = 'record'
}

export function editGesture(def: GestureDefinition): void {
  configState.draft = structuredClone($state.snapshot(def)) as GestureDefinition
  configState.screen = 'compose'
}

export function goto(screen: Screen): void {
  configState.screen = screen
}
```

- [ ] **Step 2: Commit**

```bash
git add marcelo-ui/src/stores/config.svelte.ts
git commit -m "feat(ui): add gesture config store"
```

---

### Task 4: Gesture list screen

**Files:**
- Create: `marcelo-ui/src/components/config/GestureList.svelte`

- [ ] **Step 1: Write the component**

```svelte
<script lang="ts">
  import { configState, newGesture, editGesture } from '../../stores/config.svelte'
  import { deleteGesture } from '../../lib/config-api'
  import { refreshList } from '../../stores/config.svelte'

  async function remove(id: string): Promise<void> {
    await deleteGesture(id)
    await refreshList()
  }
</script>

<div style="padding:20px;color:#cdd9e5;">
  <h2 style="margin-bottom:14px;letter-spacing:2px;">GESTOS</h2>

  {#if configState.items.length === 0}
    <p style="opacity:0.6;">Nenhum gesto configurado.</p>
  {/if}

  {#each configState.items as def (def.id)}
    <div style="display:flex;justify-content:space-between;align-items:center;
                padding:10px 12px;border:1px solid #2a3a4a;border-radius:8px;margin-bottom:8px;">
      <div>
        <strong>{def.name}</strong>
        <span style="opacity:0.6;font-size:12px;">
          → {def.binding.effect}{def.binding.action ? ` + ${def.binding.action}` : ''}
        </span>
      </div>
      <div style="display:flex;gap:8px;">
        <button onclick={() => editGesture(def)}>editar</button>
        <button onclick={() => remove(def.id)}>x</button>
      </div>
    </div>
  {/each}

  <button onclick={newGesture}
          style="margin-top:12px;padding:8px 16px;border-radius:8px;
                 background:#1f6feb;color:#fff;border:none;cursor:pointer;">
    + Novo gesto
  </button>
</div>
```

- [ ] **Step 2: Commit**

```bash
git add marcelo-ui/src/components/config/GestureList.svelte
git commit -m "feat(ui): add gesture list screen"
```

---

### Task 5: Wizard step 1 — record pose

**Files:**
- Create: `marcelo-ui/src/components/config/WizardRecord.svelte`

- [ ] **Step 1: Write the component**

```svelte
<script lang="ts">
  import { configState, goto } from '../../stores/config.svelte'
  import { startRecording, recordStatus } from '../../lib/config-api'

  let recording = $state(false)
  let remaining = $state(0)

  async function record(): Promise<void> {
    const label = configState.draft.pose.shape.trim()
    if (!label) return
    recording = true
    await startRecording(label, 15)
    const poll = setInterval(async () => {
      const s = await recordStatus()
      remaining = s.remaining
      if (!s.active) {
        clearInterval(poll)
        recording = false
      }
    }, 200)
  }
</script>

<div style="padding:20px;color:#cdd9e5;">
  <h3>1 · Gravar pose</h3>

  <img src="http://localhost:8001/preview" alt="preview"
       style="width:100%;max-width:360px;border-radius:10px;margin:12px 0;border:1px solid #2a3a4a;" />

  <label style="display:block;margin-bottom:8px;">
    Nome da pose
    <input bind:value={configState.draft.pose.shape}
           placeholder="ex: mao_aberta"
           style="display:block;margin-top:4px;padding:6px;width:240px;" />
  </label>

  <button onclick={record} disabled={recording}
          style="padding:8px 16px;border-radius:8px;background:#1f6feb;color:#fff;border:none;">
    {recording ? `Gravando… ${remaining}` : 'Segurar e gravar (15 frames)'}
  </button>

  <div style="margin-top:16px;display:flex;gap:8px;">
    <button onclick={() => goto('list')}>voltar</button>
    <button onclick={() => goto('compose')}>próximo →</button>
  </div>
</div>
```

Note: built-in poses (`fist`/`open`/`pinch`/`point`) need no recording — the user can type one of those names or skip straight to compose.

- [ ] **Step 2: Commit**

```bash
git add marcelo-ui/src/components/config/WizardRecord.svelte
git commit -m "feat(ui): add wizard step 1 (record pose)"
```

---

### Task 6: Wizard step 2 — compose + live test

**Files:**
- Create: `marcelo-ui/src/components/config/WizardCompose.svelte`

- [ ] **Step 1: Write the component**

```svelte
<script lang="ts">
  import { onDestroy } from 'svelte'
  import { configState, goto } from '../../stores/config.svelte'
  import { currentGesture, BUILTIN_POSES, MOTIONS } from '../../lib/config-api'

  let detected = $state('none')
  const poll = setInterval(async () => {
    detected = (await currentGesture()).gesture
  }, 250)
  onDestroy(() => clearInterval(poll))
</script>

<div style="padding:20px;color:#cdd9e5;">
  <h3>2 · Compor gesto</h3>

  <label style="display:block;margin:8px 0;">
    Nome do gesto
    <input bind:value={configState.draft.name}
           oninput={() => { configState.draft.id = configState.draft.name.toLowerCase().replace(/\s+/g, '_') }}
           style="display:block;margin-top:4px;padding:6px;width:240px;" />
  </label>

  <label style="display:block;margin:8px 0;">
    Pose
    <input list="poses" bind:value={configState.draft.pose.shape}
           style="display:block;margin-top:4px;padding:6px;width:240px;" />
    <datalist id="poses">
      {#each BUILTIN_POSES as p}<option value={p}></option>{/each}
    </datalist>
  </label>

  <label style="display:block;margin:8px 0;">
    Mãos
    <select bind:value={configState.draft.pose.hands}>
      <option value={1}>1</option>
      <option value={2}>2</option>
    </select>
  </label>

  <label style="display:block;margin:8px 0;">
    Movimento
    <select bind:value={configState.draft.motion.type}>
      {#each MOTIONS as m}<option value={m}>{m}</option>{/each}
    </select>
  </label>

  <p style="margin-top:12px;opacity:0.8;">
    Teste ao vivo — detectado agora:
    <strong style="color:{detected === configState.draft.id ? '#7ee787' : '#cdd9e5'};">{detected}</strong>
  </p>

  <div style="margin-top:16px;display:flex;gap:8px;">
    <button onclick={() => goto('record')}>← voltar</button>
    <button onclick={() => goto('bind')}>próximo →</button>
  </div>
</div>
```

- [ ] **Step 2: Commit**

```bash
git add marcelo-ui/src/components/config/WizardCompose.svelte
git commit -m "feat(ui): add wizard step 2 (compose + live test)"
```

---

### Task 7: Wizard step 3 — bind + save

**Files:**
- Create: `marcelo-ui/src/components/config/WizardBind.svelte`

- [ ] **Step 1: Write the component**

```svelte
<script lang="ts">
  import { configState, goto, refreshList } from '../../stores/config.svelte'
  import { saveGesture, EFFECTS, ACTIONS } from '../../lib/config-api'

  let modelParam = $state('gemini')
  let projectParam = $state('')

  async function save(): Promise<void> {
    const d = configState.draft
    if (d.binding.action === 'swap_model') d.binding.action_params = { model: modelParam }
    else if (d.binding.action === 'open_project') d.binding.action_params = { project: projectParam }
    else d.binding.action_params = {}
    if (!d.id) d.id = d.name.toLowerCase().replace(/\s+/g, '_')
    await saveGesture(d)
    await refreshList()
    goto('list')
  }
</script>

<div style="padding:20px;color:#cdd9e5;">
  <h3>3 · Ligar (efeito + ação)</h3>

  <label style="display:block;margin:8px 0;">
    Efeito
    <select bind:value={configState.draft.binding.effect}>
      {#each EFFECTS as e}<option value={e}>{e}</option>{/each}
    </select>
  </label>

  <label style="display:block;margin:8px 0;">
    Ação
    <select bind:value={configState.draft.binding.action}>
      {#each ACTIONS as a}<option value={a === 'none' ? null : a}>{a}</option>{/each}
    </select>
  </label>

  {#if configState.draft.binding.action === 'swap_model'}
    <label style="display:block;margin:8px 0;">
      Modelo
      <select bind:value={modelParam}>
        <option value="groq">groq</option>
        <option value="gemini">gemini</option>
      </select>
    </label>
  {:else if configState.draft.binding.action === 'open_project'}
    <label style="display:block;margin:8px 0;">
      Projeto
      <input bind:value={projectParam} style="padding:6px;" />
    </label>
  {/if}

  <div style="margin-top:16px;display:flex;gap:8px;">
    <button onclick={() => goto('compose')}>← voltar</button>
    <button onclick={save}
            style="padding:8px 16px;border-radius:8px;background:#238636;color:#fff;border:none;">
      Salvar gesto
    </button>
  </div>
</div>
```

- [ ] **Step 2: Commit**

```bash
git add marcelo-ui/src/components/config/WizardBind.svelte
git commit -m "feat(ui): add wizard step 3 (bind + save)"
```

---

### Task 8: Overlay container + App integration

**Files:**
- Create: `marcelo-ui/src/components/config/ConfigOverlay.svelte`
- Modify: `marcelo-ui/src/components/App.svelte`

- [ ] **Step 1: Write the overlay**

```svelte
<script lang="ts">
  import { configState, closeConfig } from '../../stores/config.svelte'
  import GestureList from './GestureList.svelte'
  import WizardRecord from './WizardRecord.svelte'
  import WizardCompose from './WizardCompose.svelte'
  import WizardBind from './WizardBind.svelte'
</script>

{#if configState.open}
  <div style="position:fixed;inset:0;z-index:50;display:flex;align-items:center;justify-content:center;
              background:rgba(3,6,10,0.7);backdrop-filter:blur(4px);">
    <div style="width:480px;max-height:80vh;overflow:auto;background:#0b1016;
                border:1px solid #2a3a4a;border-radius:14px;position:relative;">
      <button onclick={closeConfig}
              style="position:absolute;right:12px;top:12px;background:none;border:none;color:#8899aa;cursor:pointer;">✕</button>
      {#if configState.screen === 'list'}<GestureList />
      {:else if configState.screen === 'record'}<WizardRecord />
      {:else if configState.screen === 'compose'}<WizardCompose />
      {:else if configState.screen === 'bind'}<WizardBind />
      {/if}
    </div>
  </div>
{/if}
```

- [ ] **Step 2: Add the gear toggle + overlay to App.svelte**

In `marcelo-ui/src/components/App.svelte`, import and mount:

```svelte
<script lang="ts">
  import ParticleCanvas    from './ParticleCanvas.svelte'
  import WebcamView        from './WebcamView.svelte'
  import ChatOverlay       from './ChatOverlay.svelte'
  import ProjectsOverlay   from './ProjectsOverlay.svelte'
  import GestureHUD        from './GestureHUD.svelte'
  import ConfigOverlay     from './config/ConfigOverlay.svelte'
  import { openConfig }    from '../stores/config.svelte'
</script>

<ParticleCanvas />
<WebcamView />
<GestureHUD />
<ChatOverlay />
<ProjectsOverlay />
<ConfigOverlay />

<button onclick={openConfig}
        style="position:fixed;left:16px;bottom:16px;z-index:20;width:40px;height:40px;border-radius:50%;
               background:#11161d;color:#cdd9e5;border:1px solid #2a3a4a;cursor:pointer;">⚙</button>
```

Note: confirm `App.svelte`'s path. Per the repo it is `marcelo-ui/src/App.svelte` (root), not `components/`. Adjust the import paths (`./components/...`) if `App.svelte` lives at `src/App.svelte`. Verify with the existing file before editing.

- [ ] **Step 3: Manual end-to-end verify**

Start backend (8000), gesture-service (8001), vite (5173). Click the ⚙ gear.
Expected: the config overlay opens; "+ Novo gesto" → record a pose (progress counts down) → compose (live "detectado agora" updates) → bind (effect + action + param) → Salvar → the new gesture appears in the list and, after the backend reload, its action fires when performed.

- [ ] **Step 4: Commit**

```bash
git add marcelo-ui/src/components/config/ConfigOverlay.svelte marcelo-ui/src/App.svelte
git commit -m "feat(ui): add config overlay + gear toggle; wire the wizard"
```

---

### Task 9: Phase close + program close

- [ ] **Step 1: Frontend type check + build**

Run: `cd marcelo-ui && npx svelte-check --tsconfig ./tsconfig.json && npm run build`
Expected: 0 type errors; build succeeds.

- [ ] **Step 2: Backend full suite**

Run: `.venv\Scripts\python -m pytest && .venv\Scripts\python -m ruff check app gesture_service && .venv\Scripts\python -m pyright app gesture_service`
Expected: green across the board.

- [ ] **Step 3: Full-program manual acceptance (against the spec Success Criteria)**

With all three processes running:
- CV runs in a separate process; the browser never prompts for camera. ✓
- A live annotated webcam preview shows in a corner. ✓
- Built-in gestures produce fluid GPU reactions and trigger actions (model swap, open project). ✓
- A brand-new gesture can be created entirely from the UI (record → compose → bind) with no code. ✓
- Adding an effect/action means registering it in its catalog only. ✓
- Particles hold 60fps at 65k+. ✓

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore(gesture): phase 6 type/build/acceptance pass"
```

---

## Self-Review Notes

- **Spec coverage (Phase 6 §):** 6.1 list → Task 4. 6.2 record → Tasks 1,5. 6.3 compose + live test → Task 6. 6.4 bind + save → Task 7. Container/integration → Task 8.
- **Architecture correction:** recording is server-side (Task 1) because the browser has no landmarks under decision A; the Phase 5 vector-upload endpoint remains for tests. This is called out, not silently dropped.
- **App.svelte path caveat:** Task 8 Step 2 flags that `App.svelte` is at `src/App.svelte` in the repo; import paths must be verified before editing.
- **Type consistency:** consumes Phase 5 endpoints (`/api/v1/gestures`, service `/poses/*`, `/current`) and the Phase 3 effect names; `GestureDefinition` TS shape mirrors `GestureDefinitionSchema`.
- **Program complete:** with Phase 6 done, all six phases of the PLAN-INDEX are delivered and the spec's Success Criteria are verifiable end-to-end.
```
