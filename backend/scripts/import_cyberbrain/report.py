"""Cuadre de la importacion: que entró, que se descarto y por que.

El cuadre es la unica forma de saber que el importador no perdio datos: se escribe
en un archivo de texto (para quedar como registro) y se muestra por stdout (para
verlo en el momento).

Los numeros esperados estan en ``docs/plan-importacion-ciberbrain.md``: el cuadre
compara lo leido del TSV contra lo efectivamente escrito, que es lo que hace falta
para que la cuenta cierre.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Mapping


def _formato_importe(valor: Decimal | int | float | None) -> str:
    """Importe con separador de miles y dos decimales (como lo muestra el legacy)."""
    if valor is None:
        valor = Decimal("0")
    if not isinstance(valor, Decimal):
        valor = Decimal(str(valor))
    entero = f"{valor:,.2f}"
    return entero.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


@dataclass
class LineaCuadre:
    """Una fila del cuadre: una entidad del destino y su origen."""

    entidad: str
    origen: str
    leidos: int = 0
    insertados: int = 0
    omitidos: int = 0
    descartados: int = 0
    motivo: str = ""
    importes: dict[str, Decimal] = field(default_factory=dict)

    def __str__(self) -> str:
        partes = [
            f"{self.entidad:<26}",
            f"{self.leidos:>9}",
            f"{self.insertados:>9}",
            f"{self.omitidos:>9}",
            f"{self.descartados:>9}",
        ]
        return "  ".join(partes)


class Reporte:
    """Acumula el cuadre de la importacion y lo arma para imprimir."""

    def __init__(self, empresa: str, origen: str, modo: str) -> None:
        self.empresa = empresa
        self.origen = origen
        self.modo = modo
        self.lineas: list[LineaCuadre] = []
        self.observaciones: list[str] = []
        self._descartes: list[tuple[str, dict[str, int]]] = []
        self.secciones: list[tuple[str, list[str]]] = []

    # -- carga de datos ---------------------------------------------------
    def linea(
        self,
        entidad: str,
        origen: str,
        leidos: int = 0,
        insertados: int = 0,
        omitidos: int = 0,
        descartados: int = 0,
        motivo: str = "",
        importes: Mapping[str, Decimal] | None = None,
    ) -> LineaCuadre:
        """Registra el cuadre de una entidad."""
        fila = LineaCuadre(
            entidad=entidad,
            origen=origen,
            leidos=leidos,
            insertados=insertados,
            omitidos=omitidos,
            descartados=descartados,
            motivo=motivo,
            importes=dict(importes or {}),
        )
        self.lineas.append(fila)
        return fila

    def observacion(self, texto: str) -> None:
        """Anota una decision o una diferencia con lo esperado."""
        self.observaciones.append(texto)

    def descartes(self, titulo: str, conteos: dict[str, int]) -> None:
        """Anota los descartes de una entidad: cuantos y por que.

        Lo que no entra tiene que quedar a la vista: un numero escondido es un
        numero que despues nadie puede explicar.
        """
        self._descartes.append((titulo, dict(conteos)))

    def seccion(self, titulo: str, lineas: Iterable[str]) -> None:
        """Agrega un bloque de detalle (por ejemplo, el cierre por empresa a liquidar)."""
        self.secciones.append((titulo, list(lineas)))

    # -- salida -----------------------------------------------------------
    def render(self) -> str:
        """Arma el cuadro completo como texto."""
        salida: list[str] = []
        salida.append("=" * 78)
        salida.append("CUADRE DE IMPORTACION CIBERBRAIN (SQL Server -> MySQL)")
        salida.append("=" * 78)
        salida.append(f"Empresa   : {self.empresa}")
        salida.append(f"Origen    : {self.origen}")
        salida.append(f"Modo      : {self.modo}")
        salida.append("")
        salida.append(
            f"{'ENTIDAD':<26} {'LEIDOS':>9} {'INSERT.':>9} {'OMITID.':>9} {'DESCART.':>9}"
        )
        salida.append("-" * 78)
        for fila in self.lineas:
            salida.append(str(fila))
            if fila.motivo:
                salida.append(f"{'':<26} motivo: {fila.motivo}")
            for nombre, valor in fila.importes.items():
                salida.append(f"{'':<26} {nombre}: {_formato_importe(valor)}")
        if self.secciones:
            salida.append("")
            for titulo, lineas in self.secciones:
                salida.append(titulo)
                salida.append("-" * len(titulo))
                salida.extend(lineas)
        if self._descartes:
            salida.append("")
            salida.append("DESCARTES Y CONTEO EXACTO")
            salida.append("-" * 78)
            for titulo, conteos in self._descartes:
                salida.append(titulo)
                for nombre, cantidad in conteos.items():
                    salida.append(f"    {nombre:<52} {cantidad:>10}")
        if self.observaciones:
            salida.append("")
            salida.append("OBSERVACIONES")
            salida.append("-" * 78)
            for texto in self.observaciones:
                salida.append(f"- {texto}")
        salida.append("=" * 78)
        return "\n".join(salida)

    def escribir(self, ruta: str | os.PathLike[str]) -> str:
        """Deja el cuadre en un archivo de texto y devuelve la ruta."""
        ruta = os.fspath(ruta)
        os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
        with open(ruta, "w", encoding="utf-8", newline="\n") as archivo:
            archivo.write(self.render())
            archivo.write("\n")
        return ruta
