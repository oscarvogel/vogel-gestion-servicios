# Deploy del modulo de repuestos contra Flexxus (2026-10-24)

Bitacora del deploy del issue #114 (catalogo de repuestos contra el ERP Flexxus) y de
lo que se encontro en el camino. La parte funcional esta en
`docs/plan-repuestos-flexxus.md`; aca queda el registro del despliegue.

## Que se desplego

| Que | Donde | Estado |
|---|---|---|
| `FLEXXUS_HOST`, `FLEXXUS_PORT`, `FLEXXUS_USER`, `FLEXXUS_PASSWORD`, `FLEXXUS_CHARSET`, `FLEXXUS_DATABASE`, `FLEXXUS_TIMEOUT_SECONDS` | Variables de Coolify de **staging-backend** y **production-backend** | Cargadas (y con la clave real, que **nunca** se imprime ni se sube al repo) |
| Migraciones `0028` (parametros de Flexxus) y `0029` (trazabilidad: `item_code`, `price_source`, `price_synced_at`) | Las dos bases, por `alembic upgrade head` en el arranque del backend | Aplicadas |
| `GET /api/v1/spare-parts/search`, `GET /api/v1/spare-parts/status` | Backend | En staging y en produccion |
| `GET`/`PUT /api/v1/companies/{id}/flexxus` (superadmin) | Backend | En staging y en produccion |
| Seccion "Catalogo de repuestos (Flexxus)" del modal de empresa | Frontend | En staging y en produccion |
| `SparePartPicker` en el modal de presupuesto y en el editor de ejecucion | Frontend | En staging y en produccion |

El modulo quedo **apagado** en los dos ambientes: `flexxus.enabled` esta en `false` para
toda empresa que no tenga el override. En produccion sigue apagado **a proposito**: falta
decidir que precio se usa (costo o lista de venta).

## El orden del despliegue

1. Cargar las variables `FLEXXUS_*` en los dos backends **antes** de mergear: si el
   contenedor arranca sin la clave, el modulo queda "sin credencial" (que es distinto de
   "no aplica": el primero muestra aviso, el segundo no).
2. Merge a `main`: produccion se auto-despliega (webhook) y staging **no** (se despierta a
   mano). Asumirlo antes de mergear.
3. Desplegar staging a mano y ahi validar.
4. Produccion queda apagada hasta que se confirme el precio.

## Lo que se rompio en el camino (y como se resolvio)

### 1. El POST de variables de Coolify rechaza tres campos

`POST /api/v1/applications/{uuid}/envs` con `is_required`, `is_coolify` o `is_shared`
devuelve **422**:

```json
{"message":"Validation failed.",
 "errors":{"is_required":["This field is not allowed."],
           "is_coolify":["This field is not allowed."],
           "is_shared":["This field is not allowed."]}}
```

Los que acepta son `key`, `value`, `is_buildtime`, `is_literal`, `is_multiline`,
`is_preview` e `is_shown_once`.

### 2. Cada variable queda guardada DOS veces

Aun creando la variable con `is_buildtime: false`, Coolify la deja en **dos registros**
(uno de build y otro de runtime), con `uuid` distinto. Con los dos registros iguales es
inoffensivo.

Lo peligroso es que alguien **edite uno de los dos a mano**: en `staging-backend`,
`CORS_ORIGINS` quedo con `https://gestion-vogel...` en un registro y `*` en el otro. Por eso,
al crear una variable hay que releer el listado y **verificar que los dos registros tienen
el mismo valor**.

### 3. El listado de deployments no se filtra por UUID

El listado usa `application_name` y `application_id`, y `application_id` es el **id
numerico** (30, 31, 32...), no el UUID de la app. El commit del deploy esta en el campo
`commit`, no en `git_commit_sha`. Un filtro por `application_id -eq <uuid>` devuelve
vacio **sin error**, y eso se lee como "no hay nada en cola".

### 4. La imagen de produccion salia SIN el driver de Flexxus (esto era un bug real)

Las apps de Coolify de este repo se construyen con **Nixpacks** (`build_pack = nixpacks`,
`dockerfile` vacio), no con el `backend/Dockerfile` del repo. Nixpacks corre
`pip install .` **sin extras**.

El driver `firebirdsql` estaba **solo en el extra `flexxus`**, asi que la imagen no lo
tenia: el modulo de repuestos iba a degradar a texto libre en los dos ambientes, sin
avisar. La CI daba verde porque instalaba `.[dev,flexxus]`: validaba algo que el deploy no
hace.

Se confirmo leyendo el log del build (`Successfully installed ...` no mentionaba
`firebirdsql`) y despues en la config de la app por la API.

**Arreglo:** `firebirdsql` pasa a las **dependencias base** de `pyproject.toml` (el extra
se mantiene, para los installs explicitos y el `Dockerfile`). La CI ahora instala como
el deploy (`pip install -e .[dev]`) y verifica el import:
`python -c "import firebirdsql"`. El `Dockerfile` lleva un comentario que aclara que no
construye nada en produccion.

### 5. La base no se alcanza desde la maquina del administrador
Verificado con la red de la LAN del server caida:

- `186.5.245.12:3306` es **otro** MySQL del host (8.0.44) y rechaza a `vogelapp`.
- El firewall deja pasar **solo 80, 443 y 3306**.
- `192.168.0.189:33061` es la base de la app, pero vive en la LAN del server: sin cable no
  hay camino.
- La API de Coolify **no tiene** endpoint para ejecutar comandos ni SQL
  (`/databases/{uuid}/execute`, `/applications/{uuid}/execute` y `/servers/{uuid}/commands`
  dan 404).

**Consecuencia:** lo que haya que cambiar en la base tiene que entrar por la aplicacion.
Por eso la habilitacion del catalogo es `PUT /api/v1/companies/{id}/flexxus` (superadmin)
y no un `UPDATE` a mano sobre `company_parameters`.

## El unico conflicto del merge

`docs/sesion-2026-10-23-tecnicos.md`: los dos lados habian agregado items a la seccion de
pendientes. Resuelto **por union**: se quedo el item de `main` (mas actualizado, sobre lo
que la migracion de produccion) mas los issues #115 y #116 de la rama. Se descarto el item
"la base de produccion sigue sin tocar" de la rama, que ya era falso.

`544d18a` (rama) y `483e84c` (`main`) eran **el mismo cambio**: entro a `main` por el PR
#112. Por eso no hubo conflicto de codigo.

## Verificacion

- Suite backend sobre el **merge**: **350 tests en verde** (343 + 7 nuevos de la
  habilitacion por plataforma).
- Suite frontend: **74 en verde** (14 archivos) y `npm run build` OK.
- CI de GitHub Actions sobre `main`: en verde en `6ac44f0` y en `de04486`.
- En el servidor: `GET /api/v1/spare-parts/status` da **401** (la ruta existe y pide
  token) y `GET /api/v1/companies/3/flexxus` daba **404** antes del deploy con el endpoint
  nuevo, y **401** despues: la ruta esta viva.

### La prueba contra el ERP real (staging)

Todo esto se midio **contra el ERP de verdad**, desde el staging desplegado, con la
sesion del administrador de Electrotecniref:

1. `GET /api/v1/companies/3/flexxus` → `{"enabled": false, "price_list": 1,
   "database": "C:\\FLEXXUS\\DB\\ETR\\DB-ETR.gdb"}`.
2. `PUT /api/v1/companies/3/flexxus` (como superadmin) → `{"enabled": true}`.
   **El modulo queda habilitado para Electrotecniref en staging** y para nadie mas.
3. `GET /api/v1/spare-parts/status` → `{"disponible": true, "motivo": null, "falla": false}`:
   el modulo corresponde y hay credencial en el contenedor.
4. `GET /api/v1/spare-parts/search?q=adaptador` → **6 articulos reales** del ERP con
   codigo, descripcion, rubro, marca, stock, costo y precio de venta, y
   `price_source: flexxus:PRECIOVENTA1`. El mismo con `capacitor` (6) y con el codigo
   `05589` (1).
5. En el navegador, eligiendo "CAPACITOR 1,5MF 440V": la linea del presupuesto queda con
   **costo interno 1231,84** (`PRECIOCOMPRA`) y **precio al cliente 1847,76**
   (`PRECIOVENTA1`). Los dos precios vienen del ERP, ninguno calculado aca.
6. El desplegable entra completo a **1638x969** y a **1366x768** (a 1366 el menu va de
   373 a 633 en una ventana de 768: entra entero, con scroll interno).
7. Con el modulo apagado, el combo se comporta como texto libre **sin aviso** (que es el
   caso "no aplica": `falla: false`). Con el ERP caido, el aviso aparece y la OT sigue
   operando: eso se vio con el contenedor sin el driver, antes del arreglo.

### Lo que se escribio en staging (para que quede a las claras)

- Un **diagnostico de prueba** en la OT **#9282** (`ERINSFLEISCH AVELINO`), con el texto
  `PRUEBA DE VERIFICACION (24/10/2026) ... No es un diagnostico real`. Fue lo unico que
  hubo que escribir: el boton de "Crear presupuesto" esta deshabilitado sin diagnostico, y
  en staging ninguna OT tenia uno. **No se genero ningun presupuesto.**
- El parametro `flexxus.enabled` de Electrotecniref en **staging** (id=3) queda en
  `true`. En **produccion** queda en `false`.

La API **no tiene** un endpoint para borrar un diagnostico: si se quiere limpiar el de
prueba, hay que borrar la fila de `work_order_diagnoses` de la OT 9282 (empresa 3) por
SQL, desde una maquina con acceso a la base.

### 6. La busqueda no cubria el rubro ni la marca (y el cero resultados no decia nada)

El primer uso real del modulo, en pantalla, dio esto: el operador escribio **"foc"** y
**no aparecio nada**. Con la sensacion de que el modulo estaba roto. No lo estaba: el
ERP tiene articulos de la **marca FOCO** (adaptadores para garrafa), pero la busqueda
miraba **solo el codigo y la descripcion del articulo**.

Tres cosas se corrigieron:

1. **La busqueda ahora incluye el rubro y la marca.** El desplegable ya los muestra
   ("BREMEN PUNTERA $ 2.697,00"), asi que el operador escribe lo que ve. Con eso,
   contra el ERP real: `foc` -> 5 articulos (marca FOCO), `puntera` -> 5 (rubro
   PUNTERA), `bremen` -> 5, `jeluz` -> 5, `drean` -> 5. Antes todos devolvian cero.
2. **Cero resultados se dicen.** El menu se abria solo con resultados; con cero
   resultados se cerraba en silencio y el campo parecia muerto. Ahora el menu sigue
   abierto diciendo `No hay repuestos que coincidan con «foc»`, con la sugerencia de
   probar por rubro o marca.
3. **Nada se inventa.** "foc" sigue sin devolver focos: no hay focos en el catalogo
   (el rubro equivalente es `LAMPARAS` o `JELUZ`). Lo que devuelve son los articulos de
   la marca FOCO, que es lo que hay.

El filtro fino en Python se actualizo con el mismo criterio que el SQL (code,
descripcion, rubro y marca), y hay un test que lo verifica contra el ERP real.

## Pendientes

- [ ] **Decidir el precio**: hoy se usa la lista de venta 1 (`PRECIOVENTA1`) del ERP, que
      ya tiene el margen aplicado. La alternativa es el costo (`PRECIOCOMPRA`). Es una
      decision comercial, no tecnica, y hasta que este tomada **produccion queda apagada**.
- [ ] Prender el modulo en produccion con `PUT /api/v1/companies/{id}/flexxus` cuando la
      decision este tomada.
- [ ] Limpiar las variables duplicadas de `staging-backend` (`CORS_ORIGINS` con dos
      valores distintos): tarea vieja, sigue pendiente.
- [ ] Borrar el diagnostico de prueba de la OT 9282 de staging (ver arriba).
- [ ] El `extra` `pymssql` (importador de CiberBrain) tiene el mismo problema que
      `firebirdsql` tieneba: por estar en un extra, **nixpacks no lo instala**. No importa
      para el deploy normal (el importador se corrio local), pero conviene saberlo.
