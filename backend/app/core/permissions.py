"""Catálogo y helpers de permisos."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionDef:
    code: str
    namespace: str
    description: str


# Permisos core del Bloque 2.
# Los namespaces futuros (customers.*, equipment.*, work_orders.*, reports.*)
# están definidos para reservar identificadores; no se asignan todavía a roles.
PERMISSIONS: tuple[PermissionDef, ...] = (
    PermissionDef("companies.view", "companies", "Ver empresas"),
    PermissionDef("companies.create", "companies", "Crear empresas"),
    PermissionDef("companies.update", "companies", "Editar empresas"),
    PermissionDef("companies.disable", "companies", "Activar/desactivar empresas"),
    PermissionDef("companies.manage_users", "companies", "Gestionar usuarios de la empresa"),
    PermissionDef("users.view", "users", "Ver usuarios"),
    PermissionDef("users.create", "users", "Crear usuarios"),
    PermissionDef("users.update", "users", "Editar usuarios"),
    PermissionDef("users.disable", "users", "Activar/desactivar usuarios"),
    PermissionDef("roles.view", "roles", "Ver roles"),
    PermissionDef("roles.manage", "roles", "Crear/editar roles y asignarlos"),
)


# Namespaces reservados para módulos futuros; sin permisos específicos aún.
FUTURE_NAMESPACES: tuple[str, ...] = ("customers", "equipment", "work_orders", "reports")


SUPERADMIN_PERMISSIONS: tuple[str, ...] = tuple(p.code for p in PERMISSIONS)


# Roles del sistema predefinidos. company_id=None indica rol global (sólo SuperAdmin).
SYSTEM_ROLE_SUPERADMIN = "SuperAdmin"
SYSTEM_ROLE_COMPANY_ADMIN = "Administrador"
SYSTEM_ROLE_COMPANY_MEMBER = "Miembro"


def permission_codes() -> tuple[str, ...]:
    return tuple(p.code for p in PERMISSIONS)