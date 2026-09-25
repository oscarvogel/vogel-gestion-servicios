<script setup lang="ts">
import { onMounted } from "vue";
import { useSessionStore } from "./stores/session";
import { setUnauthorizedHandler } from "./lib/api";
import { useRouter } from "vue-router";
import ToastStack from "./components/ToastStack.vue";

const session = useSessionStore();
const router = useRouter();

onMounted(() => {
  setUnauthorizedHandler(() => {
    session.logout();
    router.replace({ name: "login" });
  });
  if (session.token && !session.me) {
    session.loadMe().catch(() => router.replace({ name: "login" }));
  }
});
</script>

<template>
  <router-view />
  <ToastStack />
</template>