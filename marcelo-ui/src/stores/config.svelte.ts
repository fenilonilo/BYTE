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
