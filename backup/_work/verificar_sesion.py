"""Prueba la cadena de sesion contra un servidor local o de staging.

Uso:
    .\\backend\\.venv\\Scripts\\python.exe backup\\_work\\verificar_sesion.py [base_url]
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/api/v1").rstrip("/")
# Las credenciales del staging van por variable de entorno: al repo no llega ninguna.
EMAIL = os.environ.get("STAGING_EMAIL", "admin@electrotecniref.com.ar")
PASSWORD = os.environ.get("STAGING_PASSWORD", "")


def call(method: str, path: str, body=None, token: str | None = None):
    url = BASE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return res.status, res.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:
        return 0, f"{type(exc).__name__}: {exc}"


def main() -> None:
    if not PASSWORD:
        print("Falta STAGING_PASSWORD (la password del usuario del staging).")
        raise SystemExit(2)
    print(f"== {BASE}")
    fallos: list[str] = []

    status, raw = call("POST", "/auth/login", {"email": EMAIL, "password": PASSWORD})
    print(f"1) login ................ {status}")
    if status != 200:
        print("   ", raw[:300])
        raise SystemExit(1)
    login = json.loads(raw)

    status, raw = call("GET", "/auth/me", token=login["access_token"])
    me = json.loads(raw) if status == 200 else {}
    membresias = me.get("memberships") or []
    company_id = membresias[0]["company_id"] if membresias else 3
    print(f"   membresias: {company_id}")

    status, raw = call("POST", "/auth/select-company", {"company_id": company_id}, token=login["access_token"])
    print(f"2) select-company ....... {status}")
    if status != 200:
        print("   ", raw[:300])
        raise SystemExit(1)
    seleccionado = json.loads(raw)
    refresh = seleccionado.get("refresh_token")
    print(f"   devuelve refresh_token: {bool(refresh)}")
    if not refresh:
        fallos.append("select-company no devuelve refresh_token")

    status, raw = call("POST", "/auth/refresh", {"refresh_token": refresh or "x"})
    print(f"3) refresh .............. {status}")
    if status != 200:
        fallos.append(f"el refresh devolvio {status}: {raw[:200]}")
        print("   ", raw[:200])
    else:
        token_nuevo = json.loads(raw)["access_token"]
        status, raw = call("GET", "/companies/current", token=token_nuevo)
        print(f"4) companies/current .... {status}")
        if status != 200:
            fallos.append(f"companies/current con el token renovado devolvio {status}: {raw[:200]}")
        else:
            print(f"   empresa: {json.loads(raw).get('name')}")

        status, raw = call("GET", "/work-orders?page=1&page_size=25", token=token_nuevo)
        print(f"5) work-orders .......... {status}")
        if status != 200:
            fallos.append(f"work-orders devolvio {status}: {raw[:200]}")
        else:
            data = json.loads(raw)
            print(f"   total: {data.get('total')} | items: {len(data.get('items') or [])}")

    print()
    if fallos:
        print("FALLA:")
        for f in fallos:
            print("  -", f)
        raise SystemExit(1)
    print("OK")


if __name__ == "__main__":
    main()
