# Dashboard: actividad del día (#58)

**Estado:** implementado el 2026-10-02
**Rama:** `feat/issue-58-actividad-del-dia`

## Objetivo

Mostrar en el dashboard la actividad diaria de la empresa: OT ingresadas hoy, terminadas
hoy y entregadas hoy, calculadas con las fechas del flujo y no con la última modificación.

## La decisión que gobierna todo: qué día es "hoy"

La base guarda las fechas del flujo como **datetime naive en UTC**. `change_status` las
estampa con `datetime.utcnow()` y el frontend las formatea con la zona horaria de la
empresa (`Company.timezone`, por defecto `America/Argentina/Cordoba`).

Consecuencia directa: **"hoy" es un concepto de la empresa, no del servidor.** Si el día
se corta a medianoche UTC, una OT recibida a las 22:30 de Córdoba pertenece al día
equivocado durante tres horas cada noche, y a la inversa.

Por eso la ventana del día se arma con la medianoche **local** de la empresa y recién
ahí se convierte a UTC para consultar:

```python
local_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
start = _to_utc_naive(local_start)                      # 00:00 local -> UTC
end   = _to_utc_naive(local_start + timedelta(days=1))  # 00:00 local siguiente -> UTC
```

Los dos bordes se convierten por separado a propósito: en un cambio de horario de verano
la ventana da 23 o 25 horas, que es lo correcto, en lugar de 24 horas corridas.

## Cambio de API

`GET /api/v1/dashboard/company` agrega un bloque `today`:

```json
"today": { "date": "2026-10-02", "received": 2, "completed": 1, "delivered": 1 }
```

- `date` es el día **local de la empresa**, en ISO. El frontend lo arma como `dd/mm/aaaa`
  con un split de string, sin pasar por `new Date()`: parsearlo como fecha ISO lo
  interpretaría como UTC y en los husos al este mostraría el día anterior.
- `received` cuenta `received_at`, `completed` cuenta `completed_at` y `delivered` cuenta
  `delivered_at`. Comparar contra la ventana excluye los `NULL`, así que una OT sin fecha
  de finalización no cuenta como terminada.

## Corrección colateral

`now`, el corte de antigüedad y el inicio de cada semana de `trend` comparaban contra
`datetime.now()`, o sea la hora del **servidor**, contra valores guardados en UTC. Con el
servidor en UTC y la empresa en UTC-3, la semana del gráfico arrancaba 3 horas tarde y la
antigüedad quedaba corrida. Ahora los tres usan el mismo reloj de empresa.

## `tzdata` es dependencia, no opcional

`zoneinfo.ZoneInfo` no encuentra zonas horarias en Windows si no está el paquete `tzdata`.
Sin él, `_company_zone` no lanza: cae silenciosamente al fallback de Córdoba, y **toda**
empresa de una máquina de desarrollo Windows contaría el día con el huso equivocado sin
ningún error visible. Por eso `tzdata` quedó en las dependencias del backend y no en las
de desarrollo.

## Pruebas

Cuatro tests en `backend/tests/test_work_orders.py`:

1. **Día de la empresa contra día UTC.** Congela el reloj en `2026-10-02T23:00Z` (= 20:00
   de Córdoba) y carga órdenes a ambos lados del corte. Los conteos correctos son 3, 1 y 2;
   tomando el día UTC daría 2, 2 y 1. Los tres números se mueven, así que el test falla
   si la implementación vuelve a la ventana en UTC.
2. **Aislamiento multiempresa.** Dos empresas con actividad el mismo día: cada dashboard
   cuenta solo lo suyo.
3. **Flujo real.** Sin congelar el reloj: se crea una OT por API y se la mueve a los
   estados que marcan finalización y entrega, comprobando que los tres contadores suben.
4. **Zona horaria inválida.** Una empresa con `timezone="Marte/Olympus_Mons"` no rompe el
   dashboard: cae a Córdoba.

Verificado que 1 y 4 fallan al forzar la ventana en UTC, y que 2 y 3 no los detectan a
propósito: son tests de aislamiento y de flujo, no de huso.

## Fuera de alcance

Los tres números **no** son navegables. El listado de OT filtra por `received_at` mediante
`date_from`/`date_to`, así que "ingresadas hoy" se podría enlazar sin tocar nada, pero
"terminadas hoy" y "entregadas hoy" necesitarían filtros nuevos por `completed_at` y
`delivered_at`. Eso es parte de #57, donde además hay que arreglar el contador de
`waiting_parts`, que hoy se resuelve buscando la palabra "repuesto" en el nombre del estado.
