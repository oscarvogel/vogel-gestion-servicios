"""Catalogo de definiciones de parametros que agrega este proyecto.

Las filas se siembran en la migracion, pero el catalogo vive aca para que los tests y el
seed puedan usar la misma fuente. Si se agrega un parametro nuevo, va en la migracion Y
aca; un test verifica que no divergan.

Formato: (parameter, default_value, description, data_type, category, editable)
"""

AI_PARAMETERS: list[tuple[str, str, str, str, str, bool]] = [
    (
        "ai.enabled",
        "false",
        "Habilita el asistente IA para esta empresa. Apagado por defecto: el sistema completo funciona sin el.",
        "bool",
        "inteligencia artificial",
        True,
    ),
    (
        "ai.monthly_quota_usd",
        "0",
        "Gasto maximo mensual de IA en dolares. 0 significa sin cuota. Es lo que se usa para medir y facturar el adicional.",
        "string",
        "inteligencia artificial",
        True,
    ),
    (
        "ai.monthly_request_limit",
        "0",
        "Cantidad maxima de pedidos al proveedor por mes. 0 significa sin limite.",
        "string",
        "inteligencia artificial",
        True,
    ),
]
