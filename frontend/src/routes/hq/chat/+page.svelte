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
      // Route through the container's Hermes agent (the deployed default) —
      // OpenAI-compatible /hermes/v1 proxy. serve.py injects the API key.
      const body = {
        model: 'hermes-agent',
        stream: false,
        messages: messages.filter((m) => m.role !== 'error').map((m) => ({
          role: m.role,
          content: m.content
        }))
      };
      const resp = await ociPost('/hermes/v1/chat/completions', body, { timeoutMs: 120000 });
      const reply = resp?.choices?.[0]?.message?.content || '(no text in response)';
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
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }
</script>

<svelte:head>
  <title>Chat · CafresoHQ</title>
</svelte:head>

<section class="space-y-5">
  <header class="card p-6 sm:p-8">
    <div class="page-kicker">CafresoHQ / Chat</div>
    <h1 class="page-title mt-4">Chat<span class="text-brand-500">.</span></h1>
    <p class="mt-4 max-w-2xl text-sm leading-6 text-ink-300">
      Messages route through your private container's Hermes agent at
      <code class="font-mono text-brand-600 dark:text-brand-300">{$endpointUrl || '(no endpoint)'}</code>.
    </p>
  </header>

  {#if !$isAuthenticated}
    <div class="card p-5 text-sm leading-6 text-ink-300">
      Sign in to start a chat. Your messages will be scoped to your ecosystem principal.
    </div>
  {:else if !$endpointReady}
    <div class="card p-5 text-sm leading-6 text-ink-300">
      Configure a working endpoint in
      <a href="/hq/settings" class="font-semibold text-brand-600 underline dark:text-brand-300">Settings</a>
      first.
    </div>
  {:else}
    <div class="card flex min-h-[64vh] flex-col overflow-hidden p-0">
      <div class="flex-1 space-y-3 overflow-y-auto p-5">
        {#if messages.length === 0}
          <div class="grid min-h-[18rem] place-items-center text-center text-sm text-ink-400">
            <div>
              <div class="page-kicker">Ready</div>
              <p class="mt-2">No messages yet. Say hi to Hermes.</p>
            </div>
          </div>
        {/if}

        {#each messages as m, i (i)}
          <div class="flex {m.role === 'user' ? 'justify-end' : 'justify-start'}">
            <div
              class="max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-6 shadow-sm
                     {m.role === 'user'
                       ? 'bg-brand-500 text-white'
                       : m.role === 'error'
                         ? 'border border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-200'
                         : 'border border-ink-600/60 bg-ink-800/55 text-ink-50'}"
            >
              <div class="whitespace-pre-wrap">{m.content}</div>
            </div>
          </div>
        {/each}

        {#if sending}
          <div class="flex justify-start">
            <div class="rounded-2xl border border-ink-600/60 bg-ink-800/55 px-4 py-3 text-sm text-ink-300">
              <span class="animate-pulse">Hermes is thinking...</span>
            </div>
          </div>
        {/if}
      </div>

      <div class="border-t border-ink-600/60 p-4">
        <div class="flex flex-col gap-2 sm:flex-row">
          <textarea
            class="input min-h-11 flex-1 resize-none font-sans"
            rows="1"
            placeholder="Ask anything..."
            bind:value={input}
            on:keydown={onKey}
            disabled={sending}
          ></textarea>
          <button class="btn-primary" on:click={send} disabled={!input.trim() || sending}>
            Send
          </button>
        </div>
        <div class="mt-2 text-xs text-ink-400">
          Enter to send / Shift+Enter for newline
        </div>
      </div>
    </div>
  {/if}
</section>
