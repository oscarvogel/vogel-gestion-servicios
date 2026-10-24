## Qué hay que hacer

Tres cambios en la pantalla **Técnicos** (maestro de técnicos de la empresa):

1. **Editar un técnico tiene que ser con un modal**, no editando la fila en el lugar.
2. **Agregar un número de celular**, con validación, y **guardarlo siempre con el prefijo `549`** si el operador no lo escribe.
3. **Búsqueda y paginado** en el listado: hoy el listado no tiene ninguno de los dos.

La captura que mandó el cliente es la pantalla "Técnicos" de producción con los 44 técnicos
cargados: el listado baja entero, el buscador no se ve y la edición es en la fila.

## Por qué

- **La edición en la fila se pierde de vista.** Con 44 filas (y el maestro va creciendo) el input inline se mezcla con la tabla: se entra a editar una fila, se hace scroll y no se sabe cuál se está editando ni se ve el botón "Guardar".
- **No hay teléfono en el maestro.** El modelo `Technician` (`backend/app/models/work_area.py:121`) tiene `id`, `company_id`, `name`, `legacy_code`, `user_id`, `active` y `created_at`: **no hay teléfono**. La API (`backend/app/api/v1/technicians.py`) sólo maneja `name` y `active`. Sin celular no se puede avisarle a un técnico por WhatsApp más adelante, y el técnico es una persona: se lo llama.
- **El listado no escala.** `GET /technicians` devuelve la lista completa, sin paginar (el propio docstring lo dice: *"El maestro es chico (decenas de personas)"*), y la pantalla filtra en el navegador (`filtrados`, en `frontend/src/views/TecnicosView.vue:46`). Hoy zafa, pero el filtro es **sólo por nombre** (no busca por celular), no hay paginado, y en la captura del cliente **el campo de búsqueda no se ve**: hay que confirmar por qué y que quede a la vista.

## 1. Editar con modal

Hoy la edición es **en la fila**: `editingId` / `editingName` + un `<input>` dentro del `<td>` y los botones "Guardar" / "Cancelar" (`frontend/src/views/TecnicosView.vue:88-109` y `203-231`).

**Requisito:**

- El botón "Editar" de la fila abre un **modal** con los datos del técnico (nombre y celular) y los botones Guardar / Cancelar.
- Se usa el `Modal.vue` que ya existe (`frontend/src/components/Modal.vue`): `open`, `title`, `width`, evento `close`. El modal va con el `Teleport` y el `modal-backdrop` que ya usan los modales de la OT.
- Se **elimina la edición inline**: queda una sola forma de editar. (El "Activar / Desactivar" sigue siendo un botón de la fila, como hoy.)
- Si el usuario **no** tiene `technicians.manage`, el botón "Editar" no se muestra y el modal no se abre.
- El modal tiene que cerrar con "Cancelar", con la `X` y con `Escape` (ya lo resuelve `Modal.vue`).

**Recomendado:** el **alta** usa el mismo modal, para no dejar dos formularios distintos con el mismo campo (nombre + celular). El alta de hoy es un form suelto en una card (`frontend/src/views/TecnicosView.vue:172-190`).

## 2. Celular con validación y prefijo 549

**Requisito:** campo de celular en el alta y en la edición, columna "Celular" en la tabla, y **guardado con `549`**.

**Modelo y API:**

- `backend/app/models/work_area.py` → agregar `phone: Mapped[str | None] = mapped_column(String(20), nullable=True)` al modelo `Technician`.
- Migración nueva de alembic (la siguiente de la serie `2026xxxx_00xx_`) con `op.add_column("technicians", sa.Column("phone", sa.String(20), nullable=True))`. El maestro ya importado queda con el celular en NULL: **no se inventa** el teléfono de los 44 técnicos históricos.
- `backend/app/api/v1/technicians.py` → `TechnicianRead`, `TechnicianInput` y `TechnicianUpdate` incorporate `phone`.

**Normalización (en el backend, que es el que manda):**

1. Se borra todo lo que no sea dígito: espacios, guiones, paréntesis, el `+`.
2. Si el número **no empieza con `549`**, se le **antepone `549`** (prefijo de Argentina para celular).
3. Si **ya empieza con `549`**, se deja como está: **el prefijo no se duplica**.
4. Con el prefijo puesto tiene que quedar un número de **12 o 13 dígitos**. Si queda fuera de ese rango → **422** con un mensaje claro para el operador, no un error genérico.
5. Si el campo viene **vacío** → se guarda **NULL** (se puede borrar el celular de un técnico).

Ejemplos:

| Lo que escribe el operador | Se guarda |
| --- | --- |
| `351 123-4567` | `5493511234567` |
| `+54 9 351 123 4567` | `5493511234567` |
| `5493511234567` | `5493511234567` (no se duplica el 549) |
| `(351) 1234567` | `5493511234567` |
| `123` | 422 — *"El celular no parece válido: se espera un número de 10 dígitos (con 549 al inicio)."* |
| *(vacío)* | `NULL` |

**En la pantalla:**

- El input acepta lo que el operador escribe (con espacios y guiones); el backend devuelve el número ya normalizado y la tabla muestra ese valor (con el `549` a la vista).
- El input del modal **no** es un `type="number"`: el `+` y los guiones tienen que poder escribirse.

## 3. Búsqueda y paginado

**Backend** — `GET /technicians` pasa a devolver el mismo sobre que las órdenes de trabajo (`backend/app/api/v1/work_orders.py:155-177`):

```
GET /technicians?search=...&active=true|false&page=1&page_size=25
-> { items: [...], total: N, page: 1, page_size: 25 }
```

- `search` busca por **nombre o celular**, ignorando mayúsculas y acentos (la normalización ya existe en `_normalizar`, `backend/app/api/v1/technicians.py:47`; para el celular se comparan los dígitos del texto buscado contra el número guardado).
- `page_size` por defecto 25, máximo 100 (igual que las OT).
- `active` reemplaza los chips "Todos / Activos / Desactivados" por un filtro del backend.
- El orden sigue siendo el actual: activos primero y, dentro de cada grupo, por nombre.

> **Ojo con el cambio de forma:** hoy la respuesta de `GET /technicians` es una **lista**. Al pasar al sobre hay que actualizar los **dos** llamados del frontend:
> - `frontend/src/views/TecnicosView.vue:62` → la pantalla del maestro.
> - `frontend/src/views/WorkOrdersView.vue:136` (`loadTechnicians`) → los combos de la recepción y del detalle de la OT, que necesitan **todos** los técnicos activos. Pide `active=true&page_size=100` y lee `items`; si `items` no viene como lista, la lista queda vacía (mismo cuidado que en `work_orders.py`, donde ya se validó la forma de la respuesta).

**Frontend** — `frontend/src/views/TecnicosView.vue`:

- El buscador llama a la API (no filtra en el navegador), con **debounce** y volviendo a la **página 1** al escribir (el patrón ya está en `searchChanged` de las OT).
- El buscador queda **visible arriba de la tabla**, junto al título. En la captura del cliente **no se ve**: hay que confirmarlo y que no vuelva a pasar.
- Barra de paginación abajo de la tabla, igual que en las OT (`frontend/src/views/WorkOrdersView.vue:285`): "X–Y de Z", elegir por página (25 / 50 / 100), "← Anterior" y "Siguiente →".

## Archivos a tocar

**Backend**

- `backend/app/models/work_area.py` (columna `phone` del modelo `Technician`)
- `backend/alembic/versions/<nueva>_tecnicos_celular.py` (migración)
- `backend/app/api/v1/technicians.py` (normalización del celular, `search` / `active` / `page` / `page_size`, `phone` en los esquemas)
- `backend/tests/test_technicians.py` (pruebas nuevas)

**Frontend**

- `frontend/src/views/TecnicosView.vue` (modal de edición y de alta, campo de celular, columna "Celular", búsqueda contra la API, barra de paginación)
- `frontend/src/views/WorkOrdersView.vue` (leer `items` y pedir los activos con `page_size=100`)
- `frontend/src/__tests__/tecnicos.test.ts` y `frontend/src/__tests__/tecnicos-activos.test.ts` (pruebas nuevas)

## Criterios de aceptación

- [ ] "Editar" abre un modal con nombre y celular del técnico; "Guardar" persiste y "Cancelar" cierra sin tocar nada.
- [ ] No queda edición inline en la fila.
- [ ] El modal no se abre para un usuario sin `technicians.manage`.
- [ ] El celular se guarda con `549` cuando el operador lo escribe sin prefijo, y **no** se duplica si ya viene con `549`.
- [ ] Un celular inválido se rechaza con un mensaje que se entienda (422), no con un error genérico.
- [ ] Un técnico puede quedar sin celular y se le puede borrar el que tenía.
- [ ] La tabla muestra la columna "Celular".
- [ ] El listado tiene buscador y barra de paginación; el buscador se ve en pantalla y filtra **contra el servidor**.
- [ ] La búsqueda encuentra por nombre (sin distinguir mayúsculas ni acentos) **y** por celular.
- [ ] La barra de paginación dice "X–Y de Z" y navega; escribir en el buscador vuelve a la página 1.
- [ ] Los combos de técnicos de la OT (recepción y detalle) **siguen funcionando** y sólo ofrecen técnicos activos.
- [ ] Se ve bien a **1638×969** y a **1366×768** (la pantalla del cliente): si el modal o la tabla se pasan de alto, van dentro de un `QScrollArea`/scroll propio, no se comprimen los widgets.

## Pruebas

**Backend** (`backend/tests/test_technicians.py`)

- Alta con celular sin prefijo → se guarda con `549`.
- `PATCH` con celular sin prefijo → se guarda con `549`; con `549` → no se duplica.
- Celular inválido → 422 con el mensaje.
- Celular vacío → `NULL`.
- Búsqueda por nombre (con acentos y mayúsculas) y por celular.
- Paginado: `total` correcto y la página pedida.

**Frontend** (`frontend/src/__tests__/tecnicos.test.ts`)

- El modal abre con los datos del técnico y el `PATCH` manda nombre + celular.
- Sin `technicians.manage` no se puede editar.
- La búsqueda llama a la API con el parámetro y vuelve a la página 1.
- La barra de paginación cambia de página.

## Fuera de alcance

- No se carga ni se inventa el celular de los técnicos importados del legacy: quedan en NULL hasta que alguien lo cargue.
- No se toca la asignación de técnicos a las OT (ya anda) ni los permisos.
- No se muestra el celular en los combos de la OT. Mandar WhatsApp al técnico con ese número es un issue aparte.

## Decisiones que tomé (si el cliente dice otra cosa, se cambian)

- El celular es **opcional**.
- Se guarda **sólo con dígitos** (sin `+`, sin espacios); el `549` siempre está.
- El prefijo `549` se aplica también a los teléfonos fijos (`549` + área + número), porque es lo que pidió el cliente.
- El modal reemplaza la edición inline: una sola forma de editar.
- El alta también pasa por el modal, para no tener dos formularios con los mismos campos.
