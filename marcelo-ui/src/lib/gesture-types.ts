export interface WireVec3 { x: number; y: number; z: number }

export interface WireGestureParams {
  points: WireVec3[]
  vector: WireVec3
  center: WireVec3
  radius: number
  magnitude: number
}

export interface WireGestureEvent {
  gesture: string
  phase: 'start' | 'hold' | 'end' | 'instant' | 'idle'
  hands: 0 | 1 | 2
  params: WireGestureParams
  ts: number
}
