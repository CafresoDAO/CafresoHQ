<script>
  // Textarea wrapper that intercepts @ characters and shows a suggestion
  // popup of known community members. bind:value={draft} from parent works
  // exactly like a plain textarea.
  import Avatar from './Avatar.svelte';

  export let value       = '';
  export let placeholder = 'Type @ to mention someone…';
  export let rows        = 4;
  export let maxlength   = 600;
  export let style       = '';
  export let className   = '';
  export let disabled    = false;

  // Seed list — in production fetched from canister participant index.
  const KNOWN_USERS = [
    { name: 'Cafreso DAO',      hue: 24  },
    { name: 'Cafreso Core',     hue: 220 },
    { name: 'Growth Guild',     hue: 112 },
    { name: 'Community Member', hue: 0   },
  ];

  let textareaEl;
  let showPopup  = false;
  let query      = '';
  let triggerAt  = -1; // index in value where the @ was typed
  let selectedIdx = 0;

  $: filtered = query.length >= 0
    ? KNOWN_USERS.filter((u) => u.name.toLowerCase().startsWith(query.toLowerCase())).slice(0, 6)
    : KNOWN_USERS.slice(0, 6);

  function handleInput() {
    const text   = textareaEl.value;
    const cursor = textareaEl.selectionStart;
    const before = text.slice(0, cursor);
    const match  = before.match(/@([\w.]*)$/);

    if (match && filtered.length > 0) {
      triggerAt   = cursor - match[0].length;
      query       = match[1];
      showPopup   = true;
      selectedIdx = 0;
    } else {
      showPopup = false;
    }
    value = text;
  }

  function pickSuggestion(user) {
    if (!textareaEl) return;
    const cursor = textareaEl.selectionStart;
    const before = value.slice(0, triggerAt);
    const after  = value.slice(cursor);
    value = `${before}@${user.name} ${after}`;
    showPopup = false;
    // Restore focus + move caret past the inserted mention.
    requestAnimationFrame(() => {
      textareaEl.focus();
      const pos = triggerAt + user.name.length + 2; // @ + name + space
      textareaEl.setSelectionRange(pos, pos);
    });
  }

  function handleKeydown(e) {
    if (!showPopup || !filtered.length) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      selectedIdx = (selectedIdx + 1) % filtered.length;
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      selectedIdx = (selectedIdx - 1 + filtered.length) % filtered.length;
    } else if (e.key === 'Enter' || e.key === 'Tab') {
      e.preventDefault();
      pickSuggestion(filtered[selectedIdx]);
    } else if (e.key === 'Escape') {
      showPopup = false;
    }
  }

  function handleBlur() {
    // Tiny delay so mousedown on popup buttons registers first.
    setTimeout(() => { showPopup = false; }, 120);
  }
</script>

<div style="position: relative;">
  <textarea
    bind:this={textareaEl}
    {value}
    {placeholder}
    {rows}
    {maxlength}
    {disabled}
    oninput={handleInput}
    onkeydown={handleKeydown}
    onblur={handleBlur}
    class={className}
    {style}
  ></textarea>

  {#if showPopup && filtered.length > 0}
    <div style="
      position: absolute; left: 0; bottom: calc(100% + 6px); z-index: 50;
      min-width: 220px; max-width: 300px;
      background: white; border: 1px solid hsl(26 30% 85%);
      border-radius: 12px; box-shadow: 0 8px 24px -6px hsl(222 30% 20% / 0.2);
      overflow: hidden; padding: 4px;
    ">
      <div style="
        font-size: 9.5px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
        color: hsl(215 16% 56%); padding: 5px 10px 3px;
      ">Mention a member</div>
      {#each filtered as u, i}
        <!-- svelte-ignore a11y-click-events-have-key-events -->
        <!-- svelte-ignore a11y-no-static-element-interactions -->
        <div
          onmousedown={(e) => { e.preventDefault(); pickSuggestion(u); }}
          style="
            display: flex; align-items: center; gap: 8px;
            padding: 7px 10px; border-radius: 8px; cursor: pointer;
            background: {selectedIdx === i ? 'hsl(43 74% 94%)' : 'transparent'};
          "
        >
          <Avatar name={u.name} hue={u.hue} size={24} />
          <span style="font-size: 13px; font-weight: 600; color: hsl(222 47% 11%);">
            @{u.name}
          </span>
        </div>
      {/each}
      <div style="
        font-size: 10px; color: hsl(215 16% 56%); padding: 4px 10px 6px;
        border-top: 1px solid hsl(26 25% 92%); margin-top: 2px;
      ">↑↓ navigate · Enter to select · Esc to close</div>
    </div>
  {/if}
</div>
