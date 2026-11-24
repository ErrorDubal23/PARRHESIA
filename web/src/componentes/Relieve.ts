// Relieve: la tarjeta bajo el cursor se inclina unos pocos grados hacia él, como un objeto que sobresale.
// Un solo oyente para toda la app (no uno por tarjeta). Solo con ratón o trackpad, y nunca si la persona pidió
// reducir el movimiento. La inclinación va en --rx / --ry; el CSS (profundidad.css) decide cuánto se nota.
import { useEffect } from "react";

const CON_RELIEVE = ".publicacion, .comunidad-fila, .carpeta, .tema-portada, .persona, .ficha-dato";
const MAXIMO = 4; // grados

export function useRelieve() {
  useEffect(() => {
    const quieto = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const conPuntero = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
    if (quieto || !conPuntero) return;
    let actual: HTMLElement | null = null;
    let pedido = 0;
    const soltar = () => {
      if (!actual) return;
      actual.style.removeProperty("--rx");
      actual.style.removeProperty("--ry");
      actual = null;
    };
    const mover = (e: PointerEvent) => {
      const objetivo = (e.target as Element | null)?.closest<HTMLElement>(CON_RELIEVE) ?? null;
      if (objetivo !== actual) soltar();
      if (!objetivo) return;
      actual = objetivo;
      cancelAnimationFrame(pedido);
      pedido = requestAnimationFrame(() => {
        const r = objetivo.getBoundingClientRect();
        const x = (e.clientX - r.left) / r.width - 0.5;   // -0.5 … 0.5
        const y = (e.clientY - r.top) / r.height - 0.5;
        objetivo.style.setProperty("--rx", `${(x * MAXIMO * 2).toFixed(2)}deg`);
        objetivo.style.setProperty("--ry", `${(-y * MAXIMO * 2).toFixed(2)}deg`);
      });
    };
    document.addEventListener("pointermove", mover, { passive: true });
    document.addEventListener("pointerleave", soltar);
    return () => {
      document.removeEventListener("pointermove", mover);
      document.removeEventListener("pointerleave", soltar);
      cancelAnimationFrame(pedido);
      soltar();
    };
  }, []);
}
