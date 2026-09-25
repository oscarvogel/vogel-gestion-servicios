import { createRouter, createWebHistory } from "vue-router";
import LoginView from "./views/LoginView.vue";
import PostLoginView from "./views/PostLoginView.vue";
import CompanySelectorView from "./views/CompanySelectorView.vue";
import DashboardView from "./views/DashboardView.vue";
import CompaniesView from "./views/CompaniesView.vue";
import UsersView from "./views/UsersView.vue";
import RolesView from "./views/RolesView.vue";
import SettingsView from "./views/SettingsView.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/app/dashboard" },
    { path: "/login", name: "login", component: LoginView },
    {
      path: "/post-login",
      name: "post-login",
      component: PostLoginView,
    },
    {
      path: "/company-selector",
      name: "company-selector",
      component: CompanySelectorView,
    },
    {
      path: "/app",
      component: () => import("./components/AppShell.vue"),
      children: [
        { path: "", redirect: "/app/dashboard" },
        {
          path: "dashboard",
          name: "dashboard",
          component: DashboardView,
        },
        {
          path: "companies",
          name: "companies",
          component: CompaniesView,
        },
        { path: "users", name: "users", component: UsersView },
        { path: "roles", name: "roles", component: RolesView },
        { path: "settings", name: "settings", component: SettingsView },
      ],
    },
    { path: "/:pathMatch(.*)*", redirect: "/app/dashboard" },
  ],
});

export default router;