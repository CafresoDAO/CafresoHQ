<script>
  /** Size of the logo in px. Responsive cap at 88vw is applied automatically. */
  export let size = 420;
  /** Optional extra delay (ms) before the sequence begins. */
  export let delay = 0;
</script>

<!-- Outer stage keeps everything positioned relative to the logo footprint -->
<div
  class="logo-stage"
  style="width: min({size}px, 88vw); animation-delay: {delay}ms;"
  aria-label="Cafreso — A Blockchain DAO"
>
  <!-- 1. Warm ambient glow that pulses behind the mark -->
  <div class="logo-glow" style="animation-delay: {delay + 200}ms;"></div>

  <!-- 2. Blockchain confirmation rings (expand & fade on load, once each) -->
  <div class="pulse-ring ring-gold" style="animation-delay: {delay + 1800}ms;"></div>
  <div class="pulse-ring ring-leaf" style="animation-delay: {delay + 2600}ms;"></div>

  <!-- 3. The wordmark itself -->
  <img
    src="/assets/cafreso-wordmark.png"
    alt=""
    role="presentation"
    class="logo-img"
    style="animation-delay: {delay + 100}ms, {delay + 2200}ms;"
  />

  <!-- 4. Gold shimmer sweep (one-shot, after reveal) -->
  <div class="logo-shimmer" style="animation-delay: {delay + 1100}ms;"></div>

  <!-- 5. Coffee steam wisps rising from the top of the mark -->
  <div class="steam s1" style="animation-delay: {delay + 2800}ms;"></div>
  <div class="steam s2" style="animation-delay: {delay + 3400}ms;"></div>
  <div class="steam s3" style="animation-delay: {delay + 3100}ms;"></div>
</div>

<style>
  /* ─── Stage ────────────────────────────────────────────────────────────── */
  .logo-stage {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    /* extra padding so rings/steam don't clip */
    padding: 32px 24px 16px;
    box-sizing: content-box;
  }

  /* ─── 1. Glow ──────────────────────────────────────────────────────────── */
  .logo-glow {
    position: absolute;
    inset: 0;
    border-radius: 50%;
    background: radial-gradient(
      ellipse at 50% 60%,
      hsl(45 95% 62% / 0.22) 0%,
      hsl(26 60% 50% / 0.10) 40%,
      transparent 68%
    );
    animation: glowAppear 1.4s both, glowPulse 5s 1.6s ease-in-out infinite;
    pointer-events: none;
  }

  @keyframes glowAppear {
    from { opacity: 0; transform: scale(0.6); }
    to   { opacity: 1; transform: scale(1); }
  }

  @keyframes glowPulse {
    0%, 100% { opacity: 0.7;  transform: scale(1); }
    50%       { opacity: 1;   transform: scale(1.10); }
  }

  /* ─── 2. Blockchain rings ──────────────────────────────────────────────── */
  .pulse-ring {
    position: absolute;
    /* rings surround the full stage */
    inset: 10%;
    border-radius: 50%;
    pointer-events: none;
    animation: ringExpand 2.2s cubic-bezier(0, 0, 0.2, 1) both;
  }
  .ring-gold { border: 1.5px solid hsl(45 95% 62% / 0.65); }
  .ring-leaf { border: 1.5px solid hsl(112 60% 45% / 0.45); }

  @keyframes ringExpand {
    from { transform: scale(0.4); opacity: 0; }
    15%  { opacity: 1; }
    to   { transform: scale(2.0); opacity: 0; }
  }

  /* ─── 3. Logo image ────────────────────────────────────────────────────── */
  .logo-img {
    position: relative;
    z-index: 2;
    width: 100%;
    height: auto;
    display: block;
    /* Two animations: spring reveal + perpetual float */
    animation:
      logoReveal 1.4s cubic-bezier(0.16, 1, 0.3, 1) both,
      logoFloat  7s   ease-in-out infinite;
  }

  @keyframes logoReveal {
    0%   {
      opacity: 0;
      transform: translateY(28px) scale(0.86);
      filter: blur(8px) brightness(1.4) sepia(0.4);
    }
    55%  {
      filter: blur(0) brightness(1.06) sepia(0.05);
    }
    100% {
      opacity: 1;
      transform: translateY(0) scale(1);
      filter: blur(0) brightness(1) sepia(0);
    }
  }

  @keyframes logoFloat {
    0%, 100% { transform: translateY(0px) rotate(0deg); }
    30%       { transform: translateY(-5px) rotate(-0.3deg); }
    70%       { transform: translateY(-3px) rotate(0.2deg); }
  }

  /* ─── 4. Gold shimmer (one-shot sweep) ───────────────────────────────── */
  .logo-shimmer {
    position: absolute;
    inset: 0;
    z-index: 3;
    pointer-events: none;
    border-radius: 4px;
    overflow: hidden;
    animation: shimmerSweep 1.6s cubic-bezier(0.4, 0, 0.2, 1) both;
    /* The gradient is the shimmer bar — moved via background-position */
    background: linear-gradient(
      110deg,
      transparent          0%,
      transparent          28%,
      hsl(45 100% 78% / 0.45) 43%,
      hsl(50 100% 95% / 0.75) 50%,
      hsl(45 100% 78% / 0.45) 57%,
      transparent          72%,
      transparent          100%
    );
    background-size: 250% 100%;
    background-position: -100% 0;
  }

  @keyframes shimmerSweep {
    0%   { background-position: -100% 0; opacity: 0; }
    8%   { opacity: 1; }
    92%  { opacity: 1; }
    100% { background-position: 220% 0; opacity: 0; }
  }

  /* ─── 5. Steam wisps ──────────────────────────────────────────────────── */
  .steam {
    position: absolute;
    /* anchored just above the top edge of the logo */
    bottom: calc(100% - 16px);
    width: 5px;
    height: 36px;
    border-radius: 999px;
    background: linear-gradient(
      to top,
      hsl(26 20% 35% / 0.30),
      hsl(26 20% 55% / 0.12) 60%,
      transparent
    );
    pointer-events: none;
    animation: steamRise 3.5s ease-in-out infinite;
  }

  .s1 { left: 28%; height: 40px; animation-duration: 3.8s; }
  .s2 { left: 50%; height: 28px; animation-duration: 3.2s; }
  .s3 { left: 70%; height: 34px; animation-duration: 4.1s; }

  @keyframes steamRise {
    0%   { transform: translateY(0)    scaleX(1)   skewX(0deg);  opacity: 0; }
    15%  { opacity: 1; }
    50%  { transform: translateY(-20px) scaleX(1.6) skewX(6deg); }
    85%  { opacity: 0.5; }
    100% { transform: translateY(-44px) scaleX(0.3) skewX(-4deg); opacity: 0; }
  }
</style>
