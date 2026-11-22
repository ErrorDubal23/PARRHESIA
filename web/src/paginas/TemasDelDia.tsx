import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, haceCuanto } from "../api";
import * as I from "../componentes/Iconos";
import { PanelVerificacion } from "../componentes/PanelVerificacion";
import { Actividad, Huella, type TemaResumen } from "../componentes/Temas";
import type { Conclusion } from "../tipos";
import { Resumen } from "./Red";
import { comoFallo, MostrarFallo, type Fallo } from "../componentes/NoEncontrado";

type Tema = TemaResumen;

const hora = (f: string) => new Date(f).toLocaleString("es-CO", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
const capitalizar = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** Medios del tema como en la columna de un periódico: nombre, puntos guía y artículos. Los que no lo cubren van aparte, en una línea tenue. */
function MediosDelTema({ registrados, medios }: { registrados: string[]; medios: TemaResumen["medios"] }) {
  const cubren = new Set(medios.map((m) => m.medio));
  const ausentes = registrados.filter((m) => !cubren.has(m));
  return (
    <>
      <ul className="recorte__medios" aria-label="Medios que lo cubren">
        {medios.map((m) => (
          <li key={m.medio}><span>{m.medio}</span><i aria-hidden="true" /><span className="cifra" title={`${m.articulos} ${m.articulos === 1 ? "artículo" : "artículos"}`}>{m.articulos} art.</span></li>
        ))}
      </ul>
      {ausentes.length > 0 && <p className="recorte__ausentes">Sin artículos sobre el tema: {ausentes.join(", ")}.</p>}
    </>
  );
}

/** Cobertura en una fila de casillas, una por medio registrado: llenas las que lo cubren. Sin cifra grande. */
function Cobertura({ registrados, cubren }: { registrados: string[]; cubren: string[] }) {
  const lista = registrados.length ? registrados : cubren;
  return (
    <span className="cobertura" role="img" aria-label={`Lo cubren ${cubren.length} de ${lista.length} medios registrados`}>
      {lista.map((m) => <i key={m} className={cubren.includes(m) ? "cobertura--si" : ""} title={m} />)}
    </span>
  );
}

const fechaLarga = (f: string) => new Date(f).toLocaleDateString("es-CO", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

export function Temas() {
  const [datos, setDatos] = useState<{ temas: Tema[]; medios_registrados: string[] } | null>(null);
  useEffect(() => { api<typeof datos>("/temas/v1/temas").then(setDatos).catch(() => setDatos({ temas: [], medios_registrados: [] })); }, []);
  const temas = datos?.temas;
  return (
    <>
      <h1 className="titulo-seccion titulo-prensa">Temas del día</h1>
      <p className="tenue intro">Temas que hoy cubren tres o más medios. Ordenados por cobertura, no por importancia.</p>
      {temas && temas.length > 0 && (
        <p className="ventana-temas">Del {hora(temas[0].ventana_inicio)} al {hora(temas[0].ventana_fin)} · {datos!.medios_registrados.length} medios registrados</p>
      )}
      {!datos && <span className="cargando"><i /><i /><i /></span>}
      {temas?.length === 0 && <p className="tenue">Aún no hay temas en esta ventana.</p>}
      <div className="recortes">
        {temas?.map((t) => {
          const cubren = t.medios.map((m) => m.medio);
          const registrados = datos!.medios_registrados;
          return (
            <div key={t.id} className="recorte-sombra">
              <article className="recorte">
                <header className="recorte__cabezote">
                  <span>Parrhesia · Temas del día</span>
                  <span>{capitalizar(fechaLarga(t.ventana_fin))}</span>
                </header>
                <div className={`recorte__cuerpo${t.imagen ? "" : " recorte__cuerpo--sin-foto"}`}>
                  {t.imagen && (
                    <figure className="recorte__foto" style={{ backgroundColor: t.imagen.color ?? undefined }}>
                      <img src={t.imagen.url} alt="" loading="lazy" decoding="async" />
                      <figcaption>
                        Foto de referencia: <a href={t.imagen.url_autor} target="_blank" rel="noreferrer noopener">{t.imagen.autor}</a> en{" "}
                        <a href={t.imagen.url_foto} target="_blank" rel="noreferrer noopener">Unsplash</a>
                      </figcaption>
                    </figure>
                  )}
                  <div className="recorte__texto">
                    <span className="recorte__seccion">#{t.etiqueta}</span>
                    <h2 className="recorte__titular"><Link to={`/temas/${t.id}`}>{capitalizar(t.titulo)}</Link></h2>
                    <p className="recorte__bajada">
                      Lo cubren {t.total_medios} de {registrados.length} medios registrados, con {t.total_articulos} artículos
                      {t.medios[0] && <> desde hace {haceCuanto(t.medios[0].primero)}</>}.
                    </p>
                    <Cobertura registrados={registrados} cubren={cubren} />
                    <MediosDelTema registrados={registrados} medios={t.medios} />
                  </div>
                </div>
                <footer className="recorte__pie">
                  <span className="recorte__ritmo"><Actividad tramos={t.actividad} /><small>Artículos cada 3 horas</small></span>
                  <Link to={`/temas/${t.id}`} className="recorte__seguir">Leer el tema completo <I.Flecha width={15} /></Link>
                </footer>
              </article>
            </div>
          );
        })}
      </div>
    </>
  );
}

export function TemaPagina() {
  const { id } = useParams();
  const [tema, setTema] = useState<(Tema & {
    articulos: { id: string; medio: string; titulo: string; url: string; publicado_en: string }[];
    declaraciones: { id: string; medio: string; actor: string; texto_citado: string; url: string; publicado_en: string }[];
  }) | null>(null);
  const [resumen, setResumen] = useState<{ conclusion: Conclusion; total: number }[]>([]);
  const [pestana, setPestana] = useState<"declaraciones" | "articulos">("declaraciones");
  const [fallo, setFallo] = useState<Fallo | null>(null);

  useEffect(() => {
    api<typeof tema>(`/temas/v1/temas/${id}`).then((t) => {
      setTema(t);
      if (t && t.declaraciones.length === 0) setPestana("articulos");
      if (t?.declaraciones.length) {
        api<{ conclusiones: typeof resumen }>("/verificacion/v1/resumen", { metodo: "POST", cuerpo: { declaraciones_reportadas: t.declaraciones.map((d) => d.id) } })
          .then((r) => setResumen(r.conclusiones)).catch(() => {});
      }
    }).catch((e) => setFallo(comoFallo(e)));
  }, [id]);

  if (fallo) return <MostrarFallo fallo={fallo} titulo="Este tema no está en el registro." />;
  if (!tema) return <span className="cargando"><i /><i /><i /></span>;
  return (
    <>
      <Link to="/temas" className="volver"><I.Volver width={18} /> Temas del día</Link>
      <header className="cabecera-tema">
        <Huella registrados={[]} cubren={tema.medios.map((m) => m.medio)} total={tema.total_medios} tamano={112} />
        <div>
          <span className="pieza-tema__etiqueta">#{tema.etiqueta}</span>
          <h1 className="titulo-seccion">{capitalizar(tema.titulo)}</h1>
          <p className="tenue">{tema.total_medios} medios · {tema.total_articulos} artículos · {tema.medios.map((m) => m.medio).join(", ")}</p>
          <Actividad tramos={tema.actividad} />
        </div>
      </header>
      <Resumen resumen={resumen} />
      <ComoLeer />
      <div className="pestanas" role="tablist">
        <button role="tab" aria-selected={pestana === "declaraciones"} onClick={() => setPestana("declaraciones")}>
          Lo que se dijo con cifras <span className="cifra tenue">{tema.declaraciones.length}</span>
        </button>
        <button role="tab" aria-selected={pestana === "articulos"} onClick={() => setPestana("articulos")}>
          Artículos <span className="cifra tenue">{tema.articulos.length}</span>
        </button>
      </div>
      {pestana === "declaraciones" && (
        <section>
          {tema.declaraciones.length === 0 && <p className="tenue">Los artículos de este tema no atribuyen cifras a ninguna persona.</p>}
          {tema.declaraciones.map((d) => (
            <article key={d.id} className="tarjeta declaracion">
              <p className="declaracion__quien">Según <strong>{d.medio}</strong>, {d.actor}:
                <a href={d.url} target="_blank" rel="noreferrer" className="enlace-suave">Leer en el medio <I.Enlace width={13} /></a></p>
              <blockquote>«{d.texto_citado}»</blockquote>
              <PanelVerificacion tipo="declaracion_reportada" id={d.id} />
            </article>
          ))}
        </section>
      )}
      {pestana === "articulos" && (
        <ul className="articulos">
          {tema.articulos.map((a) => (
            <li key={a.id}>
              <a href={a.url} target="_blank" rel="noreferrer" className="articulo">
                <span className="articulo__medio">{a.medio}</span>
                <span className="articulo__titulo">{a.titulo}</span>
                <time className="tenue">{hora(a.publicado_en)}</time>
                <I.Enlace width={15} />
              </a>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

/** Cómo leer un tema del día (decisión 34): consejos generales, sin juzgar el tema. */
function ComoLeer() {
  const [consejo, setConsejo] = useState<{ para_entenderlo: string; pasos: string[] } | null>(null);
  useEffect(() => { api<typeof consejo>("/verificacion/v1/consejos/general/leer_tema").then(setConsejo).catch(() => {}); }, []);
  if (!consejo) return null;
  return (
    <section className="guia guia--tema" aria-label="Cómo leer este tema">
      <div className="guia__bloque">
        <h3 className="guia__titulo"><I.Util width={16} /> Cómo leer este tema</h3>
        <p>{consejo.para_entenderlo}</p>
        <ol className="guia__pasos">{consejo.pasos.map((p) => <li key={p}>{p}</li>)}</ol>
      </div>
    </section>
  );
}
