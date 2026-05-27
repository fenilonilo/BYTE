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

// ─── Legacy gesture types (kept until GestureHUD migrates in Task 5) ─────────

export type HandGesture = 'none' | 'open' | 'pinch' | 'fist' | 'point' | 'swipe' | 'breathe' | 'idle'

export type BimanualGesture =
  | 'prayer-explosion'
  | 'implosion'
  | 'orbit'
  | 'freeze'
  | 'dual-pinch'
  | 'portal'

export interface HandState {
  gesture: HandGesture
  worldPos: Vector3
  velocity: Vector3
  /** milliseconds this gesture has been held continuously */
  age: number
}

export interface BimanualPattern {
  active: boolean
  pattern: BimanualGesture | null
  phase: string
  /** 0..1 completion progress for phase transitions */
  progress: number
}

export interface GestureState {
  left: HandState
  right: HandState
  bimanual: BimanualPattern
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
