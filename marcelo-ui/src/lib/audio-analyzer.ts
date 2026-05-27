let ctx: AudioContext | null = null

function _getCtx(): AudioContext {
  if (!ctx) ctx = new AudioContext()
  return ctx
}

/**
 * Decode and play an audio ArrayBuffer. Calls onAmplitude (0..1) each animation frame.
 * Returns a Promise that resolves when playback ends.
 */
export async function playAndAnalyze(
  arrayBuffer: ArrayBuffer,
  onAmplitude: (amp: number) => void,
): Promise<void> {
  const audioCtx = _getCtx()
  const decoded  = await audioCtx.decodeAudioData(arrayBuffer)

  const source   = audioCtx.createBufferSource()
  source.buffer  = decoded

  const analyser = audioCtx.createAnalyser()
  analyser.fftSize = 256
  source.connect(analyser)
  analyser.connect(audioCtx.destination)

  const data = new Uint8Array(analyser.frequencyBinCount)

  let rafId: number
  function tick() {
    analyser.getByteFrequencyData(data)
    const avg = data.reduce((a, b) => a + b, 0) / data.length
    onAmplitude(avg / 255)
    rafId = requestAnimationFrame(tick)
  }

  return new Promise((resolve) => {
    source.onended = () => {
      cancelAnimationFrame(rafId)
      onAmplitude(0)
      resolve()
    }
    source.start()
    tick()
  })
}

/**
 * Analyse mic stream amplitude in real-time.
 * Returns a stop() function.
 */
export function analyzeMicStream(
  stream: MediaStream,
  onAmplitude: (amp: number) => void,
): () => void {
  const audioCtx = _getCtx()
  const source   = audioCtx.createMediaStreamSource(stream)
  const analyser = audioCtx.createAnalyser()
  analyser.fftSize = 256
  source.connect(analyser)

  const data = new Uint8Array(analyser.frequencyBinCount)
  let rafId: number
  let running = true

  function tick() {
    if (!running) return
    analyser.getByteFrequencyData(data)
    const avg = data.reduce((a, b) => a + b, 0) / data.length
    onAmplitude(avg / 255)
    rafId = requestAnimationFrame(tick)
  }
  tick()

  return () => {
    running = false
    cancelAnimationFrame(rafId)
    onAmplitude(0)
    source.disconnect()
  }
}
