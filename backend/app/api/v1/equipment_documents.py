"""Documentos del equipo (#43).

Los binarios van al storage; aca solo quedan metadatos. Toda consulta se ancla en el
tenant de la sesion: el company_id nunca viene del frontend.
"""
from __future__ import annotations

import mimetypes
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_company_id, get_db, require_permission
from app.core.config import settings
from app.models.customer import Equipment
from app.models.equipment_document import EquipmentDocument
from app.models.user import User
from app.models.work_order import WorkOrder, WorkOrderEvent
from app.services.storage import StorageError, build_key, build_storage

router = APIRouter()

# Tipos que se pueden previsualizar en el navegador. La lista no restringe lo que se
# puede subir: es solo lo que se sabe mostrar sin descargarlo.
PREVIEWABLE = {
    "image/jpeg", "image/png", "image/webp", "image/gif",
    "application/pdf", "text/plain",
}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _equipment_or_404(db: Session, company_id: int, equipment_id: int) -> Equipment:
    equipment = db.query(Equipment).filter_by(id=equipment_id, company_id=company_id).first()
    if equipment is None:
        # 404 y no 403: no se le confirma a otra empresa que el equipo existe.
        raise HTTPException(404, "Equipo no encontrado.")
    return equipment


def _document_or_404(db: Session, company_id: int, document_id: int, include_deleted: bool = False) -> EquipmentDocument:
    query = db.query(EquipmentDocument).filter_by(id=document_id, company_id=company_id)
    if not include_deleted:
        query = query.filter(EquipmentDocument.deleted_at.is_(None))
    row = query.first()
    if row is None:
        raise HTTPException(404, "Documento no encontrado.")
    return row


def _detect_mime(upload: UploadFile, filename: str) -> str:
    declared = (upload.content_type or "").split(";")[0].strip().lower()
    guessed, _ = mimetypes.guess_type(filename or "")
    # El navegador a veces manda un MIME generico (application/octet-stream) o uno que no
    # cuadra con la extension. Cuando pasa eso se prefiere el que se deduce del nombre.
    if not declared or declared == "application/octet-stream":
        return guessed or declared or "application/octet-stream"
    return declared


def _read_or_404(db: Session, company_id: int, document_id: int) -> EquipmentDocument:
    return _document_or_404(db, company_id, document_id)


class DocumentRead(BaseModel):
    id: int
    equipment_id: int
    work_order_id: int | None
    original_filename: str
    mime_type: str
    size_bytes: int
    size_mb: float
    description: str | None
    uploaded_by_user_id: int
    created_at: datetime
    is_previewable: bool


class DocumentList(BaseModel):
    items: list[DocumentRead]
    total: int


class DocumentUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=500)


def _read(row: EquipmentDocument) -> DocumentRead:
    return DocumentRead(
        id=row.id,
        equipment_id=row.equipment_id,
        work_order_id=row.work_order_id,
        original_filename=row.original_filename,
        mime_type=row.mime_type,
        size_bytes=row.size_bytes,
        size_mb=row.size_mb,
        description=row.description,
        uploaded_by_user_id=row.uploaded_by_user_id,
        created_at=row.created_at,
        is_previewable=row.mime_type in PREVIEWABLE,
    )


@router.get("/equipment/{equipment_id}/documents", response_model=DocumentList)
def list_documents(
    equipment_id: int,
    include_deleted: bool = False,
    work_order_id: int | None = Query(default=None),
    company_id: int = Depends(get_current_company_id),
    _actor: User = Depends(require_permission("equipment.view")),
    db: Session = Depends(get_db),
):
    """Documentos del equipo. Los de una OT tambien aparecen aca: son del equipo."""
    equipment = _equipment_or_404(db, company_id, equipment_id)
    query = db.query(EquipmentDocument).filter(
        EquipmentDocument.company_id == company_id,
        EquipmentDocument.equipment_id == equipment.id,
    )
    if not include_deleted:
        query = query.filter(EquipmentDocument.deleted_at.is_(None))
    if work_order_id is not None:
        query = query.filter(EquipmentDocument.work_order_id == work_order_id)
    rows = query.order_by(EquipmentDocument.created_at.desc(), EquipmentDocument.id.desc()).all()
    return {"items": [_read(r) for r in rows], "total": len(rows)}


@router.post("/equipment/{equipment_id}/documents", response_model=DocumentRead, status_code=201)
def upload_document(
    equipment_id: int,
    file: UploadFile = File(...),
    description: str | None = Form(default=None),
    work_order_id: int | None = Form(default=None),
    company_id: int = Depends(get_current_company_id),
    actor: User = Depends(require_permission("equipment.manage")),
    db: Session = Depends(get_db),
):
    equipment = _equipment_or_404(db, company_id, equipment_id)
    filename = (file.filename or "archivo").strip() or "archivo"
    if len(filename) > 255:
        raise HTTPException(422, "El nombre del archivo es demasiado largo.")

    # La OT, si se pasa, tiene que ser de esta empresa y de este equipo. Sin esto se
    # podrian colgar documentos de una OT ajena dentro del equipo propio.
    if work_order_id is not None:
        order = db.query(WorkOrder).filter_by(id=work_order_id, company_id=company_id).first()
        if order is None or order.equipment_id != equipment.id:
            raise HTTPException(422, "La orden de trabajo no pertenece a este equipo.")

    max_bytes = settings.storage_max_file_mb * 1048576
    data = file.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(413, f"El archivo supera el maximo de {settings.storage_max_file_mb} MB.")
    if not data:
        raise HTTPException(422, "El archivo esta vacio.")

    key = build_key(company_id, equipment.id, filename)
    storage = build_storage()
    try:
        import io

        stored = storage.put(key, io.BytesIO(data), _detect_mime(file, filename))
    except StorageError as exc:
        raise HTTPException(503, str(exc))

    row = EquipmentDocument(
        company_id=company_id,
        equipment_id=equipment.id,
        work_order_id=work_order_id,
        original_filename=filename,
        mime_type=stored.content_type,
        size_bytes=stored.size_bytes,
        storage_key=stored.key,
        description=(description or "").strip()[:500] or None,
        uploaded_by_user_id=actor.id,
    )
    db.add(row)
    try:
        db.commit()
    except Exception:
        # Si la fila no entra, el archivo tampoco queda huerfano.
        try:
            storage.delete(stored.key)
        except StorageError:
            pass
        db.rollback()
        raise
    db.refresh(row)
    return _read(row)


@router.get("/documents/{document_id}/download")
def download_document(
    document_id: int,
    company_id: int = Depends(get_current_company_id),
    _actor: User = Depends(require_permission("equipment.view")),
    db: Session = Depends(get_db),
):
    """Sirve el archivo pasando por sesion, permiso y tenant.

    No se expone la ruta del storage: eso publicaria objetos privados.
    """
    row = _read_or_404(db, company_id, document_id)
    storage = build_storage()
    try:
        handle = storage.open(row.storage_key)
    except StorageError as exc:
        raise HTTPException(503, str(exc))

    def _iter():
        try:
            while True:
                chunk = handle.read(65536)
                if not chunk:
                    break
                yield chunk
        finally:
            handle.close()

    # Content-Disposition con attachment y nombre saneado para que el nombre del cliente
    # no se interpole en la cabecera.
    safe = row.original_filename.replace('"', "").replace("\r", " ").replace("\n", " ")
    return StreamingResponse(
        _iter(),
        media_type=row.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{safe}"'},
    )


@router.patch("/documents/{document_id}", response_model=DocumentRead)
def update_document(
    document_id: int,
    payload: DocumentUpdate,
    company_id: int = Depends(get_current_company_id),
    _actor: User = Depends(require_permission("equipment.manage")),
    db: Session = Depends(get_db),
):
    row = _read_or_404(db, company_id, document_id)
    row.description = (payload.description or "").strip()[:500] or None
    db.commit()
    db.refresh(row)
    return _read(row)


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(
    document_id: int,
    company_id: int = Depends(get_current_company_id),
    actor: User = Depends(require_permission("equipment.manage")),
    db: Session = Depends(get_db),
):
    """Baja logica: la fila queda con fecha y autor, el archivo sigue en el storage."""
    row = _read_or_404(db, company_id, document_id)
    row.deleted_at = _now()
    row.deleted_by_user_id = actor.id
    if row.work_order_id is not None:
        db.add(
            WorkOrderEvent(
                company_id=company_id,
                work_order_id=row.work_order_id,
                event_type="DOCUMENT_DELETED",
                status=None,
                detail=f"Se dio de baja el documento \"{row.original_filename}\" del historial del equipo.",
                user_id=actor.id,
            )
        )
    db.commit()
    return None
