from datetime import datetime
from pathlib import PurePath
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_company_id, get_db, require_permission
from app.models.user import User
from app.services.work_order_import_service import confirm_work_order_import, preview_work_order_import

router = APIRouter()
MAX_REQUEST_BYTES = 15 * 1024 * 1024


class RowDecision(BaseModel):
    key: str = Field(min_length=3, max_length=100)
    include: bool = False
    status_id: int | None = None
    customer_name: str | None = Field(default=None, max_length=180)
    phone: str | None = Field(default=None, max_length=60)
    received_at: datetime | None = None
    category: str | None = Field(default=None, max_length=80)


class ImportDecisions(BaseModel):
    rows: list[RowDecision] = Field(default_factory=list, max_length=15000)


def _read_xlsx(file: UploadFile) -> tuple[bytes, str]:
    filename = PurePath((file.filename or "registro.xlsx").replace("\\", "/")).name
    if not filename.casefold().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="Seleccioná un archivo .xlsx.")
    content = file.file.read(MAX_REQUEST_BYTES + 1)
    if len(content) > MAX_REQUEST_BYTES:
        raise HTTPException(status_code=413, detail="El archivo supera el límite de 15 MB.")
    return content, filename


@router.post("/preview")
def preview_import(
    file: UploadFile = File(...),
    company_id: int = Depends(get_current_company_id),
    _actor: User = Depends(require_permission("work_orders.manage")),
    db: Session = Depends(get_db),
):
    content, filename = _read_xlsx(file)
    return preview_work_order_import(db, company_id, content, filename)


@router.post("/confirm")
def confirm_import(
    file: UploadFile = File(...),
    preview_token: str = Form(...),
    decisions: str = Form("{}"),
    company_id: int = Depends(get_current_company_id),
    actor: User = Depends(require_permission("work_orders.manage")),
    db: Session = Depends(get_db),
):
    content, filename = _read_xlsx(file)
    try:
        parsed = ImportDecisions.model_validate_json(decisions)
    except ValidationError:
        raise HTTPException(status_code=422, detail="La selección de filas o estados no es válida.") from None
    selection: list[dict[str, Any]] = [row.model_dump() for row in parsed.rows]
    return confirm_work_order_import(db, company_id, actor, content, filename, preview_token, selection)
