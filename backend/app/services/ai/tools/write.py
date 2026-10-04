"""Herramientas de escritura: proponen, no escriben (#44 sub-issue 3).

Ninguna de estas herramientas toca el dominio. Lo que hacen es **dejar una propuesta
pendiente** y devolverle al modelo el id, para que le diga al operador que hay algo que
confirmar. La escritura ocurre recien cuando una persona llama al endpoint de confirmacion.

Por que asi y no "escribo y después se revisa":

- Un modelo puede pedir una escritura por un cliente equivocado, con un precio equivocado, o
  sobre una orden que no era. Si eso ya esta en la base, deshacerlo es trabajo de persona.
- Si la propuesta se guarda antes, la persona puede **corregir** los argumentos y confirmar lo
  corregido. Se escribe lo que la persona vio, no lo que el modelo quiso.
- Y queda el rastro: propuso el modelo, confirmo la persona, que se termino persistiendo.

El costo es que el operador tiene un paso mas. Es el precio de que una accion hecha "por IA"
sea auditable, que es lo que el issue pide.

## El riesgo se calcula al proponer

`agregar_repuesto` mueve plata y `actualizar_ot` a un estado con aviso dispara un WhatsApp al
cliente, que no se puede deshacer. Los dos se marcan con `riesgo` y `requires_notification` en
el momento de proponer, que es cuando la persona todavía puede decidir.
"""
from __future__ import annotations

from decimal import Decimal

from app.models.ai_action_proposal import (
    RIESGO_COMUNICACION,
    RIESGO_FINANCIERO,
    RIESGO_NINGUNO,
)
from app.services.ai import proposals
from app.services.ai.tools.base import ToolContext, ToolError, ToolOutcome, ToolSpec
from app.services.ai.tools.validacion import (
    MAX_DIRECCION,
    MAX_DOCUMENTO,
    MAX_EMAIL,
    MAX_MODELO,
    MAX_NOMBRE,
    MAX_SERIE,
    MAX_TEXTO,
    MAX_TEXTO_CORTO,
    MAX_TELEFONO,
    decimal,
    entero,
    texto,
    texto_opcional,
)

MENSAJE_PROPUESTA = (
    "Dejé la propuesta #{id} esperando que un humano la confirme. "
    "Decile al operador qué es y que la revise: no se escribió nada todavía."
)


def _dejar(
    ctx: ToolContext,
    tool: str,
    argumentos: dict,
    riesgo: str,
    notifica: bool,
    previo: dict | None = None,
) -> ToolOutcome:
    """Registra la propuesta y le devuelve al modelo lo que necesita para avisarle al operador.

    ``previo`` es lo que el modelo le va a poder contar al operador antes de que confirme: por
    ejemplo, como quedaria el presupuesto. Va en la respuesta, no en la propuesta, porque es
    informacion de lectura y no algo que la persona vaya a editar.
    """
    # Los campos que el modelo no lleno van como null. Guardarlos asi en la propuesta es ruido
    # para la pantalla y hace que "lo que cambio" muestre diferencias que no son diferencias.
    limpio = {k: v for k, v in argumentos.items() if v is not None}
    propuesta = proposals.crear(
        ctx.db,
        company_id=ctx.company_id,
        user_id=ctx.user_id or 0,
        tool=tool,
        argumentos=limpio,
        riesgo=riesgo,
        notifica=notifica,
    )
    datos = {
        "propuesta_id": propuesta.id,
        "estado": propuesta.status,
        "riesgo": riesgo,
        "avisa_al_cliente": notifica,
        "lo_que_hay_que_confirmar": limpio,
    }
    if previo:
        datos["previo"] = previo
    return ToolOutcome(ok=True, data=datos)


# --------------------------------------------------------------------------------------
# crear_cliente
# --------------------------------------------------------------------------------------


def _crear_cliente(ctx: ToolContext, args: dict) -> ToolOutcome:
    argumentos = {
        "nombre": texto(args.get("nombre"), "nombre", maximo=MAX_NOMBRE),
        "documento": texto_opcional(args.get("documento"), "documento", maximo=MAX_DOCUMENTO),
        "telefono": texto_opcional(args.get("telefono"), "telefono", maximo=MAX_TELEFONO),
        "whatsapp": texto_opcional(args.get("whatsapp"), "whatsapp", maximo=MAX_TELEFONO),
        "email": texto_opcional(args.get("email"), "email", maximo=MAX_EMAIL),
        "direccion": texto_opcional(args.get("direccion"), "direccion", maximo=MAX_DIRECCION),
        "notas": texto_opcional(args.get("notas"), "notas", maximo=MAX_TEXTO),
    }
    return _dejar(ctx, "crear_cliente", argumentos, RIESGO_NINGUNO, False)


# --------------------------------------------------------------------------------------
# crear_equipo
# --------------------------------------------------------------------------------------


def _crear_equipo(ctx: ToolContext, args: dict) -> ToolOutcome:
    argumentos = {
        "cliente_id": entero(args.get("cliente_id"), "cliente_id", minimo=1),
        "categoria": texto(args.get("categoria"), "categoria", maximo=MAX_NOMBRE),
        "marca": texto_opcional(args.get("marca"), "marca", maximo=100),
        "modelo": texto_opcional(args.get("modelo"), "modelo", maximo=MAX_MODELO),
        "numero_de_serie": texto_opcional(args.get("numero_de_serie"), "numero_de_serie", maximo=MAX_SERIE),
        "descripcion": texto_opcional(args.get("descripcion"), "descripcion", maximo=300),
        "notas": texto_opcional(args.get("notas"), "notas", maximo=MAX_TEXTO),
    }
    return _dejar(ctx, "crear_equipo", argumentos, RIESGO_NINGUNO, False)


# --------------------------------------------------------------------------------------
# crear_ot
# --------------------------------------------------------------------------------------


def _crear_ot(ctx: ToolContext, args: dict) -> ToolOutcome:
    argumentos = {
        "cliente_id": entero(args.get("cliente_id"), "cliente_id", minimo=1),
        "equipo_id": entero(args.get("equipo_id"), "equipo_id", minimo=1),
        "falla_reportada": texto(args.get("falla_reportada"), "falla_reportada", maximo=MAX_TEXTO),
        "condicion_fisica": texto_opcional(args.get("condicion_fisica"), "condicion_fisica", maximo=MAX_TEXTO),
        "accesorios": texto_opcional(args.get("accesorios"), "accesorios", maximo=MAX_TEXTO),
        "notas": texto_opcional(args.get("notas"), "notas", maximo=MAX_TEXTO),
    }
    return _dejar(ctx, "crear_ot", argumentos, RIESGO_NINGUNO, False)


# --------------------------------------------------------------------------------------
# actualizar_ot
# --------------------------------------------------------------------------------------


def _actualizar_ot(ctx: ToolContext, args: dict) -> ToolOutcome:
    """Un cambio de estado puede disparar un aviso al cliente, y eso no se puede deshacer.

    Por eso se calcula **antes** de proponer: `planear_aviso` no escribe nada, solo dice qué
    se mandaría. Si la propuesta se marcara al aplicar, la persona ya habria confirmado a
    ciegas.
    """
    from app.services import work_orders as wo_service

    orden_id = entero(args.get("orden"), "orden", minimo=1)
    argumentos: dict = {"orden": orden_id}

    estado_id = args.get("estado_id")
    if estado_id is None:
        # Aceptar el nombre del estado es mucho mas util para el modelo que el id, que no
        # tiene forma de adivinar. Se resuelve contra los estados de la empresa.
        nombre_estado = texto(args.get("estado"), "estado", maximo=MAX_NOMBRE)
        objetivo = _estado_por_nombre(ctx, nombre_estado)
        argumentos["estado_id"] = objetivo.id
    else:
        objetivo_id = entero(estado_id, "estado_id", minimo=1)
        argumentos["estado_id"] = objetivo_id

    if args.get("entrega_estimada") is not None:
        argumentos["entrega_estimada"] = texto(
            args.get("entrega_estimada"), "entrega_estimada", maximo=40
        )
    for campo, clave in (("notas", "notas"), ("condicion_fisica", "condicion_fisica"),
                         ("accesorios", "accesorios"), ("nota", "nota")):
        valor = texto_opcional(args.get(campo), campo, maximo=MAX_TEXTO)
        if valor is not None:
            argumentos[clave] = valor

    if len(argumentos) == 1:
        # Solo vino el id de la orden: sin estado ni campos, no hay nada que proponer. Un
        # cambio de estado SOLO si es valido, y es de lo mas frecuente: por eso el corte es
        # cuando no quedo ningun otro campo, no cuando no quedo mas que el estado.
        raise ToolError(
            "argumentos_invalidos",
            "La propuesta no trae ni un estado ni un campo para cambiar.",
        )

    aviso: list[dict] = []
    try:
        aviso = wo_service.planear_aviso(
            ctx.db, company_id=ctx.company_id, work_order_id=orden_id,
            status_id=argumentos["estado_id"],
        )
    except wo_service.ErrorDeDominio as exc:
        raise ToolError("argumentos_invalidos", exc.mensaje) from None

    notifica = bool([a for a in aviso if not a.get("skipped")])
    riesgo = RIESGO_COMUNICACION if notifica else RIESGO_NINGUNO
    return _dejar(ctx, "actualizar_ot", argumentos, riesgo, notifica)


def _estado_por_nombre(ctx: ToolContext, nombre: str):
    from sqlalchemy import select

    from app.models.work_order import WorkOrderStatus

    encontrado = ctx.db.execute(
        select(WorkOrderStatus).where(
            WorkOrderStatus.company_id == ctx.company_id,
            WorkOrderStatus.active.is_(True),
            WorkOrderStatus.name == nombre,
        )
    ).scalars().first()
    if encontrado is None:
        disponibles = [
            n for (n,) in ctx.db.execute(
                select(WorkOrderStatus.name).where(
                    WorkOrderStatus.company_id == ctx.company_id,
                    WorkOrderStatus.active.is_(True),
                ).order_by(WorkOrderStatus.sort_order)
            ).all()
        ]
        raise ToolError(
            "argumentos_invalidos",
            f'No existe el estado "{nombre}" en esta empresa. '
            f"Los que hay son: {', '.join(disponibles) or 'ninguno'}.",
        )
    return encontrado


# --------------------------------------------------------------------------------------
# agregar_diagnostico
# --------------------------------------------------------------------------------------


def _agregar_diagnostico(ctx: ToolContext, args: dict) -> ToolOutcome:
    argumentos = {
        "orden": entero(args.get("orden"), "orden", minimo=1),
        "diagnostico": texto(args.get("diagnostico"), "diagnostico", maximo=MAX_TEXTO),
        "notas_tecnicas": texto_opcional(args.get("notas_tecnicas"), "notas_tecnicas", maximo=MAX_TEXTO),
    }
    return _dejar(ctx, "agregar_diagnostico", argumentos, RIESGO_NINGUNO, False)


# --------------------------------------------------------------------------------------
# agregar_trabajo / agregar_repuesto
# --------------------------------------------------------------------------------------


def _item(ctx: ToolContext, args: dict, tool: str) -> ToolOutcome:
    argumentos = {
        "orden": entero(args.get("orden"), "orden", minimo=1),
        "descripcion": texto(args.get("descripcion"), "descripcion", maximo=MAX_TEXTO_CORTO),
        "cantidad": str(decimal(args.get("cantidad", 1), "cantidad", minimo="0.001")),
        "precio_unitario": str(decimal(args.get("precio_unitario", 0), "precio_unitario", minimo="0")),
    }
    # El costo interno no lo propone el modelo: es un dato del negocio y ademas la empresa
    # puede tenerlo oculto del cliente. Lo puede completar la persona al confirmar.
    costo = args.get("costo_unitario")
    if costo is not None:
        argumentos["costo_unitario"] = str(decimal(costo, "costo_unitario", minimo="0"))

    mueve_plata = Decimal(argumentos["precio_unitario"]) > 0 or "costo_unitario" in argumentos
    return _dejar(ctx, tool, argumentos, RIESGO_FINANCIERO if mueve_plata else RIESGO_NINGUNO, False)


def _agregar_repuesto(ctx: ToolContext, args: dict) -> ToolOutcome:
    return _item(ctx, args, "agregar_repuesto")


def _agregar_trabajo(ctx: ToolContext, args: dict) -> ToolOutcome:
    return _item(ctx, args, "agregar_trabajo")


# --------------------------------------------------------------------------------------
# generar_presupuesto
# --------------------------------------------------------------------------------------


def _generar_presupuesto(ctx: ToolContext, args: dict) -> ToolOutcome:
    """Propone emitir el presupuesto de una orden. Los importes no se proponen: se calculan.

    Que esta herramienta **no tenga un campo de precio** es la decision de diseno que hace
    verdadera la regla del sub-issue. Si aceptara importes, el modelo podria mandarle un
    precio y quedaria igual de creible que uno real: la unica defensa seria pedirle a la
    persona que lo revisara, y una revision humana no detecta un numero inventado, solo uno
    raro. Sin campo, no hay por donde inventarlo.

    Las lineas se derivan de la orden al proponer y otra vez al aplicar. Si al aplicar ya no
    se puede generar (alguien borro un precio, o la orden se entrego), la propuesta queda
    fallida con el motivo, que tambien es auditabilidad.
    """
    from app.services import work_orders as wo_service

    orden_id = entero(args.get("orden"), "orden", minimo=1)
    argumentos: dict = {"orden": orden_id}
    notas = texto_opcional(args.get("notas"), "notas", maximo=MAX_TEXTO)
    if notas is not None:
        argumentos["notas"] = notas

    try:
        orden = wo_service.leer_orden(ctx.db, ctx.company_id, orden_id)
    except wo_service.ErrorDeDominio as exc:
        raise ToolError("argumentos_invalidos", exc.mensaje) from None

    if wo_service.es_final(ctx.db, orden):
        raise ToolError(
            "argumentos_invalidos",
            "La orden de trabajo está en un estado final (entregada) y no admite presupuestos.",
        )

    calculo = wo_service.calcular_presupuesto(
        ctx.db, company_id=ctx.company_id, work_order_id=orden_id
    )
    if not calculo["puede_generar"]:
        # Aca esta el punto donde el sub-issue dice que la IA tiene que pedir y no estimar. Si
        # falta algo, se devuelve el motivo y no queda ninguna propuesta: la persona carga el
        # dato que falta y se vuelve a pedir.
        motivos = list(calculo["motivos_de_dominio"]) + list(calculo["pendientes"])
        raise ToolError(
            "argumentos_invalidos",
            "No se puede generar el presupuesto todavía. "
            + " ".join(motivos)
            + " Decile eso al operador: los precios no se estiman, se cargan.",
        )

    # Un presupuesto es un compromiso de plata con el cliente, asi que se marca como riesgo
    # financiero: es lo que la pantalla muestra antes de que la persona confirme.
    return _dejar(
        ctx,
        "generar_presupuesto",
        argumentos,
        RIESGO_FINANCIERO,
        False,
        previo={
            "total": calculo["total"],
            "cantidad_de_lineas": len(calculo["items"]),
            "items": [
                {
                    "descripcion": linea["descripcion"],
                    "tipo": linea["tipo"],
                    "cantidad": linea["cantidad"],
                    "precio_unitario": linea["precio_unitario"],
                    "total_linea": linea["total_linea"],
                }
                for linea in calculo["items"]
            ],
            "avisos": calculo["avisos"],
        },
    )


# --------------------------------------------------------------------------------------
# Catalogo
# --------------------------------------------------------------------------------------

TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="crear_cliente",
        description=(
            "Propone dar de alta un cliente. NO lo crea: deja una propuesta que un humano "
            "tiene que confirmar. Usala cuando el operador da de alta alguien."
        ),
        parameters={
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre o razón social."},
                "documento": {"type": "string", "description": "DNI, CUIT o documento."},
                "telefono": {"type": "string"},
                "whatsapp": {"type": "string"},
                "email": {"type": "string"},
                "direccion": {"type": "string"},
                "notas": {"type": "string"},
            },
            "required": ["nombre"],
        },
        permission="customers.manage",
        run=_crear_cliente,
    ),
    ToolSpec(
        name="crear_equipo",
        description=(
            "Propone registrar un equipo de un cliente. NO lo crea hasta que un humano lo "
            "confirme. La categoría es el nombre de una categoría que ya exista en la empresa."
        ),
        parameters={
            "type": "object",
            "properties": {
                "cliente_id": {"type": "integer"},
                "categoria": {"type": "string", "description": "Nombre de la categoría."},
                "marca": {"type": "string"},
                "modelo": {"type": "string"},
                "numero_de_serie": {"type": "string"},
                "descripcion": {"type": "string"},
                "notas": {"type": "string"},
            },
            "required": ["cliente_id", "categoria"],
        },
        permission="equipment.manage",
        run=_crear_equipo,
    ),
    ToolSpec(
        name="crear_ot",
        description=(
            "Propone abrir una orden de trabajo para un equipo. NO la abre hasta que un humano "
            "la confirme. Necesita el id del cliente y el del equipo, que sale de buscar_equipo."
        ),
        parameters={
            "type": "object",
            "properties": {
                "cliente_id": {"type": "integer"},
                "equipo_id": {"type": "integer"},
                "falla_reportada": {"type": "string", "description": "Lo que dice el cliente."},
                "condicion_fisica": {"type": "string"},
                "accesorios": {"type": "string"},
                "notas": {"type": "string"},
            },
            "required": ["cliente_id", "equipo_id", "falla_reportada"],
        },
        permission="work_orders.manage",
        run=_crear_ot,
    ),
    ToolSpec(
        name="actualizar_ot",
        description=(
            "Propone cambiar el estado o un dato de una orden. NO lo aplica hasta que un "
            "humano lo confirme. Ojo: si el estado destino tiene aviso configurado, al "
            "confirmar se le manda un WhatsApp o un email al cliente y eso no se puede deshacer."
        ),
        parameters={
            "type": "object",
            "properties": {
                "orden": {"type": "integer", "description": "Id de la orden de trabajo."},
                "estado": {"type": "string", "description": "Nombre del estado de destino."},
                "estado_id": {"type": "integer", "description": "Alternativa al nombre."},
                "entrega_estimada": {"type": "string"},
                "nota": {"type": "string"},
                "notas": {"type": "string"},
                "condicion_fisica": {"type": "string"},
                "accesorios": {"type": "string"},
            },
            "required": ["orden"],
        },
        permission="work_orders.manage",
        run=_actualizar_ot,
    ),
    ToolSpec(
        name="agregar_diagnostico",
        description=(
            "Propone guardar el diagnóstico técnico de una orden. NO lo guarda hasta que un "
            "humano lo confirme."
        ),
        parameters={
            "type": "object",
            "properties": {
                "orden": {"type": "integer"},
                "diagnostico": {"type": "string"},
                "notas_tecnicas": {"type": "string"},
            },
            "required": ["orden", "diagnostico"],
        },
        permission="work_orders.manage",
        run=_agregar_diagnostico,
    ),
    ToolSpec(
        name="agregar_trabajo",
        description=(
            "Propone sumar una línea de trabajo a una orden. NO la suma hasta que un humano la "
            "confirme. Si le ponés precio, es un importe que va a la cuenta del cliente."
        ),
        parameters={
            "type": "object",
            "properties": {
                "orden": {"type": "integer"},
                "descripcion": {"type": "string"},
                "cantidad": {"type": "number"},
                "precio_unitario": {"type": "number"},
                "costo_unitario": {"type": "number", "description": "Costo interno. Opcional."},
            },
            "required": ["orden", "descripcion"],
        },
        permission="work_orders.manage",
        run=_agregar_trabajo,
    ),
    ToolSpec(
        name="agregar_repuesto",
        description=(
            "Propone sumar un repuesto a una orden. NO lo suma hasta que un humano lo confirme. "
            "El precio es lo que se le cobra al cliente, así que es un importe a revisar."
        ),
        parameters={
            "type": "object",
            "properties": {
                "orden": {"type": "integer"},
                "descripcion": {"type": "string"},
                "cantidad": {"type": "number"},
                "precio_unitario": {"type": "number"},
                "costo_unitario": {"type": "number", "description": "Costo interno. Opcional."},
            },
            "required": ["orden", "descripcion"],
        },
        permission="work_orders.manage",
        run=_agregar_repuesto,
    ),
    ToolSpec(
        name="generar_presupuesto",
        description=(
            "Propone emitir el presupuesto de una orden, con los trabajos y repuestos que ya "
            "tiene cargados. NO lo emite hasta que un humano lo confirme, y NO acepta "
            "importes: los precios salen de los datos de la orden. Antes de llamarla usá "
            "calcular_presupuesto: si esa dice que falta algún precio, pedile ese precio al "
            "operador en vez de estimarlo."
        ),
        parameters={
            "type": "object",
            "properties": {
                "orden": {"type": "integer", "description": "Id de la orden de trabajo."},
                "notas": {"type": "string", "description": "Observación para el presupuesto."},
            },
            "required": ["orden"],
        },
        permission="work_orders.manage",
        run=_generar_presupuesto,
    ),
)
