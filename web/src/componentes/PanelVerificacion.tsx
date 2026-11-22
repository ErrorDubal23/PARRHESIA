import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, cifra, INDICADOR, periodo, UNIDAD } from "../api";
import type { Afirmacion, Guia, TextoVerificado } from "../tipos";
import { GraficaSerie, type Punto } from "./GraficaSerie";
import * as I from "./Iconos";
import { CONCLUSIONES, Glifo } from "./Veredicto";

const ROL: Record<string, string> = { citada: "Dato citado", contraste: "Dato al que corresponde la cifra", completa: "Dato de comparación" };
const RESULTADO: Record<string, string> = { sin_brecha: "Sin brecha", con_brecha: "Con brecha", no_aplica: "No aplica" };

function restarMeses(p: string, n: number) {
  if (p.length === 4) return String(Number(p) - Math.ceil(n / 12));
  const total = Number(p.slice(0, 4)) * 12 + Number(p.slice(5, 7)) - 1 - n;
  return `${Math.floor(total / 12)}-${String((total % 12) + 1).padStart(2, "0")}`;
}

function Afirmacion({ a }: { a: Afirmacion }) {
  const v = a.verificacion;
  const [serie, setSerie] = useState<Punto[] | null>(null);
  const citada = v?.evidencia.find((e) => e.rol === "citada");
  const unidad = UNIDAD[a.indicador ?? ""] ?? "";

  useEffect(() => {
    if (!v?.serie || !citada) return;
    const desde = restarMeses(citada.periodo, 18);
    api<{ valores: Punto[] }>(`/oficial/v1/series/${v.serie}?desde=${desde}&hasta=${citada.periodo}`)
      .then((r) => setSerie(r.valores)).catch(() => setSerie([]));
  }, [v?.serie, citada?.periodo]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <section className="panel-verificacion">
      <blockquote className="panel-verificacion__cita">«{a.texto_citado}»</blockquote>
      <dl className="panel-verificacion__lectura">
        <div><dt>Indicador</dt><dd>{INDICADOR[a.indicador ?? ""] ?? "—"}</dd></div>
        <div><dt>Periodo citado</dt><dd>{periodo(a.periodo)}</dd></div>
        <div><dt>Cifra dicha</dt><dd className="cifra">{cifra(a.valor_dicho)}{unidad}</dd></div>
      </dl>
      {a.consenso === "coinciden" && (
        <p className="panel-verificacion__consenso tenue">Dos lecturas automáticas independientes, de proveedores distintos, coinciden.</p>
      )}

      {!v ? (
        <div className="veredicto veredicto--revision veredicto--grande">
          <Glifo tipo={a.estado === "requiere_revision" ? "revision" : "pendiente"} />
          <strong>{a.estado === "requiere_revision" ? "En revisión" : "Verificando"}</strong>
          <span className="veredicto__texto">
            {a.consenso === "difieren"
              ? "Las dos lecturas automáticas no coinciden. Una persona la revisará antes de mostrar una conclusión."
              : "Uniendo la cifra a su dato oficial…"}
          </span>
        </div>
      ) : null}
      {!v && a.estado === "requiere_revision" && a.guia && <GuiaLectura guia={a.guia} />}
      {!v ? null : (
        <>
          <div className={`veredicto veredicto--${v.conclusion} veredicto--grande`}>
            <Glifo tipo={v.conclusion} tamano={22} />
            <strong>{CONCLUSIONES[v.conclusion].titulo}</strong>
            <span className="veredicto__texto">{CONCLUSIONES[v.conclusion].frase}</span>
          </div>
          {v.explicacion && <p className="panel-verificacion__explicacion">{v.explicacion}</p>}
          {a.guia && <GuiaLectura guia={a.guia} />}

          {serie && serie.length > 1 && citada && (
            <GraficaSerie puntos={serie} unidad={unidad} titulo={`${citada.nombre_serie} (${citada.fuente})`}
              resaltados={v.evidencia.map((e) => e.periodo)}
              decimales={Math.min(2, Math.max(unidad ? 1 : 0, (a.valor_dicho?.split(".")[1] ?? "").length))} />
          )}

          {v.evidencia.length > 0 && (
            <div className="evidencia">
              <h3 className="subtitulo">Evidencia oficial</h3>
              <ul>
                {v.evidencia.map((e) => (
                  <li key={e.observacion_id}>
                    <span className="sello sello--tinta">{ROL[e.rol]}</span>
                    <span className="evidencia__dato">
                      <strong className="cifra" title={`Valor exacto publicado: ${e.valor}`}>{cifra(e.valor)}{unidad}</strong>
                      <span>{periodo(e.periodo)} · {e.nombre_serie} · {e.fuente}</span>
                    </span>
                    <Link to={`/datos/dato/${e.observacion_id}`} className="enlace-suave">De dónde sale <I.Enlace width={14} /></Link>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="pruebas">
            <h3 className="subtitulo">Pruebas de contexto</h3>
            <ul>
              {v.pruebas.map((p) => (
                <li key={p.codigo} className={`prueba prueba--${p.resultado}`}>
                  <span className="prueba__marca" aria-hidden="true" />
                  <span><strong>{p.nombre}</strong>{p.detalle && <small className="tenue"> · {p.detalle}</small>}</span>
                  <span className="prueba__resultado">{RESULTADO[p.resultado]}</span>
                </li>
              ))}
            </ul>
          </div>
          <p className="tenue panel-verificacion__version">Verificación versión {v.version} · {new Date(v.creado_en).toLocaleDateString("es-CO", { day: "numeric", month: "long", year: "numeric" })}</p>
        </>
      )}
    </section>
  );
}

export function PanelVerificacion({ tipo, id }: { tipo: "publicacion" | "declaracion" | "declaracion_reportada" | "fragmento_enlace"; id: string }) {
  const [datos, setDatos] = useState<TextoVerificado | null>(null);
  useEffect(() => {
    let vivo = true;
    const traer = () => api<TextoVerificado>(`/verificacion/v1/textos/${tipo}/${id}`).then((r) => {
      if (!vivo) return;
      setDatos(r);
      if (r.estado === "pendiente") setTimeout(traer, 4000);
    }).catch(() => vivo && setDatos({ estado: "pendiente", afirmaciones: [] }));
    traer();
    return () => { vivo = false; };
  }, [tipo, id]);

  if (!datos) return <span className="cargando"><i /><i /><i /></span>;
  if (datos.estado === "sin_cifras") return <p className="sello">Opinión · sin cifras de los indicadores</p>;
  if (datos.afirmaciones.length === 0) {
    return <div className="veredicto veredicto--pendiente"><Glifo tipo="pendiente" /><span>Leyendo las cifras del texto…</span></div>;
  }
  return <div className="paneles">{datos.afirmaciones.map((a) => <Afirmacion key={a.id} a={a} />)}</div>;
}

/** Para entenderlo · Compruébalo tú · Otros medios. Las reglas deciden el contenido; la IA, si la hay, solo lo redacta. */
function GuiaLectura({ guia }: { guia: Guia }) {
  const especificos = guia.consejos.filter((c) => c.origen !== "general");
  const general = guia.consejos.find((c) => c.origen === "general");
  const pasos = [...new Set([...especificos.flatMap((c) => c.pasos), ...(especificos.length ? [] : general?.pasos ?? [])])];
  return (
    <section className="guia" aria-label="Guía de lectura">
      <div className="guia__bloque">
        <h3 className="guia__titulo"><I.Util width={16} /> Para entenderlo</h3>
        {guia.redaccion ? (
          <>
            <p>{guia.redaccion}</p>
            <small className="tenue guia__nota">Redactado con IA a partir de reglas fijas y revisado por un segundo modelo de otro proveedor: no toma partido ni agrega datos.</small>
          </>
        ) : (
          especificos.map((c) => <p key={c.origen + c.codigo}>{c.para_entenderlo}</p>)
        )}
        {!guia.redaccion && especificos.length === 0 && general && <p>{general.para_entenderlo}</p>}
      </div>
      {(pasos.length > 0 || guia.fuentes.length > 0) && (
        <div className="guia__bloque">
          <h3 className="guia__titulo"><I.Buscar width={16} /> Compruébalo tú</h3>
          {pasos.length > 0 && <ol className="guia__pasos">{pasos.map((p) => <li key={p}>{p}</li>)}</ol>}
          {guia.fuentes.map((f) => (
            <a key={f.url} href={f.url} target="_blank" rel="noreferrer noopener" className="guia__fuente">
              <strong>{f.nombre} <I.Enlace width={13} /></strong>
              <span>{f.como_leer}</span>
            </a>
          ))}
        </div>
      )}
      {guia.otros_medios.length > 0 && (
        <div className="guia__bloque">
          <h3 className="guia__titulo"><I.Temas width={16} /> Otros medios revisaron algo parecido</h3>
          <ul className="guia__medios">
            {guia.otros_medios.map((m) => (
              <li key={m.url}><a href={m.url} target="_blank" rel="noreferrer noopener"><strong>{m.medio}</strong> · {m.titulo}</a></li>
            ))}
          </ul>
          <small className="tenue guia__nota">Enlaces a lo que publicaron; Parrhesia no copia sus calificaciones.</small>
        </div>
      )}
    </section>
  );
}
