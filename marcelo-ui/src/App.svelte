<script lang="ts">
  import ParticleCanvas    from './components/ParticleCanvas.svelte'
  import WebcamView        from './components/WebcamView.svelte'
  import ChatOverlay       from './components/ChatOverlay.svelte'
  import ProjectsOverlay   from './components/ProjectsOverlay.svelte'
  import GestureHUD        from './components/GestureHUD.svelte'
  import ConfigOverlay     from './components/config/ConfigOverlay.svelte'
  import { openConfig }    from './stores/config.svelte'
</script>

<ParticleCanvas />
<WebcamView />
<GestureHUD />
<ChatOverlay />
<ProjectsOverlay />
<ConfigOverlay />

<button onclick={openConfig}
        style="position:fixed;left:16px;bottom:16px;z-index:20;width:40px;height:40px;border-radius:50%;
               background:#11161d;color:#cdd9e5;border:1px solid #2a3a4a;cursor:pointer;font-size:18px;">⚙</button>
