// Chat client — WebSocket + continuous STT loop + TTS
// Fires: onState, onTranscript, onResponse, onError

import { playAndAnalyze, analyzeMicStream } from './audio-analyzer.js';

export class ChatClient {
  constructor({ wsUrl, ttsUrl, onState, onTranscript, onResponse, onError, onPreview }) {
    this._wsUrl        = wsUrl;
    this._ttsUrl       = ttsUrl;
    this._onState      = onState      || (() => {});
    this._onTranscript = onTranscript || (() => {});
    this._onResponse   = onResponse   || (() => {});
    this._onError      = onError      || (() => {});
    this._onPreview    = onPreview    || (() => {});

    this._ws           = null;
    this._recognition  = null;
    this._sessionId    = 'ui-session';
    this._micStream    = null;
    this._micStopFn    = null;
    this._onAmpUpdate  = null;

    // Continuous mic state
    this._micActive    = false;  // user toggled on
    this._speaking     = false;  // Marcelo is speaking TTS
    this._waitingReply = false;  // waiting for WS response
  }

  // ── WebSocket ──────────────────────────────────────────────────────────────

  connect() {
    this._ws = new WebSocket(this._wsUrl);

    this._ws.onopen = () => { this._onState('idle'); };

    this._ws.onmessage = async (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === 'preview') {
        this._waitingReply = false;
        this._onState('idle');
        this._onPreview({ prompt: msg.prompt, project: msg.project });
        return;
      }
      if (msg.type === 'chunk') {
        this._onResponse(msg.text);
        this._waitingReply = false;
        await this._speakTTS(msg.text);
        this._onState('idle');
        // Resume listening after Marcelo finishes speaking
        if (this._micActive) this._startRecognition();
      } else if (msg.type === 'error') {
        this._onError(msg.text);
        this._waitingReply = false;
        this._onState('idle');
        if (this._micActive) this._startRecognition();
      }
    };

    this._ws.onerror = () => { this._onError('WebSocket error'); };
    this._ws.onclose = () => { setTimeout(() => this.connect(), 2000); };
  }

  // ── Text send ──────────────────────────────────────────────────────────────

  sendText(text) {
    const trimmed = text.trim();
    if (!trimmed || this._ws?.readyState !== WebSocket.OPEN) return;
    this._onTranscript({ role: 'user', text: trimmed });
    this._onState('thinking');
    this._waitingReply = true;
    this._ws.send(JSON.stringify({ message: trimmed, session_id: this._sessionId }));
  }

  // ── Mic toggle (called by button) ─────────────────────────────────────────

  async enableMic() {
    if (this._micActive) return;
    try {
      this._micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      this._onError('Microphone permission denied');
      return;
    }
    if (this._onAmpUpdate) {
      this._micStopFn = analyzeMicStream(this._micStream, this._onAmpUpdate);
    }
    this._micActive = true;
    this._startRecognition();
  }

  disableMic() {
    this._micActive = false;
    this._stopRecognition();
    if (this._micStopFn)  { this._micStopFn(); this._micStopFn = null; }
    if (this._micStream)  { this._micStream.getTracks().forEach(t => t.stop()); this._micStream = null; }
    this._onState('idle');
  }

  // Legacy API used by HTML
  async startMic() { await this.enableMic(); }
  stopMic()        { this.disableMic(); }

  setAmplitudeCallback(fn) { this._onAmpUpdate = fn; }

  approvePreview() {
    if (this._ws?.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify({ type: 'approve_send', session_id: this._sessionId }));
    }
  }

  cancelPreview() {
    if (this._ws?.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify({ type: 'cancel_send', session_id: this._sessionId }));
    }
  }

  // ── Recognition loop ───────────────────────────────────────────────────────

  _startRecognition() {
    if (this._recognition)   return;  // already running
    if (this._speaking)      return;  // Marcelo talking
    if (this._waitingReply)  return;  // waiting for response
    if (!this._micActive)    return;

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) { this._onError('Web Speech API not supported'); return; }

    this._onState('listening');
    const rec = new SpeechRecognition();
    rec.lang            = 'pt-BR';
    rec.continuous      = false;
    rec.interimResults  = true;
    this._recognition   = rec;

    let finalSent = false;

    rec.onresult = (ev) => {
      const transcript = Array.from(ev.results).map(r => r[0].transcript).join('');
      this._onTranscript({ role: 'interim', text: transcript });

      if (ev.results[ev.results.length - 1].isFinal && !finalSent) {
        finalSent = true;
        this._stopRecognition();
        this.sendText(transcript);
        // sendText sets waitingReply=true — recognition won't restart until reply arrives
      }
    };

    rec.onerror = (ev) => {
      // 'no-speech' is normal silence — restart loop quietly
      if (ev.error === 'no-speech' || ev.error === 'aborted') return;
      this._onError(`STT: ${ev.error}`);
    };

    rec.onend = () => {
      this._recognition = null;
      // Restart loop if still active and no pending reply
      if (this._micActive && !this._speaking && !this._waitingReply) {
        setTimeout(() => this._startRecognition(), 150);
      }
    };

    rec.start();
  }

  _stopRecognition() {
    if (this._recognition) {
      try { this._recognition.abort(); } catch (_) {}
      this._recognition = null;
    }
  }

  // ── TTS ────────────────────────────────────────────────────────────────────

  async _speakTTS(text) {
    this._speaking = true;
    this._stopRecognition();  // don't listen while speaking
    this._onState('speaking');
    try {
      const res = await fetch(this._ttsUrl, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ text }),
      });
      if (!res.ok) throw new Error(`TTS HTTP ${res.status}`);
      const buffer = await res.arrayBuffer();
      const ctx = new AudioContext();
      if (ctx.state === 'suspended') await ctx.resume();
      await playAndAnalyze(buffer, (amp) => {
        if (this._onAmpUpdate) this._onAmpUpdate(amp);
      });
    } catch (err) {
      this._onError(`TTS groq: ${err.message} — fallback`);
      await this._speakWebSpeech(text);
    } finally {
      this._speaking = false;
    }
  }

  // ── Web Speech fallback ────────────────────────────────────────────────────

  _pickVoice() {
    const voices = window.speechSynthesis.getVoices();
    return (
      voices.find(v => v.name.includes('Google') && v.lang === 'pt-BR') ||
      voices.find(v => v.lang === 'pt-BR') ||
      voices.find(v => v.lang.startsWith('pt')) ||
      voices[0] || null
    );
  }

  _speakWebSpeech(text) {
    return new Promise((resolve, reject) => {
      if (!window.speechSynthesis) { reject(new Error('no speechSynthesis')); return; }
      window.speechSynthesis.cancel();

      const speak = () => {
        const utter = new SpeechSynthesisUtterance(text);
        utter.lang = 'pt-BR'; utter.rate = 0.95; utter.pitch = 0.95;
        const voice = this._pickVoice();
        if (voice) utter.voice = voice;

        let pulse = null;
        utter.onstart = () => {
          let t = 0;
          pulse = setInterval(() => {
            t += 0.07;
            const amp = 0.28 + 0.22 * Math.abs(Math.sin(t * 1.3 + Math.random() * 0.3));
            if (this._onAmpUpdate) this._onAmpUpdate(amp);
          }, 35);
        };
        utter.onend = () => { clearInterval(pulse); if (this._onAmpUpdate) this._onAmpUpdate(0); resolve(); };
        utter.onerror = (ev) => {
          clearInterval(pulse);
          if (this._onAmpUpdate) this._onAmpUpdate(0);
          if (ev.error === 'interrupted') { resolve(); return; }
          reject(new Error(ev.error));
        };
        window.speechSynthesis.speak(utter);
      };

      window.speechSynthesis.getVoices().length === 0
        ? (window.speechSynthesis.onvoiceschanged = speak)
        : speak();
    });
  }
}
