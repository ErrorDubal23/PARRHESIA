// Comunidades (decisión 28): encontrar y crear comunidades, y la página de cada una. Los permisos los
// decide la base (social.puede); la app solo muestra lo que cada papel puede hacer.
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ErrorApi, haceCuanto } from "../api";
import { Avatar } from "../componentes/Avatar";
import * as I from "../componentes/Iconos";
import { usePublicar } from "../componentes/Marco";
import { comoFallo, MostrarFallo, type Fallo } from "../componentes/NoEncontrado";
import { TarjetaPublicacion, useAlPublicar } from "../componentes/TarjetaPublicacion";
import { TextoEnriquecido } from "../componentes/TextoEnriquecido";
import { useIrAEntrar, useSesion } from "../sesion";
import type { Publicacion } from "../tipos";

type Papel = "integrante" | "moderador" | "gestor" | "administrador";
interface Comunidad {
  id: string; nombre: string; descripcion: string; reglas: string | null; privacidad: "publica" | "privada";
  imagen: string | null; total_integrantes: number; total_publicaciones: number; creada_en: string; creada_por: string;
  mi_papel: Papel | null; solicitud_pendiente: boolean;
  temas?: string[]; fuera_de_mi_red?: number; en_comun?: number;
  permisos?: { ver: boolean; publicar: boolean; moderar: boolean; gestionar_integrantes: boolean; configurar: boolean };
}

export const PAPEL: Record<Papel, string> = {
  administrador: "Administrador", gestor: "Gestor de integrantes", moderador: "Moderador", integrante: "Integrante",
};
const mensaje = (e: unknown, defecto: string) => (e instanceof ErrorApi ? e.message : defecto);

function Simbolo({ c, grande = false }: { c: Pick<Comunidad, "nombre" | "imagen">; grande?: boolean }) {
  return c.imagen
    ? <img className={`simbolo-comunidad${grande ? " simbolo-comunidad--grande" : ""}`} src={c.imagen} alt="" />
    : <span className={`simbolo-comunidad${grande ? " simbolo-comunidad--grande" : ""}`} aria-hidden="true">{c.nombre.slice(0, 1).toUpperCase()}</span>;
}

/**
 * La comunidad como un grupo de personas que sostiene su pancarta (la inicial o la imagen de la comunidad).
 * La comunidad sostiene una pancarta. Las personitas son del mismo estilo de los avatares (DiceBear "notionists" de Zoish, CC0) y se guardan en
 * public/personitas. Cada comunidad recibe siempre el mismo trío, elegido por su id: no dice nada de quién la integra.
 */
const PERSONITAS = 12;
function Grupo({ c, grande = false }: { c: Pick<Comunidad, "id" | "nombre" | "imagen">; grande?: boolean }) {
  // FNV-1a del id y luego pasos de un generador simple: reparte bien aunque los id se parezcan.
  let h = 2166136261;
  for (const ch of c.id) h = Math.imul(h ^ ch.charCodeAt(0), 16777619) >>> 0;
  const trio: number[] = [];
  while (trio.length < 3) {
    h = (Math.imul(h, 1664525) + 1013904223) >>> 0;
    const n = (h >>> 8) % PERSONITAS;
    if (!trio.includes(n)) trio.push(n);
  }
  // Todo en un mismo plano de 150 x 100: la pancarta (tela ondulada) va por encima de las cabezas y la
  // sostienen dos palos que bajan hasta las manos de las personas de los extremos; las manos quedan por delante.
  const clip = `pancarta-${c.id}`;
  const tela = "M8 9 Q41 4 75 9 T142 9 L142 40 Q109 45 75 40 T8 40 Z";
  return (
    <span className={`grupo-comunidad${grande ? " grupo-comunidad--grande" : ""}`} aria-hidden="true">
      <svg className="grupo-comunidad__pancarta" viewBox="0 0 150 100">
        <defs><clipPath id={clip}><path d={tela} /></clipPath></defs>
        <rect x="5.5" y="3" width="4" height="80" rx="2" className="palo" />
        <rect x="140.5" y="3" width="4" height="80" rx="2" className="palo" />
        <path d={tela} className="tela" />
        {c.imagen
          ? <image href={c.imagen} x="8" y="4" width="134" height="41" preserveAspectRatio="xMidYMid slice" clipPath={`url(#${clip})`} />
          : <text x="75" y="32" textAnchor="middle" className="letra">{c.nombre.slice(0, 1).toUpperCase()}</text>}
        <path d={tela} className="borde" />
      </svg>
      <span className="grupo-comunidad__personas">
        {trio.map((n, i) => <img key={i} src={`/personitas/p${String(n + 1).padStart(2, "0")}.svg`} alt="" loading="lazy" decoding="async" />)}
      </span>
    </span>
  );
}

function Privacidad({ privacidad }: { privacidad: "publica" | "privada" }) {
  return (
    <span className="privacidad" title={privacidad === "privada" ? "Su contenido solo lo ven sus integrantes; se entra con solicitud" : "Cualquiera ve su contenido y puede entrar"}>
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        {privacidad === "privada" ? <><rect x="5" y="10" width="14" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></>
          : <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" /></>}
      </svg>
      {privacidad === "privada" ? "Privada" : "Pública"}
    </span>
  );
}

// --- Listado ---------------------------------------------------------------------------------

export function Comunidades() {
  const { usuario } = useSesion();
  const irAEntrar = useIrAEntrar();
  const [q, setQ] = useState("");
  const [mias, setMias] = useState(false);
  const [lista, setLista] = useState<Comunidad[] | null>(null);
  const [creando, setCreando] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => {
      const params = new URLSearchParams({ ...(q.trim() ? { q: q.trim() } : {}), ...(mias ? { mias: "true" } : {}) });
      api<{ comunidades: Comunidad[] }>(`/social/v1/comunidades?${params}`).then((r) => setLista(r.comunidades)).catch(() => setLista([]));
    }, 250);
    return () => clearTimeout(t);
  }, [q, mias, usuario?.id]);

  return (
    <>
      <div className="cabecera-seccion">
        <div>
          <h1 className="titulo-seccion">Comunidades</h1>
          <p className="tenue intro">Grupos alrededor de un tema. Las reglas de verificación son las mismas dentro y fuera de cualquier comunidad.</p>
        </div>
        <button className="boton" onClick={() => (usuario ? setCreando(true) : irAEntrar())}>Crear comunidad</button>
      </div>
      <div className="filtros-comunidades">
        <form className="buscar-campo" role="search" onSubmit={(e) => e.preventDefault()}>
          <I.Buscar />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar una comunidad" aria-label="Buscar una comunidad" />
        </form>
        {usuario && (
          <div className="conmutador" role="group" aria-label="Qué comunidades ver">
            <button aria-pressed={!mias} onClick={() => setMias(false)}>Todas</button>
            <button aria-pressed={mias} onClick={() => setMias(true)}>Mis comunidades</button>
          </div>
        )}
      </div>
      {usuario && !mias && !q.trim() && <Sugeridas />}
      {lista === null && <span className="cargando"><i /><i /><i /></span>}
      {lista?.length === 0 && <p className="tenue">{mias ? "Aún no perteneces a ninguna comunidad." : "No hay comunidades con ese nombre."}</p>}
      <ul className="lista-comunidades">
        {lista?.map((c) => (
          <li key={c.id}>
            <Link to={`/comunidades/${c.id}`} className="comunidad-fila tarjeta">
              <Grupo c={c} />
              <span className="comunidad-fila__cuerpo">
                <strong>{c.nombre}</strong>
                <span className="comunidad-fila__descripcion">{c.descripcion}</span>
                <span className="comunidad-fila__meta">
                  <Privacidad privacidad={c.privacidad} />
                  <span><span className="cifra">{c.total_integrantes}</span> {c.total_integrantes === 1 ? "integrante" : "integrantes"}</span>
                  {c.mi_papel && <span className="comunidad-fila__papel">{PAPEL[c.mi_papel]}</span>}
                  {c.solicitud_pendiente && <span>Solicitud enviada</span>}
                </span>
              </span>
              <I.Flecha width={18} />
            </Link>
          </li>
        ))}
      </ul>
      <CrearComunidad abierto={creando} cerrar={() => setCreando(false)} />
    </>
  );
}

/** Por qué se sugiere: los temas compartidos, nunca una inclinación política. */
function Motivo({ c, relacionada = false }: { c: Comunidad; relacionada?: boolean }) {
  return (
    <span className="motivo-sugerencia">
      {c.temas && c.temas.length > 0 && <>Hablan de {c.temas.map((t) => `#${t}`).join(", ")}</>}
      {!relacionada && c.fuera_de_mi_red !== undefined && c.fuera_de_mi_red >= 0.5 && <> · la mayoría de sus integrantes está fuera de tu red</>}
      {relacionada && c.en_comun !== undefined && <> · {c.en_comun === 0 ? "ninguna persona en común" : `${c.en_comun} ${c.en_comun === 1 ? "persona" : "personas"} en común`}</>}
    </span>
  );
}

function Sugeridas() {
  const [lista, setLista] = useState<Comunidad[] | null>(null);
  useEffect(() => { api<{ comunidades: Comunidad[] }>("/social/v1/comunidades/recomendadas").then((r) => setLista(r.comunidades)).catch(() => setLista([])); }, []);
  if (!lista || lista.length === 0) return null;
  return (
    <section className="sugeridas">
      <h2 className="subtitulo">Sugeridas para ti</h2>
      <p className="tenue sugeridas__nota">Por temas que compartes. Damos prioridad a grupos fuera de tu red; nunca a una inclinación política.</p>
      <ul className="lista-comunidades">
        {lista.map((c) => (
          <li key={c.id}>
            <Link to={`/comunidades/${c.id}`} className="comunidad-fila tarjeta">
              <Grupo c={c} />
              <span className="comunidad-fila__cuerpo">
                <strong>{c.nombre}</strong>
                <Motivo c={c} />
                <span className="comunidad-fila__meta"><span><span className="cifra">{c.total_integrantes}</span> {c.total_integrantes === 1 ? "integrante" : "integrantes"}</span></span>
              </span>
              <I.Flecha width={18} />
            </Link>
          </li>
        ))}
      </ul>
      <h2 className="subtitulo sugeridas__todas">Todas las comunidades</h2>
    </section>
  );
}

function Relacionadas({ c }: { c: Comunidad }) {
  const [lista, setLista] = useState<Comunidad[]>([]);
  useEffect(() => { api<{ comunidades: Comunidad[] }>(`/social/v1/comunidades/${c.id}/relacionadas`).then((r) => setLista(r.comunidades)).catch(() => {}); }, [c.id]);
  if (lista.length === 0) return null;
  return (
    <section className="tarjeta bloque relacionadas">
      <h2 className="subtitulo">Hablan de lo mismo</h2>
      <p className="tenue sugeridas__nota">Otras comunidades con los mismos temas; primero las que tienen menos personas en común con esta.</p>
      <ul className="integrantes">
        {lista.map((r) => (
          <li key={r.id}>
            <Link to={`/comunidades/${r.id}`} className="persona__quien">
              <Simbolo c={r} />
              <span><strong>{r.nombre}</strong><Motivo c={r} relacionada /></span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

function CrearComunidad({ abierto, cerrar }: { abierto: boolean; cerrar: () => void }) {
  const dialogo = useRef<HTMLDialogElement>(null);
  const navegar = useNavigate();
  const [datos, setDatos] = useState({ nombre: "", descripcion: "", reglas: "", privacidad: "publica" as "publica" | "privada" });
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  useEffect(() => {
    const d = dialogo.current;
    if (abierto && d && !d.open) d.showModal();
    if (!abierto && d?.open) d.close();
  }, [abierto]);
  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    setEnviando(true);
    setError(null);
    try {
      const c = await api<Comunidad>("/social/v1/comunidades", { metodo: "POST", cuerpo: { ...datos, reglas: datos.reglas || null } });
      cerrar();
      navegar(`/comunidades/${c.id}`);
    } catch (err) {
      setError(mensaje(err, "No se pudo crear la comunidad."));
    } finally {
      setEnviando(false);
    }
  };
  return (
    <dialog ref={dialogo} className="compositor" onClose={cerrar} aria-labelledby="titulo-crear-comunidad">
      <form className="compositor__cuerpo" onSubmit={enviar}>
        <div className="compositor__cabecera">
          <h2 id="titulo-crear-comunidad">Nueva comunidad</h2>
          <button type="button" className="boton-texto" onClick={cerrar}>Cerrar</button>
        </div>
        <label className="campo-cuenta"><span>Nombre</span>
          <input value={datos.nombre} onChange={(e) => setDatos({ ...datos, nombre: e.target.value })} minLength={3} maxLength={60} required placeholder="Por ejemplo, Economía colombiana" /></label>
        <label className="campo-cuenta"><span>De qué se habla aquí</span>
          <textarea value={datos.descripcion} onChange={(e) => setDatos({ ...datos, descripcion: e.target.value })} minLength={10} maxLength={500} rows={3} required /></label>
        <label className="campo-cuenta"><span>Reglas (opcional)</span>
          <textarea value={datos.reglas} onChange={(e) => setDatos({ ...datos, reglas: e.target.value })} maxLength={2000} rows={3}
            placeholder="Por ejemplo: cita la fuente de tus cifras; sin ataques personales." /></label>
        <fieldset className="opciones-privacidad">
          <legend>Privacidad</legend>
          {(["publica", "privada"] as const).map((p) => (
            <label key={p} className={datos.privacidad === p ? "elegida" : ""}>
              <input type="radio" name="privacidad" checked={datos.privacidad === p} onChange={() => setDatos({ ...datos, privacidad: p })} />
              <strong>{p === "publica" ? "Pública" : "Privada"}</strong>
              <small>{p === "publica" ? "Cualquiera ve lo publicado y entra sin aprobación." : "Solo los integrantes ven lo publicado; se entra con solicitud."}</small>
            </label>
          ))}
        </fieldset>
        <p className="compositor__nota">Serás su administrador. Ninguna comunidad cambia las reglas de verificación.</p>
        {error && <p className="aviso" role="alert">{error}</p>}
        <div className="compositor__pie"><span className="editor__espacio" />
          <button className="boton" disabled={enviando}>{enviando ? "Creando…" : "Crear comunidad"}</button></div>
      </form>
    </dialog>
  );
}

// --- Página de una comunidad -------------------------------------------------------------------

type Pestana = "publicaciones" | "integrantes" | "reglas" | "bitacora" | "administracion";

export function ComunidadPagina() {
  const { id } = useParams();
  const { usuario } = useSesion();
  const irAEntrar = useIrAEntrar();
  const abrirCompositor = usePublicar();
  const [c, setC] = useState<Comunidad | null>(null);
  const [fallo, setFallo] = useState<Fallo | null>(null);
  const [pestana, setPestana] = useState<Pestana>("publicaciones");
  const [aviso, setAviso] = useState<string | null>(null);

  const cargar = useCallback(() => {
    api<Comunidad>(`/social/v1/comunidades/${id}`).then(setC).catch((e) => setFallo(comoFallo(e)));
  }, [id]);
  useEffect(() => { setFallo(null); cargar(); }, [cargar, usuario?.id]);

  if (fallo) return <MostrarFallo fallo={fallo} titulo="Esta comunidad no existe." />;
  if (!c) return <span className="cargando"><i /><i /><i /></span>;
  const p = c.permisos!;

  const entrar = async () => {
    if (!usuario) return irAEntrar();
    setAviso(null);
    try {
      const r = await api<{ resultado: string }>(`/social/v1/comunidades/${c.id}/ingreso`, { metodo: "POST", cuerpo: {} });
      if (r.resultado === "solicitud") setAviso("Solicitud enviada. Quien gestiona los integrantes la revisará.");
      cargar();
    } catch (e) { setAviso(mensaje(e, "No se pudo entrar a la comunidad.")); }
  };
  const salir = async () => {
    setAviso(null);
    try { await api(`/social/v1/comunidades/${c.id}/integrantes/yo`, { metodo: "DELETE" }); cargar(); }
    catch (e) { setAviso(mensaje(e, "No se pudo salir de la comunidad.")); }
  };

  const pestanas: [Pestana, string][] = [["publicaciones", "Publicaciones"], ["integrantes", "Integrantes"], ["reglas", "Reglas"], ["bitacora", "Bitácora"]];
  if (p.gestionar_integrantes || p.configurar) pestanas.push(["administracion", "Administración"]);

  return (
    <>
      <Link to="/comunidades" className="volver"><I.Volver width={18} /> Comunidades</Link>
      <section className="comunidad-cabecera tarjeta">
        <Grupo c={c} grande />
        <div className="comunidad-cabecera__cuerpo">
          <h1>{c.nombre}</h1>
          <p className="comunidad-cabecera__descripcion">{c.descripcion}</p>
          <p className="comunidad-fila__meta">
            <Privacidad privacidad={c.privacidad} />
            <span><span className="cifra">{c.total_integrantes}</span> {c.total_integrantes === 1 ? "integrante" : "integrantes"}</span>
            <span><span className="cifra">{c.total_publicaciones}</span> publicaciones</span>
            <span>Creada por <Link to={`/perfil/${c.creada_por}`} className="marca-texto">@{c.creada_por}</Link></span>
            {c.mi_papel && <span className="comunidad-fila__papel">Tu papel: {PAPEL[c.mi_papel]}</span>}
          </p>
        </div>
        <div className="comunidad-cabecera__acciones">
          {c.mi_papel ? (
            <>
              {p.publicar && <button className="boton" onClick={() => abrirCompositor(null, { id: c.id, nombre: c.nombre, privacidad: c.privacidad })}>Publicar aquí</button>}
              <button className="boton-texto" onClick={salir}>Salir</button>
            </>
          ) : c.solicitud_pendiente ? (
            <span className="tenue">Solicitud enviada</span>
          ) : (
            <button className="boton" onClick={entrar}>{c.privacidad === "privada" ? "Solicitar ingreso" : "Unirme"}</button>
          )}
        </div>
      </section>
      {aviso && <p className="aviso" role="status">{aviso}</p>}

      {!p.ver ? (
        <section className="tarjeta bloque comunidad-cerrada">
          <h2 className="subtitulo">Contenido solo para integrantes</h2>
          <p className="tenue">Esta comunidad es privada: sus publicaciones, integrantes y reglas los ven quienes pertenecen a ella.</p>
        </section>
      ) : (
        <>
          <div className="pestanas" role="tablist">
            {pestanas.map(([clave, texto]) => (
              <button key={clave} role="tab" aria-selected={pestana === clave} onClick={() => setPestana(clave)}>{texto}</button>
            ))}
          </div>
          {pestana === "publicaciones" && <PublicacionesComunidad c={c} />}
          {pestana === "publicaciones" && c.privacidad === "publica" && <Relacionadas c={c} />}
          {pestana === "integrantes" && <Integrantes c={c} alCambiar={cargar} />}
          {pestana === "reglas" && (
            <section className="tarjeta bloque">
              {c.reglas ? <div className="reglas-comunidad"><TextoEnriquecido texto={c.reglas} /></div> : <p className="tenue">Esta comunidad no ha escrito reglas propias.</p>}
              <p className="tenue reglas-comunidad__nota">Además de sus reglas, aquí rigen las de Parrhesia: las cifras sobre los indicadores oficiales se leen junto a su dato oficial, igual que en cualquier otro lugar.</p>
            </section>
          )}
          {pestana === "bitacora" && <Bitacora c={c} />}
          {pestana === "administracion" && <Administracion c={c} alCambiar={cargar} />}
        </>
      )}
    </>
  );
}

function PublicacionesComunidad({ c }: { c: Comunidad }) {
  const [pubs, setPubs] = useState<Publicacion[] | null>(null);
  const cargar = useCallback(() => {
    api<{ publicaciones: Publicacion[] }>(`/social/v1/comunidades/${c.id}/publicaciones`).then((r) => setPubs(r.publicaciones)).catch(() => setPubs([]));
  }, [c.id]);
  useEffect(cargar, [cargar]);
  useAlPublicar(cargar);
  const moderar = async (accion: "fijar" | "desfijar" | "retirar", pub: Publicacion) => {
    const ruta = accion === "retirar" ? `/social/v1/publicaciones/${pub.id}` : `/social/v1/publicaciones/${pub.id}/fijada`;
    try {
      await api(ruta, { metodo: accion === "fijar" ? "PUT" : "DELETE" });
      cargar();
    } catch (e) { alert(mensaje(e, "No se pudo completar la acción.")); }
  };
  if (pubs === null) return <span className="cargando"><i /><i /><i /></span>;
  if (pubs.length === 0) return <p className="tenue">Aún no hay publicaciones en esta comunidad.</p>;
  return (
    <div className="lista-publicaciones">
      {pubs.map((pub) => (
        <div key={`${pub.id}-${pub.fijada}`}>
          <TarjetaPublicacion publicacion={pub} />
          {c.permisos?.moderar && (
            <div className="moderacion" role="group" aria-label="Moderación">
              <button className="boton-texto" onClick={() => moderar(pub.fijada ? "desfijar" : "fijar", pub)}>{pub.fijada ? "Desfijar" : "Fijar"}</button>
              <button className="boton-texto" onClick={() => { if (confirm("¿Retirar esta publicación de la comunidad? Quedará en la bitácora.")) moderar("retirar", pub); }}>Retirar</button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

interface Integrante { nombre_usuario: string; nombre_visible: string; foto: string | null; papel: Papel; desde: string }

function Integrantes({ c, alCambiar }: { c: Comunidad; alCambiar: () => void }) {
  const { usuario } = useSesion();
  const [lista, setLista] = useState<Integrante[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cargar = useCallback(() => {
    api<{ integrantes: Integrante[] }>(`/social/v1/comunidades/${c.id}/integrantes`).then((r) => setLista(r.integrantes)).catch(() => setLista([]));
  }, [c.id]);
  useEffect(cargar, [cargar]);
  const papel = async (i: Integrante, nuevo: Papel) => {
    setError(null);
    try { await api(`/social/v1/comunidades/${c.id}/integrantes/${i.nombre_usuario}/papel`, { metodo: "PUT", cuerpo: { papel: nuevo } }); cargar(); alCambiar(); }
    catch (e) { setError(mensaje(e, "No se pudo cambiar el papel.")); }
  };
  const expulsar = async (i: Integrante) => {
    const motivo = prompt(`Motivo para expulsar a @${i.nombre_usuario} (queda en la bitácora, al menos 10 caracteres):`);
    if (!motivo) return;
    setError(null);
    try { await api(`/social/v1/comunidades/${c.id}/expulsiones`, { metodo: "POST", cuerpo: { nombre_usuario: i.nombre_usuario, motivo } }); cargar(); alCambiar(); }
    catch (e) { setError(mensaje(e, "No se pudo expulsar.")); }
  };
  if (lista === null) return <span className="cargando"><i /><i /><i /></span>;
  const p = c.permisos!;
  return (
    <section className="tarjeta bloque">
      {error && <p className="aviso" role="alert">{error}</p>}
      <ul className="integrantes">
        {lista.map((i) => {
          const soyYo = usuario?.nombre_usuario === i.nombre_usuario;
          const puedoExpulsar = p.gestionar_integrantes && !soyYo && (c.mi_papel === "administrador" || !["gestor", "administrador"].includes(i.papel));
          return (
            <li key={i.nombre_usuario}>
              <Link to={`/perfil/${i.nombre_usuario}`} className="persona__quien">
                <Avatar nombre={i.nombre_visible} foto={i.foto} />
                <span><strong>{i.nombre_visible}</strong><small className="tenue">@{i.nombre_usuario} · desde {haceCuanto(i.desde)}</small></span>
              </Link>
              <span className="integrantes__acciones">
                {p.configurar ? (
                  <select value={i.papel} onChange={(e) => papel(i, e.target.value as Papel)} aria-label={`Papel de @${i.nombre_usuario}`}>
                    {(Object.keys(PAPEL) as Papel[]).map((k) => <option key={k} value={k}>{PAPEL[k]}</option>)}
                  </select>
                ) : <span className="integrantes__papel">{PAPEL[i.papel]}</span>}
                {puedoExpulsar && <button className="boton-texto" onClick={() => expulsar(i)}>Expulsar</button>}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

interface Registro { accion: string; actor: string; afectado: string | null; publicacion_id: string | null; motivo: string | null; datos: Record<string, unknown>; creada_en: string }

function frase(r: Registro): string {
  const quien = `@${r.actor}`, a = r.afectado ? `@${r.afectado}` : "";
  switch (r.accion) {
    case "creada": return `${quien} creó la comunidad`;
    case "configurada": return `${quien} cambió la configuración${r.datos.privacidad ? ` (ahora es ${r.datos.privacidad === "privada" ? "privada" : "pública"})` : ""}`;
    case "ingreso": return `${quien} entró a la comunidad`;
    case "salida": return `${quien} salió de la comunidad`;
    case "solicitud_aceptada": return `${quien} aceptó la solicitud de ${a}`;
    case "solicitud_rechazada": return `${quien} rechazó la solicitud de ${a}`;
    case "papel_asignado": return `${quien} asignó a ${a} el papel de ${PAPEL[(r.datos.papel as Papel) ?? "integrante"].toLowerCase()}`;
    case "expulsion": return `${quien} expulsó a ${a}`;
    case "publicacion_fijada": return `${quien} fijó una publicación`;
    case "publicacion_desfijada": return `${quien} desfijó una publicación`;
    case "publicacion_retirada": return `${quien} retiró una publicación de ${a}`;
    default: return `${quien}: ${r.accion}`;
  }
}

function Bitacora({ c }: { c: Comunidad }) {
  const [lista, setLista] = useState<Registro[] | null>(null);
  useEffect(() => { api<{ bitacora: Registro[] }>(`/social/v1/comunidades/${c.id}/bitacora`).then((r) => setLista(r.bitacora)).catch(() => setLista([])); }, [c.id]);
  if (lista === null) return <span className="cargando"><i /><i /><i /></span>;
  return (
    <section className="tarjeta bloque">
      <p className="tenue bitacora__nota">Todo lo que hacen quienes administran y moderan queda aquí, a la vista. No se puede borrar.</p>
      <ol className="bitacora">
        {lista.map((r, i) => (
          <li key={i}>
            <span>{frase(r)}{r.publicacion_id && <> · <Link to={`/publicacion/${r.publicacion_id}`} className="marca-texto">ver</Link></>}</span>
            {r.motivo && <span className="bitacora__motivo">Motivo: {r.motivo}</span>}
            <time className="tenue" dateTime={r.creada_en}>{haceCuanto(r.creada_en)}</time>
          </li>
        ))}
      </ol>
    </section>
  );
}

interface Solicitud { id: string; nombre_usuario: string; nombre_visible: string; foto: string | null; mensaje: string | null; creada_en: string }

function Administracion({ c, alCambiar }: { c: Comunidad; alCambiar: () => void }) {
  const p = c.permisos!;
  const [solicitudes, setSolicitudes] = useState<Solicitud[] | null>(null);
  const [datos, setDatos] = useState({ nombre: c.nombre, descripcion: c.descripcion, reglas: c.reglas ?? "", privacidad: c.privacidad });
  const [aviso, setAviso] = useState<{ ok: boolean; texto: string } | null>(null);
  const cargar = useCallback(() => {
    if (p.gestionar_integrantes) api<{ solicitudes: Solicitud[] }>(`/social/v1/comunidades/${c.id}/solicitudes`).then((r) => setSolicitudes(r.solicitudes)).catch(() => setSolicitudes([]));
  }, [c.id, p.gestionar_integrantes]);
  useEffect(cargar, [cargar]);
  const resolver = async (s: Solicitud, aceptar: boolean) => {
    try { await api(`/social/v1/comunidades/${c.id}/solicitudes/${s.id}/resolucion`, { metodo: "POST", cuerpo: { aceptar } }); cargar(); alCambiar(); }
    catch (e) { setAviso({ ok: false, texto: mensaje(e, "No se pudo resolver la solicitud.") }); }
  };
  const guardar = async (e: FormEvent) => {
    e.preventDefault();
    setAviso(null);
    try {
      await api(`/social/v1/comunidades/${c.id}`, { metodo: "PATCH", cuerpo: {
        nombre: datos.nombre !== c.nombre ? datos.nombre : null,
        descripcion: datos.descripcion !== c.descripcion ? datos.descripcion : null,
        reglas: datos.reglas !== (c.reglas ?? "") ? datos.reglas : null,
        privacidad: datos.privacidad !== c.privacidad ? datos.privacidad : null,
      } });
      setAviso({ ok: true, texto: "Configuración guardada." });
      alCambiar();
    } catch (err) { setAviso({ ok: false, texto: mensaje(err, "No se pudo guardar.") }); }
  };
  const subirImagen = async (archivo?: File) => {
    if (!archivo) return;
    const f = new FormData();
    f.append("imagen", archivo);
    try { await api(`/social/v1/comunidades/${c.id}/imagen`, { metodo: "PUT", cuerpo: f }); alCambiar(); }
    catch (e) { setAviso({ ok: false, texto: mensaje(e, "No se pudo subir la imagen.") }); }
  };
  return (
    <div className="administracion">
      {aviso && <p className={aviso.ok ? "panel-cuenta__ok" : "aviso"} role={aviso.ok ? "status" : "alert"}>{aviso.texto}</p>}
      {p.gestionar_integrantes && (
        <section className="tarjeta bloque">
          <h2 className="subtitulo">Solicitudes de ingreso</h2>
          {solicitudes?.length === 0 && <p className="tenue">No hay solicitudes pendientes.</p>}
          <ul className="integrantes">
            {solicitudes?.map((s) => (
              <li key={s.id}>
                <Link to={`/perfil/${s.nombre_usuario}`} className="persona__quien">
                  <Avatar nombre={s.nombre_visible} foto={s.foto} />
                  <span><strong>{s.nombre_visible}</strong><small className="tenue">@{s.nombre_usuario} · {haceCuanto(s.creada_en)}</small>
                    {s.mensaje && <span className="persona__bio">«{s.mensaje}»</span>}</span>
                </Link>
                <span className="integrantes__acciones">
                  <button className="boton boton--pequeno" onClick={() => resolver(s, true)}>Aceptar</button>
                  <button className="boton-texto" onClick={() => resolver(s, false)}>Rechazar</button>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {p.configurar && (
        <section className="tarjeta bloque">
          <h2 className="subtitulo">Configuración</h2>
          <div className="panel-cuenta__foto">
            <Simbolo c={c} grande />
            <label className="boton boton--borde boton--pequeno">Cambiar imagen
              <input type="file" accept="image/jpeg,image/png,image/webp" className="oculto-visual" onChange={(e) => { subirImagen(e.target.files?.[0]); e.target.value = ""; }} />
            </label>
          </div>
          <form className="panel-cuenta__campos" onSubmit={guardar}>
            <label className="campo-cuenta"><span>Nombre</span><input value={datos.nombre} onChange={(e) => setDatos({ ...datos, nombre: e.target.value })} minLength={3} maxLength={60} required /></label>
            <label className="campo-cuenta"><span>Descripción</span><textarea value={datos.descripcion} onChange={(e) => setDatos({ ...datos, descripcion: e.target.value })} minLength={10} maxLength={500} rows={3} required /></label>
            <label className="campo-cuenta"><span>Reglas</span><textarea value={datos.reglas} onChange={(e) => setDatos({ ...datos, reglas: e.target.value })} maxLength={2000} rows={4} /></label>
            <fieldset className="opciones-privacidad">
              <legend>Privacidad</legend>
              {(["publica", "privada"] as const).map((v) => (
                <label key={v} className={datos.privacidad === v ? "elegida" : ""}>
                  <input type="radio" name="privacidad-config" checked={datos.privacidad === v} onChange={() => setDatos({ ...datos, privacidad: v })} />
                  <strong>{v === "publica" ? "Pública" : "Privada"}</strong>
                </label>
              ))}
            </fieldset>
            <button className="boton">Guardar configuración</button>
          </form>
        </section>
      )}
    </div>
  );
}
