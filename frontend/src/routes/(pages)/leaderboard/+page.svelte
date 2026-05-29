<script>
  import { onMount } from 'svelte';
  import Icon from '$lib/components/Icon.svelte';
  import Button from '$lib/components/Button.svelte';
  import { bbLinks } from '$lib/links.js';
  import { getLeaderboard } from '$lib/api/devlog.js';

  // Leaderboard rows are fetched from the IndexCanister's `getLeaderboard`
  // query, which aggregates `$nanas` burn receipts by caller principal.
  // Phase 4+ will add Banking.Brave mining stats via inter-canister call.
  let rows = $state([]);
  let loading = $state(true);
  const trophyColors = ['hsl(45 95% 50%)', 'hsl(0 0% 65%)', 'hsl(28 60% 50%)'];

  onMount(async () => {
    try {
      rows = await getLeaderboard(100);
    } catch (e) {
      console.warn('[leaderboard] load failed', e);
      rows = [];
    } finally {
      loading = false;
    }
  });
</script>

<svelte:head><title>Contest · Cafreso</title></svelte:head>

<div class="mx-auto px-4 py-6 md:p-10" style="max-width: 960px;">
  <div class="text-center">
    <div class="flex items-center justify-center gap-2 text-[13px] font-medium mb-3" style="color: hsl(24 48% 28%);">
      <Icon name="trophy" size={16} /> Leaderboard
    </div>
    <h2 class="font-bold my-2" style="font-size: clamp(24px, 5vw, 32px);">Cafreso Community Leaderboard</h2>
    <p class="leading-[1.55] mx-auto text-[14px] sm:text-[15px]" style="max-width: 680px; color: hsl(215 16% 47%);">
      Ranked by combined on-chain activity — $nanas burned on dev-log tips
      plus UNI mined and sGLDT refined on Banking.Brave. One Internet Identity,
      one principal, one leaderboard.
    </p>
  </div>

  {#if rows.length === 0}
    <div
      class="mt-8 rounded-[16px] p-6 sm:p-10 text-center"
      style="background: hsl(26 40% 98%); border: 1px dashed hsl(26 30% 75%);"
    >
      <div
        class="w-14 h-14 sm:w-16 sm:h-16 mx-auto rounded-full flex items-center justify-center mb-4"
        style="background: hsl(45 80% 92%); color: hsl(32 56% 25%);"
      >
        <Icon name="trophy" size={28} />
      </div>
      <h3 class="font-bold text-[18px] sm:text-[20px] mb-2" style="color: hsl(222 47% 11%);">
        Be the first on the board
      </h3>
      <p class="text-[13.5px] sm:text-[14px] leading-[1.55] mx-auto mb-5" style="max-width: 460px; color: hsl(215 16% 47%);">
        No rankings yet. Tip a dev-log post with $nanas or submit your first
        UNI deposit on Banking.Brave — both count toward your rank.
      </p>
      <div class="flex flex-col sm:flex-row gap-2 justify-center">
        <Button href="/blog">
          <Icon name="article" size={15} /> Read the dev log
        </Button>
        <Button variant="outline" href={bbLinks.mine}>
          <Icon name="coin" size={15} /> Open Banking.Brave
          <Icon name="arrow-up-right" size={11} style="opacity: 0.6;" />
        </Button>
      </div>
    </div>
  {:else}
    <div class="leaderboard-scroll bg-white rounded-lg mt-6 overflow-hidden" style="border: 1px solid hsl(26 30% 88%);">
      <table class="w-full text-sm" style="border-collapse: collapse;">
        <thead>
          <tr class="text-left" style="background: hsl(26 30% 94%);">
            <th class="px-3 sm:px-4 py-3 text-[11px] font-semibold uppercase" style="letter-spacing: 0.05em; color: hsl(215 16% 47%);">#</th>
            <th class="px-3 sm:px-4 py-3 text-[11px] font-semibold uppercase" style="letter-spacing: 0.05em; color: hsl(215 16% 47%);">Principal</th>
            <th class="px-3 sm:px-4 py-3 text-[11px] font-semibold uppercase text-right" style="letter-spacing: 0.05em; color: hsl(215 16% 47%);">$nanas burned</th>
          </tr>
        </thead>
        <tbody>
          {#each rows as r}
            <tr style="border-top: 1px solid hsl(26 30% 92%);">
              <td class="px-3 sm:px-4 py-3.5">
                {#if r.rank <= 3}
                  <Icon name="trophy" size={20} style="color: {trophyColors[r.rank - 1]};" />
                {:else}
                  <span style="color: hsl(215 16% 47%);">{r.rank}</span>
                {/if}
              </td>
              <td class="px-3 sm:px-4 py-3.5 font-mono text-[11.5px]" style="color: hsl(222 47% 11%);">
                {r.principal.slice(0, 5)}…{r.principal.slice(-3)}
              </td>
              <td class="px-3 sm:px-4 py-3.5 text-right">
                <span class="inline-flex items-center gap-1.5 font-medium tabular-nums">
                  {r.burned.toLocaleString()}
                  <img src="/assets/nanas-coin.png" alt="" class="w-[18px]" />
                </span>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>
