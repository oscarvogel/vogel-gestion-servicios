"""Sondeo de la API de staging: login + listado de ordenes de trabajo.

Se usa para ver el cuerpo REAL que recibe el navegador (el log de Coolify solo
muestra el estado HTTP, no el body). No escribe nada: solo GET.

Uso:
    .\\backend\\.venv\\Scripts\\python.exe backup\\_work\\probe_staging.py
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

BASE = "https://gestion-vogel.186.5.245.12.sslip.io/api/v1"
# Las credenciales del staging van por variable de entorno: al repo no llega ninguna.
EMAIL = os.environ.get("STAGING_EMAIL", "admin@electrotecniref.com.ar")
PASSWORD = os.environ.get("STAGING_PASSWORD", "")


def call(method: str, path: str, body=None, token: str | None = None):
    url = BASE + path
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            raw = res.read().decode("utf-8", "replace")
            return res.status, raw
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:  # red, TLS, timeout
        return 0, f"{type(exc).__name__}: {exc}"


def main() -> None:
    if not PASSWORD:
        print("Falta STAGING_PASSWORD (la password del usuario del staging).")
        raise SystemExit(2)
    status, raw = call("POST", "/auth/login", {"email": EMAIL, "password": PASSWORD})
    print("== login:", status)
    if status != 200:
        print(raw[:800])
        return
    bundle = json.loads(raw)
    token = bundle["access_token"]
    print("   refresh:", bool(bundle.get("refresh_token")))

    # El token de login no trae empresa: hay que elegirla, como hace el frontend.
    status, raw = call("GET", "/auth/me", token=token)
    me = json.loads(raw)
    print("\n== GET /auth/me:", status)
    print("   memberships:", json.dumps(me.get("memberships"), ensure_ascii=False)[:500])
    members = [m for m in me.get("memberships", []) if m.get("active")]
    if members:
        cid = members[0]["company_id"]
        status, raw = call("POST", "/auth/select-company", {"company_id": cid}, token=token)
        print(f"\n== POST /auth/select-company ({cid}): {status}")
        if status == 200:
            token = json.loads(raw)["access_token"]
        else:
            print("   ", raw[:400])

    for path in ("/companies/current", "/company-parameters", "/work-orders/statuses"):
        status, raw = call("GET", path, token=token)
        print(f"\n== GET {path}: {status}")
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                keys = {k: v for k, v in data.items() if k in ("id", "name", "company_id", "timezone", "email", "is_superadmin")}
                print("   ", keys if keys else list(data)[:15])
        except Exception:
            print("   ", raw[:300])

    status, raw = call("GET", "/work-orders?page=1&page_size=25", token=token)
    print(f"\n== GET /work-orders?page=1&page_size=25: {status}")
    try:
        data = json.loads(raw)
    except Exception:
        print("   cuerpo no JSON:", raw[:800])
        return
    if isinstance(data, dict):
        items = data.get("items")
        print("   claves:", list(data))
        print("   total:", data.get("total"), "| items:", (len(items) if isinstance(items, list) else items))
        if isinstance(items, list) and items:
            print("   primer item:", json.dumps(items[0], ensure_ascii=False)[:400])
    else:
        print("   ", str(data)[:400])


if __name__ == "__main__":
    main()
