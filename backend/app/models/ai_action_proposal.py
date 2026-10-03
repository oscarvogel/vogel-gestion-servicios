from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

PENDIENTE = "pendiente"
# Estado intermedio del reclamo. Existe para que, si el proceso se muere a mitad de camino, la
# propuesta quede en un estado que un humano tiene que mirar y no en uno que se pueda reintentar
# solo: una fila trabada es mejor que una escritura duplicada.
APLICANDO = "aplicando"
APLICADA = "aplicada"
RECHAZADA = "rechazada"
FALLIDA = "fallida"

RIESGO_NINGUNO = "ninguno"
RIESGO_FINANCIERO = "financiero"
RIESGO_COMUNICACION = "comunicacion"


class AiActionProposal(Base):
    """Una accion de escritura que la IA propuso y que todavia no se aplico.

    Es a la vez el registro de auditoria y el candado: una propuesta se aplica una sola vez.
    El `status` pasa de `pendiente` a `aplicada` con un update condicional, asi que un doble
    clic o un reintento del navegador no escribe dos veces.

    Lo que se guarda, porque sin esto una accion hecha "por IA" no se puede auditar: lo que
    propuso el modelo (`proposed_arguments`), lo que la persona confirmo o corrigio
    (`confirmed_arguments`, que es lo que se escribe), quien hizo cada cosa, y que objeto
    quedo persistido.
    """

    __tablename__ = "ai_action_proposals"
    __table_args__ = (
        # El listado de la pantalla es "las pendientes de esta empresa".
        Index("ix_ai_action_proposals_company_status", "company_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    # Que herramienta de escritura se quiere ejecutar: crear_cliente, agregar_repuesto, ...
    tool: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=PENDIENTE)
    # Quien estaba chateando cuando el modelo propuso: la propuesta se hace en su nombre.
    proposed_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    proposed_arguments: Mapped[str] = mapped_column(Text, nullable=False)
    # Lo que confirmo la persona. NULL mientras nadie confirmo.
    confirmed_arguments: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Que se persistio: {"tipo": "cliente", "id": 123}
    result_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Riesgo de la accion segun la herramienta y sus argumentos. Se calcula al proponer, no al
    # aplicar, para que la persona lo vea ANTES de confirmar.
    risk: Mapped[str] = mapped_column(String(20), nullable=False, default=RIESGO_NINGUNO)
    # Si al aplicar se le avisa al cliente. Un WhatsApp enviado no se puede deshacer, asi que
    # se avisa antes de aplicar.
    requires_notification: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
