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
  dibujarIslas(c);
}

// San Andrés, Providencia y Santa Catalina: a unos 700 km de la costa, fuera del plano del relieve. Como en los
// mapas oficiales, van en un recuadro aparte (no a escala de distancia entre grupos), con el mismo estilo de puntos.
// Contornos reales de OpenStreetMap (© colaboradores de OpenStreetMap, ODbL), consultados el 23 nov 2026.
// Providencia y Santa Catalina comparten centro: conservan su posición real entre ellas.
const ISLAS = [
  { centro: [78, 42], contornos: [[[-81.3963, 13.3393], [-81.393, 13.3375], [-81.3915, 13.3336], [-81.391, 13.33], [-81.3927, 13.3265], [-81.3904, 13.3215], [-81.3869, 13.3203], [-81.3815, 13.3237], [-81.3752, 13.3247], [-81.3685, 13.3322], [-81.3593, 13.3343], [-81.3553, 13.3436], [-81.3566, 13.3533], [-81.35, 13.3566], [-81.3492, 13.3595], [-81.35, 13.3619], [-81.354, 13.3607], [-81.3555, 13.3655], [-81.357, 13.3683], [-81.3581, 13.3683], [-81.357, 13.3702], [-81.3582, 13.3714], [-81.3548, 13.3753], [-81.3545, 13.3775], [-81.3616, 13.379], [-81.3644, 13.3858], [-81.3666, 13.3856], [-81.3671, 13.383], [-81.3705, 13.3809], [-81.3696, 13.3804], [-81.3699, 13.3744], [-81.3725, 13.3707], [-81.3764, 13.3695], [-81.3792, 13.3719], [-81.3815, 13.3719], [-81.385, 13.3703], [-81.3884, 13.3667], [-81.3923, 13.359], [-81.3938, 13.3536], [-81.3931, 13.3477], [-81.3963, 13.3393]],
    [[-81.3809, 13.3859], [-81.3765, 13.3815], [-81.3707, 13.3825], [-81.3685, 13.3864], [-81.3713, 13.387], [-81.3715, 13.3901], [-81.3692, 13.3939], [-81.3765, 13.3934], [-81.3796, 13.3914], [-81.3809, 13.3859]]] },
  { centro: [42, 74], contornos: [[[-81.7357, 12.5308], [-81.7342, 12.5279], [-81.7275, 12.5259], [-81.73, 12.5249], [-81.7287, 12.5229], [-81.7302, 12.5115], [-81.7298, 12.5046], [-81.7346, 12.4972], [-81.7355, 12.4921], [-81.7331, 12.4825], [-81.73, 12.4803], [-81.7263, 12.483], [-81.7156, 12.5046], [-81.7132, 12.5231], [-81.708, 12.5288], [-81.7065, 12.5323], [-81.7077, 12.5408], [-81.7035, 12.5438], [-81.7046, 12.5497], [-81.7034, 12.5611], [-81.7071, 12.5612], [-81.7074, 12.5631], [-81.7003, 12.5644], [-81.7001, 12.5664], [-81.7029, 12.5669], [-81.7039, 12.5688], [-81.7054, 12.5677], [-81.7076, 12.5699], [-81.7071, 12.5721], [-81.704, 12.5705], [-81.7065, 12.5699], [-81.7039, 12.5691], [-81.7023, 12.5679], [-81.6999, 12.57], [-81.7004, 12.572], [-81.7034, 12.5743], [-81.7029, 12.5754], [-81.6964, 12.5798], [-81.6925, 12.5805], [-81.6896, 12.5795], [-81.6873, 12.5814], [-81.6893, 12.5837], [-81.6987, 12.5873], [-81.7004, 12.5897], [-81.6994, 12.5904], [-81.7039, 12.5949], [-81.7093, 12.5927], [-81.7226, 12.5782], [-81.7231, 12.5671], [-81.7311, 12.5585], [-81.7325, 12.5549], [-81.7296, 12.5473], [-81.7317, 12.5449], [-81.7357, 12.5308]]] },
];
const ESCALA_ISLAS = 300; // px del plano por grado (unas 7,5 veces la del mapa)

function dibujarIslas(c: CanvasRenderingContext2D) {
  c.globalAlpha = 0.35;
  c.strokeStyle = "#c8b79e";
  c.lineWidth = 0.6;
  c.strokeRect(10, 10, 104, 112);
  for (const grupo of ISLAS) {
    const todos = grupo.contornos.flat();
    const lon0 = (Math.min(...todos.map((q) => q[0])) + Math.max(...todos.map((q) => q[0]))) / 2;
    const lat0 = (Math.min(...todos.map((q) => q[1])) + Math.max(...todos.map((q) => q[1]))) / 2;
    for (const contorno of grupo.contornos) {
    const poli = contorno.map(([lon, lat]) => [grupo.centro[0] + (lon - lon0) * ESCALA_ISLAS, grupo.centro[1] - (lat - lat0) * ESCALA_ISLAS]);
    const xs = poli.map((q) => q[0]), ys = poli.map((q) => q[1]);
    let k = 0;
    for (let y = Math.min(...ys); y <= Math.max(...ys); y += 1.5) {
      for (let x = Math.min(...xs); x <= Math.max(...xs); x += 1.5) {
        // Desorden leve y fijo (sin azar) para que no se vea una cuadrícula, como los puntos del relieve.
        k++;
        const jx = x + Math.sin(k * 12.9898) * 0.5, jy = y + Math.cos(k * 78.233) * 0.5;
        if (!dentro(jx, jy, poli)) continue;
        c.globalAlpha = 0.35 + 0.35 * Math.abs(Math.sin(k * 3.7));
        c.fillStyle = "#e4d8c4";
        c.beginPath();
        c.arc(jx, jy, 0.75, 0, Math.PI * 2);
        c.fill();
      }
    }
    }
  }
  c.globalAlpha = 0.6;
  c.fillStyle = "#c8b79e";
  c.font = "600 8px system-ui, sans-serif";
  c.fillText("San Andrés, Providencia", 15, 106);
  c.fillText("y Santa Catalina", 15, 116);
  c.globalAlpha = 1;
}

function dentro(x: number, y: number, poli: number[][]) {
  let adentro = false;
  for (let i = 0, j = poli.length - 1; i < poli.length; j = i++) {
    const [xi, yi] = poli[i], [xj, yj] = poli[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) adentro = !adentro;
  }
  return adentro;
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
      <p className="vivo__credito">Relieve: NOAA ETOPO1 · Contorno: Natural Earth · Islas: © OpenStreetMap</p>
    </section>
  );
}
