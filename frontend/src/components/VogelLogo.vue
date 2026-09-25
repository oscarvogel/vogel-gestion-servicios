<script setup lang="ts">
defineProps<{ size?: number; mark?: boolean }>();
</script>

<template>
  <svg
    :width="size ?? 36"
    :height="size ?? 36"
    viewBox="0 0 64 64"
    xmlns="http://www.w3.org/2000/svg"
    role="img"
    aria-label="Vogel Consultoría"
  >
    <defs>
      <linearGradient id="vogel-grad" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#2d7cff" />
        <stop offset="100%" stop-color="#38e1c4" />
      </linearGradient>
    </defs>
    <rect
      x="2"
      y="2"
      width="60"
      height="60"
      rx="14"
      fill="url(#vogel-grad)"
    />
    <path
      d="M16 20 L24 44 L32 28 L40 44 L48 20"
      stroke="#fff"
      stroke-width="4.2"
      stroke-linecap="round"
      stroke-linejoin="round"
      fill="none"
    />
    <circle cx="32" cy="50" r="3" fill="#fff" />
  </svg>
</template>