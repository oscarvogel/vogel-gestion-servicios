import io
import re

RUTA = r"C:\Programacion\_worktrees\vogel-merge\docs\sesion-2026-10-23-tecnicos.md"

contenido = io.open(RUTA, encoding="utf-8").read()
lineas = contenido.split("\n")

# La linea 164 (indice 163) quedo pisada por el script anterior.
BUENA = (
    "**Por qu\u00e9 no lo traduce el test:** jsdom no calcula posiciones, as\u00ed que en el test "
    "el men\u00fa"
)

if lineas[163].startswith("lados tenian los mismos archivos"):
    lineas[163] = BUENA
    print("linea 164 restaurada")
else:
    print("ATENCION: la linea 163 dice: " + lineas[163][:60])

# Barrer cualquier CJK que haya quedado (el "了" que venia del commit anterior).
for i, linea in enumerate(lineas):
    if re.search(r"[\u4e00-\u9fff]", linea):
        nueva = re.sub(r"[\u4e00-\u9fff]+", "", linea)
        lineas[i] = nueva
        print("CJK fuera en la linea %d" % (i + 1))

contenido = "\n".join(lineas)
io.open(RUTA, "w", encoding="utf-8", newline="").write(contenido)

print("queda CJK: " + str(bool(re.search(r"[\u4e00-\u9fff]", contenido))))
