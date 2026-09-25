#!/usr/bin/env python3
"""Smoke E2E del Bloque 2 sobre backend local."""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from urllib.error import HTTPError

BASE = "http://127.0.0.1:8001"


def req(method: str, path: str, *, token: str | None = None, body: dict | None = None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(f"{BASE}{path}", method=method, headers=headers, data=data)
    try:
        with urllib.request.urlopen(request, timeout=8) as resp:
            payload = resp.read().decode() or "{}"
            return resp.status, json.loads(payload)
    except HTTPError as e:
        payload = e.read().decode() or "{}"
        try:
            return e.code, json.loads(payload)
        except Exception:
            return e.code, {"raw": payload}


def check(label: str, ok: bool, detail: str = "") -> None:
    mark = "OK" if ok else "FAIL"
    print(f"[{mark}] {label}{(' - ' + detail) if detail else ''}")
    if not ok:
        sys.exit(1)


def main() -> None:
    code, payload = req("POST", "/api/v1/auth/login", body={
        "email": "superadmin@staging.example.com",
        "password": os.environ["STAGING_SUPERADMIN_PASSWORD"],
    })
    check("1) Login SuperAdmin", code == 200, str(payload))
    su = payload["access_token"]

    code, payload = req(
        "POST",
        "/api/v1/companies",
        token=su,
        body={
            "name": f"Empresa Smoke {os.getpid()}",
            "admin_email": f"admin.smoke.{os.getpid()}@staging.example.com",
            "admin_full_name": "Admin Smoke",
            "admin_password": "Password1234",
        },
    )
    check("2) Crear Empresa + admin inicial", code == 201, str(payload)[:120])
    cid = payload["id"]
    admin_email = f"admin.smoke.{os.getpid()}@staging.example.com"

    code, payload = req(
        "POST",
        "/api/v1/auth/login",
        body={"email": admin_email, "password": "Password1234"},
    )
    check("3) Login admin nuevo", code == 200, str(payload)[:60])
    new_admin = payload["access_token"]

    code, payload = req(
        "POST",
        "/api/v1/auth/select-company",
        token=new_admin,
        body={"company_id": cid},
    )
    check("4) Select-company", code == 200, str(payload)[:60])
    ctx = payload["access_token"]

    other_id = max(cid - 1, 1)
    code, _ = req("GET", f"/api/v1/companies/{other_id}", token=ctx)
    check(f"5) Admin A GET empresa {other_id} → 403", code == 403, f"got {code}")

    code, _ = req("POST", "/api/v1/companies", token=ctx, body={"name": "Hack"})
    check("6) Admin empresa crear empresa → 403", code == 403, f"got {code}")

    code, payload = req(
        "POST",
        "/api/v1/users",
        token=ctx,
        body={
            "email": "operario@staging.example.com",
            "full_name": "Operario",
            "password": "Password1234",
        },
    )
    check("7) Admin crea usuario en su empresa", code == 201, str(payload)[:60])

    code, payload = req("GET", "/api/v1/auth/me", token=ctx)
    check("8) /me devuelve permisos del admin", code == 200 and "users.create" in payload.get("permissions", []))

    code, _ = req("POST", "/api/v1/auth/leave-company", token=ctx)
    check("9) Leave-company (volver a plataforma)", code == 200)

    code, payload = req(
        "POST",
        "/api/v1/auth/login",
        body={"email": admin_email, "password": "Password1234"},
    )
    check("10) Re-login + select-company", code == 200)
    ctx2 = req(
        "POST",
        "/api/v1/auth/select-company",
        token=payload["access_token"],
        body={"company_id": cid},
    )[1]["access_token"]

    code, payload = req("GET", "/api/v1/auth/me", token=ctx2)
    check(
        "11) Permisos persistidos tras re-login",
        code == 200 and "users.create" in payload.get("permissions", []),
    )

    code, payload = req("GET", "/api/v1/companies", token=su)
    check(
        "12) SuperAdmin lista todas las empresas",
        code == 200 and payload["total"] >= 3,
        f"total={payload.get('total')}",
    )

    code, payload = req("GET", "/api/v1/dashboard/superadmin", token=su)
    check(
        "13) Dashboard SuperAdmin con KPIs",
        code == 200 and payload["kpis"]["total_superadmins"] >= 1,
        json.dumps(payload["kpis"]),
    )

    code, payload = req("GET", "/api/v1/roles", token=ctx2)
    check(
        "14) Admin ve roles de su empresa",
        code == 200 and any(r["name"] == "Administrador" for r in payload.get("items", [])),
    )

    # Aislamiento negativo: admin.smoke intenta GET a empresa 1 (que existe).
    code, _ = req("GET", "/api/v1/companies/1", token=ctx2)
    check("15) Admin smoke GET empresa 1 → 403", code == 403, f"got {code}")

    print("OK — smoke E2E completo")


if __name__ == "__main__":
    main()