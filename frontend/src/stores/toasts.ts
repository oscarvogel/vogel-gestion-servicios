import { defineStore } from "pinia";
import { ref } from "vue";

export type ToastKind = "success" | "error" | "info";

export interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

let counter = 0;

export const useToastStore = defineStore("toasts", () => {
  const items = ref<Toast[]>([]);

  function push(message: string, kind: ToastKind = "info", ttl = 3800) {
    const id = ++counter;
    items.value = [...items.value, { id, kind, message }];
    setTimeout(() => {
      items.value = items.value.filter((t) => t.id !== id);
    }, ttl);
  }

  function dismiss(id: number) {
    items.value = items.value.filter((t) => t.id !== id);
  }

  return { items, push, dismiss };
});