// Gráfica de línea de una serie oficial. Solo recibe datos reales de la API de datos oficiales:
// si no hay datos, no se dibuja nada (nunca una gráfica de adorno).
import { cifra, periodo } from "../api";

export interface Punto { periodo: string; valor: string | null }

/** Decimales del eje: sin decimales en conteos y pesos grandes; uno en porcentajes y tasas. */
const precisionEje = (valores: number[]) => (Math.max(...valores.map(Math.abs)) >= 100 ? 0 : 1);

export function GraficaSerie({ puntos, resaltados = [], unidad = "", alto = 220, titulo, decimales }: {
  puntos: Punto[];
  resaltados?: string[];
  unidad?: string;
  alto?: number;
  titulo: string;
  decimales?: number;
}) {
  // Porcentajes con un decimal (como se citan y como los explica la verificación); conteos y pesos sin decimales.
  const precision = decimales ?? (unidad.includes("%") ? 1 : 0);
  const validos = puntos.filter((p) => p.valor !== null);
  if (validos.length < 2) return <p className="tenue">No hay suficientes datos oficiales para dibujar la serie.</p>;
  const ancho = 640;
  const valores = validos.map((p) => Number(p.valor));
  const largo = Math.max(...valores.map((v) => (cifra(String(v), precisionEje(valores)) + unidad).length));
  const m = { arriba: 24, derecha: 18, abajo: 30, izquierda: 16 + largo * 7.2 };
  let min = Math.min(...valores);
  let max = Math.max(...valores);
  const margen = (max - min || Math.abs(max) || 1) * 0.12;
  min -= margen;
  max += margen;
  const x = (i: number) => m.izquierda + (i / (validos.length - 1)) * (ancho - m.izquierda - m.derecha);
  const y = (v: number) => m.arriba + (1 - (v - min) / (max - min)) * (alto - m.arriba - m.abajo);
  const linea = validos.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(Number(p.valor)).toFixed(1)}`).join(" ");
  const area = `${linea} L${x(validos.length - 1)} ${alto - m.abajo} L${x(0)} ${alto - m.abajo} Z`;
  const marcas = [min + margen, (min + max) / 2, max - margen];
  const etiquetasX = [0, Math.floor((validos.length - 1) / 2), validos.length - 1];

  return (
    <figure className="grafica">
      <svg viewBox={`0 0 ${ancho} ${alto}`} role="img" aria-label={`${titulo}: ${validos.length} periodos, de ${periodo(validos[0].periodo)} a ${periodo(validos.at(-1)!.periodo)}`}>
        <defs>
          <linearGradient id="relleno-grafica" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="var(--arena)" stopOpacity="0.45" />
            <stop offset="1" stopColor="var(--arena)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {marcas.map((v) => (
          <g key={v}>
            <line x1={m.izquierda} x2={ancho - m.derecha} y1={y(v)} y2={y(v)} className="grafica__guia" />
            <text x={m.izquierda - 8} y={y(v) + 4} textAnchor="end" className="grafica__eje">{cifra(String(v), precisionEje(valores))}{unidad}</text>
          </g>
        ))}
        {etiquetasX.map((i) => (
          <text key={i} x={x(i)} y={alto - 8} textAnchor={i === 0 ? "start" : i === validos.length - 1 ? "end" : "middle"}
            className="grafica__eje">{periodo(validos[i].periodo, true)}</text>
        ))}
        <path d={area} fill="url(#relleno-grafica)" />
        <path d={linea} className="grafica__linea" />
        {validos.map((p, i) => resaltados.includes(p.periodo) && (
          <g key={p.periodo}>
            <line x1={x(i)} x2={x(i)} y1={m.arriba} y2={alto - m.abajo} className="grafica__marca" />
            <circle cx={x(i)} cy={y(Number(p.valor))} r="5" className="grafica__punto" />
            <text x={x(i) > ancho - 70 ? x(i) + 6 : x(i)} y={y(Number(p.valor)) - 11} textAnchor={x(i) > ancho - 70 ? "end" : "middle"} className="grafica__valor">{cifra(p.valor, precision)}{unidad}</text>
          </g>
        ))}
      </svg>
      <figcaption className="tenue">{titulo} · {periodo(validos[0].periodo)} a {periodo(validos.at(-1)!.periodo)}</figcaption>
    </figure>
  );
}
