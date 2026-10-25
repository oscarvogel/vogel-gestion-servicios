import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import { useSessionStore } from "./stores/session";
import LoginView from "./views/LoginView.vue";
import PostLoginView from "./views/PostLoginView.vue";
import CompanySelectorView from "./views/CompanySelectorView.vue";
import AccessDeniedView from "./views/AccessDeniedView.vue";
import DashboardView from "./views/DashboardView.vue";
import CompaniesView from "./views/CompaniesView.vue";
import UsersView from "./views/UsersView.vue";
import CustomersView from "./views/CustomersView.vue";
import WorkOrdersView from "./views/WorkOrdersView.vue";
import WorkOrderImportView from "./views/WorkOrderImportView.vue";
import RolesView from "./views/RolesView.vue";
import SettingsView from "./views/SettingsView.vue";
import ParametersView from "./views/ParametersView.vue";
import WorkOrderStatusesView from "./views/WorkOrderStatusesView.vue";
import AssistantView from "./views/AssistantView.vue";
import AiConsumoView from "./views/AiConsumoView.vue";
import CierreMarcasView from "./views/CierreMarcasView.vue";
import TecnicosView from "./views/TecnicosView.vue";
import AiConsumoView from "./views/AiConsumoView.vue";

declare module "vue-router" {
  interface RouteMeta {
    requiresAuth?: boolean;
    guestOnly?: boolean;
    superAdminOnly?: boolean;
    companyAdminOnly?: boolean;
    permission?: string;
    order?: number;
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
    // meta.order de cada hijo = su posicion en el menu lateral: decide si la pagina nueva
    // entra subiendo o bajando (AppShell).
    component: () => import("./components/AppShell.vue"),
    meta: { requiresAuth: true },
    children: [
      { path: "", redirect: "/app/dashboard" },
      {
        path: "dashboard",
        name: "dashboard",
        component: DashboardView,
        alias: ["/dashboard"],
        meta: { requiresAuth: true, order: 0 },
      },
      {
        path: "companies",
        name: "companies",
        component: CompaniesView,
        alias: ["/empresas"],
        meta: { requiresAuth: true, order: 12, superAdminOnly: true },
      },
      {
        path: "customers",
        name: "customers",
        component: CustomersView,
        meta: { requiresAuth: true, order: 2, permission: "customers.view" },
      },
      {
        path: "work-orders",
        name: "work-orders",
        component: WorkOrdersView,
        meta: { requiresAuth: true, order: 1, permission: "work_orders.view" },
      },
      {
        path: "work-orders/import",
        name: "work-orders-import",
        component: WorkOrderImportView,
        meta: { requiresAuth: true, order: 1.5, permission: "work_orders.manage" },
      },
      {
        path: "users",
        name: "users",
        component: UsersView,
        alias: ["/usuarios"],
        meta: { requiresAuth: true, order: 7, permission: "users.view" },
      },
      {
        path: "roles",
        name: "roles",
        component: RolesView,
        alias: ["/roles"],
        meta: { requiresAuth: true, order: 8, permission: "roles.view" },
      },
      {
        path: "parameters",
        name: "parameters",
        component: ParametersView,
        meta: { requiresAuth: true, order: 10, companyAdminOnly: true },
      },
      {
        path: "work-order-statuses",
        name: "work-order-statuses",
        component: WorkOrderStatusesView,
        meta: { requiresAuth: true, order: 9, companyAdminOnly: true },
      },
      {
        path: "cierre-marcas",
        name: "cierre-marcas",
        component: CierreMarcasView,
        alias: ["/cierre-marcas"],
        // Ver el cierre y emitirlo no es lo mismo: el permiso de ver habilita la pantalla,
        // y el de administrar habilita generar, emitir y liquidar.
        meta: { requiresAuth: true, order: 4, permission: "warranty_settlements.view" },
      },
      {
        path: "tecnicos",
        name: "tecnicos",
        component: TecnicosView,
        alias: ["/tecnicos"],
        // El maestro de técnicos: verlo lo puede cualquiera que administration órdenes, y
        // dar de alta gente o desactivarla es tarea de quien administra el maestro.
        meta: { requiresAuth: true, order: 3, permission: "technicians.view" },
      },
      {
        path: "assistant",
        name: "assistant",
        component: AssistantView,
        meta: { requiresAuth: true, order: 5, permission: "ai.use" },
      },
      {
        path: "consumo-ia",
        name: "consumo-ia",
        component: AiConsumoView,
        alias: ["/consumo-ia"],
        // El mismo permiso que el asistente: consumo sin poder usar la IA no tiene sentido.
        meta: { requiresAuth: true, order: 6, permission: "ai.use" },
      },
      {
        path: "settings",
        name: "settings",
        component: SettingsView,
        meta: { requiresAuth: true, order: 11, companyAdminOnly: true },
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

    if (to.matched.some((record) => record.meta.companyAdminOnly)) {
      const companyAdmin = session.activeCompany?.is_admin === true;
      if (!session.isSuperAdmin && !companyAdmin) return { name: "forbidden" };
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
