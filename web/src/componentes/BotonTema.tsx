import { useEffect, useId, useState } from "react";

// Interruptor de tema: un recuadro con un cielo. De día, un sol dorado con rayos de puntos (el puntillismo del
// relieve de Colombia de la pantalla de acceso) sobre un horizonte de puntos; de noche, el astro se desliza a
// la derecha, los rayos se recogen, una sombra lo convierte en luna creciente y aparecen estrellas que titilan.
// La preferencia se guarda y se comparte entre pestañas.

type Tema = "claro" | "oscuro";
const EVENTO = "tema-cambiado";

const actual = (): Tema => (document.documentElement.dataset.tema === "oscuro" ? "oscuro" : "claro");

function fijar(tema: Tema) {
  document.documentElement.dataset.tema = tema;
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
// Estrellas del cielo nocturno y horizonte de puntos (plano de 72 × 36).
const ESTRELLAS = [{ x: 9, y: 9, r: 1.1 }, { x: 18, y: 5, r: 0.7 }, { x: 14, y: 17, r: 0.8 }, { x: 25, y: 12, r: 1.2 },
  { x: 6, y: 22, r: 0.6 }, { x: 30, y: 6, r: 0.6 }];
const HORIZONTE = Array.from({ length: 22 }, (_, i) => {
  const x = 3 + i * 3.1;
  return { x, y: 31.5 - Math.sin(i * 0.55) * 1.6 - Math.sin(i * 1.7) * 0.6, r: 0.75 + ((i * 7) % 3) * 0.15 };
});

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
        {HORIZONTE.map((h, i) => <circle key={i} className="tema-astro__horizonte" cx={h.x} cy={h.y} r={h.r} />)}
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
