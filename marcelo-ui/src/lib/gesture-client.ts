import type { WireGestureEvent } from './gesture-types'

type Listener = (ev: WireGestureEvent) => void

let socket: WebSocket | null = null
let listener: Listener | null = null
let reconnectTimer: number | null = null

export function connectGestures(onEvent: Listener): void {
  listener = onEvent
  open()
}

function open(): void {
  // Vite proxies /ws -> ws://localhost:8000 (see vite.config.ts)
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  socket = new WebSocket(`${proto}://${location.host}/ws/gesture`)

  socket.onmessage = (msg) => {
    try {
      const ev = JSON.parse(msg.data) as WireGestureEvent
      listener?.(ev)
    } catch {
      /* ignore malformed frame */
    }
  }
  socket.onclose = () => {
    reconnectTimer = window.setTimeout(open, 2000)
  }
}

export function disconnectGestures(): void {
  if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
  socket?.close()
  socket = null
  listener = null
}
