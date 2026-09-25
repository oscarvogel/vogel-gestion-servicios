<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";

const props = defineProps<{
  open: boolean;
  title: string;
  width?: string;
}>();

const emit = defineEmits<{ (e: "close"): void }>();

const dialogRef = ref<HTMLDivElement | null>(null);

function onKey(e: KeyboardEvent) {
  if (e.key === "Escape" && props.open) emit("close");
}

onMounted(() => window.addEventListener("keydown", onKey));
onUnmounted(() => window.removeEventListener("keydown", onKey));
</script>

<template>
  <Teleport to="body">
    <transition name="fade">
      <div v-if="open" class="modal-backdrop" @click.self="emit('close')">
        <div
          ref="dialogRef"
          class="modal"
          :style="{ maxWidth: width ?? '560px' }"
          role="dialog"
          aria-modal="true"
        >
          <div class="modal__header">
            <div class="modal__title">{{ title }}</div>
            <button class="modal__close" type="button" @click="emit('close')" aria-label="Cerrar">×</button>
          </div>
          <slot />
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.18s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>