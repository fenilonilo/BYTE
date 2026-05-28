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
