<script>
  /* GoldCoin — the sGLDT mark. A minted gold round with an ingot glyph;
     replaces NanasCoin everywhere the real (gold) economy is shown. */
  export let size = 16;
</script>

<svg
  width={size}
  height={size}
  viewBox="0 0 24 24"
  fill="none"
  xmlns="http://www.w3.org/2000/svg"
  aria-hidden="true"
  style="display: inline-block; vertical-align: -0.15em;"
>
  <defs>
    <radialGradient id="gc-face" cx="35%" cy="30%" r="80%">
      <stop offset="0%" stop-color="#FCE9A8" />
      <stop offset="55%" stop-color="#F0C13F" />
      <stop offset="100%" stop-color="#C8921A" />
    </radialGradient>
  </defs>
  <circle cx="12" cy="12" r="11" fill="url(#gc-face)" stroke="#A87614" stroke-width="1.4" />
  <circle cx="12" cy="12" r="8.2" fill="none" stroke="#A87614" stroke-width="0.9" opacity="0.55" />
  <!-- ingot -->
  <path
    d="M8.6 13.9 L9.7 10.4 Q9.85 10 10.3 10 L13.7 10 Q14.15 10 14.3 10.4 L15.4 13.9 Q15.5 14.3 15.05 14.3 L8.95 14.3 Q8.5 14.3 8.6 13.9 Z"
    fill="#A87614"
    opacity="0.85"
  />
</svg>
