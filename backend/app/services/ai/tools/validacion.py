"""Validadores de argumentos, compartidos por las herramientas de lectura y de escritura.

Todos tiran ``ToolError(ARGUMENTOS_INVALIDOS)`` con un mensaje que el modelo puede entender y
explicarle al operador. El mensaje dice que esta mal el dato, nunca que la herramienta no
existe ni que el usuario no tiene permiso: esas respuestas van por otro camino.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.services.ai.tools.base import ARGUMENTOS_INVALIDOS, ToolError

# Tope de resultados de una busqueda. El modelo no puede pedir mil filas: el costo del prompt
# se dispara y el operador no puede leerlas.
MAX_RESULTADOS = 20

# Longitudes maxima alineadas con los modelos. Validarlas aca evita que una propuesta quede
# esperando confirmacion y reviente recien al aplicarla, con la base ya abierta.
MAX_NOMBRE = 180
MAX_DOCUMENTO = 30
MAX_TELEFONO = 60
MAX_EMAIL = 255
MAX_DIRECCION = 250
MAX_MARCA = 100
MAX_MODELO = 120
MAX_SERIE = 120
MAX_DESCRIPCION = 300
MAX_TEXTO = 4000
MAX_TEXTO_CORTO = 250


def texto(valor: object, campo: str, *, maximo: int = MAX_TEXTO, minimo: int = 1) -> str:
    if not isinstance(valor, str):
        raise ToolError(ARGUMENTOS_INVALIDOS, f"El campo '{campo}' tiene que ser un texto.")
    limpio = valor.strip()
    if len(limpio) < minimo:
        raise ToolError(ARGUMENTOS_INVALIDOS, f"El campo '{campo}' no puede estar vacio.")
    if len(limpio) > maximo:
        raise ToolError(
            ARGUMENTOS_INVALIDOS,
            f"El campo '{campo}' supera el maximo de {maximo} caracteres.",
        )
    return limpio


def texto_opcional(valor: object, campo: str, *, maximo: int = MAX_TEXTO) -> str | None:
    if valor is None:
        return None
    if not isinstance(valor, str):
        raise ToolError(ARGUMENTOS_INVALIDOS, f"El campo '{campo}' tiene que ser un texto.")
    limpio = valor.strip()
    if not limpio:
        return None
    if len(limpio) > maximo:
        raise ToolError(
            ARGUMENTOS_INVALIDOS,
            f"El campo '{campo}' supera el maximo de {maximo} caracteres.",
        )
    return limpio


def entero(valor: object, campo: str, *, minimo: int | None = None, maximo: int | None = None) -> int:
    # Se acepta "5" como texto porque el modelo a veces manda numeros entre comillas, pero
    # nada que no sea un entero: "cinco" o "5.7" no son un id.
    if isinstance(valor, bool):
        raise ToolError(ARGUMENTOS_INVALIDOS, f"El campo '{campo}' tiene que ser un numero entero.")
    try:
        n = int(valor)
    except (TypeError, ValueError):
        raise ToolError(ARGUMENTOS_INVALIDOS, f"El campo '{campo}' tiene que ser un numero entero.") from None
    if minimo is not None and n < minimo:
        raise ToolError(ARGUMENTOS_INVALIDOS, f"El campo '{campo}' no puede ser menor que {minimo}.")
    if maximo is not None and n > maximo:
        raise ToolError(ARGUMENTOS_INVALIDOS, f"El campo '{campo}' no puede ser mayor que {maximo}.")
    return n


def decimal(valor: object, campo: str, *, minimo: str = "0") -> Decimal:
    """Un importe. El minimo por defecto es cero: un precio negativo no tiene sentido."""
    if isinstance(valor, bool):
        raise ToolError(ARGUMENTOS_INVALIDOS, f"El campo '{campo}' tiene que ser un numero.")
    if valor is None or valor == "":
        raise ToolError(ARGUMENTOS_INVALIDOS, f"Falta el campo '{campo}'.")
    try:
        n = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        raise ToolError(ARGUMENTOS_INVALIDOS, f"El campo '{campo}' tiene que ser un numero.") from None
    if n.is_nan() or n.is_infinite():
        raise ToolError(ARGUMENTOS_INVALIDOS, f"El campo '{campo}' tiene que ser un numero finito.")
    if n < Decimal(minimo):
        raise ToolError(
            ARGUMENTOS_INVALIDOS, f"El campo '{campo}' no puede ser menor que {minimo}."
        )
    if abs(n) > Decimal("100000000"):
        raise ToolError(ARGUMENTOS_INVALIDOS, f"El campo '{campo}' es un valor demasiado grande.")
    return n


def limite(valor: object, por_defecto: int) -> int:
    """El limite de resultados se recorta, no se rechaza.

    Si el modelo pide 9999 y le devolvemos un error, lo mas probable es que reintente y
    gaste otro turno entero. Recortarle a MAX_RESULTADOS le da lo que necesita en la primera
    vuelta. Un valor que no es numero si es un error: ahi no hay nada que recortar.
    """
    if valor is None:
        return por_defecto
    return max(1, min(entero(valor, "limite"), MAX_RESULTADOS))


def escape_like(texto_buscado: str) -> str:
    """Escapa los comodines de LIKE para que un '%' tipeado no traiga toda la tabla."""
    return texto_buscado.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
