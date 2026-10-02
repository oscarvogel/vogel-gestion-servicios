# Deploy en Coolify: dos trampas que ya nos costaron una caída

Este documento describe cómo se despliega `vogel-gestion-servicios` en Coolify y,
sobre todo, las dos condiciones que hay que verificar **siempre** antes de un deploy.
Las dos están probadas: una de ellas dejó producción caída el 2026-10-02.

## Apps

| App | Coolify UUID | Rama | Puerto |
|---|---|---|---|
| staging-frontend | `7lnwdgdqpattc6bhkcij5d9w` | `main` | 80 |
| staging-backend | `ssknzmign82c2uapblj1x8le` | `main` | 8000 |
| production-frontend | `xfupzj8gdjij23bhvzsmzwd3` | `main` | 80 |
| production-backend | `mdp32brgexzlvdux7sgbllir` | `main` | 8000 |
| staging-db (MySQL) | `diamcot1wyytezyasugd5biv` | — | 3306 |

Las cuatro apps usan la red Docker `coolify`.

**Auto-deploy no es igual en los dos ambientes, y la diferencia es deliberada:**

| Ambiente | Despliegue |
|---|---|
| producción | **automático**: cualquier merge a `main` redespliega frontend y backend |
| staging | **manual**, a pedido. No mergear a `main` con el firme de que esto se actualizó solo |

Staging es el ambiente donde se prueba antes de dejar que producción se mueva sola. Un
merge llega igual a `main`, pero **staging queda en la versión anterior hasta que se lo
despierte a mano**. Asumirlo antes de mergear: si vas a validar en staging, el deploy es un
paso explícito, no una consecuencia del merge.

### Variables duplicadas

`POST /applications/{uuid}/envs` no deduplica por clave (ver más abajo). Hoy hay duplicados
en dos apps, ambos con el mismo valor, así que el build no se rompe, pero conviene
borrar la sobra:

- `production-frontend`: `BACKEND_INTERNAL_URL` dos veces.
- `staging-backend`: todas las variables (`DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS`,
  `STAGING_*_PASSWORD`) dos veces.

Cuando las dos copias tienen el **mismo** valor es inofensivo. Con valores distintos es una
bomba: no sabés cuál gana el build.

---

## Trampa 1: `git_commit_sha` anclado

Producción tenía `git_commit_sha` fijado a `79b939f` (un commit del 30 de septiembre)
en vez de `HEAD`. Eso parte el deploy en dos comportamientos que no coinciden:

- **Auto-deploy por webhook:** usa el SHA del webhook, o sea el HEAD del branch. Ignora
  el anclaje.
- **Deploy manual desde la API o la UI:** respeta el anclaje y construye ese commit viejo.

Resultado: la app andaba con el código nuevo porque el último deploy había sido por
webhook, pero el primer deploy manual construye septiembre. Si además el bundle hornea
una ruta relativa, el nginx de septiembre no la tiene y la app queda sin API.

**Regla:** los cuatro apps deben tener `git_commit_sha = HEAD`. Antes de cualquier
deploy manual, verificalo:

```bash
curl -s -H "Authorization: Bearer $COOLIFY_TOKEN" \
  "$COOLIFY/api/v1/applications/xfupzj8gdjij23bhvzsmzwd3" | jq '.git_commit_sha'
```

Si no dice `HEAD`, primero `PATCH` con `{"git_commit_sha": "HEAD"}` y recién después
desplegar.

---

## Trampa 2: `BACKEND_INTERNAL_URL` tiene que ser un alias de red

El frontend nginx proxea `/api/` al backend. El destino se hornea en la imagen durante
el build y **no se puede cambiar en runtime**. Lo que no funciona:

| Valor | Por qué no |
|---|---|
| `http://backend:8000` (default del Dockerfile) | en Coolify el servicio no se llama `backend` |
| `https://<uuid>.186.5.245.12.sslip.io` | la URL pública **no resuelve desde dentro del contenedor** |
| `mdp32brgexzlvdux7sgbllir-093058854806` | el nombre real del contenedor lleva timestamp y cambia en cada deploy |

El backend no publica su puerto: `186.5.245.12:8000` da timeout y
`ports_mappings` es `None`. O sea que **solo se alcanza entrando por el proxy de
Coolify**, y un contenedor no puede volver a meterse por su propio ingress.

**La solución es un alias de red estable** en el backend:

```
custom_network_aliases = vogel-backend-prod     # producción
custom_network_aliases = vogel-backend-stg      # staging
BACKEND_INTERNAL_URL   = http://vogel-backend-prod:8000
```

El alias sobrevive a los deploys; el nombre del contenedor no.

---

## Same-origin: staging ya, producción no

Estado real verificado el 2026-10-02 mirando el bundle que se sirve, no la variable:

| Ambiente | `VITE_API_URL` horneada | Modo |
|---|---|---|
| staging | `/api/v1` | same-origin |
| producción | `https://api.servicios.vogelconsultoria.com.ar/api/v1` | cross-origin |

Staging ya está migrado. **Producción sigue en cross-origin**: el browser llama a
`api.servicios.vogelconsultoria.com.ar` con otro origen. Funciona, pero obliga a mantener
`CORS_ORIGINS` sincronizado con cada dominio nuevo.

Para activar en producción alcanza con **una sola variable**:

```bash
# frontend de produccion
PATCH /api/v1/applications/xfupzj8gdjij23bhvzsmzwd3/envs
  key=VITE_API_URL  value=/api/v1
POST  /api/v1/deploy?uuid=xfupzj8gdjij23bhvzsmzwd3
```

Sin tocar `BACKEND_INTERNAL_URL`: ya apunta al alias. No hace falta redesplegar el
backend, y el frontend queda con la API en su mismo origen.

### Ojo al verificar el modo

Comprobarlo con `grep '/api/v1'` sobre el bundle **da falso positivo**: la URL absoluta
también contiene ese texto. Hay que buscar la URL absoluta:

```bash
curl -s https://servicios.vogelconsultoria.com.ar/ | grep -oE 'src="[^"]+\.js"'
# bajar ese .js y buscar 'https://api\.' -> cross-origin; ausente -> same-origin
```

### Revertir

Volver `VITE_API_URL` a la URL absoluta y redesplegar el frontend. Es lo que se hizo el
2026-10-02 para sacar producción de abajo, y tarda un par de minutos.

---

## Verificar, siempre

Después de **cualquier** deploy, mirá el bundle realmente servido. El status 200 de la
página no dice nada: el frontend puede cargar perfecto con la API rota.

```bash
FRONT=https://servicios.vogelconsultoria.com.ar

# 1) que URL horneó el bundle
curl -s $FRONT/ | grep -oE 'src="[^"]+\.js"'          # bajar ese .js y grepear
#    '/api/v1'  -> same-origin
#    https://api... -> cross-origin

# 2) que la API responde por el origen del frontend
curl -s -o /dev/null -w '%{http_code}\n' -X POST $FRONT/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"nadie@example.com","password":"x"}'
# 401 con application/json = el proxy llega al backend
# 405 o HTML               = el nginx NO tiene la ruta /api/ (bundle y nginx desalineados)
```

Esa segunda prueba es la que evitó el corte, y la que omití en producción.

### Script: `scripts/verify-deploy.ps1`

Lo mismo automatizado, más el modo de API y con reintentos, que es lo que hace falta
después de un deploy porque el contenedor reinicia y contesta a medias:

```powershell
# una sola vez
.\scripts\verify-deploy.ps1 -Url https://servicios.vogelconsultoria.com.ar -Expected "Actividad de hoy"

# esperando a que un deploy termine de servir (no falla al primer intento)
.\scripts\verify-deploy.ps1 -Url https://gestion-vogel.186.5.245.12.sslip.io -Expected "Actividad de hoy" -Wait -TimeoutSeconds 600
```

Cambiá `-Expected` por el texto que quieras ver en el bundle del issue. Sale con código 0
si todo pasa y 1 con el detalle si no, así que sirve como paso de un pipeline.

## Desplegar a mano

```powershell
$tok = (Get-Content "$env:USERPROFILE\.coolify-token" -Raw).Trim()
$h   = @{ Authorization = "Bearer $tok" }
$api = "https://coolify.vogelconsultoria.com.ar"

# Trampa 1: desanclar antes de un deploy manual
$a = Invoke-RestMethod "$api/api/v1/applications/<uuid>" -Headers $h
if ($a.git_commit_sha -ne 'HEAD') {
  Invoke-RestMethod -Method Patch -Uri "$api/api/v1/applications/<uuid>" -Headers $h `
    -ContentType 'application/json' -Body (@{ git_commit_sha = 'HEAD' } | ConvertTo-Json)
}

Invoke-RestMethod -Method Post -Uri "$api/api/v1/deploy?uuid=<uuid>&force=true" -Headers $h
```

El token vive en `%USERPROFILE%\.coolify-token` (un archivo, una línea, 51 caracteres).
El panel no responde en ningún puerto conocido de `186.5.245.12`: se entra por
`https://coolify.vogelconsultoria.com.ar`.

---

## Notas de la API de Coolify

- Las variables se identifican por `key`, no por `uuid` (el `uuid` da 422).
- El flag de variable de build es `is_buildtime`, **no** `is_build_env` (da 422).
- `POST /applications/{uuid}/envs` **no deduplica por clave**: creá la variable sabiendo
  que puede quedar duplicada, y borrá la sobra con
  `DELETE /applications/{uuid}/envs/{env_uuid}`. Duplicados con valores distintos son
  una bomba: no sabés cuál gana el build.
- Para borrar: el `env_uuid` va en el path, no como query param.
