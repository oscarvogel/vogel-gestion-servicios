# Integracion del PR #118: el listado y el detalle de la OT se descargan visualmente (2026-10-24)

Bitacora de la integracion del PR #118 de Roman Vogel Corach (`romanvsc`), del
despliegue en los dos ambientes y de lo que se verifico en el camino.

El PR es **solo frontend**: reorganiza la pantalla de ordenes de trabajo para bajar la
carga visual, sin tocar el backend.

| Que | Donde | Estado |
|---|---|---|
| Listado de OT: color del estado solo en la etiqueta, la fila abre la OT, falla informada a dos lineas, filtros plegados | `frontend/src/views/WorkOrdersView.vue` | En staging y en produccion |
| Detalle de OT: encabezado `OT #n`, resumen a la izquierda, pasos del taller numerados a la derecha, un solo boton primario (el del paso pendiente), avisos e historial plegados | `frontend/src/views/WorkOrdersView.vue` | En staging y en produccion |
| Etiquetas de los 15 tipos de evento del historial | `frontend/src/views/WorkOrdersView.vue` | En staging y en produccion |
| Dos tests que buscaban el boton "Abrir OT" ahora toman `.work-order-link` | `frontend/src/__tests__/tecnicos*.test.ts` | En staging y en produccion |
| Capturas antes/despues | `Cambios_Fase1/`, `Cambios_Fase2/` | En el repo |

## El orden del despliegue

El merge a `main` **despliega produccion solo**, por webhook. Staging es manual. Ese
detalle define el orden, porque si se mergea primero, produccion ya sale antes de que
alguien mire staging.

1. Se publico el commit del PR en una rama del repo (`staging/pr-118`) y se apunto
   **solo `staging-frontend`** a esa rama: el backend no cambio, asi que no hace falta
   tocarlo.
2. Se desplego staging a mano y se valido con datos reales.
3. recien ahi se mergeo a `main`, que encola el deploy de produccion.
4. Al final, `staging-frontend` volvio a `main` y se redesployo, para que los dos
   ambientes queden en el mismo commit.

## Lo que se verifico antes de mergear

El PR viene de un **fork** (`romanvsc/vogel-gestion-servicios`), y por eso la CI de
GitHub quedo en `action_required`: los workflows de un fork ajeno no corren sin
aprobacion. El PR **nunca tuvo un check verde**. Como no hay quien apruebe el workflow
desde el panel en cada PR de Roman, la validacion se hizo local:

| Chequeo | Resultado |
|---|---|
| `npm test` (frontend) | 75 tests, 14 archivos, en verde |
| `npm run build` (frontend) | bundle generado sin errores |
| `pytest -q` (backend, sobre `main`) | 352 tests en verde (3m34s) |
| `git diff origin/main origin/staging/pr-118 -- frontend backend` | **vacio**: el codigo que se valido en staging es identico al que quedo en `main` |

## Lo que se valido en staging (con los datos reales)

No con capturas de Roman, sino contra el sistema andando, con la base de staging y
las 9.316 OT de Electrotecniref.

- **Bundle**: `scripts/verify-deploy.ps1` contra
  `https://gestion-vogel.186.5.245.12.sslip.io` con el marcador `work-order-link`, que
  existe **solo** en el codigo nuevo (el bundle anterior no lo tiene). Resultado: OK,
  API en `401 json` (el proxy llega al backend) y modo same-origin.
- **Datos**: login real + `POST /auth/select-company` (empresa 3) + `GET /work-orders`
  -> `total: 9316`, 25 items.
- **Pantalla** (Playwright, 1638x969 y 1366x768, que son las dos resoluciones que
  importa): 25 filas, 25 botones `.work-order-link`, filtros plegados con el boton en
  el encabezado, detalle con `OT #9316`, 4 pasos numerados, 4 bloques de resumen, 2
  secciones plegadas y **un solo boton primario**. Sin errores de consola y sin
  peticiones a la API que fallen.

## Lo que se rompio en el camino (y como se resolvio)

### 1. El PR no tiene CI verde, y no por culpa del codigo

Es lo primero que hay que mirar en un PR de un fork: `gh pr checks` no reporta nada y
`gh run list --branch <rama>` muestra el workflow en `action_required`. No es un test
roto: **el workflow nunca corrio**. Por eso la validacion se hizo local antes de
mergear.

### 2. La rama del PR no esta en `origin`

`git fetch origin ui/ordenes-de-trabajo-menos-cargadas` falla con
`couldn't find remote ref`: la rama vive en el fork. Para poder mirarla en staging
(no en un entorno local) se publico el **commit exacto** (`569292b`) en una rama del
repo propio:

```bash
git push origin 569292b:refs/heads/staging/pr-118
```

Apuntar la app a un commit de un fork habria hecho depender a staging de que el fork
no se borre.

### 3. El listado de deployments de la API de Coolify miente

`GET /api/v1/deployments` **ignora** `per_page`, `page` y `status`: con cualquiera de
esos filtros devuelve lo mismo. Peor: devuelve **solo los deploys en curso**, asi que
desaparecen de la lista en cuanto terminan. Para saber si el tuyo sigue vivo hay que
mirarlo mientras corre, no despues. Si se mira despues, "no esta en la lista" se lee
como "no hay deploy" y parece que el ambiente quedo en la version anterior.

### 4. Dos webhooks de GitHub, uno por tipo de app

El repo tiene dos webhooks, los dos con la misma URL de Coolify
(`/webhooks/source/github/events/manual`) y los dos con evento `push`. Cada uno
responde con la app que le corresponde:

```
hook 689866758 -> production-backend  "Deployment queued."
hook 689872280 -> production-frontend "Deployment queued."
```

Un push a una rama que no sea `main` responde `No matching application or invalid
signature.` y a una rama borrada, `Nothing to do. Branch deleted.` O sea: el webhook
**no es un error**, y un `failed` en la entrega no significa que el deploy haya fallado.

### 5. Los deploys se encolan por servidor

Al mergear, los dos deploys de produccion entraron: el frontend `in_progress` y el
backend `queued`. Es normal: es cola, no un deploy trabado. (`queued` durante diez
minutos no es un deploy trabado: es cola.)

### 6. La credencial de staging que servia antes ya no sirve

`admin@electrotecniref.com.ar` (la que se le mando al cliente por mail) **no** entra
con ninguna de las variables de password del backend de staging. Las que si funcionan
son las del seed: `superadmin`, `usuario.a`, `usuario.b` y `usuario.shared`
(`STAGING_*_PASSWORD` en las variables de `staging-backend`).

De esas, las tres de empresa dan **403** al pedir ordenes de trabajo: el rol de
miembro no alcanza para `work_orders.view`. La que sirve es el **superadmin**, con el
que hay que elegir empresa (`POST /auth/select-company`, empresa 3 = Electrotecniref)
antes de pedir las OT.

La contrasena nunca se escribio en ningun lado de esta sesion: el script de
validacion la lee de la API de Coolify y la usa en memoria.

### 7. `PATCH /applications/{uuid}` devuelve un objeto sin los campos del patch

Devuelve 200 con el cuerpo sin `git_branch` ni `git_commit_sha`. No es un error: hay
que **releer la app** con un GET para confirmar que el cambio quedo aplicado.

## Pendientes

- **La CI de los PRs de Roman nunca corre** (queda en `action_required` por venir de
  un fork). Se puede pedir a GitHub que no pida aprobacion para este repositorio, o
  pedirle a Roman que trabaje sobre una rama del repo principal.
- **Las capturas antes/despues quedan en el repo** (`Cambios_Fase1/`,
  `Cambios_Fase2/`, 13 imagenes, ~1,5 MB). Son evidencia del PR, pero ruido en la raiz
  del repo. Se pueden mover a `docs/img/` o borrar en una limpieza aparte.
- **`STAGING_ADMIN_A_PASSWORD` sigue sin fijarse**: el admin de empresa A tiene una
  contrasena aleatoria que no se puede recuperar. Por eso hoy la validacion de
  staging con datos reales depende del superadmin.
- Las variables duplicadas en `production-frontend` (`BACKEND_INTERNAL_URL`) y en
  `staging-backend` (todas) siguen sin limpiar: hoy no rompen nada porque los valores
  son iguales.
