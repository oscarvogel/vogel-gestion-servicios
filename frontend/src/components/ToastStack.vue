<script setup lang="ts">
import { useToastStore } from "../stores/toasts";

const toasts = useToastStore();
</script>

<template>
  <Teleport to="body">
    <div class="toast-stack" role="status" aria-live="polite">
      <div
        v-for="toast in toasts.items"
        :key="toast.id"
        :class="['toast', `toast--${toast.kind}`]"
        @click="toasts.dismiss(toast.id)"
      >
        {{ toast.message }}
      </div>
    </div>
  </Teleport>
</template>