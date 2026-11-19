// "Ei Byte" in the browser: the same models/ei_byte.onnx as voice/wake.py, behind the same
// openWakeWord streaming pipeline (16 kHz PCM16 -> melspectrogram -> embedding -> classifier),
// run locally with onnxruntime-web. No audio leaves the browser while waiting for the wake word.

export const WAKE_THRESHOLD = 0.5; // voice/config.py default (BYTE_VOICE_THRESHOLD)
export const ORT_URL = 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.22.0/dist/ort.wasm.min.mjs';

const CHUNK = 1280; // 80 ms at 16 kHz
const MEL_CONTEXT = 160 * 3; // openWakeWord re-reads 3 hops of past audio per chunk
const MEL_BINS = 32;
const MEL_WINDOW = 76; // mel frames per embedding
const EMB_SIZE = 96;
const EMB_WINDOW = 16; // embeddings per classifier input

/**
 * Load the three models from `base` with an onnxruntime-web module. Returns
 * `{ push(Int16Array) -> Promise<number>, reset() }`; push gives the best score of the chunks it
 * completed (0 while warming up). Calls must not overlap: await each one.
 */
export async function createWake(ort, base) {
  const load = (name) => ort.InferenceSession.create(`${base}/${name}.onnx`, { executionProviders: ['wasm'] });
  const [mel, emb, cls] = await Promise.all(['melspectrogram', 'embedding_model', 'ei_byte'].map(load));

  async function run(session, data, dims) {
    const out = await session.run({ [session.inputNames[0]]: new ort.Tensor('float32', data, dims) });
    return out[session.outputNames[0]].data;
  }
  async function melRows(audio) {
    const spec = await run(mel, audio, [1, audio.length]);
    const rows = [];
    for (let f = 0; f < spec.length / MEL_BINS; f++) {
      rows.push(spec.slice(f * MEL_BINS, (f + 1) * MEL_BINS).map((x) => x / 10 + 2));
    }
    return rows;
  }
  const embed = (rows) => run(emb, flat(rows), [1, MEL_WINDOW, MEL_BINS, 1]);

  // openWakeWord starts its feature buffer from 4 s of low noise, so it scores right away.
  const noise = Float32Array.from({ length: 16000 * 4 }, () => Math.floor(Math.random() * 2000) - 1000);
  const noiseRows = await melRows(noise);
  const seed = [];
  for (let end = noiseRows.length; seed.length < EMB_WINDOW; end -= 8) seed.unshift(await embed(noiseRows.slice(end - MEL_WINDOW, end)));

  let pending, tail, mels, embs, muted;
  function reset() {
    pending = new Float32Array(0);
    tail = new Float32Array(0);
    mels = Array.from({ length: MEL_WINDOW }, () => new Float32Array(MEL_BINS).fill(1));
    embs = seed.slice();
    muted = 5; // openWakeWord zeroes the first 5 predictions after a reset
  }
  reset();

  async function step(chunk) {
    const audio = concat(tail, chunk);
    tail = audio.slice(-MEL_CONTEXT);
    mels.push(...await melRows(audio));
    mels.splice(0, mels.length - MEL_WINDOW);
    embs.push(await embed(mels));
    embs.splice(0, embs.length - EMB_WINDOW);
    const score = (await run(cls, flat(embs), [1, EMB_WINDOW, EMB_SIZE]))[0];
    if (muted > 0) { muted--; return 0; }
    return score;
  }

  async function push(pcm) {
    // openWakeWord feeds the int16 values as floats, unscaled.
    pending = concat(pending, Float32Array.from(pcm));
    let best = 0;
    while (pending.length >= CHUNK) {
      const chunk = pending.slice(0, CHUNK);
      pending = pending.slice(CHUNK);
      best = Math.max(best, await step(chunk));
    }
    return best;
  }

  return { push, reset };
}

function concat(a, b) {
  const out = new Float32Array(a.length + b.length);
  out.set(a);
  out.set(b, a.length);
  return out;
}

function flat(rows) {
  const out = new Float32Array(rows.length * rows[0].length);
  rows.forEach((r, i) => out.set(r, i * r.length));
  return out;
}
