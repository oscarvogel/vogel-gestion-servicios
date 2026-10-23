"""Los pasos de la importacion, en el orden en que se ejecutan."""

from __future__ import annotations

from typing import Callable

from ..context import Contexto
from . import areas, customers, equipment, invoices, parts, personas, technicians, work_orders

#: (nombre, funcion) de cada paso. El orden lo imponen las claves foraneas.
STEPS: tuple[tuple[str, Callable[[Contexto], None]], ...] = (
    ("personas", personas.ejecutar),
    ("customers", customers.ejecutar),
    ("areas", areas.ejecutar),
    ("equipment", equipment.ejecutar),
    ("work_orders", work_orders.ejecutar),
    ("parts", parts.ejecutar),
    ("technicians", technicians.ejecutar),
    ("invoices", invoices.ejecutar),
)

__all__ = ["STEPS"]
