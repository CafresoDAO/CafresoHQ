<script>
  export let canister;
  export let block;
  export let compact = false;
</script>

<span
  class="inline-flex items-center gap-1.5 font-medium whitespace-nowrap"
  style="
    background: hsl(26 45% 96% / 0.7);
    border: 1px solid hsl(26 30% 85%);
    padding: {compact ? '2px 8px' : '4px 10px'};
    border-radius: 999px;
    font-size: {compact ? '10.5px' : '11px'};
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    color: hsl(24 40% 22%);
    letter-spacing: 0.02em;
  "
>
  <img src="/assets/icp.png" alt="" style="width: {compact ? 11 : 13}px; height: {compact ? 11 : 13}px;" />
  <span>{canister}</span>
  <span style="color: hsl(215 16% 47%);">·</span>
  <span>#{block.toLocaleString()}</span>
</span>
