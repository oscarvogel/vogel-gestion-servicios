from types import SimpleNamespace

from app.services.work_order_import_service import _suggest_status


def _status(status_id: int, name: str, *, delivered: bool = False, completed: bool = False):
    return SimpleNamespace(
        id=status_id,
        name=name,
        marks_delivered=delivered,
        marks_completed=completed,
    )


def _suggest(color_meaning: str | None, legacy_status: str | None = None):
    statuses = [
        _status(1, "Recibido"),
        _status(2, "Presupuestado"),
        _status(3, "Esperando repuesto"),
        _status(4, "Listo", completed=True),
        _status(5, "Entregado", delivered=True, completed=True),
    ]
    by_name = {status.name.casefold(): status for status in statuses}
    return _suggest_status(
        {"color_meaning": color_meaning, "legacy_status": legacy_status},
        by_name,
        statuses,
        statuses[0],
    )


def test_color_meaning_suggests_delivered():
    status, matched = _suggest("Terminado y entregado", "Terminado")
    assert (status.id, matched) == (5, True)


def test_color_meaning_suggests_ready_when_delivery_is_pending():
    status, matched = _suggest("Terminado pero falta entregar", "Terminado")
    assert (status.id, matched) == (4, True)


def test_color_meaning_suggests_waiting_for_parts():
    status, matched = _suggest("Para Repuesto", "Sin Arreglo")
    assert (status.id, matched) == (3, True)


def test_unmapped_nonrepair_color_stays_initial_for_review():
    status, matched = _suggest("Sin arreglo / No justifica reparacion", "Sin Arreglo")
    assert (status.id, matched) == (1, False)


def test_ambiguous_for_sale_or_sold_color_stays_initial_for_review():
    status, matched = _suggest("En Venta o Vendido", "Terminado")
    assert (status.id, matched) == (1, False)


def test_legacy_status_is_used_when_color_meaning_is_missing():
    status, matched = _suggest(None, "Listo")
    assert (status.id, matched) == (4, True)
