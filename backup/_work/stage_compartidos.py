import io, os, subprocess, sys, tempfile

ROOT = r"C:\Programacion\vogel-gestion"

# Bloques del otro worker (IA) que NO van en mi commit: se quitan de la copia que se indexa.
QUITAR = {
    "frontend/src/router.ts": [
        'import AiConsumoView from "./views/AiConsumoView.vue";\n',
        '''      {
        path: "consumo-ia",
        name: "consumo-ia",
        component: AiConsumoView,
        alias: ["/consumo-ia"],
        // El mismo permiso que el asistente: consumo sin poder usar la IA no tiene sentido.
        meta: { requiresAuth: true, permission: "ai.use" },
      },
''',
    ],
    "frontend/src/components/Sidebar.vue": [
        '''    {
      id: "consumo-ia",
      label: "Consumo de IA",
      to: "/app/consumo-ia",
      icon: IconAssistant,
      // Junto al asistente porque es la otra mitad de la misma pregunta: cuanto se uso y
      // cuanto queda. Sin empresa activa no hay "mi consumo", y la ruta tampoco responderia.
      visible: session.activeCompany !== null && session.hasPermission("ai.use"),
    },
''',
    ],
}

for rel, bloques in QUITAR.items():
    src = os.path.join(ROOT, rel.replace("/", os.sep))
    texto = io.open(src, encoding="utf-8", newline="").read()
    # El archivo puede estar en CRLF: los bloques a quitar se adaptan a su fin de linea.
    crlf = "\r\n" in texto
    copia = texto
    for b in bloques:
        patron = b.replace("\n", "\r\n") if crlf else b
        if patron not in copia:
            print("!! no encontre el bloque en", rel, "->", b.strip().splitlines()[0])
            sys.exit(1)
        copia = copia.replace(patron, "", 1)
    fd, tmp = tempfile.mkstemp(suffix=".tmp")
    os.close(fd)
    with io.open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(copia)
    # hash-object: mete el blob en el repo sin tocar el archivo del working tree
    h = subprocess.run(["git", "hash-object", "-w", tmp], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(["git", "update-index", "--cacheinfo", "100644," + h + "," + rel], cwd=ROOT, check=True)
    os.remove(tmp)
    print("indexado", rel, "->", h)
