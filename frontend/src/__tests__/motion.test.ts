import { afterEach, describe, expect, it, vi } from "vitest";
import { gsap } from "gsap";
import { revealIn } from "../lib/motion";

function escena() {
  const root = document.createElement("div");
  root.innerHTML = `
    <span id="n" data-count="1234.5" data-decimals="1" data-prefix="$ ">$ 1.234,5</span>
    <div id="card" data-rise></div>
    <i id="bar" data-grow-x></i>`;
  document.body.appendChild(root);
  return root;
}

describe("microanimaciones", () => {
  afterEach(() => {
    document.body.innerHTML = "";
    vi.unstubAllGlobals();
  });

  it("con movimiento reducido no anima ni toca el texto", () => {
    vi.stubGlobal("matchMedia", (q: string) => ({ matches: q.includes("reduce") }));
    const root = escena();

    expect(revealIn(root)).toBeNull();
    expect(root.querySelector("#n")!.textContent).toBe("$ 1.234,5");
    expect(root.querySelector<HTMLElement>("#card")!.getAttribute("style")).toBeNull();
  });

  it("el contador pasa por valores intermedios y termina en el texto que pinto Vue", () => {
    const root = escena();
    const tl = revealIn(root)!;
    const n = root.querySelector("#n")!;

    tl.progress(0.3);
    const intermedio = n.textContent!;
    expect(intermedio).toMatch(/^\$ [\d.]+,\d$/);
    expect(intermedio).not.toBe("$ 1.234,5");

    tl.progress(1);
    expect(n.textContent).toBe("$ 1.234,5");
    // Sin estilos residuales: un transform que queda rompe sticky y modales.
    expect(root.querySelector<HTMLElement>("#card")!.style.transform).toBe("");
    expect(root.querySelector<HTMLElement>("#bar")!.style.transform).toBe("");
  });

  it("la segunda vez cuenta desde el valor anterior", () => {
    const root = escena();
    revealIn(root)!.progress(1);
    const n = root.querySelector<HTMLElement>("#n")!;
    expect(n.dataset.from).toBe("1234.5");

    n.dataset.count = "2000";
    n.textContent = "$ 2.000,0";
    const tl = revealIn(root)!;
    tl.progress(0.01);
    const valor = Number(n.textContent!.replace("$ ", "").replace(/\./g, "").replace(",", "."));
    expect(valor).toBeGreaterThanOrEqual(1234.5);
    expect(valor).toBeLessThan(2000);
  });

  it("una cuenta vieja no pisa el numero de un dato nuevo", () => {
    // El dato cambia mientras la cuenta corre (cambiar de mes en el cierre): la cuenta
    // vieja ya no vale y no puede escribir sobre el numero que pino Vue.
    const root = escena();
    const n = root.querySelector<HTMLElement>("#n")!;
    const tl = revealIn(root)!;
    tl.progress(0.05);

    n.dataset.count = "2000";
    n.textContent = "$ 2.000,0";
    tl.progress(0.5);

    expect(n.textContent).toBe("$ 2.000,0");
  });

  it("el numero no queda en cero cuando se corta la cuenta anterior", () => {
    // Es lo que pasaba en el cierre: al cambiar de mes, la cuenta anterior se cortaba
    // con el numero en cero y el total a liquidar quedaba en $ 0,00.
    const root = escena();
    const n = root.querySelector<HTMLElement>("#n")!;
    let ctx: gsap.Context | null = null;
    let tl: gsap.core.Timeline | null = null;
    const reveal = () => {
      ctx?.revert();
      ctx = gsap.context(() => {
        tl = revealIn(root);
      }, root);
    };

    reveal();
    tl!.progress(0.02);
    n.dataset.count = "2000";
    n.textContent = "$ 2.000,0";
    reveal();
    tl!.progress(1);

    expect(n.textContent).toBe("$ 2.000,0");
  });
});
