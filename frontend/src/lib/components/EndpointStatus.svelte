<script>
  import { endpointUrl, endpointHealth } from '$lib/stores/endpoint.js';
  export let compact = false;

  $: state = $endpointHealth.state;
  $: hasUrl = !!$endpointUrl;
  $: cls    = state === 'ok'      ? 'pill-ok'
            : state === 'probing' ? 'pill-warn'
            : state === 'error'   ? 'pill-err'
            : 'pill-idle';
  $: dot    = state === 'ok'      ? 'text-emerald-400'
            : state === 'probing' ? 'text-amber-400 animate-pulse'
            : state === 'error'   ? 'text-rose-400'
            : 'text-ink-400';
  $: label  = state === 'ok'      ? (compact ? 'OCI live' : 'Container live')
            : state === 'probing' ? 'Probing…'
            : state === 'error'   ? 'Unreachable'
            : hasUrl              ? 'Idle'
                                  : 'Not configured';
</script>

{#if compact}
  <a href="/settings" class={cls} title={$endpointUrl || 'No endpoint configured'}>
    <span class="glow-dot {dot}"></span>
    <span class="hidden sm:inline">{label}</span>
  </a>
{:else}
  <div class="flex items-center gap-3">
    <span class={cls}>
      <span class="glow-dot {dot}"></span>
      {label}
    </span>
    {#if $endpointUrl}
      <code class="text-xs text-ink-400 font-mono truncate max-w-xs">{$endpointUrl}</code>
    {/if}
  </div>
{/if}
