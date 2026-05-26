// Chat client — WebSocket to /ws/chat + Web Speech API STT + TTS via /tts
// Fires: onState, onTranscript, onResponse, onError

import { playAndAnalyze, analyzeMicStream } from './audio-analyzer.js';

export class ChatClient {
  constructor({ wsUrl, ttsUrl, onState, onTranscript, onResponse, onError }) {
    this._wsUrl        = wsUrl;
    this._ttsUrl       = ttsUrl;
    this._onState      = onState      || (() => {});
    this._onTranscript = onTranscript || (() => {});
    this._onResponse   = onResponse   || (() => {});
    this._onError      = onError      || (() => {});

    this._ws            = null;
    this._recognition   = null;
    this._sessionId     = 'ui-session';
    this._micStream     = null;
    this._micStopFn     = null;
    this._silenceTimer  = null;
    this._onAmpUpdate   = null;
  }

  connect() {
    this._ws = new WebSocket(this._wsUrl);

    this._ws.onopen = () => {
      this._onState('idle');
    };

    this._ws.onmessage = async (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === 'chunk') {
        this._onResponse(msg.text);
        await this._speakTTS(msg.text);
        this._onState('idle');
      } else if (msg.type === 'error') {
        this._onError(msg.text);
        this._onState('idle');
      }
    };

    this._ws.onerror = () => {
      this._onError('WebSocket error');
    };

    this._ws.onclose = () => {
      setTimeout(() => this.connect(), 2000);
    };
  }

  sendText(text) {
    const trimmed = text.trim();
    if (!trimmed || this._ws?.readyState !== WebSocket.OPEN) return;
    this._onTranscript({ role: 'user', text: trimmed });
    this._onState('thinking');
    this._ws.send(JSON.stringify({ message: trimmed, session_id: this._sessionId }));
  }

  async startMic() {
    if (this._recognition) return;

    try {
      this._micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      this._onError('Microphone permission denied');
      return;
    }

    this._onState('listening');

    if (this._onAmpUpdate) {
      this._micStopFn = analyzeMicStream(this._micStream, this._onAmpUpdate);
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      this._onError('Web Speech API not supported');
      return;
    }

    this._recognition = new SpeechRecognition();
    this._recognition.lang = 'pt-BR';
    this._recognition.continuous = false;
    this._recognition.interimResults = true;

    this._recognition.onresult = (ev) => {
      const transcript = Array.from(ev.results)
        .map(r => r[0].transcript)
        .join('');

      this._onTranscript({ role: 'interim', text: transcript });

      clearTimeout(this._silenceTimer);
      this._silenceTimer = setTimeout(() => this._finalizeMic(), 2000);

      if (ev.results[ev.results.length - 1].isFinal) {
        this._finalizeMic();
        this.sendText(transcript);
      }
    };

    this._recognition.onerror = () => this._finalizeMic();
    this._recognition.onend   = () => { this._recognition = null; };
    this._recognition.start();
  }

  stopMic() {
    this._finalizeMic();
  }

  setAmplitudeCallback(fn) {
    this._onAmpUpdate = fn;
  }

  _finalizeMic() {
    if (this._micStopFn)   { this._micStopFn(); this._micStopFn = null; }
    if (this._recognition) { this._recognition.stop(); this._recognition = null; }
    if (this._micStream)   { this._micStream.getTracks().forEach(t => t.stop()); this._micStream = null; }
    clearTimeout(this._silenceTimer);
  }

  async _speakTTS(text) {
    this._onState('speaking');
    try {
      const res = await fetch(this._ttsUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });

      if (!res.ok) throw new Error(`TTS HTTP ${res.status}`);

      const buffer = await res.arrayBuffer();
      await playAndAnalyze(buffer, (amp) => {
        if (this._onAmpUpdate) this._onAmpUpdate(amp);
      });
    } catch (err) {
      this._onError(`TTS error: ${err.message}`);
    }
  }
}
