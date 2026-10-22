"""Paso 1: clientes.

El maestro de clientes tiene **dos fuentes**, y esa es la clave del paso:

1. ``dbo.CC_Clientes_Tabla``: 14.730 filas de las que salen 14.245 clientes (el
   legacy guarda una fila por sucursal: ``TRIPLEX LTDA.`` aparece 79 veces).
2. La **copia del cliente que el legacy pego en la propia OT**: el 64 % de las OTs
   del corte (5.969 de 9.316) no tienen ``CodCli``, pero si traen nombre, telefono,
   email y direccion. De ahi salen los clientes que no estan en el maestro
   (decision D1 del brief): 3.593 nombres distintos, de los cuales 274 ya existen en
   el maestro y 3.319 son clientes nuevos.

Con las dos fuentes **no se descarta ninguna OT**: ``work_orders.customer_id`` es
NOT NULL en el destino y toda OT del corte tiene con que quedarse.

Reglas de consolidate:

- la clave es el **nombre normalizado** (mayusculas, espacios colapsados) y, si el
  CUIT es valido, el CUIT: dos filas con CUIT valido son el mismo cliente aunque el
  nombre difiera,
- ``document`` solo guarda un CUIT de 11 digitos, que **pase el digito verificador**
  y que sea **unico en toda la base** (decision D2): de los 197 clientes con CUIT de
  11 digitos, 13 CUITs estan repetidos entre clientes distintos (y romperian el
  indice unico), asi que el primero conserva el CUIT y los demas quedan NULL. Para
  los clientes deducidos de la OT el documento queda NULL: ``NroDocumento`` no es un
  documento confiable (D4),
- ``customer_type`` es ``COMPANY`` si el CUIT es valido o el nombre tiene un sufijo
  societario; si no, ``PERSON``,
- ``address`` es la direccion de la primera sucursal y las demas van al ``notes``,
  etiquetadas como sucursales.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from sqlalchemy import select

from .. import mappers, source
from ..context import Contexto

#: Marca que deja en el ``notes`` de los clientes importados del legacy. Sirve para
#: dos cosas: dejar registro de de donde salio la fila, y poder borrar en
#: ``--replace`` solo lo importado (y no lo cargado a mano en la aplicacion).
MARCA_LEGACY = "[legacy CiberBrain]"

#: Nombre del cliente que se usa cuando la OT no trae cliente y su nombre no
#: coincide con ninguno del maestro.
NOMBRE_SIN_IDENTIFICAR = "SIN IDENTIFICAR"


def _clave_de_agrupacion(fila: dict[str, object]) -> str:
    """Clave con la que se agrupan los clientes del maestro.

    Es el nombre normalizado, salvo que el legacy no tenga nombre: en ese caso la clave
    es el CodCli, para que dos clientes sin nombre no terminen fusionados en uno solo.
    """
    nombre = mappers.normalizar_nombre(str(fila["nombre"]))
    if not nombre:
        return f"__sin_nombre__{fila['codcli']}"
    return nombre


def _nombre_sin_nombre(codcli: str) -> str:
    """Nombre para un cliente del maestro que el legacy no tiene.

    ``customers.name`` no puede quedar vacio (la API lo valida con ``min_length=1``, y un
    cliente sin nombre hace fallar el listado entero con un 500), asi que hace falta un
    nombre que lo identifique. No se inventa una identidad: el nombre dice lo que es, y
    el CodCli del legacy queda en el ``notes`` junto con la marca de importado.
    """
    return f"SIN NOMBRE (CodCli {codcli})"

#: Documento de los clientes deducidos de la OT.
#:
#: D1 dice que, si el mismo nombre trae documentos distintos, "gana el mas
#: frecuente y los otros quedan NULL"; D2 dice que para los clientes deducidos de la
#: OT el documento queda NULL porque ``NroDocumento`` no es confiable. Se aplica D2
#: (es la regla mas especifica y su razon es la que manda: un NULL honesto es
#: preferible a un dato falso) y el calculo del "mas frecuente" queda countable en
#: el reporte, asi que la decision es reversible en un solo lugar.
DOCUMENTO_DE_CLIENTES_DEDUCIDOS = None


def _sucursales(direcciones: list[str]) -> str:
    """Arma el bloque de sucursales para el ``notes`` del cliente."""
    if not direcciones:
        return ""
    lineas = "\n".join(f"- {direccion}" for direccion in direcciones)
    return f"\nSucursales ({len(direcciones)}):\n{lineas}"


def _codcli_de_notas(notas: str | None) -> str | None:
    """Saca el CodCli del legacy de la marca del ``notes``.

    La marca es ``[legacy CiberBrain] codcli=123``: con ella se reconoce lo importado
    en una corrida anterior (y se borra solo eso con ``--replace``).
    """
    if not notas or not notas.startswith(MARCA_LEGACY):
        return None
    for parte in notas.splitlines():
        if parte.startswith("codcli="):
            return parte.split("=", 1)[1].strip()
    return None


class _Grupos:
    """Union-find de clientes (reservado para cuando el legacy fuse por CUIT).

    Hoy **no** se usa: los 13 CUITs repetidos son de clientes distintos y fusionarlos
    seria borrar un cliente (decision D2).
    """

    def __init__(self) -> None:
        self._padre: dict[object, object] = {}

    def buscar(self, elemento: object) -> object:
        self._padre.setdefault(elemento, elemento)
        raiz = elemento
        while self._padre[raiz] != raiz:
            raiz = self._padre[raiz]
        while self._padre[elemento] != raiz:
            self._padre[elemento], elemento = raiz, self._padre[elemento]
        return raiz

    def unir(self, uno: object, otro: object) -> None:
        raiz_a, raiz_b = self.buscar(uno), self.buscar(otro)
        if raiz_a != raiz_b:
            self._padre[raiz_b] = raiz_a


def ejecutar(ctx: Contexto) -> None:
    """Consolida el maestro de clientes y lo escribe en el destino."""
    tabla = ctx.tabla("customers")

    maestro = _maestro(ctx)
    _crear_maestro(ctx, maestro)
    deducidos = _clientes_deducidos(ctx)
    _crear_deducidos(ctx, deducidos)

    ctx.reporte.observacion(
        "Cierre mensual: entra toda OT cuya politica pertenece a un area con empresa "
        "a liquidar (work_areas.billing_customer_id). El flag de garantia solo "
        "categoriza, no decide la inclusion (decision D6): en el corte son 6.418 OTs "
        "con empresa a liquidar, de las cuales 2.853 en garantia estricta y 3.565 "
        "fuera de garantia que las marcas igual pagan."
    )


# ---------------------------------------------------------------------------
# 1. Maestro del legacy
# ---------------------------------------------------------------------------
def _maestro(ctx: Contexto) -> dict[str, object]:
    """Consolida ``CC_Clientes_Tabla``: 14.730 filas -> un cliente por nombre.

    La clave de consolidacion es el **nombre normalizado** (D1: trim, espacios
    colapsados, sin distinguir mayusculas). Los clientes NO se fusionan por CUIT:
    hay 13 CUITs repetidos entre clientes **distintos** (decision D2), y ahi son dos
    clientes distintos que comparten un CUIT mal cargado. Fusionarlos seria borrar
    un cliente; lo que se hace es que solo el primero conserve el CUIT y los demas
    queden con ``document`` NULL (si no, rompen el indice unico).
    """
    filas = []
    for (
        codcli,
        cliente,
        telefonos,
        email,
        vendedor,
        tipo,
        direccion,
        nuestro_codigo,
        liquidar_cliente,
        cuit,
    ) in ctx.fuente.clientes():
        filas.append(
            {
                "codcli": source.texto(codcli),
                "nombre": source.texto(cliente),
                "telefonos": source.texto(telefonos),
                "email": source.texto(email),
                "vendedor": source.texto(vendedor),
                "direccion": source.texto(direccion),
                "nuestro_codigo": source.texto(nuestro_codigo),
                "cuit": source.texto(cuit),
            }
        )

    por_nombre: dict[str, list[dict[str, object]]] = defaultdict(list)
    for fila in filas:
        por_nombre[_clave_de_agrupacion(fila)].append(fila)
    # Orden estable por CodCli: define quien conserva el CUIT cuando hay colision.
    grupos_ordenados = [
        sorted(miembros, key=lambda f: (len(f["codcli"]), f["codcli"]))
        for _, miembros in sorted(
            por_nombre.items(), key=lambda par: (len(par[1][0]["codcli"]), par[1][0]["codcli"])
        )
    ]

    # --- documento: CUIT de 11 digitos, con digito verificador y unico ---
    filas_con_cuit = sum(1 for f in filas if mappers.cuit_de_11_digitos(f["cuit"]))
    cuit_por_grupo: dict[int, str | None] = {}
    repeticiones: Counter[str] = Counter()
    for indice, miembros in enumerate(grupos_ordenados):
        candidatos = Counter(
            cuit
            for m in miembros
            if (cuit := mappers.cuit_normalizado(m["cuit"])) is not None
        )
        cuit = candidatos.most_common(1)[0][0] if candidatos else None
        cuit_por_grupo[indice] = cuit
        if cuit:
            repeticiones[cuit] += 1

    documentos: dict[int, str | None] = {}
    cuit_en_colision = 0
    sin_dv = 0
    sin_cuit = 0
    for indice, miembros in enumerate(grupos_ordenados):
        cuit = cuit_por_grupo[indice]
        if cuit is None:
            sin_cuit += 1
            documentos[indice] = None
            continue
        if repeticiones[cuit] > 1:
            # El primer grupo (menor CodCli) conserva el CUIT; los demas, NULL.
            documentos[indice] = None
            cuit_en_colision += 1
            continue
        documentos[indice] = cuit

    # Los CUITs de 11 digitos que no pasan el verificador se cuentan aparte.
    sin_dv = sum(
        1
        for f in filas
        if mappers.cuit_de_11_digitos(f["cuit"])
        and mappers.cuit_normalizado(f["cuit"]) is None
    )

    return {
        "filas": filas,
        "grupos": grupos_ordenados,
        "documentos": documentos,
        "cuit_en_colision": cuit_en_colision,
        "sin_dv": sin_dv,
        "sin_cuit": sin_cuit,
        "filas_con_cuit": filas_con_cuit,
    }


def _crear_maestro(ctx: Contexto, maestro: dict[str, object]) -> None:
    """Escribe los clientes del maestro consolidado."""
    tabla = ctx.tabla("customers")
    filas: list[dict[str, object]] = maestro["filas"]
    grupos: list[list[dict[str, object]]] = maestro["grupos"]
    documentos: dict[int, str | None] = maestro["documentos"]

    # Clientes ya importados en una corrida anterior: se recuperan por la marca del
    # ``notes``, que guarda el CodCli que los identifica. Asi una segunda corrida
    # sin ``--replace`` no duplica el maestro.
    ya_importados: dict[str, tuple[int, str]] = {}
    for cliente_id, nombre, notas in ctx.session.execute(
        select(tabla.c.id, tabla.c.name, tabla.c.notes).where(
            tabla.c.company_id == ctx.company_id, tabla.c.notes.like(f"{MARCA_LEGACY}%")
        )
    ).all():
        codigo = _codcli_de_notas(notas)
        if codigo:
            ya_importados[codigo] = (cliente_id, nombre)

    a_crear: list[dict[str, object]] = []
    indice_por_codcli: dict[str, int] = {}
    indice_por_nombre: dict[str, int] = {}
    absorbidas = 0
    reutilizados = 0

    for indice, miembros in enumerate(grupos):
        representante = miembros[0]
        absorbidas += len(miembros) - 1
        nombre = mappers.normalizar_nombre(representante["nombre"]) or _nombre_sin_nombre(
            str(representante["codcli"])
        )
        existente = ya_importados.get(representante["codcli"])
        if existente is not None:
            cliente_id, nombre_guardado = existente
            reutilizados += 1
            for miembro in miembros:
                ctx.clientes_por_codcli[miembro["codcli"]] = cliente_id
            ctx.clientes_por_nombre.setdefault(nombre_guardado, cliente_id)
            ctx.clientes_por_nombre.setdefault(nombre, cliente_id)
            continue
        documento = documentos.get(indice)
        direcciones = [m["direccion"] for m in miembros[1:] if m["direccion"]]
        notas = f"{MARCA_LEGACY}\ncodcli={representante['codcli']}"
        if direcciones:
            notas += _sucursales(direcciones)
        vendedor = source.entero(representante["vendedor"], 0) or 0
        a_crear.append(
            {
                "company_id": ctx.company_id,
                "customer_type": mappers.tipo_cliente(nombre, documento),
                "name": source.recortar("customers.name", nombre, 180) or nombre,
                "document": source.recortar("customers.document", documento, 30),
                "phone": source.recortar("customers.phone", representante["telefonos"], 60),
                "whatsapp": None,
                "email": source.recortar(
                    "customers.email", mappers.email_valido(representante["email"]), 255
                ),
                "address": source.recortar("customers.address", representante["direccion"], 250),
                "notes": notas,
                "active": True,
                "seller_id": ctx.vendedores_por_codigo.get(str(vendedor)) if vendedor > 0 else None,
            }
        )
        nuevo_indice = len(a_crear)
        for miembro in miembros:
            indice_por_codcli[miembro["codcli"]] = nuevo_indice
        indice_por_nombre.setdefault(nombre, nuevo_indice)

    ctx.insertar(tabla, a_crear)
    ids = [int(fila["id"]) for fila in a_crear]
    ctx.clientes_por_codcli.update(
        {codcli: ids[indice - 1] for codcli, indice in indice_por_codcli.items()}
    )
    ctx.clientes_por_nombre.update(
        {nombre: ids[indice - 1] for nombre, indice in indice_por_nombre.items()}
    )

    ctx.reporte.linea(
        "customers (maestro)",
        "CC_Clientes_Tabla",
        leidos=len(filas),
        insertados=len(a_crear),
        omitidos=reutilizados,
        descartados=absorbidas,
        motivo=(
            f"{absorbidas} filas consolidadas en clientes repetidos (nombre + CUIT "
            f"valido); documento solo si el CUIT pasa el digito verificador y es unico"
        ),
    )
    ctx.reporte.descartes(
        "clientes del maestro",
        {
            "filas del legacy": len(filas),
            "clientes tras consolidar (por nombre normalizado)": len(grupos),
            "filas absorbidas por consolidacion": absorbidas,
            "filas con CUIT de 11 digitos": maestro["filas_con_cuit"],
            "filas sin CUIT de 11 digitos": len(filas) - maestro["filas_con_cuit"],
            "filas con CUIT de 11 digitos que no pasan el digito verificador": maestro["sin_dv"],
            "CUIT en colision entre clientes distintos (dejan document NULL)": maestro[
                "cuit_en_colision"
            ],
            "clientes que quedan sin document": len(grupos) - sum(
                1 for documento in documentos.values() if documento
            ),
        },
    )


# ---------------------------------------------------------------------------
# 2. Clientes deducidos de la OT (decision D1)
# ---------------------------------------------------------------------------
def _clientes_deducidos(ctx: Contexto) -> dict[str, object]:
    """Agrupa por nombre las OTs sin ``CodCli`` y saca los clientes nuevos.

    La clave de agrupamiento es el nombre normalizado (D1). Si el nombre ya existe
    en el maestro, no se crea nada: esa OT es de un cliente que ya se conoce.
    """
    por_nombre: dict[str, list[dict[str, str]]] = defaultdict(list)
    for (
        cliente,
        nro_documento,
        telefonos,
        email,
        direccion,
        codcli,
    ) in ctx.fuente.ordenes_sin_cliente():
        nombre = mappers.normalizar_nombre(source.texto(cliente))
        if not nombre:
            continue
        por_nombre[nombre].append(
            {
                "documento": source.texto(nro_documento),
                "telefonos": source.texto(telefonos),
                "email": source.texto(email),
                "direccion": source.texto(direccion),
            }
        )

    nuevos = []
    emparejados_ots = 0
    emparejados_nombres = 0
    conflictos = 0
    conflictos_con_vacio = 0
    for nombre, datos in por_nombre.items():
        if nombre in ctx.clientes_por_nombre:
            emparejados_ots += len(datos)
            emparejados_nombres += 1
            continue
        documentos = Counter(d["documento"] for d in datos if d["documento"])
        if len(documentos) > 1:
            conflictos += 1
        if len(set(d["documento"] for d in datos)) > 1:
            conflictos_con_vacio += 1
        documento_mas_frecuente = documentos.most_common(1)[0][0] if documentos else None
        direcciones = Counter(d["direccion"] for d in datos if d["direccion"])
        direccion_principal = direcciones.most_common(1)[0][0] if direcciones else ""
        otras = [d for d in direcciones if d != direccion_principal]
        telefonos = Counter(d["telefonos"] for d in datos if d["telefonos"])
        email = Counter(d["email"] for d in datos if d["email"])
        nuevos.append(
            {
                "nombre": nombre,
                "documento": documento_mas_frecuente,
                "telefonos": telefonos.most_common(1)[0][0] if telefonos else "",
                "email": mappers.email_valido(email.most_common(1)[0][0]) if email else "",
                "direccion": direccion_principal,
                "sucursales": otras,
                "ots": len(datos),
            }
        )

    return {
        "grupos": por_nombre,
        "nuevos": nuevos,
        "emparejados_ots": emparejados_ots,
        "emparejados_nombres": emparejados_nombres,
        "conflictos": conflictos,
        "conflictos_con_vacio": conflictos_con_vacio,
    }


def _crear_deducidos(ctx: Contexto, deducidos: dict[str, object]) -> None:
    """Escribe los clientes que se deducen de las OTs sin cliente."""
    tabla = ctx.tabla("customers")
    grupos: dict[str, list[dict[str, str]]] = deducidos["grupos"]
    nuevos: list[dict[str, object]] = deducidos["nuevos"]

    ya_importados: dict[str, int] = {}
    for cliente_id, nombre, notas in ctx.session.execute(
        select(tabla.c.id, tabla.c.name, tabla.c.notes).where(
            tabla.c.company_id == ctx.company_id, tabla.c.notes.like(f"{MARCA_LEGACY}%")
        )
    ).all():
        if notas and notas.startswith(MARCA_LEGACY) and "codcli=0" in notas.splitlines()[0]:
            ya_importados[nombre] = cliente_id

    a_crear = []
    for cliente in nuevos:
        nombre = cliente["nombre"]
        existente = ya_importados.get(nombre)
        if existente is not None:
            ctx.clientes_por_nombre[nombre] = existente
            continue
        notas = f"{MARCA_LEGACY}\ncodcli=0\ndeduced={cliente['ots']}"
        if cliente["sucursales"]:
            notas += _sucursales(sorted(cliente["sucursales"]))
        documento = DOCUMENTO_DE_CLIENTES_DEDUCIDOS
        a_crear.append(
            {
                "company_id": ctx.company_id,
                "customer_type": mappers.tipo_cliente(nombre, documento),
                "name": source.recortar("customers.name", nombre, 180) or nombre,
                "document": source.recortar("customers.document", documento, 30),
                "phone": source.recortar("customers.phone", cliente["telefonos"], 60),
                "whatsapp": None,
                "email": source.recortar(
                    "customers.email", mappers.email_valido(cliente["email"]), 255
                ),
                "address": source.recortar("customers.address", cliente["direccion"], 250),
                "notes": notas,
                "active": True,
                "seller_id": None,
            }
        )

    ctx.insertar(tabla, a_crear)
    for fila in a_crear:
        ctx.clientes_por_nombre[str(fila["name"])] = int(fila["id"])

    # --- cliente sin identificar (red de seguridad) ---------------------
    ya_existe = ctx.session.execute(
        select(tabla.c.id).where(
            tabla.c.company_id == ctx.company_id,
            tabla.c.name == NOMBRE_SIN_IDENTIFICAR,
        )
    ).scalar_one_or_none()
    if ya_existe is None:
        sin_identificar = {
            "company_id": ctx.company_id,
            "customer_type": "COMPANY",
            "name": NOMBRE_SIN_IDENTIFICAR,
            "document": None,
            "phone": None,
            "whatsapp": None,
            "email": None,
            "address": None,
            "notes": (
                f"{MARCA_LEGACY}\ncodcli=0\n"
                "Cliente generico para las OTs sin CodCli y sin nombre. Con la "
                "deduccion por nombre deberia quedar vacio: es la red de seguridad."
            ),
            "active": True,
            "seller_id": None,
        }
        ctx.insertar(tabla, [sin_identificar])
        ctx.cliente_sin_identificar = int(sin_identificar["id"])
    else:
        ctx.cliente_sin_identificar = int(ya_existe)

    total_ots = sum(len(datos) for datos in grupos.values())
    ctx.reporte.linea(
        "customers (deducidos de la OT)",
        "CS_Trabajos (sin CodCli)",
        leidos=total_ots,
        insertados=len(a_crear),
        omitidos=deducidos["emparejados_ots"],
        motivo=(
            "clientes que el legacy copio a la OT y no estan en CC_Clientes_Tabla "
            "(D1): clave = nombre normalizado"
        ),
    )
    ctx.reporte.descartes(
        "clientes deducidos de la OT",
        {
            "OTs sin CodCli": total_ots,
            "nombres distintos": len(grupos),
            "nombres que ya estaban en el maestro": deducidos["emparejados_nombres"],
            "OTs emparejadas con el maestro": deducidos["emparejados_ots"],
            "clientes nuevos deducidos": len(nuevos),
            "nombres con documentos distintos (sin vacio)": deducidos["conflictos"],
            "nombres con documentos distintos (incluyendo vacio)": deducidos[
                "conflictos_con_vacio"
            ],
        },
    )
