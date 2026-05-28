<script lang="ts">
  import { onMount, tick } from 'svelte'
  import { chatState, addMessage, appendChunk, setInterim, setPreview } from '../stores/chat.svelte'
  import { WsClient } from '../lib/ws-client'
  import StatusBadge from './StatusBadge.svelte'
  import type { ParticleState } from '../lib/types'
  import { setState as setParticleState, setAmplitude } from '../lib/gpgpu/engine'

  let collapsed = $state(false)
  let inputText = $state('')
  let transcriptEl: HTMLDivElement
  let particleState = $state<ParticleState>('idle')

  let client: WsClient

  onMount(() => {
    client = new WsClient({
      wsUrl:  `ws://${window.location.host}/ws/chat`,
      ttsUrl: '/api/v1/tts',
      sttUrl: '/api/v1/stt',
      onState: (s) => {
        particleState = s as ParticleState
        setParticleState(s as ParticleState)
      },
      onChunk: (text) => {
        // WS streaming chunk — adds/appends to assistant message history
        appendChunk(text)
        _scrollToBottom()
      },
      onInterim: (text) => {
        // STT in-progress — shown separately, NOT added to message history
        setInterim(text)
      },
      onPreview: (text) => {
        setPreview(text)
      },
      onDone: () => {
        chatState.streaming = false
      },
      onError: (msg) => {
        addMessage('assistant', `⚠ ${msg}`)
      },
    })

    client.setAmpCallback((amp) => setAmplitude(amp))
    client.connect()
  })

  async function _scrollToBottom() {
    await tick()
    transcriptEl?.scrollTo({ top: transcriptEl.scrollHeight, behavior: 'smooth' })
  }

  function sendText() {
    const t = inputText.trim()
    if (!t) return
    addMessage('user', t)
    client.sendText(t)
    inputText = ''
    _scrollToBottom()
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendText() }
  }

  function toggleMic() {
    if (particleState === 'listening') {
      client.stopMic()
    } else {
      client.startMic()
    }
  }

  function approve() { client.approve(); setPreview(null) }
  function cancel()  { client.cancel();  setPreview(null) }
</script>

<div style="
  position:fixed;
  bottom:24px;
  left:24px;
  z-index:20;
  width:340px;
  max-height:480px;
  background:rgba(6,10,15,0.75);
  backdrop-filter:blur(12px);
  border:1px solid rgba(255,255,255,0.08);
  border-radius:12px;
  display:flex;
  flex-direction:column;
  overflow:hidden;
  transition:max-height 200ms ease, opacity 200ms ease;
  {collapsed ? 'max-height:48px;' : ''}
">
  <!-- Header -->
  <div
    onclick={() => collapsed = !collapsed}
    style="
      display:flex;align-items:center;justify-content:space-between;
      padding:12px 14px;cursor:pointer;flex-shrink:0;
      border-bottom:1px solid {collapsed ? 'transparent' : 'rgba(255,255,255,0.05)'};
    "
  >
    <span style="font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:2px;color:rgba(99,179,255,0.7);text-transform:uppercase;">
      💬 chat
    </span>
    <StatusBadge state={particleState} />
  </div>

  {#if !collapsed}
    <!-- Transcript -->
    <div
      bind:this={transcriptEl}
      style="
        flex:1;overflow-y:auto;padding:12px 14px;
        display:flex;flex-direction:column;gap:8px;
        scrollbar-width:thin;scrollbar-color:rgba(255,255,255,0.1) transparent;
      "
    >
      {#each chatState.messages as msg (msg.id)}
        <div style="
          display:flex;
          flex-direction:column;
          align-items:{msg.role === 'user' ? 'flex-end' : 'flex-start'};
        ">
          <div style="
            max-width:85%;
            background:{msg.role === 'user' ? 'rgba(150,80,255,0.1)' : 'rgba(99,179,255,0.07)'};
            border:1px solid {msg.role === 'user' ? 'rgba(150,80,255,0.2)' : 'rgba(99,179,255,0.15)'};
            border-radius:8px;
            padding:7px 10px;
            font-family:Inter,sans-serif;
            font-size:13px;
            color:rgba(255,255,255,0.82);
            line-height:1.5;
            white-space:pre-wrap;word-break:break-word;
          ">
            {msg.text}
          </div>
        </div>
      {/each}

      {#if chatState.interim}
        <div style="
          font-size:12px;color:rgba(255,255,255,0.3);
          font-style:italic;padding:4px 2px;
        ">{chatState.interim}…</div>
      {/if}
    </div>

    <!-- Preview card -->
    {#if chatState.preview}
      <div style="
        margin:0 14px 10px;
        background:rgba(255,200,80,0.05);
        border:1px solid rgba(255,200,80,0.2);
        border-radius:8px;padding:10px;
      ">
        <div style="font-family:'JetBrains Mono',monospace;font-size:9px;letter-spacing:1px;color:rgba(255,200,80,0.6);margin-bottom:6px;">
          ⚡ CLAUDE CODE — CONFIRMAR?
        </div>
        <div style="font-size:12px;color:rgba(255,255,255,0.6);margin-bottom:8px;white-space:pre-wrap;">{chatState.preview}</div>
        <div style="display:flex;gap:6px;">
          <button
            onclick={approve}
            style="flex:1;padding:5px;border-radius:5px;border:1px solid rgba(150,255,180,0.3);background:rgba(150,255,180,0.08);color:rgba(150,255,180,0.8);font-size:11px;cursor:pointer;font-family:'JetBrains Mono',monospace;"
          >✓ ENVIAR</button>
          <button
            onclick={cancel}
            style="flex:1;padding:5px;border-radius:5px;border:1px solid rgba(255,100,80,0.3);background:rgba(255,100,80,0.06);color:rgba(255,100,80,0.7);font-size:11px;cursor:pointer;font-family:'JetBrains Mono',monospace;"
          >✕ CANCELAR</button>
        </div>
      </div>
    {/if}

    <!-- Input dock -->
    <div style="
      padding:10px 12px;
      display:flex;gap:6px;align-items:center;
      border-top:1px solid rgba(255,255,255,0.05);flex-shrink:0;
    ">
      <input
        bind:value={inputText}
        onkeydown={onKeydown}
        placeholder="mensagem…"
        style="
          flex:1;background:rgba(255,255,255,0.03);
          border:1px solid rgba(255,255,255,0.08);
          border-radius:6px;padding:7px 10px;
          color:rgba(255,255,255,0.8);
          font-family:Inter,sans-serif;font-size:13px;
          outline:none;
        "
      />
      <button
        onclick={toggleMic}
        title={particleState === 'listening' ? 'Parar microfone' : 'Iniciar microfone'}
        style="
          width:32px;height:32px;border-radius:50%;
          border:1px solid {particleState === 'listening' ? 'rgba(150,255,180,0.5)' : 'rgba(255,255,255,0.12)'};
          background:{particleState === 'listening' ? 'rgba(150,255,180,0.12)' : 'rgba(255,255,255,0.04)'};
          color:rgba(255,255,255,0.6);font-size:13px;cursor:pointer;
          display:flex;align-items:center;justify-content:center;
        "
      >🎤</button>
      <button
        onclick={sendText}
        style="
          width:32px;height:32px;border-radius:50%;
          border:1px solid rgba(99,179,255,0.3);
          background:rgba(99,179,255,0.1);
          color:rgba(99,179,255,0.8);font-size:13px;cursor:pointer;
          display:flex;align-items:center;justify-content:center;
        "
      >↑</button>
    </div>
  {/if}
</div>
