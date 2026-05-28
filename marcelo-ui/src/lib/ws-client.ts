import { playAndAnalyze, analyzeMicStream } from './audio-analyzer'

type StateCallback   = (s: 'idle' | 'listening' | 'thinking' | 'speaking') => void
type ChunkCallback   = (text: string) => void
type InterimCallback = (text: string | null) => void
type PreviewCallback = (text: string) => void
type DoneCallback    = (text: string) => void
type ErrorCallback   = (msg: string) => void
type AmpCallback     = (amp: number) => void

interface WsClientOptions {
  wsUrl:      string
  ttsUrl:     string
  sttUrl:     string
  onState:    StateCallback
  onChunk:    ChunkCallback
  onInterim:  InterimCallback
  onPreview:  PreviewCallback
  onDone:     DoneCallback
  onError:    ErrorCallback
}

const AMP_THRESHOLD  = 0.02  // amplitude above this = speech
const SILENCE_MS     = 1500  // silence duration before auto-stop
const MAX_RECORD_MS  = 30000 // hard cap per session

export class WsClient {
  private _ws:          WebSocket | null = null
  private _micStream:   MediaStream | null = null
  private _micStopFn:   (() => void) | null = null
  private _recorder:    MediaRecorder | null = null
  private _chunks:      Blob[] = []
  private _silenceAt:   number | null = null
  private _hasSpoken    = false
  private _maxTimer:    ReturnType<typeof setTimeout> | null = null
  private _onAmp:       AmpCallback | null = null
  private _sessionId  = 'ui-session'

  constructor(private readonly _opts: WsClientOptions) {}

  connect(): void {
    this._ws = new WebSocket(this._opts.wsUrl)

    this._ws.onopen = () => { this._opts.onState('idle') }

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

  approve(): void { this._ws?.send(JSON.stringify({ type: 'approve_send' })) }
  cancel():  void { this._ws?.send(JSON.stringify({ type: 'cancel_send' })) }

  async startMic(): Promise<void> {
    if (this._recorder) return

    try {
      this._micStream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch {
      this._opts.onError('Microphone permission denied')
      return
    }

    this._opts.onState('listening')
    this._chunks   = []
    this._hasSpoken = false
    this._silenceAt = null

    // Amplitude analysis for VAD + visual feedback
    this._micStopFn = analyzeMicStream(this._micStream, (amp) => {
      this._onAmp?.(amp)
      if (amp > AMP_THRESHOLD) {
        this._hasSpoken = true
        this._silenceAt = null
      } else if (this._hasSpoken) {
        if (this._silenceAt === null) {
          this._silenceAt = Date.now()
        } else if (Date.now() - this._silenceAt >= SILENCE_MS) {
          this._stopRecording()
        }
      }
    })

    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : 'audio/webm'

    this._recorder = new MediaRecorder(this._micStream, { mimeType })
    this._recorder.ondataavailable = (e) => { if (e.data.size > 0) this._chunks.push(e.data) }
    this._recorder.onstop = () => { void this._transcribeAndSend() }
    this._recorder.start(250) // collect chunks every 250ms

    // Hard cap: stop after MAX_RECORD_MS regardless
    this._maxTimer = setTimeout(() => this._stopRecording(), MAX_RECORD_MS)
  }

  stopMic(): void { this._stopRecording() }

  setAmpCallback(fn: AmpCallback): void { this._onAmp = fn }

  private _stopRecording(): void {
    if (!this._recorder) return
    if (this._maxTimer) { clearTimeout(this._maxTimer); this._maxTimer = null }
    this._micStopFn?.(); this._micStopFn = null
    this._micStream?.getTracks().forEach(t => t.stop()); this._micStream = null
    const rec = this._recorder; this._recorder = null
    if (rec.state !== 'inactive') rec.stop() // triggers onstop → _transcribeAndSend
  }

  private async _transcribeAndSend(): Promise<void> {
    if (this._chunks.length === 0 || !this._hasSpoken) {
      this._opts.onState('idle')
      return
    }

    this._opts.onInterim('transcrevendo…')

    const blob = new Blob(this._chunks, { type: 'audio/webm' })
    // Reject suspiciously small blobs (< 2KB = silence/noise only)
    if (blob.size < 2048) {
      this._opts.onState('idle')
      return
    }
    const formData = new FormData()
    formData.append('audio', blob, 'audio.webm')

    try {
      const res = await fetch(this._opts.sttUrl, { method: 'POST', body: formData })
      if (!res.ok) throw new Error(`STT HTTP ${res.status}`)
      const { transcript } = await res.json() as { transcript: string }
      this._opts.onInterim(null)
      if (transcript.trim()) {
        this.sendText(transcript)
      } else {
        this._opts.onState('idle')
      }
    } catch (err) {
      this._opts.onInterim(null)
      this._opts.onError(`STT error: ${(err as Error).message}`)
      this._opts.onState('idle')
    }
  }

  private async _speakTTS(text: string): Promise<void> {
    this._opts.onState('speaking')
    try {
      const res = await fetch(this._opts.ttsUrl, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ text }),
      })
      if (!res.ok) throw new Error(`TTS HTTP ${res.status}`)
      const buf = await res.arrayBuffer()
      await playAndAnalyze(buf, amp => this._onAmp?.(amp))
    } catch (err) {
      this._opts.onError(`TTS error: ${(err as Error).message}`)
    }
  }
}
