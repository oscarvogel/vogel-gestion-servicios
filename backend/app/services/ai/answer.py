"""La respuesta con datos la arma el servidor, no el modelo.

Motivo, medido contra la API el 2026-10-03: cuando el modelo tiene su propia respuesta
anterior en el historial, contesta de memoria y **inventa** fechas, estados y cantidades. En
tres corridas distintas dio tres historiales distintos, y ninguno era el real. Ni
``tool_choice: "required"`` ni un prompt estricto lo cortan: el primero lo ignora la API, y
el segundo reduce la fabricacion pero no la elimina.

Asi que la regla no es "pedile que no invente": es **que no pueda escribir los datos**.

- La **ficha** la arma el servidor con los valores que salieron de la base. Es la fuente, y
  la que el operador mira.
- El **texto** del modelo es un comentario. No puede contener ningun dato: si el modelo se
  pasa y escribe un numero, una fecha o un estado, ese texto se descarta y se reemplaza por
  una frase neutra del servidor.

Eso convierte la regla en algo verificable: al operador no le puede llegar un dato que no
venga de la ficha, porque el texto del modelo no llega con ningun valor adentro.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.work_order import WorkOrderStatus

# Cualquier cifra: cantidades, fechas, numeros de orden, ids, series. Todo eso es dato.
_DIGITO = re.compile(r"\d")

# Los estados tienen palabras ("En espera de repuesto"), asi que no se comparan palabra por
# palabra sino sobre el texto entero normalizado, donde "en espera" queda pegado. Si se
# comparara palabra por palabra, "esta en diagnostico" no encontraria nunca "En diagnóstico".
#
# La normalizacion saca tildes: el modelo escribe "diagnostico" y la empresa tiene
# "diagnóstico", y son el mismo estado. Sin esto, un estado con tilde es imposible de
# encontrar.
def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in sin_tildes if c.isalnum() and not unicodedata.combining(c))


# Un estado mas corto que esto no se busca: "A" o "OK" aparecen dentro de cualquier frase y
# darian falsos positivos que matan texto legitimo.
_ESTADO_MINIMO = 4

# La frase que queda cuando el modelo se pasa. No dice nada que no sea cierto.
TEXTO_NEUTRO = "El asistente comento la respuesta; el detalle esta en la ficha de arriba."


@dataclass
class Ficha:
    """Los datos, armados por el servidor a partir de los resultados de las herramientas."""

    bloques: list[dict[str, Any]] = field(default_factory=list)
    # Nombres de las herramientas que se ejecutaron, en orden.
    consultas: list[dict[str, Any]] = field(default_factory=list)

    @property
    def vacia(self) -> bool:
        return not self.bloques

    def as_dict(self) -> dict[str, Any]:
        return {"bloques": self.bloques, "consultas": self.consultas}


# --------------------------------------------------------------------------------------
# La ficha
# --------------------------------------------------------------------------------------


def construir_ficha(resultados: list[tuple[str, Any]]) -> Ficha:
    """Arma la ficha desde los resultados de las herramientas.

    No consulta nada ni interpreta nada: traduce el ``data`` de cada herramienta a bloques que
    la UI puede mostrar tal cual. Los valores son los que salieron de la base, porque vienen
    de la herramienta sin tocar.
    """
    ficha = Ficha()
    for nombre, data in resultados:
        if not isinstance(data, dict):
            continue
        ficha.consultas.append({"herramienta": nombre, "tiene_datos": bool(data.get("resultados") or data.get("encontrado"))})
        bloque = _bloque(nombre, data)
        if bloque is not None:
            ficha.bloques.append(bloque)
    return ficha


_TITULOS = {
    "buscar_cliente": "Clientes encontrados",
    "buscar_equipo": "Equipos encontrados",
    "consultar_historial_equipo": "Historial del equipo",
}


def _bloque(nombre: str, data: dict) -> dict | None:
    titulo = _TITULOS.get(nombre)
    if titulo is None:
        return None

    if nombre == "consultar_historial_equipo":
        if not data.get("encontrado"):
            # Misma forma que el caso con datos, con las listas vacias: la UI no tiene que
            # preguntar si viene `historial` o no.
            return {
                "tipo": nombre,
                "titulo": titulo,
                "vacio": True,
                "equipo": None,
                "cantidad_de_ordenes": 0,
                "historial": [],
                "detalle": data.get("nota", "No hay resultados para esa consulta."),
            }
        equipo = data.get("equipo") or {}
        historial = data.get("historial") or []
        return {
            "tipo": nombre,
            "titulo": titulo,
            "vacio": not historial,
            "equipo": equipo,
            "cantidad_de_ordenes": data.get("cantidad_de_ordenes", len(historial)),
            "historial": historial,
        }

    resultados = data.get("resultados") or []
    return {"tipo": nombre, "titulo": titulo, "vacio": not resultados, "resultados": resultados}


# --------------------------------------------------------------------------------------
# El saneo del texto
# --------------------------------------------------------------------------------------


def estados_de_la_empresa(db: Session, company_id: int) -> set[str]:
    """Los nombres de estado de la empresa, normalizados.

    Van al saneo para que el modelo no pueda escribir "Listo" o "Entregado" en su texto. Si
    un nombre de estado es una palabra comun ("Nuevo", "Cerrado"), el texto con esa palabra se
    descarta: es preferible perder una frase a mostrarle un estado al operador.
    """
    nombres = db.execute(
        select(WorkOrderStatus.name).where(WorkOrderStatus.company_id == company_id)
    ).scalars().all()
    return {_normalizar(n) for n in nombres if n and len(_normalizar(n)) >= _ESTADO_MINIMO}


def sanear(texto: str, estados: set[str]) -> tuple[str, bool]:
    """Quita del texto del modelo cualquier cosa que parezca un dato.

    Devuelve el texto usable y si hubo que reemplazarlo. La regla es simple y dichosa: el
    texto del modelo no lleva numeros ni estados, porque esos son de la ficha.
    """
    limpio = (texto or "").strip()
    if not limpio:
        return "", False

    if _DIGITO.search(limpio):
        return TEXTO_NEUTRO, True

    aplastado = _normalizar(limpio)
    for estado in estados:
        if estado and estado in aplastado:
            return TEXTO_NEUTRO, True

    return limpio, False
