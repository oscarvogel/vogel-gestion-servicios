import io

RUTA = r"C:\Programacion\_worktrees\vogel-merge\docs\sesion-2026-10-23-tecnicos.md"

contenido = io.open(RUTA, encoding="utf-8").read()

# --- 1) Leccion nueva en 5.9 ---
viejo = (
    "3. **Un 502/499 en el log del proxy explica una pantalla vacia.** `499` es el cliente\n"
    "   que corta la peticion; `connect() failed (111)` es el upstream que no acepta.\n"
)
nuevo = viejo + (
    "4. **Un test que pasa no siempre prueba el fix.** El test del proxy daba 20/20\n"
    "   *con* el bug del IPv6, porque nginx reintenta la misma peticion contra otra\n"
    "   direccion del AAAA y termina respondiendo igual. Lo que prueba el fix es el log:\n"
    "   cero lineas con IPv6.\n"
)
assert viejo in contenido, "no encontre la leccion 3"
contenido = contenido.replace(viejo, nuevo, 1)

# --- 2) Resultado del despliegue en 5.10: se reemplaza el parrafo entero ---
ini = contenido.find("**El despliegue.**")
assert ini > 0, "no encontre el parrafo del despliegue"
fin = contenido.find("\n\n", ini)
assert fin > ini, "el parrafo no termina"

nuevo2 = (
    "**El despliegue.** Las dos apps de staging (`...-staging-backend` y\n"
    "`...-staging-frontend`) se apuntaron a `main` y se re-desplegaron. La cola de\n"
    "deploys de Coolify es **compartida entre proyectos**: delante de los nuestros\n"
    "hab\u00eda deploys de `vogel-gestion-servicios-production` y de\n"
    "`registro-produccion`, y hubo que esperar.\n"
    "\n"
    "El backend sali\u00f3 bien a la primera (deploy 1680). El frontend **no**: el deploy\n"
    "1681 dej\u00f3 el contenedor viejo sirviendo (el bundle segu\u00eda siendo\n"
    "`index-DODAW9H1.js`, el anterior) y, peor, el nginx de ese contenedor segu\u00eda\n"
    "resolviendo el backend por IPv6 (`upstream: \"http://[fd04:36e8:6aaa::17]:8000\"`),\n"
    "con `connect() failed (111)` y alg\u00fan 500. Al re-desplegar (1683) s\u00ed: bundle\n"
    "`index-COx7kMJw.js` y **cero** upstreams IPv6 en el log del nginx.\n"
    "\n"
    "**Verificado en el navegador** (despu\u00e9s del deploy final):\n"
    "\n"
    "- \"9316 \u00f3rdenes en esta empresa\" en el listado (no \"0 \u00f3rdenes\").\n"
    "- Maestro de t\u00e9cnicos: \"45 activos de 45\", con los filtros Todos / Activos /\n"
    "  Desactivados y las acciones Renombrar / Desactivar.\n"
    "- El combo de t\u00e9cnico de la recepci\u00f3n **abre debajo del campo** con los\n"
    "  t\u00e9cnicos activos, y filtrando \"allad\" aparece \"Alladio\".\n"
    "- El men\u00fa tiene las tres secciones juntas: Cierre a marcas, T\u00e9cnicos y\n"
    "  Consumo de IA (la que tra\u00eda `main`).\n"
    "- La sesi\u00f3n sobrevive a una recarga completa de la p\u00e1gina (por el refresh token\n"
    "  con empresa), y el listado sigue con las OTs de CiberBrain (#9316, #9315, ...).\n"
)
contenido = contenido[:ini] + nuevo2 + contenido[fin:]

io.open(RUTA, "w", encoding="utf-8", newline="").write(contenido)
print("bitacora actualizada")
