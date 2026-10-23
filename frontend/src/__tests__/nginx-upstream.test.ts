import { describe, it, expect } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * El nginx del frontend proxea /api/ al backend. La resolucion del nombre la hace el
 * DNS embebido de Docker, que devuelve el A (IPv4) y el AAAA (IPv6) del contenedor.
 *
 * El backend arranca con `uvicorn --host 0.0.0.0`: escucha en IPv4 y NO en IPv6. Sin
 * `ipv6=off` en el resolver, nginx elige al azar entre la A y la AAAA y la mitad de las
 * peticiones al backend fallan con "connection refused": la pantalla se queda vacia
 * ("Todavia no hay ordenes de trabajo") sin que se entienda por que.
 *
 * Este test controla la linea del resolver: si alguien la saca, falla.
 */
function leerNginxConf(): string {
  const rutas = ["nginx.conf", "frontend/nginx.conf"];
  const archivo = rutas.map((r) => resolve(process.cwd(), r)).find((r) => existsSync(r));
  expect(archivo, "no se encontro nginx.conf").toBeTruthy();
  return readFileSync(archivo!, "utf8");
}

describe("nginx del frontend", () => {
  it("el resolver pide solo direcciones IPv4", () => {
    const conf = leerNginxConf();
    // Solo la directiva real (no las menciones en los comentarios).
    const resolver = conf.match(/^\s*resolver\s+[^;]+;/m);
    expect(resolver, "no hay ninguna directiva resolver").toBeTruthy();
    expect(resolver![0]).toMatch(/ipv6=off/);
  });

  it("el backend se resuelve por nombre, no por IP fija", () => {
    const conf = leerNginxConf();
    // Una IP horneada en la imagen queda vieja en cada deploy: el contenedor del
    // backend cambia de direccion. Tiene que ser un nombre (el alias de red).
    expect(conf).not.toMatch(/BACKEND_INTERNAL_URL.*https?:\/\/\[\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\]/);
    expect(conf).toContain("__BACKEND_INTERNAL_URL__");
  });
});
