// Panel de identidad de la pantalla de acceso: el relieve real de Colombia en puntillismo (NOAA ETOPO1
// y Natural Earth, dominio público; ver web/scripts/generar_relieve.py), sobre un plano con
// perspectiva, y pequeñas mariposas con la forma del logo que lo recorren. Sin datos oficiales: las
// cifras viven dentro de la app. Sin colores de ningún partido.
import { useEffect, useId, useRef } from "react";
import { ALA, ALTO, ANCHO, ESPEJO } from "../marca";
import { Logo } from "./Iconos";

// Tamaño de diseño del plano (unidades del archivo de relieve: 40 por grado).
const PLANO = { ancho: 496, alto: 680 };

// Trayectorias de vuelo en coordenadas del plano: curvas suaves y cerradas alrededor del país.
const VUELOS = [
  { d: "M70 520 C20 380 120 210 230 150 S450 170 430 330 S300 560 170 600 S100 580 70 520 Z", dur: 38, retraso: 0, tam: 26 },
  { d: "M300 90 C380 60 470 160 420 250 S260 330 240 230 S220 120 300 90 Z", dur: 27, retraso: -9, tam: 20 },
  { d: "M150 300 C210 250 300 300 310 380 S250 500 180 470 S90 350 150 300 Z", dur: 31, retraso: -17, tam: 17 },
  { d: "M380 620 C300 660 230 560 290 500 S440 430 470 520 S450 590 380 620 Z", dur: 34, retraso: -4, tam: 22 },
  { d: "M40 260 C60 160 200 60 300 40 S200 180 160 240 S30 360 40 260 Z", dur: 42, retraso: -25, tam: 16 },
];

interface Relieve { ancho: number; alto: number; puntos: number[] }

function dibujar(lienzo: HTMLCanvasElement, relieve: Relieve) {
  const escala = Math.min(2.5, (window.devicePixelRatio || 1) * (lienzo.clientWidth / PLANO.ancho));
  if (!escala) return;
  lienzo.width = Math.round(PLANO.ancho * escala);
  lienzo.height = Math.round(PLANO.alto * escala);
  const c = lienzo.getContext("2d");
  if (!c) return;
  c.scale(escala, escala);
  const p = relieve.puntos;
  for (let i = 0; i < p.length; i += 4) {
    const nivel = p[i + 2], luz = p[i + 3] / 15;
    // Bajo: puntos pequeños y tenues; alto: más grandes y con luz de crema.
    c.globalAlpha = 0.16 + 0.84 * luz ** 1.4;
    c.fillStyle = nivel > 9 ? "#f6f0e6" : nivel > 4 ? "#e4d8c4" : "#c8b79e";
    c.beginPath();
    c.arc(p[i], p[i + 1], 0.5 + nivel * 0.085, 0, Math.PI * 2);
    c.fill();
  }
}

function Mariposa({ id }: { id: string }) {
  return (
    <svg className="mariposa__cuerpo" viewBox={`0 0 ${ANCHO} ${ALTO}`} aria-hidden="true">
      <g className="mariposa__ala"><use href={`#${id}`} /></g>
      <g className="mariposa__ala"><use href={`#${id}`} transform={ESPEJO} /></g>
    </svg>
  );
}

export function PanelVivo() {
  const panel = useRef<HTMLElement>(null);
  const lienzo = useRef<HTMLCanvasElement>(null);
  const idAla = useId();

  // El relieve se carga aparte (su propio archivo), solo en esta pantalla.
  useEffect(() => {
    let vivo = true;
    let relieve: Relieve | null = null;
    const repintar = () => { if (relieve && lienzo.current) dibujar(lienzo.current, relieve); };
    import("../datos/relieve_colombia.json").then((m) => {
      if (!vivo) return;
      relieve = m.default as Relieve;
      repintar();
    });
    const observador = new ResizeObserver(repintar);
    if (lienzo.current) observador.observe(lienzo.current);
    return () => { vivo = false; observador.disconnect(); };
  }, []);

  // Paralaje leve con el puntero (el plano se inclina unos grados); quieto si se pide menos movimiento.
  useEffect(() => {
    const el = panel.current;
    if (!el || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let cuadro = 0;
    const mover = (e: PointerEvent) => {
      cancelAnimationFrame(cuadro);
      cuadro = requestAnimationFrame(() => {
        const r = el.getBoundingClientRect();
        el.style.setProperty("--px", ((e.clientX - r.left) / r.width - 0.5).toFixed(3));
        el.style.setProperty("--py", ((e.clientY - r.top) / r.height - 0.5).toFixed(3));
      });
    };
    el.addEventListener("pointermove", mover);
    return () => { el.removeEventListener("pointermove", mover); cancelAnimationFrame(cuadro); };
  }, []);

  return (
    <section className="vivo" ref={panel} aria-hidden="true">
      <svg width="0" height="0" style={{ position: "absolute" }}><defs><path id={idAla} d={ALA} /></defs></svg>
      <div className="vivo__escena">
        <div className="vivo__plano">
          <canvas ref={lienzo} className="vivo__relieve" />
          {VUELOS.map((v, i) => (
            <span key={i} className="mariposa" style={{
              offsetPath: `path("${v.d}")`, width: v.tam, height: (v.tam * ALTO) / ANCHO,
              animationDuration: `${v.dur}s`, animationDelay: `${v.retraso}s`,
              ["--aleteo" as string]: `${0.62 + i * 0.07}s`, ["--desfase" as string]: `${i * -0.13}s`,
            }}>
              <Mariposa id={idAla} />
            </span>
          ))}
        </div>
      </div>

      <div className="vivo__texto">
        <span className="vivo__logo"><Logo tamano={84} aleteo="siempre" /></span>
        <p className="vivo__firma">Parrhesia · Colombia</p>
        <h2 className="vivo__lema">La palabra es tuya.<br /><em>El dato, de todos.</em></h2>
        <p className="vivo__bajada">Una red para opinar con libertad, donde cada cifra pública se lee junto a su fuente oficial.</p>
      </div>
      <p className="vivo__credito">Relieve: NOAA ETOPO1 · Contorno: Natural Earth</p>
    </section>
  );
}
