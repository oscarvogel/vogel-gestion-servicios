import io
import re

RUTA = r"C:\Programacion\_worktrees\vogel-merge\docs\sesion-2026-10-23-tecnicos.md"

with io.open(RUTA, encoding="utf-8") as fh:
    texto = fh.read()

cambios = []
lineas = texto.split("\n")

# 1) Sacar el fragmento que se colo en chino y dejar la frase ARMada.
for i, linea in enumerate(lineas):
    if re.search(r"[\u4e00-\u9fff]", linea):
        lineas[i] = "lados tenian los mismos archivos, pero con commits distintos. Conflictos:"
        cambios.append("linea %d (CJK fuera)" % (i + 1))
texto = "\n".join(lineas)

# 2) Recuperar el encabezado de la seccion 6.
if "## 6. Pendientes" not in texto:
    marcador = "- [x] **Puerto p"
    i = texto.find(marcador)
    if i > 0:
        texto = texto[:i] + "## 6. Pendientes\n\n" + texto[i:]
        cambios.append("encabezado 6 recuperado")

# 3) Pendientes: el merge ya esta hecho.
viejo = (
    "- [ ] Merge de `feature/cyberbrain-migracion` a `main` y, despu\u00e9s, restaurar staging a `main`\n"
    "      (la base de staging ya est\u00e1 en `20261023_0027`; `main` s\u00f3lo llega a `0025`)."
)
nuevo = (
    "- [x] Merge de `feature/cyberbrain-migracion` a `main` (commit `22a2f14`, CI en verde) y staging\n"
    "      restaurado a `main`: la base de staging qued\u00f3 en `20261023_0027` y `main` ahora tambi\u00e9n\n"
    "      llega a `0027`."
)
if viejo in texto:
    texto = texto.replace(viejo, nuevo, 1)
    cambios.append("pendiente del merge")

viejo2 = "- [ ] La base de producci\u00f3n sigue sin tocar."
nuevo2 = (
    "- [x] La base de producci\u00f3n: nadie la toc\u00f3 a mano, pero el deploy de producci\u00f3n tom\u00f3 `main`\n"
    "      y aplic\u00f3 las migraciones 0026 y 0027 (las dos aditivas). El men\u00fa **T\u00e9cnicos** queda\n"
    "      visible para los Administradores pero con el maestro **vac\u00edo**: los datos de CiberBrain\n"
    "      s\u00f3lo est\u00e1n en la base de staging."
)
if viejo2 in texto:
    texto = texto.replace(viejo2, nuevo2, 1)
    cambios.append("pendiente de produccion")

with io.open(RUTA, "w", encoding="utf-8", newline="") as fh:
    fh.write(texto)

print("cambios: " + (", ".join(cambios) if cambios else "NINGUNO"))
print("queda CJK: " + str(bool(re.search(r"[\u4e00-\u9fff]", texto))))
print("tiene '## 6. Pendientes': " + str("## 6. Pendientes" in texto))
