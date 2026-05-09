<script>
  import { onMount, onDestroy } from 'svelte';
  import {
    vaultState, vaultError, vaultFiles, vaultUnlocked,
    unlockVault, lockVault,
    createFile, readFile, updateFile, renameFile, deleteFile,
    uploadFiles, triggerDownload, downloadFileBlob,
  } from '$lib/stores/vault.js';
  import { isAuthenticated, principalText } from '$lib/stores/auth.js';
  import { endpointReady } from '$lib/stores/endpoint.js';

  let selected      = null;     // metadata of currently open file
  let editorContent = '';
  let editorDirty   = false;
  let saving        = false;
  let savedAt       = null;     // last successful autosave timestamp
  let opening       = false;    // loading file content
  let creatingName  = '';

  // Upload state
  let dragOver        = false;
  let uploading       = false;
  let uploadProgress  = '';   // current phase string from onProgress
  let uploadCount     = 0;    // files queued in current batch
  let uploadDone      = 0;    // files completed in current batch
  let uploadFailed    = [];   // [{name, error}]
  let fileInput;              // <input type=file> ref

  // Binary preview state — when an image/PDF is selected, we object-URL it
  let previewUrl = null;
  let previewType = '';
  $: if (!selected || !selected.isBinary) {
    if (previewUrl) { URL.revokeObjectURL(previewUrl); previewUrl = null; previewType = ''; }
  }

  // Autosave (debounced) — preserves edits without an explicit Save button.
  let _autosaveTimer = null;
  function scheduleAutosave() {
    editorDirty = true;
    clearTimeout(_autosaveTimer);
    _autosaveTimer = setTimeout(() => doSave(), 800);
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
    } finally { saving = false; }
  }

  async function openFile(f) {
    if (editorDirty) await doSave();
    selected = f;
    opening = true;
    editorDirty = false;
    editorContent = '';
    if (previewUrl) { URL.revokeObjectURL(previewUrl); previewUrl = null; previewType = ''; }
    try {
      if (f.isBinary) {
        // Binary file: build an object URL for inline preview
        const blob = await downloadFileBlob(f.id);
        previewUrl  = URL.createObjectURL(blob);
        previewType = (f.mimeType || '').toLowerCase();
      } else {
        // Text/Markdown note: load into the editor
        editorContent = await readFile(f.id);
      }
    } catch (e) {
      alert('Open failed: ' + (e?.message || e));
      selected = null;
    } finally { opening = false; }
  }

  async function handleUpload(filesList) {
    if (!filesList || !filesList.length) return;
    uploading = true;
    uploadCount = filesList.length;
    uploadDone  = 0;
    uploadFailed = [];
    uploadProgress = `0 of ${uploadCount}`;
    try {
      const result = await uploadFiles(filesList, {
        onProgress: ({ phase, file }) => {
          if (phase === 'done') uploadDone += 1;
          uploadProgress = `${uploadDone} of ${uploadCount} — ${phase}: ${file}`;
        },
      });
      uploadFailed = result.failed;
      if (result.failed.length) {
        const msg = result.failed.map((f) => `• ${f.name}: ${f.error}`).join('\n');
        alert(`Some files failed:\n\n${msg}`);
      }
    } catch (e) {
      alert('Upload error: ' + (e?.message || e));
    } finally {
      uploading = false;
      uploadProgress = '';
      // Clear the file input so the same file can be re-selected
      if (fileInput) fileInput.value = '';
    }
  }

  function onDrop(e) {
    dragOver = false;
    if (e.dataTransfer?.files?.length) handleUpload(e.dataTransfer.files);
  }
  function onDragOver(e) { e.preventDefault(); dragOver = true; }
  function onDragLeave()  { dragOver = false; }
  function onPickFiles()  { fileInput?.click(); }

  function fmtMime(m) {
    if (!m) return '';
    if (m.length > 28) return m.slice(0, 26) + '…';
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
    if (!confirm(`Delete "${selected.name}" permanently?\n\nThe encrypted blob will be removed from your container — there is no server-side recovery.`)) return;
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
    if (s < 60)        return `${s}s ago`;
    if (s < 3600)      return `${Math.floor(s / 60)}m ago`;
    if (s < 86400)     return `${Math.floor(s / 3600)}h ago`;
    return `${Math.floor(s / 86400)}d ago`;
  }

  // Auto-unlock when authenticated + endpoint ready
  $: if ($isAuthenticated && $endpointReady && $vaultState === 'idle') {
    unlockVault();
  }

  onMount(() => { /* reactive `$:` above triggers unlock */ });
  onDestroy(() => clearTimeout(_autosaveTimer));
</script>

<section class="space-y-4">
  <header class="flex flex-wrap items-center justify-between gap-3">
    <div>
      <div class="flex items-center gap-2">
        <h1 class="text-2xl font-semibold tracking-tight">Vault</h1>
        <span class="pill-ok" title="Vault content is encrypted on your device with vetKeys-derived keys before being stored. No one — not Anthony, not OCI, not the ICP subnet — can read your files.">
          🔐 Zero-knowledge
        </span>
      </div>
      <p class="mt-1 text-sm text-ink-400">
        End-to-end encrypted Markdown notes. Keys derived from your Internet Identity via ICP vetKeys.
      </p>
    </div>
    <div class="flex items-center gap-2">
      {#if $vaultUnlocked}
        <span class="text-xs text-ink-400">{$vaultFiles.length} file{$vaultFiles.length === 1 ? '' : 's'}</span>
        <button class="btn-ghost btn-sm" on:click={lockVault} title="Forget the master key in this session">
          Lock
        </button>
      {/if}
    </div>
  </header>

  <!-- ── State gates ─────────────────────────────────────────────────────── -->
  {#if !$isAuthenticated}
    <div class="card p-6 text-sm text-ink-200">
      Sign in with Internet Identity to derive your vault key. Your principal
      is the only thing that can decrypt your files — keep your II anchor safe.
    </div>

  {:else if !$endpointReady}
    <div class="card p-6 text-sm text-ink-200">
      Provision your container first. Encrypted blobs are stored there; this
      app only holds the keys (which are derived fresh per session via vetKeys).
      <a href="/" class="block mt-3 btn-primary btn-sm">Go to dashboard →</a>
    </div>

  {:else if $vaultState === 'unlocking'}
    <div class="card p-6 text-sm text-ink-200 flex items-center gap-3">
      <span class="glow-dot text-brand-400 animate-pulse"></span>
      <div>
        <div class="font-medium">Deriving your vault key…</div>
        <div class="text-xs text-ink-400 mt-0.5">
          Threshold-decrypting via ICP vetKeys. Takes ~2 seconds the first time per session.
        </div>
      </div>
    </div>

  {:else if $vaultState === 'error'}
    <div class="card p-6 space-y-3">
      <div class="text-sm font-medium text-rose-300">Couldn't unlock vault</div>
      <pre class="text-xs font-mono text-rose-200 whitespace-pre-wrap">{$vaultError}</pre>
      <div class="flex gap-2">
        <button class="btn-primary btn-sm" on:click={unlockVault}>Retry</button>
        <a href="/settings" class="btn-ghost btn-sm">Check settings</a>
      </div>
    </div>

  {:else if $vaultState === 'locked'}
    <div class="card p-6 space-y-3">
      <div class="text-sm text-ink-200">
        Vault is locked. Your encrypted files remain on your container, untouched.
      </div>
      <button class="btn-primary btn-sm" on:click={unlockVault}>Unlock vault</button>
    </div>

  {:else}
    <!-- ── Unlocked: main vault UI ─────────────────────────────────────── -->
    <div class="grid gap-4 md:grid-cols-[20rem_1fr]">

      <!-- File list + upload -->
      <div class="card p-3 max-h-[78vh] overflow-y-auto space-y-3"
           on:dragover={onDragOver}
           on:dragleave={onDragLeave}
           on:drop|preventDefault={onDrop}
           role="region"
           aria-label="Vault files">
        <!-- New note -->
        <form class="flex gap-2" on:submit|preventDefault={newFile}>
          <input class="input flex-1 text-sm"
                 placeholder="New note name…"
                 bind:value={creatingName}
                 autocomplete="off" spellcheck="false" />
          <button class="btn-primary btn-sm" type="submit" disabled={!creatingName.trim()}>
            +
          </button>
        </form>

        <!-- Upload files -->
        <div class="flex items-center gap-2">
          <input type="file" multiple class="hidden"
                 bind:this={fileInput}
                 on:change={(e) => handleUpload(e.target.files)} />
          <button class="btn-ghost btn-sm flex-1" on:click={onPickFiles} disabled={uploading}>
            {uploading ? 'Encrypting…' : '⬆ Upload files'}
          </button>
        </div>

        <!-- Drag-drop hint + progress -->
        {#if dragOver}
          <div class="rounded-md border-2 border-dashed border-brand-500/60
                      bg-brand-500/10 p-4 text-center text-sm text-brand-300">
            Drop files to encrypt + upload
          </div>
        {:else if uploading}
          <div class="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
            <div class="flex items-center gap-2">
              <span class="glow-dot text-amber-400 animate-pulse"></span>
              <span class="truncate">{uploadProgress}</span>
            </div>
          </div>
        {/if}

        {#if $vaultFiles.length === 0}
          <div class="px-2 py-4 text-sm text-ink-400 text-center">
            No notes yet.<br />
            <span class="text-xs">Create one above — it'll be encrypted before leaving your browser.</span>
          </div>
        {:else}
          <ul class="space-y-1">
            {#each $vaultFiles as f (f.id)}
              <li>
                <button on:click={() => openFile(f)}
                        class="w-full text-left px-3 py-2 rounded-md transition-colors
                              {selected?.id === f.id
                                ? 'bg-brand-500/10 border border-brand-500/40'
                                : 'hover:bg-ink-800/40 border border-transparent'}">
                  <div class="text-sm font-medium truncate">{f.name}</div>
                  <div class="text-xs text-ink-400 flex justify-between">
                    <span>{fmtSize(f.size)}</span>
                    <span>{fmtRel(f.updatedAt)}</span>
                  </div>
                </button>
              </li>
            {/each}
          </ul>
        {/if}
      </div>

      <!-- Editor -->
      <div class="card p-0 min-h-[78vh] flex flex-col overflow-hidden">
        {#if !selected}
          <div class="m-auto p-6 text-center text-sm text-ink-400">
            Select a note to view, or create a new one.
          </div>
        {:else if opening}
          <div class="m-auto p-6 text-sm text-ink-400 flex items-center gap-2">
            <span class="glow-dot text-brand-400 animate-pulse"></span>
            Decrypting…
          </div>
        {:else}
          <!-- Editor header -->
          <div class="flex items-center justify-between gap-3 border-b border-ink-600/30 px-4 py-2.5">
            <div class="min-w-0">
              <div class="text-sm font-medium truncate">{selected.name}</div>
              <div class="text-xs text-ink-400 font-mono truncate">
                id {selected.id}
                {#if selected.isBinary}
                  · {fmtMime(selected.mimeType)} · {fmtSize(selected.size)}
                {/if}
              </div>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              {#if !selected.isBinary && saving}
                <span class="text-xs text-ink-400">
                  <span class="animate-pulse">Encrypting…</span>
                </span>
              {:else if !selected.isBinary && editorDirty}
                <span class="text-xs text-amber-400">Unsaved</span>
              {:else if !selected.isBinary && savedAt}
                <span class="text-xs text-emerald-400" title={savedAt.toLocaleString()}>
                  Saved
                </span>
              {/if}
              {#if selected.isBinary}
                <button class="btn-primary btn-sm" on:click={() => triggerDownload(selected.id)}>
                  ⬇ Download
                </button>
              {/if}
              <button class="btn-ghost btn-sm" on:click={rename}>Rename</button>
              <button class="btn-ghost btn-sm text-rose-300 hover:text-rose-200"
                      on:click={remove}>Delete</button>
            </div>
          </div>

          <!-- Body — text editor OR binary preview -->
          {#if selected.isBinary}
            <!-- Binary preview: image inline; PDF inline; everything else, generic file card -->
            <div class="flex-1 overflow-auto bg-ink-900/50">
              {#if previewType.startsWith('image/') && previewUrl}
                <div class="grid place-items-center p-6">
                  <img src={previewUrl} alt={selected.name}
                       class="max-h-[68vh] max-w-full rounded-md border border-ink-600/30 shadow-lg" />
                </div>
              {:else if previewType === 'application/pdf' && previewUrl}
                <iframe src={previewUrl} title={selected.name}
                        class="block h-full w-full border-0 bg-ink-900"
                        style="min-height: 70vh;"></iframe>
              {:else if (previewType.startsWith('text/') || previewType === 'application/json') && previewUrl}
                <iframe src={previewUrl} title={selected.name}
                        class="block h-full w-full border-0 bg-ink-900"
                        style="min-height: 60vh;"></iframe>
              {:else}
                <div class="grid place-items-center p-12 text-center">
                  <div class="space-y-3 max-w-md">
                    <div class="text-4xl">📦</div>
                    <div class="text-base font-medium">{selected.name}</div>
                    <div class="text-xs text-ink-400 font-mono">
                      {fmtMime(selected.mimeType)} · {fmtSize(selected.size)}
                    </div>
                    <p class="text-sm text-ink-300">
                      Inline preview not supported for this file type.
                      Download to view it on your device — decryption happens
                      in your browser before the download completes.
                    </p>
                    <button class="btn-primary" on:click={() => triggerDownload(selected.id)}>
                      ⬇ Download {selected.name}
                    </button>
                  </div>
                </div>
              {/if}
            </div>
          {:else}
            <!-- Text/Markdown editor -->
            <textarea
              class="flex-1 w-full p-4 bg-transparent text-sm font-mono text-ink-100 resize-none
                     focus:outline-none focus:ring-0"
              spellcheck="false"
              bind:value={editorContent}
              on:input={scheduleAutosave}
              placeholder="# Start writing…
Encrypted client-side before each save."></textarea>
          {/if}
        {/if}
      </div>
    </div>

    <!-- Trust footer -->
    <div class="rounded-lg border border-ink-600/30 bg-ink-900/40 px-4 py-3 text-xs text-ink-400">
      <span class="font-medium text-ink-200">Zero-knowledge guarantee:</span>
      Your master key is derived per session via threshold cryptography on ICP — no single party
      ever sees it in plaintext, including Anthony. File contents and names are encrypted with
      AES-GCM in your browser before being stored on your container. If you lose your Internet
      Identity, the data cannot be recovered. <span class="font-mono">{$principalText.slice(0, 12)}…</span>
    </div>
  {/if}
</section>
