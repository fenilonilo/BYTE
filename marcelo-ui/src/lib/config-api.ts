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
