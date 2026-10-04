from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_company_id,
    get_current_user,
    get_db,
    require_superadmin,
)
from app.api.v1.schemas import (
    CompanyCreate,
    CompanyDetail,
    CompanyListResponse,
    CompanyRead,
    CompanyUpdate,
    TokenBundle,
)
from app.core.security import create_access_token, hash_password
from app.models.company import Company, CompanyParameter, ParameterDefinition
from app.models.role import Permission, Role
from app.models.user import CompanyUser, User

router = APIRouter()


def _serialize(company: Company, user_count: int = 0) -> CompanyRead:
    return CompanyRead(
        id=company.id,
        name=company.name,
        legal_name=company.legal_name,
        tax_id=company.tax_id,
        slug=company.slug,
        email=company.email,
        phone=company.phone,
        address=company.address,
        notes=company.notes,
        timezone=company.timezone,
        locale=company.locale,
        whatsapp_instance_id=company.whatsapp_instance_id,
        notification_sender_name=company.notification_sender_name,
        notification_sender_email=company.notification_sender_email,
        active=company.active,
        created_at=company.created_at,
        updated_at=company.updated_at,
        user_count=user_count,
    )


# IMPORTANTE: las rutas estáticas (current, enter) deben declararse ANTES
# de las rutas con path parameter /{company_id} para no ser capturadas por
# la conversión a int (que devolvería 422).


@router.get("/current", response_model=CompanyRead)
def current_company(
    company_id: int = Depends(get_current_company_id), db: Session = Depends(get_db)
):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    return _serialize(company, user_count=_count_users(db, company.id))


@router.post("/{company_id}/enter", response_model=TokenBundle)
def enter_company(
    company_id: int,
    user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    if not company.active:
        raise HTTPException(status_code=403, detail="La empresa está inactiva.")
    return TokenBundle(
        access_token=create_access_token(
            user.id, company.id, superadmin=user.is_superadmin
        )
    )


@router.get("", response_model=CompanyListResponse)
def list_companies(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: Optional[str] = None,
    active: Optional[bool] = None,
):
    base = db.query(Company)
    if user.is_superadmin:
        query = base
    else:
        query = base.join(CompanyUser, CompanyUser.company_id == Company.id).filter(
            CompanyUser.user_id == user.id, CompanyUser.active.is_(True)
        )
    if active is not None:
        query = query.filter(Company.active.is_(active))
    if search:
        like = f"%{search.strip()}%"
        query = query.filter(
            (Company.name.ilike(like))
            | (Company.legal_name.ilike(like))
            | (Company.tax_id.ilike(like))
            | (Company.slug.ilike(like))
        )
    total = query.with_entities(func.count(Company.id)).scalar() or 0
    rows = (
        query.order_by(Company.active.desc(), Company.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    user_counts = dict(
        db.query(CompanyUser.company_id, func.count(CompanyUser.id))
        .filter(CompanyUser.active.is_(True))
        .group_by(CompanyUser.company_id)
        .all()
    )
    items = [_serialize(c, user_counts.get(c.id, 0)) for c in rows]
    return CompanyListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.post("", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
def create_company(
    payload: CompanyCreate,
    _admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """Crea una empresa. Sólo SuperAdmin (companies.create)."""
    if db.query(Company).filter(Company.name == payload.name).first():
        raise HTTPException(status_code=409, detail="Ya existe una empresa con ese nombre.")
    slug = payload.slug or _slugify(payload.name)
    if db.query(Company).filter(Company.slug == slug).first():
        raise HTTPException(status_code=409, detail="Ya existe una empresa con ese identificador.")
    company = Company(
        name=payload.name,
        legal_name=payload.legal_name,
        tax_id=payload.tax_id,
        slug=slug,
        email=payload.email,
        phone=payload.phone,
        address=payload.address,
        notes=payload.notes,
        timezone=payload.timezone or "America/Argentina/Cordoba",
        locale=payload.locale or "es-AR",
        whatsapp_instance_id=payload.whatsapp_instance_id,
        notification_sender_name=payload.notification_sender_name,
        notification_sender_email=payload.notification_sender_email,
        active=payload.active,
    )
    db.add(company)
    db.flush()
    from app.models.work_order import WorkOrderStatus
    for name,color,order,initial,final,completed,delivered in [
        ("Recibido","#10B981",10,True,False,False,False),("En diagnóstico","#3B82F6",20,False,False,False,False),
        ("Presupuestado","#8B5CF6",30,False,False,False,False),("Esperando aprobación","#F59E0B",40,False,False,False,False),
        ("En reparación","#06B6D4",50,False,False,False,False),("Esperando repuesto","#F97316",60,False,False,False,False),
        ("Listo","#22C55E",70,False,False,True,False),("Entregado","#64748B",80,False,True,False,True)]:
        db.add(WorkOrderStatus(company_id=company.id,name=name,color=color,sort_order=order,active=True,is_initial=initial,is_final=final,marks_completed=completed,marks_delivered=delivered))

    if payload.admin_email:
        admin_user = db.query(User).filter(User.email == str(payload.admin_email)).first()
        if admin_user is None:
            if not payload.admin_password or not payload.admin_full_name:
                raise HTTPException(
                    status_code=400,
                    detail="Debe indicar nombre completo y contraseña para crear el administrador inicial.",
                )
            admin_user = User(
                email=str(payload.admin_email),
                full_name=payload.admin_full_name,
                password_hash=hash_password(payload.admin_password),
                active=True,
            )
            db.add(admin_user)
            db.flush()
        admin_role = (
            db.query(Role)
            .filter_by(company_id=company.id, name="Administrador")
            .first()
        )
        if admin_role is None:
            admin_role = Role(
                company_id=company.id,
                name="Administrador",
                description="Acceso completo sobre la empresa",
                is_system=True,
                active=True,
            )
            db.add(admin_role)
            db.flush()
            _grant_all_company_permissions(db, admin_role)
        membership = CompanyUser(
            company_id=company.id,
            user_id=admin_user.id,
            role="ADMIN",
            is_admin=True,
            active=True,
        )
        db.add(membership)
        db.flush()
        from app.models.role import CompanyUserRole

        db.add(
            CompanyUserRole(
                company_user_id=membership.id, role_id=admin_role.id, active=True
            )
        )
    db.commit()
    db.refresh(company)
    return _serialize(company, user_count=_count_users(db, company.id))


@router.get("/{company_id}", response_model=CompanyDetail)
def get_company(
    company_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    if not user.is_superadmin:
        membership = (
            db.query(CompanyUser)
            .filter_by(user_id=user.id, company_id=company.id, active=True)
            .first()
        )
        if not membership:
            raise HTTPException(status_code=403, detail="No tiene acceso a esta empresa.")
    users_total = _count_users(db, company.id)
    admin_total = (
        db.query(func.count(CompanyUser.id))
        .filter_by(company_id=company.id, active=True, is_admin=True)
        .scalar()
        or 0
    )
    return CompanyDetail(
        id=company.id,
        name=company.name,
        legal_name=company.legal_name,
        tax_id=company.tax_id,
        slug=company.slug,
        email=company.email,
        phone=company.phone,
        address=company.address,
        notes=company.notes,
        timezone=company.timezone,
        locale=company.locale,
        whatsapp_instance_id=company.whatsapp_instance_id,
        notification_sender_name=company.notification_sender_name,
        notification_sender_email=company.notification_sender_email,
        active=company.active,
        created_at=company.created_at,
        updated_at=company.updated_at,
        user_count=users_total,
        admin_count=int(admin_total),
        member_count=users_total - int(admin_total),
        is_active=company.active,
    )


@router.patch("/{company_id}", response_model=CompanyRead)
def update_company(
    company_id: int,
    payload: CompanyUpdate,
    _admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] != company.name:
        if db.query(Company).filter(Company.name == data["name"]).first():
            raise HTTPException(status_code=409, detail="Ya existe una empresa con ese nombre.")
    if "slug" in data and data["slug"] and data["slug"] != company.slug:
        if db.query(Company).filter(Company.slug == data["slug"]).first():
            raise HTTPException(status_code=409, detail="Ya existe una empresa con ese identificador.")
    for key, value in data.items():
        setattr(company, key, value)
    db.commit()
    db.refresh(company)
    return _serialize(company, user_count=_count_users(db, company.id))


@router.post("/{company_id}/enable", response_model=CompanyRead)
def enable_company(
    company_id: int,
    _admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    company.active = True
    db.commit()
    db.refresh(company)
    return _serialize(company, user_count=_count_users(db, company.id))


@router.post("/{company_id}/disable", response_model=CompanyRead)
def disable_company(
    company_id: int,
    _admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    company.active = False
    db.commit()
    db.refresh(company)
    return _serialize(company, user_count=_count_users(db, company.id))


# ---------- El adicional de IA, desde la plataforma ----------
#
# La IA se vende por empresa, asi que su interruptor y su techo de uso NO son configuracion
# del cliente: los parametros estan en `parameter_definitions.editable = false` y
# `PATCH /company-parameters` los rechaza con 403. Esta es la unica via para cambiarlo, y es
# superadmin.
#
# Que sea un endpoint explicito y no "un superadmin puede saltarse el editable" importa por
# dos razones: queda escrito que estos tres parametros son comerciales, y el que lo escribe
# dice que es a proposito. Saltarse la regla en general habria que dejar la puerta abierta
# para todos los demas.


def _numero(valor: float | int) -> str:
    """Como se guarda un numero en un parametro que llega como texto.

    El servicio lee con `float()`, asi que 0 y 0.0 son el mismo valor, pero `str(0.0)` es
    "0.0" y no "0". Guardar "0.0" contra un default "0" dejaba un override que decia
    exactamente lo mismo que el default, y la pantalla lo mostraba como "personalizado":
    el superadmin no podia distinguir "le deje sin cuota a proposito" de "nunca le dije nada".
    """
    numero = float(valor)
    return str(int(numero)) if numero.is_integer() else str(numero)


class AiEntitlementUpdate(BaseModel):
    enabled: bool
    # 0 = sin cuota y sin limite. Es el valor por defecto del catalogo.
    monthly_quota_usd: float = 0
    monthly_request_limit: int = 0


class AiEntitlementRead(BaseModel):
    company_id: int
    company_name: str
    enabled: bool
    monthly_quota_usd: float
    monthly_request_limit: int
    # Lo consumido del mes en curso. Va en la misma respuesta porque la pregunta de la
    # plataforma es siempre la misma: cuanto lleva gastado esta empresa y cuando se frena.
    usage_requests: int
    usage_cost_usd: float
    usage_input_tokens: int
    usage_output_tokens: int
    # El mes anterior, para ver la tendencia y no solo el mes en curso.
    last_period_cost_usd: float
    over_quota: bool
    # Que el limite de la cuota ya se toco, para que la pantalla lo diga en vez de dejar
    # que el usuario lo descubra cuando la IA le deje de responder.
    quota_exhausted: bool


@router.get("/{company_id}/ai", response_model=AiEntitlementRead)
def get_ai_entitlement(
    company_id: int,
    _admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """Como esta la IA en esa empresa y cuanto consumio del mes. No escribe nada."""
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    from app.services.ai import entitlement
    from app.services.ai.usage import last_period_cost, month_totals

    totals = month_totals(db, company_id)
    quota = entitlement.monthly_quota_usd(db, company_id)
    limite = entitlement.monthly_request_limit(db, company_id)
    return AiEntitlementRead(
        company_id=company.id,
        company_name=company.name,
        enabled=entitlement.is_enabled(db, company_id),
        monthly_quota_usd=quota,
        monthly_request_limit=limite,
        usage_requests=totals["requests"],
        usage_cost_usd=totals["cost_usd"],
        usage_input_tokens=totals["input_tokens"],
        usage_output_tokens=totals["output_tokens"],
        last_period_cost_usd=last_period_cost(db, company_id),
        over_quota=bool(
            (quota and totals["cost_usd"] >= quota)
            or (limite and totals["requests"] >= limite)
        ),
        quota_exhausted=bool(
            quota and totals["cost_usd"] >= quota
        ),
    )


@router.put("/{company_id}/ai", response_model=AiEntitlementRead)
def set_ai_entitlement(
    company_id: int,
    payload: AiEntitlementUpdate,
    _admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """Habilita o deshabilita la IA de esa empresa y le fija su techo de uso.

    No le amigues `PATCH /company-parameters` a proposito. Ahi el `editable` protege, y esta
    es la excepcion: aca lo que se esta haciendo es una decision comercial, entonces queda
    en un endpoint con un nombre que lo dice y no en una puerta trasera.

    Un valor igual al default borra el override en vez de guardarlo, como hace la pantalla:
    asi "sin cuota" es de verdad el default del catalogo y no una fila que dice 0.
    """
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    if payload.monthly_quota_usd < 0:
        raise HTTPException(status_code=422, detail="La cuota no puede ser negativa.")
    if payload.monthly_request_limit < 0:
        raise HTTPException(status_code=422, detail="El límite de pedidos no puede ser negativo.")

    from app.core.parameter_catalog import AI_PARAMETERS

    valores = {
        "ai.enabled": "true" if payload.enabled else "false",
        "ai.monthly_quota_usd": _numero(payload.monthly_quota_usd),
        "ai.monthly_request_limit": _numero(payload.monthly_request_limit),
    }
    defaults = {p[0]: p[1] for p in AI_PARAMETERS}
    for nombre, valor in valores.items():
        definicion = db.query(ParameterDefinition).filter_by(parameter=nombre).first()
        if definicion is None:
            raise HTTPException(
                status_code=409,
                detail=f"Falta la definición del parámetro {nombre}. Corré las migraciones.",
            )
        fila = (
            db.query(CompanyParameter)
            .filter_by(company_id=company_id, parameter_definition_id=definicion.id)
            .first()
        )
        if valor == defaults[nombre]:
            # Volvio al default: el override sobra. Ademas molestaria en la pantalla, que
            # loeria "personalizado" para un valor que en realidad es el general.
            if fila is not None:
                db.delete(fila)
            continue
        if fila is None:
            db.add(
                CompanyParameter(
                    company_id=company_id, parameter_definition_id=definicion.id, value=valor
                )
            )
        else:
            fila.value = valor
    db.commit()
    return get_ai_entitlement(company_id, _admin, db)


# ---------- Helpers ----------
def _slugify(value: str) -> str:
    out = []
    for char in value.lower():
        if char.isalnum():
            out.append(char)
        elif char in (" ", "-", "_"):
            out.append("-")
    slug = "".join(out).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:80] or "empresa"


def _count_users(db: Session, company_id: int) -> int:
    return (
        db.query(func.count(CompanyUser.id))
        .filter_by(company_id=company_id, active=True)
        .scalar()
        or 0
    )


def _grant_all_company_permissions(db: Session, role: Role) -> None:
    from app.core.permissions import PERMISSIONS

    codes = [p.code for p in PERMISSIONS]
    permissions = db.query(Permission).filter(Permission.code.in_(codes)).all()
    for permission in permissions:
        from app.models.role import role_permissions

        db.execute(
            role_permissions.insert().values(role_id=role.id, permission_id=permission.id)
        )
