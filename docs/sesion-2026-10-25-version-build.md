# La version del sistema ahora cambia con cada despliegue (2026-10-25)

Bitacora de la sesion en que el pie del menu paso de decir siempre `v0.2 · Modo Empresa`
a decir que build esta vivo: `v0.2 · ecf258d · Modo Empresa`.

El pedido era concreto: *"lo que no cambia aun es la version del sistema, eso habiamos
visto para que vaya tomando cada despliegue"*. O sea, no un numero de version que haya
que subir a mano cada vez que se publica, sino algo que se sepa **cual es el build que
esta corriendo**, sin adivinar.

| Que | Donde | Estado |
|---|---|---|
| El commit del deploy, expuesto por la API | `backend/app/core/build_info.py` | En staging y en produccion |
| `/health` dice que version y que commit estan vivos (sin login) | `backend/app/main.py` | En staging y en produccion |
| `/auth/me` trae el bloque `build` | `backend/app/api/v1/schemas.py`, `auth.py` | En staging y en produccion |
| Vite inyecta version, sha y momento del build | `frontend/vite.config.ts`, `frontend/src/env.d.ts` | En staging y en produccion |
| El pie del menu arma el texto con el commit | `frontend/src/components/Sidebar.vue` | En staging y en produccion |
| El sha del deploy queda escrito en el bundle | `frontend/Dockerfile` | En staging y en produccion |

## Que se decide mostrar

Hay dos formas de resolver "que version esta viva":

1. **Un numero de version** (`v0.2` -> `v0.3`) que hay que subir a mano en el
   `package.json` antes de cada release. Se olvida, y cuando se olvida el pie miente.
2. **El commit del deploy**: sale solo, es automatico y es trazable. Si el pie dice
   `ecf258d`, se puede ir al repo y ver exactamente ese commit.

Se eligio la segunda. El `v0.2` sigue estando (sale del `package.json` del frontend), pero
deja de ser el unico dato: ahora convive con el commit, que es lo que cambia.

El backend tiene su propio numero (`0.1.0`) y no coincide con el del frontend (`0.2`).
Se dejo asi: son dos paquetes distintos y forzar que coincidan seria mentir sobre uno de
los dos. Lo que importa para saber que build esta vivo es el commit, que es el mismo de
las dos puntas.

## De donde sale el commit

`SOURCE_COMMIT` es una variable que Coolify define en el contenedor con el commit que se
despliega. El backend la lee (probando varios nombres, porque el de Coolify cambio entre
versiones: `SOURCE_COMMIT`, `SOURCE_COMMIT_SHA`, `GIT_COMMIT`, `COMMIT_SHA`) y la expone
en dos lugares:

- **`/health`** -> `{"status":"ok","version":"0.1.0","commit":"ecf258d..."}`. Se puede
  preguntar que build esta vivo **sin login**, que es lo que sirve para un chequeo rápido
  o para un monitor.
- **`/auth/me`** -> agrega el campo `build`. El frontend lo pide con la sesion ya
  iniciada, asi que el pie lo tiene sin hacen un pedido extra.

### El sha en el bundle: por que queda vacio en Coolify

El frontend tambien lleva un `__BUILD_SHA__` escrito en el bundle (Vite lo define al
compilar), para que el pie tenga un dato aunque la API no responda. En un build local
sale de `git rev-parse`. En Coolify **queda vacio**, y se verifico por que:

- El contexto de build del frontend es `/frontend` (el `base_directory` de la app), asi que
  la imagen no tiene la carpeta `.git` y no hay forma de sacar el commit de adentro.
- Coolify **no** pasa `SOURCE_COMMIT` como build arg al build del Dockerfile: se
  declaro `ARG SOURCE_COMMIT` y se comprobo en el bundle servido que el sha seguia
  vacio. (La API de Coolify no expone el ajuste "Source commit availability", asi que
  tampoco se puede cambiar desde aca.)

El `ARG SOURCE_COMMIT` quedo declarado igual, con su comentario: si alguien activa en
Coolify "Source commit availability: Available during build", el bundle sale con el sha
sin tocar una linea de codigo.

**La cadena del pie** (en este orden, de mas confiable a menos):

1. El commit de la API (`session.me?.build?.commit`): siempre correcto.
2. El sha del bundle: sirve en builds locales y si se habilita el build arg.
3. La fecha del build (`build 25/10 08:22`): el ultimo recurso.

El orden importa. Durante la ventana de un deploy de produccion pasa que el frontend
nuevo ya esta sirviendo y el backend viejo todavia no (el backend tarda ~7 minutos en
construirse y el frontend ~2). En esa ventana la API todavia no trae `build` y el pie cae
a la fecha del bundle, que es la verdad de ese momento en vez de un commit viejo.

## Los tests

| Suite | Resultado |
|---|---|
| Frontend (`npm test`) | **89 tests** en verde (86 del PR #120 + 3 nuevos de `version-build.test.ts`) |
| Backend (`pytest -q`, venv propio) | **355 tests** en verde (353 + 2 nuevos en `test_health.py`) |

Los tests nuevos cubren: que el pie muestre el commit de la API, que cae al sha del
bundle cuando la API no trae commit, y que cae a la fecha del build cuando no hay nada de
eso. Del lado del backend, que `/health` devuelva el commit cuando el entorno lo expone
(el test lo setea con `monkeypatch`).

## Lo que se valido en staging (contra el sistema real)

- **`/health`**:
  `{"status":"ok","version":"0.1.0","commit":"ecf258d3833f52bcc4323106b56531b18709eb4f"}`.
- **`/auth/me`** con login real: el bloque `build` llega con el commit.
- **El pie, con Playwright**, en 1638x969 y 1366x768, en tema oscuro y claro:
  `v0.2 · ecf258d · Modo Empresa`, **sin errores de consola y sin peticiones fallidas**.
- **La prueba de que cambia**: se hicieron dos despliegues seguidos y el pie paso de
  `c40be83` a `ecf258d` **solo**, sin tocar nada. Eso es exactamente lo que se pedia.

## Lo que se valido en produccion

- **El deploy fue automatico**: al mergear el PR a `main` dispara el webhook y las dos
  apps de produccion se desplegaron solas, sin tocar la consola de Coolify.
- **`/health`** de produccion:
  `{"status":"ok","version":"0.1.0","commit":"3c2c96c4629e42b2b16cd514105873d690a84765"}`.
- **El pie, con Playwright**, en 1638x969 y 1366x768, en tema oscuro y claro:
  `v0.2 · 3c2c96c · Modo Empresa`, **sin errores de consola y sin peticiones fallidas**.

## Lo que se rompio en el camino (y como se resolvio)

### 1. El watcher de deploy nunca ve el estado "terminado"

`GET /api/v1/deployments` de Coolify **solo lista los deploys en curso**: cuando uno
termina desaparece de la lista, no hay estado terminal que leer. Un watcher escrito como
"esperar a que el estado sea successful" nunca lo ve y termina en timeout con un falso
"fallo". La forma correcta es tratar **"ya no esta en la lista" como exito**.

### 2. `/health` no esta en `/api/v1`

El backend expone `/health` en la raiz y el nginx del frontend lo proxea con un
`location = /health`. Buscarlo en `/api/v1/health` da 404 y hace pensar que el backend
esta caido cuando no lo esta.

### 3. El bundle no puede saber el commit en Coolify

Ver la seccion de arriba: el contexto de build es `/frontend` (sin `.git`) y Coolify no
pasa `SOURCE_COMMIT` como build arg. Se comprobo **en el bundle servido**, no leyendo el
Dockerfile: el sha seguia vacio despues de declarar el `ARG`.

### 4. La cola del server de Coolify es compartida

Los dos deploys de staging (frontend y backend) y los de produccion se turnaron en la
cola con otros proyectos del mismo server (`mantenimiento-staging`, `fasa-erp-web-staging`,
`race-center`). `queued` durante diez minutos no es un deploy trabado: es cola.

### 5. PowerShell 5.1 y los `.ps1` sin BOM

Un `.ps1` sin BOM con una tilde en un identificador no parsea (PowerShell 5.1 lo lee como
ANSI). Los watchers que se escriben en `%TEMP%` van en **ASCII puro**. Y `gh --jq` con
comillas dobles se rompe: el PowerShell se come las comillas internas y el jq falla con
`unexpected token`; hay que usar comillas simples afuera.
