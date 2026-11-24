import { useEffect, useId, useState } from "react";

// Interruptor de tema: un recuadro con un cielo sobre las montañas de Colombia (tres cordilleras, un nevado y una
// palma de cera). De día, un sol dorado con rayos de puntos (el puntillismo del relieve de la pantalla de acceso);
// de noche, el astro se desliza a
// la derecha, los rayos se recogen, una sombra lo convierte en luna creciente y aparecen estrellas que titilan.
// La preferencia se guarda y se comparte entre pestañas.

type Tema = "claro" | "oscuro";
const EVENTO = "tema-cambiado";

const actual = (): Tema => (document.documentElement.dataset.tema === "oscuro" ? "oscuro" : "claro");

function fijar(tema: Tema) {
  // Cambio uniforme: cada parte de la página tiene su propia transición y, si se dejan, cambian a destiempo.
  // Se apagan un instante (menos las del interruptor, que tiene su animación) y la página cambia de una vez.
  const raiz = document.documentElement;
  raiz.classList.add("cambiando-tema");
  raiz.dataset.tema = tema;
  void raiz.offsetHeight;                               // aplica los colores nuevos sin transición
  requestAnimationFrame(() => requestAnimationFrame(() => raiz.classList.remove("cambiando-tema")));
  try { localStorage.setItem("tema", tema); } catch { /* sin almacenamiento: vale solo esta visita */ }
  window.dispatchEvent(new CustomEvent(EVENTO));
}

function useTema(): [Tema, (t: Tema) => void] {
  const [tema, setTema] = useState<Tema>(actual);
  useEffect(() => {
    const sincronizar = () => setTema(actual());
    const otraPestana = (e: StorageEvent) => {
      if (e.key === "tema" && (e.newValue === "claro" || e.newValue === "oscuro")) {
        document.documentElement.dataset.tema = e.newValue;
        sincronizar();
      }
    };
    window.addEventListener(EVENTO, sincronizar);
    window.addEventListener("storage", otraPestana);
    return () => { window.removeEventListener(EVENTO, sincronizar); window.removeEventListener("storage", otraPestana); };
  }, []);
  return [tema, fijar];
}

// Rayos: doce puntos en anillo alrededor del disco (en un plano de 32 × 32).
const RAYOS = Array.from({ length: 12 }, (_, i) => {
  const a = (i * Math.PI) / 6;
  return { cx: 16 + Math.cos(a) * 12.2, cy: 16 + Math.sin(a) * 12.2, r: i % 2 ? 0.95 : 1.35 };
});
// Estrellas del cielo nocturno (plano de 72 × 36).
const ESTRELLAS = [{ x: 9, y: 9, r: 1.1 }, { x: 18, y: 5, r: 0.7 }, { x: 14, y: 17, r: 0.8 }, { x: 25, y: 12, r: 1.2 },
  { x: 6, y: 22, r: 0.6 }, { x: 30, y: 6, r: 0.6 }];
export function BotonTema({ className = "" }: { className?: string }) {
  const [tema, setTema] = useTema();
  const oscuro = tema === "oscuro";
  const mascara = "sombra-luna-" + useId().replace(/[^a-zA-Z0-9]/g, "");
  return (
    <button type="button" role="switch" aria-checked={oscuro} aria-label="Tema oscuro"
      title={oscuro ? "Cambiar a tema claro" : "Cambiar a tema oscuro"}
      className={`tema-astro${oscuro ? " tema-astro--noche" : ""}${className ? ` ${className}` : ""}`}
      onClick={() => setTema(oscuro ? "claro" : "oscuro")}>
      <svg className="tema-astro__cielo" viewBox="0 0 72 36" aria-hidden="true">
        {ESTRELLAS.map((e, i) => (
          <circle key={i} className="tema-astro__estrella" cx={e.x} cy={e.y} r={e.r}
            style={{ animationDelay: `${i * 0.45}s`, transitionDelay: `${0.15 + i * 0.05}s` }} />
        ))}
        {/* Las tres cordilleras de los Andes colombianos en capas, un nevado y una palma de cera. */}
        <path className="tema-astro__monte tema-astro__monte--lejos"
          d="M0 25 L6 21.5 L11 23 L17 18 L22 20.5 L28 15.5 L32 17.5 L36 13 L41 18 L46 15.5 L52 19.5 L58 16.5 L64 20 L72 18 L72 36 L0 36 Z" />
        <path className="tema-astro__nieve" d="M33.9 15.1 L36 13 L38.3 15.3 L37.1 14.9 L36.1 15.9 L35.1 14.8 Z" />
        <path className="tema-astro__monte tema-astro__monte--medio"
          d="M0 28.5 L5 25.5 L10 27 L16 22.5 L21 25 L27 21.5 L32 24.5 L38 22 L44 25.5 L50 22.5 L56 26 L62 24 L67 26.5 L72 25 L72 36 L0 36 Z" />
        <path className="tema-astro__monte tema-astro__monte--cerca"
          d="M0 32 C7 29.5 13 31.5 20 30.5 C27 29.2 33 31.6 41 30.4 C49 29.2 57 31.8 64 30.6 C67 30.1 70 30.4 72 30.8 L72 36 L0 36 Z" />
        <g className="tema-astro__palma">
          <path d="M57.3 30.4 C57.6 27.5 57.7 25 57.5 22.4" />
          <path d="M57.5 22.4 C56 21.6 54.6 21.9 53.6 22.8 M57.5 22.4 C59 21.5 60.5 21.9 61.4 22.9 M57.5 22.4 C56.7 21 55.6 20.3 54.4 20.4 M57.5 22.4 C58.4 21 59.6 20.4 60.7 20.6 M57.5 22.4 C57.4 21 57.6 19.9 58.2 19.3" />
        </g>
      </svg>
      <span className="tema-astro__ficha" aria-hidden="true">
        <svg viewBox="0 0 32 32">
          <defs>
            <mask id={mascara}>
              <rect width="32" height="32" fill="#fff" />
              <circle className="tema-astro__sombra" cx="16" cy="16" r="7.4" fill="#000" />
            </mask>
          </defs>
          <g className="tema-astro__rayos">
            {RAYOS.map((r, i) => <circle key={i} {...r} style={{ transitionDelay: `${i * 18}ms` }} />)}
          </g>
          <circle className="tema-astro__disco" cx="16" cy="16" r="7.4" mask={`url(#${mascara})`} />
          <g className="tema-astro__crateres">
            <circle cx="12.6" cy="13.4" r="1" /><circle cx="11.8" cy="18.6" r="0.75" /><circle cx="14.6" cy="20.6" r="0.55" />
          </g>
        </svg>
      </span>
    </button>
  );
}
