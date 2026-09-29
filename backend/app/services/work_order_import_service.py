from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.company import Company
from app.models.customer import Customer, Equipment, EquipmentCategory
from app.models.user import User
from app.models.work_order import WorkOrder, WorkOrderCounter, WorkOrderEvent, WorkOrderStatus
from app.models.work_order_import import WorkOrderImportBatch, WorkOrderImportRow
from app.services.work_order_import_parser import ParsedSourceRow, WorkbookImportError, normalized_row_hash, parse_work_order_xlsx

logger = logging.getLogger(__name__)


def _norm(value: Any) -> str:
    text_value = unicodedata.normalize("NFKD", str(value or ""))
    text_value = "".join(ch for ch in text_value if not unicodedata.combining(ch)).casefold()
    return re.sub(r"[^a-z0-9]+", " ", text_value).strip()


def _row_key(row: ParsedSourceRow) -> str:
    return f"{row.sheet}:{row.row_number}"


def _duplicate_key(row: ParsedSourceRow) -> tuple | None:
    fields = row.fields
    received = fields.get("received_at")
    values = (_norm(fields.get("customer_name")), received, _norm(fields.get("category")), _norm(fields.get("brand")), _norm(fields.get("model")), _norm(fields.get("motive")))
    if not values[0] or not received or not values[2] or not (values[4] or values[5]):
        return None
    return (values[0], received.date().isoformat(), values[2], values[3], values[4], values[5])


def _status_by_name(statuses: list[WorkOrderStatus], fragment: str) -> WorkOrderStatus | None:
    return next((item for item in statuses if fragment in _norm(item.name)), None)


def _suggest_status(fields: dict[str, Any], statuses_by_name: dict[str, WorkOrderStatus], statuses: list[WorkOrderStatus], initial: WorkOrderStatus | None) -> tuple[WorkOrderStatus | None, bool]:
    color = _norm(fields.get("color_meaning"))
    target: WorkOrderStatus | None = None
    ambiguous_color = "en venta o vendido" in color
    if color and not ambiguous_color:
        if any(value in color for value in ("entregado", "retiran sin", "vendido")):
            target = next((item for item in statuses if item.marks_delivered), None) or _status_by_name(statuses, "entregado")
        elif any(value in color for value in ("falta entregar", "para la venta", "en venta")):
            target = _status_by_name(statuses, "listo")
            target = target or next((item for item in statuses if item.marks_completed and not item.marks_delivered), None)
        elif "presupuesto" in color:
            target = _status_by_name(statuses, "presupuest")
        elif any(value in color for value in ("repuesto", "en espera", "espera")):
            target = _status_by_name(statuses, "repuesto")
        elif any(value in color for value in ("sin arreglo", "no justifica reparacion", "descartado")):
            target = _status_by_name(statuses, "no reparado")

    matched = target is not None
    if target is None and not ambiguous_color and fields.get("legacy_status"):
        target = statuses_by_name.get(_norm(fields["legacy_status"]))
        matched = target is not None
    elif ambiguous_color:
        matched = False
    if target is None:
        target = initial
    return target, matched


def _preview_signature(company_id: int, file_sha: str, issued: int) -> str:
    message = f"{company_id}:{file_sha}:{issued}".encode("utf-8")
    signature = hmac.new(settings.jwt_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return f"{company_id}:{file_sha}:{issued}:{signature}"


def verify_preview_token(token: str, company_id: int, file_sha: str) -> bool:
    try:
        token_company, token_sha, issued_text, signature = token.split(":", 3)
        token_company_int = int(token_company)
        issued = int(issued_text)
    except (AttributeError, ValueError):
        return False
    now = int(datetime.utcnow().timestamp())
    if token_company_int != company_id or token_sha != file_sha or issued > now or now - issued > 3600:
        return False
    expected = _preview_signature(company_id, file_sha, issued).rsplit(":", 1)[1]
    return hmac.compare_digest(signature, expected)


def preview_work_order_import(db: Session, company_id: int, content: bytes, filename: str) -> dict[str, Any]:
    try:
        workbook = parse_work_order_xlsx(content, filename)
    except WorkbookImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if not workbook.rows:
        raise HTTPException(status_code=422, detail="No se encontraron filas en las hojas detalladas permitidas.")
    company = db.query(Company).filter_by(id=company_id, active=True).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa activa no encontrada.")

    statuses = db.query(WorkOrderStatus).filter_by(company_id=company_id, active=True).order_by(WorkOrderStatus.sort_order, WorkOrderStatus.id).all()
    initial = next((item for item in statuses if item.is_initial), statuses[0] if statuses else None)
    statuses_by_name = {_norm(item.name): item for item in statuses}
    batch = db.query(WorkOrderImportBatch).filter_by(company_id=company_id, file_sha256=workbook.sha256).first()
    imported_locations: set[tuple[str, int]] = set()
    if batch:
        imported_locations = set(db.query(WorkOrderImportRow.source_sheet, WorkOrderImportRow.source_row)
            .filter_by(company_id=company_id, batch_id=batch.id).all())

    duplicate_counts: dict[tuple, int] = defaultdict(int)
    for row in workbook.rows:
        key = _duplicate_key(row)
        if key:
            duplicate_counts[key] += 1

    counts = {"ready": 0, "warning": 0, "duplicate": 0, "blocked": 0, "already_imported": 0}
    previews: list[dict[str, Any]] = []
    sheet_counts = {name: {key: 0 for key in counts} for name in workbook.sheet_counts}
    for row in workbook.rows:
        fields = row.fields
        problems: list[str] = []
        warnings: list[str] = []
        if not fields.get("customer_name"):
            problems.append("Falta el cliente.")
        if not fields.get("received_at"):
            problems.append("Falta una fecha de recepción válida.")
        if not fields.get("category"):
            problems.append("Falta el tipo o categoría del equipo.")
        if not fields.get("motive"):
            warnings.append("La planilla no informa el motivo del trabajo.")
        if not fields.get("legacy_status"):
            warnings.append("La planilla no informa un estado original.")
        target, matched_status = _suggest_status(fields, statuses_by_name, statuses, initial)
        if not matched_status and (fields.get("legacy_status") or fields.get("color_meaning")):
            warnings.append("El estado o significado del color no coincide con uno configurado; revisá la equivalencia propuesta.")
        already = (row.sheet, row.row_number) in imported_locations
        duplicate = bool(_duplicate_key(row) and duplicate_counts[_duplicate_key(row)] > 1)
        if already:
            state = "already_imported"
        elif problems:
            state = "blocked"
        elif duplicate:
            state = "duplicate"
            warnings.append("Hay una fila con cliente, fecha y equipo/motivo coincidentes en otra fila.")
        elif warnings:
            state = "warning"
        else:
            state = "ready"
        counts[state] += 1
        sheet_counts[row.sheet][state] += 1
        previews.append({
            "key": _row_key(row), "sheet": row.sheet, "source_row": row.row_number,
            "ficha": fields.get("ficha"), "customer": fields.get("customer_name"), "phone": fields.get("phone"),
            "received_at": fields["received_at"].isoformat() if fields.get("received_at") else None,
            "category": fields.get("category"), "brand": fields.get("brand"), "model": fields.get("model"),
            "motive": fields.get("motive"), "legacy_status": fields.get("legacy_status"),
            "color_meaning": fields.get("color_meaning"),
            "suggested_status_id": target.id if target else None,
            "suggested_status_name": target.name if target else "RECEIVED",
            "state": state, "problems": problems, "warnings": warnings,
            "row_sha256": normalized_row_hash(row),
        })
    issued = int(datetime.utcnow().timestamp())
    return {
        "company_id": company_id, "company_name": company.name, "filename": filename[:255],
        "file_sha256": workbook.sha256, "preview_token": _preview_signature(company_id, workbook.sha256, issued),
        "sheets": [{"name": name, "rows": workbook.sheet_counts.get(name, 0), **sheet_counts.get(name, {})} for name in ("Maquinas 2024", "2025", "Desarmados", "Hoja1")],
        "counts": counts,
        "statuses": [{"id": s.id, "name": s.name, "is_initial": s.is_initial, "is_final": s.is_final, "marks_delivered": s.marks_delivered} for s in statuses],
        "rows": previews,
    }


def _next_number(db: Session, company_id: int) -> int:
    if db.get_bind().dialect.name == "mysql":
        db.execute(text("INSERT INTO work_order_counters (company_id,last_number) VALUES (:cid,LAST_INSERT_ID(1)) ON DUPLICATE KEY UPDATE last_number=LAST_INSERT_ID(last_number+1)"), {"cid": company_id})
        return int(db.execute(text("SELECT LAST_INSERT_ID()")).scalar_one())
    counter = db.get(WorkOrderCounter, company_id)
    if counter is None:
        db.add(WorkOrderCounter(company_id=company_id, last_number=1))
        db.flush()
        return 1
    counter.last_number += 1
    db.flush()
    return counter.last_number


def _get_or_create_customer(db: Session, company_id: int, name: str, phone: str | None, cache: dict[tuple[str, str], Customer], candidates: list[Customer]) -> Customer:
    key = (_norm(name), _norm(phone))
    if key in cache:
        return cache[key]
    matches = [customer for customer in candidates if _norm(customer.name) == _norm(name)]
    customer = next((item for item in matches if phone and _norm(item.phone or item.whatsapp) == _norm(phone)), None)
    customer = customer or next((item for item in matches if not (item.phone or item.whatsapp)), None)
    if customer is None and not phone and len(matches) == 1:
        customer = matches[0]
    if customer is None:
        customer = Customer(company_id=company_id, customer_type="PERSON", name=name[:180], phone=phone[:60] if phone else None)
        db.add(customer)
        db.flush()
        candidates.append(customer)
    cache[key] = customer
    return customer


def _get_or_create_category(db: Session, company_id: int, name: str, cache: dict[str, EquipmentCategory], candidates: list[EquipmentCategory]) -> EquipmentCategory:
    key = _norm(name)
    if key not in cache:
        category = next((item for item in candidates if _norm(item.name) == key), None)
        if category is None:
            category = EquipmentCategory(company_id=company_id, name=name[:80])
            db.add(category)
            db.flush()
            candidates.append(category)
        cache[key] = category
    return cache[key]


def confirm_work_order_import(db: Session, company_id: int, actor: User, content: bytes, filename: str, preview_token: str, decisions: list[dict[str, Any]]) -> dict[str, Any]:
    preview = preview_work_order_import(db, company_id, content, filename)
    if not verify_preview_token(preview_token, company_id, preview["file_sha256"]):
        raise HTTPException(status_code=409, detail="La vista previa venció o no corresponde al archivo y empresa activa. Volvé a previsualizar.")
    decision_map = {item["key"]: item for item in decisions}
    preview_by_key = {item["key"]: item for item in preview["rows"]}
    if set(decision_map) - set(preview_by_key):
        raise HTTPException(status_code=422, detail="La selección incluye filas que no pertenecen a este archivo.")

    batch = db.query(WorkOrderImportBatch).filter_by(company_id=company_id, file_sha256=preview["file_sha256"]).first()
    imported_count = 0
    skipped_count = 0
    result_rows: list[dict[str, Any]] = []
    status_rows = db.query(WorkOrderStatus).filter_by(company_id=company_id, active=True).all()
    valid_status_ids = {item.id for item in status_rows}
    parsed_workbook = parse_work_order_xlsx(content, filename)
    parsed_by_key = {_row_key(row): row for row in parsed_workbook.rows}
    customer_cache: dict[tuple[str, str], Customer] = {}
    category_cache: dict[str, EquipmentCategory] = {}
    customer_candidates = db.query(Customer).filter_by(company_id=company_id, active=True).order_by(Customer.id).all()
    category_candidates = db.query(EquipmentCategory).filter_by(company_id=company_id).order_by(EquipmentCategory.id).all()
    try:
        if batch is None:
            batch = WorkOrderImportBatch(company_id=company_id, file_sha256=preview["file_sha256"], filename=filename[:255], created_by_user_id=actor.id)
            db.add(batch)
            db.flush()
        existing_locations = set(db.query(WorkOrderImportRow.source_sheet, WorkOrderImportRow.source_row)
            .filter_by(company_id=company_id, batch_id=batch.id).all())
        imported_order_ids: list[int] = []
        for key, source in parsed_by_key.items():
            item = preview_by_key[key]
            if item["state"] == "already_imported" or (source.sheet, source.row_number) in existing_locations:
                skipped_count += 1
                result_rows.append({"key": key, "result": "already_imported", "work_order_id": None})
                continue
            decision = decision_map.get(key, {})
            fields = dict(source.fields)
            corrections = {name: decision.get(name) for name in ("customer_name", "phone", "received_at", "category")}
            for name, value in corrections.items():
                if value is not None and (not isinstance(value, str) or value.strip()):
                    fields[name] = value.strip() if isinstance(value, str) else value
            reasons = []
            if not fields.get("customer_name"):
                reasons.append("Falta el cliente.")
            if not fields.get("received_at"):
                reasons.append("Falta una fecha de recepción válida.")
            if not fields.get("category"):
                reasons.append("Falta el tipo o categoría del equipo.")
            if reasons:
                skipped_count += 1
                result_rows.append({"key": key, "result": "blocked", "reasons": reasons, "work_order_id": None})
                continue
            if item["state"] == "duplicate" and not decision.get("include", False):
                skipped_count += 1
                result_rows.append({"key": key, "result": "omitted_duplicate", "work_order_id": None})
                continue
            if isinstance(fields.get("received_at"), str):
                try:
                    fields["received_at"] = datetime.fromisoformat(fields["received_at"])
                except ValueError:
                    skipped_count += 1
                    result_rows.append({"key": key, "result": "blocked", "reasons": ["La fecha corregida no es válida."], "work_order_id": None})
                    continue
            status_id = decision.get("status_id", item["suggested_status_id"])
            if status_id is not None and status_id not in valid_status_ids:
                raise HTTPException(status_code=422, detail=f"El estado seleccionado para {key} no pertenece a la empresa activa.")
            target_status = next((status for status in status_rows if status.id == status_id), None)
            customer = _get_or_create_customer(db, company_id, fields["customer_name"], fields.get("phone"), customer_cache, customer_candidates)
            category = _get_or_create_category(db, company_id, fields["category"], category_cache, category_candidates)
            equipment_notes = "\n".join(f"{label}: {value}" for label, value in (("Ficha histórica", fields.get("ficha")), ("Técnico", fields.get("technician")), ("Sector", fields.get("sector"))) if value) or None
            equipment = Equipment(company_id=company_id, customer_id=customer.id, category_id=category.id,
                brand=(fields.get("brand") or "")[:100] or None, model=(fields.get("model") or "")[:120] or None,
                description=(fields.get("motive") or "")[:300] or None, notes=equipment_notes)
            db.add(equipment)
            db.flush()
            notes = {
                "Origen": f"Importación histórica · {source.sheet}, fila {source.row_number}",
                "Ficha histórica": fields.get("ficha"), "Estado original": fields.get("legacy_status"),
                "Recibió": fields.get("received_by"), "Repuestos": fields.get("spare_parts"),
                "Bobinado": fields.get("winding"), "Técnico": fields.get("technician"),
                "Pagado": fields.get("paid"), "Garantía": fields.get("warranty"),
                "Sector": fields.get("sector"), "Significado del color": fields.get("color_meaning"),
                "Entrega a": fields.get("delivered_to"),
                "Fecha de egreso registrada": fields.get("exit_at"),
            }
            note_text = "\n".join(f"{label}: {value}" for label, value in notes.items() if value)
            number = _next_number(db, company_id)
            status_code = re.sub(r"[^A-Z0-9]+", "_", (target_status.name if target_status else "RECEIVED").upper()).strip("_")[:30] or "RECEIVED"
            exit_at = fields.get("exit_at")
            order = WorkOrder(company_id=company_id, number=number, customer_id=customer.id, equipment_id=equipment.id,
                received_at=fields["received_at"],
                completed_at=exit_at if target_status and target_status.marks_completed else None,
                delivered_at=exit_at if target_status and target_status.marks_delivered else None,
                reported_fault=fields.get("motive") or "Sin motivo registrado en la planilla.", notes=note_text or None,
                received_by_user_id=actor.id, status=status_code, status_id=target_status.id if target_status else None)
            db.add(order)
            db.flush()
            db.add(WorkOrderEvent(company_id=company_id, work_order_id=order.id, event_type="RECEPTION", status=status_code,
                detail=f"Importada desde {source.sheet}, fila {source.row_number}.", user_id=actor.id))
            raw_fields = {str(k): (str(v) if v is not None else "") for k, v in source.source_values.items()}
            edited = {name: (value.isoformat() if hasattr(value, "isoformat") else value) for name, value in corrections.items() if value is not None and value != source.fields.get(name)}
            if edited:
                raw_fields["_import_corrections"] = json.dumps(edited, ensure_ascii=False)
            db.add(WorkOrderImportRow(company_id=company_id, batch_id=batch.id, work_order_id=order.id,
                source_sheet=source.sheet, source_row=source.row_number, legacy_ficha=fields.get("ficha"),
                legacy_status=fields.get("legacy_status"), row_sha256=normalized_row_hash(source), legacy_fields=raw_fields))
            existing_locations.add((source.sheet, source.row_number))
            imported_order_ids.append(order.id)
            imported_count += 1
            result_rows.append({"key": key, "result": "imported", "work_order_id": order.id, "work_order_number": number})
        batch.imported_count = (batch.imported_count or 0) + imported_count
        db.commit()
        return {"imported": imported_count, "skipped": skipped_count, "rows": result_rows, "work_order_ids": imported_order_ids}
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception("Work-order import rolled back for company_id=%s", company_id)
        raise HTTPException(status_code=409, detail="No se pudo completar la importación; se revirtieron los cambios. Volvé a previsualizar antes de reintentar.") from None
