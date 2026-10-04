"""Presupuestos con IA desde datos reales (#44, sub-issue 4).

La restriccion que este sub-issue no negocia es una sola: **la IA no puede inventar precios**.
Todo lo de abajo existe para demostrar que eso no es una instruccion en el prompt sino una
propiedad del diseno, y que un test la verifica:

- El presupuesto se arma con los trabajos y repuestos que ya estan cargados en la orden.
- Cada precio sale de un dato real de esa linea, y la linea dice de cual.
- Lo que falta queda **pendiente**, nunca estimado en silencio.
- `generar_presupuesto` no tiene ningun campo por donde mandar un precio.
- Con `show_internal_costs` apagado, la IA no ve costos ni margenes, y el costo tampoco le
  sirve para derivar el precio (porque el precio derivado revela el costo).

Y las de siempre, que no hay que relaxingar porque sea un sub-issue de precios: la propuesta
no escribe, la escritura escribe lo que la persona confirmo, y nada de otra empresa.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.ai_action_proposal import FALLIDA, PENDIENTE, RIESGO_FINANCIERO, AiActionProposal
from app.models.company import CompanyParameter, ParameterDefinition
from app.models.work_order import WorkOrder, WorkOrderStatus
from app.models.work_order_quote import (
    WorkOrderDiagnosis,
    WorkOrderExecutionItem,
    WorkOrderQuote,
    WorkOrderQuoteItem,
)
from app.services import work_orders as wo_service
from app.services.ai import proposals
from app.services.ai.tools import ToolContext, disponibles, ejecutar
from app.services.ai.tools.write import TOOLS as TOOLS_ESCRITURA
from tests.test_ai import _dar_permiso_ia, _habilitar
from tests.test_work_orders import setup

TODOS = frozenset(
    {
        "ai.use", "customers.view", "customers.manage", "equipment.view", "equipment.manage",
        "work_orders.view", "work_orders.manage",
    }
)


def _contexto(db, company_id, permisos=TODOS, user_id=1):
    return ToolContext(db=db, company_id=company_id, user_id=user_id, permissions=permisos)


def _proponer(db, company_id, tool, argumentos, permisos=TODOS):
    return ejecutar(tool, argumentos, _contexto(db, company_id, permisos))


def _set_parameter(db, company, key, value):
    d = db.query(ParameterDefinition).filter_by(parameter=key).first()
    if d is None:
        d = ParameterDefinition(parameter=key, default_value=str(value), description=key,
                                data_type="string", category="precios", editable=True, active=True)
        db.add(d)
        db.flush()
    o = db.query(CompanyParameter).filter_by(company_id=company.id, parameter_definition_id=d.id).first()
    if o is None:
        db.add(CompanyParameter(company_id=company.id, parameter_definition_id=d.id, value=str(value)))
    else:
        o.value = str(value)
    db.commit()


def _escenario(db, sufijo, *, markup="50", diagnostico=True):
    """Empresa con una orden,Items de trabajo y repuestos, y el diagnostico cargado."""
    company, user, customer, equipment = setup(db, sufijo)
    _habilitar(db, company.id)
    _dar_permiso_ia(db, company.id)
    _set_parameter(db, company, "pricing.parts_markup_percent", markup)

    # El `setup` compartido crea el estado "Presupuestado" pero sin `marks_quoted`, asi que en
    # los tests no hay ningun estado de destino al emitir. En produccion la empresa marca el
    # estado, y ahi es donde se decide que la orden se mueve al presupuestar. Se marca aca para
    # que el test mida el comportamiento real y no un atajo.
    presupuestado = (
        db.query(WorkOrderStatus)
        .filter_by(company_id=company.id, name="Presupuestado")
        .first()
    )
    if presupuestado is not None:
        presupuestado.marks_quoted = True
        db.commit()

    orden = wo_service.crear_orden(
        db, company_id=company.id, user_id=user.id, customer_id=customer.id,
        equipment_id=equipment.id, reported_fault="No enciende",
    )
    db.commit()
    if diagnostico:
        wo_service.guardar_diagnostico(
            db, company_id=company.id, user_id=user.id,
            work_order_id=orden.id, diagnosis="Fuente quemada",
        )
        db.commit()
    return company, user, orden


def _ejecucion(db, company, orden, item_type, descripcion, cantidad=1, costo=0, precio=0):
    fila = WorkOrderExecutionItem(
        company_id=company.id, work_order_id=orden.id, item_type=item_type,
        description=descripcion, quantity=Decimal(str(cantidad)),
        unit_cost=Decimal(str(costo)), unit_price=Decimal(str(precio)),
        created_by_user_id=1,
    )
    db.add(fila)
    db.commit()
    return fila


# --- los precios salen de la orden, y se puede demostrar de donde -------------------------


def test_el_calculo_arma_una_linea_por_trabajo_con_el_id_del_dato_de_origen(db_session):
    """Cada linea dice de que trabajo o repuesto salio: eso es la trazabilidad."""
    company, _, orden = _escenario(db_session, "pres-trazable")
    repuesto = _ejecucion(db_session, company, orden, "PART", "Fuente 24V", cantidad=2,
                          costo=10000, precio=0)

    resultado = _proponer(db_session, company.id, "calcular_presupuesto", {"orden": orden.id})

    assert resultado.ok is True
    assert resultado.data["encontrado"] is True
    linea = resultado.data["items"][0]
    assert linea["origen_id"] == repuesto.id
    assert linea["descripcion"] == "Fuente 24V"
    assert linea["tipo"] == "PART"


def test_el_precio_de_un_repuesto_sale_del_costo_con_el_margen_de_la_empresa(db_session):
    """Sin precio cargado, el precio es costo + markup. Y lo dice de donde salio."""
    company, _, orden = _escenario(db_session, "pres-markup", markup="50")
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=10000, precio=0)

    datos = _proponer(db_session, company.id, "calcular_presupuesto", {"orden": orden.id}).data

    assert datos["items"][0]["origen_del_precio"] == "costo_mas_markup"
    assert datos["items"][0]["precio_unitario"] == "15000.00"
    assert datos["items"][0]["markup"] == "50"
    assert datos["total"] == "15000.00"


def test_un_precio_ya_cargado_manda_sobre_el_margen(db_session):
    """Si alguien cargo el precio, el markup no se lo toca."""
    company, _, orden = _escenario(db_session, "pres-precio-fijo", markup="50")
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=10000, precio=22000)

    datos = _proponer(db_session, company.id, "calcular_presupuesto", {"orden": orden.id}).data

    assert datos["items"][0]["origen_del_precio"] == "precio_cargado"
    assert datos["items"][0]["precio_unitario"] == "22000.00"


def test_los_subtotales_separan_repuestos_de_mano_de_obra(db_session):
    company, _, orden = _escenario(db_session, "pres-subtotales")
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=10000, precio=0)
    _ejecucion(db_session, company, orden, "LABOR", "Resoldado", cantidad=2, costo=8000, precio=0)

    datos = _proponer(db_session, company.id, "calcular_presupuesto", {"orden": orden.id}).data

    assert datos["subtotal_repuestos"] == "15000.00"
    assert datos["subtotal_manos_de_obra"] == "16000.00"
    assert datos["total"] == "31000.00"


# --- lo que falta queda pendiente, no estimado ------------------------------------------


def test_una_linea_sin_precio_ni_costo_queda_pendiente_y_no_se_estima(db_session):
    """El caso central del sub-issue: no hay dato, entonces no hay precio."""
    company, _, orden = _escenario(db_session, "pres-pendiente")
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=0, precio=0)

    datos = _proponer(db_session, company.id, "calcular_presupuesto", {"orden": orden.id}).data

    linea = datos["items"][0]
    assert linea["precio_unitario"] is None
    assert linea["total_linea"] is None
    assert linea["origen_del_precio"] == "sin_precio"
    assert linea["pendiente"]
    assert datos["pendientes"], "tiene que decir que falta algo"
    assert datos["puede_generar"] is False
    # Y el total no se infla con el pendiente como si valiera cero.
    assert datos["total"] == "0.00"


def test_una_orden_sin_trabajos_no_tiene_presupuesto_que_hacer(db_session):
    company, _, orden = _escenario(db_session, "pres-vacia")

    datos = _proponer(db_session, company.id, "calcular_presupuesto", {"orden": orden.id}).data

    assert datos["puede_generar"] is False
    assert datos["pendientes"]


def test_sin_diagnostico_no_se_puede_presupuestar_y_dice_que_falta(db_session):
    company, _, orden = _escenario(db_session, "pres-sin-diag", diagnostico=False)
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=1000, precio=0)

    datos = _proponer(db_session, company.id, "calcular_presupuesto", {"orden": orden.id}).data

    assert datos["puede_generar"] is False
    assert datos["motivos_de_dominio"]
    assert datos["diagnostico"]["cargado"] is False


def test_la_mano_de_obra_sin_precio_carga_aviso_de_que_no_tiene_margen(db_session):
    """El numero sale de un dato real, pero la mano de obra no lleva markup: hay que avisar."""
    company, _, orden = _escenario(db_session, "pres-margen-cero")
    _ejecucion(db_session, company, orden, "LABOR", "Resoldado", costo=8000, precio=0)

    datos = _proponer(db_session, company.id, "calcular_presupuesto", {"orden": orden.id}).data

    assert datos["items"][0]["precio_unitario"] == "8000.00"
    assert datos["avisos"], "tiene que avisar que el precio sale del costo sin margen"
    # No bloquea: el precio es real.
    assert datos["puede_generar"] is True


# --- la empresa que no muestra costos internos ------------------------------------------


def test_con_costos_ocultos_la_ia_no_ve_costo_ni_markup_ni_margen(db_session):
    company, _, orden = _escenario(db_session, "pres-ocultos")
    _set_parameter(db_session, company, "work_orders.show_internal_costs", "false")
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=10000, precio=25000)

    datos = _proponer(db_session, company.id, "calcular_presupuesto", {"orden": orden.id}).data

    assert datos["costos_visibles"] is False
    linea = datos["items"][0]
    assert "costo_unitario" not in linea
    assert "markup" not in linea
    assert "margen" not in linea


def test_con_costos_ocultos_el_costo_no_sirve_para_derivar_el_precio(db_session):
    """El precio derivado del costo revela el costo: por eso no se deriva."""
    company, _, orden = _escenario(db_session, "pres-ocultos-deriva")
    _set_parameter(db_session, company, "work_orders.show_internal_costs", "false")
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=10000, precio=0)

    datos = _proponer(db_session, company.id, "calcular_presupuesto", {"orden": orden.id}).data

    linea = datos["items"][0]
    assert linea["precio_unitario"] is None
    assert linea["pendiente"]
    assert datos["puede_generar"] is False


def test_con_costos_visibles_el_costo_si_sirve_para_derivar(db_session):
    """El caso contrario, para que el test anterior no pase por el camino equivocado."""
    company, _, orden = _escenario(db_session, "pres-visibles-deriva")
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=10000, precio=0)

    datos = _proponer(db_session, company.id, "calcular_presupuesto", {"orden": orden.id}).data

    assert datos["costos_visibles"] is True
    assert datos["items"][0]["costo_unitario"] == "10000.00"


# --- la herramienta de escribir no tiene por donde mandar un precio ----------------------


def test_generar_presupuesto_no_tiene_ningun_parametro_de_importe():
    """El test estructural del sub-issue: no hay campo, no hay por que inventar.

    Si alguien agrega un `precio_unitario` o un `items` a esta herramienta, este test
    revienta. Es la red que hace que la regla no dependa de que alguien se acuerde de ella.
    """
    herramienta = next(t for t in TOOLS_ESCRITURA if t.name == "generar_presupuesto")
    propiedades = set(herramienta.parameters.get("properties", {}))

    assert propiedades == {"orden", "notas"}
    assert not any(
        p in propiedades for p in ("precio", "precio_unitario", "items", "costo", "total", "markup")
    )


def test_proponer_el_presupuesto_no_es_emitirlo(db_session):
    """La regla de siempre: propone, no escribe."""
    company, _, orden = _escenario(db_session, "prop-pres-no-escribe")
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=1000, precio=0)

    antes = db_session.query(WorkOrderQuote).filter_by(company_id=company.id).count()
    resultado = _proponer(db_session, company.id, "generar_presupuesto", {"orden": orden.id})

    assert resultado.ok is True
    assert resultado.data["riesgo"] == RIESGO_FINANCIERO
    assert db_session.query(WorkOrderQuote).filter_by(company_id=company.id).count() == antes


def test_proponer_con_un_precio_faltante_falla_diciendo_que_falta_y_no_deja_nada(db_session):
    """No es "proponer con lo que hay": es no proponer, y explicar."""
    company, _, orden = _escenario(db_session, "prop-pres-pendiente")
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=0, precio=0)

    resultado = _proponer(db_session, company.id, "generar_presupuesto", {"orden": orden.id})

    assert resultado.ok is False
    assert resultado.error_code == "argumentos_invalidos"
    assert "Fuente" in resultado.error_message
    assert db_session.query(AiActionProposal).filter_by(company_id=company.id).count() == 0


def test_la_propuesta_le_muestra_al_modelo_como_va_a_quedar(db_session):
    """El operador tiene que ver los importes antes de confirmar, no despues."""
    company, _, orden = _escenario(db_session, "prop-pres-previo")
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=1000, precio=0)

    datos = _proponer(db_session, company.id, "generar_presupuesto", {"orden": orden.id}).data

    assert datos["previo"]["total"] == "1500.00"
    assert datos["previo"]["items"][0]["descripcion"] == "Fuente"


# --- confirmar escribe lo que dice la orden ----------------------------------------------


def test_confirmar_emite_el_presupuesto_con_las_lineas_de_la_orden(db_session):
    company, _, orden = _escenario(db_session, "pres-confirmar")
    _ejecucion(db_session, company, orden, "PART", "Fuente", cantidad=2, costo=10000, precio=0)
    _ejecucion(db_session, company, orden, "LABOR", "Resoldado", costo=0, precio=20000)

    propuesta = _proponer(db_session, company.id, "generar_presupuesto", {"orden": orden.id})
    confirmada = proposals.confirmar(
        db_session, propuesta.data["propuesta_id"], company_id=company.id, user_id=1
    )

    assert confirmada.status == "aplicada"
    presupuesto = (
        db_session.query(WorkOrderQuote).filter_by(company_id=company.id).one()
    )
    # 2 fuentes a 15000 (costo 10000 con 50% de margen) mas 20000 de mano de obra.
    assert presupuesto.total == Decimal("50000.00")
    assert presupuesto.version == 1
    lineas = (
        db_session.query(WorkOrderQuoteItem)
        .filter_by(quote_id=presupuesto.id)
        .order_by(WorkOrderQuoteItem.id)
        .all()
    )
    assert [l.description for l in lineas] == ["Fuente", "Resoldado"]
    assert [l.item_type for l in lineas] == ["PART", "LABOR"]
    assert lineas[0].line_total == Decimal("30000.00")
    assert lineas[1].line_total == Decimal("20000.00")


def test_confirmar_mueve_la_orden_a_presupuestado_y_cierra_el_diagnostico(db_session):
    """Las dos cosas que hace la pantalla al emitir, y que tambien tienen que pasar por aca."""
    company, _, orden = _escenario(db_session, "pres-estado")
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=1000, precio=0)

    propuesta = _proponer(db_session, company.id, "generar_presupuesto", {"orden": orden.id})
    proposals.confirmar(db_session, propuesta.data["propuesta_id"], company_id=company.id, user_id=1)

    db_session.refresh(orden)
    estado = db_session.get(WorkOrderStatus, orden.status_id)
    assert estado.name == "Presupuestado"
    diagnostico = (
        db_session.query(WorkOrderDiagnosis).filter_by(company_id=company.id, work_order_id=orden.id).one()
    )
    assert diagnostico.is_open is False


def test_si_entre_la_propuesta_y_la_confirmacion_falta_un_precio_queda_fallida(db_session):
    """El estado de la orden manda en el momento de aplicar, no en el de proponer."""
    company, _, orden = _escenario(db_session, "pres-cambio")
    repuesto = _ejecucion(db_session, company, orden, "PART", "Fuente", costo=1000, precio=0)

    propuesta = _proponer(db_session, company.id, "generar_presupuesto", {"orden": orden.id})
    # Mientras la propuesta esperaba, alguien vacio el precio de la linea.
    repuesto.unit_price = Decimal("0")
    repuesto.unit_cost = Decimal("0")
    db_session.commit()

    with pytest.raises(proposals.ErrorDePropuesta):
        proposals.confirmar(
            db_session, propuesta.data["propuesta_id"], company_id=company.id, user_id=1
        )

    assert db_session.query(WorkOrderQuote).filter_by(company_id=company.id).count() == 0
    fila = db_session.get(AiActionProposal, propuesta.data["propuesta_id"])
    assert fila.status == FALLIDA
    assert fila.result_error


# --- aislamiento y permisos -------------------------------------------------------------


def test_una_orden_de_otra_empresa_devuelve_vacio_y_no_un_error(db_session):
    """Mismo criterio que las otras lecturas: indistinguible de una orden que no existe."""
    company_a, _, orden_a = _escenario(db_session, "pres-iso-a")
    company_b, _, _ = _escenario(db_session, "pres-iso-b")
    _ejecucion(db_session, company_a, orden_a, "PART", "Fuente secreta", costo=5000, precio=0)

    datos = _proponer(db_session, company_b.id, "calcular_presupuesto", {"orden": orden_a.id}).data

    assert datos["encontrado"] is False
    assert "Fuente" not in str(datos)


def test_no_se_puede_presupuestar_una_orden_de_otra_empresa(db_session):
    company_a, _, orden_a = _escenario(db_session, "pres-iso-c")
    company_b, _, _ = _escenario(db_session, "pres-iso-d")
    _ejecucion(db_session, company_a, orden_a, "PART", "Fuente", costo=5000, precio=0)

    resultado = _proponer(db_session, company_b.id, "generar_presupuesto", {"orden": orden_a.id})

    assert resultado.ok is False
    assert db_session.query(AiActionProposal).filter_by(company_id=company_b.id).count() == 0
    assert db_session.query(WorkOrderQuote).filter_by(company_id=company_b.id).count() == 0


def test_sin_work_orders_manage_no_se_ofrece_generar_presupuesto(db_session):
    company, _, orden = _escenario(db_session, "pres-sin-permiso")
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=1000, precio=0)

    sin_gestion = frozenset({"ai.use", "work_orders.view"})
    nombres = {t.name for t in disponibles(sin_gestion)}

    assert "generar_presupuesto" not in nombres
    assert "calcular_presupuesto" in nombres, "leer el calculo es parte de ver la orden"
    resultado = _proponer(db_session, company.id, "generar_presupuesto", {"orden": orden.id},
                          permisos=sin_gestion)
    assert resultado.ok is False
    assert resultado.error_code == "sin_permiso"


# --- la API y la IA escriben por el mismo camino ----------------------------------------


def test_un_trabajo_agregado_por_la_ia_se_guarda_como_LABOR_y_no_como_WORK(db_session):
    """El dominio entero habla PART y LABOR. `agregar_trabajo` escribia "WORK".

    No se veia roto porque la pantalla cae en la rama "no es PART" y lo muestra como Trabajo.
    Se veia al usar el dato: cualquier consulta que filtre `item_type = 'LABOR'` — y el
    calculo del presupuesto es una — dejaba afuera esas filas. Este test fija el valor para
    que el que escriba la fila de abajo tenga que conocer el vocabulario.
    """
    company, _, orden = _escenario(db_session, "labor-vocab")

    propuesta = _proponer(db_session, company.id, "agregar_trabajo",
                          {"orden": orden.id, "descripcion": "Resoldado de conector",
                           "cantidad": 1, "precio_unitario": 20000})
    proposals.confirmar(db_session, propuesta.data["propuesta_id"], company_id=company.id, user_id=1)

    fila = (
        db_session.query(WorkOrderExecutionItem)
        .filter_by(company_id=company.id, work_order_id=orden.id)
        .one()
    )
    assert fila.item_type == "LABOR"
    # Y el calculo lo trata como mano de obra, que es lo que hace sin margen.
    datos = _proponer(db_session, company.id, "calcular_presupuesto", {"orden": orden.id}).data
    assert datos["items"][0]["tipo"] == "LABOR"
    assert datos["subtotal_manos_de_obra"] == "20000.00"


def test_el_calculo_de_la_ia_y_el_de_la_pantalla_dan_el_mismo_numero(db_session):
    """Si divergieran, la IA estaria aplicando reglas que la aplicacion no aplica."""
    company, user, orden = _escenario(db_session, "pres-mismo-camino")
    _ejecucion(db_session, company, orden, "PART", "Fuente", cantidad=2, costo=10000, precio=0)

    calculado = _proponer(db_session, company.id, "calcular_presupuesto", {"orden": orden.id}).data

    presupuesto = wo_service.crear_presupuesto(
        db_session, company_id=company.id, user_id=user.id, work_order_id=orden.id,
        items=[{"item_type": "PART", "description": "Fuente", "quantity": 2,
                "unit_cost": 10000, "unit_price": None}],
    )
    db_session.commit()

    assert str(presupuesto.total) == calculado["total"] == "30000.00"
    assert str(presupuesto.subtotal_parts) == calculado["subtotal_repuestos"]


def test_una_orden_entregada_no_admite_presupuesto(db_session):
    company, user, orden = _escenario(db_session, "pres-entregada")
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=1000, precio=0)
    entregada = (
        db_session.query(WorkOrderStatus)
        .filter_by(company_id=company.id, is_final=True)
        .first()
    )
    orden.status_id = entregada.id
    db_session.commit()

    datos = _proponer(db_session, company.id, "calcular_presupuesto", {"orden": orden.id}).data
    assert datos["puede_generar"] is False
    assert datos["motivos_de_dominio"]

    resultado = _proponer(db_session, company.id, "generar_presupuesto", {"orden": orden.id})
    assert resultado.ok is False
    assert db_session.query(WorkOrderQuote).filter_by(company_id=company.id).count() == 0
