<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import { useSessionStore } from "../stores/session";

const route=useRoute();
const session=useSessionStore();
const canCustomers=computed(()=>session.hasPermission("customers.view"));
const canOrders=computed(()=>session.hasPermission("work_orders.view"));
const active=(prefix:string)=>route.path.startsWith(prefix);
</script>
<template>
  <nav class="mobile-bottom-nav" aria-label="Navegación principal">
    <RouterLink to="/app/dashboard" class="mobile-bottom-nav__item" :class="{active:active('/app/dashboard')}">
      <svg viewBox="0 0 24 24"><path d="M4 13h6V4H4v9Zm0 7h6v-4H4v4Zm10 0h6v-9h-6v9Zm0-16v4h6V4h-6Z"/></svg><span>Inicio</span>
    </RouterLink>
    <RouterLink v-if="canCustomers" to="/app/customers" class="mobile-bottom-nav__item" :class="{active:active('/app/customers')}">
      <svg viewBox="0 0 24 24"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg><span>Clientes</span>
    </RouterLink>
    <RouterLink v-if="canOrders" :to="{path:'/app/work-orders',query:{action:'new'}}" class="mobile-bottom-nav__item mobile-bottom-nav__item--primary">
      <span class="mobile-bottom-nav__primary-icon"><svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg></span><span>Nueva OT</span>
    </RouterLink>
    <RouterLink v-if="canOrders" to="/app/work-orders" class="mobile-bottom-nav__item" :class="{active:active('/app/work-orders')}">
      <svg viewBox="0 0 24 24"><path d="M9 5H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-4M9 3h6v4H9V3ZM8 12h8M8 16h5"/></svg><span>Órdenes</span>
    </RouterLink>
    <button class="mobile-bottom-nav__item" type="button" @click="$emit('more')">
      <svg viewBox="0 0 24 24"><circle cx="12" cy="5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="19" r="1"/></svg><span>Más</span>
    </button>
  </nav>
</template>
<style scoped>
.mobile-bottom-nav{display:none}
@media(max-width:700px){
.mobile-bottom-nav{position:fixed;left:0;right:0;bottom:0;z-index:70;height:calc(68px + env(safe-area-inset-bottom));padding:5px 8px env(safe-area-inset-bottom);display:grid;grid-template-columns:repeat(5,1fr);align-items:end;background:rgba(8,20,43,.97);border-top:1px solid var(--color-border-strong);box-shadow:0 -10px 30px rgba(0,0,0,.25);backdrop-filter:blur(14px)}
.mobile-bottom-nav__item{height:58px;min-width:0;border:0;background:transparent;color:var(--color-text-muted);text-decoration:none;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;font:inherit;font-size:10px;cursor:pointer}
.mobile-bottom-nav__item>svg{width:21px;height:21px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.mobile-bottom-nav__item.active{color:var(--vogel-primary)}
.mobile-bottom-nav__item--primary{color:var(--color-text-primary)}
.mobile-bottom-nav__primary-icon{width:42px;height:42px;margin-top:-18px;border-radius:50%;display:grid;place-items:center;background:var(--vogel-primary);color:#fff;box-shadow:0 7px 18px rgba(45,124,255,.38)}
.mobile-bottom-nav__primary-icon svg{width:22px;height:22px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round}
}
</style>