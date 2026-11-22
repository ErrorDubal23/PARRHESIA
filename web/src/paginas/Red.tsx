import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { EditarPerfil } from "../componentes/EditarPerfil";
import { api, cifra } from "../api";
import * as I from "../componentes/Iconos";
import { usePublicar } from "../componentes/Marco";
import { PanelVerificacion } from "../componentes/PanelVerificacion";
import { TarjetaPublicacion, useAlPublicar } from "../componentes/TarjetaPublicacion";
import { CONCLUSIONES, Glifo } from "../componentes/Veredicto";
import { useSesion } from "../sesion";
import type { Conclusion, Publicacion } from "../tipos";
import { Avatar } from "../componentes/Avatar";
import { comoFallo, MostrarFallo, type Fallo } from "../componentes/NoEncontrado";


export function Inicio() {
  const { usuario, cargando } = useSesion();
  const abrir = usePublicar();
  const [feed, setFeed] = useState<{ publicaciones: Publicacion[]; fuente: string } | null>(null);

  const cargar = useCallback(() => {
    if (usuario) api<{ publicaciones: Publicacion[]; fuente: string }>("/social/v1/feed").then(setFeed).catch(() => setFeed({ publicaciones: [], fuente: "" }));
  }, [usuario]);
  useEffect(cargar, [cargar]);
  useAlPublicar(cargar);

  if (cargando) return <span className="cargando"><i /><i /><i /></span>;
  if (!usuario) {
    return (
      <>
      <section className="bienvenida tarjeta">
        <I.Logo tamano={72} aleteo="al-pasar" />
        <h1>La palabra es tuya.<br /><em>El dato, de todos.</em></h1>
        <p>Una red para opinar con libertad, donde cada cifra pública se lee junto a su fuente oficial,
          completa y con la misma regla para cualquier afirmación.</p>
        <div className="bienvenida__acciones">
          <Link to="/registro" className="boton">Crear una cuenta</Link>
          <Link to="/entrar" className="boton boton--borde">Entrar</Link>
          <Link to="/temas" className="enlace-suave">Ver los temas del día <I.Flecha width={14} /></Link>
        </div>
      </section>
      </>
    );
  }
  return (
    <>
      <button className="caja-publicar tarjeta" onClick={() => abrir()} title="Publicar (tecla N)">
        <Avatar nombre={usuario.nombre_visible} foto={usuario.foto} />
        <span className="caja-publicar__campo tenue">¿Qué quieres compartir hoy, {usuario.nombre_visible.split(" ")[0]}?</span>
        <span className="caja-publicar__enviar" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round"><path d="M21 3 3 10.5l7.5 2.6L13 21z" /><path d="m10.5 13.1 4-4" /></svg>
        </span>
      </button>
      {feed === null && <span className="cargando"><i /><i /><i /></span>}
      {feed?.fuente === "respaldo" && (
        <p className="aviso">La red ampliada no está disponible en este momento: por ahora ves solo a quienes sigues.</p>
      )}
      {feed && feed.publicaciones.length === 0 && (
        <div className="vacio tarjeta">
          <h2>Tu inicio está vacío</h2>
          <p className="tenue">Sigue a otras personas desde los temas y las tendencias. Aquí aparecerá lo que publiquen en los últimos siete días.</p>
          <Link to="/tendencias" className="boton boton--borde">Explorar tendencias</Link>
        </div>
      )}
      <div className="lista-publicaciones">
        {feed?.publicaciones.map((p) => <TarjetaPublicacion key={p.id} publicacion={p} />)}
      </div>
    </>
  );
}

export function PublicacionDetalle() {
  const { id } = useParams();
  const [hilo, setHilo] = useState<Publicacion[] | null>(null);
  const [error, setError] = useState<Fallo | null>(null);
  const cargar = useCallback(() => {
    api<{ hilo: Publicacion[] }>(`/social/v1/publicaciones/${id}/hilo`).then((r) => setHilo(r.hilo))
      .catch((e) => setError(comoFallo(e)));
  }, [id]);
  useEffect(cargar, [cargar]);
  useAlPublicar(cargar);

  if (error) return <MostrarFallo fallo={error} titulo="Esta publicación no existe." />;
  if (!hilo) return <span className="cargando"><i /><i /><i /></span>;
  const [raiz, ...respuestas] = hilo;
  return (
    <>
      <Link to="/" className="volver"><I.Volver width={18} /> Volver</Link>
      <TarjetaPublicacion publicacion={raiz} enlazar={false} />
      {raiz.estado === "visible" && raiz.texto && raiz.verificacion !== "sin_cifras" && (
        <section className="tarjeta seccion-verificacion">
          <h2 className="sello sello--tinta">Lo que dicen los datos oficiales</h2>
          <PanelVerificacion tipo="publicacion" id={raiz.id} />
        </section>
      )}
      {respuestas.length > 0 && <h2 className="subtitulo">Respuestas</h2>}
      <div className="lista-publicaciones">
        {respuestas.map((r) => (
          <div key={r.id} style={{ marginLeft: Math.min(r.profundidad ?? 1, 4) * 18 - 18 }}>
            <TarjetaPublicacion publicacion={r} />
          </div>
        ))}
      </div>
    </>
  );
}

export function PerfilPagina() {
  const { nombre } = useParams();
  const { usuario } = useSesion();
  const navegar = useNavigate();
  const [perfil, setPerfil] = useState<{ nombre_usuario: string; nombre_visible: string; biografia: string | null; foto: string | null;
    estado: string; lo_sigo: boolean; creado_en: string; estadisticas: { seguidores: number; seguidos: number; publicaciones: number } } | null>(null);
  const [editando, setEditando] = useState(false);
  const [publicaciones, setPublicaciones] = useState<Publicacion[]>([]);
  const [error, setError] = useState<Fallo | null>(null);
  const [siguiendo, setSiguiendo] = useState(false);

  useEffect(() => {
    setError(null);
    api<NonNullable<typeof perfil>>(`/social/v1/usuarios/${nombre}`).then((p) => {
      setPerfil(p);
      setSiguiendo(p.lo_sigo);
      // Un nombre anterior lleva al perfil: la dirección se corrige al nombre actual.
      if (nombre && p.nombre_usuario !== nombre.toLowerCase()) navegar(`/perfil/${p.nombre_usuario}`, { replace: true });
    }).catch((e) => setError(comoFallo(e)));
    api<{ publicaciones: Publicacion[] }>(`/social/v1/usuarios/${nombre}/publicaciones`).then((r) => setPublicaciones(r.publicaciones)).catch(() => {});
  }, [nombre, usuario?.foto, usuario?.nombre_visible, usuario?.biografia]); // eslint-disable-line react-hooks/exhaustive-deps

  const seguir = async () => {
    await api(`/social/v1/usuarios/${nombre}/seguidores/yo`, { metodo: siguiendo ? "DELETE" : "PUT" });
    setSiguiendo(!siguiendo);
    if (perfil) setPerfil({ ...perfil, estadisticas: { ...perfil.estadisticas, seguidores: perfil.estadisticas.seguidores + (siguiendo ? -1 : 1) } });
  };

  if (error) return <MostrarFallo fallo={error} titulo="Esta persona no está en Parrhesia." />;
  if (!perfil) return <span className="cargando"><i /><i /><i /></span>;
  const propio = usuario?.nombre_usuario === perfil.nombre_usuario;
  return (
    <>
      <section className="perfil tarjeta">
        <Avatar nombre={perfil.nombre_visible} foto={perfil.foto} grande />
        <div>
          <h1>{perfil.nombre_visible}</h1>
          <p className="tenue">@{perfil.nombre_usuario} · desde {new Date(perfil.creado_en).toLocaleDateString("es-CO", { month: "long", year: "numeric" })}</p>
          {perfil.estado === "desactivada" && <p className="aviso">Esta cuenta está desactivada. Sus publicaciones se conservan.</p>}
          {perfil.biografia && <p className="perfil__bio">{perfil.biografia}</p>}
          <dl className="perfil__cifras">
            <div><dt>Publicaciones</dt><dd className="cifra">{perfil.estadisticas.publicaciones}</dd></div>
            <div><dt>Seguidores</dt><dd className="cifra">{perfil.estadisticas.seguidores}</dd></div>
            <div><dt>Siguiendo</dt><dd className="cifra">{perfil.estadisticas.seguidos}</dd></div>
          </dl>
        </div>
        {usuario && !propio && perfil.estado === "activo" && (
          <button className={`boton ${siguiendo ? "boton--borde" : ""}`} onClick={seguir}>{siguiendo ? "Dejar de seguir" : "Seguir"}</button>
        )}
        {propio && <button className="boton boton--borde" onClick={() => setEditando(true)}>Editar perfil</button>}
      </section>
      {propio && <EditarPerfil abierto={editando} cerrar={() => setEditando(false)} />}
      <div className="lista-publicaciones">
        {publicaciones.map((p) => <TarjetaPublicacion key={p.id} publicacion={p} />)}
        {publicaciones.length === 0 && <p className="tenue">Todavía no hay publicaciones.</p>}
      </div>
    </>
  );
}

type FilaTendencia = { etiqueta: string; total_publicaciones: number; total_autores: number; diversidad?: string; puntaje?: string };

/** Marcas del eje: 1, 2 o 5 por diez, para que las líneas caigan en números redondos. */
function marcas(maximo: number): number[] {
  const paso = [1, 2, 5, 10, 20, 50, 100, 200, 500].find((p) => maximo / p <= 5) ?? Math.ceil(maximo / 5);
  const tope = Math.ceil(maximo / paso) * paso;
  return Array.from({ length: tope / paso + 1 }, (_, i) => i * paso);
}

/**
 * Tendencias como barras horizontales. La barra mide las publicaciones; cuando el grafo calculó la diversidad,
 * la parte oscura es lo que cuenta para el orden (publicaciones × diversidad) y la clara lo que la diversidad
 * descuenta. Cada fila es un enlace a su tendencia; al pasar el cursor o el foco aparece el detalle.
 */
function GraficaTendencias({ tendencias }: { tendencias: FilaTendencia[] }) {
  const [activa, setActiva] = useState<number | null>(null);
  const conDiversidad = tendencias.some((t) => t.puntaje != null);
  const eje = marcas(Math.max(...tendencias.map((t) => t.total_publicaciones)));
  const tope = eje[eje.length - 1];
  const pct = (n: number) => `${(n / tope) * 100}%`;
  return (
    <figure className="grafica-tendencias tarjeta">
      <figcaption className="grafica-tendencias__cabecera">
        <span>
          <strong>Publicaciones por etiqueta</strong>
          <small>Últimas 24 horas · ordenadas {conDiversidad ? "por publicaciones de personas que no se siguen entre sí" : "por publicaciones"}</small>
        </span>
        {conDiversidad && (
          <span className="grafica-tendencias__leyenda">
            <span><i className="muestra muestra--cuenta" /> Cuentan para el orden</span>
            <span><i className="muestra muestra--resto" /> Descontadas por estar entre personas que se siguen</span>
          </span>
        )}
      </figcaption>
      <div className="grafica-tendencias__cuerpo">
        <div className="grafica-tendencias__rejilla" aria-hidden="true">
          {eje.map((m) => <span key={m} style={{ left: pct(m) }} />)}
        </div>
        <ol className="grafica-tendencias__filas">
          {tendencias.map((t, i) => {
            const cuenta = t.puntaje != null ? Number(t.puntaje) : t.total_publicaciones;
            const diversidad = t.diversidad != null ? Number(t.diversidad) : null;
            const detalle = `#${t.etiqueta}: ${t.total_publicaciones} publicaciones de ${t.total_autores} personas`
              + (diversidad != null ? `, diversidad ${cifra(t.diversidad!)}` : "");
            return (
              <li key={t.etiqueta}>
                <Link to={`/tendencias/${t.etiqueta}`} className={`barra-tendencia${activa === i ? " barra-tendencia--activa" : ""}`}
                  aria-label={`${detalle}. Ver la tendencia`}
                  onMouseEnter={() => setActiva(i)} onMouseLeave={() => setActiva(null)}
                  onFocus={() => setActiva(i)} onBlur={() => setActiva(null)}>
                  <span className="barra-tendencia__puesto cifra">{i + 1}</span>
                  <span className="barra-tendencia__nombre">#{t.etiqueta}</span>
                  <span className="barra-tendencia__pista">
                    <span className="barra-tendencia__total" style={{ width: pct(t.total_publicaciones) }}>
                      <span className="barra-tendencia__cuenta" style={{ width: `${(cuenta / t.total_publicaciones) * 100}%` }} />
                    </span>
                    <span className="barra-tendencia__valor cifra" style={{ left: pct(t.total_publicaciones) }}>{t.total_publicaciones}</span>
                    {activa === i && (
                      <span className={`barra-tendencia__detalle${tendencias.length > 4 && i >= tendencias.length / 2 ? " barra-tendencia__detalle--arriba" : ""}`} role="tooltip" style={{ left: `min(${pct(t.total_publicaciones)}, calc(100% - 220px))` }}>
                        <strong>#{t.etiqueta}</strong>
                        <span><b className="cifra">{t.total_publicaciones}</b> publicaciones</span>
                        <span><b className="cifra">{t.total_autores}</b> personas distintas</span>
                        {diversidad != null && <span>Diversidad <b className="cifra">{cifra(t.diversidad!)}</b> <small>(1 = nadie se sigue entre sí)</small></span>}
                        <em>Ver la tendencia <I.Flecha width={13} /></em>
                      </span>
                    )}
                  </span>
                </Link>
              </li>
            );
          })}
        </ol>
        <div className="grafica-tendencias__eje" aria-hidden="true">
          {eje.map((m) => <span key={m} className="cifra" style={{ left: pct(m) }}>{m}</span>)}
        </div>
      </div>
    </figure>
  );
}

export function Tendencias() {
  const [datos, setDatos] = useState<{ fuente: string; aviso?: string; tendencias: FilaTendencia[] } | null>(null);
  useEffect(() => { api<typeof datos>("/social/v1/tendencias").then(setDatos).catch(() => setDatos({ fuente: "", tendencias: [] })); }, []);
  return (
    <>
      <h1 className="titulo-seccion">Tendencias</h1>
      <p className="tenue intro">Etiquetas que más personas usaron en las últimas 24 horas. Cuentan más cuando las usan personas que no se siguen entre sí: ningún grupo cerrado puede inflar una tendencia.</p>
      {datos?.aviso && <p className="aviso">{datos.aviso}</p>}
      {datos && datos.tendencias.length === 0 && <p className="tenue">Aún no hay tendencias. Una etiqueta entra cuando la usan al menos tres personas con cuentas de más de siete días.</p>}
      {datos && datos.tendencias.length > 0 && <GraficaTendencias tendencias={datos.tendencias} />}
    </>
  );
}

export function TendenciaPagina() {
  const { etiqueta } = useParams();
  const [datos, setDatos] = useState<{ declaraciones: { id: string; texto: string; dicha_el: string; url_fuente: string; nombre_completo: string; figura_id: string }[];
    publicaciones: Publicacion[]; resumen: { conclusion: Conclusion; total: number }[] } | null>(null);
  useEffect(() => { api<typeof datos>(`/social/v1/tendencias/${etiqueta}`).then(setDatos).catch(() => {}); }, [etiqueta]);
  if (!datos) return <span className="cargando"><i /><i /><i /></span>;
  return (
    <>
      <Link to="/tendencias" className="volver"><I.Volver width={18} /> Tendencias</Link>
      <h1 className="titulo-seccion">#{etiqueta}</h1>
      <Resumen resumen={datos.resumen} />
      {datos.declaraciones.length > 0 && (
        <section>
          <h2 className="subtitulo">Lo que dijeron las figuras públicas</h2>
          {datos.declaraciones.map((d) => (
            <article key={d.id} className="tarjeta declaracion">
              <p className="declaracion__quien"><Link to={`/figuras/${d.figura_id}`}><strong>{d.nombre_completo}</strong></Link>
                <span className="tenue"> · {new Date(d.dicha_el + "T12:00").toLocaleDateString("es-CO", { day: "numeric", month: "long", year: "numeric" })}</span>
                <a href={d.url_fuente} target="_blank" rel="noreferrer" className="enlace-suave">Fuente <I.Enlace width={13} /></a></p>
              <blockquote>«{d.texto}»</blockquote>
              <PanelVerificacion tipo="declaracion" id={d.id} />
            </article>
          ))}
        </section>
      )}
      <h2 className="subtitulo">Lo que se dice en la red</h2>
      <div className="lista-publicaciones">
        {datos.publicaciones.map((p) => <TarjetaPublicacion key={p.id} publicacion={p} />)}
        {datos.publicaciones.length === 0 && <p className="tenue">Nadie ha publicado con esta etiqueta en los últimos siete días.</p>}
      </div>
    </>
  );
}

/** Conteo de conclusiones vigentes: solo cuenta lo guardado, no produce cifras nuevas. */
export function Resumen({ resumen }: { resumen: { conclusion: Conclusion; total: number }[] }) {
  const total = resumen.reduce((s, r) => s + r.total, 0);
  if (!total) return null;
  return (
    <section className="resumen tarjeta" aria-label="Resumen de las conclusiones">
      <p className="sello sello--tinta">{total} {total === 1 ? "cifra verificada" : "cifras verificadas"}</p>
      <ul>
        {resumen.map((r) => (
          <li key={r.conclusion}>
            <Glifo tipo={r.conclusion} />
            <span>{CONCLUSIONES[r.conclusion].titulo}</span>
            <span className="resumen__barra"><span style={{ width: `${(r.total / total) * 100}%` }} /></span>
            <strong className="cifra">{r.total}</strong>
          </li>
        ))}
      </ul>
    </section>
  );
}
