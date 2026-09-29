from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import zlib
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
ALLOWED_SHEETS = ("Maquinas 2024", "2025", "Desarmados", "Hoja1")
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_UNPACKED_BYTES = 100 * 1024 * 1024
MAX_ZIP_ENTRIES = 2000
MAX_ROWS_PER_SHEET = 15000


class WorkbookImportError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedSourceRow:
    sheet: str
    row_number: int
    fields: dict[str, Any]
    source_values: dict[str, Any]


@dataclass(frozen=True)
class ParsedWorkbook:
    sha256: str
    rows: list[ParsedSourceRow]
    sheet_counts: dict[str, int]


def _tag(name: str) -> str:
    return f"{{{MAIN_NS}}}{name}"


def _read_entry(archive: zipfile.ZipFile, path: str) -> bytes:
    try:
        return archive.read(path)
    except (zipfile.BadZipFile, OSError, EOFError, RuntimeError, NotImplementedError, zlib.error):
        raise WorkbookImportError("El archivo XLSX está dañado o contiene una compresión no válida.") from None


def _text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return "".join(part.text or "" for part in node.findall(f".//{_tag('t')}"))


def _column_index(cell_reference: str) -> int:
    letters = re.match(r"[A-Za-z]+", cell_reference)
    if not letters:
        raise WorkbookImportError("El libro contiene una referencia de celda inválida.")
    index = 0
    for char in letters.group(0).upper():
        index = index * 26 + ord(char) - 64
    return index - 1


def _normal_header(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _parse_date(value: Any) -> datetime | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not 1 <= float(value) <= 73415:
            return None
        try:
            parsed = datetime(1899, 12, 30) + timedelta(days=float(value))
            return parsed.replace(hour=0, minute=0, second=0, microsecond=0)
        except (OverflowError, ValueError):
            return None
    raw = str(value).strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", raw):
        try:
            serial = float(raw)
            if 1 <= serial <= 73415:
                return (datetime(1899, 12, 30) + timedelta(days=serial)).replace(hour=0, minute=0, second=0, microsecond=0)
        except (OverflowError, ValueError):
            return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
        return parsed if 1900 <= parsed.year <= 2100 else None
    except ValueError:
        return None


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).replace("\u00a0", " ").split()).strip()
    return text or None


def _source_field(source: dict[str, Any], *names: str) -> str | None:
    for name in names:
        key = _normal_header(name)
        if key in source and _clean(source[key]) is not None:
            return _clean(source[key])
    return None


def _map_fields(sheet: str, row: dict[str, Any]) -> dict[str, Any]:
    date_value = row.get("0") if sheet == "2025" else None
    received = _parse_date(date_value) if date_value not in (None, "") else None
    if received is None:
        received = _parse_date(_source_field(row, "fecha", "fecha ingreso", "fecha recepción"))
    return {
        "received_at": received,
        "customer_name": _source_field(row, "cliente"),
        "phone": _source_field(row, "celular", "telefono", "teléfono"),
        "category": _source_field(row, "maq mot bba otro", "maquina motor bomba otro"),
        "brand": _source_field(row, "marca"),
        "model": _source_field(row, "caracteristicas", "características", "modelo"),
        "motive": _source_field(row, "motivo", "falla", "trabajo"),
        "received_by": _source_field(row, "recibi", "recibí"),
        "ficha": _source_field(row, "n de ficha", "numero de ficha", "ficha"),
        "legacy_status": _source_field(row, "estado"),
        "spare_parts": _source_field(row, "repuestos"),
        "winding": _source_field(row, "bobinado"),
        "technician": _source_field(row, "realizado por", "tecnico", "técnico"),
        "paid": _source_field(row, "pagado"),
        "warranty": _source_field(row, "garantia", "garantía"),
        "sector": _source_field(row, "sector que esta", "sector que está"),
        "color_meaning": _source_field(row, "significado de colores"),
        "delivered_to": _source_field(row, "se entrega a"),
        "exit_at": _parse_date(_source_field(row, "fecha egreso", "entregado listo rep", "devuelto el")),
    }


def parse_work_order_xlsx(content: bytes, filename: str) -> ParsedWorkbook:
    if not filename.casefold().endswith(".xlsx"):
        raise WorkbookImportError("Seleccioná un archivo .xlsx.")
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise WorkbookImportError("El archivo está vacío o supera el límite de 15 MB.")
    if not content.startswith(b"PK"):
        raise WorkbookImportError("El archivo no tiene un contenedor XLSX válido.")
    try:
        archive = zipfile.ZipFile(BytesIO(content))
    except (zipfile.BadZipFile, OSError):
        raise WorkbookImportError("No se pudo abrir el archivo XLSX.") from None
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ZIP_ENTRIES:
            raise WorkbookImportError("El libro tiene demasiados componentes internos.")
        if sum(item.file_size for item in infos) > MAX_UNPACKED_BYTES:
            raise WorkbookImportError("El contenido expandido del libro supera 100 MB.")
        for info in infos:
            path = PurePosixPath(info.filename)
            if path.is_absolute() or ".." in path.parts or info.flag_bits & 0x1:
                raise WorkbookImportError("El libro contiene una entrada ZIP no permitida.")
        required = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels"}
        if not required.issubset(archive.namelist()):
            raise WorkbookImportError("El archivo no contiene una estructura XLSX completa.")
        try:
            workbook_bytes = _read_entry(archive, "xl/workbook.xml")
            if b"<!DOCTYPE" in workbook_bytes.upper() or b"<!ENTITY" in workbook_bytes.upper():
                raise WorkbookImportError("El libro contiene declaraciones XML no permitidas.")
            workbook = ET.fromstring(workbook_bytes)
            rel_bytes = _read_entry(archive, "xl/_rels/workbook.xml.rels")
            if b"<!DOCTYPE" in rel_bytes.upper() or b"<!ENTITY" in rel_bytes.upper():
                raise WorkbookImportError("El libro contiene relaciones XML no permitidas.")
            rel_root = ET.fromstring(rel_bytes)
            rels = {node.attrib["Id"]: node.attrib["Target"] for node in rel_root.findall(f"{{{PKG_REL_NS}}}Relationship")}
            shared: list[str] = []
            if "xl/sharedStrings.xml" in archive.namelist():
                shared_xml = _read_entry(archive, "xl/sharedStrings.xml")
                if b"<!DOCTYPE" in shared_xml.upper() or b"<!ENTITY" in shared_xml.upper():
                    raise WorkbookImportError("El libro contiene textos XML no permitidos.")
                strings = ET.fromstring(shared_xml)
                shared = [_text(item) for item in strings.findall(_tag("si"))]
        except (ET.ParseError, KeyError):
            raise WorkbookImportError("El libro contiene XML incompleto o inválido.") from None

        sheet_entries: dict[str, str] = {}
        for sheet in workbook.findall(f"{_tag('sheets')}/{_tag('sheet')}"):
            name = sheet.attrib.get("name", "")
            relation = sheet.attrib.get(f"{{{REL_NS}}}id", "")
            if name not in ALLOWED_SHEETS or sheet.attrib.get("state", "visible") != "visible":
                continue
            target = rels.get(relation)
            if not target:
                continue
            target_path = target.lstrip("/") if target.startswith("/") else (PurePosixPath("xl") / target).as_posix()
            if ".." in PurePosixPath(target_path).parts or target_path not in archive.namelist():
                raise WorkbookImportError(f"No se pudo resolver la hoja {name}.")
            sheet_entries[name] = target_path

        try:
            parsed_rows: list[ParsedSourceRow] = []
            counts: dict[str, int] = {}
            for name in ALLOWED_SHEETS:
                if name not in sheet_entries:
                    counts[name] = 0
                    continue
                xml = _read_entry(archive, sheet_entries[name])
                if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
                    raise WorkbookImportError("Una hoja contiene declaraciones XML no permitidas.")
                root = ET.fromstring(xml)
                sheet_rows = root.findall(f".//{_tag('sheetData')}/{_tag('row')}")
                if len(sheet_rows) > MAX_ROWS_PER_SHEET:
                    raise WorkbookImportError(f"La hoja {name} supera 15.000 filas.")
                headers: dict[int, str] = {}
                count = 0
                for row_el in sheet_rows:
                    try:
                        row_number = int(row_el.attrib.get("r", "0"))
                    except ValueError:
                        raise WorkbookImportError(f"La hoja {name} contiene un número de fila inválido.") from None
                    cells: dict[int, Any] = {}
                    for cell in row_el.findall(_tag("c")):
                        idx = _column_index(cell.attrib.get("r", ""))
                        value_el = cell.find(_tag("v"))
                        inline_el = cell.find(_tag("is"))
                        value: Any = value_el.text if value_el is not None else (_text(inline_el) if inline_el is not None else None)
                        if cell.attrib.get("t") == "s" and value not in (None, ""):
                            try:
                                value = shared[int(value)]
                            except (ValueError, IndexError):
                                raise WorkbookImportError(f"La hoja {name} referencia un texto interno inválido.") from None
                        cells[idx] = value
                    if row_number == 1:
                        headers = {idx: _normal_header(value) for idx, value in cells.items() if _clean(value)}
                        continue
                    if not cells or not any(_clean(value) for value in cells.values()):
                        continue
                    source_values = {headers.get(idx, f"columna {idx + 1}"): value for idx, value in cells.items()}
                    fields = _map_fields(name, source_values)
                    parsed_rows.append(ParsedSourceRow(name, row_number, fields, source_values))
                    count += 1
                    if len(parsed_rows) > 15000:
                        raise WorkbookImportError("El libro supera 15.000 filas de datos en total.")
                counts[name] = count
        except ET.ParseError:
            raise WorkbookImportError("Una hoja contiene XML incompleto o inválido.") from None
    return ParsedWorkbook(hashlib.sha256(content).hexdigest(), parsed_rows, counts)


def normalized_row_hash(row: ParsedSourceRow) -> str:
    fields = {
        key: value.isoformat() if isinstance(value, (date, datetime)) else (_clean(value) if value is not None else None)
        for key, value in row.fields.items()
    }
    payload = json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()