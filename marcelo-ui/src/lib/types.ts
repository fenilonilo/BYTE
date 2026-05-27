import type { Vector3 } from 'three'

// ─── Unified Gesture (new architecture) ──────────────────────────────────────

export type UnifiedGesture =
  | 'none' | 'pinch' | 'swipe'
  | 'explosion' | 'orbit' | 'freeze' | 'portal'

export interface UnifiedGestureState {
  gesture:      UnifiedGesture
  handCount:    0 | 1 | 2
  swipeSign:    number           // +1 right, -1 left; only meaningful for 'swipe'
  orbitAnchor:  Vector3          // world position of pinch hand; only for 'orbit'
  portalCenter: Vector3          // midpoint between hands; only for 'portal'
  portalRadius: number           // half-distance between hands; only for 'portal'
  phase:        string           // 'idle' | 'contact' | 'blast' | 'sustained' | 'instant'
}

// ─── Chat ─────────────────────────────────────────────────────────────────────

export type MessageRole = 'user' | 'assistant' | 'interim'

export interface ChatMessage {
  id: string
  role: MessageRole
  text: string
  timestamp: number
}

export interface ChatState {
  messages: ChatMessage[]
  /** STT in-progress transcript, null when not listening */
  interim: string | null
  /** Claude Code task preview awaiting approve/cancel */
  preview: string | null
  streaming: boolean
  connected: boolean
}

// ─── Projects ─────────────────────────────────────────────────────────────────

export interface ProjectItem {
  name: string
  path: string
  /** Unix timestamp seconds (from backend mtime) */
  mtime: number
}

export interface ProjectsState {
  items: ProjectItem[]
  loading: boolean
}

// ─── Particle engine state ────────────────────────────────────────────────────

export type ParticleState = 'idle' | 'listening' | 'thinking' | 'speaking'
