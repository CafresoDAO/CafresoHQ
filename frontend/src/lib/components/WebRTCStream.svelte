<script>
  /**
   * WebRTC remote desktop stream component.
   * Supports two signaling backends:
   *   - Moonlight (server-sends-offer): Sunshine / moonlight-web-stream
   *   - Selkies (client-sends-offer): Selkies-GStreamer for Linux desktops
   *
   * The signaling mode is auto-detected from session.selkies_port or can be
   * forced via session.signaling_mode = 'moonlight' | 'selkies'.
   */
  import { onMount, onDestroy } from 'svelte';

  /** Session object with ip, port, stream_url, stream_protocol */
  export let session;
  /** Called when stream connects successfully */
  export let onConnected = () => {};
  /** Called on fatal error */
  export let onError = (/** @type {string} */ _msg) => {};

  /** Enable clipboard sync between browser and remote */
  export let clipboardSync = true;
  /** Enable file transfer via drag-drop */
  export let fileTransfer = true;

  let videoEl;
  let canvasEl;
  let pc = null;
  let dc = null;       // data channel for input
  let clipDc = null;   // data channel for clipboard
  let fileDc = null;   // data channel for file transfer
  let ws = null;       // signaling websocket

  let status = 'connecting';
  let stats  = { rtt: 0, bitrate: 0, fps: 0, resolution: '' };
  let statsInterval;
  let uploadProgress = null;  // { name, pct } or null

  // ── Signaling mode detection ──────────────────────────────────────────────
  // Selkies-GStreamer uses client-initiated offers with a different WS protocol.
  // Moonlight/Sunshine uses server-initiated offers.
  const signalingMode = session?.signaling_mode ||
    (session?.selkies_port ? 'selkies' : 'moonlight');

  // ── ICE configuration ─────────────────────────────────────────────────────
  const iceServers = [
    { urls: 'stun:stun.l.google.com:19302' },
    ...(session?.turn_servers || []).map((t) => ({
      urls: t.urls,
      username: t.username,
      credential: t.credential,
    })),
  ];

  // ── Signaling ─────────────────────────────────────────────────────────────

  function signalingUrl() {
    const base = session.stream_url || '';
    if (base.startsWith('wss://') || base.startsWith('ws://')) return base;
    const url = new URL(base || `https://${session.ip}:${session.port || 47989}`);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    url.pathname = url.pathname.replace(/\/$/, '') + '/ws';
    return url.toString();
  }

  function connectSignaling() {
    const url = signalingUrl();
    status = 'signaling';

    ws = new WebSocket(url);

    ws.onopen = async () => {
      status = 'negotiating';
      createPeerConnection();

      if (signalingMode === 'selkies') {
        // Selkies: client creates and sends the offer
        try {
          // Add transceiver for receiving video/audio
          pc.addTransceiver('video', { direction: 'recvonly' });
          pc.addTransceiver('audio', { direction: 'recvonly' });
          const offer = await pc.createOffer();
          await pc.setLocalDescription(offer);
          ws.send(JSON.stringify({
            type: 'offer',
            sdp: pc.localDescription.sdp,
          }));
        } catch (e) {
          status = 'error';
          onError('Failed to create Selkies offer: ' + e.message);
        }
      } else {
        // Moonlight: request the server to send an offer
        ws.send(JSON.stringify({ type: 'offer_request', codec: 'h264' }));
      }
    };

    ws.onmessage = async (event) => {
      let msg;
      try { msg = JSON.parse(event.data); } catch { return; }

      if (msg.type === 'offer') {
        // Server sent SDP offer (Moonlight pattern)
        await pc.setRemoteDescription(new RTCSessionDescription({
          type: 'offer', sdp: msg.sdp,
        }));
        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);
        ws.send(JSON.stringify({
          type: 'answer',
          sdp: pc.localDescription.sdp,
        }));
      } else if (msg.type === 'answer') {
        // Server answered our offer (Selkies pattern)
        await pc.setRemoteDescription(new RTCSessionDescription({
          type: 'answer', sdp: msg.sdp,
        }));
      } else if (msg.type === 'candidate' || msg.type === 'ice') {
        // ICE candidate from server (both protocols)
        const candidate = msg.candidate || msg;
        if (candidate.candidate) {
          try {
            await pc.addIceCandidate(new RTCIceCandidate({
              candidate: candidate.candidate,
              sdpMid: candidate.sdpMid ?? candidate.sdpMid,
              sdpMLineIndex: candidate.sdpMLineIndex ?? candidate.sdpMLineIndex,
            }));
          } catch (e) {
            console.warn('[webrtc] ICE candidate error:', e);
          }
        }
      } else if (msg.type === 'error') {
        status = 'error';
        onError(msg.message || 'Signaling error');
      }
    };

    ws.onerror = () => {
      status = 'error';
      onError('WebSocket signaling failed');
    };

    ws.onclose = () => {
      if (status !== 'error') {
        status = 'disconnected';
      }
    };
  }

  // ── Peer Connection ───────────────────────────────────────────────────────

  function createPeerConnection() {
    pc = new RTCPeerConnection({ iceServers });

    // Receive remote video/audio tracks
    pc.ontrack = (event) => {
      if (event.track.kind === 'video' && videoEl) {
        videoEl.srcObject = event.streams[0];
        status = 'streaming';
        onConnected();
      }
    };

    // ICE candidates → signaling server
    pc.onicecandidate = (event) => {
      if (event.candidate && ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'candidate',
          candidate: event.candidate.candidate,
          sdpMid: event.candidate.sdpMid,
          sdpMLineIndex: event.candidate.sdpMLineIndex,
        }));
      }
    };

    pc.oniceconnectionstatechange = () => {
      if (pc.iceConnectionState === 'connected' || pc.iceConnectionState === 'completed') {
        status = 'streaming';
      } else if (pc.iceConnectionState === 'failed') {
        status = 'error';
        onError('ICE connection failed — check network/firewall');
      } else if (pc.iceConnectionState === 'disconnected') {
        status = 'reconnecting';
        // Brief disconnects are normal; wait before erroring
        setTimeout(() => {
          if (pc?.iceConnectionState === 'disconnected') {
            status = 'error';
            onError('Connection lost');
          }
        }, 5000);
      }
    };

    // Data channel for input (keyboard, mouse) — moonlight protocol
    dc = pc.createDataChannel('input', { ordered: true });
    dc.onopen = () => console.log('[webrtc] input data channel open');
    dc.onclose = () => console.log('[webrtc] input data channel closed');

    // Clipboard sync data channel
    if (clipboardSync) {
      clipDc = pc.createDataChannel('clipboard', { ordered: true });
      clipDc.onopen = () => console.log('[webrtc] clipboard channel open');
      clipDc.onmessage = async (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'clipboard' && msg.text) {
            await navigator.clipboard.writeText(msg.text);
          }
        } catch (_) { /* clipboard write may fail without focus */ }
      };
    }

    // File transfer data channel (binary, unordered for throughput)
    if (fileTransfer) {
      fileDc = pc.createDataChannel('filetransfer', {
        ordered: true,
        maxRetransmits: 10,
      });
      fileDc.binaryType = 'arraybuffer';
      fileDc.onopen = () => console.log('[webrtc] file transfer channel open');
    }
  }

  // ── Input relay ───────────────────────────────────────────────────────────

  function sendInput(type, data) {
    if (dc?.readyState !== 'open') return;
    dc.send(JSON.stringify({ type, ...data }));
  }

  function handleKeyDown(e) {
    e.preventDefault();
    sendInput('keydown', { key: e.key, code: e.code, keyCode: e.keyCode });
  }

  function handleKeyUp(e) {
    e.preventDefault();
    sendInput('keyup', { key: e.key, code: e.code, keyCode: e.keyCode });
  }

  function relativeCoords(e) {
    if (!videoEl) return { x: 0, y: 0 };
    const rect = videoEl.getBoundingClientRect();
    return {
      x: (e.clientX - rect.left) / rect.width,
      y: (e.clientY - rect.top) / rect.height,
    };
  }

  function handleMouseMove(e) {
    sendInput('mousemove', relativeCoords(e));
  }

  function handleMouseDown(e) {
    e.preventDefault();
    videoEl?.focus();
    sendInput('mousedown', { button: e.button, ...relativeCoords(e) });
  }

  function handleMouseUp(e) {
    sendInput('mouseup', { button: e.button, ...relativeCoords(e) });
  }

  function handleWheel(e) {
    e.preventDefault();
    sendInput('wheel', { deltaX: e.deltaX, deltaY: e.deltaY, ...relativeCoords(e) });
  }

  function handleContextMenu(e) {
    e.preventDefault();
  }

  // ── Clipboard sync ────────────────────────────────────────────────────────

  async function handlePaste(e) {
    if (!clipboardSync || clipDc?.readyState !== 'open') return;
    const text = e.clipboardData?.getData('text/plain');
    if (text) {
      e.preventDefault();
      clipDc.send(JSON.stringify({ type: 'clipboard', text }));
    }
  }

  async function handleCopy(e) {
    // When user copies in the remote desktop, the remote sends clipboard
    // data over clipDc.onmessage (handled above). This handler is for
    // explicit Ctrl+C keypresses in the browser that should be forwarded.
  }

  // ── File transfer (drag & drop) ──────────────────────────────────────────

  let isDragOver = false;

  function handleDragOver(e) {
    if (!fileTransfer) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
    isDragOver = true;
  }

  function handleDragLeave(e) {
    isDragOver = false;
  }

  async function handleDrop(e) {
    e.preventDefault();
    isDragOver = false;
    if (!fileTransfer || fileDc?.readyState !== 'open') return;

    const files = e.dataTransfer?.files;
    if (!files || files.length === 0) return;

    for (const file of files) {
      await sendFile(file);
    }
  }

  async function sendFile(file) {
    if (fileDc?.readyState !== 'open') return;

    const CHUNK_SIZE = 16384;  // 16KB chunks
    const totalChunks = Math.ceil(file.size / CHUNK_SIZE);

    // Send file metadata as JSON
    fileDc.send(JSON.stringify({
      type: 'file_start',
      name: file.name,
      size: file.size,
      mime: file.type || 'application/octet-stream',
      chunks: totalChunks,
    }));

    // Read and send file in chunks
    const buffer = await file.arrayBuffer();
    let offset = 0;
    let chunkIdx = 0;

    while (offset < file.size) {
      const end = Math.min(offset + CHUNK_SIZE, file.size);
      const chunk = buffer.slice(offset, end);

      // Wait for data channel buffer to drain
      while (fileDc.bufferedAmount > 1048576) {
        await new Promise((r) => setTimeout(r, 50));
      }

      fileDc.send(chunk);
      offset = end;
      chunkIdx++;
      uploadProgress = {
        name: file.name,
        pct: Math.round((chunkIdx / totalChunks) * 100),
      };
    }

    // Send completion marker
    fileDc.send(JSON.stringify({
      type: 'file_end',
      name: file.name,
      size: file.size,
    }));

    // Clear progress after a brief delay
    setTimeout(() => { uploadProgress = null; }, 1500);
  }

  // ── Stats polling ─────────────────────────────────────────────────────────

  async function pollStats() {
    if (!pc) return;
    try {
      const report = await pc.getStats();
      report.forEach((s) => {
        if (s.type === 'inbound-rtp' && s.kind === 'video') {
          stats.fps = s.framesPerSecond || 0;
          if (s.frameWidth && s.frameHeight) {
            stats.resolution = `${s.frameWidth}x${s.frameHeight}`;
          }
          if (s.bytesReceived && s._prevBytes !== undefined) {
            const dt = (s.timestamp - s._prevTimestamp) / 1000;
            stats.bitrate = Math.round(((s.bytesReceived - s._prevBytes) * 8) / dt / 1000);
          }
          s._prevBytes = s.bytesReceived;
          s._prevTimestamp = s.timestamp;
        }
        if (s.type === 'candidate-pair' && s.state === 'succeeded') {
          stats.rtt = Math.round(s.currentRoundTripTime * 1000) || 0;
        }
      });
    } catch (_) { /* stats not critical */ }
  }

  // ── Lifecycle ─────────────────────────────────────────────────────────────

  onMount(() => {
    connectSignaling();
    statsInterval = setInterval(pollStats, 2000);
  });

  onDestroy(() => {
    clearInterval(statsInterval);
    fileDc?.close();
    clipDc?.close();
    dc?.close();
    pc?.close();
    ws?.close();
    pc = null;
    dc = null;
    clipDc = null;
    fileDc = null;
    ws = null;
  });
</script>

<!-- svelte-ignore a11y_no_static_element_interactions a11y_no_noninteractive_element_interactions -->
<div class="relative w-full h-full bg-black select-none" tabindex="-1" role="application"
  on:keydown={handleKeyDown}
  on:keyup={handleKeyUp}
  on:contextmenu={handleContextMenu}
  on:paste={handlePaste}
  on:copy={handleCopy}
  on:dragover={handleDragOver}
  on:dragleave={handleDragLeave}
  on:drop={handleDrop}
>
  {#if status === 'streaming'}
    <!-- Remote desktop video -->
    <!-- svelte-ignore a11y_media_has_caption -->
    <video
      bind:this={videoEl}
      class="w-full h-full object-contain"
      autoplay
      playsinline
      on:mousemove={handleMouseMove}
      on:mousedown={handleMouseDown}
      on:mouseup={handleMouseUp}
      on:wheel|preventDefault={handleWheel}
    ></video>

    <!-- Stats overlay (top-right) -->
    <div class="absolute top-2 right-2 flex items-center gap-2 rounded-full bg-black/60 px-2.5 py-1
                text-[10px] font-mono text-white/70 backdrop-blur-sm pointer-events-none">
      <span class="glow-dot {stats.rtt < 30 ? 'text-green-400' : stats.rtt < 80 ? 'text-yellow-400' : 'text-red-400'}"></span>
      {stats.rtt}ms
      {#if stats.fps}
        &middot; {stats.fps}fps
      {/if}
      {#if stats.bitrate}
        &middot; {stats.bitrate}kbps
      {/if}
      {#if stats.resolution}
        &middot; {stats.resolution}
      {/if}
      &middot; <span class="opacity-50">{signalingMode}</span>
    </div>

    <!-- Drag-drop overlay -->
    {#if isDragOver}
      <div class="absolute inset-0 z-20 grid place-items-center bg-brand-500/20 border-2 border-dashed border-brand-400 backdrop-blur-sm pointer-events-none">
        <div class="text-center space-y-2">
          <svg class="w-12 h-12 mx-auto text-brand-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
            <path d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
          </svg>
          <p class="text-sm font-medium text-brand-300">Drop files to transfer</p>
        </div>
      </div>
    {/if}

    <!-- File upload progress -->
    {#if uploadProgress}
      <div class="absolute bottom-4 left-1/2 -translate-x-1/2 z-20 flex items-center gap-3 rounded-full bg-ink-900/90 px-4 py-2 backdrop-blur-sm">
        <svg class="w-4 h-4 text-brand-400 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
        </svg>
        <span class="text-xs font-mono text-ink-200 max-w-[200px] truncate">{uploadProgress.name}</span>
        <span class="text-xs font-mono text-brand-400">{uploadProgress.pct}%</span>
        <div class="w-20 h-1.5 rounded-full bg-ink-700 overflow-hidden">
          <div class="h-full rounded-full bg-brand-500 transition-all" style="width: {uploadProgress.pct}%"></div>
        </div>
      </div>
    {/if}
  {:else}
    <!-- Connection states -->
    <div class="absolute inset-0 grid place-items-center">
      <div class="text-center space-y-3">
        {#if status === 'error'}
          <div class="h-12 w-12 mx-auto rounded-full bg-red-500/20 grid place-items-center">
            <svg class="w-6 h-6 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <p class="text-sm text-red-300">Connection failed</p>
          <button class="btn-ghost btn-sm" on:click={() => { status = 'connecting'; connectSignaling(); }}>
            Retry
          </button>
        {:else if status === 'disconnected'}
          <p class="text-sm text-ink-400">Disconnected</p>
          <button class="btn-ghost btn-sm" on:click={() => { status = 'connecting'; connectSignaling(); }}>
            Reconnect
          </button>
        {:else}
          <div class="h-10 w-10 mx-auto rounded-full border-2 border-brand-500 border-t-transparent animate-spin"></div>
          <p class="text-sm text-ink-300">
            {#if status === 'connecting'}
              Connecting to remote desktop...
            {:else if status === 'signaling'}
              Establishing signaling channel...
            {:else if status === 'negotiating'}
              Negotiating stream...
            {:else if status === 'reconnecting'}
              Reconnecting...
            {:else}
              {status}
            {/if}
          </p>
          <p class="text-[10px] text-ink-500">
            {session?.ip || 'unknown host'}:{session?.port || '?'}
          </p>
        {/if}
      </div>
    </div>
  {/if}
</div>
