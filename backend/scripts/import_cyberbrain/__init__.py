"""Paquete del importador de CiberBrain (SQL Server -> MySQL).

El legacy de CiberBrain (base ``CiberBase``) se exporta a TSV en
``backup/_work/csv`` y desde ahi este paquete lo lleva al sistema destino.

Orden de los pasos (cada uno en su propia transaccion):

1. ``personas``: estados, usuarios, vendedores y tecnicos,
2. ``customers``: maestro de clientes consolidado,
3. ``areas``: marcas (areas con sus politicas de garantia),
4. ``equipment``: maestro de equipos,
5. ``work_orders``: ordenes de trabajo,
6. ``parts``: lineas de la OT,
7. ``technicians``: intervenciones y comisiones por linea,
8. ``invoices``: facturas.

El orden no es estetico: es el de las dependencias de clave foranea. Los clientes van
antes que las areas porque el area dice a quien se liquida; los equipos van antes que
las OTs porque la OT no tiene equipo sin serie.
"""

from __future__ import annotations

from . import mappers, report, source

__all__ = ["mappers", "report", "source"]
