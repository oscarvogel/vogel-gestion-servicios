from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WorkArea(Base):
    """La marca / area de trabajo, con las DOS capas que tiene el legacy.

    En CiberBrain la garantia no es un campo: son tres tablas encajadas.

      - ``dbo.Areas``              una fila por area (la marca). ``CodCli`` dice a quien se
                                  le liquida. ``Empresa`` es un texto viejo y desactualizado.
      - ``dbo.TiposTrabajos``      sub-tipos dentro del area: ``FUERA``, ``AGU``, ``AAC``,
                                  ``ASC``, ``AGS``, ``TGU``, ``TAC``, ``TSC``, ``TGS``.
      - ``dbo.Aux_PoliticasxArea`` la politica real: (Area, TipoTrabajo). ``CS_Trabajos.IDPolitica``
                                  apunta aca, **no** a ``Areas``.

    ``dbo.CS_PoliticasxArea`` es una vista que une las dos capas y ya resuelve
    ``Garantia`` y ``Liquidar``. Por eso aca se guardan las dos: ``area_name`` +
    ``policy_code``, y la garantia resuelta en ``warranty_type``.

    ``policy_code`` vacio significa "politica principal" de esa area (la que no tiene
    sub-tipo). Se usa cadena vacia y no NULL para que el indice unico sirva: en MySQL los
    NULL de un indice unico son todos distintos entre si.

    ``warranty_type`` (viene de ``Garantia``):
      0 = fuera de garantia, 1 = garantia de terceros (de fabrica), 2 = garantia propia/de service.

    ``liquidate_mode`` (viene de ``Liquidar``) NO es "a quien se liquida": es el ciclo de vida
    de la OT. 0 y 3 = liquidacion manual, 1 = automatica, 2 = no se liquida nunca.
    """

    __tablename__ = "work_areas"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "area_code", "policy_code", name="uq_work_areas_company_area_policy"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    # dbo.Areas.Codigo (int en el legacy) y dbo.Areas.Area
    area_code: Mapped[str] = mapped_column(String(20), nullable=False)
    area_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    # dbo.TiposTrabajos.Codigo; "" = politica principal
    policy_code: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    policy_description: Mapped[str | None] = mapped_column(String(150), nullable=True)
    is_principal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # dbo.Areas.CodCli -> customers.id. NULL = el area no se le liquida a nadie.
    billing_customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id"), nullable=True, index=True
    )
    # dbo.Areas.Empresa: texto del legacy, desactualizado. Se guarda solo como referencia.
    brand_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    warranty_type: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    liquidate_mode: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warranty_period_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    utility: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Comisiones por tipo de parte (dbo.Areas.Comision* / MontoComision*)
    commission_service_mode: Mapped[int | None] = mapped_column(Integer, nullable=True)
    commission_service_pct: Mapped[float | None] = mapped_column(Numeric(9, 2), nullable=True)
    commission_product_mode: Mapped[int | None] = mapped_column(Integer, nullable=True)
    commission_product_pct: Mapped[float | None] = mapped_column(Numeric(9, 2), nullable=True)
    commission_part_mode: Mapped[int | None] = mapped_column(Integer, nullable=True)
    commission_part_pct: Mapped[float | None] = mapped_column(Numeric(9, 2), nullable=True)
    commission_other_mode: Mapped[int | None] = mapped_column(Integer, nullable=True)
    commission_other_pct: Mapped[float | None] = mapped_column(Numeric(9, 2), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WorkBench(Base):
    """Mesa de trabajo.

    En el legacy la mesa es texto libre (``CS_Trabajos.Ubicacion``) y la misma mesa esta
    escrita de tres maneras distintas: ``TALLER``, ``TALLER-BOX1``, ``TALLER - BOX B``. Las
    cuatro tablas candidatas a maestro (``UBIC_Ubicaciones``, ``CS_Ubicaciones``,
    ``CK_Ubicaciones``, ``CK_ArticulosxUbicacion``) estan vacias.

    Se normaliza: ``normalized_code`` es la clave de agrupacion y ``legacy_aliases`` deja
    registro de los textos de origen que caeron en esa mesa.
    """

    __tablename__ = "work_benches"
    __table_args__ = (
        UniqueConstraint("company_id", "normalized_code", name="uq_work_benches_company_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    normalized_code: Mapped[str] = mapped_column(String(80), nullable=False)
    legacy_aliases: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class Seller(Base):
    """Vendedor. En el legacy es un ``CC_Usuarios`` con la tarea 2 ("Vendedor") asignada."""

    __tablename__ = "sellers"
    __table_args__ = (
        UniqueConstraint("company_id", "legacy_code", name="uq_sellers_company_legacy_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    legacy_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class Technician(Base):
    """Tecnico. En el legacy es un ``CC_Usuarios`` con la tarea 3 ("Tecnico") asignada.

    Ojo: 40 de las 77 personas que intervinieron en una OT ya no existen como usuarios, y el
    legacy los muestra como "Sistema". Esos se importan igual, con ``legacy_code`` NULL.
    """

    __tablename__ = "technicians"
    __table_args__ = (
        UniqueConstraint("company_id", "legacy_code", name="uq_technicians_company_legacy_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    legacy_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
