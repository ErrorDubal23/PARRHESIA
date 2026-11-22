// Ficha de un dato oficial: la cifra protagonista con su unidad, los valores publicados del periodo
// anterior y de un año antes (sin calcular diferencias: la fuente no las publica), una línea con los
// últimos valores reales, la fuente, la fecha de actualización y los avisos (provisional, notas).
import { Link } from "react-router-dom";
import { cifra, INDICADOR, nombreCanal, periodo, UNIDAD } from "../api";

export interface PuntoResumen { periodo: string; valor: string }
export interface Resumen {
  ultimo: PuntoResumen & { observacion_id: string; provisional: boolean; actualizado_fuente: string | null; descargado_en: string | null };
  anterior: PuntoResumen | null;
  hace_un_anio: PuntoResumen | null;
  notas_vigentes: { tipo: string; estado: string }[];
  recientes: PuntoResumen[];
}
export interface SerieResumida {
  codigo: string; nombre: string; indicador: string; variante: string; unidad: string; frecuencia: string;
  productor: string; canal: string; resumen: Resumen | null;
  otros_canales?: { codigo: string; canal: string }[];   // la misma serie, leída por otro canal (contraste)
}

export const VARIANTE: Record<string, string> = {
  annual: "anual", monthly: "mensual", year_to_date: "año corrido", monthly_rate: "tasa mensual",
  nominal: "valor nominal", monthly_count: "víctimas por mes",
};

const fecha = (iso: string) =>
  new Date(iso.length === 10 ? `${iso}T12:00:00` : iso).toLocaleDateString("es-CO", { day: "numeric", month: "long", year: "numeric" });

/** El valor como se publicó, con hasta dos decimales y la unidad pegada si es un porcentaje. */
function Valor({ valor, indicador, clase }: { valor: string; indicador: string; clase?: string }) {
  const sufijo = UNIDAD[indicador];
  return (
    <span className={clase} title={`Valor exacto publicado: ${valor}`}>
      {cifra(valor, 2)}{sufijo && <small>{sufijo.trim()}</small>}
    </span>
  );
}

/** Solo la dirección (mayor, menor, igual), nunca la diferencia. */
function Direccion({ ahora, antes }: { ahora: string; antes: string }) {
  const a = Number(ahora), b = Number(antes);
  const tipo = a > b ? "mayor" : a < b ? "menor" : "igual";
  const texto = { mayor: "El último valor es mayor", menor: "El último valor es menor", igual: "El último valor es igual" }[tipo];
  return (
    <svg className={`direccion direccion--${tipo}`} viewBox="0 0 12 12" width="12" height="12" role="img" aria-label={texto}>
      <title>{texto}</title>
      {tipo === "igual" ? <path d="M2 4.5h8M2 7.5h8" /> : <path d={tipo === "mayor" ? "M6 2.5 10.5 9h-9z" : "M6 9.5 1.5 3h9z"} />}
    </svg>
  );
}

/** Línea de los últimos valores reales; el último punto marcado. */
export function Linea({ puntos }: { puntos: PuntoResumen[] }) {
  const v = puntos.map((p) => Number(p.valor));
  if (v.length < 2) return null;
  const ancho = 220, alto = 52, m = 5;
  const min = Math.min(...v), max = Math.max(...v);
  const x = (i: number) => m + (i / (v.length - 1)) * (ancho - 2 * m);
  const y = (n: number) => m + (1 - (n - min) / (max - min || 1)) * (alto - 2 * m);
  const d = v.map((n, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(n).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${ancho} ${alto}`} className="linea-dato" aria-hidden="true">
      <path d={`${d} L${x(v.length - 1)} ${alto} L${x(0)} ${alto} Z`} className="linea-dato__area" />
      <path d={d} className="linea-dato__trazo" />
      <circle cx={x(v.length - 1)} cy={y(v.at(-1)!)} r="3.4" className="linea-dato__ultimo" />
    </svg>
  );
}

export function FichaDato({ serie, cabecera = false }: { serie: SerieResumida; cabecera?: boolean }) {
  const r = serie.resumen;
  const via = serie.canal !== serie.productor ? ` · vía ${nombreCanal(serie.canal)}` : "";
  const contenido = (
    <>
      <div className="ficha-dato__titulo">
        <strong>{INDICADOR[serie.indicador] ?? serie.indicador}</strong>
        <span>{VARIANTE[serie.variante] ?? serie.variante}</span>
      </div>
      {!r ? <p className="tenue">Aún no hay datos aceptados de esta serie.</p> : (
        <>
          <div className="ficha-dato__principal">
            <Valor valor={r.ultimo.valor} indicador={serie.indicador} clase="ficha-dato__cifra cifra-destacada" />
            <span className="ficha-dato__periodo">
              {periodo(r.ultimo.periodo)}
              {!UNIDAD[serie.indicador] && <small> · {serie.unidad.toLowerCase()}</small>}
            </span>
          </div>
          {(r.anterior || r.hace_un_anio) && (
            <dl className="ficha-dato__comparacion">
              {r.anterior && (
                <div>
                  <dt>Periodo anterior</dt>
                  <dd><Valor valor={r.anterior.valor} indicador={serie.indicador} clase="cifra" /> <Direccion ahora={r.ultimo.valor} antes={r.anterior.valor} /></dd>
                  <dd className="ficha-dato__cuando">{periodo(r.anterior.periodo)}</dd>
                </div>
              )}
              {r.hace_un_anio && (
                <div>
                  <dt>Un año antes</dt>
                  <dd><Valor valor={r.hace_un_anio.valor} indicador={serie.indicador} clase="cifra" /> <Direccion ahora={r.ultimo.valor} antes={r.hace_un_anio.valor} /></dd>
                  <dd className="ficha-dato__cuando">{periodo(r.hace_un_anio.periodo)}</dd>
                </div>
              )}
            </dl>
          )}
          {!cabecera && <Linea puntos={r.recientes} />}
          <p className="ficha-dato__fuente">
            <strong>{serie.productor}</strong>{via}
            {serie.otros_canales && serie.otros_canales.length > 0 && (
              <><br />También publicada vía {serie.otros_canales.map((o) => nombreCanal(o.canal)).join(", ")}: se usa para contrastar.</>
            )}
            <br />
            {r.ultimo.actualizado_fuente ? `Actualizado por la fuente el ${fecha(r.ultimo.actualizado_fuente)}`
              : r.ultimo.descargado_en ? `Consultado el ${fecha(r.ultimo.descargado_en)}` : ""}
          </p>
          {(r.ultimo.provisional || r.notas_vigentes.length > 0) && (
            <p className="ficha-dato__avisos">
              {r.ultimo.provisional && <span title="Puede cambiar hasta abril del año siguiente">Dato provisional</span>}
              {r.notas_vigentes.length > 0 && (
                <span>{r.notas_vigentes.length === 1 ? "1 nota de la fuente" : `${r.notas_vigentes.length} notas de la fuente`} para este periodo</span>
              )}
            </p>
          )}
        </>
      )}
    </>
  );
  if (cabecera) return <section className="ficha-dato ficha-dato--cabecera tarjeta">{contenido}</section>;
  return <Link to={`/datos/${serie.codigo}`} className="ficha-dato tarjeta">{contenido}</Link>;
}
