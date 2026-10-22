"""Reglas de mapeo del legacy al destino.

Todo lo que se decide "a mano" vive aca, y no en los pasos de importacion: asi las
decisiones se pueden leer (y corregir) en un solo lugar, y se pueden testear sin
tocar la base.

Las decisiones no son tecnicas: son del cliente y estan tomadas en
``docs/plan-importacion-ciberbrain.md``. Donde el legacy era ambiguo, la regla que se
aplica esta documentada en la funcion que la aplica.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

# ---------------------------------------------------------------------------
# Nombres y clientes
# ---------------------------------------------------------------------------

#: Sufijos societarios que delatan que el cliente es una empresa. El legacy los
#: escribe de todas las formas posibles (con y sin puntos, con y sin espacios), asi
#: que se buscan sobre el nombre en mayusculas y con los puntos tolerados.
_SUFIJOS_SOCIETARIOS = re.compile(
    r"(?:^|[^A-Z0-9])("
    r"S\.?\s*A\.?(?:\s*E\.?\s*C\.?)?(?:\s*I\.?\s*F\.?)?\.?|"
    r"S\.?\s*R\.?\s*L\.?|"
    r"LTDA\.?|"
    r"COOP\.?|"
    r"S\.?\s*A\.?\s*S\.?|"
    r"S\.?\s*DE\s+C\.?|"
    r"SOC\.?\s*DE\s+RESP\.?|"
    r"S\.?\s*A\.?\s*Y\s+C\.?|"
    r"EIRL\.?"
    r")(?:[^A-Z0-9]|$)"
)


#: Un email con la forma minima: local@dominio.tld. Sirve para descartar los
#: placeholders del legacy ("NO TIENE", "NO SE", "TIENE", ".") que el destino
#: rechaza con la validacion EmailStr.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+$")


def email_valido(valor: str | None) -> str | None:
    """Email del legacy, o ``None`` si no es un email.

    El legacy usa placeholders en el campo de email: 6.487 de los 14.730 clientes
    tienen "NO TIENE" (o "NO SE", "NOTIENE", "."). El destino valida el email con
    ``EmailStr``, asi que copiarlo tal cual hace fallar el listado de clientes
    entero con un 500.

    Un placeholder no es un email: se guarda como NULL, que es la ausencia de dato.
    Si el campo trae mas de una direccion, se toma la primera que sea valida.
    """
    if not valor:
        return None
    for candidato in re.split(r"[\s,;]+", valor.strip()):
        candidato = candidato.strip()
        if candidato and _EMAIL_RE.match(candidato):
            return candidato
    return None


def sin_acentos(valor: str) -> str:
    """Quita los acentos y pasa a mayusculas.

    Se usa para comparar textos del legacy (nombres, tipos de equipo) donde la
    tilde no debe decidir: el legacy escribe ``ILUMINACIÓN`` y ``ILUMINACION`` para
    lo mismo.
    """
    normalizado = unicodedata.normalize("NFKD", valor or "")
    sin = "".join(c for c in normalizado if not unicodedata.combining(c))
    return sin.upper()


def normalizar_nombre(valor: str) -> str:
    """Nombre canonico para comparar: mayusculas, espacios colapsados, sin bordes.

    Es la clave de consolidacion de clientes: ``TRIPLEX LTDA.`` y ``TRIPLEX LTDA``
    (con doble espacio) son el mismo cliente.
    """
    return re.sub(r"\s+", " ", (valor or "").strip()).upper()


def cuit_valido(valor: str) -> bool:
    """Dice si el texto es un CUIT de 11 digitos con digito verificador correcto.

    El digito verificador del CUIT se calcula con los pesos 5,4,3,2,7,6,5,4,3,2
    sobre los primeros 10 digitos (AFIP). Sin esta validacion el maestro de
    clientes queda con documentos que no son documentos: en la base hay
    placeholders (``100000``, ``11111111``) que no son CUIT.
    """
    digitos = (valor or "").strip()
    if len(digitos) != 11 or not digitos.isdigit():
        return False
    numeros = [int(d) for d in digitos]
    if numeros[0] == numeros[1] == numeros[2]:
        return False
    return _digito_verificador(numeros[:10]) == numeros[10]


def _digito_verificador(primeros_diez: list[int]) -> int:
    """Digito verificador de un CUIT (ponderacion 5,4,3,2,7,6,5,4,3,2)."""
    pesos = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    suma = sum(p * d for p, d in zip(pesos, primeros_diez))
    resto = 11 - (suma % 11)
    if resto == 11:
        return 0
    if resto == 10:
        return 9
    return resto


def cuit_normalizado(valor: str) -> str | None:
    """CUIT de 11 digitos (sin guiones) si **pasa el digito verificador**; si no, ``None``."""
    digitos = re.sub(r"\D", "", valor or "")
    if cuit_valido(digitos):
        return digitos
    return None


def cuit_de_11_digitos(valor: str) -> str | None:
    """CUIT de 11 digitos (sin guiones), sin validar el digito verificador.

    Sirve para contar: hay CUITs de 11 digitos que no pasan el verificador y hay
    placeholders mas cortos (``100000``, ``11111111``) que ni son de 11 digitos.
    """
    digitos = re.sub(r"\D", "", valor or "")
    return digitos if len(digitos) == 11 else None


def es_sociedad(nombre: str) -> bool:
    """El nombre tiene un sufijo societario (S.A., S.R.L., LTDA., COOP, ...)."""
    return bool(_SUFIJOS_SOCIETARIOS.search(normalizar_nombre(nombre)))


def tipo_cliente(nombre: str, cuit: str | None) -> str:
    """``COMPANY`` si el CUIT es valido o el nombre tiene sufijo societario.

    Es la decision 1.2 del plan: el legacy no tiene un campo de tipo de cliente, asi
    que hay que deducirlo. Un CUIT valido alcanza por si solo (una persona con CUIT
    tambien es una empresa unipersonal).
    """
    if cuit and cuit_valido(cuit):
        return "COMPANY"
    if es_sociedad(nombre):
        return "COMPANY"
    return "PERSON"


# ---------------------------------------------------------------------------
# Mesas de trabajo
# ---------------------------------------------------------------------------

#: Prefijos que se sacan de la mesa: el legacy escribe la mesa con el taller de
#: adelante (``TALLER - BOX B``) y la parte del taller no distingue una mesa de otra.
_PREFIJOS_MESA = ("TALLER",)

#: Un texto de ubicacion que no es una mesa. En el legacy, ``Ubicacion`` se usa
#: tambien para dejar anotada la retirada del equipo ("Retirada el 10/09/2022"):
#: esas filas no son mesas y no pueden ir al maestro de mesas.
_ES_NOTA_DE_RETIRADA = re.compile(r"^RETIRADA\b")


def normalizar_mesa(valor: str) -> tuple[str, str] | None:
    """Devuelve ``(codigo, nombre)`` de la mesa, o ``None`` si no es una mesa.

    La normalizacion une las tres formas en que el legacy escribe la misma mesa
    (``TALLER-BOX1``, ``TALLER - BOX B``, ``TALLER - BOX A``): mayusculas, un solo
    separador, y ``BOX1``/``BOX 1``/``BOX-1`` quedan iguales.

    Suposicion: un texto que no parece una mesa (nota de retirada, texto libre) se
    deja fuera del maestro y la OT queda sin mesa. Meter 1.000 "mesas" chamadas
    "RETIRADA EL 10/09/2022" ensuciaria el maestro sin ningun beneficio.
    """
    limpio = re.sub(r"\s+", " ", (valor or "").strip()).upper()
    if limpio == "":
        return None
    if _ES_NOTA_DE_RETIRADA.match(limpio):
        return None
    # Separadores unificados: todo lo que no sea alfanumerico pasa a un guion.
    codigo = re.sub(r"[^A-Z0-9]+", "-", limpio).strip("-")
    if codigo == "":
        return None
    # Prefijo redundante del taller.
    for prefijo in _PREFIJOS_MESA:
        if codigo.startswith(prefijo + "-"):
            codigo = codigo[len(prefijo) + 1:]
            break
    if codigo == "":
        codigo = limpio
    # BOX1 == BOX 1 == BOX-1
    codigo = re.sub(r"^BOX-?(\d+)$", r"BOX \1", codigo)
    return codigo, codigo


# ---------------------------------------------------------------------------
# Estados de la OT
# ---------------------------------------------------------------------------

#: Estado del destino para cada estado del legacy.
#:
#: La funcion del legacy ``dbo.CS_GetEstadoTrabajo`` los describe asi:
#: ``-1`` = "Para Iniciar"/"Esperando Recepcion"/"Para Visitar", ``0`` = "Para
#: Presupuestar", ``1`` = "Para Informar", ``2`` = "En Aprobacion", ``3`` = "Faltan
#: Requisitos", ``4`` = "Abierta", ``5`` = "Rechazada", ``6`` = "Anulada", ``7`` =
#: "Cerrada", ``8`` = "Liquidada"/"Facturada".
#:
#: Se usa el mapeo pedido (que corre un paso respecto de los rotulos del legacy):
#: ``0`` -> "En diagnostico", ``1`` -> "Presupuestado". Los estados 3, 5 y 6 no
#: existen entre los defaults del destino y se crean.
ESTADO_LEGACY_A_DESTINO = {
    -1: "Recibido",
    0: "En diagnóstico",
    1: "Presupuestado",
    2: "Esperando aprobación",
    3: "Faltan requisitos",
    4: "En reparación",
    5: "Rechazada",
    6: "Anulada",
    7: "Listo",
    8: "Entregado",
}

#: Estados defaults de la empresa, con los mismos valores que usa el endpoint de
#: alta de empresa (``backend/app/api/v1/companies.py``).
ESTADOS_POR_DEFECTO = (
    ("Recibido", "#10B981", 10, True, False, False, False),
    ("En diagnóstico", "#3B82F6", 20, False, False, False, False),
    ("Presupuestado", "#8B5CF6", 30, False, False, False, False),
    ("Esperando aprobación", "#F59E0B", 40, False, False, False, False),
    ("En reparación", "#06B6D4", 50, False, False, False, False),
    ("Esperando repuesto", "#F97316", 60, False, False, False, False),
    ("Listo", "#22C55E", 70, False, False, True, False),
    ("Entregado", "#64748B", 80, False, True, False, True),
)

#: Estados que el legacy usa y el destino no tiene. Se crean con estos colores para
#: que se vean distintos en el tablero.
ESTADOS_LEGACY_EXTRA = (
    ("Faltan requisitos", "#F97316", 90),
    ("Rechazada", "#EF4444", 100),
    ("Anulada", "#6B7280", 110),
)


def estado_destino(estado_legacy: int | None) -> str:
    """Nombre del estado de destino para un estado del legacy.

    Si el legacy no tiene estado (o tiene uno que no se conoce), va al estado **inicial**
    ("Recibido"), no al final. Marcar como "Entregado" una OT de la que no se sabe el
    estado es mostrar como terminado un trabajo que no se sabe si se termino: en el
    corte 2020+ son 47 OTs sin estado, y "Entregado" es ademas el estado final del
    tablero (``is_final``).
    """
    if estado_legacy is None:
        return "Recibido"
    return ESTADO_LEGACY_A_DESTINO.get(estado_legacy, "Recibido")


# ---------------------------------------------------------------------------
# Garantia
# ---------------------------------------------------------------------------

#: ``work_areas.warranty_type`` -> ``work_orders.warranty_status``.
#:
#: Ojo: la garantia sale de la **politica** del area (la fuente autoritativa del
#: legacy) y no del flag crudo de la OT: los dos difieren en 184 OTs del historico.
GARANTIA_A_ESTADO = {
    0: "out_of_warranty",
    1: "warranty",
    2: "own_warranty",
}


# ---------------------------------------------------------------------------
# Lineas de la OT
# ---------------------------------------------------------------------------

#: ``CS_Partes.Tipo`` (ya es el tipo del destino).
TIPO_PARTE = {0: 0, 1: 1, 2: 2, 3: 3}

#: ``CS_Partes.LiquidaComision``: 0 = sin comision, -1 = se divide entre todos,
#: -2 = el responsable de la OT, -3 = el proveedor de la parte, > 0 = el codigo de
#: un tecnico del legacy.
COMISION_SIN_COMISION = 0
COMISION_TODOS = -1
COMISION_RESPONSABLE = -2
COMISION_PROVEEDOR = -3


def tipo_comision(valor: int | None) -> int:
    """Valor de ``commission_recipient_type`` (lo que ya viene del legacy)."""
    if valor is None:
        return COMISION_SIN_COMISION
    return valor


# ---------------------------------------------------------------------------
# Equipos
# ---------------------------------------------------------------------------

#: Series que el legacy escribe cuando el numero de serie no se pudo leer. No son
#: series: si se guardan, el maestro de equipos se llena de equipos indistinguibles.
SERIES_INVALIDAS = {
    "ILEGIBLE",
    "FALTA",
    "S/N",
    "N/S",
    "S7N",
    "S",
    "NO TIENE",
    "NO TIENE SERIAL",
    "SIN SERIAL",
    "SIN NUMERO",
    "SIN NUMERO DE SERIE",
    "NO SERIAL",
    "NINGUNO",
    "NULO",
    "-",
    "0",
}


def serie_util(valor: str) -> str | None:
    """Serie del legacy, o ``None`` si es un placeholder.

    La clave del equipo es ``(cliente, serie)``: si la serie no sirve, el equipo queda
    como "sin serie identificable" y se agrupa con los demas de ese cliente.
    """
    limpio = re.sub(r"\s+", " ", (valor or "").strip()).upper()
    if limpio == "":
        return None
    if limpio in SERIES_INVALIDAS:
        return None
    return limpio


#: Tipos de equipo que se reconocen en el texto del legacy. El orden no importa:
#: se buscan todos y gana el mas largo (para que "LAVARROPAS" no gane sobre
#: "LAVARROPA S.A.").
_TIPOS_EQUIPO = (
    "LAVARROPAS",
    "LAVARROPA",
    "SECARROPAS",
    "SECADORA",
    "LAVAVAJILLAS",
    "AIRE ACONDICIONADO",
    "AIRE ACONDICIOANDO",
    "HELADERA",
    "HELDERA",
    "MICROONDAS",
    "CLIMATIZADOR",
    "CALEFON",
    "HORNO",
    "HORNILLO",
    "COOKTOP",
    "COCINA",
    "TELEVISOR",
    "LAVADORA",
    "ASPIRADORA",
    "VENTILADOR",
    "PURIFICADOR",
    "ENFRIADOR",
    "BEBEDERO",
    "DISPENSER",
    "CAMPANA",
    "FORMIGA",
    "FREEZER",
    "EXHIBIDORA",
    "ILUMINACION",
    "LUMINARIA",
    "LUMINARIAS",
    "CAMARA DE FRIO",
    "EQUIPO DE FRIO",
    "PLACA",
    "ANAFE",
    "SISTEMA SOLAR",
    "CAPACITOR",
    "MANTENIMIENTO",
    "TERMO",
    "FRIGOBAR",
    "ESTABILIZADOR",
    "PORTON ELECTRICO",
    "MOTOR DE PORTON",
    "FABRICADORA DE HIELO",
    "TURBOCALENTADOR",
    "MULTIPROCESADORA",
    "CAVA DE VINO",
    "MAQUINA DE PICOLE",
    "REFRIGERADOR",
    "CONGELADOR",
)

#: Marcas que aparecen en el texto del legacy. Se usan para armar el catalogo
#: curado de categorias (tipo + marca).
_MARCAS_EQUIPO = (
    "ESLABON DE LUJO",
    "ELECTROLUX",
    "WHIRLPOOL",
    "INDESIT",
    "BAMBI",
    "KOHINOOR",
    "DURABRAND",
    "MIDEA",
    "PATRICK",
    "PATRIOT",
    "PHILCO",
    "SAMSUNG",
    "SANYO",
    "BRIKET",
    "ORBIS",
    "DREAN",
    "CANDY",
    "GAFA",
    "INELRO",
    "BGH",
    "ASTORIA",
    "YAPAY",
    "LG",
    "TCL",
)

_TIPOS_EQUIPO_ORDENADOS = sorted(_TIPOS_EQUIPO, key=len, reverse=True)
_MARCAS_EQUIPO_ORDENADAS = sorted(_MARCAS_EQUIPO, key=len, reverse=True)

#: Cuantas categorias curadas se arman con los valores mas frecuentes del corte. El
#: resto va a "OTROS": con 2.588 textos de equipo distintos no hay forma de tener un
#: catalogo util, y el maestro tiene que servir para filtrar, no paracepsular.
CANTIDAD_CATEGORIAS = 60

#: Categoria de reserva.
CATEGORIA_OTROS = "OTROS"


def tipo_equipo(equipo: str) -> str | None:
    """Tipo de equipo deducido del texto del legacy (LAVARROPAS, HELADERA, ...)."""
    texto = sin_acentos(equipo)
    for tipo in _TIPOS_EQUIPO_ORDENADOS:
        if tipo in texto:
            return tipo
    # Abreviaturas del legacy: "LAV." = lavadora, "SEC." = secadora.
    if texto.startswith("LAV."):
        return "LAVARROPAS"
    if texto.startswith("SEC."):
        return "SECARROPAS"
    return None


def marca_equipo(equipo: str) -> str | None:
    """Marca deducida del texto del legacy."""
    texto = sin_acentos(equipo)
    for marca in _MARCAS_EQUIPO_ORDENADAS:
        if marca in texto:
            return marca
    return None


def clave_categoria_equipo(equipo: str) -> tuple[str | None, str | None]:
    """Par ``(tipo, marca)`` con el que se arma el catalogo de categorias."""
    return tipo_equipo(equipo), marca_equipo(equipo)


def nombre_categoria(tipo: str | None, marca: str | None) -> str:
    """Nombre de la categoria para un par ``(tipo, marca)``."""
    if tipo is None:
        return CATEGORIA_OTROS
    if marca is None:
        return tipo
    return f"{tipo} {marca}"


# ---------------------------------------------------------------------------
# Facturas
# ---------------------------------------------------------------------------

#: ``CG_Facturas_Tabla.TipoDoc`` -> ``invoices.invoice_type``.
TIPO_DOCUMENTO = {1: "factura", 31: "factura_mipyme"}


def tipo_invoice(tipo_doc: int | None) -> str:
    """Tipo de la factura en el destino."""
    return TIPO_DOCUMENTO.get(tipo_doc or 0, "factura")


# ---------------------------------------------------------------------------
# Importes
# ---------------------------------------------------------------------------

#: Decimal de referencia para las sumas del cuadre (los importes del legacy tienen 6
#: decimales, pero las sumas se redondean a centimos para el informe).
CENTIMOS = Decimal("0.01")
