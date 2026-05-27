import type { ChatMessage, ChatState } from '../lib/types'

let _idCounter = 0
function _id(): string { return `msg-${++_idCounter}` }

export const chatState = $state<ChatState>({
  messages: [],
  interim:  null,
  preview:  null,
  streaming: false,
  connected: false,
})

export function addMessage(role: ChatMessage['role'], text: string): void {
  chatState.messages.push({ id: _id(), role, text, timestamp: Date.now() })
}

export function appendChunk(text: string): void {
  const last = chatState.messages.at(-1)
  if (last?.role === 'assistant') {
    last.text += text
  } else {
    chatState.messages.push({ id: _id(), role: 'assistant', text, timestamp: Date.now() })
  }
}

export function setInterim(text: string | null): void {
  chatState.interim = text
}

export function setPreview(text: string | null): void {
  chatState.preview = text
}
