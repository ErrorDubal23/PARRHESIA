// Análisis de enlaces en segundo plano: los lleva la app completa, no la página "Analizar". La persona puede
// ir al feed o a cualquier otra parte; un aviso flotante muestra el tiempo y cuántas cifras están listas, y al
// terminar avisa con un enlace al resultado. Los análisis pendientes se recuerdan en este navegador (si el
// almacenamiento falla, todo sigue funcionando mientras la pestaña esté abierta). La verificación corre en el
// servidor: esto solo pregunta cada pocos segundos cómo va.
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { api, ErrorApi } from "../api";
import * as I from "./Iconos";

type Fase = "leyendo" | "verificando" | "listo" | "error";
interface Tarea {
  clave: string;             // local, mientras no hay id
  id?: string;               // id del análisis en el servidor
  etiqueta: string;          // dominio o "Texto pegado"
  inicio: number;            // ms
  fin?: number;
  fase: Fase;
  total: number;
  listos: number;
  error?: string;
}
interface Contexto {
  iniciar: (pedido: { url: string } | { texto: string }) => Promise<string>;
}

const ALMACEN = "parrhesia.analisis";
const CADA_MS = 3000;
const Ctx = createContext<Contexto | null>(null);
export const useAnalisis = () => useContext(Ctx)!;

const leerGuardadas = (): Tarea[] => {
  try { return JSON.parse(localStorage.getItem(ALMACEN) ?? "[]"); } catch { return []; }
};
const guardar = (tareas: Tarea[]) => {
  try { localStorage.setItem(ALMACEN, JSON.stringify(tareas.filter((t) => t.id && t.fase !== "error"))); } catch { /* sin almacenamiento */ }
};
const etiquetaDe = (pedido: { url: string } | { texto: string }) => {
  if ("texto" in pedido) return "Texto pegado";
  try { return new URL(pedido.url).hostname.replace(/^www\./, ""); } catch { return "Enlace"; }
};
const reloj = (ms: number) => {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

export function AnalisisProvider({ children }: { children: ReactNode }) {
  const [tareas, setTareas] = useState<Tarea[]>(leerGuardadas);
  const [ahora, setAhora] = useState(Date.now());
  const enCurso = useRef(false);
  const actualizar = useCallback((clave: string, cambio: Partial<Tarea>) =>
    setTareas((ts) => ts.map((t) => (t.clave === clave ? { ...t, ...cambio } : t))), []);

  useEffect(() => guardar(tareas), [tareas]);

  const iniciar = useCallback(async (pedido: { url: string } | { texto: string }) => {
    const clave = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    setTareas((ts) => [...ts, { clave, etiqueta: etiquetaDe(pedido), inicio: Date.now(), fase: "leyendo", total: 0, listos: 0 }]);
    try {
      const r = await api<{ id: string }>("/verificacion/v1/enlaces", { metodo: "POST", cuerpo: pedido });
      actualizar(clave, { id: r.id, fase: "verificando" });
      return r.id;
    } catch (err) {
      // En "Analizar" el error lo muestra la página; en cualquier otra, el aviso flotante.
      actualizar(clave, { fase: "error", fin: Date.now(),
        error: err instanceof ErrorApi ? err.message : "No se pudo leer. Revisa tu conexión." });
      throw err;
    }
  }, [actualizar]);

  // Un solo sondeo para todas las tareas en curso, y el reloj del aviso.
  const activas = tareas.filter((t) => t.fase === "leyendo" || t.fase === "verificando").length;
  useEffect(() => {
    if (!activas) return;
    const reloj = setInterval(() => setAhora(Date.now()), 1000);
    const sondeo = setInterval(async () => {
      if (enCurso.current) return;
      enCurso.current = true;
      try {
        const pendientes = tareas.filter((t) => t.fase === "verificando" && t.id);
        for (const t of pendientes) {
          try {
            const e = await api<{ estado: string; fragmentos: { estado: string }[] }>(`/verificacion/v1/enlaces/${t.id}`);
            const listos = e.fragmentos.filter((f) => f.estado !== "pendiente").length;
            actualizar(t.clave, e.estado === "pendiente"
              ? { total: e.fragmentos.length, listos }
              : { total: e.fragmentos.length, listos: e.fragmentos.length, fase: "listo", fin: Date.now() });
          } catch (err) {
            if (err instanceof ErrorApi && err.estado === 404) actualizar(t.clave, { fase: "error", error: "Ese análisis ya no existe." });
          }
        }
      } finally {
        enCurso.current = false;
      }
    }, CADA_MS);
    return () => { clearInterval(reloj); clearInterval(sondeo); };
  }, [activas, tareas, actualizar]);

  return (
    <Ctx.Provider value={{ iniciar }}>
      {children}
      <AvisosAnalisis tareas={tareas} ahora={ahora} cerrar={(clave) => setTareas((ts) => ts.filter((t) => t.clave !== clave))} />
    </Ctx.Provider>
  );
}

function AvisosAnalisis({ tareas, ahora, cerrar }: { tareas: Tarea[]; ahora: number; cerrar: (clave: string) => void }) {
  const { pathname } = useLocation();
  // Si la persona ya está viendo un análisis terminado, su aviso sobra.
  useEffect(() => {
    tareas.filter((t) => t.fase === "listo" && t.id && pathname === `/analizar/${t.id}`).forEach((t) => cerrar(t.clave));
  }, [pathname, tareas, cerrar]);
  useEffect(() => {
    if (pathname === "/analizar") tareas.filter((t) => t.fase === "error").forEach((t) => cerrar(t.clave));
  }, [pathname, tareas, cerrar]);
  const visibles = tareas.filter((t) => !(t.fase === "error" && pathname === "/analizar"));
  if (!visibles.length) return null;
  return (
    <div className="avisos-analisis" role="status" aria-live="polite">
      {visibles.map((t) => (
        <div key={t.clave} className={`aviso-analisis aviso-analisis--${t.fase}`}>
          <span className="aviso-analisis__icono" aria-hidden="true">{t.fase === "listo" ? <I.Util width={16} /> : <I.Enlace width={15} />}</span>
          <span className="aviso-analisis__texto">
            <strong>{t.fase === "listo" ? "Análisis listo" : t.fase === "leyendo" ? "Leyendo la noticia"
              : t.fase === "error" ? "No se pudo analizar" : "Analizando cifras"}</strong>
            <small>
              {t.etiqueta} · <span className="cifra">{reloj((t.fin ?? ahora) - t.inicio)}</span>
              {t.fase === "verificando" && t.total > 0 && <> · <span className="cifra">{t.listos} de {t.total}</span> listas</>}
              {t.fase === "listo" && t.total === 0 && " · sin cifras de los indicadores"}
              {t.fase === "error" && <> · {t.error}</>}
            </small>
          </span>
          {t.id && (t.fase === "listo" || pathname !== `/analizar/${t.id}`) && (
            <Link to={`/analizar/${t.id}`} className="aviso-analisis__ir">{t.fase === "listo" ? "Ver" : "Abrir"}</Link>
          )}
          {t.fase !== "leyendo" && (
            <button type="button" className="aviso-analisis__cerrar" onClick={() => cerrar(t.clave)}
              aria-label={t.fase === "listo" ? "Cerrar aviso" : "Dejar de seguir (el análisis sigue en el servidor)"}
              title={t.fase === "listo" ? "Cerrar" : "Dejar de seguir; el análisis sigue en el servidor"}>×</button>
          )}
        </div>
      ))}
    </div>
  );
}
