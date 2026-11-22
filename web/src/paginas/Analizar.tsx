// Análisis de enlaces externos (decisión 29): una noticia vista en otra red pasa por el mismo motor.
// La página se lee en memoria; solo quedan los metadatos que ella declara y las citas cortas con cifras.
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useAnalisis } from "../componentes/AnalisisEnCurso";
import { alAzar, ENLACES, MODO_DEMO, TEXTOS } from "../datos/demostracion";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ErrorApi, haceCuanto } from "../api";
import { PanelVerificacion } from "../componentes/PanelVerificacion";
import * as I from "../componentes/Iconos";
import { useIrAEntrar, useSesion } from "../sesion";

interface Fragmento { id: string; posicion: number; texto: string; estado: string }
interface Enlace {
  id: string; url: string | null; dominio: string | null; titulo: string | null; sitio: string | null;
  autor_declarado: string | null; publicado_declarado: string | null; creado_en: string; estado: string;
  fragmentos: Fragmento[];
}

export function Analizar() {
  const { usuario } = useSesion();
  const irAEntrar = useIrAEntrar();
  const navegar = useNavigate();
  const [modo, setModo] = useState<"url" | "texto">("url");
  const [valor, setValor] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const { iniciar } = useAnalisis();
  // El análisis lo lleva la app (AnalisisEnCurso): si la persona se va a otra página, sigue y avisa al terminar.
  const abierta = useRef(true);
  useEffect(() => () => { abierta.current = false; }, []);

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    if (!usuario) return irAEntrar();
    setEnviando(true);
    setError(null);
    try {
      const id = await iniciar(modo === "url" ? { url: valor.trim() } : { texto: valor.trim() });
      if (abierta.current) navegar(`/analizar/${id}`);
    } catch (err) {
      const mensaje = err instanceof ErrorApi ? err.message : "No se pudo analizar. Revisa tu conexión.";
      setError(mensaje);
      if (modo === "url" && err instanceof ErrorApi && ["red_cerrada", "robots", "ilegible"].includes(err.codigo)) {
        setModo("texto");   // se pide el texto: el campo queda listo para pegarlo
        setValor("");
      }
    } finally {
      if (abierta.current) setEnviando(false);
    }
  };

  return (
    <section>
      <h1 className="titulo-seccion">Analizar un enlace</h1>
      <p className="tenue analizar__ayuda">
        Pega una noticia que viste en otra red o portal. Leemos la página una vez, sin guardarla: solo quedan las
        frases con cifras de los 8 indicadores, y cada una pasa por el mismo motor que las publicaciones.
      </p>
      <div className="pestanas" role="tablist">
        <button role="tab" aria-selected={modo === "url"} onClick={() => { setModo("url"); setValor(""); }}>Enlace</button>
        <button role="tab" aria-selected={modo === "texto"} onClick={() => { setModo("texto"); setValor(""); }}>Texto</button>
      </div>
      <form className="tarjeta analizar__formulario" onSubmit={enviar}>
        {modo === "url" ? (
          <label className="campo-cuenta"><span>Enlace de la noticia</span>
            <input type="url" value={valor} onChange={(e) => setValor(e.target.value)} placeholder="https://…" required pattern="https?://.+" maxLength={2000} />
          </label>
        ) : (
          <label className="campo-cuenta"><span>Texto de la publicación o noticia</span>
            <textarea value={valor} onChange={(e) => setValor(e.target.value)} rows={7} minLength={20} maxLength={20000} required
              placeholder="Copia y pega aquí el texto (las redes como X, Facebook o Instagram no permiten leerlo automáticamente)." />
          </label>
        )}
        {error && <p className="aviso" role="alert">{error}</p>}
        <div className="analizar__acciones">
          {MODO_DEMO && (
            <button type="button" className="boton boton--borde" title="Modo demostración: llena el campo con un ejemplo; tú decides si lo analizas"
              onClick={() => setValor(modo === "url" ? alAzar(ENLACES, ENLACES.find((e) => e.url === valor)).url : alAzar(TEXTOS, valor))}>
              {modo === "url" ? "Noticia de ejemplo" : "Texto de ejemplo"}
            </button>
          )}
          <button className="boton" disabled={enviando || !valor.trim()}>{enviando ? "Leyendo…" : "Analizar"}</button>
        </div>
        {MODO_DEMO && modo === "url" && ENLACES.some((e) => e.url === valor) && (
          <p className="tenue analizar__ejemplo">{(() => { const e = ENLACES.find((x) => x.url === valor)!; return `${e.medio} · ${e.tema}`; })()}</p>
        )}
      </form>
    </section>
  );
}

export function AnalisisPagina() {
  const { id } = useParams();
  const [enlace, setEnlace] = useState<Enlace | null>(null);
  const [falta, setFalta] = useState(false);
  useEffect(() => {
    let vivo = true;
    api<Enlace>(`/verificacion/v1/enlaces/${id}`).then((r) => vivo && setEnlace(r)).catch(() => vivo && setFalta(true));
    return () => { vivo = false; };
  }, [id]);

  if (falta) return <p className="tenue">No existe ese análisis.</p>;
  if (!enlace) return <span className="cargando"><i /><i /><i /></span>;
  return (
    <section>
      <Link to="/analizar" className="volver"><I.Volver width={18} /> Analizar otro</Link>
      <header className="tarjeta analizar__ficha">
        <span className="sello">{enlace.url ? "Según la página" : "Texto pegado"}</span>
        <h1 className="titulo-seccion">{enlace.titulo ?? (enlace.url ? enlace.dominio : "Texto analizado")}</h1>
        <p className="tenue">
          {[enlace.sitio ?? enlace.dominio, enlace.autor_declarado, enlace.publicado_declarado?.slice(0, 10)].filter(Boolean).join(" · ")}
          {enlace.url && <> · <a href={enlace.url} target="_blank" rel="noreferrer noopener" className="enlace-suave">Abrir la página <I.Enlace width={13} /></a></>}
        </p>
        <p className="tenue analizar__nota">
          {enlace.url && "Título, sitio, autor y fecha son los que declara la página; no se verifican. "}Analizado {haceCuanto(enlace.creado_en)}.
        </p>
      </header>
      <h2 className="analizar__subtitulo">Lo que se dijo con cifras <span className="cifra tenue">{enlace.fragmentos.length}</span></h2>
      {enlace.fragmentos.length === 0 && (
        <p className="tenue">No encontramos cifras sobre los 8 indicadores (inflación, desempleo, salario mínimo, deuda pública,
          homicidios, hurtos, extorsión y secuestro). Lo demás es opinión o contexto y no se verifica.</p>
      )}
      {enlace.fragmentos.map((f) => (
        <article key={f.id} className="tarjeta declaracion">
          <blockquote>«{f.texto}»</blockquote>
          <PanelVerificacion tipo="fragmento_enlace" id={f.id} />
        </article>
      ))}
    </section>
  );
}
