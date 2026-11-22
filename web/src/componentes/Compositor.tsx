// Editor de publicaciones: escribir con formato (**negrita**, *cursiva*, [enlace](https://…)),
// mencionar personas y figuras públicas con @, etiquetas con #, contador de lo visible y vista previa.
// El formato son marcas de texto (formato.ts), nunca HTML; el límite de 500 cuenta solo lo visible.
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { alAzar, MODO_DEMO, PUBLICACIONES, RESPUESTAS } from "../datos/demostracion";
import { api, ErrorApi } from "../api";
import { dominioSeguro, MAXIMO_CON_MARCAS, MAXIMO_VISIBLE, textoPlano } from "../formato";
import type { Publicacion } from "../tipos";
import { Avatar } from "./Avatar";
import type { ComunidadDestino } from "./Marco";
import { TextoEnriquecido } from "./TextoEnriquecido";

interface Figura { id: string; nombre_completo: string; cargo?: string | null }
type Sugerencia =
  | { tipo: "persona"; nombre_usuario: string; nombre_visible: string; foto: string | null }
  | { tipo: "figura"; id: string; nombre: string; cargo?: string | null };

const sinTildes = (s: string) => s.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
const esMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);
const atajo = (letra: string) => `${esMac ? "⌘" : "Ctrl+"}${letra}`;

const Icono = ({ d }: { d: string }) => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>
);

export function Compositor({ abierto, cerrar, respondeA, comunidad }: { abierto: boolean; cerrar: () => void; respondeA?: Publicacion | null; comunidad?: ComunidadDestino }) {
  const [texto, setTexto] = useState("");
  const ultimoEjemplo = useRef<(typeof PUBLICACIONES)[number] | undefined>(undefined);
  const [figuras, setFiguras] = useState<Figura[]>([]);
  const [mencionadas, setMencionadas] = useState<Figura[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [vista, setVista] = useState(false);
  const [enlace, setEnlace] = useState<{ url: string; inicio: number; fin: number } | null>(null);
  const [sugerencias, setSugerencias] = useState<Sugerencia[]>([]);
  const [activa, setActiva] = useState(0);
  const [token, setToken] = useState<{ inicio: number; fin: number; consulta: string } | null>(null);
  const dialogo = useRef<HTMLDialogElement>(null);
  const area = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const d = dialogo.current;
    if (!d) return;
    if (abierto && !d.open) {
      d.showModal();
      setError(null);
      setVista(false);
      api<{ figuras: Figura[] }>("/social/v1/figuras").then((r) => setFiguras(r.figuras)).catch(() => {});
    }
    if (!abierto && d.open) d.close();
  }, [abierto]);

  // Autocompletado de @: personas (búsqueda del servidor) y figuras públicas (lista local).
  useEffect(() => {
    if (!token || token.consulta.length < 2) return setSugerencias([]);
    const q = sinTildes(token.consulta);
    const deFiguras: Sugerencia[] = figuras.filter((f) => sinTildes(f.nombre_completo).includes(q)).slice(0, 3)
      .map((f) => ({ tipo: "figura", id: f.id, nombre: f.nombre_completo, cargo: f.cargo }));
    setSugerencias(deFiguras);
    setActiva(0);
    const t = setTimeout(() => {
      api<{ usuarios: { nombre_usuario: string; nombre_visible: string; foto: string | null }[] }>(`/social/v1/usuarios?q=${encodeURIComponent(token.consulta)}&limite=5`)
        .then((r) => setSugerencias([...r.usuarios.map((u) => ({ tipo: "persona" as const, ...u })), ...deFiguras]))
        .catch(() => {});
    }, 220);
    return () => clearTimeout(t);
  }, [token, figuras]);

  const visibles = [...textoPlano(texto).trim()].length; // por caracteres, como length() de PostgreSQL
  const excedido = visibles > MAXIMO_VISIBLE;

  /** Cambia el texto y deja el cursor donde corresponde. */
  const reemplazar = (inicio: number, fin: number, nuevo: string, cursor?: [number, number]) => {
    setTexto((actual) => actual.slice(0, inicio) + nuevo + actual.slice(fin));
    requestAnimationFrame(() => {
      const ta = area.current;
      if (!ta) return;
      ta.focus();
      const [a, b] = cursor ?? [inicio + nuevo.length, inicio + nuevo.length];
      ta.setSelectionRange(a, b);
    });
  };

  /** Negrita o cursiva sobre la selección (los espacios de los bordes quedan fuera de la marca). */
  const envolver = (marca: "**" | "*") => {
    const ta = area.current;
    if (!ta) return;
    const [s, e] = [ta.selectionStart, ta.selectionEnd];
    const sel = texto.slice(s, e);
    const nucleo = sel.trim();
    if (!nucleo) return reemplazar(s, e, marca + marca, [s + marca.length, s + marca.length]);
    const izq = sel.slice(0, sel.indexOf(nucleo)), der = sel.slice(sel.indexOf(nucleo) + nucleo.length);
    // Si ya tiene la marca, se la quita.
    if (nucleo.startsWith(marca) && nucleo.endsWith(marca) && nucleo.length > marca.length * 2) {
      const sinMarca = nucleo.slice(marca.length, -marca.length);
      return reemplazar(s, e, izq + sinMarca + der, [s + izq.length, s + izq.length + sinMarca.length]);
    }
    reemplazar(s, e, izq + marca + nucleo + marca + der, [s + izq.length + marca.length, s + izq.length + marca.length + nucleo.length]);
  };

  const abrirEnlace = () => {
    const ta = area.current;
    if (ta) setEnlace({ url: "https://", inicio: ta.selectionStart, fin: ta.selectionEnd });
  };
  const aplicarEnlace = () => {
    if (!enlace) return;
    const dominio = dominioSeguro(enlace.url.trim());
    if (!dominio) return setError("El enlace debe empezar por https:// y ser una dirección válida.");
    const etiqueta = texto.slice(enlace.inicio, enlace.fin).trim().replace(/[[\]\n]/g, "") || dominio;
    setError(null);
    setEnlace(null);
    reemplazar(enlace.inicio, enlace.fin, `[${etiqueta.slice(0, 200)}](${enlace.url.trim()})`);
  };

  const insertar = (signo: "@" | "#") => {
    const ta = area.current;
    if (!ta) return;
    const s = ta.selectionStart;
    const antes = s > 0 && !/\s/.test(texto[s - 1]) ? " " : "";
    reemplazar(s, ta.selectionEnd, antes + signo);
  };

  const revisarToken = () => {
    const ta = area.current;
    if (!ta) return;
    const antes = texto.slice(0, ta.selectionStart);
    const m = antes.match(/(^|[\s(])@([\p{L}\p{N}_]{0,30})$/u);
    setToken(m ? { inicio: ta.selectionStart - m[2].length - 1, fin: ta.selectionStart, consulta: m[2] } : null);
  };
  useEffect(revisarToken, [texto]); // eslint-disable-line react-hooks/exhaustive-deps

  const elegir = (s: Sugerencia) => {
    if (!token) return;
    if (s.tipo === "persona") {
      reemplazar(token.inicio, token.fin, `@${s.nombre_usuario} `);
    } else {
      reemplazar(token.inicio, token.fin, `${s.nombre} `);
      setMencionadas((l) => (l.some((f) => f.id === s.id) || l.length >= 10 ? l : [...l, { id: s.id, nombre_completo: s.nombre, cargo: s.cargo }]));
    }
    setToken(null);
    setSugerencias([]);
  };

  const publicar = async () => {
    if (!textoPlano(texto).trim() || excedido || enviando) return;
    setEnviando(true);
    setError(null);
    try {
      // En una comunidad se publica por su propia ruta; las respuestas heredan la comunidad en la base.
      if (comunidad && !respondeA) {
        await api(`/social/v1/comunidades/${comunidad.id}/publicaciones`, { metodo: "POST", cuerpo: { texto, figuras_ids: mencionadas.map((f) => f.id) } });
      } else {
        await api("/social/v1/publicaciones", {
          metodo: "POST",
          cuerpo: { texto, responde_a_id: respondeA?.id ?? null, figuras_ids: mencionadas.map((f) => f.id) },
        });
      }
      setTexto("");
      setMencionadas([]);
      window.dispatchEvent(new Event("publicacion-creada"));
      cerrar();
    } catch (e) {
      setError(e instanceof ErrorApi ? e.message : "No se pudo publicar. Revisa tu conexión e inténtalo de nuevo.");
    } finally {
      setEnviando(false);
    }
  };

  const teclas = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (sugerencias.length && token) {
      if (e.key === "ArrowDown") { e.preventDefault(); return setActiva((a) => (a + 1) % sugerencias.length); }
      if (e.key === "ArrowUp") { e.preventDefault(); return setActiva((a) => (a - 1 + sugerencias.length) % sugerencias.length); }
      if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); return elegir(sugerencias[activa]); }
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); return setSugerencias([]); }
    }
    const mod = esMac ? e.metaKey : e.ctrlKey;
    if (mod && e.key.toLowerCase() === "b") { e.preventDefault(); envolver("**"); }
    else if (mod && e.key.toLowerCase() === "i") { e.preventDefault(); envolver("*"); }
    else if (mod && e.key.toLowerCase() === "k") { e.preventDefault(); abrirEnlace(); }
    else if (mod && e.key === "Enter") { e.preventDefault(); publicar(); }
  };

  const listaId = "sugerencias-mencion";
  return (
    <dialog ref={dialogo} className="compositor" onClose={cerrar} aria-labelledby="titulo-compositor">
      <form method="dialog" className="compositor__cuerpo" onSubmit={(e) => { e.preventDefault(); publicar(); }}>
        <div className="compositor__cabecera">
          <h2 id="titulo-compositor">{respondeA ? `Responder a @${respondeA.autor.nombre_usuario}` : comunidad ? `Publicar en ${comunidad.nombre}` : "Nueva publicación"}</h2>
          <button type="button" className="boton-texto" onClick={cerrar} aria-label="Cerrar">Cerrar</button>
        </div>
        {respondeA?.texto && <blockquote className="compositor__cita"><TextoEnriquecido texto={respondeA.texto} /></blockquote>}

        <div className="editor">
          <div className="editor__barra" role="toolbar" aria-label="Formato">
            <button type="button" onClick={() => envolver("**")} disabled={vista} aria-label="Negrita" title={`Negrita (${atajo("B")})`}><Icono d="M7 5h6a3.5 3.5 0 0 1 0 7H7zM7 12h7a3.5 3.5 0 0 1 0 7H7z" /></button>
            <button type="button" onClick={() => envolver("*")} disabled={vista} aria-label="Cursiva" title={`Cursiva (${atajo("I")})`}><Icono d="M14 5h-4M14 19h-4M13 5l-2 14" /></button>
            <button type="button" onClick={abrirEnlace} disabled={vista} aria-label="Enlace" title={`Enlace (${atajo("K")})`}><Icono d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" /></button>
            <span className="editor__separador" aria-hidden="true" />
            <button type="button" onClick={() => insertar("@")} disabled={vista} aria-label="Mencionar a una persona o figura pública" title="Mencionar (@)"><Icono d="M16 12a4 4 0 1 1-1.2-2.8M16 8v5.5a2.5 2.5 0 0 0 5 0V12a9 9 0 1 0-3.5 7.1" /></button>
            <button type="button" onClick={() => insertar("#")} disabled={vista} aria-label="Agregar una etiqueta" title="Etiqueta (#)"><Icono d="M9 4 7 20M17 4l-2 16M4 9h16M3 15h16" /></button>
            <span className="editor__espacio" />
            {MODO_DEMO && !vista && (
              <button type="button" className="editor__ejemplo" title="Modo demostración: llena el campo con un ejemplo; tú decides si lo publicas"
                onClick={() => { const e = alAzar(respondeA ? RESPUESTAS : PUBLICACIONES, ultimoEjemplo.current); ultimoEjemplo.current = e; setTexto(e.texto); area.current?.focus(); }}>
                <Icono d="M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zM8.5 8.5h.01M15.5 8.5h.01M12 12h.01M8.5 15.5h.01M15.5 15.5h.01" />
                Ejemplo al azar
              </button>
            )}
            <button type="button" className="editor__vista" onClick={() => setVista(!vista)} aria-pressed={vista} disabled={!texto.trim()}>
              {vista ? "Editar" : "Vista previa"}
            </button>
          </div>

          {vista ? (
            <div className="editor__vista-previa publicacion__texto" aria-label="Vista previa"><TextoEnriquecido texto={texto} /></div>
          ) : (
            <div className="editor__campo">
              <textarea ref={area} className="compositor__texto" value={texto} maxLength={MAXIMO_CON_MARCAS} autoFocus rows={5}
                placeholder="¿Qué quieres decir? Usa @ para mencionar y # para etiquetar."
                aria-label="Texto de la publicación" aria-describedby="cuenta-visible"
                aria-autocomplete="list" aria-controls={sugerencias.length ? listaId : undefined}
                aria-activedescendant={sugerencias.length ? `${listaId}-${activa}` : undefined}
                onChange={(e) => setTexto(e.target.value)} onKeyDown={teclas} onClick={revisarToken}
                onKeyUp={(e) => { if (!e.key.startsWith("Arrow")) revisarToken(); }} />
              {sugerencias.length > 0 && token && (
                <ul className="sugerencias" id={listaId} role="listbox" aria-label="Sugerencias para mencionar">
                  {sugerencias.map((s, i) => (
                    <li key={s.tipo === "persona" ? s.nombre_usuario : s.id} id={`${listaId}-${i}`} role="option" aria-selected={i === activa}
                      className={i === activa ? "activa" : ""} onMouseDown={(e) => { e.preventDefault(); elegir(s); }} onMouseEnter={() => setActiva(i)}>
                      {s.tipo === "persona" ? (
                        <><Avatar nombre={s.nombre_visible} foto={s.foto} /><span><strong>{s.nombre_visible}</strong><small>@{s.nombre_usuario}</small></span></>
                      ) : (
                        <><span className="sugerencias__figura" aria-hidden="true">{s.nombre.slice(0, 1)}</span><span><strong>{s.nombre}</strong><small>Figura pública{s.cargo ? ` · ${s.cargo}` : ""}</small></span></>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {enlace && (
            <div className="editor__enlace" role="group" aria-label="Agregar enlace">
              <input value={enlace.url} onChange={(e) => setEnlace({ ...enlace, url: e.target.value })} autoFocus aria-label="Dirección del enlace (https)"
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); aplicarEnlace(); } if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); setEnlace(null); } }} />
              <button type="button" className="boton boton--pequeno" onClick={aplicarEnlace}>Aplicar</button>
              <button type="button" className="boton-texto" onClick={() => setEnlace(null)}>Cancelar</button>
            </div>
          )}
        </div>

        {mencionadas.length > 0 && (
          <p className="compositor__mencionadas">
            Menciona a{" "}
            {mencionadas.map((f, i) => (
              <span key={f.id}>
                {i > 0 && ", "}<strong>{f.nombre_completo}</strong>
                <button type="button" className="compositor__quitar" onClick={() => setMencionadas((l) => l.filter((x) => x.id !== f.id))}
                  aria-label={`Quitar la mención de ${f.nombre_completo}`}>×</button>
              </span>
            ))}
          </p>
        )}

        <div className="compositor__pie">
          <p className="compositor__nota">
            {comunidad?.privacidad === "privada" && !respondeA && <><strong>Solo la verán los integrantes de {comunidad.nombre}.</strong> </>}
            {(respondeA?.comunidad?.privacidad === "privada") && <><strong>Solo la verán los integrantes de {respondeA.comunidad.nombre}.</strong> </>}
            Las cifras sobre los 8 indicadores oficiales se leen junto a su dato oficial. Las opiniones se publican tal cual.
          </p>
          <span id="cuenta-visible" aria-live="polite"
            className={`compositor__cuenta cifra${excedido ? " compositor__cuenta--excedido" : visibles > MAXIMO_VISIBLE - 60 ? " compositor__cuenta--poco" : ""}`}>
            {excedido ? `${visibles - MAXIMO_VISIBLE} de más` : `${visibles} / ${MAXIMO_VISIBLE}`}
          </span>
          <button className="boton" disabled={!textoPlano(texto).trim() || excedido || enviando} title={`Publicar (${atajo("Enter")})`}>
            {enviando ? "Publicando…" : "Publicar"}
          </button>
        </div>
        {error && <p className="aviso" role="alert">{error}</p>}
      </form>
    </dialog>
  );
}
