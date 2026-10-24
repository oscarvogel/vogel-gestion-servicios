## Qué hay que hacer

Dos cosas, que el cliente pidió en la misma tanda:

1. **Identidad de la empresa: cada empresa puede tener su logo.** Se sube desde la pantalla de
   Empresas y tiene que aparecer **en las órdenes** (comprobante de recepción y presupuesto
   impreso) y **en todos lados** dentro de la app. El logo de **Vogel Consultoría** sigue
   apareciendo, pero **chico**: es la marca de la plataforma, no la del cliente.
2. **La versión que muestra la app no se actualiza nunca.** En el pie del menú lateral dice
   `v0.2 · Modo Empresa` desde hace meses, y ese texto está **escrito a mano**. Tiene que mostrar
   la versión real del build que está corriendo el cliente.

## Por qué

**Identidad.** El comprobante de recepción y el presupuesto salen con el nombre de la empresa
pelado, sin logo ni datos: el cliente final recibe un papel sin identidad, y en una plataforma
multiempresa los comprobantes de una empresa se terminan confundiendo con los de otra. Hoy el
modelo de empresa ni siquiera tiene campo de logo (`backend/app/models/company.py:8`).

**Versión.** Hoy la versión es una constante:

- `frontend/src/components/Sidebar.vue:168` → `<div>v0.2 · {{ ... "Modo Empresa" }}</div>`: el
  texto está **escrito en el template**. No sale de `package.json`, no sale del backend, no sale
  del build: no hay forma de que se actualice solo.
- `frontend/package.json` → `"version": "0.2.0"`, sin bumpear nunca.
- `backend/app/main.py:17` → `/health` devuelve `{"status":"ok"}`: el backend tampoco sabe qué
  versión está corriendo.
- `frontend/Dockerfile` → los únicos `ARG` son `VITE_API_URL` y `BACKEND_INTERNAL_URL`: el build
  no recibe versión ni commit. `docker-compose.yml` → `build.args` con esas dos variables y nada
  más.

La consecuencia práctica: cuando algo falla en el cliente **no hay forma de saber si está viendo
el bundle nuevo o uno viejo**. Y en un piloto, un changelog que dice una cosa y una pantalla que
muestra otra es exactamente el tipo de cosa que hace desconfiar.

## 1. Logo de la empresa

### Backend

**Los binarios no van a MySQL.** Ya está el storage con volumen persistente
(`backend/app/services/storage.py`: `build_storage()`, `build_key()`, `put`/`open`/`delete`), y el
patrón a copiar es el de los documentos de equipo
(`backend/app/api/v1/equipment_documents.py:132` la subida, `:213` la descarga con
`StreamingResponse`). La razón está escrita en el propio modelo: *"aca no hay contenido de
archivo. MySQL se backs uppea, se replica y se consulta todo el tiempo; meterle fotos de video
engorda los backups sin ganar nada"*.

Cambios:

- **Modelo** (`backend/app/models/company.py`): columnas en `companies` →
  `logo_storage_key` (String 500, nullable), `logo_mime_type`, `logo_size_bytes`,
  `logo_updated_at`. Una sola fila por empresa alcanza: el logo es único por empresa. Si mañana se
  quieren más archivos (favicon, sellos), se migra a una tabla `company_assets`.
- **Migración** de alembic nueva (la siguiente de la serie `2026xxxx_00xx_`).
- **API** (`backend/app/api/v1/companies.py`), todos con sesión y con la empresa activa:
  - `POST /companies/current/logo` (multipart, permiso `companies.manage`) → sube o reemplaza;
    devuelve la empresa con `has_logo`.
  - `GET /companies/current/logo` → sirve el archivo (`StreamingResponse`, `Content-Disposition:
    inline`). **Nunca** se sirve por una ruta del storage: eso publicaría archivos privados.
  - `DELETE /companies/current/logo` → lo saca y borra el archivo del storage.
  - `CompanyRead` gana `has_logo: bool` (y `logo_url`).
- **Validaciones al subir**:
  - **Sólo PNG, JPG/JPEG y WEBP.** Nada de SVG: un SVG puede traer script.
  - Máximo **2 MB** (413 si se pasa, con el mensaje de siempre).
  - Archivo vacío → 422.
  - La clave del storage la genera el servidor (`build_key`), nunca el nombre que manda el
    frontend.
  - Al reemplazar, el archivo anterior se borra del storage: no quedan huérfanos.
  - Si la empresa no tiene logo, el GET responde 404 y la pantalla cae al fallback (nombre).
- Si la empresa no tiene logo, `GET /companies/current/logo` responde 404 y la pantalla usa el
  fallback (nombre de la empresa), no una imagen rota.

### Frontend

- **Pantalla de Empresas** (`frontend/src/views/CompaniesView.vue`): sección **"Identidad"** con
  la previsualización del logo, "Subir logo" (input file) y "Quitar logo".
- **Menú lateral** (`frontend/src/components/Sidebar.vue:148-150`): hoy está el logo de Vogel a
  86px. Queda así:
  - el **logo de la empresa** arriba (altura ~48-56px, `object-fit: contain`);
  - el logo de **Vogel Consultoría** **chico** (`<VogelLogo :size="28" mark />`) al lado o debajo,
    como marca de plataforma;
  - si la empresa no tiene logo: el nombre de la empresa + el logo de Vogel chico.
- **Comprobante de recepción** (`frontend/src/views/WorkOrdersView.vue:287-291`, bloque
  `receipt-print__brand`): logo de la empresa + nombre + razón social + CUIT + teléfono +
  dirección + email. Es el papel que ve el cliente final: hoy no tiene nada de eso.
- **Presupuesto impreso** (`printBudget`): mismo encabezado que el comprobante.
- **Barra superior** (`frontend/src/components/Topbar.vue`): logo chico junto al nombre de la
  empresa.
- El logo se sirve por un endpoint que pide sesión, así que se trae con
  `apiGet("/companies/current/logo", { responseType: "blob" })` y se muestra con
  `URL.createObjectURL(blob)`. Hay que **revocar la URL** (`URL.revokeObjectURL`) al cambiar de
  empresa o al desmontar: si no, cada cambio de empresa deja un blob colgado en memoria.
- Si la API está caída o el logo no carga, la app sigue mostrando el nombre de la empresa.

### Criterios de aceptación (logo)

- [ ] Se sube un logo desde Empresas y se ve en esa misma pantalla.
- [ ] Aparece en el **comprobante de recepción impreso** y en el **presupuesto impreso**.
- [ ] Aparece en el **menú lateral** y en la **barra superior**.
- [ ] El logo de Vogel Consultoría **sigue** en pantalla, pero **chico**.
- [ ] Una empresa sin logo no ve imágenes rotas: se ve el nombre.
- [ ] Al cambiar de empresa cambia el logo (y no queda el de la empresa anterior).
- [ ] SVG, archivo vacío y archivo de más de 2 MB se rechazan con un mensaje claro.
- [ ] El logo de una empresa **no** es visible desde otra empresa (probado con dos empresas).
- [ ] Se ve bien a **1638×969** y a **1366×768** (la pantalla del cliente).

## 2. La versión tiene que ser real

### Qué hay que hacer

1. **Una sola fuente de verdad.** Un archivo `VERSION` en la raíz del repo (con el formato que se
   use para los releases) que se bumpea **en cada release**. `package.json` puede seguirlo, pero
   no puede ser la fuente: el frontend y el backend tienen que mostrar lo mismo.
2. **Hornearla en el build.** `ARG VITE_APP_VERSION` y `ARG VITE_APP_COMMIT` en
   `frontend/Dockerfile`, con `ENV` antes del `npm run build` (el mismo patrón que ya usa
   `VITE_API_URL`), y en `docker-compose.yml` → `build.args`:
   `VITE_APP_VERSION: ${VITE_APP_VERSION}`, `VITE_APP_COMMIT: ${SOURCE_COMMIT:-unknown}`. En el
   frontend se lee con `import.meta.env.VITE_APP_VERSION`.
   > El texto tiene que quedar **horneado en el bundle**, no guardado sólo en una variable de
   > runtime: así se puede verificar por fuera que lo que se sirvió es lo esperado (ver punto 5).
3. **El backend también la conoce.** `APP_VERSION` / `APP_COMMIT` por variable de entorno y
   `/health` (o un `GET /api/v1/meta`) que devuelva `{"status":"ok","version":"...","commit":"..."}`.
   Sirve para comparar: si el bundle dice una cosa y `/health` dice otra, hay un deploy a medias.
4. **Mostrar la versión real.** Pie del menú lateral → `v2026.10.23 · a1b2c3d · Modo Empresa` (el
   commit corto se puede omitir). Y en **Ajustes** (o en una pantalla "Acerca de") un bloque con
   versión, commit y fecha de build.
5. **Que no vuelva a pasar.** `scripts/verify-deploy.ps1` ya acepta `-Expected "<texto>"` y baja
   el bundle realmente servido: hay que pasarle la versión del release (por ejemplo
   `-Expected "v2026.10.23"`) para que la verificación **falle si se sirvió un bundle viejo**.
   Hoy ese parámetro no se usa para esto, y por eso una versión vieja pasa inadvertida.
6. **Regla de release:** el número de versión se bumpea junto con el deploy, y `package.json`
   (`"version"`) deja de ser el lugar donde se mira.

### Criterios de aceptación (versión)

- [ ] El pie del menú lateral muestra la versión del build desplegado, no un texto fijo.
- [ ] La versión cambia después de un deploy (se verifica con `scripts/verify-deploy.ps1`).
- [ ] `/health` devuelve la versión y el commit.
- [ ] La pantalla de Ajustes muestra versión, commit y fecha de build.
- [ ] No queda ningún `v0.2` hardcodeado en el frontend.
- [ ] El número de versión está en un solo archivo y se bumpea en cada release.

## Archivos a tocar

**Backend**

- `backend/app/models/company.py` (columnas del logo)
- `backend/alembic/versions/<nueva>_logo_empresa.py` (migración)
- `backend/app/api/v1/companies.py` (subir / servir / quitar el logo, `has_logo`)
- `backend/app/main.py` (`/health` con versión y commit)
- `backend/app/core/config.py` (`APP_VERSION`, `APP_COMMIT`)
- `backend/tests/` (pruebas del logo y de la versión)

**Frontend**

- `frontend/src/views/CompaniesView.vue` (sección Identidad)
- `frontend/src/components/Sidebar.vue` (logo de la empresa + logo de Vogel chico + versión real)
- `frontend/src/components/Topbar.vue` (logo chico)
- `frontend/src/views/WorkOrdersView.vue` (comprobante y presupuesto impresos con el logo)
- `frontend/src/views/SettingsView.vue` (bloque "Acerca de")
- `frontend/src/lib/api.ts` (helper para traer el logo como blob y revocar la URL)
- `frontend/Dockerfile`, `docker-compose.yml` (ARG de versión y commit)
- `frontend/src/__tests__/` (pruebas nuevas)

## Pruebas

**Backend**

- Subir un logo: se guarda en el storage y la empresa queda con `has_logo`.
- Servir el logo: devuelve el archivo y el `Content-Type` correcto.
- El logo de la empresa A no se puede pedir desde la empresa B.
- Rechazo: SVG, archivo vacío y archivo de más de 2 MB.
- Reemplazar el logo borra el anterior del storage.
- `/health` devuelve versión y commit.

**Frontend**

- La pantalla de Empresas sube el logo y lo previsualiza.
- El sidebar muestra el logo de la empresa y el de Vogel chico.
- El comprobante impreso lleva el logo.
- El pie muestra la versión del build (no "v0.2").
- Una empresa sin logo muestra el nombre, sin imagen rota.

## Fuera de alcance

- Logo en los **correos y en los WhatsApp** al cliente: es otro tema (hoy el remitente sale de
  `notification_sender_name` y `email_from_name`).
- **Favicon** / ícono de la pestaña: es único por app, no por empresa; se puede hacer después.
- Recorte automático de la imagen: hoy el backend no tiene Pillow (`pyproject.toml`), así que
  habría que agregar la dependencia. Salvo que se acepte el tamaño original con el tope de 2 MB.

## Decisiones que tomé (si el cliente dice otra cosa, se cambian)

- El logo es **por empresa** (multi-tenant) y vive en el **storage**, no en MySQL.
- Formatos: PNG/JPG/WEBP, máximo 2 MB, **sin SVG**.
- Si la empresa no tiene logo, se ve el **nombre** de la empresa + el logo de Vogel chico.
- El logo de Vogel queda en **28px**, como marca de plataforma, al lado del logo de la empresa.
- La versión se **hornea en el build** y además la reporta el backend: los dos tienen que decir lo
  mismo.
