"""Actualiza la bitacora: puerto cerrado + verificacion en navegador."""
from __future__ import annotations

import io

RUTA = "docs/sesion-2026-10-23-tecnicos.md"

NUEVO = """### 5.6 Verificacion en el navegador (staging)

Con el backend y el frontend desplegados, se comprobo en el navegador (la pestana del
usuario, en la sesion real de staging):

| Que se verifico | Resultado |
| --- | --- |
| Listado de ordenes | "9316 ordenes en esta empresa" con la tabla llena |
| Combo de tecnicos de la recepcion | La lista (44 del maestro) abre **debajo del campo** y se puede elegir: "Alladio" quedo seleccionado con su boton "Quitar" |
| Filtro del combo | Escribir "allad" deja solo "Alladio" (filtra por contiene, ignora acentos) |
| "+ Nueva OT" del dashboard | La URL `/app/work-orders?new=1` abre el modal de "Nueva recepcion" y despues se limpia el query de la URL |
| Panel "Tecnicos asignados" del detalle de la OT | Aparece con el campo "Agregar un tecnico..." y la lista de disponibles |
| Sesion | La barra superior muestra la empresa (Electrotecniref) y el boton "Cambiar" |

La sesion del navegador se recuperó yendo a `/company-selector` y eligiendo la empresa:
el token que estaba en el navegador habia quedado en modo plataforma. Con el fix del
refresh token, eso ya no se repite, y `bootstrap()` vuelve a elegir sola la empresa si la
sesion se recarga sin ella guardada (cubierto por
`frontend/src/__tests__/sesion-empresa.test.ts`).

Puerto de la base: se cerro (`is_public=false`, `public_port=''`) al terminar el
diagnostico; la API de staging sigue respondiendo 200 con las 9.316 ordenes.

### 5.7 Como se subio a staging (y lo que costo)

La cola de deploys de Coolify es **compartida entre proyectos**: un deploy de otro
proyecto ("chat-central") estuvo `in_progress` un rato largo y dejo en cola los nuestros
(los deploys 1661/1662 del backend y el frontend). Durante la espera, el navegador
pide un asset que todavia no existe y el nginx responde **200 con el index.html** en
lugar del JS: la pagina queda en "Verificando tu sesion..." sin error visible. Si pasa
algo raro con la pagina en staging, primero mirar el estado de los deploys.

Cada deploy hay que pedirlo con el commit explicito:

```powershell
$body = @{ git_branch = 'feature/cyberbrain-migracion'; git_commit_sha = 'HEAD' } | ConvertTo-Json
Invoke-RestMethod -Uri "$api/api/v1/applications/<uuid>" -Headers $h -Method Patch -Body $body -ContentType 'application/json'
Invoke-RestMethod -Uri "$api/api/v1/deploy?uuid=<uuid>&force=true" -Headers $h -Method Post -ContentType 'application/json'
```

Y para saber si el bundle nuevo quedo servido hay que mirar el **nombre del asset** que
devuelve el `index.html` (`assets/index-<hash>.js`): si el hash no cambio, el deploy
todavia no termino o quedo en cola.

---

"""


def main() -> None:
    texto = io.open(RUTA, encoding="utf-8").read()
    crlf = texto.count("\r\n") > texto.count("\n") / 2
    nl = "\r\n" if crlf else "\n"

    i = texto.find("## 6. Pendientes")
    if i < 0:
        raise SystemExit("No se encontro la seccion de pendientes")

    # El puerto de la base ya esta cerrado: se saca de los pendientes.
    pendientes = texto[i:]
    pendientes = pendientes.replace(
        "- [ ] **Cerrar el puerto p\u00fablico de la base de staging** "
        "(`is_public=true`, `public_port=33061`):\n"
        "      se abri\u00f3 para diagnosticar el listado y hay que volver a cerrarlo\n"
        "      (`PATCH /api/v1/databases/diamcot1wyytezyasugd5biv {is_public=false; public_port=''}`).\n",
        "- [x] **Puerto p\u00fablico de la base de staging cerrado** (`is_public=false`, "
        "`public_port=''`): se abri\u00f3 para diagnosticar el listado y qued\u00f3 cerrado "
        "al terminar.\n",
    )

    bloque = texto[:i] + NUEVO.replace("\n", nl) + pendientes
    io.open(RUTA, "wb").write(bloque.encode("utf-8"))
    print("Bitacora actualizada")


if __name__ == "__main__":
    main()
