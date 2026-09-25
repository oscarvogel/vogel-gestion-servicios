import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import router from "./router";
import { useSessionStore } from "./stores/session";
import { setUnauthorizedHandler } from "./lib/api";
import "./styles/global.css";

const pinia = createPinia();
const session = useSessionStore(pinia);
setUnauthorizedHandler(() => {
  void session.logout().finally(() => router.replace({ name: "login" }));
});
createApp(App).use(pinia).use(router).mount("#app");
