import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, haceCuanto } from "../api";
import { useIrAEntrar, useSesion } from "../sesion";
import type { Publicacion, TextoVerificado } from "../tipos";
import * as I from "./Iconos";
import { usePublicar } from "./Marco";
import { Veredicto } from "./Veredicto";
import { Avatar } from "./Avatar";
import { TextoEnriquecido } from "./TextoEnriquecido";

/** Trae la conclusión de la primera afirmación y vuelve a preguntar mientras esté pendiente. */
export function useVerificacion(publicacion: Publicacion) {
  const [estado, setEstado] = useState(publicacion.verificacion);
  const [detalle, setDetalle] = useState<TextoVerificado | null>(null);
  useEffect(() => {
    if (estado === "sin_cifras") return;
    let vivo = true;
    let intentos = 0;
    const traer = async () => {
      try {
        const r = await api<TextoVerificado>(`/verificacion/v1/textos/publicacion/${publicacion.id}`);
        if (!vivo) return;
        setDetalle(r);
        setEstado(r.estado);
        if (r.estado === "pendiente" && intentos++ < 40) setTimeout(traer, 4000);
      } catch {
        if (vivo && intentos++ < 40) setTimeout(traer, 6000);
      }
    };
    traer();
    return () => { vivo = false; };
  }, [publicacion.id]); // eslint-disable-line react-hooks/exhaustive-deps
  return { estado, detalle };
}

export function TarjetaPublicacion({ publicacion: inicial, enlazar = true }: { publicacion: Publicacion; enlazar?: boolean }) {
  const [p, setP] = useState(inicial);
  const { usuario } = useSesion();
  const navegar = useNavigate();
  const irAEntrar = useIrAEntrar();
  const abrirCompositor = usePublicar();
  const { estado, detalle } = useVerificacion(p);
  const primera = detalle?.afirmaciones.find((a) => a.verificacion);

  const reaccionar = async (tipo: "me_gusta" | "util") => {
    if (!usuario) return irAEntrar();
    const quitar = p.mi_reaccion === tipo;
    const r = await api<Publicacion>(`/social/v1/publicaciones/${p.id}/reacciones/yo`,
      quitar ? { metodo: "DELETE" } : { metodo: "PUT", cuerpo: { tipo } });
    setP({ ...p, ...r });
  };
  const [compartiendo, setCompartiendo] = useState(false);
  const compartir = async () => {
    if (!usuario) return irAEntrar();
    if (compartiendo) return;
    setCompartiendo(true);
    try {
      if (p.mi_compartida) {   // ya la compartí: pulsar otra vez deshace
        await api(`/social/v1/publicaciones/${p.mi_compartida}`, { metodo: "DELETE" });
        setP({ ...p, mi_compartida: null, totales: { ...p.totales, compartidas: Math.max(0, p.totales.compartidas - 1) } });
      } else {
        const r = await api<{ id: string }>("/social/v1/publicaciones", { metodo: "POST", cuerpo: { texto: null, comparte_id: p.id } });
        setP({ ...p, mi_compartida: r.id, totales: { ...p.totales, compartidas: p.totales.compartidas + 1 } });
      }
      window.dispatchEvent(new Event("publicacion-creada"));
    } finally {
      setCompartiendo(false);
    }
  };

  // Retirar (auditoría FN-06): el autor retira lo suyo; un administrador, lo de cualquiera. La base lo decide
  // igual (social.retirar_publicacion); aquí solo se ofrece a quien puede, con confirmación.
  const [confirmando, setConfirmando] = useState(false);
  const [errorRetirar, setErrorRetirar] = useState<string | null>(null);
  const esMia = usuario?.nombre_usuario === p.autor.nombre_usuario;
  const puedeRetirar = !!usuario && (esMia || usuario.rol === "admin");
  const retirar = async () => {
    try {
      await api(`/social/v1/publicaciones/${p.id}`, { metodo: "DELETE" });
      setP({ ...p, estado: esMia ? "retirada_por_autor" : "retirada_por_moderacion", texto: null });
      setConfirmando(false);
      window.dispatchEvent(new Event("publicacion-creada"));
    } catch {
      setErrorRetirar("No se pudo retirar. Inténtalo de nuevo.");
    }
  };

  const retirada = p.estado !== "visible";
  const abrir = () => navegar(`/publicacion/${p.id}`);
  return (
    <article className={`publicacion ${enlazar ? "publicacion--enlazable" : ""}`} onClick={() => enlazar && abrir()}>
      <Link to={`/perfil/${p.autor.nombre_usuario}`} className="publicacion__avatar" onClick={(e) => e.stopPropagation()}
        aria-label={`Perfil de ${p.autor.nombre_visible}`}>
        <Avatar nombre={p.autor.nombre_visible} foto={p.autor.foto} />
      </Link>
      <div className="publicacion__cuerpo">
        <header className="publicacion__cabecera">
          <Link to={`/perfil/${p.autor.nombre_usuario}`} className="publicacion__autor" onClick={(e) => e.stopPropagation()}>
            <strong>{p.autor.nombre_visible}</strong>
            <span className="tenue">@{p.autor.nombre_usuario}</span>
          </Link>
          {/* La hora es el enlace a la publicación (auditoría FN-18): así se abre también con el teclado. */}
          <Link to={`/publicacion/${p.id}`} className="publicacion__hora" onClick={(e) => e.stopPropagation()}
            aria-label={`Abrir la publicación de ${p.autor.nombre_visible}, ${haceCuanto(p.creado_en)}`}>
            <time className="tenue" dateTime={p.creado_en} title={new Date(p.creado_en).toLocaleString("es-CO")}>{haceCuanto(p.creado_en)}</time>
          </Link>
          {p.distancia === 2 && <span className="sello" title="Lo sigue alguien a quien sigues">Red ampliada</span>}
          {p.comunidad && (
            <Link to={`/comunidades/${p.comunidad.id}`} className="publicacion__comunidad" onClick={(e) => e.stopPropagation()}
              title={p.comunidad.privacidad === "privada" ? "Comunidad privada: solo la ven sus integrantes" : "Comunidad pública"}>
              en {p.comunidad.nombre}{p.comunidad.privacidad === "privada" && " · privada"}
            </Link>
          )}
          {p.fijada && <span className="publicacion__fijada">Fijada</span>}
        </header>

        {p.responde_a && p.responde_a_id && (
          <Link to={`/publicacion/${p.responde_a_id}`} className="publicacion__contexto" onClick={(e) => e.stopPropagation()}>
            <I.Responder width={14} /> Respondiendo a @{p.responde_a.nombre_usuario}
          </Link>
        )}

        {retirada ? (
          <p className="publicacion__retirada">Esta publicación fue retirada.</p>
        ) : p.texto ? (
          <p className="publicacion__texto"><TextoEnriquecido texto={p.texto} /></p>
        ) : (
          <p className="publicacion__compartida tenue"><I.Compartir width={16} /> Compartió</p>
        )}

        {!retirada && p.comparte_id && <Incrustada original={p.original} />}
        {!retirada && p.texto && estado === "sin_cifras" && <span className="publicacion__tipo">Opinión</span>}

        {!retirada && (
          <footer className="publicacion__acciones" onClick={(e) => e.stopPropagation()}>
            <button className="accion" onClick={() => abrirCompositor(p)} aria-label={`Responder (${p.totales.respuestas})`}>
              <I.Responder width={18} /><span className="cifra">{p.totales.respuestas}</span>
            </button>
            <button className={`accion ${p.mi_compartida ? "accion--activa" : ""}`} onClick={compartir} disabled={compartiendo}
              aria-pressed={!!p.mi_compartida} aria-label={p.mi_compartida ? "Deshacer compartida" : "Compartir"}
              title={p.mi_compartida ? "Compartiste esta publicación · pulsa para deshacer" : "Compartir"}>
              <I.Compartir width={18} /><span className="cifra">{p.totales.compartidas}</span>
            </button>
            <button className={`accion ${p.mi_reaccion === "me_gusta" ? "accion--activa" : ""}`} onClick={() => reaccionar("me_gusta")}
              aria-pressed={p.mi_reaccion === "me_gusta"} aria-label="Me gusta" title="Me gusta">
              <I.MeGusta width={18} lleno={p.mi_reaccion === "me_gusta"} /><span className="cifra">{p.totales.me_gusta}</span>
            </button>
            <span className="publicacion__separador" aria-hidden="true" />
            <button className={`accion ${p.mi_reaccion === "util" ? "accion--activa" : ""}`} onClick={() => reaccionar("util")}
              aria-pressed={p.mi_reaccion === "util"} aria-label="Útil" title="Me sirvió para entender">
              <I.Util width={18} lleno={p.mi_reaccion === "util"} /><span>Útil · <span className="cifra">{p.totales.util}</span></span>
            </button>
            {puedeRetirar && (confirmando ? (
              <span className="publicacion__confirmar" role="group" aria-label="Confirmar retiro">
                {errorRetirar ?? (esMia ? "¿Retirar tu publicación?" : "¿Retirarla por moderación?")}
                <button type="button" className="boton-texto publicacion__si" onClick={retirar}>Sí, retirar</button>
                <button type="button" className="boton-texto" onClick={() => { setConfirmando(false); setErrorRetirar(null); }}>No</button>
              </span>
            ) : (
              <button type="button" className="accion publicacion__retirar" onClick={() => setConfirmando(true)}
                aria-label={esMia ? "Retirar mi publicación" : "Retirar por moderación"} title={esMia ? "Retirar" : "Retirar por moderación"}>
                Retirar
              </button>
            ))}
          </footer>
        )}

        {!retirada && p.texto && estado !== "sin_cifras" && (
          <button className="publicacion__veredicto" onClick={(e) => { e.stopPropagation(); abrir(); }} aria-label="Ver el análisis completo">
            <Veredicto estado={estado} conclusion={primera?.verificacion?.conclusion} resumen={primera?.verificacion?.explicacion} />
            <svg className="publicacion__ir" viewBox="0 0 12 12" width="14" height="14" aria-hidden="true"><path d="M4.5 3l3 3-3 3" /></svg>
          </button>
        )}
      </div>
    </article>
  );
}

/** La publicación compartida, dentro de la tarjeta de quien la compartió, con su conclusión si tiene cifras. */
function Incrustada({ original }: { original: Publicacion | null }) {
  const navegar = useNavigate();
  if (!original || original.estado !== "visible") {
    return <div className="incrustada incrustada--vacia tenue">La publicación original ya no está disponible.</div>;
  }
  return (
    <div className="incrustada" role="link" tabIndex={0}
      onClick={(e) => { e.stopPropagation(); navegar(`/publicacion/${original.id}`); }}
      onKeyDown={(e) => { if (e.key === "Enter") navegar(`/publicacion/${original.id}`); }}>
      <div className="incrustada__cabecera">
        <Avatar nombre={original.autor.nombre_visible} foto={original.autor.foto} />
        <strong>{original.autor.nombre_visible}</strong>
        <span className="tenue">@{original.autor.nombre_usuario} · {haceCuanto(original.creado_en)}</span>
      </div>
      {original.texto && <p className="publicacion__texto"><TextoEnriquecido texto={original.texto} /></p>}
      <VeredictoDe publicacion={original} />
    </div>
  );
}

function VeredictoDe({ publicacion }: { publicacion: Publicacion }) {
  const { estado, detalle } = useVerificacion(publicacion);
  const primera = detalle?.afirmaciones.find((a) => a.verificacion);
  if (estado === "sin_cifras") return null;
  return <Veredicto estado={estado} conclusion={primera?.verificacion?.conclusion} resumen={primera?.verificacion?.explicacion} />;
}

/** Vuelve a cargar una lista cuando alguien publica desde el compositor. */
export function useAlPublicar(recargar: () => void) {
  useEffect(() => {
    window.addEventListener("publicacion-creada", recargar);
    return () => window.removeEventListener("publicacion-creada", recargar);
  }, [recargar]);
}
