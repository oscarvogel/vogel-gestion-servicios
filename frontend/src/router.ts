import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import { useSessionStore } from "./stores/session";
import LoginView from "./views/LoginView.vue";
import PostLoginView from "./views/PostLoginView.vue";
import CompanySelectorView from "./views/CompanySelectorView.vue";
import AccessDeniedView from "./views/AccessDeniedView.vue";
import DashboardView from "./views/DashboardView.vue";
import CompaniesView from "./views/CompaniesView.vue";
import UsersView from "./views/UsersView.vue";
import RolesView from "./views/RolesView.vue";
import SettingsView from "./views/SettingsView.vue";

declare module "vue-router" {
  interface RouteMeta {
    requiresAuth?: boolean;
    guestOnly?: boolean;
    superAdminOnly?: boolean;
    permission?: string;
  }
}

const routes: RouteRecordRaw[] = [
  { path: "/", redirect: "/app/dashboard" },
  { path: "/login", name: "login", component: LoginView, meta: { guestOnly: true } },
  {
    path: "/post-login",
    name: "post-login",
    component: PostLoginView,
    meta: { requiresAuth: true },
  },
  {
    path: "/company-selector",
    name: "company-selector",
    component: CompanySelectorView,
    meta: { requiresAuth: true },
  },
  {
    path: "/403",
    name: "forbidden",
    component: AccessDeniedView,
    meta: { requiresAuth: true },
  },
  {
    path: "/app",
    component: () => import("./components/AppShell.vue"),
    meta: { requiresAuth: true },
    children: [
      { path: "", redirect: "/app/dashboard" },
      {
        path: "dashboard",
        name: "dashboard",
        component: DashboardView,
        alias: ["/dashboard"],
        meta: { requiresAuth: true },
      },
      {
        path: "companies",
        name: "companies",
        component: CompaniesView,
        alias: ["/empresas"],
        meta: { requiresAuth: true, superAdminOnly: true },
      },
      {
        path: "users",
        name: "users",
        component: UsersView,
        alias: ["/usuarios"],
        meta: { requiresAuth: true, permission: "users.view" },
      },
      {
        path: "roles",
        name: "roles",
        component: RolesView,
        alias: ["/roles"],
        meta: { requiresAuth: true, permission: "roles.view" },
      },
      {
        path: "settings",
        name: "settings",
        component: SettingsView,
        meta: { requiresAuth: true, superAdminOnly: true },
      },
    ],
  },
  { path: "/:pathMatch(.*)*", redirect: "/app/dashboard" },
];

export function createAppRouter() {
  const router = createRouter({
    history: createWebHistory(),
    routes,
  });

  router.beforeEach(async (to) => {
    const session = useSessionStore();
    await session.bootstrap();

    if (to.matched.some((record) => record.meta.requiresAuth) && !session.isAuthenticated) {
      return { name: "login", query: { redirect: to.fullPath } };
    }

    if (to.meta.guestOnly && session.isAuthenticated) {
      return { name: "post-login" };
    }

    if (to.matched.some((record) => record.meta.superAdminOnly) && !session.isSuperAdmin) {
      return { name: "forbidden" };
    }

    const requiredPermission = to.matched
      .map((record) => record.meta.permission)
      .find((permission): permission is string => Boolean(permission));
    if (requiredPermission && !session.hasPermission(requiredPermission)) {
      return { name: "forbidden" };
    }

    return true;
  });

  return router;
}

const router = createAppRouter();
export default router;
