import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, cifra, INDICADOR, nombreCanal, periodo, UNIDAD } from "../api";
import { FichaDato, type SerieResumida } from "../componentes/FichaDato";
import { GraficaSerie, type Punto } from "../componentes/GraficaSerie";
import * as I from "../componentes/Iconos";
import { useSesion } from "../sesion";
import { comoFallo, MostrarFallo, type Fallo } from "../componentes/NoEncontrado";

// Orden de los grupos: economía y luego seguridad, como en el catálogo.
const ORDEN = ["inflation", "unemployment", "minimum_wage", "public_debt", "homicides", "theft", "extortion", "kidnapping"];

export function Datos() {
  const [series, setSeries] = useState<SerieResumida[] | null>(null);
  useEffect(() => { api<{ series: SerieResumida[] }>("/oficial/v1/series").then((r) => setSeries(r.series)).catch(() => setSeries([])); }, []);
  const grupos = ORDEN.map((ind) => [ind, (series ?? []).filter((s) => s.indicador === ind)] as const).filter(([, l]) => l.length);
  return (
    <>
      <h1 className="titulo-seccion">Datos oficiales</h1>
      <p className="tenue intro">Cifras de fuentes oficiales registradas, tal como se publicaron y con su rastro hasta el archivo original. Cada una pasó siete controles de calidad.</p>
      {series === null && <span className="cargando"><i /><i /><i /></span>}
      {grupos.map(([ind, lista]) => (
        <section key={ind} className="grupo-datos">
          <h2 className="grupo-datos__titulo">{INDICADOR[ind] ?? ind}</h2>
          <div className="fichas-datos">{lista.map((s) => <FichaDato key={s.codigo} serie={s} />)}</div>
        </section>
      ))}
    </>
  );
}

export function SeriePagina() {
  const { codigo } = useParams();
  const [serie, setSerie] = useState<(SerieResumida & { geografia: string; valores: (Punto & { observacion_id: string })[];
    notas: { clave_nota: string; tipo: string; vigente_desde: string | null; vigente_hasta: string | null; estado: string; contenido: { text?: string; texto?: string } }[];
    alertas_abiertas: { alerta_id: string; periodo: string; tipo: string }[] }) | null>(null);
  const [fallo, setFallo] = useState<Fallo | null>(null);
  useEffect(() => { setFallo(null); api<typeof serie>(`/oficial/v1/series/${codigo}`).then(setSerie).catch((e) => setFallo(comoFallo(e))); }, [codigo]);
  if (fallo) return <MostrarFallo fallo={fallo} titulo="Esta serie no está en el catálogo de datos oficiales." />;
  if (!serie) return <span className="cargando"><i /><i /><i /></span>;
  const unidad = UNIDAD[serie.indicador] ?? "";
  const recientes = serie.valores.slice(-60);
  const ultimo = serie.resumen?.ultimo.periodo;
  return (
    <>
      <Link to="/datos" className="volver"><I.Volver width={18} /> Datos oficiales</Link>
      <h1 className="titulo-seccion">{serie.nombre}</h1>
      <p className="tenue">{serie.unidad} · frecuencia {serie.frecuencia} · productor {serie.productor}{serie.canal !== serie.productor ? `, consultado vía ${nombreCanal(serie.canal)}` : ""}</p>
      <div className="serie-cabecera">
        <FichaDato serie={serie} cabecera />
        <section className="tarjeta bloque serie-cabecera__grafica">
          <GraficaSerie puntos={recientes} unidad={unidad} alto={250} titulo="Últimos cinco años" resaltados={ultimo ? [ultimo] : []} decimales={2} />
        </section>
      </div>
      {serie.alertas_abiertas.length > 0 && (
        <p className="aviso">Hay {serie.alertas_abiertas.length} {serie.alertas_abiertas.length === 1 ? "dato en revisión" : "datos en revisión"} en esta serie ({serie.alertas_abiertas.map((a) => periodo(a.periodo)).join(", ")}). Mientras tanto no se usan.</p>
      )}
      {serie.notas.length > 0 && (
        <section className="tarjeta bloque">
          <h2 className="subtitulo">Notas de la serie</h2>
          <ul className="notas">
            {serie.notas.map((n) => (
              <li key={n.clave_nota}>
                <span className="sello">{n.vigente_desde ? `Desde ${periodo(n.vigente_desde)}` : "Toda la serie"}{n.vigente_hasta ? ` hasta ${periodo(n.vigente_hasta)}` : ""}{n.estado !== "confirmed" ? " · por confirmar" : ""}</span>
                <p>{n.contenido.texto ?? n.contenido.text ?? n.tipo}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
      <section className="tarjeta bloque">
        <h2 className="subtitulo">Valores publicados</h2>
        <table className="tabla tabla-cifras">
          <thead><tr><th>Periodo</th><th className="derecha-num">Valor publicado</th><th /></tr></thead>
          <tbody>
            {[...serie.valores].reverse().slice(0, 36).map((v) => (
              <tr key={v.observacion_id}>
                <td>{periodo(v.periodo)}</td>
                <td className="cifra derecha-num" title={`Valor exacto: ${v.valor}`}>{cifra(v.valor, 4)}{unidad}</td>
                <td><Link to={`/datos/dato/${v.observacion_id}`} className="enlace-suave">De dónde sale <I.Enlace width={13} /></Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}

export function DatoPagina() {
  const { id } = useParams();
  const { usuario } = useSesion();
  const [dato, setDato] = useState<{ serie: string; periodo: string; valor: string; estado: string; estado_contraste: string; marcas: string[];
    descarga: { canal: string; descargado_en: string; actualizado_fuente: string | null };
    archivos_originales: { nombre: string; url: string; sha256: string }[];
    contrastes: { fuente: string; nivel: string; periodo_comparado: string; valor_fuente: string | null; valor_serie: string | null; resultado: string }[];
    versiones: { id: string; valor: string; estado: string; creado_en: string }[] } | null>(null);
  const [fallo, setFallo] = useState<Fallo | null>(null);
  useEffect(() => { setFallo(null); api<typeof dato>(`/oficial/v1/observaciones/${id}`).then(setDato).catch((e) => setFallo(comoFallo(e))); }, [id]);
  if (fallo) return <MostrarFallo fallo={fallo} titulo="Este dato no está en el registro oficial." />;
  if (!dato) return <span className="cargando"><i /><i /><i /></span>;
  return (
    <>
      <Link to={`/datos/${dato.serie}`} className="volver"><I.Volver width={18} /> Volver a la serie</Link>
      <p className="sello">De dónde sale este dato</p>
      <h1 className="titulo-seccion"><span className="cifra-destacada">{cifra(dato.valor, 2)}</span> <small className="tenue">· {periodo(dato.periodo)}</small></h1>
      <p className="tenue">Valor exacto publicado: <code className="cifra-exacta">{dato.valor}</code> · {dato.estado === "aceptada" ? "aceptado" : "en cuarentena"}</p>
      <ol className="rastro">
        <li className="tarjeta">
          <strong>Descarga</strong>
          <span>{new Date(dato.descarga.descargado_en).toLocaleString("es-CO")} · vía {nombreCanal(dato.descarga.canal)}</span>
          {dato.descarga.actualizado_fuente && <span className="tenue">Actualizado por la fuente el {new Date(`${dato.descarga.actualizado_fuente}T12:00:00`).toLocaleDateString("es-CO", { day: "numeric", month: "long", year: "numeric" })}</span>}
        </li>
        <li className="tarjeta">
          <strong>Archivos originales</strong>
          {dato.archivos_originales.map((a) => (
            <span key={a.sha256}><a href={a.url} target="_blank" rel="noreferrer" className="marca-texto">{a.nombre}</a>
              <code className="huella" title="Huella SHA-256: si el archivo cambia, la huella cambia">{a.sha256.slice(0, 16)}…</code></span>
          ))}
        </li>
        {dato.contrastes.length > 0 && (
          <li className="tarjeta">
            <strong>Contraste con otra fuente</strong>
            {dato.contrastes.map((c, i) => (
              <span key={i}>{c.fuente} ({c.nivel}, {periodo(c.periodo_comparado)}): {c.valor_fuente ?? "—"} frente a {c.valor_serie ?? "—"} · <em>{c.resultado}</em></span>
            ))}
          </li>
        )}
        {dato.versiones.length > 1 && (
          <li className="tarjeta">
            <strong>Versiones del mismo periodo</strong>
            {dato.versiones.map((v) => <span key={v.id} className="cifra">{v.valor} · {v.estado === "aceptada" ? "aceptado" : "en cuarentena"} · {new Date(v.creado_en).toLocaleDateString("es-CO")}</span>)}
          </li>
        )}
      </ol>
      {usuario && usuario.rol !== "usuario" && dato.marcas.length > 0 && <p className="tenue">Marcas: {dato.marcas.join(", ")}</p>}
    </>
  );
}
