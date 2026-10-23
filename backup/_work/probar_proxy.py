r"""Prueba la estabilidad del proxy del frontend contra el backend.

Antes del fix (resolver sin ipv6=off) nginx elegia al azar entre la A y la AAAA del
contenedor del backend, y como el backend solo escucha en IPv4, la mitad de las
peticiones fallaban con "connection refused".

Ojo: este test da 20/20 *con* el bug, porque nginx reintenta la peticion contra
otra direccion y al final responde igual. Lo que prueba el fix es el log del
nginx: cero lineas con IPv6.

Uso:
    .\backend\.venv\Scripts\python.exe backup\_work\probar_proxy.py [n]
"""
from __future__ import annotations

import sys
import time
import urllib.error
import urllib.request

BASE = "https://gestion-vogel.186.5.245.12.sslip.io"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 20


def pedir(ruta: str) -> tuple[int, str]:
    req = urllib.request.Request(BASE + ruta, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=25) as res:
            return res.status, ""
    except urllib.error.HTTPError as exc:
        return exc.code, f"HTTP {exc.code}"
    except Exception as exc:
        return 0, f"{type(exc).__name__}: {exc}"


def main() -> None:
    fallos = 0
    for i in range(N):
        status, err = pedir("/api/v1/work-orders/statuses")
        if status != 401:
            fallos += 1
            print(f"  #{i + 1}: {status} {err}")
        time.sleep(0.2)
    print(f"\n{N - fallos}/{N} peticiones llegaron al backend (se espera 401 sin token).")
    if fallos:
        print(f"FALLAN {fallos}")
        raise SystemExit(1)
    print("OK: el proxy llega siempre al backend.")


if __name__ == "__main__":
    main()
