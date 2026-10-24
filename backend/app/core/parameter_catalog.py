"""Catalogo de definiciones de parametros que agrega este proyecto.

Las filas se siembran en la migracion, pero el catalogo vive aca para que los tests y el
seed puedan usar la misma fuente. Si se agrega un parametro nuevo, va en la migracion Y
aca; un test verifica que no divergan.

Formato: (parameter, default_value, description, data_type, category, editable)

**`editable` importa mas de lo que parece en esta categoria.** `False` no es solo "la
pantalla lo muestra apagado": `company_parameters.py` corta el PATCH con 403, asi que un
administrador de empresa no lo puede cambiar ni-armando la peticion a mano.
"""

# Los tres parametros de la IA son **configuracion comercial de la plataforma**, no
# configuracion del cliente. `ai.enabled` es la decision de si a esa empresa se le vende el
# adicional, y los otros dos son su techo de uso: si el cliente pudiera editarlos, podria
# prenderse solo el adicional y ademas ponerse la cuota en 0, que significa sin cuota.
#
# Se los habilita desde el lado de la plataforma, con `PUT /companies/{id}/ai`, que es
# superadmin. Siguen siendo **visibles** en la pantalla de Parametros de la empresa, solo
# que de lectura: que un cliente vea "IA: no incluida en tu plan" es honesto y abre la
# conversacion comercial, y esconderlo seria solo dejar un modulo que no aparece sin
# explicación.
AI_PARAMETERS: list[tuple[str, str, str, str, str, bool]] = [
    (
        "ai.enabled",
        "false",
        "Habilita el asistente IA para esta empresa. Apagado por defecto: el sistema completo funciona sin el. Lo habilita la plataforma.",
        "bool",
        "inteligencia artificial",
        False,
    ),
    (
        "ai.monthly_quota_usd",
        "0",
        "Gasto maximo mensual de IA en dolares. 0 significa sin cuota. Es lo que se usa para medir y facturar el adicional.",
        "string",
        "inteligencia artificial",
        False,
    ),
    (
        "ai.monthly_request_limit",
        "0",
        "Cantidad maxima de pedidos al proveedor por mes. 0 significa sin limite.",
        "string",
        "inteligencia artificial",
        False,
    ),
]


# Los parametros de Flexxus (ERP de Suevos). Son **de plataforma**, no del
# cliente, por la misma razon que los de la IA: el ERP es de una sola
# plataforma y el catalogo de repuestos que expone es el de un cliente
# concreto. Prendido para otra empresa, esa empresa veria el catalogo y los
# precios de otro, asi que solo la plataforma lo habilita.
#
# `flexxus.enabled` apagado por default: una empresa que no lo tenga no ve
# nada, aunque el ERP este configurado y accesible.
FLEXXUS_PARAMETERS: list[tuple[str, str, str, str, str, bool]] = [
    (
        "flexxus.enabled",
        "false",
        "Habilita el catalogo de repuestos de Flexxus para esta empresa. Apagado por defecto: solo lo habilita la plataforma.",
        "bool",
        "integraciones",
        False,
    ),
    (
        "flexxus.database",
        r"C:\FLEXXUS\DB\ETR\DB-ETR.gdb",
        "Base de Flexxus (ruta del .gdb vista desde el servidor Firebird) que usa esta empresa.",
        "string",
        "integraciones",
        False,
    ),
    (
        "flexxus.price_list",
        "1",
        "Lista de precios de Flexxus que se toma como precio de venta (1 a 5).",
        "integer",
        "integraciones",
        False,
    ),
]
