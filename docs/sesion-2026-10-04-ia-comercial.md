# Bitácora 2026-10-04: la IA es un adicional, y el adicional lo habilita la plataforma

No es un sub-issue de #44. Es un agujero que apareció mientras se armaba el sub-issue 5, cuando
el usuario preguntó cómo iba a saber a quién cobrarle el uso de la IA.

## El agujero

La IA es un adicional comercial, y su interruptor y su techo de uso estaban en la misma
pantalla —y con los mismos permisos— que la configuración del cliente:

| Parámetro | Qué es en realidad |
|---|---|
| `ai.enabled` | **la decisión de si se le vende el adicional** |
| `ai.monthly_quota_usd` | **cuánto se le regala por mes** |
| `ai.monthly_request_limit` | **cuántos pedidos se le dan gratis** |

Los tres eran `editable=True`, o sea que un administrador de empresa podía, por su cuenta:
prender la IA y ponerse la cuota en 0. Y 0 significa **sin cuota**.

Son dos agujeros, y el segundo es el peor: aunque le sacaras el interruptor, si el cliente
puede tocar el techo, el techo no es un techo.

## El arreglo son dos piezas, y hace falta las dos

### 1. El cliente no puede: `editable=False`

Los tres quedan con `editable=False` en `app/core/parameter_catalog.py`, y la migración
`20261004_0023` lo lleva a las bases que ya los tienen en `true`.

No es cosmético: `company_parameters.py:61` ya cortaba el PATCH con 403 cuando el parámetro no
era editable. El flag existía, la pantalla ya deshabilitaba el switch, el API ya lo rechazaba.
Lo que faltaba era la decisión de **qué** parámetros iban con `False`.

Un test pone la fila del parámetro en `editable=True` y verifica que los tests fallan con
`assert 200 == 403`: no solo que el switch se ve apagado, sino que el administrador recibe el
no **en el servidor**, aunque arme la petición a mano.

### 2. La plataforma sí puede: `PUT /companies/{id}/ai`

Si solo se cerrara el punto 1, la IA quedaría apagada para siempre: el PATCH exige empresa
activa y administrador de empresa, así que nadie la encendería.

El endpoint nuevo es superadmin y ajusta los tres de una vez. Deliberadamente **no** se le
amigó "un superadmin puede saltarse el `editable`": ese atajo deja la puerta abierta para
todos los demás parámetros. Esto es un endpoint con nombre propio que dice lo que hace, y el
que lo escribe está eligiendo a propósito.

Trae también lo que la plataforma necesita ver para decidir a quién se le vende: **cuánto
consumió la empresa este mes** y cuánto va el mes anterior. Con eso, la pregunta "cómo me
entero si le quiero cobrar" ya tiene respuesta en pantalla.

## Dos cosas que decidí y conviene que sepas

**Los parámetros siguen visibles para la empresa, pero de lectura.** Que un cliente vea "IA: no
incluida en tu plan" es honesto y abre la conversación comercial. Esconderlo sería dejar un
módulo que aparece y desaparece sin explicación, que es peor. Hay un test que lo fija.

**No queda registro de quién cambió el plan y cuándo.** `CompanyParameter` tiene `updated_at`
así que hay una fecha, pero no quién. Se puede agregar si lo necesitás para auditar; no lo
puse porque es una tabla nueva y esto ya era bastante.

## Un bug mío que encontró un test

`str(0.0)` es `"0.0"` y no `"0"`. Poner la cuota en 0 guardaba un override con el valor
`"0.0"` contra un default `"0"`: decía exactamente lo mismo que el default pero la pantalla
lo mostraba como **"personalizado"**, y no se podía distinguir "le dejé sin cuota a
propósito" de "nunca le dije nada". Se resolvió normalizando el número a su forma entera
antes de comparar con el default.

Lo detectó `test_poner_la_cuota_en_cero_borra_el_override`, no la revisión del código.

## Verificación

- **256 tests del backend** en verde (eran 240), 16 nuevos, 31 del frontend, build OK.
- El arreglo se validó **contra el código roto**: con `editable=True` en el catálogo fallan
  cuatro tests, con `assert 200 == 403` y con el valor del parámetro en la respuesta.
- Un test levanta una base con la migración 0018 aplicada, corre la 0023 y verifica que las
  tres filas quedan no editables y que `alembic_version` es `20261004_0023`.
- Otro verifica que un administrador de empresa recibe 403 en el endpoint nuevo, no solo en el
  de parámetros: la puerta de atrás también tiene que estar cerrada.

## Pendiente

- El tablero de consumo por empresa como pantalla propia sigue siendo el sub-issue **#96**.
  Lo de hoy muestra el consumo de **una** empresa dentro del modal; #96 es el listado de todas
  para ver quién Agostó qué y decidir a quién se le renueva.
- El detalle que importa para facturar: el `cost_usd` es una **estimación** con la tabla de
  precios de la plataforma, no la factura de MiniMax. Sirve para medir y para el adicional;
  para cobrar al centavo hay que cruzarlo con la factura del proveedor.
