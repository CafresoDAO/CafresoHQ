<script>
  import { ociPost, EndpointError } from '$lib/api/ociClient.js';
  import { isAuthenticated } from '$lib/stores/auth.js';
  import { endpointReady, endpointUrl } from '$lib/stores/endpoint.js';

  /** @type {{ role: 'user'|'assistant'|'error', content: string }[]} */
  let messages = [];
  let input = '';
  let sending = false;

  async function send() {
    const text = input.trim();
    if (!text || sending) return;
    messages = [...messages, { role: 'user', content: text }];
    input = '';
    sending = true;
    try {
      // Hit the container's Anthropic proxy. serve.py routes /api/anthropic/v1/messages
      // to api.anthropic.com using the user's stored API key.
      const body = {
        model: 'claude-sonnet-4-5',
        max_tokens: 1024,
        messages: messages.filter((m) => m.role !== 'error').map((m) => ({
          role: m.role, content: m.content
        }))
      };
      const resp = await ociPost('/api/anthropic/v1/messages', body, { timeoutMs: 60000 });
      // Anthropic returns content blocks; concatenate text blocks
      const reply = (resp?.content || [])
        .filter((b) => b.type === 'text')
        .map((b) => b.text)
        .join('\n') || '(no text in response)';
      messages = [...messages, { role: 'assistant', content: reply }];
    } catch (err) {
      const detail = err instanceof EndpointError && err.body
        ? `${err.message}: ${err.body}`
        : String(err.message || err);
      messages = [...messages, { role: 'error', content: detail }];
    } finally {
      sending = false;
    }
  }

  function onKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  }
</script>

<section class="space-y-4">
  <header class="space-y-1">
    <h1 class="text-2xl font-semibold tracking-tight">Chat</h1>
    <p class="text-sm text-ink-400">
      Messages route through your private container's Anthropic proxy at
      <code class="font-mono text-brand-300">{$endpointUrl || '(no endpoint)'}</code>.
    </p>
  </header>

  {#if !$isAuthenticated}
    <div class="card p-5 text-sm text-ink-200">
      Sign in to start a chat. Your messages will be scoped to your ecosystem principal.
    </div>
  {:else if !$endpointReady}
    <div class="card p-5 text-sm text-ink-200">
      Configure a working endpoint in <a href="/settings" class="text-brand-400 underline">Settings</a> first.
    </div>
  {:else}
    <div class="card p-0 flex flex-col" style="min-height: 60vh;">
      <!-- transcript -->
      <div class="flex-1 space-y-3 overflow-y-auto p-5">
        {#if messages.length === 0}
          <div class="text-center text-sm text-ink-400 py-12">
            No messages yet. Say hi to Claude.
          </div>
        {/if}
        {#each messages as m, i (i)}
          <div class="flex {m.role === 'user' ? 'justify-end' : 'justify-start'}">
            <div class="max-w-[80%] rounded-2xl px-4 py-2.5 text-sm
                        {m.role === 'user'
                          ? 'bg-brand-500 text-ink-900'
                          : m.role === 'error'
                            ? 'bg-rose-500/15 text-rose-200 border border-rose-500/30'
                            : 'bg-ink-800/60 text-ink-50 border border-ink-600/40'}">
              <div class="whitespace-pre-wrap">{m.content}</div>
            </div>
          </div>
        {/each}
        {#if sending}
          <div class="flex justify-start">
            <div class="rounded-2xl bg-ink-800/60 border border-ink-600/40
                        px-4 py-2.5 text-sm text-ink-200 animate-pulse">
              Claude is thinking…
            </div>
          </div>
        {/if}
      </div>

      <!-- input -->
      <div class="border-t border-ink-600/30 p-4">
        <div class="flex gap-2">
          <textarea class="input flex-1 resize-none font-sans"
                    rows="1"
                    placeholder="Ask anything…"
                    bind:value={input}
                    on:keydown={onKey}
                    disabled={sending}></textarea>
          <button class="btn-primary" on:click={send}
                  disabled={!input.trim() || sending}>
            Send
          </button>
        </div>
        <div class="mt-1.5 text-xs text-ink-400">
          ⏎ to send · Shift+⏎ for newline
        </div>
      </div>
    </div>
  {/if}
</section>
