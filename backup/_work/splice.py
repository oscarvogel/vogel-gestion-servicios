"""Empalma un bloque nuevo en un .md reemplazando todo lo que va entre dos secciones.

Uso: python splice.py <archivo_destino> <archivo_bloque> <prefijo_seccion_inicio> <prefijo_seccion_fin>
Las secciones se localizan por el prefijo de linea (p.ej. "## 1." y "## 2."), no por
texto literal, asi el empalme no depende de acentos ni de redaccion.
"""
import io
import sys


def main() -> int:
    dest, block_path, start_prefix, end_prefix = sys.argv[1:5]

    with io.open(dest, encoding="utf-8") as fh:
        doc = fh.read()
    with io.open(block_path, encoding="utf-8") as fh:
        block = fh.read()

    lines = doc.split("\n")

    start = None
    end = None
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if start is None and stripped.startswith(start_prefix):
            start = idx
            continue
        if start is not None and stripped.startswith(end_prefix):
            end = idx
            break

    if start is None:
        print("ERROR: no se encontro la seccion %r" % start_prefix)
        return 1
    if end is None:
        print("ERROR: no se encontro la seccion %r" % end_prefix)
        return 1

    new_lines = lines[:start] + block.rstrip("\n").split("\n") + ["", "---", ""] + lines[end:]
    new_doc = "\n".join(new_lines)

    with io.open(dest, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(new_doc)

    print("OK: secciones %s..%s reemplazadas -> %d bytes" % (start + 1, end, len(new_doc.encode("utf-8"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
