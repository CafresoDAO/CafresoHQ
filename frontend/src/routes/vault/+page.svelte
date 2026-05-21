<script>
  import { onMount, onDestroy } from 'svelte';
  import {
    vaultState,
    vaultError,
    vaultFiles,
    vaultUnlocked,
    unlockVault,
    lockVault,
    createFile,
    readFile,
    updateFile,
    renameFile,
    deleteFile,
    uploadFiles,
    triggerDownload,
    downloadFileBlob
  } from '$lib/stores/vault.js';
  import { isAuthenticated, principalText } from '$lib/stores/auth.js';
  import { endpointReady } from '$lib/stores/endpoint.js';

  let selected = null;
  let editorContent = '';
  let editorDirty = false;
  let saving = false;
  let savedAt = null;
  let opening = false;
  let creatingName = '';

  let dragOver = false;
  let uploading = false;
  let uploadProgress = '';
  let uploadCount = 0;
  let uploadDone = 0;
  let uploadFailed = [];
  let fileInput;

  let previewUrl = null;
  let previewType = '';
  $: if (!selected || !selected.isBinary) {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      previewUrl = null;
      previewType = '';
    }
  }

  let autosaveTimer = null;
  function scheduleAutosave() {
    editorDirty = true;
    clearTimeout(autosaveTimer);
    autosaveTimer = setTimeout(() => doSave(), 800);
  }

  async function doSave() {
    if (!selected || !editorDirty || saving) return;
    saving = true;
    try {
      await updateFile(selected.id, editorContent);
      editorDirty = false;
      savedAt = new Date();
    } catch (e) {
      alert('Save failed: ' + (e?.message || e));
    } finally {
      saving = false;
    }
  }

  async function openFile(f) {
    if (editorDirty) await doSave();
    selected = f;
    opening = true;
    editorDirty = false;
    editorContent = '';
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      previewUrl = null;
      previewType = '';
    }
    try {
      if (f.isBinary) {
        const blob = await downloadFileBlob(f.id);
        previewUrl = URL.createObjectURL(blob);
        previewType = (f.mimeType || '').toLowerCase();
      } else {
        editorContent = await readFile(f.id);
      }
    } catch (e) {
      alert('Open failed: ' + (e?.message || e));
      selected = null;
    } finally {
      opening = false;
    }
  }

  async function handleUpload(filesList) {
    if (!filesList || !filesList.length) return;
    uploading = true;
    uploadCount = filesList.length;
    uploadDone = 0;
    uploadFailed = [];
    uploadProgress = `0 of ${uploadCount}`;
    try {
      const result = await uploadFiles(filesList, {
        onProgress: ({ phase, file }) => {
          if (phase === 'done') uploadDone += 1;
          uploadProgress = `${uploadDone} of ${uploadCount} - ${phase}: ${file}`;
        }
      });
      uploadFailed = result.failed;
      if (result.failed.length) {
        const msg = result.failed.map((f) => `- ${f.name}: ${f.error}`).join('\n');
        alert(`Some files failed:\n\n${msg}`);
      }
    } catch (e) {
      alert('Upload error: ' + (e?.message || e));
    } finally {
      uploading = false;
      uploadProgress = '';
      if (fileInput) fileInput.value = '';
    }
  }

  function onDrop(e) {
    dragOver = false;
    if (e.dataTransfer?.files?.length) handleUpload(e.dataTransfer.files);
  }
  function onDragOver(e) {
    e.preventDefault();
    dragOver = true;
  }
  function onDragLeave() {
    dragOver = false;
  }
  function onPickFiles() {
    fileInput?.click();
  }

  function onFileInputChange(e) {
    if (e.currentTarget instanceof HTMLInputElement) {
      handleUpload(e.currentTarget.files);
    }
  }

  function fmtMime(m) {
    if (!m) return '';
    if (m.length > 28) return m.slice(0, 26) + '...';
    return m;
  }

  async function newFile() {
    const name = (creatingName || '').trim();
    if (!name) return;
    try {
      const meta = await createFile(name, '# ' + name + '\n\n');
      creatingName = '';
      await openFile(meta);
    } catch (e) {
      alert('Create failed: ' + (e?.message || e));
    }
  }

  async function rename() {
    if (!selected) return;
    const next = prompt('Rename to:', selected.name);
    if (!next || next === selected.name) return;
    try {
      await renameFile(selected.id, next);
      selected = { ...selected, name: next };
    } catch (e) {
      alert('Rename failed: ' + (e?.message || e));
    }
  }

  async function remove() {
    if (!selected) return;
    if (!confirm(`Delete "${selected.name}" permanently?\n\nThe encrypted blob will be removed from your container. There is no server-side recovery.`)) return;
    try {
      await deleteFile(selected.id);
      selected = null;
      editorContent = '';
    } catch (e) {
      alert('Delete failed: ' + (e?.message || e));
    }
  }

  function fmtSize(b) {
    if (b == null) return '';
    if (b < 1024) return `${b} B`;
    if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
    return `${(b / 1024 / 1024).toFixed(1)} MB`;
  }
  function fmtRel(ms) {
    if (!ms) return '';
    const s = Math.floor((Date.now() - ms) / 1000);
    if (s < 60) return `${s}s ago`;
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    return `${Math.floor(s / 86400)}d ago`;
  }

  $: if ($isAuthenticated && $endpointReady && $vaultState === 'idle') {
    unlockVault();
  }

  onMount(() => {});
  onDestroy(() => clearTimeout(autosaveTimer));
</script>

<section class="space-y-5">
  <header class="card p-6 sm:p-8">
    <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <div class="page-kicker">Crypto / vetKeys / BLS12-381</div>
        <h1 class="page-title mt-4">Vault<span class="text-brand-500">.</span></h1>
        <p class="mt-4 max-w-2xl text-sm leading-6 text-ink-300">
          End-to-end encrypted files of any type. Keys are derived from your
          Internet Identity via ICP vetKeys.
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <span class="pill-ok">Zero knowledge</span>
        {#if $vaultUnlocked}
          <span class="text-xs text-ink-400">{$vaultFiles.length} file{$vaultFiles.length === 1 ? '' : 's'}</span>
          <button class="btn-ghost btn-sm" on:click={lockVault} title="Forget the master key in this session">
            Lock
          </button>
        {/if}
      </div>
    </div>
  </header>

  {#if !$isAuthenticated}
    <div class="card p-6 text-sm leading-6 text-ink-300">
      Sign in with Internet Identity to derive your vault key. Your principal is
      the only thing that can decrypt your files, so keep your II anchor safe.
    </div>
  {:else if !$endpointReady}
    <div class="card p-6 text-sm leading-6 text-ink-300">
      Provision your container first. Encrypted blobs are stored there; this app
      only holds keys derived fresh per session via vetKeys.
      <a href="/" class="btn-primary btn-sm mt-4">Go to dashboard</a>
    </div>
  {:else if $vaultState === 'unlocking'}
    <div class="card flex items-center gap-3 p-6 text-sm text-ink-300">
      <span class="glow-dot text-brand-400 animate-pulse"></span>
      <div>
        <div class="font-semibold text-ink-50">Deriving your vault key...</div>
        <div class="mt-0.5 text-xs text-ink-400">
          Threshold-decrypting via ICP vetKeys. The first time per session takes about 2 seconds.
        </div>
      </div>
    </div>
  {:else if $vaultState === 'error'}
    <div class="card space-y-3 p-6">
      <div class="text-sm font-semibold text-rose-700 dark:text-rose-300">Couldn't unlock vault</div>
      <pre class="whitespace-pre-wrap font-mono text-xs text-rose-700 dark:text-rose-200">{$vaultError}</pre>
      <div class="flex gap-2">
        <button class="btn-primary btn-sm" on:click={unlockVault}>Retry</button>
        <a href="/settings" class="btn-ghost btn-sm">Check settings</a>
      </div>
    </div>
  {:else if $vaultState === 'locked'}
    <div class="card space-y-3 p-6">
      <div class="text-sm leading-6 text-ink-300">
        Vault is locked. Your encrypted files remain on your container, untouched.
      </div>
      <button class="btn-primary btn-sm" on:click={unlockVault}>Unlock vault</button>
    </div>
  {:else}
    <div class="grid gap-4 lg:grid-cols-[20rem_1fr]">
      <div
        class="card max-h-[78vh] space-y-3 overflow-y-auto p-3"
        on:dragover={onDragOver}
        on:dragleave={onDragLeave}
        on:drop|preventDefault={onDrop}
        role="region"
        aria-label="Vault files"
      >
        <form class="flex gap-2" on:submit|preventDefault={newFile}>
          <input
            class="input flex-1 text-sm"
            placeholder="New note name..."
            bind:value={creatingName}
            autocomplete="off"
            spellcheck="false"
          />
          <button class="btn-primary btn-sm" type="submit" disabled={!creatingName.trim()}>
            Add
          </button>
        </form>

        <div class="flex items-center gap-2">
          <input
            type="file"
            multiple
            class="hidden"
            bind:this={fileInput}
            on:change={onFileInputChange}
          />
          <button class="btn-ghost btn-sm flex-1" on:click={onPickFiles} disabled={uploading}>
            {uploading ? 'Encrypting...' : 'Upload files'}
          </button>
        </div>

        {#if dragOver}
          <div class="rounded-xl border-2 border-dashed border-brand-500/60 bg-brand-500/10 p-4 text-center text-sm text-brand-700 dark:text-brand-300">
            Drop files to encrypt and upload
          </div>
        {:else if uploading}
          <div class="rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-200">
            <div class="flex items-center gap-2">
              <span class="glow-dot text-amber-400 animate-pulse"></span>
              <span class="truncate">{uploadProgress}</span>
            </div>
          </div>
        {/if}

        {#if $vaultFiles.length === 0}
          <div class="px-2 py-6 text-center text-sm text-ink-400">
            No files yet.<br />
            <span class="text-xs">Create a note or upload any file. Encryption happens before it leaves your browser.</span>
          </div>
        {:else}
          <ul class="space-y-1">
            {#each $vaultFiles as f (f.id)}
              <li>
                <button
                  on:click={() => openFile(f)}
                  class="w-full rounded-xl border px-3 py-2 text-left transition-colors
                         {selected?.id === f.id
                           ? 'border-brand-500/50 bg-brand-500/15'
                           : 'border-transparent hover:border-ink-600/60 hover:bg-ink-800/50'}"
                >
                  <div class="truncate text-sm font-semibold">{f.name}</div>
                  <div class="mt-1 flex justify-between gap-2 text-xs text-ink-400">
                    <span>{fmtSize(f.size)}</span>
                    <span>{fmtRel(f.updatedAt)}</span>
                  </div>
                </button>
              </li>
            {/each}
          </ul>
        {/if}
      </div>

      <div class="card flex min-h-[78vh] flex-col overflow-hidden p-0">
        {#if !selected}
          <div class="m-auto p-6 text-center text-sm text-ink-400">
            Select a note to view, or create a new one.
          </div>
        {:else if opening}
          <div class="m-auto flex items-center gap-2 p-6 text-sm text-ink-400">
            <span class="glow-dot text-brand-400 animate-pulse"></span>
            Decrypting...
          </div>
        {:else}
          <div class="flex items-center justify-between gap-3 border-b border-ink-600/60 px-4 py-3">
            <div class="min-w-0">
              <div class="truncate text-sm font-semibold">{selected.name}</div>
              <div class="truncate font-mono text-xs text-ink-400">
                id {selected.id}
                {#if selected.isBinary}
                  / {fmtMime(selected.mimeType)} / {fmtSize(selected.size)}
                {/if}
              </div>
            </div>
            <div class="flex shrink-0 flex-wrap items-center justify-end gap-2">
              {#if !selected.isBinary && saving}
                <span class="text-xs text-ink-400"><span class="animate-pulse">Encrypting...</span></span>
              {:else if !selected.isBinary && editorDirty}
                <span class="text-xs text-amber-600 dark:text-amber-400">Unsaved</span>
              {:else if !selected.isBinary && savedAt}
                <span class="text-xs text-emerald-600 dark:text-emerald-400" title={savedAt.toLocaleString()}>
                  Saved
                </span>
              {/if}
              {#if selected.isBinary}
                <button class="btn-primary btn-sm" on:click={() => triggerDownload(selected.id)}>
                  Download
                </button>
              {/if}
              <button class="btn-ghost btn-sm" on:click={rename}>Rename</button>
              <button class="btn-ghost btn-sm text-rose-700 hover:text-rose-800 dark:text-rose-300 dark:hover:text-rose-200" on:click={remove}>
                Delete
              </button>
            </div>
          </div>

          {#if selected.isBinary}
            <div class="flex-1 overflow-auto bg-ink-900/35">
              {#if previewType.startsWith('image/') && previewUrl}
                <div class="grid place-items-center p-6">
                  <img src={previewUrl} alt={selected.name} class="max-h-[68vh] max-w-full rounded-xl border border-ink-600/60 shadow-lg" />
                </div>
              {:else if previewType.startsWith('video/') && previewUrl}
                <div class="grid h-full place-items-center p-4">
                  <!-- svelte-ignore a11y-media-has-caption -->
                  <video src={previewUrl} controls class="max-h-[68vh] max-w-full rounded-xl border border-ink-600/60 shadow-lg" style="outline: none;"></video>
                </div>
              {:else if previewType.startsWith('audio/') && previewUrl}
                <div class="grid place-items-center p-12">
                  <div class="w-full max-w-sm space-y-4 text-center">
                    <div class="text-sm font-semibold uppercase tracking-[0.22em] text-ink-400">Audio</div>
                    <div class="truncate text-sm font-semibold">{selected.name}</div>
                    <audio src={previewUrl} controls class="w-full" style="outline: none;"></audio>
                  </div>
                </div>
              {:else if previewType === 'application/pdf' && previewUrl}
                <iframe src={previewUrl} title={selected.name} class="block h-full w-full border-0 bg-ink-900" style="min-height: 70vh;"></iframe>
              {:else if (previewType.startsWith('text/') || previewType === 'application/json') && previewUrl}
                <iframe src={previewUrl} title={selected.name} class="block h-full w-full border-0 bg-ink-900" style="min-height: 60vh;"></iframe>
              {:else}
                <div class="grid place-items-center p-12 text-center">
                  <div class="max-w-md space-y-3">
                    <div class="page-kicker">File Preview</div>
                    <div class="text-base font-semibold">{selected.name}</div>
                    <div class="font-mono text-xs text-ink-400">
                      {fmtMime(selected.mimeType)} / {fmtSize(selected.size)}
                    </div>
                    <p class="text-sm leading-6 text-ink-300">
                      Inline preview is not supported for this file type. Download to view it
                      on your device; decryption happens in your browser before download completes.
                    </p>
                    <button class="btn-primary" on:click={() => triggerDownload(selected.id)}>
                      Download {selected.name}
                    </button>
                  </div>
                </div>
              {/if}
            </div>
          {:else}
            <textarea
              class="flex-1 w-full resize-none bg-transparent p-4 font-mono text-sm text-ink-100 focus:outline-none focus:ring-0"
              spellcheck="false"
              bind:value={editorContent}
              on:input={scheduleAutosave}
              placeholder="# Start writing...
Encrypted client-side before each save."
            ></textarea>
          {/if}
        {/if}
      </div>
    </div>

    <div class="card-quiet px-4 py-3 text-xs leading-5 text-ink-400">
      <span class="font-semibold text-ink-200">Zero-knowledge guarantee:</span>
      Your master key is derived per session via threshold cryptography on ICP. All
      files and names are encrypted with AES-GCM in your browser before leaving your device.
      Any file type up to 200 MB. If you lose your Internet Identity, the data cannot
      be recovered. <span class="font-mono">{$principalText.slice(0, 12)}...</span>
    </div>
  {/if}
</section>
