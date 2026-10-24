"""Reemplaza la seccion 5.3 de la bitacora por la version corregida.

Se hace con Python porque el archivo tiene finales de linea CRLF y el editor
no encuentra el bloque con saltos LF.
"""
from __future__ import annotations

import io

RUTA = "docs/sesion-2026-10-23-tecnicos.md"

NUEVO = """### 5.3 El listado mostraba "0 órdenes" (el token había perdido la empresa)

Lo primero que se hizo fue llamar a la API de staging **como el navegador**: login real
(`admin@electrotecniref.com.ar`), `POST /auth/select-company` con la empresa 3 y después
`GET /work-orders?page=1&page_size=25`. La respuesta fue **200 con `total: 9316` y 25
ítems**: el backend estaba bien.

Pero el navegador seguía mostrando "0 órdenes" con el bundle nuevo y una recarga. La
prueba que faltaba era mirar **qué código HTTP devolvía el navegador**, y no sólo el que
devolvía mi script. En el log de acceso de nginx del frontend:

```
GET /api/v1/work-orders?page=1&page_size=25   409
GET /api/v1/work-orders/statuses               409
GET /api/v1/technicians                        409
GET /api/v1/companies/current                  409
```

**409 "Active company required"**: el token que tenía el navegador **no traía `company_id`**.
O sea, no era que el listado viniera vacío: **todas** las consultas de empresa fallaban, y
`load()` se tragaba el error en un toast, así que la pantalla mostraba el estado vacío sin
explicar nada.

#### La causa raíz (de backend)

`create_refresh_token(user_id)` **no guardaba la empresa**:

- `/auth/login` devuelve un refresh token sin empresa (correcto: el usuario todavía no
  eligió empresa).
- `/auth/select-company` devolvía **solo** el access token: el refresh token guardado en el
  navegador seguía siendo el del login, sin empresa.
- `/auth/refresh` leía `company_id` del refresh token → siempre `None` → devolvía un access
  token **sin empresa**.

O sea: **cada vez que se renovaba el access token, el usuario volvía al modo plataforma** y
todas las consultas de empresa empezaban a dar 409. Como el token de acceso dura poco, el
problema aparecía "un rato después de loguearse" y se veía como si la pantalla se rompiera
sola.

**Arreglo (backend):**

- `create_refresh_token(user_id, company_id=None)` → el refresh token lleva la empresa.
- `/auth/select-company` devuelve además un **refresh token nuevo con la empresa**.
- `/auth/leave-company` devuelve un refresh token sin empresa (modo plataforma).

**Arreglo (frontend):**

- `selectCompany()`, `leaveCompany()` y el refresh de `api.ts` guardan el refresh token
  que devuelve el backend (antes solo guardaban el access token).
- `bootstrap()`: si la sesión se recarga **sin empresa guardada** y el usuario tiene **una
  sola** empresa activa, la elige solo. Antes la app entraba igual a las vistas de empresa
  con un token sin empresa y todo daba 409. Con varias empresas sigue yendo al selector.

#### Dos detalles que costaron tiempo y conviene no repetir

- **El token del login no trae `company_id`**: sin `POST /auth/select-company`, todo lo que
  sea de empresa responde **409 "Active company required"** (no 401). El login del frontend
  es el que resuelve ese paso.
- **El log de acceso de Coolify no muestra el cuerpo**, solo el estado. Para ver qué recibe
  el navegador hay que llamar a la API con el mismo token (`backup/_work/probe_staging.py`)
  **o leer el log de nginx del frontend**, que sí tiene el código HTTP de cada pedido.

Como defensa, `load()` valida la forma de la respuesta (`Array.isArray` sobre `items`,
`total` numérico) para que una respuesta inesperada muestre el estado vacío en vez de
romper el render, `loadStatuses()` tiene `try/catch` y el deep-link no depende de que las
cargas tengan éxito.

### 5.4 Cómo se diagnosticó (para no repetirlo)

| Paso | Qué se hizo | Qué apareció |
| --- | --- | --- |
| 1 | `GET /api/v1/work-orders` con login + `select-company` desde un script | **200 con 9.316** → el backend estaba bien |
| 2 | Log de nginx del frontend | **409 en todas** las consultas de empresa → el token no tenía empresa |
| 3 | `GET /api/v1/auth/me` del navegador | 200 con 1 membresía (empresa 3) |
| 4 | Botón "cambiar empresa" de la barra superior | **no estaba** → `activeCompany` era `null` → no había empresa guardada en el navegador |

El paso 4 es el que cierra el círculo: sin empresa guardada, `bootstrap()` no llamaba a
`select-company` y el token se quedaba en modo plataforma.

---
"""


def main() -> None:
    crudo = io.open(RUTA, "rb").read()
    texto = crudo.decode("utf-8")
    crlf = texto.count("\r\n") > texto.count("\n") / 2
    nl = "\r\n" if crlf else "\n"

    i = texto.find("### 5.3 ")
    j = texto.find("## 6. Pendientes")
    if i < 0 or j < 0 or j < i:
        raise SystemExit(f"No se encontró el bloque (i={i}, j={j})")

    bloque = texto[i:j]
    nuevo = NUEVO.replace("\n", nl)
    salida = texto[:i] + nuevo + texto[j:]
    io.open(RUTA, "wb").write(salida.encode("utf-8"))
    print(f"Reemplazado: {len(bloque)} chars -> {len(nuevo)} chars (nl={nl!r})")


if __name__ == "__main__":
    main()
