// Web Audio API analyser — TTS audio bytes → amplitude + mic stream → amplitude

let audioCtx = null;

function _getCtx() {
  if (!audioCtx) audioCtx = new AudioContext();
  return audioCtx;
}

/**
 * Decode and play TTS ArrayBuffer. Calls onAmplitude(0.0–1.0) each frame.
 * Returns Promise that resolves when playback ends.
 */
export async function playAndAnalyze(arrayBuffer, onAmplitude) {
  const ctx = _getCtx();
  if (ctx.state === 'suspended') await ctx.resume();
  const decoded = await ctx.decodeAudioData(arrayBuffer.slice(0));

  const analyser = ctx.createAnalyser();
  analyser.fftSize = 512;
  analyser.smoothingTimeConstant = 0.8;

  const source = ctx.createBufferSource();
  source.buffer = decoded;
  source.connect(analyser);
  analyser.connect(ctx.destination);
  source.start();

  const freqData = new Uint8Array(analyser.frequencyBinCount);
  let rafId;

  return new Promise((resolve) => {
    function tick() {
      analyser.getByteFrequencyData(freqData);
      let sum = 0;
      for (let i = 0; i < freqData.length; i++) sum += freqData[i];
      onAmplitude(sum / freqData.length / 255);
      rafId = requestAnimationFrame(tick);
    }

    source.onended = () => {
      cancelAnimationFrame(rafId);
      onAmplitude(0);
      resolve();
    };

    rafId = requestAnimationFrame(tick);
  });
}

/**
 * Analyse microphone stream. Returns stop() function.
 * Calls onAmplitude(0.0–1.0) each frame while active.
 */
export function analyzeMicStream(stream, onAmplitude) {
  const ctx     = _getCtx();
  const source  = ctx.createMediaStreamSource(stream);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 256;
  analyser.smoothingTimeConstant = 0.6;

  source.connect(analyser);

  const freqData = new Uint8Array(analyser.frequencyBinCount);
  let active = true;
  let rafId;

  function tick() {
    if (!active) return;
    analyser.getByteFrequencyData(freqData);
    let sum = 0;
    for (let i = 0; i < freqData.length; i++) sum += freqData[i];
    onAmplitude(sum / freqData.length / 255);
    rafId = requestAnimationFrame(tick);
  }

  rafId = requestAnimationFrame(tick);

  return function stop() {
    active = false;
    cancelAnimationFrame(rafId);
    onAmplitude(0);
    source.disconnect();
  };
}
