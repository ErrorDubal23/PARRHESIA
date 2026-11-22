// Figuras públicas: fichas con fuente oficial para cada dato, sus declaraciones verificadas y la bitácora
// de cambios. Solo verificadores y administradores crean y editan; cualquiera puede proponer una figura.
// El partido es un dato público con su fuente: nunca se usa para agrupar, colorear ni contar lados.
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ErrorApi, haceCuanto } from "../api";
import { Avatar } from "../componentes/Avatar";
import * as I from "../componentes/Iconos";
import { comoFallo, MostrarFallo, type Fallo } from "../componentes/NoEncontrado";
import { PanelVerificacion } from "../componentes/PanelVerificacion";
import { useIrAEntrar, useSesion } from "../sesion";

export interface Figura {
  id: string; nombre_completo: string; cargo: string | null; url_fuente_cargo: string | null; cargo_desde: string | null;
  cargo_hasta: string | null; partido: string | null; url_fuente_partido: string | null; foto: string | null; estado: "activa" | "archivada";
}
type Declaracion = { id: string; texto: string; dicha_el: string; tipo: string; url_fuente: string; estado_promesa: string | null; etiquetas: string[] };

const mensaje = (e: unknown, defecto: string) => (e instanceof ErrorApi ? e.message : defecto);
const fechaCorta = (d: string) => new Date(`${d}T12:00`).toLocaleDateString("es-CO", { month: "short", year: "numeric" });
const fecha = (d: string) => new Date(`${d}T12:00`).toLocaleDateString("es-CO", { day: "numeric", month: "long", year: "numeric" });
const dominio = (url: string) => { try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; } };

function Fuente({ url }: { url: string | null }) {
  if (!url) return null;
  return <a href={url} target="_blank" rel="noopener noreferrer" className="enlace-externo enlace-fuente">fuente<span className="enlace-externo__dominio">{dominio(url)}</span></a>;
}

function useDialogo(abierto: boolean) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (abierto && d && !d.open) d.showModal();
    if (!abierto && d?.open) d.close();
  }, [abierto]);
  return ref;
}

/** Aviso de fichas con nombre parecido mientras se escribe (para no crear duplicados). */
function Parecidas({ nombre, excluir }: { nombre: string; excluir?: string }) {
  const [lista, setLista] = useState<{ id: string; nombre_completo: string; cargo: string | null }[]>([]);
  useEffect(() => {
    if (nombre.trim().length < 3) return setLista([]);
    const t = setTimeout(() => {
      api<{ parecidas: typeof lista }>(`/social/v1/figuras/parecidas?nombre=${encodeURIComponent(nombre)}`)
        .then((r) => setLista(r.parecidas.filter((p) => p.id !== excluir))).catch(() => {});
    }, 300);
    return () => clearTimeout(t);
  }, [nombre, excluir]);
  if (!lista.length) return null;
  return (
    <p className="aviso" role="status">
      Ya hay fichas con un nombre parecido:{" "}
      {lista.map((p, i) => <span key={p.id}>{i > 0 && ", "}<Link to={`/figuras/${p.id}`} className="marca-texto">{p.nombre_completo}</Link>{p.cargo && ` (${p.cargo})`}</span>)}.
      Revisa que no sea la misma persona.
    </p>
  );
}

export function Figuras() {
  const { usuario } = useSesion();
  const irAEntrar = useIrAEntrar();
  const gestiona = usuario?.rol === "verificador" || usuario?.rol === "admin";
  const [figuras, setFiguras] = useState<Figura[] | null>(null);
  const [archivadas, setArchivadas] = useState(false);
  const [formulario, setFormulario] = useState<"crear" | "proponer" | null>(null);
  const cargar = useCallback(() => {
    api<{ figuras: Figura[] }>(`/social/v1/figuras${archivadas ? "?archivadas=true" : ""}`).then((r) => setFiguras(r.figuras)).catch(() => setFiguras([]));
  }, [archivadas]);
  useEffect(cargar, [cargar]);
  return (
    <>
      <div className="cabecera-seccion">
        <div>
          <h1 className="titulo-seccion">Figuras públicas</h1>
          <p className="tenue intro">Declaraciones con su fuente y, para cada cifra, el dato oficial. La misma regla para todas.</p>
        </div>
        <button className="boton" onClick={() => (!usuario ? irAEntrar() : setFormulario(gestiona ? "crear" : "proponer"))}>
          {gestiona ? "Registrar figura" : "Proponer una figura"}
        </button>
      </div>
      {gestiona && (
        <label className="casilla filtro-archivadas">
          <input type="checkbox" checked={archivadas} onChange={(e) => setArchivadas(e.target.checked)} /> <span>Mostrar también las archivadas</span>
        </label>
      )}
      {figuras?.length === 0 && <p className="tenue">Todavía no hay figuras públicas registradas.</p>}
      <div className="figuras">
        {figuras?.map((f) => (
          <Link key={f.id} to={`/figuras/${f.id}`} className={`carpeta${f.estado === "archivada" ? " figura--archivada" : ""}`}>
            <span className="carpeta__pestana">{f.estado === "archivada" ? "Archivada" : "Ficha pública"}</span>
            <span className="carpeta__hoja">
              <Avatar nombre={f.nombre_completo} foto={f.foto} />
              <strong>{f.nombre_completo}</strong>
              {f.cargo && <span>{f.cargo}</span>}
            </span>
            <span className="carpeta__solapa">
              <small>{f.cargo_hasta ? `Hasta ${fechaCorta(f.cargo_hasta)}` : f.cargo_desde ? `En el cargo desde ${fechaCorta(f.cargo_desde)}` : "Cargo con fuente oficial"}</small>
              <I.Flecha width={15} />
            </span>
          </Link>
        ))}
      </div>
      <FormularioFigura abierto={formulario === "crear"} cerrar={() => setFormulario(null)} alGuardar={cargar} />
      <ProponerFigura abierto={formulario === "proponer"} cerrar={() => setFormulario(null)} />
    </>
  );
}

const VACIA = { nombre_completo: "", cargo: "", url_fuente_cargo: "https://", cargo_desde: "", cargo_hasta: "", partido: "", url_fuente_partido: "", motivo: "" };

function FormularioFigura({ abierto, cerrar, alGuardar, figura }: { abierto: boolean; cerrar: () => void; alGuardar: () => void; figura?: Figura }) {
  const ref = useDialogo(abierto);
  const inicial = figura ? {
    nombre_completo: figura.nombre_completo, cargo: figura.cargo ?? "", url_fuente_cargo: figura.url_fuente_cargo ?? "https://",
    cargo_desde: figura.cargo_desde ?? "", cargo_hasta: figura.cargo_hasta ?? "", partido: figura.partido ?? "",
    url_fuente_partido: figura.url_fuente_partido ?? "", motivo: "" } : VACIA;
  const [d, setD] = useState(inicial);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (abierto) { setD(inicial); setError(null); } }, [abierto]); // eslint-disable-line react-hooks/exhaustive-deps
  const campo = (k: keyof typeof d) => ({ value: d[k], onChange: (e: { target: { value: string } }) => setD({ ...d, [k]: e.target.value }) });
  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const cuerpo = {
      nombre_completo: d.nombre_completo, cargo: d.cargo, url_fuente_cargo: d.url_fuente_cargo,
      cargo_desde: d.cargo_desde || null, cargo_hasta: d.cargo_hasta || null,
      partido: figura ? d.partido : d.partido || null, url_fuente_partido: d.url_fuente_partido || null,
      ...(figura ? { motivo: d.motivo || null } : {}),
    };
    try {
      await api(figura ? `/social/v1/figuras/${figura.id}` : "/social/v1/figuras", { metodo: figura ? "PATCH" : "POST", cuerpo });
      alGuardar();
      cerrar();
    } catch (err) { setError(mensaje(err, "No se pudo guardar la ficha.")); }
  };
  return (
    <dialog ref={ref} className="compositor" onClose={cerrar} aria-labelledby="titulo-figura">
      <form className="compositor__cuerpo" onSubmit={enviar}>
        <div className="compositor__cabecera">
          <h2 id="titulo-figura">{figura ? "Editar ficha" : "Registrar figura pública"}</h2>
          <button type="button" className="boton-texto" onClick={cerrar}>Cerrar</button>
        </div>
        <label className="campo-cuenta"><span>Nombre completo</span><input {...campo("nombre_completo")} minLength={3} maxLength={120} required /></label>
        {abierto && <Parecidas nombre={d.nombre_completo} excluir={figura?.id} />}
        <div className="campos-dobles">
          <label className="campo-cuenta"><span>Cargo actual</span><input {...campo("cargo")} minLength={2} maxLength={160} required placeholder="Por ejemplo, Ministra de Trabajo" /></label>
          <label className="campo-cuenta"><span>Fuente oficial del cargo</span><input {...campo("url_fuente_cargo")} type="url" pattern="https://.+" required /></label>
        </div>
        <div className="campos-dobles">
          <label className="campo-cuenta"><span>En el cargo desde (opcional)</span><input {...campo("cargo_desde")} type="date" /></label>
          <label className="campo-cuenta"><span>Hasta (opcional)</span><input {...campo("cargo_hasta")} type="date" /></label>
        </div>
        <div className="campos-dobles">
          <label className="campo-cuenta"><span>Partido o movimiento (opcional)</span><input {...campo("partido")} maxLength={120} /></label>
          <label className="campo-cuenta"><span>Fuente oficial del partido</span><input {...campo("url_fuente_partido")} type="url" pattern="https://.+" required={!!d.partido.trim()} /></label>
        </div>
        {figura && <label className="campo-cuenta"><span>Motivo del cambio (queda en la bitácora)</span><input {...campo("motivo")} maxLength={500} /></label>}
        <p className="compositor__nota">Cada dato necesita una fuente oficial (https). El partido es un dato público: no se usa para agrupar ni contar lados.</p>
        {error && <p className="aviso" role="alert">{error}</p>}
        <div className="compositor__pie"><span className="editor__espacio" /><button className="boton">{figura ? "Guardar cambios" : "Registrar"}</button></div>
      </form>
    </dialog>
  );
}

function ProponerFigura({ abierto, cerrar }: { abierto: boolean; cerrar: () => void }) {
  const ref = useDialogo(abierto);
  const [d, setD] = useState({ nombre_completo: "", cargo: "", url_fuente: "https://", nota: "" });
  const [estado, setEstado] = useState<{ ok: boolean; texto: string } | null>(null);
  useEffect(() => { if (abierto) setEstado(null); }, [abierto]);
  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api("/social/v1/propuestas-figura", { metodo: "POST", cuerpo: { ...d, nota: d.nota || null } });
      setEstado({ ok: true, texto: "Propuesta enviada. El equipo de verificación la revisará." });
      setD({ nombre_completo: "", cargo: "", url_fuente: "https://", nota: "" });
    } catch (err) { setEstado({ ok: false, texto: mensaje(err, "No se pudo enviar la propuesta.") }); }
  };
  return (
    <dialog ref={ref} className="compositor" onClose={cerrar} aria-labelledby="titulo-proponer">
      <form className="compositor__cuerpo" onSubmit={enviar}>
        <div className="compositor__cabecera">
          <h2 id="titulo-proponer">Proponer una figura pública</h2>
          <button type="button" className="boton-texto" onClick={cerrar}>Cerrar</button>
        </div>
        <p className="tenue">Solo personas con un cargo público o una función pública reconocida. El equipo de verificación revisa cada propuesta.</p>
        <label className="campo-cuenta"><span>Nombre completo</span><input value={d.nombre_completo} onChange={(e) => setD({ ...d, nombre_completo: e.target.value })} minLength={3} maxLength={120} required /></label>
        {abierto && <Parecidas nombre={d.nombre_completo} />}
        <label className="campo-cuenta"><span>Cargo</span><input value={d.cargo} onChange={(e) => setD({ ...d, cargo: e.target.value })} minLength={2} maxLength={160} required /></label>
        <label className="campo-cuenta"><span>Fuente oficial del cargo</span><input value={d.url_fuente} onChange={(e) => setD({ ...d, url_fuente: e.target.value })} type="url" pattern="https://.+" required /></label>
        <label className="campo-cuenta"><span>Nota para el equipo (opcional)</span><textarea value={d.nota} onChange={(e) => setD({ ...d, nota: e.target.value })} maxLength={500} rows={2} /></label>
        {estado && <p className={estado.ok ? "panel-cuenta__ok" : "aviso"} role={estado.ok ? "status" : "alert"}>{estado.texto}</p>}
        <div className="compositor__pie"><span className="editor__espacio" /><button className="boton">Enviar propuesta</button></div>
      </form>
    </dialog>
  );
}

type Cambio = { accion: string; actor: string; cambios: Record<string, unknown>; motivo: string | null; creada_en: string };
const CAMPO: Record<string, string> = {
  nombre_completo: "nombre", cargo: "cargo", url_fuente_cargo: "fuente del cargo", cargo_desde: "inicio del cargo",
  cargo_hasta: "fin del cargo", partido: "partido", url_fuente_partido: "fuente del partido", estado: "estado",
};
const ACCION: Record<string, string> = {
  creada: "creó la ficha", editada: "editó la ficha", archivada: "archivó la ficha", reactivada: "reactivó la ficha", foto: "cambió la foto",
};

export function FiguraPagina() {
  const { id } = useParams();
  const { usuario } = useSesion();
  const gestiona = usuario?.rol === "verificador" || usuario?.rol === "admin";
  const [figura, setFigura] = useState<(Figura & { declaraciones: Declaracion[] }) | null>(null);
  const [bitacora, setBitacora] = useState<Cambio[]>([]);
  const [fallo, setFallo] = useState<Fallo | null>(null);
  const [editando, setEditando] = useState(false);
  const [declarando, setDeclarando] = useState(false);
  const cargar = useCallback(() => {
    api<typeof figura>(`/social/v1/figuras/${id}`).then(setFigura).catch((e) => setFallo(comoFallo(e)));
    api<{ bitacora: Cambio[] }>(`/social/v1/figuras/${id}/bitacora`).then((r) => setBitacora(r.bitacora)).catch(() => {});
  }, [id]);
  useEffect(() => { setFallo(null); cargar(); }, [cargar]);
  if (fallo) return <MostrarFallo fallo={fallo} titulo="Esta figura pública no está registrada." />;
  if (!figura) return <span className="cargando"><i /><i /><i /></span>;

  const subirFoto = async (archivo?: File) => {
    if (!archivo) return;
    const f = new FormData();
    f.append("foto", archivo);
    try { await api(`/social/v1/figuras/${figura.id}/foto`, { metodo: "PUT", cuerpo: f }); cargar(); }
    catch (e) { alert(mensaje(e, "No se pudo subir la foto.")); }
  };
  const archivar = async () => {
    const motivo = prompt(figura.estado === "activa" ? "Motivo para archivar la ficha (queda en la bitácora):" : "Motivo para reactivar la ficha:");
    if (motivo === null) return;
    try { await api(`/social/v1/figuras/${figura.id}`, { metodo: "PATCH", cuerpo: { estado: figura.estado === "activa" ? "archivada" : "activa", motivo } }); cargar(); }
    catch (e) { alert(mensaje(e, "No se pudo cambiar el estado.")); }
  };

  return (
    <>
      <Link to="/figuras" className="volver"><I.Volver width={18} /> Figuras públicas</Link>
      <section className="perfil tarjeta ficha-figura">
        <Avatar nombre={figura.nombre_completo} foto={figura.foto} grande />
        <div>
          <h1>{figura.nombre_completo}</h1>
          {figura.estado === "archivada" && <p className="aviso">Ficha archivada: se conserva con sus declaraciones, pero ya no aparece en el listado.</p>}
          <dl className="ficha-figura__datos">
            {figura.cargo && (
              <div><dt>Cargo</dt><dd>{figura.cargo} <Fuente url={figura.url_fuente_cargo} />
                {(figura.cargo_desde || figura.cargo_hasta) && <small className="tenue"> · {figura.cargo_desde ? `desde ${fecha(figura.cargo_desde)}` : ""}{figura.cargo_hasta ? ` hasta ${fecha(figura.cargo_hasta)}` : ""}</small>}
              </dd></div>
            )}
            {figura.partido && <div><dt>Partido o movimiento</dt><dd>{figura.partido} <Fuente url={figura.url_fuente_partido} /></dd></div>}
          </dl>
        </div>
        {gestiona && (
          <div className="ficha-figura__acciones">
            <button className="boton boton--pequeno" onClick={() => setDeclarando(true)}>Registrar declaración</button>
            <button className="boton boton--borde boton--pequeno" onClick={() => setEditando(true)}>Editar ficha</button>
            <label className="boton-texto">Cambiar foto
              <input type="file" accept="image/jpeg,image/png,image/webp" className="oculto-visual" onChange={(e) => { subirFoto(e.target.files?.[0]); e.target.value = ""; }} />
            </label>
            <button className="boton-texto" onClick={archivar}>{figura.estado === "activa" ? "Archivar" : "Reactivar"}</button>
          </div>
        )}
      </section>

      <h2 className="subtitulo">Declaraciones</h2>
      {figura.declaraciones.length === 0 && <p className="tenue">Todavía no hay declaraciones registradas.</p>}
      {figura.declaraciones.map((d) => (
        <article key={d.id} className="tarjeta declaracion">
          <p className="declaracion__quien">
            <span className="sello">{d.tipo === "promesa" ? `Promesa · ${d.estado_promesa?.replace("_", " ")}` : "Declaración"}</span>
            <span className="tenue">{fecha(d.dicha_el)}</span>
            <a href={d.url_fuente} target="_blank" rel="noopener noreferrer" className="enlace-suave">Fuente <I.Enlace width={13} /></a>
          </p>
          <blockquote>«{d.texto}»</blockquote>
          {d.etiquetas.length > 0 && <p>{d.etiquetas.map((e) => <Link key={e} to={`/tendencias/${e}`} className="marca-texto">#{e} </Link>)}</p>}
          <PanelVerificacion tipo="declaracion" id={d.id} />
        </article>
      ))}

      {bitacora.length > 0 && (
        <section className="tarjeta bloque">
          <h2 className="subtitulo">Cambios en esta ficha</h2>
          <ol className="bitacora">
            {bitacora.map((b, i) => (
              <li key={i}>
                <span>
                  @{b.actor} {ACCION[b.accion] ?? b.accion}
                  {b.accion !== "creada" && Object.entries(b.cambios).filter(([k]) => CAMPO[k]).map(([k, v]) => {
                    const c = v as { antes: unknown; despues: unknown };
                    return <span key={k} className="bitacora__cambio"> · {CAMPO[k]}: {String(c.antes ?? "—")} → {String(c.despues ?? "—")}</span>;
                  })}
                </span>
                {b.motivo && <span className="bitacora__motivo">Motivo: {b.motivo}</span>}
                <time className="tenue" dateTime={b.creada_en}>{haceCuanto(b.creada_en)}</time>
              </li>
            ))}
          </ol>
        </section>
      )}
      {gestiona && <FormularioFigura abierto={editando} cerrar={() => setEditando(false)} alGuardar={cargar} figura={figura} />}
      {gestiona && <RegistrarDeclaracion abierto={declarando} cerrar={() => setDeclarando(false)} figura={figura} alGuardar={cargar} />}
    </>
  );
}

function RegistrarDeclaracion({ abierto, cerrar, figura, alGuardar }: { abierto: boolean; cerrar: () => void; figura: Figura; alGuardar: () => void }) {
  const ref = useDialogo(abierto);
  const [d, setD] = useState({ texto: "", dicha_el: "", tipo: "declaracion", url_fuente: "https://", etiquetas: "" });
  const [error, setError] = useState<string | null>(null);
  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api(`/social/v1/figuras/${figura.id}/declaraciones`, { metodo: "POST", cuerpo: {
        texto: d.texto, dicha_el: d.dicha_el, tipo: d.tipo, url_fuente: d.url_fuente,
        etiquetas: d.etiquetas.split(/[\s,]+/).map((x) => x.replace(/^#/, "").toLowerCase()).filter(Boolean),
      } });
      setD({ texto: "", dicha_el: "", tipo: "declaracion", url_fuente: "https://", etiquetas: "" });
      alGuardar();
      cerrar();
    } catch (err) { setError(mensaje(err, "No se pudo registrar la declaración.")); }
  };
  return (
    <dialog ref={ref} className="compositor" onClose={cerrar} aria-labelledby="titulo-declaracion">
      <form className="compositor__cuerpo" onSubmit={enviar}>
        <div className="compositor__cabecera">
          <h2 id="titulo-declaracion">Declaración de {figura.nombre_completo}</h2>
          <button type="button" className="boton-texto" onClick={cerrar}>Cerrar</button>
        </div>
        <label className="campo-cuenta"><span>Lo que dijo, textual</span><textarea value={d.texto} onChange={(e) => setD({ ...d, texto: e.target.value })} rows={4} maxLength={2000} required /></label>
        <div className="campos-dobles">
          <label className="campo-cuenta"><span>Fecha</span><input type="date" value={d.dicha_el} onChange={(e) => setD({ ...d, dicha_el: e.target.value })} required /></label>
          <label className="campo-cuenta"><span>Tipo</span>
            <select value={d.tipo} onChange={(e) => setD({ ...d, tipo: e.target.value })}><option value="declaracion">Declaración</option><option value="promesa">Promesa</option></select></label>
        </div>
        <label className="campo-cuenta"><span>Fuente (video, transcripción o nota de prensa)</span><input type="url" value={d.url_fuente} onChange={(e) => setD({ ...d, url_fuente: e.target.value })} pattern="https?://.+" required /></label>
        <label className="campo-cuenta"><span>Etiquetas (opcional)</span><input value={d.etiquetas} onChange={(e) => setD({ ...d, etiquetas: e.target.value })} placeholder="#desempleo #inflacion" /></label>
        <p className="compositor__nota">Si la declaración cita una cifra de los 8 indicadores, se verifica sola con la misma regla que cualquier publicación.</p>
        {error && <p className="aviso" role="alert">{error}</p>}
        <div className="compositor__pie"><span className="editor__espacio" /><button className="boton">Registrar</button></div>
      </form>
    </dialog>
  );
}
