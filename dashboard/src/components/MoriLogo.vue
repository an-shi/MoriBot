<script setup lang="ts">
withDefaults(
  defineProps<{
    size?: number
    showText?: boolean
  }>(),
  {
    size: 36,
    showText: false,
  },
)
</script>

<template>
  <span class="mori-logo" :style="{ '--mark-size': `${size}px` }">
    <svg
      class="mori-logo__mark"
      viewBox="0 0 48 48"
      fill="none"
      aria-hidden="true"
    >
      <rect
        x="1"
        y="1"
        width="46"
        height="46"
        rx="14"
        fill="var(--mori-logo-bg)"
        stroke="var(--mori-logo-border)"
        stroke-width="1.5"
      />
      <path
        d="M12.5 33.5C12.5 21.8 21.2 13.8 36 13.5c0 12.1-8.4 20-19.5 20h-4Z"
        fill="var(--mori-logo-leaf)"
      />
      <path
        d="M14.5 33.2c5.2-7.1 10.4-11.4 17.5-14.2"
        stroke="var(--mori-logo-vein)"
        stroke-width="2.3"
        stroke-linecap="round"
      />
    </svg>
    <span v-if="showText" class="mori-logo__text">Mori<span>Bot</span></span>
  </span>
</template>

<style scoped>
.mori-logo {
  display: inline-flex;
  align-items: center;
  gap: calc(var(--mark-size) * 0.28);
  line-height: 1;
}

.mori-logo__mark {
  width: var(--mark-size);
  height: var(--mark-size);
  flex: none;
  filter: drop-shadow(0 6px 18px rgba(0, 0, 0, 0.18));
}

.mori-logo__text {
  color: var(--mori-text);
  font-size: calc(var(--mark-size) * 0.58);
  font-weight: 700;
  letter-spacing: -0.03em;
}

.mori-logo__text span {
  color: var(--mori-mint);
}
</style>
