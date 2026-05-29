<script>
  // Renders comment text with @mentions highlighted.
  // Splits on the @word boundary and wraps matches in styled spans.
  export let text = '';
  export let accentColor = 'hsl(43 74% 54%)';
  export let accentBg    = 'hsl(43 74% 92%)';

  // Split on @mentions — keep the delimiter in the result so we can iterate.
  $: parts = text.split(/(@[\w.]+)/g).map((segment) => ({
    isMention: /^@[\w.]+$/.test(segment),
    text: segment,
  }));
</script>

<span class="mention-text">{#each parts as p}{#if p.isMention}<span
    class="mention"
    style="
      color: {accentColor};
      background: {accentBg};
      border-radius: 4px;
      padding: 0 3px;
      font-weight: 600;
      font-size: 0.93em;
    "
  >{p.text}</span>{:else}{p.text}{/if}{/each}</span>

<style>
  .mention-text {
    white-space: pre-wrap;
    word-break: break-word;
  }
</style>
