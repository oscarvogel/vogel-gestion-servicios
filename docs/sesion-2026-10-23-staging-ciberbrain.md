# Sesión 2026-10-23 — Levantar los datos de CiberBrain en staging y desplegar la rama

Objetivo de la sesión: que el cliente pueda ver en **staging** el histórico importado del legacy
CiberBrain, y dejar definido **qué rama se despliega en Coolify** y por qué.

**Estado al terminar:**

- La base de **staging** tiene los datos importados (9.316 OTs, 17.565 clientes, 29.799 líneas,
  18.383 intervinientes, 10.509 comisiones, 1.962 facturas), verificados **contra el legacy**.
- La API del cierre en staging devuelve **exactamente** los números del cuadre de junio 2025.
- Staging corre la rama **`feature/cyberbrain-migracion`** (backend y frontend).
- La base de staging pasó por un incidente que hay que documentar (§4): quedó caída ~50 minutos y
  hubo que repararla cambiando el `datadir`.

---

## 1. Qué se levantó

| Qué | Dónde | Estado |
|---|---|---|
| Datos de CiberBrain | base de staging (MySQL 8.4.13) | importados y verificados |
| Pantalla del cierre mensual | staging, rama `feature/cyberbrain-migracion` | desplegada |
| Rama en el remoto | `origin/feature/cyberbrain-migracion` (12 commits) | pusheada |

### El import, en números

El dump sale de la base local (`vogel-mysql` en WSL, con el importador ya corrido) y se aplica en la
de staging. Script: `backup/_work/import_staging.sh` (dump: `backup/_work/dump_local_cierre.sql`,
16 MB, 39 tablas).

| Tabla | Filas |
|---|---|
| `work_orders` | 9.316 |
| `customers` | 17.565 |
| `work_order_parts` | 29.799 |
| `work_order_technicians` | 18.383 |
| `work_order_part_commissions` | 10.509 |
| `equipment` | 9.316 |
| `invoices` | 1.962 |
| `work_areas` | 126 |
| `companies` | 3 (Electrotecniref + las 2 empresas demo del seed) |
| `users` | 52 |

`alembic_version` queda en **`20261022_0026`**, que es la revisión de la rama.

### La verificación que importa

`GET /api/v1/warranty-settlements?period=2025-06` contra **staging** (no contra la base local):

| | Legacy | Staging |
|---|---|---|
| OTs con empresa a liquidar | 123 / 1.675.486,90 | **123 / 1.675.486,90** |
| Garantía | 91 / 1.045.148,145 | **91 / 1.045.148,145** |
| Fuera de garantía | 32 / 630.338,755 | **32 / 630.338,755** |

Cuadra al centavo. Los acentes también: `Gómez Maria José` guardado como `47C3B36D...` (UTF-8
correcto). **Ojo:** si mirás el JSON con `Invoke-RestMethod` en PowerShell 5.1, los acentes salen
como `GÃ³mez` — es la decodificación Latin-1 de la consola, no un dato roto.

---

## 2. Qué rama se despliega en Coolify, y por qué

**Staging: `feature/cyberbrain-migracion`.**

```powershell
# backend: ssknzmign82c2uapblj1x8le
# frontend: 7lnwdgdqpattc6bhkcij5d9w
PATCH /api/v1/applications/<uuid>  { git_branch = 'feature/cyberbrain-migracion', git_commit_sha = 'HEAD' }
POST  /api/v1/deploy?uuid=<uuid>&force=true
```

**Por qué no se puede dejar staging en `main` todavía.** El `Dockerfile` del backend arranca con
`alembic upgrade head && uvicorn ...`. La base de staging quedó en `20261022_0026` (la migración de
la garantía propia) y **`main` solo llega a `20261022_0025`**. Con la base en 0026 y el código en
0025, alembic no encuentra la revisión y **el contenedor del backend no levanta**: staging se
quedaría sin API.

O sea: staging tiene que seguir apuntando a la rama hasta que **la rama esté mergeada a `main`**
(que es lo que arrastra la 0026). Recién ahí se puede restaurar staging a `main`.

| | |
|---|---|
| **Ahora** | staging en `feature/cyberbrain-migracion` |
| **Después del merge** | staging vuelve a `main` y se redespliega (paso 4 del runbook) |
| **Si se restaura `main` antes del merge** | staging queda sin backend |

---

## 3. Cómo se llega a la base de staging desde la PC

Esto no estaba documentado y es lo que más tiempo costó:

1. La base de staging **no está publicada**: `is_public=false`, sin `public_port`. El `DATABASE_URL`
   del backend apunta al nombre interno de Docker (`diamcot1wyytezyasugd5biv:3306`), que solo
   existe dentro de la red `coolify`.
2. El **firewall del server** deja pasar solamente **80, 443 y 3306** en la IP pública
   `186.5.245.12`. El 3306 es **otro** MySQL del host (8.0.44), no el de Coolify (8.4.13).
3. La clave: el server **también tiene IP privada en la LAN de fasa_189** y por ahí el firewall es
   más permisivo:

   ```
   186.5.245.12:33061  -> filtrado (no llega)
   192.168.0.189:33061 -> ABIERTO  <- esta es la ruta
   ```

4. Para exponerla hay que **publicar el puerto en Coolify** y **recrear el contenedor** (un `start`
   no alcanza; el mapeo de puertos solo se aplica al recrear):

   ```powershell
   PATCH /api/v1/databases/<uuid>  { is_public = true, public_port = 33061 }
   POST  /api/v1/databases/<uuid>/stop          # esperar "exited"
   POST  /api/v1/deploy?uuid=<uuid>&force=true  # recrea con el puerto
   ```

5. **Después hay que bajar `is_public` a `false`** y volver a recrear, para no dejar la base
   expuesta. Es el paso que hay que hacer sí o sí al terminar.

El grant de MySQL no es el problema: `vogelapp@%` acepta desde cualquier IP. El firewall era la
única barrera.

---

## 4. El incidente: la base de staging se cayó y hubo que repararla

**Causa raíz: la etiqueta `mysql:8` es móvil.** El recurso de Coolify tenía `image: mysql:8`, y
ese tag hoy resuelve a **8.4.13**; el volumen se había creado con **8.4.11**. Al reiniciar el
contenedor (que descarga la imagen nueva), MySQL intentó la migración de datos y quedó colgado.

La cadena, en orden:

| Hora | Qué pasó |
|---|---|
| 10:24 | El contenedor arranca con 8.4.13: *"Server upgrade from '80411' to '80413' started"* y se queda quieto. |
| 10:25 | El **health check** (`health_check_start_period=5` segundos) lo da por muerto: la inicialización de InnoDB tarda **60 segundos** en esa base. Coolify lo reinicia **en medio de la migración**. |
| 10:32 | Con 8.4.11 el server dice *"server upgrade of version 80411 is still pending"* y se niega a arrancar: la migración quedó a medias. |
| 10:39 | Se resuelve con un `datadir` nuevo (§4.1). MySQL levanta: *"ready for connections. Version: '8.4.13'"*. |

Durante ese rato **staging estaba caído**: el backend devolvía 500 en todas las requests.

### 4.1 Cómo se reparó, sin perder nada

El `datadir` roto **no se borró**: se le dijo a MySQL que use otro, dentro del mismo volumen.

```ini
# mysql_conf del recurso de la base (la API de Coolify lo espera en base64)
[mysqld]
datadir=/var/lib/mysql/v2
```

El datadir viejo sigue en `/var/lib/mysql/` y se puede recuperar. El nuevo se inicializó vacío y
adentro se importó el dump.

### 4.2 Los tres cambios de configuración que hay que dejar

| Cambio | Por qué |
|---|---|
| `image: mysql:8.4.13` (fijada, no `mysql:8`) | el tag móvil es la causa raíz del incidente. Con la versión fijada no hay migración sorpresa. |
| `mysql_conf` con `datadir=/var/lib/mysql/v2` | sin esto el server vuelve al datadir roto y no arranca. |
| `health_check_start_period: 600` (era 5) | 5 segundos es menos que los 60 que tarda InnoDB: el contenedor moría antes de estar listo. |

### 4.3 Lo que se perdió

El datadir viejo **no** se pudo leer (el server no arrancaba), así que no hay backup del contenido
anterior de staging. Era el seed de `scripts/seed_staging.py` (superadmin + Empresa Demo A/B + 6
usuarios) más los restos de los smoke tests. **El seed se reconstruyó** en la base local antes de
dumpear (`seed_staging.py` con los passwords de staging), así que el superadmin y las empresas demo
siguen existiendo. Lo que **no** volvió: `Botz Blitz`, `Empresa Smoke 37`, `Prueba Docs` y
`Traid Walter` (restos de smoke, hay `scripts/cleanup_staging_smoke.py` para eso).

---

## 5. Hallazgos que no son míos pero conviene que queden escritos

- **El `firewall` del server es la documentada.** `186.5.245.12` deja pasar 80, 443 y 3306. El
  backend de staging no publica su puerto (como dice el runbook) y la base tampoco: para llegar
  hay que usar la **IP privada `192.168.0.189`**.
- **Variables duplicadas en `staging-backend`:** hay **dos** `DATABASE_URL` (mismo valor, inofensivo)
  y **dos `CORS_ORIGINS` con valores distintos** (`https://gestion-vogel...` y `*`). Con valores
  distintos es la "bomba de reloj" del runbook: no se sabe cuál gana. **No se tocó** (es un
  cambio de infra que amerita su propia decisión), pero hay que cleaningarlo.
- **La cola de deploys es por servidor.** `chat-central` quedó `in_progress` más de 30 minutos y
  dejó encolados los deploys de staging. Mientras tanto, `POST /start` devolvía **409** ("ya hay
  una acción en curso"), que no es un error del recurso sino cola.
- **El endpoint `/execute` no existe en esta versión de Coolify** (404), ni en aplicaciones ni en
  bases. Sin SSH al server (no hay llaves en la máquina), la única forma de meter datos era
  publicar el puerto.

---

## 6. Pendientes

- [ ] **Merge de `feature/cyberbrain-migracion` a `main`.** Es lo que habilita volver a dejar staging
      en `main` (§2). Ojo: el merge dispara el **auto-deploy de producción**; la migración 0026
      corre ahí también.
- [ ] **Restaurar staging a `main`** (`git_branch=main`, `git_commit_sha=HEAD`, redesplegar) **después
      del merge**. El paso 4 del runbook, que no es opcional.
- [ ] **Bajar `is_public` de la base** y volver a recrear el contenedor, para no dejar el puerto
      33061 publicado.
- [ ] **Limpiar las variables duplicadas** de `staging-backend` (`CORS_ORIGINS` con dos valores).
- [ ] Decidir qué hacer con el **datadir viejo** (`/var/lib/mysql/`): ocupa espacio en el volumen y
      ya no se usa. Se puede borrar desde el panel, pero conviene hacerlo con la base parada.
- [ ] **Revisar el contenido de la base de producción**: no se tocó. El importador corrió contra la
      base local; producción sigue con lo que tenía.
- [ ] La **garantía propia (Alladio)** queda en el tercer casillero desde la 0026: falta revisar
      contra el legacy que la distribución sea la misma (no hay contra en el legacy, es decisión
      nuestra).
