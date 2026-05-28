<script lang="ts">
  import { configState, closeConfig } from '../../stores/config.svelte'
  import GestureList from './GestureList.svelte'
  import WizardRecord from './WizardRecord.svelte'
  import WizardCompose from './WizardCompose.svelte'
  import WizardBind from './WizardBind.svelte'
</script>

{#if configState.open}
  <div style="position:fixed;inset:0;z-index:50;display:flex;align-items:center;justify-content:center;
              background:rgba(3,6,10,0.7);backdrop-filter:blur(4px);">
    <div style="width:480px;max-height:80vh;overflow:auto;background:#0b1016;
                border:1px solid #2a3a4a;border-radius:14px;position:relative;">
      <button onclick={closeConfig}
              style="position:absolute;right:12px;top:12px;background:none;border:none;color:#8899aa;cursor:pointer;">✕</button>
      {#if configState.screen === 'list'}<GestureList />
      {:else if configState.screen === 'record'}<WizardRecord />
      {:else if configState.screen === 'compose'}<WizardCompose />
      {:else if configState.screen === 'bind'}<WizardBind />
      {/if}
    </div>
  </div>
{/if}
