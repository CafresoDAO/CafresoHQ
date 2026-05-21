<script>
  /** Modal form for onboarding a custom VM / remote endpoint. */
  export let onSubmit  = (/** @type {any} */ _data) => {};
  export let onCancel  = () => {};
  export let submitting = false;
  export let error      = '';

  let name     = '';
  let host     = '';
  let port     = 47989;
  let protocol = 'webrtc';
  let icon     = 'monitor';
  let desc     = '';

  const protocols = [
    { value: 'webrtc',    label: 'WebRTC (Sunshine / Selkies)' },
    { value: 'websocket', label: 'WebSocket (noVNC / KasmVNC)' },
    { value: 'rdp',       label: 'RDP (Remote Desktop)' },
    { value: 'iframe',    label: 'Iframe (Web UI)' },
  ];

  const icons = [
    { value: 'monitor',  label: 'Desktop Monitor' },
    { value: 'linux',    label: 'Linux' },
    { value: 'terminal', label: 'Terminal' },
    { value: 'gamepad',  label: 'Gamepad' },
    { value: 'code',     label: 'Code Editor' },
    { value: 'globe',    label: 'Web / Globe' },
    { value: 'shield',   label: 'Shield' },
  ];

  function handleSubmit() {
    if (!name.trim() || !host.trim()) return;
    onSubmit({ name, host, port, protocol, icon, description: desc });
  }

  function handleKeydown(e) {
    if (e.key === 'Escape') onCancel();
  }
</script>

<svelte:window on:keydown={handleKeydown} />

<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions a11y_interactive_supports_focus -->
<div class="fixed inset-0 z-50 grid place-items-center bg-black/60 backdrop-blur-sm" role="dialog" on:click|self={onCancel}>
  <div class="card w-full max-w-md p-6 space-y-5 shadow-2xl">
    <div>
      <div class="page-kicker">Bring Your Own</div>
      <h2 class="text-xl font-semibold text-ink-50 mt-1">Register a VM or Endpoint</h2>
      <p class="text-sm text-ink-300 mt-1">
        Connect any machine running Sunshine, noVNC, or a web-based interface.
      </p>
    </div>

    <form on:submit|preventDefault={handleSubmit} class="space-y-4">
      <div>
        <label for="vm-name" class="text-xs font-semibold uppercase tracking-wide text-ink-300">
          Display Name
        </label>
        <input
          id="vm-name"
          class="input mt-1"
          type="text"
          placeholder="My Windows PC"
          bind:value={name}
          required
        />
      </div>

      <div class="grid grid-cols-3 gap-3">
        <div class="col-span-2">
          <label for="vm-host" class="text-xs font-semibold uppercase tracking-wide text-ink-300">
            Host / IP Address
          </label>
          <input
            id="vm-host"
            class="input mt-1"
            type="text"
            placeholder="192.168.1.100 or my-pc.local"
            bind:value={host}
            required
          />
        </div>
        <div>
          <label for="vm-port" class="text-xs font-semibold uppercase tracking-wide text-ink-300">
            Port
          </label>
          <input
            id="vm-port"
            class="input mt-1"
            type="number"
            min="1"
            max="65535"
            bind:value={port}
          />
        </div>
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label for="vm-protocol" class="text-xs font-semibold uppercase tracking-wide text-ink-300">
            Protocol
          </label>
          <select id="vm-protocol" class="input mt-1" bind:value={protocol}>
            {#each protocols as p}
              <option value={p.value}>{p.label}</option>
            {/each}
          </select>
        </div>
        <div>
          <label for="vm-icon" class="text-xs font-semibold uppercase tracking-wide text-ink-300">
            Icon
          </label>
          <select id="vm-icon" class="input mt-1" bind:value={icon}>
            {#each icons as ic}
              <option value={ic.value}>{ic.label}</option>
            {/each}
          </select>
        </div>
      </div>

      <div>
        <label for="vm-desc" class="text-xs font-semibold uppercase tracking-wide text-ink-300">
          Description <span class="text-ink-500 normal-case">(optional)</span>
        </label>
        <input
          id="vm-desc"
          class="input mt-1"
          type="text"
          placeholder="My home lab Windows 11 machine"
          bind:value={desc}
        />
      </div>

      {#if error}
        <div class="rounded-lg bg-rose-500/15 border border-rose-500/30 px-3 py-2 text-sm text-rose-300">
          {error}
        </div>
      {/if}

      <div class="flex items-center gap-3 pt-1">
        <button
          type="submit"
          class="btn-primary flex-1"
          disabled={submitting || !name.trim() || !host.trim()}
        >
          {#if submitting}
            <span class="animate-pulse">Registering...</span>
          {:else}
            Register VM
          {/if}
        </button>
        <button type="button" class="btn-ghost" on:click={onCancel}>
          Cancel
        </button>
      </div>
    </form>

    <p class="text-[10px] text-ink-500 leading-relaxed">
      Your VM must be reachable from this gateway. For Sunshine-based streaming,
      install <a href="https://github.com/LizardByte/Sunshine" class="text-brand-500 hover:underline" target="_blank" rel="noopener">Sunshine</a> on the target machine and ensure port {port} is open.
    </p>
  </div>
</div>
