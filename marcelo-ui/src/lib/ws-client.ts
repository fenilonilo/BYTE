import { playAndAnalyze, analyzeMicStream } from './audio-analyzer'

// Web Speech API — not yet in TypeScript's built-in DOM lib
interface SpeechRecognitionResult {
  readonly isFinal: boolean
  readonly length: number
  item(index: number): SpeechRecognitionAlternative
  [index: number]: SpeechRecognitionAlternative
}
interface SpeechRecognitionResultList {
  readonly length: number
  item(index: number): SpeechRecognitionResult
  [index: number]: SpeechRecognitionResult
}
interface SpeechRecognitionEvent extends Event {
  readonly results: SpeechRecognitionResultList
}
interface SpeechRecognitionErrorEvent extends Event {
  readonly error: string
}
interface SpeechRecognition extends EventTarget {
  lang: string
  continuous: boolean
  interimResults: boolean
  onresult: ((ev: SpeechRecognitionEvent) => void) | null
  onerror: ((ev: SpeechRecognitionErrorEvent) => void) | null
  onend: (() => void) | null
  start(): void
  stop(): void
}
interface SpeechRecognitionConstructor {
  new (): SpeechRecognition
}

type StateCallback    = (s: 'idle' | 'listening' | 'thinking' | 'speaking') => void
type ChunkCallback    = (text: string) => void
type InterimCallback  = (text: string | null) => void
type PreviewCallback  = (text: string) => void
type DoneCallback     = (text: string) => void
type ErrorCallback    = (msg: string) => void
type AmpCallback      = (amp: number) => void

interface WsClientOptions {
  wsUrl:      string
  ttsUrl:     string
  onState:    StateCallback
  onChunk:    ChunkCallback
  /** Called with in-progress STT text, null when mic stops */
  onInterim:  InterimCallback
  onPreview:  PreviewCallback
  onDone:     DoneCallback
  onError:    ErrorCallback
}

export class WsClient {
  private _ws:           WebSocket | null = null
  private _recognition:  SpeechRecognition | null = null
  private _micStream:    MediaStream | null = null
  private _micStopFn:    (() => void) | null = null
  private _silenceTimer: ReturnType<typeof setTimeout> | null = null
  private _onAmp:        AmpCallback | null = null
  private _sessionId = 'ui-session'

  constructor(private readonly _opts: WsClientOptions) {}

  connect(): void {
    this._ws = new WebSocket(this._opts.wsUrl)

    this._ws.onopen = () => {
      this._opts.onState('idle')
    }

    this._ws.onmessage = async (ev: MessageEvent) => {
      const msg = JSON.parse(ev.data as string) as { type: string; text?: string }

      if (msg.type === 'chunk') {
        this._opts.onChunk(msg.text ?? '')
        await this._speakTTS(msg.text ?? '')
        this._opts.onState('idle')
      } else if (msg.type === 'preview') {
        this._opts.onPreview(msg.text ?? '')
      } else if (msg.type === 'done') {
        this._opts.onDone(msg.text ?? '')
        this._opts.onState('idle')
      } else if (msg.type === 'error') {
        this._opts.onError(msg.text ?? 'Unknown error')
        this._opts.onState('idle')
      }
    }

    this._ws.onerror = () => this._opts.onError('WebSocket error')
    this._ws.onclose = () => { setTimeout(() => this.connect(), 2000) }
  }

  sendText(text: string): void {
    const trimmed = text.trim()
    if (!trimmed || this._ws?.readyState !== WebSocket.OPEN) return
    this._opts.onState('thinking')
    this._ws.send(JSON.stringify({ type: 'message', message: trimmed, session_id: this._sessionId }))
  }

  approve(): void {
    this._ws?.send(JSON.stringify({ type: 'approve_send' }))
  }

  cancel(): void {
    this._ws?.send(JSON.stringify({ type: 'cancel_send' }))
  }

  async startMic(): Promise<void> {
    if (this._recognition) return
    try {
      this._micStream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch {
      this._opts.onError('Microphone permission denied')
      return
    }

    this._opts.onState('listening')
    if (this._onAmp) {
      this._micStopFn = analyzeMicStream(this._micStream, this._onAmp)
    }

    const w = window as Window & {
      SpeechRecognition?: SpeechRecognitionConstructor
      webkitSpeechRecognition?: SpeechRecognitionConstructor
    }
    const SR: SpeechRecognitionConstructor | undefined = w.SpeechRecognition ?? w.webkitSpeechRecognition
    if (!SR) { this._opts.onError('Web Speech API not supported'); return }

    this._recognition = new SR()
    this._recognition.lang = 'pt-BR'
    this._recognition.continuous = false
    this._recognition.interimResults = true

    this._recognition.onresult = (ev: SpeechRecognitionEvent) => {
      const transcript = Array.from(ev.results).map((r: SpeechRecognitionResult) => r[0].transcript).join('')
      // Interim: show in-progress text without adding to message history
      this._opts.onInterim(transcript)

      clearTimeout(this._silenceTimer!)
      this._silenceTimer = setTimeout(() => this._finalizeMic(), 2000)

      if (ev.results[ev.results.length - 1].isFinal) {
        this._opts.onInterim(null)  // clear interim
        this._finalizeMic()
        this.sendText(transcript)
      }
    }

    this._recognition.onerror  = () => { this._opts.onInterim(null); this._finalizeMic() }
    this._recognition.onend    = () => { this._recognition = null }
    this._recognition.start()
  }

  stopMic(): void { this._finalizeMic() }

  setAmpCallback(fn: AmpCallback): void { this._onAmp = fn }

  private _finalizeMic(): void {
    this._micStopFn?.(); this._micStopFn = null
    this._recognition?.stop(); this._recognition = null
    this._micStream?.getTracks().forEach(t => t.stop()); this._micStream = null
    if (this._silenceTimer) clearTimeout(this._silenceTimer)
  }

  private async _speakTTS(text: string): Promise<void> {
    this._opts.onState('speaking')
    try {
      const res = await fetch(this._opts.ttsUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      })
      if (!res.ok) throw new Error(`TTS HTTP ${res.status}`)
      const buf = await res.arrayBuffer()
      await playAndAnalyze(buf, amp => this._onAmp?.(amp))
    } catch (err) {
      this._opts.onError(`TTS error: ${(err as Error).message}`)
    }
  }
}
