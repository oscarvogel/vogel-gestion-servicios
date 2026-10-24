"""Agrega a la bitacora la causa raiz del '0 ordenes': el proxy resolvia en IPv6."""
from __future__ import annotations

import io

RUTA = "docs/sesion-2026-10-23-tecnicos.md"

NUEVO = """### 5.8 La causa de fondo del "0 ordenes": el proxy resolvia en IPv6

Despues de arreglar la sesion (5.3) el listado seguia mostrando "0 ordenes" en el
navegador, aunque la API llamada desde un script devolvia 200 con las 9.316 ordenes.
La diferencia era **el camino**: el script pegaba al backend por HTTPS, el navegador
pasa por el proxy nginx del frontend.

En el log de nginx del frontend:

```
[error] connect() failed (111: Connection refused) while connecting to upstream,
request: "GET /api/v1/work-orders?page=1&page_size=25",
upstream: "http://[fd04:36e8:6aaa::11]:8000/api/v1/work-orders?page=1&page_size=25"
```

**Causa:** el `resolver` de nginx (el DNS embebido de Docker, 127.0.0.11) devuelve
**las dos** direcciones del contenedor del backend: la A (IPv4) y la AAAA (IPv6). El
backend arranca con `uvicorn app.main:app --host 0.0.0.0 --port 8000`: escucha en IPv4
y **no** en IPv6. nginx elegia al azar entre las dos, y la mitad de las peticiones al
backend fallaban con "connection refused". La app recibia un 502, `load()` lo tragaba
en un toast y la pantalla quedaba en cero: "Todavia no hay ordenes de trabajo".

Por eso:
- desde un script (que pega al backend por HTTPS) siempre se veian 9.316 ordenes;
- en el navegador era intermitente, y a veces se veia la lista y a veces no;
- el `Promise.all` del `onMounted` (antes del fix) se caia con un solo fallo.

**Arreglo:** `frontend/nginx.conf` -> `resolver 127.0.0.11 valid=30s ipv6=off;` Con
`ipv6=off` nginx solo pide direcciones IPv4, que son las que el backend escucha.

**Como se comprueba:** `backup/_work/probar_proxy.py` pega 20 veces al backend a traves
del proxy (se espera 401 sin token). Antes del fix caia la mitad; ahora **20/20**.

Test de estructura: `frontend/src/__tests__/nginx-upstream.test.ts` (2 tests) deja
escrito que el resolver tiene que llevar `ipv6=off` y que el backend se resuelve por
nombre (una IP fija horneada en la imagen queda vieja en cada deploy).

### 5.9 Lecciones de este Diagnostico

1. **Probar por el mismo camino que el usuario.** Un script que pegue al backend no
   prueba el proxy: la mitad de los fallos vivian ahi.
2. **El codigo HTTP del navegador importa.** El log de acceso de nginx del frontend
   tiene el codigo de cada peticion; el de Coolify solo da estado, y el de la API no
   muestra ni el cuerpo.
3. **Un 502/499 en el log del proxy explica una pantalla vacia.** `499` es el cliente
   que corta la peticion; `connect() failed (111)` es el upstream que no acepta.

---

"""


def main() -> None:
    texto = io.open(RUTA, encoding="utf-8").read()
    crlf = texto.count("\r\n") > texto.count("\n") / 2
    nl = "\r\n" if crlf else "\n"
    i = texto.find("## 6. Pendientes")
    if i < 0:
        raise SystemExit("No se encontro la seccion de pendientes")
    bloque = texto[:i] + NUEVO.replace("\n", nl) + texto[i:]
    io.open(RUTA, "wb").write(bloque.encode("utf-8"))
    print("Bitacora actualizada")


if __name__ == "__main__":
    main()
