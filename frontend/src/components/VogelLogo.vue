<script setup lang="ts">
withDefaults(defineProps<{ size?: number; mark?: boolean }>(), {
  size: 36,
  mark: false,
});

const OFFICIAL_LOGO_URL =
  "https://vogelconsultoria.com.ar/assets/logo-vogel-generated-DhTW546M.webp";
</script>

<template>
  <span
    class="vogel-logo"
    :class="{ 'vogel-logo--mark': mark }"
    :style="{ height: `${size}px` }"
    role="img"
    aria-label="Vogel Consultoría"
  >
    <img
      :src="OFFICIAL_LOGO_URL"
      alt="Vogel Consultoría"
      decoding="async"
      draggable="false"
    />
  </span>
</template>

<style scoped>
.vogel-logo {
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
  overflow: hidden;
  border-radius: 8px;
}

.vogel-logo img {
  display: block;
  width: auto;
  height: 100%;
  max-width: min(320px, 42vw);
  object-fit: contain;
  object-position: left center;
}

.vogel-logo--mark {
  width: var(--logo-mark-size, 42px);
}

.vogel-logo--mark img {
  width: 100%;
  max-width: none;
  object-fit: cover;
  object-position: left center;
}
</style>
