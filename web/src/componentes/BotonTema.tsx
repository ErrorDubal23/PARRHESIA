import { useEffect, useState } from "react";
import { Logo } from "./Iconos";

// Interruptor de tema con la identidad de Parrhesia: una ficha con el logo se desliza; de día las alas
// están abiertas junto a un sol de puntos, de noche se pliegan junto a tres estrellas (los puntos
// remiten al puntillismo del relieve). La preferencia se guarda y se comparte entre instancias.

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

// Sol: ocho puntos en anillo y uno al centro. Estrellas: tres puntos de distinto tamaño.
const SOL = Array.from({ length: 8 }, (_, i) => {
  const a = (i * Math.PI) / 4;
  return { cx: 8 + Math.cos(a) * 5.4, cy: 8 + Math.sin(a) * 5.4, r: 1.05 };
}).concat({ cx: 8, cy: 8, r: 2.3 });
const ESTRELLAS = [{ cx: 4, cy: 5, r: 1.3 }, { cx: 11.5, cy: 3.5, r: 0.85 }, { cx: 9, cy: 11.5, r: 1.6 }];

export function BotonTema({ className = "" }: { className?: string }) {
  const [tema, setTema] = useTema();
  const oscuro = tema === "oscuro";
  return (
    <button type="button" role="switch" aria-checked={oscuro} aria-label="Tema oscuro"
      title={oscuro ? "Cambiar a tema claro" : "Cambiar a tema oscuro"}
      className={`tema-alas${oscuro ? " tema-alas--noche" : ""}${className ? ` ${className}` : ""}`}
      onClick={() => setTema(oscuro ? "claro" : "oscuro")}>
      <svg className="tema-alas__cielo tema-alas__cielo--dia" viewBox="0 0 16 16" aria-hidden="true">
        {SOL.map((p, i) => <circle key={i} {...p} style={{ transitionDelay: `${i * 25}ms` }} />)}
      </svg>
      <svg className="tema-alas__cielo tema-alas__cielo--noche" viewBox="0 0 16 16" aria-hidden="true">
        {ESTRELLAS.map((p, i) => <circle key={i} {...p} style={{ transitionDelay: `${i * 60}ms` }} />)}
      </svg>
      <span className="tema-alas__ficha" aria-hidden="true"><Logo tamano={17} /></span>
    </button>
  );
}
