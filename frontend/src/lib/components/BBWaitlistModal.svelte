<script>
  import Icon from './Icon.svelte';
  import { bbModalOpen } from '$lib/stores/blog.js';

  let step = 0;
  let signed = false;

  $: if ($bbModalOpen) {
    step = 0;
    signed = false;
  }

  function close() {
    bbModalOpen.set(false);
  }

  async function next() {
    if (step === 1) {
      signed = true;
      await new Promise((r) => setTimeout(r, 1100));
      step = 2;
    } else if (step === 2) {
      close();
    } else {
      step += 1;
    }
  }

  const BB = {
    navy: 'hsl(220 72% 22%)',
    navyDeep: 'hsl(220 78% 14%)',
    gold: 'hsl(43 74% 54%)',
    ivory: 'hsl(42 40% 96%)'
  };
</script>

{#if $bbModalOpen}
  <div
    on:click={close}
    role="presentation"
    class="fade-up fixed inset-0 z-[60] flex items-center justify-center"
    style="background: hsl(220 78% 8% / 0.72); backdrop-filter: blur(6px); padding: 20px;"
  >
    <div
      on:click|stopPropagation
      role="dialog"
      class="overflow-hidden"
      style="
        width: min(520px, 100%);
        background: {BB.ivory}; border: 2px solid {BB.gold};
        border-radius: 16px;
        box-shadow: 0 40px 80px -20px {BB.navyDeep};
      "
    >
      <!-- Navy header -->
      <div
        class="relative"
        style="
          background: linear-gradient(180deg, {BB.navyDeep}, {BB.navy});
          color: {BB.ivory}; padding: 24px 28px;
          border-bottom: 1px solid {BB.gold};
        "
      >
        <button
          on:click={close}
          class="absolute bg-transparent border-none cursor-pointer"
          style="top: 14px; right: 14px; color: {BB.ivory}; padding: 6px; border-radius: 6px;"
          aria-label="Close"
        >
          <Icon name="x" size={18} />
        </button>
        <div class="flex items-center gap-3.5">
          <img src="/assets/banking-brave-logo.png" alt="" style="width: 56px; height: 56px;" />
          <div>
            <div
              class="uppercase font-bold mb-1"
              style="font-size: 10.5px; letter-spacing: 0.2em; color: {BB.gold};"
            >Banking.Brave · Testnet</div>
            <h3 class="font-serif-display m-0" style="font-size: 24px; font-weight: 600; letter-spacing: -0.01em;">
              Reserve your seat
            </h3>
          </div>
        </div>
        <div class="flex mt-4" style="gap: 6px;">
          {#each [0, 1, 2] as i}
            <span
              class="flex-1"
              style="
                height: 3px; border-radius: 2px;
                background: {i <= step ? BB.gold : 'hsl(220 40% 30%)'};
                transition: background .3s;
              "
            ></span>
          {/each}
        </div>
      </div>

      <div style="padding: 28px 32px;">
        {#if step === 0}
          <p class="m-0 mb-5" style="font-size: 15px; line-height: 1.6; color: hsl(222 30% 20%);">
            You're about to stake <strong>500 $CF</strong> to reserve a testnet seat. Your stake returns at mainnet launch, plus a founding-member bonus equal to one month of vault yield.
          </p>
          <div
            class="bg-white rounded-xl mb-4"
            style="border: 1px solid hsl(220 20% 85%); padding: 16px;"
          >
            <div
              class="flex justify-between items-center text-sm mb-2.5 pb-2.5"
              style="border-bottom: 1px dashed hsl(220 20% 88%);"
            >
              <span style="color: hsl(215 16% 47%);">Stake</span>
              <span class="font-serif-display" style="font-size: 22px; font-weight: 600; color: {BB.navyDeep};">500 $CF</span>
            </div>
            <div class="flex justify-between items-center text-sm mb-2.5">
              <span style="color: hsl(215 16% 47%);">Lock-up</span>
              <span class="font-semibold" style="color: {BB.navyDeep};">Until mainnet launch (est. Jun 2026)</span>
            </div>
            <div class="flex justify-between items-center text-sm">
              <span style="color: hsl(215 16% 47%);">Founding bonus</span>
              <span class="font-semibold" style="color: hsl(112 43% 35%);">+3.02 $CF (1 mo. yield)</span>
            </div>
          </div>
          <label
            class="flex gap-2.5 items-start text-[13px]"
            style="color: hsl(222 30% 25%); line-height: 1.5;"
          >
            <input type="checkbox" checked style="margin-top: 3px; accent-color: {BB.navy};" />
            <span>I understand the stake is locked until mainnet and subject to SNS governance.</span>
          </label>
        {/if}

        {#if step === 1}
          <div class="text-center" style="padding: 18px 0;">
            <div
              class="mx-auto mb-4 flex items-center justify-center rounded-full text-white"
              style="
                width: 92px; height: 92px;
                background: {signed ? 'hsl(112 43% 45%)' : BB.navy};
                transition: background .4s;
                box-shadow: 0 0 0 6px {signed ? 'hsl(112 43% 45% / 0.2)' : 'hsl(220 55% 22% / 0.15)'};
              "
            >
              {#if signed}
                <Icon name="check" size={48} weight="fill" />
              {:else}
                <Icon name="fingerprint" size={48} />
              {/if}
            </div>
            <h3 class="font-serif-display m-0 mb-1.5" style="font-size: 22px; font-weight: 600; color: {BB.navyDeep}; letter-spacing: -0.01em;">
              {signed ? 'Signature accepted' : 'Sign with Internet Identity'}
            </h3>
            <p class="mx-auto m-0" style="font-size: 14px; line-height: 1.55; color: hsl(215 16% 47%); max-width: 340px;">
              {signed
                ? 'Broadcasting to the Banking.Brave vault canister…'
                : 'Approve the stake transaction in your II popup. Non-custodial — your keys never leave the device.'}
            </p>
            {#if signed}
              <div
                class="mt-4 font-mono text-[11px]"
                style="color: hsl(215 16% 40%);"
              >tx 0x9a2c…f810 · block #4,824,091</div>
            {/if}
          </div>
        {/if}

        {#if step === 2}
          <div class="text-center" style="padding: 6px 0;">
            <div class="relative mx-auto mb-3.5" style="width: 120px;">
              <img src="/assets/banking-brave-logo.png" alt="" style="width: 100%;" />
              <div
                class="absolute flex items-center justify-center rounded-full text-white"
                style="
                  bottom: -6px; right: -6px;
                  width: 36px; height: 36px;
                  background: hsl(112 43% 45%);
                  box-shadow: 0 4px 10px hsl(112 43% 20% / 0.3);
                "
              >
                <Icon name="check" size={22} weight="fill" />
              </div>
            </div>
            <div
              class="uppercase font-bold mb-1.5"
              style="font-size: 10.5px; letter-spacing: 0.2em; color: {BB.gold};"
            >Seat #615 of 1,000</div>
            <h3 class="font-serif-display m-0 mb-2" style="font-size: 26px; font-weight: 600; color: {BB.navyDeep}; letter-spacing: -0.01em;">
              You're in.
            </h3>
            <p class="mx-auto mb-4" style="font-size: 14.5px; line-height: 1.55; color: hsl(215 16% 40%); max-width: 360px;">
              Welcome, founding member. Testnet opens May 12 — we'll ping your Internet Identity when your vault is ready to fund.
            </p>
            <div
              class="inline-flex items-center gap-2.5 bg-white rounded-lg"
              style="border: 1px solid {BB.gold}; padding: 12px 16px; font-size: 12px; color: {BB.navyDeep};"
            >
              <Icon name="calendar-check" size={16} style="color: {BB.navy};" />
              Testnet opens <strong>May 12, 2026</strong>
            </div>
          </div>
        {/if}
      </div>

      <div
        class="flex justify-end"
        style="padding: 14px 28px 22px; gap: 10px; border-top: 1px solid hsl(220 20% 88%);"
      >
        {#if step < 2}
          <button
            on:click={close}
            class="bg-transparent border-none cursor-pointer"
            style="color: hsl(215 16% 47%); padding: 10px 14px; font-family: inherit; font-size: 14px;"
          >Cancel</button>
        {/if}
        <button
          on:click={next}
          disabled={step === 1 && !signed}
          class="inline-flex items-center gap-2 cursor-pointer text-white font-semibold"
          style="
            background: {step === 1 && !signed ? 'hsl(220 20% 70%)' : BB.navy};
            border: none; padding: 11px 22px; border-radius: 8px;
            font-family: inherit; font-size: 14px;
            cursor: {step === 1 && !signed ? 'default' : 'pointer'};
            opacity: {step === 1 && !signed ? 0.7 : 1};
          "
        >
          {#if step === 0}Continue <Icon name="arrow-right" size={14} />{/if}
          {#if step === 1 && !signed}Waiting for signature… <span class="spin"><Icon name="circle-notch" size={14} /></span>{/if}
          {#if step === 1 && signed}Confirmed <Icon name="check" size={14} />{/if}
          {#if step === 2}Back to Dev Log{/if}
        </button>
      </div>
    </div>
  </div>
{/if}
