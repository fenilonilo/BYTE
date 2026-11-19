// Microphone worklet: the context's rate in, PCM16 mono out at 16 kHz (wake word) and 24 kHz
// (WS /live). Each output sample is the mean of the input samples it spans: a box filter is a
// cheap anti-alias that keeps speech intelligible without a FIR.

export class Resampler {
  constructor(fromRate, toRate) {
    this.step = fromRate / toRate;
    this.pos = 0;
    this.sum = 0;
    this.n = 0;
    this.last = 0;
  }

  /** Feed Float32 samples in [-1, 1]; returns the PCM16 samples completed so far. */
  push(input) {
    const out = [];
    for (let i = 0; i < input.length; i++) {
      this.sum += input[i];
      this.n++;
      this.pos += 1;
      while (this.pos >= this.step) {
        if (this.n) { this.last = this.sum / this.n; this.sum = 0; this.n = 0; }
        out.push(this.last); // upsampling (step < 1) repeats the last value
        this.pos -= this.step;
      }
    }
    return floatToPcm16(out);
  }
}

export function floatToPcm16(samples) {
  const pcm = new Int16Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return pcm;
}

// 1280 samples is the 80 ms chunk openWakeWord expects; 960 is 40 ms of live audio.
const CHUNK = { 16000: 1280, 24000: 960 };

if (typeof AudioWorkletProcessor !== 'undefined') {
  class MicProcessor extends AudioWorkletProcessor {
    constructor() {
      super();
      // `sampleRate` is the AudioWorkletGlobalScope's: the context's rate.
      this.lanes = Object.keys(CHUNK).map((rate) => ({
        rate: Number(rate), size: CHUNK[rate], resampler: new Resampler(sampleRate, Number(rate)), buf: [],
      }));
    }

    process(inputs) {
      const channel = inputs[0]?.[0];
      if (!channel) return true;
      for (const lane of this.lanes) {
        const pcm = lane.resampler.push(channel);
        for (let i = 0; i < pcm.length; i++) lane.buf.push(pcm[i]);
        while (lane.buf.length >= lane.size) {
          const chunk = Int16Array.from(lane.buf.splice(0, lane.size));
          this.port.postMessage({ rate: lane.rate, pcm: chunk }, [chunk.buffer]);
        }
      }
      return true;
    }
  }
  registerProcessor('byte-mic', MicProcessor);
}
